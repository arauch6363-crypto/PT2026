"""
RTR und ARR – die beiden Ratings aus PT_Vorarbeiten.ipynb, übertragen auf die PMU-Tabellen.

RTR  "rating after race" (Notebook: update_ratings_with_history, Abschnitt 6/8)
     Elo-artig, Rennen für Rennen in zeitlicher Reihenfolge. Startwert = Rating (kg) beim ersten
     Lauf, sonst 30. In jedem Rennen tritt jeder Starter gegen jeden an:
         erwartet  = Stufe((Rating_i − 0,625·Gewicht_i) − (Rating_j − 0,625·Gewicht_j))
         tatsächl. = Stufe((Längen_j − Längen_i) · kg je Länge)
         Überraschung = tatsächlich − erwartet
     Stufe(l) = ±(1 + 4·log10(1 + 9·|l|/6)), ab 6 gekappt bei ±5.
     RTR_neu = RTR_alt + K · (Ø Überraschung + Preisbonus),  K = 0,5,
     Preisbonus = (Preis-Quantil − 0,5) · 5 · exp(−0,07 · Lauf-Nr. des Pferdes).

ARR  (Notebook: calculate_arr, Abschnitt 8.2)
     Leistung im Rennen, gemessen an den Pferden im vorderen Drittel des Einlaufs (pos_perc > 0,66; Sieger = 1)
     als Referenz. Für jede Referenz r und jedes Pferd j:
         Wert = (Längen_r − Längen_j) · kpl / max(log4(Längen_r − Längen_j), 1)
                + (Gewicht_j − Gewicht_r) · kpl + Rating_r
     (für die Referenz selbst: Rating_r).  ARR_j = Ø über die Referenzen, nicht unter 0.
     Fehlende Ratings werden vorher wie in Abschnitt 8.1 ergänzt: Ø des ersten bekannten Ratings
     anderer Pferde mit gleichem Platzbereich (pos_perc in Fünfteln), Alter, Kategorie und einem
     Preisgeld innerhalb ±7,5 %, die im jeweiligen Lauf selbst auch ohne Rating waren.

kg je Länge (kpl) nach Bodenklasse (VERY SLOW … VERY FAST, PSF) und 200-m-Distanzgruppe wie im Notebook.

Eingabe (eine Zeile je Starter mit Platz, nur Rennen mit Einlauf):
    race_id, date, horse, finish_pos, lengths_back (kumuliert zum Sieger, Sieger 0), weight_kg,
    rating (kg, darf fehlen), age, going_category, distance_group, prize, categorie, horse_run
Ausgabe: dieselben Zeilen plus rtr, arr, rating_filled.

Bewusste Abweichungen vom Notebook (sonst entstehen NaN, die ein Pferd dauerhaft ausschließen):
    * fehlendes Gewicht -> Ø des Feldes (nur für RTR; ARR bleibt dort leer, wie im Notebook)
    * fehlende Bodenklasse -> FAST (RTR; wie der Vorgabewert im Notebook), ARR bleibt leer
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

KG_PER_LENGTH = {
    "VERY SLOW": {"0-1000": 1.2, "1001-1200": 1.1, "1201-1400": 1.0,
                  "1401-1600": 0.95, "1601-1800": 0.9, "1801-2000": 0.85,
                  "2001-2200": 0.8, "2201-2400": 0.75, "2401-2600": 0.7,
                  "2601-2800": 0.65, "2801-3000": 0.6, "3001-3200": 0.55,
                  "3201-3400": 0.5, "3401-3600": 0.45, ">3600": 0.4},
    "SLOW":      {"0-1000": 1.3, "1001-1200": 1.2, "1201-1400": 1.1,
                  "1401-1600": 1.05, "1601-1800": 1.0, "1801-2000": 0.95,
                  "2001-2200": 0.9, "2201-2400": 0.85, "2401-2600": 0.8,
                  "2601-2800": 0.75, "2801-3000": 0.7, "3001-3200": 0.65,
                  "3201-3400": 0.6, "3401-3600": 0.55, ">3600": 0.5},
    "FAST":      {"0-1000": 1.5, "1001-1200": 1.4, "1201-1400": 1.3,
                  "1401-1600": 1.2, "1601-1800": 1.15, "1801-2000": 1.1,
                  "2001-2200": 1.05, "2201-2400": 1.0, "2401-2600": 0.95,
                  "2601-2800": 0.9, "2801-3000": 0.85, "3001-3200": 0.8,
                  "3201-3400": 0.75, "3401-3600": 0.7, ">3600": 0.65},
    "VERY FAST": {"0-1000": 1.6, "1001-1200": 1.5, "1201-1400": 1.4,
                  "1401-1600": 1.3, "1601-1800": 1.25, "1801-2000": 1.2,
                  "2001-2200": 1.15, "2201-2400": 1.1, "2401-2600": 1.05,
                  "2601-2800": 1.0, "2801-3000": 0.95, "3001-3200": 0.9,
                  "3201-3400": 0.85, "3401-3600": 0.8, ">3600": 0.75},
    "PSF":       {"0-1000": 1.4, "1001-1200": 1.3, "1201-1400": 1.2,
                  "1401-1600": 1.1, "1601-1800": 1.05, "1801-2000": 1.0,
                  "2001-2200": 0.95, "2201-2400": 0.9, "2401-2600": 0.85,
                  "2601-2800": 0.8, "2801-3000": 0.75, "3001-3200": 0.7,
                  "3201-3400": 0.65, "3401-3600": 0.6, ">3600": 0.55},
}

# PMU-Bodenbegriff (racecard.going_klasse) -> Bodenklasse des Notebooks
GOING_KATEGORIE = {
    "LOURD": "VERY SLOW", "TRES LOURD": "VERY SLOW", "COLLANT": "VERY SLOW",
    "SOUPLE": "SLOW", "TRES SOUPLE": "SLOW",
    "BON SOUPLE": "FAST", "BON": "FAST",
    "LEGER": "VERY FAST", "BON LEGER": "VERY FAST", "TRES LEGER": "VERY FAST",
    "PSF": "PSF",
}

START_RATING = 30.0
K_FAKTOR = 0.5            # wie im Notebook beim Aufruf (k_factor=0.5)
ALPHA = 0.07
GEWICHT_FAKTOR = 0.625    # kg Rating je kg Gewicht beim erwarteten Ergebnis
ARR_REF_POS = 0.66        # Referenzpferde: pos_perc > 0,66 (vorderes Drittel, Sieger = 1)
BACKFILL_TOL = 0.075      # Preisgeld ±7,5 % beim Ergänzen fehlender Ratings
POS_BINS = [0, 0.2, 0.4, 0.6, 0.8, 1.001]


def distance_group(m) -> str | None:
    if m is None or pd.isna(m):
        return None
    m = int(m)
    if m <= 1000:
        return "0-1000"
    if m > 3600:
        return ">3600"
    lower = ((m - 1) // 200) * 200 + 1
    return f"{lower}-{lower + 199}"


def stufe(l):
    """signed_bucket des Notebooks, vektorisiert: ±(1 + 4·log10(1 + 9·|l|/6)), ab |l| ≥ 6 gleich ±5."""
    l = np.asarray(l, dtype=float)
    a = np.abs(l)
    m = np.where(a >= 6.0, 5.0, 1.0 + 4.0 * np.log1p(9 * np.minimum(a, 6.0) / 6.0) / np.log(10))
    return np.where(l >= 0, m, -m)


def _kpl(going, dgroup, vorgabe_fast: bool) -> float | None:
    g = going if isinstance(going, str) and going else ("FAST" if vorgabe_fast else None)
    if g is None:
        return None
    tab = KG_PER_LENGTH.get(g.upper())
    if tab is None:
        tab = KG_PER_LENGTH["FAST"] if vorgabe_fast else None
    if tab is None:
        return None
    if dgroup in tab:
        return tab[dgroup]
    return 1.0 if vorgabe_fast else None


def _rennen(df: pd.DataFrame):
    """(race_id, Zeilenindex) je Rennen, zeitlich sortiert; innerhalb des Rennens nach Platz."""
    df = df.sort_values(["date", "race_id", "finish_pos"], kind="stable")
    rid = df["race_id"].to_numpy()
    if not len(rid):
        return df, []
    cut = np.flatnonzero(rid[1:] != rid[:-1]) + 1
    return df, list(zip(np.r_[0, cut], np.r_[cut, len(rid)]))


# --------------------------------------------------------------------------
# RTR
# --------------------------------------------------------------------------
def rtr(df: pd.DataFrame, k: float = K_FAKTOR, alpha: float = ALPHA, initial: dict | None = None,
        praemie: str = "feld") -> pd.Series:
    """rating_after_race je Zeile (Index wie df).

    praemie="feld" rechnet das Preis-Quantil wie das Notebook innerhalb des Rennens – dort haben alle
    Starter dasselbe Preisgeld, das Quantil ist also (n+1)/(2n) und der Bonus sehr klein.
    praemie="gesamt" nimmt stattdessen das Quantil des Preisgelds unter allen Rennen."""
    ratings = dict(initial or {})
    d, bereiche = _rennen(df)
    horse = d["horse"].to_numpy(object)
    w = pd.to_numeric(d["weight_kg"], errors="coerce").to_numpy(float)
    lb = pd.to_numeric(d["lengths_back"], errors="coerce").fillna(0).to_numpy(float)
    hc = pd.to_numeric(d["rating"], errors="coerce").to_numpy(float)
    run = pd.to_numeric(d["horse_run"], errors="coerce").fillna(1).to_numpy(float)
    going = d["going_category"].to_numpy(object)
    dgrp = d["distance_group"].to_numpy(object)
    if praemie == "gesamt":
        pr = d.drop_duplicates("race_id").set_index("race_id")["prize"]
        q_rennen = pd.to_numeric(pr, errors="coerce").rank(pct=True).fillna(0.5)
        q_all = d["race_id"].map(q_rennen).to_numpy(float)
    out = np.full(len(d), np.nan)

    for a, b in bereiche:
        n = b - a
        hs = horse[a:b]
        r0 = np.array([ratings.get(h, np.nan) for h in hs], dtype=float)
        neu = np.isnan(r0)
        r0[neu] = np.where(np.isnan(hc[a:b][neu]), START_RATING, hc[a:b][neu])
        ww = w[a:b].copy()
        if np.isnan(ww).any():
            ww[np.isnan(ww)] = np.nanmean(ww) if (~np.isnan(ww)).any() else 0.0
        if n > 1:
            mult = _kpl(going[a], dgrp[a], vorgabe_fast=True)
            perf = r0 - GEWICHT_FAKTOR * ww
            l = lb[a:b]
            erwartet = stufe(perf[:, None] - perf[None, :])
            tatsaechlich = stufe((l[None, :] - l[:, None]) * mult)
            s = np.triu(tatsaechlich - erwartet, 1)          # Paare i < j in Einlaufreihenfolge
            avg = (s.sum(axis=1) - s.sum(axis=0)) / (n - 1)
        else:
            avg = np.zeros(1)
        q = q_all[a:b] if praemie == "gesamt" else np.full(n, (n + 1) / (2 * n))
        bonus = (q - 0.5) * 5 * np.exp(-alpha * run[a:b])
        r1 = r0 + k * (avg + bonus)
        out[a:b] = r1
        for h, v in zip(hs, r1):
            ratings[h] = v
    return pd.Series(out, index=d.index).reindex(df.index)


# --------------------------------------------------------------------------
# Fehlende Ratings ergänzen (Notebook 8.1)
# --------------------------------------------------------------------------
def ratings_ergaenzen(df: pd.DataFrame, tol: float = BACKFILL_TOL) -> pd.Series:
    """Rating je Zeile, fehlende wie im Notebook ergänzt (Index wie df)."""
    hc = pd.to_numeric(df["rating"], errors="coerce")
    fehlt = hc.isna()
    if not fehlt.any():
        return hc
    erstes = (df[hc.notna()].assign(_r=hc).sort_values("date", kind="stable")
                .drop_duplicates("horse")[["horse", "_r"]].set_index("horse")["_r"])
    t = df.loc[fehlt, ["horse", "pos_perc", "age", "categorie", "prize"]].copy()
    # ohne Platzbereich eine eigene Gruppe: im Notebook trifft beim Merge NaN auf NaN
    t["bin"] = pd.cut(t["pos_perc"], bins=POS_BINS, labels=False, right=False).fillna(-1)
    t["age"] = pd.to_numeric(t["age"], errors="coerce").fillna(-1)
    t["categorie"] = t["categorie"].fillna("__NULL__")
    t["prize"] = pd.to_numeric(t["prize"], errors="coerce")
    t["ref"] = t["horse"].map(erstes)
    keys = ["bin", "age", "categorie"]
    wert = pd.Series(np.nan, index=t.index)
    for _, g in t.dropna(subset=["bin", "prize"]).groupby(keys, sort=False):
        pool = g[g["ref"].notna()].sort_values("prize", kind="stable")
        if pool.empty:
            continue
        pp, pv = pool["prize"].to_numpy(float), pool["ref"].to_numpy(float)
        cs = np.r_[0, np.cumsum(pv)]
        p = g["prize"].to_numpy(float)
        lo = np.searchsorted(pp, p * (1 - tol), side="left")
        hi = np.searchsorted(pp, p * (1 + tol), side="right")
        summe, anzahl = cs[hi] - cs[lo], (hi - lo).astype(float)
        # Zeilen desselben Pferdes zählen nicht (das Notebook schließt horseId_runner == horseId_ref aus)
        ph = pool["horse"].to_numpy(object)
        for i, h in enumerate(g["horse"].to_numpy(object)):
            if anzahl[i] == 0:
                continue
            eigen = ph[lo[i]:hi[i]] == h
            if eigen.any():
                summe[i] -= pv[lo[i]:hi[i]][eigen].sum()
                anzahl[i] -= eigen.sum()
        with np.errstate(invalid="ignore", divide="ignore"):
            wert.loc[g.index] = np.where(anzahl > 0, summe / anzahl, np.nan)
    return hc.fillna(wert)


# --------------------------------------------------------------------------
# ARR
# --------------------------------------------------------------------------
def arr(df: pd.DataFrame, rating_col: str = "rating_filled") -> pd.Series:
    """ARR je Zeile (Index wie df)."""
    d, bereiche = _rennen(df)
    clb = np.maximum(pd.to_numeric(d["lengths_back"], errors="coerce").fillna(0).to_numpy(float), 0)
    wkg = pd.to_numeric(d["weight_kg"], errors="coerce").to_numpy(float)
    hc = pd.to_numeric(d[rating_col], errors="coerce").to_numpy(float)
    pos = pd.to_numeric(d["pos_perc"], errors="coerce").to_numpy(float)
    going = d["going_category"].to_numpy(object)
    dgrp = d["distance_group"].to_numpy(object)
    out = np.full(len(d), np.nan)
    for a, b in bereiche:
        kpl = _kpl(going[a], dgrp[a], vorgabe_fast=False)
        if kpl is None:
            continue
        mask = pos[a:b] > ARR_REF_POS
        if not mask.any():
            continue
        c, wk, h = clb[a:b], wkg[a:b], hc[a:b]
        ld = c[mask][:, None] - c[None, :]
        with np.errstate(divide="ignore", invalid="ignore"):
            logf = np.where(ld > 0, np.maximum(np.log(np.where(ld > 0, ld, 1)) / np.log(4), 1.0), 1.0)
        wd = wk[None, :] - wk[mask][:, None]
        hr = h[mask][:, None]
        ref = ld * kpl / logf + wd * kpl + hr
        ref = np.where(np.flatnonzero(mask)[:, None] == np.arange(b - a)[None, :], hr, ref)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)          # Spalte nur aus NaN
            v = np.nanmean(ref, axis=0)
        out[a:b] = np.round(np.where(np.isnan(v), np.nan, np.maximum(v, 0)), 2)
    return pd.Series(out, index=d.index).reindex(df.index)


def berechnen(df: pd.DataFrame, **kw) -> pd.DataFrame:
    """RTR, ergänztes Rating und ARR für alle Zeilen."""
    df = df.copy()
    n = df.groupby("race_id")["race_id"].transform("count")
    df["pos_perc"] = (n - pd.to_numeric(df["finish_pos"], errors="coerce")) / (n - 1).where(n > 1)
    df["rtr"] = rtr(df, **kw).round(1)
    df["rating_filled"] = ratings_ergaenzen(df)
    df["arr"] = arr(df)
    return df
