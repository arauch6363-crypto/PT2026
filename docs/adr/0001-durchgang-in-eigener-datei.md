# Urteile eines Durchgangs in eigener Datei statt in der HTML-Karte

Die Urteile eines Durchgangs (NAP, BET, abgelehnte Kandidaten mit Begründung) liegen als
`racecards/durchgang_JJJJMMTT_HHMM.json` neben der Karte, je Lauf eine neue Datei, je Rennen gilt die jüngste.
`racecard.run` und `festkurse_aktualisieren` setzen sie beim Schreiben in die HTML ein, das Value-Dashboard rechnet
die Claude-Tipps daraus. Die HTML ist nur Anzeige.

## Considered Options

- **Urteile direkt in die HTML in Drive schreiben** – verworfen: `festkurse_aktualisieren` schreibt die HTML für
  spätere Veranstaltungen neu und hätte die Kennzeichen gelöscht; die Drive-Verbindung der geplanten Aufgabe kann den
  Inhalt einer Datei nicht ersetzen und nimmt höchstens etwa 3 MB je Aufruf mit, die Karten haben 4–11 MB.
- **Eine Datei je Tag, bei jedem Lauf überschrieben** – verworfen: Überschreiben geht über die Drive-Verbindung nicht,
  und zwei Läufe kämen sich in die Quere.

## Consequences

- Die markierte Karte sieht der Nutzer sofort nur im Artefakt „Racecard heute“; in Drive erst nach dem nächsten
  Notebook-Lauf.
- Kartendaten (`_daten.json`) und Claude-JSONs bleiben ohne Urteile – der blinde Teil darf sie nie sehen.
