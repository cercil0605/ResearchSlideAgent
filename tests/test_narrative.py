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
    return json.loads(Path("examples/narrative.slidespec.json").read_text())


def test_research_flow_is_independent_of_visual_prototypes(tmp_path):
    spec = SlideSpec.model_validate(narrative())
    main = [s for s in spec.slides if s.part == "main"]
    assert main[2].section == "example" and main[2].prototype_id == "method"
    metric = next(i for i, s in enumerate(main) if s.section == "metric")
    assert main[metric - 1].section == "experiment" and main[metric].prototype_id == "method"
    assert main[-1].section == "summary" and main[-1].prototype_id == "overview"
    assert spec.slides[-1].part == "appendix" and spec.slides[-1].prototype_id == "method"
    assert sum(s.section == "experiment" for s in main) == 2
    output = tmp_path / "narrative.pptx"
    manifest = generate(TEMPLATE, spec, output)
    assert verify(TEMPLATE, output, spec, manifest)["status"] == "passed"
    assert manifest["rules_digest"] == authoring_context()["rules_digest"]
    assert manifest["slides"][-1]["presentation_part"] == "appendix"
    actual = Presentation(output)
    for index, item in enumerate(spec.slides):
        if item.section in {"example", "background", "related", "objective", "metric", "summary"}:
            assert any(s.name.startswith("rsa:node:") for s in actual.slides[index].shapes)
    with ZipFile(TEMPLATE) as source, ZipFile(output) as target:
        for name in source.namelist():
            if name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")):
                assert source.read(name) == target.read(name)


@pytest.mark.parametrize("failure", ["missing_section", "main_after_appendix", "missing_summary",
                                     "cover_mismatch", "missing_results", "second_cover", "missing_result_visual"])
def test_new_schema_preserves_research_structure(failure):
    raw = narrative()
    if failure == "missing_section":
        raw["slides"][2]["section"] = None
    elif failure == "main_after_appendix":
        raw["slides"][2]["part"] = "appendix"
    elif failure == "missing_summary":
        raw["slides"][-2]["section"] = "discussion"
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


def test_old_schema_cannot_silently_ignore_section_or_appendix():
    raw = narrative()
    raw["schema_version"] = "1.1"
    with pytest.raises(ValidationError, match="section/part require"):
        SlideSpec.model_validate(raw)


def test_wide_visual_can_explain_methods_without_changing_geometry(tmp_path):
    raw = narrative()
    item = deepcopy(next(s for s in raw["slides"] if s["prototype_id"] == "results_figure"))
    item.update(section="method", part="main", slide_order=1)
    raw.update(purpose_mode="general", slides=[item])
    spec = SlideSpec.model_validate(raw)
    output = tmp_path / "wide.pptx"
    generate(TEMPLATE, spec, output)
    info = authoring_feedback(TEMPLATE, spec)
    assert info["pages"][0]["visual_frame_inches"][0] > 6.7
    assert info["content_review"] == info["visual_review"] == "not_performed"


def test_feedback_exposes_inherited_headings_and_missing_visuals():
    raw = json.loads(Path("examples/research-format.slidespec.json").read_text())
    raw["schema_version"] = "1.2"
    for item in raw["slides"]:
        item["section"] = "results" if item["prototype_id"].startswith("results_") else item["prototype_id"]
    info = authoring_feedback(TEMPLATE, SlideSpec.model_validate(raw))
    experiment = next(p for p in info["pages"] if p["section"] == "experiment")
    assert "評価指標" in {h["text"] for h in experiment["inherited_headings"]}
    assert any(w["slide_id"] == experiment["slide_id"] and w["code"] == "MISSING_EXPLANATORY_VISUAL"
               for w in info["warnings"])
