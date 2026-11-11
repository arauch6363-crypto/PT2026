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
| Q53 | Leitfrage | „Reicht es für den Sieg?“ – beste zu heute passende Leistung (ARR im Referenzlauf) gegen das Niveau der Besten im Feld; sicher im Geld, aber selten siegreich ist für die Siegwette schwächer |
| Q54 | Erster Start auf der Bahn | Fragezeichen nur auf Bahnen mit Eigenheiten (z. B. Strasbourg, Fontainebleau); sonst neutral |
| Q55 | Dichte Startfolge | Gegenargument ab etwa 4 Starts in 6 Wochen, stärker je exposed |
| Q56 | Bahnkategorie | Von großen Bahnen (Paris, Deauville) in die Provinz = Pro; umgekehrt = Gegen |
| Q57 | Trainer-Jockey | Gemeinsame Bilanz des Gespanns zählt, mehr als Einzelbilanzen bei genug Starts |
| Q47 | Gestörter Lauf | Quellen: Rennkommentar und Rennverlauf (z. B. weit hinten, Rennen von vorne entschieden = gegen den Verlauf) |

### Karte 11.11.2026 (Ergebnisse dem Nutzer unbekannt)

- **R2C1 Strasbourg Dublin Calling (3)**: FK 3,2, Modell 31,4 % (Rang 1/10), Value +0 % → **keine Wette** („sehr dünner Wert, da muss schon was Überzeugendes dabei sein“). Pro: guter Trainer (A. Botti) – in Strasbourg 2 Jahre ohne Sieg, aber 5 von 7 platziert, stark mit 2-Jährigen in Conditions-Rennen; Referenzlauf Clairefontaine Très souple 3. mit bestem ARR, in einem **aufgewerteten Rennen** (4 Gegner aufgewertet, 2 nicht) vergleichbarer Klasse; Bahn bekannt und gut gelaufen. Gegen: Jockey in Strasbourg wenig erfolgreich. Fazit: wird realistisch gut laufen, aber nicht mehr wert als 3,2; kein Grund, deutlich unter das Modell zu gehen – nur kein Value.
- **R2C1 Matinera (9)**: Debütantin, FK 30, Value +20 % → **keine Wette**. Abstammung recht gut (gute 2-Jährige), aber Trainerin (Mme Y. Vollmer) bringt Zweijährige nicht siegfertig: letzte 20 Starts ohne Sieg, 2 Plätze, mit 2-Jährigen wenig erfolgreich („spricht Bände“). Bestätigt Q50: bei Debütanten entscheiden Abstammung und vor allem der Trainer mit (Zwei-)Jährigen/Debütanten.
- Vorhersage Claude für R2C1 (keine Wette, beide) stimmte.
- **R2C3 (Hcp 3j, 2100 m, Très souple)**: **keine Wette** im Rennen – Vorhersage stimmte im Ergebnis, **nicht in der Reihenfolge**. Nutzer: L'Annonciade am ehesten, dann Roi du Ciel/Marakana.
  - **Roi du Ciel (10)**, +11 %: 21 Starts als 3-Jähriger = „richtig viel, sehr exposed im Vergleich“; erstmals Scheuklappen (Fragezeichen); zuletzt 5/7 in schwächerem Rennen; Sables nur ein ARR „im hinteren Feld“, Provinzbahn; Referenzlauf Strasbourg Très souple 3. – aber ARR dort „rot eingefärbt“ (schwach im heutigen Feld). „Könnte solide laufen, aber reicht das für den Sieg?“
  - **L'Annonciade (7)**, +47 %: weniger exposed (7 Starts); sehr kleiner, aber geschickt operierender Stall; Jockey holt laut A/E mehr aus Pferden heraus (Pro); Abstammung unauffällig; letzter Lauf Chantilly 1800 m in stärker besetztem Rennen nicht weit geschlagen, Kommentar „anständig“; davor 7/12 Conditions; keine Form auf sehr schwerem Boden; Saint-Cloud Très souple 8/10 in stärkerem Rennen, recht weit geschlagen. „Könnte irgendwo reinlaufen, für den Sieg eher nicht.“
  - **Marakana (8)**, +27 %: deutsches Pferd, 7 Starts/2 Plätze; Duo G. Geisler / K. Braye in Strasbourg häufig, kleines Quartier, gewinnt selten; Referenzlauf hier 9/13 in vergleichbarem Handicap – „kein Argument, warum er heute viel besser sein sollte“.
- **R2C4 Teardrop Explodes (4)**: FK 3,7, Modell 27,5 % (Rang 2/8, Nutzer sagte „Rang 1“), Value +2 % → **keine Wette** („zu viele Fragezeichen bei niedrigem Value“) – Vorhersage stimmte im Ergebnis, Begründung teils anders:
  - Pro (Nutzer): Form da – zuletzt vor 9 Tagen platziert unter ähnlichen Bedingungen mit hohem ARR (aber nur Claimer); in Nantes **gegen den Verlauf** vorne platziert (Claude hatte „hinter Onkel Volli“ als Gegenargument gelesen); **Trainer-Jockey-Kombination** (C./H. Boutin, 249 Starts, A/E 1,12) eine der stärksten im Feld (Claude hatte nur Trainer-A/E 0,85 gesehen); kommt von **großen Bahnen in die Provinz** (Vorteil).
  - Gegen/Fragezeichen (Nutzer): **sehr dichte Startfolge** zuletzt („irgendwann könnte die Luft raus sein“); 1,5 kg über letzter Siegmarke; **erster Start auf der Bahn** als Fragezeichen.
- **R2C5 (Hcp 4j+, 1400 m, Très souple, 16 St.)**: **keine Wette, alle drei** – Vorhersage Claude (Wette Verdansk) **falsch, aber knapp**: Reihenfolge stimmte (Nutzer: „wenn dann Verdansk, Fireman klar nicht, Little Lady auch eher nicht“), nur die Grenze lag beim Nutzer vor Platz 1.
  - **Verdansk (1)**, FK 8,5, Rang 1/16, +67 %: Pro: Rang 1 + solider Value, CGD, Referenzform Fontainebleau solide (aber kein Top-ARR), in Strasbourg mehrfach gut gelaufen, auch im Handicap auf weichem Boden, dieses Jahr mehrfach auf sehr weichem Boden; sehr kleiner, aber kompetenter Stall; Jockey kennt das Pferd, hat mit ihm gewonnen, guter Schnitt in Strasbourg; höchstes unbereinigtes Valeur im Feld dämpft die Klassenfrage. Gegen/Fragezeichen: 2,5 kg über der Siegmarke; **Klassenfrage**; **63,5 kg auf schwerem Boden** könnten nachteilig sein.
  - **Fireman (5)**, FK 25, Rang 7/16, +55 %: Gegen: **Scheuklappen ab, seine besten Läufe kamen mit Scheuklappen**; in Strasbourg 2× unplatziert; eher über > 1400 m besser; **auf Rechtskursen schlechter**; letzte Strasbourg-Formen ordentlich, reichen aber normalerweise nicht.
  - **Little Lady (6)**, FK 16, Rang 3/16, +36 %: Pro: Rang 3 + solider Value; Trainerin aktuell schlecht in Form, **aber in Strasbourg sehr erfolgreich** (161 Starts, 23 Siege); laut Referenzform 4.10. vor Fireman. Boden von Abstammung/Vorlieben kein Problem, aber kein großes Plus.
- **R2C3** Lehren: Leitfrage ist **„reicht es für den Sieg?“**, nicht „läuft er solide“; Exposure relativ zum Alter; „nicht weit geschlagen in stärkerem Rennen“ zählt mehr als die Platzierung; ARR des Referenzlaufs gegen das heutige Feld (Farbe auf der Karte); Jockey-A/E als Pro.

## Offen

- Wie groß ist eine Korrektur (Skala für modellfremde Argumente)?
- Wie wird der relative Modell-Rang konkret gewichtet?
- Weitere Rennen der Übungskarte.
