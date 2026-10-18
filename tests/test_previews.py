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


def test_preview_images_are_cached_and_never_claim_visual_review(store, settings, preview_renderer):
    _, job, _ = completed(store, settings)
    assert previews.preview_files(store, "alice", job["id"]) is None
    data, metadata = previews.preview_image(store, "alice", job["id"], overview=True)
    assert data.startswith(b"\x89PNG") and metadata["pages"] == [1, 2, 3, 4, 5]
    assert metadata["next_page"] is None and metadata["visual_review"] == "not_performed"
    assert metadata["powerpoint_verified"] is False
    single, info = previews.preview_image(store, "alice", job["id"], page=2)
    assert single.startswith(b"\x89PNG") and info["pages"] == [2]
    assert info["next_page"] == 3
    assert len(preview_renderer) == 1


@pytest.mark.parametrize("page", [0, 6, 41])
def test_invalid_page_is_rejected_before_conversion(store, settings, preview_renderer, page):
    _, job, _ = completed(store, settings)
    with pytest.raises(StateError, match="PREVIEW_PAGE_OUT_OF_RANGE"):
        previews.preview_image(store, "alice", job["id"], page)
    assert not preview_renderer


def test_cached_previews_obey_ownership_and_expiry(store, settings, preview_renderer):
    project, job, _ = completed(store, settings)
    previews.preview_image(store, "alice", job["id"])
    with pytest.raises(StateError):
        previews.preview_image(store, "bob", job["id"])
    with store.connect() as con:
        con.execute("UPDATE projects SET expires=0 WHERE id=?", (project["id"],))
    with pytest.raises(StateError, match="EXPIRED"):
        previews.preview_image(store, "alice", job["id"])


def test_cache_fingerprint_mismatch_renders_again(store, settings, preview_renderer):
    _, job, _ = completed(store, settings)
    directory, _ = previews.preview_files(store, "alice", job["id"], create=True)
    manifest = directory / "preview.json"
    data = json.loads(manifest.read_text())
    data["pptx_sha256"] = "wrong-version"
    manifest.write_text(json.dumps(data))
    assert previews.preview_files(store, "alice", job["id"]) is None
    previews.preview_image(store, "alice", job["id"])
    assert len(preview_renderer) == 2


def test_render_failure_leaves_pptx_available_and_can_be_retried(store, settings, preview_renderer, monkeypatch):
    _, job, _ = completed(store, settings)
    render = previews.render

    def fail(*args):
        raise RuntimeError("test failure")

    monkeypatch.setattr(previews, "render", fail)
    with pytest.raises(StateError, match="PREVIEW_RENDER_FAILED"):
        previews.preview_image(store, "alice", job["id"])
    assert previews.preview_files(store, "alice", job["id"]) is None
    assert store.job("alice", job["id"])["state"] == "completed"
    monkeypatch.setattr(previews, "render", render)
    assert previews.preview_image(store, "alice", job["id"])[0].startswith(b"\x89PNG")


def test_pending_job_has_no_preview(store):
    project, _ = saved_project(store)
    job = store.enqueue("alice", project["id"])
    with pytest.raises(StateError, match="JOB_NOT_COMPLETED"):
        previews.preview_image(store, "alice", job["id"])


def test_large_manual_output_is_not_rendered_and_remains_downloadable(store, settings, preview_renderer):
    from pptx import Presentation

    _, job, _ = completed(store, settings)
    output = json.loads(store.job("alice", job["id"])["output"])
    large = Presentation()
    for _ in range(41):
        large.slides.add_slide(large.slide_layouts[6])
    large.save(store.root / output["pptx"])
    with pytest.raises(StateError, match="PREVIEW_PAGE_LIMIT"):
        previews.preview_image(store, "alice", job["id"])
    assert not preview_renderer
    assert previews.preview_files(store, "alice", job["id"]) is None
    assert store.job("alice", job["id"])["state"] == "completed"


def test_rendering_is_bounded(store, settings, preview_renderer):
    _, job, _ = completed(store, settings)
    assert previews._RENDER_SLOT.acquire(blocking=False)
    try:
        with pytest.raises(StateError, match="PREVIEW_BUSY"):
            previews.preview_image(store, "alice", job["id"])
    finally:
        previews._RENDER_SLOT.release()
    assert not preview_renderer


def test_expiry_during_render_does_not_publish_preview(store, settings, preview_renderer, monkeypatch):
    project, job, _ = completed(store, settings)
    render = previews.render

    def expire(path, directory):
        result = render(path, directory)
        with store.connect() as con:
            con.execute("UPDATE projects SET expires=0 WHERE id=?", (project["id"],))
        return result

    monkeypatch.setattr(previews, "render", expire)
    with pytest.raises(StateError, match="EXPIRED"):
        previews.preview_image(store, "alice", job["id"])
    with store.connect() as con:
        output = json.loads(con.execute("SELECT output FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])
    assert not (store.root / output["directory"] / "preview").exists()


def test_new_spec_gets_new_previews_while_old_job_stays_immutable(store, settings, preview_renderer):
    project, first, spec = completed(store, settings)
    _, before = previews.preview_image(store, "alice", first["id"])
    from research_slide_agent.models import SlideSpec

    raw = spec.model_dump()
    raw["spec_version"] = 2
    raw["slides"][0]["title"] = "Changed version"
    store.save_spec("alice", project["id"], SlideSpec.model_validate(raw), 1)
    second = store.enqueue("alice", project["id"])
    assert process_one(store, settings)
    _, after = previews.preview_image(store, "alice", second["id"])
    assert before["pptx_sha256"] != after["pptx_sha256"]
    assert previews.preview_image(store, "alice", first["id"])[1]["pptx_sha256"] == before["pptx_sha256"]
    assert len(preview_renderer) == 2
