from .models import SlideSpec


def sample_spec(presentation_id="demo", count=5):
    """Synthetic fixture, never research evidence or fabricated bibliography."""
    slides = [
        {
            "slide_id": "overview",
            "slide_order": 1,
            "layout_id": 1,
            "title": "Editable presentation demo",
            "key_message": "Synthetic content for software verification",
            "body_blocks": [
                {
                    "id": "intro",
                    "text": "All figures use native PowerPoint objects.\nReplace the fixture with approved research content.",
                }
            ],
        },
        {
            "slide_id": "flow",
            "slide_order": 2,
            "layout_id": 1,
            "title": "Processing flow",
            "key_message": "A simple process with connected native shapes",
            "diagram_spec": {
                "kind": "flowchart",
                "nodes": [
                    {"id": "a", "text": "Input"},
                    {"id": "b", "text": "Process", "emphasis": True},
                    {"id": "c", "text": "Output"},
                ],
                "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
            },
        },
        {
            "slide_id": "system",
            "slide_order": 3,
            "layout_id": 1,
            "title": "System components",
            "key_message": "The API delegates generation to the worker",
            "diagram_spec": {
                "kind": "system",
                "nodes": [
                    {"id": "a", "text": "MCP API"},
                    {"id": "b", "text": "Job queue"},
                    {"id": "c", "text": "Worker"},
                ],
                "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
            },
        },
        {
            "slide_id": "table",
            "slide_order": 4,
            "layout_id": 1,
            "title": "Editable table",
            "key_message": "Synthetic values used only as test data",
            "table_spec": {"columns": ["Case", "Value"], "rows": [["A", "10"], ["B", "20"], ["C", "30"]]},
        },
        {
            "slide_id": "chart",
            "slide_order": 5,
            "layout_id": 1,
            "title": "Editable chart",
            "key_message": "The chart includes its original workbook",
            "chart_spec": {
                "kind": "bar",
                "categories": ["A", "B", "C"],
                "series": [{"name": "Synthetic", "values": [10, 20, 30]}],
                "x_label": "Case",
                "y_label": "Test units",
            },
        },
    ]
    expanded = []
    for i in range(count):
        item = dict(slides[i % len(slides)])
        item.update(slide_id=f"s{i + 1}", slide_order=i + 1)
        expanded.append(item)
    return SlideSpec.model_validate(
        {
            "presentation_id": presentation_id,
            "spec_version": 1,
            "presentation_metadata": {
                "title": "Research Slide Agent PoC",
                "audience": "Developers",
                "purpose": "Software verification",
                "duration_minutes": 10,
                "language": "en",
            },
            "slides": expanded,
        }
    )
