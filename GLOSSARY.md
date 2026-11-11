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

**Aufgewicht**:
Die heutige Handicap-Marke liegt über der Marke des letzten Siegs. Ein Fragezeichen, umso größer, je exposed das Pferd ist.
_Avoid_: Strafe, Mehrgewicht

**Exposed**:
Ein Pferd mit vielen Starts und eher höherem Alter, von dem kaum noch Steigerung zu erwarten ist. Gegenteil: **unexposed** (wenige Starts, jung, Steigerung möglich).
_Avoid_: ausgereizt, erfahren

### Boden

**Bodenangabe**:
Die genaue PMU-Bodenbezeichnung des Tages (Bon, Bon souple, Souple, Très souple, Collant, Lourd …).
_Avoid_: Boden ohne Zusatz, Going

**Bodengruppe**:
Die grobe Einteilung der Karte (Very slow, Slow, Fast, Very fast, PSF), in der z. B. Souple und Très souple zusammenfallen.
_Avoid_: Bodenangabe

**Value**:
Festkurs × Modell-Siegchance − 1, also der erwartete Gewinn je 1 € Einsatz auf Sieg.
_Avoid_: Wert, Value-Lücke, EV, Edge

**Value-Faktor**:
Die geeichte Kennzahl des Value-Modells (oberstes Zehntel „gold“, unterstes Fünftel „Warnung“). Hat mit Value nichts zu tun.
_Avoid_: Value (ohne „-Faktor“), Wert

### Auswahl

**Kandidat**:
Ein Starter mit Value > 0. Nur Kandidaten werden in der Analyse angesehen; eine Kursgrenze gibt es nicht.
_Avoid_: Value-Pferd, Tipp

**Pro-Argument**:
Ein Grund, der für ein Pferd spricht, gleich ob das Modell ihn schon kennt.
_Avoid_: Angle, Plus ohne Zusatz

**Gesamturteil**:
Die Entscheidung Wette ja oder nein über einen Kandidaten, abgewogen aus Value, Pro-Argumenten, Gegenargumenten und Fragezeichen, ohne eine eigene Siegchance zu berechnen.
_Avoid_: eigene Siegchance, eigener Value, Score

**Wette**:
Ein Kandidat, für den das Gesamturteil ja lautet. Mehrere Wetten im selben Rennen sind erlaubt. Einsatz: ⅛ Kelly auf die Modell-Siegchance.
_Avoid_: Tipp (das ist der mechanische Vorschlag der Karte), Pick

**Mindestquote**:
Der niedrigste Festkurs, zu dem eine Wette noch abgegeben wird. Liegt der Festkurs beim Wetten darunter, wird nicht gewettet.
_Avoid_: faire Quote (das ist 1 ÷ Modell-Siegchance), Mindestkurs

**Tipp**:
Der mechanische Vorschlag der Karte nach ihrer Kelly-Regel, ohne Analyse.
_Avoid_: Wette

## Relationships

- Ein **Kandidat** ist ein Starter, dessen **Value** größer als 0 ist.
- **Value** entsteht aus **Festkurs** und **Modell-Siegchance**; der **Value-Faktor** geht nicht ein.
- Über jeden **Kandidaten** fällt ein **Gesamturteil**; lautet es ja, ist er eine **Wette**.
- Das **Gesamturteil** wägt **Value** gegen **Pro-Argumente**, **Gegenargumente** und **Fragezeichen** ab.
- Eine **Wette** kann zugleich ein **Tipp** der Karte sein, muss es aber nicht.

## Flagged ambiguities

- „Value“ wurde für drei Dinge benutzt: Festkurs × Chance − 1, den Value-Faktor und den Abstand der eigenen Chance zur Prognose. Geklärt: **Value** ist nur Ersteres; der Faktor heißt **Value-Faktor**.
- „Kurs“ meint im Code teils die Quote, teils die Bahnkonfiguration. Für die Quote gilt **Festkurs**.
