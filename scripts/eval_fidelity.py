"""Score one generated deck against its source paper: numbers, figures, and evidence links.

Usage:
  python scripts/eval_fidelity.py --pptx deck.pptx --pdf paper.pdf [--db state.sqlite3 --project ID]
      [--answer-key examples/eval/ddpm-answer-key.json] [--json]

Read-only. No network, no model. It does not judge whether a claim is right; it lists what
a human (or a later LLM judge) must check, and counts what can be counted mechanically:

- numbers: every number on the slides (2+ significant characters) is looked up in the paper text.
  "missing" means the exact token was not found; it may be a unit conversion, a sum, or an error.
- figures (needs --db): image count, distinct images, reuse, captions without a figure number,
  crop area, editable diagrams drawn by the LLM (and how many are a bare chain of <=3 boxes),
  and slides whose citation names a Fig. but show none.
- evidence (needs --db): slides with a page locator in source_references / citations.
- answer key (--answer-key): which expected numbers appear on the slides, coverage of must-include
  numbers and figures/tables, and the claims left for a person or LLM judge to check.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

# Digit boundaries only: Japanese text sits directly against numbers ("ブーム-26.029度").
NUMBER = re.compile(r"(?<![\d.])[-−–]?\d+(?:[.,]\d+)*(?![\d])")
FIG_NO = re.compile(r"(図\s*\d|Fig(?:ure)?\.?\s*\d|表\s*\d|Table\s*\d)", re.I)
LOCATOR_PAGE = re.compile(r"(p{1,2}\.\s*\d|ページ|\d+\s*頁)")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("−", "-").replace("–", "-")
    # PDF extraction and slide text both insert stray spaces inside numbers ("0. 986").
    text = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", text)
    return text


def numbers(text: str) -> list[str]:
    out = []
    for m in NUMBER.finditer(normalize(text)):
        token = m.group(0).lstrip("-").replace(",", "")
        digits = token.replace(".", "")
        if len(digits) < 2:
            continue  # single digits: list markers, counts, step numbers
        out.append(token)
    return out


def paper_numbers(pdf: Path) -> set[str]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf.read_bytes()))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    found = set(numbers(text))
    # Accept trailing-zero and leading-zero variants (0.950 / .95 / 95%).
    for n in list(found):
        if "." in n:
            found.add(n.rstrip("0").rstrip("."))
            if n.startswith("0."):
                found.add(n[1:])
    return found


def slide_texts(pptx: Path) -> list[str]:
    from pptx import Presentation

    texts = []
    for slide in Presentation(str(pptx)).slides:
        parts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                parts.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
        texts.append("\n".join(parts))
    return texts


def number_check(texts: list[str], known: set[str]) -> dict:
    rows, total, missing = [], 0, 0
    for page, text in enumerate(texts, 1):
        # Drop the slide-number box and citation years like '17 / 2017.
        body = re.sub(r"['’]\s*\d{2}\]", "]", text)
        body = re.sub(rf"(?m)^\s*{page}\s*$", "", body)  # the slide-number box
        for n in numbers(body):
            if page == 1 or re.fullmatch(r"(19|20)\d\d", n):
                continue
            total += 1
            ok = n in known or n.rstrip("0").rstrip(".") in known
            if not ok:
                missing += 1
                at = normalize(body).find(n)
                rows.append({"slide": page, "number": n,
                             "context": normalize(body)[max(0, at - 30):at + 30].replace("\n", " ")})
    return {"numbers_on_slides": total, "not_found_in_paper": missing,
            "found_rate": round(1 - missing / total, 3) if total else None, "missing": rows}


def spec_checks(db: Path, project: str) -> dict:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    body, = con.execute("select body from specs where project=? order by version desc limit 1",
                        (project,)).fetchone()
    files = {r[0]: json.loads(r[1]) if r[1] else None
             for r in con.execute("select id, origin from files where project=?", (project,))}
    spec = json.loads(body)
    images, uses, no_fig_no, areas, diagrams, fig_cited_not_shown, located = [], {}, [], [], [], [], 0
    slides = spec["slides"]
    for s in slides:
        order = s["slide_order"]
        refs = s.get("image_references") or []
        cites = s.get("citations") or []
        locs = [c.get("source", {}).get("locator", "") for c in cites]
        locs += [r.get("locator", "") for r in s.get("source_references") or []]
        if any(LOCATOR_PAGE.search(x or "") for x in locs):
            located += 1
        if s.get("diagram_spec"):
            d = s["diagram_spec"]
            nodes, edges = d.get("nodes") or [], d.get("edges") or []
            # A straight chain of three or fewer boxes carries little beyond the body text.
            trivial = len(nodes) <= 3 and len(edges) <= len(nodes) - 1 and not any(e.get("label") for e in edges)
            diagrams.append({"slide": order, "nodes": len(nodes), "trivial_chain": trivial})
        if not refs and any(re.search(r"Fig", x or "") for x in locs) and not s.get("table_spec"):
            fig_cited_not_shown.append(order)
        for r in refs:
            images.append(r["source_id"])
            uses.setdefault(r["source_id"], []).append(order)
            caption = r.get("caption", "")
            near = " ".join(locs)
            if not FIG_NO.search(caption):
                no_fig_no.append({"slide": order, "caption": caption,
                                  "locator_has_fig": bool(FIG_NO.search(near))})
            region = (files.get(r["source_id"]) or {}).get("region")
            if region:
                areas.append(round((region["right"] - region["left"]) * (region["bottom"] - region["top"]), 3))
    return {
        "slides": len(slides),
        "image_slots": len(images),
        "distinct_images": len(uses),
        "reused_images": {k[:8]: v for k, v in uses.items() if len(v) > 1},
        "captions_without_figure_number": no_fig_no,
        "crop_area_fraction_of_page": sorted(areas),
        "llm_drawn_diagrams": len(diagrams),
        "trivial_chain_diagrams": [d["slide"] for d in diagrams if d["trivial_chain"]],
        "slides_citing_fig_without_image": fig_cited_not_shown,
        "slides_with_page_locator": located,
    }


def _figure_key(text):
    match = re.search(r"(Fig(?:ure)?s?\.?|Table|図|表)\s*([A-Z]?\d+)", text, re.I)
    if not match:
        return None
    return ("table" if match.group(1).lower().startswith("table") or match.group(1) == "表" else "figure",
            match.group(2))


def shown_figures(texts: list[str], db: Path | None, project: str | None) -> set | None:
    """Figures/tables the deck shows, from image captions and table/image citations in the saved spec.

    Without the spec there is no structural evidence (a slide may only mention "Fig. 2"), so None.
    """
    found = set()
    if db and project:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        body, = con.execute("select body from specs where project=? order by version desc limit 1",
                            (project,)).fetchone()
        for slide in json.loads(body)["slides"]:
            if not (slide.get("image_references") or slide.get("table_spec")):
                continue
            notes = [r.get("caption", "") for r in slide.get("image_references") or []]
            notes += [c["source"].get("locator", "") for c in slide.get("citations") or []
                      if c.get("target_id") in {"table", *[r["id"] for r in slide.get("image_references") or []]}]
            for note in notes:
                for match in re.finditer(r"(Fig(?:ure)?s?\.?|Table|図|表)\s*[A-Z]?\d+", note, re.I):
                    found.add(_figure_key(match.group(0)))
        return found
    return None


def _contains_value(deck: str, value: str) -> bool:
    """value appears as a whole number: '3.17' does not match inside '13.17', '1000' not inside '10000'."""
    value = re.sub(r"\s+", "", normalize(value))
    head = r"(?<![\d.])" if value[:1].isdigit() else ""
    tail = r"(?!\d|\.\d)" if value[-1:].isdigit() else ""
    return re.search(head + re.escape(value) + tail, deck) is not None


def answer_key_check(texts: list[str], key: dict, figures: set | None) -> dict:
    # Drop spaces inside a line ("17 秒", "3. 17") but keep line, text-box and slide breaks, so that
    # separate values ("3.17" and a page number "2" below it) are never joined into "3.172".
    deck = "\n".join(re.sub(r"[ \t\u3000]+", "", line) for line in normalize("\n\n".join(texts)).splitlines())
    rows = []
    for item in key["numbers"]:
        hit = any(_contains_value(deck, a) for a in item["accept"])
        rows.append({"id": item["id"], "must_include": item["must_include"], "found": hit,
                     "statement": item["statement"]})
    must = [r for r in rows if r["must_include"]]
    figure_rows = [{"id": f["id"], "figure": f["figure"], "must_include": f["must_include"],
                    "shown": None if figures is None else _figure_key(f["figure"]) in figures}
                   for f in key.get("figures", [])]
    must_figures = [f for f in figure_rows if f["must_include"]]
    return {
        "status": key.get("status"),
        "numbers_found": sum(r["found"] for r in rows), "numbers_total": len(rows),
        "must_numbers_found": sum(r["found"] for r in must), "must_numbers_total": len(must),
        "must_figures_shown": None if figures is None else sum(f["shown"] for f in must_figures),
        "must_figures_total": len(must_figures),
        "missing_numbers": [r for r in rows if not r["found"]],
        "figures": figure_rows,
        "claims_to_judge": [{"id": c["id"], "must_include": c["must_include"], "statement": c["statement"],
                             "locator": c["locator"]} for c in key.get("claims", [])],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pptx", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--project")
    parser.add_argument("--answer-key", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    texts = slide_texts(args.pptx)
    result = {"numbers": number_check(texts, paper_numbers(args.pdf))}
    if args.db and args.project:
        result["spec"] = spec_checks(args.db, args.project)
    if args.answer_key:
        key = json.loads(args.answer_key.read_text())
        result["answer_key"] = answer_key_check(texts, key, shown_figures(texts, args.db, args.project))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    n = result["numbers"]
    print(f"numbers on slides: {n['numbers_on_slides']}  not found in paper: {n['not_found_in_paper']}"
          f"  found rate: {n['found_rate']}")
    for row in n["missing"]:
        print(f"  slide {row['slide']:>2}  {row['number']:<10} …{row['context']}…")
    if "spec" in result:
        for k, v in result["spec"].items():
            print(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    if "answer_key" in result:
        a = result["answer_key"]
        print(f"answer key ({a['status']}): numbers {a['numbers_found']}/{a['numbers_total']}, "
              f"must-include numbers {a['must_numbers_found']}/{a['must_numbers_total']}, "
              f"must-include figures/tables {a['must_figures_shown']}/{a['must_figures_total']}")
        for row in a["missing_numbers"]:
            print(f"  missing {row['id']}{' (must)' if row['must_include'] else ''}: {row['statement']}")
        if a["must_figures_shown"] is None:
            print("  figures/tables: unavailable without --db and --project (mentions are not evidence)")
        for row in a["figures"]:
            if row["shown"] is False:
                print(f"  not shown {row['id']} {row['figure']}{' (must)' if row['must_include'] else ''}")
        print(f"  claims to judge by hand: {len(a['claims_to_judge'])}")


if __name__ == "__main__":
    main()
