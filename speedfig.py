"""
Bereinigte Leistungskennzahlen aus den Tracking-Daten: L600, L400, Best Seg und Finish-Index.

Jede Rohzeit vermischt drei Dinge: die Bedingungen (Distanz, Boden, Bahn), den Rennverlauf
(wie schnell vorne angegangen wurde) und die eigentliche Leistung des Pferdes. Die Kennzahl
wird deshalb in vier Stufen aufgebaut:

1. Einheitliche Basis
   L600, L400 und Best Seg als Geschwindigkeit in m/s. Best Seg nur aus den letzten
   BEST_SEG_BEREICH_M Metern, sonst würde bei Sprints der Startspeed mit dem Endspeed
   verglichen.

2. Rennanteil und Pferdeanteil
   Rennreferenz = Median der vorderen Hälfte des Einlaufs (weit Geschlagene werden oft
   ausgeritten und verfälschen den Schnitt). Pferdeanteil = Pferd minus Rennreferenz.

3. Par für den Rennanteil
   Erwartete Rennreferenz aus Distanz (stetig), Boden (Penetrometer, ersatzweise Mittel der
   Bodenklasse, dazu die Klasse selbst), Bahn und Pace-Ratio des Rennens. Geschätzt als
   Ridge-Regression auf Rennebene: seltene Bahnen und Bodenklassen werden zum Gesamtmittel
   gezogen. Die Abweichung der Rennreferenz vom Par ist der Renneffekt; er wird wie ein
   zufälliger Effekt geschrumpft, je weniger Pferde die Referenz tragen.

4. Kennzahl je Pferd
   bereinigt = geschrumpfter Renneffekt + Pferdeanteil, positiv = schneller als erwartet.
   Ausgedrückt in Längen (LAENGE_M Meter je Länge) über die jeweilige Strecke, der
   Finish-Index in Indexpunkten. Weit geschlagene Pferde (> AUSGERITTEN_L Längen) werden
   markiert und gehen nicht in Durchschnitte ein.

validierung() prüft Wiederholbarkeit (Korrelation aufeinanderfolgender Läufe desselben
Pferdes) und Prognosekraft (Korrelation mit dem nächsten Ergebnis) – bereinigt gegen roh.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LAENGE_M = 2.4                  # Meter je Länge
AUSGERITTEN_L = 10.0            # ab so vielen Längen Rückstand gilt ein Lauf als unzuverlässig
BEST_SEG_BEREICH_M = 800        # Best Seg nur aus Abschnitten innerhalb der letzten 800 m
MIN_REF = 2                     # so viele Pferde der vorderen Hälfte braucht eine Rennreferenz
RIDGE = 5.0                     # Schrumpfung für Bahn- und Bodenklassen-Effekte (in "Rennen")
MIN_RENNEN = 30                 # so viele Rennen braucht das Par-Modell

# Kennzahl -> (Rohspalte in m/s bzw. Index, Strecke in m für die Umrechnung in Längen)
KENNZAHLEN = {"v600": 600, "v400": 400, "vbest": None, "fi": None}


def best_seg_final(sections: pd.DataFrame, bereich: int = BEST_SEG_BEREICH_M) -> pd.DataFrame:
    """Schnellster Abschnitt je Starter innerhalb der letzten `bereich` Meter.
    -> race_id, saddle_no, vbest (m/s), best_seg_len_m, best_seg_to_go_m (Beginn des Abschnitts)"""
    cols = ["race_id", "saddle_no", "vbest", "best_seg_len_m", "best_seg_to_go_m"]
    if sections is None or sections.empty or not {"m_to_go", "seg_len_m", "split_s"} <= set(sections):
        return pd.DataFrame(columns=cols)
    s = sections.copy()
    for c in ["saddle_no", "m_to_go", "seg_len_m", "split_s"]:
        s[c] = pd.to_numeric(s[c], errors="coerce")
    s["start_to_go"] = s["m_to_go"] + s["seg_len_m"]
    s = s[(s["start_to_go"] <= bereich) & (s["split_s"] > 0) & (s["seg_len_m"] > 0)]
    s["vbest"] = s["seg_len_m"] / s["split_s"]
    s = s[s["vbest"].between(10, 21)]                       # 36–75 km/h, sonst Messfehler
    if s.empty:
        return pd.DataFrame(columns=cols)
    s = s.sort_values("vbest", ascending=False).drop_duplicates(["race_id", "saddle_no"])
    return s.rename(columns={"seg_len_m": "best_seg_len_m", "start_to_go": "best_seg_to_go_m"})[cols]


def _rennreferenz(h: pd.DataFrame, col: str) -> pd.DataFrame:
    """Median der vorderen Hälfte des Einlaufs je Rennen, dazu Streuung und Anzahl."""
    halb = np.ceil(h["n_runners"] / 2)
    vorn = h[(h["finish_pos"] <= halb) & h[col].notna()]
    g = vorn.groupby("race_id")[col]
    ref = pd.DataFrame({"ref": g.median(), "n_ref": g.count(), "var_ref": g.var()})
    return ref[ref["n_ref"] >= MIN_REF]


def _design(r: pd.DataFrame, going_mittel: dict | None = None) -> tuple[np.ndarray, np.ndarray, dict]:
    """Merkmale für das Par-Modell auf Rennebene. Rückgabe: X, Strafgewichte, Imputationswerte."""
    wert = pd.to_numeric(r["going_value"], errors="coerce").astype(float)
    if going_mittel is None:
        going_mittel = {k: float(v) for k, v in wert.groupby(r["going_class"]).mean().items() if pd.notna(v)}
    gesamt = float(np.mean(list(going_mittel.values()))) if going_mittel else 3.5
    gv = wert.fillna(r["going_class"].map(going_mittel)).fillna(gesamt).astype(float)
    d = pd.to_numeric(r["distance_m"], errors="coerce").astype(float) / 1000
    pace = (pd.to_numeric(r["pace_ratio"], errors="coerce").astype(float) - 100) / 5
    stetig = pd.DataFrame({"d": d, "d2": d ** 2, "gv": gv, "gv_fehlt": wert.isna().astype(float),
                           "psf": (r["going_class"] == "PSF").astype(float), "pace": pace, "pace2": pace ** 2})
    dummies = pd.get_dummies(r[["course_key", "going_class"]].astype("string").fillna("?"),
                             prefix=["bahn", "boden"], dtype=float)
    X = pd.concat([pd.Series(1.0, index=r.index, name="const"), stetig, dummies], axis=1)
    strafe = np.r_[0.0, np.zeros(stetig.shape[1]), np.full(dummies.shape[1], RIDGE)]
    return X, strafe, going_mittel


def _ridge(X: pd.DataFrame, y: pd.Series, strafe: np.ndarray) -> pd.Series:
    A = X.to_numpy(float)
    mu = A.mean(0)
    sd = A.std(0)
    sd[sd == 0] = 1
    stetige = strafe == 0
    stetige[0] = False                                        # Konstante nicht skalieren
    Z = A.copy()
    Z[:, stetige] = (A[:, stetige] - mu[stetige]) / sd[stetige]
    beta = np.linalg.solve(Z.T @ Z + np.diag(strafe) + 1e-9 * np.eye(len(strafe)), Z.T @ y.to_numpy(float))
    return pd.Series(Z @ beta, index=X.index)


def rennpar(h: pd.DataFrame, col: str) -> pd.DataFrame:
    """Rennreferenz, Par und geschrumpfter Renneffekt je Rennen für die Kennzahl `col`."""
    ref = _rennreferenz(h, col)
    rennen = (h.drop_duplicates("race_id").set_index("race_id")
                [["distance_m", "going_value", "going_class", "course_key", "pace_ratio"]])
    r = ref.join(rennen, how="inner")
    r = r[r["distance_m"].notna() & r["pace_ratio"].notna()]
    if len(r) < MIN_RENNEN:
        return pd.DataFrame(columns=["ref", "par", "renneffekt"])
    X, strafe, _ = _design(r)
    r["par"] = _ridge(X, r["ref"], strafe)
    resid = r["ref"] - r["par"]
    # Varianzanteile: innerhalb des Rennens (Messrauschen der Referenz) und zwischen Rennen
    s2_in = float(np.nanmean(r["var_ref"])) if r["var_ref"].notna().any() else 0.0
    rausch = s2_in / r["n_ref"] * (np.pi / 2)                 # Varianz eines Medians ≈ π/2 · σ²/n
    s2_zw = max(float(resid.var()) - float(rausch.mean()), 1e-9)
    r["renneffekt"] = resid * s2_zw / (s2_zw + rausch)
    return r[["ref", "par", "renneffekt"]]


def berechnen(h: pd.DataFrame, sections: pd.DataFrame | None = None) -> pd.DataFrame:
    """Fügt h die bereinigten Kennzahlen hinzu:
    v600_adj_l, v400_adj_l, best_adj_l (Längen, + = schneller als erwartet), fi_adj (Indexpunkte),
    best_seg_s (Zeit für 200 m im schnellsten Abschnitt der letzten 800 m), best_seg_to_go_m,
    ausgeritten (bool)."""
    h = h.copy()
    h["v600"] = h["speed_last600_kmh"] / 3.6
    h["v400"] = h["speed_last400_kmh"] / 3.6
    h["fi"] = h["finish_index"]
    b = best_seg_final(sections)
    h = h.drop(columns=[c for c in b.columns if c not in ("race_id", "saddle_no") and c in h])
    h = h.merge(b, on=["race_id", "saddle_no"], how="left")
    h["best_seg_s"] = 200 / h["vbest"]
    h["ausgeritten"] = h["lengths_behind"] > AUSGERITTEN_L
    for col, strecke in KENNZAHLEN.items():
        name = {"v600": "v600_adj_l", "v400": "v400_adj_l", "vbest": "best_adj_l", "fi": "fi_adj"}[col]
        par = rennpar(h, col) if h[col].notna().any() else pd.DataFrame()
        if par.empty:
            h[name] = np.nan
            continue
        ref = h["race_id"].map(par["ref"])
        effekt = h["race_id"].map(par["renneffekt"])
        diff = effekt + (h[col] - ref)                        # m/s bzw. Indexpunkte
        if col == "fi":
            h[name] = diff
        else:
            meter = strecke if strecke else h["best_seg_len_m"]
            zeit = meter / ref                                # Sekunden über die Strecke
            h[name] = diff * zeit / LAENGE_M                  # Vorsprung in Längen
    return h.drop(columns=["v600", "v400", "fi"])


def validierung(h: pd.DataFrame) -> pd.DataFrame:
    """Wiederholbarkeit (Korrelation zweier aufeinanderfolgender Läufe desselben Pferdes)
    und Prognosekraft (Rangkorrelation mit der Platzierung im nächsten Lauf, als Anteil des
    Feldes; negativ = höherer Wert, bessere nächste Platzierung) – bereinigt gegen roh."""
    paare = {"L600": ("speed_last600_kmh", "v600_adj_l"), "L400": ("speed_last400_kmh", "v400_adj_l"),
             "Best Seg": ("vbest", "best_adj_l"), "Finish-Index": ("finish_index", "fi_adj")}
    d = h.sort_values(["horse_id", "date"]).copy()
    d["pos_pct"] = (d["finish_pos"] - 1) / (d["n_runners"] - 1).clip(lower=1)
    g = d.groupby("horse_id")
    d["naechster_pos"] = g["pos_pct"].shift(-1)
    zeilen = []
    for name, (roh, adj) in paare.items():
        if roh not in d or adj not in d:
            continue
        z = {"Kennzahl": name}
        for art, c in (("roh", roh), ("bereinigt", adj)):
            ok = d[c].notna() & ~d["ausgeritten"].fillna(False)
            x = d[c].where(ok)
            naechst = x.groupby(d["horse_id"]).shift(-1)
            z[f"Wiederholbarkeit {art}"] = round(x.corr(naechst), 3)
            ok2 = x.notna() & d["naechster_pos"].notna()                 # Spearman ohne scipy
            z[f"Prognose {art}"] = round(x[ok2].rank().corr(d.loc[ok2, "naechster_pos"].rank()), 3)
        zeilen.append(z)
    return pd.DataFrame(zeilen)
