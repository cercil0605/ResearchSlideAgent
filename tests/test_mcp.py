import asyncio
import base64
import hashlib
import io
import json
import socket
from pathlib import Path

import pytest
import uvicorn
from mcp import Client
from PIL import Image

from research_slide_agent.app import create_app
from research_slide_agent.models import SlideSpec
from research_slide_agent.worker import process_one


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["legacy", "auto"])
async def test_real_streamable_http_workflow(settings, mode):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    settings.base_url = f"http://127.0.0.1:{port}"
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.02)
        async with Client(settings.base_url + "/mcp", mode=mode) as session:
            tools = (await session.list_tools()).tools
            names = {t.name for t in tools}
            assert {"create_project", "save_slide_spec", "enqueue_generation", "show_viewer"} <= names
            assert not any("approve_from" in n for n in names)
            file_tool = next(t for t in tools if t.name == "register_chatgpt_file")
            assert file_tool.meta["openai/fileParams"] == ["file"]
            schema = file_tool.input_schema["$defs"]["OpenAIFile"]
            assert set(schema["required"]) == {"download_url", "file_id"}
            assert {"file_name", "mime_type"} <= schema["properties"].keys()
            profile = await session.call_tool("get_profile", {})
            assert not profile.is_error, profile
            assert profile.structured_content["id"] == "dev-user"
            created = await session.call_tool("create_project", {})
            pid = created.structured_content["id"]
            from research_slide_agent.sample import sample_spec

            spec = sample_spec(pid)
            result = await session.call_tool(
                "save_slide_spec",
                {"presentation_id": pid, "spec": spec.model_dump(), "expected_version": 0},
            )
            assert not result.is_error
            result = await session.call_tool("enqueue_generation", {"presentation_id": pid})
            assert result.is_error
            for stage, target in [("outline", "")] + [("slide", s.slide_id) for s in spec.slides]:
                r = await session.call_tool(
                    "request_approval", {"presentation_id": pid, "stage": stage, "slide_id": target}
                )
                app.state.store.approve_from_browser("dev-user", r.structured_content["review_id"])
            queued = await session.call_tool("enqueue_generation", {"presentation_id": pid})
            job = queued.structured_content
            assert job["state"] == "queued"
            assert await asyncio.to_thread(process_one, app.state.store, settings)
            result = await session.call_tool("get_preview", {"job_id": job["id"]})
            assert result.structured_content["job"]["state"] == "completed"
            resource = await session.read_resource("ui://research-slide-agent/viewer.html")
            assert "Research Slide Agent" in resource.contents[0].text
            assert resource.contents[0].mime_type == "text/html;profile=mcp-app"
    finally:
        server.should_exit = True
        await task


@pytest.mark.asyncio
async def test_canonical_generation_delivers_real_image_content(settings):
    settings.template = Path("templates/lab-template.pptx")
    settings.require_render = True
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    settings.base_url = f"http://127.0.0.1:{listener.getsockname()[1]}"
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.02)
        async with Client(settings.base_url + "/mcp") as session:
            created = await session.call_tool("create_project", {})
            pid = created.structured_content["id"]
            raw = json.loads(Path("examples/research-format.slidespec.json").read_text())
            item = next(s for s in raw["slides"] if s.get("table_spec"))
            item["slide_order"] = 1
            raw.update(presentation_id=pid, purpose_mode="general", slides=[item])
            spec = SlideSpec.model_validate(raw)
            saved = await session.call_tool("save_slide_spec", {
                "presentation_id": pid, "spec": spec.model_dump(), "expected_version": 0})
            assert not saved.is_error
            for stage, target in [("outline", ""), ("slide", item["slide_id"])]:
                review = await session.call_tool("request_approval", {
                    "presentation_id": pid, "stage": stage, "slide_id": target})
                app.state.store.approve_from_browser("dev-user", review.structured_content["review_id"])
            queued = await session.call_tool("enqueue_generation", {"presentation_id": pid})
            jid = queued.structured_content["id"]
            premature = await session.call_tool("get_preview_image", {"job_id": jid, "page": 1})
            assert premature.is_error
            await asyncio.to_thread(process_one, app.state.store, settings)
            job = app.state.store.job("dev-user", jid)
            assert job["state"] == "completed", job
            result = await session.call_tool("get_preview_image", {"job_id": jid, "page": 1})
            assert not result.is_error, result
            block = next(c for c in result.content if c.type == "image")
            data = base64.b64decode(block.data)
            assert block.mime_type == "image/png"
            with Image.open(io.BytesIO(data)) as image:
                assert image.format == "PNG" and max(image.size) == 1600
            metadata = json.loads(next(c.text for c in result.content if c.type == "text"))
            assert metadata["image_sha256"] == hashlib.sha256(data).hexdigest()
            assert metadata["visual_review"] == "pending"
            report = await session.call_tool("get_generation_report", {"job_id": jid})
            assert report.structured_content["quality"]["format_conformance"] == "canonical_slide_xml_and_shared_parts"
            assert report.structured_content["provenance"]["code_commit"]
            for page in (0, 2):
                invalid = await session.call_tool("get_preview_image", {"job_id": jid, "page": page})
                assert invalid.is_error
            with app.state.store.connect() as con:
                con.execute("UPDATE projects SET expires=0 WHERE id=?", (pid,))
            expired = await session.call_tool("get_preview_image", {"job_id": jid, "page": 1})
            assert expired.is_error
    finally:
        server.should_exit = True
        await task
