"""Named layout slots: keep template paragraph styles and placeholder geometry."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from lxml import etree
from pptx.oxml.xmlchemy import OxmlElement


def layouts_of(prs):
    """Stable file-wide layout IDs, including layouts on the second and later masters."""
    return [layout for master in prs.slide_masters for layout in master.slide_layouts]


def restore_template_parts(template, output):
    """Keep original bytes after checking that the writer made only serialization changes."""
    with TemporaryDirectory(dir=output.parent) as scratch:
        staged = Path(scratch) / "written.pptx"
        with ZipFile(template) as source, ZipFile(output) as written:
            replacements = {}
            for name in source.namelist():
                if not name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/")):
                    continue
                original, actual = source.read(name), written.read(name)
                a, b = etree.fromstring(original), etree.fromstring(actual)
                if name.endswith(".rels"):
                    equal = (a.tag, a.attrib, sorted(tuple(sorted(e.attrib.items())) for e in a)) == (
                        b.tag,
                        b.attrib,
                        sorted(tuple(sorted(e.attrib.items())) for e in b),
                    )
                else:
                    equal = etree.tostring(a, method="c14n") == etree.tostring(b, method="c14n")
                if not equal:
                    raise ValueError(f"Template part was modified: {name}")
                replacements[name] = original
            with ZipFile(staged, "w") as target:
                for info in written.infolist():
                    target.writestr(info, replacements.get(info.filename, written.read(info.filename)))
        staged.replace(output)


def slots_of(layout):
    return {p.name.removeprefix("rsa:"): p for p in layout.placeholders if p.name.startswith("rsa:")}


def paragraph_style(shape, level=0):
    styles = shape._element.xpath(f"./p:txBody/a:lstStyle/a:lvl{level + 1}pPr")
    if not styles:
        raise ValueError(f"Template has no explicit paragraph style for level {level}: {shape.name}")
    return styles[0]


def write_slot(shape, prototype, paragraphs):
    """paragraphs are (text, level, bullet); XML and coordinates never come from the model."""
    tx = shape._element.txBody
    for child in list(tx):
        tx.remove(child)
    source_tx = prototype._element.txBody
    for tag in ("a:bodyPr", "a:lstStyle"):
        tx.append(deepcopy(source_tx.find(tag, source_tx.nsmap)))
    expanded = [(line, level, bullet) for text, level, bullet in paragraphs for line in text.split("\n")]
    for text, level, bullet in expanded:
        style = paragraph_style(prototype, level)
        if bullet and not any(
            style.find(tag, style.nsmap) is not None for tag in ("a:buChar", "a:buAutoNum")
        ):
            raise ValueError(f"Template has no bullet style for level {level}: {prototype.name}")
        p = OxmlElement("a:p")
        ppr = deepcopy(style)
        ppr.tag = f"{{{ppr.nsmap['a']}}}pPr"
        ppr.set("lvl", str(level))
        if not bullet:
            for element in list(ppr):
                if element.tag.rsplit("}", 1)[-1].startswith("bu"):
                    ppr.remove(element)
            default = ppr.find("a:defRPr", ppr.nsmap)
            position = list(ppr).index(default) if default is not None else len(ppr)
            ppr.insert(position, OxmlElement("a:buNone"))
        p.append(ppr)
        run = OxmlElement("a:r")
        rpr = deepcopy(style.find("a:defRPr", style.nsmap))
        if rpr is not None:
            rpr.tag = f"{{{rpr.nsmap['a']}}}rPr"
            run.append(rpr)
        value = OxmlElement("a:t")
        value.text = text
        run.append(value)
        p.append(run)
        tx.append(p)
    if not paragraphs:
        tx.append(OxmlElement("a:p"))


def slot_font_size(prototype, level=0):
    style = paragraph_style(prototype, level)
    rpr = style.find("a:defRPr", style.nsmap)
    if rpr is None or rpr.get("sz") is None:
        raise ValueError(f"Template needs an explicit font size: {prototype.name}")
    return int(rpr.get("sz")) / 100


def slot_font(prototype, level=0):
    style = paragraph_style(prototype, level)
    for tag in ("a:ea", "a:latin"):
        fonts = style.findall(f"a:defRPr/{tag}", style.nsmap)
        if fonts and fonts[0].get("typeface") and not fonts[0].get("typeface").startswith("+"):
            return fonts[0].get("typeface")
    return None
