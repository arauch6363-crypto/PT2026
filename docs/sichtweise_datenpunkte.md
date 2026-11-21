# Sichtweise je Datenpunkt

Rohtext des Nutzers: wie er jeden Datenpunkt des Blatts liest und gewichtet. **Quelle, nicht Skill** – der Durchgang
liest diese Datei nicht. Aus ihr werden in Themenblöcken Vorschläge destilliert (Schwellen → `blatt.py`, Begriffe →
`GLOSSARY.md`, Prüfregeln → `SKILL.md`, Gewichte → `EINSICHTEN.md`), wie in der Ergebnisanalyse mit Ja/Nein/Ändern und
Testsatz je Block. Die Begründungen bleiben hier.

**So ausfüllen:** Unter **Deine Sicht** frei schreiben. Am meisten bringen Zahlen („ab 250 m“), Bedingungen („nur
wenn …“, „immer“) und Gewichte („kippt allein“, „zählt deutlich“, „nur am Rande“). Wo der Skill schon stimmt, genügt
„passt“. **Offen** sind meine Fragen an der Stelle, wo der Skill heute schweigt oder vage ist. Der Abschnitt kann
auch im Chat diktiert werden; Claude trägt ihn ein.

Stand des Skills: 21.11.2026. Kennungen und Gewichte aus `SKILL.md` / `EINSICHTEN.md`.

---

## A. Rennkopf

### A1 Rennart (Handicap, Conditions, Claimer, Maiden, Listed, Gruppe)

- **Skill heute:** Handicap → Marke gegen letzte Sieg-/Platzmarke; sonst gewichtsbereinigte Valeur
  (`P-VALEUR-HOECHSTE`). Claimer → Handicap ist ein Aufstieg (`G-CLAIMER-AUFSTIEG` [gewichtig]). Spezialität des
  Trainers je Rennart (`G-TRAINER-SPEZIALITAET`).
- **Offen:** Unterscheidest du Handicap-Stufen (Quinté, Catégorie divisée, Course B)? Was ändert sich in Listed und
  Gruppe (kleine Felder, Klasse vor Form)? Gelten in Maidens/Debütantenrennen andere Hauptkriterien?

> **Deine Sicht:**

### A2 Altersklasse des Rennens (2j, 3j, 3j+, 4j+)

- **Skill heute:** nur indirekt: Exposure relativ zum Alter, `G-STUTE` bei jungen Pferden, Abstammung und Qualität
  der Linie bei jungen Pferden.
- **Offen:** Dreijährige gegen Ältere (Gewichtsvorteil, Jahreszeit)? Entwicklung der Zwei- und Dreijährigen über die
  Saison (dein Beispiel bei Distanz)? Ab welchem Alter lässt ein Pferd nach?

> **Deine Sicht:**

### A3 Distanz

- **Skill heute:** keine Distanzklassen. `F-DISTANZ-NEU` „erstmals diese Distanzgruppe“ (Gruppe nicht definiert),
  `G-DISTANZ-PROBLEME` [ausschlaggebend], entkräftet, wenn Abstammung und Formtrend die längere Distanz tragen. Ein
  Lauf gilt als „≈heute“ bei bis zu 200 m Unterschied.
- **Offen:** deine Klassen (Sprint, Mitteldistanz, Steher, Extremsteher); ab welchem Distanzwechsel es zählt; ob 200 m
  für den Referenzlauf passen oder je Distanz anders sein sollten (200 m im Sprint ≠ 200 m auf 3000 m).

> **Deine Sicht:** *(Entwurf aus dem Chat vom 21.11.)* Sprintrennen bis 1400 m, unter 1200 m an Sprintspezialisten
> gerichtet. Steherrennen ab 2400 m, ab 2800 m an Extremsteher gerichtet. Je extremer die Distanz, desto mehr achte
> ich auf die Abstammung und die bisherigen Leistungen auf dieser Strecke; bei Mitteldistanz weniger entscheidend.
> Bei Zwei- und Dreijährigen wächst die Distanzreichweite bis etwa zum Sommer; Zweijährige laufen zu Beginn nur
> Sprintdistanzen, 1600 m kann im Sommer für einen Zweijährigen schon eine Steherdistanz sein. Distanzänderungen seit
> dem letzten Start ab etwa 250 m sind auffällig; dann achte ich verstärkt auf Abstammungssignale zur Distanz und auf
> frühere Leistungen auf der neuen Distanz.

### A4 Bodenangabe, Bodengruppe, Quelle

- **Skill heute:** ausführlich für weichen Boden: Collant = Lourd (Very slow), Souple belegt Très souple nicht
  vollständig (`F-BODEN-SOUPLE` [leicht]), `F-BODEN-NEU` ab Très souple, `G-BODEN-WEICH-SCHWACH` [gewichtig],
  `P-BODEN-BEWAEHRT` [gewichtig]; Abstammung zählt bei den ersten ein bis drei Läufen auf einem Boden.
- **Offen:** schneller Boden (Bon, Bon léger, Sec) – gleich streng? Wie liest du eine Bodenangabe, die nur
  angenommen ist (Quelle „Annahme“) oder sich am Renntag ändern kann? PSF-Zustände (standard, lente, rapide)?

> **Deine Sicht:**

### A5 Belag (Gras, PSF)

- **Skill heute:** `F-BELAG-NEU` [leicht]: erstmals PSF kaum negativ, wenn die Abstammung passt; Vater zählt mehr.
  `G-KEIN-REFERENZ`, wenn auf dem Belag noch kein Lauf.
- **Offen:** Wechsel PSF → Gras ebenso? Gibt es PSF-Spezialisten, die auf Gras abfallen?

> **Deine Sicht:**

### A6 Bahn und Richtung (Rechts-, Linkskurs, gerade Bahn)

- **Skill heute:** `P-BAHN` (Bahnbewährung), `G-RICHTUNG` [gewichtig], `F-BAHN-EIGENHEIT` (Strasbourg,
  Fontainebleau), `P-PROVINZ` / umgekehrt Gegen (Bahnkategorie).
- **Offen:** Welche Bahnen haben für dich Eigenheiten (Steigung, enge Kurven, lange Gerade) und was folgt daraus?
  Welche zählen als groß, welche als Provinz? Ab wie vielen Läufen ist eine Richtungsbilanz belastbar?

> **Deine Sicht:**

### A7 Feldgröße

- **Skill heute:** nur relativ beim Modell-Rang (Drittel).
- **Offen:** Ändert ein großes Feld (16+) oder ein kleines (unter 7) dein Urteil – Box, Tempo, Kursspanne?

> **Deine Sicht:**

### A8 Klassenindex und Preisgeld

- **Skill heute:** Klassenindex zum Vergleich von Rennen („stärkeres Rennen“, Claimer-Ausgleich nur bei deutlich
  höherem Index), keine Schwellen. Preisgeld wird nicht verwendet.
- **Offen:** Ab welchem Abstand ist ein Rennen „deutlich stärker“ (5 Punkte, 10 Punkte)? Sagt dir das Preisgeld
  etwas?

> **Deine Sicht:**

### A9 Tempo und Laufstile

- **Skill heute:** `G-TEMPO-VORNE` (vorne laufend bei schnellem Tempo mit mehreren Führenden); von hinten bei
  schnellem Tempo = Pro.
- **Offen:** langsames Tempo / einzelner Führer (Vorteil vorne?); Tempo „unbekannt“; Zusammenspiel mit Distanz
  (Sprint vs. Steher).

> **Deine Sicht:**

### A10 FK-Favorit, Top-ARR, Top-Valeur, Höchstgewicht

- **Skill heute:** Elle für die Leitfrage zusammen mit den Maßstäben (`U-MASSSTAB`, `G-MASSSTAB-BESSER`,
  `U-ARR-ABSTAND` [leicht]: etwa 3 Punkte ARR unter dem Besten → höchstens klein).
- **Offen:** Wie stark ein klarer Favorit (FK unter 2) das ganze Rennen für dich verändert.

> **Deine Sicht:**

---

## B. Kandidat: Modell und Markt

### B1 Modell-Siegchance, Modell-Rang, Value

- **Skill heute:** Value nur Filter; Rang nach Drittel (`P-RANG-VORNE`, `G-RANG-HINTEN` [gewichtig]); Faustregel nach
  Value (`U-FAUSTREGEL`), `U-VALUE-DUENN` [ausschlaggebend], `U-VALUE-OHNE-PRO`, `G-MODELL-UNSICHER` [vorläufig].
- **Offen:** passt die Faustregel so?

> **Deine Sicht:**

### B2 Value-Faktor (gold, Warnung)

- **Skill heute:** **nicht verwendet** – steht im Blatt, keine Regel.
- **Offen:** Was bedeuten „gold“ und „Warnung“ für dich, und sollen sie zählen?

> **Deine Sicht:**

---

## C. Kandidat: Pferd

### C1 Alter und Geschlecht

- **Skill heute:** `G-STUTE` [leicht] bei jungen Pferden, `F-WALLACH` (erstmals Wallach), `G-EXPOSED-ALT` (7–8 Jahre).
- **Offen:** Stuten im Herbst / in Stutenrennen? Erster Start als Wallach – eher Plus oder Fragezeichen?

> **Deine Sicht:**

### C2 Starts, Siege, Plätze (Exposure, Siegquote)

- **Skill heute:** Exposure relativ zum Alter (21 Starts mit 3 = sehr viel; 25 mit 4 = relativ jung),
  `P-UNEXPOSED`, `G-SELTEN-SIEG` (unter einem Sieg je etwa 14 Starts, viele Plätze).
- **Offen:** passt die Grenze 1:14? Gilt ein „ewiger Zweiter“ anders als ein seltener Sieger mit wenigen Plätzen?

> **Deine Sicht:**

### C3 Gewicht (kg, Höchstgewicht)

- **Skill heute:** nur `G-GEWICHT-BODEN` (ab etwa 62 kg auf Très souple oder schwerer) und
  `G-GEWICHT-KLASSE-BODEN` [ausschlaggebend].
- **Offen:** Gewichtsänderung gegen den letzten Lauf; Gewichtserlaubnis von Nachwuchsjockeys (Lehrling, Cravache
  d'or); Gewicht auf schnellem Boden oder kurzer Distanz.

> **Deine Sicht:**

### C4 Marke (nur Handicap) und Valeur bereinigt (sonst)

- **Skill heute:** `P-MARKE-UNTER` („deutlich“ unter letzter Sieg-/Platzmarke), `G-UEBER-SIEGMARKE` [gewichtig],
  `F-AUFGEWICHT`; außerhalb des Handicaps `P-VALEUR-HOECHSTE`.
- **Offen:** Ab wie viel kg ist „deutlich“ – unter und über der Marke? Sieg- oder Platzmarke, welche zählt mehr?

> **Deine Sicht:**

### C5 Box

- **Skill heute:** nur signifikante Abweichung zählt (`G-BOX` [gewichtig], `P-BOX` [leicht]).
- **Offen:** Box je nach Distanz und Bahn (kurzer Weg zur ersten Kurve)?

> **Deine Sicht:**

### C6 Laufstil

- **Skill heute:** nur im Zusammenspiel mit dem Tempo (A9).

> **Deine Sicht:**

### C7 Tage seit letztem Start, Startfolge

- **Skill heute:** `F-PAUSE` „lange Pause“ **ohne Schwelle**; `G-STARTFOLGE` ab etwa 4 Starts in 6 Wochen.
- **Offen:** Ab wie vielen Tagen ist eine Pause lang – je Alter oder Trainer anders? Ist ein Start nach 7–14 Tagen
  ein Plus (Trainer nutzt die Form)?

> **Deine Sicht:**

### C8 CGD

- **Skill heute:** `P-CGD` [gewichtig], „lässt aufhorchen“, kann bei dünnem Value den Ausschlag geben.
- **Offen:** Zählt ein großes C/G/D (gewonnen) deutlich mehr als ein kleines (platziert)? Welcher der drei
  Buchstaben wiegt für dich am meisten?

> **Deine Sicht:**

### C9 Badges

- **Skill heute:** **nicht verwendet**. Bedeutung (`racecard.py`): C = schon auf dieser Bahn gewonnen, D = über diese
  Distanz (±100 m) gewonnen, CD = beides im selben Lauf, BF = im letzten Lauf als Favorit geschlagen.
- **Offen:** CD überschneidet sich mit CGD – reicht CGD? Ist „BF“ (geschlagener Favorit) für dich ein Signal, und in
  welche Richtung?

> **Deine Sicht:**

### C10 Ausrüstung und Ausrüstungswechsel

- **Skill heute:** ausführlich nach den Bilanzen mit und ohne (`G-AUSRUESTUNG-WEG` [ausschlaggebend],
  `P-AUSRUESTUNG-ZURUECK` [gewichtig], `F-AUSRUESTUNG-NEU`).

> **Deine Sicht:**

---

## D. Kandidat: Vorlieben und Abstammung

### D1 Vorlieben Boden, Distanz, Bahn, Richtung (Gesamtbilanz, A/E)

- **Skill heute:** immer aus den Vorlieben lesen, nicht aus den Formzeilen; Boden ausführlich (A4), Distanz nur
  `G-DISTANZ-PROBLEME`.
- **Offen:** Ab wie vielen Läufen ist eine Bilanz belastbar? Ab welchem A/E ist sie gut (über 1,2?) bzw. schlecht
  (unter 0,7?)?

> **Deine Sicht:**

### D2 Abstammung (Gesamtwert, Skalen Boden, Distanz, Belag, Reife)

- **Skill heute:** nur wo eigene Erfahrung fehlt (junge Pferde, ein bis drei Läufe auf dem Boden). `G-ABSTAMMUNG`
  [ausschlaggebend] ab etwa −15, `F-ABSTAMMUNG-LEICHT` um −9; Vater zählt mehr (`F-BELAG-NEU`); Frankels und sehr
  weicher Boden.
- **Offen:** Skala **Reife** (wann zählt sie)? Skala **Distanz** bei Distanzwechsel (siehe A3)? Weitere Hengste mit
  Eigenheiten wie Frankel?

> **Deine Sicht:**

### D3 Qualität der Linie (Valeur-Index, Gewinn je Lauf)

- **Skill heute:** zählt bei jungen Pferden „fürs Potenzial“, **ohne Schwellen**.
- **Offen:** Ab welchem Index ist eine Linie stark (über 110?) bzw. schwach (unter 90?)?

> **Deine Sicht:**

---

## E. Kandidat: Verbindungen

### E1 Trainer (Form 30 Tage, Bahn, Rennart, Alter, Stall, Wechsel)

- **Skill heute:** ausführlich: `G-TRAINER-KALT` [gewichtig] (etwa 2/40, A/E um 0,5), `P-TRAINER`, `G-STALL-KLEIN`,
  `G-TRAINER-SPEZIALITAET`, `F-TRAINERWECHSEL`, `P-NEUER-TRAINER` [vorläufig], `G-DEBUET-STALL` [ausschlaggebend],
  `P-BRITE`.
- **Offen:** Trainer, die du namentlich kennst (bringen Pferde frisch, mögen bestimmte Bahnen)?

> **Deine Sicht:**

### E2 Jockey und Gespann

- **Skill heute:** `P-JOCKEY-KENNT` [leicht], `P-GESPANN` [gewichtig], Jockey-A/E über 1 = Pro.
- **Offen:** Jockeywechsel zum Spitzenjockey als Signal? Nachwuchsjockeys mit Gewichtserlaubnis (siehe C3)?

> **Deine Sicht:**

---

## F. Kandidat: Ratings

### F1 ARR (bereinigt, Rang, Bestwert)

- **Skill heute:** Kern der Leitfrage: ARR im Referenzlauf gegen Top-ARR und Maßstäbe (`G-ARR-UNTER`
  [ausschlaggebend], `U-ARR-ABSTAND`, `G-MASSSTAB-BESSER`).

> **Deine Sicht:**

### F2 TR-Rang, RTR-Rang, Duelle

- **Skill heute:** **nicht verwendet** – steht im Blatt, keine Regel.
- **Offen:** Sollen sie zählen, etwa die Duelle (Längen vor oder hinter den heutigen Gegnern) als Ergänzung zu
  `G-DIREKT-HINTER` / `P-GEGNER-GESCHLAGEN`?

> **Deine Sicht:**

---

## G. Formzeilen

### G1 Platz, Abstand in Längen, Feldgröße

- **Skill heute:** Abstand vor Platzierung; „nicht weit geschlagen in stärkerem Rennen“ zählt mehr;
  `G-LETZTER-HEUTE-BODEN` ab 5 Längen; „unzuverlässig“ ab 10 Längen (nur Markierung).
- **Offen:** Ab wie vielen Längen ist ein Lauf „nah dran“ (unter 2?)? Wie gehst du mit Läufen über 10 Längen um?

> **Deine Sicht:**

### G2 Quote im damaligen Lauf

- **Skill heute:** **nicht verwendet**.
- **Offen:** Sagt dir ein geschlagener Favorit oder ein Außenseiter, der knapp verlor, etwas?

> **Deine Sicht:**

### G3 Klassenindex des Laufs, aufgewertet / abgewertet

- **Skill heute:** `P-ABSTIEG` nur, wenn die stärkeren Rennen nicht abgewertet sind; aufgewertet hebt den
  Referenzlauf (Mehrheit der Gegner lief danach besser).

> **Deine Sicht:**

### G4 Rennverlauf und Zwischenfall

- **Skill heute:** `P-GEGEN-VERLAUF` [gewichtig], `P-GESTOERT`, `G-SIEG-MIT-VERLAUF`.

> **Deine Sicht:**

### G5 Rennkommentar und Crible

- **Skill heute:** Kontext; gestörte Läufe aus dem Kommentar höher einordnen.
- **Offen:** Gibt es Formulierungen im Kommentar, die für dich ein klares Signal sind („a fini fort“, „sans être
  inquiété“)?

> **Deine Sicht:**

### G6 Externe und ausländische Läufe

- **Skill heute:** `F-AUSLAND`, Lücke statt Negativbefund; `G-MODELL-UNSICHER` [vorläufig].

> **Deine Sicht:**

---

## H. Was im Blatt fehlt

Angaben, die du beim Urteil nutzt, die aber nicht im Blatt stehen (bekannt: Tagesquoten und PMU-Prognose sind bewusst
nicht im Modell).

> **Deine Sicht:**
