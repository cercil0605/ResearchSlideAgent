import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree
from pptx import Presentation

from research_slide_agent.engine import LayoutError, generate, template_info, verify
from research_slide_agent.models import PrototypeParagraph, SlideSpec
from research_slide_agent.prototypes import query, replace_text

TEMPLATE = Path("templates/lab-template.pptx")


def example(nodes, edges, direction="horizontal"):
    raw = json.loads(Path("examples/research-format.slidespec.json").read_text())
    item = next(s for s in raw["slides"] if s["prototype_id"] == "method")
    item.update(slide_order=1, diagram_spec={"kind": "flowchart", "direction": direction,
                                          "nodes": nodes, "edges": edges})
    raw.update(purpose_mode="general", slides=[item])
    return SlideSpec.model_validate(raw)


@pytest.mark.parametrize("direction", ["horizontal", "vertical"])
@pytest.mark.parametrize("pattern", ["sequence", "branch", "merge", "comparison"])
def test_native_explanation_preserves_relationships(tmp_path, direction, pattern):
    patterns = {
        "sequence": (["入力", "処理", "出力"], [(0, 1), (1, 2)]),
        "branch": (["条件", "パス", "シュート"], [(0, 1), (0, 2)]),
        "merge": (["実行1", "実行2", "実行3", "平均"], [(0, 3), (1, 3), (2, 3)]),
        "comparison": (["正解図", "生成図", "共通要素", "割合"], [(0, 2), (1, 2), (2, 3)]),
    }
    words, links = patterns[pattern]
    nodes = [{"id": str(i), "text": t} for i, t in enumerate(words)]
    if pattern == "branch":
        nodes[0]["kind"] = "decision"
    edges = [{"source": str(a), "target": str(b)} for a, b in links]
    if pattern == "branch":
        edges[0]["label"], edges[1]["label"] = "はい", "いいえ"
    spec = example(nodes, edges, direction)
    output = tmp_path / f"{pattern}-{direction}.pptx"
    manifest = generate(TEMPLATE, spec, output)
    slide = Presentation(output).slides[0]
    named = {s.name: s for s in slide.shapes}
    assert "図の差し替え枠" not in named
    assert not any(s.has_chart for s in slide.shapes)
    assert not any(s.shape_type == 13 for s in slide.shapes)  # Native shapes, not a bitmap diagram.
    for i, (a, b) in enumerate(links):
        connector = named[f"rsa:edge:{i}"]._element
        assert connector.xpath(".//a:stCxn/@id") == [str(named[f"rsa:node:{a}"].shape_id)]
        assert connector.xpath(".//a:endCxn/@id") == [str(named[f"rsa:node:{b}"].shape_id)]
        assert connector.xpath(".//a:tailEnd/@type") == ["triangle"]
    for i in range(len(words)):
        label = named[f"rsa:node-label:{i}"]
        assert label.text == words[i]
        assert label.text_frame.paragraphs[0].runs[0].font.size.pt == 15
    if pattern == "branch":
        assert named["rsa:node:0"]._element.xpath("./p:spPr/a:prstGeom/@prst") == ["diamond"]
        assert named["rsa:edge-label:0"].text == "はい"
    assert verify(TEMPLATE, output, spec, manifest)["status"] == "passed"
    with ZipFile(TEMPLATE) as source, ZipFile(output) as target:
        for name in source.namelist():
            if name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")):
                assert source.read(name) == target.read(name)


def test_wrong_connector_is_rejected_by_verification(tmp_path):
    spec = example([{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
                   [{"source": "a", "target": "b"}])
    original, corrupted = tmp_path / "good.pptx", tmp_path / "bad.pptx"
    manifest = generate(TEMPLATE, spec, original)
    with ZipFile(original) as src, ZipFile(corrupted, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "ppt/slides/slide1.xml":
                root = etree.fromstring(data)
                query(root, ".//p:cxnSp//a:endCxn")[0].set("id", "1000")
                data = etree.tostring(root)
            dst.writestr(name, data)
    with pytest.raises(LayoutError, match="FORMAT_OR_CONTENT_MISMATCH"):
        verify(TEMPLATE, corrupted, spec, manifest)


@pytest.mark.parametrize("edges", [
    [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
    [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}, {"source": "a", "target": "c"}],
])
def test_unsupported_graph_never_publishes_partial_file(tmp_path, edges):
    spec = example([{"id": key, "text": key} for key in "abc"], edges)
    output = tmp_path / "unsupported.pptx"
    with pytest.raises(LayoutError):
        generate(TEMPLATE, spec, output)
    assert not output.exists()


@pytest.mark.parametrize("prefix", ["・", "•", "- "])
@pytest.mark.parametrize("rich", [False, True])
def test_duplicate_bullet_in_plain_or_split_runs_is_rejected(tmp_path, prefix, rich):
    spec = example([{"id": "a", "text": "A"}], [])
    value = {"runs": [{"text": prefix}, {"text": "本文"}]} if rich else {"text": prefix + "本文"}
    spec.slides[0].replacements["手法の特徴"] = [PrototypeParagraph.model_validate(value)]
    output = tmp_path / "duplicate.pptx"
    with pytest.raises(ValueError, match="DUPLICATE_BULLET"):
        generate(TEMPLATE, spec, output)
    assert not output.exists()


def test_legitimate_text_and_nonbullet_shapes_are_unchanged():
    prs = Presentation(TEMPLATE)
    body = next(s for s in prs.slides[5].shapes if s.name == "手法の特徴")
    tx = etree.fromstring(body._element.txBody.xml)
    replace_text(tx, [PrototypeParagraph(text="発話・動作"), PrototypeParagraph(text="-1.2点")])
    assert query(tx, ".//a:t/text()") == ["発話・動作", "-1.2点"]
    replace_text(tx, [PrototypeParagraph.model_validate({"runs": [{"text": "-"}, {"text": "1.2点"}]})])
    assert query(tx, ".//a:t/text()") == ["-", "1.2点"]
    caption = next(s for s in prs.slides[5].shapes if s.name == "図題")
    tx = etree.fromstring(caption._element.txBody.xml)
    replace_text(tx, [PrototypeParagraph(text="・記号の例")])
    assert query(tx, ".//a:t/text()") == ["・記号の例"]


def test_client_can_discover_diagram_support():
    capabilities = template_info(TEMPLATE)["diagram_capabilities"]
    assert capabilities["native_connectors"] and capabilities["branches_and_merges"]
    assert capabilities["forward_adjacent_stages_only"]
