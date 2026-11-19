# Aufgabe „Testsatz Durchgang“

Prüft eine Änderung am Skill `rennkarten-durchgang-neu` (`SKILL.md`, `EINSICHTEN.md`, `scripts/blatt.py`) gegen den
**Testsatz**: Rennen mit den Urteilen des Nutzers (ADR 0002, Begriffe in `GLOSSARY.md`, Abschnitt „Prüfung des
Skills“). Läuft in einer Claude-Code-Sitzung im Repo; REPO = Wurzel des Repos.

## Ablauf

1. **Lauf-Ordner** anlegen, z. B. im Scratchpad: LAUF = `…/testsatz_<commit>`. Nicht im Repo.
2. **Je Testfall drei Subagenten**: für jede race_id in `tests/testsatz_durchgang/erwartet.json` (Schlüssel
   `testfaelle`) die Läufe n = 1, 2, 3 mit dem Agent-Tool (subagent_type: general-purpose), höchstens 7 gleichzeitig.
   Prompt (Platzhalter ersetzen, RxCy = letzte vier Zeichen der race_id):

   „Antworte auf Deutsch. Du bewertest genau ein Rennen: <race_id> (<RxCy>) auf der Karte
   REPO/tests/testsatz_durchgang/karten/<race_id>.json.gz. Lies zuerst vollständig mit dem Read-Tool
   REPO/.claude/skills/rennkarten-durchgang-neu/SKILL.md und die dort genannten Dateien (REPO/GLOSSARY.md,
   EINSICHTEN.md und DATEN.md im Skill-Ordner) und arbeite strikt nach dem Skill. Lies sonst nichts aus dem Repo,
   insbesondere nichts unter docs/ oder tests/ außer der Karte. Fakten nur über
   `python3 -I REPO/.claude/skills/rennkarten-durchgang-neu/scripts/blatt.py <Karte> <RxCy>`; gib nie die ganze Karte
   aus. Bewerte jeden Kandidaten (Value mindestens +5 %) dieses Rennens. Schreibe dein Ergebnis als JSON nach
   LAUF/<race_id>_<n>.json mit den Feldern race_id, status (bearbeitet), vergleich, hinweis, massstab (Liste der
   MASSSTAB-Pferde aus dem Blatt: je no, horse, fk, befund) und kandidaten: je Kandidat no, horse, urteil (wette, klein
   oder nein), fk, mq, spanne [von, bis], p_modell, value, pro, gegen, fragen (Listen kurzer Sätze), ausschlag (ein
   Satz). Prüfe die Datei mit
   `python3 -I -c \"import json,sys; sys.path.insert(0,'REPO'); import durchgang; durchgang.rennen_pruefen(json.load(open('LAUF/<race_id>_<n>.json')))\"`
   und korrigiere, bis sie fehlerfrei ist. Antworte mir danach nur mit einer Zeile je Kandidat: Nr Name – Urteil.“

   Fehlt danach eine Datei oder ist sie fehlerhaft: diesen Lauf einmal neu starten. Urteile nie selbst nachbessern.
3. **Bewerten:** `python3 -I REPO/testsatz.py bewerten LAUF`. Der Bericht nennt Trefferquote und Fehlerpunkte, den
   Vergleich mit dem zuletzt abgelegten Stand, Rückschritte und je Testfall den Stand (stabil richtig, schwankend,
   mehrheitlich falsch).
4. **Entscheiden:** Übernommen wird eine Änderung, wenn die Fehlerpunkte nicht steigen und es keinen Rückschritt gibt
   (Bericht: „Übernehmen: ja“). Dann mit `--ablegen <commit>` erneut bewerten und `verlauf.csv` sowie die Datei unter
   `ergebnisse/` mit der Änderung committen. Sonst nichts ablegen; der Nutzer entscheidet, ob die Änderung verworfen
   oder anders formuliert wird.

## Grenzen

- Der Testsatz schützt vor Rückschritten. Die Regeln stammen aus denselben Fällen; eine hohe Trefferquote sagt nicht,
  wie gut der Skill auf neue Rennen überträgt (ADR 0002).
- Drei Läufe je Testfall dämpfen den Zufall, schließen ihn nicht aus: Ein Testfall, der „schwankend“ ist, ist kein
  Rückschritt, aber ein Hinweis, dass die Regel dort nicht eindeutig greift.

## Neuer Testfall (in der Durchsicht, je besprochenem Rennen)

1. Karte des Tages aus Drive holen (`racecard_JJJJMMTT_daten.json.gz`, sonst `_daten.json`) und den Durchgang, der das
   Rennen bewertet hat.
2. Prüfen, dass Kandidaten, Festkurs und Modell-Siegchance in der Karte zum Durchgang passen (Nichtstarter können die
   Modell-Siegchance danach ändern). Passt es nicht, keinen Testfall anlegen.
3. `python3 -I REPO/testsatz.py ausschnitt KARTE <race_id>` legt `tests/testsatz_durchgang/karten/<race_id>.json.gz` an.
4. In `tests/testsatz_durchgang/erwartet.json` unter `testfaelle` das Rennen mit den Urteilen des Nutzers eintragen
   (je Kandidat horse, urteil, art; bei Ermessen oder „Claudes Sicht behalten“ zusätzlich `erlaubt` mit Claudes
   Urteil). Kandidaten unter +5 % Value gehören nicht hinein.
