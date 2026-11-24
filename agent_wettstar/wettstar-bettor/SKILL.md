---
name: wettstar-bettor
description: Platziert Festkurs-Siegwetten (Sieg FK) auf wettstar-pferdewetten.de per Playwright in einer einzigen Browser-Session mit einem Login. Enthält Rennlink-Auflösung, Guthaben-Check und Dialog-Validierung. Verwenden für die Tipps (NAP/BET) aus dem Payload der Aufgabe Racecard-Durchgang oder nach ausdrücklicher Nutzeranweisung.
---

# Wettstar Festkurs-Wetten

Gilt nur im Auftrag laut Agent-Systemprompt (dessen Sicherheitsregeln haben Vorrang).

## Ablauf
1. Zertifikate importieren (siehe Systemprompt, UMGEBUNG), falls noch nicht geschehen.
2. `/tmp/ws/bets.json` schreiben, eine Liste mit je einem Objekt pro Wette:
   `{"bahn":"Deauville","zeit":"16:50","nr":14,"name":"SUPERCLASS","min_fk":6.5,"stake":10}`
   - `zeit` = Startzeit (französische Zeit), `nr` = Startnummer (Zahl vor dem Punkt),
     `min_fk` = Mindest-Festkurs (mq aus dem Payload), `stake` = 10 (NAP) oder 5 (BET).
   - `bahn` und `name` wie auf der Karte (Großschreibung, Akzente, Apostrophe egal; das Skript vergleicht normalisiert).
   - Optional `"race_url"`, wenn der Rennlink bekannt ist.
3. Ausführen (Pfad `scripts/bet_multi.py` relativ zu diesem Skill-Ordner):
   `python3 <skill-pfad>/scripts/bet_multi.py /tmp/ws/bets.json LIVE`
   WS_USER und WS_PASS müssen als Umgebungsvariablen gesetzt sein (siehe Systemprompt).
   Ohne `LIVE` läuft nur ein Dry-Run bis zum Dialog (nicht bestätigen).
4. Ausgabe lesen: `PLATZIERT <Name>: Ticket <Nr>` = Erfolg, `ABBRUCH: ...` = nicht gewettet.

## Regeln
- Mehrere Wetten immer in EINEM Aufruf (ein Login).
- Das Skript nicht neu schreiben und nicht ändern, solange es nicht nachweislich scheitert.
- Kein separater Dry-Run, wenn das Skript unverändert ist (es validiert den Dialog selbst).
- Exit-Code 3 oder Meldung „keine Bestätigung gesehen“: NICHT erneut ausführen, erst „Offene Wetten“ prüfen.
- Zu wenig Guthaben (Exit-Code 2): melden und stoppen, keine Einzahlung.
- Keine Screenshots lesen, solange die Textausgabe zur Fehlersuche reicht.
- Zugangsdaten nie in Dateien, Befehle oder Berichte schreiben.

## Seitenwissen
- Cookie-Banner: `get_by_text("Ablehnen", exact=True)` (kein Button-Role).
- Login-Formular erscheint erst nach Klick auf den Header-Button „Login“, dann `#login-username`.
- Seiten mit `wait_until="networkidle"` laden (SPA).
- Rennlink: Startseite > `a[href*='meeting=']` (Text enthält Bahn) > Meeting-Seite > `a[href*='/race/']` mit Text „Start HH:MM Uhr“. Bei mehreren Meetings derselben Bahn stoppt das Skript.
- Wettsteuer 5 % kommt zum Einsatz hinzu (10 € → 10,50 €).
