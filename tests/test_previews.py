import json

import pytest
from conftest import saved_project

from research_slide_agent import previews
from research_slide_agent.store import StateError
from research_slide_agent.worker import process_one


def completed(store, settings):
    project, spec = saved_project(store)
    job = store.enqueue("alice", project["id"])
    assert process_one(store, settings)
    return project, job, spec


def rendered(store, settings, job_id, **kwargs):
    data, info = previews.preview_image(store, "alice", job_id, **kwargs)
    if data is None:
        assert info["state"] == "queued"
        assert process_one(store, settings)
        data, info = previews.preview_image(store, "alice", job_id, **kwargs)
    assert data is not None
    return data, info


def test_api_queues_once_and_worker_renders_before_images_are_served(store, settings, preview_renderer):
    _, job, _ = completed(store, settings)
    assert previews.preview_files(store, "alice", job["id"]) is None
    data, pending = previews.preview_image(store, "alice", job["id"], overview=True)
    assert data is None and pending["state"] == "queued" and not preview_renderer
    again = previews.preview_image(store, "alice", job["id"])[1]
    assert again["preview_job_id"] == pending["preview_job_id"]
    assert process_one(store, settings)
    data, metadata = previews.preview_image(store, "alice", job["id"], overview=True)
    assert data.startswith(b"\x89PNG") and metadata["pages"] == [1, 2, 3, 4, 5]
    assert metadata["state"] == "ready" and metadata["next_page"] is None
    assert metadata["visual_review"] == "not_performed" and not metadata["powerpoint_verified"]
    single, info = previews.preview_image(store, "alice", job["id"], page=2)
    assert single.startswith(b"\x89PNG") and info["pages"] == [2] and info["next_page"] == 3
    assert len(preview_renderer) == 1
    assert store.job("alice", pending["preview_job_id"])["state"] == "completed"
    assert store.job("alice", job["id"])["state"] == "completed"


@pytest.mark.parametrize("page", [0, 6, 41])
def test_invalid_page_is_rejected_before_conversion(store, settings, preview_renderer, page):
    _, job, _ = completed(store, settings)
    with pytest.raises(StateError, match="PREVIEW_PAGE_OUT_OF_RANGE"):
        previews.preview_image(store, "alice", job["id"], page)
    assert not preview_renderer


def test_cached_previews_obey_ownership_and_expiry(store, settings, preview_renderer):
    project, job, _ = completed(store, settings)
    rendered(store, settings, job["id"])
    with pytest.raises(StateError):
        previews.preview_image(store, "bob", job["id"])
    with store.connect() as con:
        con.execute("UPDATE projects SET expires=0 WHERE id=?", (project["id"],))
    with pytest.raises(StateError, match="EXPIRED"):
        previews.preview_image(store, "alice", job["id"])


def test_cache_fingerprint_mismatch_is_rerendered_only_by_worker(store, settings, preview_renderer):
    _, job, _ = completed(store, settings)
    rendered(store, settings, job["id"])
    directory, _ = previews.preview_files(store, "alice", job["id"])
    manifest = directory / "preview.json"
    data = json.loads(manifest.read_text())
    data["pptx_sha256"] = "wrong-version"
    manifest.write_text(json.dumps(data))
    assert previews.preview_files(store, "alice", job["id"]) is None
    pending = previews.preview_image(store, "alice", job["id"])
    assert pending[0] is None and len(preview_renderer) == 1
    assert process_one(store, settings)
    assert previews.preview_image(store, "alice", job["id"])[0].startswith(b"\x89PNG")
    assert len(preview_renderer) == 2


def test_render_failure_leaves_pptx_available_and_can_be_retried(store, settings, preview_renderer, monkeypatch):
    _, job, _ = completed(store, settings)
    render = previews.render

    def fail(*args):
        raise RuntimeError("test failure")

    monkeypatch.setattr(previews, "render", fail)
    pending = previews.preview_image(store, "alice", job["id"])[1]
    assert process_one(store, settings)
    assert store.job("alice", pending["preview_job_id"])["state"] == "failed"
    assert previews.preview_image(store, "alice", job["id"])[1]["state"] == "failed"
    assert previews.preview_files(store, "alice", job["id"]) is None
    assert store.job("alice", job["id"])["state"] == "completed"
    store.retry("alice", pending["preview_job_id"])
    monkeypatch.setattr(previews, "render", render)
    assert process_one(store, settings)
    assert previews.preview_image(store, "alice", job["id"])[0].startswith(b"\x89PNG")


def test_pending_job_has_no_preview(store):
    project, _ = saved_project(store)
    job = store.enqueue("alice", project["id"])
    with pytest.raises(StateError, match="JOB_NOT_COMPLETED"):
        previews.preview_image(store, "alice", job["id"])


def test_large_manual_output_is_rejected_by_worker_while_pptx_remains_available(store, settings, preview_renderer):
    from pptx import Presentation

    _, job, _ = completed(store, settings)
    output = json.loads(store.job("alice", job["id"])["output"])
    large = Presentation()
    for _ in range(41):
        large.slides.add_slide(large.slide_layouts[6])
    large.save(store.root / output["pptx"])
    pending = previews.preview_image(store, "alice", job["id"])[1]
    assert process_one(store, settings)
    assert store.job("alice", pending["preview_job_id"])["error"] == "PREVIEW_PAGE_LIMIT"
    assert not preview_renderer and previews.preview_files(store, "alice", job["id"]) is None
    assert store.job("alice", job["id"])["state"] == "completed"


def test_rendering_respects_the_existing_user_job_limit(store, settings, preview_renderer):
    _, first, _ = completed(store, settings)
    _, second, _ = completed(store, settings)
    assert previews.preview_image(store, "alice", first["id"])[1]["state"] == "queued"
    with pytest.raises(StateError, match="PREVIEW_BUSY"):
        previews.preview_image(store, "alice", second["id"])
    assert not preview_renderer


def test_expiry_during_worker_render_does_not_publish_preview(store, settings, preview_renderer, monkeypatch):
    project, job, _ = completed(store, settings)
    render = previews.render

    def expire(path, directory):
        result = render(path, directory)
        with store.connect() as con:
            con.execute("UPDATE projects SET expires=0 WHERE id=?", (project["id"],))
        return result

    monkeypatch.setattr(previews, "render", expire)
    previews.preview_image(store, "alice", job["id"])
    with pytest.raises(StateError, match="EXPIRED"):
        process_one(store, settings)
    with store.connect() as con:
        output = json.loads(con.execute("SELECT output FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])
    assert not (store.root / output["directory"] / "preview").exists()


def test_new_spec_gets_new_previews_while_old_job_stays_immutable(store, settings, preview_renderer):
    project, first, spec = completed(store, settings)
    _, before = rendered(store, settings, first["id"])
    from research_slide_agent.models import SlideSpec

    raw = spec.model_dump()
    raw["spec_version"] = 2
    raw["slides"][0]["title"] = "Changed version"
    store.save_spec("alice", project["id"], SlideSpec.model_validate(raw), 1)
    second = store.enqueue("alice", project["id"])
    assert process_one(store, settings)
    _, after = rendered(store, settings, second["id"])
    assert before["pptx_sha256"] != after["pptx_sha256"]
    assert previews.preview_image(store, "alice", first["id"])[1]["pptx_sha256"] == before["pptx_sha256"]
    assert len(preview_renderer) == 2


def test_changed_source_is_rejected_after_preview_is_queued(store, settings, preview_renderer):
    _, job, _ = completed(store, settings)
    pending = previews.preview_image(store, "alice", job["id"])[1]
    output = json.loads(store.job("alice", job["id"])["output"])
    path = store.root / output["pptx"]
    path.write_bytes(path.read_bytes() + b'changed')
    assert process_one(store, settings)
    assert store.job("alice", pending["preview_job_id"])["error"] == "PREVIEW_SOURCE_CHANGED"
    assert not preview_renderer


def test_unfinished_render_job_cannot_publish_cached_images(store, settings, preview_renderer, monkeypatch):
    _, job, _ = completed(store, settings)
    pending = previews.preview_image(store, "alice", job["id"])[1]
    finish = store.finish
    checked = []

    def inspect(job_id, token, state, **kwargs):
        if job_id == pending["preview_job_id"] and state == "validating":
            output = json.loads(store.job("alice", job["id"])["output"])
            assert (store.root / output["directory"] / "preview/preview.json").exists()
            assert previews.preview_files(store, "alice", job["id"]) is None
            checked.append(True)
        return finish(job_id, token, state, **kwargs)

    monkeypatch.setattr(store, "finish", inspect)
    assert process_one(store, settings) and checked
    assert previews.preview_files(store, "alice", job["id"]) is not None
