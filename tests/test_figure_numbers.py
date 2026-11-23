import io
import json
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter

from research_slide_agent.figures import figure_number
from research_slide_agent.models import SlideSpec
from research_slide_agent.prototypes import authoring_feedback
from research_slide_agent.store import StateError

TEMPLATE = Path("templates/lab-template.pptx")


def png():
    data = io.BytesIO()
    Image.new("RGB", (100, 80), "gray").save(data, format="PNG")
    return data.getvalue()


def paper_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=200)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def figure_spec(store, *, crop=True, caption="単関節例", locator="p.5 Fig.7(a)", explicit=True):
    p = store.create("alice")
    pdf = store.register("alice", p["id"], "paper.pdf", paper_bytes(), author="Ishizawaら", year=2026)
    origin = ({"operation": "pdf_crop_v1", "source_id": pdf["source_id"], "sha256": pdf["sha256"], "page": 5}
              if crop else None)
    image = store.register("alice", p["id"], "figure-p5.png", png(), _origin=origin)
    raw = json.loads(Path("examples/research-format.slidespec.json").read_text())
    slide = next(s for s in raw["slides"] if s["prototype_id"] == "results_figure")
    slide.pop("diagram_spec", None)
    ref = {"source_id": pdf["source_id"], "locator": locator}
    slide.update(slide_order=1, image_references=[{"id": "fig", "source_id": image["source_id"], "caption": caption}],
                 source_references=[ref],
                 citations=[{"source": ref, "author": "Ishizawaら", "year": 2026, "target_id": "fig"}])
    if explicit:
        slide["replacements"]["図題"] = [{"text": f"{caption} [Ishizawaら '26]"}]
    else:
        slide["replacements"].pop("図題", None)
        slide["replacements"]["結果の要点"] = [{"text": "単関節の例 [Ishizawaら '26]"}]
    raw.update(presentation_id=p["id"], purpose_mode="general", slides=[slide])
    return p["id"], SlideSpec.model_validate(raw)


@pytest.mark.parametrize("text,number", [
    ("Fig. 7(b) 並列区間", "Fig. 7(b)"), ("p.5 Fig.7(a)", "Fig.7(a)"), ("Figure 3: samples", "Figure 3"),
    ("Table 2の抜粋", "Table 2"), ("図2左", "図2"), ("表 1", "表 1"), ("単関節例", None), ("説明図", None),
])
def test_figure_number_detection(text, number):
    assert figure_number(text) == number


def test_number_from_locator_is_prefixed_into_caption_and_slot(store):
    pid, spec = figure_spec(store)
    result = store.save_spec("alice", pid, spec, 0)
    assert result["authoring_feedback"]["figure_numbers_added"] == [
        {"slide_id": spec.slides[0].slide_id, "image_id": "fig", "caption": "Fig.7(a) 単関節例"}]
    saved = store.project("alice", pid)["spec"]["slides"][0]
    assert saved["image_references"][0]["caption"] == "Fig.7(a) 単関節例"
    assert saved["replacements"]["図題"][0]["text"] == "Fig.7(a) 単関節例 [Ishizawaら '26]"


def test_caption_with_number_is_left_alone(store):
    pid, spec = figure_spec(store, caption="Fig. 7(a) 単関節例")
    result = store.save_spec("alice", pid, spec, 0)
    assert "figure_numbers_added" not in result["authoring_feedback"]


def test_crop_without_any_number_cannot_be_saved(store):
    pid, spec = figure_spec(store, locator="p.5")
    with pytest.raises(StateError, match="FIGURE_NUMBER_REQUIRED"):
        store.save_spec("alice", pid, spec, 0)


def test_uploaded_photo_does_not_need_a_figure_number(store):
    pid, spec = figure_spec(store, crop=False, locator="提供写真")
    assert "figure_numbers_added" not in store.save_spec("alice", pid, spec, 0)["authoring_feedback"]


def test_generated_slide_shows_the_number(store, settings):
    from research_slide_agent.worker import process_one

    settings.template = TEMPLATE
    pid, spec = figure_spec(store, explicit=False)
    store.save_spec("alice", pid, spec, 0)
    job = store.enqueue("alice", pid)
    assert process_one(store, settings)
    done = store.job("alice", job["id"])
    assert done["state"] == "completed", done
    from pptx import Presentation

    prs = Presentation(store.root / json.loads(done["output"])["pptx"])
    assert any("Fig.7(a) 単関節例" in s.text_frame.text for s in prs.slides[0].shapes if s.has_text_frame)


def _diagram(nodes, edges=(), kind="flowchart"):
    return {"kind": kind, "direction": "vertical",
            "nodes": [{"id": f"n{i}", "text": t, **({"kind": "decision"} if t.endswith("?") else {})}
                      for i, t in enumerate(nodes)],
            "edges": [dict(source=a, target=b, **({"label": label} if label else {})) for a, b, label in edges]}


@pytest.mark.parametrize("diagram,trivial", [
    (_diagram(["学習画像", "分布を学習", "新しい画像"], [("n0", "n1", ""), ("n1", "n2", "")]), True),
    (_diagram(["FID", "IS", "NLL"], kind="comparison"), True),
    (_diagram(["入力", "判定?", "出力"], [("n0", "n1", ""), ("n1", "n2", "")]), False),
    (_diagram(["符号器", "復号器", "出力"], [("n0", "n1", "K, V"), ("n1", "n2", "")]), False),
    (_diagram(["記録", "生成", "中継", "実行"], [("n0", "n1", ""), ("n1", "n2", ""), ("n2", "n3", "")]), False),
])
def test_trivial_diagram_warning(diagram, trivial):
    raw = json.loads(Path("examples/research-quality.slidespec.json").read_text())
    item = next(s for s in raw["slides"] if s.get("diagram_spec"))
    item["diagram_spec"] = diagram
    info = authoring_feedback(TEMPLATE, SlideSpec.model_validate(raw))
    codes = {w["code"] for w in info["warnings"] if w["slide_id"] == item["slide_id"]}
    assert ("TRIVIAL_DIAGRAM" in codes) is trivial


def test_text_pages_need_no_visual_but_empty_figure_frames_are_flagged():
    raw = json.loads(Path("examples/research-quality.slidespec.json").read_text())
    overview = raw["slides"][1]
    overview["diagram_spec"] = None
    overview["citations"] = [c for c in overview.get("citations", []) if c["target_id"] != "diagram"]
    info = authoring_feedback(TEMPLATE, SlideSpec.model_validate(raw))
    assert "MISSING_EXPLANATORY_VISUAL" not in {w["code"] for w in info["warnings"]}
    flagged = {w["slide_id"] for w in info["warnings"] if w["code"] == "EMPTY_FIGURE_FRAME"}
    assert flagged == {overview["slide_id"]}
