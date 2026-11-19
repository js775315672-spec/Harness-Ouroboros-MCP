"""Select verified lessons from the Hydra evidence index."""
import argparse
import json
from pathlib import Path
import re


def select(document, query):
    if document.get("schema") != "hydra-verified-history-v1":
        raise ValueError("unknown history schema")
    result = []
    seen = set()
    used_runs = set()
    for row in document["cycles"]:
        if (type(row["cycle"]) is not int or row["cycle"] in seen
                or not re.fullmatch(r"[0-9a-f]{40}", row["candidate"])
                or type(row["independent"]["normal_passed"]) is not int
                or row["independent"]["normal_passed"] < 1
                or type(row["operational_tests"]) is not int or row["operational_tests"] < 1
                or any(type(row[k]) is not int or row[k] < 1 for k in ("model", "operation"))):
            raise ValueError("invalid cycle evidence")
        if row["model"] in used_runs or row["operation"] in used_runs or row["model"] == row["operation"]:
            raise ValueError("cycle run already credited")
        used_runs.update((row["model"], row["operation"]))
        seen.add(row["cycle"])
        if query.casefold() not in (row["problem"] + " " + row["change"] + " " + " ".join(row["lessons"])).casefold():
            continue
        result.append({"cycle": row["cycle"], "lessons": row["lessons"],
                       "independent_run": row["model"], "operational_run": row["operation"],
                       "candidate": row["candidate"]})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=Path("hydra/memory/history.json"))
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    print(json.dumps(select(json.loads(args.history.read_bytes()), args.query), ensure_ascii=False))
