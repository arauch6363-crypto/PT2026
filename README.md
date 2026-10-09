# PT2026 – Tracking-Daten französischer Flachrennen

Sammelt französische **Flachrennen** (bereits gelaufen) aus dem PMU-Programm und
sucht dazu die Tracking-PDFs von France Galop.

* **Code** (dieses Repository): die `.py`-Dateien.
* **Daten und Workflow**: Google Drive. Dort liegt das Notebook
  `tracking_workflow.ipynb`, das in Google Colab ausgeführt wird und sich den
  Code aus diesem Repository holt. Alle erzeugten Dateien (PDFs, Parquet,
  Fortschritt, Bahncodes) werden ebenfalls in Drive abgelegt.

## Ablauf

```
PMU-Programm  ──►  französische Flachrennen, die schon gelaufen sind
                   (Trab, Hindernis, Ausland und abgesagte Rennen fallen raus)
      │
      ├──►  Rennen + Starter je Rennen            →  pmu_races / pmu_runners
      │
      └──►  je Rennen: gibt es ein Tracking-PDF?  →  tracking_status
                       ja  →  PDF auswerten       →  tracking_races / _runners /
                                                     _sections / _leader
```

Das PMU-Programm ist die Grundgesamtheit: jedes gelaufene Flachrennen bekommt
eine Zeile in `tracking_status` – mit oder ohne Tracking. So lässt sich jederzeit
beantworten, wie vollständig die Tracking-Abdeckung ist.

## Warum der Aufwand bei den Bahnen?

Tracking ist eine Eigenschaft von **Renntag und Rennen**, nicht von der Bahn:

* Eine Bahn kann heute Tracking haben und am nächsten Renntag nicht. Deshalb
  wird nirgends gespeichert „Bahn X hat kein Tracking“. Jedes Rennen wird
  einzeln geprüft, und jeder Renntag von Neuem.
* Eine Bahn trägt oft Flach- **und** Hindernisrennen am selben Tag aus. Ein
  fehlendes PDF für ein Rennen sagt deshalb nichts über die übrigen Rennen
  desselben Tages aus.
* Schlüssel der Codetabelle ist der **PMU-Bahncode**, nicht der Name: das Programm
  nennt dieselbe Bahn je nach Feld `HIPPODROME DE TOULOUSE LA CEPIERE` oder
  `LA CEPIERE`. Namen werden zusätzlich vereinheitlicht (`pmu.norm`, entfernt auch
  den Vorsatz „Hippodrome de"), und ohne PMU-Code wird nur bei exaktem Namen
  zugeordnet – `DEAUVILLE CLAIREFONTAINE` ist eine andere Bahn als `DEAUVILLE`.
* **Der France-Galop-Code ist der PMU-Bahncode.** In allen bisher bestätigten
  Fällen gilt das ohne Ausnahme – auch dort, wo er sich aus dem Namen nicht
  ableiten lässt: `NANTES` = `PET` (Le Petit Port), `SAINT MALO` = `S-M`,
  `TOULOUSE LA CEPIERE` = `CEP`. Er wird deshalb unverändert übernommen,
  einschließlich Sonderzeichen, und an **jedem** Renntag neu probiert.
* Nur wenn der PMU-Code nichts liefert, werden Kandidaten aus dem Namen
  geraten. Ein geratener Treffer zählt aber nur, wenn der Bahnname im PDF-Kopf
  dazu passt – sonst würde `CHATEAUBRIANT` den Code `CHA` von `CHANTILLY` erben.
  Nur dieses Raten unterliegt einer Sperre (`ERSTE_VERSUCHE`,
  `WIEDER_NACH_TAGEN`); der PMU-Code selbst wird nie ausgesetzt.
* France Galop veröffentlicht PDFs teils verspätet. Renntage der letzten
  `nachzuegler_tage` Tage werden bei jedem Lauf erneut nach den noch fehlenden
  PDFs gefragt.
* Wird ein Bahncode erst später gefunden, haben früher verarbeitete Tage Lücken.
  Jeder Lauf prüft deshalb am Ende, für welche erledigten Tage inzwischen ein
  passender Code bekannt ist, und trägt diese Tage nach.

## Dateien

| Datei | Inhalt |
|---|---|
| `pmu.py` | PMU-Programm: Rennen, Starter, Filter (Frankreich / Flach / gelaufen) |
| `france_galop.py` | Bahncodes, PDF-Suche und -Download, Gegenprüfung des Bahnnamens |
| `parse_tracking.py` | Tracking-PDF → Tabellen (Zwischenzeiten, Abschnitte, Kennzahlen) |
| `pipeline.py` | Tagesablauf, Fortschritt, Parquet-Ausgabe, Auswertungshilfen |
| `racecard.py` | Interaktive Race Card für die heutigen Rennen (HTML) |
| `tempo_delta.py` | ΔL600 A / ΔB200 A: Schlusstempo gegen die Erwartung, verglichen innerhalb Tag × Kurs × Going, mit Klassenkorrektur |
| `pmu_basis.py` | Wissensbasis aus der PMU-Schnittstelle: Rennen (mit Siegerzeit, Kommentar), Starter (mit Kommentar, Zeit), Dividenden |
| `standardzeiten.py` | Siegerzeiten aus dem PMU-Programm über lange Historie sammeln, Standardzeiten je Konfiguration des Tages |
| `timeform_ratings.py` | TR: Zeit-Rating nach Timeform-Art (Standardzeiten, Going Allowance) mit Finishing-Speed-Upgrade, Backtest |
| `rtr_arr.py` | Ratings aus PT_Vorarbeiten: RTR (Elo-artiges Rating nach dem Rennen) und ARR (Leistung im Rennen) |
| `tipp_auswertung.py` | Claude-Tipps (Ausgabe des Skills) gegen die Ergebnisse: Treffsicherheit, Stufen, Angle-Typen, Wett-Ergebnis |
| `hypothesen_backtest.py` | Hypothesen H1–H5 (Rennverlauf, Überreaktion, Handicap-Erhöhung, Tempo × Stil, Presse-Konsens) per A/E und bedingtem Logit |
| `regel_backtest.py` | Regeln des Skills gegen die Datenbank prüfen: A/E gegen den Markt (Endquote) je Regel |
| `racecard_template.html` | Layout der Race Card; die Daten werden als JSON eingesetzt |
| `selftest.py` | Selbsttest ohne Internet (`python selftest.py`) |

## Ausgabe in Drive

```
<ORDNER>/
  pdfs/                     heruntergeladene Tracking-PDFs
  parquet/<tabelle>/<JJJJMMTT>.parquet
        pmu_races, pmu_runners,
        tracking_status,                 ← eine Zeile je gelaufenem Flachrennen
        tracking_races, tracking_runners, tracking_sections,
        tracking_leader, tracking_obstacles, fehler
  track_codes.csv           gelernte Bahncodes
  fortschritt.json          erledigte Tage
```

`race_id` (z. B. `20260919R3C5` = Datum, Reunion, Course) ist in allen Tabellen
gleich, PMU- und Tracking-Daten lassen sich darüber direkt verbinden.

## Ohne Colab benutzen

```bash
pip install -r requirements.txt
python -c "
from pathlib import Path
import pipeline as tp
base = Path('daten')
tp.run('2022-01-01', base=base, pdf_dir=base/'pdfs', max_tage=5)
"
```

## Tipp-Auswertung (Skill gegen die Ergebnisse)

Die Ausgabe von Claude je Renntag (Markdown mit dem Protokoll-Block ```json {"tipps": [...]}``` am Ende, Skill C2) in
`<BASE>/tipps/` legen; ältere Dateien ohne Block werden aus den Tabellen gelesen (ohne Angle-Typen).

```python
import tipp_auswertung as ta
erg = ta.run(BASE)        # Notebook Abschnitt 4
```

Verbindet die Tipps mit Einlauf und Endquote (`pmu_runners`), Sieg-Dividende (`pmu_dividends`) und Prognose-Chance
(`racecards/racecard_JJJJMMTT_claude.json`); das Ergebnis eines Renntags liegt ab dem Folgetag vor. Laufendes Protokoll
`auswertung/tipps_protokoll.parquet` (+ .csv). Bericht: Log-Loss/Brier Claude gegen Prognose, Siege/Plätze gegen die
Erwartung je Stufe, je Angle-Typ (Kandidat/Abwertung), je Prognose-Rang und Rennart, Wett-Ergebnis der Kandidaten
(alle bzw. nur bei Endquote ≥ Mindestquote). Skill-Änderungen erst, wenn ein Muster über rund 100 Kandidaten hält
oder der Regel-Backtest es bestätigt.

## Hypothesen-Backtest

```python
import hypothesen_backtest as hb
erg = hb.run(BASE)        # oder hb.run(BASE, hist=hist)
```

Je Hypothese A/E-Gruppen gegen die Endquote und ein bedingtes Logit je Rennen (P(Sieg) ∝ exp(β·ln p_mkt + γ·x)): γ > 0
= zu wenig gewettet. H1 Rennverlauf gegen das Pferd (≤ 60 Tage, Tracking, nicht ausgeritten; abgestuft gegen Pech im
Kommentar), H2 Überreaktion auf das Vorrennen (Marktchance, geschlagene Favoriten, Überraschungssieger; zusammen mit H1),
H3 Handicap-Erhöhung nach Sieg (Stufen 0–1,5/2–3,5/≥ 4; ARR des Siegrennens gegen neue Marke, Dreijährige), H4 Führende ×
erwartetes Tempo × Frontvorteil der Bahn, H5 Presse-Konsens nur vorwärts aus `racecards/*_claude.json`. H1/H4 im Testteil
(Norm, Pace-Kalibrierung, Bias auf der ersten Hälfte gelernt). CSV nach `auswertung/hypothesen_*_JJJJMMTT.csv`.

## Regel-Backtest (Skill gegen die Datenbank)

```python
import regel_backtest as rb
erg = rb.run(BASE)        # Tabelle drucken, CSV nach <BASE>/auswertung/regel_backtest_JJJJMMTT.csv
```

Je Regel des Skills (Wallach im Claimer, Exposure, Pause, Klassenabstieg, Tempo/Bias, Startbox, Laufbild, Wechsel,
Favorit mit Fragezeichen, Ratings; Belagwechsel Gras ↔ PSF mit Formübertragung und Vorlieben von Pferd, Vater und
Muttervater; Rennverlauf des letzten Laufs: mit oder gegen den Verlauf) und ihren Vergleichsgruppen: Starter, Siege, erwartete Siege nach der Endquote,
A/E Sieg mit z-Wert, A/E Platz und ROI. Merkmale nur aus früheren Läufen; Box, Bias und Linienqualität werden auf der
ersten Hälfte der Tage gelernt und auf der zweiten geprüft („Test“). Rennverlauf je Rennen = Ø frühe Position der ersten drei − Ø des Feldes (negativ = vorne gewonnen),
gegen die Norm der Bahn/Distanz; die 25 % extremsten Rennen gelten als Vorne- bzw. Hinten-Rennen, ab 8 Startern. Gruppen unter 50 Startern sind als `duenn` markiert.

## Wissensbasis aus der PMU-Schnittstelle

```python
import pmu_basis as pb
pb.run(BASE, "2019-01-01", max_tage=100)   # in Etappen, erneut aufrufen setzt fort
pb.abdeckung(BASE)                          # je Monat: Rennen, Starter, Anteil mit Zeit, Kommentar, Dividenden
```

Je Tag (französische, gelaufene Flachrennen) eine Datei in `parquet/pmu_races`, `parquet/pmu_runners` und neu
`parquet/pmu_dividends`. Vorhandene Tagesdateien werden überschrieben, fehlende Ordner angelegt. Zusätzlich zu den
bisherigen Spalten: Siegerzeit `race_time_s`, Piste, Parcours, Rennkommentar und alle einfachen Felder der Rennseite
(`c_…`); je Starter der Kommentar nach dem Rennen (`comment`, fehlt er bei Client 61, wird ein anderer Client
gefragt), die Zeit `time_s` (von PMU, sonst Siegerzeit + Längen, `time_est = True`) und alle einfachen Felder (`p_…`);
Dividenden aus `rapports-definitifs` je Wette und Kombination. Der Client, der zuletzt Kommentare geliefert hat, wird
für die Starterliste zuerst gefragt (rund 3 statt 5 Anfragen je Rennen), Pause 0,2 s. Fortschritt in `pmu_basis_fortschritt.json`,
Abbruch nach 3 stummen Tagen. Die tägliche Pipeline behält diese Zusatzspalten beim erneuten Schreiben eines Tages.

## Standardzeiten je Konfiguration

```python
import standardzeiten as sz
sz.run(BASE, "2019-01-01", max_tage=200)   # in Etappen: je Aufruf höchstens 200 Tage, erneut aufrufen
std = sz.laden_standards(BASE)              # <BASE>/standardzeiten/standards.parquet (auch .csv)
sz.standard_fuer(std, "CHANTILLY", 1600, piste="GAZON", parcours="Grande piste")
```

Eine Standardzeit gilt für die **Konfiguration des Tages**: Bahn, Distanz, Piste (Gras/PSF), Parcours
(z. B. Grande piste, Piste ronde, Ligne droite) und Corde. Gesammelt wird je Tag das PMU-Programm
(französische, gelaufene Flachrennen) mit der Siegerzeit `dureeCourse` (Einheit wird am Tempo erkannt; fehlt sie,
einmal die Rennseite), Boden, Preisgeld und Altersklasse – Ablage in `<BASE>/standardzeiten/rennen/<JJJJMM>.parquet`,
erledigte Tage in `fortschritt.json`. Antwortet PMU an 3 Tagen in Folge nicht, bricht die Sammlung ab.

Berechnung: Siegerzeit in s/km auf eine Referenzklasse umgerechnet (β aus Altersklasse und log. Preisgeld, innerhalb
Tag × Bahn × Boden), dann abwechselnd per Median Standardzeit je Konfiguration und Going Allowance je
Tag × Bahn × Boden. Nullpunkt der Allowance je Bahn und Belag – Gras: guter Boden (Bon, Bon souple, Bon léger),
PSF: eigener Median –, die Standardzeit gilt also für guten Boden. Konfigurationen mit wenigen Rennen werden zur
Standardzeit derselben Bahn und Distanz gezogen (n / (n + 5)); `belastbar` ab 5 Rennen. Dazu
`going_allowances.parquet` je Renntag. Grundlage sind die eigene Sammlung und – vorrangig – `pmu_races` aus
pmu_basis (hippodrome, distance_m, track_type, parcours_norm, corde -> race_time_s).

**Verwendung in TR:** `racecard.run` lädt `standardzeiten.je_rennen(BASE)` – je gesammeltem Rennen die Standardzeit
seiner Konfiguration des Tages und die Going Allowance seines Renntags (aus allen Rennen des Tages). TR nutzt diese
Standardzeiten vorrangig und startet die Timeform-Allowance von dort; Rennen ohne Eintrag behalten die Schätzung aus
den Tracking-Rennen. Nach neuen Sammel-Etappen `sz.run(BASE, "2019-01-01", sammeln_ok=False)` neu berechnen.

## Race Card für heute

```python
import racecard
racecard.run(BASE)          # -> <BASE>/racecards/racecard_<JJJJMMTT>.html
```

Holt das heutige PMU-Programm (französische Flachrennen, auch die noch nicht
gelaufenen) und kombiniert es mit der gesammelten Historie in `parquet/`.
Die HTML-Datei ist eigenständig und lässt sich direkt im Browser öffnen.

Je Starter:

* **Übersicht**: Trikot (PMU `urlCasaque`, eingebettet), Musique, Karriere Läufe-Siege-Plätze
  und Gewinn je Lauf aus der Datenbank (Preisgeld je Platz laut PMU `montantOffert…`, sonst 50/19/14/9/4 %
  des Rennpreises), Muttervater, Jockey und Trainer mit A/E über 365 Tage (🔥 / 🧊, wenn die letzten 30 Tage
  deutlich besser/schlechter waren), Hinweise auf Trainerwechsel, Scheuklappen-Wechsel und
  „erstmals Wallach“, der Kurs hervorgehoben, dazu Ø von ΔL600 A und ΔB200 A
  der letzten 5 Läufe mit Tracking (gewichtet nach Distanz- und Going-Ähnlichkeit zu heute, zum Nullpunkt
  geschrumpft, mit Streuung) samt Rang im heutigen Feld.
* **Formzeilen** der letzten 7 Läufe mit Fünftel-Position 400 m vor dem Ziel, Pace-Ratio,
  Finish-Index (roh und bereinigt), ±800, Weg gegenüber dem Median des Feldes, ΔL600 A und
  ΔB200 A und der Klasse des Rennens (Kl.: Ø Valeur und Ø Gewinn je Lauf der Teilnehmer in den
  365 Tagen davor). Je Lauf lassen sich die je zwei wieder gelaufenen Gegner direkt davor und dahinter aufklappen
  (Bilanz am Knopf über das ganze Feld), mit Platz und Klasse (€/L+, Val+) im nächsten Start und ob der
  besser oder schlechter war als der Rang ihrer Quote; der Knopf zeigt besser / (besser + schlechter).
* **Heutige Gegner · frühere Duelle**: Rennen, in denen das Pferd schon auf heutige Gegner traf – Platz
  beider, Abstand, Gewichte damals und die Verschiebung des Gewichtsunterschieds bis heute. Eingeschränkt wie die
  indirekten Duelle: letzte 120 Tage, Distanz ±200 m zu heute, Boden innerhalb einer Stufe (`DUELL_TAGE`,
  `DUELL_DIST_M`, `DUELL_BODEN`); anders als dort zählen alle Platzierungen.
* **Startbox**: unter der Box die Abweichung der Ø relativen Platzierung (Starter − Platz) / (Starter − 1) aus
  dieser Box auf derselben Konfiguration (Bahn | Distanz | track_type | parcours_norm | Corde) von 0,5.
* **Übersicht**: Läufe-Siege-Plätze neben der Musique, Besitzer mit A/E, Scheuklappen-Symbol (klassisch /
  australisch), rechts nur die cote probable der PMU-Prognose. Aktuelle Kurse (Morgen-/Totokurs) enthält die Karte nicht, auch nicht im DATA-Block. RTR, ΔL600 A und ΔB200 A nur hier.
* **Rennverlauf** je Formzeile (`verlauf`, `verlauf_pferd`, `verlauf_plus`): Ø frühe Position der ersten drei gegen das Feld,
  verglichen mit der Norm der Bahn/Distanz (Vorne-/Hinten-Rennen = extremste 25 %, ab 8 Startern). „gegen V.“ beim Platz,
  wenn das Pferd gegen den Verlauf lief und trotzdem vorne landete (grün; Backtest: A/E Sieg 1,17, Platz 1,13);
  grau umrandet „gegen V.“ ohne vordere Platzierung und „mit V.“ – im Backtest ohne Effekt, nur zur Einordnung.
* **Video**: „▶ Video“ je früherem Lauf und „▶ PMU“ beim heutigen Rennen öffnen die Rennseite bei PMU
  (pmu.fr/turf/TTMMJJJJ/rX/cY/) mit dem Replay in einem neuen Tab. Einbetten geht nicht zuverlässig (PMU lässt die Seite
  nicht in fremden Seiten laden, das Video braucht deren Player).
* **Pausen** in den letzten Läufen: eigene Zeile „⏸ Pause n Tage“ zwischen zwei Läufen (bzw. „seit dem letzten Lauf“
  bis heute), ab 56 Tagen (8 Wochen, wie die Pausenregel im Skill).
* **Formzeilen** zusätzlich mit Valeur, Scheuklappen-Symbol und Endquote; ARR, TR und Klasse (Val, €/L) farbig im
  Vergleich zu allen früheren Läufen der heutigen Starter, ±800 und Weg m bei auffälligen Werten farbig.
* **Übersicht**: Karriere mit €/Lauf neben der Musique; Rating mit letzter Sieg- bzw. Platzmarke im Handicap;
  Rating, Tage, RTR, ARR und TR farbig nach dem Rang im Feld. Vorlieben zusätzlich Pferd nach Scheuklappen.
* **PMU-Prognose** (`pmu.prognosen`, Endpunkte `/pronostics` und `/pronostics-detailles`, nur vor dem Rennen):
  Rennkommentar der Redaktion, Auswahl mit cote probable (4/1 = 4,0) und Konsens der Tippgeber (Borda) im
  Rennkopf; am Pferd P1 … (Rang der Auswahl) bzw. T5 (in 5 Tipp-Listen), cote probable im Prognose-Kasten,
  Kurzkommentar (cribles) ganz unten in der Übersichtszeile über die volle Breite (kursiv, farbig) – übersetzt wie die Kommentare.
* **Kommentare** (`comment` je Starter aus pmu_runners) unter jedem früheren Lauf, auf Deutsch übersetzt, wo
  möglich (`uebersetzen.py`, deep-translator: DeepL mit Umgebungsvariable `DEEPL_API_KEY`, sonst Google, sonst
  MyMemory; Cache `<BASE>/uebersetzungen_fr_de.json`; Schnelltest `uebersetzen.pruefen()`); sonst französisch
  (FR). Abschalten mit `racecard.run(..., uebersetzen_aktiv=False)`.
* **A/E** zusätzlich für Besitzer und Züchter; Abstammung mit Zahl der Pferde und Ø der höchsten Valeur der
  Nachkommen als 3-Jährige (Ø max Val 3j).
* **Indizes €/L+ und Val+**: 100 × Wert ÷ Ø der Population (alle Trainer, Jockeys, Besitzer, Züchter im selben
  Zeitfenster bzw. alle Väter, Muttervater, Crosses; nur ab 5 Läufen bzw. 3 dreijährigen Nachkommen).
  100 = Durchschnitt, über 100 überdurchschnittlich; Chips wie A/E: grün ab 110, rot bis 90, blass bei wenig Daten.
* **Klasse Val+ und €/L+** (Rennkopf und Formzeilen): Ø Valeur bzw. Ø Gewinn je Lauf (365 Tage davor) der
  Teilnehmer ÷ Ø aller früheren Rennen × 100. Nur die Basis des Index €/L+ (`racecard.klassen_wert`,
  Spalte `cls_epr_kl`) ist anders gerechnet: jedes Preisgeld wird logarithmiert, log(1 + €), und je Pferd
  gemittelt (einzelne hohe Preisgelder ziehen den Schnitt nicht hoch; Läufe ohne Geld zählen 0, für eigene Läufe
  wie für die Verbindungen gleich). Das eigene Ø zählt, sobald der erste Start des Pferdes (in der Datenbank)
  mindestens ein Jahr zurückliegt – reicht die Historie dafür nicht zurück, ab 4 Jahren –, danach immer (ohne Lauf
  in den 365 Tagen über alle früheren Läufe). Davor gilt das gewichtete Ø der Verbindungen: Trainer 50 %, Besitzer
  30 %, Züchter 20 %, nur aus Läufen ihrer Pferde im ersten Jahr (je 365 Tage davor, ab 5 Läufen; fehlt einer,
  werden die Gewichte hochgerechnet). Rennstärke = Ø über die Starter; Index = 100 × Rennstärke ÷ Ø aller früheren
  Rennen. So fallen Rennen mit vielen wenig gelaufenen Pferden nicht künstlich ab. Angezeigte Beträge
  (€/L, `cls_epr`, `class.epr`) bleiben der einfache Ø der Pferde mit Läufen in den 365 Tagen. In den Formzeilen Farbverlauf nach der Lage unter allen früheren
  Läufen der heutigen Starter (rot = niedrigster, grün = höchster Wert für dieses Rennen); ebenso das Preisgeld.
* **Duelle** mit heutigen Gegnern nur aus den letzten 365 Tagen; je Duell „heute erwartet“ = Abstand damals −
  Verschiebung des Gewichtsunterschieds (1 kg = 1 Länge), am Knopf „vorne erwartet gegen x/y“ (je Gegner das letzte Duell).
* **Indirekte Duelle** (`racecard._indirekte_duelle`): je heutigem Gegner über gemeinsame frühere Gegner –
  Vergleichsrennen ≤ 120 Tage, ±200 m, Boden innerhalb einer Stufe (PSF nur mit PSF), alle drei Pferde mit
  relativer Platzierung > 0,5. Leistung = Längen × kg je Länge (`rtr_arr.KG_PER_LENGTH`) + Mehrgewicht; heute
  erwartet = Ø Unterschied − heutiges Mehrgewicht. Knopf mit Zusammenfassung, Tabelle je heutigem Gegner.
* **Duell-Rangfolge** (`racecard.duell_rangfolge`, Kachel „Duell“, Rennkopf „Duell-Rang“, JSON `duel_rank` je
  Starter und `duel_order` je Rennen): aus allen direkten und indirekten Duellen des heutigen Feldes je Pferd ein
  Wert in Längen, sodass die Unterschiede möglichst gut alle heute erwarteten Abstände treffen (kleinste Quadrate,
  Massey; A schlägt B, B schlägt C -> A, B, C). Gewicht: direkt 2, indirekt 1, mal 0,5^(Alter / 60 Tage);
  Abstände auf ±5 L begrenzt, jedes Paar einmal. Pferde ohne Verbindung untereinander bilden getrennte Gruppen.
* **Startbox in den früheren Läufen**: „Box 3 ▲/▼“, wenn die Box auf der Konfiguration dieses Rennens auffällig
  gut bzw. schlecht war (Ø relative Platzierung ≥ 0,05 von 0,5 entfernt und ≥ 2 Standardfehler; dieselbe Regel
  färbt die Box in der Übersicht).
* **Pferd auf dieser Bahn** (nur die heutige) und **Pferd nach Trainer** (alle bisherigen Trainer mit Zeitraum,
  neuester zuerst); in der A/E-Tabelle nur noch €/L+ (Betrag im Tooltip); in den Formzeilen Box bei Distanz/Boden
  und Valeur als eigene Spalte (klein: heutige Valeur − damalige);
  Hinweis **Besitzerwechsel** gegenüber dem letzten Lauf.
* **Klasse** im Rennkopf: Ø Valeur der Starter und Ø ihres Gewinns je Lauf der letzten 365 Tage, farbig als
  Perzentil aller früheren Rennen (grün oberes, rot unteres Drittel).
* **€/Lauf-Kachel** und Karriere im Detail (gesamt und 365 Tage) nur aus der PMU-Historie, mit Rang im Feld;
  grün ab 1,25 × Median des Feldes, rot bis 0,8 ×. €/Lauf auch für Trainer, Jockey, Vater, Muttervater und
  Cross (gegen den Ø aller Läufe im selben Zeitraum). Vorlieben zusätzlich Vater und Muttervater nach
  Altersgruppe (2j, 3j, 4j+).
* **Rohwerte aus den Abschnitten** (`speedfig.rohwerte_aus_abschnitten`): L600, L400, Tempo
  600–400 m und Finish-Index werden beim Bau der Race Card aus `tracking_sections` neu gebildet,
  nicht aus den beim Parsen abgelegten Spalten – so gelten die Korrekturen auch für alte Daten ohne
  Neu-Parsen: fehlender Split → kein Tempo (statt zu hohem), Wegfaktor (gelaufene ÷ nominale
  Distanz) skaliert die Tempi, Finish-Index = Tempo letzte 400 m ÷ Tempo davor, und die berechneten
  letzten 600 m werden gegen die offizielle Angabe der Übersichtsseite geprüft (bei Abweichung
  > 0,5 s werden die Tempi dieses Laufs verworfen).
* **ΔL600 A / ΔB200 A** (`tempo_delta.py`, km/h): Tempo der letzten 600 m bzw. schnellstes 200-m-Segment der
  letzten 800 m gegenüber der Erwartung. Verglichen wird nur innerhalb **Tag × Kurs × Going** (Bodengruppe
  des offiziellen PMU-Begriffs, nicht der Penetrometerwert), korrigiert um Kurs × Distanz und Pace-Ratio (linear + quadratisch
  je Distanzgruppe). Dazu die **Klassenkorrektur** der Gruppe: β × (Ø Klasse der Gruppe − Ø Klasse aller Läufe),
  β aus Altersklasse (`conditions_age`) und log. Preisgeld, geschätzt über die ganze Historie innerhalb der
  Gruppen. So wird ein Tag mit nur schwachen Rennen nicht überbewertet. Rennen mit Pace-Ratio im 1.–99. Perzentil
  und ≥ 5 Rennen je Kurs × Distanz. Beim Lauf werden β und die Spanne der Klassenkorrektur ausgegeben.
* **TR** (`timeform_ratings.py`, lb, bezogen auf 55 kg), nach `tempo_delta` berechnet:
  1. Standardzeit je Kurs × Distanz (s/km) = Median der Siegerzeiten guter Klasse, auf eine Referenzklasse
     umgerechnet (β aus Altersklasse und log. Preisgeld); Going Allowance je Tag × Kurs × Going zuerst aus den
     Siegerzeiten, dann nach Timeform aus den Zeiten der Pferde gegen ihre Ratings aus anderen Rennen (3 Runden).
  2. Zeit-Rating: eigene Zeit (Siegerzeit + `behind_winner_s`) minus Allowance gegen den Standard, Wegverlust
     gutgeschrieben, Sekunden → Längen (auf den eigenen Daten kalibriert) → lb (lb je Länge nach Distanz), Gewicht
     gegen 55 kg. Ausgerittene ohne Rating.
  3. Finishing Speed: FS% = (T·d·100)/(D·t) über die letzten 400 m (bis 1600 m) bzw. 600 m, je Pferd und je Rennen
     (Führender, gegen den Par je Kurs × Distanz).
  4. Upgrade = c · (d/D) · f(Optimum − FS%), f = Quadrat bis 3 FS-Punkte, darüber linear (sonst explodiert es in sehr
     langsam gelaufenen Rennen), höchstens 12 lb; gedeckelte Läufe sind in der Formzeile mit * markiert und zählen
     nicht für das beste TR der Übersicht. Optimum = Median-FS% der effizienten Läufe (höchstens 5 lb unter der
     scheinbaren Fähigkeit) je Kurs × Distanz, zur Distanzgruppe geschrumpft, plus Verschiebung je Bodenklasse;
     c ab 1,25 auf den eigenen Daten kalibriert, getrennt für zu schnell / zu langsam angegangen. TR = Zeit + Upgrade.
  5. Backtest beim Lauf: Korrelation mit dem nächsten Ergebnis und Top-3-Quote des Bestbewerteten für TR,
     Zeit-Rating, ΔL600 A, ΔB200 A und ARR.
  Race Card: TR immer auf das **heutige Gewicht** umgerechnet (TR − (heutiges Gewicht − 55 kg) × 2,2), damit die
  Pferde eines Rennens vergleichbar sind – in der Übersicht (gewichteter Ø der letzten 5 Läufe mit TR, Gewicht =
  Distanzähnlichkeit × Going-Ähnlichkeit auf der Leiter Très léger … Lourd, PSF gegen Gras 0,25, ohne gedeckelte
  Läufe; Rang im Feld) und in den
  Formzeilen (klein TR bei 55 kg, Zeit-Rating und Upgrade); dazu FS% gegen Optimum, Rennen-FS% gegen Par.
* **Bereinigte Kennzahlen** (`speedfig.py`, in der Race Card nur noch für den Finish-Index): Rennanteil (Median der vorderen Hälfte) gegen einen Par
  aus Distanz, Boden, Bahn und frühem Tempo des Führenden (nicht der Pace-Ratio – deren Nenner
  ist das Schlusstempo selbst), geschätzt per Ridge-Regression mit Leave-one-out, plus
  Pferdeanteil gegenüber dem Feld. L600/L400 in Längen, Best Seg/Δ400/Peak in km/h. Fehlt
  `pace_early_kmh` in älteren `tracking_races`, wird das frühe Tempo aus `tracking_leader` gebildet.
  Beim Lauf wird eine Validierung ausgegeben (Wiederholbarkeit, Prognosekraft; bereinigt gegen roh)
  sowie die Gegenprobe der letzten 600 m.
* **RTR und ARR** (`rtr_arr.py`, wie in PT_Vorarbeiten, in kg) für jeden gespeicherten Lauf:
  RTR = Elo-artiges Rating nach dem Rennen (jeder gegen jeden, erwarteter Abstand aus Rating − 0,625 × Gewicht
  gegen tatsächliche Längen × kg je Länge, K = 0,5), ARR = Leistung im Rennen gemessen an den Pferden im
  vorderen Drittel des Einlaufs (fehlende Ratings wie im Notebook ergänzt). Gegen das Notebook geprüft:
  ARR und Ergänzung identisch, RTR identisch bei gleicher Reihenfolge der Starter (hier: Einlauf). Bereinigt
  nach Gewicht: `x_adj = x − Gewicht + 55` – in der Übersicht mit dem heutigen Gewicht (RTR aktuell, ARR nach Distanz- und
  Going-Ähnlichkeit gewichteter Ø der letzten 5 Läufe wie TR, Rang im Feld), in den Formzeilen ebenfalls mit dem heutigen Gewicht (ARR 36, heute 52 kg -> 39); klein daneben der Rohwert.
  Das **Rating** (Valeur) der Übersicht wird genauso bereinigt (`rating_adj`; Farbe und Rang danach). Unverändert
  auf der offiziellen Valeur bleiben die Sieg- und Platzmarke darunter und die Val-Spalte der Formzeilen.
* **A/E Platz** statt A/E auf Sieg: Plätze ÷ Σ erwartete Platzwahrscheinlichkeit. Platz (`is_place`) = 1.–2. bei
  bis zu 7 Startern, 1.–3. ab 8. Erwartung aus den Endquoten: Marge herausgerechnet, dann Harville mit Korrektur
  (`racecard.harville_platz`, p^0,8 für Platz 2, p^0,65 für Platz 3). Ohne Marge liegt der Schnitt bei 1; A/E Sieg
  steht zum Vergleich im Tooltip.
* **A/E** für Trainer und Jockey über 30, 90 und 365 Tage; Abstammung (Vater, Muttervater und
  Cross Vater × Muttervater) über die gesamte Historie. Muttervater aus `dam_sire` (Programm) bzw.
  `p_nomPereMere` (pmu_basis).
* **Boden**: Alle Berechnungen (Vorlieben, Kachel-Gewichte, ΔL600/ΔB200-Gruppen, TR und Going Allowance,
  Standardzeiten, RTR/ARR, Speedfig) nutzen nur die Bodengruppe nach `rtr_arr.GOING_MAP`: Lourd, Très lourd,
  Collant = VERY SLOW · Souple, Très souple = SLOW · Bon souple, Bon = FAST · Léger, Bon léger, Très léger =
  VERY FAST · PSF Standard/Lente/Rapide = PSF. Der Penetrometerwert wird nur angezeigt.
* **Boden von heute, solange PMU ihn noch nicht hat**: Bei PSF-Rennen (Bahnart `typePiste`/Parcours) gilt PSF.
  Bei Gras gilt der Eintrag der Bahn in `boden_manuell.json` (im Repo, auf GitHub editieren; Vorgabe überall
  „Bon“). Gültige Begriffe stehen oben in der Datei zum Kopieren; Tippfehler werden gemeldet und übergangen.
  Mit `"datum"` gelten die Angaben nur für die Rennkarte dieses Tages. Liefert PMU eine Angabe, hat sie immer
  Vorrang. Die Karte zeigt „(manuell)“ an. Fehlt eine Bahn in der Datei, gilt die Annahme FAST, und die Ausgabe
  nennt den Bahnnamen zum Ergänzen.
* **Letzte Läufe**: Die letzten 7 Läufe. Gelb markiert ist, was dem heutigen Rennen entspricht: K = Kurs mit
  gleichem Belag (PSF gegen Gras), D = Distanz ±100 m, B = Bodengruppe. Fehlt unter den 7 ein Lauf auf dem
  heutigen Kurs (gleicher Belag), über die heutige Distanz (±100 m) oder in der heutigen Bodengruppe, kommt unten gestrichelt abgetrennt der letzte ältere Lauf mit
  diesem Merkmal dazu. Ein Lauf kann mehrere Merkmale abdecken. Es sind höchstens 3 zusätzliche Läufe, also bis
  zu 10 Zeilen (`formzeilen_auswahl`).
* **Distanzgruppen der Vorlieben** (`rtr_arr.distance_group`): 0-1000, dann je 200 m (1001-1200 …), >3600.
* **Vorlieben**: Pferd mit allen Böden, Distanzen und Kursen der gesamten Historie (heute markiert),
  Trainer (mit Jockey, Kurs, Typ, Altersgruppe 2j/3j/4j+) und Jockey (Kurs, Trainer) der letzten zwei
  Jahre, Jockey auf dem Pferd, Vater und Muttervater nach Distanz und Boden über die gesamte Historie.
  **▲ / ▼** hinter dem A/E (Trainer, Jockey, Vater, Muttervater; `ae_abweichung`) bedeutet: Die Vorliebe weicht
  deutlich und signifikant vom Rest derselben Person bzw. Linie ab. Bedingungen: mindestens ×1,2 bzw. ×0,8 des
  A/E aus ihren übrigen Läufen im selben Zeitraum, mindestens 2 Standardfehler und mindestens 20 übrige Läufe –
  wie beim Box-Urteil.
* **Laufstil** je Pferd (F / V / M / H), **Pace-Szenario** aus Tempomachern und Feldgröße,
  **Bahn-Bias** vorne gegen hinten je Bahn und Distanz, angezeigt relativ zum Schnitt aller Bahnen (0 = wie überall;
  Rohwert darunter). Pace-Modell: +x je Tempomacher und +y je Starter gegenüber 10 Startern (aus früheren Rennen
  geschätzt; mehr Starter = schnelleres Tempo). Beim Scrollen bleibt eine Kurzzeile des Rennens oben fixiert.
* Racing-Post-Kürzel **C / D / CD / BF**, Tage seit dem letzten Lauf, Gewicht, Rating, Startbox.

## Skill Rennkarten-Durchgang

`.claude/skills/rennkarten-durchgang/SKILL.md` ist der qualitative Durchgang durch eine Rennkarte. Er geht Pferd für Pferd
in der Reihenfolge der PMU-Prognose vor und prüft je Starter, ob es einen Wett-Angle gibt und ob dieser schon
eingepreist ist. Daraus leitet er den Edge gegen die Prognose-Chance und eine Mindestquote (Festkurs) ab.

Der Skill liest die von `racecard.py` erzeugte HTML-Karte. Die Daten stecken dort im eingebetteten `const DATA = …`
und werden mit Python geparst.

- **Claude Code:** In Sitzungen auf diesem Repo steht der Skill automatisch zur Verfügung.
- **claude.ai:** Dort wird er weiterhin als `.skill`/ZIP hochgeladen. Die Datei hier ist die versionierte Vorlage.
- **Pflege:** Neue Erkenntnisse aus Analysen kommen als knappe Regel an die passende Stelle des Rasters (A/B/C), nicht als
  neuer Abschnitt. Nach jeder Anpassung wird konsolidiert: Doppeltes zusammenführen und Erklärungen kürzen, die die
  Claude-JSON schon vorrechnet. Der Umfang soll nicht wachsen (Stand 09.10.2026: rund 55.700 Zeichen).

**Claude-Version der Karte** (`claude_export.py`): Neben `racecard_JJJJMMTT.html` schreibt `racecard.run` die Datei
`racecard_JJJJMMTT_claude.json` (abschalten mit `claude=False`).

- **Inhalt:** **alle Daten der Karte**, auch Detailinfos, die der Skill heute nicht nutzt. Neue Felder der Karte kommen automatisch mit; ein Selbsttest prüft die Vollständigkeit.
- **Weggelassen** sind nur Trikots, je Formzeile die volle Gegnerliste (es bleiben `rivals_nah` mit den zwei Gegnern davor und dahinter und `rivals_stat`) und die Zwischenwerte der Berechnung (`claude_export.OHNE_FORMZEILE`).
- **Umgeordnet:** Starter nach Prognose-Rang, Nichtstarter getrennt (`nichtstarter`, Nummern in `nr`).
- **Vorgerechnet:** Prognose-Chance nach der Potenzmethode (`p_prog`), `marge`, `reihenfolge`, `bias_rel` gegen den Schnitt aller Bahnen, `luecke` (PMU-Starts − Datenbank-Läufe).
- **Größe:** etwa ein Drittel der HTML-Karte (02.10.: 2,8 statt 8,2 MB).
- **Zur Analyse** in claude.ai hochladen: den Skill und diese Datei statt der HTML-Karte. Der Skill liest sie bevorzugt; die HTML-Karte bleibt als Rückfall.

**claude.ai-Projekt:** Systemprompt und Einrichtung (Skill über die GitHub-Anbindung, nur die Claude-JSON hochladen) stehen in
`claude_projekt/systemprompt.md`.
