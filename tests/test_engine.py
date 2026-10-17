import zipfile

import pytest
from pptx import Presentation
from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN

from research_slide_agent.engine import LayoutError, generate, inspect_pptx, patch_text, render
from research_slide_agent.models import Chart, Citation, Diagram, SourceRef, Table
from research_slide_agent.sample import sample_spec


def test_five_editable_and_master_retained(settings, tmp_path):
    output = tmp_path / "slides.pptx"
    spec = sample_spec()
    manifest = generate(settings.template, spec, output)
    prs = Presentation(output)
    assert len(prs.slides) == 5
    assert any(s.has_table for slide in prs.slides for s in slide.shapes)
    assert any(s.has_chart for slide in prs.slides for s in slide.shapes)
    with zipfile.ZipFile(settings.template) as before, zipfile.ZipFile(output) as after:
        for name in before.namelist():
            if name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")):
                assert before.read(name) == after.read(name)
        assert any(n.startswith("ppt/embeddings/") and n.endswith(".xlsx") for n in after.namelist())
    flow = prs.slides[1]
    edges = [s for s in flow.shapes if s.name.startswith("rsa:edge:")]
    assert len(edges) == 2
    assert all(s._element.xpath(".//a:stCxn") and s._element.xpath(".//a:endCxn") for s in edges)
    assert manifest["structure"][4]["shapes"]


@pytest.mark.parametrize("kind", ["flowchart", "system", "comparison", "timeline"])
def test_diagram_types(settings, tmp_path, kind):
    spec = sample_spec(count=1)
    spec.slides[0].body_blocks = []
    spec.slides[0].diagram_spec = Diagram.model_validate(
        {
            "kind": kind,
            "nodes": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
            "edges": [{"source": "a", "target": "b"}],
        }
    )
    generate(settings.template, spec, tmp_path / f"{kind}.pptx")


@pytest.mark.parametrize("kind", ["bar", "line", "scatter"])
def test_chart_types(settings, tmp_path, kind):
    spec = sample_spec(count=1)
    spec.slides[0].body_blocks = []
    spec.slides[0].chart_spec = Chart.model_validate(
        {
            "kind": kind,
            "categories": ["A", "B"],
            "x_values": [1, 2] if kind == "scatter" else None,
            "series": [{"name": "Data", "values": [3, 4]}],
            "x_label": "X",
            "y_label": "Y",
        }
    )
    output = tmp_path / f"{kind}.pptx"
    generate(settings.template, spec, output)
    chart = next(s.chart for s in Presentation(output).slides[0].shapes if s.has_chart)
    root = chart._chartSpace
    definitions = root.xpath(".//c:catAx/c:axId/@val | .//c:valAx/c:axId/@val")
    all_ids = root.xpath(".//c:axId/@val | .//c:crossAx/@val")
    assert len(set(definitions)) == 2
    assert set(all_ids) == set(definitions)
    assert all(0 <= int(value) <= 2**31 - 1 for value in all_ids)


def test_40_slides(settings, tmp_path):
    output = tmp_path / "forty.pptx"
    generate(settings.template, sample_spec(count=40), output)
    assert len(Presentation(output).slides) == 40


@pytest.mark.parametrize(
    "author,year,label",
    [("小林ら", 2013, " [小林ら '13]"), ("Kobayashi", 2005, " [Kobayashi '05]"), ("著者", 2000, " [著者 '00]")],
)
def test_professor_citation_format_keeps_full_year(author, year, label):
    citation = Citation(source=SourceRef(source_id="fixture", locator="page 1"), author=author, year=year, target_id="key_message")
    assert citation.label == label
    assert citation.model_dump()["year"] == year


def test_professor_table_rules_keep_values_and_native_cells(settings, tmp_path):
    spec = sample_spec(count=1)
    spec.slides[0].body_blocks = []
    data = Table(columns=["項目", "数値"], rows=[["A", "1,234.50"], ["B", "−0.20"], ["C", "未測定"]])
    spec.slides[0].table_spec = data
    output = tmp_path / "table-rules.pptx"
    generate(settings.template, spec, output)
    table = next(s.table for s in Presentation(output).slides[0].shapes if s.has_table)
    assert [[c.text for c in row.cells] for row in table.rows] == [data.columns, *data.rows]
    widths = set()
    for row in table.rows:
        for cell in row.cells:
            assert cell.text_frame.auto_size == MSO_AUTO_SIZE.NONE
            assert cell._tc.xpath("./a:tcPr/a:noFill")
            assert cell._tc.xpath("./a:tcPr/a:lnL/a:noFill")
            assert cell._tc.xpath("./a:tcPr/a:lnR/a:noFill")
            widths.update(cell._tc.xpath("./a:tcPr/*[starts-with(local-name(), 'ln')]/@w"))
    assert len(widths) == 1 and int(next(iter(widths))) > 0
    assert table.cell(0, 0)._tc.xpath("./a:tcPr/a:lnT/a:solidFill/a:srgbClr/@val") == ["000000"]
    assert table.cell(0, 0)._tc.xpath("./a:tcPr/a:lnB/a:solidFill/a:srgbClr/@val") == ["000000"]
    assert table.cell(2, 0)._tc.xpath("./a:tcPr/a:lnT/a:solidFill/a:srgbClr/@val") == ["FFFFFF"]
    assert table.cell(1, 0).text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT
    assert table.cell(1, 1).text_frame.paragraphs[0].alignment == PP_ALIGN.RIGHT
    assert table.cell(2, 1).text_frame.paragraphs[0].alignment == PP_ALIGN.RIGHT
    assert table.cell(3, 1).text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT


def test_partial_edit_preserves_unselected_parts(settings, tmp_path):
    original = tmp_path / "manual.pptx"
    generate(settings.template, sample_spec(), original)
    target = next(s for s in inspect_pptx(original)[0]["shapes"] if s["name"] == "rsa:key_message")
    changes = [
        {
            "slide_number": 1,
            "shape_id": target["shape_id"],
            "expected_sha256": target["sha256"],
            "text": "Human-approved replacement",
        }
    ]
    edited = tmp_path / "edited.pptx"
    patch_text(original, edited, changes)
    with zipfile.ZipFile(original) as before, zipfile.ZipFile(edited) as after:
        for name in before.namelist():
            if name != "ppt/slides/slide1.xml":
                assert before.read(name) == after.read(name)
    assert "Human-approved replacement" in [
        s.text for s in Presentation(edited).slides[0].shapes if s.has_text_frame
    ]
    with pytest.raises(LayoutError, match="EDIT_CONFLICT"):
        patch_text(edited, tmp_path / "conflict.pptx", changes)


def test_overflow_refuses_content_change(settings, tmp_path):
    spec = sample_spec(count=1)
    spec.slides[0].key_message = "長い文章" * 70
    with pytest.raises(LayoutError, match="TEXT_OVERFLOW"):
        generate(settings.template, spec, tmp_path / "bad.pptx")


def test_cycles_rejected(settings, tmp_path):
    spec = sample_spec(count=2)
    spec.slides[1].diagram_spec.edges.append(
        type(spec.slides[1].diagram_spec.edges[0])(source="c", target="a")
    )
    with pytest.raises(LayoutError, match="Cyclic"):
        generate(settings.template, spec, tmp_path / "bad.pptx")


def test_render_pages(settings, tmp_path):
    import shutil

    if not shutil.which("soffice") or not shutil.which("pdftoppm"):
        pytest.skip("LibreOffice/Poppler not installed")
    output = tmp_path / "rendered.pptx"
    generate(settings.template, sample_spec(), output)
    result = render(output, tmp_path / "preview")
    assert result["page_count"] == len(result["images"]) == 5


def test_safe_layout_repair_keeps_approved_text(settings, tmp_path):
    spec = sample_spec(count=1)
    spec.slides[0].body_blocks = []
    spec.slides[0].key_message = "検証用の文章を配置します。" * 6
    output = tmp_path / "repair.pptx"
    manifest = generate(settings.template, spec, output)
    assert 1 <= manifest["quality"]["auto_repair_attempts"] <= 2
    assert spec.slides[0].key_message in [
        s.text for s in Presentation(output).slides[0].shapes if s.has_text_frame
    ]


def test_citations_stay_native_and_near_target(settings, tmp_path):
    spec = sample_spec(count=1)
    ref = SourceRef(source_id="uploaded-fixture", locator="page 2")
    slide = spec.slides[0]
    slide.source_references = [ref]
    slide.body_blocks[0].source_references = [ref]
    slide.citations = [Citation(source=ref, author="試験資料", year=2026, target_id=slide.body_blocks[0].id)]
    output = tmp_path / "citation.pptx"
    generate(settings.template, spec, output)
    shapes = list(Presentation(output).slides[0].shapes)
    citation = next(s for s in shapes if s.name.startswith("rsa:citation:"))
    block = next(s for s in shapes if s.name.startswith("rsa:block:"))
    assert citation.text == " [試験資料 '26]"
    assert abs(citation.top - (block.top + block.height)) < 100
