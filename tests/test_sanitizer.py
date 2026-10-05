"""
Unit tests for app/services/sanitizer.py

Verifies that all secret patterns are redacted correctly and that
oversized logs are tail-truncated with the expected notice.
"""

from unittest.mock import patch

from app.services.sanitizer import sanitize_log

# ── Helpers ────────────────────────────────────────────────────────────────────


def _sanitize(text: str, max_chars: int = 50_000) -> str:
    """Call sanitize_log with an overridden max_log_size_chars value."""
    with patch("app.services.sanitizer.settings") as mock_settings:
        mock_settings.max_log_size_chars = max_chars
        return sanitize_log(text)


# ── GitHub Personal Access Token ──────────────────────────────────────────────

class TestGitHubTokenRedaction:
    def test_classic_ghp_token_is_redacted(self) -> None:
        log = "Cloning with token ghp_" + "A" * 36
        result = _sanitize(log)
        assert "ghp_" not in result
        assert "[REDACTED_SECRET]" in result

    def test_classic_ghs_token_is_redacted(self) -> None:
        log = "Auth header: ghs_" + "B" * 36
        result = _sanitize(log)
        assert "ghs_" not in result
        assert "[REDACTED_SECRET]" in result

    def test_normal_text_is_not_redacted(self) -> None:
        log = "Build succeeded. No secrets here."
        result = _sanitize(log)
        assert result == log


# ── AWS Access Key ID ──────────────────────────────────────────────────────────

class TestAWSKeyRedaction:
    def test_aws_access_key_id_is_redacted(self) -> None:
        log = "Using AWS key AKIA" + "A" * 16
        result = _sanitize(log)
        assert "AKIA" not in result
        assert "[REDACTED_SECRET]" in result

    def test_partial_akia_not_redacted(self) -> None:
        # Only exactly 16 chars after AKIA should match
        log = "AKIA" + "A" * 10  # too short — should NOT be redacted
        result = _sanitize(log)
        # The pattern requires exactly 16 uppercase alphanumeric chars, so this
        # should pass through unchanged.
        assert "[REDACTED_SECRET]" not in result


# ── PEM Private Key ────────────────────────────────────────────────────────────

class TestPrivateKeyRedaction:
    RSA_KEY = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0Z3VS5JJcds3xHn/ygWep4P\n"
        "-----END RSA PRIVATE KEY-----"
    )
    OPENSSH_KEY = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAA\n"
        "-----END OPENSSH PRIVATE KEY-----"
    )

    def test_rsa_private_key_is_redacted(self) -> None:
        result = _sanitize(self.RSA_KEY)
        assert "BEGIN RSA PRIVATE KEY" not in result
        assert "[REDACTED_PRIVATE_KEY]" in result

    def test_openssh_private_key_is_redacted(self) -> None:
        result = _sanitize(self.OPENSSH_KEY)
        assert "BEGIN OPENSSH PRIVATE KEY" not in result
        assert "[REDACTED_PRIVATE_KEY]" in result

    def test_key_embedded_in_log_is_redacted(self) -> None:
        log = f"Uploading SSH key:\n{self.RSA_KEY}\nDone."
        result = _sanitize(log)
        assert "PRIVATE KEY" not in result
        assert "Uploading SSH key:" in result
        assert "Done." in result


# ── Generic environment variable secrets ──────────────────────────────────────

class TestEnvSecretRedaction:
    def test_password_env_var_is_redacted(self) -> None:
        log = "Loaded config: DB_PASSWORD=supersecret123"
        result = _sanitize(log)
        assert "supersecret123" not in result
        assert "[REDACTED_ENV_SECRET]" in result

    def test_api_key_env_var_is_redacted(self) -> None:
        log = "export API_KEY=sk-abc123XYZ"
        result = _sanitize(log)
        assert "sk-abc123XYZ" not in result
        assert "[REDACTED_ENV_SECRET]" in result

    def test_token_env_var_is_redacted(self) -> None:
        log = "CI_SECRET_TOKEN=tok_live_0000aaaa"
        result = _sanitize(log)
        assert "tok_live_0000aaaa" not in result


# ── JWT redaction ──────────────────────────────────────────────────────────────

class TestJWTRedaction:
    JWT = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )

    def test_jwt_is_redacted(self) -> None:
        log = f"Authorization: Bearer {self.JWT}"
        result = _sanitize(log)
        assert self.JWT not in result
        assert "[REDACTED" in result


# ── Truncation ─────────────────────────────────────────────────────────────────

class TestLogTruncation:
    def test_log_within_limit_is_not_truncated(self) -> None:
        log = "x" * 100
        result = _sanitize(log, max_chars=200)
        assert "Truncated" not in result
        assert result == log

    def test_oversized_log_is_tail_truncated(self) -> None:
        tail = "FAILURE: exit code 1"
        log = ("a" * 1000) + tail
        result = _sanitize(log, max_chars=100)
        assert "Truncated" in result
        assert tail in result

    def test_truncation_notice_contains_byte_count(self) -> None:
        log = "a" * 500
        result = _sanitize(log, max_chars=100)
        assert "400" in result  # 500 - 100 = 400 chars dropped
