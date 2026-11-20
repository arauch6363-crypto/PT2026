---
name: rennkarten-durchgang-neu
description: "Wählt auf einer französischen Galopp-Racecard (Vollblut, PT2026-HTML-Karte) aus den Value-Kandidaten (Festkurs × Modell-Siegchance − 1 mindestens +5 %) die Siegwetten aus, die der Nutzer tatsächlich spielen würde – je Kandidat Pro-Argumente, Gegenargumente und Fragezeichen, Gesamturteil mit Leitfrage „reicht es für den Sieg?“, Rennvergleich, eigene Kursspanne, Mindestquote und Einheiten. Verwenden, wenn eine Karte oder einzelne Rennen auf Wetten durchgegangen werden sollen."
---

# Rennkarten-Durchgang

Aus dem Interview vom 10./11.11.2026 (`docs/interview_rennkarten_durchgang.md`). Begriffe stehen in `GLOSSARY.md`
(im Repo-Hauptordner; im hochgeladenen claude.ai-Skill im Skill-Ordner) und werden hier nicht wiederholt – vor dem
ersten Durchgang lesen. Daten: `DATEN.md`. **Gewichtung und typische Fehler: `EINSICHTEN.md`** – vor dem ersten Rennen
lesen; jedes Argument im Urteil so schwer nehmen, wie es dort eingestuft ist.
Automatisch läuft der Skill über die Aufgabe „Racecard-Durchgang API“ (`claude_projekt/aufgabe_durchgang.md`, je Rennen
ein Subagent); von Hand gilt dasselbe Vorgehen und dasselbe Ergebnisformat.

## Ziel und Leitfrage

Es geht um **Siegwetten zum Festkurs**. Ausgangsmenge sind nur **Kandidaten** (Value mindestens +5 %, weil 5 % Steuer vom Gewinn abgehen; keine
Kursgrenze); alle
anderen Starter werden nur als Gegner betrachtet. Über jeden Kandidaten fällt ein **Gesamturteil**: Wette, kleine
Wette oder keine Wette. Gerechnet wird dabei nicht – der Nutzer wettet, wenn ihn ein Pferd insgesamt überzeugt.

Die **Leitfrage** jedes Urteils: **Reicht es für den Sieg?** Ein Pferd, das solide laufen und im Geld landen wird, ist
noch keine Siegwette. Gemessen wird das an der besten zu heute passenden Leistung (ARR im Referenzlauf) gegen die
besten Pferde des heutigen Feldes.

Der Modell-Value ist **nur der Filter**, welche Pferde angesehen werden. Ob der Festkurs reicht, entscheidet die
**eigene Kursspanne** (siehe Gesamturteil): Ein Pferd mit +29 % Modell-Value kann zu kurz sein, eines mit +6 % lang
genug.

**Kennungen.** Jedes Argument der Listen unten und in `EINSICHTEN.md` trägt eine Kennung wie
`G-AUSRUESTUNG-WEG` (F = Fragezeichen, G = Gegen, P = Pro, U = Urteil). Jeder Satz in Pro, Gegen und Fragezeichen,
der sich auf eine solche Regel stützt, endet mit ihrer Kennung in Klammern, z. B. „Ohne Scheuklappen, mit denen die
drei besten Läufe kamen (G-AUSRUESTUNG-WEG)“. Der Satz **Ausschlag** nennt die Kennung der Regel, die das Urteil
entschieden hat, oder das Wort „Ermessen“, wenn keine passt. Nur Kennungen verwenden, die in `SKILL.md` oder
`EINSICHTEN.md` stehen; die Prüfung (`durchgang.rennen_pruefen`) lehnt unbekannte ab. Die Ergebnisanalyse zählt
daran, wie oft eine Regel griff und wie es ausging.

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
3. **Maßstäbe** (Abschnitt unten) kurz prüfen – das Blatt druckt sie als `MASSSTAB 1/2` und `2/2` mit.
4. **Je Kandidat die Prüfliste** (nächster Abschnitt) – Ergebnis: Pro-Argumente, Gegenargumente, Fragezeichen.
5. **Gesamturteil** je Kandidat mit eigener Kursspanne.
6. **Rennvergleich**: Kandidaten nach Beweislage ordnen, gegen die Maßstäbe stellen, Grenze ziehen.
7. **Ausgabe** wie unten.

## Maßstab

Je Rennen werden zusätzlich **zwei Pferde als Maßstab** kurz geprüft: die **zwei Besten im Festkurs, die keine
Kandidaten sind** (Kandidaten werden übersprungen, sie werden ohnehin geprüft). Ist der FK-Favorit kein Kandidat, ist
er Maßstab 1; sonst rückt der nächstbeste ohne Kandidaten-Value nach. Ein Maßstab ist **nie eine Wette** und braucht
keinen Value. Je Maßstab kurz: beste zu heute passende Leistung (Referenzlauf, ARR), Beleg für Boden und Distanz,
Verbindungen, Laufstil gegen Tempo, größtes Fragezeichen. Zusammen zeigen die beiden, **was in diesem Rennen für den
Sieg verlangt ist**. Jeder Kandidat wird in der Leitfrage gegen sie gemessen (`U-MASSSTAB`): Was müsste er besser können als die
Maßstäbe, und ist das belegt? Ist ein Maßstab Debütant oder kaum belegt, steht das ausdrücklich im Urteil („Maßstab
offen“). Die Kursspanne bleibt eigene Einschätzung, nicht abgeleitet von den Festkursen der Maßstäbe. (Vom Nutzer zur
Regel erklärt: „ohne Referenz gegen das nächstbeste Pferd fehlt die Elle, gegen was man besser sein muss“; zweiter
Maßstab auf seinen Wunsch.)

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
6. **Umstände heute.** Box (nur `signifikant` zählt), Gewicht (ab etwa 62 kg auf Très souple oder
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

- `F-DISTANZ-NEU` erstmals diese Distanzgruppe (auch Distanzwechsel nach unten, gemildert, wenn das Pferd vorne mitläuft)
- `F-BODEN-NEU` erstmals dieser Boden ab Très souple (Collant und Lourd gelten als derselbe Boden)
- `F-BELAG-NEU` erstmals dieser Belag
- `F-AUSRUESTUNG-NEU` erstmals Scheuklappen oder andere Ausrüstung („warum heute?“; Wechsel sonst siehe Ausrüstungswechsel
  in Punkt 6)
- `F-KLASSE-HOCH` Bewährung nur aus tieferer Klasse (z. B. Claimer) oder erstmals deutlich höhere Klasse
- `F-PAUSE` Rückkehr nach langer Pause
- `F-WALLACH` erstmals Wallach
- `F-TRAINERWECHSEL` Trainerwechsel
- `F-AUFGEWICHT` **Aufgewicht** (nur im Handicap; umso größer, je exposed)
- `F-BAHN-EIGENHEIT` erster Start auf einer Bahn mit Eigenheiten (Strasbourg, Fontainebleau)
- `F-KLASSENFRAGE` Klassenfrage (kleiner Stall, Formen nur aus schwachen Rennen)
- `F-AUSLAND` nicht einzuordnende Auslandsformen

Ein Fragezeichen ist **entkräftet** (zählt nicht oder wird zum Pro-Argument), wenn Belege dafür sprechen: erstmals
eine längere Distanz, aber die Abstammung trägt sie und das Pferd lief bisher umso besser, je weiter der Weg war;
Trainerwechsel zu einem klar starken Stall; Claimer-Sieg, aber vorher schon Handicap-Form auf ähnlicher Marke.
Nicht mechanisch zählen.

### Typische Gegenargumente

- `G-RANG-HINTEN` hinterer Modell-Rang
- `G-REFERENZ-SCHWACH` schwacher Referenzlauf ohne Grund zur Steigerung
- `G-ARR-UNTER` ARR deutlich unter den Besten im Feld
- `G-SELTEN-SIEG` selten gewinnend: weniger als ein Sieg aus etwa 14 Starts, dazu viele Plätze. Wer öfter gewinnt,
  ist kein seltener Sieger, auch nach einer Reihe zweiter Plätze. *Tipinso 16.11.*
- `G-TRAINER-KALT` kalter Trainer (abgestuft)
- `G-AUSRUESTUNG-WEG` Ausrüstung fällt weg, mit der die besten Läufe kamen (Punkt 6)
- `G-RICHTUNG` in der heutigen Richtung klar schlechter
- `G-BOX` signifikant schlechte Box
- `G-GEWICHT-BODEN` Gewicht ab etwa 62 kg auf Très souple oder schwerer. Ein Höchstgewicht darunter ist kein
  Gegenargument; außerhalb des Handicaps steckt es schon in der gewichtsbereinigten Valeur. *Tipinso 16.11. (59,5 kg
  auf Collant)*
- `G-STARTFOLGE` dichte Startfolge
- `G-FORM-WEIT-WEG` Formen „weit weg von dem, was benötigt wird“
- `G-TEMPO-VORNE` vorne laufend gegen schnelles Tempo
- `G-STUTE` Stute gegen Hengste (bei jungen Pferden, leicht)
- `G-SIEG-MIT-VERLAUF` Sieg, bei dem das Rennen den Vorderen half und das Pferd vorne lief (etwas weniger wert)
- `G-DIREKT-HINTER` im direkten Vergleich hinter einem heutigen Gegner
- `G-CLAIMER-AUFSTIEG` **Aufstieg aus Claimern (Verkaufsrennen) ins Handicap** – ausgeglichen nur durch deutlich höheren
  Klassenindex der Claimer (nicht bloß ein paar Punkte) oder schon vorhandene Handicap-Form auf ähnlicher Marke; bei
  kurzer Quote wiegt es schwerer.

### Typische Pro-Argumente

- `P-RANG-VORNE` vorderer Modell-Rang mit solidem Value
- `P-CGD` CGD
- `P-REFERENZ-GUT` Referenzlauf unter heutigen Bedingungen mit gutem ARR
- `P-BAHN` Bahnbewährung (gewonnen oder platziert)
- `P-BODEN-BEWAEHRT` Bewährung genau auf der heutigen Bodenangabe
- `P-BOX` signifikant gute Box
- `P-GEGEN-VERLAUF` gegen den Verlauf gut gelaufen
- `P-GESTOERT` gestörter letzter Lauf
- `P-MARKE-UNTER` im Handicap: Marke deutlich unter letzter Sieg-/Platzmarke
- `P-VALEUR-HOECHSTE` außerhalb des Handicaps: höchste gewichtsbereinigte Valeur im Feld
- `P-TRAINER` Trainer heiß oder auf der Bahn stark
- `P-JOCKEY-KENNT` Jockey kennt das Pferd
- `P-GESPANN` starkes Gespann
- `P-PROVINZ` Abstieg in die Provinz
- `P-ABSTIEG` Abstieg aus stärkeren Rennen (nur wenn diese Rennen nicht abgewertet sind)
- `P-BRITE` britischer Trainer
- `P-UNEXPOSED` unexposed mit Steigerungspotenzial
- `P-AUSRUESTUNG-ZURUECK` Ausrüstung kommt zurück, mit der die besten Läufe kamen
- `P-ERSTER-ANSATZ` „erster Ansatz“ nach einer Reihe schwacher Läufe

## Gesamturteil

Je Kandidat: Pro-Argumente, Gegenargumente, Fragezeichen, dann die **eigene Kursspanne** – grob, ehrlich, ohne
Rechnung („fair eher 8–10“). Gewettet wird, wenn der Festkurs klar über der Spanne liegt (`U-KURSSPANNE`) und die Leitfrage mit „ja,
kann reichen“ beantwortet ist (`U-LEITFRAGE`). Mindestquote = unterer Rand der Spanne.

- **Wette** = 1 Einheit. **Kleine Wette** = ½ Einheit: interessant, aber „da fehlt einiges“ (z. B. erster Ansatz
  nach vielen schwachen Läufen, Value dünn).
- `U-KEIN-AUSWEG` **Keine kleine Wette als Ausweg:** Ist das Pferd exposed und sind Trainer oder Jockey schwach bzw. ohne aktuelle
  Form, wird es keine kleine Wette, auch wenn Value, Konstanz oder Marke dafür sprechen. Die kleine Wette ist für
  Pferde, bei denen einiges fehlt, aber die Grundlage stimmt (unexposed, starke Verbindungen),
  nicht für exposed Pferde mit schwachen Verbindungen.
- **Keine Wette**, wenn die Fragezeichen überwiegen, die Leitfrage verneint wird oder der Festkurs die eigene
  Einschätzung nicht übersteigt.

`U-FAUSTREGEL` **Faustregel** (Orientierung, keine Rechenregel; Abweichungen ausdrücklich nennen):

- Value knapp über der Grenze (+5 bis etwa +10 %): nur bei klarer, überzeugender Beweislage (z. B. CGD, Bewährung auf
  sehr weichem Boden, Marke unter letzter Platzmarke) – und nur, wenn die eigene Spanne unter dem Festkurs liegt.
- +10 % bis +50 %: höchstens ein Fragezeichen und kein gewichtiges Gegenargument.
- Über +50 %: ein bis zwei Fragezeichen tragbar, **wenn genug für das Pferd spricht**. Viel Value ohne Pro-Argumente
  oder mit Aufgewicht, Klassenfrage und Höchstgewicht auf schwerem Boden zusammen reicht nicht.
- `G-DEBUET-STALL` Debütanten: nur wenn der Stall Debütanten bzw. Zweijährige siegfertig bringt **und** die Abstammung passt;
  ein Stall ohne Sieg in den letzten 20 Starts „spricht Bände“.

## Rennvergleich

Bei mehreren Kandidaten im selben Rennen: nach Beweislage ordnen und eine Grenze ziehen (`U-GRENZE`); gewettet wird nur, wer klar
überzeugt – in der Regel höchstens zwei. Auch der beste Kandidat kann unter der Grenze liegen (keine Wette im Rennen).
Die Maßstäbe stehen als Bezugslinie dabei (ohne Platz in der Reihenfolge), z. B. „Boomslang > Sir Dasch – Maßstäbe El
Lagar (2,8): sieglos, ARR 32,4, erstmals 2000 m und PSF; Tiger Bay (4,5): ARR 34, PSF bewährt – Boomslang auf dem
Papier besser als beide; Grenze vor Platz 1 (Kurs zu kurz)“.

## Ausgabe

Je Rennen:

```
## R2C7 Strasbourg 14:24 – Handicap 4j+, 2350 m, Très souple, 13 Starter (Klasse sehr schwach, Tempo schnell)
**5 Algeciras** – FK 13 · Modell 8,2 % (Rang 5/13) · Value +7 %
- Pro: …
- Gegen: …
- Fragezeichen: …
- Urteil: **Wette (1 Einheit)** – fair eher 9–11, Mindestquote 11. Ausschlag: … (P-CGD)
…
Maßstab 1: 3 Afterglow (FK 6,5): … (kurz, kein Urteil)
Maßstab 2: 8 … (FK 7): …
Rennvergleich: Algeciras > Cole Chop > Lady Madeira > Afterglow > Go For It – Grenze nach Platz 2.
```

Am Ende eine Wett-Tabelle (Rennen | Zeit | Nr Pferd | Festkurs | Kursspanne | Mindestquote | Einheiten | Ausschlag).

**Ergebnis je Rennen** (dasselbe Format im automatischen Durchgang, geprüft mit `durchgang.rennen_pruefen`, abgelegt
als `durchgang_JJJJMMTT_HHMM.json`, ausgewertet im Value-Dashboard), mit **allen** Kandidaten:

```json
{"race_id": "20261111R2C7", "status": "bearbeitet", "vergleich": "Algeciras > Cole Chop > … – Grenze nach Platz 2",
 "hinweis": "", "massstab": [{"no": 3, "horse": "…", "fk": 6.5, "befund": "…"},
                           {"no": 8, "horse": "…", "fk": 7.0, "befund": "…"}],
 "kandidaten": [{"no": 5, "horse": "ALGECIRAS", "urteil": "wette", "fk": 13.0, "mq": 11, "spanne": [9, 11],
                 "p_modell": 0.079, "value": 0.03, "pro": ["Auf Collant gewonnen (P-BODEN-BEWAEHRT)"], "gegen": ["…"],
                 "fragen": ["…"], "ausschlag": "CGD und Boden tragen den dünnen Value (P-CGD)"}]}
```

`urteil` ist `wette`, `klein` oder `nein` (1, ½, 0 Einheiten). `massstab` ist eine Liste mit höchstens zwei Pferden in
Festkurs-Reihenfolge, steht nicht unter den Kandidaten und zählt nie als Claude-Tipp (`[]`, wenn das Blatt keinen nennt). `status`: `bearbeitet`, bei Araber/AQPS `araber`
(Kandidaten leer).

## Lernschleife

Gilt nur für die Durchsicht mit dem Nutzer, nicht für den automatischen Durchgang.

- **Je besprochenem Rennen** ins Fallarchiv des Repos (eine Zeile je Kandidat, Art **Übereinstimmung**, **Claude
  lernt** oder **Claudes Sicht behalten**; Ort und Format in `claude_projekt/task.md`) und dazu ein **Testfall** im
  Testsatz (`claude_projekt/aufgabe_testsatz.md`). Archiv und Testsatz gehören nicht zum Skill und werden beim
  Durchgang nicht gelesen.
- **Vor jeder Änderung** an diesem Skill den Testsatz laufen lassen; übernommen wird nur, was die Fehlerpunkte nicht
  erhöht und keinen Rückschritt bringt (ADR 0002).
- **Am Ende der Sitzung verdichten:** Änderungen an `EINSICHTEN.md` (Gewicht aus der Argumentation des Nutzers, ein
  Beispiel je Einsicht, Doppeltes zusammenfassen) und an `SKILL.md` vorschlagen, Zustimmung abwarten, dann eintragen.
- **Regel in `SKILL.md`** erst, wenn zwei Fälle „Claude lernt“ in dieselbe Richtung zeigen oder der Nutzer sie
  ausdrücklich zur Regel erklärt; bis dahin in `EINSICHTEN.md` im Abschnitt ihres Prüfschritts mit dem Vermerk „vorläufig“. Abweichende, vom Nutzer nicht
  abgelehnte Urteile und Lagen, in denen der Nutzer selbst schwankte, kommen unter „Ermessen“.
- **Kennungen sind dauerhaft:** Eine neue Regel oder Einsicht bekommt eine neue Kennung; eine bestehende wird nie
  umbenannt oder für eine andere Bedeutung wiederverwendet (das Regelprotokoll der Ergebnisanalyse zählt nach ihr).
  Eine gestrichene Regel nimmt ihre Kennung mit.
- Widerspricht ein neues Urteil einer Regel oder Einsicht, das ansprechen (Ausnahme oder Regel zu streng?). Neue
  Begriffe gehen in `GLOSSARY.md`.
