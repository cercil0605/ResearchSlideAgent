import json
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

import pytest
from pptx import Presentation
from pydantic import ValidationError

from research_slide_agent.engine import generate, verify
from research_slide_agent.models import SlideSpec
from research_slide_agent.prototypes import authoring_feedback
from research_slide_agent.rules import authoring_context

TEMPLATE = Path("templates/lab-template.pptx")


def narrative():
    return json.loads(Path("examples/research-quality.slidespec.json").read_text())


def test_research_flow_is_independent_of_visual_prototypes(tmp_path):
    raw = narrative()
    method = next(s for s in raw["slides"] if s.get("composition") == "text_visual")
    background = raw["slides"][2]
    background.update(prototype_id="method", composition="text_visual",
                      replacements=deepcopy(method["replacements"]), diagram_spec=deepcopy(method["diagram_spec"]),
                      content_map={"problem": ["手法の説明"], "context": ["手法の特徴"]})
    spec = SlideSpec.model_validate(raw)
    output = tmp_path / "narrative.pptx"
    manifest = generate(TEMPLATE, spec, output)
    assert verify(TEMPLATE, output, spec, manifest)["status"] == "passed"
    assert manifest["rules_digest"] == authoring_context()["rules_digest"]
    assert spec.slides[2].section == "background" and spec.slides[2].prototype_id == "method"
    actual = Presentation(output)
    assert any(s.name.startswith("rsa:node:") for s in actual.slides[2].shapes)
    with ZipFile(TEMPLATE) as source, ZipFile(output) as target:
        for name in source.namelist():
            if name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")):
                assert source.read(name) == target.read(name)


@pytest.mark.parametrize("failure", ["missing_section", "main_after_appendix", "missing_summary",
                                     "cover_mismatch", "missing_results", "second_cover", "missing_result_visual"])
def test_schema_preserves_research_structure(failure):
    raw = narrative()
    if failure == "missing_section":
        raw["slides"][2].pop("section")
    elif failure == "main_after_appendix":
        raw["slides"][2]["part"] = "appendix"
    elif failure == "missing_summary":
        raw["slides"][-1]["section"] = "discussion"
    elif failure == "cover_mismatch":
        raw["slides"][2]["prototype_id"] = "cover"
    elif failure == "missing_results":
        for item in raw["slides"]:
            if item["section"] == "results":
                item["section"] = "method"
    elif failure == "second_cover":
        raw["slides"][2].update(section="cover", prototype_id="cover")
    else:
        for item in raw["slides"]:
            if item["section"] == "results":
                item.update(diagram_spec=None, table_spec=None, image_references=[])
    with pytest.raises(ValidationError):
        SlideSpec.model_validate(raw)


def test_wide_visual_can_explain_methods(tmp_path):
    from research_slide_agent.sample import sample_spec

    raw = sample_spec().model_dump()
    item = deepcopy(next(s for s in raw["slides"] if s["prototype_id"] == "results_figure"))
    item.update(section="method", slide_order=1)
    raw.update(slides=[item])
    spec = SlideSpec.model_validate(raw)
    output = tmp_path / "wide.pptx"
    generate(TEMPLATE, spec, output)
    info = authoring_feedback(TEMPLATE, spec)
    assert info["pages"][0]["visual_frame_inches"][0] > 6.7
    assert info["content_review"] == info["visual_review"] == "not_performed"


def test_feedback_exposes_inherited_headings_and_accepts_text_pages():
    raw = json.loads(Path("examples/research-format.slidespec.json").read_text())
    info = authoring_feedback(TEMPLATE, SlideSpec.model_validate(raw))
    experiment = next(p for p in info["pages"] if p["section"] == "experiment")
    assert "評価指標" in {h["text"] for h in experiment["inherited_headings"]}
    assert not experiment["has_visual"]
    assert not any(w["slide_id"] == experiment["slide_id"] for w in info["warnings"])


def test_feedback_flags_table_on_a_non_table_prototype():
    raw = json.loads(Path("examples/research-format.slidespec.json").read_text())
    item = next(s for s in raw["slides"] if s.get("table_spec"))
    item.update(prototype_id="method", content_map={})
    raw["purpose_mode"] = "general"
    info = authoring_feedback(TEMPLATE, SlideSpec.model_validate(raw))
    assert any(w["slide_id"] == item["slide_id"] and w["code"] == "VISUAL_LAYOUT_UNSUPPORTED"
               and "results_table" in w["guidance"] for w in info["warnings"])
