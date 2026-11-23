import importlib.util
import json
from pathlib import Path

SCRIPT = Path("scripts/eval_fidelity.py")
spec = importlib.util.spec_from_file_location("eval_fidelity", SCRIPT)
eval_fidelity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_fidelity)


def test_answer_key_is_well_formed():
    key = json.loads(Path("examples/eval/ddpm-answer-key.json").read_text())
    assert key["status"] == "draft_pending_owner_review"
    ids = [item["id"] for group in ("numbers", "claims", "figures") for item in key[group]]
    assert len(ids) == len(set(ids))
    assert all(item["accept"] and item["locator"] for item in key["numbers"])
    assert all(eval_fidelity._figure_key(item["figure"]) for item in key["figures"])


def test_answer_key_check_counts_numbers_and_figures():
    key = {"status": "draft", "numbers": [
        {"id": "N1", "must_include": True, "statement": "FID", "accept": ["3.17"]},
        {"id": "N2", "must_include": False, "statement": "steps", "accept": ["1000"]}],
        "claims": [{"id": "C1", "must_include": True, "statement": "s", "locator": "p.1"}],
        "figures": [{"id": "F1", "must_include": True, "figure": "Table 1"},
                    {"id": "F2", "must_include": False, "figure": "Fig. 2"}]}
    texts = ["FIDは 3. 17（Table 1 より）", "図2　生成の流れ"]
    result = eval_fidelity.answer_key_check(texts, key, eval_fidelity.shown_figures(texts, None, None))
    assert (result["must_numbers_found"], result["numbers_found"]) == (1, 1)
    assert [f["shown"] for f in result["figures"]] == [True, True]
    assert result["claims_to_judge"][0]["id"] == "C1"
