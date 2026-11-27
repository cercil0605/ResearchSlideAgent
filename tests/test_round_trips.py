import asyncio
import json
import threading

import pytest
from conftest import saved_project

from research_slide_agent import round_trips
from research_slide_agent.auth import Auth
from research_slide_agent.config import Settings
from research_slide_agent.paper import estimate_tokens
from research_slide_agent.round_trips import authoring_context_part, compact_feedback, merge_slides
from research_slide_agent.rules import authoring_context
from research_slide_agent.server import make_mcp
from research_slide_agent.store import StateError, Store
from research_slide_agent.worker import process_one


def test_rules_come_in_parts_under_the_client_limit_and_cover_every_document():
    full = authoring_context()
    first = authoring_context_part(1)
    parts = [first] + [authoring_context_part(n) for n in range(2, first["parts"] + 1)]
    assert first["parts"] >= 2 and parts[-1]["next_part"] is None
    assert all(p["rules_digest"] == full["rules_digest"] for p in parts)
    for part in parts:
        assert estimate_tokens(json.dumps(part, ensure_ascii=False)) <= 20_000
    joined = {}
    for part in parts:
        for document in part["documents"]:
            joined[document["id"]] = joined.get(document["id"], "") + document["text"]
    assert joined == {d["id"]: d["text"] for d in full["documents"]}
    with pytest.raises(StateError, match="PART_INVALID"):
        authoring_context_part(first["parts"] + 1)


def test_long_documents_split_at_headings(monkeypatch):
    monkeypatch.setattr(round_trips, "RULE_PART_TOKENS", 4000)
    _, parts = round_trips.rule_parts()
    pieces = [d for part in parts for d in part if d.get("piece")]
    assert pieces and all(d["text"].startswith("## ") or d["piece"].startswith("1/") for d in pieces)


def test_compact_feedback_keeps_only_pages_that_need_attention():
    feedback = {
        "pages": [{"slide_id": "a", "page": 1, "title": "A", "content_evidence": {"x": "long"},
                   "missing_page_roles": [], "inherited_headings": []},
                  {"slide_id": "b", "page": 2, "title": "B", "content_evidence": {"x": "long"},
                   "missing_page_roles": ["result"], "inherited_headings": []},
                  {"slide_id": "c", "page": 3, "title": "C", "content_evidence": {}}],
        "warnings": [{"slide_id": "c", "code": "TRIVIAL_DIAGRAM", "guidance": "…"}],
        "content_review": "not_performed", "figure_numbers_added": [{"slide_id": "c"}],
    }
    compact = compact_feedback(feedback)
    assert [p["slide_id"] for p in compact["pages"]] == ["b", "c"]
    assert "content_evidence" not in json.dumps(compact)
    assert compact["pages_checked"] == 3 and compact["pages_without_issues"] == 1
    assert compact["figure_numbers_added"] and compact["content_review"] == "not_performed"
    assert compact["warnings"] == [{"slide_id": "c", "code": "TRIVIAL_DIAGRAM"}]
    assert compact["guidance"] == {"TRIVIAL_DIAGRAM": "…"}
    only_c = compact_feedback(feedback, {"c"})
    assert [p["slide_id"] for p in only_c["pages"]] == ["c"] and only_c["pages_checked"] == 1
    assert compact_feedback(feedback, detail=True)["pages"][0]["content_evidence"]


def test_merge_slides_replaces_inserts_removes_and_renumbers(store):
    project, spec = saved_project(store, count=5)
    current = spec.model_dump(mode="json")
    slides = current["slides"]
    replaced = {**slides[1], "title": "差し替え"}
    inserted = {**slides[3], "slide_id": "new", "slide_order": 3, "title": "追加"}
    merged, changed = merge_slides(current, [replaced, inserted], [slides[4]["slide_id"]], 1)
    assert changed == {slides[1]["slide_id"], "new"}
    assert [s.slide_order for s in merged.slides] == [1, 2, 3, 4, 5]
    assert [s.slide_id for s in merged.slides] == [slides[0]["slide_id"], slides[1]["slide_id"], "new",
                                                   slides[2]["slide_id"], slides[3]["slide_id"]]
    assert merged.slides[1].title == "差し替え" and merged.spec_version == 2
    with pytest.raises(StateError, match="SLIDE_NOT_FOUND"):
        merge_slides(current, [], ["missing"], 1)
    with pytest.raises(StateError, match="SPEC_REQUIRED"):
        merge_slides(None, [replaced], [], 0)
    with pytest.raises(StateError, match="PATCH_EMPTY"):
        merge_slides(current, [], [], 1)


@pytest.fixture
def local(settings, tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    local = Settings(local=True, data_dir=settings.data_dir, template=settings.template,
                     input_dirs=(inputs,), output_dir=tmp_path / "out")
    store = Store(local)
    return store, local, make_mcp(store, local, Auth(local))


def worker(store, settings, stop):
    while not stop.is_set():
        if not process_one(store, settings):
            stop.wait(0.05)


@pytest.mark.asyncio
async def test_generation_waits_and_returns_every_page_overview(local, preview_renderer, monkeypatch):
    store, settings, mcp = local
    monkeypatch.setattr(round_trips, "GENERATION_WAIT_SECONDS", 20)
    monkeypatch.setattr(round_trips, "PREVIEW_WAIT_SECONDS", 20)
    project, spec = saved_project(store, owner="local-user", count=8)
    stop = threading.Event()
    thread = threading.Thread(target=worker, args=(store, settings, stop), daemon=True)
    thread.start()
    try:
        result = await mcp.call_tool("enqueue_generation", {"presentation_id": project["id"]})
    finally:
        stop.set()
        thread.join(5)
    summary = json.loads(result.content[0].text)
    assert summary["job"]["state"] == "completed" and summary["job"]["local_path"]
    assert summary["preview"]["page_count"] == 8 and summary["preview"]["sheets"] == 2
    assert [c.type for c in result.content[1:]] == ["image", "image"]
    again = await mcp.call_tool("get_slide_preview", {"job_id": summary["job"]["id"], "all_pages": True})
    assert [c.type for c in again.content] == ["text", "image", "image"]
    assert len(preview_renderer) == 1  # rendered once, reused


@pytest.mark.asyncio
async def test_generation_wait_reports_a_running_job(local, monkeypatch):
    store, _, mcp = local
    monkeypatch.setattr(round_trips, "GENERATION_WAIT_SECONDS", 0.2)
    project, _ = saved_project(store, owner="local-user")
    result = await mcp.call_tool("enqueue_generation", {"presentation_id": project["id"]})
    summary = json.loads(result.content[0].text)
    assert summary["job"]["state"] == "queued" and "get_job" in summary["guidance"]


@pytest.mark.asyncio
async def test_patch_slides_tool_returns_feedback_for_changed_slides(local):
    store, _, mcp = local
    project, spec = saved_project(store, owner="local-user", count=5)
    slide = spec.slides[2].model_dump(mode="json")
    slide["title"] = "直したページ"
    result = await mcp.call_tool("patch_slides", {"presentation_id": project["id"], "expected_version": 1,
                                                  "slides": [slide]})
    data = json.loads(result.content[0].text)
    assert data["spec_version"] == 2
    assert data["authoring_feedback"]["pages_checked"] == 1
    assert store.project("local-user", project["id"])["spec"]["slides"][2]["title"] == "直したページ"
    assert asyncio.iscoroutinefunction(mcp.call_tool)


def test_patched_slides_land_at_their_requested_positions(store):
    project, spec = saved_project(store, count=5)
    current = spec.model_dump(mode="json")
    ids = [s["slide_id"] for s in current["slides"]]
    moved = {**current["slides"][1], "slide_order": 4}
    merged, _ = merge_slides(current, [moved], [], 1)
    assert [s.slide_id for s in merged.slides] == [ids[0], ids[2], ids[3], ids[1], ids[4]]
    new = [{**current["slides"][3], "slide_id": f"new{n}", "slide_order": n} for n in (2, 3)]
    merged, _ = merge_slides(current, new, [], 1)
    assert [s.slide_id for s in merged.slides][:4] == [ids[0], "new2", "new3", ids[1]]


def test_guidance_that_differs_between_pages_stays_with_each_warning():
    feedback = {"pages": [{"slide_id": i, "page": n, "title": i} for n, i in enumerate("abc", 1)],
                "warnings": [{"slide_id": "b", "code": "ADJACENT_TABLE_MERGE_REVIEW", "guidance": "Compare with a"},
                             {"slide_id": "c", "code": "ADJACENT_TABLE_MERGE_REVIEW", "guidance": "Compare with b"},
                             {"slide_id": "a", "code": "TRIVIAL_DIAGRAM", "guidance": "same"},
                             {"slide_id": "c", "code": "TRIVIAL_DIAGRAM", "guidance": "same"}]}
    compact = compact_feedback(feedback)
    assert compact["guidance"] == {"TRIVIAL_DIAGRAM": "same"}
    assert [w.get("guidance") for w in compact["warnings"]] == ["Compare with a", "Compare with b", None, None]
