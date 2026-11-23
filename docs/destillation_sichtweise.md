# Destillation des Sichtweise-Interviews

Quelle: `docs/sichtweise_interview.md` (23.11.2026). Ziel: `SKILL.md`, `EINSICHTEN.md`, `scripts/blatt.py` und
`GLOSSARY.md` des Skills `rennkarten-durchgang-neu`. Je Block: Vorschläge wörtlich → Entscheidung des Nutzers
(ja / nein / ändern) → eintragen → Testsatz (gestuft) → Commit. Geschrieben nach `writing-for-agents`.

## Leitlinien (writing-for-agents, angewandt)

- **Sprawl ist die Hauptgefahr.** `SKILL.md` (18 KB) und `EINSICHTEN.md` (14 KB) liest jeder Subagent in jedem Rennen ganz.
  Jeder Block soll den Skill **nicht länger** machen als nötig; wo eine neue Regel eine alte ersetzt, fällt die alte.
- **Rechnen ist Sache des Blatts (Umgebung), Urteilen Sache des Skills.** Schwellen, Klassen, Ränge im Feld, Bahnkategorie
  rechnet `blatt.py` und druckt sie fertig („Klassenindex +7 gegen heute“, „Bahn: groß → Provinz“). Der Skill sagt nur,
  wie schwer das wiegt. Das spart Tokens im Skill und macht die Urteile stabiler.
- **Verzweigung im Blatt statt im Skill:** Die ausführliche Laufanalyse druckt das Blatt nur für den **Referenzlauf**
  (und den letzten Lauf) – genau dort, wo der Nutzer tief liest. Die übrigen Läufe bleiben einzeilig.
- **Leitwörter des Nutzers:** *Referenzlauf*, *Hygienefaktor*, *relativ zum Feld*, *kompetitiv*. Einmal im Glossar
  definiert, dann nur noch als Wort.
- **Positiv formulieren**, eine Bedeutung an einem Ort, keine No-ops (Regeln, die der Agent ohnehin befolgt).

## Blöcke

| Block | Inhalt (Interview) | Ziel |
|---|---|---|
| **1** | **Referenzlauf und Läufe danach** (Q1, G, G9, G10, G12, A8) | Prüfschritte 2/3, EINSICHTEN 2/3, Laufanalyse im Blatt |
| 2 | Wechsel von Belag, Boden, Distanz (A3, A4, A5, D1, D2) | Prüfschritt 4, Distanzklassen im Blatt |
| 3 | Klasse: Rennart, Klassenindex, Marke, Ratings, Gewinn je Lauf, Top-3-Quote (A1, A2, A9, A11, C2, C3, C5, F) | Prüfschritt 1, Leitfrage |
| 4 | Verbindungen: A/E-Matrix, Besitzer, Pause (E1–E4, C8) | Prüfschritt 5, Blatt |
| 5 | Umstände: Bahn, Bias, Tempo, Geschlecht, Gewicht, Box, Toto, Presse, Ausland (A6, A7, A10, A12, B3, C1, C4, C6, G13) | Prüfschritt 6, Blatt |
| 6 | Aufräumen: was aus dem Blatt fällt (B2, A6 Layout) | Blatt |

---

## Block 1 – Referenzlauf und Läufe danach

### V1-1 `SKILL.md`: Prüfschritte 2 und 3 ersetzen (aendern)

**alt** (Prüfliste je Kandidat, Punkte 2 und 3):

> 2. **Letzter Lauf im Zusammenhang.** Welches Rennen, welche Klasse, welche Bahn (groß oder Provinz), welcher Boden,
>    wie weit geschlagen, Kommentar und Rennverlauf. Ein schwacher Lauf unter ganz anderen Bedingungen (andere
>    Distanz, anderer Boden, nicht weit geschlagen) darf übergangen werden. „Nicht weit geschlagen in stärkerem Rennen“
>    zählt mehr als die Platzierung.
> 3. **Referenzlauf.** Der jüngste Lauf unter heutigen Bedingungen (Blatt: `≈heute`, `gleiche Bahn`, `sehr weich`):
>    Platz, Abstand, Marke damals gegen heute (nur im Handicap), **ARR dort gegen Top-ARR im heutigen Feld** (Leitfrage),
>    welche heutigen Gegner er dort geschlagen hat, ob das Rennen **aufgewertet** ist. Gestörte Läufe (Kommentar:
>    behindert, eingeklemmt, „Nase im Wind“/ohne Deckung, am Rand galoppiert; Blatt: gegen den Verlauf, Zwischenfall)
>    unterschätzen das Pferd – entsprechend höher einordnen. Kein Referenzlauf ist selbst ein Fragezeichen. Ist der
>    Referenzlauf schlecht und gibt es kein Argument, warum es heute besser sein sollte, ist das ein starkes
>    Gegenargument.

**neu:**

> 2. **Referenzlauf.** Der jüngste Lauf unter heutigen Bedingungen (Blatt: `≈heute`), höchstens etwa ein Jahr alt, je
>    jünger desto besser. Ihn gründlich lesen, in dieser Reihenfolge:
>    - **kompetitiv?** Platz relativ zur Starterzahl und Abstand in Längen; knapp geschlagen im großen Feld ist oft ein
>      sehr gutes Rennen.
>    - **ARR** des Laufs relativ zum Feld (Rang unter den Läufen der heutigen Starter) und gegen Top-ARR und Maßstäbe
>      (Leitfrage); TR bestätigt.
>    - **Kommentar, Position, Tempo:** klarer Lauf, Effort in der Geraden, kämpferisch – oder behindert, „Nase im Wind“,
>      außen herum. Von weit hinten Boden gutgemacht, als vorne gewonnen wurde, hinten bei langsamem oder vorne bei sehr
>      schnellem Tempo: Der Lauf war besser, als der Platz zeigt.
>    - **Gegner:** wie sie danach liefen (aufgewertet/abgewertet; bei jungen Pferden besonders wichtig) und welche
>      heutigen Gegner es direkt oder indirekt schlug.
>    - **Marke damals gegen heute** (nur im Handicap).
>
>    Kein Referenzlauf ist selbst ein Fragezeichen.
> 3. **Läufe seit dem Referenzlauf (Hygienefaktor).** Die letzten ein bis zwei Läufe unter anderen Bedingungen nur
>    prüfen, nicht bewerten: Lief das Pferd dort ordentlich, zählen sie nicht; war es völlig abgeschlagen (ARR und
>    Abstand zusammen), ist fraglich, ob der Referenzlauf heute übertragbar ist. Kommentar, Box, Jockey und Quote
>    erklären einen schwachen Lauf oft.

*Begründung:* Reihenfolge und Tiefe wie im Interview (G); „letzter Lauf“ wird zum Hygienefaktor (Q1). Ein Satz entfällt
als Doppel (`G-REFERENZ-SCHWACH` steht in `EINSICHTEN.md`). Länge etwa gleich.

### V1-2 `EINSICHTEN.md`: Abschnitte 2 und 3 tauschen und umbenennen (aendern)

`## 2. Letzter Lauf` → `## 3. Läufe seit dem Referenzlauf`; `## 3. Referenzlauf und Leitfrage` → `## 2. Referenzlauf und
Leitfrage`. Inhalte bleiben, Reihenfolge wie die Prüfliste.

### V1-3 `EINSICHTEN.md`: Hygienefaktor (aendern + neu)

**alt:**

> - **[leicht]** `P-LETZTER-ANDERS` Ein schwacher letzter Lauf unter anderen Bedingungen (Boden, Distanz) wird übergangen.
>   *Mister Chang, Come Alone.*

**neu:**

> - **[leicht]** `P-LETZTER-ANDERS` Ein ordentlicher Lauf seit dem Referenzlauf unter anderen Bedingungen (Belag,
>   Boden, Distanz) zählt nicht gegen das Pferd. *Mister Chang, Come Alone.*
> - **[gewichtig]** `G-HYGIENE` War das Pferd seit dem Referenzlauf unter anderen Bedingungen völlig abgeschlagen, ist
>   fraglich, ob der Referenzlauf heute übertragbar ist.

### V1-4 `EINSICHTEN.md`: Quote und Jockey damals (neu)

> - **[leicht]** `P-GEWETTET` / `G-UNGEWETTET` War das Pferd in einem enttäuschenden Lauf gut gewettet, erwartete der
>   Stall mehr – heute ist eine Steigerung möglich, erst recht mit stärkerem Jockey als damals; war es kaum gewettet,
>   leicht dagegen.

### V1-5 `blatt.py`: Laufanalyse für Referenzlauf und letzten Lauf

Unter der Formzeile des **Referenzlaufs** (`≈heute`, der jüngste) und des **letzten Laufs** je eine Zeile:

> `Lauf: früh 9. → 400 m vor dem Ziel 4. (Wagen 2/5; erste drei aus Wagen 1, 1, 3) · +4 Plätze ab 800 m · Weg +9 m ·
> Tempo schnell früh · ARR Rang 2 von 40 Läufen der heutigen Starter (90 Tage) · TR 31 · Gegner danach 5↑ 2↓ (Sieger
> X gewann danach) · heutige Gegner: 4 Y 2,5 L dahinter`

Übrige Läufe bleiben einzeilig wie heute; der Finish-Index kommt nicht hinein.

### V1-6 `GLOSSARY.md`: Hygienefaktor (neu)

> **Hygienefaktor**:
> Die Prüfung der Läufe seit dem Referenzlauf unter anderen Bedingungen: Ordentlich gelaufen zählt nicht, völlig
> abgeschlagen stellt die Übertragbarkeit des Referenzlaufs in Frage.
> _Avoid_: letzte Form (als Urteilsgrundlage)

## Entscheidungen Block 1

Der Nutzer nahm am 23.11. alle Vorschläge an und gab die übrigen Blöcke pauschal frei („ich vertraue deinen
Änderungen pauschal“). Testsatz einmal am Ende über alle Blöcke.


| Vorschlag | Entscheidung | Notiz |
|---|---|---|
| V1-1 | ja (23.11., pauschal) | |
| V1-2 | ja (23.11., pauschal) | |
| V1-3 | ja (23.11., pauschal) | |
| V1-4 | ja (23.11., pauschal) | |
| V1-5 | ja (23.11., pauschal) | |
| V1-6 | ja (23.11., pauschal) | |

---

## Blöcke 2 bis 6 (pauschal freigegeben, 23.11.)

Umgesetzt ohne Einzelvorlage, nach den Leitlinien oben. Wortlaut steht in den Dateien; hier nur was wohin ging.

| Block | `SKILL.md` | `EINSICHTEN.md` | `blatt.py` | `GLOSSARY.md` |
|---|---|---|---|---|
| 2 Wechsel | Prüfschritt 4: Platzquote, Wechsel, Distanzklasse, Distanzwechsel ab 250 m, Nachkommen-Split, Linie relativ zum Feld | `F-BELAG-NEU` geschärft; neu `P-WECHSEL-BESSER` / `G-WECHSEL-SCHLECHTER` | Distanzklasse im Kopf, Platzquote statt A/E in den Vorlieben, Distanzwechsel, Nachkommen je Distanzklasse, Linie mit Pos+/€/L+/maxVal+ und Rang | Distanzklasse |
| 3 Klasse | Prüfschritt 1 „Ausgangslage und Klasse“ (Kennzahl-Reihenfolge, Karriere relativ zum Feld, Zenit, hohe Marken, CGD C > G > D); Klasse des Referenzlaufs; `G-SELTEN-SIEG` → `G-SELTEN-VORNE` | `G-ARR-UNTER` gewichtig mit Ausnahme; neu `P-ABSTIEG`, `P-MARKE-UNTER`, `P-MARKE-HOCH`/`P-MARKE-BEWIESEN`, `G-DREIJAEHRIG-FRUEH`/`P-DREIJAEHRIG-HERBST`, `U-FAVORIT-KLAR` | Karriere (Platzquote, Gewinn je Lauf, Rang), Klassenindex des Laufs gegen heute mit Preis, Ratings mit TR-Wert und ΔL600, Crible auch im Original | – |
| 4 Verbindungen | Prüfschritt 5 „Trainer, Jockey, Besitzer“ (A/E-Matrix 365 Tage zuerst, dann 30 Tage); `F-PAUSE` mit Schwelle | `G-TRAINER-KALT`, `P-TRAINER` auf die Matrix; neu `P-JOCKEY-STARK`, `P-BESITZER` | Matrixlage für Trainer, Jockey, Besitzer; Besitzer = Züchter | – |
| 5 Umstände | Prüfschritt 6 (Gewicht, Tempo/Bias als Indikatoren, Bahnkategorie, PSF-Geläufe, Crible, Toto); `F-WALLACH`, `F-BAHN-EIGENHEIT` gestrichen; `P-WALLACH`; `F-AUSLAND` mit Länderfolge | `G-STUTE`/`P-WALLACH` allgemein; neu `G-GEWICHT-BODEN`, `P-BIAS`/`G-BIAS`, `G-PRESSE`/`G-TOTO` | Bahnkategorie und Bias im Kopf, Bahnwechsel, Land bei Auslandsläufen, Toto-Warnung | Bahnkategorie |
| 6 Aufräumen | – | typische Fehler 6–10 entfernt (stehen jetzt in den Prüfschritten); unter 200 Zeilen | Value-Faktor und Badges entfallen | – |

**Nicht umgesetzt:** Gewichtserlaubnis des Lehrlingsjockeys (fehlt in der Karte); Verteilung der Starts je Alter
(spätere Auswertung); offene Punkte aus dem Interview.

**Umfang danach:** `SKILL.md` 18,5 → 20,6 KB, `EINSICHTEN.md` 13,6 → 15,9 KB, Blatt je Rennen etwa +30 %
(Karte 21.11.). Die Verdichtungsprüfung meldet weiterhin fünf volle Abschnitte – Anlass für die nächste
Ergebnisanalyse.
