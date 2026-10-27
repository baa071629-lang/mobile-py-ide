"""Test du pont Android (``pyide_native``) sans appareil.

Le pont est initialisé avec des dossiers temporaires, puis on vérifie les
opérations que l'interface appelle réellement dans l'application.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = textwrap.dedent(
    """
    import json, os, sys, tempfile, time
    sys.path.insert(0, {root!r})
    import pyide_native

    base = tempfile.mkdtemp(prefix="pyide-native-")
    files = os.path.join(base, "files")
    cache = os.path.join(base, "cache")
    os.makedirs(files, exist_ok=True)
    os.makedirs(cache, exist_ok=True)
    info = pyide_native.init(json.dumps({{"filesDir": files, "cacheDir": cache,
                                         "version": "3.0.0"}}))
    print("INIT", info)

    def call(op, **params):
        params["op"] = op
        return json.loads(pyide_native.request(json.dumps(params)))

    health = call("health")
    print("HEALTH", health["native"], health["root"])
    tree = call("tree", dir="")
    print("TREE", [entry["name"] for entry in tree["entries"]])

    target = os.path.join(files, "projects", "essai.py")
    saved = call("file.save", path=target, content="print('ok')\\n")
    print("SAVE", saved["ok"], saved["rel"])
    read = call("file.read", path=target)
    print("READ", read["content"].strip())
    diag = call("diagnose", path=target, code="import os\\nx = 1\\n")
    print("DIAG", isinstance(diag.get("markers"), list))
    fmt = call("format", code="x=1\\n")
    print("FMT", fmt.get("code", "").strip())
    cat = call("packages.catalog")
    print("CAT", len(cat["catalog"]) > 3, cat["backend"])
    err = call("file.read", path="/etc/passwd")
    print("ERR", err.get("error") is not None, err.get("status"))

    events = []
    class Sink:
        def onEvent(self, run_id, payload):
            events.append(json.loads(payload))

    code = "nom = input('Qui ? ')\\nprint('salut', nom)\\n"
    run_id = pyide_native.start_run(json.dumps({{"code": code, "timeout": 10}}), "run1", Sink())
    deadline = time.time() + 5
    while time.time() < deadline and not any(e.get("type") == "need_input" for e in events):
        time.sleep(0.05)
    pyide_native.run_input("run1", "Awa\\n")
    deadline = time.time() + 10
    while time.time() < deadline and not any(e.get("type") == "exit" for e in events):
        time.sleep(0.05)
    text = "".join(e.get("data", "") for e in events if e.get("type") == "stdout")
    print("RUN", "salut Awa" in text, any(e.get("type") == "need_input" for e in events))
    """
)


class NativeBridgeTestCase(unittest.TestCase):
    def test_pont_android_de_bout_en_bout(self):
        script = SCRIPT.format(root=str(ROOT))
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout
        self.assertIn("HEALTH True", output)
        self.assertIn("TREE ['bienvenue.py']", output)
        self.assertIn("SAVE True essai.py", output)
        self.assertIn("READ print('ok')", output)
        self.assertIn("DIAG True", output)
        self.assertIn("FMT x = 1", output)
        self.assertIn("CAT True wheels", output)
        self.assertIn("ERR True 403", output)
        self.assertIn("RUN True True", output)


if __name__ == "__main__":
    unittest.main()
