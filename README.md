# Harness-Ouroboros-MCP

Hydra runs approved tasks through GitHub Actions. Its next-task workflow reads the last 12 completed standing runs on main and writes a `hydra-next-task.json` artifact. A newer successful job resolves an earlier failure with the same name. An unresolved admission failure takes priority over worker failures.

When the selector finds no unresolved failure in that window, it checks the [Cycle 01 dispatch preflight](docs/evolution/cycle-01-dispatch-preflight.json). A blocked, undispatched cycle adds a `next_review` field with the evidence needed to proceed. This field is advisory. The [ORIL ledger and evaluation contract](docs/evolution/README.md) describes how to assess a candidate before adopting it.

Run the offline selector tests from the repository root with `python -B -m unittest discover -s tests -v`.
