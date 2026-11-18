---
name: rennkarten-durchgang-neu
description: "Wählt auf einer französischen Galopp-Racecard (Vollblut, PT2026-HTML-Karte) aus den Value-Kandidaten (Festkurs × Modell-Siegchance − 1 über 0) die Siegwetten aus, die der Nutzer tatsächlich spielen würde – je Kandidat Pro-Argumente, Gegenargumente und Fragezeichen, Gesamturteil mit Leitfrage „reicht es für den Sieg?“, Rennvergleich, eigene Kursspanne, Mindestquote und Einheiten. Verwenden, wenn eine Karte oder einzelne Rennen auf Wetten durchgegangen werden sollen."
---

# Rennkarten-Durchgang

Aus dem Interview vom 10./11.11.2026 (`docs/interview_rennkarten_durchgang.md`). Begriffe stehen in `GLOSSARY.md`
(im Repo-Hauptordner; im hochgeladenen claude.ai-Skill im Skill-Ordner) und werden hier nicht wiederholt – vor dem
ersten Durchgang lesen. Daten: `DATEN.md`. **Gewichtung und typische Fehler: `EINSICHTEN.md`** – vor dem ersten Rennen
lesen; jedes Argument im Urteil so schwer nehmen, wie es dort eingestuft ist.
Automatisch läuft der Skill über die Aufgabe „Racecard-Durchgang API“ (`claude_projekt/aufgabe_durchgang.md`, je Rennen
ein Subagent); von Hand gilt dasselbe Vorgehen und dasselbe Ergebnisformat.

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

1. **Fakten ziehen.** `python3 -I <Skill-Ordner>/scripts/blatt.py KARTE` zeigt die Übersicht (Rennen mit
   Kandidaten, Festkurs-Stand). KARTE ist `racecard_JJJJMMTT_daten.json.gz` (komprimierte Kartendaten, Normalfall) oder
   die HTML-Karte `racecard_JJJJMMTT.html` bzw. `…_daten.json` – das Skript liest alle drei. Skill-Ordner: in Claude
   Code `.claude/skills/rennkarten-durchgang-neu`, in claude.ai der Ordner, aus dem diese SKILL.md geladen wurde. Nie
   die Karte selbst ausgeben oder einlesen – sie ist über 10 MB groß; nur die Ausgabe des Skripts lesen. Mit Bahn oder
   Rennen (`STRASBOURG`, `R2C5`) als weiteres Argument druckt es je Rennen den Kopf und je Kandidat das Blatt. Uhrzeit gegen den Start prüfen (französische
   Zeit); ist ein Rennen schon gelaufen oder in wenigen Minuten, das sagen.
2. **Rennen lesen** (Kopf des Blatts): Rennart, Klasse (Klassenindex), Feldgröße, Bodenangabe und Bodengruppe,
   Distanz, Bahn und Richtung, erwartetes Tempo mit Laufstilen, FK-Favorit, Top-ARR und Top-Valeur im Feld,
   Höchstgewicht. Nur Vollblut; Araber, Anglo-Araber, AQPS nicht.
3. **Maßstab** (Abschnitt unten) kurz prüfen – das Blatt druckt ihn als `MASSSTAB` mit.
4. **Je Kandidat die Prüfliste** (nächster Abschnitt) – Ergebnis: Pro-Argumente, Gegenargumente, Fragezeichen.
5. **Gesamturteil** je Kandidat mit eigener Kursspanne.
6. **Rennvergleich**: Kandidaten nach Beweislage ordnen, gegen den Maßstab stellen, Grenze ziehen.
7. **Ausgabe** wie unten.

## Maßstab

Je Rennen wird zusätzlich ein Pferd als Vergleichsmaßstab kurz geprüft: der **FK-Favorit**, oder der **Zweite im
Festkurs**, wenn der Favorit selbst Kandidat ist (ist auch der Zweite Kandidat, entfällt der zusätzliche Maßstab). Der
Maßstab ist **nie eine Wette** und braucht keinen Value. Kurz gefasst: beste zu heute passende Leistung (Referenzlauf,
ARR), Beleg für Boden und Distanz, Verbindungen, Laufstil gegen Tempo, größtes Fragezeichen. Jeder Kandidat wird in der
Leitfrage gegen ihn gemessen: Was müsste er besser können als der Maßstab, und ist das belegt? Ist der Maßstab ein
Debütant oder kaum belegt, steht das ausdrücklich im Urteil („Maßstab offen“). Die Kursspanne bleibt eigene
Einschätzung, nicht abgeleitet vom Festkurs des Maßstabs. (Vom Nutzer zur Regel erklärt:
„ohne Referenz gegen das nächstbeste Pferd fehlt die Elle, gegen was man besser sein muss“.)

## Prüfliste je Kandidat

Reihenfolge wie der Nutzer sie geht. Jeder Punkt kann Pro-Argument, Gegenargument oder Fragezeichen liefern.

1. **Ausgangslage.** Value und **Modell-Rang relativ zur Feldgröße** (vorderes/mittleres/hinteres Drittel; ein
   hinterer Rang ist ein Gegenargument, ein vorderer mit solidem Value „erstmal sehr positiv“). **Exposure** relativ
   zum Alter (21 Starts als 3-Jähriger sind sehr viel; 4-jährig mit 25 Starts gilt noch als „relativ jung“).
   **Marke – nur im Handicap:** Dort zählt die heutige Marke gegen die letzte Sieg- bzw. Platzmarke, weil das Gewicht
   die Valeur ausgleicht. **In allen anderen Rennen** (Conditions, Claimer, Listed, Gruppe, Rennart unbekannt) gleicht
   niemand die Valeurs aus: Dort zählt, wer die **höchste gewichtsbereinigte Valeur** im Feld hat (Valeur − Gewicht +
   55, Rang im Blatt). Eine Marke unter der letzten Platzmarke ist dort kein Plus, sondern eher ein Zeichen, dass das
   Pferd nachlässt. Kennzeichen **CGD** (auf Bahn, Distanz, Boden gewonnen) „lässt aufhorchen“.
2. **Letzter Lauf im Zusammenhang.** Welches Rennen, welche Klasse, welche Bahn (groß oder Provinz), welcher Boden,
   wie weit geschlagen, Kommentar und Rennverlauf. Ein schwacher Lauf unter ganz anderen Bedingungen (andere
   Distanz, anderer Boden, nicht weit geschlagen) darf übergangen werden. „Nicht weit geschlagen in stärkerem Rennen“
   zählt mehr als die Platzierung.
3. **Referenzlauf.** Der jüngste Lauf unter heutigen Bedingungen (Blatt: `≈heute`, `gleiche Bahn`, `sehr weich`):
   Platz, Abstand, Marke damals gegen heute (nur im Handicap), **ARR dort gegen Top-ARR im heutigen Feld** (Leitfrage), welche heutigen
   Gegner er dort geschlagen hat, ob das Rennen **aufgewertet** ist. Gestörte Läufe (Kommentar: behindert, eingeklemmt,
   „Nase im Wind“/ohne Deckung, am Rand galoppiert; Blatt: gegen den Verlauf, Zwischenfall) nicht für bare Münze
   nehmen – sie unterschätzen das Pferd. Kein Referenzlauf ist selbst ein Fragezeichen. Ist der Referenzlauf schlecht
   und gibt es kein Argument, warum es heute besser sein sollte, ist das ein starkes Gegenargument.
4. **Vorlieben (Gesamtbilanz), dann Abstammung.** (Abstammung differenziert lesen: z. B. Frankels mögen sehr
   weichen Boden manchmal nicht – Souple ist dafür nicht weich genug.) Boden, Distanz, Bahn, Richtung, Ausrüstung aus den **Vorlieben**
   des Blatts – nie nur aus den letzten Formzeilen (die zeigen höchstens sieben Läufe). **Boden vergleichen:**
   Collant und Lourd bilden zusammen die Gruppe Very slow und sind für uns gleichwertig – ein Lauf auf Collant belegt
   Lourd und umgekehrt. Innerhalb der Gruppe Slow wird unterschieden: Souple belegt Très souple nicht vollständig.
   Ein Lauf auf genau diesem Boden bzw. in dieser Gruppe ist ein starkes Argument.
   **Abstammung nur, wo die eigene Erfahrung fehlt:** Bei viel gelaufenen Pferden zählt die eigene Bilanz auf dem
   Boden, die Abstammungsstatistik ist dann ohne Belang (kein Gegenargument „Muttervater passt nicht“ bei einem
   Pferd, das auf diesem Boden schon gelaufen ist). Wichtig ist die Abstammung (alle Skalen: Boden, Distanz, Belag,
   Reife; Gesamtwert) für junge, wenig gelaufene Pferde und für Pferde, die einen Boden zum ersten bis dritten Mal
   erleben – dort kann eine klar unpassende Abstammung allein die Wette kippen. Bei jungen Pferden
   zählt zusätzlich die **Qualität** der Linie (Blatt: max. Valeur der Nachkommen als Index, Gewinn je Lauf als
   Index), weil sie etwas über das Potenzial sagt.
5. **Trainer und Jockey.** Trainerwechsel in den letzten Läufen beachten (Blatt: „Trainer erst seit N Läufen“).
   Trainer: Form 30 Tage (kalt = Gegenargument, abgestuft), Bilanz auf der Bahn (kann eine
   kalte Form ausgleichen), Spezialität (Rennart, Alter, Debütanten), Stallgröße und -erfolg (kleiner Stall ohne Sieg
   in zwei Jahren = Gegenargument; klein, aber „geschickt operierend“ = neutral bis Pro). Jockey: Bilanz auf der Bahn,
   kennt das Pferd (Siege zusammen = Pro), Jockey-A/E (holt mehr heraus = Pro), **Gespann Trainer + Jockey** – zählt
   bei genug Starts mehr als die Einzelbilanzen.
6. **Umstände heute.** Box (nur `signifikant` zählt), Gewicht (Höchstgewicht bzw. ab ca. 62 kg auf Très souple oder
   schwerer = Gegenargument), Tempo gegen Laufstil (Führender bei schnellem Tempo mit mehreren Führenden = Gegen;
   Pferd von hinten bei schnellem Tempo = Pro), Startfolge (ab etwa 4 Starts in 6 Wochen = Gegenargument, „irgendwann
   ist die Luft raus“), Bahnkategorie (von großen Bahnen in die Provinz = Pro, umgekehrt Gegen), Reise (britischer
   Trainer = Pro; spanisch, deutsch, weit reisend französisch nur begrenzt). Crible und Rennkommentar sind Kontext.
   **Ausrüstungswechsel** (Scheuklappen, australische Scheuklappen) nach den Bilanzen mit und ohne (Blatt:
   „Ausrüstung“) bewerten, nicht nach dem Wechsel an sich:
   - fällt weg, **mit ihr kamen die besten Läufe** → starkes Gegenargument, bei kurzer Quote ausschlaggebend;
   - fällt weg, **mit ihr liefen die Formen auch schwach** → neutral, man probiert etwas Neues;
   - fällt weg, **ohne sie lief das Pferd fast immer** → neutral bis Pro, Rückkehr zum Normalen;
   - **kommt zurück, mit ihr kamen die besten Läufe** → Pro;
   - **erstmals** → Fragezeichen „warum heute?“.
7. **Gesamturteil** – nächster Abschnitt.

### Fragezeichen (unbewiesen, offene Liste)

Erstmals diese Distanzgruppe (auch Distanzwechsel nach unten, gemildert, wenn das Pferd vorne mitläuft) · erstmals
dieser Boden ab Très souple (Collant und Lourd gelten als derselbe Boden) · erstmals dieser Belag · erstmals Scheuklappen oder andere Ausrüstung („warum
heute?“; Wechsel sonst siehe Ausrüstungswechsel in Punkt 6) · Bewährung nur aus tieferer Klasse (z. B. Claimer) oder erstmals deutlich höhere Klasse · Rückkehr nach
langer Pause · erstmals Wallach · Trainerwechsel · **Aufgewicht** (nur im Handicap; umso größer, je exposed) · erster Start auf einer
Bahn mit Eigenheiten (Strasbourg, Fontainebleau) · Klassenfrage (kleiner Stall, Formen nur aus schwachen Rennen) ·
nicht einzuordnende Auslandsformen.

Ein Fragezeichen ist **entkräftet** (zählt nicht oder wird zum Pro-Argument), wenn Belege dafür sprechen: erstmals
eine längere Distanz, aber die Abstammung trägt sie und das Pferd lief bisher umso besser, je weiter der Weg war;
Trainerwechsel zu einem klar starken Stall; Claimer-Sieg, aber vorher schon Handicap-Form auf ähnlicher Marke.
Nicht mechanisch zählen.

### Typische Gegenargumente

Hinterer Modell-Rang · schwacher Referenzlauf ohne Grund zur Steigerung · ARR deutlich unter den Besten im Feld ·
selten gewinnend (viele Plätze, kaum Siege) · kalter Trainer (abgestuft) · Ausrüstung fällt weg, mit der die besten
Läufe kamen (Punkt 6) · in der heutigen Richtung klar schlechter · signifikant schlechte Box · Höchstgewicht auf sehr weichem
Boden · dichte Startfolge · Formen „weit weg von dem, was benötigt wird“ · vorne laufend gegen schnelles Tempo · Stute
gegen Hengste (bei jungen Pferden, leicht) · Sieg, bei dem das Rennen den Vorderen half und das Pferd vorne lief
(etwas weniger wert) · im direkten Vergleich hinter einem heutigen Gegner · **Aufstieg aus Claimern (Verkaufsrennen) ins Handicap** – ausgeglichen
nur durch deutlich höheren Klassenindex der Claimer (nicht bloß ein paar Punkte) oder schon vorhandene
Handicap-Form auf ähnlicher Marke; bei kurzer Quote wiegt es schwerer.

### Typische Pro-Argumente

Vorderer Modell-Rang mit solidem Value · CGD · Referenzlauf unter heutigen Bedingungen mit gutem ARR · Bahnbewährung
(gewonnen oder platziert) · Bewährung genau auf der heutigen Bodenangabe · signifikant gute Box · gegen den Verlauf gut gelaufen · gestörter
letzter Lauf · im Handicap: Marke deutlich unter letzter Sieg-/Platzmarke · außerhalb des Handicaps: höchste
gewichtsbereinigte Valeur im Feld · Trainer heiß oder auf der Bahn stark · Jockey kennt
das Pferd · starkes Gespann · Abstieg in die Provinz · Abstieg aus stärkeren Rennen (nur wenn diese Rennen nicht abgewertet sind) · britischer Trainer · unexposed mit Steigerungspotenzial · Ausrüstung kommt
zurück, mit der die besten Läufe kamen ·
„erster Ansatz“ nach einer Reihe schwacher Läufe.

## Gesamturteil

Je Kandidat: Pro-Argumente, Gegenargumente, Fragezeichen, dann die **eigene Kursspanne** – grob, ehrlich, ohne
Rechnung („fair eher 8–10“). Gewettet wird, wenn der Festkurs klar über der Spanne liegt und die Leitfrage mit „ja,
kann reichen“ beantwortet ist. Mindestquote = unterer Rand der Spanne.

- **Wette** = 1 Einheit. **Kleine Wette** = ½ Einheit: interessant, aber „da fehlt einiges“ (z. B. erster Ansatz
  nach vielen schwachen Läufen, Value dünn).
- **Keine kleine Wette als Ausweg:** Ist das Pferd exposed und sind Trainer oder Jockey schwach bzw. ohne aktuelle
  Form, wird es keine kleine Wette, auch wenn Value, Konstanz oder Marke dafür sprechen. Die kleine Wette ist für
  Pferde, bei denen einiges fehlt, aber die Grundlage stimmt (unexposed, starke Verbindungen),
  nicht für exposed Pferde mit schwachen Verbindungen.
- **Keine Wette**, wenn die Fragezeichen überwiegen, die Leitfrage verneint wird oder der Festkurs die eigene
  Einschätzung nicht übersteigt.

**Faustregel** (Orientierung, keine Rechenregel; Abweichungen ausdrücklich nennen):

- Value nahe 0 (bis etwa +5 %): nur bei klarer, überzeugender Beweislage (z. B. CGD, Bewährung auf sehr
  weichem Boden, Marke unter letzter Platzmarke) – und nur, wenn die eigene Spanne unter dem Festkurs liegt.
- +5 % bis +50 %: höchstens ein Fragezeichen und kein gewichtiges Gegenargument.
- Über +50 %: ein bis zwei Fragezeichen tragbar, **wenn genug für das Pferd spricht**. Viel Value ohne Pro-Argumente
  oder mit Aufgewicht, Klassenfrage und Höchstgewicht auf schwerem Boden zusammen reicht nicht.
- Debütanten: nur wenn der Stall Debütanten bzw. Zweijährige siegfertig bringt **und** die Abstammung passt;
  ein Stall ohne Sieg in den letzten 20 Starts „spricht Bände“.

## Rennvergleich

Bei mehreren Kandidaten im selben Rennen: nach Beweislage ordnen und eine Grenze ziehen; gewettet wird nur, wer klar
überzeugt – in der Regel höchstens zwei. Auch der beste Kandidat kann unter der Grenze liegen (keine Wette im Rennen).
Der Maßstab steht als Bezugslinie dabei (ohne Platz in der Reihenfolge), z. B. „Boomslang > Sir Dasch – Maßstab El
Lagar (2,8): sieglos, ARR 32,4, erstmals 2000 m und PSF – Boomslang auf dem Papier klar besser; Grenze vor Platz 1
(Kurs zu kurz)“.

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
Maßstab 3 Afterglow (FK 6,5): … (kurz, kein Urteil)
Rennvergleich: Algeciras > Cole Chop > Lady Madeira > Afterglow > Go For It – Grenze nach Platz 2.
```

Am Ende eine Wett-Tabelle (Rennen | Zeit | Nr Pferd | Festkurs | Kursspanne | Mindestquote | Einheiten | Ausschlag).

**Ergebnis je Rennen** (dasselbe Format im automatischen Durchgang, geprüft mit `durchgang.rennen_pruefen`, abgelegt
als `durchgang_JJJJMMTT_HHMM.json`, ausgewertet im Value-Dashboard), mit **allen** Kandidaten:

```json
{"race_id": "20261111R2C7", "status": "bearbeitet", "vergleich": "Algeciras > Cole Chop > … – Grenze nach Platz 2",
 "hinweis": "", "massstab": {"no": 3, "horse": "…", "fk": 6.5, "befund": "…"},
 "kandidaten": [{"no": 5, "horse": "ALGECIRAS", "urteil": "wette", "fk": 13.0, "mq": 11, "spanne": [9, 11],
                 "p_modell": 0.079, "value": 0.03, "pro": ["…"], "gegen": ["…"], "fragen": ["…"],
                 "ausschlag": "…"}]}
```

`urteil` ist `wette`, `klein` oder `nein` (1, ½, 0 Einheiten). `massstab` steht nicht unter den Kandidaten und zählt
nie als Claude-Tipp (`null`, wenn kein zusätzlicher Maßstab). `status`: `bearbeitet`, bei Araber/AQPS `araber`
(Kandidaten leer).

## Lernschleife

Gilt nur für die Durchsicht mit dem Nutzer, nicht für den automatischen Durchgang.

- **Je besprochenem Rennen** ins Fallarchiv des Repos (eine Zeile je Kandidat, Art **Übereinstimmung**, **Claude
  lernt** oder **Claudes Sicht behalten**; Ort und Format in `claude_projekt/task.md`). Das Archiv gehört nicht zum
  Skill und wird beim Durchgang nicht gelesen.
- **Am Ende der Sitzung verdichten:** Änderungen an `EINSICHTEN.md` (Gewicht aus der Argumentation des Nutzers, ein
  Beispiel je Einsicht, Doppeltes zusammenfassen) und an `SKILL.md` vorschlagen, Zustimmung abwarten, dann eintragen.
- **Regel in `SKILL.md`** erst, wenn zwei Fälle „Claude lernt“ in dieselbe Richtung zeigen oder der Nutzer sie
  ausdrücklich zur Regel erklärt; bis dahin unter „Vorläufig“ in `EINSICHTEN.md`. Abweichende, vom Nutzer nicht
  abgelehnte Urteile und Lagen, in denen der Nutzer selbst schwankte, kommen unter „Ermessen“.
- Widerspricht ein neues Urteil einer Regel oder Einsicht, das ansprechen (Ausnahme oder Regel zu streng?). Neue
  Begriffe gehen in `GLOSSARY.md`.
