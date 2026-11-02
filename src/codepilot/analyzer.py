"""Safe, deterministic source inspection. Submitted code is parsed, never executed."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Finding:
    severity: str
    rule: str
    title: str
    detail: str
    line: int | None = None
    suggestion: str = ""


@dataclass(frozen=True)
class CodeFacts:
    language: str
    lines: int
    characters: int
    functions: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    parseable: bool = False


def inspect_python(code: str) -> tuple[CodeFacts, list[Finding]]:
    """Return basic Python structure and heuristic findings without running code."""
    line_count = len(code.splitlines())
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        finding = Finding(
            severity="error",
            rule="PY001",
            title="Python syntax error",
            detail=exc.msg,
            line=exc.lineno,
            suggestion="Fix the syntax at or just before this line, then run the file's test suite.",
        )
        return CodeFacts("Python", line_count, len(code), parseable=False), [finding]

    functions = tuple(
        node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    classes = tuple(node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.extend(alias.name for alias in node.names if alias.name != "*")

    facts = CodeFacts(
        language="Python",
        lines=line_count,
        characters=len(code),
        functions=functions,
        classes=classes,
        imports=tuple(dict.fromkeys(imports)),
        parseable=True,
    )
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = [*node.args.defaults, *(item for item in node.args.kw_defaults if item is not None)]
            for default in defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)) or (
                    isinstance(default, ast.Call)
                    and isinstance(default.func, ast.Name)
                    and default.func.id in {"list", "dict", "set"}
                    and not default.args
                    and not default.keywords
                ):
                    findings.append(
                        Finding(
                            "warning",
                            "PY101",
                            "Mutable default argument",
                            f"`{node.name}` uses a mutable object as a default; the same object is reused across calls.",
                            default.lineno,
                            "Use `None` as the default and create a fresh list/dict/set inside the function.",
                        )
                    )
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None:
                findings.append(
                    Finding(
                        "warning",
                        "PY102",
                        "Bare except clause",
                        "This catches every exception, including interrupts and process-exit signals.",
                        node.lineno,
                        "Catch the narrow exception types the code can recover from, and let unexpected errors surface.",
                    )
                )
            elif isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}:
                findings.append(
                    Finding(
                        "info",
                        "PY103",
                        "Broad exception handler",
                        f"Catching `{node.type.id}` can hide unrelated failures if they are swallowed.",
                        node.lineno,
                        "Consider catching specific exceptions and preserving useful error context.",
                    )
                )
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec"}:
                findings.append(
                    Finding(
                        "warning",
                        "PY104",
                        f"Dynamic `{node.func.id}` call",
                        "Dynamic source evaluation can turn untrusted input into executable code.",
                        node.lineno,
                        "Avoid evaluating untrusted strings; use a constrained parser or explicit dispatch instead.",
                    )
                )
        elif isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            if any(isinstance(part, ast.Constant) and part.value is None for part in operands) and any(
                isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops
            ):
                findings.append(
                    Finding(
                        "info",
                        "PY105",
                        "Identity comparison with None",
                        "Python style and semantics favor identity checks for the singleton `None`.",
                        node.lineno,
                        "Use `is None` or `is not None`.",
                    )
                )

    # Stable ordering helps the UI and makes tests/reviews reproducible.
    findings.sort(key=lambda item: (item.line or 0, item.rule))
    return facts, findings


def summarize(code: str, language: str, facts: CodeFacts | None = None) -> str:
    if language.lower() == "python":
        facts = facts or inspect_python(code)[0]
        if not facts.parseable:
            return (
                f"Python snippet, {facts.lines} lines. Parsing failed, so structure could not be summarized."
            )
        items: list[str] = []
        if facts.classes:
            items.append("classes: " + ", ".join(facts.classes))
        if facts.functions:
            items.append("functions: " + ", ".join(facts.functions))
        if facts.imports:
            items.append("imports: " + ", ".join(facts.imports))
        structure = "; ".join(items) if items else "no top-level classes or functions detected"
        return f"Python snippet with {facts.lines} lines ({facts.characters} characters); {structure}."
    lines = len(code.splitlines())
    return f"{language} snippet with {lines} lines ({len(code)} characters). Offline mode does not parse this language."


def offline_response(task: str, code: str, language: str, facts: CodeFacts, findings: list[Finding]) -> str:
    """Conservative task-specific result; no model is implied in offline mode."""
    summary = summarize(code, language, facts)
    if task == "summarize":
        return summary + " This structural summary does not infer behavior beyond the visible syntax."
    if task == "explain":
        if language.lower() == "python" and facts.parseable:
            return (
                summary
                + " For a precise behavioral explanation, inspect the function bodies and follow their call paths; "
                "the offline analyzer reports structure rather than claiming full semantic understanding."
            )
        return summary + " Add a configured model for a natural-language explanation; no code was executed."
    if task == "bugs":
        if findings:
            rendered = "\n".join(f"- {f.rule} {f.title}: {f.detail}" for f in findings)
            return "Heuristic findings (not a proof of defects):\n" + rendered
        return (
            "No issue was detected by the small offline rule set. This does not establish that the code is bug-free; "
            "exercise the relevant inputs and run project tests."
        )
    if task == "improve":
        if findings:
            actions = "\n".join(f"- {f.suggestion}" for f in findings if f.suggestion)
            return "Review these possible improvements first:\n" + actions
        return (
            "No rule-based improvement was triggered. Review naming, error handling, boundary cases, complexity, "
            "and project-specific style; a configured model can make context-aware suggestions."
        )
    if task == "tests":
        names = list(facts.functions)
        if language.lower() == "python" and facts.parseable and names:
            cases = "\n".join(
                f"def test_{name}_replace_with_behavioral_case():\n"
                f"    # TODO: choose representative inputs and the expected result for `{name}`.\n"
                f'    pytest.skip("replace this scaffold with a verified behavioral assertion")\n'
                for name in names[:8]
            )
            return (
                "Starter scaffold only — each test is intentionally skipped until you supply real inputs and expected "
                "behavior. It is not evidence that the functions pass tests.\n\n"
                "```python\nimport pytest\n\n"
                + cases
                + "```\n\nImport the functions from your package and replace each skipped placeholder with assertions."
            )
        return (
            "Offline mode cannot infer trustworthy expected values for this snippet. Create tests from documented "
            "contracts, including a normal case, boundary cases, and invalid inputs; a configured model can draft "
            "a more tailored scaffold for human review."
        )
    return "Unsupported task. Choose explain, bugs, improve, tests, or summarize."


def facts_to_dict(facts: CodeFacts) -> dict[str, object]:
    data = asdict(facts)
    data["functions"] = list(facts.functions)
    data["classes"] = list(facts.classes)
    data["imports"] = list(facts.imports)
    return data


def findings_to_dict(findings: list[Finding]) -> list[dict[str, object]]:
    return [asdict(item) for item in findings]
