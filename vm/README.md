# PT2026 auf einer VM (Google Compute Engine)

Ziel: Der Tagesablauf (Ergebnisse, Dashboard, Rennkarte 90 min vor dem ersten Rennen, Festkurse je Reunion) läuft
jeden Morgen ohne Colab. Daten bleiben in Google Drive (`PT_tracking`), die VM bindet den Ordner über rclone ein.
Colab bleibt der Rückfall (`MODUS = 'manuell'` bzw. `'automatik'` im Notebook).

## 1 · VM anlegen (einmal, in der Google Cloud Console oder Cloud Shell)

Projekt mit Abrechnung wählen, dann in der Cloud Shell:

```bash
gcloud compute instances create pt2026 --zone europe-west3-b --machine-type e2-standard-2 \
  --image-family debian-12 --image-project debian-cloud --boot-disk-size 40GB
```

Frankfurt (`europe-west3`), damit Wettstar eine deutsche Adresse sieht. 2 vCPU / 8 GB reichen für die Karte
(Training bleibt in Colab).

**Kosten sparen:** Compute Engine → Instanzzeitpläne → Zeitplan „Start 6:45, Stopp 20:00, Europe/Paris“ anlegen und
der VM zuweisen (das Dienstkonto „Compute Engine Service Agent“ braucht dafür die Rolle *Compute Instance Admin*;
die Console bietet das beim Anlegen an).

## 2 · Einrichten (einmal)

```bash
gcloud compute ssh pt2026 --zone europe-west3-b
curl -fsSL https://raw.githubusercontent.com/arauch6363-crypto/PT2026/main/vm/einrichten.sh | bash
```

Installiert Python-Umgebung, Pakete, Chromium für Wettstar und rclone; klont den Code nach `~/pt2026`.

## 3 · Google Drive verbinden (einmal)

Von deinem Rechner eine SSH-Verbindung mit Weiterleitung öffnen, damit die Anmeldung im eigenen Browser klappt:

```bash
gcloud compute ssh pt2026 --zone europe-west3-b -- -L 53682:localhost:53682
rclone config
```

In `rclone config`: `n` (neu) → Name **gdrive** → Typ **drive** → client_id/secret leer → scope **1** (voller Zugriff)
→ restliche Fragen mit Enter → „Use web browser to automatically authenticate?“ **y** → den angezeigten Link
`http://127.0.0.1:53682/auth?...` im eigenen Browser öffnen und mit dem Google-Konto anmelden, dem der Ordner
`PT_tracking` gehört → „Shared Drive?“ **n** → bestätigen.

Prüfen: `rclone lsd gdrive:PT_tracking` zeigt die Unterordner (parquet, racecards, modelle …).

## 4 · Wettstar-Test (vor allem anderen)

```bash
cd ~/pt2026 && ~/venv/bin/python -c "import wettstar, pmu; print(wettstar.festkurse(pmu.heute()).head(20))"
```

Zu einer Zeit, zu der es Festkurse gibt. Kommen Kurse: weiter. Kommt eine Sperre oder nichts: VM löschen
(`gcloud compute instances delete pt2026 --zone europe-west3-b`) – Festkurse bleiben dann in Colab.

## 5 · Push-Nachrichten (optional)

App **ntfy** aufs Handy, dort ein Thema mit langem Zufallsnamen abonnieren, auf der VM:

```bash
echo 'NTFY_TOPIC=<dein-thema>' > ~/.pt2026.env
```

Gemeldet werden: Rennkarte gebaut, Festkurse je Reunion, Boden nur angenommen, Fehler, Ende.

## 6 · Zeitplan einschalten

```bash
mkdir -p ~/.config/systemd/user
cp ~/pt2026/vm/pt2026.service ~/pt2026/vm/pt2026.timer ~/.config/systemd/user/
sudo loginctl enable-linger $USER          # Nutzer-Timer laufen auch ohne Anmeldung
systemctl --user daemon-reload && systemctl --user enable --now pt2026.timer
systemctl --user list-timers               # nächster Lauf 06:55
```

Ein Lauf von Hand (z. B. zum Test): `systemctl --user start pt2026` · Ausgabe live:
`journalctl --user -u pt2026 -f` · Protokoll je Tag: `PT_tracking/logs/taeglich_JJJJMMTT.log` (auch in Drive).

## Ablauf je Tag

`vm/lauf.sh` (6:55): `git pull`, Drive einbinden (rclone mount mit lokalem Cache), dann `taeglich.py`:
`tagesablauf.ergebnisse_holen` (wie Notebook Abschnitt 2, gleiche Stand-Datei – Colab überspringt danach) und
`tagesablauf.morgen` (wie Abschnitt 3a). Das Notebook bleibt unverändert nutzbar; läuft beides am selben Tag,
holt nur das erste die Ergebnisse.

**Wichtig:** Nicht gleichzeitig Colab-Automatik und VM laufen lassen – beide würden die Karte bauen.
