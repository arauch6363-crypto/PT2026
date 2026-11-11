---
name: rennkarten-durchgang-neu
description: "Entwurf v1 (parallel zum alten rennkarten-durchgang): Wählt auf einer französischen Galopp-Racecard (Vollblut, PT2026-HTML-Karte) aus den Value-Kandidaten (Festkurs × Modell-Siegchance − 1 > 0) die Siegwetten aus, die der Nutzer tatsächlich spielen würde – je Kandidat Pro-Argumente, Gegenargumente und Fragezeichen, Gesamturteil mit Leitfrage „reicht es für den Sieg?“, Rennvergleich, eigene Kursspanne, Mindestquote und Einheiten. Verwenden, wenn eine Karte oder einzelne Rennen auf Wetten durchgegangen werden sollen."
---

# Rennkarten-Durchgang (neu, v1)

Aus dem Interview vom 10./11.11.2026 (`docs/interview_rennkarten_durchgang.md`). Begriffe stehen in `GLOSSARY.md` im
Repo-Hauptordner und werden hier nicht wiederholt – vor dem ersten Durchgang lesen. Daten: `DATEN.md`. Beispiele:
`FAELLE.md`. Der alte Skill `rennkarten-durchgang` bleibt bis zum Abschluss der Erprobung bestehen.

## Ziel und Leitfrage

Es geht um **Siegwetten zum Festkurs**. Ausgangsmenge sind nur **Kandidaten** (Value > 0, keine Kursgrenze); alle
anderen Starter werden nur als Gegner betrachtet. Über jeden Kandidaten fällt ein **Gesamturteil**: Wette, kleine
Wette oder keine Wette. Gerechnet wird dabei nicht – der Nutzer wettet, wenn ihn ein Pferd insgesamt überzeugt.

Die **Leitfrage** jedes Urteils: **Reicht es für den Sieg?** Ein Pferd, das solide laufen und im Geld landen wird, ist
noch keine Siegwette. Gemessen wird das an der besten zu heute passenden Leistung (ARR im Referenzlauf) gegen die
besten Pferde des heutigen Feldes.

Der Modell-Value ist **nur der Filter**, welche Pferde angesehen werden. Ob der Festkurs reicht, entscheidet die
**eigene Kursspanne** (siehe Gesamturteil): Ein Pferd mit +29 % Modell-Value kann zu kurz sein, eines mit +3 % lang
genug.

## Ablauf

1. **Fakten ziehen.** `python3 -I .claude/skills/rennkarten-durchgang-neu/scripts/blatt.py KARTE.html` zeigt die
   Übersicht (Rennen mit Kandidaten, Festkurs-Stand). Mit Bahn oder Rennen (`STRASBOURG`, `R2C5`) als weiteres
   Argument druckt es je Rennen den Kopf und je Kandidat das Blatt. Uhrzeit gegen den Start prüfen (französische
   Zeit); ist ein Rennen schon gelaufen oder in wenigen Minuten, das sagen.
2. **Rennen lesen** (Kopf des Blatts): Rennart, Klasse (Klassenindex), Feldgröße, Bodenangabe und Bodengruppe,
   Distanz, Bahn und Richtung, erwartetes Tempo mit Laufstilen, FK-Favorit, Top-ARR und Top-Valeur im Feld,
   Höchstgewicht. Nur Vollblut; Araber, Anglo-Araber, AQPS nicht.
3. **Je Kandidat die Prüfliste** (nächster Abschnitt) – Ergebnis: Pro-Argumente, Gegenargumente, Fragezeichen.
4. **Gesamturteil** je Kandidat mit eigener Kursspanne.
5. **Rennvergleich** bei mehreren Kandidaten: nach Beweislage ordnen, Grenze ziehen.
6. **Ausgabe** wie unten.

## Prüfliste je Kandidat

Reihenfolge wie der Nutzer sie geht. Jeder Punkt kann Pro-Argument, Gegenargument oder Fragezeichen liefern.

1. **Ausgangslage.** Value und **Modell-Rang relativ zur Feldgröße** (vorderes/mittleres/hinteres Drittel; ein
   hinterer Rang ist ein Gegenargument, ein vorderer mit solidem Value „erstmal sehr positiv“). **Exposure** relativ
   zum Alter (21 Starts als 3-Jähriger sind sehr viel; 4-jährig mit 25 Starts gilt noch als „relativ jung“).
   **Marke** gegen letzte Sieg- bzw. Platzmarke. Kennzeichen **CGD** (auf Bahn, Distanz, Boden gewonnen) „lässt
   aufhorchen“.
2. **Letzter Lauf im Zusammenhang.** Welches Rennen, welche Klasse, welche Bahn (groß oder Provinz), welcher Boden,
   wie weit geschlagen, Kommentar und Rennverlauf. Ein schwacher Lauf unter ganz anderen Bedingungen (andere
   Distanz, anderer Boden, nicht weit geschlagen) darf übergangen werden. „Nicht weit geschlagen in stärkerem Rennen“
   zählt mehr als die Platzierung.
3. **Referenzlauf.** Der jüngste Lauf unter heutigen Bedingungen (Blatt: `≈heute`, `gleiche Bahn`, `sehr weich`):
   Platz, Abstand, Marke damals gegen heute, **ARR dort gegen Top-ARR im heutigen Feld** (Leitfrage), welche heutigen
   Gegner er dort geschlagen hat, ob das Rennen **aufgewertet** ist. Gestörte Läufe (Kommentar: behindert, eingeklemmt,
   „Nase im Wind“/ohne Deckung, am Rand galoppiert; Blatt: gegen den Verlauf, Zwischenfall) nicht für bare Münze
   nehmen – sie unterschätzen das Pferd. Kein Referenzlauf ist selbst ein Fragezeichen. Ist der Referenzlauf schlecht
   und gibt es kein Argument, warum es heute besser sein sollte, ist das ein starkes Gegenargument.
4. **Vorlieben (Gesamtbilanz), dann Abstammung.** (Abstammung differenziert lesen: z. B. Frankels mögen sehr
   weichen Boden manchmal nicht – Souple ist dafür nicht weich genug.) Boden, Distanz, Bahn, Richtung, Ausrüstung aus den **Vorlieben**
   des Blatts – nie nur aus den letzten Formzeilen (die zeigen höchstens sieben Läufe). Bei Très souple und weicher
   zählt die **genaue Bodenangabe**: ein Lauf genau auf diesem Boden ist ein starkes Argument. Abstammung (alle Skalen: Boden, Distanz, Belag, Reife;
   Gesamtwert) wiegt umso mehr, je dünner die eigene Bilanz unter den heutigen Bedingungen ist – bei wenig gelaufenen
   Pferden kann eine klar unpassende Abstammung allein die Wette kippen (Littoral Nord). Sonst ergänzend,
   vor allem bei dünner eigener Bilanz.
5. **Trainer und Jockey.** Trainer: Form 30 Tage (kalt = Gegenargument, abgestuft), Bilanz auf der Bahn (kann eine
   kalte Form ausgleichen), Spezialität (Rennart, Alter, Debütanten), Stallgröße und -erfolg (kleiner Stall ohne Sieg
   in zwei Jahren = Gegenargument; klein, aber „geschickt operierend“ = neutral bis Pro). Jockey: Bilanz auf der Bahn,
   kennt das Pferd (Siege zusammen = Pro), Jockey-A/E (holt mehr heraus = Pro), **Gespann Trainer + Jockey** – zählt
   bei genug Starts mehr als die Einzelbilanzen.
6. **Umstände heute.** Box (nur `signifikant` zählt), Gewicht (Höchstgewicht bzw. ab ca. 62 kg auf Très souple oder
   schwerer = Gegenargument), Tempo gegen Laufstil (Führender bei schnellem Tempo mit mehreren Führenden = Gegen;
   Pferd von hinten bei schnellem Tempo = Pro), Startfolge (ab etwa 4 Starts in 6 Wochen = Gegenargument, „irgendwann
   ist die Luft raus“), Bahnkategorie (von großen Bahnen in die Provinz = Pro, umgekehrt Gegen), Reise (britischer
   Trainer = Pro; spanisch, deutsch, weit reisend französisch nur begrenzt). Crible und Rennkommentar sind Kontext.
7. **Gesamturteil** – nächster Abschnitt.

### Fragezeichen (unbewiesen, offene Liste)

Erstmals diese Distanzgruppe (auch Distanzwechsel nach unten, gemildert, wenn das Pferd vorne mitläuft) · erstmals
diese Bodenangabe ab Très souple · erstmals dieser Belag · erstmals Scheuklappen oder andere Ausrüstung („warum
heute?“) · Bewährung nur aus tieferer Klasse (z. B. Claimer) oder erstmals deutlich höhere Klasse · Rückkehr nach
langer Pause · erstmals Wallach · Trainerwechsel · **Aufgewicht** (umso größer, je exposed) · erster Start auf einer
Bahn mit Eigenheiten (Strasbourg, Fontainebleau) · Klassenfrage (kleiner Stall, Formen nur aus schwachen Rennen) ·
nicht einzuordnende Auslandsformen.

### Typische Gegenargumente

Hinterer Modell-Rang · schwacher Referenzlauf ohne Grund zur Steigerung · ARR deutlich unter den Besten im Feld ·
selten gewinnend (viele Plätze, kaum Siege) · kalter Trainer (abgestuft) · Ausrüstung fällt weg, mit der die besten
Läufe kamen · in der heutigen Richtung klar schlechter · signifikant schlechte Box · Höchstgewicht auf sehr weichem
Boden · dichte Startfolge · Formen „weit weg von dem, was benötigt wird“ · vorne laufend gegen schnelles Tempo · Stute
gegen Hengste (bei jungen Pferden, leicht) · Sieg, bei dem das Rennen den Vorderen half und das Pferd vorne lief
(etwas weniger wert) · im direkten Vergleich hinter einem heutigen Gegner.

### Typische Pro-Argumente

Vorderer Modell-Rang mit solidem Value · CGD · Referenzlauf unter heutigen Bedingungen mit gutem ARR · Bahnbewährung
(gewonnen oder platziert) · Bewährung genau auf der heutigen Bodenangabe · gegen den Verlauf gut gelaufen · gestörter
letzter Lauf · Marke deutlich unter letzter Sieg-/Platzmarke · Trainer heiß oder auf der Bahn stark · Jockey kennt
das Pferd · starkes Gespann · Abstieg in die Provinz · Abstieg aus stärkeren Rennen (nur wenn diese Rennen nicht abgewertet sind) · britischer Trainer · unexposed mit Steigerungspotenzial ·
„erster Ansatz“ nach einer Reihe schwacher Läufe.

## Gesamturteil

Je Kandidat: Pro-Argumente, Gegenargumente, Fragezeichen, dann die **eigene Kursspanne** – grob, ehrlich, ohne
Rechnung („fair eher 8–10“). Gewettet wird, wenn der Festkurs klar über der Spanne liegt und die Leitfrage mit „ja,
kann reichen“ beantwortet ist. Mindestquote = unterer Rand der Spanne.

- **Wette** = 1 Einheit. **Kleine Wette** = ½ Einheit: interessant, aber „da fehlt einiges“ (z. B. erster Ansatz
  nach vielen schwachen Läufen, Value dünn).
- **Keine Wette**, wenn die Fragezeichen überwiegen, die Leitfrage verneint wird oder der Festkurs die eigene
  Einschätzung nicht übersteigt.

**Faustregel** (Orientierung, keine Rechenregel; Abweichungen ausdrücklich nennen):

- Value nahe 0 (bis etwa +5 %): nur bei klarer, überzeugender Beweislage (z. B. Algeciras: CGD, Bewährung auf sehr
  weichem Boden, Marke unter letzter Platzmarke) – und nur, wenn die eigene Spanne unter dem Festkurs liegt.
- +5 % bis +50 %: höchstens ein Fragezeichen und kein gewichtiges Gegenargument.
- Über +50 %: ein bis zwei Fragezeichen tragbar, **wenn genug für das Pferd spricht**. Viel Value ohne Pro-Argumente
  (Interactiv) oder mit Aufgewicht, Klassenfrage und Höchstgewicht auf schwerem Boden zusammen (Verdansk) reicht nicht.
- **Sehr hoher Value (etwa über +100 %) ist ein Warnsignal**, wenn er auf Formen beruht, die das Modell schlecht
  bewerten kann (Auslandsformen, externe Läufe, wenig Daten): Dann ist eher das Modell unsicher als der Markt falsch –
  eher keine Wette (vorläufig, ein Fall: Arkansas).
- Debütanten: nur wenn der Stall Debütanten bzw. Zweijährige siegfertig bringt **und** die Abstammung passt;
  ein Stall ohne Sieg in den letzten 20 Starts „spricht Bände“.

## Rennvergleich

Bei mehreren Kandidaten im selben Rennen: nach Beweislage ordnen und eine Grenze ziehen; gewettet wird nur, wer klar
überzeugt – in der Regel höchstens zwei. Auch der beste Kandidat kann unter der Grenze liegen (keine Wette im Rennen).

## Ausgabe

Je Rennen:

```
## R2C7 Strasbourg 14:24 – Handicap 4j+, 2350 m, Très souple, 13 Starter (Klasse sehr schwach, Tempo schnell)
**5 Algeciras** – FK 13 · Modell 7,9 % (Rang 5/13) · Value +3 %
- Pro: …
- Gegen: …
- Fragezeichen: …
- Urteil: **Wette (1 Einheit)** – fair eher 9–11, Mindestquote 11. Ausschlag: …
…
Rennvergleich: Algeciras > Cole Chop > Lady Madeira > Afterglow > Go For It – Grenze nach Platz 2.
```

Am Ende eine Wett-Tabelle (Rennen | Zeit | Nr Pferd | Festkurs | Kursspanne | Mindestquote | Einheiten | Ausschlag)
und der Protokoll-Block für die Auswertung, mit **allen** Kandidaten:

```json
{"wetten": [{"race_id": "20261111R2C7", "no": 5, "urteil": "wette", "einheiten": 1, "fk": 13.0,
             "spanne": [9, 11], "mq": 11, "p_modell": 0.079, "value": 0.03}]}
```

`urteil` ist `wette`, `klein` oder `nein` (`einheiten` 1, 0,5, 0). Hinweis: `tipp_auswertung.py` liest noch das alte
Format (`{"tipps": …}` mit Stufen) und muss für diesen Block angepasst werden.

## Lernschleife

Weicht der Nutzer von einem Urteil ab, kommt der Fall mit seinem Ausschlag-Satz in `FAELLE.md`. Faustregeln und
Listen ändern sich erst, wenn sich ein Muster wiederholt; neue Begriffe gehen in `GLOSSARY.md`.
