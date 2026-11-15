"""GBNF grammar builder: constrain Qwen's *syntax*, leave the *semantics* to the model.

llama.cpp can restrict token sampling to a grammar. The grammar below only fixes the
shape '"\\xHH" in log or "\\xHH" in log'; WHICH bytes appear is still the model's choice
(optionally limited to an allowed alphabet). This removes raw-NUL/ESC emission, markdown
fences, prose and name-vs-literal confusion at decode time instead of after the fact.
"""
import re

_HEX = re.compile(r"^[0-9a-f]{2}$")


def _gbnf_literal(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_in_log_grammar(allowed_hex=("00", "1b"), min_clauses=2, max_clauses=2,
                         variable="log"):
    """Return GBNF text for: "\xHH" in <variable> (or "\xHH" in <variable>)*"""
    hexes = tuple(allowed_hex)
    if not hexes or not all(isinstance(h, str) and _HEX.match(h) for h in hexes):
        raise ValueError("allowed_hex must be lowercase two-digit hex strings")
    if not (1 <= min_clauses <= max_clauses <= 8):
        raise ValueError("clause bounds must satisfy 1 <= min <= max <= 8")
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", variable):
        raise ValueError("invalid variable name")
    alternatives = " | ".join(_gbnf_literal("\\x" + h) for h in hexes)
    clause = _gbnf_literal('"') + " byte " + _gbnf_literal('" in ' + variable)
    # first min_clauses are mandatory; the rest are optional tail repetitions
    root = "clause" + "".join(
        (" " + _gbnf_literal(" or ") + " clause") if i < min_clauses - 1
        else (" (" + _gbnf_literal(" or ") + " clause)?")
        for i in range(max_clauses - 1))
    return "root ::= %s\nclause ::= %s\nbyte ::= %s\n" % (root, clause, alternatives)


def python_validator(allowed_hex=("00", "1b"), min_clauses=2, max_clauses=2,
                     variable="log"):
    """Regex mirroring the grammar, so the shape is testable without llama.cpp."""
    alt = "|".join(re.escape("\\x" + h) for h in allowed_hex)
    clause = r'"(?:%s)" in %s' % (alt, re.escape(variable))
    pattern = "^%s(?: or %s){%d,%d}$" % (clause, clause, min_clauses - 1, max_clauses - 1)
    return re.compile(pattern)
