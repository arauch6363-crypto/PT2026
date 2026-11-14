#!/usr/bin/env bash
# Täglicher Lauf auf der VM (vom systemd-Timer um 6:55 gestartet): Code aktualisieren, Drive einbinden, taeglich.py.
set -uo pipefail
CODE=$HOME/pt2026
BASE=$HOME/drive/PT_tracking
git -C "$CODE" pull -q || echo "git pull fehlgeschlagen – laufe mit dem vorhandenen Stand"
if ! mountpoint -q "$HOME/drive"; then
  rclone mount gdrive: "$HOME/drive" --daemon --vfs-cache-mode full --vfs-cache-max-size 20G \
    --vfs-cache-max-age 720h --dir-cache-time 5m --poll-interval 1m --allow-other
  sleep 10
fi
[ -d "$BASE" ] || { echo "Drive nicht eingebunden ($BASE fehlt)"; exit 1; }
[ -f "$HOME/.pt2026.env" ] && set -a && . "$HOME/.pt2026.env" && set +a     # NTFY_TOPIC=…
cd "$CODE" && exec "$HOME/venv/bin/python" taeglich.py --base "$BASE"
