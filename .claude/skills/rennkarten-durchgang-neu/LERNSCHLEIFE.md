# Lernschleife

Gilt nur für die Durchsicht mit dem Nutzer, nicht für den automatischen Durchgang. Herkunft der Regeln: Interview vom
10./11.11.2026 (`docs/interview_rennkarten_durchgang.md`).

- **Je besprochenem Rennen** ins Fallarchiv des Repos (eine Zeile je Kandidat, Art **Übereinstimmung**, **Claude
  lernt** oder **Claudes Sicht behalten**; Ort und Format in `claude_projekt/aufgabe_durchsicht.md`) und dazu ein **Testfall** im
  Testsatz (`claude_projekt/aufgabe_testsatz.md`). Archiv und Testsatz gehören nicht zum Skill und werden beim
  Durchgang nicht gelesen.
- **Vor jeder Änderung** an diesem Skill den Testsatz laufen lassen (gestuft, einmal für alle Änderungen der Sitzung); übernommen wird nur, was die Fehlerpunkte nicht
  erhöht und keinen Rückschritt bringt (ADR 0002).
- **Vor jeder vorgeschlagenen Änderung** an `SKILL.md`, `EINSICHTEN.md` oder `LERNSCHLEIFE.md`
  `.claude/skills/writing-for-agents/SKILL.md` lesen und anwenden: Jeder Text steht danach im Kontext jedes Durchgangs.
- **Am Ende der Sitzung verdichten:** Änderungen an `EINSICHTEN.md` (Gewicht aus der Argumentation des Nutzers, ein
  Beispiel je Einsicht, Doppeltes zusammenfassen) und an `SKILL.md` vorschlagen, Zustimmung abwarten, dann eintragen.
  `SKILL.md` bleibt ohne Pferdenamen als Beleg (nur die Formatbeispiele nennen Pferde).
- **Regel in `SKILL.md`** erst, wenn zwei Fälle „Claude lernt“ in dieselbe Richtung zeigen oder der Nutzer sie
  ausdrücklich zur Regel erklärt; bis dahin in `EINSICHTEN.md` im Abschnitt ihres Prüfschritts mit dem Vermerk
  „vorläufig“. Abweichende, vom Nutzer nicht abgelehnte Urteile und Lagen, in denen der Nutzer selbst schwankte, kommen
  unter „Ermessen“.
- **Jede Kennung steht genau einmal** in `SKILL.md` (was geprüft wird) bzw. `EINSICHTEN.md` (wie schwer es wiegt) –
  eine Einsicht zu einer Kennung steht nur in einem Abschnitt, mit einem Gewicht.
- **Kennungen sind dauerhaft:** Eine neue Regel oder Einsicht bekommt eine neue Kennung; eine bestehende wird nie
  umbenannt oder für eine andere Bedeutung wiederverwendet (das Regelprotokoll der Ergebnisanalyse zählt nach ihr).
  Eine gestrichene Regel nimmt ihre Kennung mit.
- Widerspricht ein neues Urteil einer Regel oder Einsicht, das ansprechen (Ausnahme oder Regel zu streng?). Neue
  Begriffe gehen in `GLOSSARY.md`.
