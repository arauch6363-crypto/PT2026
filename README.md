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
| `rpr.py` | Performance-Ratings nach Racing-Post-Art (RPR) aus Gewicht, Längen und Ankerpferden |
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

## Race Card für heute

```python
import racecard
racecard.run(BASE)          # -> <BASE>/racecards/racecard_<JJJJMMTT>.html
```

Holt das heutige PMU-Programm (französische Flachrennen, auch die noch nicht
gelaufenen) und kombiniert es mit der gesammelten Historie in `parquet/`.
Die HTML-Datei ist eigenständig und lässt sich direkt im Browser öffnen.

Je Starter:

* **Übersicht**: Trikot (PMU `urlCasaque`, eingebettet), Musique, Karriere Starts-Siege-Plätze
  und Gewinn je Start, Jockey und Trainer mit A/E über 365 Tage (🔥 / 🧊, wenn die letzten 30 Tage
  deutlich besser/schlechter waren), Hinweise auf Trainerwechsel, Scheuklappen-Wechsel und
  „erstmals Wallach“, der Kurs hervorgehoben, dazu Ø der bereinigten L600, Δ400 und Best Seg
  der letzten 5 Läufe mit Tracking (gewichtet nach Distanzähnlichkeit zu heute, zum Nullpunkt
  geschrumpft, mit Streuung) samt Rang im heutigen Feld.
* **Formzeilen** der letzten 7 Läufe mit Fünftel-Position 400 m vor dem Ziel, Pace-Ratio,
  Finish-Index (roh und bereinigt), ±800, Weg gegenüber dem Median des Feldes, Best Seg
  (letzte 800 m), L600, L400, Δ400 (L400 − Tempo 600–400 m) und Peak (Best Seg − L600). Für die
  letzten 5 Läufe lassen sich die Gegner aufklappen, die seitdem wieder liefen (die 3, die dem Pferd
  am nächsten waren), mit Platz im nächsten Start und ob der besser oder schlechter war als der Rang
  ihrer Quote.
* **Rohwerte aus den Abschnitten** (`speedfig.rohwerte_aus_abschnitten`): L600, L400, Tempo
  600–400 m und Finish-Index werden beim Bau der Race Card aus `tracking_sections` neu gebildet,
  nicht aus den beim Parsen abgelegten Spalten – so gelten die Korrekturen auch für alte Daten ohne
  Neu-Parsen: fehlender Split → kein Tempo (statt zu hohem), Wegfaktor (gelaufene ÷ nominale
  Distanz) skaliert die Tempi, Finish-Index = Tempo letzte 400 m ÷ Tempo davor, und die berechneten
  letzten 600 m werden gegen die offizielle Angabe der Übersichtsseite geprüft (bei Abweichung
  > 0,5 s werden die Tempi dieses Laufs verworfen).
* **Bereinigte Kennzahlen** (`speedfig.py`): Rennanteil (Median der vorderen Hälfte) gegen einen Par
  aus Distanz, Boden, Bahn und frühem Tempo des Führenden (nicht der Pace-Ratio – deren Nenner
  ist das Schlusstempo selbst), geschätzt per Ridge-Regression mit Leave-one-out, plus
  Pferdeanteil gegenüber dem Feld. L600/L400 in Längen, Best Seg/Δ400/Peak in km/h. Fehlt
  `pace_early_kmh` in älteren `tracking_races`, wird das frühe Tempo aus `tracking_leader` gebildet.
  Beim Lauf wird eine Validierung ausgegeben (Wiederholbarkeit, Prognosekraft; bereinigt gegen roh)
  sowie die Gegenprobe der letzten 600 m.
* **Replay** je Formzeile: `pmu.replay` fragt `online.pmu.fr/rest/papi/v1/programme/{TTMMJJJJ}/R{r}/C{c}/replay`
  (ersatzweise die Rennseite ohne `/replay`) und nimmt die erste Video-Adresse der Antwort. Zwischengespeichert in
  `<BASE>/replays.json`; fehlt ein Replay, wird 14 Tage lang höchstens einmal am Tag erneut gefragt. Ohne Replay
  verlinkt die Formzeile die PMU-Rennseite. Prüfen, was PMU liefert: `pmu.replay_diagnose("20260923R3C3")`.
* **RPR** (`rpr.py`, Performance-Rating nach Racing-Post-Art in lb, ≈ Rating in kg × 2,2) für jeden
  gespeicherten Lauf: Leistung im Rennen aus Gewicht (mit Gewichtsausgleich für das Alter) und geschlagenen
  Längen, Niveau des Rennens über Starter mit Rating oder früheren RPRs (chronologisch bewertet), zum
  Klassenwert geschrumpft. In der Übersicht bestes RPR der letzten 6 Läufe (klein das letzte) mit Rang im
  Feld, in den Formzeilen je Lauf (`?` = vorläufig, kein Anker im Feld; Bestwert / unter Wert / Abstand gekappt).
* **A/E** für Trainer, Jockey und Vater über 30, 90 und 365 Tage.
* **Vorlieben**: Pferd mit allen Böden und Distanzen der gesamten Historie (heute markiert),
  Trainer und Jockey der letzten zwei Jahre, Vater über die gesamte Historie.
* **Laufstil** je Pferd (F / V / M / H), **Pace-Szenario** aus Tempomachern und Feldgröße,
  **Bahn-Bias** vorne gegen hinten je Bahn und Distanz.
* Racing-Post-Kürzel **C / D / CD / BF**, Tage seit dem letzten Lauf, Gewicht, Rating, Startbox.
