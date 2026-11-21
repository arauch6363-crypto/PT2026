# Aufgabe „Ergebnisanalyse“

Anweisungen für die Aufgabe in Claude Code (claude.ai/code/routines, **manuell gestartet**). Der kurze Text der
Aufgabe verweist hierher; Änderungen am Ablauf laufen über einen PR in diesem Repo. Grundsatz: ADR 0003. Urteilsteil:
Skill `ergebnis-analyse` (`.claude/skills/ergebnis-analyse/SKILL.md`) – vor Schritt 4 vollständig lesen.

Antworte auf Deutsch. Die Aufgabe läuft in zwei Teilen in derselben Sitzung: **Teil A** analysiert den ältesten noch
offenen Renntag und legt die Vorschläge auf die Seite; dann wartet sie. **Teil B** beginnt, wenn der Nutzer in der
Sitzung „entschieden“ schreibt (er nimmt sich die Seite im Lauf des Tages vor).

## Feste Angaben

- REPO = Wurzel des Repos dieser Sitzung (`git rev-parse --show-toplevel`). Alle Skripte mit `python3 -I`.
- Arbeitsordner AO = `/tmp/ea` (nicht im Repo).
- Drive-Ordner racecards (Karten, Durchgänge): `1K0W0TtV5JGE7UZSEwErU9NVkqvb-k_XX`.
- Drive-Ordner `parquet/pmu_runners` (Einlauf, Datei `JJJJMMTT.parquet`, liegt am Morgen nach dem Renntag vor):
  `1FKnNBVxIsOfUjTePuZHVSgQ3-jfFlwmE`.
- Seite „Ergebnisanalyse“: `https://claude.ai/artifact/C5NsxheLAUouXqWowp4K8K` (Vorlage `REPO/ergebnisanalyse_seite.html`,
  Datenbank-Sammlungen `tage` und `vorschlaege`).
- Erster Tag mit automatischen Durchgängen: 20261115. Datum immer französische Zeit.
- Drive nur lesen; nichts in Drive anlegen, ändern oder löschen. Keine geplanten Aufgaben anlegen oder ändern.

## Teil A – analysieren

### 1. Vorbereitung

- `pip install -q pyarrow`; `mkdir -p AO`; Commit merken (`git -C REPO rev-parse --short HEAD`).
- Drive-Tools laden: ToolSearch `select:mcp__Google_Drive__search_files,mcp__Google_Drive__download_file_content`
  (heißen sie anders, ToolSearch mit „Google Drive“). Artefakt-Datenbank: ToolSearch `select:ArtifactData`.

### 2. Tag bestimmen

- search_files mit `parentId = '1K0W0TtV5JGE7UZSEwErU9NVkqvb-k_XX' and title contains 'durchgang_2026'`,
  excludeContentSnippets=true, pageSize 100, alle Seiten. Tage = Datumsteil der Titel `durchgang_JJJJMMTT_HHMM.json`
  ab 20261115, ohne heute.
- `python3 -I REPO/ergebnis_analyse.py naechster-tag <Tage …>` → TAG. Bei „keiner“: melden „Alle Renntage mit
  Durchgang sind analysiert.“ und enden.
- search_files mit `parentId = '1FKnNBVxIsOfUjTePuZHVSgQ3-jfFlwmE' and title = 'TAG.parquet'`. Fehlt die Datei:
  melden „Einlauf vom TAG noch nicht in Drive“ und enden.

### 3. Material holen und bauen

- download_file_content für `TAG.parquet`, `racecard_TAG_daten.json.gz` (Ordner racecards; fehlt sie,
  `racecard_TAG_daten.json`) und jede `durchgang_TAG_*.json`. Die Inhalte landen als Datei unter
  `~/.claude/projects/*/tool-results/` oder `/tmp/claude-tool-results/`, entweder roh (Binärdatei) oder als JSON mit
  base64 im Feld `content`. Je Datei unter ihrem Titel nach AO kopieren bzw. dekodieren; nie den Inhalt in die
  Unterhaltung holen.
- `python3 -I REPO/ergebnis_analyse.py material AO/racecard_TAG_daten.json.gz AO/TAG.parquet AO/durchgang_TAG_*.json --aus AO/analyse_TAG.json`
- `python3 -I REPO/ergebnis_analyse.py protokoll AO/analyse_TAG.json` (schreibt `REPO/auswertung/regelprotokoll.csv`),
  dann `python3 -I REPO/ergebnis_analyse.py bericht > AO/bericht.json`.

### 4. Analysieren

- Skill `ergebnis-analyse` Schritt 1 bis 4 mit KARTE = `AO/racecard_TAG_daten.json.gz`, ANALYSE = `AO/analyse_TAG.json`.
- Vorschläge nummerieren: id = `TAG-1`, `TAG-2`, … (Verdichtung: `TAG-V1`, …; Regel unter Druck: `TAG-D1`, …).

### 5. Seite füllen

- `vorschlaege.csv` fortschreiben: Vorschläge als JSON-Liste nach `AO/vorschlaege_TAG.json` (Felder wie die CSV,
  `entscheidung` offen), dann `python3 -I REPO/ergebnis_analyse.py vorschlaege AO/vorschlaege_TAG.json`.
- ArtifactData `batch` auf die Seite (url oben), höchstens 50 Einträge je Batch:
  - `set` in `tage`, doc_id TAG: `datum` TAG, `titel` (z. B. „Mi 18.11. · Pau“), `zaehlung` aus dem Material,
    `hinweis` (ein bis zwei Sätze: Lage des Tages, z. B. Häufung „Ermessen“), `faelle` (je Fall art, rennen, no, horse,
    urteil, fk, pos, `regel` = Kennung oder „Ermessen“, `befund` = ein Satz), `regelprotokoll` = Inhalt von
    `AO/bericht.json`.
  - `set` in `vorschlaege`, doc_id = id: alle Felder des Vorschlags aus dem Skill plus `datum` TAG, `entscheidung`
    „offen“, `notiz` „“.
  - Gibt es den Tag schon (erneuter Start), zuerst lesen und mit `if_version` schreiben.

### 6. Melden und warten

Im Chat: Link zur Seite, je Siegergruppe die Zahl, die Vorschläge als Liste (id – Titel), und der Satz „Entscheide
auf der Seite und schreib mir dann ‚entschieden‘.“ Dann die Antwort beenden.

## Teil B – integrieren (nach „entschieden“)

1. ArtifactData `query` auf `vorschlaege` mit `entscheidung` ungleich „offen“; dazu die gelesenen Versionen merken.
   Entscheidungen nach `vorschlaege.csv` übernehmen (`ergebnis_analyse.py vorschlaege` mit id, entscheidung, notiz,
   gewicht). Noch offene bleiben offen und erscheinen beim nächsten Lauf wieder.
2. Für **ja** und **geaendert** den Text in `SKILL.md` bzw. `EINSICHTEN.md` von `rennkarten-durchgang-neu` eintragen
   (Skill `ergebnis-analyse`, `INTEGRIEREN.md`; bei „geaendert“ den neuen Text zuerst im Chat zeigen und auf ein Ok
   warten). Eine neue Kennung muss danach von `durchgang.kennungen()` gefunden werden.
3. Gab es eine Änderung am Skill: Testsatz **einmal** für alle Änderungen zusammen nach
   `claude_projekt/aufgabe_testsatz.md` laufen lassen (gestuft: erst ein Lauf je Testfall). Rückschritt →
   Konflikt dem Nutzer zeigen und seine Entscheidung abwarten (Regel umformulieren oder Testfall ändern), dann den
   Testsatz erneut. Erst bei „Übernehmen: ja“ ablegen (`--ablegen`).
4. `python3 -I REPO/ergebnis_analyse.py tag-abschliessen TAG --commit <Commit> --vorschlaege <Anzahl>`.
5. Commit auf einem neuen Branch (Name z. B. `ergebnisanalyse-TAG`, sonst der Branch der Sitzung): Änderungen am
   Skill, `auswertung/*.csv`, gegebenenfalls Testsatz-Ergebnis. PR gegen `main` mit: Tag, Siegergruppen,
   angenommene/abgelehnte Vorschläge, Testsatz-Ergebnis. Auch ohne angenommenen Vorschlag gibt es den PR (nur
   Protokoll).
6. Im Chat: Link zum PR, eine Zeile je Vorschlag mit Entscheidung, und ob ein weiterer Tag offen ist
   (`naechster-tag` erneut).

## Aufgabentext für die Routine (kurz)

```
Führe die Aufgabe „Ergebnisanalyse“ nach claude_projekt/aufgabe_ergebnisanalyse.md im Repo aus (Teil A). Wenn ich
danach „entschieden“ schreibe, Teil B.
```
