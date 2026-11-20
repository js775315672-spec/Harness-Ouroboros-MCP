"""ORIL cycle trend comparison. Observational only; never a promotion gate."""
import argparse
import json
import math
from pathlib import Path

FIELDS = ("total_seconds", "model_seconds", "verification_seconds", "followup_seconds",
          "queue_seconds", "accepted_improvements", "retries", "failures", "regressions", "rollbacks")
DIRECTIONS = {"total_seconds": -1, "model_seconds": -1, "verification_seconds": -1,
              "followup_seconds": -1, "queue_seconds": -1, "accepted_improvements": 1,
              "retries": -1, "failures": -1, "regressions": -1, "rollbacks": -1}


def valid_nonnegative(value):
    """Reject booleans, nonfinite values and unrepresentably large integers."""
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def finite_median(values):
    """Median of nonnegative finite samples without overflow in even-size averaging."""
    ordered = sorted(values)
    size = len(ordered)
    if size % 2:
        return ordered[size // 2]
    lower, upper = ordered[size // 2 - 1], ordered[size // 2]
    # (lower + upper) / 2 can overflow for two finite large floats.
    return lower + (upper - lower) / 2


def compare(records, current_id, window=12):
    """Compare only matching task_type and difficulty; missing data is not zero."""
    if not isinstance(records, list) or not 5 <= window <= 12:
        raise ValueError("invalid records or window")
    ids = [r.get("cycle_id") for r in records if isinstance(r, dict)]
    if len(ids) != len(records) or len(set(ids)) != len(ids):
        raise ValueError("invalid or duplicate cycle_id")
    current = next((r for r in records if r["cycle_id"] == current_id), None)
    if current is None:
        raise ValueError("current cycle missing")
    for field in ("task_type", "difficulty"):
        if not current.get(field):
            raise ValueError("missing " + field)
    idx = records.index(current)
    history = [r for r in records[:idx] if
               r.get("task_type") == current["task_type"] and
               r.get("difficulty") == current["difficulty"]][-window:]
    result = {"cycle_id": current_id, "comparison_n": len(history), "metrics": {}}
    for field in FIELDS:
        vals = [r[field] for r in history if valid_nonnegative(r.get(field))]
        val = current.get(field)
        valid_current = valid_nonnegative(val)
        entry = {"n": len(vals), "previous_median": None, "current": val if valid_current else None, "change_pct": None,
                 "verdict": "판단불가"}
        if valid_current and len(vals) >= 3:
            median = finite_median(vals)
            entry["previous_median"] = median
            if median > 0:
                change = (val - median) / median * 100
                if math.isfinite(change):
                    entry["change_pct"] = round(change, 2)
                    direction = DIRECTIONS[field]
                    entry["verdict"] = ("유지" if abs(change) < 1 else
                                        "향상" if change * direction > 0 else "악화")
            elif val == 0:
                entry["change_pct"] = 0
                entry["verdict"] = "유지"
        result["metrics"][field] = entry
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("records", type=Path)
    p.add_argument("--cycle-id", required=True)
    p.add_argument("--window", type=int, default=12)
    args = p.parse_args()
    result = compare(json.loads(args.records.read_text(encoding="utf-8")), args.cycle_id, args.window)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
