from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse
from httpx import HTTPError
from pydantic import BaseModel, Field

from codepilot.analyzer import CodeFacts, facts_to_dict, findings_to_dict, inspect_python, offline_response
from codepilot.model import ask_model, model_is_configured, model_name

MAX_CODE_CHARS = 24_000
MAX_CONTEXT_CHARS = 3_000
STATIC = Path(__file__).parent / "static"

app = FastAPI(
    title="CodePilot",
    description="Local-first coding assistant with safe Python heuristics and optional model review.",
    version="1.0.0",
)


class AnalyzeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)
    task: Literal["explain", "bugs", "improve", "tests", "summarize"] = "explain"
    language: str = Field(default="Python", min_length=1, max_length=40)
    context: str = Field(default="", max_length=MAX_CONTEXT_CHARS)
    use_model: bool = False


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "model_available": model_is_configured(),
        "model": model_name() if model_is_configured() else None,
    }


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest) -> dict[str, object]:
    task = request.task
    python_mode = request.language.strip().lower() == "python"
    if python_mode:
        facts, findings = inspect_python(request.code)
    else:
        # Other languages are accepted for optional model review; no language parser is bundled.
        facts = CodeFacts(
            request.language.strip(), len(request.code.splitlines()), len(request.code), parseable=False
        )
        findings = []
    local_result = offline_response(
        task, request.code, "Python" if python_mode else request.language, facts, findings
    )
    result = local_result
    mode = "offline heuristic"
    warning = (
        "Offline output is limited; it is not a substitute for running tests, linters, or security review."
    )
    if request.use_model:
        if not model_is_configured():
            warning = "No provider key is configured. Returned the offline result; configure a compatible provider to enable model review."
        else:
            try:
                result = await ask_model(task, request.code, request.language.strip(), request.context)
                mode = "configured model"
                warning = "Model output may be incorrect or incomplete. Review every suggestion and run appropriate tests before using it."
            except (RuntimeError, OSError, TimeoutError, HTTPError):
                # Provider errors never cause the code text, credentials, or raw provider response to be echoed.
                warning = "Model request failed. Returned the offline result instead."
    return {
        "task": task,
        "language": request.language.strip(),
        "result": result,
        "mode": mode,
        "warning": warning,
        "facts": facts_to_dict(facts),
        "findings": findings_to_dict(findings),
        "code_was_executed": False,
    }
