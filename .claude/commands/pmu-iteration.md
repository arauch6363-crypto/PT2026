Führe einen Durchlauf der PMU-Lernschleife aus. Lies zuerst STATE.md. Der gesamte Zustand liegt in Dateien, nicht im Gesprächsverlauf.

HARTE REGELN GEGEN INFORMATIONSLECKS
- Es werden nur Rennen analysiert, die noch NICHT gestartet sind. Vergangene Rennen werden nie getippt.
- Für die Analyse sind nur Informationen erlaubt, die vor dem Start veröffentlicht wurden: Programm, Formen, Presse, Pronostics, Statistiken, aktuelle Quoten.
- Jede Prognose wird VOR dem Start in data/predictions/ festgeschrieben: mit UTC-Zeitstempel und SHA-256-Hash. Den Hash zusätzlich in STATE.md eintragen. Festgeschriebene Prognosen werden nie geändert.
- Ergebnisse werden erst abgerufen, wenn das Rennen offiziell beendet ist. Taucht ein Ergebnis vor dem Festschreiben auf, wird das Rennen als "kontaminiert" markiert und nicht gewertet.

ABLAUF
A) AUSWERTEN: Für alle festgeschriebenen Rennen, die beendet, aber noch nicht ausgewertet sind:
   - Offizielles Ergebnis und Endquoten bzw. Rapports nach data/results/ speichern.
   - ledger.csv aktualisieren. Nichtstarter berücksichtigen.

B) LERNEN: Nur wenn seit der letzten Skill-Änderung mindestens [30] neue Wetten ausgewertet wurden:
   - Kennzahlen berechnen:
     - ROI bei Flat Stake (1 Einheit)
     - Trefferquote je Wettart
     - Brier Score und Log-Loss der eigenen Siegwahrscheinlichkeiten im Vergleich zu den aus den Endquoten abgeleiteten Marktwahrscheinlichkeiten (Abzug herausgerechnet)
     - CLV (Quote beim Tipp gegenüber Endquote)
   - Fehleranalyse: Welche Regeln haben bei Fehltipps gegriffen? Welche Faktoren hätten die Sieger erkannt?
   - Höchstens [2] Änderungen am Skill. Neue Regeln starten als "Hypothese". "Aktiv" werden sie erst, wenn sie sich auf NEUEN Rennen bestätigt haben. Regeln mit schlechter Bilanz nach "Verworfen" verschieben, mit Begründung.
   - Skill-Version erhöhen, CHANGELOG.md ergänzen, Bericht nach reports/iteration_XXX.md.
   - Bei weniger als [30] neuen Wetten nur Beobachtungen als Hypothesen-Notiz festhalten. Den Skill nicht ändern.

C) TIPPEN: Lade das Tagesprogramm, sofern es noch nicht in data/racecards/ liegt. Wähle die Rennen nach diesem Kriterium aus: [z. B. Quinté+ / alle Trabrennen / Felder mit mindestens 10 Startern]. Für jedes dieser Rennen, das in den nächsten [15–45] Minuten startet und noch keine Prognose hat:
   - Vollständige Rennkarte speichern: Starter, Jockey bzw. Driver, Trainer, Musique, Distanz bzw. Gewicht, Startplatz, Beschlag bzw. Eisen (Trab), aktuelle Quoten.
   - Den Skill pmu-rennanalyse anwenden, und zwar NUR mit aktiven Regeln. Hypothesen separat notieren, ohne dass sie die Wette beeinflussen.
   - Zusätzlich öffentliche Quellen von vor dem Start heranziehen. Für jede Quelle die URL notieren.
   - Für jedes Pferd eine Siegwahrscheinlichkeit angeben. Die Summe muss 100 % ergeben.
   - Wetten nur, wenn eigene Wahrscheinlichkeit × aktuelle Quote ≥ [1,15]. Wettarten: [Simple Gagnant / Simple Placé]. "Keine Wette" ist ein gültiges Ergebnis.
   - Prognose festschreiben (siehe Regeln oben).

D) ABSCHLUSS: STATE.md aktualisieren (Iteration +1, offene Rennen mit Startzeit, Skill-Version, kumulierte Kennzahlen). Danach eine Zusammenfassung von höchstens 5 Zeilen. Gab es nichts zu tun, antworte nur mit "Nichts zu tun – nächstes Rennen: <Zeit>".

ALLGEMEIN
- Nichts erfinden. Fehlende Daten als "unbekannt" eintragen.
- Bei Datenproblemen den Fehler in STATE.md dokumentieren und mit dem nächsten Schritt weitermachen.
- Nach [200] Wetten ohne positiven CLV und ohne bessere Kalibrierung als der Markt: das klar melden, statt weiter an den Regeln zu drehen.
