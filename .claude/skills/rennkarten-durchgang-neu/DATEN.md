# Daten der Karte für den Durchgang

Die HTML-Karte (`racecard_JJJJMMTT.html` aus `racecard.py`) enthält alle Daten in einer Zeile `const DATA = {…}`;
dieselben Daten stehen in `racecard_JJJJMMTT_daten.json` und komprimiert in `…_daten.json.gz` (unter 10 MB).
`scripts/blatt.py` liest sie und druckt nur, was die Prüfliste braucht. Diese Seite sagt, woher jede Angabe stammt und
wo die Daten Lücken haben.

## Rennen

| Angabe | Feld | Hinweis |
|---|---|---|
| Bodenangabe | `going` | z. B. „Très souple“; `going_source` PMU, PSF, manuell, France Galop (offizielle Angabe von france-galop.com, gleichwertig mit PMU) oder Annahme |
| Bodengruppe | `going_label` | Very slow (Collant, Lourd), Slow (Souple, Très souple), Fast (Bon souple, Bon), Very fast, PSF |
| Bahnkategorie | aus dem Bahnnamen (`blatt.py`) | groß, mittel, Provinz nach dem Nutzer; ausländische Bahnen mit Land |
| Bahn-Bias | `bias.iv_front`, `iv_back`, `races` | Sieg-Impact des vorderen bzw. hinteren Drittels (früh) auf Bahn und Distanz; begrenzt verlässlich |
| Richtung | `corde` | CORDE_DROITE = Rechtskurs, CORDE_GAUCHE = Linkskurs, LIGNE_DROITE = gerade |
| Klasse | `class.val_idx` | Ø Valeur der Teilnehmer, 100 = Ø aller Rennen; je Formzeile `cls_val_idx` |
| Tempo | `pace.label`, `pace.groups` | F führend, V vorne dabei, M Mittelfeld, H hinten; `unknown` ohne Laufstil |
| Festkurs-Stand | `festkurse_bahnen` | je Bahn Uhrzeit; Bahnen ohne Festkurse haben keine Kandidaten |
| Maßstäbe | aus `fk.sieg` | Die zwei Besten im Festkurs ohne Kandidaten-Value (unter +5 %); Kandidaten werden übersprungen. Blatt: `MASSSTAB 1/2`, `2/2` mit vollem Blatt |

## Starter

| Angabe | Feld | Hinweis |
|---|---|---|
| Modell-Siegchance | `power.sieg` | `sieg_blind` = ohne Schichten; derzeit meist gleich |
| Modell-Rang | aus `power.p` | 1 + Zahl der Starter mit höherer Power-Zahl (wie die Karte) |
| Festkurs | `fk.sieg` | Value = `fk.sieg × power.sieg − 1` |
| Value-Faktor | `power.wert`, `gold`, `warn` | nicht im Blatt (im Urteil ohne Belang) |
| Toto | `fk.toto` | nur als Warnung im Blatt, wenn mindestens doppelt so hoch wie der Festkurs; fällt bis zum Start oft stark |
| Marke | `rating`; `hcp_mark` | `hcp_mark.kind` sieg/platz, `diff` = heute − damalige Marke (positiv = Aufgewicht); **nur im Handicap aussagekräftig** |
| Valeur bereinigt | `rating_adj`, `rating_rank`/`rating_n` | Valeur − Gewicht + 55; zählt außerhalb des Handicaps (wer hat heute die meiste Klasse fürs Gewicht) |
| Qualität der Linie | `ae.pedigree.sire/dam_sire`: `pos_idx`, `epr_idx`, `max_val3_idx`, `horses` | Ø Platzierung, Gewinn je Lauf, Ø höchste Valeur der Dreijährigen der Nachkommen, als Index; das Blatt zeigt den Rang im Feld |
| Nachkommen je Distanzklasse | `pref_ref.sire/dam_sire.distance` → `pref_alle` | Läufe und Platzquote je Distanzklasse; das Blatt zeigt sie bei Distanzwechsel ab 250 m oder ohne Lauf in der heutigen Distanzgruppe |
| CGD | `cgd` | Je Buchstabe Bahn mit Belag (C), Bodengruppe (G), Distanzgruppe (D): Großbuchstabe = dort gewonnen, klein = platziert, · = gelaufen ohne Platz, ◦ = erstmals, – = unbekannt |
| Vorlieben | `pref.horse.going/distance/course/richtung/blinkers/trainer` | **Gesamtbilanz** der Datenbank; `today` markiert die heutige Gruppe; das Blatt zeigt die Platzquote statt A/E |
| A/E-Matrix | `ae.trainer/jockey/owner.d365`: `ae`, `pos_idx` | A/E+ = 100 × A/E Platz, Pos+ = Ø Platzierung als Index; das Blatt zeigt den Rang unter den Personen dieser Rolle im Rennen |
| Trainer | `ae.trainer.d30` (Form), `pref.trainer.course/racetype/age` | `trend` hot/cold; Trainerwechsel aus `pref.horse.trainer` (Läufe beim heutigen Trainer gegen alle) – Blatt: „Trainer erst seit N Läufen“ (bis 5) |
| Jockey | `ae.jockey.d365`, `pref.jockey.course/horse/trainer` | `pref.jockey.trainer` = Gespann |
| Ratings | `arr.adj` (gewichtsbereinigt), `arr.rank`, `tr.heute`, `tr.rank`, `rtr.rank`, `summary.dl600_a` | Top-ARR des Feldes im Blattkopf; ΔL600 = Tempo der letzten 600 m gegen Erwartung (km/h), Ø der Läufe |
| Karriere | `career.all`: Läufe, Siege, Plätze (einschließlich Siege), Gewinn je Lauf | Platzquote und Gewinn je Lauf mit Rang im Feld |
| Duelle | `duel_rank.score_l` | Längen vor (+) oder hinter (−) den Gegnern, direkt und indirekt |
| Box | `draw_stat.dev`, `sig` | Abweichung der Ø relativen Platzierung aus dieser Box von 0,5 (1 = Sieger, 0 = Letzter): **positiv = Box besser**, negativ = schlechter; nur `sig` = belastbar (Blatt: „signifikant besser/schlechter“) |
| Abstammung | `abst.sire/dam_sire.boden/dist.passung` | `sicher` = genug Läufe |

## Formzeilen (`form_lines`, neueste zuerst)

Je Lauf: `dist`, `going`, `type`, `pos`/`ran`, `margin` (Längen geschlagen), `odds`, `valeur` (Marke damals),
`weight`, `cls_val_idx`, `arr`/`arr_adj`, `blinkers`, `incident`, `unreliable` (> 10 L geschlagen), `verlauf`
(Rennen begünstigte vorne/hinten), `verlauf_pferd` (mit/gegen), `verlauf_plus` (gegen den Verlauf vorne gelandet –
ein belegtes Plus), `rivals_stat` (wie die Gegner danach liefen: aufgewertet, wenn mindestens die Hälfte besser),
`comment_de` (Rennkommentar, übersetzt; fehlt die Übersetzung, zeigt das Blatt das französische Original
`comment`).

## Leitfrage und Auslöser (gerechnet von `blatt.py`)

- **Leitfrage** (Rennkopf): je Kandidat und Maßstab der ARR (ber.) des Referenzlaufs mit Datum und Abstand zum Top-ARR
  des Feldes (`arr.adj`); „keiner“ ohne Lauf ≈heute im Blatt, „N Tage alt“ ab 366 Tagen.
- **Auslöser** (je Pferd): Regeln, deren Bedingung reine Rechnung ist, mit Kennung und Zahl. Schwellen wie in
  `SKILL.md`/`EINSICHTEN.md`:

| Kennung | Bedingung |
|---|---|
| `G-ARR-UNTER` | Referenz-ARR (ber.) 3 Punkte und mehr unter dem besten `arr.adj` der anderen Starter |
| `G-KEIN-REFERENZ` | kein Lauf ≈heute im Blatt oder Referenzlauf älter als 365 Tage; steht er unter „Ältere Läufe“, nur ein Hinweis |
| `F-AUFGEWICHT`, `G-UEBER-SIEGMARKE` | nur Handicap, `hcp_mark.kind` sieg: über 0 kg bzw. ab 1 kg über der letzten Siegmarke |
| `G-GEWICHT-BODEN` | ab 62 kg auf Très souple, Collant, Lourd; mit Aufgewicht auf Collant/Lourd zusätzlich `G-GEWICHT-KLASSE-BODEN` (Klassenfrage offen) |
| `G-STARTFOLGE` | ab 4 Starts in 42 Tagen (Formzeilen) |
| `G-GESPANN-OHNE-SIEG` | Gespann (`pref.jockey.trainer`) ab 20 Starts ohne Sieg |
| `G-TRAINER-KALT` | Bahnbilanz des Trainers ab 30 Starts mit A/E bis 0,55 |
| `F-PAUSE`, `F-TRAINERWECHSEL` | ab 60 Tagen seit dem letzten Start; Trainer erst seit höchstens 5 Läufen |
| `F-BELAG-NEU`, `F-BODEN-NEU`, `F-DISTANZ-NEU` | kein Lauf auf dem Belag (Vorlieben); CGD-Buchstabe G bzw. D „◦“, Boden nur ab Très souple |
| `G-ABSTAMMUNG` | Abstammung gesamt −15 und schlechter, heute erster bis dritter Lauf auf Belag oder Bodengruppe |
| `G-AUSRUESTUNG-WEG`, `P-AUSRUESTUNG-ZURUECK`, `F-AUSRUESTUNG-NEU` | Ausrüstung heute anders als im letzten Lauf und Platzquote mit ihr höher als ohne; ohne Läufe mit ihr: erstmals |
| `P-CGD`, `G-BOX`, `P-BOX` | Großbuchstabe im CGD; Box signifikant |

Nicht gerechnet, weil es Urteil braucht oder die Daten fehlen: exposed, Klassenfrage, „klar besser“, Trainerform der
letzten 30 Tage, erstmals Très souple innerhalb der Bodengruppe Slow.

## Lücken

- **Formzeilen zeigen nur die letzten Läufe** (höchstens sieben) und, falls darunter keiner auf derselben Bahn, Distanz
  (±100 m) oder Bodengruppe war, je Merkmal den letzten älteren (Feld `extra`, im Blatt „Ältere Läufe“); die
  Gesamtbilanz steht in den Vorlieben (`pref`).
- **Externe Läufe** (Belgien, PMH-Bahnen) haben oft keine Quote, Marke oder Ratings (`extern`).
- Läufe, die PMU gar nicht meldet, fehlen ganz; `starts` (PMU-Gesamtzahl) kann größer sein als die Zahl der Formzeilen.
- Eine fehlende Angabe ist eine Lücke, kein Negativbefund.
