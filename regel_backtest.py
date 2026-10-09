"""Regeln des Skills „rennkarten-durchgang“ gegen die Datenbank prüfen: Gewinnt eine Gruppe öfter, als der Markt erwartet?

Maßstab ist die Endquote (odds_final): erwartete Siege = Σ Marktchance (1/Quote, je Rennen auf 100 % normiert),
erwartete Plätze = exp_place (Harville aus derselben Quote). A/E über 1 heißt: Die Gruppe läuft besser, als ihre
Quote sagt – das Argument ist nicht (ganz) eingepreist. z = (Siege − erwartet) / √Σ p(1−p); ab |z| ≈ 2 belastbar.
ROI = Ø Gewinn je 1 € Siegwette zur Endquote (vor Abzügen, nur zur Orientierung).

Nur Merkmale, die vor dem Rennen bekannt sind (Vorlauf je Pferd per shift). Startbox, Bias und Linienqualität
werden auf den Daten vor TEILUNG gelernt und nur danach geprüft, damit sich die Regel nicht selbst bestätigt.

Colab:
    import regel_backtest as rb
    erg = rb.run(BASE)                 # lädt die Historie wie die Race Card, druckt die Tabelle, speichert CSV
    erg = rb.run(BASE, hist=hist)      # mit schon geladener Historie (racecard.vorbereiten)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import racecard as rc

TEILUNG = 0.5            # Anteil der Tage (zeitlich vorne) zum Lernen von Box, Bias und Linienqualität
MIN_N = 50               # kleinere Gruppen werden markiert („dünn“)


# --------------------------------------------------------------------------
# Laden und Merkmale
# --------------------------------------------------------------------------
def laden(base: Path) -> pd.DataFrame:
    import pipeline as tp
    import standardzeiten
    return rc.vorbereiten(tp.lade("pmu_races", base), tp.lade("pmu_runners", base),
                          tp.lade("tracking_races", base), tp.lade("tracking_runners", base),
                          tp.lade("tracking_sections", base), tp.lade("tracking_leader", base),
                          standards=standardzeiten.je_rennen(base))


def _rang(h: pd.DataFrame, spalte: str) -> pd.Series:
    """Rang im Feld (1 = höchster Wert), nur unter Startern mit Wert."""
    return h.groupby("race_id")[spalte].rank(ascending=False, method="min")


def merkmale(h: pd.DataFrame) -> pd.DataFrame:
    h = h[h["finish_pos"].notna() | h["won"].notna()].copy()
    h = h.sort_values(["date", "race_id", "saddle_no"]).reset_index(drop=True)
    # Markt
    q = (1 / h["odds_final"]).where(h["odds_final"] > 1)
    voll = q.notna().groupby(h["race_id"]).transform("all")
    h["p_mkt"] = (q / q.groupby(h["race_id"]).transform("sum")).where(voll)
    h["fav"] = h["odds_rank"] == 1
    # Vorlauf je Pferd
    g = h.groupby("horse_id", sort=False)
    h["n_vor"] = g.cumcount()
    h["starts_pmu"] = pd.to_numeric(h["starts"], errors="coerce") if "starts" in h else np.nan
    h["starts_x"] = h["starts_pmu"].fillna(h["n_vor"])
    h["tage"] = (h["date"] - g["date"].shift()).dt.days
    h["dchg"] = h["distance_m"] - g["distance_m"].shift()
    h["psf"] = h["going_pmu"].eq("PSF")
    h["belagwechsel"] = g["psf"].shift().notna() & (h["psf"] != g["psf"].shift())
    psf_vor = g["psf"].shift()
    h["gras_psf"] = psf_vor.eq(False) & h["psf"]
    h["psf_gras"] = psf_vor.eq(True) & ~h["psf"]
    h["psf_laeufe_vor"] = h["psf"].astype(int).groupby(h["horse_id"]).cumsum() - h["psf"].astype(int)
    # Eigene Belagbilanz vor dem Rennen: Ø relative Platzierung auf dem heutigen und dem anderen Belag
    rp = h["rel_place"].fillna(0.5)
    for name, m in [("psf", h["psf"]), ("gras", ~h["psf"])]:
        n = m.astype(int).groupby(h["horse_id"]).cumsum() - m.astype(int)
        s = (rp * m).groupby(h["horse_id"]).cumsum() - rp * m
        h[f"n_{name}"], h[f"rp_{name}"] = n, (s / n).where(n > 0)
    heute_rp = np.where(h["psf"], h["rp_psf"], h["rp_gras"])
    ander_rp = np.where(h["psf"], h["rp_gras"], h["rp_psf"])
    genug = (np.where(h["psf"], h["n_psf"], h["n_gras"]) >= 2) & (np.where(h["psf"], h["n_gras"], h["n_psf"]) >= 2)
    diff = pd.Series(heute_rp - ander_rp, index=h.index).where(genug)
    h["pferd_belag"] = np.select([diff >= 0.1, diff <= -0.1, diff.notna()], ["besser", "schlechter", "gleich"], "unbekannt")
    if "trainer_key" in h:
        tv = g["trainer_key"].shift()
        h["trainerwechsel"] = tv.notna() & h["trainer_key"].notna() & (tv != h["trainer_key"])
    else:
        h["trainerwechsel"] = False
    if "blinkers" in h:
        mit = h["blinkers"].map(rc.scheuklappen_gruppe).isin(["klassisch", "australisch"])
        vorher = g["blinkers"].shift().map(rc.scheuklappen_gruppe)
        h["scheuklappen_neu"] = mit & vorher.eq("ohne")
    else:
        h["scheuklappen_neu"] = False
    sx = h["sex"].astype("string").str.upper().str[:1] if "sex" in h else pd.Series(pd.NA, index=h.index)
    h["wallach"] = sx.eq("H")
    # Laufstil vor dem Rennen: Ø frühe Position der letzten STIL_LAEUFE getrackten Läufe, mindestens 3
    ep = g["early_pct"].shift()
    h["stil_vor"] = ep.groupby(h["horse_id"]).transform(lambda x: x.rolling(rc.STIL_LAEUFE, min_periods=1).mean())
    h["stil_n"] = ep.notna().groupby(h["horse_id"]).cumsum()
    h.loc[h["stil_n"] < 3, "stil_vor"] = np.nan
    h["stil"] = h["stil_vor"].map(lambda v: rc.stil(v)[0] if pd.notna(v) else None)
    h["n_front"] = (h["stil_vor"] <= rc.TEMPOMACHER).groupby(h["race_id"]).transform("sum")
    h["stil_bekannt"] = h["stil_vor"].notna().groupby(h["race_id"]).transform("sum")
    # letzter Lauf
    for c in ["pace_ratio", "early_pct", "weg_med", "pos_gain_800_finish", "d_L600_A", "finish_pos", "won",
              "cls_epr_kl", "tr", "arr", "rtr"]:
        h[c + "_vor"] = g[c].shift() if c in h else np.nan
    for c in ["tr", "arr", "rtr"]:
        h[c + "_rang"] = _rang(h, c + "_vor")
    return h


rennverlauf = rc.rennverlauf          # Rennverlauf je Rennen und Starter (racecard)


def lernen_testen(h: pd.DataFrame) -> pd.DataFrame:
    """Box, Bias und Linienqualität auf dem frühen Teil lernen, auf dem späten anwenden (Spalte test)."""
    tage = np.sort(h["date"].dropna().unique())
    grenze = tage[int(len(tage) * TEILUNG)]
    lern, h["test"] = h[h["date"] < grenze], h["date"] >= grenze
    # Rennverlauf je Rennen und Starter, dazu der Stand des letzten Laufs
    h = rennverlauf(h.sort_values(["date", "race_id", "saddle_no"]).reset_index(drop=True), lern)
    g = h.groupby("horse_id", sort=False)
    for c in ["verlauf_pferd", "verlauf_kl", "rel_place"]:
        h[c + "_vor"] = g[c].shift()
    h["lengths_behind_vor"] = g["lengths_behind"].shift() if "lengths_behind" in h else np.nan
    # Startbox
    bx = lern.dropna(subset=["konfig", "draw", "rel_place"]).groupby(["konfig", "draw"])["rel_place"].agg(["mean", "count"])
    bx = bx[bx["count"] >= rc.BOX_MIN_LAEUFE]
    urteil = {k: rc.box_urteil(m, n) for k, (m, n) in zip(bx.index, bx[["mean", "count"]].to_numpy())}
    def box(k, d):
        u = urteil.get((k, d))
        return None if not u or not u["sig"] else ("gut" if u["dev"] > 0 else "schlecht")
    h["box"] = [box(k, d) for k, d in zip(h["konfig"], h["draw"])]
    # Bias je Bahn/Distanz relativ zum Schnitt
    bb = rc.bahn_bias(lern)
    ges = (bb["gesamt"] or {}).get("bias")
    def brel(c, d, b):
        e = bb["exakt"].get((c, d)) or bb["gruppe"].get((c, b))
        return None if not e or ges is None else e["bias"] - ges
    h["bias_rel"] = [brel(c, d, b) for c, d, b in zip(h["course_key"], h["distance_m"], h["dist_bucket"])]
    # Linienqualität: Ø höchste Valeur der 3-jährigen Nachkommen (wie max_val3), oberes Viertel
    if "sire_key" in h:
        je = lern[lern["age"] == 3].groupby(["sire_key", "horse_id"])["valeur"].max().dropna()
        q = je.groupby(level=0).agg(["mean", "size"])
        q = q[q["size"] >= rc.POP_MIN_PFERDE]["mean"]
        h["linie_top"] = h["sire_key"].map((q >= q.quantile(0.75)).to_dict()).eq(True) if len(q) else False
    else:
        h["linie_top"] = False
    # Belagneigung von Vater und Muttervater: Ø rel. Platzierung der Nachkommen auf PSF − auf Gras (gelernt)
    for rolle in ("sire", "dam_sire"):
        k = rolle + "_key"
        if k not in h:
            h[rolle + "_belag"] = "neutral"
            continue
        a = lern.dropna(subset=[k, "rel_place"]).groupby([k, "psf"])["rel_place"].agg(["mean", "size"]).unstack("psf")
        ok = (a[("size", True)] >= 30) & (a[("size", False)] >= 30) if ("size", True) in a and ("size", False) in a else None
        if ok is None or not ok.any():
            h[rolle + "_belag"] = "neutral"
            continue
        neig = (a[("mean", True)] - a[("mean", False)])[ok]
        hi, lo = neig.quantile(0.75), neig.quantile(0.25)
        lab = {s: ("psf" if v >= hi else "gras" if v <= lo else "neutral") for s, v in neig.items()}
        nl = h[k].map(lab).fillna("neutral")
        h[rolle + "_belag"] = np.select([nl.eq("neutral"), nl.eq(np.where(h["psf"], "psf", "gras"))],
                                        ["neutral", "passt"], "passt nicht")
    return h


# --------------------------------------------------------------------------
# Auswertung
# --------------------------------------------------------------------------
def kennzahlen(t: pd.DataFrame) -> dict:
    t = t[t["p_mkt"].notna()]
    n, w, e = len(t), int(t["won"].sum()), float(t["p_mkt"].sum())
    var = float((t["p_mkt"] * (1 - t["p_mkt"])).sum())
    pl, epl = int(t["placed"].sum()), float(t["exp_place"].sum()) if "exp_place" in t else np.nan
    roi = float((t["won"] * t["odds_final"]).sum() / n - 1) if n else np.nan
    return {"n": n, "siege": w, "erw": round(e, 1), "ae_sieg": round(w / e, 2) if e else np.nan,
            "z": round((w - e) / np.sqrt(var), 1) if var else np.nan, "plaetze": pl,
            "ae_platz": round(pl / epl, 2) if epl else np.nan, "roi": round(roi, 2),
            "duenn": n < MIN_N}


def regeln(h: pd.DataFrame) -> list[tuple[str, str, pd.Series]]:
    """(Skill-Stelle, Gruppe, Maske). Vergleichsgruppen stehen jeweils dabei."""
    T = h["racetype"].fillna("")
    claimer, hcp, cond = T.eq("Claimer"), T.eq("Handicap"), T.isin(["Conditions", "Listed", "Group 1", "Group 2", "Group 3"])
    s, tg = h["starts_x"], h["tage"]
    alle = pd.Series(True, index=h.index)
    R = []
    add = lambda stelle, name, m: R.append((stelle, name, m.fillna(False).astype(bool)))
    # A1 Wallach im Claimer
    for typ, m in [("Claimer", claimer), ("Handicap", hcp), ("Conditions+", cond)]:
        add("A1 Wallach", f"Wallach · {typ}", h["wallach"] & m)
        add("A1 Wallach", f"kein Wallach · {typ}", ~h["wallach"] & m)
    # B1 Exposure: wenige Starts je Rennart, mit Linienqualität
    for typ, m in [("Claimer", claimer), ("Handicap", hcp), ("Conditions+", cond), ("alle", alle)]:
        add("B1 Exposure", f"1–3 Starts · {typ}", s.between(1, 3) & m)
        add("B1 Exposure", f"4–10 Starts · {typ}", s.between(4, 10) & m)
        add("B1 Exposure", f"> 10 Starts · {typ}", (s > 10) & m)
    add("B1 Exposure", "1–3 Starts · Top-Linie (Test)", s.between(1, 3) & h["linie_top"] & h["test"])
    add("B1 Exposure", "1–3 Starts · übrige Linien (Test)", s.between(1, 3) & ~h["linie_top"] & h["test"])
    add("B1 Exposure", "1–3 Starts · letzter Lauf stärkeres Rennen", s.between(1, 3) & (h["cls_epr_kl_vor"] > 1.3 * h["cls_epr_kl"]))
    add("B1 Exposure", "3j Handicap · ≤ 5 Starts", hcp & (h["age"] == 3) & (s <= 5))
    add("B1 Exposure", "3j Handicap · ≥ 12 Starts", hcp & (h["age"] == 3) & (s >= 12))
    # B6a Pause, getrennt nach Erfahrung
    for name, m in [("1–3 Starts", s.between(1, 3)), ("4–10 Starts", s.between(4, 10)), ("> 10 Starts", s > 10)]:
        for tn, tm in [("≤ 35 T", tg <= 35), ("36–55 T", tg.between(36, 55)), ("56–90 T", tg.between(56, 90)),
                       ("> 90 T", tg > 90)]:
            add("B6a Pause", f"{name} · {tn}", m & tm)
    # A3/B0 Klassenabstieg
    add("A3 Klasse", "letzter Lauf ≥ 30 % stärkeres Rennen · Claimer", claimer & (h["cls_epr_kl_vor"] > 1.3 * h["cls_epr_kl"]))
    add("A3 Klasse", "letzter Lauf ≥ 30 % stärkeres Rennen · übrige", ~claimer & (h["cls_epr_kl_vor"] > 1.3 * h["cls_epr_kl"]))
    # A4 Tempo und Bias (Laufstil aus ≥ 3 getrackten Läufen vor dem Rennen)
    vorne, hinten = h["stil"].isin(["F", "V"]), h["stil"].isin(["M", "H"])
    br = pd.to_numeric(h["bias_rel"], errors="coerce")
    for name, m in [("bias_rel > +0,25", br > 0.25), ("bias_rel ±0,25", br.abs() <= 0.25), ("bias_rel < −0,25", br < -0.25)]:
        add("A4 Bias (Test)", f"F/V · {name}", vorne & m & h["test"])
        add("A4 Bias (Test)", f"M/H · {name}", hinten & m & h["test"])
    bek = h["stil_bekannt"] >= 0.6 * h["n_runners"]
    add("A4 Tempo", "Stil F · einziger Tempomacher", (h["stil"] == "F") & (h["n_front"] == 1) & bek)
    add("A4 Tempo", "Stil F · ≥ 3 Tempomacher", (h["stil"] == "F") & (h["n_front"] >= 3) & bek)
    add("A4 Tempo", "Stil F/V · kein/1 Tempomacher im Feld", vorne & (h["n_front"] <= 1) & bek)
    add("A4 Tempo", "Stil H · ≥ 3 Tempomacher", (h["stil"] == "H") & (h["n_front"] >= 3) & bek)
    add("A4 Tempo", "Stil H · ≤ 1 Tempomacher", (h["stil"] == "H") & (h["n_front"] <= 1) & bek)
    # B6 Startbox (Test)
    add("B6 Box (Test)", "Box sig gut", h["box"].eq("gut") & h["test"])
    add("B6 Box (Test)", "Box sig schlecht", h["box"].eq("schlecht") & h["test"])
    add("B6 Box (Test)", "Box sig schlecht · Stil F/V", h["box"].eq("schlecht") & vorne & h["test"])
    add("B6 Box (Test)", "Box sig schlecht · Stil M/H", h["box"].eq("schlecht") & hinten & h["test"])
    # B4 Laufbild des letzten Laufs
    add("B4 Laufbild", "zuletzt hinten (≥ 0,65) im langsamen Rennen (pace < 97)", (h["early_pct_vor"] >= 0.65) & (h["pace_ratio_vor"] < 97))
    add("B4 Laufbild", "zuletzt vorne (≤ 0,2) im langsamen Rennen (pace < 97)", (h["early_pct_vor"] <= 0.2) & (h["pace_ratio_vor"] < 97))
    add("B4 Laufbild", "zuletzt vorne (≤ 0,2) im schnellen Rennen (pace > 103)", (h["early_pct_vor"] <= 0.2) & (h["pace_ratio_vor"] > 103))
    add("B4 Laufbild", "zuletzt Umweg ≥ 10 m und ≥ 3 Plätze gutgemacht", (h["weg_med_vor"] >= 10) & (h["pos_gain_800_finish_vor"] >= 3))
    add("B4 Laufbild", "zuletzt ΔL600 A ≥ +0,5, nicht gewonnen", (h["d_L600_A_vor"] >= 0.5) & (h["won_vor"] == 0))
    add("B4 Laufbild", "zuletzt ΔL600 A ≤ −0,5", h["d_L600_A_vor"] <= -0.5)
    # B2 Wechsel
    add("B2 Wechsel", "Trainerwechsel", h["trainerwechsel"])
    add("B2 Wechsel", "Scheuklappen neu (zuletzt ohne)", h["scheuklappen_neu"])
    add("B6 Distanz", "Distanz −300 m oder mehr", h["dchg"] <= -300)
    add("B6 Distanz", "Distanz +300 m oder mehr", h["dchg"] >= 300)
    add("B6 Belag", "Belagwechsel Gras ↔ PSF", h["belagwechsel"])
    add("B6 Belag", "Gras → PSF", h["gras_psf"])
    add("B6 Belag", "Gras → PSF · erstmals PSF", h["gras_psf"] & (h["psf_laeufe_vor"] == 0) & (h["n_vor"] > 0))
    add("B6 Belag", "Gras → PSF · schon PSF gelaufen", h["gras_psf"] & (h["psf_laeufe_vor"] > 0))
    add("B6 Belag", "PSF → Gras", h["psf_gras"])
    add("B6 Belag", "Gras → PSF · zuletzt platziert", h["gras_psf"] & (h["finish_pos_vor"] <= 3))
    add("B6 Belag", "PSF → Gras · zuletzt platziert", h["psf_gras"] & (h["finish_pos_vor"] <= 3))
    # Übertragbarkeit guter Form: zuletzt platziert, heute gleicher Belag oder Wechsel
    gleich = h["belagwechsel"].eq(False) & (h["n_vor"] > 0)
    for fn, fm in [("zuletzt Sieg", h["finish_pos_vor"] == 1), ("zuletzt platziert", h["finish_pos_vor"] <= 3),
                   ("zuletzt unplatziert", h["finish_pos_vor"] > 3)]:
        add("B6 Belag Form", f"{fn} · gleicher Belag", fm & gleich)
        add("B6 Belag Form", f"{fn} · Gras → PSF", fm & h["gras_psf"])
        add("B6 Belag Form", f"{fn} · PSF → Gras", fm & h["psf_gras"])
    # Vorlieben bei Belagwechsel: eigene Bilanz, Vater, Muttervater (Abstammung: Test)
    wechsel = h["belagwechsel"]
    for lab in ["besser", "gleich", "schlechter", "unbekannt"]:
        add("B6 Belag Pferd", f"Wechsel · eigene Bilanz heutiger Belag {lab}", wechsel & h["pferd_belag"].eq(lab))
    for rolle, rn in [("sire", "Vater"), ("dam_sire", "Muttervater")]:
        for lab in ["passt", "neutral", "passt nicht"]:
            add("B6 Belag Abst. (Test)", f"Wechsel · {rn} {lab}", wechsel & h[rolle + "_belag"].eq(lab) & h["test"])
        add("B6 Belag Abst. (Test)", f"erstmals PSF · {rn} passt", h["gras_psf"] & (h["psf_laeufe_vor"] == 0)
            & (h["n_vor"] > 0) & h[rolle + "_belag"].eq("passt") & h["test"])
        add("B6 Belag Abst. (Test)", f"erstmals PSF · {rn} passt nicht", h["gras_psf"] & (h["psf_laeufe_vor"] == 0)
            & (h["n_vor"] > 0) & h[rolle + "_belag"].eq("passt nicht") & h["test"])
    beide = h["sire_belag"].eq("passt") & h["dam_sire_belag"].eq("passt")
    add("B6 Belag Abst. (Test)", "Wechsel · Vater und Muttervater passen", wechsel & beide & h["test"])
    # B4 Rennverlauf des letzten Laufs (Norm je Bahn/Distanz gelernt, geprüft nur im Testteil)
    vp, gut = h["verlauf_pferd_vor"], (h["rel_place_vor"] >= 0.6) | (h["finish_pos_vor"] <= 3)
    for name, m in [("gegen den Verlauf", vp.eq("gegen")), ("mit dem Verlauf", vp.eq("mit")),
                    ("Verlauf neutral", vp.eq("neutral"))]:
        add("B4 Verlauf (Test)", f"zuletzt {name}", m & h["test"])
        add("B4 Verlauf (Test)", f"zuletzt {name} · vorderes Feld", m & gut & h["test"])
        add("B4 Verlauf (Test)", f"zuletzt {name} · hinteres Feld", m & ~gut & h["test"])
    for kl, name in [("vorne", "Vorne-Rennen"), ("hinten", "Hinten-Rennen")]:
        k = h["verlauf_kl_vor"].eq(kl) & h["test"]
        add("B4 Verlauf (Test)", f"{name} · zuletzt gegen, ≤ 3 L geschlagen", k & vp.eq("gegen") & (h["lengths_behind_vor"] <= 3))
        add("B4 Verlauf (Test)", f"{name} · zuletzt mit, gewonnen", k & vp.eq("mit") & (h["finish_pos_vor"] == 1))
    # B12 Favorit mit Fragezeichen
    fz = ((tg >= 56).astype(int) + (h["dchg"].abs() >= 300).astype(int) + h["belagwechsel"].astype(int))
    for k, name in [(0, "0"), (1, "1"), (2, "≥ 2")]:
        add("B12 Favorit", f"Favorit · {name} Fragezeichen", h["fav"] & (fz >= 2 if k == 2 else fz == k))
    # B13 Ratings (Wert vor dem Rennen, Rang im Feld)
    for c, lab in [("tr", "TR"), ("arr", "ARR"), ("rtr", "RTR")]:
        add("B13 Ratings", f"{lab} Rang 1", h[c + "_rang"] == 1)
    top2 = sum((h[c + "_rang"] <= 2).astype(int) for c in ["tr", "arr", "rtr"])
    add("B13 Ratings", "≥ 2 von 3 Ratings Top 2", top2 >= 2)
    add("B13 Ratings", "≥ 2 von 3 Ratings Top 2 · nicht Favorit", (top2 >= 2) & ~h["fav"])
    return R


def auswerten(h: pd.DataFrame) -> pd.DataFrame:
    zeilen = [{"stelle": st, "gruppe": name, **kennzahlen(h[m])} for st, name, m in regeln(h)]
    return pd.DataFrame(zeilen)


def run(base: Path | None = None, *, hist: pd.DataFrame | None = None, out: Path | None = None) -> pd.DataFrame:
    if hist is None:
        print("Historie laden (wie die Race Card) …")
        hist = laden(Path(base))
    h = lernen_testen(merkmale(hist))
    mit = h["p_mkt"].notna()
    print(f"{h['race_id'].nunique():,} Rennen, {len(h):,} Starter, davon {mit.sum():,} mit Endquote; "
          f"Zeitraum {h['date'].min():%d.%m.%Y}–{h['date'].max():%d.%m.%Y}; Test ab {h.loc[h['test'], 'date'].min():%d.%m.%Y}")
    erg = auswerten(h)
    with pd.option_context("display.width", 200, "display.max_rows", 500, "display.max_colwidth", 60):
        print(erg.to_string(index=False))
    if base is not None or out is not None:
        out = Path(out) if out else Path(base) / "auswertung" / f"regel_backtest_{pd.Timestamp.today():%Y%m%d}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        erg.to_csv(out, index=False)
        print(f"gespeichert: {out}")
    return erg
