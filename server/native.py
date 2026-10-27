"""Exécution Python dans le processus de l'application Android (Chaquopy).

Sur un serveur Termux, chaque exécution utilise un vrai sous-processus
(``server/runner.py``). Dans l'app Android, il n'y a pas de ``fork`` : le code
tourne dans un fil d'exécution dédié, avec :

* ``stdout``/``stderr`` redirigés vers l'interface en temps réel ;
* ``input()`` connecté au champ de saisie du terminal (comme PyramIDE) ;
* arrêt coopératif (interruption asynchrone du fil) et délai maximal ;
* console interactive (``>>>``) persistante ;
* canevas graphique ``pyide_gui`` et affichage des figures Matplotlib/Pillow.
"""

from __future__ import annotations

import builtins
import code
import ctypes
import os
import sys
import threading
import time
import traceback
from pathlib import Path

from . import gui
from .config import MAX_OUTPUT_BYTES, MAX_RUN_SECONDS, USER_SITE

try:  # Chaquopy fournit ctypes, mais on reste tolérant.
    import ctypes
except ImportError:  # pragma: no cover - dépend de la build Python
    ctypes = None

GRAPHICS_MISSING = {
    "tkinter": "Tkinter n'est pas disponible dans l'application Android. "
               "Utilise « from pyide_gui import screen » pour dessiner.",
    "pygame": "Pygame n'est pas installé. Installe « pygame-ce » depuis l'onglet "
              "Paquets, ou utilise « pyide_gui » pour un canevas simple.",
    "kivy": "Kivy n'est pas installé dans cette version. Utilise « pyide_gui » "
            "ou installe un paquet pur Python depuis l'onglet Paquets.",
    "turtle": "Le module turtle nécessite Tkinter, absent sur Android. "
              "Le canevas « pyide_gui » offre les mêmes primitives de dessin.",
}


class _MissingToolkitFinder:
    def find_spec(self, fullname, path=None, target=None):  # noqa: D401
        if fullname in GRAPHICS_MISSING:
            raise ModuleNotFoundError(GRAPHICS_MISSING[fullname], name=fullname)
        return None


_finder = _MissingToolkitFinder()


def _install_finder() -> None:
    if _finder not in sys.meta_path:
        sys.meta_path.insert(0, _finder)


def _remove_finder() -> None:
    try:
        sys.meta_path.remove(_finder)
    except ValueError:
        pass


class OutputStream:
    """Flux texte qui pousse les écritures vers l'interface."""

    def __init__(self, session, name: str):
        self.session = session
        self.name = name
        self.encoding = "utf-8"
        self.errors = "replace"

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return False

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            text = str(text)
        self.session._emit_text(self.name, text)
        return len(text)

    def flush(self) -> None:
        return None


class StdinStream:
    """Entrée standard alimentée par le champ de saisie de l'application."""

    def __init__(self, session):
        self.session = session
        self.encoding = "utf-8"
        self.errors = "replace"
        self._buffer = ""
        self._closed = False

    # -- protocole ------------------------------------------------------
    def readable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return True

    def feed(self, data: str) -> None:
        with self.session._input_cond:
            self._buffer += data
            self.session._input_cv.notify_all()

    def eof(self) -> None:
        with self.session._input_cond:
            self._closed = True
            self.session._input_cv.notify_all()

    def readline(self, size: int = -1) -> str:
        while True:
            if self._buffer:
                index = self._buffer.find("\n")
                if index >= 0:
                    line, self._buffer = self._buffer[:index + 1], self._buffer[index + 1:]
                    self.session._emit_line_echo(line)
                    return line
                if size and 0 < size <= len(self._buffer):
                    line, self._buffer = self._buffer[:size], self._buffer[size:]
                    self.session._emit_line_echo(line)
                    return line
            if self._closed or self.session.stopping:
                rest, self._buffer = self._buffer, ""
                return rest
            self.session._request_input()
            with self.session._input_cond:
                if not self._buffer and not self._closed:
                    self.session._input_cv.wait(timeout=0.2)

    def read(self, size: int = -1) -> str:
        chunks: list[str] = []
        while True:
            line = self.readline()
            if not line:
                break
            chunks.append(line)
            if size and 0 < size <= sum(len(c) for c in chunks):
                break
        return "".join(chunks)

    def readlines(self, hint: int = -1) -> list[str]:
        return self.read().splitlines(keepends=True)

    def __iter__(self):
        while True:
            line = self.readline()
            if not line:
                return
            yield line

    def close(self) -> None:
        self.eof()

    def fileno(self) -> int:
        raise OSError("Pas de descripteur de fichier pour l'entrée standard")


def _async_raise(thread_id: int, exc_type) -> None:
    """Interrompt un fil Python bloqué (best effort selon la plateforme)."""
    if ctypes is None or thread_id is None:
        return
    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_id), ctypes.py_object(exc_type)
    )


class NativeSession:
    """Exécution d'un programme Python dans un fil dédié."""

    def __init__(self, emit, code: str | None = None, path: str | None = None,
                 args: list[str] | None = None, timeout: float | None = None,
                 repl: bool = False):
        self.emit = emit
        self.code = code
        self.path = path
        self.args = list(args or [])
        self.repl = repl
        self.timeout = float(timeout or MAX_RUN_SECONDS)
        self.stdin = StdinStream(self)
        self.stdout = OutputStream(self, "stdout")
        self.stderr = OutputStream(self, "stderr")
        self.thread: threading.Thread | None = None
        self.stopping = False
        self.finished = False
        self.exit_code = 0
        self.started_at = 0.0
        self.bytes_written = 0
        self.truncated = False
        self._input_cond = threading.Condition()
        self._input_cv = self._input_cond
        self._input_requested = False
        self._globals: dict = {}
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    # -- événements -----------------------------------------------------
    @property
    def _stopping(self) -> bool:  # compat interne
        return self.stopping

    def _emit_text(self, stream: str, text: str) -> None:
        if not text:
            return
        with self._lock:
            self.bytes_written += len(text.encode("utf-8", "replace"))
            if self.bytes_written > MAX_OUTPUT_BYTES and not self.truncated:
                self.truncated = True
                self.emit({"type": "stderr",
                           "data": "\n… sortie tronquée : exécution arrêtée.\n"})
                self.stop()
                return
        self.emit({"type": stream, "data": text})

    def _emit_line_echo(self, line: str) -> None:
        self.emit({"type": "input_echo", "data": line})

    def _request_input(self) -> None:
        with self._input_cond:
            if self._input_requested or self.stopping or self.finished:
                return
            self._input_requested = True
        self.emit({"type": "need_input"})

    def _clear_input_request(self) -> None:
        with self._input_cond:
            self._input_requested = False

    # -- cycle de vie ---------------------------------------------------
    def start(self) -> None:
        self.started_at = time.monotonic()
        self.thread = threading.Thread(target=self._run, name="pyide-run", daemon=True)
        self.thread.start()
        if self.timeout > 0:
            self._timer = threading.Timer(self.timeout, self._on_timeout)
            self._timer.daemon = True
            self._timer.start()
        self.emit({"type": "started", "repl": self.repl,
                   "cwd": self._cwd(), "pid": None})

    def _on_timeout(self) -> None:
        if self.finished:
            return
        self._emit_text("stderr", f"\n— délai de {self.timeout:.0f} s dépassé —\n")
        self.exit_code = 124
        self.stop()

    def _cwd(self) -> str:
        if self.path:
            return str(Path(self.path).parent)
        from .config import PROJECTS_ROOT
        return str(PROJECTS_ROOT)

    def _prepare(self) -> None:
        os.environ.setdefault("MPLBACKEND", "Agg")
        sys.argv = [self.path or "<console>", *self.args]
        sys.path.insert(0, self._cwd())
        if USER_SITE.is_dir() and str(USER_SITE) not in sys.path:
            sys.path.insert(0, str(USER_SITE))
        gui.set_emitter(self.emit)
        gui.install_hooks()
        _install_finder()

    def _run(self) -> None:
        old_stdout, old_stderr, old_stdin = sys.stdout, sys.stderr, sys.stdin
        old_cwd = os.getcwd()
        sys.stdout, sys.stderr, sys.stdin = self.stdout, self.stderr, self.stdin
        code_value = 0
        try:
            self._prepare()
            try:
                os.chdir(self._cwd())
            except OSError:
                pass
            source = self.code
            if source is None and self.path:
                source = Path(self.path).read_text("utf-8")
            filename = self.path or "<programme>"
            if self.repl:
                self._run_repl()
            elif source is not None:
                exec(compile(source, filename, "exec"), self._make_globals(filename))
            else:
                raise RuntimeError("Aucun code à exécuter")
        except SystemExit as exc:
            code_value = int(exc.code or 0) if str(exc.code or 0).lstrip("-").isdigit() else 0
        except KeyboardInterrupt:
            code_value = 130
            self._emit_text("stderr", "\nKeyboardInterrupt\n")
        except BaseException:
            code_value = 1
            self._emit_text("stderr", traceback.format_exc())
        finally:
            if not self.stopping and code_value == 0:
                code_value = self.exit_code
            self.finished = True
            self._clear_input_request()
            if self._timer:
                self._timer.cancel()
            _remove_finder()
            sys.stdout, sys.stderr, sys.stdin = old_stdout, old_stderr, old_stdin
            try:
                os.chdir(old_cwd)
            except OSError:
                pass
            duration = time.monotonic() - self.started_at
            self.emit({
                "type": "exit", "code": code_value, "duration": duration,
                "timedOut": self.exit_code == 124, "truncated": self.truncated,
                "cancelled": self.stopping,
            })

    def _make_globals(self, filename: str) -> dict:
        globals_dict = {
            "__name__": "__main__",
            "__file__": filename,
            "__builtins__": builtins,
            "__package__": None,
            "__doc__": None,
        }
        self._globals = globals_dict
        return globals_dict

    def _run_repl(self) -> None:
        """Console interactive persistante (comme « python -i »)."""
        globals_dict = self._make_globals(self.path or "<console>")
        console = code.InteractiveConsole(globals_dict, filename="<console>")
        console.runsource("import sys")
        while not self.stopping:
            self._clear_input_request()
            self._request_input()
            line = self.stdin.readline()
            if not line:
                break
            console.push(line.rstrip("\n"))
        self._emit_text("stdout", "\n")

    def send_stdin(self, data: str) -> bool:
        if self.finished:
            return False
        self._clear_input_request()
        self.stdin.feed(data)
        return True

    def close_stdin(self) -> None:
        self.stdin.eof()

    def stop(self) -> None:
        if self.finished or self.stopping:
            return
        self.stopping = True
        self.stdin.eof()
        if self.thread and self.thread.is_alive():
            try:
                _async_raise(self.thread.ident, KeyboardInterrupt)
            except (ValueError, TypeError, SystemError):
                pass
        self.emit({"type": "stopping"})

    def wait(self, timeout: float | None = None) -> dict:
        if self.thread:
            self.thread.join(timeout=timeout)
        return {
            "code": self.exit_code, "finished": self.finished,
            "duration": time.monotonic() - self.started_at,
        }
