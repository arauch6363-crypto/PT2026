---
name: ergebnis-analyse
description: "Gleicht die Durchgänge eines Renntags (Skill rennkarten-durchgang-neu) mit dem Einlauf ab: je verpasstem Sieger und verlorenem Claude-Tipp, an welcher Regel es lag und welcher Datenpunkt der Karte geholfen hätte, mit Gegenprobe; daraus wörtliche Vorschläge für SKILL.md oder EINSICHTEN.md, über die der Nutzer entscheidet. Verwenden für die Aufgabe „Ergebnisanalyse“ oder wenn ein vergangener Renntag auf Lehren für den Durchgang-Skill durchgesehen werden soll."
---

# Ergebnisanalyse

Die Ergebnisanalyse **liefert Vorschläge, der Nutzer entscheidet** (ADR 0003). Ein Fall genügt für einen Vorschlag; ob
er sich verallgemeinern lässt, beurteilt der Nutzer. Begriffe (Siegergruppe, verpasster Sieger, verlorener
Claude-Tipp, Vorschlag, Gegenprobe, Regelkennung, Regelprotokoll) stehen in `GLOSSARY.md`. Ablauf mit Drive, Seite und
PR: `claude_projekt/aufgabe_ergebnisanalyse.md`; dieser Skill ist der Urteilsteil.

Jeder Vorschlag ist ein Text, den ab dann **jeder Subagent in jedem Durchgang** liest. Darum schreibt die
Ergebnisanalyse für Agenten: Vor dem ersten Vorschlag `.claude/skills/writing-for-agents/SKILL.md` lesen (Skill
`writing-for-agents`) und nach dem Abschnitt „Schreiben für den Durchgang“ unten anwenden.

## 1. Lesen – sparsam

- `SKILL.md` und `EINSICHTEN.md` von `.claude/skills/rennkarten-durchgang-neu/` ganz: Ein Vorschlag muss wissen, was
  schon dasteht.
- Das Material (`analyse_JJJJMMTT.json`) **nur über das Skript**: `python3 -I ergebnis_analyse.py faelle ANALYSE`
  zeigt Zählung und je Fall eine Zeile, `… faelle ANALYSE RxCy` den Eintrag eines Rennens (Pro/Gegen, Maßstäbe). Die
  Mechanik ist dort erledigt – nichts nachrechnen.
- Fakten zur Karte nur für das **Rennen des Falls**:
  `python3 -I .claude/skills/rennkarten-durchgang-neu/scripts/blatt.py KARTE RxCy`. Die Blätter der übrigen Rennen
  liest die Gegenprobe per Skript.

Fertig, wenn die Fallliste vorliegt und beide Skill-Dateien gelesen sind.

## 2. Je Fall

Bearbeitet werden **verpasste Sieger** und **verlorene Claude-Tipps**. Treffer bekommen eine Zeile („Regel X trug“).
Sieger aus Maßstab oder sonstige Sieger werden nur gezählt: Sie betreffen den Kandidaten-Filter, nicht den Skill.

1. **Regel.** Woran hing das Urteil? Die Kennung aus dem Ausschlag; fehlt sie, die Regel aus dem Text zuordnen und
   „(zugeordnet)“ dazuschreiben. Passt keine: „Ermessen“ – eine Häufung davon ist selbst ein Befund: Dort fehlt eine
   Regel.
2. **Datenpunkt.** Was im Blatt hätte das richtige Urteil gestützt? Nur Angaben, die **vor dem Rennen** im Blatt
   standen; Einlauf, Endquote, Rennkommentar und Tracking dieses Rennens sind Nachwissen. Wörtlich zitiert. Kein
   Datenpunkt ist ein gültiges Ergebnis („Rennen nicht lesbar, Sieg aus dem Nichts“) – dann kein Vorschlag.
3. **Gegenprobe.** `python3 -I ergebnis_analyse.py gegenprobe KARTE ANALYSE 'MUSTER'` mit einem regulären Ausdruck,
   der den Datenpunkt trifft (z. B. `'CGD \S*D'`, `'Trainerwechsel'`). Es meldet, bei wie vielen Verlierern des Tages
   (Kandidaten und Maßstäbe aller Rennen) er ebenfalls stand, mit Namen und Zeile. Hängt der Datenpunkt an einer Zahl
   oder einem Vergleich, den kein Muster fasst, die gemeldeten Zeilen prüfen statt weitere Blätter zu lesen. Eine
   Gegenprobe, die den Datenpunkt bei vielen Verlierern zeigt, gehört in den Vorschlag, auch wenn sie ihn schwächt.
4. **Abgleich.** Trifft eine bestehende Einsicht (selber Abschnitt von `EINSICHTEN.md`) oder Regel (`SKILL.md`) die
   Lage, ist der Vorschlag `aendern` oder `zusammenfassen` – eine Bedeutung, ein Ort. `neu` nur, wenn keine bestehende
   die Lage trifft.
5. **Schluss.** Hätte eine andere Gewichtung oder Regel das Urteil gedreht, ohne bei den Verlierern der Gegenprobe
   falsch zu drehen? Ja → Vorschlag. Nein → ein Satz Befund.

Fertig, wenn **jeder** verpasste Sieger und verlorene Tipp entweder in einem Vorschlag steht oder einen Satz Befund hat.

## 3. Vorschlag

Jeder Vorschlag ist eine **konkrete Textänderung**, über die der Nutzer mit Ja, Nein oder Ändern entscheidet:

| Feld | Inhalt |
|---|---|
| `titel` | ein Satz, was sich ändert |
| `fall` | `verpasster_sieger`, `verlorener_tipp` oder `regel_unter_druck` |
| `rennen`, `race_id`, `no`, `horse` | der Fall |
| `durchgang` | ein Satz: Urteil, Festkurs, woran es hing |
| `datenpunkt` | Zitat aus dem Blatt |
| `gegenprobe` | höchstens drei Sätze: wie viele Verlierer mit Namen, was den Vorschlag schwächt |
| `art` | `neu`, `aendern`, `zusammenfassen`, `gewicht` oder `streichen` |
| `zieldatei` | `SKILL.md` (Regel, Liste) oder `EINSICHTEN.md` (Gewichtung, typischer Fehler) |
| `kennung` | bestehende Kennung oder eine neue nach dem Muster in `SKILL.md` („Kennungen“) |
| `alt` | bei `aendern` und `zusammenfassen`: der bisherige Text, wörtlich (bei mehreren Einsichten alle) |
| `text` | **wörtlich** der neue Text, so wie er in der Datei stehen soll, mit Fallbeispiel in *kursiv* |
| `gewicht` | `ausschlaggebend`, `gewichtig` oder `leicht` – Claudes Vorschlag |

Mehrere Fälle, die auf dieselbe Regel zeigen, ergeben **einen** Vorschlag mit allen Fällen. Reihenfolge nach Stärke:
klare Gegenprobe und klarer Regelbezug zuerst. Ein früher abgelehnter Vorschlag (`auswertung/vorschlaege.csv`,
`entscheidung` nein) kommt nur mit neuen Belegen wieder, mit Verweis auf die Ablehnung.

## Schreiben für den Durchgang

`titel` und `text` liest der Nutzer so, wie der Text in der Datei stehen wird; danach liest ihn der Durchgang-Agent.
Die Hebel aus `writing-for-agents`, angewandt auf einen Vorschlag:

- **Eine Bedeutung, ein Ort** (single source of truth): Was eine bestehende Einsicht schon sagt, wird dort geschärft
  (`aendern`), nicht neu daneben gestellt. Ein `text`, der eine andere Einsicht teilweise wiederholt, nennt sie in
  `alt` und wird `zusammenfassen`.
- **Kein No-op:** Ein Text, den der Durchgang ohnehin befolgt (etwa „Boden prüfen“, „Form beachten“), ändert kein
  Urteil – dann Befund statt Vorschlag. Jeder Text muss ein Urteil in mindestens einem Fall drehen.
- **Leitwörter:** Begriffe aus `GLOSSARY.md` (Referenzlauf, Maßstab, Bodenangabe, Klassenindex, Rennverlauf,
  Aufgewicht) statt Umschreibungen; jede Lage mit demselben Wort, mit dem sie in `SKILL.md` geprüft wird. Kürzel und
  Markierungen aus dem Blatt heißen im Text so: `≈heute` → „Referenzlauf“ bzw. „Lauf unter heutigen Bedingungen“,
  „gegen den Verlauf“ → „gegen den Rennverlauf gelaufen“, „Zwischenfall“ → „behindert, eingeklemmt“; `ber.` entfällt.
- **Positiv:** was gilt und was dann zu tun ist, nicht welche andere Regel nicht gilt.
- **Kurz** (gegen Sprawl): eine Regel in höchstens zwei Sätzen (etwa 35 Wörter), dahinter das Fallbeispiel in
  *kursiv* mit Pferd und Datum; eine Ausnahme höchstens als Halbsatz. Zahlen nur, wo die Regel an ihnen hängt,
  gerundet („etwa 2 Punkte ARR“, „5 Längen und mehr“).
- **Beleg getrennt:** Blattzitate, Klassenindizes und Rechenwege stehen in `datenpunkt` und `gegenprobe`, nie in
  `text`.

Beispiel:

> `G-MASSSTAB-BESSER` Lief ein Maßstab in seinem Referenzlauf klar besser als der Kandidat in seinem (etwa 2 Punkte ARR
> mehr, in einem stärkeren Rennen), reicht es bei kurzer Quote nicht für eine Wette. *X Rays 15.11.*

Fertig, wenn jeder `text` alle sechs Punkte erfüllt.

## Verdichten

`EINSICHTEN.md` wird von jedem Subagenten in jedem Durchgang ganz gelesen; jede Zeile kostet Aufmerksamkeit. Bei jedem
Lauf `python3 -I ergebnis_analyse.py verdichtung` prüfen; jeder gemeldete Anlass ergibt Vorschläge:

- **`abschnitt_voll`** (mehr als 8 Einsichten): Einsichten, die dieselbe Lage beschreiben, als `zusammenfassen`; wo
  nichts doppelt ist, die schwächste [leicht]-Einsicht ohne neuen Fall als `streichen`.
- **`datei_lang`** (mehr als 200 Zeilen): dasselbe für die längsten Abschnitte; Fallbeispiele auf höchstens zwei je
  Einsicht kürzen (das neuere bleibt).
- **`vorlaeufig_bestaetigt`**: `gewicht`, der den Vermerk „vorläufig“ streicht. **`vorlaeufig_unter_druck`**:
  `streichen`.

**Zusammenfassen:** Der neue Text ersetzt alle beteiligten Einsichten. Eine Kennung bleibt – die ältere oder die
treffendere. Die übrigen kommen in `EINSICHTEN.md` unter „Stillgelegte Kennungen“ (`ALT` → `NEU`) und verschwinden aus
Text und Listen; das Regelprotokoll zählt sie unter der verbleibenden weiter. Zeigen zwei Einsichten in verschiedene
Richtungen (Pro und Gegen derselben Lage), stehen sie als ein Eintrag mit beiden Kennungen; keine wird stillgelegt.

Vermerk **vorläufig** (eine Einsicht aus einem Fall): steht hinter dem Gewicht, `[gewichtig · vorläufig]`; die Einsicht
kommt in den Abschnitt ihres Prüfschritts.

## Regel unter Druck

Meldet `ergebnis_analyse.py bericht` eine Regel als `unter_druck` (n ≥ 20, z gegen ihre Richtung), wird daraus ein
Vorschlag `streichen` oder `gewicht` mit den Zahlen in `gegenprobe` (n, Siege, erwartet, A/E, z). Eine Regel wird nur
mit „ja“ des Nutzers gestrichen.

## Integrieren (nach Entscheidung des Nutzers)

- **ja**: den Text unverändert eintragen; neue Einsichten in den Abschnitt ihres Prüfschritts, aus einem Fall mit
  Vermerk „vorläufig“. Bei `zusammenfassen` die alten Einträge entfernen und stillgelegte Kennungen eintragen.
  **geaendert**: den Text nach der Notiz des Nutzers umschreiben (Abschnitt „Schreiben für den Durchgang“) und vor dem
  Eintragen im Chat zeigen. **nein**: nichts eintragen; die Notiz ist die Begründung.
- Kennungen bleiben dauerhaft (Regel in `LERNSCHLEIFE.md` des Durchgang-Skills).
- Danach **einmal** den Testsatz für alle eingetragenen Änderungen zusammen (`claude_projekt/aufgabe_testsatz.md`,
  gestuft). Zeigt er einen **Rückschritt**, dem Nutzer den Konflikt zeigen: Testfall, sein damaliges Urteil, das
  Urteil mit der neuen Regel. Er entscheidet: Regel umformulieren oder das erwartete Urteil im Testfall ändern. Eine
  Änderung am Testfall bekommt in `tests/testsatz_durchgang/erwartet.json` beim Kandidaten `geaendert` mit Datum und
  Grund.
