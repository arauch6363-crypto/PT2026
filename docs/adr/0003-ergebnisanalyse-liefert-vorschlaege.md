# Ergebnisanalyse liefert Vorschläge, der Nutzer entscheidet, das Regelprotokoll prüft

Die **Ergebnisanalyse** (Skill `ergebnis-analyse`, Aufgabe „Ergebnisanalyse“) gleicht die Durchgänge eines Renntags
mit dem Einlauf ab und schlägt Änderungen am Skill `rennkarten-durchgang-neu` vor. Sie ist **kein neuer Maßstab**:
ADR 0002 gilt weiter, der Skill wird am Urteil des Nutzers gemessen. Ein Vorschlag wird erst übernommen, wenn der
Nutzer „ja“ sagt und der Testsatz keinen Rückschritt zeigt. Ein Vorschlag darf aus **einem einzigen Fall** entstehen;
ob er sich verallgemeinern lässt, beurteilt der Nutzer aus seiner Erfahrung. Ob die Regel danach trägt, zeigt das
**Regelprotokoll**: nur vorwärts, je Regelkennung, A/E gegen den Festkurs beim Durchgang.

Untersucht werden **verpasste Sieger** (abgelehnter Kandidat gewinnt) und **verlorene Claude-Tipps**. Treffer gehen nur
ins Regelprotokoll. Sieger, die Maßstab oder gar kein Kandidat waren, werden gezählt, aber sie erzeugen keinen
Vorschlag am Skill, denn sie betreffen den Kandidaten-Filter (Value ≥ +5 %), nicht den Durchgang. Jeder Vorschlag
nennt den Datenpunkt, wie er **vor dem Rennen** auf der Karte stand, und die **Gegenprobe**: wie viele Verlierer
desselben Tages ihn ebenfalls hatten.

## Considered Options

- **Ergebnisse als Maßstab neben dem Testsatz** – verworfen: Zwei Lernschleifen würden gegeneinander ziehen, der
  Testsatz zum Urteil des Nutzers, die Ergebnisse zum Zufall der letzten Tage (Fallzahlen wie in ADR 0002).
- **Vorschlag erst ab mehreren gleichen Fällen** – verworfen auf Wunsch des Nutzers: Er kann aus Erfahrung beurteilen,
  ob eine Regel aus einem Fall allgemein gilt; die Daten widerlegen sie später im Regelprotokoll.
- **Backtest auf der Historie vor der Entscheidung** (`regel_backtest.py`) – verworfen: Der Nutzer entscheidet aus
  Erfahrung; geprüft wird vorwärts.
- **Neue Regel schlägt den Testsatz** – verworfen: Kippt ein Testfall, sieht der Nutzer den Konflikt und entscheidet,
  ob er die Regel umformuliert oder sein damaliges Urteil im Testfall ausdrücklich ändert (mit Datum und Grund).

## Consequences

- Jede Regel und Einsicht trägt eine dauerhafte **Regelkennung**; der Durchgang zitiert sie, und
  `durchgang.rennen_pruefen_streng` lehnt unbekannte Kennungen ab. Durchgänge vor der Einführung haben keine
  Kennungen; für sie ordnet die Ergebnisanalyse die Regel aus dem Text zu, ins Regelprotokoll gehen sie nicht.
- Regelprotokoll, Vorschläge und analysierte Tage liegen im Repo unter `auswertung/`; jeder analysierte Tag ergibt
  einen PR, auch ohne angenommenen Vorschlag.
- Eine Regel **unter Druck** (n ≥ 20, z ≤ −2 gegen ihre Richtung) wird dem Nutzer erneut vorgelegt, nie automatisch
  gestrichen.

## Nachtrag 27.11.2026: Rückschau, Drift, Kandidatenprotokoll, Kalibrierung

Bis zum 21.11. kamen 10 von 14 untersuchten Fällen aus verlorenen Tipps, alle 27 Vorschläge wurden angenommen, und die
Gegenprobe sieht nur Verlierer desselben Tages. So kann der Skill unbemerkt immer strenger werden. Dagegen stehen jetzt
Zahlen, die die Ergebnisanalyse mitliefert:

- **Rückschau** (`rueckschau`): Ein Vorschlag mit `wirkung` „strenger“ nennt die bisherigen Treffer, die die Regel
  gestrichen hätte.
- **Drift** (`drift`): Anteil wette / klein / nein je Tag und in den letzten 7 Tagen gegen davor, dazu angenommene
  Vorschläge `strenger` : `lockerer`. Halbiert sich der Tipp-Anteil, wird der Nutzer gefragt; nichts greift
  automatisch ein.
- **Kandidatenprotokoll** (`auswertung/kandidaten.csv`) und **Kalibrierung** (`kalibrierung`): je Urteil Siege gegen
  die Erwartung nach Markt und nach der eigenen Kursspanne, Ø ln(Festkurs / Endquote). Sie tragen schneller als das
  Regelprotokoll, weil jeder Kandidat zählt und nicht jede Kennung für sich.

Was die Zahlen **nicht** sagen: Bei den Fallzahlen einiger Wochen (bis 21.11. elf Tipps an zwei Tagen im
Regelprotokoll) ist jede Abweichung im Rahmen des Zufalls; erst ab etwa 50 Tipps lässt sich eine zu großzügige
Kursspanne von Pech unterscheiden. Ein Festkurs über der Endquote heißt, der Durchgang hat früh einen guten Kurs
erwischt, nicht, dass das Urteil richtig war. Die Zahlen sind **kein neuer Maßstab** neben dem Testsatz: ADR 0002 gilt
weiter, sie begründen allein keinen Vorschlag, sondern stehen als Beleg im Bericht und in der Gegenprobe. Das
Kandidatenprotokoll beginnt am 27.11.2026; für frühere Tage liegen Kursspanne, Modellchance und Endquote nicht im Repo,
die Drift zählt dort aus dem Regelprotokoll (nur Kandidaten mit zitierter Kennung).
