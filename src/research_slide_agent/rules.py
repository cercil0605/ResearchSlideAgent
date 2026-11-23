"""Serve the plugin's canonical authoring references without maintaining another copy."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

RULES_RESOURCE_URI = "research-slides://authoring-context"
SERVER_INSTRUCTIONS = (
    "First read every part of get_authoring_context in full, then get_template_info. Read PDF papers "
    "fully with read_paper; crop figures with crop_pdf_region(figure=...). Map required content to "
    "schema 1.3 body slots; preserve contributions, conditions and caveats; ground claims in the paper; "
    "never truncate. Save once, then send changes with patch_slides. enqueue_generation waits and returns "
    "page overviews: fix readability before delivery. Autonomous unless discussion is requested."
)

DOCUMENTS = (
    ("workflow", "制作ワークフロー", "authoring-workflow.md"),
    ("professor", "教授の明示ルール", "professor-guidelines.md"),
    ("presentation", "過去資料から得た説明規則", "presentation-guidelines.md"),
    ("canonical", "正本の入力・検証手順", "canonical-skeleton.md"),
)


def _rules_directory() -> Traversable:
    # Wheels contain the exact reference files via Hatch force-include. An editable
    # source checkout reads those same canonical files directly, independent of cwd.
    bundled = files("research_slide_agent").joinpath("authoring_rules")
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parents[2] / (
        "plugins/research-slide-agent/skills/research-slides/references"
    )


def authoring_context() -> dict[str, Any]:
    directory = _rules_directory()
    documents = []
    for document_id, title, filename in DOCUMENTS:
        try:
            data = directory.joinpath(filename).read_bytes()
            text = data.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError("AUTHORING_RULES_UNAVAILABLE: reinstall the complete rules package") from exc
        if not text.strip():
            raise ValueError("AUTHORING_RULES_UNAVAILABLE: required document is empty")
        documents.append({
            "id": document_id,
            "title": title,
            "path": "references/" + filename,
            "sha256": hashlib.sha256(data).hexdigest(),
            "text": text,
        })
    fingerprints = {document["id"]: document["sha256"] for document in documents}
    digest = hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest()
    return {
        "schema_version": "1.0",
        "rules_digest": digest,
        "required_documents": [document_id for document_id, _, _ in DOCUMENTS],
        "documents": documents,
    }
