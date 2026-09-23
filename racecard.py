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
    A/E            Siege / Summe(1 / Endquote)  – über 1: gewinnt öfter, als der Markt erwartet
    Position vor dem Finish
                   Platz im Feld am Messpunkt POS_VOR_FINISH_M vor dem Ziel, als Fünftel
                   des Feldes (1 = vorderstes Fünftel)
    adjustiert     best_seg_s, speed_last600_kmh, speed_last400_kmh abzüglich des Erwartungswerts
                   für Boden (PMU-Begriff), Distanz, Alter, Renntempo (Pace-Ratio) und Bahn
                   (additives Modell, per Backfitting geschätzt).
                   Positiv heißt immer: besser als erwartet (bei best_seg_s also schneller).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import pmu

TEMPLATE = Path(__file__).with_name("racecard_template.html")

POS_VOR_FINISH_M = 400          # Messpunkt für "Position vor dem Finish"
LETZTE_LAEUFE = 6               # so viele Formzeilen je Pferd
AE_FENSTER = (90, 365)          # Tage
MIN_GRUPPE = 30                 # so viele Läufe braucht eine Gruppe, bevor ihr Effekt zählt

GOING_LABEL = {"good": "Gut (≤ 3,3)", "soft": "Weich (3,4–3,9)", "heavy": "Schwer (≥ 4,0)",
               "psf": "PSF (Allwetter)"}
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
PLAUSIBEL = {"best_seg_s": (9.0, 16.0), "speed_last600_kmh": (40.0, 75.0),
             "speed_last400_kmh": (40.0, 75.0), "finish_index": (70.0, 130.0),
             "pos_gain_800_finish": (-20, 20), "pace_ratio": (60.0, 160.0)}
ADJ = {"best_seg_s": False, "speed_last600_kmh": True, "speed_last400_kmh": True}   # höher = besser?
# Einflussgrößen der Adjustierung. Das Renntempo gehört dazu, weil ein langsam angegangenes
# Rennen (Pace-Ratio < 100) automatisch schnelle Schlussabschnitte liefert.
ADJ_KEYS = ("going_class", "dist_bucket", "age_bucket", "pace_class", "course_key")

# PMU-Bodenbegriffe, längste zuerst ("TRES SOUPLE" vor "SOUPLE")
GOING_KLASSEN = ["TRES LEGER", "BON LEGER", "BON SOUPLE", "TRES SOUPLE", "COLLANT", "LOURD",
                 "LEGER", "SOUPLE", "BON"]
# Ersatz, wenn nur der Penetrometer-Wert bekannt ist: (bis Wert, Klasse)
GOING_NACH_WERT = [(2.8, "BON LEGER"), (3.3, "BON"), (3.6, "BON SOUPLE"), (3.9, "SOUPLE"),
                   (4.4, "TRES SOUPLE"), (99, "LOURD")]
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


def going_bucket(going, going_value) -> str | None:
    if going is not None and "PSF" in str(going).upper():
        return "psf"
    v = _num(going_value)
    if v is None:
        return None
    return "good" if v <= 3.3 else "soft" if v <= 3.9 else "heavy"


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
                trk_runners: pd.DataFrame | None = None, trk_sections: pd.DataFrame | None = None) -> pd.DataFrame:
    """Eine Zeile je Starter und Rennen, mit Renndaten und Tracking-Kennzahlen."""
    if races.empty or runners.empty:
        return pd.DataFrame()
    r = races.drop_duplicates("race_id", keep="last").copy()
    r["date"] = pd.to_datetime(r["race_id"].astype(str).str[:8], format="%Y%m%d", errors="coerce")
    r["distance_m"] = pd.to_numeric(r["distance_m"], errors="coerce")
    r["prize_eur"] = pd.to_numeric(r.get("prize_eur"), errors="coerce")
    r["going_value"] = to_float(r["going_value"]) if "going_value" in r else np.nan
    r["going_bucket"] = [going_bucket(g, v) for g, v in zip(r.get("going"), r["going_value"])]
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

    h = h.merge(r[["race_id", "date", "hippodrome", "course_key", "distance_m", "going", "going_value",
                   "going_bucket", "going_class", "dist_bucket", "prize_eur", "racetype"]],
                on="race_id", how="inner")
    h["n_runners"] = h.groupby("race_id")["saddle_no"].transform("count")
    h["won"] = (h["finish_pos"] == 1).astype(int)
    h["placed"] = (h["finish_pos"] <= 3).astype(int)
    h["age_bucket"] = h["age"].map(age_bucket)
    fav = h.groupby("race_id")["odds_final"].transform("min")
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
        cols = [c for c in ["finish_index", "pos_gain_800_finish", "best_seg_s", "speed_last600_kmh",
                            "speed_last400_kmh"] if c in t]
        for c in cols:
            t[c] = pd.to_numeric(t[c], errors="coerce")
        t = t.drop_duplicates(["race_id", "saddle_no"], keep="last")[["race_id", "saddle_no", *cols]]
        h = h.merge(t, on=["race_id", "saddle_no"], how="left")
        h["tracking"] = h["race_id"].isin(set(t["race_id"]))
    else:
        h["tracking"] = False
    if trk_races is not None and not trk_races.empty and "pace_ratio" in trk_races:
        p = trk_races.drop_duplicates("race_id", keep="last")[["race_id", "pace_ratio"]].copy()
        p["pace_ratio"] = pd.to_numeric(p["pace_ratio"], errors="coerce")
        h = h.merge(p, on="race_id", how="left")
    if trk_sections is not None and not trk_sections.empty:
        h = h.merge(position_vor_finish(trk_sections), on=["race_id", "saddle_no"], how="left")
    for c in list(PLAUSIBEL) + ["pos_before", "pos_before_m"]:
        if c not in h:
            h[c] = np.nan
    for c, (lo, hi) in PLAUSIBEL.items():
        h[c] = h[c].where(h[c].between(lo, hi))
    h["pace_class"] = h["pace_ratio"].map(pace_klasse)
    ok = h["pos_before"].notna() & (h["n_runners"] > 0)
    h["fifth"] = np.where(ok, np.ceil(h["pos_before"] / h["n_runners"].clip(lower=1) * 5).clip(1, 5), np.nan)

    for c, higher in ADJ.items():
        h[c + "_adj"] = adjustieren(h, c, higher)
    return h.sort_values(["date", "race_id", "finish_pos"]).reset_index(drop=True)


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


def adjustieren(h: pd.DataFrame, col: str, higher_better: bool, *,
                keys=ADJ_KEYS, runden: int = 12) -> pd.Series:
    """Wert minus Erwartung für Boden, Distanz, Alter, Renntempo und Bahn (additive Effekte,
    Backfitting: jeder Effekt wird auf dem Rest der übrigen geschätzt, so dass sich z. B. Bahn
    und Boden nicht gegenseitig doppelt zählen). Gruppen mit weniger als MIN_GRUPPE Läufen
    bekommen keinen eigenen Effekt. Positiv heißt immer 'besser als erwartet'."""
    keys = [k for k in keys if k in h]
    y = pd.to_numeric(h[col], errors="coerce")
    m = y.notna()
    if m.sum() < MIN_GRUPPE:
        return pd.Series(np.nan, index=h.index)
    base = y[m].mean()
    eff = {k: pd.Series(0.0, index=h.index) for k in keys}
    for _ in range(runden):
        for k in keys:
            rest = y - base - sum(eff[j] for j in keys if j != k)
            g = h.loc[m, k].astype("string").fillna("?")
            stats = rest[m].groupby(g).agg(["mean", "count"])
            werte = stats["mean"].where(stats["count"] >= MIN_GRUPPE, 0.0)
            werte = werte - (werte * stats["count"]).sum() / stats["count"].sum()   # zentrieren
            eff[k] = h[k].astype("string").fillna("?").map(werte).fillna(0.0).astype(float)
    erwartet = base + sum(eff.values())
    diff = y - erwartet
    return diff if higher_better else -diff


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
def _formzeile(z) -> dict:
    return {
        "date": z["date"].strftime("%Y-%m-%d"), "race_id": z["race_id"],
        "course": _txt(z["hippodrome"]), "dist": _num(z["distance_m"], 0),
        "going": _txt(z["going"]), "going_value": _num(z["going_value"], 1),
        "prize": _num(z["prize_eur"], 0), "type": _txt(z["racetype"]),
        "pos": _num(z["finish_pos"], 0), "ran": _num(z["n_runners"], 0),
        "margin": _num(z.get("margin"), 2), "weight": _num(z["weight_kg"], 1),
        "jockey": _txt(z.get("jockey")), "odds": _num(z["odds_final"], 1),
        "incident": _txt(z.get("incident")), "fav": bool(z["favourite"]),
        "tracking": bool(z["tracking"]),
        "pos_before": _num(z["pos_before"], 0), "pos_before_m": _num(z["pos_before_m"], 0),
        "fifth": _num(z["fifth"], 0), "pace_ratio": _num(z["pace_ratio"], 1),
        "finish_index": _num(z["finish_index"], 1), "pos_gain": _num(z["pos_gain_800_finish"], 0),
        "best_seg_s": _num(z["best_seg_s"], 2), "best_seg_adj": _num(z["best_seg_s_adj"], 2),
        "v600": _num(z["speed_last600_kmh"], 2), "v600_adj": _num(z["speed_last600_kmh_adj"], 2),
        "v400": _num(z["speed_last400_kmh"], 2), "v400_adj": _num(z["speed_last400_kmh_adj"], 2),
    }


def baue_daten(hist: pd.DataFrame, races_heute: pd.DataFrame, runners_heute: pd.DataFrame,
               tag: date) -> dict:
    heute = pd.Timestamp(tag)
    h = hist[hist["date"] < heute].copy() if not hist.empty else hist
    if h.empty:
        h = pd.DataFrame(columns=["date", "horse_id", "trainer_key", "jockey_key", "sire_key", "course_key",
                                  "going_bucket", "dist_bucket", "racetype", "won", "placed", "odds_final",
                                  "distance_m", "finish_pos"])

    # A/E-Tabellen
    ae = {}
    for rolle in ("trainer", "jockey", "sire"):
        for tage in AE_FENSTER:
            sub = h[h["date"] >= heute - timedelta(days=tage)]
            ae[(rolle, tage)] = gruppen(sub, [rolle + "_key"])

    # Vorlieben (gesamte Historie vor heute)
    pref = {
        "horse_going": gruppen(h, ["horse_id", "going_bucket"]),
        "horse_dist": gruppen(h, ["horse_id", "dist_bucket"]),
        "trainer_jockey": gruppen(h, ["trainer_key", "jockey_key"]),
        "trainer_course": gruppen(h, ["trainer_key", "course_key"]),
        "trainer_type": gruppen(h, ["trainer_key", "racetype"]),
        "jockey_course": gruppen(h, ["jockey_key", "course_key"]),
        "sire_dist": gruppen(h, ["sire_key", "dist_bucket"]),
        "sire_going": gruppen(h, ["sire_key", "going_bucket"]),
    }

    rh = races_heute.drop_duplicates("race_id").copy()
    ru = runners_heute.drop_duplicates(["race_id", "saddle_no"]).copy()
    for c in ["horse", "jockey", "trainer", "sire"]:
        ru[c + "_key"] = norm_name(ru[c]) if c in ru else pd.Series(pd.NA, index=ru.index, dtype="string")
    ru["horse_id"] = ru["horse_key"].fillna("?") + "|" + ru["sire_key"].fillna("?")
    ids = set(ru["horse_id"])
    hh = h[h["horse_id"].isin(ids)].sort_values("date", ascending=False)
    per_pferd = {k: g for k, g in hh.groupby("horse_id", sort=False)}

    meetings: dict[int, dict] = {}
    races_out = {}
    for _, r in rh.sort_values(["reunion", "race_no"]).iterrows():
        gb = going_bucket(r.get("going"), to_float(pd.Series([r.get("going_value")])).iloc[0])
        db = dist_bucket(r.get("distance_m"))
        rt = kategorie(r.get("categorie"))
        course = norm_name(pd.Series([r.get("hippodrome")])).iloc[0]
        dist = _num(r.get("distance_m"), 0)
        starters = []
        for _, p in ru[ru["race_id"] == r["race_id"]].sort_values("saddle_no").iterrows():
            hid, tk, jk, sk = p["horse_id"], p["trainer_key"], p["jockey_key"], p["sire_key"]
            vorher = per_pferd.get(hid, pd.DataFrame())
            form = [_formzeile(z) for _, z in vorher.head(LETZTE_LAEUFE).iterrows()]
            siege = vorher[vorher["won"] == 1] if len(vorher) else vorher
            c_sieg = bool(len(siege) and (siege["course_key"] == course).any())
            d_sieg = bool(len(siege) and dist is not None and ((siege["distance_m"] - dist).abs() <= 100).any())
            badges = (["CD"] if c_sieg and d_sieg and ((siege["course_key"] == course)
                                                         & ((siege["distance_m"] - dist).abs() <= 100)).any()
                      else [b for b, ok in (("C", c_sieg), ("D", d_sieg)) if ok])
            if len(vorher) and bool(vorher.iloc[0]["favourite"]) and vorher.iloc[0]["won"] != 1:
                badges.append("BF")
            tracked = vorher[vorher["tracking"]].head(3) if len(vorher) else vorher

            def q(tab, key):
                return _leer() if any(_txt(k) is None for k in key) else pref[tab].get(key, _leer())

            status = str(p.get("status") or "").upper()
            inc = str(p.get("incident") or "").upper()
            starters.append({
                "no": _num(p.get("saddle_no"), 0), "draw": _num(p.get("draw"), 0),
                "horse": _txt(p.get("horse")), "age": _num(p.get("age"), 0), "sex": _txt(p.get("sex")),
                "weight": _num(p.get("weight_kg"), 1),
                "rating": _num(p.get("rating"), 1), "blinkers": _txt(p.get("blinkers")),
                "jockey": _txt(p.get("jockey")), "trainer": _txt(p.get("trainer")), "owner": _txt(p.get("owner")),
                "sire": _txt(p.get("sire")), "dam": _txt(p.get("dam")), "form": _txt(p.get("form")),
                "starts": _num(p.get("starts"), 0), "wins": _num(p.get("wins"), 0),
                "places": _num(p.get("places"), 0), "earnings": _num(p.get("earnings_eur"), 0),
                "odds": _num(p.get("odds_final"), 1), "odds_morning": _num(p.get("odds_morning"), 1),
                "nr": "NON_PARTANT" in (status, inc),
                "days": int((heute - vorher.iloc[0]["date"]).days) if len(vorher) else None,
                "badges": badges,
                "summary": {
                    "v400_adj": _num(tracked["speed_last400_kmh_adj"].max(), 2) if len(tracked) else None,
                    "v600_adj": _num(tracked["speed_last600_kmh_adj"].max(), 2) if len(tracked) else None,
                    "fi": _num(tracked["finish_index"].mean(), 1) if len(tracked) else None,
                },
                "ae": {rolle: {f"d{t}": ae[(rolle, t)].get(key, _leer()) for t in AE_FENSTER}
                       for rolle, key in (("trainer", tk), ("jockey", jk), ("sire", sk))},
                "pref": {
                    "horse": {"going": q("horse_going", (hid, gb)), "distance": q("horse_dist", (hid, db))},
                    "trainer": {"jockey": q("trainer_jockey", (tk, jk)), "course": q("trainer_course", (tk, course)),
                                "racetype": q("trainer_type", (tk, rt))},
                    "jockey": {"course": q("jockey_course", (jk, course)), "trainer": q("trainer_jockey", (tk, jk))},
                    "sire": {"distance": q("sire_dist", (sk, db)), "going": q("sire_going", (sk, gb))},
                },
                "form_lines": form,
            })
        m = meetings.setdefault(int(r["reunion"]), {"reunion": int(r["reunion"]),
                                                     "course": _txt(r.get("hippodrome")), "races": []})
        m["races"].append(r["race_id"])
        races_out[r["race_id"]] = {
            "race_id": r["race_id"], "reunion": int(r["reunion"]), "race_no": int(r["race_no"]),
            "time": _txt(r.get("post_time")), "name": _txt(r.get("race_name")), "course": _txt(r.get("hippodrome")),
            "distance": dist, "going": _txt(r.get("going")), "going_value": _txt(r.get("going_value")),
            "going_bucket": gb, "going_label": GOING_LABEL.get(gb), "dist_bucket": db,
            "dist_label": DIST_LABEL.get(db), "prize": _num(r.get("prize_eur"), 0), "type": rt,
            "age": _txt(r.get("conditions_age")), "sex": _txt(r.get("conditions_sexe")),
            "corde": _txt(r.get("corde")), "declared": _num(r.get("runners_declared"), 0),
            "status": _txt(r.get("statut")), "result": _txt(r.get("finish_order")),
            "runners": starters,
        }
    hist_von = h["date"].min() if len(h) else None
    return {
        "date": heute.strftime("%Y-%m-%d"),
        "generated": datetime.now(pmu.PARIS).strftime("%Y-%m-%d %H:%M"),
        "history": {"from": hist_von.strftime("%Y-%m-%d") if hist_von is not None else None,
                    "runs": int(len(h)), "tracked": int(h["tracking"].sum()) if "tracking" in h else 0},
        "params": {"pos_before_m": POS_VOR_FINISH_M, "ae_windows": list(AE_FENSTER), "form_runs": LETZTE_LAEUFE},
        "meetings": sorted(meetings.values(), key=lambda m: m["reunion"]),
        "races": races_out,
    }


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
                       tp.lade("tracking_sections", base))
    daten = baue_daten(hist, races_heute, runners_heute, tag)
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
