"""Extract the supplied professor sample into a small, source-traceable PPTX template.

The recipe is deliberately specific to slide_sample.pptx. It never guesses which
research figures or hidden draft pages should become shared template artwork.
"""

import argparse
import hashlib
import json
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.oxml.xmlchemy import OxmlElement

from research_slide_agent.template_styles import layouts_of, write_slot

SOURCE_SHA256 = "de2fe26ff1a007e2f72d9258563bc4554a408fc06ab5054c5fd0cd8835f1afc3"


def shape_by_id(slide, shape_id):
    return next(s for s in slide.shapes if s.shape_id == shape_id)


def style_from_paragraph(shape, index, size=None):
    """Retain actual run/paragraph properties, not an inferred font/color palette."""
    paragraph = shape.text_frame.paragraphs[index]._p
    ppr = paragraph.find("a:pPr", paragraph.nsmap)
    level = int(ppr.get("lvl", "0")) if ppr is not None else 0
    master = shape.part.slide_layout.slide_master
    kind = "bodyStyle" if shape.is_placeholder else "otherStyle"
    inherited = master._element.xpath(f"./p:txStyles/p:{kind}/a:lvl{level + 1}pPr")
    style = deepcopy(inherited[0]) if inherited else OxmlElement("a:pPr")
    if ppr is not None:
        style.attrib.update(ppr.attrib)
        for child in ppr:
            for old in style.findall(child.tag):
                style.remove(old)
            style.append(deepcopy(child))
    rprs = paragraph.xpath("./a:r/a:rPr")
    default = style.find("a:defRPr", style.nsmap)
    rpr = deepcopy(default) if default is not None else OxmlElement("a:defRPr")
    if rprs:
        rpr.attrib.update(rprs[0].attrib)
        for child in rprs[0]:
            for old in rpr.findall(child.tag):
                rpr.remove(old)
            rpr.append(deepcopy(child))
    if size is not None:
        rpr.set("sz", str(size))
    # Merging inherited and direct properties can move latin/ea after cs.
    # CT_TextCharacterProperties is an ordered sequence, not a property map.
    run_order = [
        "ln", "noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill",
        "effectLst", "effectDag", "highlight", "uLnTx", "uLn", "uFillTx", "uFill",
        "latin", "ea", "cs", "sym", "hlinkClick", "hlinkMouseOver", "rtl", "extLst",
    ]
    rpr[:] = sorted(rpr, key=lambda e: run_order.index(e.tag.rsplit("}", 1)[-1]))
    rpr.tag = f"{{{rpr.nsmap['a']}}}defRPr"
    for old in style.findall("a:defRPr", style.nsmap):
        style.remove(old)
    # Missing paragraph properties must not pick up the destination bodyStyle's
    # colored Wingdings bullets or spacing when an ordinary textbox becomes a slot.
    for tag in ("a:spcBef", "a:spcAft"):
        if style.find(tag, style.nsmap) is None:
            spacing = OxmlElement(tag)
            points = OxmlElement("a:spcPts")
            points.set("val", "0")
            spacing.append(points)
            style.append(spacing)
    if not any(style.find(tag, style.nsmap) is not None for tag in ("a:buClr", "a:buClrTx")):
        color = OxmlElement("a:buClrTx")
        style.append(color)
    if not any(style.find(tag, style.nsmap) is not None for tag in ("a:buChar", "a:buAutoNum", "a:buNone")):
        style.append(OxmlElement("a:buNone"))
    style.append(rpr)
    order = [
        "lnSpc",
        "spcBef",
        "spcAft",
        "buClrTx",
        "buClr",
        "buSzTx",
        "buSzPct",
        "buSzPts",
        "buFontTx",
        "buFont",
        "buNone",
        "buAutoNum",
        "buChar",
        "buBlip",
        "tabLst",
        "defRPr",
        "extLst",
    ]
    style[:] = sorted(style, key=lambda e: order.index(e.tag.rsplit("}", 1)[-1]))
    return style


def placeholder(prototype, shape_id, role, idx, box, styles, kind="body"):
    element = deepcopy(prototype._element)
    nv = element.nvSpPr
    nv.cNvPr.set("id", str(shape_id))
    nv.cNvPr.set("name", "rsa:" + role)
    nv.cNvSpPr.attrib.pop("txBox", None)
    for ph in list(nv.nvPr):
        nv.nvPr.remove(ph)
    ph = OxmlElement("p:ph")
    ph.set("type", kind)
    ph.set("idx", str(idx))
    nv.nvPr.append(ph)
    sp = element.spPr
    xfrm = sp.get_or_add_xfrm()
    xfrm.off.x, xfrm.off.y, xfrm.ext.cx, xfrm.ext.cy = map(int, box)
    tx = element.txBody
    body = deepcopy(tx.bodyPr)
    for child in list(body):
        if child.tag.rsplit("}", 1)[-1] in {"spAutoFit", "normAutofit", "noAutofit"}:
            body.remove(child)
    body.append(OxmlElement("a:noAutofit"))
    body.set("wrap", "square")
    for child in list(tx):
        tx.remove(child)
    tx.append(body)
    ls = OxmlElement("a:lstStyle")
    for i, original in enumerate(styles):
        style = deepcopy(original)
        style.tag = f"{{{style.nsmap['a']}}}lvl{i + 1}pPr"
        style.attrib.pop("lvl", None)
        ls.append(style)
    tx.append(ls)
    tx.append(OxmlElement("a:p"))
    return element


def extract(source, output):
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("Source differs from the inspected sample; review the extraction recipe first")
    if source.resolve() == output.resolve():
        raise ValueError("Never overwrite the original sample")
    prs = Presentation(source)
    layouts = layouts_of(prs)
    master = prs.slides[1].slide_layout.slide_master
    body_source = shape_by_id(prs.slides[7], 4)
    cover_title = shape_by_id(prs.slides[0], 4)
    cover_author = shape_by_id(prs.slides[0], 15)
    body_box = shape_by_id(prs.slides[2], 11)
    plain = style_from_paragraph(body_source, 1)
    bullet = style_from_paragraph(body_source, 6)
    # The overview uses 16 pt for its denser body. Preserve that actual run size
    # for the third level instead of introducing an invented smaller font.
    nested = style_from_paragraph(shape_by_id(prs.slides[27], 13), 3, size=1600)
    styles = [plain, bullet, nested]
    # A citation source is picked by its actual displayed bibliography text.
    citation_shape = next(s for s in prs.slides[6].shapes if s.has_text_frame and "錦正社" in s.text)
    cite = style_from_paragraph(citation_shape, 0)
    if cite.find("a:defRPr", cite.nsmap).get("sz") is None:
        cite.find("a:defRPr", cite.nsmap).set("sz", "1050")
    x, y, w, h = body_box.left, body_box.top, body_box.width, body_box.height
    margin = body_source.text_frame.margin_left
    gap = margin * 2
    key_h = round(18 * 1.3 * 2 * 12700 + 2 * body_source.text_frame.margin_top)
    # The inspected citation actually uses 12 pt. Reserve its real line height
    # and both text-frame margins, rather than assuming the 10.5 pt fallback.
    cite_size = int(cite.find("a:defRPr", cite.nsmap).get("sz")) / 100
    cite_spacing = int(cite.find("a:lnSpc/a:spcPct", cite.nsmap).get("val")) / 100000
    cite_h = round(
        cite_size * cite_spacing * 12700
        + body_source.text_frame.margin_top
        + body_source.text_frame.margin_bottom
    ) + 1  # One EMU avoids floating-point rejection at the exact boundary.
    rest_y = y + key_h + gap
    rest_h = y + h - rest_y - cite_h - gap
    half_w = (w - gap) // 2
    regular_base = deepcopy(prs.slides[1].slide_layout._element)
    reports = []

    # Reuse five previously unused layout parts on the same source master.
    # This avoids changing the original slideMaster XML, including its layout list.
    definitions = [
        (master.slide_layouts[2], "RSA 本文", {"body": (x, rest_y, w, rest_h)}),
        (
            master.slide_layouts[3],
            "RSA 本文と図",
            {
                "body": (x, rest_y, half_w, rest_h),
                "visual": (x + half_w + gap, rest_y, half_w, rest_h),
            },
        ),
        (
            master.slide_layouts[4],
            "RSA 二段組",
            {
                "body": (x, rest_y, half_w, rest_h),
                "body_right": (x + half_w + gap, rest_y, half_w, rest_h),
            },
        ),
        (master.slide_layouts[5], "RSA 図表", {"visual": (x, rest_y, w, rest_h)}),
    ]
    for layout, name, slots in definitions:
        root = layout._element
        root.attrib.clear()
        root.attrib.update(regular_base.attrib)
        for child in list(root):
            root.remove(child)
        for child in regular_base:
            root.append(deepcopy(child))
        root.cSld.set("name", name)
        tree = root.spTree
        # Leave the original title and page number attached to the same master.
        for s in layout.placeholders:
            if s.placeholder_format.type.name == "TITLE":
                s.name = "rsa:title"
                inherited = deepcopy(master._element.xpath("./p:txStyles/p:titleStyle/a:lvl1pPr")[0])
                ls = s._element.txBody.find("a:lstStyle", s._element.nsmap)
                for child in list(ls):
                    ls.remove(child)
                ls.append(inherited)
        slots = {"key_message": (x, y, w, key_h), **slots, "citations": (x, y + h - cite_h, w, cite_h)}
        for j, (role, box) in enumerate(slots.items(), 20):
            tree.append(
                placeholder(
                    body_source,
                    100 + j,
                    role,
                    j,
                    box,
                    [cite] if role == "citations" else styles,
                    "obj" if role == "visual" else "body",
                )
            )
        reports.append({"layout_id": layouts.index(layout), "name": name, "slots": slots})

    # Cover title uses its real source shape. Source branding pictures and separator
    # remain as static layout artwork; the research title/authors are removed.
    cover = master.slide_layouts[0]
    cover._element.cSld.set("name", "RSA 表紙")
    tree = cover._element.spTree
    for child in list(tree)[2:]:
        if child.xpath(".//p:ph"):
            tree.remove(child)
    source_cover = prs.slides[0]
    for shape in source_cover.shapes:
        if shape.has_text_frame and shape.text.strip():
            continue
        element = deepcopy(shape._element)
        # Remap IDs when combining source slide artwork with original layout art.
        next_id = max(int(n.get("id")) for n in tree.xpath(".//p:cNvPr")) + 1
        remap = {}
        for node in element.xpath(".//p:cNvPr"):
            remap[node.get("id")] = str(next_id)
            node.set("id", str(next_id))
            next_id += 1
        for node in element.xpath(".//a:stCxn | .//a:endCxn"):
            if node.get("id") in remap:
                node.set("id", remap[node.get("id")])
        for node in element.iter():
            for attr, rid in list(node.attrib.items()):
                if attr.startswith("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"):
                    relationship = source_cover.part.rels[rid]
                    node.set(attr, cover.part.relate_to(relationship.target_part, relationship.reltype))
        tree.append(element)
    for j, (role, prototype, index, kind) in enumerate(
        [("title", cover_title, 0, "title"), ("key_message", cover_author, 0, "body")], 30
    ):
        style = style_from_paragraph(prototype, index)
        # Author box has several sizes in the sample; retain its actual 20 pt run.
        if role == "key_message":
            run = next(
                r
                for p in prototype.text_frame.paragraphs
                for r in p.runs
                if r.font.size and r.font.size.pt == 20
            )
            old = style.find("a:defRPr", style.nsmap)
            style.remove(old)
            new = deepcopy(run._r.rPr)
            new.tag = f"{{{new.nsmap['a']}}}defRPr"
            style.append(new)
        tree.append(
            placeholder(
                prototype,
                200 + j,
                role,
                0 if role == "title" else j,
                (prototype.left, prototype.top, prototype.width, prototype.height),
                [style],
                kind,
            )
        )
    reports.insert(0, {"layout_id": layouts.index(cover), "name": "RSA 表紙", "source_page": 1})
    for element in list(prs.slides._sldIdLst):
        prs.part.drop_rel(element.rId)
        prs.slides._sldIdLst.remove(element)
    examples = [
        [("テンプレートの見本", 0, False)],
        [("本文の見本", 0, False), ("第1階層の箇条書き", 1, True), ("第2階層の箇条書き", 2, True)],
    ]
    for item in reports:
        layout = layouts[item["layout_id"]]
        slide = prs.slides.add_slide(layout)
        for p in slide.placeholders:
            original = next(
                s for s in layout.placeholders if s.placeholder_format.idx == p.placeholder_format.idx
            )
            role = original.name.removeprefix("rsa:")
            p.name = original.name
            if role == "title":
                if original._element.xpath("./p:txBody/a:lstStyle/a:lvl1pPr"):
                    write_slot(p, original, [(item["name"], 0, False)])
                else:
                    p.text = item["name"]
            elif role in {"body", "body_right"}:
                write_slot(p, original, examples[1])
            elif role == "visual":
                write_slot(p, original, [("編集可能な図表の配置領域", 0, False)])
            elif role == "citations":
                write_slot(p, original, [(" [著者 '25]（引用位置の見本）", 0, False)])
            elif role == "key_message":
                write_slot(p, original, examples[0])
        slide.notes_slide.notes_text_frame.text = "書式確認用ダミー。研究内容・実験値は含まない。"
    for prop in ("author", "last_modified_by", "subject", "keywords", "comments", "category"):
        setattr(prs.core_properties, prop, "")
    prs.core_properties.title = "Laboratory slide template"
    package = prs.part.package
    for rel in list(package.iter_rels()):
        if rel.reltype.endswith("/thumbnail"):
            package.drop_rel(rel.rId)
    output.parent.mkdir(parents=True, exist_ok=True)
    prs.save(output)
    # Restore untouched original master/theme/layout parts verbatim. Only the five
    # intentionally normalized layouts are different from the professor source.
    changed = {str(cover.part.partname).lstrip("/")} | {
        str(layout.part.partname).lstrip("/") for layout, _, _ in definitions
    }
    changed_rels = {str(Path(p).parent / "_rels" / (Path(p).name + ".rels")) for p in changed}
    with tempfile.TemporaryDirectory(dir=output.parent) as scratch:
        saved = Path(scratch) / "saved.pptx"
        output.replace(saved)
        with (
            zipfile.ZipFile(source) as src,
            zipfile.ZipFile(saved) as generated,
            zipfile.ZipFile(output, "w") as dst,
        ):
            for info in generated.infolist():
                name = info.filename
                keep = (
                    name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/"))
                    and name not in changed | changed_rels
                )
                data = src.read(name) if keep and name in src.namelist() else generated.read(name)
                if name == "docProps/app.xml":
                    # Do not retain the research deck's 42 titles and editing
                    # history in an otherwise content-free shared template.
                    namespace = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
                    root = etree.Element(f"{{{namespace}}}Properties", nsmap={None: namespace})
                    for key, value in {
                        "Application": "Research Slide Agent",
                        "Slides": "5",
                        "Notes": "5",
                        "HiddenSlides": "0",
                        "MMClips": "0",
                    }.items():
                        etree.SubElement(root, f"{{{namespace}}}{key}").text = value
                    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                dst.writestr(info, data)
    report = {
        "source_sha256": digest,
        "template_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "source_pages": {"body_geometry": 3, "body_styles": [8, 28], "citation_style": 7, "cover": 1},
        "original_master_and_theme_preserved": True,
        "normalized_layout_parts": sorted(changed),
        "layouts": reports,
        "fonts": ["Yu Gothic", "Arial"],
        "font_substitution_in_pi_preview": True,
        "normalization": "Reserved a key-message row and citation row; split content bounds for reusable layouts.",
    }
    output.with_suffix(".profile.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("slide_sample.pptx"))
    parser.add_argument("--output", type=Path, default=Path("templates/lab-template.pptx"))
    args = parser.parse_args()
    print(json.dumps(extract(args.source, args.output), ensure_ascii=False, indent=2))
