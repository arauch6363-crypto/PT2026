---
name: pmu-rennanalyse
description: Analyse von PMU-Rennkarten (FR) – Siegwahrscheinlichkeiten je Pferd schätzen und Value Bets erkennen. Nutzen, wenn eine PMU-Rennkarte analysiert wird.
---

# PMU-Rennanalyse – Version v0.1

Paper Trading: Es wird nur auf dem Papier gewettet, 1 Einheit je Wette (Flat Stake). Kein echtes Geld, kein Login
bei Buchmachern oder beim PMU.

Grundhaltung: Der PMU-Markt (Pari mutuel, Totalisator) ist gut kalibriert, aber nicht perfekt. Diese Methode
schätzt nicht neben dem Markt her, sondern **korrigiert den Markt** mit wenigen, begründeten Faktoren und wettet nur bei
deutlichem Abstand. Das folgt dem Ansatz von Benter (1994): Ein Fundamentalmodell allein ist schlechter kalibriert
als die Totalisator-Quoten. Kombiniert man beide, wird es besser als jedes für sich.

Was gilt in v0.1?
- **Methode und Faktoren** (die beiden nächsten Abschnitte) sind die Basis. Sie gelten immer.
- **Regeln** (Tabelle R-xx) sind zusätzliche, eng umrissene Anpassungen. Sie wirken auf die Wette nur mit Status
  „Aktiv“. In v0.1 ist **keine Regel aktiv**. Alle stehen als „Hypothese“ in der Tabelle und werden nur notiert.
- Alle Gewichte und Konstanten sind Startwerte (Stand v0.1, nicht kalibriert). Sie ändern sich nur über Schritt B
  der Lernschleife.

---

# Methode (Schritt für Schritt)

**Schritt 0 – Zulässigkeit prüfen** (sonst „Keine Wette“, Grund notieren)
- Das Rennen ist noch nicht gestartet. Startzeit in UTC aus dem Programm (PMU liefert Epoch-Millisekunden; Paris =
  UTC+1 im Winter, UTC+2 im Sommer).
- Es liegt kein Ergebnis, keine Arrivée und kein Rapport zu diesem Rennen vor. Liegt eines vor: Rennen als
  „kontaminiert“ markieren und abbrechen.
- Disziplin bestimmen: TRAB (attelé, monté), GALOPP (plat) oder HINDERNIS (haies, steeple-chase, cross).
- Nichtstarter (NP, non-partants) streichen. Feldgröße = tatsächliche Starter.
- Es gibt aktuelle Simple-Gagnant-Quoten für mindestens 80 % der Starter. Sonst keine Wette, die Analyse wird aber
  trotzdem festgeschrieben.

**Schritt 1 – Marktwahrscheinlichkeit (Anker)**
- Aus den aktuellen Gagnant-Quoten o_i (Dezimalquote, Rapport für 1 €): roh r_i = 1/o_i.
- Overround U = Σ r_i. Die Marktwahrscheinlichkeit ist q_i = r_i / U (Abzug proportional herausgerechnet).
- U und den Zeitpunkt der Quoten (UTC) notieren. Den Abzug nicht als feste Zahl annehmen, sondern immer aus U
  ablesen.
- Fehlt die Quote eines Starters: q_i aus der Cote probable des PMU-Pronostics, falls vorhanden. Sonst q_i = Mittel
  der drei schlechtesten bekannten q. Danach neu normieren und den Ersatz kennzeichnen.

**Schritt 2 – Fundamentalwert (blind)**
- Schritt 2 wird **ohne Blick auf Quoten, Pronostics und Presse-Tipps** gemacht. Sonst übernimmt man nur den Markt.
- Für jedes Pferd jeden Faktor der passenden Disziplin (nächster Abschnitt) relativ zum heutigen Feld bewerten:
  −2 (klar schlechter als das Feld) … 0 (Durchschnitt oder unbekannt) … +2 (klar besser).
- Ist ein Faktor unbekannt, gilt 0 und „unbekannt“ wird notiert. Eine Lücke ist kein Minuspunkt.
- Score S_i = Σ Gewicht_f × Bewertung_if.
- Fundamentalwahrscheinlichkeit f_i = exp(0,15 × S_i) / Σ_j exp(0,15 × S_j).
  Die Temperatur 0,15 ist so gewählt, dass bei einem Score-Abstand von 16 Punkten (etwa −8 bis +8) das Verhältnis
  zwischen bestem und schwächstem Pferd etwa 10 : 1 beträgt (e^(0,15 × 16) ≈ 11). Das entspricht grob der Spanne
  mittlerer PMU-Felder.

**Schritt 3 – Kombination**
- log p_i = 0,80 × log q_i + 0,20 × log f_i + Abschlag_i. Danach normieren, sodass Σ p_i = 100 %.
- Abschlag_i: nur aus Zuverlässigkeitsfaktoren (Trab: Disqualifikationsrisiko, Hindernis: Sturz- und
  Verweigerungsrisiko), siehe Faktoren. Höchstens log(0,7).
- Kappung: p_i ≤ 1,6 × q_i und p_i ≥ 0,5 × q_i. Ohne neue, bestätigte Belege weicht v0.1 nicht weiter vom Markt ab.
- Ergebnis je Pferd: q_i, f_i, p_i. Die Summe aller p_i muss 100,0 % ergeben (auf 0,1 % runden und
  Rundungsrest dem Favoriten zuschlagen).

**Schritt 4 – Value-Prüfung**
- Simple Gagnant: EV_i = p_i × o_i (aktuelle Quote). Wette, wenn EV_i ≥ Schwelle (siehe Befehl, Start 1,15).
- Simple Placé: nur, wenn eine aktuelle Placé-Quote (Rapport probable) vorliegt. Platzwahrscheinlichkeit nach Harville
  aus den p_i (Plätze: 3 bei ≥ 8 Startern, 2 bei 4–7 Startern, keine Placé-Wette bei < 4 Startern). Harville
  überschätzt Favoriten im Platz, deshalb wird P(Platz) beim Favoriten des Rennens um 5 % relativ gekürzt.
  Fehlt die Placé-Quote, gilt „unbekannt“ und es gibt keine Placé-Wette.
- Basis-Schutzregeln (gelten immer, keine Hypothesen):
  - Keine Gagnant-Wette bei aktueller Quote > 30. Grund: Favorite-Longshot-Bias im Totalisator und große Unsicherheit.
  - Keine Wette, wenn der Quotenzeitpunkt mehr als 45 Minuten vor dem Start liegt (kleiner Pool, die Quote ist
    noch nicht belastbar).
  - Höchstens 2 Wetten je Rennen (z. B. Gagnant und Placé auf dasselbe Pferd, oder zwei Gagnant-Wetten).
  - Ist der Abstand allein durch einen Ersatzwert aus Schritt 1 entstanden: keine Wette.
- Einsatz immer 1 Einheit (Flat Stake).

**Schritt 5 – Hypothesen notieren (ohne Wirkung)**
- Für jede Regel mit Status „Hypothese“, deren Bedingung im Rennen erfüllt ist: Regel-ID, Pferd und Richtung (+/−)
  notieren. Das ändert weder p_i noch die Wette. Diese Notizen sind das Material für Schritt B.

**Schritt 6 – Ausgabe festschreiben** (Datei `data/predictions/<rennen_id>.json`)
```json
{
  "rennen_id": "20261106R1C4",
  "start_utc": "2026-11-06T13:50:00Z",
  "festgeschrieben_utc": "…",
  "skill_version": "v0.1",
  "disziplin": "TRAB|GALOPP|HINDERNIS",
  "rennart": "…", "distanz_m": 0, "starter": 0, "nichtstarter": [],
  "quoten_zeitpunkt_utc": "…", "overround": 0.0,
  "quellen": [{"url": "…", "abgerufen_utc": "…", "inhalt": "Programm|Starter|Quoten|Presse|Pronostic"}],
  "pferde": [{"nr": 1, "name": "…", "q_markt": 0.0, "f_fund": 0.0, "p": 0.0, "quote": 0.0,
              "ev": 0.0, "faktoren": {"form": 0}, "unbekannt": []}],
  "wetten": [{"nr": 1, "pferd": "…", "wettart": "Simple Gagnant", "quote_tipp": 0.0, "einsatz": 1, "ev": 0.0}],
  "keine_wette_grund": null,
  "hypothesen_notizen": [{"regel": "H-T1", "nr": 1, "richtung": "+"}]
}
```
Danach `sha256sum data/predictions/<rennen_id>.json` ausführen und den Hash in STATE.md eintragen. Die Datei wird
nie mehr geändert. Korrekturen kommen als neue Notiz in STATE.md, nicht in die Datei.

---

# Faktoren und Gewichtung je Disziplin

Bewertung je Faktor −2 … +2 relativ zum Feld (siehe Schritt 2). Das Gewicht steht in Klammern.

## Die Musique lesen (alle Disziplinen)
- Sie wird von **links (jüngster Lauf) nach rechts** gelesen. Eine Zahl in Klammern, z. B. „(25)“, markiert den
  Jahreswechsel. Die Läufe rechts davon stammen aus 2025.
- Ziffer = Platz. 0 = nicht unter den ersten 9 (bzw. nicht platziert).
- Buchstabe nach der Ziffer = Disziplin: a = attelé, m = monté, p = plat (Galopp), h = haies, s = steeple-chase,
  c = cross.
- Sonderzeichen: D = disqualifiziert (Trab: Galoppsprung oder Gangartfehler), A = angehalten (arrêté),
  T = gestürzt (tombé). Andere Buchstaben (z. B. R) bedeuten je nach Quelle verschiedene Dinge: in der Quelle
  nachsehen, sonst „unbekannt“.
- Die Musique sagt nichts über Klasse, Distanz und Boden des jeweiligen Laufs. Wenn möglich, die detaillierten
  Leistungen (performances détaillées) dazunehmen.

## TRAB (attelé / monté)
| Faktor | Gewicht | Bewertung |
|---|---|---|
| Form: letzte 5 Läufe in **derselben Disziplin** (attelé bzw. monté), jüngere Läufe zählen stärker | 3,0 | Platzierungen auf vergleichbarem Niveau; D bei frischer Form nicht als Leistung zählen, aber unter Zuverlässigkeit |
| Klasse: Gewinnsumme (gains) relativ zur Grenze der Prüfung, Niveau der letzten Rennen (Gruppe, Vincennes, Provinz) | 2,0 | Nahe an der gains-Obergrenze = in dieser Prüfung stark; Wechsel aus einer höheren Klasse = + |
| Driver bzw. Reiter (monté): Klasse und Formkurve, Wechsel zu einem Top-Driver | 2,0 | Top-Driver des Meetings bzw. gezielter Wechsel nach oben = + |
| Beschlag (Déferrage): D4 = barfuß an allen vier Hufen, DA = vorn, DP = hinten | 1,5 | D4 (vor allem erstmals oder erstmals wieder) = +; zurück zu Eisen nach D4-Leistungen = − |
| Startart und Startplatz: Autostart-Nummer bzw. Volte mit Zulage (z. B. +25 m) | 1,5 | Autostart: zweite Reihe bzw. ganz außen = −; Volte: Zulage = −, wenn das Pferd nicht klar überlegen ist |
| Trainer: Formkurve der letzten 30 Tage, Erfolgsquote mit diesem Driver | 1,5 | |
| Distanz und Bahn: Eignung für die Distanz, Bahnkenntnis (z. B. Steigung der Grande Piste in Vincennes), Laufrichtung | 1,0 | |
| Frische: Tage seit dem letzten Lauf, Comeback nach Pause, Laufserie | 1,0 | Lange Pause ohne Qualifikationsform = −; nicht verwechseln mit gezielter Vorbereitung |
| **Zuverlässigkeit** (Abschlag in Schritt 3, kein Score): Anteil D/A in den letzten 10 Läufen | – | ≥ 3 D in 10 Läufen: Abschlag log(0,85); ≥ 5: log(0,7) |

Begründung: Im Trab dominieren Form, Klasse (über die gains-Logik) und Driver. Barfußlaufen und Startposition sind
die bekanntesten trabspezifischen Hebel in der französischen Fachpresse. Disqualifikationen sind das Hauptrisiko
einer Siegwette.

## GALOPP (plat)
| Faktor | Gewicht | Bewertung |
|---|---|---|
| Form: Niveau der letzten 3–4 Läufe (Platz, Abstand zum Sieger, Klasse des Rennens) | 3,0 | |
| Gewicht und Rating: in Handicaps getragenes Gewicht gegen das Rating (Valeur) der letzten guten Leistung; Erlaubnis (décharge) des Reiters | 2,0 | Rating heute unter dem Niveau der letzten Siegform = +; deutlich darüber = − |
| Boden (terrain): bon, souple, collant, lourd, très lourd, PSF (Kunstbahn) | 1,5 | Nachgewiesene Eignung = +; heute erstmals auf diesem Boden = 0 (unbekannt) |
| Startbox (corde) × Bahn × Distanz × Feldgröße | 1,5 | Nur werten, wo der Boxeffekt auf dieser Bahn und Distanz bekannt ist; große Felder und kurze Distanzen verstärken ihn |
| Jockey: Klasse, Formkurve, Wechsel zu einem Top-Jockey | 1,5 | |
| Trainer: Formkurve der letzten 30 Tage, Trainer-Muster (z. B. Reprise, Handicap-Debüt) | 1,5 | |
| Distanz-Eignung (Siege bzw. Platzierungen auf ± 200 m) | 1,0 | |
| Frische: Tage seit dem letzten Lauf, Reprise nach Pause | 1,0 | |
| Ausrüstung: Scheuklappen (œillères) erstmals | 0,5 | |
| Abstammung, nur bei Debütanten bzw. unbekanntem Boden | 0,5 | |

Begründung: Klasse und Form tragen am meisten. In Handicaps zählt die Differenz zwischen getragenem Gewicht und
tatsächlichem Leistungsvermögen. Box und Boden sind bahnspezifisch und werden nur mit Beleg gewertet. Die
Repository-Werkzeuge (power_modell.py, value_bets.py) liefern dazu Zahlen, wenn die Daten erreichbar sind.

## HINDERNIS (haies / steeple-chase / cross)
| Faktor | Gewicht | Bewertung |
|---|---|---|
| Form: letzte 3–4 Läufe über Hindernisse, gleiche Art (haies bzw. steeple) | 2,5 | Form aus Flachrennen zählt nur halb |
| Steher-Qualität und Distanz | 1,5 | |
| Boden (Hindernisrennen laufen oft auf schwerem Boden) | 1,5 | |
| Gewicht (inkl. Erlaubnis) | 1,5 | |
| Jockey und Trainer (Hindernis-Spezialisten, Auteuil-Ställe) | 1,5 | |
| Bahnkenntnis (Auteuil, Pau, Enghien, Compiègne …): Siege bzw. Platzierungen auf dieser Bahn | 1,0 | |
| Frische | 1,0 | |
| **Springsicherheit** (Abschlag in Schritt 3): T/A (und belegte Verweigerungen) in den letzten 8 Hindernisläufen | – | 2 Vorfälle: log(0,85); ≥ 3: log(0,7) |

Begründung: Im Hindernisrennen ist die Siegchance immer durch das Risiko begrenzt, das Ziel nicht zu erreichen.
Deshalb ist Springsicherheit ein eigener Abschlag und kein Score-Faktor.

---

# Aktive Regeln

In v0.1 ist keine Regel aktiv. Alle Regeln sind Hypothesen und beeinflussen keine Wette. Eine Regel wird „Aktiv“
erst nach Bestätigung auf **neuen** Rennen, die nach der Aufnahme als Hypothese festgeschrieben wurden.
Spalten: n = Fälle seit Aufnahme, ROI = Flat-Stake-ROI der Fälle, Kalibrierung = Siege / erwartete Siege nach
Marktwahrscheinlichkeit (A/E).

| ID | Regel | Geltung | n | ROI | Kalibrierung | Status |
|---|---|---|---|---|---|---|
| H-T1 | Erstmals D4 (oder erstmals wieder D4 nach ≥ 3 Läufen mit Eisen): p_i × 1,15 | TRAB | 0 | – | – | Hypothese |
| H-T2 | Autostart, Start aus der zweiten Reihe bei ≥ 12 Startern: p_i × 0,85 | TRAB, Autostart | 0 | – | – | Hypothese |
| H-T3 | Wechsel zu einem Driver mit Top-5-Siegquote des Meetings: p_i × 1,10 | TRAB | 0 | – | – | Hypothese |
| H-G1 | Favorit des Marktes (q ≥ 30 %) in einem Handicap mit ≥ 14 Startern: p_i × 0,90 | GALOPP, Handicap | 0 | – | – | Hypothese |
| H-G2 | Erstmals Scheuklappen nach ≥ 3 Läufen ohne: p_i × 1,10 | GALOPP | 0 | – | – | Hypothese |
| H-G3 | Gewichtserlaubnis ≥ 2 kg in Handicaps: p_i × 1,08 | GALOPP, Handicap | 0 | – | – | Hypothese |
| H-H1 | Gestürzt bzw. angehalten im letzten Lauf, sonst sicher: kein Abschlag (Marktüberreaktion) | HINDERNIS | 0 | – | – | Hypothese |
| H-A1 | Quote steigt (driftet) zwischen Morgenquote und aktueller Quote um > 50 %: keine Wette auf dieses Pferd | ALLE | 0 | – | – | Hypothese |
| H-A2 | Favorite-Longshot-Bias: Gagnant nur bis Quote 15 statt 30 | ALLE | 0 | – | – | Hypothese |

# Hypothesen

Zu jeder Regel: Grundlage und Prüfkriterium. „Bestätigt“ heißt für alle Regeln: mindestens 30 neue Fälle, A/E über
1,0 in Richtung der Regel, und der Brier Score von p mit der Regel ist besser als ohne. Erst dann darf sie nach
„Aktiv“, und höchstens 2 Änderungen je Lernschritt.

- **H-T1 (D4 erstmals):** In der französischen Trabpresse gilt der Wechsel auf barfuß als bekanntes Signal. Offen ist,
  ob der Markt es schon voll einpreist. Prüfen: A/E gegen q.
- **H-T2 (zweite Reihe im Autostart):** Pferde aus der zweiten Reihe verlieren Boden oder werden eingeschlossen. Es ist
  unklar, ob der Markt das unterschätzt. Prüfen: A/E gegen q, getrennt nach Bahn.
- **H-T3 (Driver-Upgrade):** Ein Wechsel zu einem Top-Driver kann eine gezielte Absicht zeigen. Prüfen: A/E gegen q.
- **H-G1 (Favorit im großen Handicap):** In großen Handicaps (z. B. Quinté+) könnte die Öffentlichkeit Favoriten
  überwetten. Prüfen: A/E der Favoriten gegen q.
- **H-G2 (Scheuklappen erstmals):** Gilt in der Literatur als gemischtes Signal. Nur prüfen, nicht vorab gewichten.
- **H-G3 (Erlaubnis):** Die Gewichtserlaubnis (décharge) junger Reiter könnte unterbewertet sein. Prüfen: A/E gegen q.
- **H-H1 (Sturz im Vorlauf):** Ein einzelner Sturz führt oft zu längeren Quoten, obwohl das Pferd sonst sicher springt.
- **H-A1 (Drift):** Steigende Quoten kurz vor dem Start können auf negative Information hinweisen (Stall wettet nicht,
  Gesundheit). Prüfen: A/E gegen die Endquote bei Pferden mit starkem Drift.
- **H-A2 (Longshots):** Der Favorite-Longshot-Bias ist für Totalisatormärkte vielfach belegt. Prüfen: ROI und A/E nach
  Quotenklassen (< 5, 5–10, 10–15, 15–30).

Notizen aus Lernschritten mit < 30 Wetten: (noch keine)

# Verworfene Regeln

(noch keine) – Format: ID | Regel | n | ROI | A/E | Grund | verworfen in Version

# Bekannte Fallen

- **Nichtstarter (NP):** Eine Wette auf einen Nichtstarter wird erstattet (Status „nichtstarter“, gewinn 0). Fallen
  Starter kurz vor dem Start heraus, verschieben sich alle Marktwahrscheinlichkeiten. Deshalb Quoten erst nach den
  letzten NP-Meldungen nehmen. Bei Placé ändert sich durch einen NP die Zahl der bezahlten Plätze (8 → 7 Starter:
  nur noch 2 Plätze).
- **Quotenbewegung im Totalisator:** Die PMU-Quote vor dem Start ist **nicht** die Auszahlung. Bezahlt wird der
  Endrapport. In den letzten Minuten kommt viel Geld (auch aus ausländischen Pools), und Favoriten verkürzen oft.
  Deshalb ist der CLV (Tippquote gegenüber Endquote) die wichtigste Frühkennzahl. Gewertet wird im Ledger immer mit
  quote_end.
- **Kleine Felder:** Bei < 8 Startern gibt es nur 2 Placé-Plätze, bei < 4 keine Placé-Wette. Kleine Felder haben einen
  dünnen Pool und springende Quoten. In kleinen Feldern ist ein EV-Vorteil oft nur Rauschen.
- **Placé-Mindestrapport:** Auf Favoriten sind Placé-Rapports sehr niedrig. Die exakten Mindestauszahlungsregeln des
  PMU sind nicht verifiziert (unbekannt). Bis zur Prüfung keine Placé-Wette mit Quote < 1,3.
- **Disziplin im Trab:** Musique-Läufe in monté sagen wenig über attelé und umgekehrt. Immer die Disziplin-Buchstaben
  lesen.
- **Musique ohne Kontext:** Eine „1“ in einem schwachen Provinzrennen ist nicht dasselbe wie eine „3“ in Vincennes.
  Ein „0“ nach einer Pause kann ein Vorbereitungslauf gewesen sein.
- **Quinté+ und Publikumsgeld:** In Quinté+-Rennen gibt es sehr viel Gelegenheitsgeld. Presse-Favoriten werden dort
  eher überwettet. Das ist eine Hypothese (H-G1), keine Tatsache.
- **Zeitzonen:** Das PMU-Programm liefert Startzeiten in Epoch-ms und mit Zeitzonen-Offset. Alles in UTC umrechnen.
  Programmzeiten können sich am Renntag verschieben (Verspätungen). Den Start nur über den Status „gestartet“ bzw.
  „Arrivée“ feststellen, nicht über die Uhr.
- **Informationsleck:** Nach dem Start erscheinen auf vielen Seiten Arrivées und Rapports. Für die Analyse nur
  Seiten verwenden, die vor dem Start abgerufen wurden, und den Abrufzeitpunkt notieren. Taucht vor dem Festschreiben
  ein Ergebnis auf: kontaminiert.
- **Rennen im Ausland:** Der PMU nimmt Wetten auf ausländische Rennen an (z. B. aus Schweden oder Deutschland). Die
  Faktoren sind für französische Rennen gedacht. Ausländische Rennen nur analysieren, wenn das Auswahlkriterium sie
  ausdrücklich einschließt.
- **Dead Heat:** Bei totem Rennen teilt der Rapport die Auszahlung. Den offiziellen Rapport übernehmen, nicht selbst
  rechnen.
