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

* **Formzeilen** der letzten 6 Läufe: `29 Aug 2026 Deauville · 1200m Bon 27k Handicap · 4/13 (2l) 57kg`,
  dazu je Lauf eine Grafik, in welchem Fünftel des Feldes das Pferd 400 m vor dem Ziel lag,
  eine Grafik zum Pace-Ratio des Rennens sowie `finish_index`, `pos_gain_800_finish`,
  `best_seg_s`, `speed_last600_kmh` und `speed_last400_kmh`.
  Die drei letzten Werte werden zusätzlich **adjustiert** gezeigt: Abweichung vom
  Erwartungswert für Boden (PMU-Begriff), Distanz, Alter, Renntempo (Pace-Ratio) und Bahn
  (additives Modell). Positiv heißt immer besser als erwartet.
* **A/E** für Trainer, Jockey und Vater über 90 und 365 Tage: Siege / Σ(1/Endquote).
* **Vorlieben unter heutigen Bedingungen**: Pferd (Boden, Distanz), Trainer (Jockey, Bahn,
  Renntyp), Jockey (Bahn, Trainer), Vater (Distanz, Boden), jeweils Siege-Starts, Quote und A/E.
* Racing-Post-Kürzel **C / D / CD / BF**, Tage seit dem letzten Lauf, Musique, Gewicht, Rating,
  Startbox, Kurs und Morgenkurs.
