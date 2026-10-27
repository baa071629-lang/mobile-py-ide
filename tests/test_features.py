"""Tests des nouveautés 3.0 : dossiers multiples, paquets, entrée interactive.

Lancement : ``.venv/bin/python -m pytest tests -q``
"""

from __future__ import annotations

import json
import urllib.parse
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_smoke import TOKEN, Server  # noqa: E402

ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server()
        cls.server.start()
        cls.base = cls.server.base
        cls.root = Path(cls.server.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def request(self, path, method="GET", data=None):
        headers = {}
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        headers["X-Pyide-Token"] = TOKEN
        request = urllib.request.Request(
            self.base + path, data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            try:
                return exc.code, json.loads(payload)
            except json.JSONDecodeError:
                return exc.code, {"detail": payload.decode("utf-8", "replace")}


class PlacesTestCase(ServerTestCase):
    def test_places_expose_le_dossier_projets(self):
        status, data = self.request("/api/places")
        self.assertEqual(status, 200, data)
        paths = [place["path"] for place in data["places"]]
        self.assertIn(str(self.root.resolve()), paths)
        self.assertTrue(any(place["isProjects"] for place in data["places"]))

    def test_ajout_puis_retrait_d_un_dossier(self):
        extra = self.root / "mes-projets"
        extra.mkdir(exist_ok=True)
        status, data = self.request(
            "/api/places/add", "POST", {"path": str(extra), "label": "Mes projets"}
        )
        self.assertEqual(status, 200, data)
        place = data["place"]
        self.assertEqual(place["label"], "Mes projets")

        status, tree = self.request(f"/api/tree?dir={urllib.parse.quote(str(extra))}")
        self.assertEqual(status, 200, tree)
        self.assertEqual(tree["dir"], str(extra.resolve()))

        status, removed = self.request("/api/places/remove", "POST", {"id": place["id"]})
        self.assertEqual(status, 200, removed)
        self.assertTrue(removed["ok"])

    def test_chemins_absolus_et_confinement(self):
        target = self.root / "abs" / "script.py"
        status, saved = self.request(
            "/api/file", "POST", {"path": str(target), "content": "print(1)\n"}
        )
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved["path"], str(target.resolve()))
        self.assertEqual(saved["rel"], "abs/script.py")

        status, read = self.request(f"/api/file?path={urllib.parse.quote(str(target))}")
        self.assertEqual(status, 200, read)
        self.assertEqual(read["content"], "print(1)\n")

        status, error = self.request("/api/file?path=/etc/passwd")
        self.assertEqual(status, 403)
        self.assertIn("autoris", error["detail"].lower())

    def test_catalogue_de_paquets(self):
        status, data = self.request("/api/packages/catalog")
        self.assertEqual(status, 200, data)
        names = [item["name"] for item in data["catalog"]]
        self.assertIn("requests", names)
        self.assertIn(data["backend"], {"pip", "wheels"})
        pygame = next(item for item in data["catalog"] if item["name"] == "pygame-ce")
        self.assertTrue(pygame["graphics"])

    def test_execution_avec_entree_standard(self):
        status, result = self.request("/api/run", "POST", {
            "code": 'nom = input("nom ? ")\nprint("salut", nom)\n',
            "stdin": "Awa\n",
            "timeout": 15,
        })
        self.assertEqual(status, 200, result)
        self.assertEqual(result["code"], 0)
        self.assertIn("salut Awa", result["stdout"])

    def test_import_d_un_fichier_externe(self):
        source = self.root / "externe.txt"
        source.write_text("bonjour", encoding="utf-8")
        destination = self.root / "projet"
        destination.mkdir(exist_ok=True)
        status, data = self.request("/api/import", "POST", {
            "source": str(source), "dir": str(destination),
        })
        self.assertEqual(status, 200, data)
        self.assertTrue((destination / "externe.txt").is_file())


class NativeSessionTestCase(unittest.TestCase):
    """Exécution embarquée utilisée par l'application Android."""

    def run_code(self, code, *, repl=False, feed=None, wait=1.0):
        from server import native

        events = []
        session = native.NativeSession(events.append, code=code, timeout=8, repl=repl)
        session.start()
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and not session.finished:
            time.sleep(0.02)
        if feed:
            session.send_stdin(feed)
        for _ in range(120):
            if session.finished:
                break
            time.sleep(0.05)
        session.stop()
        return events

    def test_input_et_sortie(self):
        events = self.run_code('nom = input("Qui ? ")\nprint("hello", nom)\n', feed="Sam\n")
        text = "".join(event.get("data", "") for event in events if event["type"] == "stdout")
        self.assertIn("Qui ? ", text)
        self.assertIn("hello Sam", text)
        self.assertTrue(any(event["type"] == "need_input" for event in events))
        self.assertTrue(any(event["type"] == "exit" for event in events))

    def test_console_interactive(self):
        events = self.run_code("", repl=True, feed="2+3\n", wait=0.4)
        text = "".join(event.get("data", "") for event in events if event["type"] == "stdout")
        self.assertIn("5", text)

    def test_canevas_graphique(self):
        events = self.run_code(
            'from pyide_gui import screen\ns = screen(320, 200, "#000000")\n'
            's.circle(10, 10, 5, "#ff0000")\ns.present()\n'
        )
        ops = [event.get("op") for event in events if event["type"] == "gfx"]
        self.assertIn("open", ops)
        self.assertIn("circle", ops)
        self.assertIn("present", ops)

    def test_erreur_affichee(self):
        events = self.run_code("1/0\n")
        text = "".join(event.get("data", "") for event in events if event["type"] == "stderr")
        self.assertIn("ZeroDivisionError", text)
        exit_event = next(event for event in events if event["type"] == "exit")
        self.assertNotEqual(exit_event["code"], 0)


if __name__ == "__main__":
    unittest.main()
