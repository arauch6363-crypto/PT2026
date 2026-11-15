#!/usr/bin/env bash
# Lauf auf der VM (beim Hochfahren bzw. vom Timer gestartet): Code aktualisieren, Drive einbinden, taeglich.py.
# Mit PT2026_PAUSEN=1 in ~/.pt2026.env: danach Drive-Uploads abwarten und die Maschine herunterfahren
# (taeglich.py hat dann das Wecken geplant oder der Tag ist fertig). ~/.nicht_abschalten verhindert das (z. B. beim Testen).
set -uo pipefail
CODE=$HOME/pt2026
BASE=$HOME/drive/PT_tracking
git -C "$CODE" pull -q || echo "git pull fehlgeschlagen – laufe mit dem vorhandenen Stand"
if ! mountpoint -q "$HOME/drive"; then
  rclone mount gdrive: "$HOME/drive" --daemon --vfs-cache-mode full --vfs-cache-max-size 20G \
    --vfs-cache-max-age 720h --dir-cache-time 5m --poll-interval 1m --allow-other \
    --rc --rc-addr 127.0.0.1:5572 --rc-no-auth
  sleep 10
fi
[ -d "$BASE" ] || { echo "Drive nicht eingebunden ($BASE fehlt)"; exit 1; }
[ -f "$HOME/.pt2026.env" ] && set -a && . "$HOME/.pt2026.env" && set +a     # NTFY_TOPIC, DURCHGANG_TOKEN, PT2026_PAUSEN …
cd "$CODE" && "$HOME/venv/bin/python" taeglich.py --base "$BASE"
rc=$?
if [ "${PT2026_PAUSEN:-0}" = "1" ] && [ ! -e "$HOME/.nicht_abschalten" ]; then
  echo "Warte auf Drive-Uploads, dann herunterfahren …"
  for i in $(seq 1 60); do                                  # höchstens 10 min
    sleep 10
    offen=$(rclone rc vfs/stats --url http://127.0.0.1:5572 2>/dev/null \
      | "$HOME/venv/bin/python" -c "import json,sys; d=json.load(sys.stdin).get('diskCache',{}); print(d.get('uploadsInProgress',0)+d.get('uploadsQueued',0))" 2>/dev/null || echo 0)
    [ "$offen" = "0" ] && break
  done
  fusermount3 -u "$HOME/drive" 2>/dev/null || fusermount -u "$HOME/drive" 2>/dev/null || true
  sudo systemctl poweroff
fi
exit $rc
