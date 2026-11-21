# Sichtweise je Datenpunkt

Rohtext des Nutzers: wie er jeden Datenpunkt der Rennkarte liest und gewichtet. **Quelle, nicht Skill** – der
Durchgang liest diese Datei nicht. Aus ihr werden in Themenblöcken Vorschläge destilliert (Schwellen → `blatt.py`,
Begriffe → `GLOSSARY.md`, Prüfregeln → `SKILL.md`, Gewichte → `EINSICHTEN.md`), wie in der Ergebnisanalyse mit
Ja/Nein/Ändern und Testsatz je Block. Die Begründungen bleiben hier.

**Grundlage:** alle Felder der Karte vom 21.11.2026 (`racecard_20261121_daten.json.gz`) und ihre Anzeige in der
HTML-Karte (`racecard_template.html`), abgeglichen mit dem, was `blatt.py` dem Durchgang zeigt, und mit `SKILL.md` /
`EINSICHTEN.md`. Je Datenpunkt:

- **Blatt:** ✅ zeigt es dem Durchgang · ◐ nur teilweise · ❌ nur in der Karte – der Durchgang sieht es nicht.
- **Skill heute:** was die Regeln dazu sagen (Kennung, Gewicht).
- **Offen:** meine Fragen, wo der Skill schweigt oder vage ist.
- **Deine Sicht:** frei schreiben. Am meisten bringen Zahlen („ab 250 m“), Bedingungen („nur wenn …“, „immer“) und
  Gewichte („kippt allein“, „zählt deutlich“, „nur am Rande“). Wo der Skill stimmt: „passt“. Bei ❌ zusätzlich: soll
  der Durchgang es sehen, oder bleibt es weg? Auch im Chat diktierbar; Claude trägt es ein.

> **Behoben am 21.11.:** Das Blatt zeigt jetzt den Rennkommentar (übersetzt, sonst das französische Original) und
> die älteren Läufe mit gleicher Bahn, Distanz oder Boden, die die Karte nach den letzten sieben anhängt (G11, G12).

---

## A. Rennen

### A1 Rennart (Handicap, Conditions, Claimer, Maiden, Listed, Gruppe) · Blatt ✅

- **Skill heute:** Handicap → Marke gegen letzte Sieg-/Platzmarke; sonst gewichtsbereinigte Valeur
  (`P-VALEUR-HOECHSTE`). Claimer → Handicap ist ein Aufstieg (`G-CLAIMER-AUFSTIEG` [gewichtig]). Spezialität des
  Trainers je Rennart (`G-TRAINER-SPEZIALITAET`).
- **Offen:** Handicap-Stufen (Quinté, Catégorie divisée, Course B)? Was ändert sich in Listed und Gruppe? Andere
  Hauptkriterien in Maidens und Debütantenrennen?

> **Deine Sicht:**

### A2 Altersklasse und Geschlecht des Rennens · Blatt ◐ (Alter ✅, Stutenrennen ❌)

- **Skill heute:** nur indirekt: Exposure relativ zum Alter, `G-STUTE` [leicht] bei jungen Pferden.
- **Offen:** Dreijährige gegen Ältere (Gewichtsvorteil, Jahreszeit)? Entwicklung der Zwei- und Dreijährigen über die
  Saison? Stutenrennen (Karte: `sex`) anders lesen?

> **Deine Sicht:**

### A3 Distanz und Distanzklasse · Blatt ◐ (Meter ✅, Klasse der Karte ❌)

- **Karte:** Distanzklassen `dist_label`: bis 1300 m · 1301–1700 · 1701–2100 · 2101–2600 · über 2600 m; feinere
  Gruppe `dist_group` (z. B. 1801–2000). CGD und Vorlieben rechnen mit diesen Gruppen.
- **Skill heute:** keine Distanzklassen. `F-DISTANZ-NEU` „erstmals diese Distanzgruppe“, `G-DISTANZ-PROBLEME`
  [ausschlaggebend], entkräftet, wenn Abstammung und Formtrend die längere Distanz tragen. Ein Lauf gilt als „≈heute“
  bei bis zu 200 m Unterschied.
- **Offen:** Deine Grenzen (unten) weichen von denen der Karte ab (Sprint bis 1400 statt 1300, Steher ab 2400 statt
  2600). Welche sollen gelten – und sollen Vorlieben und CGD dann auch nach deinen Klassen rechnen? Passen 200 m für
  den Referenzlauf auf jeder Distanz?

> **Deine Sicht:** *(Entwurf aus dem Chat vom 21.11.)* Sprintrennen bis 1400 m, unter 1200 m an Sprintspezialisten
> gerichtet. Steherrennen ab 2400 m, ab 2800 m an Extremsteher gerichtet. Je extremer die Distanz, desto mehr achte
> ich auf die Abstammung und die bisherigen Leistungen auf dieser Strecke; bei Mitteldistanz weniger entscheidend.
> Bei Zwei- und Dreijährigen wächst die Distanzreichweite bis etwa zum Sommer; Zweijährige laufen zu Beginn nur
> Sprintdistanzen, 1600 m kann im Sommer für einen Zweijährigen schon eine Steherdistanz sein. Distanzänderungen seit
> dem letzten Start ab etwa 250 m sind auffällig; dann achte ich verstärkt auf Abstammungssignale zur Distanz und auf
> frühere Leistungen auf der neuen Distanz.

### A4 Boden: Bodenangabe, Gruppe, Quelle, Messwert · Blatt ◐ (Messwert `going_value` ❌)

- **Skill heute:** ausführlich für weichen Boden: Collant = Lourd (Very slow), Souple belegt Très souple nicht
  vollständig (`F-BODEN-SOUPLE` [leicht]), `F-BODEN-NEU` ab Très souple, `G-BODEN-WEICH-SCHWACH` [gewichtig],
  `P-BODEN-BEWAEHRT` [gewichtig]; Abstammung zählt bei den ersten ein bis drei Läufen auf einem Boden.
- **Offen:** schneller Boden (Bon, Bon léger, Sec) – gleich streng? Angenommene Bodenangabe (Quelle „Annahme“)?
  PSF-Zustände? Nutzt du den Penetrometer-Wert von France Galop?

> **Deine Sicht:**

### A5 Belag (Gras, PSF) · Blatt ✅

- **Skill heute:** `F-BELAG-NEU` [leicht]: erstmals PSF kaum negativ, wenn die Abstammung passt; Vater zählt mehr.
  `G-KEIN-REFERENZ`, wenn auf dem Belag noch kein Lauf.
- **Offen:** Wechsel PSF → Gras ebenso? PSF-Spezialisten, die auf Gras abfallen?

> **Deine Sicht:**

### A6 Bahn, Richtung, Layout · Blatt ◐ (Bahn und Richtung ✅, Layout eng/normal/weit ❌)

- **Karte:** Bahn-Layout (eng, normal, weit) und Konfiguration (Bahn, Distanz, Belag, Richtung); Vorlieben des
  Pferdes und des Jockeys je Layout.
- **Skill heute:** `P-BAHN`, `G-RICHTUNG` [gewichtig], `F-BAHN-EIGENHEIT` (Strasbourg, Fontainebleau), `P-PROVINZ`.
- **Offen:** Welche Bahnen haben für dich Eigenheiten und was folgt daraus? Welche zählen als groß, welche als
  Provinz? Ab wie vielen Läufen ist eine Richtungs- oder Layoutbilanz belastbar?

> **Deine Sicht:**

### A7 Bahn-Bias (vorne oder hinten im Vorteil) · Blatt ❌

- **Karte:** je Bahn und Distanz aus den bisherigen Rennen: Sieg-Impact vorderes gegen hinteres Drittel (z. B.
  Deauville 1900 m: vorne 1,29, hinten 0,65 aus 362 Rennen).
- **Skill heute:** nichts.
- **Offen:** Soll der Bias mit Laufstil und Tempo zusammen zählen (Vorreiter auf einer Vorne-Bahn)?

> **Deine Sicht:**

### A8 Feldgröße · Blatt ✅

- **Karte:** Jockey-Bilanz je Feldgröße (klein bis 7, normal 8–12, groß ab 13) – Blatt ❌.
- **Skill heute:** nur relativ beim Modell-Rang (Drittel).
- **Offen:** Ändert ein großes oder kleines Feld dein Urteil – Box, Tempo, Kursspanne, Jockey?

> **Deine Sicht:**

### A9 Klassenindex und Preisgeld · Blatt ✅ (Index), Preisgeld nur Kopf

- **Karte:** zweiter Klassenindex über Gewinn je Lauf (`class.epr_idx`) – Blatt ❌.
- **Skill heute:** Klassenindex zum Vergleich von Rennen, keine Schwellen. Preisgeld ungenutzt.
- **Offen:** Ab welchem Abstand ist ein Rennen „deutlich stärker“? Valeur-Index oder Gewinn-Index – welcher sagt dir
  mehr?

> **Deine Sicht:**

### A10 Tempo und Laufstile · Blatt ✅

- **Skill heute:** `G-TEMPO-VORNE` (vorne laufend bei schnellem Tempo mit mehreren Führenden); von hinten bei
  schnellem Tempo = Pro.
- **Offen:** langsames Tempo / einzelner Führer; Tempo „unbekannt“; Zusammenspiel mit Distanz und Bahn-Bias (A7).

> **Deine Sicht:**

### A11 FK-Favorit, Top-ARR, Top-Valeur, Höchstgewicht · Blatt ✅

- **Skill heute:** Elle für die Leitfrage zusammen mit den Maßstäben (`U-MASSSTAB`, `G-MASSSTAB-BESSER`,
  `U-ARR-ABSTAND` [leicht]).
- **Offen:** Wie stark ein klarer Favorit (FK unter 2) das Rennen für dich verändert.

> **Deine Sicht:**

### A12 Presse: Prognose, Tipps, Crible · Blatt ◐ (Crible ✅, Prognose und Tipps ❌ – bewusst)

- **Karte:** PMU-Prognose (Rang, Kurs), Tipp-Konsens der Presse, Crible.
- **Skill heute:** Crible ist Kontext; Prognose bisher bewusst nicht im Blatt.
- **Offen:** Bleibt es dabei?

> **Deine Sicht:**

---

## B. Modell und Markt

### B1 Modell-Siegchance, Modell-Rang, Value · Blatt ✅

- **Skill heute:** Value nur Filter; Rang nach Drittel (`P-RANG-VORNE`, `G-RANG-HINTEN` [gewichtig]); Faustregel nach
  Value (`U-FAUSTREGEL`), `U-VALUE-DUENN` [ausschlaggebend], `U-VALUE-OHNE-PRO`, `G-MODELL-UNSICHER` [vorläufig].
- **Offen:** passt die Faustregel so?

> **Deine Sicht:**

### B2 Value-Faktor (gold, Warnung), Siegchance ohne Markt · Blatt ◐ (Wert ✅, ohne Markt ❌)

- **Skill heute:** **nicht verwendet**.
- **Offen:** Was bedeuten „gold“ und „Warnung“ für dich? Sagt dir ein großer Abstand zwischen Siegchance mit und
  ohne Markt etwas?

> **Deine Sicht:**

### B3 Platz-Festkurs, Toto, Kelly-Tipp der Karte · Blatt ❌

- **Skill heute:** nichts (es geht um Siegwetten).
- **Offen:** Spielen Platzkurs oder Totokurs in dein Urteil hinein?

> **Deine Sicht:**

---

## C. Pferd

### C1 Alter und Geschlecht · Blatt ✅

- **Skill heute:** `G-STUTE` [leicht] bei jungen Pferden, `F-WALLACH`, `G-EXPOSED-ALT` (7–8 Jahre).
- **Offen:** Stuten im Herbst / in Stutenrennen? Erster Start als Wallach – Plus oder Fragezeichen?

> **Deine Sicht:**

### C2 Starts, Siege, Plätze · Blatt ✅

- **Skill heute:** Exposure relativ zum Alter, `P-UNEXPOSED`, `G-SELTEN-SIEG` (unter einem Sieg je etwa 14 Starts).
- **Offen:** passt 1:14? „Ewiger Zweiter“ anders als seltener Sieger mit wenigen Plätzen?

> **Deine Sicht:**

### C3 Gewinnsumme und Gewinn je Lauf (Karriere, 365 Tage, Rang im Feld) · Blatt ❌

- **Karte:** Karriere und letzte 365 Tage: Läufe-Siege-Plätze, Gewinn, Gewinn je Lauf mit Rang im Feld und
  Verhältnis zum Feld.
- **Skill heute:** nichts – Klasse wird nur über Valeur und ARR gelesen.
- **Offen:** Ist der Gewinn je Lauf für dich ein Klassenmaß? Zählt der Rang im Feld?

> **Deine Sicht:**

### C4 Gewicht · Blatt ✅

- **Skill heute:** nur `G-GEWICHT-BODEN` (ab etwa 62 kg auf Très souple oder schwerer) und
  `G-GEWICHT-KLASSE-BODEN` [ausschlaggebend].
- **Offen:** Gewichtsänderung gegen den letzten Lauf; Gewichtserlaubnis von Nachwuchsjockeys; Gewicht auf schnellem
  Boden oder kurzer Distanz.

> **Deine Sicht:**

### C5 Marke (Handicap) und Valeur bereinigt (sonst) · Blatt ✅

- **Skill heute:** `P-MARKE-UNTER` („deutlich“), `G-UEBER-SIEGMARKE` [gewichtig], `F-AUFGEWICHT`;
  `P-VALEUR-HOECHSTE`. Die Karte färbt heute − damals je Formzeile ab ±1,5 und ±3.
- **Offen:** Ab wie viel kg ist „deutlich“? Sieg- oder Platzmarke, welche zählt mehr?

> **Deine Sicht:**

### C6 Box · Blatt ✅

- **Skill heute:** nur signifikante Abweichung zählt (`G-BOX` [gewichtig], `P-BOX` [leicht]).
- **Offen:** Box je nach Distanz und Bahn (kurzer Weg zur ersten Kurve)?

> **Deine Sicht:**

### C7 Laufstil (Stil, früh Ø %) · Blatt ◐ (Stil ✅, früh Ø % ❌)

- **Skill heute:** nur im Zusammenspiel mit dem Tempo (A10).

> **Deine Sicht:**

### C8 Pause und Startfolge · Blatt ✅

- **Skill heute:** `F-PAUSE` „lange Pause“ **ohne Schwelle** (die Karte färbt Pausen ab 60 Tagen rot);
  `G-STARTFOLGE` ab etwa 4 Starts in 6 Wochen.
- **Offen:** Ab wie vielen Tagen ist eine Pause lang – je Alter oder Trainer anders? Ist ein Start nach 7–14 Tagen
  ein Plus?

> **Deine Sicht:**

### C9 CGD und Badges · Blatt ✅

- **Bedeutung:** CGD je Buchstabe Bahn (C), Boden (G), Distanzgruppe (D): groß = gewonnen, klein = platziert.
  Badges: C = Bahnsieg, D = Distanzsieg (±100 m), CD = beides im selben Lauf, BF = im letzten Lauf als Favorit
  geschlagen.
- **Skill heute:** `P-CGD` [gewichtig]; Badges **nicht verwendet**.
- **Offen:** Großbuchstabe deutlich mehr wert als klein? Welcher Buchstabe wiegt am meisten? Ist „BF“ ein Signal?

> **Deine Sicht:**

### C10 Ausrüstung und Ausrüstungswechsel · Blatt ✅

- **Skill heute:** ausführlich nach den Bilanzen mit und ohne (`G-AUSRUESTUNG-WEG` [ausschlaggebend],
  `P-AUSRUESTUNG-ZURUECK` [gewichtig], `F-AUSRUESTUNG-NEU`).

> **Deine Sicht:**

### C11 Fehlende Läufe · Blatt ❌

- **Karte:** Hinweis, wie viele Läufe in der Historie fehlen.
- **Skill heute:** „eine fehlende Angabe ist eine Lücke, kein Negativbefund“ (`DATEN.md`).

> **Deine Sicht:**

---

## D. Vorlieben und Abstammung

### D1 Vorlieben des Pferdes (Boden, Distanz, Bahn, Layout, Richtung, Ausrüstung, Trainer) · Blatt ◐

- **Blatt:** Boden ganz, Distanz/Bahn/Richtung nur die heutige Gruppe, Ausrüstung ✅; Layout ❌; Signifikanz (✱,
  „eigener Schnitt“) ❌; Sieg-A/E (`ae_win`) ❌.
- **Skill heute:** immer aus den Vorlieben lesen, nicht aus den Formzeilen; Boden ausführlich, Distanz nur
  `G-DISTANZ-PROBLEME`.
- **Offen:** Ab wie vielen Läufen belastbar? Ab welchem A/E gut bzw. schlecht? Platz-A/E oder Sieg-A/E?

> **Deine Sicht:**

### D2 Abstammungs-Passung (Gesamtwert, Skalen Boden, Distanz, Belag, Reife) · Blatt ✅

- **Karte zusätzlich ❌:** Perzentil je Skala gegen alle Linien, Passung je früherem Lauf.
- **Skill heute:** nur wo eigene Erfahrung fehlt. `G-ABSTAMMUNG` [ausschlaggebend] ab etwa −15,
  `F-ABSTAMMUNG-LEICHT` um −9; Vater zählt mehr; Frankels und sehr weicher Boden.
- **Offen:** Skala Reife? Skala Distanz bei Distanzwechsel (A3)? Weitere Hengste mit Eigenheiten?

> **Deine Sicht:**

### D3 Nachkommen-Statistik (Vater, Muttervater, Cross) · Blatt ◐ (Valeur- und Gewinn-Index ✅, Rest ❌)

- **Karte:** je Vater, Muttervater und **Cross** (Vater × Muttervater): Pferde, A/E, Platzierungs-Index,
  Gewinn-Index, Valeur-Index; Bilanzen der Nachkommen nach Alter, Distanz, Boden.
- **Skill heute:** Qualität der Linie bei jungen Pferden, **ohne Schwellen**; Cross unbenutzt.
- **Offen:** Ab welchem Index ist eine Linie stark bzw. schwach? Zählt der Cross?

> **Deine Sicht:**

---

## E. Verbindungen

### E1 Trainer (Form 30/90/365 Tage, Trend, Bahn, Rennart, Alter, Wechsel) · Blatt ◐ (30 Tage ✅, 90/365 und Sieg-A/E ❌)

- **Skill heute:** `G-TRAINER-KALT` [gewichtig] (etwa 2/40, A/E um 0,5), `P-TRAINER`, `G-STALL-KLEIN`,
  `G-TRAINER-SPEZIALITAET`, `F-TRAINERWECHSEL`, `P-NEUER-TRAINER` [vorläufig], `G-DEBUET-STALL` [ausschlaggebend],
  `P-BRITE`.
- **Offen:** 30 Tage oder 90 Tage als Formmaß? Trainer, die du namentlich kennst?

> **Deine Sicht:**

### E2 Jockey (Form 30/90/365, Bahn, Pferd, Layout, Richtung, Feldgröße) · Blatt ◐ (365 Tage, Bahn, Pferd ✅; Rest ❌)

- **Skill heute:** `P-JOCKEY-KENNT` [leicht], Jockey-A/E über 1 = Pro.
- **Offen:** Jockeywechsel zum Spitzenjockey als Signal? Jockey-Form 30 Tage? Nachwuchsjockeys mit Erlaubnis?

> **Deine Sicht:**

### E3 Matrix Trainer × Jockey (Gespann) · Blatt ◐ (Jockey für Trainer ✅, Trainer mit Jockey ❌)

- **Karte:** beide Richtungen, zwei Jahre, mit Signifikanz, und die A/E-Übersicht je Rolle mit Zeitfenstern.
- **Skill heute:** `P-GESPANN` [gewichtig] – zählt bei genug Starts mehr als die Einzelbilanzen.
- **Offen:** Ab wie vielen gemeinsamen Starts zählt das Gespann? Welche Richtung schaust du an?

> **Deine Sicht:**

### E4 Besitzer und Züchter (A/E, Trend) · Blatt ❌

- **Skill heute:** nichts.
- **Offen:** Spielen Besitzer (z. B. große Ställe, Wechsel des Besitzers) oder Züchter für dich eine Rolle?

> **Deine Sicht:**

---

## F. Ratings und Vergleich im Feld

### F1 ARR (bereinigt, Rang, Ø ± Streuung, Bestwert, letzter) · Blatt ◐ (bereinigt, Rang, Bestwert ✅; Ø, Streuung, letzter ❌)

- **Skill heute:** Kern der Leitfrage: ARR im Referenzlauf gegen Top-ARR und Maßstäbe (`G-ARR-UNTER`
  [ausschlaggebend], `U-ARR-ABSTAND`, `G-MASSSTAB-BESSER`).
- **Offen:** Zählt eine große Streuung (unbeständig) gegen das Pferd?

> **Deine Sicht:**

### F2 TR und RTR (heute, Ø, Bestwert, Rang) · Blatt ◐ (nur Rang)

- **Karte:** TR = Zeit-Rating aus dem Tracking plus Upgrade, aufs heutige Gewicht; RTR = Rating-Leistung aufs
  heutige Gewicht.
- **Skill heute:** **nicht verwendet**.
- **Offen:** Sollen TR/RTR neben ARR zählen – etwa als Bestätigung, wenn ARR und TR übereinstimmen?

> **Deine Sicht:**

### F3 Schlussspeed: ΔL600 und ΔB200 (Ø, Rang im Feld) · Blatt ❌

- **Karte:** Tempo der letzten 600 m und schnellstes 200-m-Segment gegen Erwartung (km/h), Ø über die Läufe, Rang im
  Feld.
- **Skill heute:** nichts.
- **Offen:** Ist ein starker Schlussspeed für dich ein Pro-Argument – auf welchen Distanzen, bei welchem Tempo?

> **Deine Sicht:**

### F4 Duelle direkt und indirekt · Blatt ◐ (Score und Rang ✅, Einzelduelle ❌)

- **Karte:** je heutigem Gegner direkte Duelle (180 Tage, ±200 m) mit Gewichtsverschiebung und erwartetem Abstand
  heute; indirekte über gemeinsame Gegner.
- **Skill heute:** `G-DIREKT-HINTER`, `P-GEGNER-GESCHLAGEN` [gewichtig]; der Duell-Score selbst ist ungenutzt.
- **Offen:** Wie viel ist ein direktes Duell mit Gewichtsverschiebung wert? Indirekte Duelle überhaupt?

> **Deine Sicht:**

---

## G. Formzeilen (je früherem Lauf)

### G1 Platz, Abstand, Feldgröße · Blatt ✅

- **Skill heute:** Abstand vor Platzierung; `G-LETZTER-HEUTE-BODEN` ab 5 Längen; „ausgeritten?“ ab 10 Längen (zählt
  nicht in den Schnitt).
- **Offen:** Ab wie vielen Längen „nah dran“? Umgang mit Läufen über 10 Längen?

> **Deine Sicht:**

### G2 Position im Rennen: früh und 400 m vor dem Ziel, Fünftel des Feldes · Blatt ❌

- **Karte:** frühe Position → Position 400 m vor dem Ziel, als „Wagen“ (Fünftel des Feldes), dazu die Wagen der
  ersten drei im Ziel.
- **Skill heute:** nichts – nur Laufstil und Rennverlauf (G6).
- **Offen:** Was liest du daraus (z. B. „von hinten aus dem 5. Wagen noch Dritter“)?

> **Deine Sicht:**

### G3 Plätze gutgemacht ab 800 m, Weg gegen den Median · Blatt ❌

- **Karte:** Plätze gut- oder verlorengemacht ab 800 m vor dem Ziel (auffällig ab ±3) und Weg in Metern mehr oder
  weniger als der Median (≈ Längen; auffällig ab 7,5 m, also außen herum gelaufen).
- **Skill heute:** nichts; „am Rand galoppiert“ nur über den Kommentar.
- **Offen:** Wie viel ist ein langer Weg wert – rechnest du ihn in Längen auf den Abstand an?

> **Deine Sicht:**

### G4 Tempo im Lauf (Pace) und Finish-Index · Blatt ❌

- **Karte:** Pace = Tempo früh ÷ Tempo Schluss (schnell früh / gleichmäßig / langsam früh); Finish-Index = Endspeed
  ÷ Tempo davor, bereinigt und als Stufe (very weak … very strong) gegen alle Läufe der heutigen Starter.
- **Skill heute:** nichts.
- **Offen:** Hebt ein starker Finish-Index nach schnellem Tempo einen Lauf auf? Wie stark?

> **Deine Sicht:**

### G5 Zeit-Rating des Laufs (TR) und ARR des Laufs mit Rang · Blatt ◐ (ARR ✅, TR je Lauf ❌, Rang unter den Läufen der Starter ❌)

- **Skill heute:** ARR im Referenzlauf ist zentral; TR je Lauf ungenutzt.

> **Deine Sicht:**

### G6 Rennverlauf, Zwischenfall · Blatt ✅ (Verlaufswert als Zahl ❌)

- **Skill heute:** `P-GEGEN-VERLAUF` [gewichtig], `P-GESTOERT`, `G-SIEG-MIT-VERLAUF`.

> **Deine Sicht:**

### G7 Gegner des Laufs: aufgewertet/abgewertet, Sieger, wie die Gegner danach liefen · Blatt ◐ (Zählung ✅, Namen und „danach“ ❌)

- **Karte:** je Gegner Abstand, Platz und nächster Lauf (Platz, Quote, Urteil); daraus aufgewertet/abgewertet;
  Sieger des Laufs.
- **Skill heute:** aufgewertet hebt den Referenzlauf; `P-ABSTIEG` nur bei nicht abgewerteten Rennen.
- **Offen:** Zählt für dich, *wer* danach gewonnen hat (z. B. der Sieger gewann danach ein Listed)?

> **Deine Sicht:**

### G8 Klassenindex des Laufs (Valeur- und Gewinn-Index) · Blatt ◐ (Valeur-Index ✅)

> **Deine Sicht:**

### G9 Quote, Favorit, Quotenrang im damaligen Lauf · Blatt ◐ (Quote ✅, Favorit und Rang ❌)

- **Skill heute:** nicht verwendet.
- **Offen:** Sagt dir ein geschlagener Favorit oder ein knapp geschlagener Außenseiter etwas?

> **Deine Sicht:**

### G10 Jockey, Box, Gewicht, Ausrüstung, Preisgeld je Lauf · Blatt ◐ (Gewicht, Ausrüstung ✅; Jockey, Box, Preisgeld ❌)

> **Deine Sicht:**

### G11 Rennkommentar · Blatt ✅ (seit 21.11.)

- **Skill heute:** gestörte Läufe aus dem Kommentar höher einordnen.
- **Offen:** Formulierungen, die für dich ein klares Signal sind („a fini fort“, „sans être inquiété“)?

> **Deine Sicht:**

### G12 Ältere Läufe mit gleicher Bahn, Distanz oder Boden · Blatt ✅ (seit 21.11.)

- **Karte und Blatt:** nach den letzten sieben Läufen der letzte ältere Lauf mit gleicher Bahn, Distanz bzw. Boden.
- **Offen:** Wie alt darf ein Referenzlauf sein, bis er nicht mehr zählt?

> **Deine Sicht:**

### G13 Externe und ausländische Läufe · Blatt ✅

- **Skill heute:** `F-AUSLAND`, Lücke statt Negativbefund; `G-MODELL-UNSICHER` [vorläufig].

> **Deine Sicht:**

---

## H. Was in der Karte fehlt

Angaben, die du beim Urteil nutzt, die aber weder Karte noch Blatt zeigen (bekannt: Tagesquoten bewusst nicht im
Modell).

> **Deine Sicht:**
