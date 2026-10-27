"""Gestion des paquets Python du venv (pip list / install / uninstall)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import sys

from .files import ApiError

_PACKAGE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*"
    r"(\[[A-Za-z0-9._,-]+\])?"
    r"((==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*+!_-]+)?$"
)
_PIP_TIMEOUT = 300


def _clean_spec(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) > 200 or not _PACKAGE_RE.match(value):
        raise ApiError(400, "Nom de paquet invalide")
    return value


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
    return proc.returncode or 0, text[-20000:]


async def list_packages() -> dict:
    code, output = await _pip([
        "list", "--format=json", "--disable-pip-version-check",
    ], timeout=60)
    if code != 0:
        return {"packages": [], "python": sys.version.split()[0], "error": output}
    try:
        packages = json.loads(output)
    except json.JSONDecodeError:
        return {"packages": [], "python": sys.version.split()[0], "error": output}
    packages.sort(key=lambda item: item.get("name", "").lower())
    return {"packages": packages, "python": sys.version.split()[0], "error": None}


async def install_package(spec: str, upgrade: bool = False) -> dict:
    spec = _clean_spec(spec)
    args = ["install", "--no-input", spec]
    if upgrade:
        args.insert(1, "--upgrade")
    code, output = await _pip(args)
    return {"ok": code == 0, "code": code, "output": output}


async def uninstall_package(name: str) -> dict:
    if "[" in name or "==" in name or ">" in name or "<" in name:
        raise ApiError(400, "Indique uniquement le nom du paquet")
    name = _clean_spec(name)
    code, output = await _pip(["uninstall", "-y", name])
    return {"ok": code == 0, "code": code, "output": output}
