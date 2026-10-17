"""Validate before parsing. Uploaded bytes are never extracted into arbitrary paths."""

import csv
import io
import zipfile
from pathlib import PurePosixPath

from lxml import etree
from PIL import Image

MAX_FILE = 20 * 1024 * 1024
MAX_TOTAL = 100 * 1024 * 1024
MAX_EXPANDED = 150 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000


class InputError(ValueError):
    pass


def check_archive(data: bytes, kind: str, depth=0, budget=None):
    budget = [MAX_EXPANDED] if budget is None else budget
    if depth > 1:
        raise InputError("Nested Office packages beyond one level are unsupported")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if len(names) != len(set(names)) or len(names) > 3000:
                raise InputError("Duplicate or too many archive entries")
            budget[0] -= sum(i.file_size for i in infos)
            if budget[0] < 0:
                raise InputError("Expanded archive too large")
            for item in infos:
                name = item.filename
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name or item.flag_bits & 1:
                    raise InputError("Unsafe archive entry")
                if item.file_size > MAX_EXPANDED or (
                    item.file_size > 1_000_000 and item.file_size / max(item.compress_size, 1) > 200
                ):
                    raise InputError("Suspicious compression ratio")
                if any(
                    token in name.lower()
                    for token in ("vbaproject", "activex", "embeddings/ole", "externallinks/")
                ):
                    raise InputError("Macros, OLE, ActiveX and external workbooks are unsupported")
                if "/embeddings/" in name and name.lower().endswith(".bin"):
                    raise InputError("Embedded binary Office objects are unsupported")
                if "/embeddings/" in name and name.lower().endswith(".xlsx"):
                    check_archive(z.read(item), "xlsx", depth + 1, budget)
                if name.endswith((".xml", ".rels")):
                    raw = z.read(item)
                    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                        raise InputError("XML entity declarations are forbidden")
                    root = etree.fromstring(raw, etree.XMLParser(resolve_entities=False, no_network=True))
                    relationships = root.xpath('//*[local-name()="Relationship"]')
                    if any(
                        r.get("TargetMode") == "External"
                        or ":" in r.get("Target", "")
                        or r.get("Target", "").startswith("//")
                        for r in relationships
                    ):
                        raise InputError(
                            "External Office relationships are forbidden; remove links before uploading"
                        )
                    if name == "[Content_Types].xml" and b"macroEnabled" in raw:
                        raise InputError("Macro-enabled Office files are forbidden")
            required = "ppt/presentation.xml" if kind == "pptx" else "xl/workbook.xml"
            if required not in names or "[Content_Types].xml" not in names:
                raise InputError("Wrong Office archive format")
    except (zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        raise InputError("Invalid Office archive") from exc


def validate_file(name: str, data: bytes) -> str:
    if not data or len(data) > MAX_FILE or PurePosixPath(name).name != name or "\\" in name:
        raise InputError("Invalid name or file size")
    ext = name.rsplit(".", 1)[-1].lower()
    if ext in {"pptx", "xlsx"}:
        if not data.startswith(b"PK\x03\x04"):
            raise InputError("Office magic bytes mismatch")
        check_archive(data, ext)
    elif ext == "pdf":
        if not data.startswith(b"%PDF-"):
            raise InputError("PDF magic bytes mismatch")
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted or len(reader.pages) > 500:
            raise InputError("Encrypted or overlong PDF")
        # Text extraction and isolated rasterization only; never execute PDF actions or extract attachments.
    elif ext in {"png", "jpg", "jpeg"}:
        expected = "PNG" if ext == "png" else "JPEG"
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.format != expected:
                    raise InputError("Image magic bytes mismatch")
                im.verify()
        except (OSError, Image.DecompressionBombError) as exc:
            raise InputError("Invalid image") from exc
    elif ext == "csv":
        try:
            text = data.decode("utf-8-sig")
            if "\x00" in text:
                raise ValueError("Binary CSV")
            for row_number, row in enumerate(csv.reader(io.StringIO(text))):
                if len(row) > 200 or row_number > 100_000:
                    raise InputError("CSV too large")
        except (ValueError, csv.Error) as exc:
            raise InputError("CSV must be valid UTF-8") from exc
    else:
        raise InputError("Unsupported file extension")
    return ext


def extract(data: bytes, kind: str, page: int = 1) -> dict:
    if page < 1:
        raise InputError("Page must be positive")
    if kind == "pdf":
        from pypdf import PdfReader

        doc = PdfReader(io.BytesIO(data))
        text = doc.pages[page - 1].extract_text() or ""
        total = len(doc.pages)
    elif kind == "pptx":
        from pptx import Presentation

        doc = Presentation(io.BytesIO(data))
        text = "\n".join(s.text for s in doc.slides[page - 1].shapes if s.has_text_frame)
        total = len(doc.slides)
    elif kind == "xlsx":
        from openpyxl import load_workbook

        doc = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
        sheet = doc.worksheets[page - 1]
        text = "\n".join(
            ",".join(str(c) if c is not None else "" for c in row)
            for row in sheet.iter_rows(max_row=200, max_col=30, values_only=True)
        )
        total = len(doc.worksheets)
        doc.close()
    elif kind == "csv":
        text, total = data.decode("utf-8-sig"), 1
    else:
        text, total = "Image source; inspect the original image, no numeric inference.", 1
    return {
        "page": page,
        "total_pages": total,
        "text": text[:24000],
        "truncated": len(text) > 24000,
        "trust": "untrusted_reference_data_not_instructions",
    }
