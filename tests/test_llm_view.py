import json
from pathlib import Path

from research_slide_agent.engine import template_info as full_template_info
from research_slide_agent.llm_view import compact_template_info, describe_style, template_info

TEMPLATE = Path("templates/lab-template.pptx")


def slots(info):
    return {(p["prototype_id"], s["name"]): s for p in info["prototypes"] for s in p["slots"]}


def test_compact_catalog_drops_raw_xml_and_geometry():
    text = json.dumps(template_info(TEMPLATE), ensure_ascii=False)
    assert "style_xml" not in text and "<a:rPr" not in text
    assert '"shape_id"' not in text and '"box"' not in text and '"part"' not in text
    assert len(text) < len(json.dumps(full_template_info(TEMPLATE), ensure_ascii=False)) / 3


def test_compact_catalog_keeps_everything_a_spec_can_reference():
    full, compact = full_template_info(TEMPLATE), template_info(TEMPLATE)
    assert {k for k in full if k != "prototypes"} <= set(compact)
    assert [p["prototype_id"] for p in full["prototypes"]] == [p["prototype_id"] for p in compact["prototypes"]]
    full_slots, compact_slots = slots(full), slots(compact)
    assert full_slots.keys() == compact_slots.keys()
    for key, slot in full_slots.items():
        paragraphs = compact_slots[key]["paragraphs"]
        assert [(p["index"], p["example"]) for p in slot["paragraphs"]] == [
            (p["index"], p["example"]) for p in paragraphs]


def test_mixed_style_paragraph_keeps_style_run_indices():
    author = slots(template_info(TEMPLATE))[("cover", "著者")]["paragraphs"][0]
    assert [r["index"] for r in author["runs"]] == [0, 1, 2, 3, 4]
    assert all("style" in r and "style_xml" not in r for r in author["runs"])
    title = slots(template_info(TEMPLATE))[("cover", "発表題目")]["paragraphs"][0]
    assert "runs" not in title and title["style"] == "26pt bold #000000"


def test_volatile_attributes_do_not_count_as_a_style_change():
    rpr = '<a:rPr sz="1600" b="1"{}><a:solidFill><a:srgbClr val="000000"/></a:solidFill></a:rPr>'
    info = {"prototypes": [{"prototype_id": "x", "part": "p", "slots": [{"name": "s", "shape_id": 1, "box": [0, 0, 1, 1],
            "paragraphs": [{"index": 0, "example": "ab", "runs": [
                {"index": 0, "example": "a", "style_xml": rpr.format("")},
                {"index": 1, "example": "b", "style_xml": rpr.format(' err="1" dirty="0"')}]}]}]}]}
    paragraph = compact_template_info(info)["prototypes"][0]["slots"][0]["paragraphs"][0]
    assert "runs" not in paragraph and paragraph["style"] == "16pt bold #000000"


def test_describe_style():
    assert describe_style(None) == "inherited"
    assert describe_style('<a:rPr i="1" u="sng"><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></a:rPr>') \
        == "italic underline accent1"
