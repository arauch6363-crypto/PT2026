# Interview: neuer Skill rennkarten-durchgang

Arbeitsnotizen aus dem /grill-with-docs-Interview (Start 11.11.2026). Wird beim Schreiben des neuen Skills aufgelöst; Begriffe stehen in `GLOSSARY.md`.

## Entscheidungen

| # | Frage | Entscheidung |
|---|---|---|
| Q1 | Neu- oder Umbau | Neuaufbau aus dem Vorgehen des Nutzers; alter Skill nur als Checkliste für Nachfragen |
| Q2/Q12 | Rennauswahl | Keine eigene Stufe: jedes Rennen mit mindestens einem Kandidaten; nur Vollblut |
| Q3/Q7/Q15 | Ausgangsmenge | Nur Kandidaten (Value > 0), keine Kursgrenze |
| Q6 | Begriff | Value = Festkurs Sieg × Modell-Siegchance − 1 |
| Q8/Q17 | Einsatz | Analyse entscheidet; Einsatz mechanisch ⅛ Kelly auf die eigene Siegchance |
| Q9 | Methode | Modell-Siegchance zur eigenen Siegchance korrigieren, Value neu rechnen |
| Q10 | Blind/Markt | Zweiteilung entfällt; Prognose, Presse-Tipps, Cribles nur Kontext |
| Q11 | Wettart | Nur Sieg |
| Q13 | Übungskarte | 10.11.2026 (Fontainebleau R1, Amiens R4), Entscheidung vor Blick aufs Ergebnis |
| Q14 | Schwelle | Wette bei eigenem Value ≥ +20 % |
| Q16 | Grenzen | Keine festen Grenzen je Rennen/Veranstaltung |
| Q18 | Vorgehen | Rennen für Rennen; ab ca. Rennen 5 sagt Claude die Entscheidung vorher |
| Q19 | Modell-Rang | Rang nach Power-Zahl im Feld |
| Q20 | Rang-Grenze | Keine feste Regel, aber der relative Modell-Rang wiegt schwer |
| Q21 | Rolle der Argumente | Bei Value ≥ +20 % vor allem Prüfung auf Gegenargumente; Pro-Argumente heben die Chance nur, wenn modellfremd. Unter +20 % braucht es ein modellfremdes Pro-Argument |
| Q22 | Reise-Argument | Britische Trainer: Plus (lange Reise, höheres Durchschnittsniveau GB-Flachrennen). Spanische, deutsche, (weit reisende) französische Trainer: nur begrenzt |
| Q23 | Boden | Bei sehr weichem Boden zählt die genaue Bodenangabe; Bewährung genau auf dieser Angabe ist ein starkes Argument (hier für die Favoritin, gegen Kenergy) |

| Q26 | Fragezeichen | Zum Ausprobieren: Fragezeichen (unbewiesene Bedingung) heben die Schwelle (Startwert +15 Punkte je Fragezeichen), Gegenargumente senken die Chance |
| Q27 | Hinterer Modell-Rang | Kein Fragezeichen, sondern ein Gegenargument |
| Q21 (revidiert) | modellfremd/modellbekannt | Nutzer will **keine** Unterscheidung: auch Argumente, die das Modell kennt, bewegen die eigene Siegchance (Doppelzählung bewusst; Details offen) |

## Fakten zum Modell (für „modellfremd“)

- Kennt: Startzahl, ARR/TR/RTR (auch feldrelativ), Duelle und indirekte Vergleiche, Bodenbilanz und Abstammung je Bodengruppe, Klasse, Trainer/Jockey-Statistik, Pausen, Wallach/Scheuklappen, Tempo/Laufstil/Box.
- Kennt nicht: Land des Trainers (Reise-km misst nur ab französischer Heimatbahn), Läufe, die PMU gar nicht meldet, vermutlich die feine Bodenangabe innerhalb einer Bodengruppe.
- Modell-Siegchance enthält laut Doku derzeit keine Prognose/Tipps (Prognose-Schicht nur als Schatten).

## Beispiel-Entscheidungen (10.11.2026)

- **R1C1 Kenergy (5)**: FK 6,0, Modell 27,2 % (Rang 2/7), Value +63 % → **Wette**. Modellfremd: britischer Trainer (+). Gegen: Favoritin Shunshoku hat genau auf Très souple gewonnen, Kenergy nur auf Souple (−). Übrige Gründe (ARR/TR, indirekt +1,7 L, unexposed) kennt das Modell.
- **R1C1 Trevilly (4)**: FK 16, Modell 6,7 % (Rang 6/7), Value +7 % → **keine Wette**. Value unter Schwelle, schlechter relativer Rang; Fragezeichen (erstmals Wallach, einziger neuer Lauf auf PMH-Bahn nach fast einem Jahr Pause).

- **R1C3 La Belle Isola (1)**: FK 4,5, Modell 39,8 % (Rang 1/11), Value +79 % → **Wette** („starker Vorteil“). Fragezeichen: ARR gewichtsbereinigt nur Rang 5 (60 kg Höchstgewicht; modellbekannt), nie auf Très souple gelaufen, Abstammung Boden ohne Aussage (Vater mit 36 Läufen). Distanz bewährt (1001–1200 m: 4 Läufe, 2 Siege).
- **R1C3 Ozark James (3)**: FK 11, Modell 12,0 % (Rang 3/11), Value +32 %, Value-Faktor gold → **keine Wette**, „zu viele Fragezeichen“: erstmals Scheuklappen („warum heute?“), erstmals 1200 m (bisher nur 1201–1600 m), Bewährung auf Très souple nur im Claimer, Abstammung ohne Beleg für den Boden. Dafür sprachen: ARR gewichtsbereinigt Rang 1, indirekt +3,3 L, einziger Führender.

## Offen

- Wie groß ist eine Korrektur (Skala für modellfremde Argumente)?
- Wie wird der relative Modell-Rang konkret gewichtet?
- Weitere Rennen der Übungskarte.
