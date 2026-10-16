"""Exercise the actual extracted template using clearly labelled synthetic content."""

import json
from pathlib import Path

from research_slide_agent.engine import generate, render, template_info
from research_slide_agent.models import SlideSpec


def make_spec(template):
    layouts = {layout["name"]: layout["layout_id"] for layout in template_info(template)["layouts"]}
    common = {"key_message": "書式確認用の合成データです"}
    slides = [
        {
            "title": "研究発表テンプレート",
            "layout_id": layouts["RSA 表紙"],
            "key_message": "発表者名・所属の見本",
        },
        {
            **common,
            "title": "本文と箇条書き",
            "layout_id": layouts["RSA 本文"],
            "body_blocks": [
                {"id": "a", "text": "本文の位置と書式を確認します"},
                {"id": "b", "text": "第1階層の項目", "level": 1, "bullet": True},
                {"id": "c", "text": "第2階層の項目", "level": 2, "bullet": True},
            ],
        },
        {
            **common,
            "title": "本文と編集可能な図",
            "layout_id": layouts["RSA 本文と図"],
            "body_blocks": [{"id": "a", "text": "図と文章を並べて説明します"}],
            "diagram_spec": {
                "kind": "flowchart",
                "nodes": [{"id": "a", "text": "入力"}, {"id": "b", "text": "出力"}],
                "edges": [{"source": "a", "target": "b"}],
            },
        },
        {
            **common,
            "title": "二段組",
            "layout_id": layouts["RSA 二段組"],
            "body_blocks": [
                {"id": "a", "text": "左列の説明", "bullet": True, "level": 1},
                {"id": "b", "text": "右列の説明", "slot": "body_right", "bullet": True, "level": 1},
            ],
        },
        {
            **common,
            "title": "編集可能な表",
            "layout_id": layouts["RSA 図表"],
            "table_spec": {"columns": ["試験", "値"], "rows": [["A", "10"], ["B", "20"]]},
        },
        {
            **common,
            "title": "編集可能なグラフ",
            "layout_id": layouts["RSA 図表"],
            "chart_spec": {
                "kind": "bar",
                "categories": ["A", "B"],
                "series": [{"name": "合成値", "values": [10, 20]}],
                "x_label": "試験",
                "y_label": "合成値",
            },
        },
    ]
    for i, slide in enumerate(slides, 1):
        slide.update(slide_id=f"check{i}", slide_order=i)
    return SlideSpec.model_validate(
        {
            "presentation_id": "template-check",
            "spec_version": 1,
            "presentation_metadata": {
                "title": "書式確認",
                "audience": "開発者",
                "purpose": "合成データによる書式試験",
                "duration_minutes": 5,
            },
            "slides": slides,
        }
    )


if __name__ == "__main__":
    template = Path("templates/lab-template.pptx")
    output = Path("artifacts/template-check/presentation.pptx")
    spec = make_spec(template)
    manifest = generate(template, spec, output)
    output.with_suffix(".spec.json").write_text(spec.model_dump_json(indent=2))
    preview = render(output, output.parent / "preview")
    print(json.dumps({"quality": manifest["quality"], "preview": preview}, ensure_ascii=False))
