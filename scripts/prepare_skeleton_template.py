"""Register the revised skeleton unchanged; inventory slide-level replacement styles."""

import argparse
import json
import tempfile
from pathlib import Path

from research_slide_agent.engine import render
from research_slide_agent.prototypes import prepare, profile_for, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        help="Import a replacement skeleton; omit to use the bundled canonical template")
    parser.add_argument("--output", type=Path, default=Path("templates/lab-template.pptx"))
    parser.add_argument("--render-preview", action="store_true",
                        help="Render the registered template and write its matching .preview.pdf and provenance")
    args = parser.parse_args()
    if args.source:
        report = prepare(args.source, args.output)
    else:
        report = profile_for(args.output)
        if report is None:
            parser.error("No registered canonical template; specify --source to import one")
    if args.render_preview:
        with tempfile.TemporaryDirectory(dir=args.output.parent) as directory:
            preview = render(args.output, Path(directory))
            pdf = Path(directory) / preview["pdf"]
            args.output.with_suffix(".preview.pdf").write_bytes(pdf.read_bytes())
            args.output.with_suffix(".preview.json").write_text(json.dumps({
                "template_sha256": report["template_sha256"],
                "preview_sha256": sha(pdf.read_bytes()),
                "page_count": preview["page_count"],
                "renderer": preview["renderer"],
                "powerpoint_verified": False,
            }, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "prototypes"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
