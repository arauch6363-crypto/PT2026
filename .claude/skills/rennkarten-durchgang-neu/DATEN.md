# Daten der Karte für den Durchgang

Die HTML-Karte (`racecard_JJJJMMTT.html` aus `racecard.py`) enthält alle Daten in einer Zeile `const DATA = {…}`.
`scripts/blatt.py` liest sie und druckt nur, was die Prüfliste braucht. Diese Seite sagt, woher jede Angabe stammt und
wo die Daten Lücken haben.

## Rennen

| Angabe | Feld | Hinweis |
|---|---|---|
| Bodenangabe | `going` | z. B. „Très souple“; `going_source` PMU, manuell oder Annahme |
| Bodengruppe | `going_label` | Very slow (Collant, Lourd – für uns gleichwertig), Slow (Souple, Très souple – unterscheiden), Fast (Bon souple, Bon), Very fast, PSF |
| Richtung | `corde` | CORDE_DROITE = Rechtskurs, CORDE_GAUCHE = Linkskurs, LIGNE_DROITE = gerade |
| Klasse | `class.val_idx` | Ø Valeur der Teilnehmer, 100 = Ø aller Rennen; je Formzeile `cls_val_idx` |
| Tempo | `pace.label`, `pace.groups` | F führend, V vorne dabei, M Mittelfeld, H hinten; `unknown` ohne Laufstil |
| Festkurs-Stand | `festkurse_bahnen` | je Bahn Uhrzeit; Bahnen ohne Festkurse haben keine Kandidaten |

## Starter

| Angabe | Feld | Hinweis |
|---|---|---|
| Modell-Siegchance | `power.sieg` | `sieg_blind` = ohne Schichten; derzeit meist gleich |
| Modell-Rang | aus `power.p` | 1 + Zahl der Starter mit höherer Power-Zahl (wie die Karte) |
| Festkurs | `fk.sieg` | Value = `fk.sieg × power.sieg − 1` |
| Value-Faktor | `power.wert`, `gold`, `warn` | nicht dasselbe wie Value |
| Marke | `rating`; `hcp_mark` | `hcp_mark.kind` sieg/platz, `diff` = heute − damalige Marke (positiv = Aufgewicht); **nur im Handicap aussagekräftig** |
| Valeur bereinigt | `rating_adj`, `rating_rank`/`rating_n` | Valeur − Gewicht + 55; zählt außerhalb des Handicaps (wer hat heute die meiste Klasse fürs Gewicht) |
| Qualität der Linie | `ae.pedigree.sire/dam_sire`: `max_val3_idx`, `epr_idx`, `horses` | Ø höchste Valeur der Nachkommen als Dreijährige bzw. Gewinn je Lauf, als Index; v. a. bei jungen Pferden |
| CGD | `cgd` | Je Buchstabe Bahn mit Belag (C), Bodengruppe (G), Distanzgruppe (D): Großbuchstabe = dort gewonnen, klein = platziert, · = gelaufen ohne Platz, ◦ = erstmals, – = unbekannt |
| Vorlieben | `pref.horse.going/distance/course/richtung/blinkers/trainer` | **Gesamtbilanz** der Datenbank; `today` markiert die heutige Gruppe |
| Trainer | `ae.trainer.d30` (Form), `pref.trainer.course/racetype/age` | `trend` hot/cold |
| Jockey | `ae.jockey.d365`, `pref.jockey.course/horse/trainer` | `pref.jockey.trainer` = Gespann |
| Ratings | `arr.adj` (gewichtsbereinigt), `arr.rank`, `tr.rank`, `rtr.rank` | Top-ARR des Feldes im Blattkopf |
| Duelle | `duel_rank.score_l` | Längen vor (+) oder hinter (−) den Gegnern, direkt und indirekt |
| Box | `draw_stat.dev`, `sig` | nur `sig` = belastbar |
| Abstammung | `abst.sire/dam_sire.boden/dist.passung` | `sicher` = genug Läufe |

## Formzeilen (`form_lines`, neueste zuerst)

Je Lauf: `dist`, `going`, `type`, `pos`/`ran`, `margin` (Längen geschlagen), `odds`, `valeur` (Marke damals),
`weight`, `cls_val_idx`, `arr`/`arr_adj`, `blinkers`, `incident`, `unreliable` (> 10 L geschlagen), `verlauf`
(Rennen begünstigte vorne/hinten), `verlauf_pferd` (mit/gegen), `verlauf_plus` (gegen den Verlauf vorne gelandet –
ein belegtes Plus), `rivals_stat` (wie die Gegner danach liefen: aufgewertet, wenn mindestens die Hälfte besser),
`comment_de` (Rennkommentar, übersetzt).

## Lücken

- **Formzeilen zeigen nur die letzten Läufe.** Für Boden, Distanz, Bahn immer die Vorlieben lesen (Fall Algeciras:
  „nie auf Très souple“ war falsch, die Vorlieben zeigten einen Sieg auf sehr weichem Boden).
- **Externe Läufe** (Belgien, PMH-Bahnen) haben oft keine Quote, Marke oder Ratings (`extern`).
- Läufe, die PMU gar nicht meldet, fehlen ganz; `starts` (PMU-Gesamtzahl) kann größer sein als die Zahl der Formzeilen.
- Eine fehlende Angabe ist eine Lücke, kein Negativbefund.
