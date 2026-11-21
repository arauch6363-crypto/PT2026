# Aufgabe „Durchsicht“

Der Nutzer bewertet Claudes Urteile aus den automatischen Durchgängen, Rennen für Rennen, in einer Claude-Code-Sitzung
im Repo. **Ziel:** Ein NAP von Claude ist genau das, was der Nutzer selbst spielen würde. Daraus entstehen Fälle,
Testfälle, Einsichten und Regeln; die Regeln dafür stehen in `.claude/skills/rennkarten-durchgang-neu/LERNSCHLEIFE.md`.
Antworte auf Deutsch, knapp, mit den Begriffen aus `GLOSSARY.md`.

## Zuerst lesen

`SKILL.md`, `EINSICHTEN.md`, `LERNSCHLEIFE.md` und `DATEN.md` im Skill-Ordner, `GLOSSARY.md`; zum Nachschlagen
früherer Fälle `docs/faelle_rennkarten_durchgang.md` und `docs/interview_rennkarten_durchgang.md` (Abschnitt
„Offen“ zeigt, wo die letzte Durchsicht stand).

## Daten

Drive-Ordner racecards und das Herunterladen wie in `aufgabe_ergebnisanalyse.md` („Feste Angaben“, Schritt 3): je
Rennen gilt der jüngste `durchgang_JJJJMMTT_HHMM.json`; Karte `racecard_JJJJMMTT_daten.json.gz`. Downloads und Uploads
in einen eigenen Ordner im Scratchpad, Python mit `-I`. Fakten je Rennen über
`python3 -I .claude/skills/rennkarten-durchgang-neu/scripts/blatt.py KARTE RxCy`.

## Auswahl

Rennen mit Claude-Tipp (`wette`, `klein`) und knappe Ablehnungen (Value über +30 % oder Modell-Rang 1–2); andere auf
Zuruf. Araber und AQPS zählen nicht. Nur gelaufene Rennen, und bewertet wird die Entscheidung **vor** dem Rennen: Der
Einlauf bleibt aus der Unterhaltung.

## Je Rennen

1. **Zeigen:** Rennkopf (Rennart, Distanz, Boden, Feld, Klassenindex, Tempo, FK-Favorit, Top-ARR, Höchstgewicht), je
   Kandidat FK · Rang · Value, Pro / Gegen / Fragezeichen, Claudes Urteil mit Spanne und Ausschlag-Satz; Rennvergleich
   und Maßstab. Dann **eine** gezielte Frage, wo es spannend ist.
2. **Klären:** Bei Abweichung nachfragen, bis klar ist, welches Argument falsch gewichtet oder übersehen wurde.
   Widerspricht das Urteil einer Regel oder einem früheren Fall: „Ausnahme oder Regel zu streng?“ – eine andere
   Perspektive ist erwünscht. Nachschlagbare Fakten selbst im Blatt prüfen, auch Behauptungen des Nutzers.
3. **Ablegen** (siehe unten) und committen.

Fertig mit einem Rennen, wenn jeder Kandidat eine Zeile im Fallarchiv hat und der Testfall angelegt ist.

## Ablage

- **Fallarchiv `docs/faelle_rennkarten_durchgang.md`:** je Kandidat eine Zeile in „Wetten“ (kleine Wetten mit
  **klein**) bzw. „Keine Wette“: `| Pferd (TT.MM. Bahn RxCy) | Art | Lage | Ausschlag |`. Art *Übereinstimmung* (ein
  Satz), *Claude lernt* (Urteil des Nutzers gilt, mit „**Claude hatte …**“, dazu eine Zeile unter „Abweichungen
  Claude ↔ Nutzer“) oder *Claudes Sicht behalten* (Claudes Argument vertretbar, keine Regel).
- **`docs/interview_rennkarten_durchgang.md`:** je Rennen ein Abschnitt `### TT.MM. Bahn RxCy – …` vor „## Stand“ mit
  den Kernsätzen des Nutzers wörtlich und dem Ergebnis; „Offen“ fortschreiben.
- **Testfall:** nach `aufgabe_testsatz.md`, „Neuer Testfall“.
- **Werkzeug-Lücke** (das Blatt zeigt etwas nicht oder missverständlich): in `scripts/blatt.py` beheben, in `DATEN.md`
  erklären.

## Sitzungsende

Verdichten und Regeln nach `LERNSCHLEIFE.md`; Testsatz einmal für alle Skill-Änderungen der Sitzung. Vor dem Push
`python -m pytest -q tests` (bei Code-Änderungen auch `python selftest.py`), dann PR.
