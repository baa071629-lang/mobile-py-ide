# Mobile Py IDE 3.0

IDE Python **mobile-first** pour Android, inspiré de PyramIDE : éditeur Monaco
hors ligne, exécution Python réelle, entrée interactive, gestion de dossiers,
modules/paquets et écran graphique.

Deux façons de l'utiliser :

| Mode | Ce que tu installes | Python |
|---|---|---|
| **Application Android (APK)** | `app-debug.apk` depuis les [releases](../../releases) | 3.11 embarqué (Chaquopy), aucun root, aucune autre app |
| **Serveur Termux / PC** | ce dépôt + `install_termux.sh` | ton Python Termux, avec `pip` complet |

## Télécharger l'APK

1. Ouvre la page **[Releases](../../releases)** et télécharge `app-debug.apk`
   (tag `android-v3.0.0`).
2. Autorise l'installation depuis cette source, puis installe.
3. Au premier lancement, l'app extrait son moteur Python et crée un projet
   d'exemple (`bienvenue.py`).
4. Pour accéder à tes dossiers (`/sdcard`, `Download`, `Documents`…), touche
   **☰ → ＋** : Android ouvre l'écran « Accès à tous les fichiers ».

L'APK est compilé automatiquement par GitHub Actions à chaque modification du
serveur ou de l'interface (`.github/workflows/android.yml`).

## Nouveautés 3.0

- **Éditeur et sortie séparés** : deux zones distinctes, redimensionnables en
  glissant la poignée (⫿ dans la barre du haut pour masquer la sortie).
- **Entrée interactive comme PyramIDE** : quand le programme appelle `input()`,
  l'invite (« Ton nom ? ») s'affiche dans la sortie et le champ de saisie prend
  le focus. Historique ↑/↓, `EOF` (Ctrl+D), bouton **Stop** pour interrompre.
- **Accès à tes dossiers** : projets, dossier personnel, stockage du téléphone,
  plus tout dossier ajouté à la volée. Import de fichiers via le sélecteur
  Android.
- **Modules et paquets** : liste des modules installés, **catalogue** (Requests,
  Rich, Pygame, NumPy, Pillow, Matplotlib, Kivy…), **recherche PyPI**,
  installation/désinstallation/mise à jour, badges « Graphique » et
  « roue native ».
- **Écran graphique** : canevas dessinable (`pyide_gui`), images Pillow,
  tracés Matplotlib — affiché dans l'onglet **Graphique**.
- **Corrections** : chemins absolus fiables, démarrage plus rapide, panneau
  repliable, écho de saisie sans doublon, définition vers un chemin absolu,
  gestion des erreurs d'import de modules graphiques.

## Fonctionnalités

### Éditeur
Monaco local (aucun CDN), multi-onglets, thème clair/sombre, complétion Jedi,
signature, survol, aller à la définition, diagnostics Pyflakes en direct,
formatage autopep8, recherche dans le fichier, ouverture rapide (`Ctrl+P`),
recherche plein texte (`Ctrl+Maj+F`), exemples de code, sauvegarde automatique.

### Exécution
Bouton ▶ (`Ctrl+Entrée`), sortie en temps réel, stdout/stderr séparés, entrée
standard interactive, arrêt, timeout configurable, console Python (`python -i`),
exécution de la sélection, arguments en ligne de commande, repli HTTP si la
WebSocket n'est pas disponible.

### Fichiers
Parcours, création, renommage, suppression, import, upload, téléchargement,
recherche, dossiers cachés. Tous les accès sont confinés aux **emplacements
autorisés** (aucune évasion `../`).

### Paquets
Sur Termux/PC : `pip` réel dans le venv de l'IDE.
Dans l'app Android : téléchargement des **roues pures** (`py3-none-any`) depuis
PyPI et installation dans un dossier utilisateur — aucun compilateur requis.
Les paquets natifs (NumPy, Pillow, Matplotlib) sont installés **au moment du
build** de l'APK, comme le « dépôt de bibliothèques précompilées » de PyramIDE.

### Écran graphique

```python
from pyide_gui import screen

s = screen(640, 400, "#101020")   # canevas
s.clear()
s.rect(20, 20, 120, 60, "#89b4fa")
s.circle(320, 200, 70, "#f9e2af")
s.line(0, 400, 640, 0, "#a6e3a1", width=3)
s.text(24, 340, "Bonjour !", "#cdd6f4", size=22)
s.present()
```

`plt.show()` (Matplotlib) et `Image.show()` (Pillow) affichent aussi leur rendu
dans cet onglet.

## Installation (Termux)

```bash
pkg install git
git clone https://github.com/baa071629-lang/mobile-py-ide.git ~/mobile-py-ide
bash ~/mobile-py-ide/install_termux.sh
start-pyide
```

Puis ouvre `http://127.0.0.1:8765`. L'installateur crée la racine
`~/storage/shared/PyIDE` (ou `~/projects`). Après `termux-setup-storage`, le
stockage partagé apparaît comme emplacement « Stockage du téléphone ».

### Depuis un PC (même Wi-Fi)

```bash
PYIDE_HOST=0.0.0.0 PYIDE_TOKEN=mon-secret bash start.sh
```

> ⚠️ Le serveur exécute du code Python arbitraire. Ne l'expose **jamais** sur
> Internet, et utilise toujours `PYIDE_TOKEN` sur un réseau local.

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `PYIDE_HOST` | `127.0.0.1` | Adresse d'écoute (`0.0.0.0` pour le réseau local) |
| `PYIDE_PORT` | `8765` | Port HTTP/WebSocket |
| `PYIDE_PROJECTS` | `~/storage/shared/PyIDE` ou `~/projects` | Racine des projets |
| `PYIDE_ROOTS` | *(vide)* | Dossiers supplémentaires autorisés (`:` ou `,`) |
| `PYIDE_TOKEN` | *(vide)* | Jeton d'accès partagé ; obligatoire hors localhost |
| `PYIDE_RUN_TIMEOUT` | `30` | Timeout d'exécution par défaut (secondes) |
| `PYIDE_PKG_BACKEND` | `pip` (`wheels` sur Android) | Moteur d'installation des paquets |
| `PYIDE_USER_SITE` | `~/.pyide-packages` | Dossier des roues installées |
| `PYIDE_AI_URL` / `_KEY` / `_MODEL` | *(vide)* | API compatible OpenAI |
| `PYIDE_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama local détecté automatiquement |

## Raccourcis

| Raccourci | Action |
|---|---|
| `Ctrl+S` | Enregistrer |
| `Ctrl+Entrée` | Exécuter / arrêter |
| `Ctrl+K` / `F1` | Palette de commandes |
| `Ctrl+P` | Ouverture rapide |
| `Ctrl+Maj+F` | Recherche dans les fichiers |
| `Ctrl+W` | Fermer l'onglet |
| `Ctrl+Maj+E` | Afficher / masquer les fichiers |
| `Échap` | Fermer panneau, barre latérale ou modale |

Sur mobile, le clavier rapide fournit Tab, indentation, parenthèses, guillemets,
annuler/rétablir et recherche.

## Architecture

```
mobile-py-ide/
├── server/
│   ├── app.py         # Starlette : routes HTTP, WebSocket, événements graphiques
│   ├── analysis.py    # Jedi + Pyflakes + autopep8
│   ├── files.py       # Emplacements multiples, fichiers, recherche confinée
│   ├── runner.py      # Sous-processus Python (serveur) : flux, stdin, stop
│   ├── native.py      # Exécution en fil (app Android) : stdin, stop, REPL, canevas
│   ├── gui.py         # Canevas graphique + accroches Matplotlib/Pillow
│   ├── packages.py    # pip (serveur) ou roues pures (Android) + recherche PyPI
│   ├── ai.py          # Assistant IA optionnel
│   ├── snippets.py    # Exemples de code
│   └── config.py      # Emplacements, constantes, variables d'environnement
├── pyide_native.py    # Pont Python ⇄ Kotlin (opérations, exécution, entrées)
├── pyide_gui.py       # Module « canevas » utilisable par les programmes
├── sitecustomize.py   # Signale les lectures de stdin (serveur)
├── web/
│   ├── index.html     # Interface : éditeur | poignée | sortie
│   ├── app.js         # Monaco, onglets, terminal, graphique, paquets, modales
│   ├── transport.js   # HTTP/WebSocket ou pont Android (même code appelant)
│   ├── style.css      # Thèmes, split, panneaux
│   └── vendor/monaco/ # Monaco hors ligne
├── android/           # Projet Gradle : WebView + Chaquopy (Python 3.11)
├── tests/             # HTTP/WebSocket, pont natif, canevas, entrée
└── .github/workflows/android.yml
```

Le même code Python sert les deux modes : `server/app.py` expose les routes pour
le navigateur, `pyide_native.py` expose les mêmes opérations au pont Android.
Côté web, `transport.js` traduit chaque route REST en opération native : le
reste du frontend ne sait pas sur quelle plateforme il tourne.

### API principale

- `POST /api/complete`, `/api/hover`, `/api/signature`, `/api/definition`
- `POST /api/diagnose`, `/api/format`
- `GET /api/health` (public), `/api/places`, `/api/tree`, `/api/info`,
  `/api/file`, `/api/exists`, `/api/search`, `/api/files`, `/api/download`
- `POST /api/file`, `/api/mkdir`, `/api/rename`, `/api/delete`, `/api/upload`,
  `/api/import`, `/api/places/add`, `/api/places/remove`, `/api/run`
- `GET /api/packages`, `/api/packages/catalog`, `/api/packages/search`,
  `/api/packages/info` ; `POST /api/packages/install`, `/api/packages/uninstall`
- `POST /api/ai`, `GET /api/ai/status`, `GET /api/snippets`
- `WS /ws/run` : `start`, `stdin`, `close_stdin`, `stop` → `started`, `stdout`,
  `stderr`, `need_input`, `input_echo`, `gfx`, `image`, `exit`, `error`

Toutes les routes `/api/*` (sauf `/api/health`) et `/ws/run` exigent
`X-Pyide-Token` ou `?token=…` lorsque `PYIDE_TOKEN` est défini.

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest tests -q
```

Les tests démarrent un serveur isolé (port libre, dossier temporaire, jeton) et
couvrent : fichiers et confinement, emplacements multiples, analyse, formatage,
exécution HTTP + WebSocket (stdin), canevas graphique, pont Android
(`pyide_native`) de bout en bout.

## Compiler l'APK

Le build se fait sur GitHub Actions (SDK Android + JDK 17 + Python 3.11) :

```bash
gh workflow run "APK Android"   # ou simplement pousser sur une PR
```

En local, si tu as le SDK Android et Python 3.11 :

```bash
cd android && gradle assembleDebug
# APK : app/build/outputs/apk/debug/app-debug.apk
```

## Limites connues

- **Pas de Tkinter/Kivy/Pygame natif** dans l'APK : ces boîtes à outils
  nécessitent un serveur graphique absent d'Android. L'écran graphique
  `pyide_gui` couvre les besoins de dessin simples, et un module manquant
  affiche un message explicite.
- Dans l'app Android, l'installation de paquets est limitée aux **roues pures**
  (pas de compilation). Les bibliothèques natives doivent être intégrées au
  build.
- Le bac à sable Android (SAF) impose de **copier** les fichiers choisis dans le
  projet ; l'accès direct nécessite la permission « tous les fichiers ».
- Pas de débogueur pas à pas (breakpoints).
- Sortie limitée à 512 Ko par exécution et fichiers limités à 5 Mo.
- Le jeton est un secret partagé, pas un système multi-utilisateurs.

## Licence

Projet personnel de `baa071629-lang`. Monaco est distribué sous licence MIT
(voir `web/vendor/monaco`).
