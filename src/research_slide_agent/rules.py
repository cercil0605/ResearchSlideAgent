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
    "Before planning, call get_authoring_context and read all required documents in full, then get_template_info. "
    "Use schema 1.2: separate section from prototype, explain an early concrete example, preserve "
    "contributions, evaluation conditions and source caveats. Ground claims in the paper; never truncate. "
    "Self-check before save_slide_spec, inspect feedback, then get_slide_preview after generation and fix "
    "readability before delivery. Autonomous unless discussion is requested; preserve agreed scope."
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
