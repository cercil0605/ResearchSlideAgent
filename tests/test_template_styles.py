import importlib.util
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches

from research_slide_agent.engine import LayoutError, generate, template_info
from research_slide_agent.models import Block
from research_slide_agent.sample import sample_spec
from research_slide_agent.template_styles import restore_template_parts


@pytest.fixture
def named_template(settings):
    prs = Presentation(settings.template)
    layout = prs.slide_layouts[1]
    title = next(p for p in layout.placeholders if p.placeholder_format.idx == 0)
    title.name = "rsa:title"
    body = next(p for p in layout.placeholders if p.placeholder_format.idx == 1)
    body.name = "rsa:body"
    key = deepcopy(body._element)
    key.nvSpPr.cNvPr.set("id", "100")
    key.nvSpPr.cNvPr.set("name", "rsa:key_message")
    key.nvSpPr.nvPr.ph.set("idx", "20")
    layout._element.spTree.append(key)
    slots = [body, next(p for p in layout.placeholders if p.placeholder_format.idx == 20)]
    for p in slots:
        tx = p._element.txBody
        ls = tx.find("a:lstStyle", tx.nsmap)
        for child in list(ls):
            ls.remove(child)
        for i, size in enumerate([2200, 1800, 1600], 1):
            style = OxmlElement(f"a:lvl{i}pPr")
            style.set("marL", str((i - 1) * 200000))
            if i > 1:
                style.set("indent", "-160000")
                bullet = OxmlElement("a:buChar")
                bullet.set("char", "•")
                style.append(bullet)
            font = OxmlElement("a:defRPr")
            font.set("sz", str(size))
            for tag in ("a:latin", "a:ea"):
                face = OxmlElement(tag)
                face.set("typeface", "Yu Gothic")
                font.append(face)
            style.append(font)
            ls.append(style)
    original = (body.left, body.top, body.width, body.height)
    key_shape = slots[1]
    key_shape.left, key_shape.top, key_shape.width, key_shape.height = original
    key_shape.height = Inches(0.8)
    body.left, body.top, body.width, body.height = (
        original[0],
        original[1] + Inches(1.2),
        original[2],
        original[3] - Inches(1.2),
    )
    prs.save(settings.template)
    return settings.template


def test_named_slots_preserve_geometry_fonts_and_bullets(named_template, tmp_path):
    spec = sample_spec(count=1)
    spec.slides[0].key_message = "書式の確認"
    spec.slides[0].body_blocks = [
        Block(id="a", text="第一項目", level=1, bullet=True),
        Block(id="b", text="下位項目", level=2, bullet=True),
    ]
    result = tmp_path / "result.pptx"
    generate(named_template, spec, result)
    prs = Presentation(result)
    body = next(s for s in prs.slides[0].shapes if s.name == "rsa:slot:body")
    original = next(
        p for p in Presentation(named_template).slide_layouts[1].placeholders if p.name == "rsa:body"
    )
    assert (body.left, body.top, body.width, body.height) == (
        original.left,
        original.top,
        original.width,
        original.height,
    )
    assert [p.level for p in body.text_frame.paragraphs] == [1, 2]
    assert [p.runs[0].font.size.pt for p in body.text_frame.paragraphs] == [18, 16]
    assert body._element.xpath("./p:txBody/a:p/a:pPr/a:buChar/@char") == ["•", "•"]
    assert body._element.xpath("./p:txBody/a:p/a:r/a:rPr/a:ea/@typeface") == ["Yu Gothic", "Yu Gothic"]
    assert template_info(named_template)["layouts"][1]["template_slots"]


def test_named_slot_overflow_does_not_resize(named_template, tmp_path):
    spec = sample_spec(count=1)
    spec.slides[0].key_message = "一行の要点"
    spec.slides[0].body_blocks = [Block(id="a", text="長い文章\n" * 90)]
    with pytest.raises(LayoutError, match="TEXT_OVERFLOW"):
        generate(named_template, spec, tmp_path / "overflow.pptx")
    spec.slides[0].body_blocks = [Block(id="a", text="右列", slot="body_right")]
    with pytest.raises(LayoutError, match="no body_right slot"):
        generate(named_template, spec, tmp_path / "wrong-layout.pptx")
    spec.slides[0].layout_id = 0
    with pytest.raises(LayoutError, match="named template layout"):
        generate(named_template, spec, tmp_path / "unprepared-layout.pptx")


def test_restore_rejects_real_master_changes(settings, tmp_path):
    target = tmp_path / "changed.pptx"
    with zipfile.ZipFile(settings.template) as source, zipfile.ZipFile(target, "w") as result:
        for name in source.namelist():
            data = source.read(name)
            if name == "ppt/slideMasters/slideMaster1.xml":
                data = data.replace(b'val="FFFFFF"', b'val="EEEEEE"', 1)
            result.writestr(name, data)
    with pytest.raises(ValueError, match="Template part was modified"):
        restore_template_parts(settings.template, target)


@pytest.mark.skipif(not Path("slide_sample.pptx").exists(), reason="Private professor sample is local only")
def test_actual_professor_template_extraction(tmp_path):
    module = importlib.util.spec_from_file_location("prepare_lab_template", "scripts/prepare_lab_template.py")
    recipe = importlib.util.module_from_spec(module)
    module.loader.exec_module(recipe)
    output = tmp_path / "template.pptx"
    report = recipe.extract(Path("slide_sample.pptx"), output)
    with zipfile.ZipFile("slide_sample.pptx") as source, zipfile.ZipFile(output) as result:
        for name in source.namelist():
            if name.startswith(("ppt/slideMasters/", "ppt/theme/")):
                assert source.read(name) == result.read(name)
        assert not any(name.endswith(".mp4") for name in result.namelist())
        assert "七十二候" not in result.read("docProps/app.xml").decode()
    prs = Presentation(output)
    assert len(prs.slides) == 5
    assert all(
        "七十二候" not in shape.text for slide in prs.slides for shape in slide.shapes if shape.has_text_frame
    )
    assert len(report["layouts"]) == 5
    assert len(prs.slide_masters) == 2
    cover = prs.slide_masters[1].slide_layouts[0]
    assert any(shape.name == "Rectangle 3" for shape in cover.shapes)
