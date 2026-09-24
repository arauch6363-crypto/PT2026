"""
rpr.py - Racing-Post-style performance ratings (RPR) for French flat races.

Works directly on the two PMU tables:

    races_raw   - one row per race   (race_id, date, distance_m, going, going_value,
                                      categorie, prize_eur, conditions_age, ...)
    runners_raw - one row per runner (race_id, horse, status, age, sex, weight_kg,
                                      rating, finish_pos, lengths_behind, lengths_prev,
                                      incident, ...)

The data has no race times, so the "time vs standard" leg of the Racing Post method
is unavailable. Ratings are therefore built from the three legs that ARE available:

  1. Relative performance inside the race
         rel_lb = (adjusted weight - winner's adjusted weight) - beaten margin in lb
     where adjusted weight = weight carried (lb) + weight-for-age (+ optional sex allowance)
     and the margin is converted with the Racing Post lb-per-length scale, damped on soft ground.

  2. Absolute level of the race
     Runners with an established mark ("valeur" = `rating`, kg, converted to lb, and/or
     their own recent RPRs) act as measuring instruments.  For each anchor in the
     top part of the field we compute the base the race must have had if that horse
     ran to its mark; the median of those is the race base, shrunk towards a class
     prior (median winner mark per categorie x prize band) when anchors are scarce.

  3. Chronological calibration
     Races are processed in date order so that a horse's earlier RPRs become anchors
     for later races (step 4 of the methodology).

Usage
-----
    from rpr import RPRModel, RPRConfig

    model = RPRModel(RPRConfig())
    ratings, race_info = model.fit(races_raw, runners_raw)

    model.table("20260809R1C3")      # RP-style result table
    print(model.narrative("20260809R1C3"))

Scale note
----------
French official ratings are in kg.  By default 1 kg = 2.2046 lb with no offset, so an
RPR here is "valeur x 2.2".  Set RPRConfig.or_offset if you want to align with BHA marks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Constants / lookup tables
# --------------------------------------------------------------------------- #

LB_PER_KG = 2.2046
FURLONG_M = 201.168

# Racing Post flat scale: lb per length by race distance (metres, upper bound of band)
LB_PER_LENGTH_BY_DIST: List[Tuple[int, float]] = [
    (1100, 3.00),   # 5f
    (1300, 2.50),   # 6f
    (1500, 2.25),   # 7f
    (1700, 2.00),   # 1m
    (1900, 1.75),   # 9f
    (2100, 1.50),   # 10f
    (2500, 1.25),   # 11-12f
    (99999, 1.00),  # 14f+
]

# Softer ground -> a length is worth fewer lb.  Checked in order; first match wins.
GOING_FACTORS: List[Tuple[str, float]] = [
    ("très lourd", 0.80), ("tres lourd", 0.80),
    ("lourd", 0.85), ("collant", 0.85),
    ("très souple", 0.90), ("tres souple", 0.90),
    ("bon souple", 1.00),
    ("souple", 0.95),
]

# Weight-for-age a 3yo RECEIVES from 4yo+ (lb).  Rows: distance in furlongs,
# columns: months Jan..Dec (Jan/Feb use the March figure, BHA-style approximation).
WFA_3YO: Dict[int, List[int]] = {
    5:  [15, 15, 15, 13, 11, 9, 7, 5, 3, 2, 1, 0],
    6:  [16, 16, 16, 14, 12, 10, 8, 6, 4, 3, 2, 1],
    7:  [18, 18, 18, 16, 14, 12, 10, 8, 6, 4, 3, 2],
    8:  [20, 20, 20, 17, 15, 13, 11, 9, 7, 5, 4, 3],
    9:  [22, 22, 22, 19, 17, 15, 12, 10, 8, 6, 5, 4],
    10: [24, 24, 24, 21, 18, 16, 14, 11, 9, 7, 6, 5],
    11: [25, 25, 25, 22, 20, 17, 15, 12, 10, 8, 7, 6],
    12: [26, 26, 26, 24, 21, 18, 16, 13, 11, 9, 8, 6],
    14: [28, 28, 28, 26, 23, 20, 17, 15, 12, 10, 9, 7],
    16: [31, 31, 31, 28, 25, 22, 19, 16, 14, 12, 10, 8],
}

# Runners that get no rating at all
NON_RATED_INCIDENTS = {
    "NON_PARTANT", "ARRETE", "TOMBE", "DISTANCE", "RESTE_AU_POTEAU", "DEROBE", "DISQUALIFIE",
}

FEMALE_SEX = {"FEMELLES"}


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

@dataclass
class RPRConfig:
    or_scale: float = LB_PER_KG        # `rating` (kg) -> lb
    or_offset: float = 0.0             # added after scaling (align to BHA scale if wanted)
    sex_allowance_lb: float = 0.0      # e.g. 3.3 to credit fillies vs males in mixed races
    anchor_top_fraction: float = 0.5   # only runners in the top x of the field are anchors
    anchor_min_top: int = 3            # ... but always at least the first N home
    prior_rpr_runs: int = 3            # how many previous RPRs to look at per horse
    prior_weight: float = 0.5          # weight of prior-RPR anchor vs official rating when both exist
    shrink_k: float = 2.0              # base = n/(n+k) * anchor_base + k/(n+k) * class_prior
    max_winner_uplift_lb: float = 8.0  # max lb of *margin* credit a winner gets over the runner-up
    two_yo_extra_lb: float = 12.0      # crude 2yo-vs-3yo allowance on top of the 3yo table
    default_base: float = 70.0         # class prior fallback when nothing else is known
    prize_bins: int = 5                # prize bands per categorie for the class prior


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #

def parse_going_value(v) -> Optional[float]:
    """'3,3' -> 3.3 ; returns None if unparseable."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def going_factor(going: Optional[str], going_value=None) -> float:
    """Multiplier on lb-per-length for the ground."""
    g = "" if going is None or (isinstance(going, float) and math.isnan(going)) else str(going).strip().lower()
    for key, f in GOING_FACTORS:
        if key in g:
            return f
    if g:                       # 'Bon', 'Léger', 'PSF ...' etc.
        return 1.0
    pv = parse_going_value(going_value)
    if pv is None:
        return 1.0
    if pv <= 3.5:
        return 1.0
    if pv <= 4.0:
        return 0.95
    if pv <= 4.5:
        return 0.90
    return 0.85


def lb_per_length(distance_m: int, going: Optional[str] = None, going_value=None) -> float:
    base = LB_PER_LENGTH_BY_DIST[-1][1]
    for upper, lb in LB_PER_LENGTH_BY_DIST:
        if distance_m <= upper:
            base = lb
            break
    return base * going_factor(going, going_value)


def wfa_lb(age: int, month: int, distance_m: int, cfg: RPRConfig) -> float:
    """Weight-for-age allowance (lb) a horse of `age` receives from a mature (4yo+) horse."""
    if age >= 4:
        return 0.0
    furlongs = distance_m / FURLONG_M
    keys = sorted(WFA_3YO)
    if furlongs <= keys[0]:
        val = WFA_3YO[keys[0]][month - 1]
    elif furlongs >= keys[-1]:
        val = WFA_3YO[keys[-1]][month - 1]
    else:
        lo = max(k for k in keys if k <= furlongs)
        hi = min(k for k in keys if k >= furlongs)
        if lo == hi:
            val = WFA_3YO[lo][month - 1]
        else:
            w = (furlongs - lo) / (hi - lo)
            val = (1 - w) * WFA_3YO[lo][month - 1] + w * WFA_3YO[hi][month - 1]
    if age == 2:
        val += cfg.two_yo_extra_lb
    return float(val)


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cum = np.cumsum(w)
    return float(v[np.searchsorted(cum, 0.5 * cum[-1])])


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #

class RPRModel:
    def __init__(self, cfg: Optional[RPRConfig] = None):
        self.cfg = cfg or RPRConfig()
        self.ratings_: Optional[pd.DataFrame] = None
        self.race_info_: Optional[pd.DataFrame] = None
        self.class_prior_: Dict[Tuple[str, int], float] = {}
        self._prize_edges: Dict[str, np.ndarray] = {}
        self._history: Dict[str, List[Tuple[str, float]]] = {}

    # ------------------------------------------------------------------ fit
    def fit(self, races: pd.DataFrame, runners: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        races = self._prepare_races(races)
        runners = self._prepare_runners(runners)
        self._build_class_prior(races, runners)
        self._history = {}

        # one pass over numpy arrays: runners are sorted by race_id, finish_pos (NaN last)
        runners = runners[runners["race_id"].isin(set(races["race_id"]))].reset_index(drop=True)
        cols = self._arrays(runners)
        rid = runners["race_id"].to_numpy()
        bounds = {}
        if len(rid):
            cut = np.flatnonzero(rid[1:] != rid[:-1]) + 1
            starts, ends = np.r_[0, cut], np.r_[cut, len(rid)]
            bounds = dict(zip(rid[starts], zip(starts, ends)))

        n = len(runners)
        res = {c: np.full(n, np.nan) for c in self._OUT_NUM}
        res["is_anchor"] = np.zeros(n, dtype=bool)
        res["note"] = np.full(n, "", dtype=object)
        order, infos = [], []
        for race in races.to_dict("records"):
            b = bounds.get(race["race_id"])
            if b is None:
                continue
            sl = slice(*b)
            out, info = self._rate_core(race, {c: v[sl] for c, v in cols.items()})
            for c in res:
                res[c][sl] = out[c]
            order.append(np.arange(*b))
            infos.append(info)
            for h, r in zip(cols["horse"][sl], out["rpr"]):
                if not np.isnan(r):
                    self._history.setdefault(h, []).append((race["date"], float(r)))

        idx = np.concatenate(order) if order else np.array([], dtype=int)
        rated = runners.iloc[idx].assign(**{c: v[idx] for c, v in res.items()})
        self.ratings_ = rated[self._KEEP].reset_index(drop=True) if order else pd.DataFrame()
        self.race_info_ = pd.DataFrame(infos)
        return self.ratings_, self.race_info_

    # -------------------------------------------------------------- prepare
    @staticmethod
    def _prepare_races(races: pd.DataFrame) -> pd.DataFrame:
        r = races.copy()
        r = r[r["statut"].isin(["ARRIVEE_DEFINITIVE_COMPLETE", "FIN_COURSE"])]
        r["date"] = r["date"].astype(str)
        r["month"] = pd.to_datetime(r["date"], format="%Y%m%d", errors="coerce").dt.month.fillna(6).astype(int)
        return r.sort_values(["date", "hippodrome", "race_no"]).reset_index(drop=True)

    def _prepare_runners(self, runners: pd.DataFrame) -> pd.DataFrame:
        cfg = self.cfg
        r = runners.copy()
        r = r[r["status"] == "PARTANT"]
        r["incident"] = r["incident"].fillna("")
        r["or_lb"] = r["rating"] * cfg.or_scale + cfg.or_offset
        r["weight_lb"] = r["weight_kg"] * LB_PER_KG

        # fill missing lengths_behind: winner = 0, otherwise cumulative lengths_prev
        r = r.sort_values(["race_id", "finish_pos"])
        r.loc[(r["finish_pos"] == 1) & r["lengths_behind"].isna(), "lengths_behind"] = 0.0
        cum = r.groupby("race_id")["lengths_prev"].cumsum()
        need = r["lengths_behind"].isna() & r["finish_pos"].notna()
        r.loc[need, "lengths_behind"] = cum[need]
        return r

    def _build_class_prior(self, races: pd.DataFrame, runners: pd.DataFrame) -> None:
        """Median winner mark (lb) per categorie x prize band."""
        win = runners[runners["finish_pos"] == 1][["race_id", "or_lb"]]
        m = races[["race_id", "categorie", "prize_eur"]].merge(win, on="race_id", how="left")
        self.class_prior_, self._prize_edges = {}, {}
        for cat, g in m.groupby("categorie"):
            logp = np.log1p(g["prize_eur"].astype(float))
            try:
                edges = np.unique(np.quantile(logp, np.linspace(0, 1, self.cfg.prize_bins + 1)))
            except Exception:
                edges = np.array([logp.min(), logp.max()])
            self._prize_edges[cat] = edges
            band = np.clip(np.searchsorted(edges, logp, side="right") - 1, 0, max(len(edges) - 2, 0))
            for b, gb in g.assign(band=band).groupby("band"):
                med = gb["or_lb"].median()
                if pd.notna(med):
                    self.class_prior_[(cat, int(b))] = float(med)
        self._global_prior = float(m["or_lb"].median()) if m["or_lb"].notna().any() else self.cfg.default_base

    def class_prior(self, categorie: str, prize_eur: float) -> float:
        edges = self._prize_edges.get(categorie)
        if edges is None:
            return self._global_prior
        b = int(np.clip(np.searchsorted(edges, np.log1p(float(prize_eur)), side="right") - 1,
                        0, max(len(edges) - 2, 0)))
        # fall back to nearest band of the same categorie, then global
        for delta in range(0, 6):
            for cand in (b - delta, b + delta):
                if (categorie, cand) in self.class_prior_:
                    return self.class_prior_[(categorie, cand)]
        return self._global_prior

    # ------------------------------------------------------------ rate race
    def _prior_rpr(self, horse: str) -> Optional[float]:
        hist = self._history.get(horse)
        if not hist:
            return None
        recent = [r for _, r in hist[-self.cfg.prior_rpr_runs:]]
        return float(np.median(recent))

    _KEEP = ["race_id", "horse", "finish_pos", "age", "sex", "weight_kg", "lengths_behind",
             "rating", "or_lb", "prior_rpr", "wfa_lb", "sex_lb", "margin_lb", "rel_lb",
             "is_anchor", "rpr", "note"]
    _OUT_NUM = ["prior_rpr", "wfa_lb", "sex_lb", "margin_lb", "rel_lb", "anchor_mark", "rpr"]

    @staticmethod
    def _arrays(rr: pd.DataFrame) -> dict:
        return {
            "horse": rr["horse"].to_numpy(object),
            "incident": rr["incident"].fillna("").astype(str).to_numpy(object),
            "sex": rr["sex"].to_numpy(object),
            **{c: pd.to_numeric(rr[c], errors="coerce").to_numpy(float)
               for c in ["finish_pos", "lengths_behind", "age", "weight_lb", "or_lb"]},
        }

    def rate_race(self, race: pd.Series, rr: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
        """Rate one race (runners already prepared).  fit() uses the same core on numpy slices."""
        df = rr.sort_values("finish_pos", kind="stable").copy()
        out, info = self._rate_core(race, self._arrays(df))
        for c, v in out.items():
            df[c] = v
        for c in self._KEEP:
            if c not in df.columns:
                df[c] = np.nan
        return df[self._KEEP].reset_index(drop=True), info

    def _rate_core(self, race, a: dict) -> Tuple[dict, dict]:
        """One race on numpy arrays sorted by finish_pos (non-finishers last)."""
        cfg = self.cfg
        m = len(a["horse"])
        out = {c: np.full(m, np.nan) for c in self._OUT_NUM}
        out["is_anchor"] = np.zeros(m, dtype=bool)
        note = np.full(m, "", dtype=object)
        out["note"] = note
        dist = int(race["distance_m"])
        month = int(race.get("month", 6))
        lpl = lb_per_length(dist, race.get("going"), race.get("going_value"))

        # --- eligibility ---------------------------------------------------
        inc = a["incident"]
        nonrated = np.array([i in NON_RATED_INCIDENTS for i in inc], dtype=bool)
        fp, lb = a["finish_pos"], a["lengths_behind"]
        bad = nonrated | np.isnan(fp) | np.isnan(lb)
        note[nonrated] = inc[nonrated]
        note[np.isnan(lb) & ~np.isnan(fp) & ~nonrated] = "no margin available"
        fi = np.flatnonzero(~bad)
        fi = fi[np.argsort(fp[fi], kind="stable")]
        n_nonfin = int(nonrated.sum())
        if len(fi) < 2:
            return out, self._info(race, out["rpr"], n_nonfin, np.nan, 0, np.nan, "unrated", lpl)

        # --- relative performance ------------------------------------------
        female = np.array([s in FEMALE_SEX for s in a["sex"]], dtype=bool)
        mixed_race = bool(female.any() and (~female).any())
        wfa = np.array([wfa_lb(int(x), month, dist, cfg) for x in a["age"][fi]], dtype=float)
        sex_lb = np.where(female[fi] & mixed_race, cfg.sex_allowance_lb, 0.0)
        margin = lb[fi] * lpl
        adj = a["weight_lb"][fi] + wfa + sex_lb
        rel = (adj - adj[0]) - margin

        # --- anchors -------------------------------------------------------
        n = len(fi)
        top_n = max(cfg.anchor_min_top, int(math.ceil(n * cfg.anchor_top_fraction)))
        prior = np.array([np.nan if (p := self._prior_rpr(h)) is None else p for h in a["horse"][fi]], dtype=float)
        orl = a["or_lb"][fi]
        both = ~np.isnan(prior) & ~np.isnan(orl)
        anchor_mark = np.where(both, cfg.prior_weight * np.nan_to_num(prior) + (1 - cfg.prior_weight) * np.nan_to_num(orl),
                               np.where(np.isnan(prior), orl, prior))
        is_anchor = ~np.isnan(anchor_mark) & (np.arange(n) < top_n)

        prior_base = self.class_prior(race["categorie"], race["prize_eur"])
        k = int(is_anchor.sum())
        if k:
            implied = anchor_mark[is_anchor] - rel[is_anchor]
            w = 1.0 / (1.0 + np.arange(k))                        # 1st home weighs most
            anchor_base = _weighted_median(implied, w)
            base = (k / (k + cfg.shrink_k)) * anchor_base + (cfg.shrink_k / (k + cfg.shrink_k)) * prior_base
            spread = float(np.ptp(implied)) if k > 1 else 0.0
            method = "anchor+prior" if k < 4 else "anchor"
        else:
            base, spread, method = prior_base, np.nan, "class prior"

        rpr = base + rel
        fnote = note[fi].copy()

        # --- winner cap: a wide-margin win is not fully credited ----------------
        # (only the margin term is capped; weight differences stay fully credited)
        excess = float(margin[1]) - cfg.max_winner_uplift_lb
        if excess > 0:
            rpr[0] -= excess
            fnote[0] = (f"won by {lb[fi[1]]:.1f}L; margin credit "
                        f"capped at {cfg.max_winner_uplift_lb:.0f}lb over runner-up")

        rpr = np.round(rpr, 0)

        # --- notes on big moves vs mark ------------------------------------
        for j, d in enumerate(rpr - anchor_mark):
            if np.isnan(d) or fnote[j]:
                continue
            if d >= 8:
                fnote[j] = f"career-best, +{d:.0f}lb on mark"
            elif d <= -12:
                fnote[j] = f"well below mark ({d:.0f}lb)"

        for c, v in (("prior_rpr", prior), ("wfa_lb", wfa), ("sex_lb", sex_lb), ("margin_lb", margin),
                     ("rel_lb", rel), ("anchor_mark", anchor_mark), ("rpr", rpr)):
            out[c][fi] = v
        out["is_anchor"][fi] = is_anchor
        note[fi] = fnote
        info = self._info(race, out["rpr"], n_nonfin, base, k, spread, method, lpl, prior_base)
        return out, info

    # -------------------------------------------------------------- output
    @staticmethod
    def _info(race, rpr, n_nonfin, base, n_anchors, spread, method, lpl, prior_base=np.nan) -> dict:
        rated = rpr[~np.isnan(rpr)]
        return {
            "race_id": race["race_id"], "date": race["date"], "hippodrome": race["hippodrome"],
            "race_name": race["race_name"], "categorie": race["categorie"],
            "distance_m": race["distance_m"], "going": race.get("going"),
            "lb_per_length": round(lpl, 2), "class_prior": prior_base,
            "base_rpr": base, "n_anchors": n_anchors, "anchor_spread_lb": spread,
            "method": method, "n_rated": int(rated.size),
            "top_rpr": float(rated.max()) if rated.size else np.nan,
            "n_non_finishers": n_nonfin,
        }
    def table(self, race_id: str) -> pd.DataFrame:
        """Racing-Post style result table for one race."""
        if self.ratings_ is None:
            raise RuntimeError("call fit() first")
        t = self.ratings_[self.ratings_["race_id"] == race_id].copy()
        t["margin"] = np.where(t["finish_pos"] == 1, "won",
                               t["lengths_behind"].map(lambda x: f"{x:.2f}L" if pd.notna(x) else ""))
        t["OR"] = t["rating"]
        return t[["finish_pos", "horse", "age", "weight_kg", "margin", "OR", "rpr", "note"]] \
            .rename(columns={"finish_pos": "pos", "weight_kg": "wt_kg", "rpr": "RPR"})

    def narrative(self, race_id: str) -> str:
        """2-5 sentence handicapper's note for one race."""
        if self.race_info_ is None:
            raise RuntimeError("call fit() first")
        row = self.race_info_[self.race_info_["race_id"] == race_id]
        if row.empty:
            return f"{race_id}: not rated."
        i = row.iloc[0]
        t = self.ratings_[self.ratings_["race_id"] == race_id]
        rated = t.dropna(subset=["rpr"]).sort_values("finish_pos")
        if rated.empty:
            return f"{i['race_name']} ({i['hippodrome']}, {i['date']}): too few finishers with margins to rate."
        win = rated.iloc[0]
        s = [f"{i['race_name']} ({i['hippodrome']}, {i['date']}, {i['distance_m']}m, {i['categorie']}, "
             f"going '{i['going']}'): the winner {win['horse']} is rated {win['rpr']:.0f}."]
        if i["method"] == "class prior":
            s.append(f"No runner had a usable mark, so the level ({i['base_rpr']:.0f} for the winner) "
                     f"is the class prior for this type of race and should be treated as provisional.")
        else:
            s.append(f"The level is set by {i['n_anchors']} anchor runner(s) with established marks "
                     f"(spread of implied levels {i['anchor_spread_lb']:.0f}lb"
                     + (", shrunk towards the class prior" if i["method"] == "anchor+prior" else "") + ").")
        strong = rated.loc[rated["note"].str.contains("career-best", na=False), "horse"].tolist()
        if strong:
            s.append("Career-best figures for " + ", ".join(strong) + ".")
        if "capped" in str(win["note"]):
            s.append("The winner's margin was not fully credited; the figure is capped relative to the runner-up.")
        if i["n_non_finishers"]:
            s.append(f"{int(i['n_non_finishers'])} runner(s) unrated (pulled up / fell / disqualified).")
        return " ".join(s[:5])


# --------------------------------------------------------------------------- #
# Convenience entry point
# --------------------------------------------------------------------------- #

def compute_rpr(races_raw: pd.DataFrame, runners_raw: pd.DataFrame,
                cfg: Optional[RPRConfig] = None) -> Tuple[pd.DataFrame, pd.DataFrame, "RPRModel"]:
    """Return (ratings, race_info, model)."""
    model = RPRModel(cfg)
    ratings, info = model.fit(races_raw, runners_raw)
    return ratings, info, model


if __name__ == "__main__":  # smoke test on a synthetic race
    races = pd.DataFrame([{
        "race_id": "T1", "date": "20260901", "hippodrome": "CHANTILLY", "race_no": 1,
        "race_name": "PRIX TEST", "statut": "ARRIVEE_DEFINITIVE_COMPLETE", "distance_m": 1600,
        "going": "Bon souple", "going_value": "3,4", "categorie": "HANDICAP_DIVISE", "prize_eur": 30000,
    }])
    runners = pd.DataFrame({
        "race_id": "T1", "horse": list("ABCDE"), "status": "PARTANT", "age": [4, 3, 5, 4, 3],
        "sex": ["MALES", "FEMELLES", "HONGRES", "MALES", "HONGRES"],
        "weight_kg": [60, 57, 58.5, 56, 55], "rating": [38, 36, 36.5, 34, 33],
        "finish_pos": [1, 2, 3, 4, np.nan], "lengths_behind": [0, 0.5, 2.0, 5.0, np.nan],
        "lengths_prev": [np.nan, 0.5, 1.5, 3.0, np.nan], "incident": [None, None, None, None, "ARRETE"],
    })
    r, i, m = compute_rpr(races, runners)
    print(m.table("T1").to_string(index=False))
    print(m.narrative("T1"))
