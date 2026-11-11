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

**Eigene Siegchance**:
Die Modell-Siegchance, korrigiert um Argumente, die das Modell nicht kennt.
_Avoid_: p_blind, korrigierte Chance, Siegchance ohne Zusatz

**Eigener Value**:
Festkurs × eigene Siegchance − 1.
_Avoid_: korrigierter Value, Edge

**Wette**:
Ein Kandidat, dessen eigener Value mindestens +20 % beträgt; der Einsatz folgt mechanisch aus ⅛ Kelly auf die eigene Siegchance. Mehrere Wetten im selben Rennen sind erlaubt.
_Avoid_: Tipp (das ist der mechanische Vorschlag der Karte), Pick

**Tipp**:
Der mechanische Vorschlag der Karte nach ihrer Kelly-Regel, ohne Analyse.
_Avoid_: Wette

## Relationships

- Ein **Kandidat** ist ein Starter, dessen **Value** größer als 0 ist.
- **Value** entsteht aus **Festkurs** und **Modell-Siegchance**; der **Value-Faktor** geht nicht ein.
- Die Analyse macht aus der **Modell-Siegchance** eines **Kandidaten** die **eigene Siegchance**; ist der **eigene Value** ≥ +20 %, wird er zur **Wette**.
- Eine **Wette** kann zugleich ein **Tipp** der Karte sein, muss es aber nicht.

## Flagged ambiguities

- „Value“ wurde für drei Dinge benutzt: Festkurs × Chance − 1, den Value-Faktor und den Abstand der eigenen Chance zur Prognose. Geklärt: **Value** ist nur Ersteres; der Faktor heißt **Value-Faktor**.
- „Kurs“ meint im Code teils die Quote, teils die Bahnkonfiguration. Für die Quote gilt **Festkurs**.
