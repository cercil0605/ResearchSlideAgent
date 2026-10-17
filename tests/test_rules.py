import hashlib
import re
from pathlib import Path

import pytest

from research_slide_agent import rules

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/research-slide-agent/skills/research-slides"


def test_context_contains_every_canonical_document_in_full():
    context = rules.authoring_context()
    assert context["required_documents"] == ["workflow", "professor", "presentation", "canonical"]
    assert [document["id"] for document in context["documents"]] == context["required_documents"]
    for document in context["documents"]:
        original = (SKILL / document["path"]).read_bytes()
        assert document["text"].encode("utf-8") == original
        assert document["sha256"] == hashlib.sha256(original).hexdigest()
    assert rules.authoring_context() == context
    assert len(context["rules_digest"]) == 64
    # The bootstrap's fallback must resolve the same four files after installation.
    links = re.findall(r"\]\((references/[^)]+)\)", (SKILL / "SKILL.md").read_text())
    assert set(links) == {document["path"] for document in context["documents"]}


def test_rule_changes_invalidate_digest_without_changing_another_copy(tmp_path, monkeypatch):
    for _, _, filename in rules.DOCUMENTS:
        (tmp_path / filename).write_bytes((SKILL / "references" / filename).read_bytes())
    monkeypatch.setattr(rules, "_rules_directory", lambda: tmp_path)
    before = rules.authoring_context()
    filename = tmp_path / "professor-guidelines.md"
    filename.write_text(filename.read_text() + "\n追加の制作規則\n")
    after = rules.authoring_context()
    assert before["rules_digest"] != after["rules_digest"]
    assert after["documents"][1]["text"].endswith("追加の制作規則\n")
    assert before["documents"][0] == after["documents"][0]


@pytest.mark.parametrize("failure", ["missing", "empty", "invalid_utf8"])
def test_unavailable_rules_fail_instead_of_returning_partial_context(tmp_path, monkeypatch, failure):
    for _, _, filename in rules.DOCUMENTS:
        (tmp_path / filename).write_text("complete rule text")
    target = tmp_path / "professor-guidelines.md"
    if failure == "missing":
        target.unlink()
    else:
        target.write_bytes(b"" if failure == "empty" else b"\xff")
    monkeypatch.setattr(rules, "_rules_directory", lambda: tmp_path)
    with pytest.raises(ValueError, match="AUTHORING_RULES_UNAVAILABLE"):
        rules.authoring_context()


def test_installed_package_uses_bundled_rules_without_checkout(tmp_path, monkeypatch):
    bundled = tmp_path / "authoring_rules"
    bundled.mkdir()
    monkeypatch.setattr(rules, "files", lambda _: tmp_path)
    assert rules._rules_directory() == bundled


def test_server_instructions_fit_the_initial_guidance_budget():
    assert len(rules.SERVER_INSTRUCTIONS) <= 512
    assert "get_authoring_context" in rules.SERVER_INSTRUCTIONS
    assert "get_template_info" in rules.SERVER_INSTRUCTIONS
