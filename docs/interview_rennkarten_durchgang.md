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

| Q29 | Rechnen? | **Nein.** Kein arithmetisches Verfahren; der Nutzer wettet, wenn ihn das Pferd insgesamt überzeugt. Ersetzt Q9 (eigene Siegchance), Q14 (Schwelle auf eigenen Value), Q24/Q28/Q30/Q32 (Faktoren) |
| Q33 | Form der Entscheidung | Je Kandidat: Pro-Argumente, Gegenargumente, Fragezeichen → Gesamturteil Wette ja/nein mit einem Satz zum Ausschlag |
| Q34 | Einsatz/Mindestquote | Mechanisch aus der Modell-Siegchance: ⅛ Kelly; Mindestquote = 1,2 ÷ Modell-Siegchance (ersetzt Q17) |
| Q35 | Untergrenze +20 %? | Keine harte Untergrenze: auch unter +20 % Value wettbar, wenn sehr viel dafür spricht (Value > 0 bleibt Voraussetzung) |
| Q36 | Faustregel | Ja, als Orientierung: +20–50 % höchstens ein Fragezeichen und kein gewichtiges Gegenargument; über +50 % ein bis zwei Fragezeichen tragbar. Dazu Fallsammlung im Skill; Abweichungen ausdrücklich nennen |

| Q38 | Aufgewicht | Fragezeichen: Marke über der des letzten Siegs. Wiegt schwerer bei exposed Pferden (viele Starts, älter), leichter bei jungen/unexposed (Steigerung möglich) |

## Fakten zum Modell (für „modellfremd“)

- Kennt: Startzahl, ARR/TR/RTR (auch feldrelativ), Duelle und indirekte Vergleiche, Bodenbilanz und Abstammung je Bodengruppe, Klasse, Trainer/Jockey-Statistik, Pausen, Wallach/Scheuklappen, Tempo/Laufstil/Box.
- Kennt nicht: Land des Trainers (Reise-km misst nur ab französischer Heimatbahn), Läufe, die PMU gar nicht meldet, vermutlich die feine Bodenangabe innerhalb einer Bodengruppe.
- Modell-Siegchance enthält laut Doku derzeit keine Prognose/Tipps (Prognose-Schicht nur als Schatten).

## Beispiel-Entscheidungen (10.11.2026)

- **R1C1 Kenergy (5)**: FK 6,0, Modell 27,2 % (Rang 2/7), Value +63 % → **Wette**. Modellfremd: britischer Trainer (+). Gegen: Favoritin Shunshoku hat genau auf Très souple gewonnen, Kenergy nur auf Souple (−). Übrige Gründe (ARR/TR, indirekt +1,7 L, unexposed) kennt das Modell.
- **R1C1 Trevilly (4)**: FK 16, Modell 6,7 % (Rang 6/7), Value +7 % → **keine Wette**. Value unter Schwelle, schlechter relativer Rang; Fragezeichen (erstmals Wallach, einziger neuer Lauf auf PMH-Bahn nach fast einem Jahr Pause).

- **R1C3 La Belle Isola (1)**: FK 4,5, Modell 39,8 % (Rang 1/11), Value +79 % → **Wette** („starker Vorteil“). Fragezeichen: ARR gewichtsbereinigt nur Rang 5 (60 kg Höchstgewicht; modellbekannt), nie auf Très souple gelaufen, Abstammung Boden ohne Aussage (Vater mit 36 Läufen). Distanz bewährt (1001–1200 m: 4 Läufe, 2 Siege).
- **R1C3 Ozark James (3)**: FK 11, Modell 12,0 % (Rang 3/11), Value +32 %, Value-Faktor gold → **keine Wette**, „zu viele Fragezeichen“: erstmals Scheuklappen („warum heute?“), erstmals 1200 m (bisher nur 1201–1600 m), Bewährung auf Très souple nur im Claimer, Abstammung ohne Beleg für den Boden. Dafür sprachen: ARR gewichtsbereinigt Rang 1, indirekt +3,3 L, einziger Führender.

- **R1C4 Interactiv (2)**: FK 35, Modell 6,7 % (Rang 6/16), Value +135 % → **keine Wette** („Boden zu großes Fragezeichen, dass er sein Aufgewicht vom letzten Sieg verteidigen kann“). Fragezeichen: nach Handicap-Sieg auf Bon 3 kg höher (Marke 40 → 43), heute Très souple statt guter Bahn; auf schwerem Boden einmal schlecht (Collant 9/12), auf weichem einmal ordentlich; Abstammung ohne Plus. Kaum Pro-Argumente (ARR Rang 14/16). Nutzer liest auch das Crible (Pressenotiz) als Quelle.

- **R1C4 Grand Scoop (3)**: FK 16, Modell 13,6 % (Rang 2/16), Value +118 % → **Wette** („Fragezeichen nicht groß genug, um bei diesem Value gegen eine Wette zu opponieren“). Prüfreihenfolge des Nutzers:
  1. Letzter Lauf im Kontext (6. im Rennen, das Interactiv gewann, auf guter Bahn) → Form okay.
  2. Lauf unter heutigen Bedingungen gesucht: 22.08. Deauville 1200 m Collant, 3. → **Referenzlauf**; Marke damals ähnlich wie heute.
  3. Bodenvorlieben (Bilanz) bestätigen Neigung für schweren Boden; Abstammung ohne Signal; Distanz passt.
  4. Trainerform 30 Tage (G. Mossé): kalt, nicht extrem → notiert.
  5. Referenzlauf vertieft: ARR dort 38,1; über diesen Lauf direkt vor 5 heutigen Gegnern und indirekt vorne → starkes Pro. Aber: 38,1 gehört nicht zu den Top-Formen im Feld.
  6. Startbox: gut (Box-Abweichung +0,06).
  7. Bahnerfahrung Fontainebleau (schwierige Bahn): einmal gelaufen, unplatziert → nicht hart angekreidet.
  8. Gesamturteil gegen Value und Modell-Rang.

- **R1C4 Mister Chang (4)**: FK 25, Modell 5,9 % (Rang 7/16), Value +47 % → **Wette** (mit Grand Scoop die Value-Wetten des Rennens). Pro: CGD-Kennzeichen (auf Bahn, Distanz und Boden gewonnen); Formen auf weichem Boden mit höherer Marke nah dran (Chantilly Souple 5/8 bei 1,5 kg höherer Marke, ARR gewichtsbereinigt 39,5 – weit vorne im Feld; Deauville Collant 9/16 bei 2 kg höherer Marke, 5 L geschlagen); Fontainebleau: 5 Läufe, 1 Sieg, 2 Plätze (u. a. 17.03. Souple 4/15); derselbe Jockey (H. Journiac) mit zwei Siegen auf dem Pferd. Fragezeichen: 1,5 kg über letzter Siegmarke (bei „relativ jungem“ Pferd leicht). Letzter Lauf 14/16 auf Bon „außen vor gelassen“ (anderer Boden, nicht weit geschlagen). Trainer/Jockey-Form unauffällig. Nicht vom Nutzer genannt, aber auf der Karte: 12.05. Chantilly **Très souple** Hcp 3/16 bei Marke 38,5.
- **R1C4 Interactiv**: Nutzer bestätigt am Ende (Satz abgebrochen) vermutlich „keine Wette“.

| Q40 | Prüfliste | Ja; Nutzer erläutert beim nächsten Mal ausführlicher, evtl. 1–2 Schritte mehr |
| Q41 | Referenzlauf | Der jüngste Lauf, der den heutigen Bedingungen am nächsten kommt. Ältere Läufe können Referenz sein, wenn auf derselben Bahn oder unter regulären Bedingungen gelaufen; ein gestörter Lauf (Behinderung o. Ä.) zählt nicht für bare Münze |
| Q42 | Kalter Trainer | Gegenargument, abgestuft nach Stärke |
| Q43 | Bahn | Plus nur, wenn auf der Bahn schon gewonnen oder platziert; sonst neutral (kein Fragezeichen) |
| Q44 | Rang-Wording | „vorderer/hinterer“ Modell-Rang |

- **R1C4 Laith (10)**: FK 11, Modell 11,2 % (Rang 3/16), Value +23 % → **keine Wette** (im Rennvergleich Rang 3 von 4 Kandidaten). Kein Referenzlauf: letzte Läufe über 1400 m+ auf Bon souple; erstmals unter 1201 m (Fragezeichen, gemildert: läuft meist vorne mit). Weicher Boden: Lourd/Collant 2025 in Saint-Cloud und Bordeaux, einmal 2. → kann es. Abstammung ohne Hinweis. Trainer in Form (Pro), Box okay. Nicht viel dagegen, aber schwächere Beweislage als Grand Scoop und Mister Chang.
- **R1C4 Rennvergleich**: Bei mehreren Kandidaten im selben Rennen entscheidet der Nutzer **relativ**: Kandidaten nach Beweislage ordnen (Grand Scoop, Mister Chang > Laith > Interactiv) und eine Grenze ziehen; hier nach Platz 2.

| Q45 | Exposed | Eine Skala, keine feste Grenze; wenige Starts und jung = unexposed |
| Q46 | Platziert / im Geld | Platziert: Top 3 bei ≥ 8 Startern, Top 2 bei ≤ 7. „Gut gelaufen“ = im Geld = Top 5 |
| Q47 | Gestörter Lauf | Quellen: Rennkommentar und Rennverlauf (z. B. weit hinten, Rennen von vorne entschieden = gegen den Verlauf) |

## Offen

- Wie groß ist eine Korrektur (Skala für modellfremde Argumente)?
- Wie wird der relative Modell-Rang konkret gewichtet?
- Weitere Rennen der Übungskarte.
