---
name: rennkarten-durchgang-neu
description: "Rennkarte/Racecard (französischer Galopp, PT2026) auf Siegwetten durchgehen – ganze Karte oder einzelne Rennen: Value-Kandidaten prüfen, Urteil mit Kursspanne und Mindestquote."
---

# Rennkarten-Durchgang

Vor dem ersten Rennen lesen: `GLOSSARY.md` (Begriffe; im Repo-Hauptordner, im hochgeladenen claude.ai-Skill im
Skill-Ordner), `DATEN.md` (woher jede Angabe stammt) und **`EINSICHTEN.md`** (wie schwer jedes Argument wiegt, typische
Fehler). Im automatischen Durchgang wie von Hand: dasselbe Vorgehen, dasselbe Ergebnisformat. Bei Durchsicht mit dem
Nutzer zusätzlich `LERNSCHLEIFE.md`.

## Ziel und Leitfrage

Es geht um **Siegwetten zum Festkurs**. Ausgangsmenge sind nur **Kandidaten** (Value mindestens +5 %, weil 5 % Steuer
vom Gewinn abgehen; keine Kursgrenze); alle anderen Starter sind Gegner. Über jeden Kandidaten fällt ein
**Gesamturteil**: Wette, kleine Wette oder keine Wette – aus dem Gesamteindruck, nicht aus einer Rechnung.

Die **Leitfrage** jedes Urteils: **Reicht es für den Sieg?** Ein Pferd, das solide laufen und im Geld landen wird, ist
noch keine Siegwette. Gemessen wird an der besten zu heute passenden Leistung (ARR im Referenzlauf) gegen die besten
Pferde des heutigen Feldes und gegen die Maßstäbe.

Der Modell-Value ist **nur der Filter**, welche Pferde angesehen werden. Ob der Festkurs reicht, entscheidet die
**eigene Kursspanne** (siehe Gesamturteil): Ein Pferd mit +29 % Modell-Value kann zu kurz sein, eines mit +6 % lang
genug.

**Kennungen.** Jedes Argument der Listen unten und in `EINSICHTEN.md` trägt eine Kennung wie `G-AUSRUESTUNG-WEG`
(F = Fragezeichen, G = Gegen, P = Pro, U = Urteil). Jeder Satz in Pro, Gegen und Fragezeichen, der sich auf eine
solche Regel stützt, endet mit ihrer Kennung in Klammern, z. B. „Ohne Scheuklappen, mit denen die drei besten Läufe
kamen (G-AUSRUESTUNG-WEG)“. Der Satz **Ausschlag** nennt die Kennung der Regel, die das Urteil entschieden hat, oder
das Wort „Ermessen“, wenn keine passt. Gültig sind nur Kennungen aus `SKILL.md` und `EINSICHTEN.md`; die Prüfung
(`durchgang.rennen_pruefen`) lehnt andere ab. Die Ergebnisanalyse zählt daran, wie oft eine Regel griff und wie es
ausging.

## Ablauf

1. **Fakten ziehen.** `python3 -I <Skill-Ordner>/scripts/blatt.py KARTE` zeigt die Übersicht (Rennen mit
   Kandidaten, Festkurs-Stand). KARTE ist `racecard_JJJJMMTT_daten.json.gz` (Normalfall) oder die HTML-Karte
   `racecard_JJJJMMTT.html` bzw. `…_daten.json` – das Skript liest alle drei. Skill-Ordner: in Claude Code
   `.claude/skills/rennkarten-durchgang-neu`, in claude.ai der Ordner, aus dem diese SKILL.md geladen wurde. Die Karte
   ist über 10 MB groß: nur die Ausgabe des Skripts lesen, nie die Karte selbst. Mit Bahn oder Rennen (`STRASBOURG`,
   `R2C5`) als weiteres Argument druckt es je Rennen den Kopf und je Kandidat das Blatt. Uhrzeit gegen den Start
   prüfen (französische Zeit); ist ein Rennen schon gelaufen oder in wenigen Minuten, das sagen.
2. **Rennen lesen** (Kopf des Blatts): Rennart, Klasse (Klassenindex), Feldgröße, Bodenangabe und Bodengruppe,
   Distanz, Bahn und Richtung, erwartetes Tempo mit Laufstilen, FK-Favorit, Top-ARR und Top-Valeur im Feld,
   Höchstgewicht. Nur Vollblut; Araber, Anglo-Araber, AQPS nicht.
3. **Maßstäbe** prüfen (Abschnitt unten; im Blatt `MASSSTAB 1/2` und `2/2`). Fertig, wenn je Maßstab Referenz-ARR
   und größtes Fragezeichen feststehen.
4. **Je Kandidat die Prüfliste.** Fertig, wenn jeder der sechs Prüfpunkte je Kandidat einen Befund (Pro, Gegen,
   Fragezeichen) oder ausdrücklich „nichts“ geliefert hat.
5. **Gesamturteil** je Kandidat. Fertig, wenn die Leitfrage mit Zahlen beantwortet ist (Referenz-ARR des Kandidaten
   gegen Top-ARR im Feld und gegen beide Maßstäbe) und Spanne, Mindestquote und Ausschlag mit Kennung stehen.
6. **Rennvergleich**: Kandidaten nach Beweislage ordnen, gegen die Maßstäbe stellen, Grenze ziehen.
7. **Ausgabe** wie unten.

## Maßstab

Je Rennen werden zusätzlich **zwei Pferde als Maßstab** kurz geprüft: die **zwei Besten im Festkurs, die keine
Kandidaten sind** (Kandidaten werden übersprungen, sie werden ohnehin geprüft). Ist der FK-Favorit kein Kandidat, ist
er Maßstab 1; sonst rückt der nächstbeste ohne Kandidaten-Value nach. Ein Maßstab ist **nie eine Wette** und braucht
keinen Value. Je Maßstab kurz: beste zu heute passende Leistung (Referenzlauf, ARR), Beleg für Boden und Distanz,
Verbindungen, Laufstil gegen Tempo, größtes Fragezeichen. Zusammen zeigen die beiden, **was in diesem Rennen für den
Sieg verlangt ist** – die Elle für die Leitfrage (`U-MASSSTAB`): Was müsste der Kandidat besser können als die
Maßstäbe, und ist das belegt? Ist ein Maßstab Debütant oder kaum belegt, steht das ausdrücklich im Urteil („Maßstab
offen“). Die Kursspanne bleibt eigene Einschätzung, nicht abgeleitet von den Festkursen der Maßstäbe.

## Prüfliste je Kandidat

Reihenfolge wie der Nutzer sie geht. Jeder Punkt kann Pro-Argument, Gegenargument oder Fragezeichen liefern.

1. **Ausgangslage und Klasse.** Value und **Modell-Rang relativ zur Feldgröße** (vorderes/mittleres/hinteres
   Drittel; ein hinterer Rang ist ein Gegenargument, ein vorderer mit solidem Value „erstmal sehr positiv“). **Klasse
   relativ zum Feld,** in dieser Reihenfolge: ARR, Valeur (außerhalb des Handicaps), TR, ΔL600, RTR, Duelle (nur mit
   mehreren Duellen); dazu Platzquote und Gewinn je Lauf mit Rang im Feld (Blatt: Karriere). **Exposure** relativ zum
   Alter (21 Starts als 3-Jähriger sind sehr viel; 4-jährig mit 25 Starts gilt noch als „relativ jung“); wenig
   gelaufene Pferde steigern sich bis ins vierte Jahr, der Zenit liegt bei 3 bis 5 Jahren.
   **Marke – nur im Handicap:** Dort zählt die heutige Marke gegen die letzte Sieg- bzw. Platzmarke, weil das Gewicht
   die Valeur ausgleicht – nicht ganz, hohe Marken sind leicht im Vorteil. **In allen anderen Rennen** (Conditions, Claimer, Listed, Gruppe, Rennart unbekannt) gleicht
   niemand die Valeurs aus: Dort zählt, wer die **höchste gewichtsbereinigte Valeur** im Feld hat (Valeur − Gewicht +
   55, Rang im Blatt). Eine Marke unter der letzten Platzmarke ist dort ein Zeichen, dass das Pferd nachlässt.
   Kennzeichen **CGD** (auf Bahn, Distanz, Boden gewonnen) „lässt aufhorchen“; C wiegt am meisten, dann G, dann D.
2. **Referenzlauf.** Der jüngste Lauf unter heutigen Bedingungen (Blatt: `≈heute`), höchstens etwa ein Jahr alt, je
   jünger desto besser. Ihn gründlich lesen, in dieser Reihenfolge (Blatt: Zeile „Lauf:“ darunter):
   - **kompetitiv?** Platz relativ zur Starterzahl und Abstand in Längen; knapp geschlagen im großen Feld ist oft ein
     sehr gutes Rennen.
   - **ARR** des Laufs relativ zum Feld (Rang unter den Läufen der heutigen Starter) und gegen Top-ARR und Maßstäbe
     (Leitfrage); TR bestätigt.
   - **Kommentar, Position, Tempo:** klarer Lauf, Effort in der Geraden, kämpferisch – oder behindert, „Nase im Wind“,
     außen herum. Von weit hinten Boden gutgemacht, als vorne gewonnen wurde, hinten bei langsamem oder vorne bei sehr
     schnellem Tempo: Der Lauf war besser, als der Platz zeigt.
   - **Klasse des Laufs:** Klassenindex gegen heute (Blatt: Abstand), bei jungen Pferden die Dotierung; Listed- und
     Gruppe-Formen wiegen am meisten, Claimer am wenigsten (`P-ABSTIEG`, `G-CLAIMER-AUFSTIEG`).
   - **Gegner:** wie sie danach liefen (aufgewertet/abgewertet; bei jungen Pferden besonders wichtig) und welche
     heutigen Gegner es direkt oder indirekt schlug.
   - **Marke damals gegen heute** (nur im Handicap).

   Kein Referenzlauf ist selbst ein Fragezeichen.
3. **Läufe seit dem Referenzlauf (Hygienefaktor).** Die letzten ein bis zwei Läufe unter anderen Bedingungen nur
   prüfen, nicht bewerten: Lief das Pferd dort ordentlich, zählen sie nicht; war es völlig abgeschlagen (ARR und
   Abstand zusammen), ist fraglich, ob der Referenzlauf heute übertragbar ist. Kommentar, Box, Jockey und Quote
   erklären einen schwachen Lauf oft.
4. **Vorlieben (Gesamtbilanz), dann Abstammung.** Boden, Distanz, Bahn, Richtung, Ausrüstung aus den **Vorlieben**
   des Blatts lesen, über die **Platzquote** (ein Sieg ist ein zusätzliches Plus) – die Formzeilen zeigen nur einen Teil
   der Läufe. Schon wenige Läufe zählen; eine Platzierung auf einem Boden belegt ihn. **Boden vergleichen:** Collant und
   Lourd bilden zusammen die Gruppe Very slow und sind gleichwertig; Souple belegt Très souple nicht vollständig. Mit
   schnellem Boden kommen mehr Pferde zurecht, auf sehr weichem zählen Spezialisten.
   **Wechsel** von Belag, Boden oder Distanz an der Bilanz auf beiden Seiten messen (`P-WECHSEL-BESSER`,
   `G-WECHSEL-SCHLECHTER`). Ein Distanzwechsel ab etwa 250 m ist auffällig (Blatt). Je weiter die Distanz von der
   Mitteldistanz weg liegt (Blatt: Distanzklasse), desto mehr zählen Leistung auf der Strecke und Abstammung.
   **Abstammung, wo die eigene Erfahrung fehlt:** Bei viel gelaufenen Pferden zählt die eigene Bilanz, die
   Abstammungsstatistik ist dann ohne Belang. Wichtig ist die Abstammung (alle Skalen: Boden, Distanz, Belag, Reife;
   Gesamtwert) für junge, wenig gelaufene Pferde und für Pferde, die einen Boden, Belag oder eine Distanz zum ersten
   bis dritten Mal erleben – dort kann eine klar unpassende Abstammung allein die Wette kippen. Steigt ein junges Pferd
   innerhalb einer Distanzklasse deutlich, zeigt die Platzquote der Nachkommen je Distanzklasse (Blatt), ob die Linie
   längere Wege trägt. Differenziert lesen: Frankels mögen sehr weichen Boden manchmal nicht – Souple ist dafür nicht
   weich genug. Bei jungen Pferden zählt zusätzlich die **Qualität** der Linie relativ zum Feld (Blatt: Platzierungs-,
   Gewinn- und Valeur-Index der Nachkommen), weil sie etwas über das Potenzial sagt.
5. **Trainer, Jockey, Besitzer.** Zuerst die Lage in der **A/E-Matrix über 365 Tage** relativ zum Feld (Blatt: A/E+
   und Pos+ mit Rang; rechts oben = gut), dann die 30 Tage: aktuell heiß oder kalt. Trainerwechsel beachten (Blatt:
   „Trainer erst seit N Läufen“). Trainer: Bilanz auf der Bahn (kann eine kalte Form ausgleichen), Spezialität
   (Rennart, Alter, Debütanten), Stallgröße und -erfolg (kleiner Stall ohne Sieg in zwei Jahren = Gegenargument; klein,
   aber „geschickt operierend“ = neutral bis Pro). Jockey: Bilanz auf der Bahn, kennt das Pferd (Siege zusammen = Pro),
   **Gespann Trainer + Jockey** – zählt mehr als die Einzelbilanzen, sobald es einige gemeinsame Starts gibt.
   Besitzer: nur 365 Tage. Bei Maiden und Debütanten sind Verbindungen, Besitzer und Abstammung die Hauptkriterien.
6. **Umstände heute.** Box (nur `signifikant` zählt), Gewicht (ab etwa 62 kg auf Très souple oder schwerer =
   Gegenargument), Tempo gegen Laufstil (Führender bei schnellem Tempo mit mehreren Führenden = Gegen; Pferd von
   hinten bei schnellem Tempo = Pro), Startfolge (ab etwa 4 Starts in 6 Wochen = Gegenargument, „irgendwann ist die
   Luft raus“), Bahnkategorie (von großen Bahnen in die Provinz = Pro, umgekehrt Gegen), Reise (britischer Trainer =
   Pro; spanisch, deutsch, weit reisend französisch nur begrenzt). Crible und Rennkommentar sind Kontext.
   **Ausrüstungswechsel** (Scheuklappen, australische Scheuklappen) nach den Bilanzen mit und ohne bewerten (Blatt:
   „Ausrüstung“), der Wechsel an sich sagt nichts:
   - fällt weg, **mit ihr kamen die besten Läufe** → `G-AUSRUESTUNG-WEG`;
   - fällt weg, **mit ihr liefen die Formen auch schwach** → neutral, man probiert etwas Neues;
   - fällt weg, **ohne sie lief das Pferd fast immer** → neutral bis Pro, Rückkehr zum Normalen;
   - **kommt zurück, mit ihr kamen die besten Läufe** → `P-AUSRUESTUNG-ZURUECK`;
   - **erstmals** → `F-AUSRUESTUNG-NEU`.

### Fragezeichen (unbewiesen, offene Liste)

- `F-DISTANZ-NEU` erstmals diese Distanzgruppe (auch Distanzwechsel nach unten, gemildert, wenn das Pferd vorne mitläuft)
- `F-BODEN-NEU` erstmals dieser Boden ab Très souple
- `F-BELAG-NEU` erstmals dieser Belag
- `F-AUSRUESTUNG-NEU` erstmals Scheuklappen oder andere Ausrüstung („warum heute?“)
- `F-KLASSE-HOCH` Bewährung nur aus tieferer Klasse (z. B. Claimer) oder erstmals deutlich höhere Klasse
- `F-PAUSE` Rückkehr nach langer Pause (ab etwa 60 Tagen; wiegt weniger bei jungen Pferden und erfolgreichen
  Trainern)
- `F-WALLACH` erstmals Wallach
- `F-TRAINERWECHSEL` Trainerwechsel
- `F-AUFGEWICHT` **Aufgewicht** (nur im Handicap; umso größer, je exposed)
- `F-BAHN-EIGENHEIT` erster Start auf einer Bahn mit Eigenheiten (Strasbourg, Fontainebleau)
- `F-KLASSENFRAGE` Klassenfrage (kleiner Stall, Formen nur aus schwachen Rennen)
- `F-AUSLAND` nicht einzuordnende Auslandsformen

Fragezeichen **wiegen, nicht zählen**. Ein Fragezeichen ist **entkräftet** (zählt nicht oder wird zum Pro-Argument),
wenn Belege dafür sprechen: erstmals eine längere Distanz, aber die Abstammung trägt sie und das Pferd lief bisher umso
besser, je weiter der Weg war; Trainerwechsel zu einem klar starken Stall; Claimer-Sieg, aber vorher schon
Handicap-Form auf ähnlicher Marke.

### Typische Gegenargumente

- `G-RANG-HINTEN` hinterer Modell-Rang
- `G-REFERENZ-SCHWACH` schwacher Referenzlauf ohne Grund zur Steigerung
- `G-ARR-UNTER` ARR deutlich unter den Besten im Feld
- `G-SELTEN-VORNE` selten vorne: Platzquote weit hinten im Feld (Blatt: Karriere)
- `G-TRAINER-KALT` kalter Trainer (abgestuft)
- `G-AUSRUESTUNG-WEG` Ausrüstung fällt weg, mit der die besten Läufe kamen (Punkt 6)
- `G-RICHTUNG` in der heutigen Richtung klar schlechter
- `G-BOX` signifikant schlechte Box
- `G-GEWICHT-BODEN` Gewicht ab etwa 62 kg auf Très souple oder schwerer. Ein Höchstgewicht darunter ist neutral;
  außerhalb des Handicaps steckt es schon in der gewichtsbereinigten Valeur.
- `G-STARTFOLGE` dichte Startfolge
- `G-FORM-WEIT-WEG` Formen „weit weg von dem, was benötigt wird“
- `G-TEMPO-VORNE` vorne laufend gegen schnelles Tempo
- `G-STUTE` Stute gegen Hengste (bei jungen Pferden, leicht)
- `G-SIEG-MIT-VERLAUF` Sieg, bei dem das Rennen den Vorderen half und das Pferd vorne lief (etwas weniger wert)
- `G-DIREKT-HINTER` im direkten Vergleich hinter einem heutigen Gegner
- `G-CLAIMER-AUFSTIEG` **Aufstieg aus Claimern (Verkaufsrennen) ins Handicap** – ausgeglichen nur durch deutlich höheren
  Klassenindex der Claimer (nicht bloß ein paar Punkte) oder schon vorhandene Handicap-Form auf ähnlicher Marke; bei
  kurzer Quote wiegt es schwerer.
- `G-DEBUET-STALL` Debütant: Wette nur, wenn der Stall Debütanten bzw. Zweijährige siegfertig bringt **und** die
  Abstammung passt; ein Stall ohne Sieg in den letzten 20 Starts „spricht Bände“.

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

Je Kandidat: Pro-Argumente, Gegenargumente, Fragezeichen, dann die **eigene Kursspanne** – grob, ehrlich, aus dem
Gesamteindruck („fair eher 8–10“). Gewettet wird, wenn der Festkurs klar über der Spanne liegt (`U-KURSSPANNE`) und die
Leitfrage mit „ja, kann reichen“ beantwortet ist (`U-LEITFRAGE`). Mindestquote = unterer Rand der Spanne.

- **Wette** = 1 Einheit. **Kleine Wette** = ½ Einheit: interessant, aber „da fehlt einiges“ (z. B. erster Ansatz
  nach vielen schwachen Läufen, Value dünn).
- `U-KEIN-AUSWEG` **Kleine Wette nur auf stimmiger Grundlage:** Sie ist für Pferde, bei denen einiges fehlt, aber die
  Grundlage stimmt (unexposed, starke Verbindungen). Ist das Pferd exposed und sind Trainer oder Jockey schwach bzw.
  ohne aktuelle Form, lautet das Urteil keine Wette, auch wenn Value, Konstanz oder Marke dafür sprechen.
- **Keine Wette**, wenn die Fragezeichen überwiegen, die Leitfrage verneint wird oder der Festkurs die eigene
  Einschätzung nicht übersteigt.

`U-FAUSTREGEL` **Faustregel** (Orientierung, keine Rechenregel; Abweichungen ausdrücklich nennen):

- Value knapp über der Grenze (+5 bis etwa +10 %): nur bei klarer, überzeugender Beweislage (z. B. CGD, Bewährung auf
  sehr weichem Boden, Marke unter letzter Platzmarke) – und nur, wenn die eigene Spanne unter dem Festkurs liegt.
- +10 % bis +50 %: höchstens ein Fragezeichen und kein gewichtiges Gegenargument.
- Über +50 %: ein bis zwei Fragezeichen tragbar, **wenn genug für das Pferd spricht**. Viel Value ohne Pro-Argumente
  oder mit Aufgewicht, Klassenfrage und Höchstgewicht auf schwerem Boden zusammen reicht nicht.

## Rennvergleich

Bei mehreren Kandidaten im selben Rennen: nach Beweislage ordnen und eine Grenze ziehen (`U-GRENZE`); gewettet wird
nur, wer klar überzeugt – in der Regel höchstens zwei. Auch der beste Kandidat kann unter der Grenze liegen (keine
Wette im Rennen). Die Maßstäbe stehen als Bezugslinie dabei (ohne Platz in der Reihenfolge), z. B. „Boomslang > Sir
Dasch – Maßstäbe El Lagar (2,8): sieglos, ARR 32,4, erstmals 2000 m und PSF; Tiger Bay (4,5): ARR 34, PSF bewährt –
Boomslang auf dem Papier besser als beide; Grenze vor Platz 1 (Kurs zu kurz)“.

## Ausgabe

Je Rennen:

```
## R2C7 Strasbourg 14:24 – Handicap 4j+, 2350 m, Très souple, 13 Starter (Klasse sehr schwach, Tempo schnell)
**5 Algeciras** – FK 13 · Modell 8,2 % (Rang 5/13) · Value +7 %
- Pro: …
- Gegen: …
- Fragezeichen: …
- Leitfrage: Referenz-ARR … gegen Top-ARR … im Feld, Maßstäbe … und … – kann reichen / reicht nicht
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
                 "p_modell": 0.082, "value": 0.07, "pro": ["Auf Collant gewonnen (P-BODEN-BEWAEHRT)"], "gegen": ["…"],
                 "fragen": ["…"], "ausschlag": "CGD und Boden tragen den dünnen Value (P-CGD)"}]}
```

`urteil` ist `wette`, `klein` oder `nein` (1, ½, 0 Einheiten). `massstab` ist eine Liste mit höchstens zwei Pferden in
Festkurs-Reihenfolge, steht nicht unter den Kandidaten und zählt nie als Claude-Tipp (`[]`, wenn das Blatt keinen
nennt). `status`: `bearbeitet`, bei Araber/AQPS `araber` (Kandidaten leer).
