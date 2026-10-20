from copy import deepcopy

from .models import SlideSpec


def sample_spec(presentation_id="demo", count=5):
    """Canonical synthetic fixture, never research evidence or fabricated bibliography."""
    slides = [
        {"prototype_id": "background", "section": "background", "title": "Synthetic presentation demo",
         "replacements": {"背景の箇条書き": [{"text": "Synthetic content for software verification"}],
                          "動向の箇条書き": [{"text": "Replace with source-grounded research content"}]}},
        {"prototype_id": "method", "section": "method", "title": "Processing flow",
         "replacements": {"小見出し：［提案手法の名称］": [{"text": "Synthetic process"}],
                          "手法の特徴": [{"text": "Native shapes"}],
                          "手法の説明": [{"text": "Editable"}], "図題": [{"text": "Test flow"}]},
         "diagram_spec": {"kind": "flowchart", "nodes": [
             {"id": "a", "text": "Input"}, {"id": "b", "text": "Process"}, {"id": "c", "text": "Output"}],
             "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]}},
        {"prototype_id": "results_figure", "section": "results", "title": "System components",
         "replacements": {"図題": [{"text": "Synthetic system"}], "結果の要点": [{"text": "Software test only"}]},
         "diagram_spec": {"kind": "system", "nodes": [
             {"id": "a", "text": "MCP API"}, {"id": "b", "text": "Queue"}, {"id": "c", "text": "Worker"}],
             "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]}},
        {"prototype_id": "results_table", "section": "results", "title": "Editable table",
         "replacements": {"表の結果要点": [{"text": "Synthetic values; not research results"}]},
         "table_spec": {"columns": ["Case", "Value"], "rows": [["A", "10"], ["B", "20"], ["C", "30"]]}},
        {"prototype_id": "summary", "section": "summary", "title": "Summary",
         "replacements": {"まとめ：目的": [{"text": "Verify software behavior"}],
                          "まとめ：方法": [{"text": "Canonical template generation"}],
                          "まとめ：結果": [{"text": "Native diagrams and table"}],
                          "まとめ：今後の課題": [{"text": "Human content and visual review"}]}},
    ]
    expanded = []
    for i in range(count):
        item = deepcopy(slides[i % len(slides)])
        item.update(slide_id=f"s{i + 1}", slide_order=i + 1)
        expanded.append(item)
    return SlideSpec.model_validate({
        "schema_version": "1.3", "purpose_mode": "general", "presentation_id": presentation_id, "spec_version": 1,
        "presentation_metadata": {"title": "Research Slide Agent demo", "audience": "Developers",
                                  "purpose": "Software verification", "duration_minutes": 10, "language": "en"},
        "slides": expanded,
    })
