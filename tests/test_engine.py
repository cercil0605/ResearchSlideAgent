import zipfile
from pathlib import Path

import pytest
from pptx import Presentation

from research_slide_agent.engine import LayoutError, generate, inspect_pptx, patch_text, render
from research_slide_agent.models import Citation, Diagram, PrototypeParagraph, SlideSpec, SourceRef
from research_slide_agent.sample import sample_spec


def test_five_editable_and_master_retained(settings, tmp_path):
    output = tmp_path / "slides.pptx"
    spec = sample_spec()
    manifest = generate(settings.template, spec, output)
    prs = Presentation(output)
    assert len(prs.slides) == 5
    assert any(s.has_table for slide in prs.slides for s in slide.shapes)
    with zipfile.ZipFile(settings.template) as before, zipfile.ZipFile(output) as after:
        for name in before.namelist():
            if name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")):
                assert before.read(name) == after.read(name)
    flow = prs.slides[1]
    edges = [s for s in flow.shapes if s.name.startswith("rsa:edge:")]
    assert len(edges) == 2
    assert all(s._element.xpath(".//a:stCxn") and s._element.xpath(".//a:endCxn") for s in edges)
    assert manifest["quality"]["status"] == "passed"


@pytest.mark.parametrize("kind", ["flowchart", "system", "comparison", "timeline"])
def test_diagram_types(settings, tmp_path, kind):
    spec = sample_spec(count=2)
    spec.slides[1].diagram_spec = Diagram.model_validate({
        "kind": kind, "nodes": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
        "edges": [{"source": "a", "target": "b"}],
    })
    generate(settings.template, spec, tmp_path / f"{kind}.pptx")


def test_40_slides(settings, tmp_path):
    output = tmp_path / "forty.pptx"
    generate(settings.template, sample_spec(count=40), output)
    assert len(Presentation(output).slides) == 40


@pytest.mark.parametrize("author,year,label", [
    ("小林ら", 2013, " [小林ら '13]"), ("Kobayashi", 2005, " [Kobayashi '05]"), ("著者", 2000, " [著者 '00]"),
])
def test_professor_citation_format_keeps_full_year(author, year, label):
    citation = Citation(source=SourceRef(source_id="fixture", locator="page 1"), author=author,
                        year=year, target_id="背景の箇条書き")
    assert citation.label == label
    assert citation.model_dump()["year"] == year


def test_partial_edit_preserves_unselected_parts(settings, tmp_path):
    original = tmp_path / "manual.pptx"
    generate(settings.template, sample_spec(), original)
    target = next(s for s in inspect_pptx(original)[0]["shapes"] if s["name"] == "背景の箇条書き")
    changes = [{"slide_number": 1, "shape_id": target["shape_id"],
                "expected_sha256": target["sha256"], "text": "Human-approved replacement"}]
    edited = tmp_path / "edited.pptx"
    patch_text(original, edited, changes)
    with zipfile.ZipFile(original) as before, zipfile.ZipFile(edited) as after:
        for name in before.namelist():
            if name != "ppt/slides/slide1.xml":
                assert before.read(name) == after.read(name)
    assert "Human-approved replacement" in [s.text for s in Presentation(edited).slides[0].shapes if s.has_text_frame]
    with pytest.raises(LayoutError, match="EDIT_CONFLICT"):
        patch_text(edited, tmp_path / "conflict.pptx", changes)


def test_overflow_refuses_content_change(settings, tmp_path):
    spec = sample_spec(count=1)
    spec.slides[0].replacements["背景の箇条書き"] = [PrototypeParagraph(text="長い文章" * 70)]
    with pytest.raises(LayoutError, match="TEXT_OVERFLOW"):
        generate(settings.template, spec, tmp_path / "bad.pptx")


def test_cycles_rejected(settings, tmp_path):
    spec = sample_spec(count=2)
    spec.slides[1].diagram_spec.edges.append(type(spec.slides[1].diagram_spec.edges[0])(source="c", target="a"))
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


def test_citations_stay_in_the_selected_native_body(settings, tmp_path):
    spec = sample_spec(count=1)
    ref = SourceRef(source_id="uploaded-fixture", locator="page 2")
    slide = spec.slides[0]
    slide.source_references = [ref]
    citation = Citation(source=ref, author="試験資料", year=2026, target_id="背景の箇条書き")
    slide.citations = [citation]
    slide.replacements["背景の箇条書き"] = [PrototypeParagraph(text="資料に基づく説明" + citation.label)]
    output = tmp_path / "citation.pptx"
    generate(settings.template, spec, output)
    target = next(s for s in Presentation(output).slides[0].shapes if s.name == "背景の箇条書き")
    assert target.text == "資料に基づく説明" + citation.label


def test_bundled_template_supports_citations_and_egg_demo(tmp_path):
    spec = SlideSpec.model_validate_json(Path("examples/eggs.slidespec.json").read_text())
    output = tmp_path / "eggs.pptx"
    manifest = generate(Path("templates/lab-template.pptx"), spec, output)
    assert manifest["quality"]["status"] == "passed"
    prs = Presentation(output)
    assert len(prs.slides) == 5
    for index in (2, 3):
        name = "表の結果要点" if index == 2 else "図題"
        citation = next(s for s in prs.slides[index].shapes if s.name == name)
        assert spec.slides[index].citations[0].label in citation.text
        assert citation.text_frame.paragraphs[0].runs[0].font.size.pt == (16 if index == 2 else 12)
    assert any(s.has_table for s in prs.slides[2].shapes)
    assert any(s.has_table for s in prs.slides[4].shapes)
