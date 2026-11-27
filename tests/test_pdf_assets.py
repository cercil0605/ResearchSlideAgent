import base64
import io
import json
import socket
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject, RectangleObject
from starlette.testclient import TestClient

from research_slide_agent.app import create_app
from research_slide_agent.models import SlideSpec
from research_slide_agent.pdf_assets import PdfRegion, render_page
from research_slide_agent.store import StateError, Store
from research_slide_agent.worker import process_one


def paper_bytes(rotation=0, cropped=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=200)
    stream = DecodedStreamObject()
    stream.set_data(b"1 0 0 rg 0 100 200 100 re f\n0 1 0 rg 200 100 200 100 re f\n"
                    b"0 0 1 rg 0 0 200 100 re f\n1 1 0 rg 200 0 200 100 re f\n")
    page[NameObject("/Contents")] = writer._add_object(stream)
    if cropped:
        page.cropbox = RectangleObject([100, 50, 300, 150])
    page.rotate(rotation)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize("rotation,color", [(0, (255, 0, 0)), (90, (0, 0, 255)),
                                            (180, (255, 255, 0)), (270, (0, 255, 0))])
@pytest.mark.parametrize("cropped", [False, True])
def test_crop_matches_displayed_page_with_rotation_and_cropbox(tmp_path, rotation, color, cropped):
    path = tmp_path / "paper.pdf"
    path.write_bytes(paper_bytes(rotation, cropped))
    data, full = render_page(path, 1, 72)
    region = PdfRegion(left=0.05, top=0.05, right=0.45, bottom=0.45)
    crop, metadata = render_page(path, 1, 72, region)
    with Image.open(io.BytesIO(data)) as image, Image.open(io.BytesIO(crop)) as part:
        assert part.getpixel((part.width // 2, part.height // 2))[:3] == color
        assert part.tobytes() == image.crop(metadata["pixel_bounds"]).tobytes()
    expected_width = (100 if cropped else 200) if rotation in (90, 270) else (200 if cropped else 400)
    assert full["page_pixel_width"] == expected_width
    assert metadata["coordinate_system"] == "normalized_top_left_displayed_cropbox"


def test_pdf_limits_and_invalid_bounds(tmp_path):
    path = tmp_path / "paper.pdf"
    path.write_bytes(paper_bytes())
    for page, dpi in [(0, 144), (2, 144), (1, 0), (1, 301)]:
        with pytest.raises(ValueError):
            render_page(path, page, dpi)
    for bounds in [(0.5, 0, 0.4, 1), (0, 0, 1, 0), (-0.1, 0, 1, 1), (0, 0, float("nan"), 1)]:
        with pytest.raises(ValueError):
            PdfRegion(left=bounds[0], top=bounds[1], right=bounds[2], bottom=bounds[3])
    writer = PdfWriter()
    writer.add_blank_page(width=20000, height=10000)
    writer.write(path)
    _, info = render_page(path, 1, 300)
    assert max(info["page_pixel_width"], info["page_pixel_height"]) <= 3200


def rpc(client, name, **arguments):
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                         "params": {"name": name, "arguments": arguments}},
                           headers={"Accept": "application/json, text/event-stream"})
    assert response.status_code == 200
    return response.json()["result"]


def test_mcp_pdf_crop_to_strict_pptx(settings, monkeypatch):
    from research_slide_agent import server

    settings.template = Path("templates/lab-template.pptx")
    app = create_app(settings)
    monkeypatch.setenv("RSA_ATTACHMENT_HOSTS", "files.example.org")

    original = httpx.AsyncClient

    def download_client(**kwargs):
        return original(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(200, content=paper_bytes())))

    monkeypatch.setattr(server.httpx, "AsyncClient", download_client)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))])
    with TestClient(app, base_url=settings.base_url, client=("127.0.0.1", 1234)) as client:
        pid = rpc(client, "create_project")["structuredContent"]["id"]
        transfer = rpc(client, "get_file_transfer_info")["structuredContent"]
        assert transfer["configured_download_hosts"] == ["files.example.org"]
        source = rpc(client, "register_chatgpt_file", presentation_id=pid,
                     file={"download_url": "https://files.example.org/temporary", "file_id": "f1"})
        assert not source.get("isError"), source
        source_id = source["structuredContent"]["source_id"]
        page = rpc(client, "render_pdf_page", presentation_id=pid, source_id=source_id, page=1)
        assert not page.get("isError"), page
        assert any(c["type"] == "image" for c in page["content"])
        assert len(app.state.store.files("dev-user", pid)) == 1
        args = {"presentation_id": pid, "source_id": source_id, "page": 1,
                "region": {"left": 0, "top": 0, "right": 0.5, "bottom": 0.5}}
        result = rpc(client, "crop_pdf_region", **args)
        assert not result.get("isError"), result
        image_id = result["structuredContent"]["source_id"]
        assert image_id != source_id
        assert result["structuredContent"]["citation_source_id"] == source_id
        assert rpc(client, "crop_pdf_region", **args)["structuredContent"]["source_id"] == image_id
        registered = app.state.store.file("dev-user", pid, image_id)
        image = next(c for c in result["content"] if c["type"] == "image")
        assert base64.b64decode(image["data"]) == registered["path"].read_bytes()
        # Metadata may be discovered after cropping: set it once on the PDF.
        metadata = rpc(client, "set_source_metadata", presentation_id=pid, source_id=source_id,
                       author="Test", year=2026)
        assert not metadata.get("isError"), metadata
        assert app.state.store.file("dev-user", pid, image_id)["author"] == "Test"
        raw = json.loads(Path("examples/research-format.slidespec.json").read_text())
        item = next(s for s in raw["slides"] if s["prototype_id"] == "results_figure")
        item.update(slide_order=1, diagram_spec=None,
                    image_references=[{"id": "fig", "source_id": image_id, "caption": "Original figure"}],
                    source_references=[{"source_id": source_id, "locator": "p.1, Figure 1"}],
                    citations=[{"source": {"source_id": source_id, "locator": "p.1, Figure 1"},
                                "author": "Test", "year": 2026, "target_id": "fig"}])
        item["replacements"]["図題"] = [{"text": "Original figure [Test '26]"}]
        raw.update(presentation_id=pid, purpose_mode="general", slides=[item])
        spec = SlideSpec.model_validate(raw)
        saved = rpc(client, "save_slide_spec", presentation_id=pid, spec=spec.model_dump(), expected_version=0)
        assert not saved.get("isError"), saved
        jid = rpc(client, "enqueue_generation", presentation_id=pid, wait=False)["structuredContent"]["id"]
        assert process_one(app.state.store, settings)
        job = app.state.store.job("dev-user", jid)
        assert job["state"] == "completed", job
        path = app.state.store.root / json.loads(job["output"])["pptx"]
        with ZipFile(path) as archive:
            assert registered["path"].read_bytes() in [archive.read(n) for n in archive.namelist()
                                                       if n.startswith("ppt/media/")]
        assert rpc(client, "set_source_metadata", presentation_id=pid, source_id=source_id,
                   author="Changed", year=2026).get("isError")
        with pytest.raises(StateError):
            app.state.store.file("another-user", pid, image_id)
        with app.state.store.connect() as con:
            con.execute("UPDATE projects SET expires=0 WHERE id=?", (pid,))
        assert rpc(client, "render_pdf_page", presentation_id=pid, source_id=source_id).get("isError")


def test_derived_assets_quota_metadata_and_database_migration(store, settings, monkeypatch):
    pid = store.create("alice")["id"]
    parent = store.register("alice", pid, "paper.pdf", paper_bytes(), "Test", 2026)
    png, meta = render_page(store.file("alice", pid, parent["source_id"])["path"], 1, 72)
    origin = {"source_id": parent["source_id"], "sha256": parent["sha256"], **meta}
    for i in range(12):
        store.register("alice", pid, "figure.png", png, _origin={**origin, "test_index": i})
    for i in range(9):
        store.register("alice", pid, f"{i}.csv", b"a,b")
    assert len(store.files("alice", pid)) == 22
    with pytest.raises(StateError, match="FILE_LIMIT"):
        store.register("alice", pid, "extra.csv", b"a,b")
    child = next(f for f in store.files("alice", pid) if f["origin"])
    assert child["author"] == "Test" and child["year"] == 2026
    with pytest.raises(StateError, match="DERIVED_SOURCE"):
        store.source_metadata("alice", pid, child["id"], "Wrong", 2025)
    for i in range(12, 80):
        store.register("alice", pid, "figure.png", png, _origin={**origin, "test_index": i})
    with pytest.raises(StateError, match="ASSET_LIMIT"):
        store.register("alice", pid, "figure.png", png, _origin={**origin, "test_index": 80})
    from research_slide_agent import store as state

    monkeypatch.setattr(state, "MAX_TOTAL", len(paper_bytes()))
    with pytest.raises(StateError, match="FILE_LIMIT"):
        store.register("alice", pid, "figure.png", png, _origin={**origin, "test_index": 81})
    # A pre-feature DB is migrated additively; source IDs and existing rows survive.
    with store.connect() as con:
        con.execute("DELETE FROM files WHERE origin IS NOT NULL")
        con.execute("ALTER TABLE files DROP COLUMN origin")
    reopened = Store(settings)
    assert reopened.file("alice", pid, parent["source_id"])["sha"] == parent["sha256"]
    assert all(f["origin"] is None for f in reopened.files("alice", pid))


def test_pdf_access_and_wrong_type_are_rejected_before_render(settings, monkeypatch):
    from research_slide_agent import server

    app = create_app(settings)
    other = app.state.store.create("other-user")["id"]
    own = app.state.store.create("dev-user")["id"]
    foreign = app.state.store.register("other-user", other, "paper.pdf", paper_bytes())["source_id"]
    wrong_type = app.state.store.register("dev-user", own, "data.csv", b"a,b")["source_id"]

    def never_render(*args, **kwargs):
        pytest.fail("Must check project and source ownership before rendering")

    monkeypatch.setattr(server, "render_page", never_render)
    with TestClient(app, base_url=settings.base_url, client=("127.0.0.1", 1234)) as client:
        for pid, source in [(other, foreign), (own, foreign), (own, wrong_type)]:
            assert rpc(client, "render_pdf_page", presentation_id=pid, source_id=source).get("isError")
            assert rpc(client, "crop_pdf_region", presentation_id=pid, source_id=source, page=1,
                       region={"left": 0, "top": 0, "right": 1, "bottom": 1}).get("isError")


def test_manual_fallback_explains_pdf_workflow_and_escapes_filenames(settings):
    app = create_app(settings)
    with TestClient(app, base_url=settings.base_url, client=("127.0.0.1", 1234)) as client:
        pid = app.state.store.create("dev-user")["id"]
        app.state.store.register("dev-user", pid, '<img src=x onerror="bad()">.csv', b"a,b")
        response = client.get("/project/" + pid)
        assert response.status_code == 200
        assert 'type="file" multiple' in response.text
        assert '<img src=x' not in response.text
        assert '&lt;img' in response.text
        assert '<pre>' not in response.text


def test_renderer_failure_is_bounded_and_does_not_expose_stderr(tmp_path, monkeypatch):
    import subprocess

    from research_slide_agent import pdf_assets

    path = tmp_path / "paper.pdf"
    path.write_bytes(paper_bytes())

    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 30
        raise subprocess.TimeoutExpired("pdftoppm", 30)

    monkeypatch.setattr(pdf_assets.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="RENDER_TIMEOUT"):
        render_page(path)
    monkeypatch.setattr(pdf_assets.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        [], 1, stdout=b"", stderr=b"private reference text"))
    with pytest.raises(ValueError, match="RENDER_FAILED") as caught:
        render_page(path)
    assert "private" not in str(caught.value)
