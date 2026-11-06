# CHANGELOG – pmu-rennanalyse

Format je Version: Datum (UTC), Iteration, Anlass (Kennzahlen bzw. Bericht), Änderungen (höchstens 2 je Lernschritt).

## v0.1 – 2026-11-06 (Iteration 0)
- Startversion, noch ohne ausgewertete Wetten.
- Grundmethode: Marktanker aus den aktuellen Gagnant-Quoten, Abzug proportional herausgerechnet. Dazu ein blinder
  Fundamentalwert aus gewichteten Faktoren je Disziplin (Softmax, Temperatur 0,15). Kombination im Log-Raum mit
  den Gewichten 0,80 Markt und 0,20 Fundamental, gekappt auf 0,5–1,6 × Marktwahrscheinlichkeit.
- Faktoren und Gewichte für TRAB, GALOPP und HINDERNIS. Abschläge für Zuverlässigkeit (Disqualifikation bzw. Sturz).
- Basis-Schutzregeln: Gagnant nur bis Quote 30, Quoten höchstens 45 Minuten alt, höchstens 2 Wetten je Rennen.
- Regeln H-T1 bis H-T3, H-G1 bis H-G3, H-H1, H-A1 und H-A2, alle mit Status „Hypothese“. Keine Regel ist aktiv.
