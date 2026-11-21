"""Read-only dashboard: absent evidence is UNKNOWN, not success."""
BEGIN = "<!-- OFC-DASHBOARD-BEGIN -->"
END = "<!-- OFC-DASHBOARD-END -->"

def render_dashboard():
    return "\n".join((
        "## OFC independent agent dashboard (P0)",
        "",
        "| Metric | Evidence-based status |",
        "| --- | --- |",
        "| Real model execution | UNKNOWN |",
        "| Independent improvement | UNKNOWN |",
        "| Improvement throughput | NOT_MEASURED |",
        "| Comparable speed trend | NOT_MEASURED |",
        "| Generalization | NOT_VERIFIED |",
        "| Most recent blocker | P1 real model run + protected independent evaluation not yet connected |",
        "",
        "Registry and contract unit tests are **not** model improvements.",
    ))

def replace_region(readme: str, generated: str) -> str:
    if readme.count(BEGIN) != 1 or readme.count(END) != 1:
        raise ValueError("missing or ambiguous dashboard markers")
    before, tail = readme.split(BEGIN, 1)
    _old, after = tail.split(END, 1)
    return before + BEGIN + "\n" + generated.rstrip() + "\n" + END + after
