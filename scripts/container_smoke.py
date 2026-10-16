"""Isolated loopback smoke test with synthetic data. Never targets a production server."""

import asyncio
import json
import re
import socket
import tempfile
from pathlib import Path

import httpx
import uvicorn
from mcp import Client

from research_slide_agent.app import create_app
from research_slide_agent.config import Settings
from research_slide_agent.sample import sample_spec
from research_slide_agent.worker import process_one


async def main():
    with tempfile.TemporaryDirectory(prefix="rsa-smoke-") as scratch:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        base = f"http://127.0.0.1:{listener.getsockname()[1]}"
        settings = Settings(
            dev=True, data_dir=Path(scratch), base_url=base, template=Path("/templates/lab-template.pptx")
        )
        app = create_app(settings)
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            while not server.started:
                await asyncio.sleep(0.02)
            async with (
                Client(base + "/mcp", mode="legacy") as client,
                httpx.AsyncClient(base_url=base, follow_redirects=True, trust_env=False) as browser,
            ):
                p = (await client.call_tool("create_project", {})).structured_content
                spec = sample_spec(p["id"])
                saved = await client.call_tool(
                    "save_slide_spec",
                    {"presentation_id": p["id"], "spec": spec.model_dump(), "expected_version": 0},
                )
                assert not saved.is_error
                rejected = await client.call_tool("enqueue_generation", {"presentation_id": p["id"]})
                assert rejected.is_error
                for stage, target in [("outline", "")] + [("slide", s.slide_id) for s in spec.slides]:
                    r = (
                        await client.call_tool(
                            "request_approval",
                            {"presentation_id": p["id"], "stage": stage, "slide_id": target},
                        )
                    ).structured_content
                    page = await browser.get(r["review_url"])
                    assert page.status_code == 200
                    token = json.loads(re.search(r"'X-CSRF':(\"[^\"]+\")", page.text).group(1))
                    approved = await browser.post(
                        r["review_url"], json={}, headers={"X-CSRF": token, "Origin": base}
                    )
                    assert approved.status_code == 200
                job = (
                    await client.call_tool("enqueue_generation", {"presentation_id": p["id"]})
                ).structured_content
                assert await asyncio.to_thread(process_one, app.state.store, settings)
                preview = (await client.call_tool("get_preview", {"job_id": job["id"]})).structured_content
                assert preview["job"]["state"] == "completed", preview
                assert len(preview["images"]) == 5
                response = await browser.get(preview["download_url"])
                assert response.status_code == 200 and response.content.startswith(b"PK")
                assert (await browser.get(preview["images"][0]["url"])).status_code == 200
                resource = await client.read_resource("ui://research-slide-agent/viewer.html")
                assert "Research Slide Agent" in resource.contents[0].text
                print(
                    json.dumps(
                        {
                            "status": "passed",
                            "mcp": "2.3.0",
                            "approval": "browser_session_csrf_synthetic_only",
                            "rendered_pages": 5,
                            "download_bytes": len(response.content),
                        }
                    )
                )
        finally:
            server.should_exit = True
            await task


if __name__ == "__main__":
    asyncio.run(main())
