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
- **Veto und Deckel** stehen als Vermerk direkt hinter der Kennung (`` `G-…` **Veto** ``): Veto trägt jede
  [ausschlaggebend]-Einsicht an ihrer Gegen- bzw. Urteils-Kennung, Deckel nur, wo der Text selbst „höchstens kleine
  Wette“ sagt. `durchgang.vermerke()` liest sie, die strenge Prüfung setzt sie durch.
- **Auslöser gehören ins Blatt:** Lässt sich die Bedingung einer neuen oder geänderten Regel aus der Karte rechnen,
  ergänzt `scripts/blatt.py` (`ausloeser`) sie mit derselben Schwelle wie im Text, dazu Test und Zeile in `DATEN.md`.
- **Rückschau bei Verschärfung:** Ein Vorschlag, der Urteile strenger macht (neues Veto oder neuer Deckel, höheres
  Gewicht, engere Schwelle), nennt vor der Zustimmung die Rückschau der Ergebnisanalyse: welche früheren Sieger unter
  den Claude-Tipps die Regel gestrichen hätte.
- Widerspricht ein neues Urteil einer Regel oder Einsicht, das ansprechen (Ausnahme oder Regel zu streng?). Neue
  Begriffe gehen in `GLOSSARY.md`.
