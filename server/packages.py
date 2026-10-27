"""Gestion des paquets Python.

Deux moteurs d'installation :

* ``pip`` — serveur Termux/PC : pip list / install / uninstall dans le venv ;
* ``wheels`` — application Android : téléchargement des roues *pures* (py3-none-any)
  depuis PyPI puis installation dans un dossier utilisateur (pas de compilation).

Les paquets graphiques (Tkinter, Pygame, Kivy, Matplotlib…) sont signalés à
l'interface : les programmes qui les utilisent s'exécutent dans l'écran graphique.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import shutil
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from .config import PKG_BACKEND, PYPI_JSON, USER_SITE
from .files import ApiError

_PACKAGE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*"
    r"(\[[A-Za-z0-9._,-]+\])?"
    r"((==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*+!_-]+)?$"
)
_PIP_TIMEOUT = 600
_USER_AGENT = "MobilePyIDE/3.0 (Android; +https://github.com/baa071629-lang/mobile-py-ide)"

# Paquets qui ouvrent une fenêtre et s'affichent dans l'écran graphique.
GRAPHICS_PACKAGES = {
    "pygame": "Pygame",
    "pygame-ce": "Pygame",
    "kivy": "Kivy",
    "matplotlib": "Matplotlib",
    "turtle": "Turtle",
    "tkinter": "Tkinter",
    "pillow": "PIL / Images",
    "pyopengl": "OpenGL",
}

CATALOG = [
    {"name": "requests", "label": "Requests", "category": "Réseau", "graphics": False,
     "description": "Client HTTP simple et complet.", "pure": True},
    {"name": "rich", "label": "Rich", "category": "Terminal", "graphics": False,
     "description": "Tableaux, couleurs et progression dans le terminal.", "pure": True},
    {"name": "pygame-ce", "label": "Pygame", "category": "Graphique", "graphics": True,
     "description": "Jeux 2D : dessin, sons, clavier et tactile (écran graphique).", "pure": False},
    {"name": "numpy", "label": "NumPy", "category": "Sciences", "graphics": False,
     "description": "Calcul vectoriel et matrices (roue native précompilée).", "pure": False},
    {"name": "pillow", "label": "Pillow", "category": "Graphique", "graphics": True,
     "description": "Manipulation d'images (PIL).", "pure": False},
    {"name": "matplotlib", "label": "Matplotlib", "category": "Graphique", "graphics": True,
     "description": "Tracés et graphiques scientifiques.", "pure": False},
    {"name": "kivy", "label": "Kivy", "category": "Graphique", "graphics": True,
     "description": "Interfaces tactiles multi-plateformes.", "pure": False},
    {"name": "beautifulsoup4", "label": "BeautifulSoup", "category": "Web", "graphics": False,
     "description": "Analyse de pages HTML.", "pure": True},
    {"name": "pyyaml", "label": "PyYAML", "category": "Données", "graphics": False,
     "description": "Lecture et écriture YAML.", "pure": False},
    {"name": "pandas", "label": "Pandas", "category": "Sciences", "graphics": False,
     "description": "Tableaux de données (roues natives requises).", "pure": False},
    {"name": "flask", "label": "Flask", "category": "Web", "graphics": False,
     "description": "Micro-framework web (serveur local).", "pure": True},
    {"name": "pytest", "label": "Pytest", "category": "Outils", "graphics": False,
     "description": "Tests unitaires concis.", "pure": True},
]


def _clean_spec(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) > 200 or not _PACKAGE_RE.match(value):
        raise ApiError(400, "Nom de paquet invalide")
    return value


def _base_name(spec: str) -> str:
    return re.split(r"[\[=<>!~ ]", spec.strip(), maxsplit=1)[0].lower()


def _is_graphics(name: str) -> bool:
    return _base_name(name).replace("_", "-") in GRAPHICS_PACKAGES


# ---------- moteur pip (serveur) ----------

async def _pip(args: list[str], timeout: int = _PIP_TIMEOUT) -> tuple[int, str]:
    env = os.environ.copy()
    env.update({
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
        "PYTHONUNBUFFERED": "1",
    })
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pip", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    try:
        data, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            proc.kill()
        await proc.wait()
        return 124, f"Timeout : pip a dépassé {timeout} s."
    text = data.decode("utf-8", "replace")
    return proc.returncode or 0, text[-40000:]


async def _pip_list() -> dict:
    code, output = await _pip(
        ["list", "--format=json", "--disable-pip-version-check"], timeout=90
    )
    if code != 0:
        return {"packages": [], "error": output}
    try:
        packages = json.loads(output)
    except json.JSONDecodeError:
        return {"packages": [], "error": output}
    return {"packages": packages, "error": None}


# ---------- moteur roues pures (Android / sans pip) ----------

def _installed_index() -> dict:
    try:
        raw = json.loads((USER_SITE / ".installed.json").read_text("utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_index(index: dict) -> None:
    try:
        USER_SITE.mkdir(parents=True, exist_ok=True)
        (USER_SITE / ".installed.json").write_text(
            json.dumps(index, indent=2, sort_keys=True), "utf-8"
        )
    except OSError:
        pass


def _scan_user_site() -> list[dict]:
    index = _installed_index()
    packages: list[dict] = []
    if not USER_SITE.is_dir():
        return packages
    for dist in sorted(USER_SITE.glob("*.dist-info")):
        meta = dist / "METADATA"
        name, version = dist.name.rsplit("-", 2)[0], ""
        try:
            for line in meta.read_text("utf-8", "replace").splitlines():
                if line.startswith("Name: "):
                    name = line[6:].strip()
                elif line.startswith("Version: "):
                    version = line[9:].strip()
        except OSError:
            pass
        record = index.get(dist.name, {})
        packages.append({
            "name": name,
            "version": version,
            "source": "wheels",
            "graphics": _is_graphics(name),
            "files": record.get("files", []),
            "location": str(USER_SITE),
        })
    packages.sort(key=lambda item: item["name"].lower())
    return packages


def _ensure_user_site() -> None:
    try:
        USER_SITE.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ApiError(500, f"Dossier de paquets inaccessible : {exc}") from exc
    if str(USER_SITE) not in sys.path:
        sys.path.insert(0, str(USER_SITE))


def _http_json(url: str, timeout: int = 30) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT,
                                                   "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ApiError(404, "Paquet introuvable sur PyPI") from exc
        raise ApiError(502, f"PyPI a répondu {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ApiError(502, f"PyPI injoignable : {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ApiError(502, "Réponse PyPI illisible") from exc


def package_metadata(spec: str) -> dict:
    spec = _clean_spec(spec)
    base = _base_name(spec)
    version = None
    if "==" in spec:
        version = spec.split("==", 1)[1].strip()
    url = f"{PYPI_JSON}/{base}/json" if not version else f"{PYPI_JSON}/{base}/{version}/json"
    data = _http_json(url)
    info = data.get("info", {})
    files = data.get("urls", []) or []
    wheels = [f for f in files if f.get("filename", "").endswith(".whl")]
    pure = any(f.get("filename", "").endswith("py3-none-any.whl") for f in wheels)
    return {
        "name": info.get("name", base),
        "version": info.get("version"),
        "summary": info.get("summary") or "",
        "author": info.get("author") or info.get("author_email") or "",
        "home": info.get("home_page") or (info.get("project_urls") or {}).get("Homepage", ""),
        "license": info.get("license") or "",
        "pure": pure,
        "graphics": _is_graphics(base),
        "wheels": [f.get("filename") for f in wheels][:8],
        "requiresPython": info.get("requires_python") or "",
        "url": data.get("info", {}).get("package_url", f"https://pypi.org/project/{base}/"),
    }


def search_pypi(query: str, limit: int = 25) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    results: list[dict] = []
    seen: set[str] = set()

    # 1) Correspondance exacte / proche via l'API JSON (pas de HTML scraping).
    try:
        meta = package_metadata(query)
        results.append(meta)
        seen.add(meta["name"].lower())
    except ApiError:
        pass

    # 2) Recherche plein texte : page de recherche PyPI (HTML simple).
    try:
        request = urllib.request.Request(
            f"https://pypi.org/search/?q={urllib.parse.quote(query)}",
            headers={"User-Agent": _USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", "replace")
        pattern = re.compile(
            r'package-snippet__name">([^<]+)</span>.*?'
            r'package-snippet__version">([^<]+)</span>.*?'
            r'package-snippet__description">([^<]*)<',
            re.S,
        )
        for name, version, description in pattern.findall(html)[:limit]:
            key = name.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "name": name.strip(), "version": version.strip(),
                "summary": description.strip()[:200], "pure": False,
                "graphics": _is_graphics(name), "source": "pypi",
            })
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass
    return results[:limit]


def _install_wheel(spec: str, upgrade: bool = False) -> tuple[int, str]:
    _ensure_user_site()
    spec = _clean_spec(spec)
    base = _base_name(spec)
    log: list[str] = []

    index = _installed_index()
    existing = next(
        (pid for pid in index if pid.lower().startswith(base.replace("-", "_") + "-")), None
    )
    if existing and not upgrade:
        return 1, (
            f"{base} est déjà installé. Utilise « Mettre à jour » pour changer de version.\n"
        )

    meta = package_metadata(spec)
    version = meta.get("version")
    if not version:
        raise ApiError(404, "Version introuvable")

    data = _http_json(f"{PYPI_JSON}/{base}/{version}/json")
    files = [f for f in data.get("urls", []) if f.get("filename", "").endswith(".whl")]
    pick = None
    for candidate in files:
        if candidate["filename"].endswith("py3-none-any.whl"):
            pick = candidate
            break
    if pick is None:
        raise ApiError(
            409,
            f"{meta['name']} {version} n'a pas de roue pure Python (py3-none-any).\n"
            "La compilation native n'est pas disponible sur Android : choisis un "
            "paquet « roue précompilée » du catalogue ou un paquet pur Python.",
        )

    log.append(f"Récupération de {pick['filename']} ({pick.get('size', 0) // 1024} Ko)…")
    request = urllib.request.Request(
        pick["url"], headers={"User-Agent": _USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            blob = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ApiError(502, f"Téléchargement impossible : {exc}") from exc

    added: list[str] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise ApiError(502, "Roue corrompue") from exc

    with archive:
        for member in archive.namelist():
            if member.endswith("/"):
                continue
            # Empêche toute écriture hors du dossier utilisateur.
            target = (USER_SITE / member).resolve()
            if USER_SITE.resolve() not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(target, "wb") as destination:
                shutil.copyfileobj(source, destination)
            added.append(member)

    dist_info = next((m.split("/")[0] for m in added if ".dist-info/" in m), None)
    if dist_info:
        index[dist_info] = {
            "name": meta["name"], "version": version,
            "installedAt": int(time.time() * 1000),
            "files": added, "wheel": pick["filename"],
        }
        _write_index(index)
    log.append(f"{meta['name']} {version} installé ({len(added)} fichiers).")
    return 0, "\n".join(log)


def _uninstall_wheels(name: str) -> tuple[int, str]:
    base = _base_name(name).lower().replace("-", "_")
    index = _installed_index()
    removed = 0
    for dist, record in list(index.items()):
        dist_name = str(record.get("name", "")).lower().replace("-", "_")
        if dist_name != base:
            continue
        for member in record.get("files", []):
            target = USER_SITE / member
            try:
                if target.is_file():
                    target.unlink()
                    removed += 1
            except OSError:
                pass
        index.pop(dist, None)
    _write_index(index)
    # Nettoie les dossiers vides.
    if USER_SITE.is_dir():
        for child in USER_SITE.iterdir():
            if child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass
    if not removed:
        return 1, f"{name} n'est pas installé par Mobile Py IDE."
    return 0, f"{name} désinstallé ({removed} fichiers supprimés)."


# ---------- API publique ----------

async def list_packages() -> dict:
    if PKG_BACKEND == "wheels":
        packages = _scan_user_site()
        return {
            "packages": packages,
            "python": sys.version.split()[0],
            "backend": "wheels",
            "userSite": str(USER_SITE),
            "error": None,
        }

    result = await _pip_list()
    packages = result["packages"]
    for package in packages:
        package["graphics"] = _is_graphics(package.get("name", ""))
    return {
        "packages": packages,
        "python": sys.version.split()[0],
        "backend": "pip",
        "userSite": str(USER_SITE),
        "error": result.get("error"),
    }


async def install_package(spec: str, upgrade: bool = False) -> dict:
    spec = _clean_spec(spec)
    if PKG_BACKEND == "wheels":
        try:
            code, output = await asyncio.to_thread(_install_wheel, spec, upgrade)
        except ApiError as exc:
            return {"ok": False, "code": exc.status_code, "output": exc.detail}
        return {"ok": code == 0, "code": code, "output": output, "backend": "wheels"}

    args = ["install", "--no-input", spec]
    if upgrade:
        args.insert(1, "--upgrade")
    code, output = await _pip(args)
    return {"ok": code == 0, "code": code, "output": output, "backend": "pip"}


async def uninstall_package(name: str) -> dict:
    if "[" in name or "==" in name or ">" in name or "<" in name:
        raise ApiError(400, "Indique uniquement le nom du paquet")
    name = _clean_spec(name)
    if PKG_BACKEND == "wheels":
        code, output = await asyncio.to_thread(_uninstall_wheels, name)
        return {"ok": code == 0, "code": code, "output": output, "backend": "wheels"}
    code, output = await _pip(["uninstall", "-y", name])
    return {"ok": code == 0, "code": code, "output": output, "backend": "pip"}


def catalog() -> list[dict]:
    installed = {p["name"].lower() for p in _scan_user_site()}
    items = []
    for item in CATALOG:
        entry = dict(item)
        entry["installed"] = item["name"].lower() in installed
        entry["supported"] = PKG_BACKEND != "wheels" or item.get("pure", False)
        items.append(entry)
    return items


async def search(query: str) -> list[dict]:
    return await asyncio.to_thread(search_pypi, query)


async def metadata(spec: str) -> dict:
    return await asyncio.to_thread(package_metadata, spec)
