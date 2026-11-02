# Smoke evaluation notes

`scripts/evaluate.py` applies the local analyzer to four hand-authored snippets and verifies that each fixture's intentionally included pattern triggers at least one expected rule. It is a regression smoke check, not an independently labeled code corpus. The fixtures were authored to exercise rules and cannot estimate real-world precision, recall, security coverage, or usefulness. No benchmark or model-quality claim is made.
