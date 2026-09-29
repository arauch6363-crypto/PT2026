"""
TR – Zeit-Rating nach Timeform-Art (in lb), mit Upgrade aus dem Finishing Speed (Rowlands).

Phase 1  Standardzeiten und Going Allowance
    Standardzeit je Kurs × Distanz (s/km): Median der Siegerzeiten in Rennen guter Klasse, vorher auf eine
    Referenzklasse umgerechnet. β der Klasse (Altersklasse, log. Preisgeld, wie in tempo_delta) wird auf den
    Siegerzeiten geschätzt, innerhalb der Gruppen Tag × Kurs × Going.
    Going Allowance je Gruppe Tag × Kurs × Going (s/km): zuerst aus den Siegerzeiten minus Standard (Klasse
    herausgerechnet), dann nach Timeform: tatsächliche Zeiten minus die Zeiten, die die Ratings der Pferde
    (aus ihren anderen Rennen) erwarten lassen. GA_ITER Runden.

Phase 2  Zeit-Rating je Pferd
    Eigene Zeit = Siegerzeit + behind_winner_s. Abzüglich Going Allowance × Distanz, verglichen mit der
    Standardzeit. Korrekturen: Gewicht gegen REF_WEIGHT_KG (kg -> lb), Wegverlust (Mehrmeter aus dem
    Wegfaktor, in Zeit umgerechnet). Sekunden -> Längen (auf den eigenen Daten kalibriert: Längen hinter dem
    Sieger je Sekunde hinter dem Sieger, je Distanzgruppe) -> lb (lb je Länge nach Distanz).
    Ausgerittene Pferde (> AUSGERITTEN Längen) bekommen kein Rating.
    TR_Zeit = TR_BASIS − Rückstand zur Standardzeit in lb + (Gewicht − REF_WEIGHT_KG) in lb.

Phase 3  Finishing Speed %
    Abschnitt: 400 m bis 1600 m, darüber 600 m. FS% = (T·d·100)/(D·t) mit Gesamtzeit T über D und
    Abschnittszeit t über d – je Pferd aus den eigenen Zeiten, je Rennen aus den Zeiten des Führenden
    (Pace-Einordnung; Par = Median je Kurs × Distanz).

Phase 4  Optimaler FS% und Upgrade
    Optimum je Kurs × Distanz: Median-FS% der "effizienten" Läufe (Zeit-Rating höchstens EFFIZIENT_LB unter
    der scheinbaren Fähigkeit = bestes Zeit-Rating aus den anderen Läufen), zum Par der Distanzgruppe
    geschrumpft, dazu eine Verschiebung je Bodenklasse.
    Upgrade = c · (d/D) · f(O − A), Start c = 1,25 (Rowlands). f ist bis UPGRADE_KNIE FS-Punkte das Quadrat,
    darüber linear (daempfung) – das reine Quadrat explodiert in sehr langsam gelaufenen Rennen. c wird
    kalibriert: Rückstand zur scheinbaren Fähigkeit gegen (d/D)·f(O − A), getrennt für zu schnell (A < O) und
    zu langsam angegangen (A > O). Höchstens UPGRADE_MAX_LB; gedeckelte Läufe werden markiert (tr_gedeckelt).
    TR = TR_Zeit + Upgrade.

Phase 5  validierung(): sagt TR den nächsten Lauf besser voraus als das Zeit-Rating allein, ΔL600/ΔB200 und
    ARR? Korrelation mit dem nächsten Ergebnis und Trefferquote des Bestbewerteten unter den ersten drei.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import rtr_arr
import tempo_delta

REF_WEIGHT_KG = 55.0
LB_PER_KG = 2.2046
TR_BASIS = 100.0             # Rating einer Siegerzeit der Referenzklasse auf Standardboden mit REF_WEIGHT_KG
GUTE_KLASSE_Q = 0.5          # "gute Klasse": obere Hälfte nach Klassen-Näherung
MIN_STD_RENNEN = 5           # so viele Siegerzeiten braucht eine Standardzeit
GA_SHRINK = 1.0              # Bootstrap-Allowance: n / (n + GA_SHRINK) · Median
GA_ITER = 3                  # Runden der Timeform-Allowance
GA_BLEND = 3.0               # Timeform-Allowance aus n Pferden, zur Bootstrap-Allowance gezogen wie n / (n + GA_BLEND)
GA_MIN_ANDERE = 2            # so viele andere Läufe braucht ein Pferd, damit sein Rating in die Allowance eingeht
AUSGERITTEN_L = 10.0         # wie speedfig.AUSGERITTEN_L
SPEED_KMH = (40.0, 75.0)     # plausibles Durchschnittstempo
FS_BEREICH = (80.0, 130.0)   # plausibler FS%
EFFIZIENT_LB = 5.0
OPT_SHRINK = 10.0            # Optimum je Kurs × Distanz: n / (n + OPT_SHRINK) zum Par der Distanzgruppe
GOING_SHRINK = 20.0
C_START = 1.25               # Rowlands
UPGRADE_KNIE = 3.0           # FS-Punkte: bis hier quadratisch (Rowlands), darüber nur noch linear (Huber-Form)
UPGRADE_MAX_LB = 12.0        # Deckel: mehr Upgrade gibt es nicht – solche Rennen sind falsch gelaufen, TR unsicher
MIN_C_LAEUFE = 200           # je Seite so viele Läufe, damit getrennte Koeffizienten gelten

# lb je Länge nach Distanz (bis m): mehr im Sprint, weniger auf langen Distanzen
LB_PER_LENGTH = [(1100, 3.0), (1300, 2.5), (1500, 2.25), (1700, 2.0), (1900, 1.75), (2100, 1.5),
                 (2500, 1.25), (99999, 1.0)]
LAENGEN_JE_S_VORGABE = 5.0   # Ersatz, wenn die Kalibrierung zu wenige Daten hat

SPALTEN = ["tr", "tr_zeit", "tr_upgrade", "tr_ga", "fs_pct", "fs_opt", "fs_race", "fs_par", "tr_gedeckelt"]
LETZTE_INFO: dict = {}


def daempfung(abw, knie: float = UPGRADE_KNIE):
    """(O − A)² bis |O − A| = knie, darüber linear weiter (stetig und mit gleicher Steigung am Knie):
    2·knie·|O − A| − knie². Ein sehr langsam gelaufenes Rennen (FS% weit über dem Optimum) bekommt so
    kein explodierendes Upgrade."""
    a = np.abs(np.asarray(abw, dtype=float))
    return np.where(a <= knie, a ** 2, 2 * knie * a - knie ** 2)


def lb_je_laenge(dist) -> float:
    d = float(dist)
    return next(lb for bis, lb in LB_PER_LENGTH if d <= bis)


def abschnitt_m(dist) -> int:
    """Abschnitt für den FS%: 400 m bis 1600 m, darüber 600 m."""
    return 400 if float(dist) <= 1600 else 600


def _fs(T, D, t, d):
    with np.errstate(divide="ignore", invalid="ignore"):
        v = T * d * 100.0 / (D * t)
    return np.where((v >= FS_BEREICH[0]) & (v <= FS_BEREICH[1]), v, np.nan)


def abschnittszeiten(sections: pd.DataFrame | None, dist: pd.Series) -> pd.DataFrame:
    """Zeit der letzten d Meter (d = abschnitt_m) je Pferd aus den 200-m-Abschnitten: race_id, saddle_no, fs_t, fs_d."""
    leer = pd.DataFrame(columns=["race_id", "saddle_no", "fs_t", "fs_d"])
    if sections is None or sections.empty:
        return leer
    s = sections.copy()
    for c in ["saddle_no", "m_to_go", "seg_len_m", "split_s"]:
        s[c] = pd.to_numeric(s[c], errors="coerce") if c in s else np.nan
    s["D"] = s["race_id"].map(dist)
    s = s[s["D"].notna()]
    s["fs_d"] = s["D"].map(abschnitt_m)
    # m_to_go = Ende des Abschnitts; es zählen Abschnitte, die ganz in den letzten fs_d Metern liegen
    s = s[(s["m_to_go"] + s["seg_len_m"] <= s["fs_d"]) & (s["m_to_go"] >= 0)]
    g = s.groupby(["race_id", "saddle_no"]).agg(fs_t=("split_s", lambda x: x.sum(min_count=len(x))),
                                                laenge=("seg_len_m", "sum"), fs_d=("fs_d", "first")).reset_index()
    g = g[(g["laenge"] == g["fs_d"]) & g["fs_t"].notna() & (g["fs_t"] > 0)]
    return g[["race_id", "saddle_no", "fs_t", "fs_d"]]


def race_fs(leader: pd.DataFrame | None, dist: pd.Series) -> pd.Series:
    """FS% des Rennens aus den Zeiten des Führenden (race_id -> FS%)."""
    if leader is None or leader.empty:
        return pd.Series(dtype=float)
    l = leader.copy()
    l["leader_cum_s"] = pd.to_numeric(l["leader_cum_s"], errors="coerce")
    l["to"] = l["to"].astype(str).str.strip().str.upper()
    out = {}
    for rid, g in l.groupby("race_id"):
        D = dist.get(rid)
        if D is None or pd.isna(D):
            continue
        d = abschnitt_m(D)
        T = g.loc[g["to"] == "ARR", "leader_cum_s"].max()
        cum_d = g.loc[g["to"] == f"{d}M", "leader_cum_s"]
        if pd.isna(T) or cum_d.empty or pd.isna(cum_d.iloc[0]):
            continue
        out[rid] = float(_fs(T, D, T - cum_d.iloc[0], d))
    return pd.Series(out, dtype=float)


def _laengen_je_sekunde(r: pd.DataFrame) -> dict:
    """Längen hinter dem Sieger je Sekunde hinter dem Sieger, je Distanzgruppe (Median der Verhältnisse)."""
    ok = (r["behind_winner_s"].between(0.3, 6.0) & r["lengths_behind"].between(0.5, AUSGERITTEN_L))
    q = (r.loc[ok, "lengths_behind"] / r.loc[ok, "behind_winner_s"]).groupby(r.loc[ok, "band"], observed=True)
    alle = (r.loc[ok, "lengths_behind"] / r.loc[ok, "behind_winner_s"]).median() if ok.sum() >= 30 else np.nan
    werte = {b: float(v.median()) for b, v in q if len(v) >= 30}
    fallback = float(alle) if pd.notna(alle) else LAENGEN_JE_S_VORGABE
    return {b: werte.get(b, fallback) for b in tempo_delta.BAND_LABELS}


def _loo_mittel(werte: pd.Series, pferd: pd.Series, gruppe: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Mittel der Werte eines Pferdes ohne seine Läufe in derselben Gruppe, dazu die Anzahl."""
    ok = werte.notna()
    w = werte.where(ok, 0.0)
    s_h = w.groupby(pferd).transform("sum")
    n_h = ok.groupby(pferd).transform("sum")
    s_hg = w.groupby([pferd, gruppe]).transform("sum")
    n_hg = ok.groupby([pferd, gruppe]).transform("sum")
    n = n_h - n_hg
    return ((s_h - s_hg) / n.where(n > 0)), n


def _bestes_anderes(werte: pd.Series, pferd: pd.Series) -> pd.Series:
    """Bestes Rating eines Pferdes aus seinen anderen Läufen (ohne diesen)."""
    df = pd.DataFrame({"w": werte, "p": pferd})
    rang = df.groupby("p")["w"].rank(method="first", ascending=False)
    erst = df["w"].where(rang == 1).groupby(df["p"]).transform("max")
    zweit = df["w"].where(rang == 2).groupby(df["p"]).transform("max")
    return pd.Series(np.where(rang == 1, zweit, erst), index=werte.index)


def berechnen(h: pd.DataFrame, sections: pd.DataFrame | None = None,
              leader: pd.DataFrame | None = None, standards: pd.DataFrame | None = None) -> pd.DataFrame:
    """TR je Lauf (Spalten SPALTEN). Erwartet je Starter: race_id, saddle_no, horse_id, date, course_key,
    going_pmu, distance_m, prize_eur, conditions_age, finish_pos, lengths_behind, weight_kg,
    official_time_s, behind_winner_s, path_factor (optional)."""
    global LETZTE_INFO
    h = h.copy()
    for c in SPALTEN:
        h[c] = np.nan
    LETZTE_INFO = {"laeufe": 0}
    need = {"official_time_s", "behind_winner_s", "distance_m", "course_key", "date"}
    if h.empty or not need <= set(h.columns):
        return h
    for c in ["official_time_s", "behind_winner_s", "finish_pos", "lengths_behind", "weight_kg", "distance_m"]:
        h[c] = pd.to_numeric(h[c], errors="coerce")
    if "path_factor" not in h:
        h["path_factor"] = np.nan
    if "going_pmu" not in h:
        h["going_pmu"] = None

    # eigene Zeit: Siegerzeit + behind_winner_s (ersatzweise die eigene offizielle Zeit)
    sieger = h[h["finish_pos"] == 1].groupby("race_id")["official_time_s"].min()
    sieger = sieger.combine_first(h.groupby("race_id")["official_time_s"].min())
    T = h["race_id"].map(sieger) + h["behind_winner_s"]
    h["_T"] = T.fillna(h["official_time_s"])
    v = h["distance_m"] / h["_T"] * 3.6
    h.loc[~v.between(*SPEED_KMH), "_T"] = np.nan

    rc = h.drop_duplicates("race_id")[["race_id", "date", "course_key", "going_pmu", "distance_m",
                                       "prize_eur", "conditions_age"]].copy()
    rc = rc[rc["distance_m"].notna() & rc["course_key"].notna() & rc["date"].notna()]
    rc["T_sieger"] = rc["race_id"].map(sieger)
    rc = rc[(rc["distance_m"] / rc["T_sieger"] * 3.6).between(*SPEED_KMH)]
    if len(rc) < MIN_STD_RENNEN:
        return h
    rc = tempo_delta.klasse(tempo_delta.gruppen(rc))
    rc["skm"] = rc["T_sieger"] / (rc["distance_m"] / 1000)

    # Phase 1a: β der Klasse (s/km) auf den Siegerzeiten, innerhalb Tag × Kurs × Going
    class_cols, ref_age = tempo_delta.klassen_spalten(rc)
    rc = rc.set_index("race_id", drop=False)
    _, _, beta = tempo_delta._fit_fe_ab(rc, "skm", class_cols, class_cols)
    beta = beta.fillna(0.0)
    rc["kl"] = rc[class_cols].to_numpy(float) @ beta.to_numpy(float)            # s/km, negativ = bessere Klasse
    gut = rc["kl"] <= rc["kl"].quantile(GUTE_KLASSE_Q)
    kl_ref = float(rc.loc[gut, "kl"].median())
    rc["skm_ref"] = rc["skm"] - (rc["kl"] - kl_ref)                             # Siegerzeit auf Referenzklasse

    # Phase 1b: Standardzeit je Kurs × Distanz
    std_gut = rc[gut].groupby("cell")["skm_ref"].agg(["median", "count"])
    std_alle = rc.groupby("cell")["skm_ref"].agg(["median", "count"])
    std = std_gut["median"].where(std_gut["count"] >= MIN_STD_RENNEN)
    std = std.reindex(std_alle.index).combine_first(std_alle["median"].where(std_alle["count"] >= MIN_STD_RENNEN))
    rc["std"] = rc["cell"].map(std)
    # Standardzeiten aus standardzeiten.py (Konfiguration des Tages, lange Historie) haben Vorrang;
    # die eigene Schätzung aus den Tracking-Rennen bleibt als Ersatz
    rc["std_quelle"] = np.where(rc["std"].notna(), "tracking", None)
    ext = None
    if standards is not None and len(standards):
        ext = standards.drop_duplicates("race_id").set_index("race_id")
        s_ext = rc.index.to_series().map(ext["std_skm"])
        rc.loc[s_ext.notna(), "std_quelle"] = "konfiguration"
        rc["std"] = s_ext.combine_first(rc["std"])
    rc = rc[rc["std"].notna()]
    if rc.empty:
        return h

    # Phase 1c: Bootstrap-Allowance je Gruppe – aus standardzeiten.py (alle Rennen des Renntags), sonst aus den
    # eigenen Siegerzeiten (Klasse herausgerechnet)
    ga0 = (rc["skm_ref"] - rc["std"]).groupby(rc["meeting"]).agg(["median", "count"])
    ga_boot = ga0["median"] * ga0["count"] / (ga0["count"] + GA_SHRINK)
    n_ga_ext = 0
    if ext is not None and "ga_skm" in ext:
        ga_e = rc.index.to_series().map(ext["ga_skm"]).groupby(rc["meeting"]).median().dropna()
        n_ga_ext = int(len(ga_e))
        ga_boot = ga_e.combine_first(ga_boot)

    # Läufe mit allen Angaben
    d = h[h["race_id"].isin(rc.index) & h["_T"].notna()].copy()
    for c in ["meeting", "cell", "band", "std"]:
        d[c] = d["race_id"].map(rc[c])
    d["pferd"] = d["horse_id"] if "horse_id" in d else d["horse"]
    D, Tt = d["distance_m"], d["_T"]
    km = D / 1000
    d["skm"] = Tt / km
    lps = _laengen_je_sekunde(d)
    d["lb_s"] = [lb_je_laenge(x) * lps.get(b, LAENGEN_JE_S_VORGABE) for x, b in zip(D, d["band"])]
    pf = pd.to_numeric(d["path_factor"], errors="coerce").clip(1.0, 1.10).fillna(1.0)
    d["gutschrift_s"] = (pf - 1.0) * D / (D / Tt)                             # Mehrmeter in Zeit (eigenes Tempo)
    d["gew_lb"] = (d["weight_kg"] - REF_WEIGHT_KG).fillna(0.0) * LB_PER_KG
    eased = d["lengths_behind"] > AUSGERITTEN_L
    if "ausgeritten" in d:
        eased |= d["ausgeritten"].fillna(False).astype(bool)
    d["eased"] = eased

    def zeit_rating(ga: pd.Series) -> pd.Series:
        rueck_s = (d["skm"] - d["meeting"].map(ga).fillna(0.0) - d["std"]) * km - d["gutschrift_s"]
        tr = TR_BASIS - rueck_s * d["lb_s"] + d["gew_lb"]
        return tr.where(~d["eased"])

    # Phase 2 + Timeform-Allowance: tatsächliche Zeit minus die Zeit, die die Ratings erwarten lassen
    ga = ga_boot.copy()
    tr = zeit_rating(ga)
    verlauf = []
    for _ in range(GA_ITER):
        faehig, n_andere = _loo_mittel(tr, d["pferd"], d["meeting"])
        ok = n_andere >= GA_MIN_ANDERE
        erwartet_s = (TR_BASIS - faehig + d["gew_lb"]) / d["lb_s"]            # erwarteter Rückstand (s)
        roh_s = (d["skm"] - d["std"]) * km - d["gutschrift_s"]
        ga_lauf = ((roh_s - erwartet_s) / km).where(ok & ~d["eased"])
        g = ga_lauf.groupby(d["meeting"]).agg(["median", "count"])
        n = g["count"]
        ga_neu = ((n * g["median"].fillna(0) + GA_BLEND * ga_boot.reindex(g.index).fillna(0)) / (n + GA_BLEND))
        ga_neu = ga_neu.combine_first(ga_boot)
        verlauf.append(float((ga_neu - ga.reindex(ga_neu.index)).abs().mean()))
        ga = ga_neu
        tr = zeit_rating(ga)
    d["tr_zeit"] = tr
    d["tr_ga"] = d["meeting"].map(ga)                                           # Going Allowance (s/km)

    # Phase 3: FS% je Pferd und je Rennen
    dist_r = rc["distance_m"]
    ab = abschnittszeiten(sections, dist_r)
    if len(ab):
        ab["saddle_no"] = pd.to_numeric(ab["saddle_no"], errors="coerce")
        d = d.reset_index().merge(ab, on=["race_id", "saddle_no"], how="left").set_index("index")
    else:
        d["fs_t"], d["fs_d"] = np.nan, np.nan
    d["fs_pct"] = _fs(d["_T"].to_numpy(float), D.reindex(d.index).to_numpy(float),
                      d["fs_t"].to_numpy(float), d["fs_d"].to_numpy(float))
    rfs = race_fs(leader, dist_r)
    rc["fs_race"] = rc.index.map(rfs)
    par_c = rc.groupby("cell")["fs_race"].agg(["median", "count"])
    par_b = rc.groupby("band", observed=True)["fs_race"].median()
    rc["fs_par"] = [(par_c.at[c, "count"] * (par_c.at[c, "median"] if pd.notna(par_c.at[c, "median"]) else 0)
                     + OPT_SHRINK * par_b.get(b, np.nan)) / (par_c.at[c, "count"] + OPT_SHRINK)
                    for c, b in zip(rc["cell"], rc["band"])]
    d["fs_race"] = d["race_id"].map(rc["fs_race"])
    d["fs_par"] = d["race_id"].map(rc["fs_par"])

    # Phase 4: Optimum aus den effizienten Läufen, Going-Verschiebung, Upgrade
    d["faehig"] = _bestes_anderes(d["tr_zeit"], d["pferd"])
    eff = d["tr_zeit"].notna() & d["faehig"].notna() & (d["tr_zeit"] >= d["faehig"] - EFFIZIENT_LB) & d["fs_pct"].notna()
    oc = d[eff].groupby("cell")["fs_pct"].agg(["median", "count"])
    ob = d[eff].groupby("band", observed=True)["fs_pct"].median()
    ob_alle = d.loc[eff, "fs_pct"].median()
    band_par = d["band"].map(ob).astype(float).fillna(ob_alle)
    n_c = d["cell"].map(oc["count"]).fillna(0)
    d["fs_opt"] = (n_c * d["cell"].map(oc["median"]).fillna(0) + OPT_SHRINK * band_par) / (n_c + OPT_SHRINK)
    d["bodenklasse"] = d["going_pmu"].map(rtr_arr.boden_gruppe)
    abw = (d.loc[eff, "fs_pct"] - d.loc[eff, "fs_opt"]).groupby(d.loc[eff, "bodenklasse"]).agg(["median", "count"])
    shift = abw["median"] * abw["count"] / (abw["count"] + GOING_SHRINK)
    d["fs_opt"] = d["fs_opt"] + d["bodenklasse"].map(shift).fillna(0.0)

    z = (d["fs_d"] / D) * pd.Series(daempfung(d["fs_opt"] - d["fs_pct"]), index=d.index)
    zu_schnell = d["fs_pct"] < d["fs_opt"]                  # FS unter dem Optimum: vorne zu schnell angegangen
    fit = d["tr_zeit"].notna() & d["faehig"].notna() & z.notna()
    rueck = (d["faehig"] - d["tr_zeit"])[fit]

    def steigung(maske) -> tuple[float, int]:
        m = maske[fit]
        if m.sum() < 30:
            return np.nan, int(m.sum())
        X = np.c_[np.ones(m.sum()), z[fit][m]]
        b, *_ = np.linalg.lstsq(X, rueck[m], rcond=None)
        return float(b[1]), int(m.sum())

    c_sym, n_sym = steigung(pd.Series(True, index=d.index))
    c_schnell, n_schnell = steigung(zu_schnell)
    c_langsam, n_langsam = steigung(~zu_schnell)
    c_sym = c_sym if pd.notna(c_sym) and c_sym > 0 else C_START
    getrennt = (n_schnell >= MIN_C_LAEUFE and n_langsam >= MIN_C_LAEUFE
                and pd.notna(c_schnell) and pd.notna(c_langsam) and c_schnell > 0 and c_langsam > 0)
    c = np.where(zu_schnell, c_schnell, c_langsam) if getrennt else c_sym
    roh_upg = (c * z).where(d["tr_zeit"].notna())
    d["tr_gedeckelt"] = (roh_upg > UPGRADE_MAX_LB).astype(float).where(roh_upg.notna())   # 1 = gedeckelt
    d["tr_upgrade"] = roh_upg.clip(upper=UPGRADE_MAX_LB)
    d["tr"] = d["tr_zeit"] + d["tr_upgrade"].fillna(0.0)

    for col in SPALTEN:
        h.loc[d.index, col] = d[col]
    LETZTE_INFO = {
        "laeufe": int(d["tr_zeit"].notna().sum()), "rennen": int(len(rc)), "standards": int(std.notna().sum()),
        "std_konfig": int((rc["std_quelle"] == "konfiguration").sum()), "ga_extern": n_ga_ext,
        "gruppen": int(len(ga)), "ga_verlauf": verlauf, "laengen_je_s": lps,
        "beta_preis_x2": float(beta.get("log_prize_c", np.nan) * np.log(2)), "ref_age": ref_age,
        "c_start": C_START, "c_sym": float(c_sym), "c_schnell": c_schnell, "c_langsam": c_langsam,
        "n_schnell": n_schnell, "n_langsam": n_langsam, "getrennt": bool(getrennt),
        "fs_laeufe": int(d["fs_pct"].notna().sum()), "effizient": int(eff.sum()),
        "upg_p90": float(d["tr_upgrade"].quantile(0.9)) if d["tr_upgrade"].notna().any() else None,
        "upg_roh_max": float(roh_upg.max()) if roh_upg.notna().any() else None,
        "gedeckelt": int((d["tr_gedeckelt"] == 1).sum()),
    }
    return h.drop(columns=["_T"])


def bericht(info: dict | None = None) -> str:
    info = info or LETZTE_INFO
    if not info or not info.get("laeufe"):
        return "TR: zu wenige Läufe mit Zeiten – keine Zeit-Ratings."
    ga = " -> ".join(f"{x:.3f}" for x in info["ga_verlauf"])
    lps = ", ".join(f"{b.split()[0]} {v:.1f}" for b, v in info["laengen_je_s"].items())
    verwendet = "getrennt verwendet" if info["getrennt"] else f"gemeinsam {info['c_sym']:.2f} verwendet"
    c = (f"zu schnell {info['c_schnell']:.2f} (n={info['n_schnell']}), zu langsam {info['c_langsam']:.2f} "
         f"(n={info['n_langsam']}) – {verwendet}")
    return "\n".join([
        f"TR aus {info['laeufe']:,} Läufen, {info['rennen']:,} Rennen, {info['standards']} Standardzeiten, "
        f"{info['gruppen']:,} Going Allowances (Tag × Kurs × Going)",
        f"  Standardzeiten: {info.get('std_konfig', 0):,} von {info['rennen']:,} Rennen aus der Konfiguration des Tages "
        f"(standardzeiten.py), Rest aus den Tracking-Rennen geschätzt · Start-Allowance aus der Sammlung für "
        f"{info.get('ga_extern', 0):,} Renntage",
        f"  Klasse in der Standardzeit: Preisgeld ×2 {info['beta_preis_x2']:+.3f} s/km · Längen je Sekunde: {lps}",
        f"  Going Allowance nach Timeform, Änderung je Runde (Ø s/km): {ga}",
        f"  FS%: {info['fs_laeufe']:,} Läufe, {info['effizient']:,} effizient · Upgrade-Koeffizient "
        f"(Start {info['c_start']}, gedämpft ab {UPGRADE_KNIE:g} FS-Punkten): {c}",
        f"  Upgrade: 90 % unter {info['upg_p90']:.1f} lb · Deckel {UPGRADE_MAX_LB:g} lb bei {info['gedeckelt']:,} Läufen "
        f"(ungedeckelt bis {info['upg_roh_max']:.1f} lb)" if info.get("upg_p90") is not None else "  Upgrade: –",
    ])


def validierung(h: pd.DataFrame) -> pd.DataFrame:
    """Vorhersage des nächsten Laufs: Korrelation jeder Kennzahl mit dem nächsten Ergebnis (Platzanteil,
    1 = Sieger) und Trefferquote: der nach seinem letzten Lauf Bestbewertete eines Rennens unter den ersten drei."""
    kennz = {"TR": "tr", "TR Zeit": "tr_zeit", "ΔL600 A": "d_L600_A", "ΔB200 A": "d_B200_A", "ARR": "arr"}
    kennz = {k: v for k, v in kennz.items() if v in h}
    if h.empty or not kennz:
        return pd.DataFrame()
    x = h.sort_values(["date", "race_id"]).copy()
    x["pferd"] = x["horse_id"] if "horse_id" in x else x["horse"]
    x["finish_pos"] = pd.to_numeric(x["finish_pos"], errors="coerce")
    x["pos_anteil"] = 1 - (x["finish_pos"] - 1) / (x["n_runners"] - 1).where(x["n_runners"] > 1)
    x["top3"] = (x["finish_pos"] <= 3).astype(float).where(x["finish_pos"].notna())
    zeilen = []
    for name, col in kennz.items():
        vorher = x.groupby("pferd")[col].shift()                   # Wert aus dem vorigen Lauf
        naechst = x.groupby("pferd")["pos_anteil"].shift(-1)
        ok = x[col].notna() & naechst.notna()
        r = x.loc[ok, col].corr(naechst[ok]) if ok.sum() > 30 else np.nan
        t = pd.DataFrame({"race_id": x["race_id"], "v": vorher, "top3": x["top3"]}).dropna()
        n_feld = t.groupby("race_id")["v"].transform("count")
        t = t[n_feld >= 3]
        beste = t.loc[t.groupby("race_id")["v"].idxmax()] if len(t) else t
        zeilen.append({"Kennzahl": name, "Läufe": int(ok.sum()), "r nächster Lauf": round(r, 3) if pd.notna(r) else None,
                       "Rennen": int(len(beste)),
                       "Top-3-Quote Bestbewerteter": round(float(beste["top3"].mean()), 3) if len(beste) else None})
    return pd.DataFrame(zeilen)
