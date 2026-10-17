"""Deterministic, LLM-free PowerPoint engine using the original OPC template package."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_CONNECTOR, PP_PLACEHOLDER
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

from .models import SlideSpec
from .template_styles import (
    layouts_of,
    paragraph_style,
    restore_template_parts,
    slot_font,
    slot_font_size,
    slots_of,
    write_slot,
)

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


class LayoutError(ValueError):
    pass


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int


@dataclass
class Theme:
    font: str
    title_size: float
    body_size: float
    colors: dict[str, str]
    background: str
    foreground: str


def theme_of(prs, layout_id=1):
    layout = layouts_of(prs)[layout_id]
    master = layout.slide_master
    theme_parts = [r.target_part for r in master.part.rels.values() if r.reltype.endswith("/theme")]
    root = etree.fromstring(theme_parts[0].blob)
    fonts = root.xpath("//a:minorFont/a:latin/@typeface", namespaces=NS)
    colors = {}
    for el in root.xpath("//a:clrScheme/*", namespaces=NS):
        child = el[0]
        colors[etree.QName(el).localname] = (
            child.get("val") if child.tag.endswith("srgbClr") else child.get("lastClr", "000000")
        )

    def size(style, fallback):
        values = master._element.xpath(f"./p:txStyles/p:{style}/a:lvl1pPr/a:defRPr/@sz")
        return float(values[0]) / 100 if values else fallback

    bg = master._element.xpath("./p:cSld/p:bg/p:bgPr/a:solidFill/a:srgbClr/@val")
    bg_scheme = master._element.xpath("./p:cSld/p:bg/p:bgPr/a:solidFill/a:schemeClr/@val")
    background = (
        bg[0]
        if bg
        else colors.get(bg_scheme[0], colors.get("lt1", "FFFFFF"))
        if bg_scheme
        else colors.get("lt1", "FFFFFF")
    )
    foreground = colors.get("dk1", "000000")
    if contrast(foreground, background) < 4.5:
        foreground = max(
            [colors.get("dk1", "000000"), colors.get("lt1", "FFFFFF")], key=lambda c: contrast(c, background)
        )
    slots = slots_of(layout)
    body_slot = slots.get("body") or slots.get("visual") or slots.get("key_message")
    return Theme(
        (slot_font(body_slot) if body_slot is not None else None) or (fonts[0] if fonts else "Aptos"),
        slot_font_size(slots["title"])
        if "title" in slots and slots["title"]._element.xpath("./p:txBody/a:lstStyle/a:lvl1pPr/a:defRPr/@sz")
        else size("titleStyle", 32),
        slot_font_size(body_slot) if body_slot is not None else size("bodyStyle", 24),
        colors,
        background,
        foreground,
    )


def contrast(a, b):
    def lum(c):
        v = [int(c[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        v = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
        return sum(x * y for x, y in zip(v, (0.2126, 0.7152, 0.0722)))

    l1, l2 = sorted([lum(a), lum(b)])
    return (l2 + 0.05) / (l1 + 0.05)


def template_info(path: Path):
    prs = Presentation(path)
    layouts = []
    for i, layout in enumerate(layouts_of(prs)):
        placeholders = [
            {
                "index": p.placeholder_format.idx,
                "kind": str(p.placeholder_format.type),
                "box": [p.left, p.top, p.width, p.height],
            }
            for p in layout.placeholders
        ]
        slots = slots_of(layout)
        layouts.append(
            {
                "layout_id": i,
                "name": layout.name,
                "placeholders": placeholders,
                "master_part": str(layout.slide_master.part.partname),
                "slots": list(slots),
                "template_slots": bool(slots),
                "theme": theme_of(prs, i).__dict__,
            }
        )
    preferred = [entry["layout_id"] for entry in layouts if entry["template_slots"]]
    default = next((entry["layout_id"] for entry in layouts if "body" in entry["slots"]), 0)
    t = theme_of(prs, default)
    return {
        "template_id": "lab",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "width": prs.slide_width,
        "height": prs.slide_height,
        "masters": len(prs.slide_masters),
        "layouts": layouts,
        "preferred_layout_ids": preferred,
        "default_layout_id": default,
        "theme": t.__dict__,
    }


def create_test_template(path: Path):
    """Synthetic laboratory fixture. Real deployments replace this file, never recreate their master."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    master = prs.slide_masters[0]
    bg = OxmlElement("p:bg")
    bgpr = OxmlElement("p:bgPr")
    fill = OxmlElement("a:solidFill")
    color = OxmlElement("a:srgbClr")
    color.set("val", "FFFFFF")
    fill.append(color)
    bgpr.append(fill)
    bg.append(bgpr)
    master._element.cSld.insert(0, bg)
    for style, points in [("titleStyle", 32), ("bodyStyle", 22), ("otherStyle", 18)]:
        for el in master._element.xpath(f"./p:txStyles/p:{style}/a:lvl1pPr/a:defRPr"):
            el.set("sz", str(points * 100))
    footer = OxmlElement("p:sp")
    footer.append(
        etree.fromstring(
            f'''<p:nvSpPr xmlns:p="{NS["p"]}"><p:cNvPr id="900" name="LAB_MASTER_SENTINEL"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'''
        )
    )
    footer.append(
        etree.fromstring(
            f'''<p:spPr xmlns:p="{NS["p"]}" xmlns:a="{NS["a"]}"><a:xfrm><a:off x="457200" y="6537960"/><a:ext cx="11277600" cy="250000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'''
        )
    )
    footer.append(
        etree.fromstring(
            f'''<p:txBody xmlns:p="{NS["p"]}" xmlns:a="{NS["a"]}"><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="1000"/><a:t>Research Lab / Synthetic test template</a:t></a:r></a:p></p:txBody>'''
        )
    )
    master._element.spTree.append(footer)
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Template fixture — replace with your laboratory master"
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(path)


def body_box(prs, layout):
    body = next(
        (
            p
            for p in layout.placeholders
            if p.placeholder_format.type in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT)
        ),
        None,
    )
    if body is None:
        raise LayoutError("Layout needs an explicit body/content placeholder; choose another layout")
    b = Box(body.left, body.top, body.width, body.height)
    footer_top = min(
        [
            p.top
            for p in layout.placeholders
            if p.placeholder_format.type
            in (PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.DATE, PP_PLACEHOLDER.SLIDE_NUMBER)
        ]
        + [prs.slide_height]
    )
    return Box(b.x, b.y, b.w, min(b.h, footer_top - b.y - Inches(0.1)))


def units(text):
    return sum(1 if unicodedata.east_asian_width(c) in "WF" else 0.56 for c in text)


def check_fit(text, box, size):
    width = box.w / 12700 - 12
    height = box.h / 12700 - 8
    lines = sum(max(1, math.ceil(units(line) * size / max(width, 1))) for line in text.split("\n"))
    if lines * size * 1.25 > height:
        raise LayoutError("TEXT_OVERFLOW: shorten content or split the slide; font size was not reduced")


def text_box(slide, name, text, box, theme, size=None, fill=None, center=False):
    size = size or theme.body_size
    check_fit(text, box, size)
    shape = slide.shapes.add_textbox(box.x, box.y, box.w, box.h)
    shape.name = name
    tf = shape.text_frame
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(6)
    tf.margin_top = tf.margin_bottom = Pt(4)
    tf.text = text
    if fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(fill)
    fg = theme.foreground
    if fill and contrast(fg, fill) < 4.5:
        fg = max([theme.colors["dk1"], theme.colors["lt1"]], key=lambda c: contrast(c, fill))
    for p in tf.paragraphs:
        p.font.name = theme.font
        p.font.size = Pt(size)
        p.font.color.rgb = RGBColor.from_string(fg)
        if center:
            p.alignment = PP_ALIGN.CENTER
    if center:
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    return shape


def graph_positions(diagram, box, repair=0):
    nodes = diagram.nodes
    if diagram.kind in {"comparison", "timeline"}:
        levels = [[n.id] for n in nodes]
    else:
        incoming = {n.id: set() for n in nodes}
        for edge in diagram.edges:
            incoming[edge.target].add(edge.source)
        levels, remaining, visited = [], set(incoming), set()
        while remaining:
            level = [n.id for n in nodes if n.id in remaining and incoming[n.id] <= visited]
            if not level:
                if diagram.kind == "flowchart":
                    raise LayoutError(
                        "Cyclic flowchart unsupported; use a system diagram or separate loop description"
                    )
                levels = [[n.id] for n in nodes]
                break
            levels.append(level)
            remaining -= set(level)
            visited |= set(level)
    if len(levels) > 6 or max(map(len, levels)) > 4:
        raise LayoutError("Diagram too dense; split it")
    gap = Inches(0.32)
    result = {}
    for i, level in enumerate(levels):
        for j, node_id in enumerate(level):
            if diagram.direction == "horizontal":
                w = (box.w - gap * (len(levels) - 1)) // len(levels)
                h = min(Inches(1.1 + repair * 0.45), (box.h - gap * (len(level) - 1)) // len(level))
                x = box.x + i * (w + gap)
                y = box.y + (box.h - (h * len(level) + gap * (len(level) - 1))) // 2 + j * (h + gap)
            else:
                h = (box.h - gap * (len(levels) - 1)) // len(levels)
                w = min(Inches(3), (box.w - gap * (len(level) - 1)) // len(level))
                x = box.x + (box.w - (w * len(level) + gap * (len(level) - 1))) // 2 + j * (w + gap)
                y = box.y + i * (h + gap)
            result[node_id] = Box(int(x), int(y), int(w), int(h))
    return result


def diagram_shapes(slide, diagram, box, theme, repair=0):
    positions = graph_positions(diagram, box, repair)
    shapes = {}
    for node in diagram.nodes:
        b = positions[node.id]
        kind = {
            "decision": MSO_AUTO_SHAPE_TYPE.DIAMOND,
            "terminator": MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
            "process": MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        }[node.kind]
        # Decisions have smaller text area than their bounding rectangle.
        inner = Box(b.x, b.y, int(b.w * 0.65), int(b.h * 0.65)) if node.kind == "decision" else b
        check_fit(node.text, inner, theme.body_size)
        shape = slide.shapes.add_shape(kind, b.x, b.y, b.w, b.h)
        shape.name = f"rsa:node:{node.id}"
        shape.fill.solid()
        fill = theme.colors["accent1"] if node.emphasis else theme.colors.get("lt2", theme.background)
        shape.fill.fore_color.rgb = RGBColor.from_string(fill)
        shape.line.color.rgb = RGBColor.from_string(theme.colors["accent1"])
        shape.text = node.text
        shape.text_frame.auto_size = MSO_AUTO_SIZE.NONE
        shape.text_frame.word_wrap = True
        shape.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        fg = max([theme.colors["dk1"], theme.colors["lt1"]], key=lambda c: contrast(c, fill))
        for p in shape.text_frame.paragraphs:
            p.font.name, p.font.size = theme.font, Pt(theme.body_size)
            p.font.color.rgb = RGBColor.from_string(fg)
            p.alignment = PP_ALIGN.CENTER
        shapes[node.id] = shape
    for i, edge in enumerate(diagram.edges):
        a, b = shapes[edge.source], shapes[edge.target]
        horizontal = diagram.direction == "horizontal"
        x1, y1 = (
            (a.left + a.width, a.top + a.height // 2)
            if horizontal
            else (a.left + a.width // 2, a.top + a.height)
        )
        x2, y2 = (b.left, b.top + b.height // 2) if horizontal else (b.left + b.width // 2, b.top)
        line = slide.shapes.add_connector(MSO_CONNECTOR.ELBOW, x1, y1, x2, y2)
        line.name = f"rsa:edge:{edge.source}:{edge.target}"
        line.begin_connect(a, 3 if horizontal else 2)
        line.end_connect(b, 1 if horizontal else 0)
        line.line.color.rgb = RGBColor.from_string(theme.colors["accent1"])
        end = OxmlElement("a:tailEnd")
        end.set("type", "triangle")
        line.line._get_or_add_ln().append(end)
        if edge.label:
            if not horizontal or abs(y1 - y2) > Inches(0.05):
                raise LayoutError("Edge labels on branching/vertical connectors need a separate slide")
            text_box(
                slide,
                f"rsa:edge-label:{i}",
                edge.label,
                Box(x1, y1 - Inches(0.43), max(x2 - x1, Inches(0.5)), Inches(0.4)),
                theme,
                12,
            )


def native_table(slide, data, box, theme):
    rows = [data.columns, *data.rows]
    table_shape = slide.shapes.add_table(len(rows), len(data.columns), box.x, box.y, box.w, box.h)
    table_shape.name = "rsa:table"
    table = table_shape.table
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            check_fit(value, Box(0, 0, box.w // len(row), box.h // len(rows)), theme.body_size)
            cell.text = value
            cell.text_frame.auto_size = MSO_AUTO_SIZE.NONE
            cell.fill.background()
            # Explicit cell borders override the default PowerPoint table style.
            # Keep white row separators rather than removing their spacing.
            properties = cell._tc.get_or_add_tcPr()
            for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
                for old in properties.findall(tag, properties.nsmap):
                    properties.remove(old)
            for index, edge in enumerate(("L", "R", "T", "B")):
                line = OxmlElement("a:ln" + edge)
                line.set("w", "12700")
                if edge in {"L", "R"}:
                    line.append(OxmlElement("a:noFill"))
                else:
                    fill = OxmlElement("a:solidFill")
                    color = OxmlElement("a:srgbClr")
                    color.set("val", "000000" if r == 0 or (r == 1 and edge == "T") else "FFFFFF")
                    fill.append(color)
                    line.append(fill)
                properties.insert(index, line)
            numeric = r > 0 and re.fullmatch(
                r"[+\-−]?(?:\d+(?:,\d{3})*(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?%?", value.strip()
            )
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.RIGHT if numeric else PP_ALIGN.LEFT
                p.font.name, p.font.size = theme.font, Pt(theme.body_size)
                p.font.color.rgb = RGBColor.from_string(theme.foreground)
                if r == 0:
                    p.font.bold = True
                rpr = p.font._rPr
                ea = rpr.find("a:ea", rpr.nsmap)
                if ea is None:
                    ea = OxmlElement("a:ea")
                    rpr.insert_element_before(ea, "a:cs", "a:sym", "a:hlinkClick", "a:hlinkMouseOver", "a:rtl", "a:extLst")
                ea.set("typeface", theme.font)
    return table_shape


def native_chart(slide, spec, box, theme):
    if spec.kind == "scatter":
        data = XyChartData()
        for item in spec.series:
            series = data.add_series(item.name)
            for x, y in zip(spec.x_values, item.values):
                series.add_data_point(x, y)
        kind = XL_CHART_TYPE.XY_SCATTER
    else:
        data = CategoryChartData()
        data.categories = spec.categories
        for item in spec.series:
            data.add_series(item.name, item.values)
        kind = XL_CHART_TYPE.COLUMN_CLUSTERED if spec.kind == "bar" else XL_CHART_TYPE.LINE
    shape = slide.shapes.add_chart(kind, box.x, box.y, box.w, box.h, data)
    shape.name = "rsa:chart"
    chart = shape.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.font.name, chart.font.size = theme.font, Pt(max(14, theme.body_size * 0.7))
    for axis, label in [(chart.category_axis, spec.x_label), (chart.value_axis, spec.y_label)]:
        axis.has_title = True
        axis.axis_title.text_frame.text = label
    # python-pptx 1.0.2 writes negative axis IDs. Use small positive IDs for
    # both the UInt32 schema and Office's stricter Int32 maximum, keeping all
    # axis definitions and cross-references consistent within this chart.
    axes = chart._chartSpace.xpath(".//c:axId | .//c:crossAx")
    ids = {value: str(i + 1) for i, value in enumerate(dict.fromkeys(e.get("val") for e in axes))}
    for element in axes:
        element.set("val", ids[element.get("val")])
    return shape


def _check_slot(prototype, paragraphs):
    """Conservative fit using the actual slot margins, level indents and line spacing."""
    tf = prototype.text_frame
    available = (prototype.height - tf.margin_top - tf.margin_bottom) / 12700
    required = 0.0
    expanded = [(line, level, bullet) for text, level, bullet in paragraphs for line in text.split("\n")]
    for text, level, _ in expanded:
        style = paragraph_style(prototype, level)
        size = slot_font_size(prototype, level)
        width = (prototype.width - tf.margin_left - tf.margin_right - int(style.get("marL", 0))) / 12700
        lines = sum(max(1, math.ceil(units(line) * size / max(width, 1))) for line in text.split("\n"))
        spacing = style.find("a:lnSpc", style.nsmap)
        line_height = size
        if spacing is not None and len(spacing):
            value = spacing[0]
            line_height = (
                size * int(value.get("val")) / 100000
                if value.tag.endswith("spcPct")
                else int(value.get("val")) / 100
            )
        required += lines * line_height
        for tag in ("a:spcBef", "a:spcAft"):
            space = style.find(tag, style.nsmap)
            if space is not None and len(space):
                value = space[0]
                required += (
                    size * int(value.get("val")) / 100000
                    if value.tag.endswith("spcPct")
                    else int(value.get("val")) / 100
                )
    if required > available:
        raise LayoutError(
            f"TEXT_OVERFLOW: {prototype.name}; split the slide, template geometry and fonts were kept"
        )


def _named_slide(prs, layout, item, theme, images):
    slots = slots_of(layout)
    slide = prs.slides.add_slide(layout)
    live = {}
    for shape in slide.placeholders:
        prototype = next(
            p for p in layout.placeholders if p.placeholder_format.idx == shape.placeholder_format.idx
        )
        shape.left, shape.top, shape.width, shape.height = (
            prototype.left,
            prototype.top,
            prototype.width,
            prototype.height,
        )
        shape.name = prototype.name
        live[prototype.name.removeprefix("rsa:")] = shape
    title = slide.shapes.title
    if title is None:
        raise LayoutError("Template needs a title placeholder")
    title.name = f"rsa:title:{item.slide_id}"
    title_prototype = slots["title"]
    explicit = title_prototype._element.xpath("./p:txBody/a:lstStyle/a:lvl1pPr/a:defRPr/@sz")
    if explicit:
        _check_slot(title_prototype, [(item.title, 0, False)])
        write_slot(title, title_prototype, [(item.title, 0, False)])
    else:
        check_fit(item.title, Box(title.left, title.top, title.width, title.height), theme.title_size)
        title.text = item.title  # Keep master-derived font/color and original title geometry.
    content_slots = [p for role, p in slots.items() if role != "title"]
    bounds = Box(
        min(p.left for p in content_slots),
        min(p.top for p in content_slots),
        max(p.left + p.width for p in content_slots) - min(p.left for p in content_slots),
        max(p.top + p.height for p in content_slots) - min(p.top for p in content_slots),
    )
    paragraphs = {"key_message": [(item.key_message, 0, False)]}
    for block in item.body_blocks:
        if block.slot not in slots:
            raise LayoutError(f"Layout has no {block.slot} slot; choose a suitable layout")
        paragraphs.setdefault(block.slot, []).extend(
            (line, block.level, block.bullet) for line in block.text.split("\n")
        )
    visual = any([item.diagram_spec, item.table_spec, item.chart_spec, item.image_references])
    if visual and "visual" not in slots:
        raise LayoutError("Layout has no visual slot; choose a figure layout")
    if item.citations:
        if "citations" not in slots:
            raise LayoutError("Layout has no citation slot")
        labels = list(dict.fromkeys(c.label for c in item.citations))
        paragraphs["citations"] = [("".join(labels), 0, False)]
    for role, shape in list(live.items()):
        if role == "title":
            continue
        if role in paragraphs:
            _check_slot(slots[role], paragraphs[role])
            write_slot(shape, slots[role], paragraphs[role])
            shape.name = "rsa:key_message" if role == "key_message" else f"rsa:slot:{role}"
        else:
            shape._element.getparent().remove(shape._element)
    if visual:
        s = slots["visual"]
        box = Box(s.left, s.top, s.width, s.height)
        if item.diagram_spec:
            diagram_shapes(slide, item.diagram_spec, box, theme)
        elif item.table_spec:
            native_table(slide, item.table_spec, box, theme)
        elif item.chart_spec:
            native_chart(slide, item.chart_spec, box, theme)
        else:
            for i, reference in enumerate(item.image_references):
                if not images or reference.source_id not in images:
                    raise LayoutError("Image requires a registered original PNG/JPEG source")
                from PIL import Image

                cell_w = box.w // len(item.image_references)
                caption_h = int(theme.body_size * 1.4 * 12700)
                with Image.open(images[reference.source_id]) as image:
                    ratio = min(cell_w / image.width, (box.h - caption_h) / image.height)
                    width, height = int(image.width * ratio), int(image.height * ratio)
                picture = slide.shapes.add_picture(
                    str(images[reference.source_id]),
                    box.x + i * cell_w + (cell_w - width) // 2,
                    box.y,
                    width,
                    height,
                )
                picture.name = f"rsa:image:{reference.id}"
                text_box(
                    slide,
                    f"rsa:caption:{reference.id}",
                    reference.caption,
                    Box(box.x + i * cell_w, box.y + box.h - caption_h, cell_w, caption_h),
                    theme,
                )
    # python-pptx does not clone slide-number placeholders automatically.
    page_prototype = next(
        (p for p in layout.placeholders if p.placeholder_format.type == PP_PLACEHOLDER.SLIDE_NUMBER), None
    )
    if page_prototype is not None:
        element = deepcopy(page_prototype._element)
        element.nvSpPr.cNvPr.set("id", str(max(s.shape_id for s in slide.shapes) + 1))
        element.nvSpPr.cNvPr.set("name", "rsa:page_number")
        for text in element.xpath(".//a:t"):
            text.text = str(item.slide_order)
        slide.shapes._spTree.insert_element_before(element, "p:extLst")
    return slide, bounds


def _generate_once(
    template: Path, spec: SlideSpec, output: Path, images: dict[str, Path] | None = None, repair=0
):
    prs = Presentation(template)
    uses_slots = any(slots_of(layout) for layout in layouts_of(prs))
    for element in list(prs.slides._sldIdLst):
        prs.part.drop_rel(element.rId)
        prs.slides._sldIdLst.remove(element)
    manifest = {
        "spec_digest": spec.digest(),
        "slides": [],
        "template_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
    }
    for item in sorted(spec.slides, key=lambda s: s.slide_order):
        if item.layout_id >= len(layouts_of(prs)):
            raise LayoutError("Unknown template layout")
        layout = layouts_of(prs)[item.layout_id]
        if uses_slots and not slots_of(layout):
            raise LayoutError("Choose a named template layout returned by get_template_info")
        theme = theme_of(prs, item.layout_id)
        if slots_of(layout):
            slide, bounds = _named_slide(prs, layout, item, theme, images)
            slide.notes_slide.notes_text_frame.text = json.dumps(
                {
                    "slide_id": item.slide_id,
                    "spec_digest": spec.digest(),
                    "source_references": [r.model_dump() for r in item.source_references],
                    "citations": [c.model_dump() for c in item.citations],
                },
                ensure_ascii=False,
            )
            manifest["slides"].append(
                {
                    "slide_id": item.slide_id,
                    "part": str(slide.part.partname),
                    "layout_id": item.layout_id,
                    "body_box": bounds.__dict__,
                    "placement": "template_slots",
                }
            )
            continue
        if any(b.level or b.bullet or b.slot != "body" for b in item.body_blocks):
            raise LayoutError("Paragraph hierarchy requires a template with named body slots")
        if theme.body_size < 17:
            raise LayoutError("MASTER_FONT_TOO_SMALL: choose an approved layout with a readable body font")
        if contrast(theme.foreground, theme.background) < 4.5:
            raise LayoutError("MASTER_CONTRAST_TOO_LOW: template needs manual review")
        bounds = body_box(prs, layout)
        slide = prs.slides.add_slide(layout)
        title = slide.shapes.title
        if title is None:
            raise LayoutError("Selected layout has no title placeholder")
        check_fit(item.title, Box(title.left, title.top, title.width, title.height), theme.title_size)
        title.text, title.name = item.title, f"rsa:title:{item.slide_id}"
        for placeholder in list(slide.placeholders):
            if placeholder != title:
                el = placeholder._element
                el.getparent().remove(el)
        title_size = theme.title_size
        for p in title.text_frame.paragraphs:
            p.font.name, p.font.size = theme.font, Pt(title_size)
            p.font.color.rgb = RGBColor.from_string(theme.foreground)
        gap, message_h = Inches(0.18), Inches(0.66 + repair * 0.48)
        cite_h = Inches(0.4)
        target_boxes = {}
        message_box = Box(bounds.x, bounds.y, bounds.w, int(message_h))
        text_box(slide, "rsa:key_message", item.key_message, message_box, theme)
        target_boxes["key_message"] = message_box
        top = bounds.y + message_h + cite_h + gap
        available = bounds.y + bounds.h - top
        visual = any([item.diagram_spec, item.table_spec, item.chart_spec, item.image_references])
        body_w = int(bounds.w * 0.34) if visual else bounds.w
        if item.body_blocks:
            cell_h = (available - gap * (len(item.body_blocks) - 1)) // len(item.body_blocks)
            for i, block in enumerate(item.body_blocks):
                b = Box(bounds.x, int(top + i * (cell_h + gap)), body_w, int(cell_h - cite_h))
                text_box(slide, f"rsa:block:{block.id}", block.text, b, theme)
                target_boxes[block.id] = b
        visual_x = bounds.x + body_w + gap if item.body_blocks else bounds.x
        visual_w = bounds.w - body_w - gap if item.body_blocks else bounds.w
        b = Box(int(visual_x), int(top), int(visual_w), int(available - cite_h))
        if item.diagram_spec:
            diagram_shapes(slide, item.diagram_spec, b, theme, repair)
            target_boxes["diagram"] = b
        elif item.table_spec:
            native_table(slide, item.table_spec, b, theme)
            target_boxes["table"] = b
        elif item.chart_spec:
            native_chart(slide, item.chart_spec, b, theme)
            target_boxes["chart"] = b
        elif item.image_references:
            cell_w = (b.w - gap * (len(item.image_references) - 1)) // len(item.image_references)
            for i, image in enumerate(item.image_references):
                if not images or image.source_id not in images:
                    raise LayoutError("Image requires a registered original PNG/JPEG source")
                ib = Box(int(b.x + i * (cell_w + gap)), b.y, int(cell_w), b.h)
                from PIL import Image

                with Image.open(images[image.source_id]) as im:
                    ratio = min(ib.w / im.width, (ib.h - Inches(0.55)) / im.height)
                    w, h = int(im.width * ratio), int(im.height * ratio)
                pic = slide.shapes.add_picture(
                    str(images[image.source_id]), ib.x + (ib.w - w) // 2, ib.y, w, h
                )
                pic.name = f"rsa:image:{image.id}"
                text_box(
                    slide,
                    f"rsa:caption:{image.id}",
                    image.caption,
                    Box(ib.x, ib.y + ib.h - Inches(0.5), ib.w, Inches(0.5)),
                    theme,
                    16,
                )
                target_boxes[image.id] = ib
        grouped = {}
        for citation in item.citations:
            grouped.setdefault(citation.target_id, []).append(citation.label)
        for target, labels in grouped.items():
            cb = target_boxes.get(target)
            if cb is None:
                raise LayoutError("Missing citation target")
            text_box(
                slide,
                f"rsa:citation:{target}",
                "".join(dict.fromkeys(labels)),
                Box(cb.x, cb.y + cb.h, cb.w, int(cite_h)),
                theme,
                14,
            )
        slide.notes_slide.notes_text_frame.text = json.dumps(
            {
                "slide_id": item.slide_id,
                "spec_digest": spec.digest(),
                "source_references": [r.model_dump() for r in item.source_references],
                "citations": [c.model_dump() for c in item.citations],
            },
            ensure_ascii=False,
        )
        manifest["slides"].append(
            {
                "slide_id": item.slide_id,
                "part": str(slide.part.partname),
                "layout_id": item.layout_id,
                "body_box": bounds.__dict__,
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    prs.save(output)
    restore_template_parts(template, output)
    manifest["structure"] = inspect_pptx(output)
    manifest["quality"] = verify(template, output, spec, manifest)
    manifest["quality"]["auto_repair_attempts"] = repair
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def generate(template: Path, spec: SlideSpec, output: Path, images: dict[str, Path] | None = None):
    # Only enlarge available text/node boxes. Approved content and font sizes stay unchanged.
    for repair in range(3):
        try:
            return _generate_once(template, spec, output, images, repair)
        except LayoutError as exc:
            if "TEXT_OVERFLOW" not in str(exc) or repair == 2:
                raise
    raise LayoutError("Layout repair limit reached")


def inspect_pptx(path: Path):
    prs = Presentation(path)
    result = []
    for i, slide in enumerate(prs.slides):
        shapes = []
        for s in slide.shapes:
            text = s.text if s.has_text_frame else ""
            shapes.append(
                {
                    "shape_id": s.shape_id,
                    "name": s.name,
                    "text": text,
                    "sha256": hashlib.sha256(s._element.xml.encode()).hexdigest(),
                    "native_table": s.has_table,
                    "native_chart": s.has_chart,
                }
            )
        result.append({"slide_number": i + 1, "part": str(slide.part.partname), "shapes": shapes})
    return result


def verify(template, output, spec, manifest):
    """Hard structural checks. Rendering and heuristic text fit have separate reports."""
    issues = []
    with zipfile.ZipFile(template) as src, zipfile.ZipFile(output) as dst:
        for name in src.namelist():
            if name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")):
                if name not in dst.namelist() or src.read(name) != dst.read(name):
                    issues.append(f"Master/layout/theme changed: {name}")
    prs = Presentation(output)
    if len(prs.slides) != len(spec.slides):
        issues.append("Slide count differs")
    for slide, item, m in zip(
        prs.slides, sorted(spec.slides, key=lambda s: s.slide_order), manifest["slides"]
    ):
        if slide.slide_layout.part.partname != layouts_of(prs)[item.layout_id].part.partname:
            issues.append("Wrong slide layout")
        text = "\n".join(s.text for s in slide.shapes if s.has_text_frame)
        if (
            item.title not in text
            or item.key_message not in text
            or any(b.text not in text for b in item.body_blocks)
        ):
            issues.append("Approved text differs")
        for citation in item.citations:
            if citation.label not in text:
                issues.append("Citation missing")
        if bool(item.table_spec) != any(s.has_table for s in slide.shapes):
            issues.append("Editable table missing")
        if bool(item.chart_spec) != any(s.has_chart for s in slide.shapes):
            issues.append("Editable chart missing")
        if item.chart_spec:
            chart = next(s.chart for s in slide.shapes if s.has_chart)
            if not chart.part.chart_workbook.xlsx_part:
                issues.append("Embedded chart workbook missing")
            for expected, actual in zip(item.chart_spec.series, chart.series):
                if list(actual.values) != expected.values:
                    issues.append("Approved numeric values differ")
        b = Box(**m["body_box"])
        shapes = [s for s in slide.shapes if not s.name.startswith(("rsa:title:", "rsa:page_number"))]
        for s in shapes:
            if (
                s.left < b.x - 100
                or s.top < b.y - 100
                or s.left + s.width > b.x + b.w + 100
                or s.top + s.height > b.y + b.h + 100
            ):
                issues.append(f"Content outside body: {s.name}")
        objects = [s for s in shapes if not s.name.startswith(("rsa:edge:", "rsa:edge-label:"))]
        for i, a in enumerate(objects):
            for other in objects[i + 1 :]:
                overlap_x = min(a.left + a.width, other.left + other.width) - max(a.left, other.left)
                overlap_y = min(a.top + a.height, other.top + other.height) - max(a.top, other.top)
                if overlap_x > Inches(0.02) and overlap_y > Inches(0.02):
                    issues.append(f"Overlap: {a.name} / {other.name}")
    if issues:
        raise LayoutError("; ".join(issues))
    return {
        "status": "passed",
        "text_fit": "conservative_estimate",
        "overlap": "bounding_boxes",
        "font_rendering": "requires_visual_review",
        "auto_repair_attempts": 0,
    }


def render(pptx: Path, directory: Path, timeout=240):
    soffice, pdftoppm = shutil.which("soffice"), shutil.which("pdftoppm")
    if not soffice or not pdftoppm:
        raise RuntimeError("RENDERER_MISSING: install LibreOffice and Poppler")
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rsa-lo-") as profile:
        result = subprocess.run(
            [
                soffice,
                f"-env:UserInstallation={Path(profile).as_uri()}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(directory),
                str(pptx.resolve()),
            ],
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        pdf = directory / f"{pptx.stem}.pdf"
        if result.returncode or not pdf.exists():
            raise RuntimeError("RENDER_FAILED")
    for old_page in directory.glob("slide-*.png"):
        if re.fullmatch(r"slide-\d+\.png", old_page.name):
            old_page.unlink()
    subprocess.run(
        [pdftoppm, "-scale-to", "1600", "-png", str(pdf), str(directory / "slide")],
        capture_output=True,
        check=True,
        timeout=timeout,
    )
    images = sorted(directory.glob("slide-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
    from pypdf import PdfReader

    page_count = len(PdfReader(pdf).pages)
    if page_count != len(Presentation(pptx).slides) or len(images) != page_count:
        raise RuntimeError("RENDER_PAGE_COUNT_MISMATCH")
    return {
        "pdf": pdf.name,
        "images": [p.name for p in images],
        "page_count": page_count,
        "renderer": "LibreOffice",
        "fidelity": "approximate",
        "powerpoint_verified": False,
    }


def patch_text(source: Path, destination: Path, changes: list[dict]):
    """Edit only selected XML parts. All other OPC entries retain their exact bytes."""
    with zipfile.ZipFile(source) as archive:
        modified = {}
        targets = set()
        for change in changes:
            key = (change["slide_number"], change["shape_id"])
            if key in targets:
                raise LayoutError("Duplicate patch target")
            targets.add(key)
            slides = inspect_pptx(source)
            part = slides[change["slide_number"] - 1]["part"].lstrip("/")
            root = modified.get(part)
            if root is None:
                root = etree.fromstring(archive.read(part))
            matches = root.xpath(
                ".//p:sp[p:nvSpPr/p:cNvPr[@id=$id]]", namespaces=NS, id=str(change["shape_id"])
            )
            if len(matches) != 1 or matches[0].getparent().tag != f"{{{NS['p']}}}spTree":
                raise LayoutError("UNSUPPORTED_SHAPE: only top-level plain text shapes can be changed")
            shape = matches[0]
            # Serialize through python-pptx for the same fingerprint representation.
            current = next(
                s for s in slides[change["slide_number"] - 1]["shapes"] if s["shape_id"] == change["shape_id"]
            )
            if current["sha256"] != change["expected_sha256"]:
                raise LayoutError(
                    "EDIT_CONFLICT: reuploaded shape differs; inspect and obtain fresh approval"
                )
            texts = shape.xpath("./p:txBody/a:p/a:r/a:t", namespaces=NS)
            if (
                len(texts) != 1
                or len(shape.xpath("./p:txBody/a:p", namespaces=NS)) != 1
                or shape.xpath(".//a:fld", namespaces=NS)
            ):
                raise LayoutError("UNSUPPORTED_RICH_TEXT: preserve runs by editing manually")
            # Do not resize the original object or silently shrink text.
            prs = Presentation(source)
            s = next(
                s for s in prs.slides[change["slide_number"] - 1].shapes if s.shape_id == change["shape_id"]
            )
            size = s.text_frame.paragraphs[0].runs[0].font.size or s.text_frame.paragraphs[0].font.size
            if size is None:
                raise LayoutError("INHERITED_FONT_PATCH: explicit font required for safe fit check")
            check_fit(change["text"], Box(s.left, s.top, s.width, s.height), size.pt)
            texts[0].text = change["text"]
            modified[part] = root
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w") as target:
            for info in archive.infolist():
                data = (
                    etree.tostring(
                        modified[info.filename], xml_declaration=True, encoding="UTF-8", standalone=True
                    )
                    if info.filename in modified
                    else archive.read(info.filename)
                )
                target.writestr(info, data)
    return {"changed_parts": sorted(modified), "preservation": "all_unselected_parts_byte_identical"}
