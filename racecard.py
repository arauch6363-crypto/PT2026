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
                   distanzgewichteter, zum Nullpunkt geschrumpfter Ø der letzten SCHNITT_LAEUFE Läufe mit Tracking.
    Finish-Index   bereinigt nach dem Modell in speedfig.py (Rennanteil gegen Par, plus Pferdeanteil)
    RTR / ARR      Ratings aus PT_Vorarbeiten (rtr_arr.py), in kg: RTR = Elo-artiges Rating nach dem Rennen,
                   ARR = Leistung im Rennen, gemessen an den Pferden im vorderen Drittel. Bereinigt nach
                   Gewicht: x_adj = x − heutiges Gewicht + GEWICHT_REF – in der Übersicht und in den
                   Formzeilen (ein früherer ARR von 36 bei heute 52 kg -> 39)
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import pmu
import rtr_arr
import speedfig
import tempo_delta

TEMPLATE = Path(__file__).with_name("racecard_template.html")

POS_VOR_FINISH_M = 400          # Messpunkt für "Position vor dem Finish"
LETZTE_LAEUFE = 7               # so viele Formzeilen je Pferd (jede mit Replay-Link)
REPLAY_NACHFRAGE_TAGE = 14      # fehlt ein Replay, wird so lange nach dem Rennen erneut gefragt
REPLAY_STUMM_MAX = 5            # so viele Rennen in Folge ohne jede Antwort -> Abfrage abbrechen
AE_FENSTER = (30, 90, 365)      # Tage
TREND_DIFF = 0.4                # A/E 30 Tage so viel über/unter 365 Tagen -> Feuer/Eis
TREND_MIN_STARTS = 5            # so viele Starts in 30 Tagen braucht der Trend
VORLIEBEN_JT_TAGE = 730         # Jockey-/Trainer-Vorlieben: letzte zwei Jahre
GEGNER_LAEUFE = 5               # für so viele der letzten Läufe werden die Gegner verfolgt
GEGNER_MAX = 3                  # so viele Gegner je Lauf (die am nächsten am Pferd waren)
SCHNITT_LAEUFE = 5              # Ø der bereinigten Kennzahlen über so viele Läufe mit Tracking
SCHNITT_PRIOR = 1.0             # Schrumpfung zum Nullpunkt: wirkt wie ein zusätzlicher Lauf mit Wert 0
SCHNITT_DIST_M = 400            # Gewicht eines Laufs = 1 / (1 + |Distanz − heute| / SCHNITT_DIST_M)
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

# PMU-Bodenbegriffe, längste zuerst ("TRES SOUPLE" vor "SOUPLE")
GOING_KLASSEN = ["TRES LEGER", "BON LEGER", "BON SOUPLE", "TRES SOUPLE", "COLLANT", "LOURD",
                 "LEGER", "SOUPLE", "BON"]
# Ersatz, wenn nur der Penetrometer-Wert bekannt ist: (bis Wert, Klasse)
GOING_NACH_WERT = [(2.8, "BON LEGER"), (3.3, "BON"), (3.6, "BON SOUPLE"), (3.9, "SOUPLE"),
                   (4.4, "TRES SOUPLE"), (99, "LOURD")]
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


def going_klasse(going, going_value) -> str | None:
    """Bodenbegriff wie bei PMU ('BON SOUPLE', 'TRES SOUPLE', …), PSF getrennt.
    Fehlt der Begriff, wird er aus dem Penetrometer-Wert abgeleitet."""
    t = unicodedata.normalize("NFKD", str(going or "")).encode("ascii", "ignore").decode().upper()
    t = re.sub(r"[^A-Z]+", " ", t).strip()
    if "PSF" in t:
        return "PSF"
    for k in GOING_KLASSEN:
        if re.search(rf"\b{k}\b", t):
            return k
    v = _num(going_value)
    if v is None:
        return None
    return next(k for bis, k in GOING_NACH_WERT if v <= bis)


def going_anzeige(k: str | None) -> str | None:
    """'TRES SOUPLE' -> 'Très souple'"""
    if not k:
        return None
    return "PSF" if k == "PSF" else k.capitalize().replace("Tres ", "Très ").replace("leger", "léger").replace("Leger", "Léger")


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


# --------------------------------------------------------------------------
# Historie vorbereiten
# --------------------------------------------------------------------------
def vorbereiten(races: pd.DataFrame, runners: pd.DataFrame, trk_races: pd.DataFrame | None = None,
                trk_runners: pd.DataFrame | None = None, trk_sections: pd.DataFrame | None = None,
                trk_leader: pd.DataFrame | None = None) -> pd.DataFrame:
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
    # Vorlieben: nur der Bodenbegriff aus dem PMU-Programm (going), nicht der Penetrometer-Wert
    r["going_pmu"] = [going_klasse(g, None) for g in r.get("going", pd.Series(None, index=r.index))]
    r["going_class"] = [going_klasse(g, v) for g, v in zip(r.get("going"), r["going_value"])]
    r["dist_bucket"] = r["distance_m"].map(dist_bucket)
    r["racetype"] = r["categorie"].map(kategorie) if "categorie" in r else None
    r["course_key"] = norm_name(r["hippodrome"])

    h = runners.drop_duplicates(["race_id", "saddle_no"], keep="last").copy()
    h["saddle_no"] = pd.to_numeric(h["saddle_no"], errors="coerce")
    for c in ["horse", "jockey", "trainer", "sire"]:
        h[c + "_key"] = norm_name(h[c]) if c in h else pd.Series(pd.NA, index=h.index, dtype="string")
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
    h = h.merge(r[["race_id", "date", "hippodrome", "course_key", "distance_m", "going", "going_value",
                   "going_pmu", "going_class", "dist_bucket", "prize_eur", "racetype", "conditions_age"]],
                on="race_id", how="inner")
    h["n_runners"] = h.groupby("race_id")["saddle_no"].transform("count")
    h["won"] = (h["finish_pos"] == 1).astype(int)
    h["placed"] = (h["finish_pos"] <= 3).astype(int)
    h["age_bucket"] = h["age"].map(age_bucket)
    fav = h.groupby("race_id")["odds_final"].transform("min")
    h["odds_rank"] = h.groupby("race_id")["odds_final"].rank(method="min")   # Rang der Eventualquote
    h["favourite"] = (h["odds_final"] == fav) & h["odds_final"].notna()

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
                            "speed_last400_kmh", "dist_vs_winner_m", "distance_covered_m", "last600_s"] if c in t]
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

    # Weg: gelaufene Meter gegenüber dem Median aller Starter im Rennen (nicht gegenüber dem Sieger)
    h["weg_med"] = h["dist_vs_winner_m"] - h.groupby("race_id")["dist_vs_winner_m"].transform("median")
    h = speedfig.berechnen(h, trk_sections)
    # ΔL600 A / ΔB200 A: verglichen innerhalb Tag × Kurs × Going, Pace/Distanz und Klasse der Gruppe korrigiert
    h = tempo_delta.berechnen(h, trk_sections)
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
    klasse = [going_klasse(g, v) for g, v in zip(r.get("going", pd.Series(None, index=r.index)),
                                                 r.get("going_value", pd.Series(None, index=r.index)))]
    r["going_category"] = [rtr_arr.GOING_KATEGORIE.get(k) for k in klasse]
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
    runs = int(len(g))
    wins = int(g["won"].sum())
    mit = g["odds_final"].notna()
    exp = float((1 / g.loc[mit, "odds_final"]).sum())
    wins_mit = int(g.loc[mit, "won"].sum())
    return {"runs": runs, "wins": wins, "places": int(g["placed"].sum()),
            "exp": _num(exp), "ae": _num(wins_mit / exp) if exp > 0 else None}


def _leer() -> dict:
    return {"runs": 0, "wins": 0, "places": 0, "exp": None, "ae": None}


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
    return pd.DataFrame(races), pd.DataFrame(runners)


# --------------------------------------------------------------------------
# Race Card bauen
# --------------------------------------------------------------------------
def _formzeile(z, replays: dict | None = None, gewicht_heute=None) -> dict:
    """Eine Formzeile. RTR/ARR bereinigt mit dem heutigen Gewicht (gewicht_heute), nicht mit dem damaligen."""
    return {
        "date": z["date"].strftime("%Y-%m-%d"), "race_id": z["race_id"],
        "replay": ((replays or {}).get(z["race_id"]) or {}).get("url"),
        "replay_ok": bool(((replays or {}).get(z["race_id"]) or {}).get("available")),
        "page": pmu.pmu_seite(z["race_id"]),
        "course": _txt(z["hippodrome"]), "dist": _num(z["distance_m"], 0),
        "going": _txt(z["going"]), "going_value": _num(z["going_value"], 1),
        "prize": _num(z["prize_eur"], 0), "type": _txt(z["racetype"]),
        "pos": _num(z["finish_pos"], 0), "ran": _num(z["n_runners"], 0),
        "margin": _num(z.get("margin"), 2), "weight": _num(z["weight_kg"], 1),
        "jockey": _txt(z.get("jockey")), "odds": _num(z["odds_final"], 1),
        "odds_rank": _num(z.get("odds_rank"), 0),
        "incident": _txt(z.get("incident")), "fav": bool(z["favourite"]),
        "tracking": bool(z["tracking"]), "unreliable": bool(z.get("ausgeritten") is True),
        "early_pos": _num(z.get("early_pos"), 0),
        "pos_before": _num(z["pos_before"], 0), "pos_before_m": _num(z["pos_before_m"], 0),
        "fifth": _num(z["fifth"], 0), "pace_ratio": _num(z["pace_ratio"], 1),
        "finish_index": _num(z["finish_index"], 1), "fi_adj": _num(z.get("fi_adj"), 1),
        "weg_med": _num(z.get("weg_med"), 1), "pos_gain": _num(z["pos_gain_800_finish"], 0),
        "l600": _num(z["speed_last600_kmh"], 2), "b200": _num(z.get("best200_kmh"), 2),
        "b200_seg": _txt(z.get("best200_seg")),
        "dl600_a": _num(z.get("d_L600_A"), 2), "dl600_k": _num(z.get("k_L600"), 2),
        "db200_a": _num(z.get("d_B200_A"), 2), "db200_k": _num(z.get("k_B200"), 2),
        "path_factor": _num(z.get("path_factor"), 3),
        "sec_mismatch": bool(z.get("last600_mismatch") is True),
        "rtr": _num(z.get("rtr"), 1), "rtr_adj": _adj(z.get("rtr"), gewicht_heute),
        "arr": _num(z.get("arr"), 1), "arr_adj": _adj(z.get("arr"), gewicht_heute),
        "rating_filled": bool(pd.isna(z.get("rating")) and pd.notna(z.get("rating_filled"))),
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


def _wechsel(p, letzter) -> list[dict]:
    """Trainerwechsel, Ausrüstungswechsel und erstmals Wallach gegenüber dem letzten Lauf."""
    if letzter is None:
        return []
    out = []
    if _txt(letzter.get("trainer_key")) and _txt(p.get("trainer_key")) and letzter["trainer_key"] != p["trainer_key"]:
        out.append({"key": "TR", "text": f"Trainerwechsel (vorher {str(letzter.get('trainer') or '').title()})"})
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


def _gegner(z, h_rennen: dict, h_pferde: dict, heute: pd.Timestamp) -> list[dict]:
    """Gegner aus einem früheren Rennen, die danach wieder gelaufen sind – die GEGNER_MAX, die
    am nächsten am Pferd ins Ziel kamen, mit ihrem nächsten Start."""
    feld = h_rennen.get(z["race_id"])
    if feld is None:
        return []
    eigen_lb = z["lengths_behind"] if pd.notna(z["lengths_behind"]) else (0.0 if z["finish_pos"] == 1 else np.nan)
    out = []
    for _, g in feld.iterrows():
        if g["horse_id"] == z["horse_id"]:
            continue
        spaeter = h_pferde.get(g["horse_id"])
        if spaeter is None:
            continue
        spaeter = spaeter[(spaeter["date"] > z["date"]) & (spaeter["date"] < heute)]
        if spaeter.empty:
            continue
        lb = g["lengths_behind"] if pd.notna(g["lengths_behind"]) else (0.0 if g["finish_pos"] == 1 else np.nan)
        abstand_l = lb - eigen_lb if pd.notna(lb) and pd.notna(eigen_lb) else np.nan
        if pd.notna(abstand_l):
            sort = abs(abstand_l)
        elif pd.notna(g["finish_pos"]) and pd.notna(z["finish_pos"]):
            sort = abs(g["finish_pos"] - z["finish_pos"]) * 2
        else:
            sort = 99
        n = spaeter.iloc[0]
        urteil = None
        if pd.notna(n["finish_pos"]) and pd.notna(n["odds_rank"]):
            urteil = "besser" if n["finish_pos"] < n["odds_rank"] else "schlechter" if n["finish_pos"] > n["odds_rank"] else "wie erwartet"
        out.append({
            "_sort": sort, "horse": _txt(g["horse"]), "pos": _num(g["finish_pos"], 0),
            "diff_l": _num(abstand_l, 2),
            "next": {"date": n["date"].strftime("%Y-%m-%d"), "course": _txt(n["hippodrome"]),
                     "dist": _num(n["distance_m"], 0), "pos": _num(n["finish_pos"], 0),
                     "ran": _num(n["n_runners"], 0), "odds_rank": _num(n["odds_rank"], 0),
                     "odds": _num(n["odds_final"], 1), "verdict": urteil},
            "more": int(len(spaeter) - 1),
        })
    out.sort(key=lambda x: x["_sort"])
    for x in out:
        x.pop("_sort")
    return out[:GEGNER_MAX]


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


def baue_daten(hist: pd.DataFrame, races_heute: pd.DataFrame, runners_heute: pd.DataFrame,
               tag: date, silks: dict | None = None, replays: dict | None = None) -> dict:
    heute = pd.Timestamp(tag)
    silks = silks or {}
    h = hist[hist["date"] < heute].copy() if not hist.empty else hist
    if h.empty:
        h = pd.DataFrame(columns=["date", "horse_id", "trainer_key", "jockey_key", "sire_key", "course_key",
                                  "going_pmu", "dist_bucket", "racetype", "won", "placed", "odds_final",
                                  "distance_m", "finish_pos", "race_id", "lengths_behind", "odds_rank"])

    # A/E-Tabellen
    ae = {}
    for rolle in ("trainer", "jockey", "sire"):
        for tage in AE_FENSTER:
            sub = h[h["date"] >= heute - timedelta(days=tage)]
            ae[(rolle, tage)] = gruppen(sub, [rolle + "_key"])

    kal = pace_kalibrierung(h)
    bias = bahn_bias(h)

    # Vorlieben: Jockey/Trainer die letzten zwei Jahre, Vater die gesamte Historie
    h_jt = h[h["date"] >= heute - timedelta(days=VORLIEBEN_JT_TAGE)]
    pref = {
        "trainer_jockey": gruppen(h_jt, ["trainer_key", "jockey_key"]),
        "trainer_course": gruppen(h_jt, ["trainer_key", "course_key"]),
        "trainer_type": gruppen(h_jt, ["trainer_key", "racetype"]),
        "jockey_course": gruppen(h_jt, ["jockey_key", "course_key"]),
        "sire_dist": gruppen(h, ["sire_key", "dist_bucket"]),
        "sire_going": gruppen(h, ["sire_key", "going_pmu"]),
    }

    rh = races_heute.drop_duplicates("race_id").copy()
    ru = runners_heute.drop_duplicates(["race_id", "saddle_no"]).copy()
    for c in ["horse", "jockey", "trainer", "sire"]:
        ru[c + "_key"] = norm_name(ru[c]) if c in ru else pd.Series(pd.NA, index=ru.index, dtype="string")
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
        gb = going_klasse(r.get("going"), None)          # Bodenbegriff laut PMU
        db = dist_bucket(r.get("distance_m"))
        rt = kategorie(r.get("categorie"))
        course = norm_name(pd.Series([r.get("hippodrome")])).iloc[0]
        dist = _num(r.get("distance_m"), 0)
        starters = []
        for _, p in ru[ru["race_id"] == r["race_id"]].sort_values("saddle_no").iterrows():
            hid, tk, jk, sk = p["horse_id"], p["trainer_key"], p["jockey_key"], p["sire_key"]
            vorher = per_pferd.get(hid, pd.DataFrame())
            form = []
            for n, (_, z) in enumerate(vorher.head(LETZTE_LAEUFE).iterrows()):
                f = _formzeile(z, replays, p.get("weight_kg"))
                f["rivals"] = _gegner(z, h_rennen, h_pferde, heute) if n < GEGNER_LAEUFE else None
                form.append(f)
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
            ar = (vorher["arr"].head(LETZTE_LAEUFE).dropna() if len(vorher) and "arr" in vorher
                  else pd.Series(dtype=float))
            w_heute = p.get("weight_kg")
            early = float(fr.mean()) if len(fr) else None
            st_k, st_l = stil(early)
            # Ø der bereinigten Kennzahlen aus den letzten Läufen mit Tracking (ohne ausgerittene)
            zuverl = vorher[vorher["tracking"] & ~vorher["ausgeritten"].fillna(False).astype(bool)] if len(vorher) else vorher

            def schnitt(spalte, streuung=False):
                """Gewichteter Ø der letzten Läufe, zum Nullpunkt geschrumpft:
                Gewicht nach Distanzähnlichkeit zu heute, SCHNITT_PRIOR wirkt wie ein Lauf mit 0.
                Ein Lauf bei +2,0 landet so unter drei Läufen bei +1,5."""
                if not len(zuverl) or spalte not in zuverl:
                    return None
                w = zuverl[[spalte, "distance_m"]].dropna(subset=[spalte]).head(SCHNITT_LAEUFE)
                if not len(w):
                    return None
                if streuung:
                    return _num(w[spalte].std(), 2) if len(w) >= 2 else None
                d_heute = _num(r.get("distance_m"))
                gew = (1 / (1 + (w["distance_m"] - d_heute).abs() / SCHNITT_DIST_M)
                       if d_heute is not None else pd.Series(1.0, index=w.index)).fillna(1.0)
                return _num(float((gew * w[spalte]).sum() / (gew.sum() + SCHNITT_PRIOR)), 2)

            def q(tab, key):
                return _leer() if any(_txt(k) is None for k in key) else pref[tab].get(key, _leer())

            ae_p = {rolle: {f"d{t}": ae[(rolle, t)].get(key, _leer()) for t in AE_FENSTER}
                    for rolle, key in (("trainer", tk), ("jockey", jk), ("sire", sk))}
            for rolle in ae_p:
                ae_p[rolle]["trend"] = _ae_trend(ae_p[rolle]["d30"], ae_p[rolle]["d365"])
            status = str(p.get("status") or "").upper()
            inc = str(p.get("incident") or "").upper()
            starts, earn = _num(p.get("starts"), 0), _num(p.get("earnings_eur"), 0)
            starters.append({
                "no": _num(p.get("saddle_no"), 0), "draw": _num(p.get("draw"), 0),
                "horse": _txt(p.get("horse")), "age": _num(p.get("age"), 0), "sex": _txt(p.get("sex")),
                "silks": silks.get(_txt(p.get("silks_url"))),
                "weight": _num(p.get("weight_kg"), 1),
                "rating": _num(p.get("rating"), 1), "blinkers": _txt(p.get("blinkers")),
                "jockey": _txt(p.get("jockey")), "trainer": _txt(p.get("trainer")), "owner": _txt(p.get("owner")),
                "sire": _txt(p.get("sire")), "dam": _txt(p.get("dam")), "form": _txt(p.get("form")),
                "starts": starts, "wins": _num(p.get("wins"), 0),
                "places": _num(p.get("places"), 0), "earnings": earn,
                "earn_per_start": _num(earn / starts, 0) if earn and starts else None,
                "odds": _num(p.get("odds_final"), 1), "odds_morning": _num(p.get("odds_morning"), 1),
                "nr": "NON_PARTANT" in (status, inc),
                "days": int((heute - vorher.iloc[0]["date"]).days) if len(vorher) else None,
                "badges": badges,
                "changes": _wechsel(p, vorher.iloc[0] if len(vorher) else None),
                "style": st_k, "style_label": st_l, "early": _num(early, 2), "early_runs": int(len(fr)),
                "rtr": {"raw": _num(rtr_s.iloc[0], 1) if len(rtr_s) else None,
                        "adj": _adj(rtr_s.iloc[0], w_heute) if len(rtr_s) else None,
                        "prev": _num(rtr_s.iloc[1], 1) if len(rtr_s) > 1 else None, "runs": int(len(rtr_s))},
                "arr": {"best": _num(ar.max(), 1) if len(ar) else None,
                        "best_adj": _adj(ar.max(), w_heute) if len(ar) else None,
                        "last": _num(vorher.iloc[0].get("arr"), 1) if len(vorher) else None,
                        "last_adj": _adj(vorher.iloc[0].get("arr"), w_heute) if len(vorher) else None,
                        "avg3": _num(ar.head(3).mean(), 1) if len(ar) else None, "runs": int(len(ar))},
                "summary": {**{k: schnitt(c) for k, c in DELTA_SPALTEN.items()},
                            **{k + "_sd": schnitt(c, True) for k, c in DELTA_SPALTEN.items()},
                            "runs": int(min(len(zuverl), SCHNITT_LAEUFE)) if len(zuverl) else 0},
                "ae": ae_p,
                "pref": {
                    "horse": {"going": _tabelle(vorher, "going_pmu", gb, going_anzeige),
                              "distance": _tabelle(vorher, "distance_m", r.get("distance_m"),
                                                   lambda d: f"{int(d)} m")},
                    "trainer": {"jockey": q("trainer_jockey", (tk, jk)), "course": q("trainer_course", (tk, course)),
                                "racetype": q("trainer_type", (tk, rt))},
                    "jockey": {"course": q("jockey_course", (jk, course)), "trainer": q("trainer_jockey", (tk, jk))},
                    "sire": {"distance": q("sire_dist", (sk, db)), "going": q("sire_going", (sk, gb))},
                },
                "form_lines": form,
            })
        partanten = [x for x in starters if not x["nr"]]
        for k in DELTA_SPALTEN:                                   # Rang im heutigen Feld
            werte = [x["summary"][k] for x in partanten]
            for x in starters:
                x["summary"][k + "_rank"] = _rang(werte, x["summary"][k]) if not x["nr"] else None
                x["summary"][k + "_n"] = sum(w is not None for w in werte)
        for k, feld in (("rtr", "adj"), ("arr", "best_adj")):      # Rang im heutigen Feld (bereinigt)
            werte = [x[k][feld] for x in partanten]
            for x in starters:
                x[k]["rank"] = _rang(werte, x[k][feld]) if not x["nr"] else None
                x[k]["n"] = sum(w is not None for w in werte)
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
            "going_pmu": gb, "going_label": going_anzeige(gb), "dist_bucket": db,
            "dist_label": DIST_LABEL.get(db), "prize": _num(r.get("prize_eur"), 0), "type": rt,
            "age": _txt(r.get("conditions_age")), "sex": _txt(r.get("conditions_sexe")),
            "corde": _txt(r.get("corde")), "declared": _num(r.get("runners_declared"), 0),
            "status": _txt(r.get("statut")), "result": _txt(r.get("finish_order")),
            "runners": starters,
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
                   "avg_runs": SCHNITT_LAEUFE, "rivals_runs": GEGNER_LAEUFE, "rivals_max": GEGNER_MAX,
                   "best_seg_m": speedfig.BEST_SEG_BEREICH_M, "beaten_l": speedfig.AUSGERITTEN_L,
                   "avg_prior": SCHNITT_PRIOR, "avg_dist_m": SCHNITT_DIST_M, "weight_ref": GEWICHT_REF,
                   "styles": [{"key": k, "label": lab, "max": bis} for bis, k, lab in STIL]},
        "bias_all": bias["gesamt"],
        "meetings": sorted(meetings.values(), key=lambda m: m["reunion"]),
        "races": races_out,
    }


def letzte_rennen(hist: pd.DataFrame, runners_heute: pd.DataFrame, tag: date, n: int = LETZTE_LAEUFE) -> list[str]:
    """race_ids der letzten `n` Läufe aller heutigen Starter (die Formzeilen der Race Card)."""
    if hist.empty or runners_heute.empty:
        return []
    ru = runners_heute.copy()
    for c in ["horse", "sire"]:
        ru[c + "_key"] = norm_name(ru[c]) if c in ru else pd.Series(pd.NA, index=ru.index, dtype="string")
    ids = set(ru["horse_key"].fillna("?") + "|" + ru["sire_key"].fillna("?"))
    h = hist[(hist["date"] < pd.Timestamp(tag)) & hist["horse_id"].isin(ids)].sort_values("date", ascending=False)
    return sorted(set(h.groupby("horse_id").head(n)["race_id"]))


def replays(race_ids, base: Path | None = None, session: requests.Session | None = None, *,
            tag: date | None = None, pause: float = 0.3) -> dict:
    """Replay je Rennen (pmu.replay): {race_id: {"available": bool, "url": Video-Adresse oder None}},
    zwischengespeichert in <base>/replays.json. Ein vorhandenes Replay wird nie neu abgefragt; fehlt es,
    nur bei Rennen der letzten REPLAY_NACHFRAGE_TAGE Tage erneut (höchstens einmal am Tag) – PMU stellt
    Replays teils später ein. Antwortet die Schnittstelle nicht, wird nichts gespeichert."""
    tag = tag or pmu.heute()
    datei = Path(base) / "replays.json" if base else None
    cache = {}
    if datei and datei.exists():
        try:
            cache = json.loads(datei.read_text(encoding="utf-8"))
        except ValueError:
            cache = {}
    s = session or requests.Session()
    heute_s = tag.strftime("%Y-%m-%d")
    offen = []
    for rid in race_ids:
        e = cache.get(rid)
        if e and (e.get("available") or e.get("url")):
            continue
        try:
            alter = (tag - datetime.strptime(str(rid)[:8], "%Y%m%d").date()).days
        except ValueError:
            continue
        # Einträge ohne "available" stammen aus der früheren Abfrage (nur Video-Adresse) -> neu fragen
        if e is None or "available" not in e or (e.get("checked") != heute_s and alter <= REPLAY_NACHFRAGE_TAGE):
            offen.append(rid)
    stumm, geaendert = 0, False
    for i, rid in enumerate(offen, 1):
        try:
            erg = pmu.replay(rid, s)
        except (ValueError, requests.RequestException):
            erg = None
        if erg is None:
            # keine Antwort: nicht als "kein Replay" merken, und nach REPLAY_STUMM_MAX Rennen in Folge
            # aufhören, statt jedes Rennen einzeln ins Leere laufen zu lassen
            stumm += 1
            if stumm >= REPLAY_STUMM_MAX:
                print(f"  Replays: PMU antwortet nicht ({stumm} Rennen in Folge) – Abfrage abgebrochen. "
                      "Prüfen mit pmu.replay_diagnose(race_id).")
                break
            continue
        stumm, geaendert = 0, True
        cache[rid] = {**erg, "checked": heute_s}
        if i % 50 == 0:
            print(f"  Replays: {i}/{len(offen)} abgefragt")
        time.sleep(pause)
    if datei and geaendert:
        datei.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return {rid: {"available": bool(cache[rid].get("available")), "url": cache[rid].get("url")}
            for rid in race_ids if rid in cache and "available" in cache[rid]}


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


def run(base: Path, tag=None, out: Path | None = None, *, nur_flach: bool = True) -> Path:
    """Race Card für `tag` (Vorgabe: heute) bauen und als HTML speichern."""
    import pipeline as tp
    base = Path(base)
    tag = pd.to_datetime(tag).date() if tag else pmu.heute()
    print(f"PMU-Programm {tag} holen …")
    races_heute, runners_heute = programm(tag, nur_flach=nur_flach)
    if races_heute.empty:
        raise RuntimeError(f"Keine französischen {'Flach' if nur_flach else 'Galopp'}rennen am {tag}.")
    print(f"{len(races_heute)} Rennen, {len(runners_heute)} Starter. Historie laden …")
    hist = vorbereiten(tp.lade("pmu_races", base), tp.lade("pmu_runners", base),
                       tp.lade("tracking_races", base), tp.lade("tracking_runners", base),
                       tp.lade("tracking_sections", base), tp.lade("tracking_leader", base))
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
    rennen = letzte_rennen(hist, runners_heute, tag)
    print(f"Replays für {len(rennen)} frühere Rennen der Starter …")
    rp = replays(rennen, base, tag=tag)
    print(f"{sum(e['available'] for e in rp.values())} von {len(rennen)} Rennen mit Replay auf pmu.fr.")
    daten = baue_daten(hist, races_heute, runners_heute, tag, silks, rp)
    out = Path(out) if out else base / "racecards" / f"racecard_{tag:%Y%m%d}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html(daten), encoding="utf-8")
    print(f"Race Card gespeichert: {out}  ({daten['history']['runs']} historische Läufe, "
          f"davon {daten['history']['tracked']} mit Tracking)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", required=True, help="Ordner mit parquet/ (z. B. der Drive-Ordner)")
    ap.add_argument("--datum", default=None, help="JJJJ-MM-TT, Vorgabe: heute")
    ap.add_argument("--out", default=None)
    ap.add_argument("--alle-galopp", action="store_true", help="auch Hindernisrennen aufnehmen")
    a = ap.parse_args()
    run(Path(a.base), a.datum, a.out, nur_flach=not a.alle_galopp)
