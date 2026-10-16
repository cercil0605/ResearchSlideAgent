"""Configure only this repository's plugin; no account settings or secrets are changed."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument("--url", required=True)
parser.add_argument(
    "--app-id", help="Registered plugin_asdk_app technical ID, only after registering in ChatGPT"
)
args = parser.parse_args()
if urlparse(args.url).scheme != "https" or not args.url.endswith("/mcp"):
    parser.error("A public HTTPS URL ending in /mcp is required")
p = Path(__file__).resolve().parents[1] / "plugins/research-slide-agent/mcp.json"
data = json.loads(p.read_text())
server = data["mcpServers"]["research-slides"]
server["url"] = args.url
server.pop("extensions", None)
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
if args.app_id:
    if not args.app_id.startswith("plugin_asdk_app"):
        parser.error("Expected a registered plugin_asdk_app technical ID")
    app_file = p.parent / ".app.json"
    app_file.write_text(json.dumps({"apps": {"research-slides": {"id": args.app_id}}}, indent=2) + "\n")
    manifest = p.parent / "plugin.json"
    data = json.loads(manifest.read_text())
    data["extensions"]["com.openai"]["apps"] = "./.app.json"
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print(p)
