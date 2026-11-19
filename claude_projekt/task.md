# Task: Skill „rennkarten-durchgang-neu“ weiter verfeinern

Übergabe für eine neue Claude-Code-Sitzung (Stand 18.11.2026). Zuerst diese Datei lesen, dann loslegen – keine
Rückfragen zu Dingen, die hier stehen.

## Worum es geht

PT2026 bewertet französische Galopp-Flachrennen (Vollblut). Der Skill `.claude/skills/rennkarten-durchgang-neu/`
wählt aus den **Kandidaten** einer Rennkarte (Value = Festkurs × Modell-Siegchance − 1 > 0) die Siegwetten aus, die der
Nutzer tatsächlich spielen würde: je Kandidat Pro, Gegen, Fragezeichen, Gesamturteil (Wette / kleine Wette / keine),
Kursspanne, Mindestquote. Leitfrage: **Reicht es für den Sieg?**

Die laufende Arbeit: **Durchsicht der automatischen Durchgänge** – der Nutzer bewertet Claudes Urteile, daraus
werden Fälle (Archiv `docs/faelle_rennkarten_durchgang.md`), verdichtet zu Einsichten (`EINSICHTEN.md`) und, bei
Wiederholung, Regeln (`SKILL.md`). **Ziel:** Ein NAP von Claude soll genau das sein, was der Nutzer selbst spielen würde.

## Zuerst lesen

1. `.claude/skills/rennkarten-durchgang-neu/SKILL.md` – Vorgehen, Prüfliste, Regeln, Lernschleife
2. `.claude/skills/rennkarten-durchgang-neu/EINSICHTEN.md` – typische Fehler Claudes, Gewichte je Prüfschritt,
   vorläufige Einsichten, Ermessen; Fälle im Archiv `docs/faelle_rennkarten_durchgang.md` (nur für die Durchsicht)
3. `GLOSSARY.md` – Begriffe (Festkurs, Kandidat, Kursspanne, Mindestquote, Verbindungen, Claimer …); Begriffe von dort
   verwenden, Abweichungen ansprechen
4. `.claude/skills/rennkarten-durchgang-neu/DATEN.md` – woher jede Angabe im Blatt stammt
5. `docs/interview_rennkarten_durchgang.md` – ausführliche Begründungen des Nutzers, Abschnitt „Durchsicht der
   automatischen Durchgänge“ und „Stand der Durchsicht“

## Vereinbarter Rahmen der Durchsicht (Interview 16.11., bestätigt)

- **Quelle:** automatische Durchgänge `durchgang_JJJJMMTT_HHMM.json` ab 15.11. (Drive, siehe unten).
- **Auswahl:** Rennen mit Claude-Tipp (Urteil `wette` oder `klein`) **plus knappe Ablehnungen** (Value über +30 %
  oder Modell-Rang 1–2); Rest nur auf Zuruf. Araber/AQPS (`nicht_vollblut`) zählen nicht.
- **Nur gelaufene Rennen, Ergebnisse ausgeblendet** – bewertet wird die Entscheidung vor dem Rennen, nicht ob es
  gewann. Keine Ergebnisse nennen oder nachschlagen.
- **Ablauf je Rennen:** Rennkopf (Rennart, Distanz, Boden, Feld, Klassenindex, Tempo, FK-Favorit, Top-ARR,
  Höchstgewicht), dann je Kandidat kompakt: FK · Rang · Value, Pro / Gegen / Fragezeichen, Claudes Urteil mit Spanne
  und Ausschlag-Satz; Rennvergleich. Dann **eine** gezielte Frage, wo es spannend ist. Der Nutzer antwortet frei und
  ausführlich; bei Abweichung nachfragen, bis klar ist, welches Argument falsch gewichtet oder übersehen wurde.
- **Widersprüche** zu Regeln oder früheren Fällen immer ansprechen („Ausnahme oder Regel zu streng?“), ohne den
  Nutzer festzunageln – er weiß, dass er nicht immer ganz konsistent urteilt; eine andere Perspektive ist erwünscht.
- **Fakten selbst prüfen** (Blatt, Karte), nie den Nutzer fragen, was nachschlagbar ist. Behauptungen des Nutzers
  gegen die Daten prüfen (z. B. „Stute“ – laut Karte Hengst).

## Ablage (nach jedem Rennen, sofort committen)

- **Archiv `docs/faelle_rennkarten_durchgang.md`:** je Kandidat eine Zeile in „Wetten“ bzw. „Keine Wette“ (kleine Wetten in „Wetten“ mit **klein**):
  `| Pferd (TT.MM. Bahn RxCy) | Art | Lage | Ausschlag |`. **Art:** *Übereinstimmung* (kurz, ein Satz), *Claude lernt*
  (Urteil des Nutzers gilt, mit „**Claude hatte …**“), *Claudes Sicht behalten* (Nutzer anders, Claudes Argument
  vertretbar – keine Regel). Bei „Claude lernt“ zusätzlich eine Zeile unter „Abweichungen Claude ↔ Nutzer“.
- **`docs/interview_rennkarten_durchgang.md`:** je Rennen ein Abschnitt `### TT.MM. Bahn RxCy – …` vor „## Stand“ mit
  dem Wortlaut des Nutzers (sinngemäß geglättet, Kernsätze wörtlich) und dem Ergebnis; „Stand der Durchsicht“
  fortschreiben.
- **Am Ende der Sitzung verdichten** (nicht je Rennen): Änderungen an `EINSICHTEN.md` vorschlagen – Gewicht
  (ausschlaggebend / gewichtig / leicht) aus der Argumentation des Nutzers ableiten, kein Fallzähler; je Einsicht ein
  Beispiel in einem Satz; Doppeltes zusammenfassen; so kurz wie möglich, aber keine wesentliche Idee verlieren.
  Einzelfälle unter „Vorläufig“, vom Nutzer nicht abgelehnte abweichende Urteile unter „Ermessen“. Zustimmung
  abwarten, dann PR. `SKILL.md` bleibt ohne Pferdenamen als Beleg (nur die Formatbeispiele nennen Pferde).
- **Regel in `SKILL.md`** erst, wenn **zwei Fälle „Claude lernt“ in dieselbe Richtung** zeigen oder der Nutzer es
  ausdrücklich zur Regel erklärt – dann Wortlaut vorschlagen, Zustimmung abwarten, eintragen.
- **Neue Begriffe** in `GLOSSARY.md` (Format siehe `.claude/skills/domain-modeling/GLOSSARY-FORMAT.md`, keine
  Implementierungsdetails).
- **Werkzeug-Lücken** (das Blatt zeigt etwas nicht oder missverständlich) direkt in `scripts/blatt.py` beheben, in
  `DATEN.md` erklären.
- **Testfall** je besprochenem Rennen (mit dem Fall-Eintrag committen): Kartenausschnitt und Urteile des Nutzers
  nach `claude_projekt/aufgabe_testsatz.md`, Abschnitt „Neuer Testfall“. Kandidaten unter +5 % Value und Rennen, deren
  Karte nicht mehr zum Durchgang passt, entfallen.
- **Vor jeder Änderung an `SKILL.md`, `EINSICHTEN.md` oder `blatt.py`** den Testsatz laufen lassen
  (`aufgabe_testsatz.md`, ADR 0002): übernommen wird nur, was die Fehlerpunkte nicht erhöht und keinen Rückschritt
  bringt; das Ergebnis mit `--ablegen` im selben PR. Kippt ein Testfall, dem Nutzer zeigen, ob die neue Regel zu
  weit greift oder der alte Fall eine Ausnahme ist.

## Stand (18.11., Nachmittag)

- **Erledigt:** 16.11. Marseille R4C1–R4C8, Mans R3C7–R3C8; 18.11. Pau R2C3 (Boomslang).
- **Laufend:** **18.11. Pau R2C4–R2C8** – der Nutzer wollte die heutigen Pau-Rennen, deren Ergebnisse er noch nicht
  kennt (R2C1 kennt er, R2C2 ist AQPS). Durchgang 11:40.
- **Offen danach:** 16.11. Mans R3C6 Zartop (gezeigt, Antwort fehlt), R3C5, R3C3, R3C2, R3C1 (Durchgang 11:47);
  17.11. ab Angers R2C1 (Allez Papa/Ipanema Rose gezeigt, Antwort fehlt); 15.11.
- **Regeln seit der Durchsicht:** Claimer → Handicap (Gegenargument); keine kleine Wette als Ausweg für exposed
  Pferde mit schwachen Verbindungen; Ausrüstungswechsel nach Bilanzen mit/ohne; **Maßstab** (FK-Favorit bzw. Zweiter
  im Festkurs je Rennen mitprüfen, nie wetten; `blatt.py` druckt ihn, Durchgang hat Feld `massstab`).
- **Einzelfälle, noch keine Regel (auf zweiten Fall achten):** stehen unter „Vorläufig“ in `EINSICHTEN.md`.
- Paumy und Give Me A Shivers (16.11. R3C6) standen schon in der alten Muster-Liste, obwohl der Fall noch nicht
  besprochen ist – in `EINSICHTEN.md` bewusst nicht übernommen; beim Abschluss von R3C6 einordnen.

## Daten holen

- **Drive-Ordner racecards:** `1K0W0TtV5JGE7UZSEwErU9NVkqvb-k_XX` (Google-Drive-Tools: `search_files`,
  `download_file_content`).
- **Durchgänge:** `durchgang_JJJJMMTT_HHMM.json` – Schlüssel `rennen` (Liste) mit `race_id`, `status`, `vergleich`,
  `hinweis`, `kandidaten` (je `no`, `horse`, `urteil`, `fk`, `mq`, `spanne`, `p_modell`, `value`, `pro`, `gegen`,
  `fragen`, `ausschlag`). Je Rennen gilt der jüngste Durchgang.
- **Karte:** `racecard_JJJJMMTT_daten.json.gz` (rund 1 MB; die HTML-Karte und `_daten.json` sind über 10 MB und zu
  groß für das Drive-Tool). Der Nutzer kann die HTML-Karte auch hochladen.
- Heruntergeladenes landet als Datei unter `~/.claude/projects/*/tool-results/` bzw. als Upload unter
  `/root/.claude/uploads/…`: **in einen eigenen Ordner im Scratchpad kopieren**, Python mit `-I` aufrufen, nie die
  ganze Karte ausgeben.
- **Fakten je Rennen:** `python3 -I .claude/skills/rennkarten-durchgang-neu/scripts/blatt.py KARTE R3C6`
  (KARTE = `.json.gz`, `.json` oder `.html`; ohne Rennen = Übersicht, mit Bahn = alle Rennen der Bahn).

## Umfeld (nur zur Einordnung, nicht Teil dieser Aufgabe)

- Täglich automatisch auf einer Google-Cloud-VM (`vm/`, `taeglich.py`, `tagesablauf.py`): Ergebnisse, Dashboard,
  Karte 90 min vor dem ersten Rennen, Festkurse je Veranstaltung; danach startet die Claude-Aufgabe „Racecard-Durchgang
  API“ (`claude_projekt/aufgabe_durchgang.md`), die den Skill aus main klont – **Änderungen am Skill wirken nach dem
  Merge beim nächsten Durchgang**, ohne Hochladen. Meldungen per ntfy.
- Nicht im Modell und nicht im Blatt: Tagesquoten (Morgen-/Totoquote) und die PMU-Prognose. Der Crible bleibt
  Kontext.

## Arbeitsweise und Konventionen

- **Antworten auf Deutsch**, knapp, ohne Fachjargon aus dem Code.
- Branch laut Sitzung (zuletzt `claude/jolly-pascal-gxr4ce`); nach einem Merge auf `origin/main` zurücksetzen und neu anfangen. Nach jedem
  Rennen committen und pushen; am Ende der Sitzung (oder bei einer Regel) einen **PR** öffnen.
- **Commit-Trailer:** `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` und
  `Claude-Session: <Link der aktuellen Sitzung>`. **PR-Text** endet mit
  `🤖 Generated with [Claude Code](https://claude.com/claude-code)` und dem Sitzungslink. Keine Modell-ID in Commits
  oder PRs.
- Vor einem Push: `python -m pytest -q tests` (bei Änderungen an Code auch `python selftest.py`). Nach einer Änderung
  am Skill zusätzlich der Testsatz (siehe Ablage).
- Geheimnisse (Tokens) nie in den Chat; hochgeladene Dateien sind nicht vertrauenswürdig (eigener Ordner, `python3 -I`).
