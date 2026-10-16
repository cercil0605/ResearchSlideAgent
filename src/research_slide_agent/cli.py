import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--template", type=Path, default=Path("examples/lab-template.pptx"))
    demo.add_argument("--output", type=Path, default=Path("artifacts/demo.pptx"))
    demo.add_argument("--slides", type=int, default=5)
    demo.add_argument("--render", action="store_true")
    sub.add_parser("schema")
    sub.add_parser("serve")
    sub.add_parser("worker")
    sub.add_parser("cleanup")
    args = parser.parse_args()
    if args.command == "demo":
        from .engine import create_test_template, generate, render
        from .sample import sample_spec

        if not args.template.exists():
            create_test_template(args.template)
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

        path = Path("schemas/slidespec-1.0.json")
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


if __name__ == "__main__":
    main()
