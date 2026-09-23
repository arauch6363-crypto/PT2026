"""
Bereinigte Leistungskennzahlen aus den Tracking-Daten: L600, L400, Best Seg und Finish-Index.

Jede Rohzeit vermischt drei Dinge: die Bedingungen (Distanz, Boden, Bahn), den Rennverlauf
(wie schnell vorne angegangen wurde) und die eigentliche Leistung des Pferdes. Die Kennzahl
wird deshalb in vier Stufen aufgebaut:

0. Rohwerte aus den gespeicherten Abschnitten (rohwerte_aus_abschnitten)
   L600, L400, Tempo 600–400 m und Finish-Index werden aus tracking_sections neu gebildet,
   nicht aus den beim Parsen abgelegten Spalten. Damit wirken die Korrekturen auch auf alte
   Daten, ohne ein PDF neu zu parsen:
   * fehlender Split -> kein Tempo (statt Strecke ohne Zeit = zu hohes Tempo)
   * Wegfaktor (gelaufene ÷ nominale Distanz) skaliert die Tempi, weil die Abschnittslängen
     nominal sind – ein Pferd außen herum lief tatsächlich schneller
   * Finish-Index = Tempo letzte 400 m ÷ Tempo davor (Start bis 400 m vor dem Ziel) × 100;
     vorher stand im Nenner das Durchschnittstempo inkl. Finish (mechanisch gekoppelt)
   * Gegenprobe: berechnete letzte 600 m gegen die offizielle Angabe der Übersichtsseite;
     weicht sie um mehr als LAST600_TOLERANZ_S ab, sind die Abschnitte dieses Pferdes nicht
     zu trauen und die Tempi der Schlussphase werden verworfen

1. Einheitliche Basis
   L600, L400 und Best Seg als Geschwindigkeit in m/s. Best Seg nur aus den letzten
   BEST_SEG_BEREICH_M Metern, sonst würde bei Sprints der Startspeed mit dem Endspeed
   verglichen.

2. Rennanteil und Pferdeanteil
   Rennreferenz = Median der vorderen Hälfte des Einlaufs (weit Geschlagene werden oft
   ausgeritten und verfälschen den Schnitt). Pferdeanteil = Pferd minus Rennreferenz.

3. Par für den Rennanteil
   Erwartete Rennreferenz aus Distanz (stetig), Boden (Penetrometer, ersatzweise Mittel der
   Bodenklasse, dazu die Klasse selbst), Bahn und dem FRÜHEN Tempo des Rennens (Führender bis
   ~600 m vor dem Ziel). Nicht die Pace-Ratio: deren Nenner ist das Schlusstempo der Spitze,
   also fast dasselbe wie die Referenz – das Par hätte den schnellen Schluss mechanisch
   weggerechnet. Geschätzt als Ridge-Regression auf Rennebene mit Leave-one-out-Vorhersage
   (das Rennen sieht sein eigenes Ergebnis nicht): seltene Bahnen und Bodenklassen werden zum
   Gesamtmittel gezogen. Die Abweichung der Rennreferenz vom Par ist der Renneffekt; er wird
   wie ein zufälliger Effekt geschrumpft, je weniger Pferde die Referenz tragen.

4. Kennzahl je Pferd
   bereinigt = geschrumpfter Renneffekt + Pferdeanteil, positiv = schneller als erwartet.
   L600 und L400 in Längen (LAENGE_M Meter je Länge) über die jeweilige Strecke. Best Seg,
   Δ400 und Peak in km/h (Längen über 200 m wären winzig und täuschen "kein Unterschied" vor),
   der Finish-Index in Indexpunkten. Weit geschlagene Pferde (> AUSGERITTEN_L Längen) werden
   markiert und gehen nicht in Durchschnitte ein.

Profil statt Doppelung: L400 steckt zu 2/3 in L600. Deshalb gibt es zusätzlich
   Δ400  = Tempo letzte 400 m minus Tempo 600–400 m   (beschleunigt das Pferd noch oder bricht es ein)
   Peak  = Best Seg minus L600                          (Spitze gegenüber Ausdauer)
Beide werden wie die anderen Kennzahlen gegen Feld und Par bereinigt.

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

# Rohspalte (m/s bzw. Index) -> (Name der bereinigten Spalte, Einheit: Meter für Längen, "kmh", "pts")
KENNZAHLEN = {"v600": ("v600_adj_l", 600), "v400": ("v400_adj_l", 400), "vbest": ("best_adj", "kmh"),
              "accel": ("accel_adj", "kmh"), "peak": ("peak_adj", "kmh"), "fi": ("fi_adj", "pts")}
PACE_KOVARIATE = "pace_early_kmh"   # frühes Tempo des Führenden; Ersatz: pace_ratio (alte Daten)
PATH_FACTOR_MIN, PATH_FACTOR_MAX = 0.97, 1.10   # plausibler Wegfaktor (gelaufene / nominale Distanz)
LAST600_TOLERANZ_S = 0.5        # berechnete letzte 600 m dürfen so weit von der offiziellen Angabe abweichen
TEMPO_MIN_KMH, TEMPO_MAX_KMH = 40.0, 75.0       # plausibles Tempo eines Abschnitts / der Schlussphase


def _abschnitte(sections: pd.DataFrame) -> pd.DataFrame:
    """tracking_sections mit numerischen Spalten und Beginn des Abschnitts (m vor dem Ziel)."""
    s = sections.copy()
    for c in ["saddle_no", "m_to_go", "seg_len_m", "split_s", "cum_s"]:
        s[c] = pd.to_numeric(s[c], errors="coerce") if c in s else np.nan
    s["start_to_go"] = s["m_to_go"] + s["seg_len_m"]
    s["split_ok"] = (s["split_s"] > 0) & (s["seg_len_m"] > 0)
    return s


def _tempo_bereich(s: pd.DataFrame, von: int, bis: int) -> pd.Series:
    """Tempo (m/s) je Starter über die Abschnitte, die genau den Bereich `von` -> `bis` Meter vor
    dem Ziel abdecken. None, wenn Abschnitte fehlen, überlappen oder ein Split fehlt."""
    teil = s[(s["m_to_go"] >= bis) & (s["start_to_go"] <= von)]
    g = teil.groupby(["race_id", "saddle_no"])
    laenge, zeit, ok = g["seg_len_m"].sum(), g["split_s"].sum(), g["split_ok"].all()
    v = (von - bis) / zeit
    return v.where(ok & (laenge == von - bis))


def rohwerte_aus_abschnitten(h: pd.DataFrame, sections: pd.DataFrame | None) -> pd.DataFrame:
    """Bildet aus tracking_sections je Starter neu (und überschreibt die geparsten Spalten):
    speed_last600_kmh, speed_last400_kmh, speed_600_400_kmh, finish_index, path_factor,
    last600_calc_s, last600_diff_s, last600_mismatch. Erwartet in h: distance_m, optional
    distance_covered_m und last600_s (aus tracking_runners)."""
    h = h.copy()
    for c in ["speed_600_400_kmh", "path_factor", "last600_calc_s", "last600_diff_s"]:
        h[c] = np.nan
    h["last600_mismatch"] = False
    if sections is None or sections.empty or not {"m_to_go", "seg_len_m", "split_s"} <= set(sections):
        return h
    s = _abschnitte(sections)
    key = ["race_id", "saddle_no"]
    g = s.groupby(key)
    roh = pd.DataFrame({"v600": _tempo_bereich(s, 600, 0), "v400": _tempo_bereich(s, 400, 0),
                        "v_mid": _tempo_bereich(s, 600, 400)})
    # Gesamtzeit: Summe aller Splits, ersatzweise die kumulierte Zeit des letzten Abschnitts
    ziel = s[s["m_to_go"] == 0].drop_duplicates(key).set_index(key)["cum_s"]
    t_sum = g["split_s"].sum().where(g["split_ok"].all())
    roh["t_total"] = t_sum.fillna(ziel)
    roh["d_total"] = g["seg_len_m"].sum()
    roh = roh.reset_index()
    h["saddle_no"] = pd.to_numeric(h["saddle_no"], errors="coerce")
    h = h.merge(roh, on=key, how="left")
    hat = h["d_total"].notna()                                  # Starter mit Abschnitten

    # Wegfaktor
    dist = pd.to_numeric(h["distance_m"], errors="coerce")
    gelaufen = pd.to_numeric(h["distance_covered_m"], errors="coerce") if "distance_covered_m" in h else np.nan
    pf = gelaufen / dist
    h["path_factor"] = pf.where(pf.between(PATH_FACTOR_MIN, PATH_FACTOR_MAX)).round(4)
    skal = h["path_factor"].fillna(1.0)

    # Finish-Index: letzte 400 m gegen das Tempo davor (Wegfaktor kürzt sich)
    t_fin = 400 / h["v400"]
    t_early, d_early = h["t_total"] - t_fin, h["d_total"] - 400
    v_early = (d_early / t_early).where((t_early > 0) & (d_early > 0))
    fi_neu = (h["v400"] / v_early * 100).round(1)

    # Gegenprobe letzte 600 m
    h.loc[hat, "last600_calc_s"] = (600 / h["v600"]).round(2)
    if "last600_s" in h:
        off = pd.to_numeric(h["last600_s"], errors="coerce")
        h["last600_diff_s"] = (h["last600_calc_s"] - off).round(2)
        h["last600_mismatch"] = h["last600_diff_s"].abs() > LAST600_TOLERANZ_S

    neu = {"speed_last600_kmh": h["v600"] * 3.6 * skal, "speed_last400_kmh": h["v400"] * 3.6 * skal,
           "speed_600_400_kmh": h["v_mid"] * 3.6 * skal, "finish_index": fi_neu}
    for c, wert in neu.items():
        if c not in h:
            h[c] = np.nan
        wert = wert.round(2).where(~h["last600_mismatch"])
        h[c] = wert.where(hat, pd.to_numeric(h[c], errors="coerce"))   # ohne Abschnitte: geparster Wert
    for c in ["speed_last600_kmh", "speed_last400_kmh", "speed_600_400_kmh"]:
        h[c] = h[c].where(h[c].between(TEMPO_MIN_KMH, TEMPO_MAX_KMH))
    return h.drop(columns=["v600", "v400", "v_mid", "t_total", "d_total"])


def pace_frueh_aus_leader(leader: pd.DataFrame | None, distanz: pd.Series) -> pd.Series:
    """Frühes Tempo des Führenden (km/h) je race_id aus tracking_leader – für Daten, die vor der
    Spalte pace_early_kmh geparst wurden. `distanz`: Series distance_m mit race_id als Index."""
    if leader is None or leader.empty or not {"race_id", "to", "leader_cum_s"} <= set(leader):
        return pd.Series(dtype=float)
    l = leader.copy()
    l["leader_cum_s"] = pd.to_numeric(l["leader_cum_s"], errors="coerce")
    to = l["to"].astype("string")
    l["m_to_go"] = pd.to_numeric(to.str.rstrip("m"), errors="coerce").where(to != "ARR", 0)
    l = l.dropna(subset=["m_to_go", "leader_cum_s"]).sort_values(["race_id", "m_to_go"], ascending=[True, False])
    out = {}
    for rid, grp in l.groupby("race_id"):
        d = distanz.get(rid)
        if not d or grp["m_to_go"].iloc[-1] != 0:
            continue
        total = grp["leader_cum_s"].iloc[-1]
        # letzte Abschnitte, bis mindestens 600 m erreicht sind (wie derive_race)
        marke = min((m for m in grp["m_to_go"] if m >= 600), default=None)
        if marke is None:
            continue
        t_marke = grp.loc[grp["m_to_go"] == marke, "leader_cum_s"].iloc[0]
        early_d, early_t = d - marke, t_marke
        if early_d > 0 and early_t > 0:
            out[rid] = round(early_d / early_t * 3.6, 2)
    return pd.Series(out, dtype=float)


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
    pace = pd.to_numeric(r["_pace"], errors="coerce").astype(float)
    pace = pace - float(pace.mean())                              # zentriert, Ridge skaliert stetige Spalten
    stetig = pd.DataFrame({"d": d, "d2": d ** 2, "gv": gv, "gv_fehlt": wert.isna().astype(float),
                           "pace": pace, "pace2": pace ** 2, "pace_d": pace * d})
    # (kein eigenes PSF-Flag mehr – das ist bereits die Dummy-Spalte boden_PSF)
    dummies = pd.get_dummies(r[["course_key", "going_class"]].astype("string").fillna("?"),
                             prefix=["bahn", "boden"], dtype=float)
    X = pd.concat([pd.Series(1.0, index=r.index, name="const"), stetig, dummies], axis=1)
    strafe = np.r_[0.0, np.zeros(stetig.shape[1]), np.full(dummies.shape[1], RIDGE)]
    return X, strafe, going_mittel


def _ridge(X: pd.DataFrame, y: pd.Series, strafe: np.ndarray, loo: bool = True) -> pd.Series:
    """Ridge-Vorhersage. loo=True: Leave-one-out je Zeile über die Hat-Matrix
    (ŷ_(-i) = (ŷ_i − h_ii·y_i) / (1 − h_ii)) – ein Rennen bestimmt sein Par nicht selbst mit."""
    A = X.to_numpy(float)
    yv = y.to_numpy(float)
    mu = A.mean(0)
    sd = A.std(0)
    sd[sd == 0] = 1
    stetige = strafe == 0
    stetige[0] = False                                        # Konstante nicht skalieren
    Z = A.copy()
    Z[:, stetige] = (A[:, stetige] - mu[stetige]) / sd[stetige]
    G = np.linalg.inv(Z.T @ Z + np.diag(strafe) + 1e-9 * np.eye(len(strafe)))
    beta = G @ Z.T @ yv
    fit = Z @ beta
    if not loo:
        return pd.Series(fit, index=X.index)
    h = np.einsum("ij,jk,ik->i", Z, G, Z)                     # Diagonale der Hat-Matrix
    h = np.clip(h, 0, 0.95)
    return pd.Series((fit - h * yv) / (1 - h), index=X.index)


def rennpar(h: pd.DataFrame, col: str) -> pd.DataFrame:
    """Rennreferenz, Par und geschrumpfter Renneffekt je Rennen für die Kennzahl `col`."""
    ref = _rennreferenz(h, col)
    pace_col = PACE_KOVARIATE if PACE_KOVARIATE in h and h[PACE_KOVARIATE].notna().any() else "pace_ratio"
    rennen = (h.drop_duplicates("race_id").set_index("race_id")
                [["distance_m", "going_value", "going_class", "course_key", pace_col]]
                .rename(columns={pace_col: "_pace"}))
    r = ref.join(rennen, how="inner")
    r = r[r["distance_m"].notna() & r["_pace"].notna()]
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
    v600_adj_l, v400_adj_l (Längen, + = schneller als erwartet), best_adj, accel_adj, peak_adj (km/h),
    fi_adj (Indexpunkte); dazu roh: best_seg_s (Zeit für 200 m im schnellsten Abschnitt der letzten
    800 m), best_seg_to_go_m, accel_kmh (L400 − Tempo 600–400 m), peak_kmh (Best Seg − L600),
    ausgeritten (bool)."""
    h = h.copy()
    h["v600"] = h["speed_last600_kmh"] / 3.6
    h["v400"] = h["speed_last400_kmh"] / 3.6
    h["fi"] = h["finish_index"]
    b = best_seg_final(sections)
    h = h.drop(columns=[c for c in b.columns if c not in ("race_id", "saddle_no") and c in h])
    h = h.merge(b, on=["race_id", "saddle_no"], how="left")
    # Wegfaktor: Abschnittslängen sind nominal, das Pferd außen herum lief tatsächlich schneller
    if "path_factor" in h:
        h["vbest"] = h["vbest"] * pd.to_numeric(h["path_factor"], errors="coerce").fillna(1.0)
    h["best_seg_s"] = 200 / h["vbest"]
    v_mid = pd.to_numeric(h["speed_600_400_kmh"], errors="coerce") / 3.6 if "speed_600_400_kmh" in h else np.nan
    h["accel"] = h["v400"] - v_mid                           # m/s: beschleunigt (+) oder bricht ein (−)
    h["peak"] = h["vbest"] - h["v600"]                        # m/s: Spitze über Ausdauer
    h["accel_kmh"] = (h["accel"] * 3.6).round(2)
    h["peak_kmh"] = (h["peak"] * 3.6).round(2)
    h["ausgeritten"] = h["lengths_behind"] > AUSGERITTEN_L
    for col, (name, einheit) in KENNZAHLEN.items():
        par = rennpar(h, col) if h[col].notna().any() else pd.DataFrame()
        if par.empty:
            h[name] = np.nan
            continue
        ref = h["race_id"].map(par["ref"])
        effekt = h["race_id"].map(par["renneffekt"])
        diff = effekt + (h[col] - ref)                        # m/s bzw. Indexpunkte
        if einheit == "pts":
            h[name] = diff
        elif einheit == "kmh":
            h[name] = diff * 3.6
        else:
            zeit = einheit / ref                              # Sekunden über die Strecke
            h[name] = diff * zeit / LAENGE_M                  # Vorsprung in Längen
    return h.drop(columns=["v600", "v400", "fi", "accel", "peak"])


def _corr(a: pd.Series, b: pd.Series) -> float:
    """Korrelation, NaN bei zu wenigen Paaren oder konstanter Reihe (ohne Warnung)."""
    ok = a.notna() & b.notna()
    if ok.sum() < 3 or a[ok].std() == 0 or b[ok].std() == 0:
        return float("nan")
    return round(float(a[ok].corr(b[ok])), 3)


def validierung(h: pd.DataFrame) -> pd.DataFrame:
    """Wiederholbarkeit (Korrelation zweier aufeinanderfolgender Läufe desselben Pferdes)
    und Prognosekraft (Rangkorrelation mit der Platzierung im nächsten Lauf, als Anteil des
    Feldes; negativ = höherer Wert, bessere nächste Platzierung) – bereinigt gegen roh."""
    paare = {"L600": ("speed_last600_kmh", "v600_adj_l"), "L400": ("speed_last400_kmh", "v400_adj_l"),
             "Best Seg": ("vbest", "best_adj"), "Δ400": ("accel_kmh", "accel_adj"),
             "Peak": ("peak_kmh", "peak_adj"), "Finish-Index": ("finish_index", "fi_adj")}
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
            z[f"Wiederholbarkeit {art}"] = _corr(x, naechst)
            ok2 = x.notna() & d["naechster_pos"].notna()                 # Spearman ohne scipy
            z[f"Prognose {art}"] = _corr(x[ok2].rank(), d.loc[ok2, "naechster_pos"].rank())
        zeilen.append(z)
    return pd.DataFrame(zeilen)
