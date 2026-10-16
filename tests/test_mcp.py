import asyncio
import socket

import pytest
import uvicorn
from mcp import Client

from research_slide_agent.app import create_app
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
