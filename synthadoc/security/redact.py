# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Redaction of secrets from text, URLs and objects.

Defence in depth: the primary rule is still "never log or store a secret". Redaction
runs at output boundaries (log records, job errors, scheduler output, API responses)
and never rewrites data the system needs to work, such as stored source URLs.

Every pattern uses bounded or single-class quantifiers and a fixed prefix, so matching
is linear-time (the project has fixed ReDoS findings before); the tests feed it very
long adversarial inputs.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Iterable, Optional, Union
from urllib.parse import parse_qsl, urlsplit, urlunsplit

logger = logging.getLogger("synthadoc.security.redact")

_MASK = "[REDACTED]"
_NOT_MASKED = r"(?!\[REDACTED\])"

_USERINFO_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]{1,20}://)[^/\s@]+@")
# Possessive quantifiers (Python 3.11+) stop the engine backtracking into fewer spaces, which
# would let a second pass re-match "Authorization: [REDACTED]" and break idempotence.
_HEADER_RE = re.compile(
    r"""(?i)\b(authorization|proxy-authorization|cookie|set-cookie)(["']?+\s*+[:=]\s*+["']?+)"""
    + _NOT_MASKED + r"""[^\r\n"',}]*""")
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)" + _NOT_MASKED + r"[A-Za-z0-9._~+/=\-]{8,}")
_TOKEN_PATTERNS = tuple(re.compile(p) for p in (
    r"\bsk-ant-[A-Za-z0-9_\-]{20,}",
    r"\bsk-[A-Za-z0-9_\-]{20,}",
    r"\btvly-[A-Za-z0-9_\-]{16,}",
    r"\bAIza[0-9A-Za-z_\-]{30,}",
    r"\bgsk_[A-Za-z0-9]{20,}",
    r"\bgh[pousr]_[A-Za-z0-9]{30,}",
    r"\bxox[abprs]-[A-Za-z0-9\-]{10,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}",
    r"\bsd_[A-Za-z0-9]+_[A-Za-z0-9_\-]{16,}",
))
_PARAM_RE = re.compile(r"""([?&;#])([A-Za-z0-9_.\-]{1,40})=([^&#\s"'<>]*)""")
_KV_RE = re.compile(
    r"""(?i)\b(password|passwd|pwd|secret|client_secret|api[_-]?key|apikey|access_token|"""
    r"""refresh_token|auth_token|token)(["']?\s*[=:]\s*)(["']?)""" + _NOT_MASKED + r"""[^\s,;&"'}\]]+""")

# Display/log masking: broad on purpose, over-redacting a log line is harmless.
_BROAD_PARAMS = frozenset({
    "token", "access_token", "refresh_token", "id_token", "api_key", "apikey", "api-key",
    "key", "secret", "client_secret", "password", "passwd", "pwd", "sig", "signature",
    "auth", "code", "session", "sessionid", "credential", "x-amz-signature",
    "x-amz-credential", "x-amz-security-token", "x-goog-signature", "x-goog-credential",
})
# Refusal/warning: narrow and high-confidence, `?code=US` and `?key=<doc-id>` are identifiers.
_NARROW_PARAMS = frozenset({
    "access_token", "token", "api_key", "apikey", "secret", "password", "passwd",
    "signature", "x-amz-signature", "x-amz-credential",
})

_SENSITIVE_KEYS = frozenset({
    "authorization", "proxy_authorization", "cookie", "set_cookie", "password", "passwd",
    "pwd", "secret", "token", "api_key", "apikey", "access_token", "refresh_token",
    "id_token", "client_secret", "auth_token", "credential", "credentials", "private_key",
    "session_token", "x_api_key",
})
_SENSITIVE_SUFFIXES = ("_password", "_secret", "_api_key", "_access_token", "_refresh_token",
                       "_auth_token", "_private_key")

_MIN_REGISTERED_LEN = 6
_MAX_REGISTERED = 1000
_lock = threading.Lock()
_registered: list = []
_snapshot: tuple = ()          # longest first, so a long secret is not split by a short one


def register_secret_value(value: Union[str, bytes]) -> None:
    """Scrub an exact secret of unknown shape (an OAuth token) wherever it appears.

    Per process: the server and each child that holds a secret must register it.
    Very short values are ignored (they would mangle ordinary text); the registry is
    capped and evicts the oldest value first.
    """
    global _snapshot
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    if not isinstance(value, str) or len(value) < _MIN_REGISTERED_LEN:
        return
    with _lock:
        if value in _registered:
            return
        _registered.append(value)
        if len(_registered) > _MAX_REGISTERED:
            _registered.pop(0)
        _snapshot = tuple(sorted(_registered, key=len, reverse=True))


def clear_registered_values() -> None:
    global _snapshot
    with _lock:
        _registered.clear()
        _snapshot = ()


def _mask_param(match: "re.Match[str]") -> str:
    name, value = match.group(2), match.group(3)
    if name.lower() in _BROAD_PARAMS and value != _MASK:
        return f"{match.group(1)}{name}={_MASK}"
    return match.group(0)


def redact_text(text: Any) -> Any:
    """Return ``text`` with secrets masked; non-strings pass through unchanged."""
    if not isinstance(text, str) or not text:
        return text
    out = _USERINFO_RE.sub(lambda m: m.group(1) + _MASK + "@", text)
    out = _HEADER_RE.sub(lambda m: m.group(1) + m.group(2) + _MASK, out)
    out = _BEARER_RE.sub(lambda m: m.group(1) + _MASK, out)
    for pattern in _TOKEN_PATTERNS:
        out = pattern.sub(_MASK, out)
    out = _PARAM_RE.sub(_mask_param, out)
    out = _KV_RE.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + _MASK, out)
    for secret in _snapshot:
        if secret in out:
            out = out.replace(secret, _MASK)
    return out


def _mask_query(query: str) -> str:
    return _PARAM_RE.sub(_mask_param, "&" + query)[1:] if query else query


def redact_url(url: str) -> str:
    """Display form of a URL: userinfo dropped, secret-looking parameters masked."""
    if not isinstance(url, str):
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return redact_text(url)
    if not parts.scheme and not parts.netloc:
        return redact_text(url)
    netloc = parts.netloc
    if "@" in netloc:
        netloc = _MASK + "@" + netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, netloc, parts.path,
                       _mask_query(parts.query), _mask_query(parts.fragment)))


def find_secret_params(url: str) -> list:
    """Names of high-confidence secret parameters in ``url`` (for warnings or refusal)."""
    try:
        query = urlsplit(url).query
    except ValueError:
        return []
    return [name for name, _ in parse_qsl(query, keep_blank_values=True)
            if name.lower() in _NARROW_PARAMS]


def _is_sensitive_key(key: Any) -> bool:
    normal = str(key).lower().replace("-", "_")
    return normal in _SENSITIVE_KEYS or normal.endswith(_SENSITIVE_SUFFIXES)


_MAX_DEPTH = 30


def redact_obj(obj: Any, _path: frozenset = frozenset(), _depth: int = 0) -> Any:
    """Deep copy of ``obj`` with sensitive keys masked and strings redacted."""
    if isinstance(obj, str):
        return redact_text(obj)
    if not isinstance(obj, (dict, list, tuple)):
        return obj
    if id(obj) in _path:
        return "[CYCLE]"
    if _depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    path = _path | {id(obj)}
    if isinstance(obj, dict):
        return {
            key: (_MASK if _is_sensitive_key(key) and value is not None and value != ""
                  else redact_obj(value, path, _depth + 1))
            for key, value in obj.items()
        }
    items = [redact_obj(item, path, _depth + 1) for item in obj]
    return items if isinstance(obj, list) else tuple(items)


def safe_error(exc: BaseException, *, public: str) -> str:
    """Log the redacted detail server-side and return the text that is safe for clients."""
    logger.warning("%s: %s: %s", public, type(exc).__name__, redact_text(str(exc)))
    return public


class RedactingFilter(logging.Filter):
    """Handler filter: redact the message, its arguments and the exception text."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a broken format string must still be logged
            return True
        redacted = redact_text(message)
        if redacted != message:
            record.msg, record.args = redacted, None
        if record.exc_info and record.exc_info[0] is not None:
            try:
                record.exc_text = redact_text(logging.Formatter().formatException(record.exc_info))
            except Exception:  # noqa: BLE001
                pass
        return True


def install_log_filter(logger_names: Iterable[str] = ("",)) -> None:
    """Attach the redacting filter to the handlers of the named loggers (idempotent).

    Handlers added later are not covered, so call this after logging is configured.
    The empty name is the root logger.
    """
    for name in logger_names:
        for handler in logging.getLogger(name).handlers:
            if not any(isinstance(f, RedactingFilter) for f in handler.filters):
                handler.addFilter(RedactingFilter())
