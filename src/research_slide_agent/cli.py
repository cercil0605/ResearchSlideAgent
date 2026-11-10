import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--template", type=Path, default=Path("templates/lab-template.pptx"))
    demo.add_argument("--output", type=Path, default=Path("artifacts/demo.pptx"))
    demo.add_argument("--slides", type=int, default=5)
    demo.add_argument("--render", action="store_true")
    sub.add_parser("schema")
    sub.add_parser("serve")
    sub.add_parser("worker")
    sub.add_parser("cleanup")
    home = Path.home() / "ResearchSlides"
    local = sub.add_parser("local", help="Run as a local MCP server over stdio (no HTTP, no OAuth)")
    local.add_argument("--input-dir", type=Path, action="append",
                       help=f"Directory the LLM may read source files from (repeatable). Default: {home}")
    local.add_argument("--output-dir", type=Path, default=None,
                       help=f"Where finished PPTX/PDF/PNG are copied. Default: {home / 'outputs'}")
    local.add_argument("--data-dir", type=Path, default=None,
                       help="Projects, jobs and SQLite queue. Default: RSA_DATA_DIR or ~/.research-slide-agent")
    args = parser.parse_args()
    if args.command == "demo":
        from .engine import generate, render
        from .sample import sample_spec

        spec = sample_spec(count=args.slides)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.with_suffix(".spec.json").write_text(spec.model_dump_json(indent=2))
        generate(args.template, spec, args.output)
        if args.render:
            preview_dir = args.output.parent / (
                "preview" if args.output.stem == "demo" else f"{args.output.stem}-preview"
            )
            print(json.dumps(render(args.output, preview_dir)))
        print(args.output.resolve())
    elif args.command == "schema":
        from .models import SlideSpec

        path = Path("schemas/slidespec.json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(SlideSpec.model_json_schema(), ensure_ascii=False, indent=2) + "\n")
    elif args.command == "serve":
        import uvicorn

        from .app import create_app
        from .config import Settings

        settings = Settings()
        settings.validate()
        uvicorn.run(
            create_app(settings),
            host="127.0.0.1" if settings.dev else "0.0.0.0",
            port=8000,
            log_level="critical",
            access_log=False,
        )
    elif args.command == "local":
        run_local(args, home)
    else:
        from .config import Settings
        from .store import Store
        from .worker import run_forever

        settings = Settings()
        settings.validate()
        store = Store(settings)
        if args.command == "cleanup":
            print(store.cleanup())
        else:
            run_forever(store, settings)


def run_local(args, home):
    import logging
    import os

    from .auth import Auth
    from .config import Settings
    from .server import make_mcp
    from .store import Store
    from .worker import start_background

    # stdout carries the MCP protocol; keep every library logger off it.
    for namespace in ("mcp", "httpx", "httpcore"):
        logging.getLogger(namespace).handlers = [logging.NullHandler()]
        logging.getLogger(namespace).propagate = False
    template = Path(os.getenv("RSA_TEMPLATE", "templates/lab-template.pptx"))
    if not template.is_absolute() and not template.exists():
        # MCP clients launch the server from an arbitrary working directory.
        template = Path(__file__).resolve().parents[2] / template
    data_dir = args.data_dir or Path(os.getenv("RSA_DATA_DIR") or Path.home() / ".research-slide-agent")
    inputs = tuple(args.input_dir or [home])
    output = args.output_dir or home / "outputs"
    for directory in (*inputs, output, data_dir):
        directory.expanduser().mkdir(parents=True, exist_ok=True)
    settings = Settings(
        local=True, dev=False, data_dir=data_dir.expanduser(), template=template,
        input_dirs=inputs, output_dir=output,
    )
    settings.validate()
    store = Store(settings)
    start_background(store, settings)
    make_mcp(store, settings, Auth(settings)).run("stdio")


if __name__ == "__main__":
    main()
