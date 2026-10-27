"""Assistant IA optionnel : API compatible OpenAI ou Ollama local."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

from .config import AI_KEY, AI_MODEL, AI_URL, OLLAMA_URL
from .files import ApiError

_SYSTEM = (
    "Tu es un assistant de programmation Python intégré à un IDE mobile. "
    "Réponds en français, de façon concise et concrète. "
    "Quand tu proposes du code, utilise un bloc ```python avec le code complet. "
    "Ne suppose jamais que des bibliothèques non standard sont installées : "
    "précise-le si c'est le cas."
)

_MODE_PROMPTS = {
    "explain": "Explique ce que fait ce code, étape par étape, sans le réécrire.",
    "fix": (
        "Corrige les bugs de ce code. Donne une explication courte, puis le code "
        "complet corrigé dans un bloc ```python."
    ),
    "tests": (
        "Écris des tests unitaires (unittest, sans dépendance externe) pour ce code. "
        "Donne le code complet des tests dans un bloc ```python."
    ),
    "review": (
        "Fais une revue de code : bugs, lisibilité, sécurité, performance. "
        "Propose des corrections concrètes."
    ),
    "generate": "Écris le programme Python demandé, complet, dans un bloc ```python.",
    "optimize": (
        "Optimise ce code sans changer son comportement. Explique brièvement, "
        "puis donne le code complet dans un bloc ```python."
    ),
}


def _ollama_models() -> list[str]:
    try:
        request = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=1.5) as response:
            data = json.load(response)
        return [model["name"] for model in data.get("models", []) if model.get("name")]
    except Exception:
        return []


def _resolve_endpoint() -> tuple[str, str, str, str]:
    """Retourne (url complète, modèle, provider, clé)."""
    if AI_URL:
        url = AI_URL.rstrip("/")
        if not url.endswith("/chat/completions"):
            if url.endswith("/v1"):
                url += "/chat/completions"
            elif "/v1/" not in url:
                url += "/v1/chat/completions"
        return url, AI_MODEL or "default", "custom", AI_KEY

    models = _ollama_models()
    if models:
        model = AI_MODEL if AI_MODEL in models else models[0]
        return f"{OLLAMA_URL}/v1/chat/completions", model, "ollama", ""

    raise ApiError(
        503,
        "Aucun assistant IA configuré. Démarre Ollama localement, ou définis "
        "PYIDE_AI_URL (API compatible OpenAI), PYIDE_AI_MODEL et éventuellement "
        "PYIDE_AI_KEY dans start.sh, puis relance le serveur.",
    )


def status() -> dict:
    try:
        url, model, provider, _ = _resolve_endpoint()
    except ApiError as exc:
        return {
            "available": False,
            "provider": None,
            "model": None,
            "hint": exc.detail,
        }
    return {
        "available": True,
        "provider": provider,
        "model": model,
        "url": url,
        "hint": None,
    }


def _post_json(url: str, payload: dict, key: str) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:800]
        raise ApiError(502, f"Assistant IA : HTTP {exc.code} — {body}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(502, f"Assistant IA injoignable : {exc.reason}") from exc
    except TimeoutError as exc:
        raise ApiError(504, "Assistant IA : délai dépassé") from exc
    except json.JSONDecodeError as exc:
        raise ApiError(502, "Assistant IA : réponse illisible") from exc


def _extract_text(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        pass
    if isinstance(data.get("message"), dict):
        return data["message"].get("content", "")
    if isinstance(data.get("response"), str):
        return data["response"]
    raise ApiError(502, "Assistant IA : réponse sans contenu")


async def ask(mode: str, code: str = "", question: str = "",
              path: str | None = None, selection: str = "") -> dict:
    mode = (mode or "explain").strip()
    if mode not in _MODE_PROMPTS:
        raise ApiError(400, "Mode d'assistant inconnu")
    code = (code or "")[:20000]
    question = (question or "")[:4000]
    selection = (selection or "")[:20000]

    url, model, provider, key = _resolve_endpoint()

    parts = [_MODE_PROMPTS[mode]]
    if path:
        parts.append(f"Fichier : {path}")
    if question:
        parts.append(f"Demande : {question}")
    if selection:
        parts.append(f"Sélection :\n```python\n{selection}\n```")
    elif code:
        parts.append(f"Code :\n```python\n{code}\n```")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)},
        ],
        "temperature": 0.2,
        "stream": False,
    }
    data = await asyncio.to_thread(_post_json, url, payload, key)
    text = _extract_text(data).strip()
    if not text:
        raise ApiError(502, "Assistant IA : réponse vide")
    return {"text": text, "model": model, "provider": provider}
