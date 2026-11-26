"""Best-effort masking of secrets in editor state returned to the agent.

A value is replaced with `REDACTED` when:

- its key name looks secret (`password`, `clientSecret`, `accessToken`, `apiKey`,
  `Authorization`, `Cookie`, ...);
- it is the `value` of a `{key, value}` pair (headers, query parameters, properties) whose
  `key` looks secret;
- it is the `value` of an API-key authentication block (`authenticationType: "apiKey"`);
- the string itself looks like a credential: an `Authorization` scheme (`Bearer ...`,
  `Basic ...`), a JWT, or the password part of a URL such as `postgres://user:pass@host`.

Binding expressions such as `Bearer {{ appsmith.store.token }}` are kept, since they
reference a secret instead of containing it. Empty values and booleans are kept so flags
like `secretExists` stay readable.

This is a best-effort filter, NOT a guarantee. Detection relies on key names and a few
value formats, so a secret stored under a neutral name (`value`, `config`, `data`, ...) in
an unrecognised format is returned unchanged.
"""

import re
from typing import Any

REDACTED = "[REDACTED]"

_EXACT_KEYS = frozenset(
    {
        "authorization",
        "proxyauthorization",
        "cookie",
        "setcookie",
        "pwd",
    }
)
_KEY_FRAGMENTS = ("password", "passwd", "secret", "credential")
_KEY_SUFFIXES = ("token", "apikey", "privatekey", "secretkey", "servicerolekey")

_AUTH_SCHEME = re.compile(r"(?i)^\s*(bearer|basic|digest|token)\s+\S+")
_JWT = re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*$")
_URL_PASSWORD = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://[^\s/:@]+:)([^\s/@]+)(@)")
_BINDING = re.compile(r"\{\{[\s\S]*?\}\}")


def _normalize(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key or "").lower())


def is_sensitive_key(key: Any) -> bool:
    normalized = _normalize(key)
    if not normalized:
        return False
    return (
        normalized in _EXACT_KEYS
        or any(fragment in normalized for fragment in _KEY_FRAGMENTS)
        or normalized.endswith(_KEY_SUFFIXES)
    )


def _is_binding_reference(value: str) -> bool:
    """True for a binding that only names where the secret lives, optionally after an
    Authorization scheme: `{{ appsmith.store.token }}`, `Bearer {{ ... }}`."""
    if not _BINDING.search(value):
        return False
    rest = _BINDING.sub("", value).strip().lower()
    return rest in {"", "bearer", "basic", "digest", "token"}


def _mask(value: Any) -> Any:
    if value is None or isinstance(value, bool) or value == "":
        return value
    if isinstance(value, str) and _is_binding_reference(value):
        return value
    return REDACTED


def _redact_string(value: str) -> str:
    if _is_binding_reference(value):
        return value
    if _AUTH_SCHEME.match(value) or _JWT.match(value.strip()):
        return REDACTED
    return _URL_PASSWORD.sub(rf"\g<1>{REDACTED}\g<3>", value)


def redact(value: Any, key: Any = None) -> Any:
    """Return a copy of `value` with secret-looking content replaced by `REDACTED`.

    `key` is the name the value is stored under, when known (for example the last segment
    of an evaluated path)."""
    if key is not None and is_sensitive_key(key):
        return _mask(value)
    if isinstance(value, dict):
        pair_key = value.get("key")
        mask_value = (isinstance(pair_key, str) and is_sensitive_key(pair_key)) or (
            _normalize(value.get("authenticationType")) == "apikey"
        )
        return {
            k: _mask(v) if k == "value" and mask_value else redact(v, k)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value
