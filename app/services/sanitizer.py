"""
Log sanitizer — redacts common secret patterns from CI/CD build logs
before they are forwarded to a third-party LLM provider.

All transformations are pure string operations (no side-effects) so
this module is trivially unit-testable.
"""

import re

from app.config import settings

# ── Compiled redaction patterns ────────────────────────────────────────────────
# Each tuple: (human_label, compiled_regex, replacement_string)
_REDACTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # GitHub Personal Access Tokens  (classic: ghp_, fine-grained: github_pat_)
    (
        "github_token",
        re.compile(r"gh[ps]_[a-zA-Z0-9]{36}", re.ASCII),
        "[REDACTED_SECRET]",
    ),
    (
        "github_fine_grained_token",
        re.compile(r"github_pat_[a-zA-Z0-9_]{82}", re.ASCII),
        "[REDACTED_SECRET]",
    ),
    # AWS Access Key IDs
    (
        "aws_access_key",
        re.compile(r"AKIA[0-9A-Z]{16}", re.ASCII),
        "[REDACTED_SECRET]",
    ),
    # AWS Secret Access Keys (40-char base64-ish string typically following the label)
    (
        "aws_secret_key",
        re.compile(
            r"(?i)aws[_\-]?secret[_\-]?access[_\-]?key\s*[=:]\s*\S+",
            re.ASCII,
        ),
        "AWS_SECRET_ACCESS_KEY=[REDACTED_SECRET]",
    ),
    # PEM-encoded private keys (RSA, OPENSSH, EC, PGP, generic)
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN\s+(?:RSA |OPENSSH |EC |PGP |DSA )?PRIVATE KEY-----"
            r"[\s\S]*?"
            r"-----END\s+(?:RSA |OPENSSH |EC |PGP |DSA )?PRIVATE KEY-----",
            re.MULTILINE,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Bearer tokens in Authorization headers / curl commands
    (
        "bearer_token",
        re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.ASCII),
        "Bearer [REDACTED_SECRET]",
    ),
    # Generic JWT  (three base64url segments separated by dots)
    (
        "jwt",
        re.compile(
            r"eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+",
            re.ASCII,
        ),
        "[REDACTED_JWT]",
    ),
    # Environment variable assignments for sensitive keys
    # Matches: PASSWORD=..., SECRET=..., TOKEN=..., API_KEY=..., etc.
    (
        "env_secret",
        re.compile(
            r"(?i)(?:^|(?<=\s)|(?<=,))(?:[\w]*(?:PASSWORD|SECRET|TOKEN|API[_-]?KEY|PRIVATE[_-]?KEY)[\w]*)"
            r"\s*=\s*\S+",
            re.MULTILINE,
        ),
        "[REDACTED_ENV_SECRET]",
    ),
]


def sanitize_log(raw_log: str) -> str:
    """
    Redact known secret patterns from *raw_log* and truncate if it exceeds
    ``settings.max_log_size_chars``.

    Steps performed (in order):
    1. Apply every redaction regex from ``_REDACTION_PATTERNS``.
    2. Truncate to the *tail* of the log (most recent output is most relevant
       for diagnosing a failure), prepending a truncation notice if needed.

    Parameters
    ----------
    raw_log:
        The raw CI/CD build or test log string submitted by the caller.

    Returns
    -------
    str
        Sanitised (and possibly truncated) log string, safe to forward to an
        external LLM provider.
    """
    sanitized = raw_log

    # ── Step 1: Apply all redaction patterns ──────────────────────────────────
    for _label, pattern, replacement in _REDACTION_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    # ── Step 2: Truncate to tail if oversized ─────────────────────────────────
    max_chars = settings.max_log_size_chars
    if len(sanitized) > max_chars:
        dropped = len(sanitized) - max_chars
        truncation_notice = (
            f"[... Truncated first {dropped} characters — showing last "
            f"{max_chars} characters of the log ...]\n"
        )
        sanitized = truncation_notice + sanitized[-max_chars:]

    return sanitized
