"""Generate a local SlideSpec without a plugin, server, or OAuth setup."""

import argparse
import html
import json
from pathlib import Path

from research_slide_agent.config import Settings
from research_slide_agent.engine import generate, render
from research_slide_agent.models import SlideSpec


def write_preview(directory, spec, preview):
    from PIL import Image, ImageDraw, ImageOps

    pages = preview["images"]
    sheet = Image.new("RGB", (1000, ((len(pages) + 1) // 2) * 420), "#e9edf1")
    draw = ImageDraw.Draw(sheet)
    for i, name in enumerate(pages):
        with Image.open(directory / "preview" / name) as page:
            thumbnail = ImageOps.contain(page.convert("RGB"), (476, 376))
        x, y = 12 + (i % 2) * 500, 12 + (i // 2) * 420
        sheet.paste(thumbnail, (x, y + 20))
        draw.text((x, y), str(i + 1), fill="#182c40")
    sheet.save(directory / "overview.png")
    title = html.escape(spec.presentation_metadata.title)
    entries = [
        {"image": "preview/" + name, "title": slide.title}
        for name, slide in zip(pages, sorted(spec.slides, key=lambda s: s.slide_order))
    ]
    data = json.dumps(entries, ensure_ascii=False).replace("<", "\\u003c")
    page = """<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title><style>
body{margin:0;background:#edf0f4;color:#172c40;font:16px system-ui,sans-serif}
main{max-width:1000px;margin:auto;padding:20px}h1{font-size:24px}
nav{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin:16px 0}
button,a{font:inherit}button{padding:8px 20px;cursor:pointer}
img{display:block;max-width:100%;max-height:75vh;margin:auto;background:white}
a{color:#134e8a}#caption{min-height:1.5em}
</style><main><h1>__TITLE__</h1>
<nav><button id="prev">前へ</button><span id="count"></span><button id="next">次へ</button>
<a href="presentation.pptx" download>PPTX</a><a href="preview/presentation.pdf">PDF（参考表示）</a>
<a href="overview.png">一覧画像</a></nav><p id="caption"></p><img id="slide" alt="">
<p>プレビューはLibreOfficeによる参考表示です。フォント・表・改行はPowerPointと異なる場合があります。
最終的な見た目はPowerPointで確認し、PDFもPowerPointから書き出してください。</p>
</main><script>
const pages=__DATA__;let current=0;
function show(){const p=pages[current];document.getElementById('slide').src=p.image;
document.getElementById('slide').alt=p.title;document.getElementById('caption').textContent=p.title;
document.getElementById('count').textContent=`${current+1} / ${pages.length}`;
document.getElementById('prev').disabled=current===0;
document.getElementById('next').disabled=current===pages.length-1;}
function move(step){current=Math.max(0,Math.min(pages.length-1,current+step));show();}
document.getElementById('prev').onclick=()=>move(-1);
document.getElementById('next').onclick=()=>move(1);
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')move(1);if(e.key==='ArrowLeft')move(-1);});
show();</script></html>"""
    (directory / "index.html").write_text(
        page.replace("__TITLE__", title).replace("__DATA__", data), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--template", type=Path, default=Settings().template)
    parser.add_argument("--output", type=Path, default=Path("artifacts/local-presentation"))
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    spec = SlideSpec.model_validate_json(args.spec.read_text(encoding="utf-8"))
    output = args.output / "presentation.pptx"
    manifest = generate(args.template, spec, output)
    output.with_suffix(".spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    result = {"pptx": str(output.resolve()), "quality": manifest["quality"]}
    if args.render:
        preview = render(output, args.output / "preview")
        write_preview(args.output, spec, preview)
        result.update(preview=preview, viewer=str((args.output / "index.html").resolve()))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
