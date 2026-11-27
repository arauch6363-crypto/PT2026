# Ausgabe des Rennkarten-Durchgangs

Für den Durchgang von Hand und die Durchsicht mit dem Nutzer. Im automatischen Durchgang gibt der Auftrag das
JSON-Format vor; es entspricht dem Ergebnis je Rennen unten.

## Je Rennen (Markdown)

```
## R2C7 Strasbourg 14:24 – Handicap 4j+, 2350 m, Très souple, 13 Starter (Klasse sehr schwach, Tempo schnell)
**5 Algeciras** – FK 13 · Modell 8,2 % (Rang 5/13) · Value +7 %
- Pro: …
- Gegen: …
- Fragezeichen: …
- Leitfrage: Referenz-ARR … gegen Top-ARR … im Feld, Maßstäbe … und … – kann reichen / reicht nicht
- Urteil: **Wette (1 Einheit)** – fair eher 9–11. Ausschlag: … (P-CGD)
…
Maßstab 1: 3 Afterglow (FK 6,5): … (kurz, kein Urteil)
Maßstab 2: 8 … (FK 7): …
Rennvergleich: Algeciras > Cole Chop > Lady Madeira > Afterglow > Go For It – Grenze nach Platz 2.
```

Am Ende eine Wett-Tabelle (Rennen | Zeit | Nr Pferd | Festkurs | Kursspanne | Einheiten | Ausschlag).

**Ergebnis je Rennen** (dasselbe Format im automatischen Durchgang, geprüft mit `durchgang.rennen_pruefen`, abgelegt
als `durchgang_JJJJMMTT_HHMM.json`, ausgewertet im Value-Dashboard), mit **allen** Kandidaten:

```json
{"race_id": "20261111R2C7", "status": "bearbeitet", "vergleich": "Algeciras > Cole Chop > … – Grenze nach Platz 2",
 "hinweis": "", "massstab": [{"no": 3, "horse": "…", "fk": 6.5, "befund": "…"},
                           {"no": 8, "horse": "…", "fk": 7.0, "befund": "…"}],
 "kandidaten": [{"no": 5, "horse": "ALGECIRAS", "urteil": "wette", "fk": 13.0, "spanne": [9, 11],
                 "p_modell": 0.082, "value": 0.07, "pro": ["Auf Collant gewonnen (P-BODEN-BEWAEHRT)"], "gegen": ["…"],
                 "fragen": ["…"], "ausschlag": "CGD und Boden tragen den dünnen Value (P-CGD)"}]}
```

`urteil` ist `wette`, `klein` oder `nein` (1, ½, 0 Einheiten). `massstab` ist eine Liste mit höchstens zwei Pferden in
Festkurs-Reihenfolge, steht nicht unter den Kandidaten und zählt nie als Claude-Tipp (`[]`, wenn das Blatt keinen
nennt). `status`: `bearbeitet`, bei Araber/AQPS `araber` (Kandidaten leer).
