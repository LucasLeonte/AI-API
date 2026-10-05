"""Structured output schemas for the /api/v1/analyze endpoint."""

from typing import Optional

from pydantic import BaseModel, Field


class RemediatedPatch(BaseModel):
    """An optional code or YAML patch to remediate the detected failure."""

    file_path: Optional[str] = Field(
        default=None,
        description=(
            "Suggested target file to edit, e.g. '.github/workflows/ci.yml' "
            "or 'Dockerfile'."
        ),
        examples=[".github/workflows/ci.yml"],
    )
    diff_snippet: str = Field(
        ...,
        description="Actionable unified diff or replacement code block.",
        examples=[
            "- uses: actions/checkout@v2\n+ uses: actions/checkout@v4\n"
        ],
    )


class FailureAnalysis(BaseModel):
    """
    Structured diagnosis produced by the LLM for a CI/CD failure log.

    This schema is passed verbatim to the LLM as a JSON mode / response-format
    constraint so that every field is guaranteed to be present and correctly typed.
    """

    error_category: str = Field(
        ...,
        description=(
            "High-level error category, e.g. 'MissingDependency', "
            "'PermissionDenied', 'SyntaxError', 'NetworkTimeout'."
        ),
        examples=["MissingDependency"],
    )
    summary: str = Field(
        ...,
        description="Concise 1–2 sentence root-cause explanation.",
        examples=[
            "The npm install step failed because package.json does not exist "
            "at the expected working directory."
        ],
    )
    failing_command_or_step: Optional[str] = Field(
        default=None,
        description=(
            "The specific CLI command or pipeline step that produced the "
            "non-zero exit code."
        ),
        examples=["npm install"],
    )
    root_cause_breakdown: list[str] = Field(
        ...,
        description="Ordered bullet points detailing step-by-step why the runner failed.",
        examples=[
            [
                "The workflow's `working-directory` is set to the repo root.",
                "package.json was not committed to the repository.",
                "npm cannot locate the manifest and exits with ENOENT.",
            ]
        ],
    )
    suggested_fix: str = Field(
        ...,
        description=(
            "Clear, actionable instructions on how the developer resolves this failure."
        ),
        examples=[
            "Add a package.json to the root of the repository by running "
            "`npm init -y` locally and committing the result."
        ],
    )
    patch: Optional[RemediatedPatch] = Field(
        default=None,
        description="Optional code or YAML patch if a file change can directly fix the issue.",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Estimated diagnosis confidence between 0.0 (uncertain) and 1.0 (certain).",
        examples=[0.92],
    )


class AnalyzeResponse(BaseModel):
    """Top-level envelope returned by POST /api/v1/analyze."""

    status: str = Field(default="success", description="Always 'success' on HTTP 200.")
    analysis: FailureAnalysis
    execution_time_ms: int = Field(
        ...,
        description="End-to-end request processing time in milliseconds.",
        examples=[1340],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "execution_time_ms": 1340,
                    "analysis": {
                        "error_category": "MissingDependency",
                        "summary": (
                            "npm install failed because package.json is absent "
                            "from the runner workspace."
                        ),
                        "failing_command_or_step": "npm install",
                        "root_cause_breakdown": [
                            "Workflow working-directory defaults to repo root.",
                            "package.json was never committed.",
                            "npm exits with ENOENT -2.",
                        ],
                        "suggested_fix": (
                            "Run `npm init -y` locally and commit package.json."
                        ),
                        "patch": {
                            "file_path": ".github/workflows/ci.yml",
                            "diff_snippet": (
                                "-       run: npm install\n"
                                "+       run: |\n"
                                "+         [ -f package.json ] || npm init -y\n"
                                "+         npm install\n"
                            ),
                        },
                        "confidence_score": 0.92,
                    },
                }
            ]
        }
    }
