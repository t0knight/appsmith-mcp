"""Política de execução somente leitura para ações do Appsmith."""

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


SQL_PLUGINS = frozenset(
    {
        "mssql-plugin",
        "mysql-plugin",
        "oracle-plugin",
        "postgres-plugin",
        "redshift-plugin",
        "snowflake-plugin",
    }
)

SQL_FORBIDDEN_WORDS = frozenset(
    {
        "ALTER",
        "ANALYZE",
        "ATTACH",
        "BACKUP",
        "BULK",
        "CALL",
        "COMMENT",
        "COPY",
        "CREATE",
        "DBCC",
        "DECLARE",
        "DELETE",
        "DENY",
        "DETACH",
        "DROP",
        "EXEC",
        "EXECUTE",
        "GRANT",
        "INSERT",
        "INSTALL",
        "INTO",
        "KILL",
        "LOAD",
        "MERGE",
        "PRAGMA",
        "RECONFIGURE",
        "REMOVE",
        "RENAME",
        "RESTORE",
        "REVOKE",
        "SET",
        "SHUTDOWN",
        "TRUNCATE",
        "UNLOAD",
        "UPDATE",
        "USE",
        "VACUUM",
    }
)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


def _allowed(kind: str) -> PolicyDecision:
    return PolicyDecision(True, f"Execução de leitura permitida ({kind}).")


def _blocked(detail: str) -> PolicyDecision:
    return PolicyDecision(
        False,
        f"Execução bloqueada pela política somente leitura: {detail}.",
    )


def _mask_sql_literals_and_comments(sql: str) -> str:
    """Substitui comentários e literais por espaços, preservando delimitadores SQL."""
    out: list[str] = []
    i = 0
    size = len(sql)
    while i < size:
        char = sql[i]
        nxt = sql[i + 1] if i + 1 < size else ""

        if char == "-" and nxt == "-":
            out.extend((" ", " "))
            i += 2
            while i < size and sql[i] not in "\r\n":
                out.append(" ")
                i += 1
            continue

        if char == "/" and nxt == "*":
            out.extend((" ", " "))
            i += 2
            depth = 1
            while i < size and depth:
                nxt = sql[i + 1] if i + 1 < size else ""
                if sql[i] == "/" and nxt == "*":
                    depth += 1
                    out.extend((" ", " "))
                    i += 2
                elif sql[i] == "*" and nxt == "/":
                    depth -= 1
                    out.extend((" ", " "))
                    i += 2
                else:
                    out.append("\n" if sql[i] == "\n" else " ")
                    i += 1
            continue

        if char in ("'", '"', "`"):
            quote = char
            out.append(" ")
            i += 1
            while i < size:
                out.append("\n" if sql[i] == "\n" else " ")
                if sql[i] == quote:
                    if i + 1 < size and sql[i + 1] == quote:
                        out.append(" ")
                        i += 2
                        continue
                    i += 1
                    break
                if sql[i] == "\\" and i + 1 < size:
                    out.append(" ")
                    i += 2
                else:
                    i += 1
            continue

        if char == "[":
            out.append(" ")
            i += 1
            while i < size:
                out.append(" ")
                if sql[i] == "]":
                    if i + 1 < size and sql[i + 1] == "]":
                        out.append(" ")
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue

        out.append(char)
        i += 1
    return "".join(out)


def _assess_sql(config: Mapping[str, Any]) -> PolicyDecision:
    sql = config.get("body")
    if not isinstance(sql, str) or not sql.strip():
        return _blocked("SQL ausente ou vazio")

    code = _mask_sql_literals_and_comments(sql).strip()
    if code.startswith(";"):
        code = code[1:].lstrip()
    if code.endswith(";"):
        code = code[:-1].rstrip()
    if not code:
        return _blocked("SQL ausente ou vazio")
    if ";" in code:
        return _blocked("mais de uma instrução SQL")

    words = re.findall(r"[A-Za-z_][A-Za-z0-9_$#]*", code.upper())
    if not words or words[0] not in {"SELECT", "WITH"}:
        return _blocked("somente SELECT ou WITH ... SELECT é permitido")
    if words[0] == "WITH" and "SELECT" not in words:
        return _blocked("CTE sem SELECT final")

    forbidden = sorted(set(words) & SQL_FORBIDDEN_WORDS)
    if forbidden:
        return _blocked(f"palavra não permitida: {forbidden[0]}")
    return _allowed("SQL SELECT")


def _assess_rest(config: Mapping[str, Any]) -> PolicyDecision:
    method = str(config.get("httpMethod") or "").strip().upper()
    if method in {"GET", "HEAD"}:
        return _allowed(f"HTTP {method}")
    return _blocked(f"método HTTP {method or 'ausente'} não é de leitura")


def _assess_graphql(config: Mapping[str, Any]) -> PolicyDecision:
    body = config.get("body")
    if not isinstance(body, str) or not body.strip():
        return _blocked("operação GraphQL ausente ou vazia")

    without_comments = re.sub(r"(?m)#.*$", "", body).lstrip()
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", without_comments.lower()))
    if {"mutation", "subscription"} & words:
        return _blocked("GraphQL mutation/subscription não é leitura")
    if without_comments.startswith("{") or re.match(r"(?i)^query\b", without_comments):
        return _allowed("GraphQL query")
    return _blocked("somente GraphQL query é permitida")


def _contains_mongo_write_stage(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in {"$out", "$merge"}:
                return True
            if _contains_mongo_write_stage(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_mongo_write_stage(item) for item in value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return bool(re.search(r"(?i)[\"']\$(out|merge)[\"']\s*:", value))
        return _contains_mongo_write_stage(decoded)
    return False


def _assess_mongo(config: Mapping[str, Any]) -> PolicyDecision:
    form_data = config.get("formData")
    if not isinstance(form_data, Mapping):
        return _blocked("configuração MongoDB ausente")
    command_config = form_data.get("command")
    command = ""
    if isinstance(command_config, Mapping):
        command = str(command_config.get("data") or "").strip().upper()

    if command in {"FIND", "COUNT", "DISTINCT"}:
        return _allowed(f"MongoDB {command}")
    if command == "AGGREGATE":
        if _contains_mongo_write_stage(form_data.get("aggregate")):
            return _blocked("pipeline MongoDB contém $out ou $merge")
        return _allowed("MongoDB AGGREGATE")
    return _blocked(f"comando MongoDB {command or 'ausente'} não é de leitura")


def assess_query_action(action: Mapping[str, Any]) -> PolicyDecision:
    """Classifica se uma ação pode ser executada pelo MCP."""
    plugin = str(action.get("pluginPackageName") or "").strip().lower()
    config = action.get("actionConfiguration")
    if not isinstance(config, Mapping):
        return _blocked("configuração da query ausente")

    if plugin in SQL_PLUGINS:
        return _assess_sql(config)
    if plugin == "restapi-plugin":
        return _assess_rest(config)
    if plugin == "graphql-plugin":
        return _assess_graphql(config)
    if plugin == "mongo-plugin":
        return _assess_mongo(config)
    return _blocked(f"plugin {plugin or 'desconhecido'} sem regra segura")
