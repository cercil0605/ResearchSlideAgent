from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import approved_project
from pydantic import ValidationError

from research_slide_agent.models import SlideSpec
from research_slide_agent.sample import sample_spec
from research_slide_agent.store import StateError
from research_slide_agent.worker import process_one


def test_reject_before_and_after_partial_approval(store):
    p = store.create("alice")
    spec = sample_spec(p["id"])
    store.save_spec("alice", p["id"], spec, 0)
    with pytest.raises(StateError, match="APPROVAL_REQUIRED"):
        store.enqueue("alice", p["id"])
    with pytest.raises(StateError, match="OUTLINE_APPROVAL_REQUIRED"):
        store.review("alice", p["id"], "slide", "s1")
    r = store.review("alice", p["id"], "outline")
    store.approve_from_browser("alice", r["review_id"])
    with pytest.raises(StateError, match="APPROVAL_REQUIRED"):
        store.enqueue("alice", p["id"])
    with pytest.raises(ValidationError):
        SlideSpec.model_validate({**spec.model_dump(), "approved": True})


def test_version_invalidates_approvals(store):
    p, spec = approved_project(store)
    old_review = store.review("alice", p["id"], "slide", "s1")
    newer = SlideSpec.model_validate({**spec.model_dump(), "spec_version": 2})
    store.save_spec("alice", p["id"], newer, 1)
    assert not store.approvals("alice", p["id"])["outline_approved"]
    with pytest.raises(StateError, match="STALE"):
        store.approve_from_browser("alice", old_review["review_id"])
    with pytest.raises(StateError, match="APPROVAL_REQUIRED"):
        store.enqueue("alice", p["id"])
    with pytest.raises(StateError, match="VERSION_CONFLICT"):
        store.save_spec("alice", p["id"], newer, 1)


def test_owner_isolation_and_expiry(store):
    p, spec = approved_project(store)
    job = store.enqueue("alice", p["id"])
    for call in [
        lambda: store.project("bob", p["id"]),
        lambda: store.job("bob", job["id"]),
        lambda: store.files("bob", p["id"]),
        lambda: store.review("bob", p["id"], "outline"),
    ]:
        with pytest.raises(StateError):
            call()
    with store.connect() as con:
        con.execute("UPDATE projects SET expires=0 WHERE id=?", (p["id"],))
    with pytest.raises(StateError, match="EXPIRED"):
        store.project("alice", p["id"])
    assert store.cleanup()["removed_projects"] == 1
    assert not (store.root / p["id"]).exists()


def test_idempotency_and_worker(store, settings):
    p, spec = approved_project(store)
    job = store.enqueue("alice", p["id"])
    assert store.enqueue("alice", p["id"])["id"] == job["id"]
    assert process_one(store, settings)
    assert store.job("alice", job["id"])["state"] == "completed"
    assert not process_one(store, settings)
    assert store.enqueue("alice", p["id"])["state"] == "completed"


def test_atomic_claim_and_limits(store, settings):
    for owner in ["alice", "bob", "charlie"]:
        p, spec = approved_project(store, owner)
        store.enqueue(owner, p["id"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(4)))
    assert sum(c is not None for c in claims) == 1
    settings.worker_limit = 2
    assert store.claim()
    assert store.claim() is None


def test_user_queue_limit(store):
    p, spec = approved_project(store)
    store.enqueue("alice", p["id"])
    other, _ = approved_project(store)
    with pytest.raises(StateError, match="USER_JOB_LIMIT"):
        store.enqueue("alice", other["id"])


def test_lease_and_retry_ceiling(store):
    p, spec = approved_project(store)
    job = store.enqueue("alice", p["id"])
    for attempt in range(3):
        claim = store.claim()
        assert claim["attempts"] == attempt + 1
        store.finish(job["id"], claim["lease_token"], "failed", error="TEMPORARY", transient=True)
        with store.connect() as con:
            con.execute("UPDATE jobs SET available=0")
    assert store.job("alice", job["id"])["state"] == "failed"
    with pytest.raises(StateError, match="RETRY_LIMIT"):
        store.retry("alice", job["id"])


def test_old_worker_cannot_complete(store):
    p, spec = approved_project(store)
    job = store.enqueue("alice", p["id"])
    first = store.claim()
    with store.connect() as con:
        con.execute("UPDATE jobs SET lease=0 WHERE id=?", (job["id"],))
    second = store.claim()
    assert first["lease_token"] != second["lease_token"]
    with pytest.raises(StateError, match="LEASE_LOST"):
        store.finish(job["id"], first["lease_token"], "completed")


def test_reference_metadata_and_source_ownership(store):
    p = store.create("alice")
    source = store.register(
        "alice", p["id"], "data.csv", b"case,value\na,1\n", author="Test author", year=2026
    )
    spec = sample_spec(p["id"], 1)
    slide = spec.model_dump()["slides"][0]
    slide["source_references"] = [{"source_id": source["source_id"], "locator": "row 2"}]
    slide["citations"] = [
        {"source": slide["source_references"][0], "author": "Wrong", "year": 2026, "target_id": "key_message"}
    ]
    spec = SlideSpec.model_validate({**spec.model_dump(), "slides": [slide]})
    with pytest.raises(StateError, match="SOURCE_METADATA_MISMATCH"):
        store.save_spec("alice", p["id"], spec, 0)


def test_template_change_rejects_old_approval(store, settings):
    p, spec = approved_project(store)
    settings.template.write_bytes(settings.template.read_bytes() + b"changed")
    with pytest.raises(StateError, match="TEMPLATE_CHANGED"):
        store.enqueue("alice", p["id"])


def test_reuploaded_pptx_patch_workflow(store, settings, tmp_path):
    from research_slide_agent.engine import generate, inspect_pptx

    path = tmp_path / "slides.pptx"
    generate(settings.template, sample_spec(), path)
    p = store.create("alice")
    uploaded = store.register("alice", p["id"], "manual.pptx", path.read_bytes())
    shape = next(s for s in inspect_pptx(path)[0]["shapes"] if s["name"] == "rsa:key_message")
    change = {
        "slide_number": 1,
        "shape_id": shape["shape_id"],
        "expected_sha256": shape["sha256"],
        "text": "New approved text",
    }
    plan = store.patch_plan("alice", p["id"], uploaded["source_id"], [change])
    with pytest.raises(StateError, match="APPROVAL_REQUIRED"):
        store.enqueue("alice", p["id"], plan["patch_id"])
    store.approve_from_browser("alice", plan["review_id"])
    job = store.enqueue("alice", p["id"], plan["patch_id"])
    assert process_one(store, settings)
    assert store.job("alice", job["id"])["state"] == "completed"
    assert path.exists()


def test_browser_source_metadata(store):
    p = store.create("alice")
    f = store.register("alice", p["id"], "data.csv", b"a,b")
    store.source_metadata("alice", p["id"], f["source_id"], "User-confirmed", 2026)
    assert store.files("alice", p["id"])[0]["author"] == "User-confirmed"
    with pytest.raises(StateError):
        store.source_metadata("bob", p["id"], f["source_id"], "Other", 2026)
