"""Preparação segura de configurações de queries do Appsmith."""

from copy import deepcopy
from typing import Any, Mapping


SENSITIVE_HEADER_NAMES = frozenset(
    {"authorization", "proxy-authorization", "apikey", "x-api-key"}
)


def _join_path(parent: str, key: str) -> str:
    return f"{parent}.{key}" if parent else key


def _binding_paths(value: Any, path: str = "") -> list[dict[str, str]]:
    paths: list[dict[str, str]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            paths.extend(_binding_paths(child, _join_path(path, str(key))))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_binding_paths(child, f"{path}[{index}]"))
    elif isinstance(value, str) and "{{" in value and "}}" in value:
        paths.append({"key": path})
    return paths


def _reject_literal_sensitive_headers(value: Any) -> None:
    if isinstance(value, Mapping):
        headers = value.get("headers")
        if isinstance(headers, list):
            for header in headers:
                if not isinstance(header, Mapping):
                    continue
                name = str(header.get("key") or "").strip().lower()
                header_value = header.get("value")
                if (
                    name in SENSITIVE_HEADER_NAMES
                    and isinstance(header_value, str)
                    and header_value.strip()
                    and not ("{{" in header_value and "}}" in header_value)
                ):
                    raise ValueError(
                        f"header sensível '{name}' deve usar binding; "
                        "valor literal recusado"
                    )
        for child in value.values():
            _reject_literal_sensitive_headers(child)
    elif isinstance(value, list):
        for child in value:
            _reject_literal_sensitive_headers(child)


def prepare_action_configuration(
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Copia a configuração e retorna seus caminhos de binding."""
    prepared = deepcopy(dict(config))
    _reject_literal_sensitive_headers(prepared)
    return prepared, _binding_paths(prepared)
