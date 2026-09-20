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
* Gespeichert wird nur positives Wissen: welcher France-Galop-Code (z. B. `CHA`)
  zu welcher Bahn gehört. Für unbekannte Bahnen werden Kandidaten
  durchprobiert – ein Treffer zählt aber nur, wenn der Bahnname im PDF-Kopf
  dazu passt. Sonst würde z. B. `CHATEAUBRIANT` den Code `CHA` von `CHANTILLY`
  erben.
* Findet sich kein Code, wird das nur als Fehlversuch gezählt. Die Bahn wird an
  den nächsten Renntagen erneut geprüft (`ERSTE_VERSUCHE`), später in größeren
  Abständen (`WIEDER_NACH_TAGEN`) – nie dauerhaft ausgeschlossen.
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
