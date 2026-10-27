#!/data/data/com.termux/files/usr/bin/bash
# Installation de Mobile Py IDE dans Termux.
set -e

echo "=== Mobile Py IDE — installation Termux ==="

# 1. Paquets système
pkg update -y
pkg install -y python termux-tools

# 2. Dossier du projet (celui qui contient ce script)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -f "server/app.py" ] || [ ! -f "requirements.txt" ]; then
  echo "Le dossier $DIR ne ressemble pas à Mobile Py IDE."
  exit 1
fi

if [ ! -f "web/vendor/monaco/vs/loader.js" ]; then
  echo "⚠️  Monaco n'est pas vendorisé dans web/vendor/monaco/vs."
  echo "    L'éditeur ne pourra pas démarrer hors ligne."
fi

# 3. Environnement virtuel
if [ ! -d ".venv" ]; then
  python -m venv .venv
fi
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 4. Dossier projets + accès stockage partagé (pour ouvrir les projets Pydroid)
if [ -d "$HOME/storage/shared" ]; then
  mkdir -p "$HOME/storage/shared/PydroidProjects"
  echo "→ Projets Pydroid : $HOME/storage/shared/PydroidProjects"
else
  mkdir -p "$HOME/projects"
  echo "→ Dossier projets : $HOME/projects"
  echo "  (autorise le stockage avec : termux-setup-storage)"
fi

# 5. Raccourci de lancement
cat > "$HOME/start-pyide" << EOF
#!/data/data/com.termux/files/usr/bin/bash
exec bash "$DIR/start.sh"
EOF
chmod +x "$HOME/start-pyide"
chmod +x "$DIR/start.sh" "$DIR/install_termux.sh"

echo ""
echo "=== Installation terminée ==="
echo "Lance : start-pyide"
echo "Puis ouvre dans le navigateur du téléphone : http://127.0.0.1:8765"
echo "Depuis un PC : PYIDE_HOST=0.0.0.0 PYIDE_TOKEN=mon-secret start-pyide"
