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
  365 Tagen davor). Je Lauf lassen sich alle Gegner aufklappen, mit Platz im nächsten Start und ob der
  besser oder schlechter war als der Rang ihrer Quote; der Knopf zeigt besser / (besser + schlechter).
* **Heutige Gegner · frühere Duelle**: Rennen, in denen das Pferd schon auf heutige Gegner traf – Platz
  beider, Abstand, Gewichte damals und die Verschiebung des Gewichtsunterschieds bis heute.
* **Startbox**: unter der Box die Abweichung der Ø relativen Platzierung (Starter − Platz) / (Starter − 1) aus
  dieser Box auf derselben Konfiguration (Bahn | Distanz | track_type | parcours_norm | Corde) von 0,5.
* **Übersicht**: Läufe-Siege-Plätze neben der Musique, Besitzer mit A/E, Scheuklappen-Symbol (klassisch /
  australisch), Kurs mit Morgenkurs und Pfeil (▼ gefallen, ▲ gestiegen). RTR, ΔL600 A und ΔB200 A nur hier.
* **Formzeilen** zusätzlich mit Valeur, Scheuklappen-Symbol und Endquote.
* **Kommentare** (`comment` je Starter aus pmu_runners) unter jedem früheren Lauf, auf
  Deutsch übersetzt, wo möglich (`uebersetzen.py`, deep-translator, Cache `<BASE>/uebersetzungen_fr_de.json`);
  ohne Paket oder Netz bleibt der französische Text (markiert mit FR).
* **A/E** zusätzlich für Besitzer und Züchter; Abstammung mit Zahl der Pferde und Ø ihrer höchsten Valeur.
* **Duelle** mit heutigen Gegnern nur aus den letzten 365 Tagen.
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
* **A/E** für Trainer und Jockey über 30, 90 und 365 Tage; Abstammung (Vater, Muttervater und
  Cross Vater × Muttervater) über die gesamte Historie. Muttervater aus `dam_sire` (Programm) bzw.
  `p_nomPereMere` (pmu_basis).
* **Boden**: Alle Berechnungen (Vorlieben, Kachel-Gewichte, ΔL600/ΔB200-Gruppen, TR und Going Allowance,
  Standardzeiten, RTR/ARR, Speedfig) nutzen nur die Bodengruppe nach `rtr_arr.GOING_MAP`: Lourd, Très lourd,
  Collant = VERY SLOW · Souple, Très souple = SLOW · Bon souple, Bon = FAST · Léger, Bon léger, Très léger =
  VERY FAST · PSF Standard/Lente/Rapide = PSF. Der Penetrometerwert wird nur angezeigt.
* **Distanzgruppen der Vorlieben** (`rtr_arr.distance_group`): 0-1000, dann je 200 m (1001-1200 …), >3600.
* **Vorlieben**: Pferd mit allen Böden, Distanzen und Kursen der gesamten Historie (heute markiert),
  Trainer (mit Jockey, Kurs, Typ, Altersgruppe 2j/3j/4j+) und Jockey (Kurs, Trainer) der letzten zwei
  Jahre, Jockey auf dem Pferd, Vater und Muttervater nach Distanz und Boden über die gesamte Historie.
* **Laufstil** je Pferd (F / V / M / H), **Pace-Szenario** aus Tempomachern und Feldgröße,
  **Bahn-Bias** vorne gegen hinten je Bahn und Distanz.
* Racing-Post-Kürzel **C / D / CD / BF**, Tage seit dem letzten Lauf, Gewicht, Rating, Startbox.
