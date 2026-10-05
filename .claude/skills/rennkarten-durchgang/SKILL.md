---
name: "rennkarten-durchgang"
description: Qualitativer Durchgang durch eine französische Galopp-Racecard (Vollblut, Araber, Anglo-Araber), Pferd für Pferd in Reihenfolge der PMU-Prognose (cote probable), mit dem Ziel, pro Starter einen Wett-Angle zu bejahen oder zu verneinen, zu prüfen, ob die Öffentlichkeit ihn über Prognose, Cribles und Presse-Tipps schon wahrgenommen und eingepreist hat, daraus den Edge zu berechnen und für jedes Pferd mit Angle eine Mindestquote (Festkurs) zu nennen. Live-, Morgen- oder Totokurse werden nicht verwendet, auch wenn sie noch im DATA-Block stehen. Ergänzt den Skill "rennanalyse", der das quantitative Rennprofil liefert. Verwenden, wann immer eine Racecard durchgegangen, Kandidaten gesucht oder Mindestquoten bestimmt werden sollen.
---

# Rennkarten-Durchgang

## Zweck und Abgrenzung

Dieser Skill beschreibt den qualitativen Lesedurchgang durch eine Racecard.
Er ersetzt nicht den Skill `rennanalyse` mit seinem Script, sondern läuft
daneben: das Script liefert Rennprofil und statistische Angles, dieser
Durchgang liefert die Beurteilung Pferd für Pferd aus den Formzeilen.

Die Leitfrage ist nie "läuft das Pferd gut?", sondern **"gibt es hier einen
Angle?"** — einen konkreten Grund, warum dieses Pferd heute besser
abschneidet, als der Markt erwartet. Ein gutes Pferd ohne Angle ist für
diesen Durchgang uninteressant.

## Grundregeln vorab

**Prognose statt Kurs.** Die Karte zeigt keine Live-Kurse; Morgen- und
Totokurs sind nur Zwischenstände vom Zeitpunkt der Kartenerstellung und
verleiten zum Anker. Stehen `odds` oder `odds_morning` noch im
`DATA`-Block, werden sie **vollständig ignoriert** — nicht für die
Reihenfolge, nicht als Markteinschätzung, nicht als Kontrolle, nicht in
der Ausgabe. Nicht betroffen sind die **historischen Endquoten** in
`form_lines` und `rivals`: Sie bleiben Formmaß und Hinweis auf die
Stallerwartung (B4). An die Stelle der Kurse tritt die PMU-Prognose
(Abschnitt P). Der Nutzer wettet meist zu Festkurs; ob ein Pferd Value
hat, entscheidet sich erst, wenn er seinen Festkurs gegen die
Mindestquote aus Abschnitt C hält.

**Status und Nichtstarter.** `DATA.generated` sagt nur, welche Rennen noch
offen sind. Rennen mit `status` ungleich `PROGRAMMEE` (etwa `ARRIVEE_…`
mit gefülltem `result`) stehen in der Ausgabe als eine Zeile und werden
nicht durchgegangen, es sei denn, der Nutzer will sie nachbesprechen.
Nichtstarter (`nr: true`) werden gestrichen, bevor irgendetwas gerechnet
wird. `declared` minus Starter ergibt die Zahl der Nichtstarter.

**Lesereihenfolge.**
- Prognose-Rang, cote probable und der Rennkommentar der PMU dürfen am
  Anfang stehen, als Orientierung: Was sieht die Öffentlichkeit, und
  welche Pferde nennt sie?
- Auch den Crible eines Pferdes darf man zu Beginn seines Durchgangs
  lesen.
- Pflicht bleibt B11: Jedes eigene Argument wird ausdrücklich gegen Text,
  Crible und Tipps gehalten, mit dem Ergebnis *eingepreist*, *teilweise*
  oder *nicht erkannt*. Wer den Crible zuerst liest, sucht in den
  Formzeilen gezielt das, was er **nicht** nennt.
- Ratings kommen weiter erst in B13.

**Fehlende Information ist eine Lücke, kein Negativbefund.** Statistiken
mit kleiner Fallzahl werden als solche gekennzeichnet. Was die Karte
grundsätzlich nicht weiß, steht im nächsten Abschnitt.

## Abschnitt D — Was die Karte weiß und was nicht

Alle berechneten Werte (`career`, `pref`, `ae`, `days`, Duelle, Ratings,
Sektionalzeiten) stammen aus einer Datenbank **französischer
Flachrennen ab `DATA.history.from`** (derzeit Oktober 2022). Daraus
folgen Lücken, die vor dem Durchgang bekannt sein müssen:

- **`starts`, `wins`, `places` sind die PMU-Gesamtbilanz**, inklusive
  älterer Läufe, Auslandsstarts und Hindernisrennen. `career.all` kennt
  nur die Datenbank. Liegt `starts` deutlich über `career.all.runs`,
  fehlen Läufe. Die **Musique** (`form`) zeigt alle Starts; Buchstaben
  außer `p` (etwa `h`, `s`) sind Hindernisläufe, Jahreszahlen in
  Klammern trennen Saisons.
- **`days` zählt seit dem letzten Lauf in der Datenbank.** Ist das Pferd
  zwischendurch im Ausland oder über Hindernisse gelaufen, ist die Pause
  kürzer als angezeigt — vor einem Pausen-Fragezeichen (B6a) die Musique
  prüfen.
- **Kommentare gibt es fast nur zum letzten, selten zum vorletzten Lauf.**
  Ältere Formzeilen werden über Laufposition, Weg und Sektionalwerte
  gelesen (B4). `comment_de` ist eine Übersetzung; für Nuancen wie *a
  fini courageusement* gilt das Original in `comment`.
- **Laufstil, Tempo und Sektionalwerte brauchen Tracking.** Pferde ohne
  getrackte Läufe stehen in `pace.unknown` und haben kein `style`.
- **Auslandspferde.** Ein ausländischer Stall (Trainer oder Jockey aus
  Spanien, Belgien …) zusammen mit großer `luecke` heißt meist: Die
  fehlenden Starts liefen im Ausland. Dann ist auch `days` vermutlich zu
  lang, und die französische Trainerstatistik beruht auf wenigen Läufen.
  Beides nur unter Vorbehalt lesen.
- **Boden kann angenommen sein** (`going_assumed: true`): siehe A.
- **Araber und Anglo-Araber** sind eigene Populationen (A, Rennart).

Eine dieser Lücken wird beim betroffenen Pferd in einem Halbsatz genannt
und in der Sicherheitsstufe (C1) berücksichtigt — sie wird nicht als
Argument gegen das Pferd gewertet.

## Abschnitt P — Die Prognose als Wahrnehmung der Öffentlichkeit

### P1 — Die Felder

Rennebene, `races[id].prono`:

- `text` / `text_de`: Rennkommentar des Pronostiqueurs.
- `selection[]`: je Pferd `no`, `rank`, `cote` (cote probable als Bruch,
  etwa „4/1" oder „2.4/1") und `cote_dec` (dezimal, Bruch plus 1). Die
  Auswahl umfasst inzwischen in der Regel **das ganze Feld**, in feinen
  Stufen und **ohne Deckel** (auch 50/1 oder 80/1).
- `tips[]`: Tippreihen weiterer Quellen mit `source` und `nos` in
  Tippreihenfolge (meist sechs bis sieben Namen); `consensus` fasst sie
  nach Borda zusammen.
- `cribles_ohne`: Pferdekommentare ohne Zuordnung — trotzdem lesen.

Pferdeebene, `runners[].prono`:

- `sel`: Rang und cote probable dieses Pferdes.
- `tips`: in `n` von `of` Tippreihen genannt, davon `top3`-mal unter den
  ersten drei, Ø-Platz `avg`. Fehlt der Eintrag, nennt keine Quelle das
  Pferd.
- `konsens`: Platz des Pferdes im Konsens aller Tippreihen (Borda) —
  `pos` (Platz, gleiche Punkte = gleicher Platz), `of` (Zahl der
  überhaupt getippten Pferde), `pts` (Punkte). Die Karte zeigt ihn in der
  Prognose-Kachel als „Tipp 2./9“. Fehlt der Eintrag, steht das Pferd in
  keiner Tippreihe.
- `crible` / `crible_de`: Kurzkommentar zum Pferd, nicht bei jedem.

### P2 — Prognose-Chance

Die cote probable trägt eine **deutliche Marge**: Die Summe von
1 / `cote_dec` liegt typischerweise bei 115–150 %, in kleinen Feldern
eher oben. Die Normierung entscheidet deshalb spürbar über den Edge.

Normiert wird mit der **Potenzmethode**: den Exponenten k suchen, für den
Σ (1 / `cote_dec`)^k = 1 ist, und p = (1 / `cote_dec`)^k setzen. Sie
zieht die Marge stärker bei den Außenseitern ab als beim Favoriten — so,
wie Quotenmärkte die Marge tatsächlich verteilen. Bei einem Achterfeld
mit 149 % Summe macht das beim Favoriten (2.4/1) 33 statt 28 % und bei
einem 16/1-Pferd 2,9 statt 4,2 % aus; der Edge eines Außenseiters
verschiebt sich damit um fast die Hälfte. In großen Feldern mit
geringerer Marge ist der Unterschied klein.

Bei großen Außenseitern bleibt die Prognose-Chance eine Größenordnung —
die cote probable ist eine Redaktionsschätzung, kein Markt. Edges dort
mit entsprechender Vorsicht lesen.

### P3 — Wie stark wird die Öffentlichkeit das Pferd spielen?

Prognose-Rang (`sel.rank`) und Tipp-Konsens (`konsens.pos`) zusammen
ergeben die Publikumslage. Weichen beide um mehrere Plätze voneinander
ab, ist das der Fall „Quellen uneins“:

- **Publikumspferd:** vorne in der Prognose und in den Tipps, mit
  wohlwollendem Crible. Der Festkurs wird bis zum Start tendenziell
  unter der cote probable liegen.
- **Quellen uneins:** Prognose vorne, Tipps hinten oder ohne — oder
  umgekehrt, etwa ein 25/1-Pferd, das eine Zeitung an erster Stelle
  tippt. Der Kurs ist offener; der Widerspruch ist ein Hinweis, das Pferd
  genau anzusehen.
- **Übersehen:** hinten in der Prognose, in keinem Tipp, kein Crible.
  Das Publikum spielt es kaum; der Kurs liegt eher über der cote
  probable.

Mit nur einer Tippquelle (`of: 1`, derzeit der Normalfall) ist die
Tipp-Ebene dünn und wird auch so benannt. Alles hier ist eine Tendenz,
keine Gesetzmäßigkeit.

## Abschnitt A — Renncharakteristik

Zuerst das Rennen, dann die Pferde. Aus `type`, `age`, `sex`, `distance`,
`going_label`, `corde`, `prize`, `class` und `pace` ergibt sich die
Leitfrage für den ganzen Durchgang.

Dazu das **Prognose-Profil** — nur die Zahlen, nicht der Text: Wie
deutlich ist der Prognose-Favorit (2/1 ist ein klares Urteil, 4/1 in
einem großen Feld ein offenes Rennen), und wie viele Pferde stehen unter
etwa 10/1? Ein Rennen, das die Öffentlichkeit für offen hält, lässt mehr
Raum für einen Edge als eines mit einem erdrückenden Favoriten.

### A1 — Rennart und Leitfrage

Die Leitfrage hängt an der Rennart und entscheidet, welche Kriterien im
ganzen Durchgang schwer wiegen:

- **Handicap für Dreijährige:** "Wer kann sich noch steigern?" Exposure
  zählt stark, die jüngste Formentwicklung wiegt mehr als die
  Gesamtbilanz, die Abstammung wird als Vater-Mutter-Kombination gelesen.
- **Handicap für Vierjährige und ältere:** "Wer trifft heute die
  Bedingungen, und wo stimmt die Marke?" Die meisten Pferde sind exposed,
  Exposure ist nur Randnotiz. Es entscheiden Bahn-, Boden- und
  Distanzbilanz, die Marke gegen die letzte Sieg- oder Platzmarke (B6)
  und die Konstellation aus Startbox, Laufstil, Tempo und Bias.
- **Claimer (Verkaufsrennen, auch „Handicap à réclamer"):** "Wer steigt
  in der Klasse ab, und wer will hier gewinnen?" Der typische Angle ist
  ein Pferd, dessen Formzeilen aus klar stärkeren Rennen kommen
  (Klassenindizes in B0). Trainer- und Besitzerwechsel (B2) sind hier
  häufig — oft nach einem Claim — und verdienen einen Blick. Eine
  vorhandene Handicapmarke ist ein brauchbares Klassenmaß gegen das Feld.
- **Conditions, Listed und Gruppenrennen:** "Wer hat die Klasse, und was
  kostet sie heute an Gewicht?" Ohne Handicap fällt die Marke-Frage aus
  B6 weg; an ihre Stelle treten die gewichtsbereinigte Valeur
  (`rating_adj`, Rang `rating_rank`, siehe B13) im Feldvergleich, die
  Herkunftsklasse der Formzeilen, der Gewinn je Lauf relativ zum Feld
  (`career.d365.rel`) und das heutige Gewicht. In Gruppenrennen liegt die
  Prognose meist nah an der Wirklichkeit — Edges sind seltener und
  kleiner.
- **Zweijährigen-Rennen, Maiden oder Conditions mit Debütanten:** "Wer
  ist frühreif genug, und wem traut der Stall etwas zu?" Es gilt das
  eigene Raster in Abschnitt B-2J, auch bei Zweijährigen-Claimern.
- **Nachwuchsreiter-Rennen** (Apprentis, Jeunes Jockeys, oft „Course à
  conditions"): Die Gewichtserlaubnisse stecken im Gewicht, die
  Jockeystatistik beruht auf kleinen Stichproben. Ein erfahrener
  Nachwuchsreiter mit guter Form ist hier mehr wert als sonst.
- **Araber und Anglo-Araber.** Vollblutaraber laufen in eigenen Rennen
  (oft `type: "Inconnu"`, Name mit „Arabian", Formzeilen „Qualification
  Accaf"); Anglo-Araber tragen „AA" im Namen und laufen vor allem im
  Südwesten. Beide sind eigene Populationen: Valeur, Ratings und
  Abstammungsstatistik nur **innerhalb der Rasse** vergleichen, nie gegen
  Vollblut-Werte. Trainer- und Jockeystatistik mischt die Rassen und ist
  entsprechend unschärfer.
- **Rennart unbekannt (`Inconnu`)** ohne Araber-Hinweis: aus Name,
  Dotierung, Alter und Geschlecht erschließen; keine Handicap-Logik
  unterstellen.

Bei sehr wenigen Starts gilt unabhängig von der Rennart die Variante aus
B3: die ganze Karriere als Entwicklungsverlauf lesen.

### A2 — Boden

Alle Berechnungen nutzen Bodengruppen: Lourd, Très lourd, Collant =
Very slow · Souple, Très souple = Slow · Bon souple, Bon = Fast · Léger
und härter = Very fast · PSF. Der Penetrometer-Wert ist nur Anzeige.

**`going_assumed: true` heißt: Zum Kartenstand gab es noch keine
offizielle Bodenangabe; angenommen ist Fast.** Dann gilt:

- Jede Bodenbilanz mit `today: true` bezieht sich auf die Annahme. Beim
  Pferd zusätzlich die Zeile der Nachbargruppe lesen (meist Slow) — ein
  Pferd mit klar besserer Fast- als Slow-Bilanz hängt am Wetter.
- Ein Angle, der am Boden hängt, bekommt in der Ausgabe die Bedingung
  „gilt bei Bon/Bon souple" — und der Nutzer den Hinweis, den
  offiziellen Boden vor der Wette zu prüfen.
- PSF ist nie angenommen; dort entfällt das.

**Woher der Boden kommt, steht in `going_source`:**

- `PMU` — offizielle Angabe. Sie hat immer Vorrang.
- `manuell` — vom Nutzer eingetragen (`boden_manuell.json`). Gilt wie
  eine Angabe. Ein Angle, der am Boden hängt, bekommt trotzdem die
  Bedingung „gilt bei …“.
- `PSF` — PMU hat noch nichts, das Rennen ist laut Bahnart PSF.
- `Annahme` — weder PMU noch ein Eintrag; es gilt Fast, siehe oben.

### A3 — Klasse

`class.val` ist die Ø Valeur der Starter, `class.val_idx` derselbe Wert
als Index (100 = Ø aller früheren Rennen), `class.epr_idx` die
Rennstärke als Ø Gewinn je Lauf der Starter im letzten Jahr, ebenfalls
indexiert. Die Formzeilen tragen dieselben Indizes für das damalige
Rennen (`cls_val_idx`, `cls_epr_idx`). Damit wird „heute leichter oder
schwerer" in B0 zur Rechnung statt zum Eindruck. `val` fehlt, wenn zu
wenige Starter eine Valeur haben (Zweijährige, Araber).

### A4 — Tempo und Bias

- **Tempo** aus `pace`: `label` (langsam, normal, schnell), erwartete
  Pace gegen die Norm der Distanzgruppe, Zahl der Tempomacher
  (`n_front`) und die Gruppen F/V/M/H (führend, vorne dabei, Mittelfeld,
  hinten — aus der Ø frühen Position der letzten fünf getrackten Läufe).
  Pferde in `pace.unknown` sind im Tempobild nicht enthalten; läuft
  darunter ein möglicher Führender, ist das Szenario offener.
- **Ein Tempo-Angle braucht einen Beleg.** „Einziges Frontpferd" oder
  „kann unbedrängt führen" gilt nur, wenn beide Bedingungen erfüllt sind:
  1. Das Pferd hat **mindestens drei getrackte Läufe mit früher
     Position** (Formzeilen mit `early_pos`), und die frühe Position war
     dort überwiegend vorne. Eine Einordnung in F oder V aus ein oder
     zwei Läufen reicht nicht.
  2. **Kein Pferd aus `pace.unknown` könnte das Profil ebenfalls
     haben.** Ein Pferd ohne Tracking ist kein belegter Spätstarter,
     sondern unbekannt. Deshalb bei diesen Pferden Musique, Kommentare
     (*vite en tête*, *aux avant-postes*, *a mené*) und, bei Debütanten,
     den Stall prüfen. Ist ein möglicher Führender darunter, ist das
     Pferd nicht das einzige Frontpferd.

  Fehlt eine der beiden Bedingungen, bleibt das Tempo ein Nebenargument
  und trägt allein keinen Angle.
- **Felder mit wenig gelaufenen Pferden.** Hat die Mehrheit der Starter
  weniger als drei getrackte Läufe oder steht in `pace.unknown` (typisch
  für Dreijährigen-Conditions, AQPS-Flachrennen und Zweijährige), ist
  schon das Tempobild unsicher. Ein Angle, der auf dem Tempo beruht,
  steht dann in der Tabelle (C2) **höchstens mit der Sicherheit
  „spekulativ"**, auch wenn beide Bedingungen oben erfüllt sind.
- **Bias** = `iv_front` − `iv_back`. Frontrenner sind überall im
  Vorteil. Das Signal ist deshalb `bias_rel`, die Abweichung vom Schnitt
  aller Bahnen (`bias_all`):
  - innerhalb ±0,25: wie überall
  - darüber: vorne stärker im Vorteil
  - darunter: abwartend Gerittene hier besser
  - Ein absoluter Bias von +0,16 begünstigt also Spätstarter.
- **Stichprobe** `bias.races`: Unter etwa 50 Rennen ist der Bias eine
  Andeutung (`basis`: `exakt` = Bahn und Distanz, `gruppe` = Bahn und
  Distanzgruppe).
- Der Bias wird nur bei einem Pferd herangezogen, dessen Laufstil dazu
  passt — nicht pauschal auf das ganze Feld.
- **Tempo und Bias immer zusammen lesen.** Ein langsam erwartetes Rennen
  ohne echtes Frontpferd (`pace.groups.F` leer) verstärkt einen
  Frontbias: Wer nachweislich vorne gehen kann (Beleg wie oben), hat es
  doppelt gut, die Spätstarter doppelt schwer. Ein schnelles Rennen mit mehreren Führenden auf einem
  Kurs, der abwartend Gerittene ohnehin begünstigt, ist umgekehrt die
  beste Lage für die Gruppe H.

## Abschnitt B — Raster je Starter

**Reihenfolge: nach Prognose-Rang (`prono.sel.rank`), von den Favoriten
abwärts** — nicht nach Startnummer, nicht nach `odds`. Pferde ohne
Prognose-Eintrag kommen ans Ende. Die großen Außenseiter dürfen
übersprungen werden, sobald klar ist, dass sie die Entscheidung nicht
mehr berühren — **aber nicht ungelesen, wenn eine Tippquelle sie vorne
nennt** (P3). Bei gleicher cote probable ist die Reihenfolge frei.

Die Punkte B0 bis B13 sind eine Checkliste, keine starre Abfolge. In der
Praxis läuft der Durchgang je Pferd ungefähr so: letzter Lauf und was
sich heute ändert (B0) → Datenlage und Wechsel (B2) → Bilanz unter den
heutigen Bedingungen (B6) → Frische und Saisonbelastung (B6a) → Trainer
und Jockey (B7) → Crible (B11) → Fazit mit Einordnung in die laufende
Rangfolge (B12, B10) → kurzer Blick auf die Ratings (B13).

### B0 — Einstieg: der letzte Lauf und was sich heute ändert

Jedes Pferd beginnt mit seinem letzten Start (erste Zeile in
`form_lines`): Platz, Feldgröße, Rückstand, damalige Quote, ob es
Favorit war (`fav`), Bahn und Kommentar. Ein Zweiter mit einer halben
Länge zu 5:1 ist ein gelaufenes Rennen, ein Fünfter von 13 mit *a fini
courageusement* auch.

Danach sofort das **Delta zu heute** benennen, bevor irgendeine Bilanz
gelesen wird:

- **Distanz:** heute gegen letzten Lauf in Metern (`distance` gegen
  `dist`). „300 Meter weiter als zuletzt" ist der Anlass, in B6 die
  Distanzbilanz gezielt zu prüfen.
- **Belag:** PSF gegen Turf (`going` der Formzeile beginnt mit „PSF").
  Ein Belagwechsel ist der häufigste Grund, warum eine gute letzte Form
  heute wenig sagt — siehe B3.
- **Boden und Bahn:** vergleichbar oder nicht; bei angenommenem Boden
  mit Vorbehalt (A2).
- **Abstand:** `days` seit dem letzten Start — siehe B6a und D.
- **Rennniveau:** heute leichter oder schwerer als zuletzt, gemessen an
  `class.val_idx` / `class.epr_idx` heute gegen `cls_val_idx` /
  `cls_epr_idx` der Formzeile, dazu die Dotierung. 30 Indexpunkte
  Unterschied sind ein klarer Klassenschritt.

Bleibt das Delta klein — gleiche Distanz, gleicher Belag, ähnliche
Klasse, normaler Abstand —, trägt die letzte Form direkt. Je mehr sich
ändert, desto weniger.

### B1 — Exposure

**Maßstab ist `starts`** (PMU-Gesamtzahl), nicht `career.all.runs` — die
Datenbank-Karriere kann deutlich kürzer sein (D). Viele Starts heißt
exposed: das Pferd hat gezeigt, was es kann, Steigerungspotenzial ist
unwahrscheinlich. In Dreijährigen-Handicaps ist das ein Minuspunkt;
wenige Starts sind ein Pluspunkt.

**Der Maßstab ist feldrelativ.** Zwölf Starts sind bei Dreijährigen viel
und in einem Feld mit Pferden über 50 Starts wenig. In einem Feld, in
dem fast alle exposed sind, trennt das Kriterium kaum noch und tritt
hinter Bedingungen und Marke zurück.

### B2 — Datenlage, Wechsel und Kennzeichen

Bevor die Formzeilen gefiltert werden, drei kurze Prüfungen:

**Datenlage.** `starts` gegen `career.all.runs`, Musique gegen
`form_lines` (D). Fehlen jüngere Läufe — Auslandsstart, Hindernislauf —,
ist die letzte Formzeile nicht der letzte Lauf, und B0 steht unter
Vorbehalt.

**Kennzeichen** (`badges`): `C` Sieger auf der Bahn, `D` Sieger über
die Distanz (±100 m), `CD` beides im selben Rennen, `BF` beim letzten
Start als Favorit geschlagen. C, D und CD sind auch in der Presse
Standard und damit **eingepreist**; sie bestätigen, begründen aber
selten einen Angle. BF heißt: Der Stall hat sich zuletzt mehr
ausgerechnet. Hatte die Niederlage einen Grund, der heute wegfällt, ist
das ein Ansatz; ohne Grund ist ein BF-Pferd, das wieder vorne in der
Prognose steht, eher ein Kandidat für Überschätzung.

**Wechsel** (`changes`, gegenüber dem letzten Lauf in der Datenbank):

- **Ausrüstung** — `b1` erstmals (australische) Scheuklappen, `b0` ohne
  (zuletzt mit), `b↔` Wechsel der Art. Immer gegen `pref.horse.blinkers`
  lesen, die Bilanz mit und ohne. Eine Änderung allein ist kein Angle,
  eine Änderung mit guter Vorbilanz schon. Mit Vorgeschichte lesen:
  Wurde die Ausrüstung früher schon getragen und wieder abgenommen, hat
  sie nicht funktioniert — „wieder drauf" ist dann ein schwächeres
  Signal als „erstmals überhaupt".
- **Trainerwechsel** (`TR`, „vorher …") — `pref.horse.trainer` zeigt die
  Bilanz des Pferdes je Trainer mit Zeitraum (`from`, `to`). Hat das
  Pferd beim neuen Trainer schon Läufe, zählt deren Bilanz gegen die
  beim alten; ist heute der erste Start im neuen Stall, zählen dessen
  Form (B7) und die Frage, ob der Wechsel einen Klassenauf- oder -abstieg
  bedeutet. Ein formstarker neuer Stall bei schwacher Bilanz unter dem
  alten ist ein Ansatz, der selten im Crible steht.
- **Besitzerwechsel** (`OW`) — allein kein Angle, oft Folge eines Claims
  oder Verkaufs. Zusammen mit einem Trainerwechsel ein Zeichen neuer
  Pläne; das ist eine Lesart, keine Feststellung.
- **Erstmals Wallach** — ein mildes Plus bei Hengsten, die bisher
  unter ihren Möglichkeiten liefen.

### B3 — Formzeilen filtern

**Aufbau von `form_lines`:**
- Die letzten sieben Läufe; `same` nennt, worin eine Zeile heute
  entspricht: `K` Kurs mit gleichem Belag, `D` Distanz ±100 m, `B`
  Bodengruppe.
- Fehlt ein Merkmal unter den sieben, folgen bis zu drei ältere Läufe
  mit diesem Merkmal (`extra`, etwa `["K"]`). Sie sind nicht Teil der
  jüngsten Form und zählen für B6, nicht für B0.

Die Zeilen werden nicht alle gleich gelesen. Zuerst aussortieren:

- Klar geschlagene Läufe, etwa Zehnter von zwölf mit neun Längen
  Rückstand. `unreliable: true` markiert Läufe mit mehr als zehn Längen
  Rückstand — vermutlich ausgeritten, abhaken. Läufe mit `incident`
  (gestürzt, angehalten, disqualifiziert, am Start stehen geblieben)
  sind keine Formaussage.
- Läufe unter stark abweichenden Bedingungen — andere Distanzkategorie,
  anderer Boden, andere Rennart. Als nicht repräsentativ markieren,
  nicht als schlechte Form werten.
- **`tr_cap: true`** heißt: Das Rennen ist „falsch gelaufen", der
  Schlussabschnitt war extrem schnell oder langsam gegen das Optimum.
  Platz und Rückstand sagen dann wenig über die Leistungsfähigkeit — in
  beide Richtungen.
- **Eine Bedingung darf man streichen, wenn die Bilanz es rechtfertigt.**
  Ist ein Pferd auf PSF 0 aus 8 ohne Platzierung, sind die PSF-Läufe
  keine Aussage über seine Form, sondern über die Unterlage. Erst die
  Bilanz begründet das Streichen, nicht der Wunsch, eine schlechte Zeile
  loszuwerden.
- **Belagwechsel PSF ↔ Turf.** Kommt die gesamte jüngere Form von der
  PSF und läuft das Pferd heute auf Gras (oder umgekehrt), wird diese
  Form nur so weit übertragen, wie die Bilanz auf dem heutigen Belag es
  hergibt (`pref.horse.going`). Ist die PSF-Bilanz klar besser, ist die
  gute letzte Form heute ein schwächeres Argument — auch wenn die
  Abstammung keinen Nachteil auf Gras erwarten lässt (B8).
- **Saisondebüt verzeihen.** Ein klar geschlagener erster Jahresstart
  nach der Winterpause wird nicht als Formaussage gelesen, wenn danach
  ordentliche Läufe kommen — vor allem nicht bei unveränderter Marke.
- **Ausreißer zwischen guten Läufen: erst die Bedingungen prüfen.** Bevor
  ein schwacher Lauf zwischen zwei guten als Inkonstanz gilt, Distanz,
  Boden, Belag und Klasse dieses Laufs gegen die guten halten. Beispiel
  Azimuts (Le Mans, 05.10.2026): Siege über 1600 und 1850 m, geschlagen
  über 2100 und 2200 m. Das ist eine Distanzgrenze und keine Inkonstanz.
  Ein Duell aus so einem Lauf (B9) zählt dann wenig.
- Bei vielen Starts pro Pferd reicht es, gezielt nach den
  **vergleichbaren Bedingungen** zu suchen — gleiche Distanz, gleicher
  Boden, ähnliche Klasse — statt alle Zeilen der Reihe nach zu würdigen.
  `same` nimmt die Suche ab: Zeilen mit zwei oder drei Kennzeichen sind
  die ersten Kandidaten. Steht nur in einer angehängten `extra`-Zeile
  ein Lauf unter heutigen Bedingungen, ist das Material dafür alt — das
  Alter mitlesen und in der Sicherheit berücksichtigen.

**Variante bei wenig Starts:** Hat ein Pferd nur drei bis vier Läufe,
entfällt das Filtern. Stattdessen den Entwicklungsverlauf vom Debüt
bis heute durchgehen — die Richtung ist dann die Information.

### B4 — Die relevanten Läufe genau lesen

Für jede verbliebene Zeile:

- Platz, Feldgröße, Rückstand in Längen.
- Den Kommentar, falls vorhanden (D). *A fini courageusement* heißt, das
  Pferd hat gekämpft — das relativiert eine mäßige Platzierung nach oben.
- **Die damalige Quote ist zweierlei:** ein Formmaß und ein Hinweis auf
  die Stallerwartung. Ein vierter Platz zu 15:1 ist eine positive
  Überraschung; ein fünfter Platz zu 5,9:1 heißt, dass sich jemand mehr
  ausgerechnet und es nicht eingelöst hat. `odds_rank` und `fav` zeigen
  die Stellung im damaligen Markt.
- **Das Laufbild** (nur mit Tracking): frühe Position (`early_pos`) →
  Position 400 m vor dem Ziel (`pos_before`, `fifth` als Fünftel des
  Feldes, 1 = vorne) → Ziel; `pos_gain` = Plätze gutgemacht ab 800 m.
- **`weg_med`**: Meter mehr (+) oder weniger (−) als der Median des
  Feldes, rund 2,4 m je Länge. Negativ heißt kürzerer, günstiger Trip —
  die Leistung nach unten relativieren.
- **Umgekehrt aufwerten:** Positiver `weg_med` zusammen mit großem
  `pos_gain` — von hinten gekommen, in der Geraden viele Plätze gutgemacht
  und dabei Umweg in Kauf genommen — ist mehr wert, als Platz und
  Rückstand zeigen. Ein Sieg oder knapper Platz unter diesen Umständen
  war vermutlich nicht am Limit.
- **Tempo des damaligen Rennens** über `pace_ratio` (frühe Phase ÷
  Schlussphase × 100; unter 100 = langsam angegangen, Sprintfinish; über
  100 = schnell angegangen). Wer in einem langsam angegangenen Rennen
  von hinten kam, hatte es gegen sich; wer in einem schnell angegangenen
  Rennen vorne durchhielt, auch. Beides wird aufgewertet. Den Gegenfall
  — vorne im Bummelrennen, hinten im Hetzrennen — nach unten relativieren.
- **Schlussabschnitt:** `fs` (Finishing Speed des Pferdes in %) gegen
  `fs_opt` (Optimum für Kurs, Distanz und Boden); `dl600_a` und
  `db200_a` (km/h gegenüber der Erwartung, klassenbereinigt, + =
  schneller). Ein Pferd, das wiederholt über der Erwartung beendet, aber
  nur knapp platziert war, hat Reserven, die das Ergebnis nicht zeigt —
  oft ein Hinweis auf eine zu kurze Distanz oder ein zu langsames
  Tempo. Deutlich unter dem Optimum heißt: Es ging am Ende die Luft aus.
- **Laufbehinderung.** Ein Kommentar wie *n'a pas eu les coudées
  franches* oder *n'a pu s'exprimer* entschuldigt eine Platzierung —
  aber genau das steht oft auch im Crible und ist dann eingepreist (B11).
- **Startbox damals:** `draw_stat` der Formzeile — war die Box auf
  dieser Konfiguration signifikant schlecht (`sig`), ist das eine
  Entschuldigung.
- **Klasse des Herkunftsrennens** über `cls_val_idx`, `cls_epr_idx` und
  `prize` (A3). Ein vierter Platz in einem 96.000-Euro-Rennen ist etwas
  anderes als einer in einem 19.000er.
- **Aber immer mit dem damaligen Gewicht gegenlesen.** Wer im großen
  Rennen nur 54 Kilo trug und heute Top-Weight schleppt, hat den
  Klassenvorteil teilweise wieder abgegeben.
- **ARR-Werte über Läufe hinweg vergleichen.** Der ARR eines Laufes
  (`arr_adj`, auf das heutige Gewicht bereinigt) lässt sich direkt
  gegen den eines anderen Starters stellen — die härteste Währung für
  den Querbezug in B10.

### B5 — Gegneraufwertung

Über `rivals[].next` (in der Claude-Version `rivals_nah[].next`: die
Gegner direkt davor und dahinter) und `rivals_stat` (alle wieder
gelaufenen Gegner) prüfen, ob die damaligen Gegner
seither ihre Form bestätigt haben. Das Urteil `verdict` ist
**marktrelativ**: „besser" heißt, der Gegner lief im nächsten Start
besser als sein Quotenrang, „schlechter" schlechter, „wie erwartet"
entsprechend. `rivals_stat` zählt das über alle wieder gelaufenen
Gegner (`ran`).

- Haben mindestens die Hälfte der wieder gelaufenen Gegner danach
  besser abgeschnitten als ihr Quotenrang, war das Rennen stark —
  **aufgewertet**.
- Am meisten Gewicht haben die Pferde, die direkt vor und hinter dem
  Starter einkamen: Sie definieren das Niveau seiner Leistung.
- Sind nur ein oder zwei Gegner wieder gelaufen, ist das eine
  Andeutung. Ist niemand wieder gelaufen, lautet der Befund: keine
  Information ableitbar — eine Lücke, kein Minuspunkt.

### B6 — Passung auf heute

- Handicapmarke im Zeitverlauf (`valeur` der Formzeilen) gegen heute
  (`rating`). Konstante Marke über viele Läufe heißt: kommt damit klar,
  geht aber nicht darüber hinaus. Marken-Vergleiche (hier und bei
  `hcp_mark`) laufen immer über die **offizielle Valeur** `rating`, nicht
  über das gewichtsbereinigte `rating_adj` — die Karte zeigt die Valeur
  dafür klein neben dem bereinigten Wert.
- **Die entscheidende Frage im Handicap: Wie steht das Pferd heute zu
  seiner letzten Sieg- oder Platzmarke?** `hcp_mark.kind` (`sieg` oder
  `platz`) sagt, worauf sich die Marke bezieht; `diff` = heute minus
  Marke, negativ ist günstig. Zweieinhalb Kilo unter der letzten
  platzierten Marke sind ein echter Vorteil; über der Marke anzutreten
  ist ein Nachteil, auch bei guter Form. Zwei Pferde mit ähnlicher Form
  trennen sich oft genau hier. In Rennen ohne Handicap gilt statt dessen
  die Klassenfrage aus A1.
- **Das Alter der Marke mitlesen** (`hcp_mark.date`). Anderthalb Kilo
  unter einer Siegmarke vom Vorjahr sind weit weniger wert als unter
  einer aus diesem Sommer — bei einem Neunjährigen mit einem Sieg aus 37
  Starts praktisch nichts.
- **Gewichtsaufschlag nach einem Sieg.** Ein frischer Sieger trägt mehr.
  Dann lautet die Frage: Ist über den Aufschlag hinaus noch Spielraum?
- **Erstes Handicap** (noch keine `hcp_mark`, Formzeilen aus Claimer,
  Conditions oder Qualifikation): Passt die erste Marke zu dem, was das
  Pferd gezeigt hat? Gewonnene Claimer und Qualifikationen mit klarem
  Abstand gegen eine moderate Marke sind ein Plus. Ein Pferd mit wenigen
  Starts kann darüber hinaus noch zulegen (B1).
- **Startbox.** `draw` und `draw_stat`, immer zusammen mit dem
  Laufstil.
  - Aussagekräftig ist sie nur, wenn `sig` gesetzt ist (mindestens zwei
    Standardfehler und `dev` mindestens 0,05).
  - Ohne Urteil gilt die Box als neutral. Eine Randbox (ganz innen oder
    ganz außen) darf dann nur als schwacher Hinweis passend zum Laufstil
    stehen, etwa ganz außen für einen Mittelfeldläufer.
- **Distanzbilanz** aus `pref.horse.distance` (Gruppen in 200-m-Schritten,
  Eintrag mit `today: true`). **Immer gegen die beste Distanzgruppe des
  Pferdes stellen**: 0 Siege, 1 Platz aus 5 über die heutige Distanz
  heißt nicht „kann die Distanz", wenn dasselbe Pferd über 1400–1600 m 2
  Siege und 5 Plätze aus 6 hat. Dann ist die heutige Distanz eine
  Unsicherheit — auch bei einem Favoriten.
- **Bodenbilanz** aus `pref.horse.going`, bei angenommenem Boden mit der
  Nachbargruppe (A2).
- **Bahnbilanz** aus `pref.horse.course`. Ein einziger Lauf auf der Bahn
  ist eine Andeutung, keine Bilanz.
- **Die Bilanzzeilen tragen ein A/E** (`ae`, Plätze gegen die aus den
  Endquoten erwartete Zahl): Es sagt, ob das Pferd unter dieser
  Bedingung **besser lief, als der Markt ihm zutraute**. Zwei Plätze aus
  fünf als Außenseiter sind mehr als zwei aus fünf als Favorit. Wo
  rohe Zahl und A/E auseinanderlaufen, gilt das A/E.

### B6a — Frische und Saisonbelastung

- **Abstand zum letzten Start** (`days`, Vorbehalt aus D). Bei
  Handicappern im Saisonbetrieb sind zwei bis fünf Wochen normal. Ab
  etwa acht bis neun Wochen kommt das Pferd **aus einer Pause** — ein
  Fragezeichen, weil die Form nicht frisch belegt ist und der Stall es
  vielleicht erst heranführt. Allein kein Ausschluss, zusammen mit einem
  zweiten Fragezeichen (Distanz, Belag, kalter Stall) aber gewichtig.
- **Starts in der laufenden Saison** (`career.d365.runs`, feldrelativ;
  Auslandsstarts fehlen). Wenige Starts heißt frischer, aber weniger
  Beleg. Zehn und mehr bis Herbst werfen die Frage auf, ob nach einem
  Sieg mit Aufschlag noch ein Schritt kommt. Bei ansonsten ähnlicher
  Einschätzung wird das **weniger gelaufene Pferd vorgezogen**.

### B7 — Trainer und Jockey

**Die A/E-Werte sind A/E Platz:** Plätze geteilt durch die aus den
Endquoten erwarteten Plätze (Marge herausgerechnet). 1,0 heißt „wie vom
Markt erwartet", ab 1,10 auffällig gut, bis 0,90 schwach; unter zehn
Starts (bei Vorlieben fünf) dünn. `ae_win` ist das Gegenstück auf Sieg —
wichtiger für die Siegwette, aber rauschiger.

**Ablauf:**
1. `ae.trainer.d365` und `ae.jockey.d365` als Grundniveau.
2. `d30` und `trend` für die aktuelle Form. `trend` ist `hot`/`cold` bei
   mindestens 0,25 Abstand zum Jahreswert, ab fünf Starts. **Unter etwa
   15 Starts in 30 Tagen zählt `d90`**, der Trend ist dann nur ein
   Hinweis (Beispiel: 0,71 aus 13 Starts, aber `d90` 1,14 ist kein
   kalter Stall).
3. Die Spezialisierungen:
   - `pref.trainer.course`, `.racetype`, `.age` (siehe `age_label`) und
     `.jockey`
   - `pref.jockey.course`, `.trainer` und `.horse`

   Ein Trainer kann in Handicaps stark sein, aber nicht mit
   Dreijährigen. Diese Unterscheidungen ernst nehmen, statt eine
   Gesamtquote zu lesen.

**Ob eine Spezialisierung trägt, sagt `dev`** an jeder Vorliebe von
Trainer, Jockey, Vater und Muttervater. Verglichen wird das A/E mit dem
derselben Person bzw. Linie aus ihren **übrigen** Läufen im selben
Zeitraum: Trainer und Jockey 2 Jahre, Vater und Muttervater die gesamte
Historie. Felder: `base` (A/E übrige Läufe), `ratio`, `z`
(Standardfehler), `rest` (übrige Läufe), `dir`. `sig: true` (in der
Karte ▲ / ▼) heißt: mindestens ×1,2 bzw. ×0,8, mindestens 2
Standardfehler und mindestens 20 übrige Läufe. Lesart:

- **Nur `sig` ist ein belastbares Argument.** Ein hohes A/E ohne `sig`
  (etwa 2 Siege aus 9 oder 0 aus 4 auf der Bahn) ist eine Andeutung und
  wird nicht angekreidet oder gefeiert.
- Ein ▲ auf dieser Bahn oder in dieser Rennart, das der Crible nicht
  nennt, ist ein *nicht erkanntes* Argument (B11). Ein ▼ beim
  Prognose-Favoriten ist ein unabhängiges Fragezeichen (B12).
- `pref.jockey.horse` ist nur ungefähr verglichen: Die Läufe auf dem
  Pferd zählen über die ganze Historie, die übrigen Läufe des Jockeys
  über 2 Jahre. Viele gemeinsame Ritte mit guter Quote zeigen ein
  eingespieltes Paar.

`epr_idx` (€/L+, 100 = Durchschnitt) zeigt das **Niveau** eines Stalls
oder Jockeys, nicht seine Form. Ein großer Stall mit hohem €/L+ in einem
kleinen Claimer ist ein Klassensignal. Ein Jockey mit hohem €/L+ auf
einem Außenseiter ist eine bewusste Buchung. Die Besitzerstatistik
(`ae.owner`) ist eine Randnotiz.

- **Trainerform wiegt umso schwerer, je kürzer die Prognose.** Bei
  einem 25:1-Pferd ist ein kalter Stall eine Randnotiz; beim
  Prognose-Favoriten ist er ein echtes Argument gegen die Position.
- Ein guter Jockey gleicht einen kalten Trainer nicht aus — er wird
  benannt, aber das Fragezeichen beim Stall bleibt.
- **Stallgefährten.**
  - Kommen mehrere vordere Prognose-Pferde aus demselben Stall, hängt
    ihre Einschätzung an derselben Trainerform.
  - Laufen mehrere Pferde eines Stalls, verrät die **Jockey-Buchung**
    die Stallpräferenz: Der stärkere Jockey (A/E, €/L+) sitzt meist auf
    dem Pferd, dem der Stall mehr zutraut.

### B8 — Abstammung auf die heutige Bedingung

Vater und Muttervater **getrennt** beurteilen, jeweils auf die heutige
Distanz und den heutigen Boden: `pref.sire.distance`, `pref.sire.going`,
`pref.dam_sire.distance`, `pref.dam_sire.going` (bei Zwei- und
Dreijährigen auch `.age`). Ein schwacher Vater kann durch einen
passenden Muttervater ausgeglichen werden.

Die **Neigung** einer Linie zu Distanz, Boden oder Alter ist das, was `dev` (B7) misst: ▲ heißt, die Nachkommen laufen unter dieser Bedingung deutlich und signifikant besser als unter den übrigen. Das ist die eigentliche Aussage „die Linie mag weichen Boden“. Ein hohes A/E ohne `sig` kann auch nur eine gute Linie insgesamt sein. Die Distanz der Vorlieben bleibt in 200-m-Gruppen (`dist_group`), anders als die ±100 m der Formzeilen-Kennzeichen (B3).

Die Gesamtstatistik der Linien steht in `ae.pedigree` für `sire`,
`dam_sire` und `cross` (Vater × Muttervater): A/E, `epr_idx`, die Zahl
der Nachkommen (`horses`) und **`max_val3_idx`** — der Ø der höchsten
Valeur, die die Nachkommen als Dreijährige erreichten, als Index. Das
ist das beste verfügbare Maß für die **Qualität** einer Linie, getrennt
von ihrer Distanz- und Bodenneigung. Der `cross` beruht fast immer auf
wenigen Pferden und ist eine Andeutung. Bei sehr wenigen Nachkommen die
dünne Datenlage explizit benennen.

**Bei einem erfahrenen Pferd schlägt die eigene Bilanz die
Abstammung.** Sagt die Abstammung „Turf kein Nachteil", das Pferd hat
aber auf PSF klar besser gelaufen, gilt, was das Pferd gezeigt hat. Die
Abstammung trägt vor allem bei wenig Starts und bei Bedingungen, unter
denen das Pferd noch nie gelaufen ist.

### B9 — Direkte und indirekte Duelle

**Direkt** (`duels`): frühere Begegnungen mit heutigen Gegnern, mit
Abstand (`diff_l`), Gewichtsunterschied damals (`w_then`) und heute
(`w_today`) und deren Verschiebung (`shift`). Die Karte rechnet daraus
**`exp_l`, den heute erwarteten Abstand** (Abstand damals minus
Verschiebung, 1 kg = 1 Länge; positiv = vor dem Gegner).
`duels_sum` fasst je Gegner das letzte Duell zusammen. **Duelle, die
älter als etwa sechs Monate sind, gelten als nicht repräsentativ** — die
Karte zeigt bis zu einem Jahr, also nach Datum filtern. Bei Dreijährigen
hat sich in einem halben Jahr zu viel verändert.

**Indirekt** (`indirect`): Vergleich über gemeinsame frühere Gegner —
nur Rennen der letzten 120 Tage, ±200 m, Boden innerhalb einer Stufe,
alle drei Pferde in der vorderen Feldhälfte. `exp_kg` / `exp_l` ist der
heute erwartete Unterschied, `n` die Zahl der Vergleiche. Indirekte
Duelle wiegen weniger als direkte; ein einzelner Vergleich über ein
gemeinsames Pferd ist eine Andeutung, drei übereinstimmende Vergleiche
sind ein Argument.

Ein Duell, das ein heutiges Außenseiterpferd vor einem
Prognose-Favoriten sieht, ist einer der typischen *nicht erkannten*
Angles (B11).

### B10 — Querbezug zwischen den Startern

Die Schlüsselläufe verschiedener Starter direkt gegeneinander stellen:
Klasse, Dotierung, ARR und wie das Rennen gelaufen ist. Erst dadurch
wird aus zwei isolierten vierten Plätzen eine Rangfolge.

**Messlatte vom Favoriten.** Beim ersten Pferd (meist dem
Prognose-Favoriten) aus seinem besten Lauf unter heutigen Bedingungen
TR (`tr_heute`) und ARR (`arr_adj`) notieren. Jeder folgende Schlüssellauf
wird daran gemessen, zusammen mit Distanz, Klasse und Gewicht.
Beispiel: Messlatte TR 105, ARR 32,9 über 1600 m. Ein Konkurrent mit
TR 84 und ARR 29,2 über 1400 m muss über die längere Strecke deutlich
zulegen.

**Laufende Rangfolge.** Der Querbezug passiert nicht erst am Ende,
sondern nach jedem Pferd: „vor den beiden Favoriten", „knapp hinter
Liseo". So entsteht während des Durchgangs eine eigene Reihenfolge, die
sich direkt gegen die Prognose-Reihenfolge stellen lässt. Wo die eigene
Reihenfolge ein Pferd vor einen Prognose-Favoriten setzt, ist der
Edge-Kandidat.

### B11 — Abgleich mit der Prognose: gesehen oder übersehen?

Mit eigenem Urteil zum Pferd werden Prognose-Text, Crible, Tipps und
Konsens jetzt systematisch abgeglichen, auch wenn sie zur Orientierung
schon gelesen wurden (Grundregeln). Drei Fragen:

1. **Liegt die eigene grobe Einschätzung über oder unter der
   Prognose-Chance?** Eine starke Abweichung ist ein Anlass, die eigene
   Beurteilung noch einmal zu prüfen, kein Beweis.
2. **Sind die eigenen Argumente öffentlich?** Jedes Argument für den
   Angle gegen Text und Crible halten:
   - *eingepreist* — Text oder Crible nennen genau dieses Argument
     (etwa „mit australischen Scheuklappen" oder „hat schon in dieser
     Gewichtszone gewonnen"); ebenso C/D/CD-Kennzeichen.
   - *teilweise* — das Pferd wird gelobt, aber aus einem anderen Grund.
   - *nicht erkannt* — niemand erwähnt das Argument. Typisch dafür sind
     Gegneraufwertung, Laufbild und Tempo des Herkunftsrennens,
     Sektionalwerte, Bias- und Tempopassung heute, eine Bilanz unter
     heutigen Bedingungen mit gutem A/E, die Marke unter der letzten
     Platzmarke, eine Ausrüstungsänderung mit guter Vorbilanz, ein
     Trainerwechsel oder ein Duell.
3. **Wie ist die Publikumslage** (P3)?

Die Leitfrage des Durchgangs ist, warum das Pferd besser abschneidet,
**als der Markt erwartet**. Ein Argument, das die Prognose schon
ausspricht, beantwortet diese Frage nicht mehr. Das Pferd kann trotzdem
eine Wette sein — dann aber nur, weil die eigene Gewichtung deutlich
stärker ist, und das muss im Fazit so stehen. Der wertvollere Angle ist
der, den niemand sieht.

Umgekehrt: Lobt der Crible ein Pferd mit einem Argument, das die eigene
Analyse widerlegt hat, ist das ein Hinweis auf ein **überschätztes**
Publikumspferd — relevant vor allem für den Prognose-Favoriten.
Typische Fälle:

- Der Crible stützt sich auf Form vom **anderen Belag** („battu de peu
  sur la PSF"), heute ist aber Turf und die Turf-Bilanz schwächer.
- Der Crible stützt sich auf einen Lauf über eine **andere Distanz**,
  und die heutige Distanz ist laut Bilanz nicht die beste.
- Der Crible erwähnt eine **Pause**, einen kalten Stall oder ein
  BF-Kennzeichen nicht.
- Der Crible lobt einen Sieg aus einem **Bummelrennen von vorne** oder
  aus einem Rennen, das laut B5 nicht aufgewertet ist.

Dieselbe Frage „eingepreist?" gilt also auch für die eigenen
**Gegenargumente**: Ein Fragezeichen, das die Prognose nicht anspricht,
ist beim Favoriten genauso wertvoll wie ein übersehenes Plus bei einem
Außenseiter.

### B12 — Fazit je Starter: Angle ja oder nein

Ein Satz, der die Argumente dafür und dagegen benennt, und dann die
Entscheidung: klarer Angle, kein klarer Angle, oder dagegen. Regeln
dazu:

- **Mindestschwelle.** Ein Pferd muss erst einen Ansatz zeigen, bevor
  es Aufmerksamkeit bekommt. Ein Elfter von zwölf mit achtzehn Längen
  Rückstand nach langer Pause wird abgehakt, nicht diskutiert.
- **Derselbe Faktor kann gegenteilig zu werten sein.** Ein
  Distanzrückgang ist ein Plus, wenn die Abstammung oder die
  Sektionalwerte ihn stützen, und ein Fragezeichen, wenn nicht.
  Faktoren werden nie mechanisch als gut oder schlecht abgelegt.
- **Passende Bedingungen sind noch kein Angle — aber viele zusammen
  können einer werden.** Wenn Distanz, Boden, Bahn, Startbox, Laufstil,
  Tempo, Bias sowie Trainer- und Jockeyform alle in dieselbe Richtung
  zeigen, ist das ein eigenständiges Argument (Laufstil und Tempo zählen
  dabei nur mit Beleg nach A4), auch ohne spektakuläre
  Formzeile — der schwächere Angle-Typ neben „der Markt hat einen Lauf
  übersehen".
- **Typischer übersehener Angle: Formtief erklärt, heute passt alles.**
  Die schwachen letzten Zeilen kamen unter falschen Bedingungen
  (Distanz, Boden) oder in klar stärkeren Rennen. Der letzte Lauf hat
  eine Entschuldigung (behindert, nicht frei gekommen). Heute passen
  Distanz, Boden und Ausrüstung laut Bilanz, und das Rennen ist deutlich
  leichter. Die Musique sieht schlecht aus, deshalb steht das Pferd
  hinten in der Prognose. Gegenprobe: Ist die Marke seit der letzten
  guten Form gesunken oder nur leicht gefallen?
  Beispiel: Ciccio Boy (Le Mans, 05.10.2026).
- **Auch bei einem guten Pferd gehört die Frage dazu, ob es heute
  gewinnen soll.** Schwache Trainerform, eine Trainer-Jockey-Kombination
  ohne Erfolge und eine Bahn, auf der der Stall nie auffällt, können
  darauf hindeuten, dass der Start Vorbereitung auf ein höher dotiertes
  Ziel ist. Das ist eine Lesart, keine Feststellung — aber sie darf ein
  Fazit tragen.

**Bei den vorderen Prognose-Pferden zusätzlich: Ist die Position
nachvollziehbar?** Hier wird nicht nach einem Angle gesucht, sondern
geprüft, ob die kurze cote probable trägt:

- **Fragezeichen zählen, und zwar unabhängige.** Pause, unsichere
  Distanz, Belagwechsel, kalter Stall, Boden nur angenommen bei klarer
  Bodenabhängigkeit sind voneinander unabhängig. Eines davon hat fast
  jedes Pferd. **Zwei unabhängige Fragezeichen** beim Favoriten reichen
  für „Favoritenposition nicht nachvollziehbar" — mit den Gründen. Das
  spricht für die Pferde dahinter und gibt dem Favoriten in C1 einen
  negativen Edge.
- **Sieglos nach vielen Starts.** Ein Pferd mit 0 Siegen aus 15 Starts
  auf Platz zwei der Prognose ist ein Fragezeichen für die Siegwette,
  auch bei guter Platzform. Ein `ae_win` deutlich unter dem Platz-A/E
  bestätigt das Muster.
- **Handicapmarke im Verhältnis zum Leistungsvermögen.** Läuft ein
  Pferd ordentlich, kommt aber über eine bestimmte Marke nicht hinaus
  („ganz oben scheint etwas zu fehlen"), ist es ein Platzpferd, kein
  Siegkandidat — es sei denn, das heutige Rennen ist deutlich leichter.

### B13 — Gegenprobe über die Ratings

**Frühestens am Ende der Beurteilung eines Pferdes, nie vorher.** Ein
kurzer Blick auf die Ratings darf das Fazit zum einzelnen Pferd
abschließen — etwa „TR und ARR gut, trotzdem fehlt oben etwas". Der
Vergleich über das ganze Feld kommt am Ende des Durchgangs. In beiden
Fällen dienen die Ratings nicht dazu, Kandidaten zu finden, sondern die
gefundenen zu prüfen.

Alle sind auf das **heutige Gewicht** umgerechnet und tragen einen
Rang im Feld:

- **TR** (`tr.heute`): Zeit-Rating nach Timeform-Art mit
  Finishing-Speed-Upgrade, gewichteter Ø der letzten Läufe nach Distanz-
  und Bodenähnlichkeit; `best`, `last`, Streuung `sd`. Gedeckelte Läufe
  (`tr_cap`) zählen nicht.
- **ARR** (`arr.adj`): Leistung im Rennen gemessen an den Pferden im
  vorderen Drittel des Einlaufs, gewichteter Ø.
- **RTR** (`rtr.adj`): laufendes Elo-artiges Rating nach dem letzten
  Rennen.
- **Valeur bereinigt** (`rating_adj` = Valeur − Gewicht + 55, Rang
  `rating_rank`):
  - **Im Handicap** ist sie flach, weil das Gewicht die Valeur
    ausgleicht. Nur Abweichungen zählen (Erlaubnis, Gewichtsgrenze).
  - **In Conditions-, Listed- und Gruppenrennen** ist sie das direkte
    Klassenmaß (A1).
- Ergänzend **ΔL600 A / ΔB200 A** (`summary.dl600_a`, `summary.db200_a`
  mit Rang): Schlussvermögen gegenüber der Erwartung — ein Maß für den
  Speed im Finish, unabhängig vom Ergebnis.

Regeln:

- Stehen die Kandidaten aus dem Durchgang bei TR, ARR und RTR im oberen
  Bereich, ist die Einschätzung bestätigt.
- Steht ein Pferd, das im Durchgang gut aussah, bei den Ratings hinten,
  ist das ein Grund zur Abwertung — dann trägt die Beurteilung
  vermutlich zu weit.
- Große Streuung (`sd`) heißt: Der Schnitt verdeckt ein Pferd, das je
  nach Bedingung sehr unterschiedlich läuft. Dann zählt der Wert unter
  heutigen Bedingungen, nicht der Ø.
- Bei Arabern und Anglo-Arabern nur innerhalb des Feldes vergleichen
  (A1).

Die Ratings bekommen bewusst keinen Platz weiter vorne im Raster. Als
Gegenprobe am Schluss sind sie wertvoll, weil sie unabhängig von der
eigenen Lesart entstanden sind.

## Abschnitt B-2J — Variante für Zweijährige und Debütanten

Bei Zweijährigen mit null bis drei Starts ersetzt dieses Raster die
Punkte B1, B3, B6 (Marke) und B9 weitgehend. Reihenfolge bleibt nach
Prognose-Rang. Gerade bei Debütanten stützt sich die Prognose oft nur auf
Stall und Abstammung — dieselben Informationen, die auch hier vorliegen.
Ein eigenes Argument darüber hinaus ist deshalb selten; das im Fazit
ehrlich sagen.

- **2J-1 — Jeden Start lesen.** Mit so wenig Material wird jeder Lauf
  gewürdigt, auch ein weit geschlagener. Ein Vierter von zwölf mit zehn
  Längen Rückstand kann positiv sein, wenn dahinter noch ein halbes Feld
  lag. Die Frage ist nicht „wie weit geschlagen?", sondern „wen hat er
  hinter sich gelassen, und ist es ein Anfang?". Laufbild und
  Sektionalwerte (B4) sind hier besonders wertvoll: Ein Debütant, der
  unerfahren hinten lag und im Finish über der Erwartung lief, hat mehr
  gezeigt als sein Platz.
- **2J-2 — Dotierung und Quote des Debütrennens als Stallerwartung.**
  Hohe Dotierung heißt: Der Stall hat das Pferd bewusst in ein gutes
  Rennen gestellt. Eine sehr hohe Quote im selben Rennen heißt: Der
  Markt, oft auch der Stall, hat nicht viel erwartet. Die Kombination
  wird benannt, nicht aufgelöst.
- **2J-3 — Trainer mit Zweijährigen.** `pref.trainer.age` (bei
  `age_label` „2j") gezielt prüfen, nicht die Gesamtform. Ein Stall mit
  vielen Zweijährigen-Siegern ist ein Plus, einer mit 2 aus 33 ein
  Fragezeichen. Dazu die Bahnstärke des Stalls.
- **2J-4 — Abstammung auf Frühreife, Qualität und Distanz.** Hier trägt
  die Abstammung am meisten. `pref.sire.age` zeigt, wie die Linie mit
  Zweijährigen läuft; `ae.pedigree.sire.max_val3_idx`, wie gut ihre
  Nachkommen werden. 1800 oder 2000 m sind für Zweijährige weit — das
  muss von Vater- oder Muttervaterseite (`pref.*.distance`) getragen
  werden. Die Mutterseite kann eine schwache Vaterlinie aufwerten.
- **2J-5 — Debütanten.** Es bleiben Abstammung, Trainer mit
  Zweijährigen, Trainer-Jockey-Kombination und Bahnstatistik. Kein
  Laufstil, also kein Platz im Tempobild (`pace.unknown`). Mehr ist
  nicht seriös zu sagen.
- **2J-6 — Abstand zum Favoriten aus gemeinsamem Rennen.** Sind zwei
  heutige Starter schon gegeneinander gelaufen, ist der Abstand eines
  der stärksten Argumente (B9, auch indirekt). Anderthalb Längen hinter
  dem heutigen Favoriten, zu einer deutlich höheren Quote heute, ist ein
  Ansatz.
- **2J-7 — Distanzschritt.** Ein Schritt nach oben kann bei Zweijährigen
  ausdrücklich positiv sein, wenn die Abstammung ihn trägt. Stützt sie
  ihn nicht, bleibt ein Fragezeichen.
- **2J-8 — Mindestschwelle.** Ein Pferd mit einem klar geschlagenen
  Start ohne weiteres Signal wird nicht weiter verfolgt — erst der zweite
  Start zeigt, ob etwas zu erwarten ist.

**Grundhaltung:** Zweijährigen-Rennen sind spekulativer als Handicaps.
Kandidaten dürfen genannt werden, aber das Fazit benennt den spekulativen
Charakter ausdrücklich, statt Sicherheit zu suggerieren.

## Abschnitt C — Empfehlung

Aus den Startern mit bejahtem Angle entsteht eine kurze Kandidatenliste,
meist zwei bis drei Pferde. Der Prognose-Favorit (Rang 1) kommt immer
dazu — auch wenn seine Argumente als eingepreist gelten. Er ist der
Maßstab, gegen den die Kandidaten bewertet werden.

### C1 — Mindestquote je Kandidat (das Hauptergebnis)

Der letzte Schritt beantwortet die Frage des Nutzers: **Bis zu welcher
Quote ist dieses Pferd noch interessant?** Der Nutzer hält diese Zahl
später gegen seinen Festkurs. Liegt der Festkurs darüber, ist es eine
Wette; liegt er darunter, nicht.

1. **Siegchance als Spanne schätzen**, aus der Analyse heraus — zum
   Beispiel 15–20 %. Ein spekulativer Fall (Zweijährige, Debütanten,
   dünne Datenlage, Lücken aus D, ein Tempo-Angle in einem Feld wenig
   gelaufener Pferde nach A4) bekommt eine breitere und vorsichtigere
   Spanne.
2. **Faire Quote** aus der Mitte der Spanne: 1 / Chance. Bei 17,5 % also
   etwa 5,7.
3. **Mindestquote** aus dem unteren Ende: bei 15 % also 6,7. Das untere
   Ende ist der eingebaute Sicherheitsabstand — wer nur zur fairen Quote
   wettet, gewinnt langfristig nichts, auch wenn die Einschätzung
   stimmt. Auf einen gängigen Festkurs-Schritt aufrunden, nicht abrunden.
4. **Gegenprobe über das Feld.** Die geschätzten Chancen von Favorit und
   Kandidaten müssen zusammen plausibel bleiben und dem Rest des Feldes
   Raum lassen. Kommen drei Pferde zusammen auf 80 %, ist die Schätzung
   zu großzügig.
5. **Edge gegen die Prognose.** Edge = eigene Chance (Mitte der Spanne) /
   Prognose-Chance (P2, Potenzmethode) − 1. Bei 17,5 % gegen 10 % also
   +75 %. Der Edge sagt, wie weit die eigene Sicht von der Wahrnehmung
   der Öffentlichkeit abweicht — nicht, ob der Festkurs am Ende passt.
   - Ein Edge unter etwa +20 % liegt innerhalb der eigenen
     Schätzunsicherheit und trägt allein keine Kandidatur.
   - Ein großer Edge, der fast nur auf *eingepreisten* Argumenten steht,
     ist verdächtig: Die eigene Analyse hat dieselben Gründe gefunden wie
     die Prognose, sie aber stärker gewichtet. Ehrlich gegenlesen. Ein
     großer Edge aus *nicht erkannten* Argumenten ist der eigentliche
     Fund.
   - Ein deutlich negativer Edge beim Prognose-Favoriten wird benannt —
     er ist dann eher ein Pferd, gegen das man spielt.

Die Mindestquote wird **aus der eigenen Einschätzung abgeleitet, nicht
aus der Prognose**. Liegt die eigene faire Quote weit unter der cote
probable (eigene 4,0 gegen Prognose 15/1), ist das entweder der Fund des
Tages oder eine Überschätzung — die Argumente noch einmal gegenlesen und
das Ergebnis benennen.

**Bedingte Mindestquote.** Hängt der Angle am angenommenen Boden (A2),
am erwarteten Tempo oder an einer Lücke (D), wird die Bedingung zur
Mindestquote geschrieben („gilt bei Bon/Bon souple"). Ändert sich die
Bedingung, fällt die Zahl.

Der Favorit bekommt ebenfalls eine Mindestquote. Er ist nicht
automatisch ausgeschlossen: Liegt der Festkurs über seiner Mindestquote,
ist er eine Option wie jede andere. Gibt es zu einem Pferd keinen Angle,
wird keine Mindestquote genannt — eine Zahl ohne Begründung lädt zu
einer Wette ohne Grund ein.

**Rennen dürfen als schwach befunden werden.** Es ist ein legitimes und
wichtiges Ergebnis, dass ein Rennen keine klaren Angles hergibt —
typisch für Felder, in denen fast alle Pferde exposed sind, und für
Gruppenrennen mit treffsicherer Prognose. Dann wird das benannt, statt
einen Kandidaten zu konstruieren, mit Sicherheitsstufe auch im Vergleich
zu anderen Rennen des Tages.

**Erwartete Kursrichtung aus der Publikumslage — als Hinweis zum
Zeitpunkt, nicht als Value-Urteil.** Ein Publikumspferd (P3) wird bis
zum Start eher kürzer; liegt der Festkurs jetzt über der Mindestquote,
spricht das dafür, ihn früh zu nehmen. Ein übersehenes Pferd hat es
nicht eilig. Liegt die Mindestquote eines Publikumspferdes schon über
seiner cote probable, ist realistisch kaum ein passender Festkurs zu
erwarten; das so sagen.

### C2 — Ausgabe

Pro Rennen, kurz und in dieser Form:

- Kopfzeile: Rennen, Startzeit, Rennart, Boden (mit „angenommen", falls
  so), Prognose-Profil in wenigen Worten (etwa „klarer Favorit 2/1"
  oder „offen, sechs Pferde unter 10/1").
- Zwei bis drei Sätze zur Renncharakteristik und zum Ergebnis des
  Durchgangs.
- Tabelle der Kandidaten plus Favorit:

| Pferd | Angle in einem Satz | eingepreist? | Prognose (cote / Chance) | Siegchance | Edge | faire Quote | **Mindestquote** | Sicherheit |
|---|---|---|---|---|---|---|---|---|

  „eingepreist?" ist *ja*, *teilweise* oder *nein* aus B11, bei Bedarf
  mit Publikumslage (etwa „nein, übersehen"). Die Mindestquote ist das
  Ergebnis, mit Bedingung, falls eine gilt; Prognose und Edge sind die
  Begründung.
- Ist ein Rennen schwach: kein Angle, keine Mindestquote — mit einem Satz
  Begründung.

Bereits gelaufene oder laufende Rennen stehen nur als eine Zeile.

Am Ende des Renntags eine Übersicht aller Mindestquoten über alle
Rennen mit Edge, „eingepreist?" und Bedingung, sortiert nach
Sicherheitsstufe, damit der Nutzer sie direkt gegen die Festkurse seines
Buchmachers halten kann.

## Arbeitsweise im Gespräch

**Bevorzugt: die Claude-Version `racecard_JJJJMMTT_claude.json`.** Sie
enthält **alle Daten der Karte**, auch solche, die dieses Raster nicht
nutzt. Unterschiede zu `DATA`:

- **Weggelassen sind nur:**
  - Trikots und `odds` / `odds_morning`
  - je Formzeile die volle Gegnerliste; dafür gibt es `rivals_nah` (je
    zwei Gegner direkt davor und dahinter, mit nächstem Start) und
    `rivals_stat` (B5)
  - die Zwischenwerte der Berechnung (die Ergebnisse wie `dl600_a`,
    `tr_heute`, `cls_*_idx` bleiben)
- **Starter** stehen in Prognose-Reihenfolge. Nichtstarter stehen
  getrennt in `nichtstarter`, ihre Nummern in `nr`.
- **Gelaufene Rennen** haben `offen: false`.
- **Vorgerechnet:**
  - `vorgerechnet` je Rennen: `marge`, `reihenfolge`, `bias_rel`
  - je Starter: `p_prog` (P2) und `luecke` (D)

Diese Werte direkt übernehmen, nicht neu rechnen:

```python
import json
DATA = json.load(open(pfad, encoding="utf-8"))
offen = {rid: r for rid, r in DATA["races"].items() if r["offen"]}
for rid, r in offen.items():
    v = r["vorgerechnet"]                 # marge, reihenfolge, bias_rel
    for x in r["runners"]:                # schon in Prognose-Reihenfolge
        p, luecke = x["p_prog"], x["luecke"]
        alte_zeilen = [f for f in x["form_lines"] if f.get("extra")]
# Edge je Kandidat: p_eigen / x["p_prog"] - 1
```

Für ein einzelnes Rennen reicht `DATA["races"][rid]`. Den Block des
Rennens ausgeben und lesen, statt die ganze Datei zu durchsuchen.

**Rückfall: nur die HTML-Karte.** Sie hat ein eingebettetes
`const DATA = {...}` (mehrere MB). Mit Python parsen, nicht als Text
lesen, und `odds` / `odds_morning` nicht anfassen. Die vorgerechneten
Werte fehlen dort; sie werden selbst gerechnet:
- Nichtstarter (`nr: true`) streichen.
- `p_prog`: Potenzmethode wie in P2.
- `marge`: Σ 1/`cote_dec`.
- `bias_rel`: `bias.bias` − `bias_all.bias`.
- `luecke`: `starts` − `career.all.runs`.

```python
import json
s = open(pfad, encoding="utf-8").read()
i = s.index("const DATA =") + len("const DATA =")
DATA, _ = json.JSONDecoder().raw_decode(s[i:].lstrip())

def potenz_normierung(q):                 # q = {no: 1/cote_dec}; Σ q^k = 1
    lo, hi = 0.2, 6.0
    for _ in range(80):
        k = (lo + hi) / 2
        lo, hi = (k, hi) if sum(v ** k for v in q.values()) > 1 else (lo, k)
    return {no: v ** k for no, v in q.items()}
```

## Anhang — Beispiel aus der Praxis (Argentan, 01.10.2026, Rennen 5)

Prix Elisabeth Mussat, Handicap 4j+, 1900 m, guter Boden, elf Starter.
Prognose: Jonin (3) 3/1, Aurora Borealis (8) 5/1, Maizières (5) und
Liseo (4) je 8/1. Beide Favoriten aus demselben Stall, Trainer d30 kalt.
Der Durchgang des Nutzers, verkürzt:

- **Jonin (3), Favorit:** zuletzt Zweiter, eine halbe Länge, zu 5:1 —
  gut gelaufen. Aber: heute 300 m weiter (1600 → 1900), Bilanz über
  1800–2000 m 0/1/5 gegen 2/5/6 über 1400–1600 m; 65 Tage Pause; Stall
  kalt, auf der Bahn ohne Erfolg, in Handicaps nur Durchschnitt. Zwei
  unabhängige Fragezeichen plus kalter Stall → Favoritenposition nicht
  nachvollziehbar. Der Crible nennt keines davon.
- **Aurora Borealis (8):** sieglos nach 15 Starts. Die gute Form der
  letzten vier Läufe kam komplett auf PSF, Turf-Bilanz schwächer;
  bisherige Läufe eher über kürzere Wege. Erster Jahresstart auf Gras
  verziehen, Marke seither konstant. Abstammung sieht keinen
  Turf-Nachteil, aber die eigene Bilanz zählt. Der Crible stützt sich auf
  die PSF-Form → eher überschätzt.
- **Liseo (4):** zuletzt Fünfter von 13 in Saint-Cloud, 2000 m, ähnlicher
  Boden, *fini courageusement*, Rennen nicht aufgewertet. Distanz passt
  (2 Siege, 5 Plätze), auf der Bahn einmal gelaufen und platziert,
  Ausrüstung unverändert, Jockey in Form, Trainer kalt, Kombination gut,
  heute leichteres Rennen. Marke um 31, oben scheint etwas zu fehlen.
  Eingeordnet **vor beiden Favoriten** — interessantester Kandidat.
- **Maizières (5):** 35 Starts, letzter Sieg von 35,5 (2024, also alt).
  Sieg am 16.08. in Deauville über 2000 m von hinten, zehn Plätze in der
  Geraden gutgemacht, Umweg in Kauf genommen → aufwerten; Rennen leicht
  aufgewertet. Danach Fünfter auf PSF. 13 Starts in dieser Saison und
  Aufschlag nach dem Sieg — kommt noch ein Schritt? Crible lobt sie.
  Eingeordnet knapp **hinter Liseo**, weil weniger belastet besser ist.

Die Muster daraus stehen in B0, B2, B3, B4, B5, B6, B6a, B7, B8, B10,
B11 und B12.
