import asyncio
import io
import os
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from PIL import Image

from research_slide_agent.auth import Auth
from research_slide_agent.config import Settings
from research_slide_agent.sample import sample_spec
from research_slide_agent.server import LOCAL_OWNER, make_mcp
from research_slide_agent.store import Store
from research_slide_agent.worker import process_one


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def local_settings(settings, tmp_path):
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    inputs.mkdir()
    return Settings(local=True, data_dir=settings.data_dir, template=settings.template,
                    input_dirs=(inputs,), output_dir=outputs)


def test_local_requires_directories(settings):
    with pytest.raises(ValueError):
        Settings(local=True, data_dir=settings.data_dir, template=settings.template).validate()
    assert not Settings(local=True, auth_mode="cloudflare", input_dirs=(Path("."),),
                        output_dir=Path(".")).cloudflare


@pytest.mark.asyncio
async def test_local_tools_register_generate_and_export(local_settings, tmp_path):
    local_settings.validate()
    store = Store(local_settings)
    mcp = make_mcp(store, local_settings, Auth(local_settings))
    inputs = local_settings.input_dirs[0]
    (inputs / "figure.png").write_bytes(png_bytes())
    outside = tmp_path / "secret.png"
    outside.write_bytes(png_bytes())
    (inputs / "link.png").symlink_to(outside)
    async with Client(mcp) as session:
        assert "register_local_file" in session.instructions
        names = {t.name for t in (await session.list_tools()).tools}
        assert {"register_local_file", "get_file_transfer_info", "save_slide_spec", "get_slide_preview"} <= names
        assert not {"register_chatgpt_file", "create_upload", "show_viewer"} & names
        info = (await session.call_tool("get_file_transfer_info", {})).structured_content
        assert info["method"] == "register_local_file"
        profile = await session.call_tool("get_profile", {})
        assert profile.structured_content["id"] == LOCAL_OWNER
        pid = (await session.call_tool("create_project", {})).structured_content["id"]

        registered = await session.call_tool(
            "register_local_file", {"presentation_id": pid, "path": str(inputs / "figure.png")})
        assert not registered.is_error, registered
        for path, code in [(outside, "LOCAL_PATH_NOT_ALLOWED"), (inputs / "link.png", "LOCAL_PATH_NOT_ALLOWED"),
                           (inputs / ".." / "secret.png", "LOCAL_PATH_NOT_ALLOWED"),
                           ("figure.png", "LOCAL_PATH_NOT_ABSOLUTE"), (inputs / "missing.pdf", "LOCAL_FILE_NOT_FOUND")]:
            denied = await session.call_tool("register_local_file", {"presentation_id": pid, "path": str(path)})
            assert denied.is_error and code in denied.content[0].text

        spec = sample_spec(pid)
        saved = await session.call_tool(
            "save_slide_spec", {"presentation_id": pid, "spec": spec.model_dump(), "expected_version": 0})
        assert not saved.is_error, saved
        job = (await session.call_tool("enqueue_generation", {"presentation_id": pid, "wait": False})).structured_content
        assert await asyncio.to_thread(process_one, store, local_settings)
        done = (await session.call_tool("get_job", {"job_id": job["id"]})).structured_content
        assert done["state"] == "completed"
        assert done["output"]["slide_count"] == len(spec.slides)
        saved_path = Path(done["local_path"])
        assert saved_path == local_settings.output_dir.resolve() / pid / job["id"] / "presentation.pptx"
        assert saved_path.read_bytes()[:2] == b"PK"
        assert done["download_url"] == saved_path.as_uri()
        assert "expires_in" not in done


@pytest.mark.asyncio
async def test_save_and_failed_job_return_all_fit_problems(local_settings):
    from research_slide_agent.models import SlideSpec

    store = Store(local_settings)
    mcp = make_mcp(store, local_settings, Auth(local_settings))
    async with Client(mcp) as session:
        pid = (await session.call_tool("create_project", {})).structured_content["id"]
        raw = sample_spec(pid, 2).model_dump()
        raw["slides"] = [{**raw["slides"][0], "slide_id": f"s{i}", "slide_order": i,
                          "title": "長い題名" * 40,
                          "replacements": {"背景の箇条書き": [{"text": "長い説明" * 100}]}}
                         for i in (1, 2)]
        spec = SlideSpec.model_validate(raw)
        saved = await session.call_tool("save_slide_spec", {
            "presentation_id": pid, "spec": spec.model_dump(), "expected_version": 0})
        assert not saved.is_error, saved
        pages = saved.structured_content["authoring_feedback"]["pages"]
        expected = [{"page": page["page"], "slide_id": page["slide_id"], **problem}
                    for page in pages for problem in page["fit_problems"]]
        assert len(expected) == 4
        jid = (await session.call_tool(
            "enqueue_generation", {"presentation_id": pid, "wait": False})).structured_content["id"]
        pending = (await session.call_tool("get_job", {"job_id": jid})).structured_content
        assert pending["output"] is None
        assert await asyncio.to_thread(process_one, store, local_settings)
        failed = (await session.call_tool("get_job", {"job_id": jid})).structured_content
        assert failed["state"] == "failed" and failed["error"] == "LAYOUT_REQUIRES_USER_CHANGE"
        assert failed["output"]["problems"] == expected
        assert "背景の箇条書き" in failed["output"]["guidance"]
        preview = (await session.call_tool("get_preview", {"job_id": jid})).structured_content
        assert preview["job"]["output"] == failed["output"]


@pytest.mark.asyncio
async def test_rsa_local_runs_over_stdio_with_background_worker(tmp_path):
    inputs = tmp_path / "in"
    inputs.mkdir()
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "research_slide_agent.cli", "local", "--input-dir", str(inputs),
              "--output-dir", str(tmp_path / "out"), "--data-dir", str(tmp_path / "data")],
        env={**os.environ, "RSA_TEMPLATE": str(Path("templates/lab-template.pptx").resolve())},
        cwd=str(tmp_path),
    )
    async with Client(params) as session:
        pid = (await session.call_tool("create_project", {})).structured_content["id"]
        spec = sample_spec(pid)
        saved = await session.call_tool(
            "save_slide_spec", {"presentation_id": pid, "spec": spec.model_dump(), "expected_version": 0})
        assert not saved.is_error, saved
        job = (await session.call_tool("enqueue_generation", {"presentation_id": pid, "wait": False})).structured_content
        for _ in range(300):
            done = (await session.call_tool("get_job", {"job_id": job["id"]})).structured_content
            if done["state"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.1)
        assert done["state"] == "completed", done
        assert Path(done["local_path"]).is_file()
