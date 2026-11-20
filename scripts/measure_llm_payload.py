"""Measure what the LLM receives from the MCP server, per tool, through the real tool layer.

Usage: python scripts/measure_llm_payload.py [--json]

Runs the server in-process against the bundled template and a synthetic spec. No network,
no external model. Token counts are rough estimates (see estimate_tokens), not tokenizer output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_slide_agent.config import Settings  # noqa: E402
from research_slide_agent.sample import sample_spec  # noqa: E402
from research_slide_agent.server import make_mcp  # noqa: E402
from research_slide_agent.store import Store  # noqa: E402


def estimate_tokens(text: str) -> int:
    """Rough: CJK about one token per character, other text about four characters per token."""
    wide = sum(1 for c in text if ord(c) > 0x2E80)
    return round(wide + (len(text) - wide) / 4)


def text_of(result) -> str:
    return "".join(getattr(item, "text", "") for item in result.content)


async def measure() -> list[dict]:
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        template = directory / "template.pptx"
        shutil.copyfile(ROOT / "templates/lab-template.pptx", template)
        shutil.copyfile(ROOT / "templates/lab-template.profile.json", template.with_suffix(".profile.json"))
        remote = Settings(data_dir=directory / "remote", template=template, dev=True)
        tools = await make_mcp(Store(remote), remote, None).list_tools()
        definitions = json.dumps([t.model_dump(exclude_none=True) for t in tools], ensure_ascii=False)
        rows.append({"step": f"tool definitions, remote ({len(tools)} tools, every turn)",
                     "chars": len(definitions), "tokens": estimate_tokens(definitions)})

        # Local mode needs no request context, so tools can be called in-process.
        settings = Settings(data_dir=directory / "local", template=template, local=True,
                            input_dirs=[str(directory)], output_dir=directory / "out")
        store = Store(settings)
        mcp = make_mcp(store, settings, None)

        for name in ("get_authoring_context", "get_template_info"):
            text = text_of(await mcp.call_tool(name, {}))
            rows.append({"step": name, "chars": len(text), "tokens": estimate_tokens(text)})

        project = json.loads(text_of(await mcp.call_tool("create_project", {})))
        spec = sample_spec(project["id"], 8)
        text = text_of(await mcp.call_tool("save_slide_spec", {
            "presentation_id": project["id"], "spec": spec.model_dump(mode="json"), "expected_version": 0}))
        rows.append({"step": "save_slide_spec response (8 slides)", "chars": len(text),
                     "tokens": estimate_tokens(text)})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print rows as JSON")
    args = parser.parse_args()
    rows = asyncio.run(measure())
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    width = max(len(r["step"]) for r in rows)
    print(f"{'step':<{width}}  {'chars':>8}  {'~tokens':>8}")
    for r in rows:
        print(f"{r['step']:<{width}}  {r['chars']:>8,}  {r['tokens']:>8,}")
    print(f"{'total':<{width}}  {sum(r['chars'] for r in rows):>8,}  {sum(r['tokens'] for r in rows):>8,}")


if __name__ == "__main__":
    main()
