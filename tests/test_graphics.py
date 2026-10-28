"""Tests du serveur graphique : pygame, tkinter, plein écran et entrées.

Ces tests vérifient que les programmes graphiques dessinent réellement (flux
d'opérations) et reçoivent les touchers/clavier, sans appareil Android.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _prepare_env():
    os.environ["PYIDE_GFX_FILE"] = tempfile.mktemp(suffix=".jsonl")
    os.environ["PYIDE_GFX_IN"] = tempfile.mktemp(suffix=".jsonl")
    os.environ["PYIDE_IN_IDE"] = "1"
    os.environ["PYIDE_SHIMS"] = str(ROOT / "shims")
    return os.environ["PYIDE_GFX_FILE"], os.environ["PYIDE_GFX_IN"]


class PygameShimTestCase(unittest.TestCase):
    def run_program(self, code, *, feed=None, wait=6.0):
        from server import native

        gfx_file, gfx_in = _prepare_env()
        events: list[dict] = []
        session = native.NativeSession(events.append, code=code, timeout=20)
        session.start()
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and not session.finished:
            if feed:
                for payload in feed.pop(0) if feed else []:
                    session.gfx_event(payload)
            time.sleep(0.05)
        session.stop()
        time.sleep(0.1)
        return events

    def test_pygame_dessine_et_recoit_les_touchers(self):
        code = """
import pygame
pygame.init()
screen = pygame.display.set_mode((320, 200), pygame.FULLSCREEN)
pygame.display.set_caption("Test")
font = pygame.font.SysFont(None, 24)
clock = pygame.time.Clock()
frames = 0
clicks = 0
done = False
while not done and frames < 40:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            done = True
        elif event.type == pygame.MOUSEBUTTONDOWN:
            clicks += 1
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            done = True
    screen.fill((10, 10, 20))
    pygame.draw.rect(screen, (255, 0, 0), (10, 10, 50, 30))
    pygame.draw.circle(screen, (0, 255, 0), (160, 100), 20)
    pygame.draw.line(screen, (0, 0, 255), (0, 0), (320, 200), 2)
    screen.blit(font.render("salut", True, (255, 255, 255)), (10, 150))
    pygame.display.flip()
    clock.tick(20)
    frames += 1
print("frames", frames, "clics", clicks)
"""
        events = self.run_program(code)
        gfx = [event for event in events if event.get("type") == "gfx"]
        opened = next(event for event in gfx if event.get("op") == "open")
        self.assertTrue(opened["fullscreen"])
        self.assertEqual((opened["width"], opened["height"]), (320, 200))
        frames = [event for event in gfx if event.get("op") == "frame"]
        self.assertGreater(len(frames), 5)
        kinds = {op["op"] for frame in frames for op in frame.get("ops", [])}
        for expected in {"clear", "rect", "circle", "line", "text"}:
            self.assertIn(expected, kinds)
        output = "".join(e.get("data", "") for e in events if e.get("type") == "stdout")
        self.assertIn("frames", output)

    def test_les_evenements_arrivent_dans_pygame(self):
        code = """
import pygame, sys
pygame.init()
screen = pygame.display.set_mode((200, 120))
received = []
done = False
while not done:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            done = True
        elif event.type == pygame.MOUSEBUTTONDOWN:
            received.append("clic")
        elif event.type == pygame.KEYDOWN:
            received.append("touche:" + str(event.key))
        elif event.type == pygame.KEYUP:
            received.append("relache")
    if len(received) >= 2:
        done = True
print("recu", received)
"""
        events: list[dict] = []
        from server import native

        gfx_file, gfx_in = _prepare_env()
        session = native.NativeSession(events.append, code=code, timeout=20)
        session.start()
        time.sleep(0.5)
        session.gfx_event({"type": "mouse", "action": "down", "x": 10, "y": 10, "button": 1})
        session.gfx_event({"type": "key", "down": True, "name": "K_UP", "text": ""})
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not session.finished:
            time.sleep(0.05)
        session.stop()
        output = "".join(e.get("data", "") for e in events if e.get("type") == "stdout")
        self.assertIn("recu", output)
        self.assertIn("clic", output)
        self.assertIn("touche:", output)

    def test_pygame_quit_et_titre(self):
        code = """
import pygame
pygame.init()
screen = pygame.display.set_mode((100, 100))
pygame.display.set_caption("Mon jeu")
pygame.display.flip()
pygame.quit()
print("fini")
"""
        events = self.run_program(code)
        gfx = [event for event in events if event.get("type") == "gfx"]
        self.assertTrue(any(event.get("op") == "title" and event.get("title") == "Mon jeu"
                            for event in gfx))
        self.assertEqual(gfx[-1].get("op"), "close")


class TkinterShimTestCase(unittest.TestCase):
    def test_fenetre_widgets_et_canvas(self):
        from server import native

        _prepare_env()
        code = """
import tkinter as tk

root = tk.Tk()
root.title("Tk test")
root.geometry("360x520")
label = tk.Label(root, text="Bonjour")
label.pack()
button = tk.Button(root, text="OK")
button.pack()
canvas = tk.Canvas(root, width=300, height=180, background="white")
canvas.pack()
canvas.create_oval(10, 10, 90, 90, fill="#89b4fa")
canvas.create_text(120, 40, text="tracé")
root.after(400, root.destroy)
root.mainloop()
print("tk ok")
"""
        events: list[dict] = []
        session = native.NativeSession(events.append, code=code, timeout=20)
        session.start()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not session.finished:
            time.sleep(0.05)
        session.stop()
        gfx = [event for event in events if event.get("type") == "gfx"]
        opened = next(event for event in gfx if event.get("op") == "open")
        self.assertTrue(opened["fullscreen"])
        ops = [op for event in gfx if event.get("op") == "frame" for op in event.get("ops", [])]
        texts = [op.get("value") for op in ops if op["op"] == "text"]
        self.assertIn("Bonjour", texts)
        self.assertIn("OK", texts)
        self.assertIn("tracé", texts)
        self.assertTrue(any(op["op"] == "ellipse" for op in ops))
        output = "".join(e.get("data", "") for e in events if e.get("type") == "stdout")
        self.assertIn("tk ok", output)


class GraphicsServerTestCase(unittest.TestCase):
    def test_frames_et_file_d_evenements(self):
        from server import gfxserver

        path = tempfile.mktemp(suffix=".jsonl")
        os.environ["PYIDE_GFX_IN"] = path
        server = gfxserver.GraphicsServer()
        emitted: list[dict] = []
        server.bind(emitted.append)
        server.open(300, 200, "#000", fullscreen=True, title="T", mode="pygame")
        server.op("rect", x=0, y=0, w=10, h=10, color="#fff", fill=True)
        server.op("circle", x=5, y=5, r=3, color="#f00", fill=True)
        server.present()
        frames = [event for event in emitted if event.get("op") == "frame"]
        self.assertEqual(len(frames), 1)
        self.assertEqual(len(frames[0]["ops"]), 2)

        Path(path).write_text(
            json.dumps({"type": "mouse", "action": "down", "x": 3, "y": 4}) + "\n"
            + json.dumps({"type": "key", "name": "LEFT", "down": True}) + "\n",
            encoding="utf-8",
        )
        events = server.poll()
        self.assertEqual(len(events), 2)
        self.assertEqual(server.mouse, (3, 4))
        self.assertTrue(server.keys.get("LEFT"))

    def test_sortie_fichier_sans_emetteur(self):
        from server import gfxserver

        path = tempfile.mktemp(suffix=".jsonl")
        os.environ["PYIDE_GFX_FILE"] = path
        server = gfxserver.GraphicsServer()
        server.open(100, 100, "#000")
        server.op("line", x1=0, y1=0, x2=10, y2=10, color="#fff", width=1)
        server.present()
        lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["op"], "open")
        frame = json.loads(lines[1])
        self.assertEqual(frame["op"], "frame")
        self.assertEqual(frame["ops"][0]["op"], "line")

    def test_ligne_partielle_conservee(self):
        from server import gfxserver

        path = tempfile.mktemp(suffix=".jsonl")
        os.environ["PYIDE_GFX_IN"] = path
        server = gfxserver.GraphicsServer()
        ligne = json.dumps({"type": "mouse", "action": "up", "x": 7, "y": 9})
        # Écriture en cours : pas de saut de ligne final.
        Path(path).write_text(ligne[:12], encoding="utf-8")
        self.assertEqual(server.poll(), [])
        Path(path).write_text(ligne[:12] + ligne[12:] + "\n", encoding="utf-8")
        events = server.poll()
        self.assertEqual(len(events), 1)
        self.assertEqual(server.mouse, (7, 9))
        self.assertEqual(server.poll(), [])


if __name__ == "__main__":
    unittest.main()
