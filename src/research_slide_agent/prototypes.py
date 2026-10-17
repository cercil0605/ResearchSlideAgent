"""Clone canonical slide XML. Formatting is selected from examples, never from client XML.

The OPC writer keeps shared parts byte-identical, including logos, masters and themes.
No dependency on the historical 42-slide extraction recipe.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import posixpath
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree as E
from pptx import Presentation

from .models import PrototypeParagraph

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}
ENGINE = "prototype-clone-v1"
STYLE_VERSION = "skeleton-2026-10-17.1"
PROTOTYPE_IDS = (
    "cover", "overview", "background", "related", "objective", "method", "experiment",
    "results_figure", "results_table", "discussion", "summary",
)


def xml(data):
    return E.fromstring(data)


def dump(root):
    return E.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def query(root, path):
    return root.xpath(path, namespaces=NS)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def profile_for(template):
    path = template.with_suffix(".profile.json")
    if not path.exists():
        return None
    profile = json.loads(path.read_text())
    if profile.get("engine") != ENGINE:
        return None
    if profile["template_sha256"] != sha(template.read_bytes()):
        raise ValueError("TEMPLATE_HASH_MISMATCH: prepare the canonical template profile again")
    return profile


def prepare(source, output):
    """Copy the revised skeleton unchanged and inventory its actual slide-level styles."""
    if source.resolve() == output.resolve():
        raise ValueError("Source and template destination must differ")
    prs = Presentation(source)
    if len(prs.slides) != len(PROTOTYPE_IDS):
        raise ValueError("Expected the revised 11-page skeleton; this is not the 42-page sample")
    prototypes = []
    for index, (role, slide) in enumerate(zip(PROTOTYPE_IDS, prs.slides), 1):
        title = "発表題目" if role == "cover" else "タイトル 1"
        names = {s.name for s in slide.shapes}
        if title not in names:
            raise ValueError(f"Missing canonical title on page {index}")
        slots, fixed = [], []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text and "スライド番号" not in shape.name:
                slots.append({
                    "name": shape.name,
                    "shape_id": shape.shape_id,
                    "kind": "title" if shape.name == title else
                            "heading" if shape.name.startswith("小見出し") else "content",
                    "box": [shape.left, shape.top, shape.width, shape.height],
                    "paragraphs": [
                        {"index": i, "level": p.level, "example": p.text,
                         "runs": [{"index": j, "example": r.text,
                                   "style_xml": E.tostring(r._r.rPr).decode() if r._r.rPr is not None else None}
                                  for j, r in enumerate(p.runs)]}
                        for i, p in enumerate(shape.text_frame.paragraphs)
                    ],
                })
            else:
                fixed.append(shape.name)
        entry = {"prototype_id": role, "source_page": index, "part": str(slide.part.partname).lstrip("/"),
                 "title_slot": title, "slots": slots, "fixed_elements": fixed}
        tables = [s for s in slide.shapes if s.has_table]
        if tables:
            table = tables[0].table
            entry["table"] = {"name": tables[0].name, "columns": len(table.columns),
                              "column_widths": [c.width for c in table.columns],
                              "row_heights": [r.height for r in table.rows],
                              "max_body_rows": len(table.rows) - 1}
        if "図の差し替え枠" in names:
            entry["figure"] = {"frame": "図の差し替え枠", "label": "図の記入欄"}
        prototypes.append(entry)
    profile = {"engine": ENGINE, "style_version": STYLE_VERSION,
               "source_name": source.name, "source_sha256": sha(source.read_bytes()),
               "template_sha256": sha(source.read_bytes()), "prototypes": prototypes}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(source.read_bytes())
    output.with_suffix(".profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
    # A preview of the previous template must never survive a template update.
    output.with_suffix(".preview.pdf").unlink(missing_ok=True)
    output.with_suffix(".preview.json").unlink(missing_ok=True)
    return profile


def _shape(root, name):
    result = query(root, "./p:cSld/p:spTree/*[*/p:cNvPr[@name=" + _literal(name) + "]]")
    if len(result) != 1:
        raise ValueError(f"Canonical shape missing or ambiguous: {name}")
    return result[0]


def _literal(value):
    # Names originate in the local catalog, but never interpolate client text in XPath.
    if "'" in value:
        raise ValueError("Unsupported apostrophe in canonical slot name")
    return "'" + value + "'"


def _run_style(paragraph, index):
    runs = query(paragraph, "./a:r")
    if index >= len(runs):
        raise ValueError("Unknown prototype run style")
    return runs[index]


def _style_signature(run):
    root = deepcopy(run)
    for el in root.iter():
        for key in ("dirty", "err", "smtClean"):
            el.attrib.pop(key, None)
    return E.tostring(root, method="c14n")


def replace_text(container, paragraphs):
    """Clone paragraph properties and selected runs. Newlines are soft breaks, not bullets."""
    originals = query(container, "./a:p")
    generated = []
    for value in paragraphs:
        if value.prototype_paragraph >= len(originals):
            raise ValueError("Unknown prototype paragraph; select a style returned by get_template_info")
        original = originals[value.prototype_paragraph]
        p = deepcopy(original)
        for el in list(p):
            if el.tag not in {f"{{{NS['a']}}}pPr", f"{{{NS['a']}}}endParaRPr"}:
                p.remove(el)
        selections = [(r.text, r.style_run) for r in value.runs]
        if not selections:
            styles = {_style_signature(r) for r in query(original, "./a:r/a:rPr")}
            if len(styles) > 1:
                raise ValueError("MIXED_RUN_STYLES: provide runs with template style_run indices")
            selections = [(value.text, 0)]
        for text, style in selections:
            prototype = _run_style(original, style)
            for i, line in enumerate(text.split("\n")):
                if i:
                    br = E.Element(f"{{{NS['a']}}}br")
                    rpr = prototype.find(f"{{{NS['a']}}}rPr")
                    if rpr is not None:
                        br.append(deepcopy(rpr))
                    p.insert(len(p) - bool(query(p, "./a:endParaRPr")), br)
                run = deepcopy(prototype)
                run.find(f"{{{NS['a']}}}t").text = line
                p.insert(len(p) - bool(query(p, "./a:endParaRPr")), run)
        generated.append(p)
    for old in originals:
        container.remove(old)
    # An empty slot still has a valid empty paragraph, retaining the original pPr.
    if not generated:
        p = deepcopy(originals[0])
        for el in list(p):
            if el.tag != f"{{{NS['a']}}}pPr":
                p.remove(el)
        generated = [p]
    container.extend(generated)


def _size(paragraph, fallback):
    values = query(paragraph, "./a:r/a:rPr/@sz | ./a:pPr/a:defRPr/@sz")
    return max(map(int, values)) / 100 if values else fallback


def _space(paragraph, tag, size, default=0):
    values = query(paragraph, f"./a:pPr/a:{tag}/*")
    if not values:
        return default
    el = values[0]
    return int(el.get("val")) / (100000 if el.tag.endswith("spcPct") else 100) * (
        size if el.tag.endswith("spcPct") else 1)


def check_text_fit(container, width, height, fallback=16, margins=(0, 0, 0, 0), name="text"):
    """Conservative estimate, with actual pPr spacing and continuation-line indentation."""
    from .engine import LayoutError, units

    body = query(container, "./a:bodyPr")[0]
    left, right, top, bottom = [int(body.get(k, str(v))) for k, v in
                               zip(("lIns", "rIns", "tIns", "bIns"), margins)]
    available = (height - top - bottom) / 12700
    required = 0.0
    for p in query(container, "./a:p"):
        if not query(p, "./a:r/a:t"):
            continue
        size = _size(p, fallback)
        indent = query(p, "./a:pPr/@marL")
        usable = (width - left - right - (int(indent[0]) if indent else 0)) / 12700
        # Preserve soft breaks and account for mixed runs at the largest selected size.
        lines = [""]
        for el in p:
            if el.tag == f"{{{NS['a']}}}br":
                lines.append("")
            elif el.tag == f"{{{NS['a']}}}r":
                lines[-1] += "".join(query(el, "./a:t/text()"))
        count = sum(max(1, math.ceil(units(line) * size / max(usable, 1))) for line in lines)
        required += count * _space(p, "lnSpc", size, size * 1.1)
        required += _space(p, "spcBef", size) + _space(p, "spcAft", size)
    # A final paragraph's after-space does not need a following line.
    ps = query(container, "./a:p")
    if ps:
        required -= _space(ps[-1], "spcAft", _size(ps[-1], fallback))
    if required > available + 0.5:
        raise LayoutError(f"TEXT_OVERFLOW: {name}; shorten content or duplicate this prototype page")


def clone_table(shape, data):
    from .engine import LayoutError

    tbl = query(shape, ".//a:tbl")[0]
    original = query(tbl, "./a:tr")
    widths = list(map(int, query(tbl, "./a:tblGrid/a:gridCol/@w")))
    if len(data.columns) != len(widths):
        raise LayoutError(f"TABLE_COLUMNS: canonical table has {len(widths)} fixed-width columns")
    if len(data.rows) > len(original) - 1:
        raise LayoutError("TABLE_OVERFLOW: split rows across duplicate results_table pages")
    rows = []
    for index, values in enumerate([data.columns, *data.rows]):
        # Keep the header, each body row, and the final row with its black bottom rule.
        source = original[0] if index == 0 else original[-1] if index == len(data.rows) else original[index]
        row = deepcopy(source)
        for c, (cell, text) in enumerate(zip(query(row, "./a:tc"), values)):
            tx = query(cell, "./a:txBody")[0]
            replace_text(tx, [PrototypeParagraph(text=text)] if text else [])
            check_text_fit(tx, widths[c], int(row.get("h")), margins=(91440, 91440, 45720, 45720),
                           name=f"table row {index} column {c}")
        rows.append(row)
    for row in original:
        tbl.remove(row)
    tbl.extend(rows)
    query(shape, "./p:xfrm/a:ext")[0].set("cy", str(sum(int(r.get("h")) for r in rows)))


def _figure(root, item, entry, slide, media):
    """Use canonical frame/label primitives for editable diagrams or insert original images."""
    from .engine import LayoutError

    frame = _shape(root, entry["figure"]["frame"])
    label = _shape(root, entry["figure"]["label"])
    source_shape = next(s for s in slide.shapes if s.name == entry["figure"]["frame"])
    x, y, w, h = source_shape.left, source_shape.top, source_shape.width, source_shape.height
    tree = frame.getparent()
    # Keep the frame; replace only the sample label inside it.
    label.getparent().remove(label)
    if item.image_references:
        if len(item.image_references) != 1:
            raise LayoutError("One original image per canonical frame; split the page")
        ref = item.image_references[0]
        if ref.source_id not in media:
            raise LayoutError("Image requires a registered original PNG/JPEG source")
        from PIL import Image

        data = media[ref.source_id].read_bytes()
        with Image.open(media[ref.source_id]) as image:
            ratio = min(w / image.width, h / image.height)
            iw, ih = int(image.width * ratio), int(image.height * ratio)
            ext = "png" if image.format == "PNG" else "jpeg"
        name = f"rsa-{sha(data)}.{ext}"
        pic = xml(f'''<p:pic xmlns:p="{NS['p']}" xmlns:a="{NS['a']}" xmlns:r="{NS['r']}">
          <p:nvPicPr><p:cNvPr id="900" name="rsa:image"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
          <p:blipFill><a:blip r:embed="rsaImage"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
          <p:spPr><a:xfrm><a:off x="{x+(w-iw)//2}" y="{y+(h-ih)//2}"/>
          <a:ext cx="{iw}" cy="{ih}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>''')
        tree.append(pic)
        return name, data
    diagram = item.diagram_spec
    if diagram.edges or any(n.kind != "process" or n.emphasis for n in diagram.nodes):
        raise LayoutError("Canonical diagram supports ordered process boxes; use separate pages for complex graphs")
    n = len(diagram.nodes)
    if n > 4:
        raise LayoutError("DIAGRAM_OVERFLOW: split the page")
    vertical = diagram.direction == "vertical"
    gap = 120000
    for i, node in enumerate(diagram.nodes):
        nw = w - gap * 2 if vertical else (w - gap * (n + 1)) // n
        nh = (h - gap * (n + 1)) // n if vertical else min(h - gap * 2, 850000)
        nx = x + gap if vertical else x + gap + i * (nw + gap)
        ny = y + gap + i * (nh + gap) if vertical else y + (h - nh) // 2
        box = deepcopy(frame)
        caption = deepcopy(label)
        for el, sid, name in [(box, 1000 + i * 2, "rsa:node:" + node.id),
                              (caption, 1001 + i * 2, "rsa:node-label:" + node.id)]:
            nv = query(el, "./p:nvSpPr/p:cNvPr")[0]
            nv.set("id", str(sid))
            nv.set("name", name)
            transform = query(el, "./p:spPr/a:xfrm")[0]
            off, size = query(transform, "./a:off")[0], query(transform, "./a:ext")[0]
            off.set("x", str(nx))
            off.set("y", str(ny))
            size.set("cx", str(nw))
            size.set("cy", str(nh))
        tx = query(caption, "./p:txBody")[0]
        replace_text(tx, [PrototypeParagraph(text=node.text)])
        check_text_fit(tx, nw, nh, fallback=15, name=node.id)
        tree.extend([box, caption])
    return None


def build_slide(archive, entry, item, slide, media):
    from .engine import LayoutError

    root = xml(archive.read(entry["part"]))
    slots = {s["name"]: s for s in entry["slots"]}
    if set(item.replacements) - set(slots):
        raise LayoutError("Unknown replacement slot; use get_template_info prototypes")
    if entry["title_slot"] in item.replacements:
        raise LayoutError("Use title for the canonical title slot")
    replacements = dict(item.replacements)
    if item.image_references:
        caption = item.image_references[0].caption
        if "図題" not in replacements:
            replacements["図題"] = [PrototypeParagraph(text=caption)]
        elif caption not in "".join(p.text or "".join(r.text for r in p.runs) for p in replacements["図題"]):
            raise LayoutError("Image caption must be included in the canonical figure caption slot")
    replacements[entry["title_slot"]] = [PrototypeParagraph(text=item.title)]
    for name, slot in slots.items():
        if (item.diagram_spec or item.image_references) and name == entry.get("figure", {}).get("label"):
            continue  # The native visual clones this label's original run styles below.
        if name in replacements or slot["kind"] == "content":
            shape = _shape(root, name)
            tx = query(shape, "./p:txBody")[0]
            replace_text(tx, replacements.get(name, []))
            original = next(s for s in slide.shapes if s.name == name)
            fallback = 26 if item.prototype_id == "cover" and slot["kind"] == "title" else 16
            if slot["kind"] == "title" and item.prototype_id != "cover":
                values = slide.slide_layout.slide_master._element.xpath(
                    "./p:txStyles/p:titleStyle/a:lvl1pPr/a:defRPr/@sz")
                fallback = int(values[0]) / 100 if values else 24
            tf = original.text_frame
            check_text_fit(tx, original.width, original.height, fallback,
                           (tf.margin_left, tf.margin_right, tf.margin_top, tf.margin_bottom), name)
    if item.table_spec and "table" not in entry:
        raise LayoutError("Select results_table for a native canonical table")
    if "table" in entry:
        if not item.table_spec:
            raise LayoutError("results_table requires table_spec")
        clone_table(_shape(root, entry["table"]["name"]), item.table_spec)
    media_item = None
    if item.diagram_spec or item.image_references:
        if "figure" not in entry:
            raise LayoutError("Select a prototype with a figure frame")
        if entry["figure"]["label"] in item.replacements:
            raise LayoutError("Do not replace the sample label when supplying a figure")
        media_item = _figure(root, item, entry, slide, media)
    for citation in item.citations:
        text = "".join(query(root, ".//a:t/text()"))
        if citation.label not in text:
            raise LayoutError("Place each approved citation label in a nearby replacement slot")
    for text in query(root, ".//a:fld[@type='slidenum']/a:t"):
        text.text = str(item.slide_order)
    return root, media_item


def provenance(template, spec):
    source = Path(__file__).parent
    files = sorted(source.glob("*.py"))
    source_hash = sha(b"".join(p.name.encode() + b"\0" + p.read_bytes() for p in files))
    commit = os.getenv("RSA_CODE_COMMIT", "unknown")
    dirty = None
    try:
        repo = source.parents[1]
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, stderr=subprocess.DEVNULL,
                                         timeout=5).decode().strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                                            cwd=repo, timeout=5))
    except (OSError, subprocess.SubprocessError):
        pass
    return {"code_commit": commit, "working_tree_dirty": dirty, "generator_source_sha256": source_hash,
            "template_sha256": sha(template.read_bytes()), "style_version": STYLE_VERSION,
            "schema_version": spec.schema_version, "spec_version": spec.spec_version,
            "spec_digest": spec.digest(), "engine": ENGINE}


def _custom_properties(value):
    ns = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
    vt = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
    root = E.Element(f"{{{ns}}}Properties", nsmap={None: ns, "vt": vt})
    prop = E.SubElement(root, f"{{{ns}}}property", fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}",
                        pid="2", name="ResearchSlideAgentProvenance")
    E.SubElement(prop, f"{{{vt}}}lpwstr").text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return dump(root)


def generate_prototypes(template, spec, output, images=None):
    from .engine import LayoutError

    if template.resolve() == output.resolve():
        raise LayoutError("Original template must not be overwritten")
    profile = profile_for(template)
    if not profile or spec.schema_version != "1.1":
        raise LayoutError("Canonical template requires SlideSpec 1.1 prototype_id/replacements")
    entries = {e["prototype_id"]: e for e in profile["prototypes"]}
    prs = Presentation(template)
    info = provenance(template, spec)
    manifest = {**info, "provenance": info, "slides": [], "visual_review": "pending"}
    with ZipFile(template) as src:
        parts = {n: src.read(n) for n in src.namelist()
                 if not n.startswith(("ppt/slides/", "ppt/notesSlides/"))}
        presentation = xml(parts["ppt/presentation.xml"])
        rels = xml(parts["ppt/_rels/presentation.xml.rels"])
        ids = query(presentation, "./p:sldIdLst")[0]
        for el in list(ids):
            ids.remove(el)
        for rel in list(rels):
            if rel.get("Type").endswith("/slide"):
                rels.remove(rel)
        types = xml(parts["[Content_Types].xml"])
        for el in list(types):
            if el.get("PartName", "").startswith(("/ppt/slides/", "/ppt/notesSlides/")):
                types.remove(el)
        for i, item in enumerate(sorted(spec.slides, key=lambda s: s.slide_order), 1):
            if item.prototype_id not in entries:
                raise LayoutError("Unknown prototype_id")
            entry = entries[item.prototype_id]
            root, media = build_slide(src, entry, item, prs.slides[entry["source_page"] - 1], images or {})
            part = f"ppt/slides/slide{i}.xml"
            src_rels = posixpath.join(posixpath.dirname(entry["part"]), "_rels",
                                      posixpath.basename(entry["part"]) + ".rels")
            slide_rels = xml(src.read(src_rels))
            for rel in list(slide_rels):
                if rel.get("Type").endswith("/notesSlide"):
                    slide_rels.remove(rel)
            if media:
                name, data = media
                parts["ppt/media/" + name] = data
                E.SubElement(slide_rels, f"{{{NS['rel']}}}Relationship", Id="rsaImage",
                             Type=NS["r"] + "/image", Target="../media/" + name)
                ext = name.rsplit(".", 1)[1]
                if not any(el.get("Extension") == ext for el in types):
                    E.SubElement(types, f"{{{NS['ct']}}}Default", Extension=ext, ContentType="image/" + ext)
            parts[part] = dump(root)
            parts[f"ppt/slides/_rels/slide{i}.xml.rels"] = dump(slide_rels)
            rid = f"rsaSlide{i}"
            E.SubElement(ids, f"{{{NS['p']}}}sldId", id=str(255 + i), attrib={f"{{{NS['r']}}}id": rid})
            E.SubElement(rels, f"{{{NS['rel']}}}Relationship", Id=rid, Type=NS["r"] + "/slide",
                         Target=f"slides/slide{i}.xml")
            E.SubElement(types, f"{{{NS['ct']}}}Override", PartName="/" + part,
                         ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml")
            manifest["slides"].append({"slide_id": item.slide_id, "prototype_id": item.prototype_id,
                                       "source_page": entry["source_page"], "part": "/" + part})
        parts["ppt/presentation.xml"] = dump(presentation)
        parts["ppt/_rels/presentation.xml.rels"] = dump(rels)
        parts["docProps/custom.xml"] = _custom_properties(info)
        if not any(el.get("PartName") == "/docProps/custom.xml" for el in types):
            E.SubElement(types, f"{{{NS['ct']}}}Override", PartName="/docProps/custom.xml",
                         ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml")
        package_rels = xml(parts["_rels/.rels"])
        if not any(el.get("Type").endswith("/custom-properties") for el in package_rels):
            E.SubElement(package_rels, f"{{{NS['rel']}}}Relationship", Id="rsaProvenance",
                         Type=NS["r"] + "/custom-properties", Target="docProps/custom.xml")
        parts["_rels/.rels"] = dump(package_rels)
        parts["[Content_Types].xml"] = dump(types)
        # App properties otherwise retain the skeleton's obsolete slide count/title inventory.
        app_ns = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
        app = E.Element(f"{{{app_ns}}}Properties", nsmap={None: app_ns})
        for key, value in {"Application": "Research Slide Agent", "Slides": str(len(spec.slides)), "Notes": "0"}.items():
            E.SubElement(app, f"{{{app_ns}}}{key}").text = value
        parts["docProps/app.xml"] = dump(app)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Only publish a verified complete file; overflow or verification failures leave no partial output.
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        staged = Path(directory) / "candidate.pptx"
        with ZipFile(staged, "w", ZIP_DEFLATED) as dst:
            for name, data in parts.items():
                dst.writestr(name, data)
        manifest["quality"] = verify_prototypes(template, staged, spec, manifest, images)
        staged.replace(output)
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def verify_prototypes(template, output, spec, manifest, images=None):
    """Reconstruct allowed mutations from the canonical source, never trust output fingerprints."""
    from .engine import LayoutError

    profile = profile_for(template)
    entries = {e["prototype_id"]: e for e in profile["prototypes"]}
    prototypes, actual = Presentation(template), Presentation(output)
    issues = []
    if len(actual.slides) != len(spec.slides):
        issues.append("Slide count differs")
    with ZipFile(template) as src, ZipFile(output) as dst:
        for name in src.namelist():
            changed_parts = {"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml",
                             "ppt/_rels/presentation.xml.rels", "docProps/app.xml", "docProps/custom.xml"}
            if name not in changed_parts and not name.startswith(("ppt/slides/", "ppt/notesSlides/")):
                if name not in dst.namelist() or src.read(name) != dst.read(name):
                    issues.append("Fixed template part changed: " + name)
        for slide, item in zip(actual.slides, sorted(spec.slides, key=lambda s: s.slide_order)):
            entry = entries[item.prototype_id]
            expected, media = build_slide(src, entry, item, prototypes.slides[entry["source_page"] - 1], images or {})
            part = str(slide.part.partname).lstrip("/")
            found = xml(dst.read(part))
            if E.tostring(expected, method="c14n") != E.tostring(found, method="c14n"):
                issues.append(f"FORMAT_OR_CONTENT_MISMATCH: {item.slide_id} (paragraphs, runs, geometry, table and fixed elements)")
            expected_rels = xml(src.read(posixpath.join(posixpath.dirname(entry["part"]), "_rels",
                                                       posixpath.basename(entry["part"]) + ".rels")))
            for rel in list(expected_rels):
                if rel.get("Type").endswith("/notesSlide"):
                    expected_rels.remove(rel)
            if media:
                name, data = media
                E.SubElement(expected_rels, f"{{{NS['rel']}}}Relationship", Id="rsaImage",
                             Type=NS["r"] + "/image", Target="../media/" + name)
                if "ppt/media/" + name not in dst.namelist() or dst.read("ppt/media/" + name) != data:
                    issues.append("Original image differs")
            rel_part = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
            if E.tostring(expected_rels, method="c14n") != E.tostring(xml(dst.read(rel_part)), method="c14n"):
                issues.append("Slide relationships differ: " + item.slide_id)
            expected_layout = next(r.get("Target") for r in expected_rels if r.get("Type").endswith("/slideLayout"))
            if posixpath.basename(expected_layout) != posixpath.basename(str(slide.slide_layout.part.partname)):
                issues.append("Wrong canonical layout")
        recorded = query(xml(dst.read("docProps/custom.xml")), "//*[local-name()='lpwstr']/text()")
        embedded = json.loads(recorded[0])
        for key, value in {"template_sha256": sha(template.read_bytes()), "spec_digest": spec.digest(),
                           "style_version": STYLE_VERSION, "schema_version": spec.schema_version,
                           "spec_version": spec.spec_version}.items():
            if embedded.get(key) != value or manifest.get(key) != value:
                issues.append("Provenance mismatch: " + key)
    if issues:
        raise LayoutError("; ".join(issues))
    return {"status": "passed", "format_conformance": "canonical_slide_xml_and_shared_parts",
            "text_fit": "conservative_estimate", "visual_review": "pending",
            "powerpoint_verified": False, "auto_repair_attempts": 0}
