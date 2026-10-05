"""Input validation schemas for the /api/v1/analyze endpoint."""

from enum import Enum

from pydantic import BaseModel, Field


class CIEnvironment(str, Enum):
    """Supported CI/CD runner contexts for contextual log analysis."""

    GITHUB_ACTIONS = "github-actions"
    GITLAB_CI = "gitlab-ci"
    DOCKER_BUILD = "docker-build"
    GENERIC = "generic"


class AnalyzeRequest(BaseModel):
    """
    Payload accepted by POST /api/v1/analyze.

    The `log_text` field is the raw CI/CD build or test failure log.
    It is sanitised server-side before being forwarded to the LLM.
    """

    ci_environment: CIEnvironment = Field(
        default=CIEnvironment.GENERIC,
        description="CI/CD runner context — helps the LLM tailor its analysis.",
        examples=["github-actions"],
    )
    log_text: str = Field(
        ...,
        min_length=10,
        max_length=50_000,
        description="Raw error log or build failure snippet (10 – 50 000 characters).",
        examples=[
            "Run npm install\nnpm ERR! code ENOENT\nnpm ERR! syscall open\n"
            "npm ERR! path /home/runner/work/app/package.json\n"
            "npm ERR! errno -2\nnpm ERR! enoent ENOENT: no such file or directory, "
            "open '/home/runner/work/app/package.json'\nError: Process completed with exit code 1."
        ],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ci_environment": "github-actions",
                    "log_text": (
                        "Run npm install\n"
                        "npm ERR! code ENOENT\n"
                        "npm ERR! path /home/runner/work/app/package.json\n"
                        "Error: Process completed with exit code 1."
                    ),
                }
            ]
        }
    }
