"""
ΔL600 und ΔB200: Tempo der Schlussphase gegenüber der Erwartung – Pferde werden nur mit den Startern
verglichen, die am selben Tag auf derselben Bahn liefen.

    L600  = Tempo der letzten 600 m (km/h)
    B200  = schnellstes 200-m-Segment in den letzten 800 m (km/h)

Für beide Zielgrößen wird eine Regression mit festen Effekten geschätzt:

    Tempo = Renntag×Bahn + Bahn×Distanz + Pace-Ratio (linear + quadratisch je Distanzgruppe)   [A]
                                        + Klasse: log(Preisgeld), conditions_age               [B]

Der feste Effekt Renntag×Bahn ("meeting") nimmt alles heraus, was an diesem Tag auf dieser Bahn für alle
gleich war (Boden, Wind, Bahnzustand): das Pferd wird nur mit den Startern desselben Renntags verglichen.
Bahn×Distanz ("cell") nimmt die Eigenheiten des Kurses heraus. Das Residuum ist das Δ in km/h:
positiv = schneller als für dieses Rennen (Tempo, bei B auch Klasse) an diesem Tag zu erwarten.

Rennen gehen nur ein, wenn die Pace-Ratio im 1.–99. Perzentil liegt und die Kombination Bahn×Distanz
mindestens MIN_RACES_CELL Rennen hat. Seltene Altersklassen (< MIN_RACES_AGE Rennen) werden "SONSTIGE".
Nach der Vorlage im Notebook (Compiègne-Auswertung); die festen Effekte werden hier mit numpy statt
groupby herausgerechnet (gleiches Verfahren, alternierende Projektionen, deutlich schneller).
"""
from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd

MIN_RACES_CELL = 5          # Mindestzahl Rennen je Bahn × Distanz
MIN_RACES_AGE = 30          # seltenere conditions_age-Kategorien -> "SONSTIGE"
PACE_Q = (0.01, 0.99)       # Rennen mit Pace-Ratio außerhalb dieser Quantile fallen heraus
BANDS = [0, 1400, 1900, 2400, 99999]
BAND_LABELS = ["Sprint ≤1400", "Meile 1401-1900", "Mittel 1901-2400", "Lang >2400"]
B200_BEREICH_M = 800        # schnellstes Segment nur aus den letzten 800 m
B200_SEG_M = (150, 250)     # nur Segmente von etwa 200 m
B200_KMH = (40, 80)         # plausible Segmentgeschwindigkeit
L600_KMH = (40, 75)
DEMEAN_ITERS, DEMEAN_TOL = 200, 1e-7

ZIELE = {"L600": "speed_last600_kmh", "B200": "best200_kmh"}
SPALTEN = ["d_L600_A", "d_L600_B", "d_B200_A", "d_B200_B"]
LETZTE_INFO: dict = {}      # Koeffizienten und Umfang der letzten Schätzung (für die Ausgabe in racecard.run)


def norm(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper().strip()


def best200(sections: pd.DataFrame | None) -> pd.DataFrame:
    """Schnellstes ~200-m-Segment in den letzten 800 m je Pferd: race_id, saddle_no, best200_kmh, best200_seg."""
    leer = pd.DataFrame(columns=["race_id", "saddle_no", "best200_kmh", "best200_seg"])
    if sections is None or sections.empty:
        return leer
    s = sections.copy()
    for c in ["saddle_no", "m_to_go", "seg_len_m", "split_s", "speed_kmh"]:
        s[c] = pd.to_numeric(s[c], errors="coerce") if c in s else np.nan
    # Tempo aus der Abschnittsliste; fehlt es, aus Länge und Zeit
    s["speed_kmh"] = s["speed_kmh"].fillna(s["seg_len_m"] / s["split_s"] * 3.6)
    # m_to_go ist das Ende des Abschnitts, wenn die Rennen meist bei 0 enden (sonst der Beginn)
    end_based = (s.groupby("race_id")["m_to_go"].min() == 0).mean() > 0.5
    start = s["m_to_go"] + (s["seg_len_m"] if end_based else 0)
    s = s[(start <= B200_BEREICH_M) & s["seg_len_m"].between(*B200_SEG_M) & s["speed_kmh"].between(*B200_KMH)]
    if s.empty:
        return leer
    b = s.loc[s.groupby(["race_id", "saddle_no"])["speed_kmh"].idxmax()].copy()
    von = b["seg_from"].astype(str) if "seg_from" in b else start[b.index].astype(int).astype(str) + "m"
    bis = b["seg_to"].astype(str) if "seg_to" in b else b["m_to_go"].astype(int).astype(str) + "m"
    b["best200_seg"] = von + "→" + bis
    return b.rename(columns={"speed_kmh": "best200_kmh"})[["race_id", "saddle_no", "best200_kmh", "best200_seg"]]


def _demean(M: np.ndarray, codes: list[np.ndarray], iters: int = DEMEAN_ITERS, tol: float = DEMEAN_TOL) -> np.ndarray:
    """Zieht mehrere feste Effekte heraus (alternierende Projektionen), alle Spalten auf einmal.
    codes: je fester Effekt die Gruppennummern 0..k-1 (pd.factorize)."""
    out = M.astype(float).copy()
    plaene = []
    for g in codes:
        order = np.argsort(g, kind="stable")
        gs = g[order]
        starts = np.flatnonzero(np.r_[True, gs[1:] != gs[:-1]])
        plaene.append((g, order, starts, np.diff(np.r_[starts, len(g)]).astype(float)[:, None]))
    for _ in range(iters):
        alt = out.copy()
        for g, order, starts, n in plaene:
            mittel = np.add.reduceat(out[order], starts, axis=0) / n
            out -= mittel[g]
        if np.max(np.abs(out - alt)) < tol:
            break
    return out


def _gruppen_mittel(M: np.ndarray, g: np.ndarray, k: int) -> np.ndarray:
    n = np.bincount(g, minlength=k).astype(float)
    summe = np.zeros((k, M.shape[1]))
    np.add.at(summe, g, M)
    return summe / np.maximum(n, 1)[:, None]


def _demean2(M: np.ndarray, g1: np.ndarray, g2: np.ndarray) -> np.ndarray:
    """Zwei feste Effekte exakt herausrechnen (statt iterativ): g1 direkt durch Abziehen der
    Gruppenmittel, g2 über die Normalgleichungen der innerhalb g1 zentrierten g2-Dummies
    (Frisch-Waugh-Lovell). Gleiches Ergebnis wie _demean bei voller Konvergenz."""
    k1, k2 = int(g1.max()) + 1, int(g2.max()) + 1
    Mt = M.astype(float) - _gruppen_mittel(M.astype(float), g1, k1)[g1]
    n1 = np.bincount(g1, minlength=k1).astype(float)
    A = np.bincount(g1 * k2 + g2, minlength=k1 * k2).reshape(k1, k2).astype(float)   # Starts je g1 × g2
    S = np.diag(np.bincount(g2, minlength=k2).astype(float)) - A.T @ (A / n1[:, None])
    R = np.zeros((k2, M.shape[1]))
    np.add.at(R, g2, Mt)
    theta = np.linalg.lstsq(S, R, rcond=None)[0]          # singulär (eine Stufe je Teilnetz) – Residuen eindeutig
    eff = theta[g2]
    return Mt - (eff - _gruppen_mittel(eff, g1, k1)[g1])


def _fit_fe_ab(d: pd.DataFrame, target: str, cols_a: list[str], cols_b: list[str],
               fe=("meeting", "cell")) -> tuple[pd.Series, pd.Series, pd.Series]:
    """OLS mit festen Effekten für Modell A (cols_a) und B (cols_b ⊇ cols_a).
    Residuen (= Δ zur Erwartung) für A und B, Koeffizienten von B. Das Herausrechnen der festen
    Effekte wirkt spaltenweise, deshalb genügt ein Durchlauf für beide Modelle."""
    sub = d[d[target].notna()]
    if sub.empty:
        leer = pd.Series(dtype=float)
        return leer, leer, pd.Series(np.nan, index=cols_b)
    codes = [pd.factorize(sub[g])[0] for g in fe]
    M = sub[[target] + cols_b].to_numpy(float)
    k2 = int(codes[1].max()) + 1 if len(codes) == 2 else 0
    # exakt, solange die Matrix Renntag × Zelle klein genug bleibt; sonst iterativ wie im Notebook
    dm = (_demean2(M, codes[0], codes[1]) if len(codes) == 2 and (int(codes[0].max()) + 1) * k2 <= 4e7
          else _demean(M, codes))
    Y, XB = dm[:, 0], dm[:, 1:]
    XA = XB[:, [cols_b.index(c) for c in cols_a]]
    bA, *_ = np.linalg.lstsq(XA, Y, rcond=None)
    bB, *_ = np.linalg.lstsq(XB, Y, rcond=None)
    return (pd.Series(Y - XA @ bA, index=sub.index), pd.Series(Y - XB @ bB, index=sub.index),
            pd.Series(bB, index=cols_b))


def berechnen(h: pd.DataFrame, sections: pd.DataFrame | None = None) -> pd.DataFrame:
    """ΔL600 / ΔB200 nach Modell A und B je Lauf (Spalten SPALTEN, dazu best200_kmh, best200_seg).

    Erwartet je Starter: race_id, saddle_no, date, course_key (Bahn), distance_m, pace_ratio, prize_eur,
    conditions_age, speed_last600_kmh."""
    global LETZTE_INFO
    h = h.copy()
    for c in SPALTEN + ["best200_kmh"]:
        h[c] = np.nan
    h["best200_seg"] = None
    if h.empty:
        return h
    b = best200(sections)
    if len(b):
        b["saddle_no"] = pd.to_numeric(b["saddle_no"], errors="coerce")
        h = h.drop(columns=["best200_kmh", "best200_seg"]).merge(b, on=["race_id", "saddle_no"], how="left")
        h.index = pd.RangeIndex(len(h))

    # 1) Rennen: Pace-Ratio im 1.–99. Perzentil, Bahn × Distanz mit genug Rennen
    rc = h.drop_duplicates("race_id")[["race_id", "date", "course_key", "distance_m", "pace_ratio",
                                       "prize_eur", "conditions_age"]].copy()
    rc["pace_ratio"] = pd.to_numeric(rc["pace_ratio"], errors="coerce")
    rc = rc[rc["pace_ratio"].notna() & rc["distance_m"].notna() & rc["course_key"].notna() & rc["date"].notna()]
    if len(rc) < MIN_RACES_CELL:
        LETZTE_INFO = {"rennen": 0}
        return h
    lo, hi = rc["pace_ratio"].quantile(list(PACE_Q))
    rc = rc[rc["pace_ratio"].between(lo, hi)]
    rc["trk"] = rc["course_key"].astype(str).map(norm)
    rc["cell"] = rc["trk"] + "_" + rc["distance_m"].astype(int).astype(str)
    rc["meeting"] = rc["trk"] + "_" + pd.to_datetime(rc["date"]).dt.strftime("%Y-%m-%d")
    n_cell = rc.groupby("cell")["race_id"].nunique()
    rc = rc[rc["cell"].isin(n_cell[n_cell >= MIN_RACES_CELL].index)].copy()
    if rc.empty:
        LETZTE_INFO = {"rennen": 0}
        return h
    rc["band"] = pd.cut(rc["distance_m"], BANDS, labels=BAND_LABELS)

    # 2) Klasse: conditions_age (seltene -> SONSTIGE), log(Preisgeld) zentriert, fehlend -> Median + Flag
    rc["age_cond"] = rc["conditions_age"].map(lambda x: norm(x) if pd.notna(x) and str(x).strip() else "UNBEKANNT")
    age_n = rc["age_cond"].value_counts()
    rc.loc[rc["age_cond"].map(age_n) < MIN_RACES_AGE, "age_cond"] = "SONSTIGE"
    prize = pd.to_numeric(rc["prize_eur"], errors="coerce")
    rc["prize_missing"] = prize.isna().astype(float)
    rc["log_prize"] = np.log1p(prize.fillna(prize.median() if prize.notna().any() else 0))
    rc["log_prize_c"] = rc["log_prize"] - rc["log_prize"].median()
    pace_med = rc["pace_ratio"].median()

    # 3) Starter dieser Rennen mit den Zielgrößen
    merkmale = rc[["race_id", "trk", "cell", "meeting", "band", "pace_ratio", "age_cond", "prize_missing",
                   "log_prize_c"]]
    d = (h.loc[h["race_id"].isin(set(rc["race_id"])), ["race_id", "speed_last600_kmh", "best200_kmh"]]
          .reset_index().merge(merkmale, on="race_id", how="left").set_index("index"))
    d["speed_last600_kmh"] = pd.to_numeric(d["speed_last600_kmh"], errors="coerce").where(
        lambda v: v.between(*L600_KMH))

    # 4) Regressoren: A = Tempo je Distanzgruppe, B = A + Klasse
    pace_cols = []
    for bl in BAND_LABELS:
        m = (d["band"] == bl).astype(float)
        d[f"pr|{bl}"] = (d["pace_ratio"] - pace_med) * m
        d[f"pr2|{bl}"] = d[f"pr|{bl}"] ** 2
        pace_cols += [f"pr|{bl}", f"pr2|{bl}"]
    ref_age = d["age_cond"].value_counts().idxmax()
    age_cols = []
    for a in sorted(d["age_cond"].unique()):
        if a != ref_age:
            d[f"age|{a}"] = (d["age_cond"] == a).astype(float)
            age_cols.append(f"age|{a}")
    class_cols = ["log_prize_c", "prize_missing"] + age_cols

    info = {"rennen": int(d["race_id"].nunique()), "starts": int(len(d)), "bahnen": int(d["trk"].nunique()),
            "ref_age": ref_age, "ziele": {}}
    for name, col in ZIELE.items():
        rA, rB, bB = _fit_fe_ab(d, col, pace_cols, pace_cols + class_cols)
        h.loc[rA.index, f"d_{name}_A"] = rA
        h.loc[rB.index, f"d_{name}_B"] = rB
        ok = d[col].notna().any()
        info["ziele"][name] = {"n": int(d[col].notna().sum()),
                               "preis_x2": float(bB["log_prize_c"] * np.log(2)) if ok else None,
                               "alter": {c[4:]: float(bB[c]) for c in age_cols} if ok else {}}
    LETZTE_INFO = info
    return h


def bericht(info: dict | None = None) -> str:
    """Kurzbericht der Klasseneffekte (Modell B), wie im Notebook ausgegeben."""
    info = info or LETZTE_INFO
    if not info or not info.get("rennen"):
        return "ΔL600/ΔB200: zu wenige Rennen mit Tracking und Pace-Ratio – keine Schätzung."
    z = [f"ΔL600/ΔB200 geschätzt aus {info['starts']:,} Starts, {info['rennen']:,} Rennen, {info['bahnen']} Bahnen "
         f"(Vergleich nur innerhalb Renntag × Bahn)"]
    for name, e in info["ziele"].items():
        z.append(f"  {name}: {e['n']:,} Läufe · Preisgeld ×2 -> "
                 + (f"{e['preis_x2']:+.2f} km/h" if e["preis_x2"] is not None else "–")
                 + "".join(f" · {a} {v:+.2f}" for a, v in e["alter"].items())
                 + f"  (Altersklassen gegen {info['ref_age']})")
    return "\n".join(z)
