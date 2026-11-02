# Architecture

The browser submits one bounded request to the FastAPI service. Pydantic validates task, language, code, and optional context sizes. Python code is parsed with `ast.parse` and inspected using read-only tree walks; no `exec`, `eval`, imports, subprocesses, or package installation are performed on submitted source. Findings and a transparent offline task response are returned by default. A user can separately select model mode; only then, and only if configured, is code/context sent to the configured OpenAI-compatible chat endpoint.

The model call is a best-effort review path, not a sandbox or security boundary. Provider output is not executed or applied to files. The service has no persistence layer and intentionally does not log request bodies. Infrastructure and configured providers can retain their own request data.

See [architecture.mmd](architecture.mmd) for the flow diagram.
