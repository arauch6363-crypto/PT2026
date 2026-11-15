# PT2026 auf einer VM (Google Compute Engine)

Ziel: Der Tagesablauf (Ergebnisse, Dashboard, Rennkarte 90 min vor dem ersten Rennen, Festkurse je Reunion) läuft
jeden Morgen ohne Colab. Die Maschine läuft nur, wenn etwas zu tun ist: morgens kurz (Ergebnisse, Dashboard), dann
wieder ab kurz vor der Karte bis alle Veranstaltungen Festkurse haben; dazwischen ist sie aus (Schritt 6). Daten bleiben in Google Drive (`PT_tracking`), die VM bindet den Ordner über rclone ein.
Colab bleibt der Rückfall (`MODUS = 'manuell'` bzw. `'automatik'` im Notebook).

## 1 · VM anlegen (einmal, in der Google Cloud Console oder Cloud Shell)

Projekt mit Abrechnung wählen, dann in der Cloud Shell:

```bash
gcloud compute instances create pt2026 --zone europe-west3-b --machine-type e2-standard-2 \
  --image-family debian-12 --image-project debian-cloud --boot-disk-size 40GB --scopes cloud-platform
```

(`--scopes cloud-platform`: die VM darf damit ihren Weck-Job im Cloud Scheduler umstellen, Schritt 6.)

Frankfurt (`europe-west3`), damit Wettstar eine deutsche Adresse sieht. 2 vCPU / 8 GB reichen für die Karte
(Training bleibt in Colab).

Kosten: die VM kostet nur, solange sie läuft (Speicher ein paar Euro im Monat zusätzlich); Schritt 6 schaltet sie
zwischendurch und am Ende des Tages ab.

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

**Claude-Tipps starten:** den Schlüssel des API-Triggers der Aufgabe „Racecard-Durchgang“ (siehe Haupt-README) ebenfalls
dort eintragen: `echo 'DURCHGANG_TOKEN=sk-ant-oat01-…' >> ~/.pt2026.env` und `echo 'DURCHGANG_ID=trig_…' >> ~/.pt2026.env` (nur für dich lesbar: `chmod 600 ~/.pt2026.env`).

## 6 · Zeitplan: Maschine nur bei Bedarf an

Zwei Jobs im Cloud Scheduler starten die VM: **pt2026-morgen** jeden Tag um 6:45, **pt2026-wecken** stellt die VM
selbst jeden Tag auf die nächste Weckzeit (10 min vor der Karte bzw. vor den Festkursen einer späten Veranstaltung).
Nach jedem Lauf fährt sie herunter. In der **Cloud Shell** (nicht auf der VM):

```bash
P=$(gcloud config get-value project); Z=europe-west3-b; R=europe-west3
gcloud services enable cloudscheduler.googleapis.com
gcloud iam service-accounts create pt2026-wecker --display-name "PT2026 VM starten"
W=pt2026-wecker@$P.iam.gserviceaccount.com
gcloud projects add-iam-policy-binding $P --member serviceAccount:$W --role roles/compute.instanceAdmin.v1
URL=https://compute.googleapis.com/compute/v1/projects/$P/zones/$Z/instances/pt2026/start
gcloud scheduler jobs create http pt2026-morgen --location $R --schedule "45 6 * * *" --time-zone Europe/Paris \
  --http-method POST --uri $URL --oauth-service-account-email $W
gcloud scheduler jobs create http pt2026-wecken --location $R --schedule "0 0 1 1 *" --time-zone Europe/Paris \
  --http-method POST --uri $URL --oauth-service-account-email $W
# die VM (ihr Standard-Dienstkonto) darf den Weck-Job umstellen:
V=$(gcloud compute instances describe pt2026 --zone $Z --format 'value(serviceAccounts[0].email)')
gcloud projects add-iam-policy-binding $P --member serviceAccount:$V --role roles/cloudscheduler.admin
gcloud iam service-accounts add-iam-policy-binding $W --member serviceAccount:$V --role roles/iam.serviceAccountUser
```

Auf der **VM**:

```bash
echo 'PT2026_PAUSEN=1' >> ~/.pt2026.env
mkdir -p ~/.config/systemd/user
cp ~/pt2026/vm/pt2026.service ~/.config/systemd/user/
sudo loginctl enable-linger $USER          # Nutzer-Dienste starten beim Hochfahren auch ohne Anmeldung
systemctl --user daemon-reload && systemctl --user enable pt2026.service
```

Ab dann: Hochfahren → `vm/lauf.sh` → `taeglich.py --pausen` → Pause geplant oder Tag fertig → Drive-Uploads abwarten →
herunterfahren. Ergebnisse und Dashboard laufen nur im ersten Lauf des Tages (Stand `logs/.tag_JJJJMMTT.json`), die
Karte nur, solange es ihre Daten noch nicht gibt.

**Zum Arbeiten auf der VM** (sonst fährt sie nach dem Lauf herunter): `touch ~/.nicht_abschalten`, danach wieder
`rm ~/.nicht_abschalten`. Ein Lauf von Hand: `systemctl --user start pt2026` · Ausgabe live:
`journalctl --user -u pt2026 -f` · Protokoll je Tag: `PT_tracking/logs/taeglich_JJJJMMTT.log` (auch in Drive).
Schlägt das Umstellen des Weck-Jobs fehl, meldet das Protokoll/ntfy „Wecken nicht geplant“ und die VM wartet wie früher
(bleibt an).

Ohne Pausen (VM immer an, z. B. mit Instanzzeitplan): statt der Schritte auf der VM `pt2026.timer` mitkopieren und
`systemctl --user enable --now pt2026.timer` (Lauf täglich 6:55), `PT2026_PAUSEN` nicht setzen.

## Ablauf je Tag

`vm/lauf.sh` (beim Hochfahren): `git pull`, Drive einbinden (rclone mount mit lokalem Cache), dann `taeglich.py`:
`tagesablauf.ergebnisse_holen` (wie Notebook Abschnitt 2, gleiche Stand-Datei – Colab überspringt danach) und
`tagesablauf.morgen` (wie Abschnitt 3a). Das Notebook bleibt unverändert nutzbar; läuft beides am selben Tag,
holt nur das erste die Ergebnisse.

**Wichtig:** Nicht gleichzeitig Colab-Automatik und VM laufen lassen – beide würden die Karte bauen.
