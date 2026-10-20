import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pydantic import ValidationError

from research_slide_agent.engine import LayoutError, generate, template_info, verify
from research_slide_agent.models import PrototypeParagraph, SlideSpec
from research_slide_agent.prototypes import NS, prepare, query, sha

TEMPLATE = Path("templates/lab-template.pptx")


def fixture_spec():
    return SlideSpec.model_validate_json(Path("examples/research-format.slidespec.json").read_text())


def table_spec(rows=1):
    source = fixture_spec()
    item = deepcopy(next(s for s in source.slides if s.table_spec))
    item.table_spec.rows = [["A", "10.0", "20.0"]] * rows
    item.slide_order = 1
    return SlideSpec.model_validate({**source.model_dump(), "purpose_mode": "general", "slides": [item.model_dump()]})


def rewrite(source, output, transform):
    with ZipFile(source) as src, ZipFile(output, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "ppt/slides/slide1.xml":
                root = etree.fromstring(data)
                transform(root)
                data = etree.tostring(root)
            dst.writestr(name, data)


@pytest.mark.parametrize("rows", [1, 2, 3])
def test_native_table_matches_original_not_generic_rules(tmp_path, rows):
    original_bytes = TEMPLATE.read_bytes()
    spec = table_spec(rows)
    path = tmp_path / "table.pptx"
    manifest = generate(TEMPLATE, spec, path)
    reference = next(s for s in Presentation(TEMPLATE).slides[8].shapes if s.has_table)
    generated = next(s for s in Presentation(path).slides[0].shapes if s.has_table)
    table = generated.table
    assert [c.width for c in table.columns] == [c.width for c in reference.table.columns]
    assert table.rows[0].height == reference.table.rows[0].height
    assert all(row.height == reference.table.rows[1].height for row in list(table.rows)[1:])
    assert generated.height == sum(row.height for row in table.rows)
    if rows < 3:
        assert generated.height < reference.height
    assert [[c.text for c in row.cells] for row in table.rows] == [spec.slides[0].table_spec.columns, *spec.slides[0].table_spec.rows]
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row.cells):
            assert cell.text_frame.paragraphs[0].alignment == PP_ALIGN.CENTER
            assert cell.text_frame.paragraphs[0].runs[0].font.size.pt == (15 if r == 0 else 16)
            assert cell.text_frame.paragraphs[0].runs[0].font.bold
            original_row = 0 if r == 0 else 3 if r == rows else r
            original = reference.table.cell(original_row, c)
            assert etree.tostring(cell._tc.tcPr, method="c14n") == etree.tostring(original._tc.tcPr, method="c14n")
            assert (cell.margin_left, cell.margin_right, cell.margin_top, cell.margin_bottom) == (
                original.margin_left, original.margin_right, original.margin_top, original.margin_bottom)
    assert table.cell(rows, 0)._tc.xpath("./a:tcPr/a:lnB/a:solidFill/a:schemeClr/@val") == ["tx1"]
    assert TEMPLATE.read_bytes() == original_bytes
    assert verify(TEMPLATE, path, spec, manifest)["status"] == "passed"


@pytest.mark.parametrize("mutation", ["blue_fill", "bottom_border", "font_size", "alignment", "row_height", "column_width", "body_margin", "fixed_geometry", "missing_table"])
def test_verification_rejects_broken_format(tmp_path, mutation):
    spec = table_spec()
    original, broken = tmp_path / "original.pptx", tmp_path / "broken.pptx"
    manifest = generate(TEMPLATE, spec, original)

    def corrupt(root):
        cell = query(root, ".//a:tr/a:tc")[0]
        if mutation == "blue_fill":
            fill = query(cell, "./a:tcPr/a:noFill")[0]
            fill.tag = f"{{{NS['a']}}}solidFill"
            etree.SubElement(fill, f"{{{NS['a']}}}srgbClr", val="0000FF")
        elif mutation == "bottom_border":
            border = query(root, ".//a:tr[last()]/a:tc[1]/a:tcPr/a:lnB")[0]
            border.getparent().remove(border)
        elif mutation == "font_size":
            query(cell, ".//a:rPr")[0].set("sz", "900")
        elif mutation == "alignment":
            query(cell, ".//a:pPr")[0].set("algn", "l")
        elif mutation == "row_height":
            query(root, ".//a:tr")[0].set("h", "1000000")
        elif mutation == "column_width":
            query(root, ".//a:gridCol")[0].set("w", "1000000")
        elif mutation == "body_margin":
            query(cell, "./a:tcPr")[0].set("marL", "0")
        elif mutation == "fixed_geometry":
            query(root, ".//p:graphicFrame/p:xfrm/a:off")[0].set("x", "0")
        else:
            table = query(root, ".//a:tbl")[0]
            table.getparent().remove(table)

    rewrite(original, broken, corrupt)
    with pytest.raises(LayoutError, match="FORMAT_OR_CONTENT_MISMATCH"):
        verify(TEMPLATE, broken, spec, manifest)


def test_hierarchy_soft_break_emphasis_and_fixed_heading(tmp_path):
    spec = fixture_spec()
    path = tmp_path / "research.pptx"
    generate(TEMPLATE, spec, path)
    prs = Presentation(path)
    background = next(s for s in prs.slides[2].shapes if s.name == "背景の箇条書き")
    assert [p.level for p in background.text_frame.paragraphs] == [0, 1]
    assert len(background._element.xpath(".//a:br")) == 1
    assert background._element.xpath(".//a:pPr/@marL") == ["177800", "406400"]
    assert background._element.xpath(".//a:pPr/@indent") == ["-101600", "-101600"]
    source = next(s for s in Presentation(TEMPLATE).slides[2].shapes if s.name == background.name)
    for expected, actual in zip(source.text_frame.paragraphs, background.text_frame.paragraphs):
        assert etree.tostring(expected._p.pPr) == etree.tostring(actual._p.pPr)
    objective = next(s for s in prs.slides[5].shapes if s.name == "手段")
    original = next(s for s in Presentation(TEMPLATE).slides[4].shapes if s.name == "手段")
    assert objective.text_frame.paragraphs[1].runs[0]._r.rPr.xml == original.text_frame.paragraphs[1].runs[0]._r.rPr.xml
    assert not any(s.name.startswith("rsa:key_message") for sl in prs.slides for s in sl.shapes)
    assert len(prs.slides) == 13
    assert prs.slides[-1].shapes[1].text == "13"


def test_partial_run_styles_remain_selected_from_original(tmp_path):
    spec = table_spec()
    spec.slides[0].prototype_id = "cover"
    spec.slides[0].table_spec = None
    spec.slides[0].replacements = {"著者": [PrototypeParagraph.model_validate({"runs": [
        {"text": "所属", "style_run": 1}, {"text": " 著者", "style_run": 3}]})]}
    path = tmp_path / "rich.pptx"
    generate(TEMPLATE, spec, path)
    source = next(s for s in Presentation(TEMPLATE).slides[0].shapes if s.name == "著者")
    target = next(s for s in Presentation(path).slides[0].shapes if s.name == "著者")
    for actual, index in zip(target.text_frame.paragraphs[0].runs, (1, 3)):
        assert actual._r.rPr.xml == source.text_frame.paragraphs[0].runs[index]._r.rPr.xml


def test_40_prototype_pages_are_copies_with_live_page_numbers(tmp_path):
    raw = table_spec().model_dump()
    item = raw["slides"][0]
    raw["slides"] = [{**deepcopy(item), "slide_id": f"table{i}", "slide_order": i} for i in range(1, 41)]
    spec = SlideSpec.model_validate(raw)
    output = tmp_path / "forty.pptx"
    generate(TEMPLATE, spec, output)
    prs = Presentation(output)
    assert len(prs.slides) == 40
    assert all(next(s.text for s in slide.shapes if "スライド番号" in s.name) == str(i)
               for i, slide in enumerate(prs.slides, 1))


def test_empty_table_cell_remains_editable(tmp_path):
    spec = table_spec()
    spec.slides[0].table_spec.rows[0][1] = ""
    path = tmp_path / "empty.pptx"
    generate(TEMPLATE, spec, path)
    table = next(s.table for s in Presentation(path).slides[0].shapes if s.has_table)
    assert table.cell(1, 1).text == ""


def test_canonical_template_refuses_old_common_slot_input(tmp_path):
    from research_slide_agent.sample import sample_spec

    with pytest.raises(LayoutError, match="requires SlideSpec 1.1"):
        generate(TEMPLATE, sample_spec(count=1), tmp_path / "old.pptx")


def test_overflow_fails_without_publishing_or_resizing(tmp_path):
    spec = table_spec()
    spec.slides[0].table_spec.columns[0] = "長い見出し" * 20
    output = tmp_path / "overflow.pptx"
    with pytest.raises(LayoutError, match="TEXT_OVERFLOW"):
        generate(TEMPLATE, spec, output)
    assert not output.exists()
    spec = table_spec(4)
    with pytest.raises(LayoutError, match="TABLE_OVERFLOW"):
        generate(TEMPLATE, spec, output)
    spec = table_spec()
    spec.slides[0].title = "長いタイトル" * 20
    with pytest.raises(LayoutError, match="TEXT_OVERFLOW"):
        generate(TEMPLATE, spec, output)
    with pytest.raises(LayoutError, match="overwritten"):
        generate(TEMPLATE, table_spec(), TEMPLATE)


def test_inventory_hash_schema_and_embedded_provenance(tmp_path):
    spec = table_spec()
    profile = template_info(TEMPLATE)
    assert len(profile["prototypes"]) == 11
    assert profile["schema_version"] == "1.3"
    assert profile["supported_schema_versions"] == ["1.1", "1.2", "1.3"]
    output = tmp_path / "generated.pptx"
    manifest = generate(TEMPLATE, spec, output)
    assert manifest["code_commit"] and manifest["generator_source_sha256"]
    assert manifest["template_sha256"] == sha(TEMPLATE.read_bytes())
    assert manifest["spec_version"] == spec.spec_version
    assert manifest["visual_review"] == "not_performed"
    with ZipFile(output) as archive:
        raw = query(etree.fromstring(archive.read("docProps/custom.xml")), "//*[local-name()='lpwstr']/text()")[0]
        assert json.loads(raw) == manifest["provenance"]
    copied = tmp_path / "template.pptx"
    copied.with_suffix(".preview.pdf").write_bytes(b"outdated preview of the previous template")
    copied.with_suffix(".preview.json").write_text('{"template_sha256":"previous"}')
    prepare(TEMPLATE, copied)
    assert copied.read_bytes() == TEMPLATE.read_bytes()
    assert not copied.with_suffix(".preview.pdf").exists()
    assert not copied.with_suffix(".preview.json").exists()
    # A fresh checkout must be usable without the original attachment at repository root.
    command = subprocess.run([sys.executable, "scripts/prepare_skeleton_template.py", "--output", str(copied)],
                             check=True, capture_output=True, text=True)
    assert json.loads(command.stdout)["template_sha256"] == sha(TEMPLATE.read_bytes())
    copied.write_bytes(copied.read_bytes() + b"broken")
    with pytest.raises(ValueError, match="TEMPLATE_HASH_MISMATCH"):
        template_info(copied)


def test_research_flow_is_variable_length_but_not_arbitrary():
    spec = fixture_spec().model_dump()
    spec["slides"][0]["prototype_id"] = "summary"
    with pytest.raises(ValidationError, match="skeleton flow"):
        SlideSpec.model_validate(spec)
    spec = fixture_spec().model_dump()
    spec["slides"] = spec["slides"][:-1]
    with pytest.raises(ValidationError, match="needs all sections"):
        SlideSpec.model_validate(spec)


def test_original_image_within_frame(tmp_path):
    spec = table_spec()
    item = spec.slides[0]
    item.prototype_id = "results_figure"
    item.table_spec = None
    item.replacements = {"図題": [PrototypeParagraph(text="試験用画像")],
                         "結果の要点": [PrototypeParagraph(text="試験用。研究結果ではない")]}
    from research_slide_agent.models import Citation, ImageRef, SourceRef

    ref = SourceRef(source_id="picture", locator="試験画像")
    item.image_references = [ImageRef(id="im", source_id="picture", caption="試験用画像")]
    item.source_references = [ref]
    item.citations = [Citation(source=ref, target_id="im", author="試験資料", year=2026)]
    item.replacements["図題"] = [PrototypeParagraph(text="試験用画像 [試験資料 '26]")]
    image = tmp_path / "image.png"
    Image.new("RGB", (100, 100), "gray").save(image)
    output = tmp_path / "image.pptx"
    generate(TEMPLATE, spec, output, {"picture": image})
    target = next(s for s in Presentation(output).slides[0].shapes if s.name == "rsa:image")
    source = next(s for s in Presentation(TEMPLATE).slides[7].shapes if s.name == "図の差し替え枠")
    assert target.left >= source.left and target.top >= source.top
    assert target.left + target.width <= source.left + source.width
    assert target.top + target.height <= source.top + source.height
