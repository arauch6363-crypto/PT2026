# STATE – PMU-Value-Bet-Lernschleife (Paper Trading)

Nur Paper Trading: kein echtes Geld, kein Login bei Buchmachern oder beim PMU. Der gesamte Zustand liegt in Dateien.
Ablauf: `/pmu-iteration` (`.claude/commands/pmu-iteration.md`).

## Stand

| Feld | Wert |
|---|---|
| Iteration | 1 |
| Skill-Version | v0.1 (seit 2026-11-06) |
| Letzte Skill-Änderung | 2026-11-06, Iteration 0 |
| Wetten ausgewertet seit der letzten Skill-Änderung | 0 |
| Wetten gesamt (ausgewertet / offen) | 0 / 0 |
| Letzter Lauf (UTC) | 2026-11-06T18:13:43Z (Iteration 1: A/B nichts zu tun, C ohne Daten) |

## Offene Rennen (festgeschrieben, noch nicht ausgewertet)

| rennen_id | start_utc | Datei | SHA-256 | Wetten |
|---|---|---|---|---|
| – | – | – | – | – |

Keine offenen Rennen.

## Festgeschriebene Prognosen (Hash-Register, nur anhängen)

| festgeschrieben_utc | rennen_id | Datei | SHA-256 |
|---|---|---|---|

## Kumulierte Kennzahlen

| Kennzahl | Wert |
|---|---|
| ROI Flat Stake (gesamt) | – |
| Trefferquote Simple Gagnant | – |
| Trefferquote Simple Placé | – |
| Brier Score eigen / Markt | – / – |
| Log-Loss eigen / Markt | – / – |
| CLV (Ø quote_tipp / quote_end − 1) | – |
| Kontaminierte Rennen | 0 |

## Parameter der Schleife

Die Platzhalter in `pmu-iteration.md` stehen in eckigen Klammern. Es gelten diese Werte:

| Parameter | Wert | Status |
|---|---|---|
| Mindestzahl neuer Wetten für einen Lernschritt | 30 | aus dem Befehl |
| Höchstzahl Skill-Änderungen je Lernschritt | 2 | aus dem Befehl |
| Auswahl der Rennen | Französische Rennen (Ausland ausgeschlossen) mit mindestens 10 Startern. Das Quinté+ immer, auch mit weniger Startern | **Vorschlag, bitte bestätigen** |
| Zeitfenster vor dem Start | 15–45 Minuten | aus dem Befehl |
| EV-Schwelle (p × Quote) | 1,15 | aus dem Befehl |
| Wettarten | Simple Gagnant, Simple Placé (Placé nur mit aktueller Placé-Quote) | aus dem Befehl |
| Abbruchprüfung | nach 200 Wetten | aus dem Befehl |

## Konventionen

- `rennen_id` im PMU-Format `JJJJMMTTRxCy`, z. B. `20261106R1C4` (wie im übrigen Repository).
- `data/racecards/<rennen_id>.json`: Rennkarte wie abgerufen, mit Abrufzeit (UTC) und URL.
- `data/predictions/<rennen_id>.json`: Prognose (Format siehe SKILL.md, Schritt 6). Hash mit
  `sha256sum data/predictions/<rennen_id>.json`.
- `data/results/<rennen_id>.json`: offizielle Arrivée und Rapports definitifs, mit Abrufzeit.
- `data/ledger.csv`: eine Zeile je Wette.
  - `einsatz` = 1.
  - `quote_tipp` = aktuelle Quote beim Festschreiben, `quote_end` = Rapport définitif für 1 €.
  - `gewinn` = netto (Auszahlung − Einsatz). Bei Verlust ist das −1, bei Nichtstarter 0.
  - `status` ∈ {offen, gewonnen, verloren, nichtstarter, kontaminiert}.
  - `platz` = Zielplatz, oder NP, D, A, T.
- Zeiten immer in UTC (ISO 8601 mit `Z`).

## Datenquellen (geprüft am 2026-11-06 ca. 18:10 UTC aus dieser Cloud-Umgebung)

**Ergebnis: Keine Rennsport-Quelle ist erreichbar.** Programm, Starter, Quoten und Ergebnisse sind derzeit
nicht abrufbar. Der Netzwerk-Proxy der Umgebung lehnt alle Hosts ab (HTTP 403 beim CONNECT bzw. DNS-Fehler bei
WebFetch).

| Quelle | Host | Inhalt | Status |
|---|---|---|---|
| PMU-Schnittstelle (turfinfo) | online.turfinfo.api.pmu.fr | Programm, Starter, Quoten (`dernierRapportDirect`), Pronostics, Rapports definitifs | blockiert (403) |
| PMU-Schnittstelle (offline) | offline.turfinfo.api.pmu.fr | wie oben (Ausweich-Host) | blockiert (403) |
| PMU-Website | www.pmu.fr | Programm, Quoten, Arrivées | blockiert (403) |
| Equidia | www.equidia.fr | Programm, Pronostics, Ergebnisse | blockiert (403) |
| Paris-Turf | www.paris-turf.com | Presse, Pronostics, Ergebnisse | blockiert (403) |
| Geny | www.geny.com | Programm, Partants, Cotes, Arrivées | blockiert (403) |
| Zone-Turf | www.zone-turf.fr | Programm, Cotes, Arrivées | blockiert (403) |
| LeTrot | www.letrot.com | Trab: Starter, Leistungen, Ergebnisse | blockiert (403) |
| France Galop | www.france-galop.com | Galopp: Starter, Ergebnisse, Tracking | blockiert (403) |
| Turfomania, Canalturf, Boturfers | www.turfomania.fr, www.canalturf.com, www.boturfers.fr | Presse, Pronostics | blockiert (403) |
| Websuche (WebSearch-Werkzeug) | – | Suchtreffer (Titel, URL) | erreichbar, liefert aber keine strukturierten Quoten bzw. Ergebnisse und keine Seiteninhalte |

Funktionierende Quellen: **keine** für Programm, Quoten und Ergebnisse.
Voraussetzung für den Start: Die Hosts oben (mindestens `online.turfinfo.api.pmu.fr`) müssen in den
Netzwerkeinstellungen der Umgebung freigegeben sein. Danach erneut prüfen und diese Tabelle aktualisieren.

## Fehlerprotokoll

| Zeit (UTC) | Schritt | Fehler | Folge |
|---|---|---|---|
| 2026-11-06 18:08 | Einrichtung | Alle Rennsport-Hosts blockiert (Proxy-403) | Schleife kann nicht starten |
| 2026-11-06 18:13 | Iteration 1, C | Programm nicht ladbar: turfinfo-API (online/offline), pmu.fr, geny, zone-turf, equidia weiterhin blockiert (CONNECT 403) | Keine Rennkarte, keine Prognose; nächstes Rennen unbekannt |

## Hypothesen-Notizen (Beobachtungen ohne Skill-Änderung)

(noch keine)
