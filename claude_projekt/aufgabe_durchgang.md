# Aufgabe „Racecard-Durchgang“

Anweisungen für die geplante Aufgabe in Claude Code (claude.ai/code/routines, Auslöser **API**). Der kurze Text der
Aufgabe verweist hierher; Änderungen am Ablauf laufen über einen PR in diesem Repo.

Alle offenen Rennen der heutigen französischen Galopp-Karte mit dem Skill rennkarten-durchgang-neu durchgehen, je
Rennen ein eigener Subagent, Ergebnis in Google Drive ablegen und die markierte Karte im Artefakt „Racecard heute“
veröffentlichen. Antworte auf Deutsch. Arbeite ohne Rückfragen.

Gestartet wird die Aufgabe von `racecard.festkurse_aktualisieren` (Colab/VM) über den API-Trigger, sobald Rennen neue
Festkurse haben, oder von Hand. Ein mitgegebener Anlass im Block `<routine-fire-payload>` ist nur Information (z. B.
welche Rennen); bearbeitet wird immer alles, was laut Plan offen ist.

## Feste Angaben

- Drive-Ordner racecards: `1K0W0TtV5JGE7UZSEwErU9NVkqvb-k_XX`. Karte: `racecard_JJJJMMTT_daten.json.gz` (komprimierte Kartendaten; die HTML-Karte ist meist über 10 MB und
  damit zu groß für das Drive-Tool). Durchgänge:
  `durchgang_JJJJMMTT_HHMM.json` (nur diese Dateien anlegen, nie eine Karte oder andere Datei ändern oder löschen).
- Artefakt „Racecard heute“: slug `9f164b63-af54-4a00-909d-49a365241220`.
- Repo: https://github.com/arauch6363-crypto/pt2026 (öffentlich), immer der Stand von main – liegt schon unter
  `/home/claude/pt2026` (siehe Aufgabentext).
- Datum und Uhrzeit immer französische Zeit (Europe/Paris), Datum JJJJMMTT = heute
  (`TZ=Europe/Paris date +%Y%m%d`).
- Große Tool-Ergebnisse landen als Datei unter `/tmp/claude-tool-results/…` oder `~/.claude/projects/*/tool-results/`.
  Niemals base64 oder die ganze Karte in die Unterhaltung kopieren.
- Keine geplanten Aufgaben anlegen, ändern oder löschen.

## 1. Vorbereitung

- Commit merken (`git -C /home/claude/pt2026 rev-parse --short HEAD`).
- Arbeitsordner `/home/claude/rd` anlegen. Alle Skripte mit `python3 -I` aufrufen.
- Drive-Tools laden: ToolSearch `select:mcp__Google_Drive__search_files,mcp__Google_Drive__download_file_content,mcp__Google_Drive__create_file`
  (heißen sie anders, z. B. mit Präfix `mcp__claude_ai_Google_Drive__`, ToolSearch mit „Google Drive“ suchen).

## 2. Karte und bisherige Durchgänge holen

- search_files mit `parentId = '1K0W0TtV5JGE7UZSEwErU9NVkqvb-k_XX' and (title = 'racecard_JJJJMMTT_daten.json.gz' or title = 'racecard_JJJJMMTT.html' or title contains 'durchgang_JJJJMMTT_')`,
  excludeContentSnippets=true.
- **KARTE** = `/home/claude/rd/racecard_JJJJMMTT_daten.json.gz`, falls es sie gibt; sonst `/home/claude/rd/racecard_JJJJMMTT.html`
  (nur wenn unter 10 MB). Gibt es keine von beiden: abbrechen mit „Heute noch keine Karte in Drive.“.
  Alle Skripte lesen beide Formate; unten steht KARTE für diesen Pfad.
- download_file_content für die Karte (nur die gewählte Datei) und jede `durchgang_JJJJMMTT_*.json`. Dann dekodieren (das Skript findet die
  gespeicherten Ergebnisse selbst; kam ein kleines Ergebnis direkt in der Antwort, schreibe dessen JSON zuerst nach
  `/home/claude/rd/_inline_<n>.json`):

```
python3 -I - <<'PY'
import json, base64, glob, os
from pathlib import Path
quellen = glob.glob('/tmp/claude-tool-results/**/*', recursive=True) + glob.glob(os.path.expanduser('~/.claude/projects/**/tool-results/*'), recursive=True) + glob.glob('/home/claude/rd/_inline_*.json')
for f in quellen:
    if not os.path.isfile(f): continue
    try:
        d = json.loads(open(f, encoding='utf-8').read())
        if isinstance(d, list) and d and isinstance(d[0], dict) and 'text' in d[0]: d = json.loads(d[0]['text'])
    except Exception: continue
    if isinstance(d, dict) and d.get('content') and str(d.get('title', '')).startswith(('racecard_', 'durchgang_')):
        Path('/home/claude/rd', d['title']).write_bytes(base64.b64decode(d['content'])); print('ok', d['title'])
PY
```

## 3. Plan

- `python3 -I /home/claude/pt2026/durchgang.py plan KARTE /home/claude/rd/durchgang_JJJJMMTT_*.json`
  (ohne Durchgänge nur die Karte). Status je Rennen: offen, gelaufen, kein_festkurs, keine_kandidaten, araber, erledigt.
- **Karte noch nicht aktuell:** Nennt der Anlass (`<routine-fire-payload>`) Rennen mit „Festkurse da“, die laut Plan
  noch `kein_festkurs` haben und noch nicht gestartet sind, ist die Karte in Drive vermutlich noch nicht hochgeladen.
  Dann 2 Minuten warten (`sleep 120`), Karte erneut suchen und herunterladen (Schritt 2), Plan neu – höchstens 3-mal.
  Bleibt es dabei, im Ergebnis nennen („Karte in Drive ohne die gemeldeten Festkurse“).
- Kein Rennen „offen“: Schritte 4 und 5 überspringen (nichts in Drive ablegen). Gibt es Durchgänge des Tages, trotzdem
  Schritt 6 und Schritt 7. Gibt es keine, nur die Liste (Rennen, Zeit, Status) ausgeben und enden.

## 4. Je offenes Rennen ein Subagent

- Für jedes offene Rennen einen eigenen Subagenten mit dem Agent-Tool starten (subagent_type: general-purpose),
  höchstens 4 gleichzeitig, in Reihenfolge der Startzeit; die frühesten zuerst. Auf alle warten.
- Prompt je Rennen (Platzhalter ersetzen):

  „Antworte auf Deutsch. Du bewertest genau ein Rennen: <race_id> (<RxCy>, <Zeit> Uhr, <Bahn>) auf der Karte
  KARTE. Lies zuerst vollständig mit dem Read-Tool
  /home/claude/pt2026/.claude/skills/rennkarten-durchgang-neu/SKILL.md und die dort genannten Dateien
  (/home/claude/pt2026/GLOSSARY.md, EINSICHTEN.md und DATEN.md im Skill-Ordner) und arbeite strikt nach dem Skill. Fakten
  nur über `python3 -I /home/claude/pt2026/.claude/skills/rennkarten-durchgang-neu/scripts/blatt.py KARTE <RxCy>`;
  gib nie die ganze Karte aus. Bewerte jeden Kandidaten (Value mindestens +5 %) dieses Rennens, kein anderes Rennen. Schreibe dein
  Ergebnis als JSON nach /home/claude/rd/rennen_<race_id>.json mit den Feldern race_id, status (bearbeitet), vergleich
  (Rennvergleich mit Grenze und Maßstab), hinweis (z. B. Boden nur angenommen oder Start in wenigen Minuten), massstab
  (Liste der MASSSTAB-Pferde aus dem Blatt, höchstens zwei: je no, horse, fk, befund – ein bis zwei Sätze, kein Urteil;
  leere Liste, wenn das Blatt keinen nennt) und kandidaten: je
  Kandidat no, horse, urteil (wette, klein oder nein), fk (Festkurs laut Karte), mq (Mindestquote), spanne [von, bis],
  p_modell, value, pro (Liste kurzer Sätze), gegen (Liste), fragen (Liste), ausschlag (ein Satz). Alle Kandidaten
  müssen enthalten sein. Ist es kein Vollblutrennen: race_id, status araber, kandidaten leer. Prüfe die Datei mit
  `python3 -I -c "import json,sys; sys.path.insert(0,'/home/claude/pt2026'); import durchgang; durchgang.rennen_pruefen(json.load(open('/home/claude/rd/rennen_<race_id>.json')))"`
  und korrigiere, bis sie fehlerfrei ist. Antworte mir danach nur mit einer Zeile je Kandidat: Nr Name – Urteil –
  Mindestquote.“
- Fehlt danach die Datei oder ist sie fehlerhaft: den Subagenten für dieses Rennen einmal neu starten. Scheitert er
  wieder, selbst `/home/claude/rd/rennen_<race_id>.json` mit `{"race_id": …, "status": "fehler", "hinweis": "<Grund>", "kandidaten": []}`
  schreiben. Die Urteile der Subagenten unverändert übernehmen, nichts nachbewerten.

## 5. Ablegen

- HHMM = jetzt (Paris). `python3 -I /home/claude/pt2026/durchgang.py zusammenfuehren /home/claude/rd/durchgang_JJJJMMTT_HHMM.json --datum JJJJ-MM-TT /home/claude/rd/rennen_*.json`.
- In Drive anlegen: create_file mit title `durchgang_JJJJMMTT_HHMM.json`, parentId `1K0W0TtV5JGE7UZSEwErU9NVkqvb-k_XX`,
  contentMimeType `application/json`, disableConversionToGoogleType true, textContent = Inhalt der Datei (mit Read
  lesen und unverändert übergeben).

## 6. Markierte Karte veröffentlichen

- `python3 -I /home/claude/pt2026/durchgang.py markieren KARTE /home/claude/rd/racecard_heute.html --template /home/claude/pt2026/racecard_template.html /home/claude/rd/durchgang_JJJJMMTT_*.json`.
- Veröffentlichen mit dem eingebauten **Artifact**-Tool: zuerst `action: "read"` mit
  `url: https://claude.ai/code/artifact/9f164b63-af54-4a00-909d-49a365241220` (klappt das nicht:
  `https://claude.ai/artifact/9f164b63-af54-4a00-909d-49a365241220`), dann `action: "publish"` mit derselben `url` und
  `file_path: /home/claude/rd/racecard_heute.html` (kein icon, keine capabilities). Bei Konflikt einmal neu lesen und
  wiederholen. Nur wenn das Artifact-Tool fehlt: ToolSearch `select:mcp__claude-artifacts__get_artifact,mcp__claude-artifacts__list_files,mcp__claude-artifacts__publish_files`,
  get_artifact und list_files für den slug, dann publish_files mit slug, base_version, mode "patch", files
  `[{"as": "index.html", "path": "/home/claude/rd/racecard_heute.html"}]`. Gibt es beides nicht: diesen Schritt
  überspringen und das im Ergebnis sagen.
- Hat dieser Durchgang keine neuen Tipps und unterscheidet sich die Karte inhaltlich nicht von der veröffentlichten,
  darf das Veröffentlichen entfallen (im Ergebnis sagen).

## 7. Ergebnis (kurz, im Chat)

- Erste Zeile: Karte, Commit des Repos, Zeit des Durchgangs.
- `python3 -I /home/claude/pt2026/durchgang.py tabelle /home/claude/rd/durchgang_JJJJMMTT_*.json` ausgeben (alle
  Claude-Tipps des Tages).
- Danach je Rennen eine Zeile: neu bearbeitet (mit Rennvergleich), schon erledigt, kein Festkurs (startet erneut,
  sobald Festkurse geholt sind; sonst von Hand), gelaufen, Araber, Fehler.
- Link zum Artefakt „Racecard heute“ und der Name der neuen Drive-Datei (falls angelegt).
