# Merkmale des Power- und Value-Modells (Version 19)

Übersicht aller Eingangsgrößen von `power_modell.merkmale` mit kurzer Definition und Berechnung. Die Angaben sind
bewusst knapp gehalten; maßgeblich ist der Code.

## Grundregeln

- **Kein Blick in die Zukunft:** Jedes Merkmal eines Starts nutzt nur Läufe und Ergebnisse *vor* diesem Renntag.
  Verbindungs-, Abstammungs- und Box-Werte werden Tag für Tag fortgeschrieben.
- **Pos+:** Platzanteil = (Starter − Platz) ÷ (Starter − 1); 1 = Sieger, 0 = Letzter. Nicht im Ziel = 0.
- **Lernziel des Power-Modells:** Pos+ des heutigen Laufs (Regression).
- **Score (100 = Schnitt):** Mittel aus A/E Platz × 100, Ø Pos+ ÷ Ø aller × 100 und Ø log(1 + Preisgeld) ÷ Ø aller
  × 100; zur 100 hin geschrumpft (Verbindungen wie mit 10, Abstammung wie mit 20 Läufen bei 100).
- **Gewichtsbereinigung:** ARR, TR, RTR und Ratings werden auf das heutige Gewicht umgerechnet
  (Wert − Gewicht + 55 kg; TR in Pfund je kg).
- **Gewicht = getragenes Gewicht** (ab Version 19): PMU `poidsConditionMonte` (mit Erlaubnis des Reiters), sonst
  `handicapPoids`. Das gilt für die Historie (über die p_-Spalten aus pmu_basis), die heutige Karte und die Berechnung
  von ARR/RTR. Vorher stand in `weight_kg` das zugeteilte Gewicht.
- **Externe Läufe** (PMH, Ausland, Übersee aus den PMU-Detail-Leistungen) zählen für Form, Tage und Läufe; nicht für
  Verbindungen, A/E und Lernziele. Externe Läufe auf PMU-Bahnen gelten als normale PMU-Läufe.
- **Feld-relativ:** Für die Merkmale der Liste `RELATIV` gibt es zusätzlich `…_rk` (Rang im heutigen Feld, 0 = schlechtester,
  1 = bester) und `…_dz` (Abstand zum Ø des heutigen Feldes). Diese Varianten sind meist die
  wichtigsten Merkmale.
- **Leere Werte** bleiben leer (z. B. Debütanten ohne Form); LightGBM behandelt sie selbst.

## Rennen und Startplatz

- `n_runners` – Starterzahl.
- `distance_m` – Distanz in m.
- `race_prize` – log(1 + Preisgeld des Rennens).
- `feld_val` – Ø Rating (Valeur) des heutigen Feldes.
- `racetype` – Renntyp (Blacktype, Claimer, Conditions, Handicap), kategorisch.
- `going` – Bodenklasse (VERY FAST … VERY SLOW, PSF), kategorisch.
- `dist_group` – Distanzgruppe (200-m-Stufen), kategorisch.
- `age_group` – Altersgruppe des Rennens (2yo, 3yo, 3yo+, 4yo+), kategorisch.
- `season_doy` – Tag im Jahr (Reifung über die Saison).
- `draw` – Startbox. `draw_rel` – Box ÷ Starterzahl (0 innen … 1 außen).
- `box_mean` / `box_runs` – Ø Pos+ und Zahl früherer Starts aus dieser Box auf derselben Bahnkonfiguration
  (Kurs + Distanz + Bahnart).
- `box_dev` – dieselbe Box, zur Feldmitte hin geschrumpft: (Σ Pos+ + 30 × 0,5) ÷ (n + 30) − 0,5.
- `box_stil_dev` / `box_stil_runs` – Box × Laufstil: Ø Pos+ je Bahnkonfiguration, Boxdrittel (innen/Mitte/außen) und
  Stil (vorne ≤ 0,25 / Mitte / hinten ≥ 0,6 frühe Position), geschrumpft wie `box_dev`. Im Stand zählt der
  tatsächliche frühe Platz des damaligen Laufs, heute der erwartete Stil (`early`). Nur mit Tracking.

## Pferd: Stammdaten, Gewicht, Rating

- `age`, `sex` – Alter; Geschlecht (H, F, M), kategorisch.
- `weight` – heutiges (getragenes) Gewicht in kg.
- `gew_erlaubnis` – Gewichtserlaubnis: zugeteiltes minus getragenes Gewicht (Nachwuchsreiter, Reiterinnen; 0 = keine;
  leer, wenn das zugeteilte Gewicht unbekannt ist).
- `rating` – Valeur (offizielles Rating); `rating_adj` – Rating gewichtsbereinigt.
- `chg_rating` – Rating heute minus beim letzten Lauf.
- `hcp_sieg_diff` / `hcp_platz_diff` – Rating heute minus Rating beim letzten Sieg bzw. letzten Platz im Handicap
  (< 0: heute leichter eingestuft als zuletzt erfolgreich).
- `hcp_spielraum` – Handicap-Spielraum: Rating heute minus bester ARR der letzten 365 Tage (beide auf der
  Valeur-Skala, ungewichtet; < 0: lief schon besser, als das Rating heute verlangt).
- `blink` – Scheuklappen heute (0 ohne, 1 klassisch, 2 australisch). `blink_first` – heute erstmals mit.
  `blink_change` – anders als beim letzten Lauf.
- `erst_wallach` – heute erstmals als Wallach (beim letzten Lauf Hengst).
- `feld_aelter` / `feld_erfahrener` – Anteil der heutigen Gegner, die älter sind bzw. mehr Starts haben.
- `feld_anteil_maennlich` – Anteil der Gegner, die Hengst oder Wallach sind.
- `stute_gegen_hengste` – 1 = Stute in einem Rennen mit mindestens einem Hengst/Wallach, sonst 0.

## Erfahrung, Pausen, Frische

- `runs` – Zahl früherer Starts; `runs365` – davon in den letzten 365 Tagen.
- `days` – Tage seit dem letzten Lauf.
- `starts_nach_pause60` / `starts_nach_pause180` – Starts seit der letzten Pause von ≥ 60 bzw. ≥ 180 Tagen
  (1 = heute erster Start danach, bis 10; neue Pause beginnt neu; 0 = keine solche Pause; leer bei Debüt).
- `letzte_pause_tage` – Länge der ≥ 60-Tage-Pause, mit der die heutige Serie begann.

## Form der letzten Läufe

Verdichtet über die letzten 5 Läufe (`form5_…`):
- `form5_pos` / `form5_best` / `form5_std` – Ø, Bestwert und Streuung der Pos+.
- `form5_top` – Anteil Spitzenläufe (Pos+ ≥ 0,75).
- `form5_lb` – Ø Längen hinter dem Sieger.
- `form5_arr` – Ø ARR (gewichtsbereinigt).
- `form5_ue` – Ø „Pos über Erwartung“: Pos+ minus die aus dem damaligen Quotenrang erwartete Pos+.
- `form5_klasse` / `form5_preis` – Ø Feld-Rating bzw. Preisgeld dieser Läufe minus heute (> 0: zuletzt in stärkeren
  Rennen).
- `form5_extern` – Anteil externer Läufe (PMH/Ausland/Übersee).

Zeitgewichtet über bis zu 10 Läufe, Gewicht 0,5^(Tage ÷ 90) (`formz_…`):
- `formz_pos` / `formz_arr` / `formz_ue` – gewichtete Pos+, ARR, Pos über Erwartung (Pos und Ue zum Ausgangswert
  geschrumpft wie mit einem heutigen Lauf).
- `formz_n` – Summe der Gewichte (wie viele „frische“ Läufe die Form trägt).
- `formz_klasse` / `formz_preis` – wie oben, zeitgewichtet.
- `formz_pos_pmu` – `formz_pos` nur aus PMU-Läufen (ohne PMH/Ausland).
- `formz_pos_vb` – `formz_pos` um den Rennverlauf bereinigt: Läufe gegen den Verlauf bekommen einen Zuschlag, mit dem
  Verlauf einen Abzug (Ø Pos+ aller minus Ø Pos+ der Klasse, laufend aus früheren Tagen).

Trend und Klasse:
- `form_steig_pos` / `_arr` / `_lb` / `_ue` – Steigung je Lauf über die letzten 6 (> 0: wird besser bzw. mehr Längen).
- `form_best3_diff` – beste Pos+ der letzten 3 minus beste der Läufe 4–8.
- `form_pos_hoeher` – Ø Pos+ in Läufen mit mindestens gleichem Preisgeld wie heute.
- `chg_weight` / `chg_dist` / `chg_class` / `chg_prize` – Gewicht, Distanz, Feld-Rating, Preisgeld heute minus letzter
  Lauf.

## Einzelne letzte Läufe (`f1_` = letzter, `f2_` = vorletzter, `f3_` = drittletzter)

- `f_pos` – Pos+. `f_lb` – Längen hinter dem Sieger.
- `f_val` / `f_epr` – Klasse dieses Rennens (Ø Rating des Feldes; €/Lauf-Index der Gegner).
- `f_arr` / `f_tr` – ARR bzw. TR in diesem Lauf, auf das heutige Gewicht umgerechnet.
- `f_fi` / `f_g800` / `f_weg` – Tracking: Finish-Index, Positionsgewinn ab 800 m, Wegfaktor (gelaufene Strecke).
- `f_odds` / `f_orank` / `f_pm` – Endquote, Quotenrang relativ (0 Favorit … 1 Außenseiter), Marktchance damals.
- `f_verlauf` – Rennverlauf: +1 gegen, −1 mit, 0 neutral (zeitlich sauber berechnet).
- `f_tage` – Tage zwischen diesem Lauf und heute.
- `f_same_going` / `f_same_dist` – gleiche Bodengruppe bzw. Distanzgruppe wie heute.
- `f_gegner` – Gegner-Score: wie die Gegner aus diesem Rennen danach gegen ihren Quotenrang gelaufen sind (nur Starts
  vor heute).
- `f_duell` – Anteil der heutigen Gegner aus diesem Rennen, die das Pferd damals geschlagen hat.
- `f_cgd_sieg` / `_platz` / `_neu` – Kurs/Boden/Distanz-Bilanz vor diesem Lauf.
- `f_abst_pass` – Abstammungs-Passung zu diesem Rennen.
- `f_extern` – externer Lauf (PMH/Ausland/Übersee). `f1_ausland` – letzter Lauf im Ausland/Übersee.
- `f_stride_rel` – Tracking: Schrittlänge in der Rennmitte (Abschnitte bis 400 m vor dem Ziel, ohne Startabschnitt)
  minus Ø des damaligen Feldes.
- `f_stride_change` – Tracking: Schrittlänge der letzten 400 m gegen die Rennmitte in % (< 0: Schritt wird im Finish
  kürzer – Ermüdung).
- `f1_vmax_rel` – Tracking: Höchsttempo im letzten Lauf minus Ø des damaligen Feldes (km/h).
- `f_typ` – Renntyp dieses Laufs, kategorisch.

## Leistungskennzahlen (Kacheln)

- `arr` / `tr` – Ø ARR (Leistungsrating aus Zeit und Längen) bzw. TR (Zeit-Rating) der letzten 5 gültigen Läufe,
  gewichtet nach Ähnlichkeit von Distanz und Boden zu heute; gewichtsbereinigt.
- `rtr` – RTR (Rating nach dem Rennen) des letzten Laufs mit Wert, gewichtsbereinigt.
- `arr_best365` – bester ARR der letzten 365 Tage; `arr_best_dist` – bester ARR auf heutiger Distanzgruppe;
  `arr_best_abst` – letzter ARR minus Bestwert (< 0: zuletzt unter Bestform).
- `arr_neue_best` – ARR des letzten Laufs minus bester ARR aller Läufe davor (> 0: zuletzt neue Bestleistung –
  prüft die Rückfall-Hypothese nach einer Spitzenleistung).
- `dl600` / `db200` – Tracking: Δ letzte 600 m bzw. erste 200 m gegen das Feld (Ø, gewichtet).
- `early` – Ø frühe Position (Laufstil; klein = vorne).
- `epr365` – €/Lauf der letzten 365 Tage (Index).
- `lgo_pos` / `lgo_arr` – Pos+ und ARR im letzten Lauf auf heutiger Bodengruppe.
- `ldi_pos` / `ldi_arr` – dasselbe für die heutige Distanzgruppe.

## Vorlieben und Bilanz

- `won_course` / `won_dist` / `won_going` – schon auf Kurs / Distanzgruppe / Boden gewonnen.
- `placed_course` / `placed_dist` / `placed_going` – dort schon platziert.
- `best_dist` / `best_going` – heutige Distanz- bzw. Bodengruppe ist die beste des Pferdes (Score, ab 2 Läufen).
- `cgd_sieg` / `cgd_platz` / `cgd_neu` – CGD-Bilanz vor heute (Siege bzw. Plätze auf Kurs/Boden/Distanz; neu = noch nie).
- `erst_kurs` / `erst_boden` / `erst_dist` / `erst_belag` – heute erstmals auf diesem Kurs / Boden / Distanz /
  Belag (Gras ↔ PSF).
- `going_pref` – Boden-Vorliebe über den Penetrometer: heutiger Wert minus Ø Penetrometer der drei besten Läufe
  (nach Pos+, ab 3 Läufen mit Wert; > 0: heute weicher als in den besten Läufen). Ergänzt die Bodengruppen.

## Tempo im heutigen Rennen

- `pace_front` – Zahl der Starter mit Laufstil „vorne“.
- `pace_early_mean` – Ø Laufstil des Feldes.
- `early_rel` – eigener Laufstil minus Feldschnitt.

## Rennverlauf (Version 16)

- `verlauf5_gegen` / `verlauf5_mit` – Anteil der letzten 5 Läufe gegen bzw. mit dem Verlauf.
- `form5_pos_gegen` / `form5_pos_mit` – Ø Pos+ nur aus diesen Läufen.
- (dazu `formz_pos_vb` und `f_verlauf`, siehe oben)

## Verbindungen (Scores, 100 = Schnitt; je mit `_runs` = Zahl der Läufe)

- `trainer_score` / `jockey_score` / `owner_score` / `breeder_score` – Bilanz der letzten 365 Tage.
- `trainer_30_score` / `jockey_30_score` – nur letzte 30 Tage (Stallform).
- `trainer_form` / `jockey_form` – 30-Tage- minus 365-Tage-Score.
- `trainer_typ_score` – Trainer im heutigen Renntyp; `trainer_kurs_score` – Trainer auf diesem Kurs;
  `jockey_trainer_score` – diese Jockey-Trainer-Kombination.
- `trainer_debuet_score` / `trainer_pause_score` – Trainer mit Debütanten bzw. nach Pause.
- `jockey_ritte_meeting` – Ritte des Jockeys heute auf dieser Bahn (PMU-Rennen, dieses eingeschlossen).
- `trainer_starter_meeting` – Starter des Trainers heute auf dieser Bahn.
- `trainer_reise_km` – Luftlinie von der Heimatbahn des Trainers (Bahn mit den meisten Startern in den 365 Tagen
  davor) zur heutigen Bahn; Lage der Bahnen aus `bahn_orte.py`, unbekannte Bahn → leer.
- `stall_im_rennen` – Zahl der Stallgefährten (gleicher Trainer) im Rennen.
- `stall_erster` – 1, wenn das Pferd unter den Startern seines Stalls den besten Jockey (Score) hat; leer ohne
  Stallgefährten.
- `kennt_jockey` – Jockey hat das Pferd schon geritten. `chg_jockey` – anderer Jockey als zuletzt;
  `chg_jockey_score` – Score heutiger minus voriger Jockey.

## Trainer- und Besitzerwechsel (Version 17)

- `chg_trainer` – anderer Trainer als beim letzten Lauf. `trainerwechsel5` – mehr als ein Trainer in den letzten 5
  Starts.
- `laeufe_seit_trainerwechsel` – 0 = heute erster Start beim neuen Trainer, bis 10; leer ohne Wechsel.
- `tage_seit_trainerwechsel` – Tage seit dem letzten Lauf beim vorigen Trainer (bis 730).
- `trainer_sprung` – Score heutiger minus voriger Trainer (Stand vor dem Renntag).
- `form_neuer_trainer` / `form_neuer_trainer_n` – Ø Pos+ und Zahl der Läufe beim heutigen Trainer seit dem Wechsel.
- `chg_owner` – anderer Besitzer als zuletzt; `laeufe_seit_besitzerwechsel`, `tage_seit_besitzerwechsel`,
  `besitzer_sprung` – wie beim Trainer.
- `besitzer_ohne_trainer` – Besitzer gewechselt, Trainer gleich (oft Verkauf im Stall).

## Abstammung

- `sire_score` / `dam_sire_score` – Score der Nachkommen von Vater bzw. Muttervater; dazu `_epr` (€/Lauf),
  `_val3` (Ø bestes Rating der Dreijährigen), `_runs`.
- `sire_best_dist` / `sire_best_going` (ebenso Muttervater) – heutige Distanz- bzw. Bodengruppe ist die beste der
  Linie (ab 30 Läufen).
- `dam_score` / `dam_epr` / `dam_val3` / `dam_runs` – Bilanz der Geschwister (Nachkommen derselben Mutter, ohne das
  Pferd selbst).
- `abst_pass` – Abstammungs-Passung gesamt: je Skala (Distanz, Boden, Belag, Reife, Wechsel) P = (Perzentil der Linie
  − 50) × (Lage des heutigen Rennens − 50) ÷ 25, −100 … +100, aus Monatsständen; > 0 = die Linien neigen in die
  Richtung, in der das Rennen liegt.
- `abst_pass_sire` / `abst_pass_dam_sire` – nur Vater bzw. Muttervater.
- `abst_pass_dist` / `_boden` / `_belag` / `_reife` / `_wechsel` – die einzelnen Skalen (Boden auf PSF leer).
- `sire_going_pref` / `dam_sire_going_pref` – heutiger Penetrometer minus Ø Penetrometer der Spitzenläufe (Pos+ ≥ 0,75)
  der Nachkommen, zum Ø aller Spitzenläufe geschrumpft (wie mit 20 Läufen), ab 10 Spitzenläufen.

## Duelle

- `duel_score` – Bilanz aus direkten und indirekten Duellen mit den heutigen Gegnern (wie die Duell-Kachel).
- `duel_rank_rel` – Rang im Duell-Ranking des Feldes ÷ Feldgröße. `duel_weight` – wie viele Duelle dahinterstehen.

## Nur im Value-Modell

- Alle Merkmale oben (feld-relativ); keine Marktquote als Merkmal (die Morgenquote ist ausgebaut).
- Ziel „kombi“: Sieg + Platz gegen die Erwartung aus der Endquote (Poisson); das Modell lernt nur die Abweichung vom
  Markt.

## Tracking-Wert (Teilmodell)

- `trk_wert` – vorhergesagter Platzanteil aus einem eigenen LightGBM-Modell, das nur die Tracking-Merkmale (`dl600`,
  `db200`, `early`, `tr`, `f_tr`/`f_fi`/`f_g800`/`f_weg`/`f_stride_*`, `f1_vmax_rel`, Tempo und Box × Stil des Feldes)
  und den Rennrahmen (Starter, Distanz, Boden, Renntyp, Altersgruppe) kennt und nur auf Startern mit
  Tracking-Vorgeschichte lernt. `trk_wert_rk` / `trk_wert_dz` – Rang und Abstand im Feld.
- Ohne Blick in die Zukunft: je Quartal ein Teilmodell aus allen früheren Quartalen (ab 5.000 Startern mit Tracking);
  frühere Quartale und Starter ohne Tracking bleiben leer. Für die Karte wird das Teilmodell aus allen Zeilen
  gespeichert (`modelle/power_modell_tracking.txt`, für das Value-Modell `power_wert_tracking.txt`).
- Idee: Das Hauptmodell muss Tracking-Signale nicht aus vielen dünn besetzten Spalten zusammensuchen, sondern bekommt
  eine verdichtete Einschätzung; alle übrigen Merkmale (und Wechselwirkungen) bleiben.
- **Vorgabe aus** (`tracking=False`): Im Vergleich (Okt. 2026) war es auf der Validierung etwas schlechter
  (Mischung 2,0854 statt 2,0827), im Test etwas besser (1,9951 statt 1,9964) – beides im Rauschen. Einschalten
  mit `pm.trainieren(…, tracking=True)`; mit mehr Tracking-Historie erneut prüfen.

## Training: Abbruch

- `pm.trainieren(…, abbruch=…)`: wonach das Lernen auf der Validierung abbricht – `"standard"` (Regression:
  quadratischer Fehler), `"sieg"` (Log-Loss der Siegchance, dasselbe Maß wie die Modellwahl) oder `"ndcg"` (NDCG@3,
  nur die Spitze zählt). Mit `speichern=False` vergleichen, das Bessere speichern.

- **Value in der fairen Quote:** `pm.trainieren` speichert die faire Siegchance auf Validierung/Test
  (`modelle/power_oos.parquet`, außerhalb der Lerndaten); `pm.trainieren_wert` prüft p ∝ p_fair × exp(κ × Value)
  (Value = Abweichung des Value-Modells vom Markt, roh), κ auf der Validierung, Likelihood-Quotienten-Test und gepaarter
  Test (Bericht `value_in_fairer_quote`). Übernommen fließt der Value in die faire Quote ein – die Zahl dazu ist der
  Edge (angebotene gegen faire Quote); der Tooltip der fairen Quote nennt „davon Value: ±x %“ (ersetzt den goldenen
  Rahmen). Reihenfolge: erst `trainieren`, dann `trainieren_wert`.

## Kommentare (PMU, seit Ende August 2026)

- `kommentare.py`: fester Katalog von 16 Kategorien aus französischen Suchmustern (schlecht gestartet, vorne, hinten,
  ohne Deckung, langsames/schnelles Rennen, behindert, stark/ordentlich beendet, nachgelassen, unruhig, geschont,
  Problem, überlegen, knapp, Hinweis zum Merken); Verneinungen („sans être gêné“) zählen nicht. Kontrolle mit
  `km.uebersicht(df)` und `km.beispiele(df, "behindert")`.
- **Korrekturschicht auf die faire Siegchance** (noch nicht im Hauptmodell – zu wenige Monate): je Starter die Gruppen
  aus dem Kommentar zu seinem **letzten** Lauf (`k_vorne`, `k_pech` = behindert/schlecht gestartet/Problem/geschont,
  `k_ohne_deckung`, `k_gut` = stark/ordentlich beendet, `k_nachgelassen`, `k_knapp`); p ∝ p_fair × exp(Σ b × Gruppe),
  b per bedingtem Logit mit Schrumpfung. Prüfung rollierend: jede Woche wird mit Gewichten aus allen Wochen davor
  vorhergesagt (wie auf der Karte, ab 100 Rennen davor), gepaarter Test über alle so geprüften Rennen. Übernommen bei
  z ≤ −1,645 (dann aus allen neu geschätzt, auf der Karte angewandt); der
  Bericht zeigt es unter `kommentar_schicht (…)`. Mit jedem Monat mehr Daten – ab etwa einem Jahr ins Hauptmodell.

## PMU-Prognose (seit etwa Juli 2026 abrufbar)

- `prognose_basis.py`: Tabelle `pmu_prognosen` je Tag und Starter (cote probable, Platz in der Auswahl, Tippgeber, die
  das Pferd nennen). Einmalig nachholen mit `prognose_basis.nachholen_rueckwaerts(BASE)` (ab gestern zurück, bis 7 Renntage in Folge ohne Prognose); jede Karte und jeder neu
  verarbeitete Tag der Pipeline schreiben ihren Tag dazu. Die Prognose steht am Vortag/Morgen fest – Karte und Training sehen dieselbe.
- **Prognose-Schicht auf die faire Siegchance** (wie die Kommentar-Schicht): `pr_lp` = log Prognose-Chance (1/cote,
  je Rennen auf 1; nur bei vollständiger Auswahl) minus Ø im Rennen, `pr_tipp` = Anteil der Tippgeber, die das Pferd
  nennen. p ∝ p_fair × exp(b₁ × pr_lp + b₂ × pr_tipp), rollierend geprüft wie die Kommentar-Schicht, übernommen bei
  z ≤ −1,645 (Bericht `prognose_schicht (…)`).

## Training: Lern-Ziel „sieg“ und gepaarter Vergleich

- `pm.trainieren(…, art="sieg")`: LightGBM mit eigenem Ziel – Siegchance = Softmax der Vorhersage je Rennen, Verlust =
  −log Siegchance des Siegers (Benter); Abbruch nach dem Log-Loss der Siegchance. Lernt nur aus den Siegern (weniger
  Information als der Platzanteil, dafür genau das Maß der fairen Quote). `art="alle"` prüft es mit.
- `pm.vergleich(bericht_a, bericht_b, ("A", "B"))`: Log-Loss je Testrennen beider Läufe gepaart (Differenz, Standardfehler,
  z; < 0 = A besser), für die faire Siegchance (Power bzw. Power-Mischung). Die Berichte von `pm.trainieren` enthalten dafür `je_rennen`
  (nicht in der Meta-Datei gespeichert).

## Faire Quote (Karte und Value-Dashboard)

- Siegchance Power allein = Softmax(a × z) der Power-Vorhersage je Rennen (a auf der Validierung geschätzt).
- **Keine Marktquote:** Die Morgenquote ist ausgebaut – die Karte sah um 10 Uhr einen anderen Stand als den später
  gespeicherten, Training und Karte ließen sich nicht gleich rechnen.
- **Power-Mischung** (`zweitmodell=True`, Vorgabe): zusätzlich ein zweites Power-Modell mit Lern-Ziel „sieg“;
  Stärke = β × log p_Power + γ × log p_Power-sieg (Exponenten auf den Siegern der Validierung). Übernommen nur, wenn der
  Likelihood-Quotienten-Test gegen Power allein auf der Validierung χ²(1) > 3,84 ergibt. Dann ist sie **Power** auf
  der Karte (100 + 10 × z der Stärke im Feld) und die Grundlage der fairen Quote; die Treiber im Tooltip sind dann
  Power-Punkte aus beiden Modellen (Summe = Power − 100). `modelle/power_sieg.txt` wird gespeichert. Sonst bleibt Power
  die Regression.
- **CatBoost in der Power-Mischung** (`catboost=True`, Vorgabe; braucht `pip install catboost`): CatBoost lernt den
  Platzanteil auf denselben Merkmalen mit derselben Aufteilung (Abbruch auf der Validierung) und kommt als weitere Quelle
  hinzu: Stärke = β × log p_Power + γ × log p_Power-sieg + δ × log p_CatBoost (γ nur, wenn die Mischung ohne CatBoost
  übernommen ist). Übernommen nur nach Likelihood-Quotienten-Test gegen die Mischung ohne CatBoost (χ²(1) > 3,84, δ > 0);
  Bericht `power_mix mit CatBoost (ohne Markt)` mit gepaartem Test auf den Testtagen. Dann wird `modelle/power_cat.cbm`
  gespeichert, die Treiber enthalten die CatBoost-SHAP-Werte. Ohne installiertes catboost läuft alles wie bisher; fehlt
  es nur auf der Karte, bleibt Power dort die Regression (mit Hinweis).
- **Faire Quote auf der Karte** (nur noch eine): Power-Mischung × exp(κ × Value) (siehe oben) und – sobald übernommen –
  die Kommentar-Schicht. `sieg_blind` = ohne Value.

## Offen für den nächsten Neubau (Version 20)

Gesammelt, nicht dringend – beim nächsten ohnehin fälligen Neubau der Merkmale in einem Rutsch umsetzen:

1. **`draw_rel` korrigieren:** Boxen werden nach Nichtstartern nicht neu nummeriert (Box > Starterzahl in ~3 % der
   Zeilen, Werte bis 3,5). Stattdessen Rang der Box unter den tatsächlichen Startern (0 innen … 1 außen); dasselbe
   für das Boxdrittel in `box_stil_dev`.
2. **Penetrometer neu fassen:** `sire_going_pref` / `dam_sire_going_pref` (r = 0,98) messen fast nur den heutigen
   Penetrometer. Neu: `going_value` heute als eigenes Merkmal; Vorliebe von Linie und Pferd als Ø Penetrometer der
   Spitzenläufe minus Ø aller Läufe (geschrumpft); Passung = Vorliebe × (heute − Schnitt).
3. **`epr365` logarithmisch** (log(1 + €/Lauf)), damit Ausreißer `epr365_dz` nicht verzerren.
4. **`f1_tage` streichen** (identisch mit `days`).
5. **Höchsttempo ausbauen:** `f2_vmax_rel`, `f3_vmax_rel`, zeitgewichtetes Ø und Bestwert von `vmax_rel`, `vmax_rel` auf
   heutiger Distanzgruppe (`f1_vmax_rel` war im Value-Modell das stärkste neue Merkmal, Rang 16).
6. **Weglass-Tests:** `pm.trainieren(…, ohne=[…], speichern=False)` – Merkmalsgruppen ohne Neubau weglassen (z. B.
   `formz_pos_vb`/`formz_pos_pmu`, `form5_`-Dubletten, Rating-Varianten); behalten, was den Test-Log-Loss nicht
   verschlechtert.
