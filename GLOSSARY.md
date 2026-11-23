# Rennkarten-Analyse

Begriffe, mit denen PT2026 französische Flachrennen (Vollblut) auf einer Racecard bewertet und daraus Siegwetten zum Festkurs auswählt.

## Language

### Kurse und Chancen

**Festkurs**:
Die feste Siegquote eines Buchmachers, zu der gewettet wird, als Dezimalquote einschließlich Einsatz.
_Avoid_: FK (nur als Spaltenkürzel), Kurs (mehrdeutig mit der Bahnkonfiguration), Quote ohne Zusatz

**Modell-Siegchance**:
Die Siegchance eines Pferdes nach dem Power-Modell, wie sie die Karte ausweist.
_Avoid_: Power-Chance, Modellchance, Siegchance ohne Zusatz

**Modell-Rang**:
Der Platz eines Starters im Feld nach der Power-Zahl des Modells (1 = stärkster). Gelesen wird er relativ zur Feldgröße: Rang 3 von 16 wiegt anders als Rang 3 von 7.
_Avoid_: Rang ohne Zusatz, Power-Rang

**Gegenargument**:
Ein Grund, warum ein Pferd heute schwächer sein könnte, als die Modell-Siegchance sagt, gleich ob das Modell ihn kennt. Dazu zählt ein hinterer relativer Modell-Rang.
_Avoid_: Fragezeichen (das ist Ungewissheit, keine Schwäche), Minus ohne Zusatz

**Fragezeichen**:
Eine Bedingung, unter der sich ein Pferd heute noch nicht bewiesen hat (z. B. erstmals diese Distanz, diese Bodenangabe, Scheuklappen). Je höher der Value, desto mehr Fragezeichen trägt eine Wette.
_Avoid_: Gegenargument, Risiko, Zweifel

**Referenzlauf**:
Der jüngste frühere Lauf, der den heutigen Bedingungen (Belag, Bodengruppe, Distanz ±200 m) am nächsten kommt, höchstens etwa ein Jahr alt. Ein älterer Lauf auf derselben Bahn kann vorgehen; ein gestörter Lauf taugt nur eingeschränkt als Referenz.
_Avoid_: Vergleichslauf, Formlauf

**Hygienefaktor**:
Die Prüfung der Läufe seit dem Referenzlauf unter anderen Bedingungen: Ordentlich gelaufen zählt nicht, völlig abgeschlagen stellt die Übertragbarkeit des Referenzlaufs in Frage.
_Avoid_: letzte Form (als Urteilsgrundlage)

**Bahnbewährung**:
Das Pferd hat auf der heutigen Bahn schon gewonnen oder ist platziert gelaufen. Ein Pro-Argument; bloße Bahnerfahrung ohne Platzierung zählt nicht.
_Avoid_: Bahnerfahrung, Kursform

**Platziert**:
Unter den ersten drei bei 8 oder mehr Startern, unter den ersten zwei bei bis zu 7 Startern.
_Avoid_: im Geld (das ist weiter gefasst)

**Im Geld**:
Unter den ersten fünf; in Frankreich in der Regel die Plätze mit Preisgeld. Gilt als „gut gelaufen“, auch wenn nicht platziert.
_Avoid_: platziert

**Rennverlauf**:
Wie ein früheres Rennen gelaufen ist (Tempo, Positionen, wo es entschieden wurde). Lief ein Pferd weit hinten und wurde das Rennen von vorne entschieden, lief es gegen den Verlauf; sein Ergebnis unterschätzt dann seine Leistung.
_Avoid_: Laufbild, Rennbild

**Valeur bereinigt**:
Valeur − Gewicht + 55: wie viel Klasse ein Pferd heute für sein Gewicht mitbringt. Maßstab außerhalb des Handicaps; im Handicap ist sie durch die Gewichte fast gleich.
_Avoid_: Marke (die zählt nur im Handicap), Rating ohne Zusatz

**Aufgewertetes Rennen**:
Ein früheres Rennen, dessen Gegner danach überwiegend besser liefen als erwartet; eine gute Leistung darin wiegt mehr.
_Avoid_: starkes Rennen, Formrennen

**Aufgewicht**:
Die heutige Handicap-Marke liegt über der Marke des letzten Siegs. Ein Fragezeichen, umso größer, je exposed das Pferd ist. Gibt es nur im Handicap; in anderen Rennen gleicht das Gewicht die Valeur nicht aus.
_Avoid_: Strafe, Mehrgewicht

**Verbindungen**:
Trainer und Jockey eines Pferdes zusammen gesehen: ihre Stärke (Bilanz, Bahn, Gespann) und ihre aktuelle Form. Schwache oder kalte Verbindungen schließen bei einem exposed Pferd auch eine Kleine Wette aus.
_Avoid_: Connections, Stall (der Stall ist nur der Trainer)

**Claimer**:
Ein Verkaufsrennen (*à réclamer*): Jedes Pferd kann nach dem Rennen zu einem festen Preis gekauft werden, deshalb meist schwächere Felder. Der Aufstieg aus Claimern ins Handicap ist ein Gegenargument, außer die Claimer waren deutlich stärker oder es gibt schon Handicap-Form.
_Avoid_: Verkaufsrennen ohne Zusatz, Reclamer

**Exposed**:
Ein Pferd mit vielen Starts und eher höherem Alter, von dem kaum noch Steigerung zu erwarten ist. Eine Skala, keine Grenze. Gegenteil: **unexposed** (wenige Starts, jung, Steigerung möglich).
_Avoid_: ausgereizt, erfahren

### Boden

**Bodenangabe**:
Die genaue PMU-Bodenbezeichnung des Tages (Bon, Bon souple, Souple, Très souple, Collant, Lourd …).
_Avoid_: Boden ohne Zusatz, Going

**Bodengruppe**:
Die grobe Einteilung der Karte (Very slow, Slow, Fast, Very fast, PSF). Collant und Lourd (Very slow) sind für uns gleichwertig; Souple und Très souple (Slow) werden dagegen unterschieden.
_Avoid_: Bodenangabe

**Value**:
Festkurs × Modell-Siegchance − 1, also der erwartete Gewinn je 1 € Einsatz auf Sieg.
_Avoid_: Wert, Value-Lücke, EV, Edge

**Value-Faktor**:
Die geeichte Kennzahl des Value-Modells (oberstes Zehntel „gold“, unterstes Fünftel „Warnung“). Hat mit Value nichts zu tun.
_Avoid_: Value (ohne „-Faktor“), Wert

### Auswahl

**Kandidat**:
Ein Starter mit Value von mindestens +5 % (darunter frisst die Steuer von 5 % auf den Gewinn den Vorteil). Nur Kandidaten werden in der Analyse angesehen; eine Kursgrenze gibt es nicht.
_Avoid_: Value-Pferd, Tipp

**Maßstab**:
Eines der zwei Pferde, gegen die die Kandidaten eines Rennens gemessen werden: die zwei Besten im Festkurs, die keine Kandidaten sind. Sie zeigen, was im Rennen für den Sieg verlangt ist, werden kurz geprüft, brauchen keinen Value und sind nie eine Wette.
_Avoid_: Referenzpferd (verwechselbar mit Referenzlauf), Benchmark

**Pro-Argument**:
Ein Grund, der für ein Pferd spricht, gleich ob das Modell ihn schon kennt.
_Avoid_: Angle, Plus ohne Zusatz

**Gesamturteil**:
Die Entscheidung Wette ja oder nein über einen Kandidaten, abgewogen aus Value, Pro-Argumenten, Gegenargumenten und Fragezeichen, ohne eine eigene Siegchance zu berechnen.
_Avoid_: eigene Siegchance, eigener Value, Score

**Wette**:
Ein Kandidat, für den das Gesamturteil ja lautet; Einsatz 1 Einheit. Mehrere Wetten im selben Rennen sind erlaubt, in der Regel höchstens zwei.
_Avoid_: Tipp (das ist der mechanische Vorschlag der Karte), Pick

**Kleine Wette**:
Ein Kandidat, der interessant ist, bei dem aber „einiges fehlt“; Einsatz ½ Einheit.
_Avoid_: Mini-Wette, halbe Wette

**Einheit**:
Der feste Grundeinsatz einer Wette, den der Nutzer festlegt. Kelly dient nur noch als Hinweis.
_Avoid_: Kelly-Einsatz, Stake

**Kursspanne**:
Die grobe eigene Einschätzung, welcher Festkurs für ein Pferd fair wäre („fair eher 8–10“), ohne Rechnung. Gewettet wird, wenn der Festkurs klar darüber liegt.
_Avoid_: faire Quote (das ist 1 ÷ Modell-Siegchance), eigene Siegchance

**Mindestquote**:
Der untere Rand der Kursspanne: der niedrigste Festkurs, zu dem eine Wette noch abgegeben wird. Liegt der Festkurs beim Wetten darunter, wird nicht gewettet.
_Avoid_: faire Quote (das ist 1 ÷ Modell-Siegchance), Mindestkurs

**Tipp**:
Der mechanische Vorschlag der Karte nach ihrer Kelly-Regel, ohne Analyse.
_Avoid_: Wette, Claude-Tipp

**Durchgang**:
Ein Lauf des Skills über die zu diesem Zeitpunkt offenen Rennen einer Karte mit Festkurs; er liefert je Kandidat das Gesamturteil. Ein Renntag kann mehrere Durchgänge haben; je Rennen gilt der jüngste.
_Avoid_: Analyse ohne Zusatz, Lauf

**Claude-Tipp**:
Eine Wette oder Kleine Wette aus einem Durchgang. Immer mit „Claude“ zu schreiben, um sie vom Tipp der Karte zu trennen.
_Avoid_: Tipp ohne Zusatz, Pick

**NAP**:
Das Kennzeichen eines Claude-Tipps, der eine Wette ist (1 Einheit).
_Avoid_: volle Wette

**BET**:
Das Kennzeichen eines Claude-Tipps, der eine Kleine Wette ist (½ Einheit).
_Avoid_: halbe Wette

**Abgelehnter Kandidat**:
Ein Kandidat, dessen Gesamturteil in einem Durchgang nein lautet. Er dient als Vergleichsgruppe für die Claude-Tipps.
_Avoid_: keine Wette (als Substantiv), Verworfener

### Prüfung des Skills

**Testfall**:
Ein Rennen, für das der Nutzer über einzelne Kandidaten geurteilt hat: das, was der Skill zu dem Rennen sieht, und die Urteile des Nutzers als erwartete Antwort. In Ermessenslagen gelten mehrere Urteile als richtig.
_Avoid_: Fall (das ist der Eintrag in der Fallsammlung, je Pferd), Eval, Beispiel

**Testsatz**:
Alle Testfälle zusammen; damit wird jede Änderung am Skill geprüft. Er schützt vor Rückschritten, sagt aber nichts darüber, wie gut der Skill auf neue Rennen überträgt, weil die Regeln aus denselben Fällen stammen.
_Avoid_: Eval-Set, Fallsammlung

**Fehlwette**:
Der Skill spielt einen Kandidaten (Wette oder Kleine Wette), den der Nutzer nicht gespielt hätte. Wiegt doppelt so schwer wie ein verpasster Kandidat.
_Avoid_: Fehltipp, falsch positiv

**Verpasster Kandidat**:
Der Skill spielt einen Kandidaten nicht, den der Nutzer gespielt hätte.
_Avoid_: verpasster Sieger (das ist ein abgelehnter Kandidat, der gewonnen hat), falsch negativ

**Trefferquote**:
Der Anteil der Testfälle, in denen der Skill bei jedem bewerteten Kandidaten so urteilt wie der Nutzer, über die Läufe eines Testfalls gemittelt.
_Avoid_: Übereinstimmung (das ist eine Art von Fall in der Fallsammlung), Genauigkeit

**Rückschritt**:
Eine Änderung am Skill macht einen Testfall falsch, den der Skill bisher richtig beurteilt hat.
_Avoid_: Regression (nur im Code), Verschlechterung

### Ergebnisanalyse

**Ergebnisanalyse**:
Der Abgleich der Durchgänge eines Renntags mit dem Einlauf: Wo lag der Skill richtig, wo nicht, an welcher Regel lag es, welcher Datenpunkt der Karte hätte geholfen. Liefert Vorschläge, über die der Nutzer entscheidet. Nicht zu verwechseln mit der **Durchsicht**, in der der Nutzer Claudes Urteile bewertet.
_Avoid_: Durchsicht, Nachbetrachtung, Auswertung (das ist `tipp_auswertung.py`)

**Regelkennung**:
Die feste Bezeichnung einer Regel oder Einsicht des Skills, z. B. `G-AUSRUESTUNG-WEG` (F Fragezeichen, G Gegen, P Pro, U Urteil). Wird nie umbenannt oder wiederverwendet.
_Avoid_: Regelnummer, Punkt 6

**Verpasster Sieger**:
Ein abgelehnter Kandidat, der gewonnen hat.
_Avoid_: verpasster Kandidat (das ist eine Abweichung vom Urteil des Nutzers)

**Verlorener Claude-Tipp**:
Ein Claude-Tipp (NAP oder BET), der nicht gewonnen hat.
_Avoid_: Fehlwette (das ist eine Abweichung vom Urteil des Nutzers)

**Siegergruppe**:
Wohin der Sieger eines Rennens mit Durchgang gehört: **Treffer** (Claude-Tipp), **verpasster Sieger** (abgelehnter Kandidat), **Maßstab** oder **sonstiger Sieger** (weder Kandidat noch Maßstab). Nur Treffer und verpasste Sieger kann eine Änderung am Skill beeinflussen; die anderen betreffen den Kandidaten-Filter.
_Avoid_: Kategorie, Klasse (das ist die Rennklasse)

**Vorschlag**:
Eine konkrete Änderung am Skill aus der Ergebnisanalyse: Fall, Regelbezug, Datenpunkt, Gegenprobe, wörtlicher Text mit Zieldatei, Kennung und Gewicht. Der Nutzer entscheidet ja, nein oder ändern.
_Avoid_: Empfehlung, Hypothese

**Gegenprobe**:
Wie viele Verlierer desselben Tages (Kandidaten und Maßstäbe) den Datenpunkt eines Vorschlags ebenfalls hatten.
_Avoid_: Backtest (das ist `regel_backtest.py` über die ganze Historie)

**Regelprotokoll**:
Je Regelkennung: wie oft sie in Durchgängen zitiert wurde, wie oft die Pferde gewonnen haben und wie viele Siege der Festkurs erwarten ließ (A/E, z). Nur vorwärts, ab Einführung der Kennungen. Eine Regel steht **unter Druck**, wenn n ≥ 20 und z ≤ −2 gegen ihre Richtung.
_Avoid_: Regel-Backtest, Statistik

## Relationships

- Ein **Kandidat** ist ein Starter, dessen **Value** mindestens +5 % beträgt.
- Jedes Rennen hat höchstens zwei **Maßstäbe**; die **Kandidaten** werden in der Leitfrage gegen sie gemessen, gewettet werden sie nie.
- **Value** entsteht aus **Festkurs** und **Modell-Siegchance**; der **Value-Faktor** geht nicht ein.
- Über jeden **Kandidaten** fällt ein **Gesamturteil**; lautet es ja, ist er eine **Wette**.
- Das **Gesamturteil** wägt **Pro-Argumente**, **Gegenargumente** und **Fragezeichen** ab und vergleicht die **Kursspanne** mit dem **Festkurs**; **Value** entscheidet nur, wer **Kandidat** ist.
- Die **Mindestquote** ist der untere Rand der **Kursspanne**.
- Eine **Wette** kann zugleich ein **Tipp** der Karte sein, muss es aber nicht.
- Ein **Durchgang** macht aus jedem **Kandidaten** einen **Claude-Tipp** (**NAP** oder **BET**) oder einen **abgelehnten Kandidaten**.
- Ein **Claude-Tipp** wird zum **Festkurs** beim **Durchgang** abgerechnet; sein Kennzeichen erlischt nicht, wenn der Festkurs später unter die **Mindestquote** fällt.
- Ein **Testfall** fasst die Fälle eines Rennens aus der Fallsammlung zusammen; Kandidaten ohne Urteil des Nutzers laufen mit, zählen aber nicht.
- Eine Abweichung vom Urteil des Nutzers ist eine **Fehlwette** oder ein **verpasster Kandidat**; Wette gegen Kleine Wette zählt halb.
- Die **Ergebnisanalyse** ordnet jeden Sieger einer **Siegergruppe** zu und untersucht **verpasste Sieger** und **verlorene Claude-Tipps**; ihre **Vorschläge** gehen erst nach Zustimmung des Nutzers und bestandenem **Testsatz** in den Skill.
- Gemessen wird der Skill am **Testsatz** (Urteil des Nutzers), nicht am Ertrag; Ertrag und verpasste Sieger der **Claude-Tipps** und **abgelehnten Kandidaten** prüfen die Regeln des Nutzers selbst.

## Flagged ambiguities

- „Value“ wurde für drei Dinge benutzt: Festkurs × Chance − 1, den Value-Faktor und den Abstand der eigenen Chance zur Prognose. Geklärt: **Value** ist nur Ersteres; der Faktor heißt **Value-Faktor**.
- „Kurs“ meint im Code teils die Quote, teils die Bahnkonfiguration. Für die Quote gilt **Festkurs**.
- „Übereinstimmung“ ist in der Fallsammlung eine Art von Fall (Claude urteilte wie der Nutzer). Als Maß für den Skill heißt es **Trefferquote**.
