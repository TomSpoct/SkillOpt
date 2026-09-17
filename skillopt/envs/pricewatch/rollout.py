"""PriceWatch rollout: run the target model as a price-watch analyst.

Each item is one artwork. The target model receives the current skill
document as the system prompt plus a compact case sheet (work, Shopify
price, market evidence summary, % gap). It must return a JSON verdict:
one of FLAG / WATCH / NO FLAG, plus a one-line rationale.

Scoring (against the human-reviewed ground truth):
  * hard: 1 if the predicted verdict equals the expected verdict.
  * soft: exact = 1.0; FLAG vs WATCH (adjacent severity) = 0.5; anything
    else (incl. NO FLAG vs FLAG) = 0.0.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from skillopt.model import chat_target

VERDICTS = ("FLAG", "WATCH", "NO FLAG")


def _extract_verdict(text: str) -> str:
    """Pull a verdict out of a model response, tolerating extra prose."""
    if not text:
        return ""
    # Try strict JSON parse first (some models wrap in ```json fences)
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    for key in ("verdict", "Verdict", "VERDICT"):
        m = re.search(rf'"{key}"\s*:\s*"([A-Z_ ]+)"', t)
        if m:
            cand = m.group(1).upper().strip()
            if cand in VERDICTS:
                return cand
    # Fallback: first verdict token anywhere in the text
    for v in VERDICTS:
        if re.search(rf"\b{v}\b", t):
            return v
    return ""


def _score(predicted: str, expected: str) -> tuple[int, float]:
    if not predicted:
        return 0, 0.0
    if predicted == expected:
        return 1, 1.0
    if {predicted, expected} <= {"FLAG", "WATCH"}:
        return 0, 0.5  # adjacent severity — direction right, intensity off
    return 0, 0.0


def _case_sheet(item: dict) -> str:
    parts = [
        f"Artwork: {item.get('title', item.get('sku', ''))}  (SKU {item.get('sku', '')})",
        f"Shopify price: {item.get('shopify_price', 'n/a')}",
    ]
    if item.get("difference_pct") not in (None, "", "n/a"):
        parts.append(f"Market gap: {item.get('difference_pct')}% vs Shopify price")
    if item.get("market_eur") not in (None, "", "n/a"):
        parts.append(f"Market median: EUR {item.get('market_eur')}")
    if item.get("market_evidence"):
        parts.append(f"Market evidence: {item.get('market_evidence')}")
    return "\n".join(parts)


def _rollout_one(item: dict, skill_content: str, *, prediction_dir: Path,
                 max_completion_tokens: int) -> dict:
    system = skill_content
    user = (
        "You are running a price-watch check for an art print retailer. "
        "Use the skill instructions below. For the given artwork, decide the "
        "verdict:\n"
        "- FLAG: the market gap is material (roughly >25% below price) and the "
        "comparables are credible.\n"
        "- WATCH: there is a meaningful gap or ambiguity that needs one more "
        "check before flagging.\n"
        "- NO FLAG: the price is within a reasonable band of the market.\n\n"
        "Case:\n"
        f"{_case_sheet(item)}\n\n"
        "Reply with ONLY a JSON object of the form "
        '{"verdict": "FLAG|WATCH|NO FLAG", "rationale": "<one sentence>"}.'
    )
    prediction, _usage = chat_target(
        system=system,
        user=user,
        max_completion_tokens=max_completion_tokens,
    )

    predicted = _extract_verdict(prediction)
    expected = item.get("expected_verdict", "")
    hard, soft = _score(predicted, expected)

    # Persist the trajectory for the shared reflection stage.
    task_dir = prediction_dir / str(item["id"])
    task_dir.mkdir(parents=True, exist_ok=True)
    conversation = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "assistant", "content": prediction or ""},
    ]
    (task_dir / "conversation.json").write_text(
        json.dumps(conversation, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "id": str(item["id"]),
        "hard": hard,
        "soft": soft,
        "predicted_answer": prediction or "",
        "predicted_verdict": predicted,
        "expected_verdict": expected,
        "task_description": item.get("title", item.get("sku", "")),
        "question": user,
        "task_type": item.get("task_type", "verdict"),
        "target_system_prompt": system,
        "target_user_prompt": user,
        "n_turns": 1,
    }


def run_batch(*, items: list[dict], skill_content: str, out_root: str,
              workers: int = 4, max_completion_tokens: int = 4096) -> list[dict]:
    os.makedirs(out_root, exist_ok=True)
    prediction_dir = Path(out_root, "predictions")
    results = [
        _rollout_one(item, skill_content,
                     prediction_dir=prediction_dir,
                     max_completion_tokens=max_completion_tokens)
        for item in items
    ]
    Path(out_root, "rollouts.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return results
