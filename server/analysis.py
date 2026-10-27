"""Analyse Python : complétion, signature, doc, définition, diagnostics, format.

Conventions :
- Monaco : lignes 1-based, colonnes 1-based (fin exclusive).
- Jedi   : lignes 1-based, colonnes 0-based.
- Pyflakes : lignes 1-based, colonnes 1-based (début du token).
"""

from __future__ import annotations

import contextlib
import io
import re
from pathlib import Path
from typing import Any

import jedi
from pyflakes.api import check as pyflakes_check
from pyflakes.reporter import Reporter

_PYFLAKES_LINE = re.compile(r"^(?P<file>.*):(?P<line>\d+):(?P<col>\d+): (?P<msg>.*)$")

_ERROR_HINTS = (
    "undefined name",
    "duplicate argument",
    "syntax error",
    "invalid syntax",
    "return outside function",
    "yield outside function",
    "break outside loop",
    "continue outside loop",
    "referenced before assignment",
    "cannot import name",
    "future feature",
    "__future__ import",
    "encoding declaration",
    "assignment to",
    "is not defined",
)

_MONACO_KIND = {
    "module": 9,
    "class": 7,
    "instance": 6,
    "function": 3,
    "param": 6,
    "path": 17,
    "keyword": 14,
    "property": 10,
    "statement": 14,
}

_PRIORITY = {
    "param": 0,
    "keyword": 1,
    "function": 2,
    "class": 3,
    "instance": 4,
    "module": 5,
    "property": 5,
    "statement": 5,
    "path": 6,
}


def _lines(code: str) -> list[str]:
    return code.splitlines() or [""]


def _clamp(code: str, line: int, column: int) -> tuple[int, int, str]:
    lines = _lines(code)
    line = max(1, min(int(line or 1), len(lines)))
    text = lines[line - 1]
    column = max(0, min(int(column or 0), len(text)))
    return line, column, text


def _script(code: str, path: str | None) -> jedi.Script:
    kwargs: dict[str, Any] = {"code": code, "path": path}
    if path:
        project_dir = Path(path).expanduser().resolve().parent
        if project_dir.is_dir():
            kwargs["project"] = jedi.Project(str(project_dir))
    return jedi.Script(**kwargs)


def _jedi_call(func, code: str, line: int, column: int, path: str | None):
    """Appelle Jedi en corrigeant les colonnes hors limites (fin de ligne)."""
    line, column, text = _clamp(code, line, column)
    candidates = [column]
    for fallback in (len(text), len(text) - 1, 0):
        if fallback >= 0 and fallback not in candidates:
            candidates.append(fallback)
    script = _script(code, path)
    last_error: Exception | None = None
    for col in candidates:
        try:
            return func(script, line, col)
        except (ValueError, IndexError, KeyError) as exc:
            last_error = exc
        except Exception:
            return None
    return None


def complete(code: str, line: int, column: int, path: str | None = None) -> list[dict]:
    comps = _jedi_call(
        lambda script, ln, col: script.complete(line=ln, column=col),
        code, line, column, path,
    )
    if not comps:
        return []

    items: list[dict] = []
    seen: set[str] = set()
    for c in comps[:80]:
        if c.name in seen:
            continue
        seen.add(c.name)
        kind = _MONACO_KIND.get(c.type, 13)
        item = {
            "label": c.name,
            "kind": kind,
            "detail": c.type,
            "insertText": c.name,
            "sortText": f"{_PRIORITY.get(c.type, 5)}_{c.name}",
            "filterText": c.name,
        }
        try:
            doc = c.docstring(raw=True, fast=True)
        except Exception:
            doc = ""
        if doc:
            item["documentation"] = {"value": doc[:1200]}
        items.append(item)
    return items


def signature(code: str, line: int, column: int, path: str | None = None) -> dict | None:
    sigs = _jedi_call(
        lambda script, ln, col: script.get_signatures(line=ln, column=col),
        code, line, column, path,
    )
    if not sigs:
        return None
    result = []
    for sig in sigs[:5]:
        params = []
        for param in getattr(sig, "params", []):
            description = ""
            try:
                description = param.description or ""
            except Exception:
                pass
            params.append({"label": param.name, "documentation": description})
        doc = ""
        try:
            doc = sig.docstring(raw=True, fast=True) or ""
        except Exception:
            pass
        result.append({
            "label": sig.name,
            "documentation": {"value": doc[:1200]} if doc else None,
            "parameters": params,
            "activeParameter": max(0, int(getattr(sig, "index", 0) or 0)),
        })
    return {"signatures": result, "activeSignature": 0}


def hover(code: str, line: int, column: int, path: str | None = None) -> str | None:
    hovers = _jedi_call(
        lambda script, ln, col: script.help(line=ln, column=col),
        code, line, column, path,
    )
    if not hovers:
        return None
    h = hovers[0]
    parts: list[str] = []
    htype = getattr(h, "type", None)
    if htype:
        parts.append(f"*{htype}*")
    sig = getattr(h, "description", None) or getattr(h, "signature", None)
    if sig:
        parts.append(f"```python\n{sig}\n```")
    doc = ""
    try:
        doc = h.docstring(raw=True, fast=True) or h.docstring()
    except Exception:
        doc = ""
    if doc:
        parts.append(doc[:2400])
    return "\n\n".join(parts) if parts else None


def definition(code: str, line: int, column: int, path: str | None = None) -> list[dict]:
    defs = _jedi_call(
        lambda script, ln, col: script.goto(
            line=ln, column=col, follow_imports=True, follow_builtin_imports=True
        ),
        code, line, column, path,
    )
    if not defs:
        return []

    results: list[dict] = []
    seen: set[tuple[str | None, int, int]] = set()
    for d in defs[:20]:
        d_line = getattr(d, "line", None)
        if d_line is None:
            continue
        # Jedi n'expose pas toujours .path : pour le buffer courant, path et
        # module_path valent None. Le frontend doit alors naviguer dans le
        # modèle actif au lieu d'ignorer la définition.
        d_path = getattr(d, "path", None) or getattr(d, "module_path", None)
        d_col = (getattr(d, "column", 0) or 0) + 1  # Monaco : 1-based
        key = (str(d_path) if d_path else None, d_line, d_col)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "path": str(d_path) if d_path else None,
            "line": d_line,
            "column": d_col,
        })
    return results


def syntax_check(code: str) -> list[dict]:
    try:
        compile(code, "<buffer>", "exec")
    except SyntaxError as exc:
        line = exc.lineno or 1
        end_line = getattr(exc, "end_lineno", None) or line
        start = exc.offset or 1
        end = getattr(exc, "end_offset", None) or (start + 1)
        if end_line == line and end <= start:
            end = start + 1
        return [{
            "startLineNumber": line,
            "startColumn": start,
            "endLineNumber": end_line,
            "endColumn": end,
            "message": exc.msg or "Erreur de syntaxe",
            "severity": 8,
            "source": "syntax",
        }]
    return []


def diagnose(code: str, path: str | None = None) -> list[dict]:
    """Diagnostics pyflakes, au format Monaco."""
    syntax = syntax_check(code)
    if syntax:
        return syntax

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            pyflakes_check(code, path or "<buffer>", Reporter(out, err))
        except Exception:
            return []

    lines = _lines(code)
    results: list[dict] = []
    seen: set[tuple[int, int, str]] = set()

    for raw in out.getvalue().splitlines():
        match = _PYFLAKES_LINE.match(raw)
        if not match:
            continue
        line = int(match.group("line"))
        col = int(match.group("col"))
        message = match.group("msg").strip()
        if not message or line < 1 or line > len(lines):
            continue
        source_line = lines[line - 1]
        if "# noqa" in source_line.lower():
            continue
        if (line, col, message) in seen:
            continue
        seen.add((line, col, message))

        lowered = message.lower()
        severity = 8 if any(hint in lowered for hint in _ERROR_HINTS) else 4

        start_index = max(0, min(col - 1, len(source_line)))
        end_index = start_index
        if start_index < len(source_line) and (
            source_line[start_index].isalnum() or source_line[start_index] == "_"
        ):
            while end_index < len(source_line) and (
                source_line[end_index].isalnum() or source_line[end_index] == "_"
            ):
                end_index += 1
        else:
            end_index = min(len(source_line), start_index + 1)
        # Monaco : start 1-based, end exclusive 1-based.
        start_column = start_index + 1
        end_column = max(start_column + 1, end_index + 1)

        results.append({
            "startLineNumber": line,
            "startColumn": start_column,
            "endLineNumber": line,
            "endColumn": end_column,
            "message": message,
            "severity": severity,
            "source": "pyflakes",
        })
    return results


def format_code(code: str, max_line_length: int = 88) -> dict:
    try:
        import autopep8
    except ImportError:
        return {"code": code, "changed": False, "error": "autopep8 n'est pas installé"}
    try:
        formatted = autopep8.fix_code(
            code,
            options={
                "aggressive": 0,
                "max_line_length": max_line_length,
                "indent_size": 4,
            },
        )
    except Exception as exc:
        return {"code": code, "changed": False, "error": str(exc)}
    if not formatted.endswith("\n") and code.endswith("\n"):
        formatted += "\n"
    return {"code": formatted, "changed": formatted != code, "error": None}
