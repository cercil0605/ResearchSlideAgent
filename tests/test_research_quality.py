"""Regression cases from the accepted construction-paper revision; no LLM quality claim."""

import json
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image
from pptx import Presentation
from pydantic import ValidationError

from research_slide_agent.engine import LayoutError, generate, template_info, verify
from research_slide_agent.models import SlideSpec
from research_slide_agent.prototypes import authoring_feedback

TEMPLATE = Path("templates/lab-template.pptx")


def quality():
    return json.loads(Path("examples/research-quality.slidespec.json").read_text())


def page(raw, section):
    return next(s for s in raw["slides"] if s["section"] == section)


@pytest.mark.parametrize("failure", ["order", "early_example", "empty_purpose", "missing_purpose",
                                     "missing_approach", "missing_novelty", "missing_map", "missing_section",
                                     "missing_metric", "unknown_target", "duplicate_target"])
def test_reject_incomplete_research_explanations(failure):
    raw = quality()
    objective = page(raw, "objective")
    if failure == "order":
        background, related = page(raw, "background"), page(raw, "related")
        background["slide_order"], related["slide_order"] = related["slide_order"], background["slide_order"]
    elif failure == "early_example":
        example = deepcopy(page(raw, "method"))
        example.update(slide_id="early-example", section="example")
        raw["slides"].insert(2, example)
        for index, slide in enumerate(raw["slides"], 1):
            slide["slide_order"] = index
    elif failure == "empty_purpose":
        objective["replacements"]["研究目的"] = []
    elif failure.startswith("missing_") and failure.split("missing_")[1] in {"purpose", "approach", "novelty"}:
        del objective["content_map"][failure.split("missing_")[1]]
    elif failure == "missing_map":
        objective["content_map"] = {}
    elif failure == "missing_section":
        objective["paper_section"] = ""
    elif failure == "missing_metric":
        del page(raw, "experiment")["content_map"]["metric"]
    elif failure == "unknown_target":
        objective["content_map"]["purpose"] = ["存在しない欄"]
    else:
        objective["content_map"]["purpose"] = ["研究目的", "研究目的"]
    with pytest.raises(ValidationError):
        SlideSpec.model_validate(raw)


@pytest.mark.parametrize("target", ["小見出し：研究目的", "図題"])
def test_headings_and_captions_cannot_stand_in_for_explanations(tmp_path, target):
    raw = quality()
    item = page(raw, "objective") if target.startswith("小見出し") else page(raw, "overview")
    item["replacements"][target] = [{"text": "目的という見出し"}]
    item["content_map"]["purpose"] = [target]
    spec = SlideSpec.model_validate(raw)
    with pytest.raises(LayoutError, match="explanatory body slots"):
        authoring_feedback(TEMPLATE, spec)
    with pytest.raises(LayoutError, match="explanatory body slots"):
        generate(TEMPLATE, spec, tmp_path / "bad.pptx")
    assert not (tmp_path / "bad.pptx").exists()


def test_multiple_experiments_and_appendix_still_work():
    raw = quality()
    for section in ["experiment", "results", "discussion"]:
        duplicate = deepcopy(page(raw, section))
        duplicate["slide_id"] += "-second"
        raw["slides"].insert(-1, duplicate)
    appendix = deepcopy(page(raw, "method"))
    appendix.update(slide_id="appendix", part="appendix")
    raw["slides"].append(appendix)
    for index, slide in enumerate(raw["slides"], 1):
        slide["slide_order"] = index
    assert SlideSpec.model_validate(raw).slides[-1].part == "appendix"


def test_quality_example_keeps_four_joint_table_and_mixed_evidence_editable(tmp_path):
    spec = SlideSpec.model_validate(quality())
    out = tmp_path / "quality.pptx"
    report = generate(TEMPLATE, spec, out)
    assert verify(TEMPLATE, out, spec, report)["status"] == "passed"
    deck = Presentation(out)
    mixed = deck.slides[6]
    assert any(s.has_table for s in mixed.shapes)
    assert any(s.name.startswith("rsa:node:") for s in mixed.shapes)
    table = next(s.table for s in mixed.shapes if s.has_table)
    assert len(table.columns) == 2 and len(table.rows) == 4
    results = next(s.table for s in deck.slides[8].shapes if s.has_table)
    assert len(results.rows) == 5
    assert [results.cell(i, 0).text for i in range(1, 5)] == ["旋回体", "ブーム", "アーム", "バケット"]
    assert all(results.cell(i, 0).text_frame.paragraphs[0].runs[0].font.size.pt == 16 for i in range(1, 5))
    feedback = authoring_feedback(TEMPLATE, spec)
    objective = next(p for p in feedback["pages"] if p["section"] == "objective")
    assert objective["content_evidence"]["purpose"]["研究目的"] == ["操作員による手順の確認・修正を支援"]
    assert feedback["content_review"] == feedback["visual_review"] == "not_performed"
    with ZipFile(TEMPLATE) as source, ZipFile(out) as target:
        for name in source.namelist():
            if name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")):
                assert source.read(name) == target.read(name)


@pytest.mark.parametrize("composition", ["text_visual", "table_visual", "two_images"])
def test_original_images_and_captions_survive_composition_and_verification(tmp_path, composition):
    raw = quality()
    item = deepcopy(next(s for s in raw["slides"] if s.get("composition") == (
        "table_visual" if composition == "table_visual" else "text_visual")))
    item.update(slide_order=1, composition=composition)
    item.pop("diagram_spec")
    if composition == "two_images":
        item["replacements"]["手法の説明"] = [{"text": "原図の操作を比較"}]
    count = 2 if composition == "two_images" else 1
    item["image_references"] = [{"id": f"image{i}", "source_id": f"picture{i}", "caption": f"原図{i + 1}"}
                                 for i in range(count)]
    item["replacements"]["図題"] = [{"text": "\n".join(f"原図{i + 1}" for i in range(count)) + " [試験 '26]"}]
    item["citations"] = [{"source": {"source_id": f"picture{i}", "locator": "合成試験画像"},
                          "author": "試験", "year": 2026, "target_id": f"image{i}"} for i in range(count)]
    if composition == "table_visual":
        item["citations"].append({**item["citations"][0], "target_id": "table"})
    raw.update(purpose_mode="general", slides=[item])
    images = {}
    for i in range(count):
        path = tmp_path / f"picture{i}.png"
        Image.new("RGB", (300, 200), ["gray", "blue"][i]).save(path)
        images[f"picture{i}"] = path
    spec = SlideSpec.model_validate(raw)
    out = tmp_path / "pictures.pptx"
    report = generate(TEMPLATE, spec, out, images)
    assert verify(TEMPLATE, out, spec, report, images)["status"] == "passed"
    slide = Presentation(out).slides[0]
    pictures = [s for s in slide.shapes if s.name.startswith("rsa:image")]
    assert len(pictures) == count
    assert [s.image.blob for s in pictures] == [p.read_bytes() for p in images.values()]
    assert all(f"原図{i + 1}" in "".join(s.text for s in slide.shapes if s.has_text_frame) for i in range(count))
    if count == 2:
        assert pictures[0].left + pictures[0].width < pictures[1].left
    images["picture0"].write_bytes(images["picture0"].read_bytes() + b"changed")
    with pytest.raises(LayoutError, match="MISMATCH|Original image differs|relationships differ"):
        verify(TEMPLATE, out, spec, report, images)


@pytest.mark.parametrize("failure", ["wrong_prototype", "missing_table", "two_visuals", "one_image",
                                     "legacy_composition", "too_many_rows", "hidden_explanation"])
def test_unsupported_compositions_fail_without_publishing(tmp_path, failure):
    raw = quality()
    item = deepcopy(next(s for s in raw["slides"] if s.get("composition") == "table_visual"))
    item.update(slide_order=1)
    raw.update(purpose_mode="general", slides=[item])
    expected = ValidationError
    if failure == "wrong_prototype":
        item["prototype_id"] = "results_table"
    elif failure == "missing_table":
        item.pop("table_spec")
    elif failure == "two_visuals":
        item["composition"] = "canonical"
    elif failure == "one_image":
        item.update(composition="two_images", table_spec=None, diagram_spec=None)
        item["content_map"] = {}
        item["image_references"] = [{"id": "image", "source_id": "image", "caption": "図"}]
    elif failure == "legacy_composition":
        raw["schema_version"] = "1.2"
    elif failure == "too_many_rows":
        item["table_spec"]["rows"] *= 4
        expected = LayoutError
    else:
        item["replacements"]["手法の説明"] = [{"text": "表の下へ隠してはいけない本文"}]
        expected = LayoutError
    with pytest.raises(expected):
        spec = SlideSpec.model_validate(raw)
        generate(TEMPLATE, spec, tmp_path / "bad.pptx")
    assert not (tmp_path / "bad.pptx").exists()


@pytest.mark.parametrize("version", ["1.0", "1.1", "1.2"])
def test_unsupported_schema_versions_are_rejected(version):
    raw = quality()
    raw["schema_version"] = version
    with pytest.raises(ValidationError, match="1.3"):
        SlideSpec.model_validate(raw)



def test_template_catalog_advertises_new_contract():
    info = template_info(TEMPLATE)
    assert info["recommended_schema_version"] == "1.3"
    assert set(info["compositions"]) == {"text_visual", "table_visual", "two_images"}
    assert set(info["required_content_roles"]["objective"]) == {"purpose", "approach", "novelty"}


def test_construction_paper_revision_regression(tmp_path):
    spec = SlideSpec.model_validate_json(Path("tests/fixtures/construction-regression.slidespec.json").read_text())
    path = tmp_path / "construction.pptx"
    generate(TEMPLATE, spec, path)
    slides = Presentation(path).slides
    objective_text = "".join(s.text for s in slides[0].shapes if s.has_text_frame)
    assert "確認・修正" in objective_text and "実演から生成" in objective_text
    assert "直列／並列" in objective_text
    table = next(s.table for s in slides[1].shapes if s.has_table)
    assert table.cell(2, 1).text.replace("\v", "\n") == "直列モード\n速度・目標角度\nブロック内で待機"
    assert table.cell(3, 1).text.replace("\v", "\n") == "並列モード\n速度・目標角度\n区間時間Tだけ待機"
    assert table.rows[2].height > 538163  # Three lines grow the row, without shrinking type.
    errors = next(s.table for s in slides[2].shapes if s.has_table)
    assert len(errors.rows) == 5 and errors.cell(4, 0).text == "バケット"
    assert errors.cell(4, 1).text == "5.506" and errors.cell(4, 2).text == "5.498"
    assert "実際の掘削精度は未評価" in "".join(s.text for s in slides[2].shapes if s.has_text_frame)


@pytest.mark.parametrize("target", ["diagram", "table"])
def test_mixed_evidence_retains_each_citation_requirement(target):
    raw = json.loads(Path("tests/fixtures/construction-regression.slidespec.json").read_text())
    item = raw["slides"][1]
    item["citations"] = [c for c in item["citations"] if c["target_id"] != target]
    with pytest.raises(ValidationError, match="Sourced visual requires a citation"):
        SlideSpec.model_validate(raw)


@pytest.mark.parametrize("missing", ["all", "first", "second", "duplicate_first"])
def test_two_images_require_a_citation_for_each_id(missing):
    raw = quality()
    item = deepcopy(next(s for s in raw["slides"] if s.get("composition") == "text_visual"))
    item.update(slide_order=1, composition="two_images")
    item.pop("diagram_spec")
    item["image_references"] = [{"id": f"image{i}", "source_id": f"picture{i}", "caption": f"原図{i}"}
                                 for i in range(2)]
    cites = [{"source": {"source_id": f"picture{i}", "locator": f"figure {i}"},
              "target_id": f"image{i}", "author": "試験", "year": 2026} for i in range(2)]
    item["citations"] = [] if missing == "all" else [cites[1]] if missing == "first" else [cites[0]]
    if missing == "duplicate_first":
        item["citations"] *= 2
    raw.update(purpose_mode="general", slides=[item])
    with pytest.raises(ValidationError, match="Each image requires a citation"):
        SlideSpec.model_validate(raw)


def test_direct_store_save_cannot_persist_heading_as_content(store):
    from research_slide_agent.sample import sample_spec

    project = store.create("alice")
    spec = sample_spec(project["id"], 1)
    store.save_spec("alice", project["id"], spec, 0)
    raw = spec.model_dump()
    raw["spec_version"] = 2
    slide = raw["slides"][0]
    slide["replacements"]["小見出し：社会的な問題・ニーズ"] = [{"text": "課題という見出し"}]
    slide["content_map"] = {"problem": ["小見出し：社会的な問題・ニーズ"]}
    replacement = SlideSpec.model_validate(raw)  # Valid fields, invalid template-aware content target.
    with pytest.raises(LayoutError, match="explanatory body slots"):
        store.save_spec("alice", project["id"], replacement, 1)
    current = store.project("alice", project["id"])
    assert current["version"] == 1 and current["spec"] == spec.model_dump()
    with store.connect() as con:
        assert con.execute("SELECT count(*) FROM specs WHERE project=?", (project["id"],)).fetchone()[0] == 1


@pytest.mark.parametrize("field,value", [
    ("layout_id", 1), ("key_message", "old field"), ("body_blocks", []), ("chart_spec", None),
])
def test_removed_legacy_fields_are_rejected(field, value):
    raw = quality()
    raw["slides"][0][field] = value
    with pytest.raises(ValidationError, match="Extra inputs"):
        SlideSpec.model_validate(raw)
