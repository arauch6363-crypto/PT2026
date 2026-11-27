# Umsetzungsplan: Skill rennkarten-durchgang-neu und Lernschleifen (27.11.2026)

Ergebnis der Durchsicht des Skills am 27.11.2026; vom Nutzer als Ganzes freigegeben. Ziel: bessere Tipps, ohne dass
die Lernschleifen den Skill einseitig strenger machen. Der Nutzer findet die heutige Strenge passend.

## Befunde, auf denen der Plan beruht

- **Testsatz gesättigt und einseitig:** 7 Rennen vom 16.11., 16 Kandidaten (11 nein, 5 klein, 0 Wette), 14 Stände in
  Folge 7/7. Eine zu strenge Regel fällt nicht auf. Neue Fälle (auch volle Wetten) liefert der Nutzer in den
  nächsten Tagen; bis dahin bleibt der Testsatz, wie er ist.
- **Ergebnisanalyse verschärft fast nur:** 10 von 14 Fällen waren verlorene Tipps, alle 27 Vorschläge angenommen. Die
  Gegenprobe sieht nur Verlierer desselben Tages.
- **Regelprotokoll ist langsam:** 87 Kennungen, gezählt wird jedes zitierte Argument; Kursspanne und Endquote werden
  nicht ausgewertet.
- **Lesefehler statt Urteilsfehler:** Algeciras (Bodenbilanz), Senorito (Trainerwechsel), Drumard (Referenzlauf unter
  „Ältere Läufe“) – das Blatt kann solche Lagen selbst melden.
- **Gewichtung:** [ausschlaggebend] gibt es nur auf der Gegen-Seite, „höchstens kleine Wette“ steht verstreut im
  Fließtext, die Prüfung (`rennen_pruefen_streng`) kontrolliert nur Kennungen.
- **Kursspanne ohne Verfahren**, oft knapp unter dem Festkurs. **Mindestquote** widersprüchlich (SKILL: unterer Rand,
  Beispiel in AUSGABE: oberer Rand).

## Entscheidungen des Nutzers

- **Mindestquote entfällt.** Gespielt wird zum Festkurs beim Durchgang oder gar nicht. `ausloesen.py` gibt dem
  Wett-Agenten ohne `mq` schon heute den Festkurs als Untergrenze mit (`k.get("mq") or k.get("fk")`).
- Die einseitige Verschärfung wird jetzt angegangen, bevor sie die Strenge verändert.

## Rahmen für jede Änderung

- Branch `claude/brave-clarke-xjr70b`, ein Commit je Arbeitspaket, kein PR.
- Vor Textänderungen an `SKILL.md`, `EINSICHTEN.md`, `AUSGABE.md`, Subagenten-Prompts:
  `.claude/skills/writing-for-agents/SKILL.md` lesen und anwenden; Begriffe aus `GLOSSARY.md`.
- Regeln aus `LERNSCHLEIFE.md` gelten: Kennungen dauerhaft, jede Kennung an genau einem Ort, `SKILL.md` ohne
  Pferdenamen als Beleg. Bestehende Regeln behalten ihren Inhalt; dieser Plan ändert Form, Verfahren und Prüfung,
  keine Gewichte des Nutzers.
- Nach Code-Änderungen `python -m pytest -q tests`, bei Änderungen an Karte/Pipeline auch `python selftest.py`.
- Alte `durchgang_*.json` (mit `mq`, ohne neue Felder) müssen überall weiter lesbar sein.
- Der Testsatz läuft **einmal am Ende von Teil B** für alle Skill-Änderungen (`claude_projekt/aufgabe_testsatz.md`,
  gestuft). Bei Rückschritt: nichts erzwingen, nicht ablegen, Konflikt berichten.

## Teil A – Messung und Ergebnisanalyse (unabhängig von Teil B)

Dateien: `ergebnis_analyse.py`, `tests/test_ergebnis_analyse.py`, `.claude/skills/ergebnis-analyse/*.md`,
`claude_projekt/aufgabe_ergebnisanalyse.md`, `auswertung/`, ggf. `GLOSSARY.md` (nur neue Begriffe anhängen).

- **A1 Rückschau für verschärfende Vorschläge.** Neuer Befehl `ergebnis_analyse.py rueckschau KENNUNG…`: aus
  `auswertung/regelprotokoll.csv` je Kennung, wie viele bisherige Claude-Tipps (wette, klein) sie zitierten und wie
  viele davon gewannen, dazu dieselbe Zählung für abgelehnte Kandidaten. Im Skill `ergebnis-analyse` (Schritt 2,
  Gegenprobe): Ein Vorschlag, der Urteile strenger macht, nennt zusätzlich die Rückschau – welche früheren Sieger
  unter den Tipps die Regel gestrichen hätte. Neues Vorschlagsfeld `wirkung` (`strenger`, `lockerer`, `neutral`).
- **A2 Drift.** Neuer Befehl `drift`: je Tag und über die letzten 7 Tage Zahl der Kandidaten und Anteil wette / klein /
  nein (je Pferd einmal), dazu aus `vorschlaege.csv` das Verhältnis angenommener Vorschläge `strenger` : `lockerer`
  (ältere Vorschläge ohne `wirkung` als „unbekannt“). Die Ergebnisanalyse gibt die Drift je Tag im Bericht an den
  Nutzer mit aus; fällt der Tipp-Anteil der letzten 7 Tage unter die Hälfte des Anteils davor, ist das ein Anlass,
  den sie ausdrücklich nennt (kein automatischer Eingriff).
- **A3 Kandidatenprotokoll.** Neue Datei `auswertung/kandidaten.csv`, fortgeschrieben wie das Regelprotokoll, eine
  Zeile je Kandidat: datum, race_id, no, horse, urteil, fk, spanne_von, spanne_bis, p_modell, p_markt, endquote
  (`odds_final`), ausschlag_kennung, gewonnen. Nur vorwärts (ältere Tage nur, soweit die Daten im Repo liegen).
- **A4 Kalibrierung und Kurs gegen Endquote.** Neuer Befehl `kalibrierung` auf `kandidaten.csv`: je Urteil n, Siege,
  erwartete Siege nach Markt und nach Mitte der Kursspanne (1 / Mitte), Ø ln(fk / endquote) mit Zahl der Fälle
  (positiv = Festkurs lag über der Endquote). Kurz im Skill `ergebnis-analyse` und in ADR 0003 (Nachtrag) erklären,
  was die Zahlen sagen und was nicht.
- **A5 Regelprotokoll schärfen.** `bericht` zusätzlich mit Auswertung nur der Ausschlag-Kennung und gebündelt je
  Prüfschritt (Abschnitt der Kennung in `EINSICHTEN.md` bzw. Liste in `SKILL.md`). „Unter Druck“ bleibt, wie es ist.

## Teil B – Skill, Blatt, Prüfung, Ablauf

Dateien: Skill-Ordner `rennkarten-durchgang-neu`, `durchgang.py`, `tests/test_blatt.py`, `tests/test_durchgang.py`,
`claude_projekt/aufgabe_durchgang.md`, `claude_projekt/aufgabe_testsatz.md`, `GLOSSARY.md`, `racecard_template.html`,
`agent_wettstar/` (nur Doku zu `mq`).

- **B1 Mindestquote streichen.** Aus `SKILL.md`, `AUSGABE.md`, `GLOSSARY.md`, den Subagenten-Prompts
  (`aufgabe_durchgang.md`, `aufgabe_testsatz.md`) und der Tabelle in `durchgang.py`. `mq` bleibt in `durchgang.py`
  ein optionales Feld (alte Dateien). Anzeige in `racecard_template.html` ohne `mq` sauber. `ausloesen.py` nicht
  ändern (Rückfall auf den Festkurs ist gewollt); Doku des Wett-Agenten anpassen: Untergrenze = Festkurs beim
  Durchgang.
- **B2 Auslöser im Blatt.** `blatt.py` druckt je Kandidat und Maßstab eine Zeile „Auslöser:“ mit Kennung und Zahl, wo
  die Bedingung reine Rechnung ist; Schwellen wie in `SKILL.md`/`EINSICHTEN.md`:
  ARR des Referenzlaufs etwa 3 Punkte und mehr unter dem Besten (`G-ARR-UNTER`); exposed und ab 1 kg über letzter
  Siegmarke im Handicap (`G-UEBER-SIEGMARKE`); ab 62 kg auf Très souple oder schwerer (`G-GEWICHT-BODEN`); ab 4
  Starts in 6 Wochen (`G-STARTFOLGE`); Gespann ab 20 Starts ohne Sieg (`G-GESPANN-OHNE-SIEG`); Bahnbilanz des
  Trainers ab 20 Starts mit A/E bis 0,5 (`G-TRAINER-KALT`); Pause ab 60 Tagen (`F-PAUSE`); Trainerwechsel
  (`F-TRAINERWECHSEL`); erstmals Belag / Boden ab Très souple / Distanzgruppe (`F-BELAG-NEU`, `F-BODEN-NEU`,
  `F-DISTANZ-NEU`); Abstammung gesamt −15 und schlechter bei erstem bis drittem Lauf auf Belag oder Boden
  (`G-ABSTAMMUNG`); Ausrüstung fällt weg bzw. kommt zurück mit klar besserer Bilanz (`G-AUSRUESTUNG-WEG`,
  `P-AUSRUESTUNG-ZURUECK`); kein Referenzlauf oder nur älter als ein Jahr (`G-KEIN-REFERENZ`); Referenzlauf steht
  unter „Ältere Läufe“ (Hinweis ohne Kennung); `P-CGD` bei Großbuchstaben; signifikante Box (`G-BOX`, `P-BOX`).
  Dazu im Rennkopf eine Leitfrage-Zeile: Referenz-ARR je Kandidat und Maßstab gegen Top-ARR. Was sich nicht sauber
  rechnen lässt, weglassen statt raten. `SKILL.md` (Ablauf Schritt 4): Jeder Auslöser wird im Urteil bestätigt oder
  mit Beleg entkräftet; Auslöser sind nicht vollständig, die Prüfliste gilt weiter. `DATEN.md` und Tests ergänzen.
- **B3 Veto und Deckel.** In `EINSICHTEN.md` die Gewichte schärfen, ohne Inhalte zu ändern:
  [ausschlaggebend] = **Veto** (Urteil „nein“, außer eine im Ausschlag benannte Ausnahme); neuer Vermerk **Deckel**
  je Kennung für Einsichten, deren Text schon „höchstens kleine Wette“ / „trägt keine kleine Wette“ sagt
  (`G-ARR-UNTER`, `G-UEBER-SIEGMARKE`, `P-ERSTER-ANSATZ`, `G-GESPANN-OHNE-SIEG`, Trainer-Bahnbilanz usw. – nur wo der
  bestehende Text es hergibt). Maschinenlesbar, bei Einträgen mit zwei Kennungen eindeutig je Kennung. `SKILL.md`,
  Gesamturteil: zuerst Veto, dann Deckel, dann abwägen. „Typischer Fehler 2“ darauf beziehen.
- **B4 Bild einer vollen Wette.** Kurzer Abschnitt in `SKILL.md` (Gesamturteil), abgeleitet aus den Wetten des Nutzers
  in `docs/faelle_rennkarten_durchgang.md` („Wetten“) und dem Interview: was eine volle Wette positiv ausmacht. Ohne
  Pferdenamen, höchstens fünf Zeilen. **Als Entwurf kennzeichnen** – der Nutzer bestätigt den Wortlaut.
- **B5 Verfahren der Kursspanne.** `SKILL.md`, Gesamturteil: Anker nennen (fairer Modellkurs = 1 / Modell-Siegchance
  und Festkurs als Marktsicht), von dort mit benannten Argumenten verschieben; die Spanne steht fest, bevor das
  Urteil fällt. „Klar über der Spanne“ = Festkurs etwa 10 % und mehr über dem oberen Rand (deckt die 5 % Steuer).
  Neues Ausgabefeld `anker` (ein Satz) oder im Ausschlag – die einfachere Form wählen.
- **B6 Faustregel und Fehler 5 in Einklang.** Ein Satz: Die Kursspanne entscheidet, ob der Kurs reicht; die
  Faustregel sagt, wie viel Beweislage bei welchem Value nötig ist. Kein neuer Inhalt.
- **B7 Prüfung erweitern** (`durchgang.rennen_pruefen_streng`, Fehlermeldungen so, dass der Subagent sich korrigieren
  kann): bei „wette“/„klein“ Spanne vorhanden und Festkurs über dem oberen Rand; Veto-Kennung in `gegen` oder
  `ausschlag` verlangt „nein“ oder das Wort „Ausnahme“ im Ausschlag; Deckel-Kennung schließt „wette“ aus (dieselbe
  Ausnahme); neues Pflichtfeld `leitfrage` je Kandidat: {referenzlauf (Datum oder „keiner“), ref_arr, top_arr,
  massstab_arr}. Optionaler Abgleich gegen die Karte (Top-ARR, Datum ist ein Lauf des Pferdes), wenn die Karte
  mitgegeben wird; Prompts rufen die Prüfung mit Karte auf. Alle Leser der Durchgang-Dateien vertragen die neuen
  Felder.
- **B8 Prüf-Subagent für Tipps.** `aufgabe_durchgang.md` Schritt 4 und gespiegelt `aufgabe_testsatz.md`: Für jedes
  Rennen mit „wette“ oder „klein“ ein zweiter Subagent mit leerem Kontext, der Skill-Grundlagen, Blatt und die
  Ergebnisdatei bekommt. Auftrag: jede zitierte Tatsache der Tipps gegen das Blatt prüfen, Veto und Deckel prüfen,
  jeden Auslöser behandelt? Er darf ein Urteil **nur** bei falscher Tatsache oder übersehenem Veto/Deckel senken,
  nie wegen anderer Gewichtung, und nie anheben. Ergebnis je Kandidat im Feld `pruefung` (Befund, ein bis zwei
  Sätze) und `urteil_vor_pruefung`, damit messbar bleibt, wie oft und mit welchem Ausgang er eingreift (in A3 als
  Spalte aufnehmen, wenn vorhanden).
- **B9 Kontext des Subagenten.** `GLOSSARY.md` so gliedern, dass die Begriffe für den Durchgang vorne in einem Block
  stehen, und die Prompts auf diesen Block begrenzen – nur, wenn das ohne zweite Quelle der Begriffe geht
  (`skill_paket.py` beachten). Sonst weglassen und im Bericht nennen.
- **B10 Abschluss.** `LERNSCHLEIFE.md` um die neuen Regeln ergänzen (Veto/Deckel-Vermerk, Auslöser gehören ins
  Blatt, Rückschau bei Verschärfung). Tests, dann Testsatz einmal; bei „Übernehmen: ja“ mit `--ablegen` ablegen und
  committen.

## Offen, nicht Teil der Umsetzung

- Neue Testfälle, vor allem volle Wetten und andere Tage (Nutzer liefert; Durchsicht steht beim 18.11.).
- Wortlaut von B4 und die Schwelle „etwa 10 %“ in B5 bestätigt der Nutzer nach der Umsetzung.
