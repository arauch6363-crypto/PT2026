---
name: ergebnis-analyse
description: "Ergebnisanalyse eines Renntags: Durchgänge des Skills rennkarten-durchgang-neu gegen den Einlauf abgleichen und daraus Vorschläge für dessen SKILL.md oder EINSICHTEN.md ableiten. Verwenden für die Aufgabe „Ergebnisanalyse“ oder Lehren aus einem vergangenen Renntag."
---

# Ergebnisanalyse

Die Ergebnisanalyse **liefert Vorschläge, der Nutzer entscheidet** (ADR 0003). Ein Fall genügt für einen Vorschlag; ob
er sich verallgemeinern lässt, beurteilt der Nutzer. Begriffe (Siegergruppe, verpasster Sieger, verlorener
Claude-Tipp, Vorschlag, Gegenprobe, Rückschau, Regelkennung, Regelprotokoll, Kandidatenprotokoll, Drift, Kalibrierung)
stehen in `GLOSSARY.md`. Ablauf mit Drive, Seite und PR: `claude_projekt/aufgabe_ergebnisanalyse.md`; dieser Skill ist
der Urteilsteil.

## 1. Lesen

- `SKILL.md` und `EINSICHTEN.md` von `.claude/skills/rennkarten-durchgang-neu/` ganz: Ein Vorschlag muss wissen, was
  schon dasteht.
- Das Material über das Skript: `python3 -I ergebnis_analyse.py faelle ANALYSE` zeigt Zählung und je Fall eine Zeile,
  `… faelle ANALYSE RxCy` den Eintrag eines Rennens (Pro/Gegen, Maßstäbe). Seine Zahlen gelten, wie sie dastehen.
- Das Blatt des **Rennens, um das es im Fall geht**:
  `python3 -I .claude/skills/rennkarten-durchgang-neu/scripts/blatt.py KARTE RxCy`. Die übrigen Rennen erreicht die
  Gegenprobe per Skript.

Fertig, wenn die Fallliste vorliegt und beide Skill-Dateien gelesen sind.

## 2. Je Fall

Bearbeitet werden **verpasste Sieger** und **verlorene Claude-Tipps**. Treffer bekommen eine Zeile („Regel X trug“).
Sieger aus Maßstab oder sonstige Sieger werden nur gezählt: Sie betreffen den Kandidaten-Filter, nicht den Skill.

1. **Regel.** Woran hing das Urteil? Die Kennung aus dem Ausschlag; fehlt sie, die Regel aus dem Text zuordnen und
   „(zugeordnet)“ dazuschreiben. Passt keine: „Ermessen“ – eine Häufung davon ist selbst ein Befund: Dort fehlt eine
   Regel.
2. **Datenpunkt.** Was im Blatt hätte das richtige Urteil gestützt? Nur was **vor dem Rennen** im Blatt stand (Einlauf,
   Endquote, Rennkommentar und Tracking dieses Rennens kamen danach), wörtlich zitiert. Kein Datenpunkt ist ein
   gültiges Ergebnis („Rennen nicht lesbar, Sieg aus dem Nichts“) – dann kein Vorschlag.
3. **Gegenprobe.** `python3 -I ergebnis_analyse.py gegenprobe KARTE ANALYSE 'MUSTER'` mit einem regulären Ausdruck für
   den Datenpunkt (z. B. `'CGD \S*D'`, `'Trainerwechsel'`) meldet, bei wie vielen Verlierern des Tages er ebenfalls
   stand, mit Namen und Zeile. Hängt er an einer Zahl oder einem Vergleich, die gemeldeten Zeilen von Hand prüfen.
   Schwächt die Gegenprobe den Datenpunkt, gehört sie trotzdem in den Vorschlag.
   **Rückschau**, wenn der Vorschlag Urteile strenger macht: `python3 -I ergebnis_analyse.py rueckschau KENNUNG` zeigt
   die bisherigen Tipps und abgelehnten Kandidaten mit dieser Kennung und ihre Sieger; bei einer neuen Kennung
   `… rueckschau` ohne Kennung alle bisherigen Treffer. Welche dieser Treffer hätte die Regel gestrichen? Das gehört
   in `gegenprobe`, auch wenn es „keiner“ ist.
4. **Abgleich.** Trifft eine bestehende Einsicht (selber Abschnitt von `EINSICHTEN.md`) oder Regel (`SKILL.md`) die
   Lage, ist der Vorschlag `aendern` oder `zusammenfassen`; `neu` nur für eine Lage, die keine bestehende trifft.
5. **Schluss.** Hätte eine andere Gewichtung oder Regel das Urteil gedreht, ohne bei den Verlierern der Gegenprobe
   falsch zu drehen? Ja → Vorschlag. Nein → ein Satz Befund.

Fertig, wenn **jeder** verpasste Sieger und verlorene Tipp in einem Vorschlag steht oder einen Satz Befund hat.

## 3. Vorschlag

Jeder Vorschlag ist eine **konkrete Textänderung**, über die der Nutzer mit Ja, Nein oder Ändern entscheidet:

| Feld | Inhalt |
|---|---|
| `titel` | ein Satz, was sich ändert |
| `fall` | `verpasster_sieger`, `verlorener_tipp` oder `regel_unter_druck` |
| `rennen`, `race_id`, `no`, `horse` | der Fall |
| `durchgang` | ein Satz: Urteil, Festkurs, woran es hing |
| `datenpunkt` | Zitat aus dem Blatt |
| `gegenprobe` | höchstens drei Sätze: wie viele Verlierer mit Namen, was den Vorschlag schwächt; bei `strenger` dazu ein Satz Rückschau |
| `art` | `neu`, `aendern`, `zusammenfassen`, `gewicht` oder `streichen` |
| `zieldatei` | `SKILL.md` (Regel, Liste) oder `EINSICHTEN.md` (Gewichtung, typischer Fehler) |
| `kennung` | bestehende Kennung oder eine neue nach dem Muster in `SKILL.md` („Kennungen“) |
| `alt` | bei `aendern` und `zusammenfassen`: der bisherige Text, wörtlich (bei mehreren Einsichten alle) |
| `text` | **wörtlich** der neue Text, so wie er in der Datei stehen soll, mit Fallbeispiel in *kursiv* |
| `gewicht` | `ausschlaggebend`, `gewichtig` oder `leicht` – Claudes Vorschlag |
| `wirkung` | `strenger` (mehr „nein“ oder kleinere Wetten), `lockerer` (umgekehrt) oder `neutral` (Form, Verdichtung) |

Mehrere Fälle, die auf dieselbe Regel zeigen, ergeben **einen** Vorschlag mit allen Fällen. Reihenfolge nach Stärke:
klare Gegenprobe und klarer Regelbezug zuerst. Ein abgelehnter Vorschlag (`auswertung/vorschlaege.csv`, `entscheidung`
nein) kommt nur mit neuen Belegen wieder, mit Verweis auf die Ablehnung. `titel` und `text` nach dem nächsten
Abschnitt.

### Schreiben für den Durchgang

Ein angenommener `text` steht ab dann im Kontext **jedes Subagenten in jedem Durchgang**. Vor dem ersten Vorschlag
deshalb `.claude/skills/writing-for-agents/SKILL.md` lesen. Angewandt auf einen Vorschlag:

- **Eine Bedeutung, ein Ort:** Was eine bestehende Einsicht schon sagt, wird dort geschärft (`aendern`). Deckt sich ein
  neuer Text teilweise mit einer Einsicht, steht sie in `alt` und die Art ist `zusammenfassen`.
- **Dreht ein Urteil:** Jeder Text dreht das Urteil in mindestens einem Fall. Ein Text, den der Durchgang ohnehin
  befolgt („Boden prüfen“), ist ein No-op und wird ein Satz Befund.
- **Leitwörter:** Begriffe aus `GLOSSARY.md` (Referenzlauf, Maßstab, Bodenangabe, Klassenindex, Rennverlauf,
  Aufgewicht), für jede Lage dasselbe Wort wie in `SKILL.md`. Blattkürzel übersetzt: `≈heute` → „Referenzlauf“ bzw.
  „Lauf unter heutigen Bedingungen“, „gegen den Verlauf“ → „gegen den Rennverlauf gelaufen“, „Zwischenfall“ →
  „behindert, eingeklemmt“; `ber.` entfällt.
- **Positiv:** was gilt und was dann zu tun ist.
- **Kurz:** eine Regel in höchstens zwei Sätzen (etwa 35 Wörter), dahinter das Fallbeispiel in *kursiv* mit Pferd und
  Datum; eine Ausnahme höchstens als Halbsatz. Zahlen nur, wo die Regel an ihnen hängt, gerundet („etwa 2 Punkte ARR“,
  „5 Längen und mehr“).
- **Beleg getrennt:** Blattzitate, Klassenindizes und Rechenwege stehen in `datenpunkt` und `gegenprobe`.

> `G-MASSSTAB-BESSER` Lief ein Maßstab in seinem Referenzlauf klar besser als der Kandidat in seinem (etwa 2 Punkte ARR
> mehr, in einem stärkeren Rennen), reicht es bei kurzer Quote nicht für eine Wette. *X Rays 15.11.*

Fertig, wenn jeder `text` alle sechs Punkte erfüllt.

## 4. Anlässe

`python3 -I ergebnis_analyse.py verdichtung` und `… bericht`. Meldet eines einen Anlass (`abschnitt_voll`,
`datei_lang`, `vorlaeufig_*`, eine Regel `unter_druck`): [`VERDICHTEN.md`](VERDICHTEN.md) lesen und je Anlass
Vorschläge nach Abschnitt 3 machen. Fertig, wenn jeder gemeldete Anlass einen Vorschlag hat.

`… bericht --ausschlag` zählt nur die Kennung, die das Urteil entschied (mit „Ermessen“), `… bericht --pruefschritt`
bündelt die Kennungen je Prüfschritt; beide füllen sich schneller als die einzelne Kennung. Sie sind Belege für
`gegenprobe`; ein Anlass bleibt allein `unter_druck` aus `bericht`.

**Drift:** `python3 -I ergebnis_analyse.py drift` zählt je Tag wette / klein / nein und stellt den Tipp-Anteil der
letzten 7 Tage dem davor gegenüber, dazu die angenommenen Vorschläge nach `wirkung`. Die Zeile des Tages und das
Verhältnis `strenger` : `lockerer` stehen im Bericht an den Nutzer. Meldet `drift` `anlass` (Tipp-Anteil halbiert),
nennt der Bericht das ausdrücklich als Frage an den Nutzer, ob der Skill zu streng geworden ist; ein Vorschlag folgt
daraus nur auf sein Wort.

**Kalibrierung:** `python3 -I ergebnis_analyse.py kalibrierung` stellt je Urteil die Siege den erwarteten Siegen nach
Markt und nach der Mitte der eigenen Kursspanne (1 / Mitte) gegenüber, dazu Ø ln(Festkurs / Endquote): positiv heißt,
der Festkurs beim Durchgang lag über der Endquote. Gewinnen die Tipps klar seltener, als ihre Spannen sagen, war die
Spanne zu großzügig. Unter etwa 50 Tipps ist das Rauschen; die Zahlen messen den Skill nicht (ADR 0002) und tragen
allein keinen Vorschlag – sie gehören als Beleg in `gegenprobe`, wenn ein Vorschlag die Kursspanne betrifft.

## Nach der Entscheidung des Nutzers

Eintragen der Entscheidungen und Testsatz: [`INTEGRIEREN.md`](INTEGRIEREN.md).
