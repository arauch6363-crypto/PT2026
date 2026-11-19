---
name: ergebnis-analyse
description: "Gleicht die Durchgänge eines Renntags (Skill rennkarten-durchgang-neu) mit dem Einlauf ab: je verpasstem Sieger und verlorenem Claude-Tipp, an welcher Regel es lag und welcher Datenpunkt der Karte geholfen hätte, mit Gegenprobe; daraus wörtliche Vorschläge für SKILL.md oder EINSICHTEN.md, über die der Nutzer entscheidet. Verwenden für die Aufgabe „Ergebnisanalyse“ oder wenn ein vergangener Renntag auf Lehren für den Durchgang-Skill durchgesehen werden soll."
---

# Ergebnisanalyse

Grundsatz aus ADR 0003 (`docs/adr/0003-ergebnisanalyse-liefert-vorschlaege.md`): Die Ergebnisanalyse **liefert
Vorschläge, der Nutzer entscheidet**. Ein Fall genügt für einen Vorschlag; ob er sich verallgemeinern lässt, beurteilt
der Nutzer. Begriffe (Siegergruppe, verpasster Sieger, verlorener Claude-Tipp, Vorschlag, Gegenprobe, Regelkennung,
Regelprotokoll) stehen in `GLOSSARY.md`. Der Ablauf mit Drive, Seite und PR steht in
`claude_projekt/aufgabe_ergebnisanalyse.md`; dieser Skill ist der Urteilsteil.

Der Skill, über den geurteilt wird, ist `.claude/skills/rennkarten-durchgang-neu/` (`SKILL.md`, `EINSICHTEN.md`). Vor
dem ersten Fall beide lesen: Ein Vorschlag muss wissen, was schon dasteht.

## Eingang

`analyse_JJJJMMTT.json` aus `ergebnis_analyse.py material`: je Rennen mit Durchgang die Sieger mit Siegergruppe, alle
Kandidaten (Urteil, Festkurs, Platz, Pro/Gegen/Fragezeichen, Ausschlag, zitierte Kennungen) und die Maßstäbe; dazu
`faelle` (Treffer, verpasste Sieger, verlorene Tipps) und `zaehlung`. Die Mechanik ist dort erledigt – nichts davon
nachrechnen. Fakten zur Karte nur über
`python3 -I .claude/skills/rennkarten-durchgang-neu/scripts/blatt.py KARTE RxCy`.

## Je Fall

Bearbeitet werden **verpasste Sieger** und **verlorene Claude-Tipps**. Treffer bekommen nur eine Zeile („Regel X trug“).
Sieger, die Maßstab oder sonstiger Sieger waren, werden nur gezählt: Sie betreffen den Kandidaten-Filter, nicht den
Skill.

1. **Regel.** Woran hing das Urteil? Die Kennung aus dem Ausschlag; fehlt sie (Durchgänge vor den Kennungen), die
   Regel aus dem Text zuordnen und mit „(zugeordnet)“ kennzeichnen. Passt keine: „Ermessen“ – eine Häufung davon ist
   selbst ein Befund: Dort fehlt eine Regel.
2. **Datenpunkt.** Was auf der Karte hätte das richtige Urteil gestützt? Nur Angaben, die **vor dem Rennen** im Blatt
   standen. Nachwissen ist ausgeschlossen: Einlauf, Endquote, Rennkommentar und Tracking dieses Rennens. Zitat aus dem
   Blatt, nicht nacherzählt. Kein Datenpunkt zu finden ist ein gültiges Ergebnis („Rennen nicht lesbar, Sieg aus dem
   Nichts“) – dann kein Vorschlag.
3. **Gegenprobe.** Bei welchen Verlierern desselben Tages (Kandidaten und Maßstäbe aller Rennen im Material) stand
   derselbe Datenpunkt ebenfalls? Mit Namen und Anzahl, z. B. „2 von 9 Verlierern mit CGD: Afterglow, Tulpar“. Eine
   Gegenprobe, die den Datenpunkt bei vielen Verlierern zeigt, gehört in den Vorschlag, auch wenn sie ihn schwächt.
4. **Schluss.** Hätte eine andere Gewichtung oder Regel das Urteil gedreht, ohne bei den Verlierern der Gegenprobe
   falsch zu drehen? Ja → Vorschlag. Nein → Fall ohne Vorschlag mit einem Satz Befund.

## Vorschlag

Jeder Vorschlag ist eine **konkrete Textänderung**, über die der Nutzer mit Ja, Nein oder Ändern entscheiden kann:

| Feld | Inhalt |
|---|---|
| `titel` | ein Satz, was sich ändert |
| `fall` | `verpasster_sieger` oder `verlorener_tipp` (bei einer Regel unter Druck: `regel_unter_druck`) |
| `rennen`, `race_id`, `no`, `horse` | der Fall |
| `durchgang` | ein Satz: Urteil, Festkurs, woran es hing |
| `datenpunkt` | Zitat aus dem Blatt |
| `gegenprobe` | höchstens drei Sätze: wie viele Verlierer mit Namen, was den Vorschlag schwächt |
| `art` | `neu`, `aendern`, `gewicht` oder `streichen` |
| `zieldatei` | `SKILL.md` (Regel, Liste) oder `EINSICHTEN.md` (Gewichtung, typischer Fehler) |
| `kennung` | bestehende Kennung oder eine neue nach dem Muster in `SKILL.md` („Kennungen“) |
| `text` | **wörtlich** der neue oder geänderte Text, so wie er in der Datei stehen soll, mit Fallbeispiel in *kursiv* |
| `gewicht` | `ausschlaggebend`, `gewichtig` oder `leicht` – Claudes Vorschlag |

### So schreibt sich `text` und `titel`

Der Nutzer liest den Text so, wie er in `EINSICHTEN.md` stehen wird – er muss ihn ohne Blatt verstehen:

- **Kurz:** eine Regel in höchstens zwei Sätzen (etwa 35 Wörter), dahinter das Fallbeispiel in *kursiv* mit Pferd und
  Datum. So lang wie die Einsichten, die schon dastehen. Eine Ausnahme höchstens als Halbsatz.
- **Seine Wörter:** Begriffe aus `GLOSSARY.md` (Referenzlauf, Maßstab, Bodenangabe, Klassenindex, Rennverlauf,
  Aufgewicht). Markierungen und Kürzel aus dem Blatt kommen nicht vor – `≈heute` heißt im Text „Referenzlauf“ bzw.
  „Lauf unter heutigen Bedingungen“, `ber.` entfällt, „gegen den Verlauf“ heißt „gegen den Rennverlauf gelaufen“,
  „Zwischenfall“ heißt „behindert, eingeklemmt“. Wörter wie „Blatt-Beleg“ oder „Datenpunkt“ gehören nicht in den Text.
- **Zahlen nur, wo die Regel an ihnen hängt**, gerundet („etwa 2 Punkte ARR“, „5 Längen und mehr“).
- **Positiv formuliert:** was gilt, nicht welche andere Regel nicht gilt.

Blattzitate, Klassenindizes und Rechenwege stehen in `datenpunkt` und `gegenprobe`, nie in `text`. Beispiel:

> `G-MASSSTAB-BESSER` Lief ein Maßstab in seinem Referenzlauf klar besser als der Kandidat in seinem (etwa 2 Punkte ARR
> mehr, in einem stärkeren Rennen), reicht es bei kurzer Quote nicht für eine Wette. *X Rays 15.11.*

Mehrere Fälle, die auf dieselbe Regel zeigen, ergeben **einen** Vorschlag mit allen Fällen. Vorschläge nach Stärke
ordnen: klare Gegenprobe und klarer Regelbezug zuerst. Ein früher abgelehnter Vorschlag (`auswertung/vorschlaege.csv`,
`entscheidung` nein) kommt nur mit neuen Belegen wieder, und dann mit Verweis auf die Ablehnung.

## Regel unter Druck

Meldet `ergebnis_analyse.py bericht` eine Regel als `unter_druck` (n ≥ 20, z gegen ihre Richtung), wird daraus ein
Vorschlag `streichen` oder `gewicht` mit den Zahlen in `gegenprobe` (n, Siege, erwartet, A/E, z). Eine Regel wird nie
ohne „ja“ des Nutzers gestrichen.

## Integrieren (nur nach Entscheidung des Nutzers)

- **ja**: den Text unverändert eintragen. **geaendert**: den Text nach der Notiz des Nutzers umschreiben und vor dem
  Eintragen im Chat zeigen. **nein**: nichts eintragen; die Notiz ist die Begründung.
- Kennungen bleiben dauerhaft (Regel in `SKILL.md`, Lernschleife).
- Danach den Testsatz laufen lassen (`claude_projekt/aufgabe_testsatz.md`). Zeigt er einen **Rückschritt**, dem Nutzer
  den Konflikt zeigen: Testfall, sein damaliges Urteil, das Urteil mit der neuen Regel. Er entscheidet: Regel
  umformulieren oder das erwartete Urteil im Testfall ändern. Eine Änderung am Testfall bekommt in
  `tests/testsatz_durchgang/erwartet.json` beim Kandidaten `geaendert` mit Datum und Grund.
