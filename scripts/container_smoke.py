"""Isolated loopback smoke test with synthetic data. Never targets a production server."""

import asyncio
import json
import socket
import tempfile
from pathlib import Path

import httpx
import uvicorn
from mcp import Client

from research_slide_agent.app import create_app
from research_slide_agent.config import Settings
from research_slide_agent.models import SlideSpec
from research_slide_agent.worker import process_one


async def main():
    with tempfile.TemporaryDirectory(prefix="rsa-smoke-") as scratch:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        base = f"http://127.0.0.1:{listener.getsockname()[1]}"
        settings = Settings(
            dev=True, data_dir=Path(scratch), base_url=base
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
                spec = SlideSpec.model_validate({
                    "schema_version": "1.1", "purpose_mode": "general",
                    "presentation_id": p["id"], "spec_version": 1,
                    "presentation_metadata": {"title": "動作確認", "audience": "開発者",
                                              "purpose": "試験用データによる動作確認", "duration_minutes": 5},
                    "slides": [{
                        "slide_id": f"check{i}", "slide_order": i, "prototype_id": "results_table",
                        "title": f"試験用データ {i}",
                        "replacements": {"表の結果要点": [{"text": "試験用数値。研究結果ではない"}]},
                        "table_spec": {"columns": ["試験", "仮指標A", "仮指標B"],
                                       "rows": [["A", "10", "20"]]},
                    } for i in range(1, 6)],
                })
                saved = await client.call_tool(
                    "save_slide_spec",
                    {"presentation_id": p["id"], "spec": spec.model_dump(), "expected_version": 0},
                )
                assert not saved.is_error
                job = (
                    await client.call_tool("enqueue_generation", {"presentation_id": p["id"]})
                ).structured_content
                assert await asyncio.to_thread(process_one, app.state.store, settings)
                completed = (await client.call_tool("get_job", {"job_id": job["id"]})).structured_content
                assert completed["state"] == "completed", completed
                output = json.loads(completed["output"])
                assert "preview" not in output
                response = await browser.get(completed["download_url"])
                assert response.status_code == 200 and response.content.startswith(b"PK")
                resource = await client.read_resource("ui://research-slide-agent/viewer.html")
                assert "Research Slide Agent" in resource.contents[0].text
                print(
                    json.dumps(
                        {
                            "status": "passed",
                            "mcp": "2.3.0",
                            "generation": "without_approval_or_preview",
                            "slides": 5,
                            "download_bytes": len(response.content),
                        }
                    )
                )
        finally:
            server.should_exit = True
            await task


if __name__ == "__main__":
    asyncio.run(main())
