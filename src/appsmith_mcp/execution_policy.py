"""Read-only execution policy for Appsmith actions.

`execute_queries` asks this module whether a saved action may run. The policy is fail-closed:
anything it cannot positively classify as a read is blocked. It is a best-effort guard based
on static analysis of the action's saved configuration, not a guarantee. It cannot see what a
database function, stored routine or HTTP endpoint does when called, and it checks the saved
text before Appsmith evaluates `{{ }}` bindings. Database and API permissions remain the real
boundary.
"""

import itertools
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
    return PolicyDecision(True, f"Read-only execution allowed ({kind}).")


def _blocked(detail: str) -> PolicyDecision:
    return PolicyDecision(False, f"Execution blocked by the read-only policy: {detail}.")


@dataclass(frozen=True)
class _SqlDialect:
    """Lexical rules that differ between SQL engines."""

    backslash_escapes: bool  # MySQL/Snowflake: 'it\'s'; T-SQL/standard SQL: backslash is literal
    nested_comments: bool  # T-SQL/Postgres nest /* /* */ */; MySQL closes at the first */
    hash_comments: bool  # MySQL: '#' starts a line comment; T-SQL: #temp is a table name
    dollar_quotes: bool  # Postgres/Snowflake: $$...$$ and $tag$...$tag$ are string literals


# A text that hides a statement inside a literal or comment under one engine's rules can
# expose it under another's. The policy cannot rely on the plugin name alone to pick the
# rules, so SQL is allowed only when every interpretation agrees that it is a single read.
_SQL_DIALECTS = tuple(
    _SqlDialect(*flags) for flags in itertools.product((False, True), repeat=4)
)

_IDENTIFIER_CHAR = re.compile(r"[A-Za-z0-9_$]")
_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


def _blank(text: str) -> str:
    return "".join("\n" if char == "\n" else " " for char in text)


def _mask_sql_literals_and_comments(sql: str, dialect: _SqlDialect) -> str | None:
    """Replace comments and literals with spaces, keeping SQL delimiters.

    Returns None when a string literal, quoted identifier or block comment is never closed:
    the remaining text cannot be classified safely.
    """
    out: list[str] = []
    i = 0
    size = len(sql)
    while i < size:
        char = sql[i]
        nxt = sql[i + 1] if i + 1 < size else ""

        if (char == "-" and nxt == "-") or (char == "#" and dialect.hash_comments):
            end = i
            while end < size and sql[end] not in "\r\n":
                end += 1
            out.append(_blank(sql[i:end]))
            i = end
            continue

        if char == "/" and nxt == "*":
            depth = 1
            end = i + 2
            while end < size and depth:
                pair = sql[end : end + 2]
                if pair == "/*" and dialect.nested_comments:
                    depth += 1
                    end += 2
                elif pair == "*/":
                    depth -= 1
                    end += 2
                else:
                    end += 1
            if depth:
                return None
            out.append(_blank(sql[i:end]))
            i = end
            continue

        if (
            char == "$"
            and dialect.dollar_quotes
            and not (i and _IDENTIFIER_CHAR.match(sql[i - 1]))
        ):
            tag = _DOLLAR_TAG.match(sql, i)
            if tag:
                close = sql.find(tag.group(0), tag.end())
                if close < 0:
                    return None
                end = close + len(tag.group(0))
                out.append(_blank(sql[i:end]))
                i = end
                continue

        if char in ("'", '"', "`", "["):
            closing = "]" if char == "[" else char
            end = i + 1
            while True:
                if end >= size:
                    return None
                current = sql[end]
                if current == "\\" and dialect.backslash_escapes and char != "[":
                    end += 2
                    continue
                if current == closing:
                    if end + 1 < size and sql[end + 1] == closing:
                        end += 2
                        continue
                    end += 1
                    break
                end += 1
            out.append(_blank(sql[i:end]))
            i = end
            continue

        out.append(char)
        i += 1
    return "".join(out)


def _assess_sql_code(code: str | None) -> PolicyDecision:
    if code is None:
        return _blocked("unterminated string literal, quoted identifier or comment")
    code = code.strip()
    if code.startswith(";"):
        code = code[1:].lstrip()
    if code.endswith(";"):
        code = code[:-1].rstrip()
    if not code:
        return _blocked("missing or empty SQL")
    if ";" in code:
        return _blocked("more than one SQL statement")

    words = re.findall(r"[A-Za-z_][A-Za-z0-9_$#]*", code.upper())
    if not words or words[0] not in {"SELECT", "WITH"}:
        return _blocked("only SELECT or WITH ... SELECT is allowed")
    if words[0] == "WITH" and "SELECT" not in words:
        return _blocked("CTE without a final SELECT")

    forbidden = sorted(set(words) & SQL_FORBIDDEN_WORDS)
    if forbidden:
        return _blocked(f"forbidden keyword: {forbidden[0]}")
    return _allowed("SQL SELECT")


def _assess_sql(config: Mapping[str, Any]) -> PolicyDecision:
    sql = config.get("body")
    if not isinstance(sql, str) or not sql.strip():
        return _blocked("missing or empty SQL")
    for dialect in _SQL_DIALECTS:
        decision = _assess_sql_code(_mask_sql_literals_and_comments(sql, dialect))
        if not decision.allowed:
            return decision
    return _allowed("SQL SELECT")


def _assess_rest(config: Mapping[str, Any]) -> PolicyDecision:
    method = str(config.get("httpMethod") or "").strip().upper()
    if method in {"GET", "HEAD"}:
        return _allowed(f"HTTP {method}")
    return _blocked(f"HTTP method {method or 'missing'} is not read-only")


# Block strings first, then plain strings, so a '#' inside a string is not read as a comment.
_GRAPHQL_STRING = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\\n])*"')


def _assess_graphql(config: Mapping[str, Any]) -> PolicyDecision:
    body = config.get("body")
    if not isinstance(body, str) or not body.strip():
        return _blocked("missing or empty GraphQL operation")

    without_strings = _GRAPHQL_STRING.sub('""', body)
    without_comments = re.sub(r"(?m)#.*$", "", without_strings).lstrip()
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", without_comments.lower()))
    if {"mutation", "subscription"} & words:
        return _blocked("GraphQL mutations and subscriptions are not read-only")
    if without_comments.startswith("{") or re.match(r"(?i)^query\b", without_comments):
        return _allowed("GraphQL query")
    return _blocked("only GraphQL queries are allowed")


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
        return _blocked("missing MongoDB configuration")
    command_config = form_data.get("command")
    command = ""
    if isinstance(command_config, Mapping):
        command = str(command_config.get("data") or "").strip().upper()

    if command in {"FIND", "COUNT", "DISTINCT"}:
        return _allowed(f"MongoDB {command}")
    if command == "AGGREGATE":
        if _contains_mongo_write_stage(form_data.get("aggregate")):
            return _blocked("MongoDB pipeline contains $out or $merge")
        return _allowed("MongoDB AGGREGATE")
    return _blocked(f"MongoDB command {command or 'missing'} is not read-only")


def assess_query_action(action: Mapping[str, Any]) -> PolicyDecision:
    """Decide whether the MCP may execute an action."""
    plugin = str(action.get("pluginPackageName") or "").strip().lower()
    config = action.get("actionConfiguration")
    if not isinstance(config, Mapping):
        return _blocked("missing query configuration")

    if plugin in SQL_PLUGINS:
        return _assess_sql(config)
    if plugin == "restapi-plugin":
        return _assess_rest(config)
    if plugin == "graphql-plugin":
        return _assess_graphql(config)
    if plugin == "mongo-plugin":
        return _assess_mongo(config)
    return _blocked(f"no read-only rule for plugin {plugin or 'unknown'}")
