import re

import cssbeautifier
import jsbeautifier
from bs4 import BeautifulSoup


def format_source(field: str, code: str) -> str:
    """Beautify a Custom Widget source field (`js`/`css`/`html`) so it reads cleanly in
    the widget's source editor. On any beautifier error the original code is returned
    untouched."""
    try:
        if field == "js":
            return jsbeautifier.beautify(code)
        if field == "css":
            return cssbeautifier.beautify(code)
        if field == "html":
            return BeautifulSoup(code, "html.parser").prettify()
    except Exception:
        return code
    return code


_STATEMENT_START = re.compile(
    r"^\s*(?:const|let|var|class|if|for|while|switch|try|do|throw|return|delete|"
    r"function\b|async\s+function\b)\b"
)


def as_expression(snippet: str) -> str:
    """Wrap a statement-style snippet in an async IIFE so it can be evaluated.

    Snippets are evaluated as expressions, so `const x = 1; return x;` is a SyntaxError
    ("expected expression, got keyword 'const'"). A snippet that already starts with `(`
    is left alone — it is an expression or a hand-written IIFE — and so is a bare
    expression like `document.title`, which would otherwise lose its value to a wrapper
    with no `return`."""
    if not snippet or snippet.lstrip().startswith("("):
        return snippet
    if _STATEMENT_START.match(snippet):
        return f"(async () => {{\n{snippet}\n}})()"
    return snippet


def pick(obj, allowed):
    """Return a new dict with only keys from `allowed`. Drops everything else."""
    if not isinstance(obj, dict):
        return obj
    return {k: obj[k] for k in allowed if k in obj}


def parse_function_names(body: str) -> list[str]:
    """Return the top-level keys in `export default { ... }` whose values look like
    functions (arrow, function expression, or method shorthand). Best-effort —
    handles strings, comments, and nested braces but isn't a full JS parser."""
    m = re.search(r"export\s+default\s*\{", body)
    if not m:
        return []
    start = m.end()
    end = _find_matching_brace(body, start)
    if end is None:
        return []
    return _scan_top_level_functions(body[start:end])


def _find_matching_brace(s: str, start: int) -> int | None:
    depth = 1
    in_str: str | None = None
    in_block = False
    in_line = False
    i = start
    while i < len(s) and depth > 0:
        c = s[i]
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif in_block:
            if c == "*" and nxt == "/":
                in_block = False
                i += 1
        elif in_line:
            if c == "\n":
                in_line = False
        elif c == "/" and nxt == "/":
            in_line = True
            i += 1
        elif c == "/" and nxt == "*":
            in_block = True
            i += 1
        elif c in ('"', "'", "`"):
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _scan_top_level_functions(inner: str) -> list[str]:
    names: list[str] = []
    depth = 0
    in_str: str | None = None
    in_block = False
    in_line = False
    after_sep = True
    j = 0
    while j < len(inner):
        c = inner[j]
        nxt = inner[j + 1] if j + 1 < len(inner) else ""
        if in_str:
            if c == "\\":
                j += 2
                continue
            if c == in_str:
                in_str = None
            j += 1
            continue
        if in_block:
            if c == "*" and nxt == "/":
                in_block = False
                j += 2
                continue
            j += 1
            continue
        if in_line:
            if c == "\n":
                in_line = False
            j += 1
            continue
        if c == "/" and nxt == "/":
            in_line = True
            j += 2
            continue
        if c == "/" and nxt == "*":
            in_block = True
            j += 2
            continue
        if c in ('"', "'", "`"):
            in_str = c
            j += 1
            continue
        if c in "{[(":
            depth += 1
            after_sep = False
            j += 1
            continue
        if c in "}])":
            depth -= 1
            after_sep = False
            j += 1
            continue
        if depth == 0:
            if c == ",":
                after_sep = True
                j += 1
                continue
            if c.isspace():
                j += 1
                continue
            if after_sep:
                m = re.match(r"(async\s+)?([A-Za-z_$][A-Za-z0-9_$]*)", inner[j:])
                if m:
                    name = m.group(2)
                    end_k = j + m.end()
                    rest = inner[end_k:].lstrip()
                    if rest.startswith("("):
                        names.append(name)
                    elif rest.startswith(":"):
                        v = rest[1:].lstrip()
                        if (
                            v.startswith("function")
                            or v.startswith("(")
                            or v.startswith("async")
                            or re.match(r"[A-Za-z_$][A-Za-z0-9_$]*\s*=>", v)
                        ):
                            names.append(name)
                    after_sep = False
                    j = end_k
                    continue
        j += 1
    return names
