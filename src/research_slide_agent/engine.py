"""Canonical PowerPoint generation, inspection, rendering and targeted text edits."""

from __future__ import annotations

import hashlib
import math
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.util import Inches

from .models import SlideSpec

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


def template_info(path: Path):
    from .models import RESEARCH_CONTENT_ROLES
    from .prototypes import COMPOSITIONS, profile_for

    profile = profile_for(path)
    if not profile:
        raise LayoutError("CANONICAL_TEMPLATE_REQUIRED: prepare the template profile")
    return {"template_id": "lab", "sha256": profile["template_sha256"],
            "engine": profile["engine"], "style_version": profile["style_version"],
            "schema_version": "1.3", "prototypes": profile["prototypes"],
            "supported_schema_versions": ["1.3"], "recommended_schema_version": "1.3",
            "compositions": COMPOSITIONS,
            "required_content_roles": {key: sorted(value) for key, value in RESEARCH_CONTENT_ROLES.items()},
            "section_independent_of_prototype": True,
            "visual_prototypes": {
                "method": "editable diagram or original image with explanatory text; any section in 1.3",
                "results_figure": "wide original image or diagram with short explanation; any section in 1.3",
                "overview": "three text groups and a key diagram; also usable for a summary in 1.3",
            },
            "layouts": [], "generation": "clone canonical pages; replace text and framed evidence",
            "diagram_capabilities": {
                "native_connectors": True, "branches_and_merges": True,
                "max_nodes": 12, "max_stages": 6, "max_parallel_nodes": 4,
                "forward_adjacent_stages_only": True, "custom_emphasis": False,
                "fit_policy": "reject overflow; try a suitable composition, simplify repetition, then split the explanation",
            }}


def units(text):
    return sum(1 if unicodedata.east_asian_width(c) in "WF" else 0.56 for c in text)


def check_fit(text, box, size):
    width = box.w / 12700 - 12
    height = box.h / 12700 - 8
    lines = sum(max(1, math.ceil(units(line) * size / max(width, 1))) for line in text.split("\n"))
    if lines * size * 1.25 > height:
        raise LayoutError("TEXT_OVERFLOW: shorten content or split the slide; font size was not reduced")


def graph_positions(diagram, box, *, gap=None):
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
    gap = Inches(0.32) if gap is None else gap
    result = {}
    for i, level in enumerate(levels):
        for j, node_id in enumerate(level):
            if diagram.direction == "horizontal":
                w = (box.w - gap * (len(levels) - 1)) // len(levels)
                h = min(Inches(1.1), (box.h - gap * (len(level) - 1)) // len(level))
                x = box.x + i * (w + gap)
                y = box.y + (box.h - (h * len(level) + gap * (len(level) - 1))) // 2 + j * (h + gap)
            else:
                h = (box.h - gap * (len(levels) - 1)) // len(levels)
                w = min(Inches(3), (box.w - gap * (len(level) - 1)) // len(level))
                x = box.x + (box.w - (w * len(level) + gap * (len(level) - 1))) // 2 + j * (w + gap)
                y = box.y + i * (h + gap)
            result[node_id] = Box(int(x), int(y), int(w), int(h))
    return result


def generate(template: Path, spec: SlideSpec, output: Path, images: dict[str, Path] | None = None):
    from .prototypes import generate_prototypes

    return generate_prototypes(template, spec, output, images)


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


def verify(template, output, spec, manifest, images=None):
    """Reconstruct canonical slide XML; content and visual review are separate."""
    from .prototypes import verify_prototypes

    return verify_prototypes(template, output, spec, manifest, images)


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
                    "EDIT_CONFLICT: reuploaded shape differs; inspect and create a new patch"
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
