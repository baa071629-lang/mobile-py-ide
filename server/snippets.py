"""Exemples prêts à l'emploi (inspirés de la bibliothèque d'exemples de PyramIDE)."""

from __future__ import annotations

SNIPPETS: list[dict] = [
    {
        "id": "bonjour",
        "title": "Bonjour !",
        "description": "Variables, f-strings et affichage.",
        "filename": "bonjour.py",
        "category": "Débuter",
        "code": '''"""Mon premier programme."""
nom = "Ada"
age = 36

print(f"Bonjour {nom} !")
print(f"Tu as {age} ans, soit {age * 12} mois.")
''',
    },
    {
        "id": "conditions",
        "title": "Conditions",
        "description": "if / elif / else avec une saisie clavier.",
        "filename": "conditions.py",
        "category": "Débuter",
        "code": '''note = float(input("Ta note sur 20 : "))

if note >= 16:
    mention = "très bien"
elif note >= 14:
    mention = "bien"
elif note >= 12:
    mention = "assez bien"
elif note >= 10:
    mention = "passable"
else:
    mention = "insuffisant"

print(f"Mention : {mention}")
''',
    },
    {
        "id": "boucles",
        "title": "Boucles et listes",
        "description": "for, enumerate, compréhension de liste.",
        "filename": "boucles.py",
        "category": "Débuter",
        "code": '''langages = ["Python", "JavaScript", "Rust", "Go"]

for index, langage in enumerate(langages, start=1):
    print(f"{index}. {langage}")

longs = [langage for langage in langages if len(langage) > 2]
print("Noms de plus de 2 lettres :", longs)
''',
    },
    {
        "id": "fonctions",
        "title": "Fonctions",
        "description": "Arguments par défaut, annotations, docstring.",
        "filename": "fonctions.py",
        "category": "Débuter",
        "code": '''def moyenne(notes: list[float], arrondi: int = 2) -> float:
    """Calcule la moyenne d'une liste de notes."""
    if not notes:
        return 0.0
    return round(sum(notes) / len(notes), arrondi)


notes = [12, 15.5, 18, 9]
print("Moyenne :", moyenne(notes))
''',
    },
    {
        "id": "classes",
        "title": "Classes et dataclass",
        "description": "Un objet simple avec une dataclass.",
        "filename": "classes.py",
        "category": "Débuter",
        "code": '''from dataclasses import dataclass


@dataclass
class Eleve:
    nom: str
    notes: list[float]

    @property
    def moyenne(self) -> float:
        return sum(self.notes) / len(self.notes) if self.notes else 0.0

    def bulletin(self) -> str:
        return f"{self.nom} : {self.moyenne:.1f}/20"


eleve = Eleve("Ada", [18, 16, 20])
print(eleve.bulletin())
''',
    },
    {
        "id": "fichiers",
        "title": "Fichiers",
        "description": "Lire et écrire un fichier texte à côté du script.",
        "filename": "fichiers.py",
        "category": "Fichiers",
        "code": '''from pathlib import Path

fichier = Path(__file__).with_name("journal.txt")
fichier.write_text("Première ligne\\nDeuxième ligne\\n", encoding="utf-8")

for numero, ligne in enumerate(
    fichier.read_text(encoding="utf-8").splitlines(), start=1
):
    print(numero, ligne)
''',
    },
    {
        "id": "devine",
        "title": "Devine le nombre",
        "description": "Jeu complet avec input() et boucle while.",
        "filename": "devine.py",
        "category": "Jeux",
        "code": '''import random

secret = random.randint(1, 100)
essais = 0

print("J'ai choisi un nombre entre 1 et 100.")
while True:
    try:
        proposition = int(input("Ta proposition : "))
    except ValueError:
        print("Entre un nombre entier.")
        continue

    essais += 1
    if proposition < secret:
        print("Plus grand !")
    elif proposition > secret:
        print("Plus petit !")
    else:
        print(f"Bravo, trouvé en {essais} essais !")
        break
''',
    },
    {
        "id": "motdepasse",
        "title": "Générateur de mot de passe",
        "description": "Module secrets et choix aléatoires sûrs.",
        "filename": "motdepasse.py",
        "category": "Utilitaires",
        "code": '''import secrets
import string

alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
longueur = 16

mot_de_passe = "".join(secrets.choice(alphabet) for _ in range(longueur))
print(mot_de_passe)
''',
    },
    {
        "id": "json",
        "title": "JSON",
        "description": "Sérialiser et relire des données structurées.",
        "filename": "json_demo.py",
        "category": "Données",
        "code": '''import json
from pathlib import Path

donnees = {"nom": "Ada", "langages": ["Python", "C"], "actif": True}
fichier = Path(__file__).with_name("profil.json")
fichier.write_text(json.dumps(donnees, indent=2, ensure_ascii=False), encoding="utf-8")

relu = json.loads(fichier.read_text(encoding="utf-8"))
print(relu["nom"], "→", ", ".join(relu["langages"]))
''',
    },
    {
        "id": "regex",
        "title": "Expressions régulières",
        "description": "Extraire des informations d'un texte.",
        "filename": "regex_demo.py",
        "category": "Données",
        "code": '''import re

texte = "Contacte ada@example.com ou grace@dev.fr avant lundi."
emails = re.findall(r"[\\w.+-]+@[\\w-]+\\.[\\w.]+", texte)

for email in emails:
    print(email)
''',
    },
    {
        "id": "http",
        "title": "Requête HTTP",
        "description": "Appeler une API avec urllib (nécessite Internet).",
        "filename": "http_demo.py",
        "category": "Réseau",
        "code": '''import json
import urllib.request

url = "https://api.github.com/repos/python/cpython"
requete = urllib.request.Request(url, headers={"User-Agent": "MobilePyIDE"})

with urllib.request.urlopen(requete, timeout=10) as reponse:
    donnees = json.load(reponse)

print(donnees["full_name"], "★", donnees["stargazers_count"])
''',
    },
    {
        "id": "async",
        "title": "Asynchrone",
        "description": "asyncio et tâches concurrentes.",
        "filename": "async_demo.py",
        "category": "Avancé",
        "code": '''import asyncio


async def telecharger(nom: str, duree: float) -> str:
    await asyncio.sleep(duree)
    return f"{nom} terminé en {duree}s"


async def main() -> None:
    resultats = await asyncio.gather(
        telecharger("A", 0.3),
        telecharger("B", 0.1),
        telecharger("C", 0.2),
    )
    print("\\n".join(resultats))


asyncio.run(main())
''',
    },
]


def list_snippets() -> list[dict]:
    return SNIPPETS
