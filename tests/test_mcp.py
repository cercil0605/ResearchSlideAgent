import asyncio
import json
import socket
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import Client

from research_slide_agent.app import create_app
from research_slide_agent.models import SlideSpec
from research_slide_agent.rules import RULES_RESOURCE_URI, SERVER_INSTRUCTIONS, authoring_context
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
            assert session.instructions == SERVER_INSTRUCTIONS
            tools = (await session.list_tools()).tools
            names = {t.name for t in tools}
            assert {"get_authoring_context", "create_project", "save_slide_spec",
                    "enqueue_generation", "show_viewer", "get_slide_preview"} <= names
            assert "request_approval" not in names
            assert "get_preview_image" not in names
            context_tool = next(t for t in tools if t.name == "get_authoring_context")
            assert context_tool.annotations.read_only_hint
            context = await session.call_tool("get_authoring_context", {})
            assert not context.is_error
            assert context.structured_content == authoring_context()
            # A resource is an optional discovery route, not a replacement for the tool.
            resources = await session.list_resources()
            assert RULES_RESOURCE_URI in {str(resource.uri) for resource in resources.resources}
            resource = await session.read_resource(RULES_RESOURCE_URI)
            assert resource.contents[0].mime_type == "application/json"
            assert json.loads(resource.contents[0].text) == context.structured_content
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
async def test_canonical_download_then_on_demand_preview(settings, preview_renderer):
    settings.template = Path("templates/lab-template.pptx")
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
            item["section"] = "results"
            raw.update(presentation_id=pid, purpose_mode="general", schema_version="1.2", slides=[item])
            spec = SlideSpec.model_validate(raw)
            saved = await session.call_tool("save_slide_spec", {
                "presentation_id": pid, "spec": spec.model_dump(), "expected_version": 0})
            assert not saved.is_error
            assert saved.structured_content["authoring_feedback"]["pages"][0]["section"] == "results"
            queued = await session.call_tool("enqueue_generation", {"presentation_id": pid})
            jid = queued.structured_content["id"]
            pending = await session.call_tool("get_job", {"job_id": jid})
            assert "download_url" not in pending.structured_content
            await asyncio.to_thread(process_one, app.state.store, settings)
            job = app.state.store.job("dev-user", jid)
            assert job["state"] == "completed", job
            result = await session.call_tool("get_job", {"job_id": jid})
            url = result.structured_content["download_url"]
            assert result.structured_content["expires_in"] == 600
            output = json.loads(job["output"])
            assert "preview" not in output
            directory = settings.data_dir / output["directory"]
            assert not list(directory.rglob("*.pdf")) and not list(directory.rglob("*.png"))
            async with httpx.AsyncClient(trust_env=False) as browser:
                response = await browser.get(url)
                assert response.status_code == 200 and response.content.startswith(b"PK")
            legacy = await session.call_tool("get_preview", {"job_id": jid})
            assert legacy.structured_content["images"] == []
            viewer = await session.call_tool("show_viewer", {"job_id": jid})
            assert viewer.structured_content["images"] == []
            report = await session.call_tool("get_generation_report", {"job_id": jid})
            assert report.structured_content["quality"]["format_conformance"] == "canonical_slide_xml_and_shared_parts"
            assert report.structured_content["provenance"]["code_commit"]
            rendered = await session.call_tool("get_slide_preview", {"job_id": jid, "overview": True})
            assert rendered.structured_content["state"] == "queued"
            preview_job_id = rendered.structured_content["preview_job_id"]
            assert not any(content.type == "image" for content in rendered.content)
            assert not preview_renderer  # The networked API never launches LibreOffice.
            await asyncio.to_thread(process_one, app.state.store, settings)
            rendered = await session.call_tool("get_slide_preview", {"job_id": jid, "overview": True})
            assert not rendered.is_error, rendered
            assert rendered.structured_content["pages"] == [1]
            assert rendered.structured_content["visual_review"] == "not_performed"
            assert any(content.type == "image" for content in rendered.content)
            rendering_job = await session.call_tool("get_job", {"job_id": preview_job_id})
            assert rendering_job.structured_content["state"] == "completed"
            assert "download_url" not in rendering_job.structured_content
            assert (await session.call_tool("get_generation_report", {"job_id": preview_job_id})).is_error
            links = await session.call_tool("get_preview", {"job_id": jid})
            image_url = links.structured_content["images"][0]
            pdf_url = links.structured_content["pdf_url"]
            assert len(preview_renderer) == 1
            async with httpx.AsyncClient(trust_env=False) as browser:
                image = await browser.get(image_url)
                assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
                pdf = await browser.get(pdf_url)
                assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
                assert (await browser.get(image_url.replace("slide-1.png", "preview.json"))).status_code == 401
            with app.state.store.connect() as con:
                con.execute("UPDATE projects SET expires=0 WHERE id=?", (pid,))
            expired = await session.call_tool("get_job", {"job_id": jid})
            assert expired.is_error
            async with httpx.AsyncClient(trust_env=False) as browser:
                assert (await browser.get(url)).status_code == 400
                assert (await browser.get(image_url)).status_code == 400
                assert (await browser.get(pdf_url)).status_code == 400
    finally:
        server.should_exit = True
        await task
