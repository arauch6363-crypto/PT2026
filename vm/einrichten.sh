#!/usr/bin/env bash
# Einrichtung der VM (Debian/Ubuntu, z. B. Compute Engine e2-standard-2 in europe-west3). Einmal als normaler Nutzer:
#   curl -fsSL https://raw.githubusercontent.com/arauch6363-crypto/PT2026/main/vm/einrichten.sh | bash
# Danach: rclone mit Google Drive verbinden (vm/README.md, Schritt 3) und den Zeitplan einschalten (Schritt 4).
set -euo pipefail
REPO=https://github.com/arauch6363-crypto/PT2026.git
CODE=$HOME/pt2026
sudo timedatectl set-timezone Europe/Paris
sudo apt-get update -q
sudo apt-get install -y -q git python3-venv python3-pip fuse3 curl unzip
command -v rclone >/dev/null || curl -fsSL https://rclone.org/install.sh | sudo bash
[ -d "$CODE/.git" ] && git -C "$CODE" pull -q || git clone -q "$REPO" "$CODE"
python3 -m venv "$HOME/venv"
"$HOME/venv/bin/pip" install -q -r "$CODE/requirements.txt" lightgbm catboost playwright deep-translator
"$HOME/venv/bin/playwright" install --with-deps chromium
mkdir -p "$HOME/drive" "$HOME/.cache/rclone"
sudo sed -i 's/^#user_allow_other/user_allow_other/' /etc/fuse.conf
echo "Fertig. Weiter mit vm/README.md, Schritt 3 (rclone config)."
