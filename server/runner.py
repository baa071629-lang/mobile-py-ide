"""Exécution Python : processus isolé, streaming, stdin, stop, timeout."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from .config import MAX_OUTPUT_BYTES, MAX_RUN_SECONDS, PROJECTS_ROOT, USER_SITE

APP_DIR = Path(__file__).resolve().parent.parent
SHIMS_DIR = APP_DIR / "shims"
from .files import ApiError, resolve_for_run

OutputCallback = Callable[[str, str], Awaitable[None]]


@dataclass
class RunSpec:
    cmd: list[str]
    cwd: Path
    timeout: float
    temp_file: Path | None = None
    gfx_file: Path | None = None
    gfx_in: Path | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class RunResult:
    stdout: str
    stderr: str
    code: int
    duration: float
    timed_out: bool = False
    truncated: bool = False


def _validate_args(args: list[str] | None) -> list[str]:
    if not args:
        return []
    if not isinstance(args, list) or len(args) > 32:
        raise ApiError(400, "Arguments invalides")
    clean = []
    for arg in args:
        if not isinstance(arg, str) or len(arg) > 500 or "\x00" in arg:
            raise ApiError(400, "Argument invalide")
        clean.append(arg)
    return clean


def build_spec(code: str | None, path: str | None, args: list[str] | None = None,
               timeout: float | None = None, repl: bool = False) -> RunSpec:
    target, cwd = resolve_for_run(path)
    args = _validate_args(args)
    if timeout is None:
        timeout = MAX_RUN_SECONDS
    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        timeout = MAX_RUN_SECONDS
    timeout = max(1.0, min(timeout, 300.0))

    temp_file: Path | None = None
    cmd: list[str]

    if repl:
        if code is not None and code.strip():
            temp_file = cwd / f".pyide-run-{uuid.uuid4().hex[:10]}.py"
            temp_file.write_text(code, encoding="utf-8")
            cmd = [sys.executable, "-u", "-q", "-i", str(temp_file)]
        else:
            cmd = [sys.executable, "-u", "-q", "-i"]
    elif code is not None:
        temp_file = cwd / f".pyide-run-{uuid.uuid4().hex[:10]}.py"
        temp_file.write_text(code, encoding="utf-8")
        cmd = [sys.executable, "-u", str(temp_file), *args]
    elif target is not None:
        cmd = [sys.executable, "-u", str(target), *args]
    else:
        raise ApiError(400, "Aucun code ou fichier à exécuter")

    env = os.environ.copy()
    gfx_file = cwd / f".pyide-gfx-{uuid.uuid4().hex[:10]}.jsonl"
    gfx_in = cwd / f".pyide-gfxin-{uuid.uuid4().hex[:10]}.jsonl"
    paths = [str(APP_DIR)]
    if USER_SITE.is_dir():
        paths.insert(0, str(USER_SITE))
    existing = env.get("PYTHONPATH", "")
    if existing:
        paths.append(existing)
    env.update({
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "TERM": "xterm-256color",
        "MPLBACKEND": env.get("MPLBACKEND", "Agg"),
        "PYTHONPATH": os.pathsep.join(paths),
        "PYIDE_GFX_FILE": str(gfx_file),
        "PYIDE_GFX_IN": str(gfx_in),
        "PYIDE_SHIMS": str(SHIMS_DIR),
        "PYIDE_IN_IDE": "1",
    })
    env.pop("PYTHONSTARTUP", None)

    return RunSpec(cmd=cmd, cwd=cwd, timeout=timeout, temp_file=temp_file,
                   gfx_file=gfx_file, gfx_in=gfx_in, env=env)


class RunSession:
    """Un processus Python + ses flux, utilisable en HTTP ou en WebSocket."""

    def __init__(self, spec: RunSpec):
        self.spec = spec
        self.proc: asyncio.subprocess.Process | None = None
        self.output_bytes = 0
        self.truncated = False
        self.started_at = 0.0
        self._pumps: list[asyncio.Task] = []
        self._on_output: OutputCallback | None = None
        self._stdin_open = True

    async def start(self, on_output: OutputCallback | None = None) -> None:
        self._on_output = on_output
        self.started_at = time.monotonic()
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *self.spec.cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.spec.cwd),
                env=self.spec.env,
                start_new_session=True,
                limit=1024 * 1024,
            )
        except OSError as exc:
            self._cleanup_temp()
            raise ApiError(500, f"Lancement impossible : {exc}") from exc

        assert self.proc.stdout is not None and self.proc.stderr is not None
        self._pumps = [
            asyncio.create_task(self._pump(self.proc.stdout, "stdout")),
            asyncio.create_task(self._pump(self.proc.stderr, "stderr")),
        ]

    async def _emit(self, stream: str, text: str) -> None:
        if not text:
            return
        if self._on_output is not None:
            await self._on_output(stream, text)

    async def _pump(self, stream: asyncio.StreamReader, name: str) -> None:
        while True:
            try:
                chunk = await stream.read(4096)
            except (asyncio.LimitOverrunError, ValueError):
                chunk = await stream.read(4096)
            if not chunk:
                break
            text = chunk.decode("utf-8", "replace")
            self.output_bytes += len(chunk)
            if self.output_bytes > MAX_OUTPUT_BYTES:
                if not self.truncated:
                    self.truncated = True
                    await self._emit(name, "\n… sortie tronquée : processus arrêté.\n")
                    asyncio.create_task(self.stop())
                return
            await self._emit(name, text)

    async def send_stdin(self, data: str) -> bool:
        if not self.proc or not self.proc.stdin or self.proc.stdin.is_closing():
            return False
        try:
            self.proc.stdin.write(data.encode("utf-8"))
            await self.proc.stdin.drain()
            return True
        except (BrokenPipeError, ConnectionResetError):
            self._stdin_open = False
            return False

    async def close_stdin(self) -> None:
        if self.proc and self.proc.stdin and not self.proc.stdin.is_closing():
            try:
                self.proc.stdin.close()
                await self.proc.stdin.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
        self._stdin_open = False

    async def stop(self) -> None:
        if not self.proc or self.proc.returncode is not None:
            return
        self._terminate(signal.SIGTERM)
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=1.5)
        except asyncio.TimeoutError:
            self._terminate(signal.SIGKILL)
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    def _terminate(self, sig: int) -> None:
        if not self.proc:
            return
        try:
            os.killpg(os.getpgid(self.proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                self.proc.terminate() if sig == signal.SIGTERM else self.proc.kill()
            except ProcessLookupError:
                pass

    async def wait(self) -> RunResult:
        if not self.proc:
            raise ApiError(500, "Processus non démarré")
        timed_out = False
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=self.spec.timeout)
        except asyncio.TimeoutError:
            timed_out = True
            await self.stop()

        if self._pumps:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._pumps, return_exceptions=True), timeout=2
                )
            except asyncio.TimeoutError:
                for task in self._pumps:
                    task.cancel()

        code = self.proc.returncode
        if code is None:
            code = 124 if timed_out else -1
        elif timed_out:
            code = 124
        duration = time.monotonic() - self.started_at
        # Le script temporaire peut partir, mais les fichiers graphiques restent :
        # le relais lit les dernières images juste après la sortie du programme.
        self._cleanup_script()
        if self.proc.stdin and not self.proc.stdin.is_closing():
            try:
                self.proc.stdin.close()
            except (BrokenPipeError, ConnectionResetError):
                pass
        return RunResult(
            stdout="", stderr="", code=code, duration=duration,
            timed_out=timed_out, truncated=self.truncated,
        )

    def cleanup(self) -> None:
        """Supprime les fichiers temporaires (appelé une fois le relais fini)."""
        self._cleanup_temp()

    def _cleanup_temp(self) -> None:
        self._cleanup_script()
        self._cleanup_gfx()

    def _cleanup_script(self) -> None:
        if self.spec.temp_file:
            try:
                self.spec.temp_file.unlink(missing_ok=True)
            except OSError:
                pass
            self.spec.temp_file = None

    def _cleanup_gfx(self) -> None:
        for attr in ("gfx_file", "gfx_in"):
            path = getattr(self.spec, attr)
            if path is None:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            setattr(self.spec, attr, None)


async def run_capture(code: str | None, path: str | None, stdin: str | None = None,
                      args: list[str] | None = None, timeout: float | None = None,
                      repl: bool = False) -> RunResult:
    spec = build_spec(code, path, args=args, timeout=timeout, repl=repl)
    session = RunSession(spec)
    out: list[str] = []
    err: list[str] = []

    async def collect(stream: str, text: str) -> None:
        (out if stream == "stdout" else err).append(text)

    await session.start(collect)
    if stdin:
        await session.send_stdin(stdin)
    await session.close_stdin()
    result = await session.wait()
    session.cleanup()
    result.stdout = "".join(out)
    result.stderr = "".join(err)
    return result
