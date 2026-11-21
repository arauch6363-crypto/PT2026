# Skill rennkarten-durchgang-neu wird am Urteil des Nutzers gemessen, nicht am Ertrag

Eine Änderung am Skill (`SKILL.md`, `EINSICHTEN.md`) wird übernommen, wenn sie am **Testsatz** nicht schlechter
abschneidet: Testfälle sind Rennen mit den Urteilen des Nutzers aus der Fallsammlung, jedes Rennen läuft bis zu dreimal mit
dem Subagenten-Prompt des automatischen Durchgangs. Eine **Fehlwette** zählt 2, ein **verpasster Kandidat** 1, eine
Stufe Abstand (Wette gegen Kleine Wette) die Hälfte. Übernommen wird, wenn die Summe nicht steigt und kein Testfall von
„in allen drei Läufen richtig“ auf „mehrheitlich falsch“ kippt. Ertrag und verpasste Sieger prüfen getrennt davon,
etwa monatlich, die **Regeln des Nutzers**: im Value-Dashboard, Abschnitt Claude-Tipps (NAP, BET, Abgelehnt).

## Considered Options

- **Ertrag (ROI) der Claude-Tipps als Maßstab** – verworfen: Er bewertet die Wettstrategie des Nutzers, nicht ob der
  Skill sie umsetzt, und braucht bei Festkursen um 10 Hunderte Wetten, bevor ein Unterschied mehr als Zufall ist (bis
  18.11.2026 gab es 41 Claude-Tipps).
- **Verpasste Sieger als Maßstab** – verworfen aus demselben Grund; bleibt als Signal in der Zeile „Abgelehnt“.
- **Fehlwette und verpasster Kandidat gleich schwer** – verworfen: Claude-Tipps aus dem automatischen Durchgang werden
  gespielt, eine Fehlwette kostet Geld, ein verpasster Kandidat nur eine Gelegenheit; die bisherigen Abweichungen
  waren überwiegend zu großzügig.

## Consequences

- Der Testsatz schützt nur vor **Rückschritten**. Weil die Regeln aus denselben Fällen abgeleitet sind, sagt eine hohe
  Trefferquote nichts darüber, wie gut der Skill auf neue Rennen überträgt; das zeigt erst die nächste Durchsicht.
- Fälle vom 10. und 11.11.2026 (Interview) fehlen im Testsatz: Für diese Tage ist kein Kartenstand mehr erreichbar.
  Fälle, deren Pferd nach heutiger Regel kein Kandidat ist (Value unter +5 %), zählen nicht.

## Nachtrag 21.11.2026: gestufter Testsatz

Drei Läufe je Testfall kosteten bei sieben Testfällen 21 Subagenten je Prüfung, jeder mit dem ganzen Skill im Kontext;
alle sieben bisher abgelegten Stände waren 7/7 stabil richtig. Seither läuft jeder Testfall zuerst **einmal**; nur ein
Testfall, dessen erster Lauf vom Urteil des Nutzers abweicht, bekommt die Läufe zwei und drei (`testsatz.py nachlauf`).
Ein richtiger erster Lauf zählt als stabil richtig. Die Übernahmeregel bleibt: Fehlerpunkte steigen nicht, kein Testfall
kippt von stabil richtig auf mehrheitlich falsch. Preis: Eine Regel, die nur in einem von drei Läufen falsch greift,
fällt seltener auf. Im Normalfall sieben statt 21 Läufe. Der Testsatz läuft einmal für alle Änderungen einer
Ergebnisanalyse oder Durchsicht zusammen, nicht je Änderung.
