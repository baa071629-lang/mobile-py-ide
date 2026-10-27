#!/data/data/com.termux/files/usr/bin/bash
# Démarre Mobile Py IDE.
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
  echo "Environnement absent — lance d'abord : bash install_termux.sh"
  exit 1
fi

if [ ! -f "web/vendor/monaco/vs/loader.js" ]; then
  echo "Monaco est absent de web/vendor/monaco/vs."
  echo "Recopie le dossier vendor ou relance l'installation."
  exit 1
fi

. .venv/bin/activate

export PYIDE_HOST="${PYIDE_HOST:-127.0.0.1}"
export PYIDE_PORT="${PYIDE_PORT:-8765}"
export PYIDE_PROJECTS="${PYIDE_PROJECTS:-}"

echo "Mobile Py IDE démarre sur http://${PYIDE_HOST}:${PYIDE_PORT}"
if [ "$PYIDE_HOST" = "0.0.0.0" ]; then
  echo "Depuis un autre appareil du même Wi-Fi : http://<ip-de-ce-telephone>:${PYIDE_PORT}"
  if [ -n "${PYIDE_TOKEN:-}" ]; then
    echo "Jeton d'accès activé."
  else
    echo "⚠️  Aucun jeton : le serveur exécute du code arbitraire, ne l'expose pas"
    echo "    sur un réseau non fiable. Relance avec PYIDE_TOKEN=mon-secret."
  fi
fi
echo "(Ctrl+C pour arrêter)"

exec python -m server.app
