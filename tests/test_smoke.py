"""Tests de fumée HTTP/WebSocket de Mobile Py IDE.

Démarre un vrai serveur isolé (port libre, dossier temporaire, jeton obligatoire)
puis vérifie les parcours essentiels. Lancement depuis la racine du projet :

    .venv/bin/python -m unittest discover -s tests -v
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "test-secret"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Server:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pyide-test-")
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.log_path = Path(self.temp.name) / "server.log"
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        env = os.environ.copy()
        env.update({
            "PYIDE_HOST": "127.0.0.1",
            "PYIDE_PORT": str(self.port),
            "PYIDE_PROJECTS": self.temp.name,
            "PYIDE_TOKEN": TOKEN,
            "PYIDE_RUN_TIMEOUT": "10",
        })
        self.log = self.log_path.open("wb")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "server.app"],
            cwd=str(ROOT),
            env=env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                self.log.close()
                raise RuntimeError(
                    f"Serveur arrêté au démarrage :\n{self.log_path.read_text(errors='replace')}"
                )
            try:
                with urllib.request.urlopen(f"{self.base}/api/health", timeout=1) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(0.15)
        raise RuntimeError("Le serveur n'a pas démarré dans le délai imparti")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        try:
            self.log.close()
        except Exception:
            pass
        self.temp.cleanup()


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server()
        cls.server.start()
        cls.base = cls.server.base

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    # ---------- helpers ----------

    def request(self, path, method="GET", data=None, token=TOKEN, raw=False):
        headers = {}
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["X-Pyide-Token"] = token
        request = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read()
                if raw:
                    return response.status, payload.decode("utf-8", "replace")
                return response.status, json.loads(payload)
        except urllib.error.HTTPError as exc:
            try:
                payload = exc.read().decode("utf-8", "replace")
                try:
                    content = json.loads(payload)
                except json.JSONDecodeError:
                    content = payload
                return exc.code, content
            finally:
                exc.close()

    def save(self, path, content):
        status, data = self.request("/api/file", "POST", {"path": path, "content": content})
        self.assertEqual(status, 200, data)
        return data

    # ---------- santé, authentification, statique ----------

    def test_health_is_public_and_auth_required(self):
        status, health = self.request("/api/health", token=None)
        self.assertEqual(status, 200)
        self.assertTrue(health["ok"])
        self.assertTrue(health["authRequired"])

        status, error = self.request("/api/tree", token=None)
        self.assertEqual(status, 401)
        self.assertIn("Jeton", error["detail"])

        status, error = self.request("/api/tree", token="mauvais-jeton")
        self.assertEqual(status, 401)

        status, tree = self.request("/api/tree")
        self.assertEqual(status, 200)
        self.assertTrue(tree["dir"].startswith("/"), tree["dir"])
        self.assertTrue(tree["places"] if "places" in tree else True)

    def test_static_files_and_manifest(self):
        status, html = self.request("/", token=None, raw=True)
        self.assertEqual(status, 200)
        self.assertIn("Mobile Py IDE", html)
        self.assertIn("monaco", html.lower())

        status, manifest = self.request("/static/manifest.webmanifest", token=None)
        self.assertEqual(status, 200)
        self.assertEqual(manifest["display"], "standalone")

        status, _ = self.request("/static/vendor/monaco/vs/loader.js", token=None, raw=True)
        self.assertEqual(status, 200)

    # ---------- fichiers ----------

    def test_file_crud_search_and_traversal(self):
        status, missing = self.request("/api/exists?path=absent.py")
        self.assertEqual(status, 200)
        self.assertFalse(missing["exists"])

        saved = self.save("dossier/hello.py", 'print("bonjour")\n')
        self.assertTrue(saved["path"].endswith("/dossier/hello.py"), saved["path"])
        self.assertEqual(saved["rel"], "dossier/hello.py")

        status, exists = self.request("/api/exists?path=dossier/hello.py")
        self.assertTrue(exists["exists"])

        status, data = self.request("/api/file?path=dossier/hello.py")
        self.assertEqual(status, 200)
        self.assertEqual(data["content"], 'print("bonjour")\n')

        status, listing = self.request("/api/tree?dir=dossier")
        self.assertEqual(status, 200)
        self.assertIn("hello.py", [entry["name"] for entry in listing["entries"]])

        status, found = self.request("/api/search?q=bonjour")
        self.assertEqual(status, 200)
        self.assertTrue(any(item["path"].endswith("/dossier/hello.py") for item in found["results"]))
        self.assertTrue(found["results"][0]["line"] >= 1)

        status, renamed = self.request("/api/rename", "POST", {
            "path": "dossier/hello.py", "newPath": "dossier/salut.py",
        })
        self.assertEqual(status, 200, renamed)

        status, error = self.request("/api/file?path=../evasion.py")
        self.assertIn(status, (400, 403))

        status, deleted = self.request("/api/delete", "POST", {"path": "dossier/salut.py"})
        self.assertEqual(status, 200, deleted)

    # ---------- analyse / formatage ----------

    def test_analysis_and_format(self):
        code = "import os\nx = unknown\n"
        status, diag = self.request("/api/diagnose", "POST", {"code": code})
        self.assertEqual(status, 200)
        messages = " ".join(marker["message"] for marker in diag["markers"])
        self.assertIn("unknown", messages)
        self.assertIn("unused", messages)

        status, completion = self.request("/api/complete", "POST", {
            "code": "import os\nos.getc", "line": 2, "column": 7,
        })
        self.assertEqual(status, 200)
        labels = [item["label"] for item in completion["items"]]
        self.assertIn("getcwd", labels)

        status, hover = self.request("/api/hover", "POST", {
            "code": "import math\nmath.sqrt(4)\n", "line": 2, "column": 6,
        })
        self.assertEqual(status, 200)
        self.assertIn("sqrt", hover["markdown"])

        definition_code = "def cible():\n    return 1\n\nvaleur = cible()\n"
        status, definition = self.request("/api/definition", "POST", {
            "code": definition_code, "line": 4, "column": 10,
        })
        self.assertEqual(status, 200)
        self.assertTrue(definition["locations"])
        self.assertEqual(definition["locations"][0]["line"], 1)

        status, formatted = self.request("/api/format", "POST", {"code": "x=1\nprint( x )\n"})
        self.assertEqual(status, 200)
        self.assertTrue(formatted["changed"])
        self.assertIn("x = 1", formatted["code"])

    # ---------- exécution ----------

    def test_run_http_output_and_args(self):
        status, result = self.request("/api/run", "POST", {"code": "print(42)\n", "timeout": 10})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["stdout"].strip(), "42")
        self.assertEqual(result["code"], 0)

        status, result = self.request("/api/run", "POST", {
            "code": "import sys\nprint(sys.argv[1:])\n",
            "args": ["--message", "bonjour monde"],
            "timeout": 10,
        })
        self.assertEqual(status, 200, result)
        self.assertIn("['--message', 'bonjour monde']", result["stdout"])

    def test_run_timeout(self):
        started = time.monotonic()
        status, result = self.request("/api/run", "POST", {
            "code": "import time\ntime.sleep(5)\n", "timeout": 1,
        })
        self.assertEqual(status, 200, result)
        self.assertEqual(result["code"], 124)
        self.assertTrue(result["timedOut"])
        self.assertLess(time.monotonic() - started, 8)

    def test_websocket_stdin_and_token(self):
        async def scenario():
            url = f"ws://127.0.0.1:{self.server.port}/ws/run?token={TOKEN}"
            async with websockets.connect(url) as socket:
                await socket.send(json.dumps({
                    "type": "start",
                    "code": "nom = input('nom ? ')\nprint('salut', nom)\n",
                    "timeout": 10,
                }))
                events = []
                while True:
                    message = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
                    events.append(message)
                    if message.get("type") == "started":
                        await socket.send(json.dumps({"type": "stdin", "data": "Ada\n"}))
                    if message.get("type") in {"exit", "error"}:
                        break
                return events

        events = asyncio.run(scenario())
        types = [event["type"] for event in events]
        self.assertIn("started", types)
        self.assertIn("exit", types)
        stdout = "".join(event.get("data", "") for event in events if event["type"] == "stdout")
        self.assertIn("salut Ada", stdout)
        self.assertEqual(next(e for e in events if e["type"] == "exit")["code"], 0)

        async def refused():
            with self.assertRaises(Exception):
                async with websockets.connect(f"ws://127.0.0.1:{self.server.port}/ws/run"):
                    pass

        asyncio.run(refused())


if __name__ == "__main__":
    unittest.main()
