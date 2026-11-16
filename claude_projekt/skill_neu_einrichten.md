# Skill „rennkarten-durchgang-neu“ in claude.ai einrichten

Damit läuft die Analyse in der Claude-App (Web, Desktop, Handy) über das Abo – ohne API-Schlüssel und ohne
API-Kosten. Die Nutzung zählt auf das Kontingent des Abos.

## Einmalig

1. Paket bauen: `python3 skill_paket.py` (legt `dist/rennkarten-durchgang-neu.zip` an).
2. claude.ai → **Einstellungen → Fähigkeiten (Capabilities)** → **Code-Ausführung und Dateierstellung** einschalten
   (der Skill rechnet mit `scripts/blatt.py`).
3. Darunter bei **Skills** → **Skill hochladen** → die ZIP-Datei wählen und den Skill einschalten.
4. Optional ein eigenes Projekt „Rennkarten neu“ anlegen und den Block unten unter **Projekt → Anweisungen**
   einfügen. Das alte Projekt „Racecard-Analyse“ (alter Skill `rennkarten-durchgang`, inzwischen entfernt) löschen
   oder nicht mehr verwenden.

## Nach jeder Skill-Änderung

`python3 skill_paket.py` erneut ausführen, in claude.ai den alten Skill löschen und die neue ZIP hochladen. Hochgeladene
Skills synchronisieren sich nicht mit GitHub.

## Je Renntag

Die HTML-Karte des Tages (`racecard_JJJJMMTT.html`, mit Festkursen) in den Chat hochladen und z. B. schreiben:
„Geh Toulouse durch“ oder „Rennen R1C5“. Am Ende steht je Rennen das Ergebnis im Format des Skills (wie im
automatischen Durchgang). In der Regel braucht es das nicht: Die Aufgabe „Racecard-Durchgang API“ legt ihre Durchgänge
selbst als `durchgang_JJJJMMTT_HHMM.json` in `racecards/` ab, das Dashboard wertet sie aus.

## Projekt-Anweisungen (optional)

```
In diesem Projekt geht es um Siegwetten auf französische Galopp-Racecards. Antworte auf Deutsch.

- Nutze bei jeder Racecard-Anfrage den Skill "rennkarten-durchgang-neu" und arbeite nach ihm,
  auch wenn ich ihn nicht nenne.
- Die Karte kommt als HTML-Datei (racecard_JJJJMMTT.html). Lies sie nur über das Skript
  scripts/blatt.py des Skills, nie die ganze Datei.
- Geh eine Bahn Rennen für Rennen durch; gelaufene Rennen nur nennen, wenn ich sie anfordere.
- Ende jeder Bahn: Wett-Tabelle und das Ergebnis je Rennen im Format des Skills (alle Kandidaten).
- Widerspreche ich einem Urteil, frag nach dem, was für mich den Ausschlag gibt, sprich Widersprüche
  zu Regeln oder früheren Fällen an und notiere den Fall am Ende als Vorschlag für FAELLE.md
  (Art: Übereinstimmung, Claude lernt, Claudes Sicht behalten).
```
