# Integrieren

Teil des Skills `ergebnis-analyse`, nach der Entscheidung des Nutzers.

- **ja**: den Text unverändert eintragen; eine neue Einsicht in den Abschnitt ihres Prüfschritts, aus einem Fall mit
  Vermerk „vorläufig“. Bei `zusammenfassen` die alten Einträge entfernen und die stillgelegten Kennungen eintragen
  (`VERDICHTEN.md`).
- **geaendert**: den Text nach der Notiz des Nutzers umschreiben (`SKILL.md`, „Schreiben für den Durchgang“) und vor dem
  Eintragen im Chat zeigen.
- **nein**: die Notiz ist die Begründung; die Dateien bleiben, wie sie sind.

Kennungen sind dauerhaft (`LERNSCHLEIFE.md` des Durchgang-Skills).

Danach **einmal** den Testsatz für alle eingetragenen Änderungen zusammen (`claude_projekt/aufgabe_testsatz.md`,
gestuft). Bei einem **Rückschritt** dem Nutzer den Konflikt zeigen: Testfall, sein damaliges Urteil, das Urteil mit der
neuen Regel. Er entscheidet: Regel umformulieren oder das erwartete Urteil im Testfall ändern. Eine Änderung am
Testfall bekommt in `tests/testsatz_durchgang/erwartet.json` beim Kandidaten `geaendert` mit Datum und Grund.

Fertig, wenn jede Entscheidung eingetragen ist und der Testsatz „Übernehmen: ja“ meldet oder der Nutzer über den
Konflikt entschieden hat.
