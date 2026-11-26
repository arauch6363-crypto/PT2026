# Wett-Agent Wettstar (Sieg FK)

Spielt die Claude-Tipps eines Durchgangs (Aufgabe „Racecard-Durchgang“) als Festkurs-Siegwetten bei
wettstar-pferdewetten.de: **NAP 10 €, BET 5 €**, sofort nach der Auslösung, nur bei Festkurs ≥ Mindestquote (mq).

Reicht das Guthaben nicht für alle Tipps, wettet der Agent von oben (Payload-Reihenfolge = Startzeit), solange
Einsatz + 5 % Steuer gedeckt sind, und hört beim ersten ungedeckten Tipp auf. Er zahlt nie ein und holt nichts nach;
erst die nächste Auslösung mit ausreichendem Guthaben wettet wieder. Beispiel: 10 × 5 € bei 40 € → 7 Wetten
(7 × 5,25 € = 36,75 €).

- `SYSTEMPROMPT.md`: Konfiguration des Agenten (Eingabeformat, Sicherheitsregeln, Ablauf).
- `wettstar-bettor/`: Skill mit `scripts/bet_multi.py` (Playwright, ein Login für alle Wetten).
  Absichtlich nicht unter `.claude/skills/`, damit Claude-Code-Sessions in diesem Repo den Skill nicht laden.
- Zugangsdaten **nie** hier ablegen (das Repo ist öffentlich). `WS_USER`/`WS_PASS` als Secrets des
  deployten Agenten setzen.

Eingabe (Payload der API-Auslösung):

```json
{"datum": "2026-11-24", "durchgang": "durchgang_20261124_1412.json",
 "tipps": [{"race_id": "20261124R1C3", "rennen": "R1C3", "bahn": "DEAUVILLE", "zeit": "14:05",
            "nr": 7, "name": "PFERDENAME", "kennzeichen": "NAP", "fk": 6.5, "mq": 5.0}]}
```

Quellen in der Durchgang-Aufgabe: `nr`, `name` (= horse), `fk`, `mq`, Urteil („wette“ → NAP, „klein“ → BET) aus den
Rennen dieses Durchgangs; `bahn`, `zeit`, `rennen` aus `durchgang.py plan`. Nur neu bewertete Rennen schicken, damit
kein Tipp zweimal gespielt wird.

Test der Namens-/Bahnzuordnung und der Guthaben-Logik (ohne Browser): `python3 -m pytest -q tests/test_bet_multi.py`.
