import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evidence_matching import build_task_catalog, confirmation_tier, match_evidence_all, normalize_title
from task_records import task_records


def _line(text):
    return {
        "raw_line": text,
        "title": text,
        "normalized_title": normalize_title(text),
        "exact_identifiers": set(),
        "fallback_identifiers": set(),
    }


def _matches(content, hint):
    records = task_records(content, fmt="obsidian")
    catalog = build_task_catalog(records)
    return match_evidence_all(_line(hint), catalog)["matches"]


def test_confirmation_tier_single_multi_none_are_deterministic():
    content = """# Work

## 🔴 Q1
- [ ] **JAMS quarterly launch** task_id::tsk_jams area:: Ops
- [ ] **JAMS followup email** task_id::tsk_jams2 area:: Ops
- [ ] **Lifetime outreach** task_id::tsk_life area:: Sales
"""

    single = confirmation_tier(_matches(content, "JAMS quarterly"))
    multi = confirmation_tier(_matches(content, "the JAMS thing"))
    none = confirmation_tier(_matches(content, "reticulate splines"))

    assert single["tier"] == "single"
    assert single["candidates"][0]["task_id"] == "tsk_jams"
    assert multi["tier"] == "multi"
    assert [candidate["task_id"] for candidate in multi["candidates"]] == ["tsk_jams", "tsk_jams2"]
    assert none == {"tier": "none", "candidates": []}


def _scored(task_id, title, score):
    """A synthetic ranked match, for exercising confirmation_tier's threshold boundaries directly."""
    return {"canonical_task": {"task_id": task_id, "title": title}, "score": score, "match_type": "synthetic"}


def test_confirmation_tier_strong_single_with_weak_runner_up_stays_single():
    # One dominant confident match (>= 0.88) plus a runner-up ABOVE the candidate floor (0.80) but
    # BELOW confident is a clean single-confirm, NOT a downgrade to multi. This is the exact case the
    # dead-condition bug got wrong.
    tier = confirmation_tier([_scored("tsk_a", "Alpha", 0.95), _scored("tsk_b", "Beta", 0.85)])
    assert tier["tier"] == "single"
    assert [c["task_id"] for c in tier["candidates"]] == ["tsk_a"]


def test_confirmation_tier_two_confident_matches_are_multi():
    # Two matches at/above the confident threshold genuinely compete -> disambiguation.
    tier = confirmation_tier([_scored("tsk_a", "Alpha", 0.95), _scored("tsk_b", "Beta", 0.90)])
    assert tier["tier"] == "multi"
    assert [c["task_id"] for c in tier["candidates"]] == ["tsk_a", "tsk_b"]


def test_confirmation_tier_lone_weak_candidate_is_none():
    # A single match above the candidate floor but below confident is not strong enough to name one
    # task; it falls to none (the plugin nudges to /tasks rather than posting a confident confirm).
    assert confirmation_tier([_scored("tsk_a", "Alpha", 0.85)]) == {"tier": "none", "candidates": []}


def test_match_evidence_all_token_overlap_keeps_stable_order_for_fixed_board():
    content = """# Work

## 🔴 Q1
- [ ] **JAMS partner review** task_id::tsk_b area:: Ops
- [ ] **JAMS archive cleanup** task_id::tsk_a area:: Ops
"""

    first = _matches(content, "JAMS")
    second = _matches(content, "JAMS")

    assert [match["matched_task_id"] for match in first[:2]] == ["tsk_a", "tsk_b"]
    assert [match["matched_task_id"] for match in second[:2]] == ["tsk_a", "tsk_b"]
    assert all("token-overlap" in match["match_types"] for match in first[:2])
