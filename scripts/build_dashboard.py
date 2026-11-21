#!/usr/bin/env python3
"""Safely update only the README dashboard region; no ledger means UNKNOWN."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from evolution_core.dashboard import render_dashboard, replace_region

parser = argparse.ArgumentParser()
parser.add_argument("--readme", default="README.md")
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
path = Path(args.readme)
old = path.read_text(encoding="utf-8")
new = replace_region(old, render_dashboard())
if args.check:
    if new != old:
        raise SystemExit("dashboard out of date")
else:
    path.write_text(new, encoding="utf-8")
