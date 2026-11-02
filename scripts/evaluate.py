from __future__ import annotations

import json
from pathlib import Path

from codepilot.analyzer import inspect_python

CASES = {
    "mutable_default": ("def f(value=[]):\n    return value\n", "PY101"),
    "bare_except": ("try:\n    risky()\nexcept:\n    pass\n", "PY102"),
    "dynamic_eval": ("answer = eval(user_input)\n", "PY104"),
    "none_equality": ("if value == None:\n    pass\n", "PY105"),
    "syntax_error": ("def broken(:\n    pass\n", "PY001"),
}


def main() -> None:
    results = []
    for name, (code, expected_rule) in CASES.items():
        _, findings = inspect_python(code)
        rules = sorted({finding.rule for finding in findings})
        results.append(
            {
                "case": name,
                "expected_rule": expected_rule,
                "matched": expected_rule in rules,
                "observed_rules": rules,
            }
        )
    report = {
        "type": "synthetic regression smoke test; not a benchmark",
        "cases": len(results),
        "expected_rule_matches": sum(bool(row["matched"]) for row in results),
        "results": results,
        "limitations": "Hand-authored cases demonstrate only that the coded rules trigger on these examples; no real-world precision, recall, safety, or usefulness is estimated.",
    }
    path = Path("reports/synthetic_rule_smoke.json")
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not all(row["matched"] for row in results):
        raise SystemExit("One or more expected rule triggers failed.")


if __name__ == "__main__":
    main()
