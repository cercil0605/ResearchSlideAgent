"""Fit estimates calibrated on PowerPoint/LibreOffice PDFs (docs/verified.md, 2026-11-18)."""

import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

from research_slide_agent.engine import LayoutError, generate, template_info
from research_slide_agent.models import SlideSpec
from research_slide_agent.prototypes import authoring_feedback, query, wrapped_lines

TEMPLATE = Path("templates/lab-template.pptx")


def spec_with(item):
    raw = json.loads(Path("examples/research-format.slidespec.json").read_text())
    base = next(s for s in raw["slides"] if s["prototype_id"] == item.get("prototype_id", "method"))
    raw.update(purpose_mode="general", slides=[{**base, "slide_order": 1, "content_map": {}, **item}])
    return SlideSpec.model_validate(raw)


def table_visual(rows):
    """The table that overlapped the heading below it in PowerPoint (Transformer deck, page 4)."""
    return spec_with({
        "prototype_id": "method", "composition": "table_visual", "image_references": [], "citations": [],
        "source_references": [],
        "replacements": {"小見出し：［提案手法の名称］": [{"text": "整理"}], "小見出し：特徴": [{"text": "残る課題"}],
                         "手法の特徴": [{"text": "畳み込みは離れた単語ほど多くの層が必要"}], "図題": [{"text": "比較"}]},
        "table_spec": {"columns": ["研究", "方法", "到達点・残件"], "rows": rows},
        "diagram_spec": {"kind": "comparison", "nodes": [{"id": "a", "text": "比例"}, {"id": "b", "text": "一定"}]},
    })


def test_wrapping_keeps_latin_words_and_counts_whole_glyphs():
    # Measured in PowerPoint: a 77pt cell shows "ByteNet" / "・" / "ConvS2S".
    assert wrapped_lines("ByteNet・ConvS2S", 16, 77) == 3
    # Five 16pt glyphs fit in 85pt; total width / line width (1.9) would have said 2 lines.
    assert wrapped_lines("あいうえおかきくけ", 16, 85) == 2
    assert wrapped_lines("あいうえおかきくけこさ", 16, 85) == 3
    # Closing punctuation never starts a line; it moves with the preceding glyph.
    assert wrapped_lines("あいうえ。", 16, 64) == 2


def test_table_rows_that_overlapped_in_powerpoint_are_rejected_with_amounts(tmp_path):
    rows = [["ByteNet・ConvS2S", "畳み込みで全位置を並列計算", "距離に応じ演算数が増加"],
            ["自己注意の既存研究", "1文内の位置同士を注意で関係付け", "読解・要約などで成功"],
            ["End-to-end記憶網", "再帰的な注意機構", "簡単な質問応答で良好"]]
    with pytest.raises(LayoutError, match="TABLE_OVERFLOW: wrapped cells need") as error:
        generate(TEMPLATE, table_visual(rows), tmp_path / "a.pptx")
    problem = next(p for p in error.value.problems if p["code"] == "TABLE_OVERFLOW")
    assert problem["height_needed_inches"] > problem["height_available_inches"]
    assert problem["page"] == 1 and problem["wrapped_rows"]
    shorter = [["ByteNet等", "畳み込みで並列計算", "距離で演算数が増加"],
               ["自己注意", "文内の位置を関係付け", "読解・要約で成功"],
               ["記憶網", "再帰的な注意", "簡単な質問応答"]]
    generate(TEMPLATE, table_visual(shorter), tmp_path / "b.pptx")


def test_single_line_rows_keep_the_template_height(tmp_path):
    generate(TEMPLATE, table_visual([["A", "B", "C"]]), tmp_path / "t.pptx")
    with ZipFile(tmp_path / "t.pptx") as z:
        rows = query(etree.fromstring(z.read("ppt/slides/slide1.xml")), ".//a:tr/@h")
    with ZipFile(TEMPLATE) as z:
        template = query(etree.fromstring(z.read("ppt/slides/slide9.xml")), ".//a:tr/@h")
    assert rows == template[:2]


def test_row_limit_matches_what_fits_and_is_reported():
    info = template_info(TEMPLATE)
    entry = next(p for p in info["prototypes"] if p["prototype_id"] == "results_table")
    assert entry["table"]["max_body_rows"] == 4
    assert info["slot_capacity"]["results_table"]["canonical"]["table"]["max_body_rows"] == 4
    spec = spec_with({"prototype_id": "results_table", "replacements": {"表の結果要点": [{"text": "要点"}]},
                      "table_spec": {"columns": ["a", "b", "c"], "rows": [["1", "2", "3"]] * 5},
                      "image_references": [], "citations": [], "source_references": []})
    with pytest.raises(LayoutError, match="5 body rows, at most 4 fit"):
        generate(TEMPLATE, spec, Path("/nonexistent/never-written.pptx"))


def test_capacity_lists_relocated_composition_slots():
    capacity = template_info(TEMPLATE)["slot_capacity"]["method"]
    # 0.55 in holds two 16pt lines of one paragraph; a second paragraph adds 9pt and does not fit.
    assert capacity["text_visual"]["手法の特徴"]["lines"] == 2
    assert capacity["text_visual"]["手法の特徴"]["paragraph_gap_pt"] == 9
    assert capacity["text_visual"]["手法の特徴"]["box_inches"] == [6.7, 0.55]
    assert capacity["canonical"]["手法の特徴"]["box_inches"][0] < 2.1
    assert "手法の説明" not in capacity["table_visual"] and "table" in capacity["table_visual"]


def test_every_overflow_on_a_page_is_reported_at_save_time():
    spec = spec_with({"composition": "text_visual", "replacements": {
        "小見出し：［提案手法の名称］": [{"text": "名称"}], "小見出し：特徴": [{"text": "特徴"}],
        "手法の特徴": [{"text": "一行目"}, {"text": "二段落目は段落の間隔が加わるので一行でも収まらない"}],
        "図題": [{"text": "図題が長すぎて二行目に入り枠を超えてしまう場合の例です"}],
        "手法の説明": [{"text": "入力"}]}})
    feedback = authoring_feedback(TEMPLATE, spec, images={})
    page = feedback["pages"][0]
    targets = {p["target"] for p in page["fit_problems"]}
    assert {"手法の特徴", "図題"} <= targets
    assert all(p["lines_needed"] > p["lines_available"] for p in page["fit_problems"])
    assert next(p for p in page["fit_problems"] if p["target"] == "手法の特徴")["paragraphs"] == 2
    assert any(w["code"] == "LAYOUT_WILL_FAIL" for w in feedback["warnings"])


@pytest.mark.parametrize("direction", ["horizontal", "vertical"])
def test_labels_on_edges_merging_into_one_node_do_not_overlap(tmp_path, direction):
    spec = spec_with({"composition": "canonical", "image_references": [], "citations": [], "source_references": [],
                      "diagram_spec": {"kind": "flowchart", "direction": direction, "nodes": [
                          {"id": "a", "text": "符号器"}, {"id": "b", "text": "復号器"}, {"id": "c", "text": "注意"}],
                          "edges": [{"source": "a", "target": "c", "label": "K・V"},
                                    {"source": "b", "target": "c", "label": "Q"}]}})
    generate(TEMPLATE, spec, tmp_path / "d.pptx")
    with ZipFile(tmp_path / "d.pptx") as z:
        root = etree.fromstring(z.read("ppt/slides/slide1.xml"))
    boxes = []
    for shape in query(root, ".//p:sp[.//p:cNvPr[starts-with(@name, 'rsa:edge-label:')]]"):
        off, ext = query(shape, "./p:spPr/a:xfrm/a:off")[0], query(shape, "./p:spPr/a:xfrm/a:ext")[0]
        boxes.append((int(off.get("x")), int(off.get("y")), int(ext.get("cx")), int(ext.get("cy"))))
    assert len(boxes) == 2
    (ax, ay, aw, ah), (bx, by, bw, bh) = boxes
    assert not (ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah)


def test_colliding_labels_are_rejected_instead_of_written(tmp_path):
    spec = spec_with({"image_references": [], "citations": [], "source_references": [],
                      "diagram_spec": {"kind": "flowchart", "nodes": [
                          {"id": "a", "text": "入力"}, {"id": "b", "text": "出力"}],
                          "edges": [{"source": "a", "target": "b", "label": "条件1"},
                                    {"source": "a", "target": "b", "label": "条件2"}]}})
    output = tmp_path / "collision.pptx"
    with pytest.raises(LayoutError, match="DIAGRAM_LABEL_OVERLAP") as error:
        generate(TEMPLATE, spec, output)
    assert error.value.problems[0]["code"] == "DIAGRAM_LABEL_OVERLAP"
    assert not output.exists()


def test_words_longer_than_a_line_break_between_characters():
    # 77pt holds eight 16pt letters (0.56em each); a 17-letter word needs three lines, not ceil(152/77) = 2.
    assert wrapped_lines("a" * 17, 16, 77) == 3
    assert wrapped_lines("a" * 8, 16, 77) == 1
    assert wrapped_lines("a" * 9, 16, 77) == 2


def test_long_word_in_a_table_cell_is_not_underestimated(tmp_path):
    spec = spec_with({"prototype_id": "results_table", "replacements": {"表の結果要点": [{"text": "要点"}]},
                      "table_spec": {"columns": ["a", "b", "c"], "rows": [["a" * 127, "1", "2"]]},
                      "image_references": [], "citations": [], "source_references": []})
    with pytest.raises(LayoutError, match="TABLE_OVERFLOW"):
        generate(TEMPLATE, spec, tmp_path / "long.pptx")


def test_every_failing_table_cell_is_reported(tmp_path):
    long = "長い説明" * 45
    spec = spec_with({"prototype_id": "results_table", "replacements": {"表の結果要点": [{"text": "要点"}]},
                      "table_spec": {"columns": ["a", "b", "c"], "rows": [[long, long, long]]},
                      "image_references": [], "citations": [], "source_references": []})
    with pytest.raises(LayoutError) as error:
        generate(TEMPLATE, spec, tmp_path / "cells.pptx")
    targets = {p["target"] for p in error.value.problems}
    assert {"table row 1 column 0", "table row 1 column 1", "table row 1 column 2"} <= targets
    page = authoring_feedback(TEMPLATE, spec, images={})["pages"][0]
    assert {"table row 1 column 0", "table row 1 column 1", "table row 1 column 2"} <= {
        p["target"] for p in page["fit_problems"]}


def test_every_failing_diagram_node_is_reported(tmp_path):
    long = "長い" * 70
    spec = spec_with({"composition": "canonical", "image_references": [], "citations": [], "source_references": [],
                      "diagram_spec": {"kind": "flowchart", "nodes": [{"id": "a", "text": long},
                                                                       {"id": "b", "text": long}],
                                       "edges": [{"source": "a", "target": "b"}]}})
    with pytest.raises(LayoutError) as error:
        generate(TEMPLATE, spec, tmp_path / "nodes.pptx")
    assert {"a", "b"} <= {p["target"] for p in error.value.problems}
