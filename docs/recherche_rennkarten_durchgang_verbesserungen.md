# Recherche: Verbesserungen am Skill `rennkarten-durchgang-neu`

Stand 18.11.2026. Untersucht wurden zwei Achsen: (1) wie gut der Skill Anthropics Leitlinien für Agent Skills folgt,
(2) ob sich die Wettmethodik verbessern lässt. Der Skill selbst wurde nicht geändert. Begriffe wie in `GLOSSARY.md`.

**Kennzeichnung:** **Quelle:** = was die genannte Quelle sagt. **Befund:** = was im Repo steht (Datei angegeben).
**Folgerung:** = eigene Schlussfolgerung, nicht von der Quelle gedeckt.

**Quellenlage:** Diese Sitzung hatte nur eingeschränkten Netzzugang. Vollständig gelesen wurden die Anthropic-Seiten
(platform.claude.com, code.claude.com), `skills/skill-creator/SKILL.md` aus github.com/anthropics/skills und die
Conditions Générales 2026 von France Galop (PDF). arxiv.org, gesetze-im-internet.de, legifrance.gouv.fr, pmu.fr,
anj.fr und die Spiegelserver der Aufsätze waren gesperrt. Für die Fachaufsätze konnten deshalb nur die bibliografischen
Angaben und die Abstracts aus Suchergebnissen geprüft werden. Im Quellenverzeichnis ist je Quelle vermerkt, wie weit
sie geprüft ist: **V** = Volltext gelesen, **A** = Abstract bzw. Zusammenfassung im Suchergebnis geprüft,
**n. v.** = aus Kenntnis der Arbeit, in dieser Sitzung nicht nachgelesen. Wer eine Aussage mit A oder n. v. als
Grundlage für eine Regel nimmt, sollte vorher den Volltext lesen.

---

## 1. Der Skill heute (kurz)

- **Dateien:** `SKILL.md` (226 Zeilen, rund 2.500 Wörter, 18 KB), `DATEN.md` (Feldherkunft, Lücken), `FAELLE.md`
  (120 Zeilen, 19 KB, Fallsammlung mit Themenindex), `scripts/blatt.py` (312 Zeilen, reine Standardbibliothek).
  Dazu kommen `GLOSSARY.md` im Repo-Hauptordner (über `skill_paket.py` ins claude.ai-Paket kopiert) und
  `durchgang.py` (Prüfung und Zusammenführung des JSON-Ergebnisses).
- **Ablauf:** `blatt.py` holt die Fakten aus der Karte. Danach liest der Agent den Rennkopf und prüft den Maßstab
  (FK-Favorit bzw. Zweiter im Festkurs). Je Kandidat (Value = Festkurs × Modell-Siegchance − 1 > 0) arbeitet er eine
  Prüfliste mit sieben Punkten ab und sammelt Pro-Argumente, Gegenargumente und Fragezeichen. Dann folgt das
  Gesamturteil mit eigener Kursspanne und der Leitfrage „reicht es für den Sieg?“: Wette (1 Einheit), kleine Wette
  (½) oder keine. Zum Schluss kommen Rennvergleich und Ausgabe als Markdown und JSON. Das JSON prüft
  `durchgang.rennen_pruefen`.
- **Automatik:** Die Routine `claude_projekt/aufgabe_durchgang.md` startet je Rennen einen Subagenten. Jeder liest
  SKILL.md, GLOSSARY.md, DATEN.md und FAELLE.md vollständig. Das Value-Dashboard (`value_bets.claude_auswertung`)
  rechnet die Ergebnisse zum Festkurs mit 5 % Steuer ab, getrennt nach NAP, BET und abgelehnten Kandidaten.
- **Was schon versucht wurde** (Git-Historie, `docs/interview_rennkarten_durchgang.md`):
  - Der alte Skill `rennkarten-durchgang` hatte 1.277 Zeilen (blinder Prognose-Abgleich). Er wurde am 16.11. entfernt
    (Commit 7a1e604).
  - Im Interview wurden eigene Siegchance, Schwelle +20 %, Fragezeichen-Zuschläge und ⅛ Kelly ausdrücklich verworfen
    zugunsten von „kein Rechnen“ (Q29), festen Einheiten (Q61) und eigener Kursspanne (Q62).
  - Seitdem wurden Regeln aus der Durchsicht ergänzt: Ausrüstungswechsel, Claimer → Handicap, keine kleine Wette als
    Ausweg, Maßstab. Eine Regel entsteht erst aus zwei gleichgerichteten Fällen oder auf ausdrückliche Ansage.

---

## 2. Achse 1: Skill-Engineering

Maßstab sind die Seite „Skill authoring best practices“
(<https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices>, **V**), die Claude-Code-Doku
(<https://code.claude.com/docs/en/skills>, **V**), `skill-creator`
(<https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md>, **V**) und der im Repo verfügbare
Skill `writing-for-agents` (Plugin-Skill, `SKILL.md` und `SKILL-MECHANICS.md`).

### 2.1 Was der Skill schon gut macht

| Leitlinie | Quelle | Befund |
|---|---|---|
| Frontmatter: `name` ≤ 64 Zeichen in Kleinbuchstaben, `description` ≤ 1.024 Zeichen, ohne XML | best-practices, Abschnitt „Skill structure“ | Erfüllt. Die Description hat 469 Zeichen; `skill_paket.pruefen` prüft die Grenzen sogar maschinell. |
| Description in der dritten Person, mit „was“ und „wann“ | best-practices, „Writing effective descriptions“: „Always write in third person“ | Erfüllt („Wählt … aus … Verwenden, wenn …“). |
| SKILL.md unter 500 Zeilen, Details in eigene Dateien | best-practices, „Token budgets“; code.claude.com: „Keep SKILL.md under 500 lines“ | Erfüllt: 226 Zeilen. DATEN.md und FAELLE.md liegen eine Ebene tief und sind direkt aus SKILL.md verlinkt („Keep references one level deep“). |
| Skripte für deterministische Schritte, „run“ statt „read“ klar benannt | best-practices, „Provide utility scripts“, „Prefer scripts for deterministic operations“, „Make execution intent clear“ | Erfüllt. `blatt.py` wird ausgeführt, nicht gelesen. Die Karte (über 10 MB) wird nie in den Kontext geladen. |
| Keine „voodoo constants“ | best-practices, „Solve, don't defer“ | Erfüllt. `TRAINER_NEU_LAEUFE`, `FENSTER_STARTS` und `DIST_TOL` sind kommentiert. `laden()` bricht mit einer klaren Meldung ab. |
| Validierungsschleife „plan-validate-execute“ | best-practices, „Create verifiable intermediate outputs“, „Implement feedback loops“ | Teilweise erfüllt. Jeder Subagent schreibt erst `rennen_<id>.json` und prüft es mit `durchgang.rennen_pruefen`, bis es fehlerfrei ist. Lücken: siehe 2.2. |
| Freiheitsgrade passend zur Aufgabe | best-practices, „Set appropriate degrees of freedom“: hohe Freiheit, wo „Heuristics guide the approach“; niedrige, wo „Consistency is critical“ | Gut getroffen. Die Faktenbeschaffung ist fest (Skript, festes JSON), das Urteil frei (Heuristik, Faustregel ausdrücklich „keine Rechenregel“). |
| Einheitliche Begriffe | best-practices, „Use consistent terminology“ | Sehr gut. `GLOSSARY.md` mit _Avoid_-Listen; Value und Value-Faktor sind ausdrücklich getrennt. |
| Beispiele und Ausgabevorlage | best-practices, „Template pattern“, „Examples pattern“ | Erfüllt. Strenge JSON-Vorlage, Markdown-Vorlage und FAELLE.md als Beispielsammlung. |
| Iteration aus echter Nutzung (Claude A/B) | best-practices, „Develop Skills iteratively with Claude“ | Erfüllt, sogar methodisch sauber: Die Durchsicht läuft mit ausgeblendeten Ergebnissen, Abweichungen werden je Fall eingeordnet, eine Regel braucht zwei gleichgerichtete Fälle. |

### 2.2 Lücken gegenüber den Leitlinien

**E1 – Keine Evaluationen.**
**Quelle:** „Create evaluations BEFORE writing extensive documentation … Build three scenarios“ und „Evaluations are
your source of truth for measuring Skill effectiveness“ (best-practices, „Build evaluations first“). skill-creator
legt Testfälle in `evals/evals.json` ab, lässt sie mit und ohne Skill laufen und vergleicht Versionen blind
(Abschnitte „Test Cases“, „Advanced: Blind comparison“). „Tested with Haiku, Sonnet, and Opus“ steht in der Checkliste.
**Befund:** FAELLE.md enthält gut 40 Fälle mit dem Urteil des Nutzers als Sollwert, also ein fertiges Eval-Set. Es
wird aber nur gelesen, nie gegen eine neue Skill-Fassung ausgeführt. Ob eine neue Regel (z. B. Maßstab) alte
Übereinstimmungen kippt, prüft niemand.
**Folgerung:** Ein Regressionstest „Skill-Version × Fallsammlung → Übereinstimmungsquote“ ist die größte
Engineering-Lücke. Vorsicht vor Leckage: Ein Fall darf beim Test nicht in der mitgelesenen FAELLE.md stehen
(Hold-out oder FAELLE.md ohne den Testfall).

**E2 – Validator prüft die Form, aber nicht den Inhalt.**
**Quelle:** „Make validation scripts verbose with specific error messages“; Validierung „for critical operations“
(best-practices).
**Befund:** `durchgang.rennen_pruefen` (durchgang.py, Zeile 194 ff.) prüft Status, Urteil und Festkurs, aber nicht:
- ob **alle** Kandidaten der Karte enthalten sind. Der Subagenten-Prompt verlangt das nur in Worten. Im Interview ist
  vermerkt: „R3C4 fehlt in beiden Durchgängen des 16.11. (Ursache klären)“.
- ob `mq` und `spanne` zueinander und zum Festkurs passen (siehe M2),
- ob der Maßstab das Pferd aus dem Blatt ist.

**E3 – Widerspruch im Ergebnisformat (Mindestquote).**
**Befund:** SKILL.md, Abschnitt Gesamturteil: „Mindestquote = unterer Rand der Spanne“, ebenso `GLOSSARY.md`. Das
Ausgabebeispiel in SKILL.md (Zeile 195) sagt aber: „fair eher 9–11, Mindestquote 11“, also den oberen Rand. Der Test
`tests/test_durchgang.py` (Zeile 40) baut `spanne: [mq − 1, mq]`, ebenfalls oberer Rand.
**Quelle:** „Use consistent terminology“ (best-practices).
**Folgerung:** Je nachdem, welche Stelle der Agent stärker gewichtet, entstehen verschiedene Mindestquoten.
Inhaltlich siehe M2.

**E4 – Zwei bis vier Stellen für dasselbe Format.**
**Quelle:** writing-for-agents, „Pruning“: „Keep each meaning in a single source of truth“.
**Befund:** Das Ergebnis-JSON ist viermal beschrieben:
- SKILL.md, Abschnitt Ausgabe,
- der Subagenten-Prompt in `claude_projekt/aufgabe_durchgang.md` (Feldliste noch einmal ausgeschrieben),
- README Zeile 720 (dort fehlt `massstab`, also schon veraltet),
- `durchgang.rennen_pruefen` (die tatsächliche Wahrheit).

Ähnlich ist `claude_projekt/skill_neu_einrichten.md` veraltet: „Die Karte kommt als HTML-Datei“. Der Skill und die ADR
setzen inzwischen `…_daten.json.gz` voraus, weil die HTML-Karte zu groß wird.

**E5 – Kontextlast je Subagent wächst mit jeder Durchsicht.**
**Quelle:** „The context window is a public good“ und „Does this paragraph justify its token cost?“ (best-practices,
„Concise is key“). Für Referenzdateien über 100 Zeilen empfiehlt die Seite ein Inhaltsverzeichnis. writing-for-agents
warnt vor **Sprawl** und **Sediment** („stale layers that settle because adding feels safe“).
**Befund:**
- Die Routine lässt jeden Subagenten alle vier Dateien vollständig lesen, rund 50 KB. Eigene Schätzung: etwa
  13.000–15.000 Tokens je Rennen, bevor das Blatt gelesen ist.
- FAELLE.md wächst bei jeder Durchsicht. Einträge der Art „Übereinstimmung ohne neue Erkenntnis“ sollen laut
  FAELLE.md schon jetzt nur kurz eingetragen werden.
- Der Themenindex „Muster nach Thema“ wirkt bereits wie ein Inhaltsverzeichnis (gut).

**Folgerung:** Sinnvoll ist eine Obergrenze oder Verdichtung, z. B. „Übereinstimmungen“ nach dem Bestätigen einer
Regel in einer Zeile je Thema zusammenfassen. Besser noch: Der Subagent liest FAELLE.md nur in den Themen, die
`blatt.py` für seine Kandidaten anzeigt.

**E6 – Zeitbezogene und historische Angaben in der Anleitung.**
**Quelle:** „Avoid time-sensitive information“; Altes gehört in einen eigenen Abschnitt „old patterns“
(best-practices). writing-for-agents prüft jede Zeile auf Relevanz.
**Befund:** SKILL.md beginnt mit „Aus dem Interview vom 10./11.11.2026“. Im Abschnitt Maßstab steht „(Vom Nutzer zur
Regel erklärt am 18.11., Fall Boomslang: …)“. Rund 20 Pferdenamen stehen im Regeltext. Der Name des Skills trägt
„-neu“, obwohl der alte Skill entfernt ist.
**Folgerung:** Die Pferdenamen helfen beim Nachschlagen in FAELLE.md. Je Regel genügt aber ein Name. Herkunft und
Datum gehören in FAELLE.md oder in das Interview. Das Umbenennen (`-neu` weg) betrifft `durchgang.py` (Vorgabe
`skill`), `aufgabe_durchgang.md`, `skill_paket.py`, README und das hochgeladene claude.ai-Paket. Es lohnt sich nur
zusammen mit einer ohnehin fälligen Paketänderung.

**E7 – Description: Auslöser schärfen, Inhalt kürzen.**
**Quelle:**
- „Include both what the Skill does and specific triggers/contexts“ (best-practices).
- skill-creator: Claude neige zum „undertrigger“, Descriptions dürften „a little bit pushy“ sein. Alle
  „when to use“-Angaben gehören in die Description, nicht in den Rumpf.
- writing-for-agents: „Cut identity the body already carries“ und je Branch ein Auslöser.
- code.claude.com: Description und `when_to_use` werden in der Skill-Liste bei 1.536 Zeichen abgeschnitten, deshalb
  „Put the key use case first“.

**Befund:** Die Description beschreibt ausführlich das „was“ (Pro, Gegen, Fragezeichen, Rennvergleich, Kursspanne,
Mindestquote, Einheiten), aber nur einen Auslöser („wenn eine Karte oder einzelne Rennen auf Wetten durchgegangen
werden sollen“). Laut `skill_neu_einrichten.md` schreibt der Nutzer typischerweise „Geh Toulouse durch“ oder
„Rennen R1C5“, oft mit einer hochgeladenen `racecard_*`-Datei.
**Folgerung:** Die Auslöser „Bahnname oder RxCy“, „hochgeladene `racecard_JJJJMMTT…`-Datei“ und „Siegwette, Value“
vorne nennen und die Aufzählung der Ausgabeteile kürzen. Das ist ein Kandidat für die Description-Optimierung von
skill-creator (20 Testanfragen, davon 8–10 „near misses“, z. B. Fragen zum Value-Dashboard oder zum Power-Modell, die
**nicht** auslösen sollen).

**E8 – Claude-Code-Funktionen ungenutzt (gering).**
**Quelle:** code.claude.com/docs/en/skills nennt `argument-hint`, `allowed-tools` (z. B.
`Bash(${CLAUDE_SKILL_DIR}/scripts/… *)`, damit das Skript ohne Rückfrage läuft) und `${CLAUDE_SKILL_DIR}` für den
Skill-Ordner.
**Befund:** SKILL.md erklärt den Skill-Ordner in Prosa für zwei Umgebungen („in Claude Code …, in claude.ai …“).
**Folgerung:** `${CLAUDE_SKILL_DIR}` wird nur in Claude Code ersetzt. Weil der Skill auch in claude.ai läuft, bleibt
die Prosa nötig. `argument-hint: "[KARTE] [Bahn|RxCy …]"` und ein `allowed-tools`-Eintrag für `blatt.py` wären in
Claude Code ein kleiner Gewinn. `context: fork` passt nicht, weil die Routine die Subagenten schon selbst startet.

**E9 – Kein Test für `blatt.py`.**
**Befund:** `tests/` enthält keinen Test für `blatt.py`. Das Blatt ist aber die einzige Faktenquelle des Agenten:
Mehrere „Claude lernt“-Fälle gingen auf fehlende oder missverständliche Blattzeilen zurück (Littoral Nord: Belag
fehlte; Crew Dragon: Box-Richtung; Senorito: Trainerwechsel).
**Folgerung:** Ein kleiner Fixture-Test (ein Rennen als JSON, erwartete Zeilen) schützt die Felder, die die Regeln
brauchen.

---

## 3. Achse 2: Wettmethodik

### 3.1 Was der Skill fachlich schon richtig macht

- **Modell-Value nur als Filter, nicht als Urteil.**
  **Quelle:** Benter (1994) berichtet, dass die öffentlichen Quoten allein besser vorhersagten als sein
  Fundamentalmodell allein. Erst die Kombination brachte einen Vorteil (A; laut Sekundärzusammenfassung
  Pseudo-R² außerhalb der Stichprobe 0,1237 Markt gegen 0,1016 Modell gegen 0,1327 kombiniert; Zahlen nicht am Original
  geprüft).
  **Folgerung:** Die Skepsis des Skills gegenüber hohem Modell-Value („über +100 % Warnsignal“, Fall Arkansas) ist
  genau diese Einsicht, nur heuristisch umgesetzt.
- **Hinterer Modell-Rang als Gegenargument.**
  **Befund:** README, Value-Dashboard (Auswertung 18.10.–05.11.): Modell-Rang 1–2 gewann 34-mal bei 32,9 erwarteten
  Siegen, ROI +67 %; Rang ≥ 3 gewann 9-mal bei 19,5 erwarteten, −49 %. Die Regel ist also durch eigene Daten gestützt
  (kleine Stichprobe).
- **Bewertung ohne Kenntnis des Ergebnisses.** Die Durchsicht blendet die Ergebnisse aus. Das vermeidet den
  Ergebnis-Bias.
- **Infrastruktur für Closing Line Value.** `value_bets` misst schon „Kurs bis Start“ (Festkurs gegen
  Toto-Endquote, relativ zum Feld) und „Modell → Toto“. Das ist der richtige Prüfstein (siehe 3.6). Für die
  Claude-Tipps fehlt er nur noch (Vorschlag P3).

### 3.2 Value-Definition, Steuer und Schwelle (M1)

**Befund:**
- Value = `fk.sieg × power.sieg − 1` (DATEN.md, GLOSSARY.md). Kandidat ist jeder Starter mit Value > 0.
- Die Abrechnung zieht aber je Wette 5 % des Einsatzes als Steuer ab (`value_bets.STEUER = 0.05`, `_bein`).
- Der Erwartungswert je Einheit nach dem Modell ist damit `fk × p − 1 − 0,05`. Gewinnschwelle: Value ≥ +5 % bzw.
  Festkurs ≥ 1,05 ÷ p.
- Die Faustregel in SKILL.md erlaubt Wetten bei „Value nahe 0 (bis etwa +5 %)“ (Algeciras +3 %, Dublin Calling 0 %,
  Boomslang 0 %).

**Quelle:**
- Kelly (1956) und Thorp (2006): Der Einsatz ist nur bei positivem Erwartungswert positiv; bei
  b = Nettoquote ist f\* = (b·p − q)/b (n. v. bzw. A).
- Die gesetzliche Grundlage der 5 % (RennwLottG, §§ 8–10 Rennwett- und Lotteriegesetz 2021) konnte nicht nachgelesen
  werden: gesetze-im-internet.de war gesperrt. Der Steuersatz ist hier nur die **Annahme des Repos**.

**Folgerung:**
- Kandidaten mit Value zwischen 0 und +5 % haben schon nach dem eigenen Modell einen negativen Erwartungswert.
- Der Nutzer will ausdrücklich nicht rechnen (Q29). Er will aber, dass die eigene Kursspanne über den Festkurs
  entscheidet. Dann muss die Steuer in der Spanne stecken: „fair 9–11“ heißt bei 5 % Steuer erst ab etwa 11,6 wirklich
  wettbar.
- Mindestens sollte das Blatt „Value nach Steuer“ und den Break-even-Kurs 1,05 ÷ p zeigen.

### 3.3 Kursspanne und Mindestquote (M2)

**Befund:** siehe E3 (unterer und oberer Rand widersprechen sich). Dazu sagt SKILL.md: „Gewettet wird, wenn der
Festkurs klar über der Spanne liegt.“
**Folgerung:**
- Liegt die faire Einschätzung zwischen 9 und 11, hat ein Kurs von 9 nach eigener Einschätzung keinen Vorteil, nach
  Steuer sogar einen negativen Erwartungswert.
- Eine Mindestquote am **unteren** Rand widerspricht der eigenen Wettregel. Konsistent wäre: Mindestquote ≥ oberer
  Rand, mit Steuer ≈ oberer Rand × 1,05.
- Die Karte graut Tipps aus, wenn „FK < MQ“. Bei MQ am unteren Rand bleiben deshalb Tipps aktiv, die nach der eigenen
  Regel keine mehr wären.

### 3.4 Modell und Markt kombinieren (Benter) (M3)

**Quelle:**
- Bolton & Chapman (1986) schätzen Siegchancen mit einem multinomialen Logit je Rennen (n. v.).
- Benter (1994) nimmt die Modellchance und die aus den Quoten abgeleitete Chance als zwei „Experten“ und verbindet
  sie in einem zweiten Logit: p_komb ∝ exp(α·ln p_Modell + β·ln p_Markt). Die Gewichte schätzt er per
  Maximum-Likelihood auf historischen Rennen. Er wettet nur auf Basis von p_komb (A).

**Befund:**
- Das Repo schätzt dieses Modell schon, aber nur als Test: `power_modell.markt_test` (bedingtes Logit mit ln
  Marktchance und ln Power-Chance, `markt_koef`, `power_koef`).
- MERKMALE.md, Abschnitt „Faire Quote“: „Exponent neben der Endquote 0,148 → 0,205“.
- Für die Wettentscheidung wird aber die **reine** Modellchance benutzt (MERKMALE.md: „Keine Marktquote“).

**Folgerung (eigene Überschlagsrechnung):**
- Mit einem Marktexponenten nahe 1 und einem Modellexponenten von etwa 0,2 schrumpft ein Verhältnis
  p_Modell ÷ p_Markt = 2 (Modell-Value um +100 % gegenüber dem bereinigten Markt) vor dem Renormieren auf etwa
  2^0,2 ≈ 1,15. Aus +100 % werden also grob +15 %, vor Marge und Steuer.
- Das erklärt, warum sehr hoher Modell-Value so oft nicht trägt. Die Ad-hoc-Regel „über +100 % Warnsignal“ ließe
  sich durch eine kombinierte Chance ersetzen oder ergänzen.
- Grenzen:
  - Der Exponent ist gegen die **Toto-Endquote** geschätzt. Gewettet wird aber zum **Festkurs** vor dem Start, und
    Festkurse gibt es erst seit 18.10.2026 (`value_bets.START_DATUM`).
  - Bis genug Festkurs-Rennen vorliegen, wäre der Endquoten-Exponent nur ein Platzhalter.
  - Die Kombination soll das Urteil nicht ersetzen, sondern als zweite Value-Spalte im Blatt stehen
    („Value kombiniert“).

### 3.5 Favourite-Longshot-Bias und Marge (M4)

**Quelle:**
- Griffith (1949) und Ali (1977) dokumentieren für Pari-Mutuel-Wetten: Außenseiter werden über-, Favoriten
  unterwettet (n. v.).
- Snowberg & Wolfers (2010) erklären den Bias eher mit Fehleinschätzung kleiner Wahrscheinlichkeiten als mit
  Risikofreude (A).
- Shin (1993) modelliert die Buchmacher-Marge so, dass sie auf Außenseitern höher liegt. Štrumbelj (2014) findet
  Shin-Wahrscheinlichkeiten genauer als einfaches Normieren (Fußball; A).
- Für französische PMU- bzw. Festkurs-Daten wurde in dieser Sitzung **keine** Primärstudie zum Bias gefunden.

**Befund:**
- Die Karte normiert Marktchancen bisher proportional (1 ÷ Quote, je Rennen auf 100 %; `regel_backtest.py`,
  README „Potenzmethode“ für `p_prog`).
- Das Value-Dashboard warnt: „Sehr hoher Wert (über 3) deutet oft auf einen Kursfehler hin“. Der goldene Rahmen gilt
  nur bis Cote 10, weil die Auswahl darüber im Test „klar verlor“ (README).

**Folgerung:**
- Die Kandidaten mit hohem Value häufen sich bei langen Kursen. Genau dort liegen die Marge des Buchmachers und der
  Bias des Publikums.
- Wird der Markt als Vergleich oder Kombinationspartner genutzt (M3, P3), dann mit Shin- oder Potenz-Normierung statt
  proportional.
- Für den Skill selbst: Die Faustregel „über +50 % sind ein bis zwei Fragezeichen tragbar“ belohnt hohen Value. Sie
  sollte nach Kursband gelesen werden: hoher Value bei FK > 20 verdient mehr Skepsis als bei FK 4.

### 3.6 Kalibrierung, Auswahleffekt und Closing Line Value (M5)

**Quelle:**
- Niculescu-Mizil & Caruana (2005): Boosting-Modelle liefern schlecht kalibrierte Wahrscheinlichkeiten und brauchen
  eine Nachkalibrierung (n. v.). Die Karte macht das mit Softmax(a × …) und dem Faktor k, im Sinne einer
  Temperaturskalierung (Guo et al. 2017, n. v.).
- Smith & Winkler (2006), „Optimizer's Curse“: Wer aus vielen geschätzten Alternativen die mit dem höchsten
  geschätzten Wert wählt, überschätzt deren Wert systematisch (n. v.).
- Kaunitz et al. (2017): Der Durchschnitt der Schlusskurse schätzt die wahren Chancen sehr genau (A).
- Snowberg & Wolfers (2010): Endquoten sind bis auf den Longshot-Bias gut kalibriert (A).

**Befund:** Die Kandidatenmenge „Value > 0“ ist genau eine solche Auswahl nach geschätztem Wert. Dass „Modell →
Toto“ und „Kurs bis Start“ im Dashboard existieren, ist methodisch richtig.
**Folgerung:**
- Ob die qualitative Schicht (NAP/BET gegen „abgelehnt“) etwas bringt, zeigen ROI-Zahlen erst nach Hunderten
  Wetten (bei Kursen um 10 ist die Streuung riesig).
- Schneller und ehrlicher sind zwei Maße:
  - **Closing Line Value** je Gruppe (NAP, BET, abgelehnt, Maßstab): Festkurs beim Durchgang gegen Toto-Endquote,
    relativ zum Feld.
  - **Kalibrierung der eigenen Kursspanne:** Log-Loss bzw. Brier von 1 ÷ Mitte der Spanne gegen Modell und
    normierten Festkurs.
- Die eigene Kursspanne ist eine implizite Wahrscheinlichkeit. Sie lässt sich bewerten, ohne dass beim Wetten
  gerechnet wird (vereinbar mit Q29). `tipp_auswertung.py` hatte das für den alten Skill schon (Log-Loss/Brier);
  laut Interview „Offen“ ist die Umstellung auf das neue Format noch nicht erledigt.

### 3.7 Einsatz: feste Einheiten gegen (Bruchteils-)Kelly (M6)

**Quelle:**
- Kelly (1956): Der wachstumsoptimale Anteil ist f\* = (b·p − q)/b (n. v.).
- Thorp (2006) und MacLean, Thorp & Ziemba (2010): Volles Kelly bei geschätzten Wahrscheinlichkeiten führt leicht zu
  Überwetten. Bruchteils-Kelly glättet den Bankverlauf auf Kosten des Wachstums (A).
- Baker & McHale (2013): Bei Unsicherheit über p soll der Kelly-Einsatz geschrumpft werden, das verbessert das
  Ergebnis außerhalb der Stichprobe (A).

**Befund:** Der Nutzer hat ⅛ Kelly bewusst durch feste Einheiten ersetzt (Q61). Das Dashboard rechnet die
Claude-Tipps trotzdem wahlweise mit level50, ⅛, ¼, ½ und 1/1 Kelly (`value_bets.CLAUDE_STAKING`).
**Folgerung (eigene Rechnung):**
- Feste Einheiten setzen auf lange Kurse relativ viel. Beispiel: p = 0,05 bei FK 25 (Value +25 %) ergibt einen
  Kelly-Anteil von 0,25 ÷ 24 ≈ 1 %. p = 0,35 bei FK 3,5 (Value +22,5 %) ergibt 0,225 ÷ 2,5 ≈ 9 %.
- Bei gleichem Value bekommt der Außenseiter in Einheiten also etwa das Neunfache dessen, was Kelly relativ vorsähe.
- Das muss kein Fehler sein, denn feste Einheiten sind robust gegen falsche p (Baker & McHale weisen in dieselbe
  Richtung). Es erhöht aber die Streuung der Bank stark.
- Empfehlung: nichts am Skill ändern, sondern nach etwa 100 Claude-Tipps im Dashboard level50 gegen ⅛ Kelly gegen
  „Einheiten nach Kursband“ vergleichen (Bankverlauf, größter Rückgang).

### 3.8 Französische Besonderheiten (M7)

- **Valeur in Kilo.**
  **Quelle:** France Galop, Conditions Générales 2026, S. 59: „valeur handicap supérieure ou égale à 41 (équivalent
  d'official rating de 90 …)“ (V).
  **Folgerung:** 90 lb ≈ 40,8 kg. Das stützt die Annahme hinter „Valeur − Gewicht + 55“ (`racecard._adj`,
  `GEWICHT_REF = 55`), dass ein Valeur-Punkt einem Kilo entspricht.
- **Gewichtsausgleich nach Alter fehlt in der bereinigten Valeur.**
  **Quelle:** CG 2026, S. 50, „Tableau poids pour âge européen (en kilos)“: Im November erhalten 3-Jährige gegen
  4-Jährige über 2400 m noch 2,5 kg, über 1600 m 1 kg; 2-Jährige gegen 3-Jährige deutlich mehr (V).
  **Folgerung:** Wenn die Valeurs auf einer gemeinsamen Skala ohne Altersgewicht stehen, wie beim britischen Official
  Rating, schreibt „Valeur − Gewicht + 55“ in altersgemischten Conditions-Rennen dem jüngeren Pferd das
  Altersgewicht als Klassenvorteil gut. Ob französische Valeurs so gemeint sind, war hier nicht zu klären (offene
  Frage).
- **Takeout im Toto.**
  **Quelle:** Für Online-Pari-Mutuel liegt die Obergrenze des Rückflusses an die Spieler bei 85 %
  (Décret n° 2020-1349, Art. 27, laut Suchergebnis zu ANJ-Dokumenten; A). Eine offizielle Zahl für den Simple Gagnant
  im Ladennetz wurde nicht gefunden.
  **Befund:** Das Dashboard nimmt 23 % Abzug als Vorgabe.
  **Folgerung:** Für CLV-Vergleiche ist der Abzug unerheblich, solange relativ zum Feld gemessen wird. Das Dashboard
  tut das bereits.

---

## 4. Priorisierte Vorschläge

Aufwand: **S** = unter 1 Stunde, **M** = etwa ein halber Tag, **L** = mehrere Tage oder abhängig von Daten.

| # | Was ändern (Datei) | Warum | Stütze | Aufwand |
|---|---|---|---|---|
| P1 | Mindestquote eindeutig machen: in `SKILL.md` (Gesamturteil und Ausgabebeispiel) und `GLOSSARY.md` „Mindestquote = oberer Rand der Spanne (mit Steuer ×1,05)“ oder die Entscheidung des Nutzers eintragen. In `durchgang.rennen_pruefen` prüfen: `spanne[0] ≤ spanne[1]`, `mq ≥ spanne[1]` (bzw. die gewählte Regel), bei `wette`/`klein` `fk ≥ mq`. Test in `tests/test_durchgang.py`. | Widerspruch im Skill (E3); Mindestquote am unteren Rand widerspricht „Festkurs klar über der Spanne“ (M2). | best-practices: consistent terminology, validation loops; eigene Folgerung | S |
| P2 | Steuer sichtbar machen: `scripts/blatt.py` druckt je Kandidat „Value nach Steuer“ (`fk·p − 1,05`) und „Break-even 1,05 ÷ p“. In SKILL.md (Faustregel) ein Satz, dass die Spanne die Steuer enthält. Ob Kandidat erst ab Value > +5 % gilt, entscheidet der Nutzer (Frage F2). | Wetten bei +0 bis +5 % sind nach dem eigenen Modell negativ (M1). | `value_bets.STEUER`; Kelly 1956, Thorp 2006 | S |
| P3 | Messen statt meinen: `value_bets.claude_auswertung` um CLV je Gruppe erweitern (NAP, BET, abgelehnt, Maßstab: Ø log(Festkurs ÷ Toto-Endquote) relativ zum Feld, mit z) und um Log-Loss/Brier der eigenen Kursspanne (1 ÷ Mitte) gegen Modell und normierten Festkurs. `tipp_auswertung.py` auf das Durchgang-Format umstellen (laut Interview offen). | Zeigt nach Dutzenden statt Hunderten Wetten, ob die qualitative Schicht Wert schafft (M5). | Kaunitz et al. 2017; Snowberg & Wolfers 2010; Smith & Winkler 2006; best-practices „Evaluations are your source of truth“ | M |
| P4 | Eval-Set aus der Fallsammlung: `evals/faelle.json` (Datum, race_id, Nr, Sollurteil, Art) und ein kleines Skript, das den Skill je Fall mit einem Subagenten auf der archivierten Karte laufen lässt (FAELLE.md ohne den Testfall). Ausgabe: Übereinstimmungsquote je Skill-Version, getrennt nach „Interview“, „Übereinstimmung“ und „Claude lernt“. Vor jeder neuen Regel laufen lassen; einmal mit einem kleineren Modell. | Keine Regressionsprüfung (E1); neue Regeln können alte Fälle kippen. | best-practices „Build evaluations first“, „Test with all models“; skill-creator `evals/evals.json`, Blind comparison | M |
| P5 | Validator auf Vollständigkeit: `durchgang.rennen_pruefen` optional mit der Karte aufrufen und prüfen, dass alle Kandidaten (Value > 0) und der Maßstab aus `blatt.massstab` enthalten sind; die Routine übergibt die Karte. | Fehlende Rennen bzw. Kandidaten (R3C4 am 16.11.) (E2). | best-practices „Create verifiable intermediate outputs“ | S–M |
| P6 | Value-Faktor-Warnung in die Prüfliste: SKILL.md, Typische Gegenargumente, „roter Rahmen (Value-Faktor Warnung)“; das Blatt zeigt sie schon („Warnung“). | Im Test des Repos A/E ≈ 0,7 in allen Renntypen (README, Power-Modell); die Information liegt vor, der Skill nutzt sie nicht. | README (eigene Validierung) | S |
| P7 | „Value kombiniert“ als zweite Spalte: Koeffizienten aus `power_modell.markt_test` (zunächst gegen Endquote, später gegen Festkurse) in die Karte schreiben, `blatt.py` druckt `p_komb` und „Value kombiniert“. In SKILL.md die Regel „über +100 % Warnsignal“ durch „Value kombiniert ≤ 0 = Warnsignal“ ergänzen. Marktchance per Shin- oder Potenz-Normierung. | Reine Modellchance überschätzt den Vorteil systematisch; Exponent ≈ 0,2 neben dem Markt (MERKMALE.md) (M3, M4). | Benter 1994; Bolton & Chapman 1986; Shin 1993; Štrumbelj 2014 | L |
| P8 | Kontextlast begrenzen: FAELLE.md verdichten (Übereinstimmungen je bestätigter Regel in einer Zeile) oder den Subagenten anweisen, aus FAELLE.md nur die Themenzeilen zu lesen, die zu seinen Kandidaten passen. `blatt.py` könnte je Kandidat die passenden Themen des Index nennen (z. B. „Ausrüstungswechsel“, „Claimer → Handicap“). | Rund 50 KB Pflichtlektüre je Rennen, wachsend (E5). | best-practices „Concise is key“, Inhaltsverzeichnis ab 100 Zeilen; writing-for-agents: Sprawl, Sediment | M |
| P9 | Description schärfen: Auslöser vorne (Bahnname, RxCy, hochgeladene `racecard_…`-Datei, Siegwetten/Value), Aufzählung der Ausgabeteile kürzen; optional `argument-hint` und `allowed-tools` für `blatt.py` in Claude Code. Danach die Description-Optimierung von skill-creator mit 8–10 echten und 8–10 Beinahe-Auslösern. | Nur ein Auslöser, viel „was“ (E7, E8). | best-practices „Writing effective descriptions“; code.claude.com (1.536-Zeichen-Grenze, Frontmatter); skill-creator „Description Optimization“ | S (+M für die Optimierung) |
| P10 | Eine Quelle für das Ergebnisformat: im Subagenten-Prompt (`aufgabe_durchgang.md`) die Feldliste durch „Format laut SKILL.md, Abschnitt Ausgabe; Prüfung mit `rennen_pruefen`“ ersetzen. README Zeile 720 um `massstab` ergänzen. `skill_neu_einrichten.md` auf `…_daten.json.gz` umstellen. | Vierfache, schon auseinanderlaufende Beschreibung (E4). | writing-for-agents „single source of truth“ | S |
| P11 | SKILL.md entschlacken: Datums- und Herkunftsangaben nach FAELLE.md bzw. ins Interview; je Regel höchstens ein Fallname. | Zeitbezug und Sediment (E6). | best-practices „Avoid time-sensitive information“; writing-for-agents „Pruning“ | S |
| P12 | Neue Regeln gegen die Datenbank prüfen: `regel_backtest.py` (prüft noch die Regeln des alten Skills) um die neuen Regeln ergänzen: Ausrüstung fällt weg (mit/ohne-Bilanz), Claimer → Handicap, Höchstgewicht bzw. ≥ 62 kg auf Très souple oder schwerer, ≥ 4 Starts in 42 Tagen, Abstieg in die Provinz, britischer Trainer. Kennzahl A/E gegen den Markt. | Zwei Fälle reichen, um den Nutzer nachzubilden, nicht aber als Beleg für Vorhersagekraft; der Markt kann eine Regel längst einpreisen. | Benter 1994 und Bolton & Chapman 1986 (Faktoren gegen den Markt prüfen); Hausch, Ziemba & Rubinstein 1981 (n. v.) | M |
| P13 | Einsatz vergleichen statt ändern: nach etwa 100 Claude-Tipps im Dashboard level50 gegen ⅛ Kelly gegen „Einheiten nach Kursband“ (Bankverlauf, größter Rückgang). | Feste Einheiten gewichten lange Kurse bei gleichem Value bis etwa 9-fach höher als Kelly (M6). | Kelly 1956; Thorp 2006; MacLean, Thorp & Ziemba 2010; Baker & McHale 2013 | S (Auswertung) |
| P14 | Altersgewicht in der bereinigten Valeur klären: falls französische Valeurs ohne Altersgewicht gelten, in `racecard._adj` für altersgemischte Rennen das Altersgewicht aus der Tabelle der CG addieren; sonst in DATEN.md festhalten, dass es bereits enthalten ist. | Möglicher systematischer Vorteil jüngerer Pferde im Rang der bereinigten Valeur (M7). | France Galop CG 2026, S. 50 und S. 59 | S–M |
| P15 | Fixture-Test für `blatt.py` (ein Rennen, erwartete Zeilen: Maßstab, Box-Richtung, Trainerwechsel, Ausrüstung mit/ohne, Abstammung Belag/Reife). | Das Blatt ist die einzige Faktenquelle; mehrere Fehlurteile gingen auf Blattlücken zurück (E9). | best-practices „Scripts solve problems“; eigene Folgerung | S |
| P16 | Umbenennen in `rennkarten-durchgang` (ohne `-neu`), nur zusammen mit einer ohnehin fälligen Paketänderung. | Zeitbezug im Namen (E6). | best-practices „Naming conventions“, „Avoid time-sensitive information“ | M (Abstimmung Routine, claude.ai-Paket) |

**Reihenfolge, wenn wenig Zeit ist:** P1 und P2 (Widerspruch und Steuer, beides klein und mit direktem Geldbezug),
dann P3 (Messung), P5 und P6, dann P4 als Grundlage für jede weitere Regeländerung. P7 lohnt sich erst, wenn P3 zeigt,
wie viel die Kandidatenauswahl heute verliert.

---

## 5. Offene Fragen an den Nutzer

1. **Ziel des Skills:** Soll er vor allem dein Urteil nachbilden („die der Nutzer tatsächlich spielen würde“, so steht
   es in der Description) oder auch dort abweichen, wo die Daten gegen eine deiner Regeln sprechen? Davon hängt ab,
   ob eine Regel aus zwei Fällen (P4) oder erst nach einem Backtest (P12) gelten soll.
2. **Mindestquote:** Unterer oder oberer Rand der Kursspanne? Und soll die Steuer (5 % des Einsatzes laut
   `value_bets`) in die Mindestquote eingerechnet werden?
3. **Steuer:** Zahlst du bei Wettstar tatsächlich 5 % auf den Einsatz? Soll ein Kandidat dann erst ab Value > +5 %
   gelten, oder bleibt Value > 0 der Filter und die Steuer steckt nur in der Kursspanne?
4. **Kombinierte Chance:** Wäre eine zusätzliche Anzeige „Value kombiniert“ (Modell + Markt, Benter) mit Q29
   („kein Rechnen“) vereinbar, wenn sie nur als Warnsignal dient und nicht als Rechenregel?
5. **Wann wird gewettet?** Zum Festkurs beim Durchgang oder später? Davon hängt ab, welcher Kurs für CLV und
   Abrechnung gilt.
6. **Einsatz:** Sind feste Einheiten auch bei langen Kursen (FK über 20) gewollt, oder wäre eine Stufe
   „½ Einheit ab FK 20“ denkbar?
7. **Bereinigte Valeur:** Enthalten französische Valeurs das Altersgewicht schon, oder muss es in altersgemischten
   Rennen ausgeglichen werden?
8. **Fallsammlung:** Darf FAELLE.md verdichtet werden (Übereinstimmungen zu bestätigten Regeln in einer Zeile), damit
   jeder Subagent weniger lesen muss?
9. **Modell der Routine:** Mit welchem Modell laufen die Subagenten der Routine? Soll der Skill auch mit einem
   kleineren Modell getestet werden (P4)?

---

## Quellenverzeichnis

**Anthropic und Skill-Engineering**
- Anthropic: Skill authoring best practices. <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices> (früher docs.claude.com, leitet dorthin weiter). **V**
- Anthropic: Extend Claude with skills (Claude Code). <https://code.claude.com/docs/en/skills>. **V** (die ersten 100.000 Zeichen)
- anthropics/skills, `skills/skill-creator/SKILL.md`. <https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md>. **V**
- Plugin-Skill `writing-for-agents` (`SKILL.md`, `SKILL-MECHANICS.md`), in dieser Umgebung als synchronisierter Plugin-Skill vorhanden. **V**

**Wettmethodik**
- Kelly, J. L. (1956): A New Interpretation of Information Rate. Bell System Technical Journal 35(4), 917–926. doi:10.1002/j.1538-7305.1956.tb03809.x. **n. v.**
- Thorp, E. O. (2006): The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market. In: Zenios & Ziemba (Hrsg.), Handbook of Asset and Liability Management, Bd. 1, Kap. 9 (mit Abschnitt „The case for fractional Kelly“). **A**
- MacLean, L. C., Thorp, E. O., Ziemba, W. T. (2010): Long-term capital growth: the good and bad properties of the Kelly and fractional Kelly capital growth criteria. Quantitative Finance 10(7), 681–687. doi:10.1080/14697688.2010.506108. **A**
- Baker, R. D., McHale, I. G. (2013): Optimal Betting Under Parameter Uncertainty: Improving the Kelly Criterion. Decision Analysis 10(3), 189–199. doi:10.1287/deca.2013.0271. **A**
- Benter, W. (1994): Computer Based Horse Race Handicapping and Wagering Systems: A Report. In: Hausch, Lo, Ziemba (Hrsg.), Efficiency of Racetrack Betting Markets; Neuauflage 2008, Kap. 19. doi:10.1142/9789812819192_0019. **A**
- Bolton, R. N., Chapman, R. G. (1986): Searching for Positive Returns at the Track: A Multinomial Logit Model for Handicapping Horse Races. Management Science 32(8), 1040–1060. **n. v.**
- Hausch, D. B., Ziemba, W. T., Rubinstein, M. (1981): Efficiency of the Market for Racetrack Betting. Management Science 27(12), 1435–1452. **n. v.**
- Griffith, R. M. (1949): Odds Adjustments by American Horse-Race Bettors. American Journal of Psychology 62(2), 290–294. **n. v.**
- Ali, M. M. (1977): Probability and Utility Estimates for Racetrack Bettors. Journal of Political Economy 85(4), 803–815. **n. v.**
- Snowberg, E., Wolfers, J. (2010): Explaining the Favorite–Long Shot Bias: Is it Risk-Love or Misperceptions? Journal of Political Economy 118(4), 723–746 (NBER WP 15923). **A**
- Shin, H. S. (1993): Measuring the Incidence of Insider Trading in a Market for State-Contingent Claims. Economic Journal 103(420), 1141–1153. **n. v.**
- Štrumbelj, E. (2014): On determining probability forecasts from betting odds. International Journal of Forecasting 30(4), 934–943. doi:10.1016/j.ijforecast.2014.02.008. **A**
- Kaunitz, L., Zhong, S., Kreiner, J. (2017): Beating the bookies with their own numbers – and how the online sports betting market is rigged. arXiv:1710.02824. **A**
- Smith, J. E., Winkler, R. L. (2006): The Optimizer's Curse: Skepticism and Postdecision Surprise in Decision Analysis. Management Science 52(3), 311–322. **n. v.**
- Niculescu-Mizil, A., Caruana, R. (2005): Predicting Good Probabilities with Supervised Learning. ICML 2005. **n. v.**
- Guo, C., Pleiss, G., Sun, Y., Weinberger, K. Q. (2017): On Calibration of Modern Neural Networks. ICML 2017, arXiv:1706.04599. **n. v.**

**Frankreich**
- France Galop: Conditions Générales 2026 (Bulletin Officiel, Stand 3. März 2026), S. 50 (Tableau poids pour âge européen) und S. 59 (Handicaps, Valeur 41 ≈ Official Rating 90). <https://www.france-galop.com/sites/default/files/2026-03/02_cg-2026-bo_3ter_du_3_mars_2026_optimized.pdf>. **V**
- Décret n° 2020-1349 vom 4.11.2020, Art. 27 (Rückfluss an die Spieler bei Online-Wetten höchstens 85 %), wiedergegeben nach ANJ-Dokumenten im Suchergebnis, z. B. <https://ressources.anj.fr/regulation/trj/regle_determination_trj.pdf>. **A**
- Rennwett- und Lotteriegesetz (RennwLottG 2021), §§ 8–10: nicht abrufbar (gesetze-im-internet.de gesperrt). Der Steuersatz von 5 % ist hier nur die Annahme in `value_bets.STEUER`.

**Repo (Befunde)**
- `.claude/skills/rennkarten-durchgang-neu/` (SKILL.md, DATEN.md, FAELLE.md, scripts/blatt.py)
- `durchgang.py` (`rennen_pruefen`, `URTEILE`), `value_bets.py` (`STEUER`, `_bein`, `einsatz`, `claude_auswertung`, `CLAUDE_STAKING`), `racecard.py` (`_adj`, `GEWICHT_REF`), `power_modell.py` (`markt_test`), `regel_backtest.py`, `skill_paket.py`, `tests/test_durchgang.py`
- `GLOSSARY.md`, `MERKMALE.md` (Abschnitt „Faire Quote“), `README.md` (Power-Modell, Durchgänge, Value-Dashboard), `docs/interview_rennkarten_durchgang.md`, `docs/adr/0001-durchgang-in-eigener-datei.md`, `claude_projekt/aufgabe_durchgang.md`, `claude_projekt/skill_neu_einrichten.md`
- Git: Commits 3bab52f (v1) bis 245c311 (Maßstab), 7a1e604 (alter Skill mit 1.277 Zeilen entfernt)
