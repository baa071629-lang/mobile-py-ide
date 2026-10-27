# Mobile Py IDE

Un IDE Python **mobile-first** servi localement par **Termux** et utilisable dans le
navigateur Android (ou sur un PC du réseau local). Monaco, l'analyse Jedi et le
terminal interactif fonctionnent sans connexion Internet.

## Fonctionnalités

### Éditeur

- **Monaco** vendorisé localement (pas de CDN), multi-onglets, thème clair/sombre
- **Auto-complétion** Jedi : modules, fonctions, méthodes, paramètres et documentation
- **Aide sur le symbole** : signature, docstring et type au survol
- **Aller à la définition** : dans le fichier courant, un autre fichier du projet,
  ou vers la bibliothèque standard ; `Ctrl`/`Cmd` + clic
- **Diagnostics en direct** Pyflakes : noms inconnus, imports inutilisés, syntaxe…
- **Formater** avec autopep8 (commande, palette ou menu ⋯)
- **Recherche** dans le fichier, **ouverture rapide** (`Ctrl+P`) et recherche
  plein texte dans les projets (`Ctrl+Maj+F`)
- **Exemples de code** prêts à insérer (fichiers, boucles, classes, JSON, regex…)
- Annuler/rétablir, indentation, commentaire de ligne, sauvegarde automatique optionnelle

### Exécution

- Bouton ▶ ou `Ctrl+Entrée` : exécution du fichier ou du **buffer modifié**
- **Sortie en temps réel** via WebSocket, stdout/stderr séparés
- **Entrée standard interactive** (`input()`) directement dans le terminal
- **Arrêt** du processus, timeout configurable (30 s par défaut, 5 à 300 s)
- **Console Python interactive** (`python -i`) avec REPL
- **Exécuter la sélection** et **exécuter avec des arguments** de ligne de commande
- Repli automatique en HTTP si la WebSocket n'est pas disponible

### Fichiers et outils

- Gestionnaire de fichiers : parcourir, créer, renommer, supprimer, uploader,
  télécharger, afficher les fichiers cachés
- Fichiers de projet confinés dans `PYIDE_PROJECTS` (protection contre `../`)
- Palette de commandes (`Ctrl+K`), raccourcis clavier et clavier mobile dédié
- Gestionnaire **pip** : lister, installer et désinstaller les paquets du venv
- **Assistant IA optionnel** : API compatible OpenAI (OpenAI, Ollama, LM Studio…)
  avec modes expliquer / corriger / tests / revue / générer / optimiser
- Paramètres persistants : police, tabulation, retour à la ligne, lint, thème,
  autosauvegarde, timeout, clavier rapide
- Manifeste **PWA** : ajout à l'écran d'accueil Android ; le serveur Termux doit
  rester lancé

## Installation (Termux)

1. Installe [Termux (F-Droid)](https://f-droid.org/en/packages/com.termux/) —
   **pas** la version Play Store, obsolète.
2. Place le dossier dans Termux, par exemple :
   ```bash
   pkg install git
   git clone <url-de-ce-projet> ~/mobile-py-ide
   ```
3. Installe les dépendances :
   ```bash
   bash ~/mobile-py-ide/install_termux.sh
   ```
4. Lance :
   ```bash
   start-pyide
   ```
5. Ouvre `http://127.0.0.1:8765` dans le navigateur du téléphone.

L'installateur crée aussi un raccourci `~/start-pyide`. Il utilise
`~/storage/shared/PydroidProjects` si le stockage partagé est autorisé, sinon
`~/projects`.

## Ouvrir tes projets Pydroid

Après `termux-setup-storage`, les fichiers de
`/storage/emulated/0/PydroidProjects/` apparaissent dans l'onglet Fichiers (☰).
Ils peuvent être édités et exécutés directement par Mobile Py IDE.

## Depuis un PC (même Wi-Fi)

```bash
PYIDE_HOST=0.0.0.0 PYIDE_TOKEN=mon-secret bash start.sh
```

Puis ouvre `http://<ip-du-telephone>:8765`. L'interface demande le jeton et
l'envoie avec chaque requête HTTP/WebSocket.

> ⚠️ Le serveur exécute du code Python arbitraire. Ne l'expose **jamais** sur
> Internet. En réseau local, utilise toujours `PYIDE_TOKEN`.

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `PYIDE_HOST` | `127.0.0.1` | Adresse d'écoute (`0.0.0.0` pour le réseau local) |
| `PYIDE_PORT` | `8765` | Port HTTP/WebSocket |
| `PYIDE_PROJECTS` | `~/storage/shared/PydroidProjects` ou `~/projects` | Racine des projets |
| `PYIDE_TOKEN` | *(vide)* | Jeton d'accès partagé ; obligatoire hors localhost |
| `PYIDE_RUN_TIMEOUT` | `30` | Timeout d'exécution par défaut (secondes) |
| `PYIDE_AI_URL` | *(vide)* | URL d'une API compatible OpenAI |
| `PYIDE_AI_KEY` | *(vide)* | Clé de l'API IA |
| `PYIDE_AI_MODEL` | *(vide)* | Nom du modèle IA |
| `PYIDE_OLLAMA_URL` | `http://127.0.0.1:11434` | Serveur Ollama local détecté automatiquement |

Exemple avec Ollama local :

```bash
OLLAMA_HOST=127.0.0.1:11434 ollama serve &
PYIDE_AI_MODEL=qwen2.5-coder:7b bash start.sh
```

## Raccourcis

| Raccourci | Action |
|---|---|
| `Ctrl+S` | Enregistrer |
| `Ctrl+Entrée` | Exécuter / arrêter |
| `Ctrl+K` ou `F1` | Palette de commandes |
| `Ctrl+P` | Ouverture rapide d'un fichier |
| `Ctrl+Maj+P` | Palette de commandes |
| `Ctrl+Maj+F` | Rechercher dans les fichiers |
| `Ctrl+W` | Fermer l'onglet |
| `Ctrl+Maj+E` | Afficher / masquer les fichiers |
| `Échap` | Fermer panneau, barre latérale ou modale |

Sur mobile, le clavier rapide fournit Tab, indentation, parenthèses, guillemets,
annuler/rétablir et accès à la recherche.

## Architecture

```
mobile-py-ide/
├── server/
│   ├── app.py         # Routes Starlette, HTTP + WebSocket
│   ├── analysis.py    # Jedi (complétion, hover, définition) + Pyflakes
│   ├── files.py       # Arborescence, lecture/écriture, recherche sécurisée
│   ├── runner.py      # Sous-processus Python, flux, stdin, arrêt, timeout
│   ├── packages.py    # pip list / install / uninstall
│   ├── ai.py          # Assistant IA optionnel (OpenAI / Ollama)
│   ├── snippets.py    # Exemples de code
│   └── config.py      # Variables d'environnement et constantes
├── web/
│   ├── index.html     # Interface mobile
│   ├── app.js         # Monaco, onglets, terminal, palette, modales
│   ├── style.css      # Thèmes et responsive
│   ├── manifest.webmanifest
│   └── vendor/monaco/ # Monaco hors ligne
├── tests/
│   └── test_smoke.py  # Tests HTTP/WebSocket de fumée
├── install_termux.sh
├── start.sh
└── requirements.txt
```

Le backend utilise **Starlette** directement, sans FastAPI ni pydantic : ces
dépendances posent problème sous Python 3.14/Termux. Jedi, Pyflakes et autopep8
sont du Python pur.

### API principale

- `POST /api/complete`, `/api/hover`, `/api/signature`, `/api/definition`
- `POST /api/diagnose`, `/api/format`
- `GET /api/health` (public), `/api/tree`, `/api/file`, `/api/exists`,
  `/api/search`, `/api/files`, `/api/download`
- `POST /api/file`, `/api/mkdir`, `/api/rename`, `/api/delete`, `/api/upload`,
  `/api/run`
- `GET/POST /api/packages*`, `POST /api/ai`, `GET /api/ai/status`
- `GET /api/snippets`
- `WS /ws/run` : messages `start`, `stdin`, `stop` → `started`, `stdout`,
  `stderr`, `exit`, `error`

Toutes les routes `/api/*` (sauf `/api/health`) et `/ws/run` exigent
`X-Pyide-Token` ou `?token=…` lorsque `PYIDE_TOKEN` est défini.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Les tests démarrent un serveur isolé sur un port libre, avec un dossier de
projets temporaire. Ils couvrent les fichiers, l'analyse, le formatage,
l'exécution HTTP et le WebSocket (stdin, arrêt).

## Limites connues

- Pas de débogueur pas à pas (breakpoints) ; l'exécution lance un processus neuf.
- Le quota pip installe dans le **venv de l'IDE** : une mauvaise dépendance peut
  casser l'IDE. En cas de doute, réinstalle l'environnement.
- Sortie limitée à 512 Ko par exécution et fichiers limités à 5 Mo.
- Pas d'accès aux paquets de l'environnement Pydroid (sandbox séparée).
- Le jeton est un secret partagé, pas un système multi-utilisateurs.
- Une définition située hors du projet (site-packages, bibliothèque standard)
  affiche un message au lieu d'ouvrir le fichier.
