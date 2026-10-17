from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import saved_project
from pydantic import ValidationError

from research_slide_agent.models import SlideSpec
from research_slide_agent.sample import sample_spec
from research_slide_agent.store import StateError
from research_slide_agent.worker import process_one


def test_generate_without_approval(store):
    p = store.create("alice")
    with pytest.raises(StateError, match="SPEC_REQUIRED"):
        store.enqueue("alice", p["id"])
    spec = sample_spec(p["id"])
    store.save_spec("alice", p["id"], spec, 0)
    assert store.enqueue("alice", p["id"])["state"] == "queued"
    with pytest.raises(ValidationError):
        SlideSpec.model_validate({**spec.model_dump(), "approved": True})


def test_regenerate_new_version_without_approval(store, settings):
    p, spec = saved_project(store)
    first = store.enqueue("alice", p["id"])
    assert process_one(store, settings)
    newer = SlideSpec.model_validate({**spec.model_dump(), "spec_version": 2})
    store.save_spec("alice", p["id"], newer, 1)
    second = store.enqueue("alice", p["id"])
    assert second["id"] != first["id"] and second["version"] == 2
    assert process_one(store, settings)
    assert store.job("alice", second["id"])["state"] == "completed"
    with pytest.raises(StateError, match="VERSION_CONFLICT"):
        store.save_spec("alice", p["id"], newer, 1)


def test_owner_isolation_and_expiry(store):
    p, spec = saved_project(store)
    job = store.enqueue("alice", p["id"])
    for call in [
        lambda: store.project("bob", p["id"]),
        lambda: store.job("bob", job["id"]),
        lambda: store.files("bob", p["id"]),
        lambda: store.enqueue("bob", p["id"]),
    ]:
        with pytest.raises(StateError):
            call()
    with store.connect() as con:
        con.execute("UPDATE projects SET expires=0 WHERE id=?", (p["id"],))
    with pytest.raises(StateError, match="EXPIRED"):
        store.project("alice", p["id"])
    assert store.cleanup()["removed_projects"] == 1
    assert not (store.root / p["id"]).exists()


def test_idempotency_and_worker(store, settings, monkeypatch):
    import research_slide_agent.engine as engine

    def forbidden_render(*args, **kwargs):
        pytest.fail("worker must not render previews")

    monkeypatch.setattr(engine, "render", forbidden_render)
    p, spec = saved_project(store)
    job = store.enqueue("alice", p["id"])
    assert store.enqueue("alice", p["id"])["id"] == job["id"]
    assert process_one(store, settings)
    assert store.job("alice", job["id"])["state"] == "completed"
    assert not process_one(store, settings)
    assert store.enqueue("alice", p["id"])["state"] == "completed"


def test_atomic_claim_and_limits(store, settings):
    for owner in ["alice", "bob", "charlie"]:
        p, spec = saved_project(store, owner)
        store.enqueue(owner, p["id"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(4)))
    assert sum(c is not None for c in claims) == 1
    settings.worker_limit = 2
    assert store.claim()
    assert store.claim() is None


def test_user_queue_limit(store):
    p, spec = saved_project(store)
    store.enqueue("alice", p["id"])
    other, _ = saved_project(store)
    with pytest.raises(StateError, match="USER_JOB_LIMIT"):
        store.enqueue("alice", other["id"])


def test_lease_and_retry_ceiling(store):
    p, spec = saved_project(store)
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
    p, spec = saved_project(store)
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


def test_template_change_rejects_old_spec(store, settings):
    p, spec = saved_project(store)
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
        "text": "New saved text",
    }
    plan = store.patch_plan("alice", p["id"], uploaded["source_id"], [change])
    assert set(plan) == {"patch_id"}
    job = store.enqueue("alice", p["id"], plan["patch_id"])
    assert process_one(store, settings)
    assert store.job("alice", job["id"])["state"] == "completed"
    import json

    output = json.loads(store.job("alice", job["id"])["output"])
    assert "preview" not in output
    patched = store.root / output["pptx"]
    assert next(s for s in inspect_pptx(patched)[0]["shapes"]
                if s["shape_id"] == shape["shape_id"])["text"] == change["text"]
    assert store.file("alice", p["id"], uploaded["source_id"])["path"].read_bytes() == path.read_bytes()


def test_browser_source_metadata(store):
    p = store.create("alice")
    f = store.register("alice", p["id"], "data.csv", b"a,b")
    store.source_metadata("alice", p["id"], f["source_id"], "User-confirmed", 2026)
    assert store.files("alice", p["id"])[0]["author"] == "User-confirmed"
    with pytest.raises(StateError):
        store.source_metadata("bob", p["id"], f["source_id"], "Other", 2026)


def test_existing_database_keeps_legacy_rows_and_accepts_unapproved_spec(store, settings):
    from research_slide_agent.store import Store

    p, spec = saved_project(store)
    with store.connect() as con:
        con.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?)",
                    (p["id"], 1, "outline", "", spec.digest(), 1))
        con.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,0)",
                    ("old-review", p["id"], 1, "slide", "s1", spec.digest(), 9999999999))
    reopened = Store(settings)
    assert reopened.project("alice", p["id"])["spec"] == spec.model_dump()
    with reopened.connect() as con:
        assert con.execute("SELECT count(*) FROM approvals").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM reviews").fetchone()[0] == 1
    job = reopened.enqueue("alice", p["id"])
    assert process_one(reopened, settings)
    assert reopened.job("alice", job["id"])["state"] == "completed"


def test_structure_check_failure_does_not_complete(store, settings, monkeypatch):
    import research_slide_agent.worker as worker
    from research_slide_agent.engine import LayoutError

    p, _ = saved_project(store)
    job = store.enqueue("alice", p["id"])

    def invalid(*args):
        raise LayoutError("invalid output structure")

    monkeypatch.setattr(worker, "inspect_pptx", invalid)
    assert process_one(store, settings)
    failed = store.job("alice", job["id"])
    assert failed["state"] == "failed" and failed["error"] == "LAYOUT_REQUIRES_USER_CHANGE"


def test_template_change_after_enqueue_fails(store, settings):
    p, _ = saved_project(store)
    job = store.enqueue("alice", p["id"])
    settings.template.write_bytes(settings.template.read_bytes() + b"changed")
    assert process_one(store, settings)
    assert store.job("alice", job["id"])["state"] == "failed"


def test_patch_base_change_rejected_at_enqueue_and_execution(store, settings, tmp_path):
    from research_slide_agent.engine import LayoutError, generate, inspect_pptx

    path = tmp_path / "base.pptx"
    generate(settings.template, sample_spec(), path)
    p = store.create("alice")
    source = store.register("alice", p["id"], "base.pptx", path.read_bytes())["source_id"]
    shape = next(s for s in inspect_pptx(path)[0]["shapes"] if s["name"] == "rsa:key_message")
    change = {"slide_number": 1, "shape_id": shape["shape_id"],
              "expected_sha256": shape["sha256"], "text": "Updated"}
    with pytest.raises(StateError):
        store.patch_plan("bob", p["id"], source, [change])
    with pytest.raises(LayoutError, match="EDIT_CONFLICT"):
        store.patch_plan("alice", p["id"], source, [{**change, "expected_sha256": "stale"}])
    plan = store.patch_plan("alice", p["id"], source, [change])
    job = store.enqueue("alice", p["id"], plan["patch_id"])
    store.register("alice", p["id"], "newer.pptx", path.read_bytes())
    with pytest.raises(StateError, match="BASE_CHANGED"):
        store.enqueue("alice", p["id"], plan["patch_id"])
    assert process_one(store, settings)
    assert store.job("alice", job["id"])["state"] == "failed"


def test_uploaded_image_is_inserted_without_preview(store, settings):
    import io
    import json
    from pathlib import Path

    from PIL import Image
    from pptx import Presentation

    settings.template = Path("templates/lab-template.pptx")
    p = store.create("alice")
    data = io.BytesIO()
    Image.new("RGB", (100, 100), "gray").save(data, format="PNG")
    source = store.register("alice", p["id"], "source.png", data.getvalue(), author="試験資料", year=2026)
    raw = json.loads(Path("examples/research-format.slidespec.json").read_text())
    slide = next(s for s in raw["slides"] if s["prototype_id"] == "results_figure")
    slide.update(slide_order=1, image_references=[{
        "id": "image", "source_id": source["source_id"], "caption": "試験用画像"}])
    slide.pop("diagram_spec", None)
    ref = {"source_id": source["source_id"], "locator": "試験画像"}
    slide["source_references"] = [ref]
    slide["citations"] = [{"source": ref, "target_id": "image", "author": "試験資料", "year": 2026}]
    slide["replacements"]["図題"] = [{"text": "試験用画像 [試験資料 '26]"}]
    raw.update(presentation_id=p["id"], purpose_mode="general", slides=[slide])
    store.save_spec("alice", p["id"], SlideSpec.model_validate(raw), 0)
    job = store.enqueue("alice", p["id"])
    assert process_one(store, settings)
    completed = store.job("alice", job["id"])
    assert completed["state"] == "completed", completed
    output = json.loads(completed["output"])
    prs = Presentation(store.root / output["pptx"])
    picture = next(s for s in prs.slides[0].shapes if s.name == "rsa:image")
    assert picture.image.blob == data.getvalue()
    assert "preview" not in output
