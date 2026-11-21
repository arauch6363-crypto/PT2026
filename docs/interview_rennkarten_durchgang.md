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
| Q36 | Faustregel | Ja, als Orientierung: +20–50 % höchstens ein Fragezeichen und kein gewichtiges Gegenargument; über +50 % ein bis zwei Fragezeichen tragbar. Dazu Fallsammlung im Skill (seit G2: Archiv außerhalb des Skills, verdichtet in `EINSICHTEN.md`); Abweichungen ausdrücklich nennen |

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
| Q58 | Gewicht auf schwerem Boden | Höchstgewicht bzw. ab ca. 62 kg auf Très souple oder schwerer = Gegenargument; bei Verdansk mit Aufgewicht und Klassenfrage der Ausschlag |
| Q59 | Kursrichtung | Bilanz auf Rechts-/Linkskursen ist fester Prüfpunkt; klar schlechter in heutiger Richtung = Gegenargument |
| Q60 | Ausrüstungswechsel | Läufe mit/ohne vergleichen: fällt weg, womit die besten Läufe kamen = Gegenargument; erstmals dazu = Fragezeichen |
| Q61 | Einsatz | Feste Einheiten statt Kelly: Wette 1, kleine Wette ½ (ersetzt Q34 für den Einsatz); Kelly nur als Hinweis |
| Q62 | Kurs | Je Kandidat eine grobe eigene Kursspanne; gewettet, wenn der Festkurs klar darüber liegt; Mindestquote = unterer Rand. Modell-Value nur Filter für Kandidaten |
| Q63 | R2C7 | Algeciras Wette, Cole Chop kleine Wette, Rest keine |
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
- **R2C7 (Hcp 4j+, 2350 m, Très souple, 13 St., Klasse sehr schwach)**: Nutzer: **Algeciras Wette, Cole Chop eventuell kleine Wette**, keine Wette Lady Madeira, Afterglow, Go For It – Vorhersage Claude (keine Wette im Rennen, Lady Madeira knapp vorne) **falsch**.
  - **Afterglow (4)**, FK 6,5, Rang 1, +29 %: Pro: CGD; schwachen letzten Lauf auf deutlich weiterer Distanz übersehen; Vorformen kompetitiv auf heutiger Marke; Distanz/Boden kein Hindernis, auf sehr weich schon gut gelaufen; Trainerin kalt, aber in Strasbourg sehr erfolgreich. Gegen: 7-jährig, viel gelaufen, sehr exposed; Box −0,11 auffällig. Urteil: „der Wert, den der Festkurs bietet, ist zu niedrig“, obwohl Argumentation nachvollziehbar.
  - **Lady Madeira (12)**, FK 16, Rang 2, +76 %: weniger exposed, hoher Value, letzter Start solide „le nez au vent“ (ohne Deckung, kein optimaler Verlauf). **Großes Fragezeichen Distanz**: auf weiteren Wegen bisher immer mit Problemen, letzte Formen alle kürzer → nicht gut genug.
  - **Go For It (9)**, FK 16, Rang 7, +14 %: alle Formen „relativ weit weg von dem, was benötigt wird“ (8/15 auf Très souple 6 L, 5/12 6 L), kommt aus schwächeren Rennen; letzter Sieg 6 kg tiefer auf kleiner Provinzbahn (Wissembourg); sehr kleiner Stall ohne Sieg in 2 Jahren (Gegen), obwohl Trainer/Jockey in Strasbourg erfolgreich → „fehlt die Klasse“.
  - **Cole Chop (13)**, FK 25, Rang 10, +12 % → **eventuell kleine Wette**: Vorlieben weich und Distanz sehr gut (Slow 21/3/6, A/E 1,26; 2201–2400 m 13/2/3); CGD; Trainer hat in Strasbourg mehrfach gewonnen; Jockey unerfahren, aber talentiert. Letzter Lauf Lignières 8., 8 L, „unauffällig“, Vorformen sehr weit geschlagen („No-Shows“) – aber 8. Platz als **erster Ansatz** nach vielen No-Shows; Strasbourg im Frühjahr 7., 5 L, mit 4 kg höherer Marke unter identischen Bedingungen. „Da fehlt einiges, vielleicht für eine kleine Wette interessant.“
  - **Algeciras (5)**, FK 13, Rang 5, Value **+3 %** → **Wette**: CGD; Form da (zuletzt 5/8 Toulouse und 6. Strasbourg auf schnellem Boden); Vorlieben: Distanz eher negativ, aber schon gewonnen; **auf sehr weichem Boden gewonnen** (Very slow 6/1/2, A/E 2,84 – in den letzten Formzeilen nicht sichtbar, Claude hatte „nie auf Très souple“ gemeldet!); Marke unter letzter Platzmarke, nur 0,5 kg über Marke des letzten Handicap-Siegs; Trainer J. Parize und Jockey D. Santiago aktuell nicht in Form, aber solide und in Strasbourg erfolgreich. „Klarere Form“ als Cole Chop. „13:1 keine Riesen-Value.“
  - Lehren: (1) Boden-/Distanz-/Bahnbelege aus den **Vorlieben (gesamte Bilanz)**, nicht nur aus den letzten Formzeilen; (2) der Nutzer bewertet den **Kurs gegen die eigene Einschätzung** (Afterglow 6,5 zu kurz trotz +29 % Modell-Value; Algeciras 13 wettbar trotz +3 %); (3) „kleine Wette“ als Einsatzstufe; (4) „erster Ansatz nach No-Shows“ als Pro; (5) Klasse der bisherigen Rennen/Bahnen und Stallgröße/-erfolg.
- **R2C3** Lehren: Leitfrage ist **„reicht es für den Sieg?“**, nicht „läuft er solide“; Exposure relativ zum Alter; „nicht weit geschlagen in stärkerem Rennen“ zählt mehr als die Platzierung; ARR des Referenzlaufs gegen das heutige Feld (Farbe auf der Karte); Jockey-A/E als Pro.

## Probelauf v1 (Skill allein, ohne Blick auf Ergebnisse)

- **10.11. Fontainebleau R1C6–R1C9 und Amiens R4C1–R4C7:** 27 Kandidaten, 3 Wetten zu je 1 Einheit. Ergebnisse laut Nutzer: **Soif de Vivre (R1C8, FK 9) gewonnen, Vapoa (R4C3, FK 8,5) gewonnen, Bluff (R4C1, FK 2,8) Zweiter.** Bei 1 Einheit je Wette ergibt das zum Festkurs +14,5 Einheiten aus 3 Wetten (+8, +7,5, −1); Stichprobe viel zu klein für Schlüsse. Eine Durchsicht der übrigen Urteile durch den Nutzer entfällt, weil er die Ergebnisse kennt.
- **11.11. Toulouse R1C1–R1C9:** 29 Kandidaten, 6 Wetten (Majestic Sky, Blue Blossom Cen, Xilofono, Littoral Nord je 1; Arkansas, Knuckle je ½). Ergebnisse offen.

## Durchsicht der automatischen Durchgänge (ab 17.11.2026)

Rahmen (Interview 16.11.): Quelle sind die automatischen Durchgänge ab 15.11.; Rennen mit Claude-Tipp plus knappe
Ablehnungen (Value über +30 % oder Modell-Rang 1–2); nur gelaufene Rennen, Ergebnisse ausgeblendet. Fälle im Archiv
`docs/faelle_rennkarten_durchgang.md` (Art: Übereinstimmung / Claude lernt / Claudes Sicht behalten), Regel in `SKILL.md` erst bei zwei
gleichgerichteten Fällen oder ausdrücklicher Ansage. Der Nutzer weist darauf hin, dass er nicht immer ganz konsistent
urteilt – Widersprüche werden angesprochen, nicht mechanisch übernommen.

### 16.11. Marseille Pont de Vivaux R4C8 – Lovely Warrior (Claude: Wette, FK 3,5, Spanne 2,8–3,2)

Nutzer: zunächst „Wette, passt“, dann: „Scheuklappen sehe ich auch kritisch. Warum nimmt man jetzt die Scheuklappen
herunter, nachdem man sie immer erfolgreich eingesetzt hat? Und was mir sonst noch nicht gefällt, ist, dass man […] zu
so kurzer Quote wettet, die aus Verkaufsrennen kommt, jetzt im Handicap. Da finde ich die Quote ein bisschen zu kurz.
Für mich dann doch eher keine Wette.“ Auf Nachfrage: „Stute“ war ein Versprecher (Hengst, „weniger großer Nachteil“);
Claimer → Handicap nur am Rande, „der Hauptpunkt bleibt […] die weggelassenen Scheuklappen“. → Keine Wette, Art
„Claude lernt“.

### 16.11. Marseille R4C4 – Come Alone (Claude: klein), Morus, Bosquet (Claude: nein)

Nutzer: „Bei Come Alone stimme ich dir zu. Mir gefällt auch, dass Trainer/Jockey stark sind, vor allem aber auch, dass
das Pferd wenig exposed ist, also wenig Starts, jung, in einem relativ exposed Feld. Von der Abstammung her kann man
bei dem Pferd sogar noch ein bisschen was erwarten. Bahnform: ist hier schon gut gelaufen. Letzter Lauf auf jeden Fall
verziehen, weil auf schwerem Boden. Und wenn man sich die Vorform anschaut, hat er das höchste ARR im Feld. Negativ
stört die lange Pause und dass er nach der langen Pause noch keine Form gezeigt hat.“
Morus: „Im Wesentlichen einverstanden. Erster Start auf der Bahn, keine Referenz. Die Referenzformen von anderen
Sandbahnen reichen nicht, stammen aus relativ schwachen Rennen, und er war dort auch respektabel geschlagen. Das
Weglassen der Scheuklappen wiegt hier nicht schwer, da die letzten Formen mit Scheuklappen auch nicht gut waren –
dass man etwas Neues probiert, ist in dem Fall nicht negativ zu werten. Der Trainer ist auch schwach.“
Bosquet: „Stimme in allem überein.“ → Alle drei Übereinstimmung; Scheuklappen-Fall präzisiert Lovely Warrior.

### 16.11. Marseille R4C3 – Cervaro (Claude: klein), Blanc Bleu, Silgreypit (Claude: nein)

Nutzer: „Stimme im Wesentlichen mit der Analyse überein.“ → Alle drei Übereinstimmung.

### 16.11. Marseille R4C2 – Magenta Melody (Claude: klein), Giovanni Giorgio, Naturaliste (Claude: nein)

Nutzer: „Passt!“ – auch auf die Nachfrage, ob eine leicht unpassende Abstammung (Belag −9) bei erstmals PSF nur
Fragezeichen ist und nicht wie bei Littoral Nord (−17) allein kippt. → Alle drei Übereinstimmung.

### 16.11. Marseille R4C1 – Senorito (Claude: nein), Rocky Run (Claude: nein)

Nutzer zu Senorito: „Würde ich vielleicht nicht zustimmen. Was mir hier auffällt, ist, dass das Pferd erst seit kurzem
bei seinem neuen Trainer ist und für den extrem erfolgreich war. Also der hat hier eine Verbesserung wohl gefunden.
Sonst hast du es gut analysiert. Und deswegen würde ich auch bei einem jungen Pferd, das sich jetzt offensichtlich
gerade steigert, die schwachen ARRs nicht so streng bewerten, weil die können ja nur schwächer sein, wenn er gerade im
Aufsteigen begriffen ist.“ Auf Nachfrage: „Kleine Wette, fair eher 3,5–4, erst Einzelfall.“ (Daten: unter Perret
3 L/2 S/2 P, A/E 1,72.) → Claude lernt (Einzelfall). Rocky Run: keine Einwände (Übereinstimmung).

### 16.11. Mans R3C8 – Crew Dragon (Claude: klein), Tulpar (Claude: nein)

Nutzer: „Crew Dragon ist in dem Fall für mich klar keine Wette. Es ist auffällig, wie schlecht die Form von Cédric
Boutin, dem Trainer, aktuell ist. Außerdem ist der Aufstieg aus einem Verkaufsrennen oder aus mehreren Verkaufsrennen in
ein Handicap auch als Gegenargument zu sehen in den meisten Fällen. Dazu kommt, dass man auf sehr weicher Bahn bisher
einen deutlich schlechteren Schnitt hat. Was du richtig gesehen hast: dass die Box positiv zu bewerten ist.“
Zum Regelvorschlag: „Doch, ein höherer Klassenindex kann den Wechsel von Verkaufs- in Handicap-Rennen ausgleichen. Bei
Crew Dragon ist dieser Klassenindex allerdings nur marginal größer, deswegen würde ich ihn da nicht so hoch bewerten.“
→ Claude lernt; mit Lovely Warrior zweiter Fall → Regel „Aufstieg aus Claimern ins Handicap“ in `SKILL.md`.
Tulpar: „passt für mich“ (Übereinstimmung).

### 16.11. Mans R3C7 – The Cat's (Claude: klein), Piano Bar (Claude: nein)

Nutzer: „Bei Piano Bar stimme ich dir zu, bei The Cat's nicht ganz, weil mir hier schon auffällt, dass die ARRs selbst
in Referenzform anständig sind, aber nicht zu den vorderen des Feldes gehören, und er als relativ exposed Pferd immer
noch über seiner letzten Siegmarke steht. Bei einem Trainer oder einem Jockey, die beide eher zu den Schwächeren zählen
und zudem keine aktuelle Form haben.“ Auf Nachfrage: „Keine Wette für die Katze, und die Regel passt.“
→ Claude lernt; mit Crew Dragon zweiter Fall → Regel „keine kleine Wette als Ausweg“ in `SKILL.md`.

### 18.11. Pau R2C3 – Boomslang (Claude: nein, FK 2,2, Spanne 2,5–3)

Rahmen geändert: Der Nutzer wollte statt der übrigen Rennen vom 16./17.11. die **heutigen Pau-Rennen** durchgehen, deren
Ergebnisse er (bis auf R2C1) noch nicht kennt; R2C2 ist AQPS.
Nutzer: „Zweijähriger Hengst im sieglosen Rennen, ein Start, eine Platzierung […]. Letzte Form 30 Tage her, von der
Pause her gut. Bestes ARR im Feld mit 37 […]. Bei sehr langsamem Tempo aus dem Vordertreffen gelaufen, mit dem Verlauf
vorne gewesen – da muss man eventuell ein bisschen vorsichtig sein. Ansonsten war das bestimmt eine gute Leistung.
Aufgewertet kann man noch nicht sagen. […] Vater Space Blues spricht für diesen Belag, Muttervater Sea The Stars
dagegen; der Vater ist immer ein bisschen wichtiger, das sollte demnach in Ordnung gehen. Trainer absolut top, Jockey
okay, ein bisschen unter dem Durchschnitt; die Kombination verbessert sich nicht gegenseitig. Der Jockey kennt das
Pferd. […] Insgesamt für sich ist das wahrscheinlich ein gutes Pferd. Aber ich kann die Chancen schlecht beurteilen,
z. B. im Vergleich zum zweiten Favoriten El Lagar.“ (Daten: Space Blues im Blatt „Belag neutral“, Rohwerte aber PSF
117 gegen Gras 106 – Lesart des Nutzers gedeckt.)
Vorschlag des Nutzers: „Mir ist die Bewertung schwer gefallen, wenn ich keine Referenz hatte, gegen das zweitbeste oder
nächstbeste Pferd bei den Festkursen zu vergleichen, um eine Elle zu haben, gegen was man besser sein muss. Wir sollten
im Skill ergänzen, dass wir immer auch den Favoriten mit analysieren, auch wenn der einen Value unter null hat […], aber
niemals wetten, nur als Vergleichsmaßstab. Ist unser Value-Pferd selbst der Favorit, nehmen wir den nächstbesten nach
Festkurs.“ Wortlaut bestätigt → Regel **Maßstab** in `SKILL.md`, Blatt und Durchgangsformat ergänzt.
Urteil: „Boomslang können wir wahrscheinlich nicht als Wette nehmen, weil ich den Value für zu klein finde und er
letztes Mal vom Verlauf profitiert haben könnte.“ → Übereinstimmung.

### 18.11. Grilling: Verdichtung statt Fallliste

Ziel des Nutzers: sich mehr auf NAP und bessere Auswahl verlassen; der Skill soll seine Analyse imitieren. Die Fälle
werden weiter gesammelt, aber verdichtet, damit der ausführende Agent nur Regeln, Vorgehen und Einsichten liest.

| # | Frage | Entscheidung |
|---|---|---|
| G1 | Ziel | Ein NAP von Claude = was der Nutzer selbst spielen würde (Übereinstimmung); weniger, verlässlichere NAPs folgen daraus |
| G2 | Aufbau | Fälle als Archiv `docs/faelle_rennkarten_durchgang.md` (Agent liest es nicht); Regeln in `SKILL.md`; neue `EINSICHTEN.md` im Skill |
| G3 | Wann verdichten | Am Ende jeder Interview-Sitzung als Block; Vorschlag, Zustimmung, PR |
| G4 | Einzelfälle | Unter „Vorläufig (ein Fall)“ in `EINSICHTEN.md`; Agent nennt es, wenn er sich darauf stützt |
| G5 | Rennauswahl | Wie bisher (Claude-Tipps plus knappe Ablehnungen) |
| G6 | Ergebnisse | Bleiben ausgeblendet |
| G7 | Pferdenamen | Nur in `EINSICHTEN.md` als Beispiel; `SKILL.md` ohne Namen |
| G8 | Gliederung | `EINSICHTEN.md` nach den Schritten der Prüfliste |
| G9 | Beleglage | Kein Zähler; Gewicht aus der Art, wie ernst der Nutzer ein Argument nimmt |
| G10 | Ermessen | Abweichende Urteile, die der Nutzer nicht abgelehnt hat, bleiben („Galopprennen sind voll von widersprüchlichen Signalen“) |
| G11 | Länge | Keine feste Grenze; Kontext kurz halten, alle wesentlichen Ideen behalten |
| G12 | Erste Verdichtung | Sofort nach dem Interview, als PR |
| G13 | Gewichtsskala | ausschlaggebend / gewichtig / leicht |
| G14 | Typische Fehler | Eigener Abschnitt am Anfang von `EINSICHTEN.md` |

### Stand der Durchsicht (18.11.)

Erledigt: 16.11. Marseille R4C1–R4C8, Mans R3C7–R3C8; 18.11. Pau R2C3. Offen: 18.11. Pau R2C4–R2C8 (laufend);
16.11. Mans R3C6 (Zartop, gezeigt, ohne Antwort), R3C1–R3C3, R3C5; 17.11. (R2C1 Angers gezeigt, ohne Antwort); 15.11.

### Stand der Durchsicht (17.11.)

Erledigt: 16.11. Marseille R4C1–R4C8, Mans R3C7–R3C8. Offen: Mans R3C6 (gezeigt, noch ohne Antwort), R3C1–R3C3,
R3C5; R3C4 fehlt in beiden Durchgängen des 16.11. (Ursache klären); danach 15.11. und ab 17.11.

## Stand

Skill v1 geschrieben: `.claude/skills/rennkarten-durchgang-neu/` (SKILL.md, DATEN.md, FAELLE.md, scripts/blatt.py), parallel zum alten Skill.

## Offen

- Q37 (Mindestquote unter +20 %) durch Q62 ersetzt; Q49–Q52 (höchstens zwei Wetten je Rennen, Debütanten, Trainer/Jockey, aufgewertet) vorläufig wie vorgeschlagen übernommen, nicht ausdrücklich bestätigt.
- Rückmeldung zu Claudes Vorhersagen in 10.11. R1C5 fehlt.
- `tipp_auswertung.py` auf den neuen Protokoll-Block (`wetten`) umstellen.
- Erprobung v1 an weiteren Rennen; danach alten Skill ersetzen und README anpassen.
- Durchsicht (Stand 18.11.): erledigt 16.11. Marseille R4C1–R4C8, Mans
  R3C7–R3C8; 18.11. Pau R2C3. Offen: 18.11. Pau R2C4–R2C8 (Durchgang 11:40); 16.11. Mans R3C6 Zartop (gezeigt,
  Antwort fehlt), R3C5, R3C3, R3C2, R3C1 (Durchgang 11:47); 17.11. ab Angers R2C1 (Allez Papa/Ipanema Rose gezeigt,
  Antwort fehlt); 15.11. Paumy und Give Me A Shivers (16.11. R3C6) beim Abschluss von R3C6 einordnen.
