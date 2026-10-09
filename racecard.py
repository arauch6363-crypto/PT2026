"""
Interaktive Race Card (Racing-Post-/Timeform-Stil) für die heutigen Rennen.

    python racecard.py --base <DRIVE-ORDNER> [--datum 2026-09-23] [--out racecard.html]

oder im Notebook:

    import racecard
    racecard.run(BASE)                       # schreibt <BASE>/racecards/racecard_<JJJJMMTT>.html

Ablauf:
    1. PMU-Programm des Tages holen: französische Flachrennen, auch die noch nicht gelaufenen
    2. Historie aus den Parquet-Tabellen laden (pmu_races / pmu_runners / tracking_*)
    3. je Starter: letzte Läufe (Formzeilen mit Tracking-Kennzahlen), A/E von Trainer,
       Jockey und Vater (90 / 365 Tage) und Vorlieben unter den heutigen Bedingungen
    4. alles als JSON in racecard_template.html einsetzen -> eine eigenständige HTML-Datei

Kennzahlen
    A/E            Siege / Summe(1 / Endquote)  – über 1: gewinnt öfter, als der Markt erwartet.
                   Übersicht: 365 Tage, Feuer/Eis, wenn die letzten 30 Tage deutlich besser/schlechter waren
    Position vor dem Finish
                   Platz im Feld am Messpunkt POS_VOR_FINISH_M vor dem Ziel, als Fünftel
                   des Feldes (1 = vorderstes Fünftel)
    ΔL600 A/ΔB200 A Tempo letzte 600 m / schnellstes 200-m-Segment der letzten 800 m gegen die Erwartung
                   (tempo_delta.py, km/h): verglichen innerhalb Tag × Kurs × Going (offizieller Bodenbegriff),
                   korrigiert um Kurs × Distanz und Pace-Ratio, dazu die Klassenkorrektur der Gruppe
                   (β · (Ø Klasse der Gruppe − Ø Klasse gesamt), β aus Altersklasse und Preisgeld). Übersicht:
                   nach Distanz und Going gewichteter, zum Nullpunkt geschrumpfter Ø der letzten
                   SCHNITT_LAEUFE Läufe mit Tracking.
    TR             Zeit-Rating nach Timeform-Art (timeform_ratings.py, lb, bezogen auf 55 kg) plus Upgrade aus
                   dem Finishing Speed. Übersicht: nach Distanz- und Going-Ähnlichkeit gewichteter Ø der letzten
                   SCHNITT_LAEUFE Läufe mit TR (ohne gedeckelte), auf das heutige Gewicht umgerechnet
    Finish-Index   bereinigt nach dem Modell in speedfig.py (Rennanteil gegen Par, plus Pferdeanteil)
    RTR / ARR      Ratings aus PT_Vorarbeiten (rtr_arr.py), in kg: RTR = Elo-artiges Rating nach dem Rennen,
                   ARR = Leistung im Rennen, gemessen an den Pferden im vorderen Drittel. Bereinigt nach
                   Gewicht: x_adj = x − heutiges Gewicht + GEWICHT_REF – in der Übersicht (ARR: nach Distanz
                   und Going gewichteter Ø der letzten SCHNITT_LAEUFE Läufe, RTR: aktuell) und in den
                   Formzeilen (ein früherer ARR von 36 bei heute 52 kg -> 39)
"""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import pmu
import rtr_arr
import speedfig
import standardzeiten
import tempo_delta
import timeform_ratings
import uebersetzen

TEMPLATE = Path(__file__).with_name("racecard_template.html")

POS_VOR_FINISH_M = 400          # Messpunkt für "Position vor dem Finish"
LETZTE_LAEUFE = 7               # so viele Formzeilen je Pferd
AE_FENSTER = (30, 90, 365)      # Tage
TREND_DIFF = 0.25               # A/E Platz 30 Tage so viel über/unter 365 Tagen -> Feuer/Eis
TREND_MIN_STARTS = 5            # so viele Starts in 30 Tagen braucht der Trend
VORLIEBEN_JT_TAGE = 730         # Jockey-/Trainer-Vorlieben: letzte zwei Jahre
GEGNER_LAEUFE = LETZTE_LAEUFE   # für so viele der letzten Läufe werden die Gegner verfolgt (alle Gegner je Lauf)
# A/E Platz: Platz = 1.–2. bei bis zu PLATZ_GRENZE Startern, sonst 1.–3.; erwartet nach Harville mit Korrektur
PLATZ_GRENZE = 7
HARVILLE_L2, HARVILLE_L3 = 0.8, 0.65   # Stauchung p^λ für Platz 2 und 3 (Lo / Bacon-Shone)
POP_MIN_LAEUFE = 5              # Population für €/L+: nur Personen/Linien mit so vielen Läufen
POP_MIN_PFERDE = 3              # Population für max Val+: nur Linien mit so vielen 3-jährigen Nachkommen
KLASSE_TAGE = 365               # Klasse: Ø Gewinnsumme je Lauf der Teilnehmer in so vielen Tagen davor
# Nur Basis des Index €/L+ (Rennstärke): eigenes €/L, sobald der erste Start so viele Tage zurückliegt; davor das
# gewichtete €/L der Verbindungen (je KLASSE_TAGE davor, ab KLASSE_VERB_MIN Läufen). Gemittelt wird log(1 + €/L).
# Angezeigte Beträge (€/L) bleiben das einfache Ø der Pferde mit Läufen in den KLASSE_TAGE.
KLASSE_ERFAHREN_TAGE = 365
KLASSE_VERBINDUNG = {"trainer": 0.5, "owner": 0.3, "breeder": 0.2}
KLASSE_VERB_MIN = 5
INDIREKT_TAGE = 120             # indirekte Duelle: Vergleichsrennen höchstens so alt (für beide Seiten)
INDIREKT_DIST_M = 200           # … Distanz höchstens so weit auseinander
INDIREKT_REL_MIN = 0.5          # … alle drei Pferde in der vorderen Hälfte: rel. Platzierung > 0,5
DUELL_TAGE = 120                # Heutige Gegner · frühere Duelle, eingeschränkt wie die indirekten: nur Rennen der
DUELL_DIST_M = 200              # letzten DUELL_TAGE, Distanz höchstens DUELL_DIST_M von heute, Boden innerhalb einer
DUELL_BODEN = True              # Stufe (DUELL_BODEN); anders als dort zählen alle Platzierungen
BOX_SD = 0.289                  # Streuung der relativen Platzierung bei Zufall (Gleichverteilung 0…1)
BOX_Z = 2.0                     # Startbox auffällig: |Ø − 0,5| mindestens BOX_Z Standardfehler …
BOX_MIN_ABW = 0.05              # … und mindestens so weit von 0,5 entfernt
BOX_MIN_LAEUFE = 15             # Startbox-Abweichung: ab so vielen Läufen aus der Box auf der Konfiguration farbig
AE_Z = 2.0                      # Vorlieben auffällig: A/E mindestens AE_Z Standardfehler vom Rest der Person/Linie …
AE_MIN_ABW = 0.20               # … und mindestens ×1,2 bzw. ×0,8 davon entfernt
AE_MIN_REST = 20                # … bei mindestens so vielen Läufen im Rest (Maßstab)
# Preisgeld je Platz: PMU montantOffert1er … 5eme, sonst die übliche Aufteilung des Rennpreises (France Galop)
PREIS_SPALTEN = ["c_montantOffert1er", "c_montantOffert2eme", "c_montantOffert3eme", "c_montantOffert4eme",
                 "c_montantOffert5eme"]
PREIS_ANTEILE = [0.50, 0.19, 0.14, 0.09, 0.04]
SCHNITT_LAEUFE = 5              # Ø der bereinigten Kennzahlen über so viele Läufe mit Tracking
SCHNITT_PRIOR = 1.0             # Schrumpfung zum Nullpunkt: wirkt wie ein zusätzlicher Lauf mit Wert 0
SCHNITT_DIST_M = 400            # Gewicht eines Laufs = 1 / (1 + |Distanz − heute| / SCHNITT_DIST_M)
# TR-Kachel: gewichteter Ø der letzten SCHNITT_LAEUFE Läufe mit TR, Gewicht = Distanz × Going
GOING_STUFE = {"VERY FAST": 0, "FAST": 1, "SLOW": 2, "VERY SLOW": 3}     # Bodengruppen (rtr_arr.GOING_MAP)
SCHNITT_GOING_STUFEN = 1        # Going-Gewicht = 1 / (1 + |Gruppen Abstand| / SCHNITT_GOING_STUFEN)
GOING_PSF_GRAS = 0.25           # Going-Gewicht zwischen PSF und Gras
# Übersicht: Ø dieser Δ-Kennzahlen (tempo_delta, km/h) über die letzten SCHNITT_LAEUFE Läufe mit Tracking
DELTA_SPALTEN = {"dl600_a": "d_L600_A", "db200_a": "d_B200_A"}
GEWICHT_REF = 55                # x_adj = x − Gewicht (kg) + GEWICHT_REF
MIN_GRUPPE = 30                 # so viele Läufe braucht eine Gruppe, bevor ihr Effekt zählt

DIST_BINS = [0, 1300, 1700, 2100, 2600, 5000]
DIST_LABELS = ["sprint", "mile", "inter", "long", "stayer"]
DIST_LABEL = {"sprint": "bis 1300 m", "mile": "1301–1700 m", "inter": "1701–2100 m",
              "long": "2101–2600 m", "stayer": "über 2600 m"}

KATEGORIE = {
    "COURSE_A_CONDITIONS": "Conditions", "A_RECLAMER": "Claimer", "A_CONDITIONS": "Conditions",
    "HANDICAP": "Handicap", "HANDICAP_DIVISE": "Handicap", "HANDICAP_CATEGORIE": "Handicap",
    "HANDICAP_DE_CATEGORIE": "Handicap", "GROUPE_I": "Group 1", "GROUPE_II": "Group 2",
    "GROUPE_III": "Group 3", "LISTED": "Listed", "LISTE": "Listed", "COURSE_INTERNATIONALE": "International",
    "APPRENTIS_LADS_JOCKEYS": "Apprentice", "AMATEURS": "Amateur",
}

# Plausibilitätsgrenzen – Werte außerhalb sind Mess- oder Parserfehler
PLAUSIBEL = {"speed_last600_kmh": (40.0, 75.0), "speed_600_400_kmh": (40.0, 75.0),
             "speed_last400_kmh": (40.0, 75.0), "finish_index": (70.0, 130.0),
             "pos_gain_800_finish": (-20, 20), "pace_ratio": (60.0, 160.0), "pace_early_kmh": (40.0, 75.0),
             "dist_vs_winner_m": (-60.0, 100.0)}

# Laufstil: mittlere frühe Position als Anteil des Feldes (0 = an der Spitze, 1 = Letzter)
STIL_LAEUFE = 5                 # so viele Läufe mit Tracking bestimmen den Laufstil
STIL = [(0.20, "F", "Führend"), (0.40, "V", "Vorne dabei"), (0.65, "M", "Mittelfeld"), (1.01, "H", "Hinten")]
TEMPOMACHER = 0.20              # bis zu dieser frühen Position zählt ein Pferd als Tempomacher
BIAS_VORNE, BIAS_HINTEN = 1 / 3, 2 / 3   # frühe Position: vorderes / hinteres Drittel
MIN_BIAS_RENNEN = 15            # so viele Rennen braucht eine Bahn/Distanz für den Bias
PACE_SCHWELLE = 1.0             # erwartete Pace-Ratio so weit über/unter der Norm -> schnell/langsam
PACE_FELD_REF = 10              # Feldgröße, auf die sich der Starter-Effekt bezieht

PACE_BINS = [0, 94, 97, 100, 103, 999]
PACE_LABELS = ["< 94", "94–97", "97–100", "100–103", "> 103"]


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------
def norm_name(s: pd.Series) -> pd.Series:
    s = s.astype("string").str.upper().str.strip()
    s = s.str.replace(r"\s*\(S\)\s*$", "", regex=True)
    s = s.str.replace(r"\.\s+", ".", regex=True)
    return s.str.replace(r"\s+", " ", regex=True)


def to_float(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype("string").str.replace(",", ".", regex=False).str.strip(), errors="coerce")


def _num(x, nd=2):
    """JSON-taugliche Zahl oder None."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return int(round(f)) if nd == 0 else round(f, nd)


def _txt(x):
    if x is None or (isinstance(x, float) and math.isnan(x)) or x is pd.NA:
        return None
    s = str(x).strip()
    return s or None


def kategorie(c) -> str | None:
    c = _txt(c)
    if not c:
        return None
    c = c.upper()
    return KATEGORIE.get(c) or c.replace("_", " ").title()


BODEN_ANNAHME = "FAST"          # fehlt die Bodenangabe (noch), gilt der Tag als FAST (Bon, Bon souple)


def going_klasse(going, going_value=None) -> str:
    """Bodengruppe nach rtr_arr.GOING_MAP (VERY FAST, FAST, SLOW, VERY SLOW, PSF) aus dem offiziellen
    Bodenbegriff; fehlt er (oder ist unbekannt): BODEN_ANNAHME. Der Penetrometer-Wert (going_value) fließt nicht
    ein – alle Berechnungen nutzen nur die Gruppe."""
    return rtr_arr.boden_gruppe(going) or BODEN_ANNAHME


BODEN_DATEI = Path(__file__).with_name("boden_manuell.json")   # im Repo, auf GitHub editierbar
PSF_MERKMALE = {"PSF", "FIBRE", "FIBREE", "POLYTRACK", "VISCORIDE"}   # ganze Wörter


def ist_psf(r) -> bool:
    """PSF-Rennen nach PMU-Bahnart (typePiste) oder Parcours-Text."""
    t = " ".join(str(r.get(k) or "") for k in ("track_type", "parcours"))
    return bool(PSF_MERKMALE & set(rtr_arr._norm_boden(t).split()))


def boden_manuell_laden(datei: Path | None = None, tag: date | None = None) -> dict[str, str]:
    """Manuelle Bodenangaben {Bahn (pmu.norm): Bodenbegriff} aus boden_manuell.json. Nur gültige Gras-Begriffe
    nach rtr_arr.GOING_MAP; Tippfehler, PSF-Angaben und eine nicht passende 'datum'-Angabe werden gemeldet und
    übergangen. Fehlt die Datei oder ist sie kaputt: {} (dann gilt wie bisher die Annahme)."""
    f = Path(datei) if datei else BODEN_DATEI
    if not f.exists():
        return {}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"Boden manuell: {f.name} nicht lesbar ({e}) – nicht verwendet.")
        return {}
    datum = str(d.get("datum") or "").strip()
    if datum and tag is not None:
        try:
            gilt = pd.to_datetime(datum, dayfirst=not datum[:4].isdigit()).date()
        except (ValueError, TypeError):
            print(f"Boden manuell: Datum {datum!r} unverständlich – Angaben nicht verwendet.")
            return {}
        if gilt != tag:
            print(f"Boden manuell: Angaben gelten für {gilt}, Rennkarte ist für {tag} – nicht verwendet.")
            return {}
    out = {}
    for bahn, wert in (d.get("bahnen") or {}).items():
        w = str(wert or "").strip()
        if not w:
            continue
        g = rtr_arr._MAP_NORM.get(rtr_arr._norm_boden(w))      # streng: nur Begriffe aus GOING_MAP
        if g is None or g == "PSF":
            print(f"Boden manuell: {bahn}: {w!r} ist keine gültige Gras-Bodenangabe – übergangen.")
            continue
        out[pmu.norm(bahn)] = w
    return out


def _bahn_eintrag(name, manuell: dict[str, str]) -> str | None:
    """Eintrag zur Bahn: gleicher Name (pmu.norm), sonst eindeutig über die Wörter ('TOULOUSE' passt zu
    'TOULOUSE LA CEPIERE'); passt ein Eintrag auf mehrere Schreibweisen oder keiner: None."""
    n = pmu.norm(name or "")
    if n in manuell:
        return manuell[n]
    w = set(n.split())
    treffer = [k for k in manuell if w and (set(k.split()) <= w or w <= set(k.split()))]
    return manuell[treffer[0]] if len(treffer) == 1 else None


def boden_manuell_anwenden(races: pd.DataFrame, manuell: dict[str, str]) -> pd.DataFrame:
    """Bodenangabe der heutigen Rennen ergänzen, nur wo PMU (noch) keine gültige liefert:
    PSF-Rennen -> 'PSF'; Gras-Rennen -> manueller Eintrag der Bahn; sonst bleibt es bei der Annahme.
    Spalte going_quelle: PMU, manuell, PSF oder Annahme."""
    r = races.copy()
    if "going" not in r:
        r["going"] = None
    r["going"] = r["going"].astype(object)
    quelle, ohne = [], set()
    for i, z in r.iterrows():
        if rtr_arr.boden_gruppe(z.get("going")) is not None:
            quelle.append("PMU")
        elif ist_psf(z):
            r.at[i, "going"] = "PSF"
            quelle.append("PSF")
        elif _bahn_eintrag(z.get("hippodrome"), manuell):
            r.at[i, "going"] = _bahn_eintrag(z.get("hippodrome"), manuell)
            quelle.append("manuell")
        else:
            quelle.append("Annahme")
            ohne.add(str(z.get("hippodrome")))
    r["going_quelle"] = quelle
    n = pd.Series(quelle).value_counts()
    print("Boden heute: " + ", ".join(f"{k} {v}" for k, v in n.items())
          + (f" – ohne Eintrag in {BODEN_DATEI.name}: {', '.join(sorted(ohne))}" if ohne else ""))
    for (bahn, q), g in r.groupby(["hippodrome", "going_quelle"], sort=True):
        if q == "manuell":
            print(f"  {bahn}: manuell {g['going'].iloc[0]!r} ({len(g)} Rennen)")
    return r


def going_anzeige(k: str | None) -> str | None:
    """'VERY SLOW' -> 'Very slow'"""
    if not k:
        return None
    return "PSF" if k == "PSF" else k.capitalize()


def pace_klasse(p) -> str | None:
    p = _num(p)
    if p is None:
        return None
    for lo, hi, lab in zip(PACE_BINS[:-1], PACE_BINS[1:], PACE_LABELS):
        if lo <= p < hi:
            return lab
    return None


def dist_bucket(d) -> str | None:
    d = _num(d)
    if d is None:
        return None
    for lo, hi, lab in zip(DIST_BINS[:-1], DIST_BINS[1:], DIST_LABELS):
        if lo < d <= hi:
            return lab
    return None


def age_bucket(a) -> str | None:
    a = _num(a)
    return None if a is None else ("5+" if a >= 5 else str(int(a)))


def alter_gruppe(a) -> str | None:
    """Altersgruppe für die Trainer-Vorliebe: 2j, 3j, 4j+."""
    a = _num(a)
    return None if a is None or a < 2 else ("4j+" if a >= 4 else f"{int(a)}j")


def abstammung_keys(df: pd.DataFrame) -> pd.DataFrame:
    """sire_key, dam_sire_key und cross_key (Vater × Muttervater). Muttervater aus dam_sire (Programm)
    oder p_nomPereMere (pmu_basis)."""
    df = df.copy()
    ds = df["dam_sire"] if "dam_sire" in df else pd.Series(None, index=df.index, dtype=object)
    if "p_nomPereMere" in df:
        ds = ds.where(ds.notna() & (ds.astype("string").str.strip() != ""), df["p_nomPereMere"])
    df["dam_sire"] = ds
    for c in ["sire", "dam_sire"]:
        df[c + "_key"] = norm_name(df[c]) if c in df else pd.Series(pd.NA, index=df.index, dtype="string")
        df.loc[df[c + "_key"].fillna("").isin(["", "NAN", "NONE"]), c + "_key"] = pd.NA
    df["cross_key"] = (df["sire_key"] + " × " + df["dam_sire_key"]).astype("string")
    return df


def konfig_schluessel(r: pd.DataFrame) -> pd.Series:
    """Konfiguration wie bei den Standardzeiten: Bahn | Distanz | track_type | parcours_norm | Corde."""
    idx = r.index
    pn = r["parcours_norm"] if "parcours_norm" in r else pd.Series(None, index=idx, dtype=object)
    roh = r["parcours"] if "parcours" in r else pd.Series(None, index=idx, dtype=object)
    x = pd.DataFrame({
        "bahn": [pmu.norm(h or "") or h for h in r["hippodrome"]],
        "distance_m": pd.to_numeric(r["distance_m"], errors="coerce"),
        "piste": r["track_type"] if "track_type" in r else pd.Series(None, index=idx, dtype=object),
        "parcours_n": [p if isinstance(p, str) else standardzeiten.parcours_norm(q) for p, q in zip(pn, roh)],
        "corde": r["corde"] if "corde" in r else pd.Series(None, index=idx, dtype=object),
    }, index=idx)
    return standardzeiten.konfiguration(x)


def konfig_angleichen(heute: pd.Series, hist_konfig: pd.Series) -> pd.Series:
    """Fehlt heute die Bahnart (Piste '?'), den Schlüssel der häufigsten Konfiguration der Historie mit gleicher
    Bahn, Distanz, Parcours und Corde übernehmen – sonst passt er nur zu wenigen alten Rennen ohne Bahnart."""
    zahl = hist_konfig.dropna().value_counts()
    teile = {k: k.split("|") for k in zahl.index if isinstance(k, str) and k.count("|") == 4}

    def passend(k):
        if not isinstance(k, str) or k.count("|") != 4:
            return k
        b, dist, piste, parc, corde = k.split("|")
        if piste != "?":
            return k
        kand = [(zahl[h], h) for h, t in teile.items()
                if t[2] != "?" and (t[0], t[1], t[3], t[4]) == (b, dist, parc, corde)]
        return max(kand)[1] if kand else k
    return heute.map(passend)


def harville_platz(p, plaetze: int, l2: float = HARVILLE_L2, l3: float = HARVILLE_L3) -> np.ndarray:
    """Platzwahrscheinlichkeit je Starter aus Siegwahrscheinlichkeiten p (Harville mit Korrektur):
    P = p_i + Σ_j p_j·q2_i/(1−q2_j) [+ Σ_j Σ_k p_j·q2_k/(1−q2_j)·q3_i/(1−q3_j−q3_k)], q2 ∝ p^l2, q3 ∝ p^l3.
    p wird zuvor auf 1 normiert (Marge heraus); l2 = l3 = 1 ergibt das reine Harville-Modell."""
    p = np.asarray(p, float)
    p = p / p.sum()
    n = len(p)
    if plaetze >= n:
        return np.ones(n)
    q2 = p ** l2
    q2 = q2 / q2.sum()
    A = p[:, None] * q2[None, :] / np.clip(1 - q2[:, None], 1e-12, None)
    np.fill_diagonal(A, 0.0)
    P = p + A.sum(axis=0)
    if plaetze >= 3:
        q3 = p ** l3
        q3 = q3 / q3.sum()
        nenner = 1 - q3[:, None] - q3[None, :]
        B = np.where(nenner > 1e-12, A / np.where(nenner > 1e-12, nenner, 1.0), 0.0)
        np.fill_diagonal(B, 0.0)
        P = P + q3 * (B.sum() - B.sum(axis=1) - B.sum(axis=0))
    return np.clip(P, 0.0, 1.0)


def platz_erwartung(h: pd.DataFrame) -> pd.Series:
    """Erwartete Platzwahrscheinlichkeit je Starter aus den Endquoten seines Rennens (Harville mit Korrektur).
    Marge herausgerechnet über die Starter mit Quote; ohne Quote (oder < 2 Quoten im Rennen) NaN."""
    out = pd.Series(np.nan, index=h.index)
    if h.empty:
        return out
    q = pd.to_numeric(h["odds_final"], errors="coerce")
    ok = q.notna() & (q > 1)
    d = pd.DataFrame({"race": h.loc[ok, "race_id"].astype(str), "p": 1 / q[ok], "n": h.loc[ok, "n_runners"],
                      "pos": np.flatnonzero(ok.to_numpy())}).sort_values("race", kind="stable")
    werte = np.full(len(h), np.nan)
    race, p, n, pos = (d[c].to_numpy() for c in ("race", "p", "n", "pos"))
    grenzen = np.flatnonzero(race[1:] != race[:-1]) + 1
    for a, b in zip(np.r_[0, grenzen], np.r_[grenzen, len(race)]):
        if b - a < 2:
            continue
        n_ = int(n[a]) if not np.isnan(n[a]) else b - a
        werte[pos[a:b]] = harville_platz(p[a:b], 2 if n_ <= PLATZ_GRENZE else 3)
    out[:] = werte
    return out


def preisgeld_je_platz(r: pd.DataFrame) -> pd.DataFrame:
    """pz1 … pz5 je Rennen: Preisgeld für Platz 1 … 5 (PMU montantOffert…, sonst Anteil am Rennpreis)."""
    r = r.copy()
    for i, (sp, anteil) in enumerate(zip(PREIS_SPALTEN, PREIS_ANTEILE), 1):
        offen = pd.to_numeric(r[sp], errors="coerce") if sp in r else pd.Series(np.nan, index=r.index)
        r[f"pz{i}"] = offen.fillna(r["prize_eur"] * anteil)
    return r


def gewinn_vorher(h: pd.DataFrame, tage: int = KLASSE_TAGE) -> pd.DataFrame:
    """Je Lauf: Läufe und gewonnenes Preisgeld des Pferdes in den `tage` Tagen davor (ohne den Lauf selbst)
    -> runs_prev, earn_prev, epr_prev (Gewinn je Lauf); dazu epr_all_prev über alle früheren Läufe."""
    h = h.copy()
    if h.empty:
        for c in ["runs_prev", "earn_prev", "epr_prev", "epr_all_prev"]:
            h[c] = np.nan
        return h
    x = h[["horse_id", "date", "prize_won"]].copy()
    x["_i"] = np.arange(len(x))
    x = x.sort_values(["horse_id", "date"], kind="stable")
    roll = x.set_index("date").groupby("horse_id", sort=False)["prize_won"].rolling(f"{tage}D", closed="left")
    summe, anzahl = roll.sum().to_numpy(), roll.count().to_numpy()
    runs = np.empty(len(x)); earn = np.empty(len(x))
    runs[x["_i"].to_numpy()] = np.nan_to_num(anzahl)
    earn[x["_i"].to_numpy()] = np.nan_to_num(summe)
    h["runs_prev"], h["earn_prev"] = runs, earn
    h["epr_prev"] = (h["earn_prev"] / h["runs_prev"]).where(h["runs_prev"] > 0)
    # alle früheren Läufe (Läufe am selben Tag ausgenommen)
    alle, tag_ = x.groupby("horse_id", sort=False), x.groupby(["horse_id", "date"], sort=False)
    summe_a = alle["prize_won"].cumsum() - tag_["prize_won"].cumsum()
    runs_a = alle.cumcount() - tag_.cumcount()
    epr_a = np.empty(len(x))
    epr_a[x["_i"].to_numpy()] = (summe_a / runs_a.where(runs_a > 0)).to_numpy()
    h["epr_all_prev"] = epr_a
    return h


def epr_vorher(h: pd.DataFrame, schluessel: str, tage: int = KLASSE_TAGE) -> tuple[np.ndarray, np.ndarray]:
    """Je Lauf: Läufe und Gewinn je Lauf der Gruppe `schluessel` (Trainer, Besitzer …) in den `tage` Tagen
    vor dem Renntag (ohne den Renntag selbst)."""
    runs, epr = np.full(len(h), np.nan), np.full(len(h), np.nan)
    if h.empty or schluessel not in h:
        return runs, epr
    x = h[[schluessel, "date", "prize_won"]].copy()
    x["_i"] = np.arange(len(x))
    x = x[x[schluessel].notna()].sort_values([schluessel, "date"], kind="stable")
    if x.empty:
        return runs, epr
    roll = x.set_index("date").groupby(schluessel, sort=False)["prize_won"].rolling(f"{tage}D", closed="left")
    summe, anzahl = np.nan_to_num(roll.sum().to_numpy()), np.nan_to_num(roll.count().to_numpy())
    i = x["_i"].to_numpy()
    runs[i] = anzahl
    epr[i] = np.where(anzahl > 0, summe / np.maximum(anzahl, 1), np.nan)
    return runs, epr


def verbindung_log(runs: dict, epr: dict) -> np.ndarray:
    """Gewichtetes log(1 + €/L) aus Trainer, Besitzer, Züchter (KLASSE_VERBINDUNG); wer weniger als KLASSE_VERB_MIN
    Läufe hat, fällt weg, die übrigen Gewichte werden hochgerechnet."""
    summe = gewicht = 0.0
    for rolle, g in KLASSE_VERBINDUNG.items():
        r_, e_ = np.asarray(runs[rolle], dtype=float), np.asarray(epr[rolle], dtype=float)
        ok = (r_ >= KLASSE_VERB_MIN) & ~np.isnan(e_)
        summe = summe + np.where(ok, g * np.log1p(np.where(ok, e_, 0.0)), 0.0)
        gewicht = gewicht + np.where(ok, g, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(gewicht > 0, summe / np.where(gewicht > 0, gewicht, 1.0), np.nan)


def ist_erfahren(datum, erster_start, beginn, alter) -> np.ndarray:
    """Erster Start mindestens KLASSE_ERFAHREN_TAGE vor dem Rennen. Reicht die Historie dafür nicht zurück
    (Rennen im ersten Jahr der Sammlung), zählt ersatzweise das Alter: ab 4 Jahren erfahren."""
    tage = KLASSE_ERFAHREN_TAGE
    datum, erster_start = pd.to_datetime(pd.Series(datum)), pd.to_datetime(pd.Series(erster_start))
    alter = pd.to_numeric(pd.Series(alter), errors="coerce").to_numpy()
    lang = ((datum - erster_start).dt.days >= tage).to_numpy()
    unbekannt = ((datum - pd.Timestamp(beginn)).dt.days < tage).to_numpy()
    return lang | (unbekannt & (alter >= 4))


def klassen_wert(h: pd.DataFrame) -> pd.DataFrame:
    """Je Lauf der Beitrag des Pferdes zur Basis des Index €/L+, als log(1 + €/L): liegt der erste Start mindestens
    ein Jahr zurück, immer das eigene €/L (KLASSE_TAGE davor; ohne Lauf in dieser Zeit über alle früheren Läufe);
    davor das gewichtete €/L von Trainer 50 %, Besitzer 30 % und Züchter 20 % -> epr_kl, epr_eigen."""
    h = h.copy()
    if h.empty:
        h["epr_kl"], h["epr_eigen"] = np.nan, False
        return h
    erfahren = ist_erfahren(h["date"], h.groupby("horse_id")["date"].transform("min"), h["date"].min(), h["age"])
    runs, epr = {}, {}
    for rolle in KLASSE_VERBINDUNG:
        runs[rolle], epr[rolle] = epr_vorher(h, rolle + "_key")
    eigen = np.log1p(h["epr_prev"].fillna(h["epr_all_prev"]).to_numpy(dtype=float))
    h["epr_eigen"] = erfahren & ~np.isnan(eigen)
    h["epr_kl"] = np.where(h["epr_eigen"], eigen, verbindung_log(runs, epr))
    return h


def epr_aus_log(werte) -> float | None:
    """Ø von log(1 + €/L) zurück in Euro (geometrisches Mittel von 1 + €/L, minus 1)."""
    w = pd.to_numeric(pd.Series(werte, dtype=float), errors="coerce").dropna()
    return float(np.expm1(w.mean())) if len(w) else None


# --------------------------------------------------------------------------
# Historie vorbereiten
# --------------------------------------------------------------------------
def vorbereiten(races: pd.DataFrame, runners: pd.DataFrame, trk_races: pd.DataFrame | None = None,
                trk_runners: pd.DataFrame | None = None, trk_sections: pd.DataFrame | None = None,
                trk_leader: pd.DataFrame | None = None,
                standards: pd.DataFrame | None = None) -> pd.DataFrame:
    """Eine Zeile je Starter und Rennen, mit Renndaten und Tracking-Kennzahlen.
    Die Tempi der Schlussphase und der Finish-Index werden aus tracking_sections neu gebildet
    (speedfig.rohwerte_aus_abschnitten); die geparsten Spalten dienen nur als Ersatz."""
    if races.empty or runners.empty:
        return pd.DataFrame()
    r = races.drop_duplicates("race_id", keep="last").copy()
    r["date"] = pd.to_datetime(r["race_id"].astype(str).str[:8], format="%Y%m%d", errors="coerce")
    r["distance_m"] = pd.to_numeric(r["distance_m"], errors="coerce")
    r["prize_eur"] = pd.to_numeric(r.get("prize_eur"), errors="coerce")
    r["going_value"] = to_float(r["going_value"]) if "going_value" in r else np.nan
    # Boden: nur die Bodengruppe des offiziellen Begriffs (rtr_arr.GOING_MAP), nicht der Penetrometer-Wert
    r["going_pmu"] = [going_klasse(g) for g in r.get("going", pd.Series(None, index=r.index))]
    r["going_class"] = r["going_pmu"]
    r["dist_bucket"] = r["distance_m"].map(dist_bucket)
    r["dist_group"] = r["distance_m"].map(rtr_arr.distance_group)     # Distanzgruppe für die Vorlieben
    r["racetype"] = r["categorie"].map(kategorie) if "categorie" in r else None
    r["course_key"] = norm_name(r["hippodrome"])
    r["konfig"] = konfig_schluessel(r)
    r = preisgeld_je_platz(r)

    h = runners.drop_duplicates(["race_id", "saddle_no"], keep="last").copy()
    h["saddle_no"] = pd.to_numeric(h["saddle_no"], errors="coerce")
    for c in ["horse", "jockey", "trainer", "owner", "breeder"]:
        h[c + "_key"] = norm_name(h[c]) if c in h else pd.Series(pd.NA, index=h.index, dtype="string")
    h = abstammung_keys(h)
    h["horse_id"] = h["horse_key"].fillna("?") + "|" + h["sire_key"].fillna("?")
    for c in ["odds_final", "odds_morning", "weight_kg", "finish_pos", "lengths_behind", "lengths_prev", "age"]:
        if c in h:
            h[c] = pd.to_numeric(h[c], errors="coerce")
        else:
            h[c] = np.nan
    h.loc[(h["odds_final"] < 1.01) | (h["odds_final"] > 1000), "odds_final"] = np.nan
    stat = h["status"].astype("string").str.upper().fillna("")
    inc = h["incident"].astype("string").str.upper().fillna("") if "incident" in h else ""
    h = h[(stat != "NON_PARTANT") & (inc != "NON_PARTANT")].copy()

    if "conditions_age" not in r:
        r["conditions_age"] = None
    pz = [f"pz{i}" for i in range(1, len(PREIS_ANTEILE) + 1)]
    h = h.merge(r[["race_id", "date", "hippodrome", "course_key", "distance_m", "going", "going_value",
                   "going_pmu", "going_class", "dist_bucket", "dist_group", "prize_eur", "racetype", "conditions_age", "konfig",
                   *pz]],
                on="race_id", how="inner")
    # Preisgeld, das das Pferd in diesem Rennen gewonnen hat (Platz 1 … 5)
    h["prize_won"] = 0.0
    for i, c in enumerate(pz, 1):
        platz = h["finish_pos"] == i
        h.loc[platz, "prize_won"] = h.loc[platz, c]
    h["prize_won"] = h["prize_won"].fillna(0.0)
    h = h.drop(columns=pz)
    h["n_runners"] = h.groupby("race_id")["saddle_no"].transform("count")
    h["won"] = (h["finish_pos"] == 1).astype(int)
    # Platz: bis PLATZ_GRENZE Starter 1.–2., ab 8 Startern 1.–3.
    h["is_place"] = (h["finish_pos"] <= np.where(h["n_runners"] <= PLATZ_GRENZE, 2, 3)).astype(int)
    h["placed"] = h["is_place"]
    h["age_bucket"] = h["age"].map(age_bucket)
    h["age_grp"] = h["age"].map(alter_gruppe)
    h["valeur"] = pd.to_numeric(h["rating"], errors="coerce") if "rating" in h else np.nan
    # Klasse des Rennens: Ø Valeur der Teilnehmer und Ø ihres Gewinns je Lauf in den KLASSE_TAGE davor;
    # cls_epr_kl nur als Basis des Index €/L+ (log-gemittelt, Pferde im ersten Jahr mit ihren Verbindungen)
    h = klassen_wert(gewinn_vorher(h))
    h["cls_val"] = h.groupby("race_id")["valeur"].transform("mean")
    h["cls_epr"] = h.groupby("race_id")["epr_prev"].transform("mean")
    h["cls_epr_kl"] = np.expm1(h.groupby("race_id")["epr_kl"].transform("mean")).round(0)
    fav = h.groupby("race_id")["odds_final"].transform("min")
    h["odds_rank"] = h.groupby("race_id")["odds_final"].rank(method="min")   # Rang der Eventualquote
    h["favourite"] = (h["odds_final"] == fav) & h["odds_final"].notna()
    h["exp_place"] = platz_erwartung(h)
    # relative Platzierung: 1 = Sieger, 0 = Letzter (für die Startbox-Abweichung)
    h["draw"] = pd.to_numeric(h["draw"], errors="coerce") if "draw" in h else np.nan
    h["rel_place"] = ((h["n_runners"] - h["finish_pos"]) / (h["n_runners"] - 1)).where(h["n_runners"] > 1).clip(0, 1)

    # Abstand des Siegers zum Zweiten (Formzeile "1/9 (1½l)")
    # (bei totem Rennen um Platz 2 gibt es zwei Zweite – dann zählt der erste Eintrag)
    zweite = h[h["finish_pos"] == 2].groupby("race_id")["lengths_prev"].first()
    sieger = h["finish_pos"] == 1
    h.loc[sieger, "margin"] = h.loc[sieger, "race_id"].map(zweite)
    h.loc[~sieger, "margin"] = h.loc[~sieger, "lengths_behind"]

    # Tracking
    if trk_runners is not None and not trk_runners.empty:
        t = trk_runners.copy()
        t["saddle_no"] = pd.to_numeric(t["saddle_no"], errors="coerce")
        cols = [c for c in ["finish_index", "pos_gain_800_finish", "speed_last600_kmh",
                            "speed_last400_kmh", "dist_vs_winner_m", "distance_covered_m", "last600_s",
                            "official_time_s", "behind_winner_s"] if c in t]
        for c in cols:
            t[c] = pd.to_numeric(t[c], errors="coerce")
        t = t.drop_duplicates(["race_id", "saddle_no"], keep="last")[["race_id", "saddle_no", *cols]]
        h = h.merge(t, on=["race_id", "saddle_no"], how="left")
        h["tracking"] = h["race_id"].isin(set(t["race_id"]))
    else:
        h["tracking"] = False
    for c in ["speed_last600_kmh", "speed_last400_kmh", "finish_index", "pos_gain_800_finish", "dist_vs_winner_m"]:
        if c not in h:
            h[c] = np.nan
    # Tempi der Schlussphase, Finish-Index, Wegfaktor und Gegenprobe neu aus den Abschnitten
    h = speedfig.rohwerte_aus_abschnitten(h, trk_sections)
    if trk_races is not None and not trk_races.empty and "pace_ratio" in trk_races:
        pc = [c for c in ["pace_ratio", "pace_early_kmh"] if c in trk_races]
        p = trk_races.drop_duplicates("race_id", keep="last")[["race_id", *pc]].copy()
        for c in pc:
            p[c] = pd.to_numeric(p[c], errors="coerce")
        h = h.merge(p, on="race_id", how="left")
    if "pace_early_kmh" not in h:
        h["pace_early_kmh"] = np.nan
    # Frühes Tempo für Daten, die vor der Spalte pace_early_kmh geparst wurden: aus tracking_leader
    fehlt = h["pace_early_kmh"].isna()
    if fehlt.any() and trk_leader is not None and not trk_leader.empty:
        distanz = r.drop_duplicates("race_id").set_index("race_id")["distance_m"]
        ersatz = speedfig.pace_frueh_aus_leader(trk_leader[trk_leader["race_id"].isin(h.loc[fehlt, "race_id"])], distanz)
        h.loc[fehlt, "pace_early_kmh"] = h.loc[fehlt, "race_id"].map(ersatz)
    if trk_sections is not None and not trk_sections.empty:
        h = h.merge(position_vor_finish(trk_sections), on=["race_id", "saddle_no"], how="left")
        h = h.merge(position_frueh(trk_sections), on=["race_id", "saddle_no"], how="left")
    for c in list(PLAUSIBEL) + ["pos_before", "pos_before_m", "early_pos"]:
        if c not in h:
            h[c] = np.nan
    for c, (lo, hi) in PLAUSIBEL.items():
        h[c] = h[c].where(h[c].between(lo, hi))
    h["pace_class"] = h["pace_ratio"].map(pace_klasse)
    h["early_pct"] = ((h["early_pos"] - 1) / (h["n_runners"] - 1).where(h["n_runners"] > 1)).clip(0, 1)
    ok = h["pos_before"].notna() & (h["n_runners"] > 0)
    h["fifth"] = np.where(ok, np.ceil(h["pos_before"] / h["n_runners"].clip(lower=1) * 5).clip(1, 5), np.nan)
    for k in (1, 2, 3):                                   # Fünftel der ersten drei im Ziel (für die Formzeile)
        top = h[h["finish_pos"] == k].drop_duplicates("race_id").set_index("race_id")["fifth"]
        h[f"fifth_p{k}"] = h["race_id"].map(top)

    # Weg: gelaufene Meter gegenüber dem Median aller Starter im Rennen (nicht gegenüber dem Sieger)
    h["weg_med"] = h["dist_vs_winner_m"] - h.groupby("race_id")["dist_vs_winner_m"].transform("median")
    h = speedfig.berechnen(h, trk_sections)
    # ΔL600 A / ΔB200 A: verglichen innerhalb Tag × Kurs × Going, Pace/Distanz und Klasse der Gruppe korrigiert
    h = tempo_delta.berechnen(h, trk_sections)
    # TR: Zeit-Rating nach Timeform-Art mit Upgrade aus dem Finishing Speed
    h = timeform_ratings.berechnen(h, trk_sections, trk_leader, standards)
    h = h.merge(ratings_je_lauf(races, runners), on=["race_id", "horse_id"], how="left")
    return h.sort_values(["date", "race_id", "finish_pos"]).reset_index(drop=True)


def ratings_je_lauf(races: pd.DataFrame, runners: pd.DataFrame, **kw) -> pd.DataFrame:
    """RTR (rating after race) und ARR je gespeichertem Lauf, berechnet wie in PT_Vorarbeiten (rtr_arr.py).

    Bewertet werden alle Starter mit Platz, in zeitlicher Reihenfolge. Das Pferd wird über horse_id
    (Name|Vater) identifiziert, wie im Rest der Race Card. Längen zum Sieger = Summe der Abstände zum
    Vordermann (fehlende zählen 0, wie im Notebook). Rückgabe: race_id, horse_id, rtr, arr, rating_filled."""
    leer = pd.DataFrame(columns=["race_id", "horse_id", "rtr", "arr", "rating_filled"])
    if races.empty or runners.empty:
        return leer
    r = races.drop_duplicates("race_id", keep="last").copy()
    r["date"] = pd.to_datetime(r["race_id"].astype(str).str[:8], format="%Y%m%d", errors="coerce")
    r["distance_m"] = pd.to_numeric(r["distance_m"], errors="coerce")
    r["going_category"] = [going_klasse(g) for g in r.get("going", pd.Series(None, index=r.index))]
    r["distance_group"] = r["distance_m"].map(rtr_arr.distance_group)
    r["prize"] = pd.to_numeric(r.get("prize_eur"), errors="coerce")
    if "categorie" not in r:
        r["categorie"] = None

    h = runners.drop_duplicates(["race_id", "saddle_no"], keep="last").copy()
    for c in ["horse", "sire"]:
        h[c + "_key"] = norm_name(h[c]) if c in h else pd.Series(pd.NA, index=h.index, dtype="string")
    h["horse"] = (h["horse_key"].fillna("?") + "|" + h["sire_key"].fillna("?")).astype(object)
    for c in ["weight_kg", "rating", "finish_pos", "lengths_prev", "age"]:
        h[c] = pd.to_numeric(h[c], errors="coerce") if c in h else np.nan
    h = h.merge(r[["race_id", "date", "going_category", "distance_group", "prize", "categorie"]], on="race_id")
    h = h.drop_duplicates(["race_id", "horse"], keep="first").sort_values(["date", "race_id"], kind="stable")
    # Lauf-Nr. des Pferdes über alle Zeilen (wie im Notebook vor dem Filter auf Starter mit Platz)
    h["horse_run"] = h.groupby("horse").cumcount() + 1
    h = h[h["finish_pos"].notna()].sort_values(["race_id", "finish_pos"], kind="stable")
    if h.empty:
        return leer
    gap = h["lengths_prev"].where(h["finish_pos"] > 1, 0.0).fillna(0.0).clip(lower=0)
    h["lengths_back"] = gap.groupby(h["race_id"]).cumsum()
    h["race_id"] = h["race_id"].astype(object)
    d = rtr_arr.berechnen(h[["race_id", "date", "horse", "finish_pos", "lengths_back", "weight_kg", "rating", "age",
                             "going_category", "distance_group", "prize", "categorie", "horse_run"]], **kw)
    return (d.rename(columns={"horse": "horse_id"})[["race_id", "horse_id", "rtr", "arr", "rating_filled"]]
             .astype({"race_id": runners["race_id"].dtype}, errors="ignore"))


def going_gewicht(lauf, heute) -> float:
    """Ähnlichkeit zweier Bodengruppen (VERY FAST … VERY SLOW, PSF) als Gewicht: 1 bei gleicher Gruppe, halbes
    Gewicht bei SCHNITT_GOING_STUFEN Gruppen Abstand; PSF gegen Gras GOING_PSF_GRAS; unbekannt -> 1 (neutral).
    Nimmt auch Bodenbegriffe ('Bon souple') und ordnet sie der Gruppe zu."""
    a, b = going_klasse(lauf), going_klasse(heute)
    if a is None or b is None:
        return 1.0
    if (a == "PSF") != (b == "PSF"):
        return GOING_PSF_GRAS
    if a == "PSF":
        return 1.0
    sa, sb = GOING_STUFE.get(a), GOING_STUFE.get(b)
    if sa is None or sb is None:
        return 1.0
    return 1.0 / (1.0 + abs(sa - sb) / SCHNITT_GOING_STUFEN)


def lauf_gewichte(w: pd.DataFrame, dist_heute, going_heute) -> pd.Series:
    """Gewicht je früherem Lauf für die Kacheln (TR, ΔL600 A, ΔB200 A): Distanzähnlichkeit × Going-Ähnlichkeit.
    Distanz: 1 / (1 + |Distanz − heute| / SCHNITT_DIST_M); Going: going_gewicht (offizieller Bodenbegriff)."""
    d_heute = _num(dist_heute)
    g_dist = ((1 / (1 + (w["distance_m"] - d_heute).abs() / SCHNITT_DIST_M)).fillna(1.0) if d_heute is not None
              else pd.Series(1.0, index=w.index))
    g_going = (w["going_pmu"].map(lambda g: going_gewicht(g, going_heute)) if "going_pmu" in w
               else pd.Series(1.0, index=w.index))
    return (g_dist * g_going).astype(float)


def gewichteter_schnitt(laeufe: pd.DataFrame, spalte: str, dist_heute, going_heute) -> dict:
    """Kachel TR bzw. ARR: gewichteter Ø von `spalte` über die letzten SCHNITT_LAEUFE Läufe mit Wert
    (`laeufe` neueste zuerst), Gewicht = lauf_gewichte (Distanz × Going). Keine Schrumpfung – TR und ARR sind
    absolute Niveaus (TR um 100, ARR in kg), nicht Abweichungen um 0."""
    if spalte not in laeufe:
        return {"avg": None, "sd": None, "runs": 0, "gewichte": [], "best": None}
    w = laeufe.dropna(subset=[spalte]).head(SCHNITT_LAEUFE)
    if not len(w):
        return {"avg": None, "sd": None, "runs": 0, "gewichte": [], "best": None}
    gew = lauf_gewichte(w, dist_heute, going_heute)
    return {"avg": float((gew * w[spalte]).sum() / gew.sum()),
            "sd": float(w[spalte].std()) if len(w) >= 2 else None, "runs": int(len(w)),
            "gewichte": [round(float(x), 2) for x in gew], "best": float(w[spalte].max())}


def tr_schnitt(laeufe: pd.DataFrame, dist_heute, going_heute) -> dict:
    """TR-Kachel: gewichteter Ø der TR (lb, bei 55 kg); `laeufe` bereits ohne gedeckelte Läufe."""
    return gewichteter_schnitt(laeufe, "tr", dist_heute, going_heute)


def _tr_heute(tr, gewicht):
    """TR (lb, auf REF_WEIGHT_KG bezogen) auf das heutige Gewicht umgerechnet: TR − (Gewicht − 55 kg) in lb."""
    t, g = _num(tr, 2), _num(gewicht, 2)
    if t is None:
        return None
    if g is None:
        return round(t)
    return round(t - (g - timeform_ratings.REF_WEIGHT_KG) * timeform_ratings.LB_PER_KG)


def _adj(wert, gewicht):
    """Rating bereinigt nach Gewicht: wert − gewicht + GEWICHT_REF."""
    w, g = _num(wert, 2), _num(gewicht, 2)
    return None if w is None or g is None else round(w - g + GEWICHT_REF, 1)


def position_vor_finish(sections: pd.DataFrame, meter: int = POS_VOR_FINISH_M) -> pd.DataFrame:
    """Position je Starter am Messpunkt, der `meter` vor dem Ziel am nächsten liegt."""
    s = sections.copy()
    for c in ["saddle_no", "m_to_go", "position"]:
        s[c] = pd.to_numeric(s[c], errors="coerce")
    s = s[(s["m_to_go"] > 0) & s["position"].notna()]
    if s.empty:
        return pd.DataFrame(columns=["race_id", "saddle_no", "pos_before", "pos_before_m"])
    s["_abst"] = (s["m_to_go"] - meter).abs()
    s = s.sort_values(["race_id", "saddle_no", "_abst", "m_to_go"])
    s = s.drop_duplicates(["race_id", "saddle_no"])
    return s.rename(columns={"position": "pos_before", "m_to_go": "pos_before_m"})[
        ["race_id", "saddle_no", "pos_before", "pos_before_m"]]


def position_frueh(sections: pd.DataFrame) -> pd.DataFrame:
    """Frühe Position: Platz am ersten Messpunkt nach dem Start (Ende des ersten Abschnitts)."""
    s = sections.copy()
    for c in ["saddle_no", "m_to_go", "position"]:
        s[c] = pd.to_numeric(s[c], errors="coerce")
    s = s[(s["m_to_go"] > 0) & s["position"].notna()]
    if s.empty:
        return pd.DataFrame(columns=["race_id", "saddle_no", "early_pos"])
    s = s.sort_values(["race_id", "saddle_no", "m_to_go"], ascending=[True, True, False])
    s = s.drop_duplicates(["race_id", "saddle_no"])
    return s.rename(columns={"position": "early_pos"})[["race_id", "saddle_no", "early_pos"]]


def stil(early_pct) -> tuple[str, str] | tuple[None, None]:
    v = _num(early_pct, 3)
    if v is None:
        return None, None
    return next((k, lab) for bis, k, lab in STIL if v <= bis)


def pace_kalibrierung(h: pd.DataFrame) -> dict:
    """Wie hängt das Tempo eines Rennens von der Zahl der Tempomacher und der Feldgröße ab?

    Für jedes frühere Rennen mit Pace-Ratio wird gezählt, wie viele Starter VOR diesem Rennen
    (Mittel ihrer letzten STIL_LAEUFE frühen Positionen) als Tempomacher galten. Die Pace-Ratio
    hängt stark von der Distanz ab, deshalb wird ihre Abweichung von der Norm der Distanzgruppe
    per Regression erklärt:  Abweichung = a + b · Tempomacher + c · (Starter − PACE_FELD_REF)."""
    leer = {"norm": {}, "coef": None, "gesamt": None, "rennen": 0}
    if h.empty or "early_pct" not in h or h["early_pct"].notna().sum() < MIN_GRUPPE:
        return leer
    t = h[h["early_pct"].notna()].sort_values(["date", "race_id"])
    vorher = (t.groupby("horse_id")["early_pct"]
                .transform(lambda x: x.shift().rolling(STIL_LAEUFE, min_periods=1).mean()))
    h2 = h[["race_id", "saddle_no", "horse_id"]].merge(
        pd.DataFrame({"race_id": t["race_id"], "saddle_no": t["saddle_no"], "stil_vorher": vorher}),
        on=["race_id", "saddle_no"], how="left")
    per_rennen = (h2.assign(front=h2["stil_vorher"] <= TEMPOMACHER)
                    .groupby("race_id").agg(n_front=("front", "sum"), bekannt=("stil_vorher", "count")))
    r = (h.drop_duplicates("race_id")[["race_id", "pace_ratio", "dist_bucket", "n_runners"]]
          .merge(per_rennen, on="race_id", how="inner"))
    r = r[r["pace_ratio"].notna() & (r["bekannt"] >= 3) & r["n_runners"].notna()]
    if len(r) < MIN_GRUPPE:
        return leer
    norm = r.groupby("dist_bucket")["pace_ratio"].mean()
    y = (r["pace_ratio"] - r["dist_bucket"].map(norm)).to_numpy()
    X = np.column_stack([np.ones(len(r)), r["n_front"].clip(upper=5), r["n_runners"] - PACE_FELD_REF])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return {"norm": {k: round(float(v), 1) for k, v in norm.items()},
            "coef": {"a": round(float(coef[0]), 3), "front": round(float(coef[1]), 3),
                     "field": round(float(coef[2]), 3)},
            "gesamt": round(float(r["pace_ratio"].mean()), 1), "rennen": int(len(r))}


def _iv(g: pd.DataFrame, maske: pd.Series) -> float | None:
    """Impact Value: Anteil an den Siegern / Anteil an den Startern."""
    starter, sieger = maske.mean(), g["won"].sum()
    if not starter or not sieger:
        return None
    return float(g.loc[maske, "won"].sum() / sieger / starter)


def _bias(g: pd.DataFrame) -> dict | None:
    rennen = g["race_id"].nunique()
    if rennen < MIN_BIAS_RENNEN:
        return None
    vorne, hinten = _iv(g, g["early_pct"] <= BIAS_VORNE), _iv(g, g["early_pct"] >= BIAS_HINTEN)
    if vorne is None or hinten is None:
        return None
    return {"races": int(rennen), "iv_front": round(vorne, 2), "iv_back": round(hinten, 2),
            "bias": round(vorne - hinten, 2)}


def bahn_bias(h: pd.DataFrame) -> dict:
    """Waren an einer Bahn über eine Distanz Frontrenner oder abwartend gerittene Pferde
    erfolgreicher? bias = IV(vorderes Drittel früh) − IV(hinteres Drittel früh); positiv = vorne besser.
    Schlüssel: (Bahn, Distanz), ersatzweise (Bahn, Distanzgruppe); dazu der Schnitt aller Bahnen."""
    if h.empty or "early_pct" not in h:
        return {"exakt": {}, "gruppe": {}, "gesamt": None}
    t = h[h["early_pct"].notna()]
    return {"exakt": {k: b for k, g in t.groupby(["course_key", "distance_m"]) if (b := _bias(g))},
            "gruppe": {k: b for k, g in t.groupby(["course_key", "dist_bucket"]) if (b := _bias(g))},
            "gesamt": _bias(t)}


VERLAUF_MIN_STARTER = 8      # Rennverlauf erst ab so vielen Startern mit früher Position
VERLAUF_MIN_RENNEN = 15      # Norm je Bahn/Distanz ab so vielen Rennen, sonst Bahn/Distanzgruppe, sonst alle
VERLAUF_ANTEIL = 0.25        # je so viele Rennen (unten/oben) gelten als „vorne“ bzw. „hinten begünstigt“
VERLAUF_VORNE, VERLAUF_HINTEN = 0.25, 0.6   # frühe Position des Pferdes: vorne bis / hinten ab


def rennverlauf(h: pd.DataFrame, lern: pd.DataFrame) -> pd.DataFrame:
    """Wer hat im Rennen gewonnen – die vorne oder die hinten? Je Rennen: Ø frühe Position der ersten drei im Ziel
    minus Ø frühe Position des Feldes (negativ = vorne gewonnen), gegen die Norm der Bahn/Distanz (gelernt auf `lern`).
    Je Starter: mit dem Verlauf (Position passte zum Verlauf) oder gegen den Verlauf."""
    def je_rennen(d: pd.DataFrame) -> pd.DataFrame:
        t = d[d["early_pct"].notna() & d["finish_pos"].notna()]
        g = t.groupby("race_id")
        r = pd.DataFrame({"n": g.size(), "feld": g["early_pct"].mean(),
                          "top3": t[t["finish_pos"] <= 3].groupby("race_id")["early_pct"].mean()})
        r = r[r["n"] >= VERLAUF_MIN_STARTER].dropna()
        r["verlauf"] = r["top3"] - r["feld"]
        info = d.drop_duplicates("race_id").set_index("race_id")[["course_key", "distance_m", "dist_bucket"]]
        return r.join(info)
    alle, gelernt = je_rennen(h), je_rennen(lern)
    if alle.empty or gelernt.empty:
        for c in ["verlauf", "verlauf_rel", "verlauf_kl", "verlauf_pferd"]:
            h[c] = np.nan if c in ("verlauf", "verlauf_rel") else None
        return h
    def norm(keys):
        s = gelernt.groupby(keys)["verlauf"].agg(["mean", "size"])
        return s[s["size"] >= VERLAUF_MIN_RENNEN]["mean"]
    n1, n2, n0 = norm(["course_key", "distance_m"]), norm(["course_key", "dist_bucket"]), gelernt["verlauf"].mean()
    erw = [n1.get((c, d), n2.get((c, b), n0)) for c, d, b in zip(alle["course_key"], alle["distance_m"], alle["dist_bucket"])]
    alle["verlauf_rel"] = alle["verlauf"] - np.array(erw, dtype=float)
    lo, hi = gelernt["verlauf"].sub(gelernt["verlauf"].mean()).quantile([VERLAUF_ANTEIL, 1 - VERLAUF_ANTEIL])
    alle["verlauf_kl"] = np.select([alle["verlauf_rel"] <= lo, alle["verlauf_rel"] >= hi], ["vorne", "hinten"], "neutral")
    h = h.drop(columns=[c for c in ["verlauf", "verlauf_rel", "verlauf_kl"] if c in h]).merge(
        alle[["verlauf", "verlauf_rel", "verlauf_kl"]], left_on="race_id", right_index=True, how="left")
    vorne, hinten = h["early_pct"] <= VERLAUF_VORNE, h["early_pct"] >= VERLAUF_HINTEN
    kl = h["verlauf_kl"]
    h["verlauf_pferd"] = np.select(
        [(kl.eq("vorne") & hinten) | (kl.eq("hinten") & vorne), (kl.eq("vorne") & vorne) | (kl.eq("hinten") & hinten),
         kl.notna() & h["early_pct"].notna()], ["gegen", "mit", "neutral"], None)
    return h


def pace_szenario(stile: list[dict], dist_bucket: str | None, kal: dict) -> dict:
    """Erwartetes Tempo aus den Laufstilen der heutigen Starter."""
    bekannt = [x for x in stile if x["style"]]
    n_front = sum(1 for x in bekannt if x["early"] <= TEMPOMACHER)
    out = {"n_front": n_front, "known": len(bekannt), "runners": len(stile),
           "groups": {k: [x["no"] for x in bekannt if x["style"] == k] for _, k, _ in STIL},
           "unknown": [x["no"] for x in stile if not x["style"]],
           "expected": None, "norm": None, "diff": None, "label": None, "basis": None}
    norm = kal["norm"].get(dist_bucket, kal["gesamt"])
    c = kal["coef"]
    if norm is None or c is None or len(bekannt) < 3:
        return out
    teil_front = c["front"] * min(n_front, 5)
    teil_feld = c["field"] * (len(stile) - PACE_FELD_REF)
    diff = c["a"] + teil_front + teil_feld
    out.update(expected=round(norm + diff, 1), norm=norm, diff=round(diff, 2), basis=kal["rennen"],
               part_front=round(teil_front, 2), part_field=round(teil_feld, 2), coef=c,
               label="schnell" if diff >= PACE_SCHWELLE else "langsam" if diff <= -PACE_SCHWELLE else "normal")
    return out


# --------------------------------------------------------------------------
# Statistiken
# --------------------------------------------------------------------------
def _rec(g: pd.DataFrame) -> dict:
    """Bilanz einer Gruppe. A/E = A/E Platz: Plätze ÷ Σ erwartete Platzwahrscheinlichkeit (Harville mit Korrektur,
    ohne Marge), nur Läufe mit Quote. ae_win: klassisches A/E auf Sieg (Siege ÷ Σ 1/Quote) zum Vergleich."""
    runs = int(len(g))
    wins = int(g["won"].sum())
    mit = g["odds_final"].notna()
    exp_w = float((1 / g.loc[mit, "odds_final"]).sum())
    wins_mit = int(g.loc[mit, "won"].sum())
    if "exp_place" in g:
        mp = g["exp_place"].notna()
        exp = float(g.loc[mp, "exp_place"].sum())
        pl_mit = int(g.loc[mp, "placed"].sum())
        n_mit = int(mp.sum())
    else:
        exp, pl_mit, n_mit = 0.0, 0, 0
    epr = float(g["prize_won"].mean()) if runs and "prize_won" in g else None
    return {"runs": runs, "wins": wins, "places": int(g["placed"].sum()),
            "exp": _num(exp), "ae": _num(pl_mit / exp) if exp > 0 else None,
            "ae_win": _num(wins_mit / exp_w) if exp_w > 0 else None, "epr": _num(epr, 0),
            "pl_exp": pl_mit, "n_exp": n_mit}          # Plätze und Läufe, über die A/E gerechnet ist


def _leer() -> dict:
    return {"runs": 0, "wins": 0, "places": 0, "exp": None, "ae": None, "ae_win": None, "epr": None,
            "pl_exp": 0, "n_exp": 0}


def ae_abweichung(teil: dict, gesamt: dict | None) -> dict | None:
    """Weicht das A/E einer Teilgruppe (z. B. Trainer auf diesem Kurs) vom Rest derselben Person/Linie ab?
    Maßstab = A/E des Rests (gesamt minus Teil). Erwartete Plätze der Teilgruppe = Σ Erwartung × A/E Rest,
    Varianz ≈ E·(1 − E/n). Auffällig (sig), wenn A/E Teil ÷ A/E Rest mindestens AE_MIN_ABW von 1 entfernt
    ist und mindestens AE_Z Standardfehler, bei mindestens AE_MIN_REST Läufen im Rest. None ohne Grundlage."""
    if not gesamt or not teil or not teil.get("n_exp") or not teil.get("exp"):
        return None
    n_r = gesamt.get("n_exp", 0) - teil["n_exp"]
    e_r = (gesamt.get("exp") or 0) - teil["exp"]
    p_r = gesamt.get("pl_exp", 0) - teil["pl_exp"]
    if n_r <= 0 or e_r <= 0 or p_r <= 0:
        return None
    basis = p_r / e_r
    erw = teil["exp"] * basis
    var = erw * max(1 - erw / teil["n_exp"], 0.05)
    z = (teil["pl_exp"] - erw) / np.sqrt(var) if var > 0 else 0.0
    ratio = (teil["pl_exp"] / teil["exp"]) / basis
    return {"base": _num(basis), "ratio": _num(ratio), "z": _num(z, 1), "rest": int(n_r),
            "sig": bool(abs(ratio - 1) >= AE_MIN_ABW and abs(z) >= AE_Z and n_r >= AE_MIN_REST),
            "dir": 1 if ratio > 1 else -1}


def _perzentil(sortiert: np.ndarray, wert) -> int | None:
    """Anteil (0–100) der Werte, die kleiner oder gleich `wert` sind."""
    v = _num(wert)
    if v is None or not len(sortiert):
        return None
    return int(round(100 * np.searchsorted(sortiert, v, side="right") / len(sortiert)))


def gruppen(h: pd.DataFrame, keys: list[str]) -> dict:
    """{schlüssel: rec} für alle Kombinationen der Spalten `keys`."""
    if h.empty:
        return {}
    d = h.dropna(subset=keys)
    out = {}
    for k, g in d.groupby(keys if len(keys) > 1 else keys[0], sort=False):
        out[k] = _rec(g)
    return out


# --------------------------------------------------------------------------
# Programm des Tages
# --------------------------------------------------------------------------
def programm(tag: date, session: requests.Session | None = None, *, nur_flach: bool = True,
             pause: float = 0.3) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Heutige französische Flachrennen (auch noch nicht gelaufene) samt Startern."""
    s = session or requests.Session()
    meets = pmu.meetings(tag, s, nur_flach=nur_flach, nur_gelaufen=False)
    if meets is None:
        raise RuntimeError(f"PMU-Programm nicht erreichbar ({pmu.LETZTER_FEHLER})")
    races, runners = pmu.starter(tag, s, meets, pause=pause)
    races = bahnart_nachladen(races, tag, s, pause=pause)
    return pd.DataFrame(races), pd.DataFrame(runners)


def bahnart_nachladen(races: list[dict], tag: date, s: requests.Session, *, pause: float = 0.3) -> list[dict]:
    """Bahnart (typePiste) und fehlenden Parcours aus der Detailseite jedes Rennens ergänzen – das Tagesprogramm
    liefert sie nicht, pmu_basis (Historie) holt sie dort. Ohne sie passt der Konfigurationsschlüssel
    (Startbox, Standardzeiten) nicht zur Historie. Nicht erreichbar: Feld bleibt leer (Rückfall in baue_daten)."""
    import pmu_basis
    d = tag.strftime("%d%m%Y")
    for z in races:
        if z.get("track_type"):
            continue
        try:
            det = pmu_basis._hole(s, pmu_basis.RACE_PFAD.format(d=d, r=z["reunion"], c=z["race_no"])) or {}
        except Exception:                                        # Netz/Antwort kaputt: Rückfall greift
            det = {}
        if isinstance(det, dict):
            z["track_type"] = det.get("typePiste") or z.get("track_type")
            if not z.get("parcours") and det.get("parcours"):
                z["parcours"] = det["parcours"]
        time.sleep(pause)
    return races


# --------------------------------------------------------------------------
# Race Card bauen
# --------------------------------------------------------------------------
def _formzeile(z, gewicht_heute=None) -> dict:
    """Eine Formzeile. RTR/ARR bereinigt mit dem heutigen Gewicht (gewicht_heute), nicht mit dem damaligen."""
    return {
        "date": z["date"].strftime("%Y-%m-%d"), "race_id": z["race_id"],
        "course": _txt(z["hippodrome"]), "dist": _num(z["distance_m"], 0),
        "going": _txt(z["going"]), "going_value": _num(z["going_value"], 1),
        "prize": _num(z["prize_eur"], 0), "type": _txt(z["racetype"]),
        "cls_val": _num(z.get("cls_val"), 1), "cls_epr": _num(z.get("cls_epr"), 0),
        "cls_epr_kl": _num(z.get("cls_epr_kl"), 0), "won_eur": _num(z.get("prize_won"), 0),
        "pos": _num(z["finish_pos"], 0), "ran": _num(z["n_runners"], 0),
        "margin": _num(z.get("margin"), 2), "weight": _num(z["weight_kg"], 1),
        "jockey": _txt(z.get("jockey")), "odds": _num(z["odds_final"], 1),
        "odds_rank": _num(z.get("odds_rank"), 0),
        "valeur": _num(z.get("valeur"), 1), "blinkers": _txt(z.get("blinkers")), "draw": _num(z.get("draw"), 0),
        "comment": _txt(z.get("comment")),
        "incident": _txt(z.get("incident")), "fav": bool(z["favourite"]),
        "tracking": bool(z["tracking"]), "unreliable": bool(z.get("ausgeritten") is True),
        "early_pos": _num(z.get("early_pos"), 0),
        "pos_before": _num(z["pos_before"], 0), "pos_before_m": _num(z["pos_before_m"], 0),
        "fifth": _num(z["fifth"], 0), "pace_ratio": _num(z["pace_ratio"], 1),
        "top3_fifth": [_num(z.get(f"fifth_p{k}"), 0) for k in (1, 2, 3)],   # Fünftel des 1., 2., 3. im Ziel
        "finish_index": _num(z["finish_index"], 1), "fi_adj": _num(z.get("fi_adj"), 1),
        "weg_med": _num(z.get("weg_med"), 1), "pos_gain": _num(z["pos_gain_800_finish"], 0),
        "l600": _num(z["speed_last600_kmh"], 2), "b200": _num(z.get("best200_kmh"), 2),
        "b200_seg": _txt(z.get("best200_seg")),
        "tr": _num(z.get("tr"), 0), "tr_heute": _tr_heute(z.get("tr"), gewicht_heute) if pd.notna(z.get("tr")) else None,
        "tr_zeit": _num(z.get("tr_zeit"), 0), "tr_upg": _num(z.get("tr_upgrade"), 1),
        "tr_cap": bool(z.get("tr_gedeckelt") == 1),
        "tr_ga": _num(z.get("tr_ga"), 2), "fs": _num(z.get("fs_pct"), 1), "fs_opt": _num(z.get("fs_opt"), 1),
        "fs_race": _num(z.get("fs_race"), 1), "fs_par": _num(z.get("fs_par"), 1),
        "dl600_a": _num(z.get("d_L600_A"), 2), "dl600_k": _num(z.get("k_L600"), 2),
        "db200_a": _num(z.get("d_B200_A"), 2), "db200_k": _num(z.get("k_B200"), 2),
        "path_factor": _num(z.get("path_factor"), 3),
        "sec_mismatch": bool(z.get("last600_mismatch") is True),
        "rtr": _num(z.get("rtr"), 1), "rtr_adj": _adj(z.get("rtr"), gewicht_heute),
        "arr": _num(z.get("arr"), 1), "arr_adj": _adj(z.get("arr"), gewicht_heute),
        "rating_filled": bool(pd.isna(z.get("rating")) and pd.notna(z.get("rating_filled"))),
        # Rennverlauf: wer gewann (vorne/hinten/neutral, Wert gegen die Norm der Bahn) und lief das Pferd mit/gegen ihn
        "verlauf": _txt(z.get("verlauf_kl")), "verlauf_wert": _num(z.get("verlauf_rel"), 2),
        "verlauf_pferd": _txt(z.get("verlauf_pferd")),
        "verlauf_plus": bool(z.get("verlauf_pferd") == "gegen" and pd.notna(z.get("finish_pos"))
                             and (z["finish_pos"] <= 3 or (pd.notna(z.get("rel_place")) and z["rel_place"] >= 0.6))),
    }


def _ae_trend(kurz: dict, lang: dict) -> str | None:
    """'hot' / 'cold', wenn die letzten 30 Tage deutlich vom 365-Tage-Schnitt abweichen."""
    if kurz["runs"] < TREND_MIN_STARTS or kurz["ae"] is None or lang["ae"] is None:
        return None
    if kurz["ae"] >= lang["ae"] + TREND_DIFF:
        return "hot"
    if kurz["ae"] <= lang["ae"] - TREND_DIFF:
        return "cold"
    return None


def _scheuklappen(x) -> str | None:
    t = str(x or "").upper()
    if not t or t in ("NAN", "NONE") or t.startswith("SANS"):
        return None
    return "australische Scheuklappen" if "AUSTRAL" in t else "Scheuklappen"


def box_urteil(mean, n) -> dict | None:
    """Ø relative Platzierung einer Startbox: Abweichung von 0,5 und ob sie auffällig ist
    (|Abweichung| ≥ BOX_MIN_ABW und ≥ BOX_Z Standardfehler, SE = BOX_SD / √n)."""
    if mean is None or not n:
        return None
    dev = float(mean) - 0.5
    z = dev / (BOX_SD / np.sqrt(n))
    return {"mean": _num(mean, 3), "dev": _num(dev, 3), "n": int(n), "z": _num(z, 1),
            "sig": bool(abs(dev) >= BOX_MIN_ABW and abs(z) >= BOX_Z)}


def _wechsel(p, letzter) -> list[dict]:
    """Trainerwechsel, Ausrüstungswechsel und erstmals Wallach gegenüber dem letzten Lauf."""
    if letzter is None:
        return []
    out = []
    if _txt(letzter.get("trainer_key")) and _txt(p.get("trainer_key")) and letzter["trainer_key"] != p["trainer_key"]:
        out.append({"key": "TR", "text": f"Trainerwechsel (vorher {str(letzter.get('trainer') or '').title()})"})
    if _txt(letzter.get("owner_key")) and _txt(p.get("owner_key")) and letzter["owner_key"] != p["owner_key"]:
        out.append({"key": "OW", "text": f"Besitzerwechsel (vorher {str(letzter.get('owner') or '').title()})"})
    heute, vorher = _scheuklappen(p.get("blinkers")), _scheuklappen(letzter.get("blinkers"))
    if heute != vorher:
        if heute and not vorher:
            out.append({"key": "b1", "text": f"erstmals {heute}"})
        elif vorher and not heute:
            out.append({"key": "b0", "text": f"ohne {vorher} (zuletzt mit)"})
        else:
            out.append({"key": "b↔", "text": f"jetzt {heute} (zuletzt {vorher})"})
    sex_h, sex_v = str(p.get("sex") or "").upper()[:1], str(letzter.get("sex") or "").upper()[:1]
    if sex_h == "H" and sex_v == "M":
        out.append({"key": "g1", "text": "erstmals als Wallach"})
    return out


def _lb(z) -> float:
    """Längen hinter dem Sieger (Sieger 0)."""
    return z["lengths_behind"] if pd.notna(z["lengths_behind"]) else (0.0 if z["finish_pos"] == 1 else np.nan)


FORM_KRITERIEN = ("K", "D", "B")   # Reihenfolge der Kennzeichen
FORM_DIST_M = 100                  # D: Distanz höchstens so weit von heute entfernt


def gleich_heute(z, course, dist, gb) -> list[str]:
    """Kennzeichen, in denen ein früherer Lauf dem heutigen Rennen entspricht:
    K gleicher Kurs und gleicher Belag (PSF gegen Gras, PSF = Bodengruppe PSF),
    D Distanz ±FORM_DIST_M m, B gleiche Bodengruppe (GOING_MAP)."""
    out = []
    g = z.get("going_pmu")
    if course is not None and z.get("course_key") == course and pd.notna(g) and gb is not None \
            and (g == "PSF") == (gb == "PSF"):
        out.append("K")
    d = _num(z.get("distance_m"))
    if dist is not None and d is not None and abs(d - dist) <= FORM_DIST_M:
        out.append("D")
    if gb is not None and pd.notna(g) and g == gb:
        out.append("B")
    return out


def formzeilen_auswahl(vorher: pd.DataFrame, course, dist, gb) -> list[tuple]:
    """Die letzten LETZTE_LAEUFE Läufe; fehlt darunter ein Lauf auf demselben Kurs (und Belag), über die
    heutige Distanz (±FORM_DIST_M m) oder auf derselben Bodengruppe, kommt der letzte ältere Lauf mit diesem
    Merkmal dazu (je Lauf nur einmal, höchstens drei, neueste zuerst). Liste von (Zeile, None oder Liste der Kennzeichen, für die er dazukam)."""
    if not len(vorher):
        return []
    kopf, rest = vorher.head(LETZTE_LAEUFE), vorher.iloc[LETZTE_LAEUFE:]
    out = [(z, None) for _, z in kopf.iterrows()]
    vorhanden = set().union(*(gleich_heute(z, course, dist, gb) for z, _ in out))
    extra: dict[int, list[str]] = {}                       # Position in rest -> Kennzeichen
    for k in FORM_KRITERIEN:
        if k in vorhanden:
            continue
        for i in range(len(rest)):
            if k in gleich_heute(rest.iloc[i], course, dist, gb):
                extra.setdefault(i, []).append(k)
                break
    out += [(rest.iloc[i], extra[i]) for i in sorted(extra)]  # vorher ist neueste zuerst sortiert
    return out


def _feld_nachladen(rid, h: pd.DataFrame, h_rennen: dict, h_pferde: dict) -> None:
    """Feld eines älteren Rennens samt späterer Starts seiner Gegner nachtragen (für zusätzliche Formzeilen)."""
    feld = h[h["race_id"] == rid]
    h_rennen[rid] = feld
    for hid in set(feld["horse_id"]) - set(h_pferde):
        h_pferde[hid] = h[h["horse_id"] == hid].sort_values("date")


def _gegner(z, h_rennen: dict, h_pferde: dict, heute: pd.Timestamp) -> list[dict]:
    """Alle Gegner aus einem früheren Rennen in der Reihenfolge des Einlaufs, mit ihrem nächsten Start
    (None, wenn sie seitdem nicht wieder gelaufen sind) und ob der besser oder schlechter als ihre Quote war."""
    feld = h_rennen.get(z["race_id"])
    if feld is None:
        return []
    eigen_lb = _lb(z)
    out = []
    for _, g in feld.sort_values(["finish_pos", "saddle_no"], na_position="last").iterrows():
        if g["horse_id"] == z["horse_id"]:
            continue
        lb = _lb(g)
        spaeter = h_pferde.get(g["horse_id"])
        if spaeter is not None:
            spaeter = spaeter[(spaeter["date"] > z["date"]) & (spaeter["date"] < heute)]
        nxt = None
        if spaeter is not None and len(spaeter):
            n = spaeter.iloc[0]
            urteil = None
            if pd.notna(n["finish_pos"]) and pd.notna(n["odds_rank"]):
                urteil = ("besser" if n["finish_pos"] < n["odds_rank"]
                          else "schlechter" if n["finish_pos"] > n["odds_rank"] else "wie erwartet")
            nxt = {"date": n["date"].strftime("%Y-%m-%d"), "course": _txt(n["hippodrome"]),
                   "dist": _num(n["distance_m"], 0), "pos": _num(n["finish_pos"], 0),
                   "ran": _num(n["n_runners"], 0), "odds_rank": _num(n["odds_rank"], 0),
                   "odds": _num(n["odds_final"], 1), "verdict": urteil,
                   "cls_epr_kl": _num(n.get("cls_epr_kl"), 0), "cls_val": _num(n.get("cls_val"), 1)}
        out.append({
            "horse": _txt(g["horse"]), "pos": _num(g["finish_pos"], 0), "odds": _num(g["odds_final"], 1),
            "weight": _num(g["weight_kg"], 1),
            "diff_l": _num(lb - eigen_lb, 2) if pd.notna(lb) and pd.notna(eigen_lb) else None,
            "next": nxt, "more": int(len(spaeter) - 1) if nxt else 0,
        })
    return out


GEGNER_ZEIGEN = 2               # je Formzeile gezeigt: so viele wieder gelaufene Gegner direkt davor und dahinter


def gegner_auswahl(liste: list[dict] | None, pos) -> list[dict] | None:
    """Für die Anzeige: die GEGNER_ZEIGEN Gegner direkt vor und hinter dem Pferd, die seitdem wieder gelaufen sind
    (die Bilanz rivals_stat zählt weiter über das ganze Feld)."""
    if liste is None:
        return None
    wieder = [g for g in liste if g.get("next")]
    if pos is None or (isinstance(pos, float) and np.isnan(pos)):
        return wieder[:2 * GEGNER_ZEIGEN]
    vor = [g for g in wieder if g.get("pos") is not None and g["pos"] < pos][-GEGNER_ZEIGEN:]
    nach = [g for g in wieder if g.get("pos") is None or g["pos"] >= pos][:GEGNER_ZEIGEN]
    return vor + nach


def _gegner_bilanz(liste: list[dict] | None) -> dict | None:
    """Wie liefen die Gegner im nächsten Start: besser / schlechter / wie erwartet gemessen am Quotenrang."""
    if liste is None:
        return None
    v = [g["next"]["verdict"] for g in liste if g["next"]]
    return {"better": v.count("besser"), "worse": v.count("schlechter"), "same": v.count("wie erwartet"),
            "ran": len(v), "n": len(liste)}


def _duelle(eigen: pd.DataFrame, rennen: dict, heute_gew: dict, hid) -> list[dict]:
    """Frühere Rennen, in denen das Pferd auf heutige Gegner traf: Platz und Gewicht beider damals,
    Abstand in Längen und wie sich der Gewichtsunterschied bis heute verschoben hat."""
    out = []
    w_ich = heute_gew.get(hid, {}).get("weight")
    for _, z in eigen.iterrows():
        feld = rennen.get(z["race_id"])
        if feld is None:
            continue
        for _, g in feld.iterrows():
            if g["horse_id"] == hid:
                continue
            lb_ich, lb_g = _lb(z), _lb(g)
            w_g = heute_gew.get(g["horse_id"], {})
            dann = z["weight_kg"] - g["weight_kg"] if pd.notna(z["weight_kg"]) and pd.notna(g["weight_kg"]) else np.nan
            jetzt = (w_ich - w_g["weight"]) if w_ich is not None and w_g.get("weight") is not None else np.nan
            out.append({
                "rival": _txt(g["horse"]), "rival_no": w_g.get("no"),
                "date": z["date"].strftime("%Y-%m-%d"), "course": _txt(z["hippodrome"]),
                "dist": _num(z["distance_m"], 0), "going": _txt(z["going"]), "type": _txt(z["racetype"]),
                "ran": _num(z["n_runners"], 0),
                "pos": _num(z["finish_pos"], 0), "rival_pos": _num(g["finish_pos"], 0),
                "weight": _num(z["weight_kg"], 1), "rival_weight": _num(g["weight_kg"], 1),
                "diff_l": _num(lb_g - lb_ich, 2) if pd.notna(lb_g) and pd.notna(lb_ich) else None,
                "w_then": _num(dann, 1), "w_today": _num(jetzt, 1),
                "shift": _num(jetzt - dann, 1) if pd.notna(jetzt) and pd.notna(dann) else None,
                # heute erwartet: Abstand damals − Verschiebung des Gewichtsunterschieds (1 kg = 1 Länge)
                "exp_l": (_num((lb_g - lb_ich) - ((jetzt - dann) if pd.notna(jetzt) and pd.notna(dann) else 0), 1)
                          if pd.notna(lb_g) and pd.notna(lb_ich) else None),
            })
    return out


def _karriere(v: pd.DataFrame, heute: pd.Timestamp) -> dict:
    """Läufe-Siege-Plätze und Gewinn je Lauf aus der Datenbank: gesamt und letzte KLASSE_TAGE."""
    def bilanz(g):
        n = int(len(g))
        earn = float(g["prize_won"].sum()) if n and "prize_won" in g else 0.0
        return {"runs": n, "wins": int(g["won"].sum()) if n else 0, "places": int(g["placed"].sum()) if n else 0,
                "earn": _num(earn, 0), "epr": _num(earn / n, 0) if n else None}
    if not len(v):
        return {"all": bilanz(v), "d365": bilanz(v)}
    return {"all": bilanz(v), "d365": bilanz(v[v["date"] >= heute - timedelta(days=KLASSE_TAGE)])}


def scheuklappen_gruppe(x) -> str | None:
    """'SANS_OEILLERES' -> 'ohne', 'OEILLERES_CLASSIQUE' -> 'klassisch', 'OEILLERES_AUSTRALIENNES' -> 'australisch'."""
    t = str(x or "").upper()
    if not t or t in ("NAN", "NONE"):
        return None
    return "ohne" if t.startswith("SANS") else ("australisch" if "AUSTRAL" in t else "klassisch")


def handicap_marke(v: pd.DataFrame, rating_heute=None) -> dict | None:
    """Letzte Siegmarke im Handicap (Valeur beim letzten Handicap-Sieg); ohne Sieg die letzte Platzmarke (1.–3.)."""
    if not len(v) or "valeur" not in v:
        return None
    hc = v[(v["racetype"] == "Handicap") & v["valeur"].notna()]
    for art, maske in (("sieg", hc["won"] == 1), ("platz", hc["placed"] == 1)):
        t = hc[maske]
        if len(t):
            z = t.iloc[0]                                   # v ist nach Datum absteigend sortiert
            r = _num(rating_heute, 1)
            return {"kind": art, "val": _num(z["valeur"], 1), "pos": _num(z["finish_pos"], 0),
                    "date": z["date"].strftime("%Y-%m-%d"), "course": _txt(z["hippodrome"]),
                    "diff": _num(r - z["valeur"], 1) if r is not None else None}
    return None


def _duell_bilanz(duelle: list[dict]) -> dict | None:
    """Je heutigem Gegner das letzte Duell: Abstand damals ± Verschiebung des Gewichtsunterschieds (1 kg = 1 Länge)
    -> heute erwarteter Abstand (+ = vor dem Gegner). Zusammenfassung: vorne / hinten erwartet."""
    if not duelle:
        return None
    letzte = {}
    for d in sorted(duelle, key=lambda d: d["date"], reverse=True):
        letzte.setdefault(d["rival"], d)
    je = []
    for r, d in letzte.items():
        erw = (d["diff_l"] - (d["shift"] or 0)) if d["diff_l"] is not None else None
        je.append({"rival": r, "rival_no": d["rival_no"], "date": d["date"], "diff_l": d["diff_l"],
                   "shift": d["shift"], "exp_l": _num(erw, 1),
                   "n": sum(1 for x in duelle if x["rival"] == r)})
    je.sort(key=lambda e: -(e["exp_l"] if e["exp_l"] is not None else -99))
    vorne = sum(1 for e in je if e["exp_l"] is not None and e["exp_l"] > 0)
    hinten = sum(1 for e in je if e["exp_l"] is not None and e["exp_l"] < 0)
    return {"rivals": je, "ahead": vorne, "behind": hinten, "n": len(je)}


def _boden_nah(a, b) -> bool:
    """Boden innerhalb einer Stufe (Very fast – Fast – Slow – Very slow); PSF nur mit PSF."""
    a, b = going_klasse(a), going_klasse(b)
    if "PSF" in (a, b):
        return a == b
    return abs(GOING_STUFE.get(a, 1) - GOING_STUFE.get(b, 1)) <= 1


def _kg_je_laenge(going, distanz) -> float:
    return rtr_arr._kpl(going_klasse(going), rtr_arr.distance_group(_num(distanz)), vorgabe_fast=True)


def indirekte_basis(h: pd.DataFrame, heute: pd.Timestamp) -> pd.DataFrame:
    """Läufe der letzten INDIREKT_TAGE in der vorderen Feldhälfte (rel. Platzierung > INDIREKT_REL_MIN) mit
    Längen hinter dem Sieger und Gewicht – die Grundlage der indirekten Duelle."""
    if not len(h):
        return pd.DataFrame()
    g = h[(h["date"] >= heute - timedelta(days=INDIREKT_TAGE)) & (h["rel_place"] > INDIREKT_REL_MIN)].copy()
    g["lb"] = g["lengths_behind"].where(g["finish_pos"] != 1, 0.0)
    g = g.dropna(subset=["lb", "weight_kg"])
    g["kpl"] = [_kg_je_laenge(a, b) for a, b in zip(g["going_pmu"], g["distance_m"])]
    return g[["race_id", "date", "horse_id", "horse", "lb", "weight_kg", "going_pmu", "distance_m", "kpl"]]


def _indirekte_duelle(basis: pd.DataFrame, heute_gew: dict, going_heute, distanz_heute) -> dict:
    """Je heutigem Starter: Vergleich mit heutigen Gegnern über gemeinsame frühere Gegner.
    Leistung gegen den gemeinsamen Gegner in kg = Längen vor ihm × kg je Länge (Boden × Distanz) + Mehrgewicht;
    Pferd − Gegner über denselben gemeinsamen Gegner, nur Rennpaare mit ±INDIREKT_DIST_M und Boden innerhalb einer
    Stufe; heute erwartet = Ø dieser Differenzen − heutiges Mehrgewicht (kg), in Längen mit kg je Länge von heute."""
    if basis is None or not len(basis) or len(heute_gew) < 2:
        return {}
    ids = set(heute_gew)
    eigen = basis[basis["horse_id"].isin(ids)]
    if not len(eigen):
        return {}
    # Paare (heutiges Pferd, gemeinsamer Gegner) im selben Rennen
    p = eigen.merge(basis, on="race_id", suffixes=("", "_c"))
    p = p[(p["horse_id_c"] != p["horse_id"]) & ~p["horse_id_c"].isin(ids)]
    if not len(p):
        return {}
    # Leistung gegenüber dem gemeinsamen Gegner (kg, + = besser)
    p["perf"] = (p["lb_c"] - p["lb"]) * p["kpl"] + (p["weight_kg"] - p["weight_kg_c"])
    a = p[["horse_id", "horse_id_c", "race_id", "perf", "going_pmu", "distance_m"]]
    v = a.merge(a, on="horse_id_c", suffixes=("", "_r"))
    v = v[(v["horse_id"] != v["horse_id_r"]) & (v["race_id"] != v["race_id_r"])]
    if not len(v):
        return {}
    boden = pd.Series([_boden_nah(x, y) for x, y in zip(v["going_pmu"], v["going_pmu_r"])], index=v.index)
    ok = ((v["distance_m"] - v["distance_m_r"]).abs() <= INDIREKT_DIST_M) & boden
    v = v[ok]
    if not len(v):
        return {}
    v = v.assign(diff=v["perf"] - v["perf_r"])               # Pferd besser als heutiger Gegner (kg)
    kpl_heute = _kg_je_laenge(going_heute, distanz_heute)
    namen = basis.drop_duplicates("horse_id").set_index("horse_id")["horse"]
    out = {}
    for (hid, rid), g in v.groupby(["horse_id", "horse_id_r"]):
        w_i, w_r = heute_gew.get(hid, {}).get("weight"), heute_gew.get(rid, {}).get("weight")
        damals = float(g["diff"].mean())
        mehr = (w_i - w_r) if w_i is not None and w_r is not None else 0.0
        heute_kg = damals - mehr
        out.setdefault(hid, []).append({
            "rival": _txt(namen.get(rid)), "rival_no": heute_gew.get(rid, {}).get("no"),
            "n": int(len(g)), "common": sorted({_txt(namen.get(c)) for c in g["horse_id_c"]} - {None}),
            "then_kg": _num(damals, 1), "w_today": _num(mehr, 1),
            "exp_kg": _num(heute_kg, 1), "exp_l": _num(heute_kg / kpl_heute, 1) if kpl_heute else None})
    for hid, liste in out.items():
        liste.sort(key=lambda e: -(e["exp_kg"] or 0))
        out[hid] = {"rivals": liste, "n": len(liste),
                    "ahead": sum(1 for e in liste if (e["exp_kg"] or 0) > 0),
                    "behind": sum(1 for e in liste if (e["exp_kg"] or 0) < 0),
                    "kpl": _num(kpl_heute, 2)}
    return out


def _trainer_tabelle(v: pd.DataFrame, heute_wert) -> list[dict]:
    """Pferd nach Trainer mit dem Zeitraum, in dem das Pferd dort war (erster bis letzter Lauf), neuester zuerst."""
    if not len(v) or "trainer_key" not in v:
        return []
    zeilen = []
    for k, t in v.dropna(subset=["trainer_key"]).groupby("trainer_key"):
        zeilen.append({"label": str(t["trainer"].iloc[0] if "trainer" in t and pd.notna(t["trainer"].iloc[0]) else k).title(),
                       "key": k, "today": bool(k == heute_wert), **_rec(t),
                       "from": t["date"].min().strftime("%Y-%m-%d"), "to": t["date"].max().strftime("%Y-%m-%d")})
    return sorted(zeilen, key=lambda z: z["to"], reverse=True)


def _tabelle(g: pd.DataFrame, spalte: str, heute_wert, anzeige) -> list[dict]:
    """Bilanz je Ausprägung einer Spalte (z. B. alle Böden eines Pferdes), heutige markiert."""
    if g.empty or spalte not in g:
        return []
    zeilen = []
    for k, t in g.dropna(subset=[spalte]).groupby(spalte):
        zeilen.append({"label": anzeige(k), "key": k, "today": bool(k == heute_wert), **_rec(t)})
    return sorted(zeilen, key=lambda x: (not x["today"], -x["runs"]))


def _rang(werte: list, wert) -> int | None:
    """Rang (1 = bester, höher ist besser) unter den übrigen Werten."""
    if wert is None:
        return None
    return 1 + sum(1 for w in werte if w is not None and w > wert)


def _prognose_rennen(pg: dict | None) -> tuple[dict | None, dict]:
    """PMU-Prognose eines Rennens für die Race Card: (Rennteil, {Startnummer: Starterteil}).
    Konsens der Tippgeber: Punkte je Liste = Listenlänge − Position + 1 (Borda), Rangfolge nach Punkten."""
    if not pg:
        return None, {}
    je = {}
    for z in pg.get("selection") or []:
        je.setdefault(z["no"], {})["sel"] = {"rank": z.get("rank"), "cote": z.get("cote"), "cote_dec": z.get("cote_dec")}
    tipps = pg.get("tips") or []
    punkte: dict[int, float] = {}
    for t in tipps:
        L = len(t["nos"])
        for pos, no in enumerate(t["nos"], 1):
            punkte[no] = punkte.get(no, 0) + (L - pos + 1)
            e = je.setdefault(no, {}).setdefault("tips", {"n": 0, "top3": 0, "pos": []})
            e["n"] += 1
            e["top3"] += pos <= 3
            e["pos"].append(pos)
    for no, e in je.items():
        if "tips" in e:
            e["tips"] = {"n": e["tips"]["n"], "of": len(tipps), "top3": e["tips"]["top3"],
                         "avg": _num(float(np.mean(e["tips"]["pos"])), 1)}
    for no, txt in (pg.get("cribles") or {}).items():
        je.setdefault(int(no), {})["crible"] = txt
    konsens = sorted(punkte, key=lambda n: -punkte[n])
    for no in konsens:                                    # Platz im Konsens, gleiche Punkte = gleicher Platz
        je.setdefault(no, {})["konsens"] = {"pos": 1 + sum(1 for m in punkte if punkte[m] > punkte[no]),
                                            "of": len(konsens), "pts": _num(punkte[no], 0)}
    rennen = {"text": pg.get("text"), "selection": pg.get("selection") or [],
              "tips": [{"source": t["source"], "nos": t["nos"]} for t in tipps],
              "consensus": konsens[:6], "cribles_ohne": pg.get("cribles_ohne") or []}
    return rennen, je


def baue_daten(hist: pd.DataFrame, races_heute: pd.DataFrame, runners_heute: pd.DataFrame,
               tag: date, silks: dict | None = None, prognosen: dict | None = None) -> dict:
    """prognosen: {(Reunion, Rennen): pmu.prognose(...)} – PMU-Prognosen (cote probable, Kommentar, Tipps)."""
    heute = pd.Timestamp(tag)
    silks = silks or {}
    prognosen = prognosen or {}
    h = hist[hist["date"] < heute].copy() if not hist.empty else hist
    if len(h) and "early_pct" in h:                     # Rennverlauf je früherem Rennen (Norm aus der ganzen Historie)
        h = rennverlauf(h, h)
    if h.empty:
        h = pd.DataFrame(columns=["date", "horse_id", "trainer_key", "jockey_key", "sire_key", "dam_sire_key",
                                  "cross_key", "course_key", "going_pmu", "dist_bucket", "dist_group", "racetype", "age_grp",
                                  "won", "placed", "odds_final", "distance_m", "finish_pos", "race_id",
                                  "lengths_behind", "odds_rank", "prize_won", "epr_prev", "weight_kg", "owner_key",
                                  "breeder_key", "konfig", "draw", "rel_place", "valeur", "horse"])

    # A/E-Tabellen: Trainer und Jockey je Zeitfenster, Abstammung über die ganze Historie
    ae = {}
    for rolle in ("trainer", "jockey", "owner", "breeder"):
        for tage in AE_FENSTER:
            sub = h[h["date"] >= heute - timedelta(days=tage)]
            ae[(rolle, tage)] = gruppen(sub, [rolle + "_key"])
    ae_abst = {rolle: gruppen(h, [rolle + "_key"]) for rolle in ("sire", "dam_sire", "cross")}
    # Abstammung: verschiedene Pferde je Linie und – nur 3-jährige Nachkommen – Ø ihrer höchsten Valeur als 3-Jährige
    # (max je Pferd im Alter von 3 Jahren, dann Ø über die Pferde)
    abst_extra = {}
    for rolle in ("sire", "dam_sire", "cross"):
        k_ = rolle + "_key"
        if len(h) and k_ in h:
            mit = h.dropna(subset=[k_])
            pferde = mit.groupby(k_)["horse_id"].nunique()
            je3 = mit[mit["age"] == 3].groupby([k_, "horse_id"])["valeur"].max().dropna()
            g3 = je3.groupby(level=0)
            abst_extra[rolle] = pd.DataFrame({"horses": pferde, "horses3": g3.size(), "max_val3": g3.mean()})
        else:
            abst_extra[rolle] = pd.DataFrame(columns=["horses", "horses3", "max_val3"])

    # Population: Ø €/Lauf über alle Personen bzw. Linien (je Gruppe und Zeitfenster, ab POP_MIN_LAEUFE Läufen)
    # und Ø max Val 3j über alle Linien (ab POP_MIN_PFERDE 3-jährigen Nachkommen) – Basis der Indizes €/L+ und Val+
    def pop_epr(gr: dict) -> float | None:
        w = [r["epr"] for r in gr.values() if r["runs"] >= POP_MIN_LAEUFE and r["epr"] is not None]
        return float(np.mean(w)) if w else None
    pop = {f"{rolle}_d{t}": pop_epr(ae[(rolle, t)]) for rolle in ("trainer", "jockey", "owner", "breeder")
           for t in AE_FENSTER}
    for rolle in ("sire", "dam_sire", "cross"):
        pop[f"{rolle}_all"] = pop_epr(ae_abst[rolle])
        e = abst_extra[rolle]
        w = e.loc[e["horses3"].fillna(0) >= POP_MIN_PFERDE, "max_val3"].dropna() if len(e) else pd.Series(dtype=float)
        pop[f"{rolle}_val3"] = float(w.mean()) if len(w) else None

    def index(wert, basis):
        """100 = Durchschnitt der Population, > 100 überdurchschnittlich."""
        return _num(100 * wert / basis, 0) if wert is not None and basis else None
    # Startbox: Ø relative Platzierung je Konfiguration × Box
    box = (h.dropna(subset=["konfig", "draw", "rel_place"]).groupby(["konfig", "draw"])["rel_place"]
           .agg(["mean", "count"]) if len(h) and "konfig" in h else pd.DataFrame(columns=["mean", "count"]))
    # Vergleich für Gewinn je Lauf: Ø aller Läufe im selben Zeitfenster (Trainer/Jockey) bzw. der ganzen Historie
    pw = pd.to_numeric(h["prize_won"], errors="coerce") if "prize_won" in h else pd.Series(dtype=float)
    epr_ref = {f"d{t}": _num(pw[h["date"] >= heute - timedelta(days=t)].mean(), 0) for t in AE_FENSTER}
    epr_ref["all"] = _num(pw.mean(), 0)
    # Klasse: Verteilung über alle früheren Rennen (Ø Valeur, Ø Gewinn je Lauf der Teilnehmer)
    rennen_kl = h.drop_duplicates("race_id") if len(h) else h
    kl_vert = {c: np.sort(pd.to_numeric(rennen_kl[c], errors="coerce").dropna().to_numpy())
               if c in rennen_kl else np.array([]) for c in ("cls_val", "cls_epr_kl")}
    # Basis €/L+: Ø (über alle früheren Rennen, log-gemittelt) der Rennstärke cls_epr_kl
    epr_rennen = epr_aus_log(np.log1p(kl_vert["cls_epr_kl"]))
    # Klasse heute: €/L der Verbindungen in den KLASSE_TAGE davor, erster Start je Pferd, Beginn der Historie
    h_kl = h[h["date"] >= heute - timedelta(days=KLASSE_TAGE)]
    verb_epr = {rolle: h_kl.groupby(rolle + "_key")["prize_won"].agg(["count", "mean"]) if rolle + "_key" in h_kl
                else pd.DataFrame(columns=["count", "mean"]) for rolle in KLASSE_VERBINDUNG}
    beginn = h["date"].min() if len(h) else heute
    val_rennen = float(kl_vert["cls_val"].mean()) if len(kl_vert["cls_val"]) else None
    pop["rennen_epr"], pop["rennen_val"] = epr_rennen, val_rennen

    ind_basis = indirekte_basis(h, heute)                     # Grundlage der indirekten Duelle
    kal = pace_kalibrierung(h)
    bias = bahn_bias(h)

    # Vorlieben: Jockey/Trainer die letzten zwei Jahre, Vater und Muttervater die gesamte Historie
    h_jt = h[h["date"] >= heute - timedelta(days=VORLIEBEN_JT_TAGE)]
    pref = {
        "trainer_jockey": gruppen(h_jt, ["trainer_key", "jockey_key"]),
        "trainer_course": gruppen(h_jt, ["trainer_key", "course_key"]),
        "trainer_type": gruppen(h_jt, ["trainer_key", "racetype"]),
        "trainer_age": gruppen(h_jt, ["trainer_key", "age_grp"]),
        "sire_age": gruppen(h, ["sire_key", "age_grp"]),
        "dam_sire_age": gruppen(h, ["dam_sire_key", "age_grp"]),
        "jockey_course": gruppen(h_jt, ["jockey_key", "course_key"]),
        "sire_dist": gruppen(h, ["sire_key", "dist_group"]),
        "sire_going": gruppen(h, ["sire_key", "going_pmu"]),
        "dam_sire_dist": gruppen(h, ["dam_sire_key", "dist_group"]),
        "dam_sire_going": gruppen(h, ["dam_sire_key", "going_pmu"]),
        # Gesamtbilanz je Person/Linie im selben Zeitraum: Maßstab für auffällige Vorlieben (ae_abweichung)
        "trainer": gruppen(h_jt, ["trainer_key"]),
        "jockey": gruppen(h_jt, ["jockey_key"]),
        "sire": gruppen(h, ["sire_key"]),
        "dam_sire": gruppen(h, ["dam_sire_key"]),
    }

    rh = races_heute.drop_duplicates("race_id").copy()
    ru = runners_heute.drop_duplicates(["race_id", "saddle_no"]).copy()
    for c in ["horse", "jockey", "trainer", "owner", "breeder"]:
        ru[c + "_key"] = norm_name(ru[c]) if c in ru else pd.Series(pd.NA, index=ru.index, dtype="string")
    rh["konfig"] = konfig_schluessel(rh) if len(rh) else None
    if len(rh) and "konfig" in h:                          # Bahnart fehlt heute: an die Historie angleichen
        rh["konfig"] = konfig_angleichen(rh["konfig"], h["konfig"])
    ru = abstammung_keys(ru)
    ru["horse_id"] = ru["horse_key"].fillna("?") + "|" + ru["sire_key"].fillna("?")
    ids = set(ru["horse_id"])
    hh = h[h["horse_id"].isin(ids)].sort_values("date", ascending=False)
    per_pferd = {k: g for k, g in hh.groupby("horse_id", sort=False)}

    # Gegner-Verfolgung: Felder der letzten Läufe und die späteren Starts dieser Gegner
    rennen_ids = set(hh.groupby("horse_id").head(GEGNER_LAEUFE)["race_id"]) if len(hh) else set()
    felder = h[h["race_id"].isin(rennen_ids)]
    h_rennen = {k: g for k, g in felder.groupby("race_id")}
    gegner_ids = set(felder["horse_id"])
    h_pferde = {k: g.sort_values("date") for k, g in h[h["horse_id"].isin(gegner_ids)].groupby("horse_id")}

    meetings: dict[int, dict] = {}
    races_out = {}
    for _, r in rh.sort_values(["reunion", "race_no"]).iterrows():
        gb = going_klasse(r.get("going"))                # Bodengruppe laut PMU-Begriff (fehlt er: FAST)
        gb_angenommen = rtr_arr.boden_gruppe(r.get("going")) is None
        db = dist_bucket(r.get("distance_m"))
        dg = rtr_arr.distance_group(_num(r.get("distance_m")))   # Distanzgruppe der Vorlieben
        rt = kategorie(r.get("categorie"))
        course = norm_name(pd.Series([r.get("hippodrome")])).iloc[0]
        dist = _num(r.get("distance_m"), 0)
        konfig_heute = r.get("konfig")
        starters = []
        feld_heute = ru[ru["race_id"] == r["race_id"]]
        nr_heute = (feld_heute["status"].astype("string").str.upper().fillna("").eq("NON_PARTANT")
                    if "status" in feld_heute else pd.Series(False, index=feld_heute.index))
        # Heutige Gegner, die schon früher gegeneinander liefen: Rennen mit mindestens zwei heutigen Startern
        heute_gew = {z["horse_id"]: {"weight": _num(z.get("weight_kg"), 1), "no": _num(z.get("saddle_no"), 0)}
                     for _, z in feld_heute[~nr_heute].iterrows()}
        treffen = hh[hh["horse_id"].isin(set(heute_gew)) & (hh["date"] >= heute - timedelta(days=DUELL_TAGE))
                     ]
        if dist is not None and len(treffen):
            treffen = treffen[(treffen["distance_m"] - dist).abs() <= DUELL_DIST_M]
        if DUELL_BODEN and len(treffen):
            treffen = treffen[np.array([_boden_nah(b, gb) for b in treffen["going_pmu"]], dtype=bool)]
        duell_rennen = {k: g for k, g in treffen.groupby("race_id") if g["horse_id"].nunique() >= 2}
        indirekt = _indirekte_duelle(ind_basis, heute_gew, r.get("going"), r.get("distance_m"))
        # Klasse des heutigen Rennens: Ø Valeur und Ø Gewinn je Lauf (KLASSE_TAGE) der Starter wie klassen_wert
        epr_heute, epr_eigen, epr_betrag = [], 0, []
        for _, z in feld_heute[~nr_heute].iterrows():
            v_ = per_pferd.get(z["horse_id"])
            eigen = None
            if v_ is not None and len(v_):
                j_ = v_[v_["date"] >= heute - timedelta(days=KLASSE_TAGE)]
                if len(j_):                                  # angezeigter Betrag: nur Läufe der KLASSE_TAGE
                    epr_betrag.append(float(j_["prize_won"].sum()) / len(j_))
                if ist_erfahren([heute], [v_["date"].min()], beginn, [z.get("age")])[0]:
                    b_ = j_ if len(j_) else v_                # ohne Lauf im Jahr: alle früheren Läufe
                    eigen = float(np.log1p(float(b_["prize_won"].sum()) / len(b_)))
            if eigen is not None:
                epr_heute.append(eigen)
                epr_eigen += 1
                continue
            runs_, epr_ = {}, {}
            for rolle, tab in verb_epr.items():
                k_ = z.get(rolle + "_key")
                ok_ = pd.notna(k_) and k_ in tab.index
                runs_[rolle], epr_[rolle] = (tab.loc[k_, "count"], tab.loc[k_, "mean"]) if ok_ else (0, np.nan)
            w_ = float(verbindung_log(runs_, epr_))
            if not np.isnan(w_):
                epr_heute.append(w_)
        val_heute = pd.to_numeric(feld_heute.loc[~nr_heute, "rating"], errors="coerce").dropna() \
            if "rating" in feld_heute else pd.Series(dtype=float)
        epr_k = epr_aus_log(epr_heute)
        klasse = {"val": _num(val_heute.mean(), 1) if len(val_heute) else None, "val_n": int(len(val_heute)),
                  "epr": _num(float(np.mean(epr_betrag)), 0) if epr_betrag else None, "epr_n": len(epr_betrag),
                  "epr_base": _num(epr_k, 0) if epr_k is not None else None, "epr_base_n": len(epr_heute),
                  "epr_own": epr_eigen, "n": len(heute_gew)}
        klasse["val_pct"] = _perzentil(kl_vert["cls_val"], klasse["val"])
        klasse["epr_pct"] = _perzentil(kl_vert["cls_epr_kl"], klasse["epr_base"])
        klasse["epr_idx"] = index(klasse["epr_base"], epr_rennen)
        klasse["val_idx"] = index(klasse["val"], val_rennen)
        prono_r, prono_je = _prognose_rennen(prognosen.get((int(r["reunion"]), int(r["race_no"]))))
        for _, p in feld_heute.sort_values("saddle_no").iterrows():
            hid, tk, jk, sk = p["horse_id"], p["trainer_key"], p["jockey_key"], p["sire_key"]
            dk, xk = p["dam_sire_key"], p["cross_key"]
            vorher = per_pferd.get(hid, pd.DataFrame())
            form = []
            for n, (z, extra) in enumerate(formzeilen_auswahl(vorher, course, dist, gb)):
                f = _formzeile(z, p.get("weight_kg"))
                f["same"] = gleich_heute(z, course, dist, gb)     # K/D/B: Kurs+Belag, Distanz ±100 m, Bodengruppe
                f["extra"] = extra                                 # zusätzlich gezeigt: letzter Lauf auf K/D/B
                if extra and z["race_id"] not in h_rennen:         # ältere Läufe: Feld und Gegner nachladen
                    _feld_nachladen(z["race_id"], h, h_rennen, h_pferde)
                f["rivals"] = _gegner(z, h_rennen, h_pferde, heute) if n < GEGNER_LAEUFE or extra else None
                f["rivals_stat"] = _gegner_bilanz(f["rivals"])     # Bilanz über das ganze Feld
                f["rivals"] = gegner_auswahl(f["rivals"], f["pos"])  # gezeigt: je 2 wieder gelaufene davor/dahinter
                for g_ in f["rivals"] or []:                         # Klasse des nächsten Starts als Index
                    nx = g_["next"]
                    nx["epr_idx"], nx["val_idx"] = index(nx.pop("cls_epr_kl"), epr_rennen), index(nx.pop("cls_val"), val_rennen)
                bz = (box.loc[(z["konfig"], z["draw"])] if pd.notna(z.get("draw")) and pd.notna(z.get("konfig"))
                      and (z["konfig"], z["draw"]) in box.index else None)
                f["draw_stat"] = box_urteil(bz["mean"], bz["count"]) if bz is not None else None
                f["cls_val_pct"] = _perzentil(kl_vert["cls_val"], f["cls_val"])
                epr_kl_ = f.pop("cls_epr_kl")                        # nur Basis des Index, nicht angezeigt
                f["cls_epr_pct"] = _perzentil(kl_vert["cls_epr_kl"], epr_kl_)
                f["cls_epr_idx"] = index(epr_kl_, epr_rennen)         # Rennstärke: 100 = Ø aller Rennen
                f["cls_val_idx"] = index(f["cls_val"], val_rennen)    # Ø Valeur der Teilnehmer: 100 = Ø aller Rennen
                form.append(f)
            duelle = _duelle(vorher[vorher["race_id"].isin(set(duell_rennen))], duell_rennen, heute_gew, hid) \
                if len(vorher) and hid in heute_gew else []
            siege = vorher[vorher["won"] == 1] if len(vorher) else vorher
            c_sieg = bool(len(siege) and (siege["course_key"] == course).any())
            d_sieg = bool(len(siege) and dist is not None and ((siege["distance_m"] - dist).abs() <= 100).any())
            badges = (["CD"] if c_sieg and d_sieg and ((siege["course_key"] == course)
                                                         & ((siege["distance_m"] - dist).abs() <= 100)).any()
                      else [b for b, ok in (("C", c_sieg), ("D", d_sieg)) if ok])
            if len(vorher) and bool(vorher.iloc[0]["favourite"]) and vorher.iloc[0]["won"] != 1:
                badges.append("BF")
            fr = vorher["early_pct"].dropna().head(STIL_LAEUFE) if len(vorher) else pd.Series(dtype=float)
            rtr_s = vorher["rtr"].dropna() if len(vorher) and "rtr" in vorher else pd.Series(dtype=float)
            ark = gewichteter_schnitt(vorher, "arr", r.get("distance_m"), gb) if len(vorher) else \
                gewichteter_schnitt(pd.DataFrame(), "arr", None, None)
            w_heute = p.get("weight_kg")
            # TR-Kachel: ohne Läufe mit gedeckeltem Upgrade (falsch gelaufene Rennen, TR unsicher)
            tr_laeufe = (vorher[vorher["tr"].notna() & (vorher["tr_gedeckelt"].fillna(0) != 1
                                                        if "tr_gedeckelt" in vorher else True)]
                         if len(vorher) and "tr" in vorher else pd.DataFrame(columns=["tr", "distance_m"]))
            trk = tr_schnitt(tr_laeufe, r.get("distance_m"), gb)
            early = float(fr.mean()) if len(fr) else None
            st_k, st_l = stil(early)
            # Ø der bereinigten Kennzahlen aus den letzten Läufen mit Tracking (ohne ausgerittene)
            zuverl = vorher[vorher["tracking"] & ~vorher["ausgeritten"].fillna(False).astype(bool)] if len(vorher) else vorher

            def schnitt(spalte, streuung=False):
                """Gewichteter Ø der letzten Läufe, zum Nullpunkt geschrumpft:
                Gewicht nach Distanz- und Going-Ähnlichkeit zu heute (lauf_gewichte), SCHNITT_PRIOR wirkt wie
                ein Lauf mit 0. Ein Lauf bei +2,0 landet so unter drei Läufen bei +1,5."""
                if not len(zuverl) or spalte not in zuverl:
                    return None
                w = zuverl[[c for c in (spalte, "distance_m", "going_pmu") if c in zuverl]] \
                    .dropna(subset=[spalte]).head(SCHNITT_LAEUFE)
                if not len(w):
                    return None
                if streuung:
                    return _num(w[spalte].std(), 2) if len(w) >= 2 else None
                gew = lauf_gewichte(w, r.get("distance_m"), gb)
                return _num(float((gew * w[spalte]).sum() / (gew.sum() + SCHNITT_PRIOR)), 2)

            def q(tab, key, rolle=None):
                """Vorliebe aus pref[tab]; mit rolle zusätzlich die Abweichung vom Rest dieser Person/Linie
                (key[0] ist ihr Schlüssel bzw. für den Jockey key[1] bei trainer_jockey)."""
                rec_ = _leer() if any(_txt(k) is None for k in key) else pref[tab].get(key, _leer())
                if rolle is None:
                    return rec_
                ek = key[1] if (rolle == "jockey" and tab == "trainer_jockey") else key[0]
                return {**rec_, "dev": ae_abweichung(rec_, pref[rolle].get(ek) if _txt(ek) else None)}

            ok_, bk_ = p.get("owner_key"), p.get("breeder_key")
            ae_p = {}
            for rolle, key in (("trainer", tk), ("jockey", jk), ("owner", ok_), ("breeder", bk_)):
                ae_p[rolle] = {}
                for t in AE_FENSTER:
                    rec_ = ae[(rolle, t)].get(key, _leer()) if _txt(key) else _leer()
                    ae_p[rolle][f"d{t}"] = {**rec_, "epr_idx": index(rec_["epr"], pop[f"{rolle}_d{t}"])}
            for rolle in ae_p:
                ae_p[rolle]["trend"] = _ae_trend(ae_p[rolle]["d30"], ae_p[rolle]["d365"])
            ae_p["pedigree"] = {}
            for rolle, key in (("sire", sk), ("dam_sire", dk), ("cross", xk)):
                e_ = abst_extra[rolle].loc[key] if _txt(key) and key in abst_extra[rolle].index else None
                rec_ = ae_abst[rolle].get(key, _leer()) if _txt(key) else _leer()
                mv3 = _num(e_["max_val3"], 1) if e_ is not None else None
                ae_p["pedigree"][rolle] = {**rec_, "epr_idx": index(rec_["epr"], pop[f"{rolle}_all"]),
                                           "horses": int(e_["horses"]) if e_ is not None and pd.notna(e_["horses"]) else 0,
                                           "horses3": int(e_["horses3"]) if e_ is not None and pd.notna(e_["horses3"]) else 0,
                                           "max_val3": mv3, "max_val3_idx": index(mv3, pop[f"{rolle}_val3"])}
            dr_ = _num(p.get("draw"), 0)
            bx = box.loc[(konfig_heute, dr_)] if dr_ is not None and (konfig_heute, dr_) in box.index else None
            box_p = ({**box_urteil(bx["mean"], bx["count"]), "ok": bool(bx["count"] >= BOX_MIN_LAEUFE)}
                     if bx is not None else None)
            jockey_pferd = (_rec(vorher[vorher["jockey_key"] == jk]) if len(vorher) and _txt(jk)
                            and (vorher["jockey_key"] == jk).any() else _leer())
            status = str(p.get("status") or "").upper()
            inc = str(p.get("incident") or "").upper()
            starts, earn = _num(p.get("starts"), 0), _num(p.get("earnings_eur"), 0)
            starters.append({
                "no": _num(p.get("saddle_no"), 0), "draw": _num(p.get("draw"), 0), "draw_stat": box_p,
                "horse": _txt(p.get("horse")), "age": _num(p.get("age"), 0), "sex": _txt(p.get("sex")),
                "silks": silks.get(_txt(p.get("silks_url"))),
                "weight": _num(p.get("weight_kg"), 1),
                "rating": _num(p.get("rating"), 1), "blinkers": _txt(p.get("blinkers")),
                "rating_adj": _adj(p.get("rating"), w_heute),      # Valeur − heutiges Gewicht + GEWICHT_REF
                "hcp_mark": handicap_marke(vorher, p.get("rating")),
                "jockey": _txt(p.get("jockey")), "trainer": _txt(p.get("trainer")), "owner": _txt(p.get("owner")), "breeder": _txt(p.get("breeder")),
                "sire": _txt(p.get("sire")), "dam": _txt(p.get("dam")), "dam_sire": _txt(p.get("dam_sire")),
                "form": _txt(p.get("form")),
                "career": _karriere(vorher, heute),
                "starts": starts, "wins": _num(p.get("wins"), 0),
                "places": _num(p.get("places"), 0), "earnings": earn,
                "earn_per_start": _num(earn / starts, 0) if earn and starts else None,
                "nr": "NON_PARTANT" in (status, inc),
                "days": int((heute - vorher.iloc[0]["date"]).days) if len(vorher) else None,
                "badges": badges,
                "changes": _wechsel(p, vorher.iloc[0] if len(vorher) else None),
                "style": st_k, "style_label": st_l, "early": _num(early, 2), "early_runs": int(len(fr)),
                "rtr": {"raw": _num(rtr_s.iloc[0], 1) if len(rtr_s) else None,
                        "adj": _adj(rtr_s.iloc[0], w_heute) if len(rtr_s) else None,
                        "prev": _num(rtr_s.iloc[1], 1) if len(rtr_s) > 1 else None, "runs": int(len(rtr_s))},
                "arr": {"avg": _num(ark["avg"], 1), "adj": _adj(ark["avg"], w_heute),
                        "sd": _num(ark["sd"], 1), "runs": ark["runs"], "best": _num(ark["best"], 1),
                        "last": _num(vorher.iloc[0].get("arr"), 1) if len(vorher) else None},
                "tr": {"avg": _num(trk["avg"], 0), "heute": _tr_heute(trk["avg"], w_heute),
                       "sd": _num(trk["sd"], 1), "runs": trk["runs"],
                       "best": _num(tr_laeufe["tr"].head(SCHNITT_LAEUFE).max(), 0) if trk["runs"] else None,
                       "last": _num(vorher.iloc[0].get("tr"), 0) if len(vorher) else None},
                "summary": {**{k: schnitt(c) for k, c in DELTA_SPALTEN.items()},
                            **{k + "_sd": schnitt(c, True) for k, c in DELTA_SPALTEN.items()},
                            "runs": int(min(len(zuverl), SCHNITT_LAEUFE)) if len(zuverl) else 0},
                "ae": ae_p,
                "pref": {
                    "horse": {"going": _tabelle(vorher, "going_pmu", gb, going_anzeige),
                              "distance": _tabelle(vorher, "dist_group", dg, lambda d: f"{d} m"),
                              "course": [z for z in _tabelle(vorher, "course_key", course, lambda c: str(c).title())
                                         if z["today"]],                           # nur die heutige Bahn
                              "trainer": _trainer_tabelle(vorher, tk),
                              "blinkers": _tabelle(vorher.assign(blink_grp=vorher["blinkers"].map(scheuklappen_gruppe))
                                                   if len(vorher) and "blinkers" in vorher else vorher, "blink_grp",
                                                   scheuklappen_gruppe(p.get("blinkers")), str)},
                    "trainer": {"jockey": q("trainer_jockey", (tk, jk), "trainer"),
                                "course": q("trainer_course", (tk, course), "trainer"),
                                "racetype": q("trainer_type", (tk, rt), "trainer"),
                                "age": q("trainer_age", (tk, alter_gruppe(p.get("age"))), "trainer"),
                                "age_label": alter_gruppe(p.get("age"))},
                    "jockey": {"course": q("jockey_course", (jk, course), "jockey"),
                               "trainer": q("trainer_jockey", (tk, jk), "jockey"),
                               "horse": {**jockey_pferd, "dev": ae_abweichung(
                                   jockey_pferd, pref["jockey"].get(jk) if _txt(jk) else None)}},
                    "sire": {"distance": q("sire_dist", (sk, dg), "sire"), "going": q("sire_going", (sk, gb), "sire"),
                             "age": q("sire_age", (sk, alter_gruppe(p.get("age"))), "sire")},
                    "dam_sire": {"distance": q("dam_sire_dist", (dk, dg), "dam_sire"),
                                 "going": q("dam_sire_going", (dk, gb), "dam_sire"),
                                 "age": q("dam_sire_age", (dk, alter_gruppe(p.get("age"))), "dam_sire")},
                },
                "form_lines": form,
                "prono": prono_je.get(_num(p.get("saddle_no"), 0)),
                "duels": duelle,
                "duels_sum": _duell_bilanz(duelle),
                "indirect": indirekt.get(hid),
            })
        partanten = [x for x in starters if not x["nr"]]
        for k in DELTA_SPALTEN:                                   # Rang im heutigen Feld
            werte = [x["summary"][k] for x in partanten]
            for x in starters:
                x["summary"][k + "_rank"] = _rang(werte, x["summary"][k]) if not x["nr"] else None
                x["summary"][k + "_n"] = sum(w is not None for w in werte)
        for k, feld in (("rtr", "adj"), ("arr", "adj"), ("tr", "heute")):      # Rang im heutigen Feld (bereinigt)
            werte = [x[k][feld] for x in partanten]
            for x in starters:
                x[k]["rank"] = _rang(werte, x[k][feld]) if not x["nr"] else None
                x[k]["n"] = sum(w is not None for w in werte)
        werte = [x["rating_adj"] for x in partanten]             # Rating (bereinigt): Rang im heutigen Feld
        for x in starters:
            x["rating_rank"] = _rang(werte, x["rating_adj"]) if not x["nr"] else None
            x["rating_n"] = sum(w is not None for w in werte)
        for fenster in ("all", "d365"):                        # Gewinn je Lauf: Rang und Verhältnis zum Feld
            werte = [x["career"][fenster]["epr"] for x in partanten]
            vorhanden = [w for w in werte if w is not None]
            median = float(np.median(vorhanden)) if vorhanden else None
            for x in starters:
                k_ = x["career"][fenster]
                k_["rank"] = _rang(werte, k_["epr"]) if not x["nr"] else None
                k_["n"] = len(vorhanden)
                k_["rel"] = _num(k_["epr"] / median, 2) if k_["epr"] is not None and median else None
        szenario = pace_szenario(partanten, db, kal)
        b = bias["exakt"].get((course, dist)) or bias["gruppe"].get((course, db))
        b_basis = "exakt" if bias["exakt"].get((course, dist)) else ("gruppe" if b else None)
        m = meetings.setdefault(int(r["reunion"]), {"reunion": int(r["reunion"]),
                                                     "course": _txt(r.get("hippodrome")), "races": []})
        m["races"].append(r["race_id"])
        races_out[r["race_id"]] = {
            "race_id": r["race_id"], "reunion": int(r["reunion"]), "race_no": int(r["race_no"]),
            "time": _txt(r.get("post_time")), "name": _txt(r.get("race_name")), "course": _txt(r.get("hippodrome")),
            "distance": dist, "going": _txt(r.get("going")), "going_value": _txt(r.get("going_value")),
            "going_pmu": gb, "going_label": going_anzeige(gb), "going_assumed": gb_angenommen,
            "going_source": _txt(r.get("going_quelle")), "dist_bucket": db, "dist_group": dg,
            "dist_label": DIST_LABEL.get(db), "prize": _num(r.get("prize_eur"), 0), "type": rt,
            "age": _txt(r.get("conditions_age")), "sex": _txt(r.get("conditions_sexe")),
            "corde": _txt(r.get("corde")), "konfig": _txt(konfig_heute), "declared": _num(r.get("runners_declared"), 0),
            "status": _txt(r.get("statut")), "result": _txt(r.get("finish_order")),
            "runners": starters,
            "class": klasse,
            "prono": prono_r,
            "pace": szenario,
            "bias": {**b, "basis": b_basis} if b else None,
        }
    hist_von = h["date"].min() if len(h) else None
    return {
        "date": heute.strftime("%Y-%m-%d"),
        "generated": datetime.now(pmu.PARIS).strftime("%Y-%m-%d %H:%M"),
        "history": {"from": hist_von.strftime("%Y-%m-%d") if hist_von is not None else None,
                    "runs": int(len(h)), "tracked": int(h["tracking"].sum()) if "tracking" in h else 0},
        "params": {"pos_before_m": POS_VOR_FINISH_M, "ae_windows": list(AE_FENSTER), "form_runs": LETZTE_LAEUFE,
                   "style_runs": STIL_LAEUFE, "pacemaker": TEMPOMACHER, "field_ref": PACE_FELD_REF,
                   "trend_diff": TREND_DIFF, "trend_min": TREND_MIN_STARTS, "pref_jt_years": VORLIEBEN_JT_TAGE // 365,
                   "avg_runs": SCHNITT_LAEUFE, "rivals_runs": GEGNER_LAEUFE, "class_days": KLASSE_TAGE, "ind_days": INDIREKT_TAGE,
                   "ind_dist": INDIREKT_DIST_M,
                   "epr_ref": epr_ref, "class_races": int(len(kl_vert["cls_epr_kl"])),
                   "pop": {k: _num(v, 1) for k, v in pop.items()}, "pop_min_runs": POP_MIN_LAEUFE,
                   "pop_min_horses": POP_MIN_PFERDE,
                   "box_min": BOX_MIN_LAEUFE, "duel_days": DUELL_TAGE, "duel_dist": DUELL_DIST_M,
                   "best_seg_m": speedfig.BEST_SEG_BEREICH_M, "beaten_l": speedfig.AUSGERITTEN_L,
                   "avg_prior": SCHNITT_PRIOR, "avg_dist_m": SCHNITT_DIST_M, "weight_ref": GEWICHT_REF, "going_stufen": SCHNITT_GOING_STUFEN, "going_psf": GOING_PSF_GRAS, "tr_upg_max": timeform_ratings.UPGRADE_MAX_LB,
                   "tr_upg_knie": timeform_ratings.UPGRADE_KNIE,
                   "styles": [{"key": k, "label": lab, "max": bis} for bis, k, lab in STIL]},
        "bias_all": bias["gesamt"],
        "meetings": sorted(meetings.values(), key=lambda m: m["reunion"]),
        "races": races_out,
    }


def kommentare_uebersetzen(daten: dict, base: Path | None = None, **kw) -> int:
    """Kommentare der Formzeilen (je Starter aus pmu_runners, französisch) ins Deutsche übersetzen, wo möglich:
    ergänzt comment_de. Rückgabe: Zahl der übersetzten Kommentare."""
    zeilen = [f for r in daten.get("races", {}).values() for x in r["runners"] for f in x["form_lines"]]
    # dazu die PMU-Prognosen: Rennkommentar und Kurzkommentare (cribles) je Starter
    rp = [r["prono"] for r in daten.get("races", {}).values() if r.get("prono")]
    sp = [x["prono"] for r in daten.get("races", {}).values() for x in r["runners"] if x.get("prono")]
    texte = ([f.get("comment") for f in zeilen] + [r.get("text") for r in rp] + [x.get("crible") for x in sp]
             + [c.get("text") for r in rp for c in r.get("cribles_ohne", [])])
    de = uebersetzen.uebersetze(texte, base, **kw)
    uebers = lambda t: de.get(t.strip()) if isinstance(t, str) and t.strip() else None
    for r in rp:
        r["text_de"] = uebers(r.get("text"))
        for c in r.get("cribles_ohne", []):
            c["text_de"] = uebers(c.get("text"))
    for x in sp:
        x["crible_de"] = uebers(x.get("crible"))
    n = 0
    for f in zeilen:
        f["comment_de"] = uebers(f.get("comment"))
        n += f["comment_de"] is not None
    return n


def trikots(urls, session: requests.Session | None = None) -> dict:
    """Trikot-Bilder (PMU 'urlCasaque') laden und als data:-URI einbetten, damit die Race Card
    ohne Internet funktioniert. Fehlende oder fehlerhafte Bilder werden übergangen."""
    import base64
    s = session or requests.Session()
    out = {}
    for u in sorted({u for u in urls if _txt(u)}):
        try:
            r = s.get(u, headers=pmu.HEADERS, timeout=15)
            typ = (r.headers.get("Content-Type") or "image/png").split(";")[0] if hasattr(r, "headers") else "image/png"
            if r.ok and typ.startswith("image/") and len(r.content) < 200_000:
                out[u] = f"data:{typ};base64," + base64.b64encode(r.content).decode()
        except requests.RequestException:
            continue
    return out


def html(daten: dict, template: Path = TEMPLATE, *, eigenstaendig: bool = True) -> str:
    """Template mit eingesetzten Daten. eigenstaendig=True ergänzt das Dokumentgerüst
    (<!doctype html> …), damit die Datei direkt im Browser geöffnet werden kann."""
    js = json.dumps(daten, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    seite = template.read_text(encoding="utf-8").replace("/*__DATA__*/null", js, 1)
    return f'<!doctype html>\n<html lang="de">\n{seite}\n</html>\n' if eigenstaendig else seite


def run(base: Path, tag=None, out: Path | None = None, *, nur_flach: bool = True,
        uebersetzen_aktiv: bool = True, claude: bool = True) -> Path:
    """Race Card für `tag` (Vorgabe: heute) bauen und als HTML speichern; mit claude=True zusätzlich die kompakte
    Claude-Version racecard_JJJJMMTT_claude.json daneben (claude_export)."""
    import pipeline as tp
    base = Path(base)
    tag = pd.to_datetime(tag).date() if tag else pmu.heute()
    print(f"PMU-Programm {tag} holen …")
    races_heute, runners_heute = programm(tag, nur_flach=nur_flach)
    if races_heute.empty:
        raise RuntimeError(f"Keine französischen {'Flach' if nur_flach else 'Galopp'}rennen am {tag}.")
    races_heute = boden_manuell_anwenden(races_heute, boden_manuell_laden(tag=tag))   # fehlt PMU-Boden: manuell
    print(f"{len(races_heute)} Rennen, {len(runners_heute)} Starter. PMU-Prognosen holen …")
    prognosen = pmu.prognosen(tag, requests.Session(), list(zip(races_heute["reunion"], races_heute["race_no"])))
    print(f"Prognosen für {len(prognosen)} von {len(races_heute)} Rennen. Historie laden …")
    std_rennen = standardzeiten.je_rennen(base)
    print(f"Standardzeiten je Konfiguration: {len(std_rennen):,} Rennen zugeordnet"
          + ("" if len(std_rennen) else " – keine Sammlung gefunden (standardzeiten.run), TR schätzt sie selbst"))
    hist = vorbereiten(tp.lade("pmu_races", base), tp.lade("pmu_runners", base),
                       tp.lade("tracking_races", base), tp.lade("tracking_runners", base),
                       tp.lade("tracking_sections", base), tp.lade("tracking_leader", base),
                       standards=std_rennen)
    silks = trikots(runners_heute.get("silks_url", pd.Series(dtype=str)).dropna())
    print(f"{len(silks)} Trikots geladen.")
    if not hist.empty:
        if "last600_diff_s" in hist:
            gp = hist["last600_diff_s"].dropna()
            if len(gp):
                print(f"Gegenprobe letzte 600 m (berechnet − offiziell): {len(gp)} Läufe, "
                      f"Median {gp.median():+.2f} s, {int((gp.abs() > speedfig.LAST600_TOLERANZ_S).sum())} verworfen "
                      f"(> {speedfig.LAST600_TOLERANZ_S} s)")
        pf = hist["path_factor"].dropna() if "path_factor" in hist else pd.Series(dtype=float)
        if len(pf):
            print(f"Wegfaktor bekannt für {len(pf)} Läufe, Median {pf.median():.3f}")
        print(tempo_delta.bericht())
        print(timeform_ratings.bericht())
        v = timeform_ratings.validierung(hist)
        if len(v):
            print("Backtest – Vorhersage des nächsten Laufs (r mit dem Platzanteil; Top-3-Quote des Bestbewerteten):")
            print(v.to_string(index=False))
    daten = baue_daten(hist, races_heute, runners_heute, tag, silks, prognosen)
    mit_k = sum(1 for r in daten["races"].values() for x in r["runners"] for f in x["form_lines"] if f.get("comment"))
    if uebersetzen_aktiv and (mit_k or prognosen):       # Übersetzung: DeepL (DEEPL_API_KEY) -> Google -> MyMemory
        print(f"Kommentare in den Formzeilen: {mit_k}, davon auf Deutsch: {kommentare_uebersetzen(daten, base)}")
    out = Path(out) if out else base / "racecards" / f"racecard_{tag:%Y%m%d}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html(daten), encoding="utf-8")
    print(f"Race Card gespeichert: {out}  ({daten['history']['runs']} historische Läufe, "
          f"davon {daten['history']['tracked']} mit Tracking)")
    if claude:                                            # kompakte JSON für den Skill rennkarten-durchgang
        import claude_export
        cj = claude_export.schreiben(daten, out.with_name(out.stem + "_claude.json"))
        print(f"Claude-Version: {cj}  ({cj.stat().st_size / 1e6:.1f} MB)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", required=True, help="Ordner mit parquet/ (z. B. der Drive-Ordner)")
    ap.add_argument("--datum", default=None, help="JJJJ-MM-TT, Vorgabe: heute")
    ap.add_argument("--out", default=None)
    ap.add_argument("--alle-galopp", action="store_true", help="auch Hindernisrennen aufnehmen")
    a = ap.parse_args()
    run(Path(a.base), a.datum, a.out, nur_flach=not a.alle_galopp)
