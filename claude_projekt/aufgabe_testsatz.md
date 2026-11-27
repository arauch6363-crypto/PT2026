# Aufgabe „Testsatz Durchgang“

Prüft eine Änderung am Skill `rennkarten-durchgang-neu` (`SKILL.md`, `EINSICHTEN.md`, `scripts/blatt.py`) gegen den
**Testsatz**: Rennen mit den Urteilen des Nutzers (ADR 0002, Begriffe in `GLOSSARY.md`, Abschnitt „Prüfung des
Skills“). Läuft in einer Claude-Code-Sitzung im Repo; REPO = Wurzel des Repos.

## Ablauf

1. **Lauf-Ordner** anlegen, z. B. im Scratchpad: LAUF = `…/testsatz_<commit>`. Nicht im Repo.
2. **Erste Stufe – ein Subagent je Testfall**: für jede race_id in `tests/testsatz_durchgang/erwartet.json`
   (Schlüssel `testfaelle`) den Lauf n = 1 mit dem Agent-Tool (subagent_type: general-purpose), höchstens 7
   gleichzeitig. Prompt (Platzhalter ersetzen, RxCy = letzte vier Zeichen der race_id):

   „Antworte auf Deutsch. Du bewertest genau ein Rennen: <race_id> (<RxCy>) auf der Karte
   REPO/tests/testsatz_durchgang/karten/<race_id>.json.gz. Lies zuerst vollständig mit dem Read-Tool
   REPO/.claude/skills/rennkarten-durchgang-neu/SKILL.md und die dort genannten Dateien (REPO/GLOSSARY.md,
   EINSICHTEN.md und DATEN.md im Skill-Ordner) und arbeite strikt nach dem Skill. Lies sonst nichts aus dem Repo,
   insbesondere nichts unter docs/ oder tests/ außer der Karte. Fakten nur über
   `python3 -I REPO/.claude/skills/rennkarten-durchgang-neu/scripts/blatt.py <Karte> <RxCy>`; gib nie die ganze Karte
   aus. Bewerte jeden Kandidaten (Value mindestens +5 %) dieses Rennens, kein anderes Rennen. Schreibe dein Ergebnis
   als JSON nach LAUF/<race_id>_<n>.json mit den Feldern race_id, status (bearbeitet), vergleich (Rennvergleich mit
   Grenze und Maßstab), hinweis (z. B. Boden nur angenommen), massstab (Liste der MASSSTAB-Pferde aus dem Blatt,
   höchstens zwei: je no, horse, fk, befund – ein bis zwei Sätze, kein Urteil; leere Liste, wenn das Blatt keinen
   nennt) und kandidaten: je Kandidat no, horse, urteil (wette, klein oder nein), fk (Festkurs laut Karte), spanne
   [von, bis], p_modell, value, pro (Liste kurzer Sätze), gegen (Liste), fragen (Liste),
   anker (ein Satz: fairer Modellkurs, Festkurs und was die Spanne davon verschiebt), leitfrage ({referenzlauf: Datum
   JJJJ-MM-TT oder „keiner“, ref_arr, top_arr, massstab_arr: Liste je Maßstab} aus der Zeile „Leitfrage“ des Blatts),
   ausschlag (ein Satz) – Kennungen wie im Skill unter „Kennungen“ beschrieben. Alle Kandidaten müssen enthalten sein.
   Prüfe die Datei mit `python3 -I REPO/durchgang.py pruefen LAUF/<race_id>_<n>.json --karte <Karte>` und korrigiere,
   bis sie „ok“ meldet; jede Meldung sagt, was fehlt oder der Regel widerspricht. Antworte mir danach nur mit einer Zeile je Kandidat: Nr Name – Urteil –
   Kursspanne.“

   Der Prompt entspricht Schritt 4 von `aufgabe_durchgang.md` (dort zusätzlich Zeit, Bahn und der Araber-Fall, die
   hier nicht vorkommen); ändert sich jener, diesen mitziehen.

   Fehlt danach eine Datei oder ist sie fehlerhaft: diesen Lauf einmal neu starten. Urteile nie selbst nachbessern.

   **Prüf-Subagent:** Für jeden Lauf, dessen Datei ein Urteil „wette“ oder „klein“ hat, danach einen Prüf-Subagenten
   mit leerem Kontext starten, mit dem Prompt aus Schritt 4a von `aufgabe_durchgang.md` (Pfade wie oben: REPO statt
   /home/claude/pt2026, Karte des Testfalls, DATEI = LAUF/<race_id>_<n>.json; Zusatz: „Lies sonst nichts aus dem Repo,
   insbesondere nichts unter docs/ oder tests/ außer der Karte.“). Vorher die Datei nach LAUF/vor_pruefung/ kopieren;
   scheitert die Prüfung, die Datei zurückkopieren. Bewertet wird das Urteil nach der Prüfung.
3. **Zweite Stufe – nur wo nötig:** `python3 -I REPO/testsatz.py nachlauf LAUF` nennt die Testfälle, deren erster Lauf
   vom Urteil des Nutzers abweicht; nur für diese die Läufe n = 2 und 3 mit demselben Prompt, mit Prüf-Subagent wie
   oben, wo ein Lauf einen Tipp hat. Fertig, wenn `nachlauf`
   „keine“ meldet. (Ein richtiger erster Lauf gilt als stabil richtig; drei Läufe braucht nur ein abweichender Fall,
   um schwankend von mehrheitlich falsch zu trennen.)
4. **Bewerten:** `python3 -I REPO/testsatz.py bewerten LAUF`. Der Bericht nennt Trefferquote und Fehlerpunkte, den
   Vergleich mit dem zuletzt abgelegten Stand, Rückschritte und je Testfall den Stand (stabil richtig, schwankend,
   mehrheitlich falsch).
5. **Entscheiden:** Übernommen wird eine Änderung, wenn die Fehlerpunkte nicht steigen und es keinen Rückschritt gibt
   (Bericht: „Übernehmen: ja“). Dann mit `--ablegen <commit>` erneut bewerten (verweigert, wenn die Regel nicht
   erfüllt ist; Commit = letzter Commit, der den Skill ändert) und `verlauf.csv` sowie die Datei unter
   `ergebnisse/` mit der Änderung committen. Sonst nichts ablegen; der Nutzer entscheidet, ob die Änderung verworfen
   oder anders formuliert wird.

## Grenzen

- Der Testsatz schützt vor Rückschritten. Die Regeln stammen aus denselben Fällen; eine hohe Trefferquote sagt nicht,
  wie gut der Skill auf neue Rennen überträgt (ADR 0002).
- Drei Läufe bei einem abweichenden Testfall dämpfen den Zufall, schließen ihn nicht aus: Ein Testfall, der
  „schwankend“ ist, ist kein Rückschritt, aber ein Hinweis, dass die Regel dort nicht eindeutig greift. Ein einzelner
  richtiger Lauf kann eine Schwankung übersehen; das nimmt die gestufte Prüfung für etwa zwei Drittel weniger Läufe in
  Kauf (ADR 0002, Nachtrag).

## Neuer Testfall (in der Durchsicht, je besprochenem Rennen)

1. Karte des Tages aus Drive holen (`racecard_JJJJMMTT_daten.json.gz`, sonst `_daten.json`) und den Durchgang, der das
   Rennen bewertet hat.
2. Prüfen, dass Kandidaten, Festkurs und Modell-Siegchance in der Karte zum Durchgang passen (Nichtstarter können die
   Modell-Siegchance danach ändern). Passt es nicht, keinen Testfall anlegen.
3. `python3 -I REPO/testsatz.py ausschnitt KARTE <race_id>` legt `tests/testsatz_durchgang/karten/<race_id>.json.gz` an.
4. In `tests/testsatz_durchgang/erwartet.json` unter `testfaelle` das Rennen mit den Urteilen des Nutzers eintragen
   (je Kandidat horse, urteil, art; bei Ermessen oder „Claudes Sicht behalten“ zusätzlich `erlaubt` mit Claudes
   Urteil). Kandidaten unter +5 % Value gehören nicht hinein.
