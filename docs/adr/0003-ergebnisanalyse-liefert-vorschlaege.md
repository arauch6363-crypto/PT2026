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
