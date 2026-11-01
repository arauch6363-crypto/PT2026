"""Hypothesen H1–H5 gegen den Markt testen: Sagt ein Merkmal bei gegebenem Endkurs zusätzlich etwas über den Sieg voraus?

Zwei Sichten je Hypothese:
* A/E-Gruppen wie im Regel-Backtest (Siege gegen die Erwartung aus der Endquote, z, A/E Platz, ROI),
* bedingtes Logit je Rennen (McFadden): P(Sieg) ∝ exp(β·ln p_mkt + γ·x). β fängt den Markt ein, γ ist der Zusatzeffekt
  des Merkmals. γ > 0 = zu wenig gewettet, γ < 0 = zu viel gewettet; z = γ / SE, ab |z| ≈ 2 belastbar.
  Ein Merkmal gilt nur für die Starter, auf die es zutrifft (sonst 0); Rennen bleiben vollständig.

H1 Rennverlauf gegen das Pferd (Tracking) – mit abgestufter Vorhersage: Tracking-Signal stärker als Pech im Kommentar.
H2 Überreaktion auf das letzte Ergebnis (Marktchance im Vorrennen, geschlagene Favoriten, Überraschungssieger).
H3 Erhöhung im Handicap nach einem Sieg (H3a) und ob das Pferd schon über der neuen Marke lief / Dreijährige (H3b).
H4 Tempo-Szenario × Laufstil (Führende bei erwartet langsamem Tempo, × Frontvorteil der Bahn).
H5 Presse-Konsens (Herde gegen Figlewski): nur vorwärts aus den gespeicherten Claude-JSONs (Tipps sind nicht archiviert).
H6 Duell-Rangfolge (racecard.duell_rangfolge) je Testrennen nachgerechnet, nur aus früheren Läufen – dauert einige Minuten.
H7 Form gegen die Quotenerwartung des Vorlaufs: Variante B (z-Wert gegen E/SD der Pos+ bei dieser Marktchance und
   Feldgröße) und C (Perzentil unter dem Markt), linear, U-Form, je Niveau, plus/minus, letzte 5, zeitgewichtet.
   Nur Endquoten früherer Rennen – die Quote des Tages steckt allein im Maßstab (ln p_mkt), nie im Merkmal.

Colab:
    import hypothesen_backtest as hb
    erg = hb.run(BASE)              # oder hb.run(BASE, hist=hist)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import racecard as rc
import regel_backtest as rb

PECH = re.compile(r"enferm|g[êe]n[ée]|sans ses aises|manqu\w* de place|pas eu (?:de |d')?(?:passage|ouverture)|"
                  r"bouscul|coinc|n'a (?:pu|pas pu) (?:se )?d[ée]gager|tass[ée]|heurt|barr[ée]", re.I)
H1_TAGE, H2_TAGE, H2_KURZ = 60, 120, 35
MIN_AKTIV = 30                   # Variable im Logit erst ab so vielen Startern, auf die sie zutrifft


# --------------------------------------------------------------------------
# Bedingtes Logit je Rennen
# --------------------------------------------------------------------------
def clogit(df: pd.DataFrame, spalten: list[str], iter_max: int = 40) -> pd.DataFrame:
    """Bedingtes Logit (ein Sieger je Rennen). Rückgabe: Variable, Koeffizient, SE, z."""
    d = df.dropna(subset=["ln_p"]).copy()
    voll = d.groupby("race_id")["won"].transform("sum") == 1
    d = d[voll]
    zu_wenig = [c for c in spalten if int((d[c].fillna(0) != 0).sum()) < MIN_AKTIV]
    spalten = [c for c in spalten if c not in zu_wenig]
    X = np.column_stack([d["ln_p"].to_numpy(float)] + [d[c].fillna(0).to_numpy(float) for c in spalten])
    y = d["won"].to_numpy(float)
    g = pd.factorize(d["race_id"])[0]
    b = np.zeros(X.shape[1])
    b[0] = 1.0
    for _ in range(iter_max):
        eta = X @ b
        eta -= pd.Series(eta).groupby(g).transform("max").to_numpy()
        e = np.exp(eta)
        p = e / np.bincount(g, weights=e)[g]
        grad = X.T @ (y - p)
        m = np.column_stack([np.bincount(g, weights=p * X[:, j]) for j in range(X.shape[1])])
        H = X.T @ (p[:, None] * X) - m.T @ m
        try:
            schritt = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        b += schritt
        if np.abs(schritt).max() < 1e-7:
            break
    try:
        se = np.sqrt(np.diag(np.linalg.inv(H)))
    except np.linalg.LinAlgError:
        se = np.full(len(b), np.nan)
    namen = ["ln p_mkt (Markt)"] + spalten
    out = pd.DataFrame({"variable": namen, "koef": b.round(3), "se": se.round(3), "z": (b / se).round(1),
                        "n_aktiv": [len(d)] + [int((d[c].fillna(0) != 0).sum()) for c in spalten],
                        "rennen": d["race_id"].nunique()})
    if zu_wenig:                                       # zu wenige Fälle: nicht schätzen, nur nennen
        out = pd.concat([out, pd.DataFrame({"variable": zu_wenig, "n_aktiv": [int((d[c].fillna(0) != 0).sum())
                                                                              for c in zu_wenig]})], ignore_index=True)
    return out


def _z(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return (s - s.mean()) / s.std()


# --------------------------------------------------------------------------
# Merkmale
# --------------------------------------------------------------------------
def merkmale(hist: pd.DataFrame) -> pd.DataFrame:
    h = rb.lernen_testen(rb.merkmale(hist))
    h["ln_p"] = np.log(h["p_mkt"])
    h = h.sort_values(["date", "race_id", "saddle_no"]).reset_index(drop=True)
    gut = (h["finish_pos"] <= 3) | (h["rel_place"] >= 0.6)
    h["verlauf_plus"] = h["verlauf_pferd"].eq("gegen") & gut
    h["pech"] = h["comment"].astype("string").str.contains(PECH, na=False) if "comment" in h else False
    g = h.groupby("horse_id", sort=False)
    for c in ["verlauf_plus", "tracking", "ausgeritten", "fi_adj", "p_mkt", "odds_rank", "placed", "dist_group",
              "going_pmu", "valeur", "pech", "racetype"]:
        h[c + "_vor"] = g[c].shift() if c in h else np.nan
    return h


# --------------------------------------------------------------------------
# Hypothesen
# --------------------------------------------------------------------------
def h1(h: pd.DataFrame):
    basis = (h["tage"] <= H1_TAGE) & h["tracking_vor"].eq(True) & ~h["ausgeritten_vor"].eq(True)
    d = h[h["test"]].copy()
    b = basis[d.index]
    d["gegen_plus"] = (b & d["verlauf_plus_vor"].eq(True)).astype(float)
    d["mit_top3"] = (b & d["verlauf_pferd_vor"].eq("mit") & (d["finish_pos_vor"] <= 3)).astype(float)
    d["fi_adj_z"] = _z(d["fi_adj_vor"]).where(b, 0)
    d["pos_gain_z"] = _z(d["pos_gain_800_finish_vor"]).where(b, 0)
    pech = (h["tage"] <= H1_TAGE)[d.index] & d["pech_vor"].eq(True)
    d["nur_tracking"] = (d["gegen_plus"].astype(bool) & ~pech).astype(float)
    d["nur_kommentar"] = (pech & ~d["gegen_plus"].astype(bool)).astype(float)
    d["beides"] = (pech & d["gegen_plus"].astype(bool)).astype(float)
    gruppen = [("H1", "gegen den Verlauf, stark beendet (≤ 60 T)", d["gegen_plus"] == 1),
               ("H1", "Gegenprobe: mit dem Verlauf, Platz 1–3", d["mit_top3"] == 1),
               ("H1", "abgestuft: nur Tracking-Signal", d["nur_tracking"] == 1),
               ("H1", "abgestuft: nur Pech im Kommentar", d["nur_kommentar"] == 1),
               ("H1", "abgestuft: beides", d["beides"] == 1)]
    modelle = [("H1 Haupt", d, ["gegen_plus", "mit_top3", "fi_adj_z", "pos_gain_z"]),
               ("H1 abgestuft", d, ["nur_tracking", "nur_kommentar", "beides"])]
    return gruppen, modelle


def h2(h: pd.DataFrame):
    d = h.copy()
    da = (d["tage"] <= H2_TAGE) & d["p_mkt_vor"].notna()
    d["ln_p_vor"] = (np.log(d["p_mkt_vor"]) - np.log(d["p_mkt_vor"]).mean()).where(da, 0)
    d["vor_da"] = da.astype(float)
    fav_geschl = da & (d["odds_rank_vor"] <= 2) & d["placed_vor"].eq(0)
    ueberr = da & (d["odds_rank_vor"] >= 6) & d["won_vor"].eq(1)
    gleich = (d["tage"] <= H2_KURZ) & (d["dist_group"] == d["dist_group_vor"]) & (d["going_pmu"] == d["going_pmu_vor"])
    d["fav_geschlagen"], d["ueberraschung"] = fav_geschl.astype(float), ueberr.astype(float)
    d["gegen_plus"] = ((d["tage"] <= H1_TAGE) & d["verlauf_plus_vor"].eq(True)).astype(float)
    gruppen = [("H2", "zuletzt Favorit/2. Favorit, unplatziert", fav_geschl),
               ("H2", "… davon ≤ 35 T, gleiche Distanzgruppe und Boden", fav_geschl & gleich),
               ("H2", "… davon übrige", fav_geschl & ~gleich),
               ("H2", "Gegenprobe: Überraschungssieger (Quotenrang ≥ 6)", ueberr),
               ("H2", "… davon ≤ 35 T, gleiche Bedingungen", ueberr & gleich)]
    d["ln_p_vor_gleich"] = d["ln_p_vor"].where(gleich, 0)
    modelle = [("H2 Marktchance Vorrennen", d, ["ln_p_vor", "vor_da"]),
               ("H2 + kurz/gleich", d, ["ln_p_vor", "ln_p_vor_gleich", "vor_da"]),
               ("H2 Gruppen + H1", d, ["fav_geschlagen", "ueberraschung", "gegen_plus", "vor_da"])]
    return gruppen, modelle


def h3(h: pd.DataFrame):
    d = h[h["racetype"].eq("Handicap")].copy()
    sieg = d["won_vor"].eq(1) & d["racetype_vor"].eq("Handicap") & (d["tage"] <= H2_TAGE)
    erh = (d["valeur"] - d["valeur_vor"]).where(sieg)
    ueber = (d["arr_vor"] - d["valeur"]).where(sieg)          # Leistung im Siegrennen gegen die neue Marke
    d["sieg_vor"] = sieg.astype(float)
    d["erhoehung"] = erh.fillna(0)
    d["schon_drueber"] = (sieg & (ueber >= 0)).astype(float)
    d["dreijaehrig_sieg"] = (sieg & (d["age"] == 3)).astype(float)
    gruppen = [("H3a", "Handicap-Sieg zuletzt, Erhöhung 0–1,5", sieg & erh.between(0, 1.5)),
               ("H3a", "Handicap-Sieg zuletzt, Erhöhung 2–3,5", sieg & erh.between(2, 3.5)),
               ("H3a", "Handicap-Sieg zuletzt, Erhöhung ≥ 4", sieg & (erh >= 4)),
               ("H3b", "Erhöhung ≥ 2, im Siegrennen schon über neuer Marke (ARR)", sieg & (erh >= 2) & (ueber >= 0)),
               ("H3b", "Erhöhung ≥ 2, darunter", sieg & (erh >= 2) & (ueber < 0)),
               ("H3b", "Erhöhung ≥ 2, Dreijährige", sieg & (erh >= 2) & (d["age"] == 3)),
               ("H3b", "Erhöhung ≥ 2, Ältere", sieg & (erh >= 2) & (d["age"] > 3))]
    modelle = [("H3 Handicap", d, ["sieg_vor", "erhoehung", "schon_drueber", "dreijaehrig_sieg"])]
    return gruppen, modelle


def h4(h: pd.DataFrame):
    lern = h[~h["test"]]
    kal = rc.pace_kalibrierung(lern)
    d = h[h["test"]].copy()
    if not kal.get("coef"):
        return [], []
    c = kal["coef"]
    bek = d["stil_bekannt"] >= 0.6 * d["n_runners"]
    d["pace_diff"] = (c["a"] + c["front"] * d["n_front"].clip(upper=5) + c["field"] * (d["n_runners"] - rc.PACE_FELD_REF)).where(bek)
    bb = rc.bahn_bias(lern)
    ivf = [((bb["exakt"].get((k, m)) or bb["gruppe"].get((k, b2)) or {}).get("iv_front"))
           for k, m, b2 in zip(d["course_key"], d["distance_m"], d["dist_bucket"])]
    d["iv_front"] = pd.to_numeric(pd.Series(ivf, index=d.index), errors="coerce")
    front = (d["stil_vor"] <= rc.TEMPOMACHER) & bek
    d["fuehrend"] = front.astype(float)
    d["fuehrend_x_langsam"] = (-d["pace_diff"]).where(front, 0).fillna(0)
    d["fuehrend_x_ivfront"] = (d["iv_front"] - d["iv_front"].mean()).where(front, 0).fillna(0)
    lang, schnell = d["pace_diff"] <= -rc.PACE_SCHWELLE, d["pace_diff"] >= rc.PACE_SCHWELLE
    gruppen = [("H4", "führend · erwartet langsam", front & lang),
               ("H4", "führend · erwartet normal", front & ~lang & ~schnell),
               ("H4", "führend · erwartet schnell", front & schnell),
               ("H4", "führend · langsam · Bahn mit Frontvorteil (iv_front ≥ 1,3)", front & lang & (d["iv_front"] >= 1.3)),
               ("H4", "führend · einziger Tempomacher", front & (d["n_front"] == 1))]
    modelle = [("H4 Tempo × Stil", d, ["fuehrend", "fuehrend_x_langsam", "fuehrend_x_ivfront"])]
    return gruppen, modelle


def h5(h: pd.DataFrame, base: Path | None):
    """Presse-Konsens aus den gespeicherten Claude-JSONs (vorwärts, ab dem ersten gespeicherten Tag)."""
    dateien = sorted((Path(base) / "racecards").glob("racecard_*_claude.json")) if base else []
    z = []
    for f in dateien:
        try:
            dd = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        fm = f.with_name(f.name.replace("_claude.json", "_markt.json"))   # seit dem blinden Ablauf: Prognose dort
        try:
            mk = json.loads(fm.read_text(encoding="utf-8")) if fm.exists() else {}
        except ValueError:
            mk = {}
        for rid, r in (dd.get("races") or {}).items():
            pm = {y.get("no"): y.get("prono") for y in ((mk.get("races") or {}).get(rid) or {}).get("runners") or []}
            for x in r.get("runners") or []:
                pr = x.get("prono") or pm.get(x.get("no")) or {}
                ranks = [(x.get("tr") or {}).get("rank"), (x.get("arr") or {}).get("rank"), (x.get("rtr") or {}).get("rank")]
                z.append({"race_id": rid, "saddle_no": x.get("no"), "konsens_pts": (pr.get("konsens") or {}).get("pts"),
                          "konsens_pos": (pr.get("konsens") or {}).get("pos"),
                          "objektiv_top": sum(1 for v in ranks if v is not None and v <= 2) >= 2,
                          "typ": r.get("type"), "starter": len(r.get("runners") or [])})
    if not z:
        return [], []
    k = pd.DataFrame(z)
    d = h.merge(k, on=["race_id", "saddle_no"], how="inner")
    if d.empty:
        return [], []
    pts = pd.to_numeric(d["konsens_pts"], errors="coerce").fillna(0)
    d["konsens"] = pts / pts.groupby(d["race_id"]).transform("max").replace(0, np.nan)
    d["konsens"] = d["konsens"].fillna(0)
    tag = d["race_id"].str[:8]
    gross = d["typ"].eq("Handicap") & (d["starter"] >= 14)
    preis = d["prize_eur"].where(gross)
    quinte = gross & (preis == preis.groupby(tag).transform("max"))
    d["konsens_x_quinte"] = d["konsens"].where(quinte, 0)
    kpos = pd.to_numeric(d["konsens_pos"], errors="coerce")
    gruppen = [("H5", "Konsens Platz 1", kpos == 1),
               ("H5", "Konsens Platz 1 · Quinté-Ersatz", (kpos == 1) & quinte),
               ("H5", "objektiv Top (≥ 2 Ratings Top 2), Konsens nicht Top 3", d["objektiv_top"] & ~(kpos <= 3))]
    modelle = [("H5 Konsens (vorwärts)", d, ["konsens", "konsens_x_quinte"])]
    return gruppen, modelle


def duell_merkmale(h: pd.DataFrame, maske: pd.Series | None = None, log_alle: int = 1000) -> pd.DataFrame:
    """Duell-Rangfolge wie auf der Race Card für jedes Rennen in `maske`, nur aus Läufen vor dem Renntag:
    direkte Duelle (DUELL_TAGE, ±DUELL_DIST_M, Boden innerhalb einer Stufe) und indirekte (INDIREKT_*), heutige
    Gewichte aus dem Rennen selbst -> duel_score (L), duel_rank, duel_of, duel_weight je Starter (Index wie h)."""
    h = h.sort_values("date", kind="stable")
    ziel = h[maske.reindex(h.index, fill_value=False)] if maske is not None else h
    # Grundlage der indirekten Duelle einmal für die ganze Historie (vordere Hälfte, kg je Länge), je Tag geschnitten
    basis = rc.indirekte_basis(h, rc.historie_beginn(h) + pd.Timedelta(days=rc.INDIREKT_TAGE)).sort_values("date", kind="stable")
    t_h, t_b = h["date"].to_numpy(), basis["date"].to_numpy()
    spalten = ["duel_score", "duel_rank", "duel_of", "duel_weight"]
    zeilen, n = [], 0
    for tag, rennen in ziel.groupby("date", sort=True):
        t = np.datetime64(tag)
        vorher = h.iloc[np.searchsorted(t_h, np.datetime64(tag - pd.Timedelta(days=rc.DUELL_TAGE))):np.searchsorted(t_h, t)]
        b = basis.iloc[np.searchsorted(t_b, np.datetime64(tag - pd.Timedelta(days=rc.INDIREKT_TAGE))):np.searchsorted(t_b, t)]
        for _, feld in rennen.groupby("race_id"):
            n += 1
            if log_alle and n % log_alle == 0:
                print(f"  Duelle: {n:,} Rennen …")
            gew = {z["horse_id"]: {"weight": rc._num(z["weight_kg"], 1), "no": int(z["saddle_no"])}
                   for _, z in feld.iterrows() if pd.notna(z["saddle_no"])}
            if len(gew) < 2:
                continue
            dist, going = feld["distance_m"].iloc[0], feld["going"].iloc[0] if "going" in feld else None
            gb = rc.going_klasse(going)
            treffen = vorher[vorher["horse_id"].isin(set(gew))]
            if pd.notna(dist) and len(treffen):
                treffen = treffen[(treffen["distance_m"] - dist).abs() <= rc.DUELL_DIST_M]
            if rc.DUELL_BODEN and len(treffen):
                treffen = treffen[np.array([rc._boden_nah(x, gb) for x in treffen["going_pmu"]], dtype=bool)]
            duell_rennen = {k: g for k, g in treffen.groupby("race_id") if g["horse_id"].nunique() >= 2}
            indirekt = rc._indirekte_duelle(b, gew, going, dist, tag)
            starters = []
            for hid, w in gew.items():
                eigen = treffen[(treffen["horse_id"] == hid) & treffen["race_id"].isin(set(duell_rennen))]
                starters.append({"no": w["no"], "nr": False, "hid": hid, "indirect": indirekt.get(hid),
                                 "duels": rc._duelle(eigen, duell_rennen, gew, hid) if len(eigen) else []})
            rc.duell_rangfolge(starters, tag)
            idx = dict(zip(feld["horse_id"], feld.index))
            for x in starters:
                d = x["duel_rank"]
                if d:
                    zeilen.append((idx[x["hid"]], d["score_l"], d["rank"], d["of"], d["weight"]))
    out = pd.DataFrame(zeilen, columns=["_i"] + spalten).set_index("_i") if zeilen else pd.DataFrame(columns=spalten)
    return out.reindex(ziel.index)


def h6(h: pd.DataFrame):
    """Duell-Rangfolge: Zusatzeffekt des Duell-Werts (Längen gegenüber dem Ø der Pferde mit Duellen) und des
    Duell-Rangs 1 bei gegebenem Markt; nur Rennen mit mindestens drei verbundenen Pferden."""
    print("H6: Duell-Rangfolge je Testrennen nachrechnen …")
    d = h[h["test"]].copy()
    d = d.join(duell_merkmale(h, h["test"]))
    da = d["duel_rank"].notna() & (d["duel_of"] >= 3)
    d["duell_da"] = da.astype(float)
    d["duell_score"] = d["duel_score"].where(da, 0).fillna(0)
    d["duell_score_sicher"] = d["duell_score"].where(d["duel_weight"] >= 1, 0).fillna(0)
    d["duell_erster"] = (da & (d["duel_rank"] == 1)).astype(float)
    gruppen = [("H6", "Duell-Rang 1 (≥ 3 verbundene Pferde)", d["duell_erster"] == 1),
               ("H6", "… davon Gewicht ≥ 1", (d["duell_erster"] == 1) & (d["duel_weight"] >= 1)),
               ("H6", "Duell-Rang letzter (≥ 3)", da & (d["duel_rank"] == d["duel_of"])),
               ("H6", "Duell-Wert ≥ +2 L", da & (d["duel_score"] >= 2)),
               ("H6", "Duell-Wert ≤ −2 L", da & (d["duel_score"] <= -2))]
    modelle = [("H6 Duell-Rangfolge", d, ["duell_score", "duell_score_sicher", "duell_erster", "duell_da"])]
    return gruppen, modelle


# --------------------------------------------------------------------------
# H7 Form gegen die Quotenerwartung (Variante B: z-Wert, Variante C: Perzentil unter dem Markt)
# --------------------------------------------------------------------------
H7_P_BINS = 20                   # Klassen der Marktchance (Quantile auf dem Lernteil)
H7_FELD = [1, 7, 11, 15, 99]     # Feldgrößen-Gruppen: ≤ 7, 8–11, 12–15, ≥ 16
H7_MIN = 200                     # Zelle Marktchance × Feldgröße erst ab so vielen Läufen, sonst nur Marktchance
H7_TAGE = 365                    # Vorläufe höchstens so alt
H7_FORM = 5                      # Schnitt über die letzten 5 Läufe
H7_ZG_N, H7_ZG_HALB = 10, 90     # zeitgewichtet: bis zu 10 Läufe, Gewicht 0,5^(Tage ÷ 90)
H7_NIVEAU = [(0.25, 1.01, "Favorit damals (p ≥ 25 %)"), (0.08, 0.25, "Mitte damals (8–25 %)"),
             (0.0, 0.08, "Außenseiter damals (< 8 %)")]
H7_Z_KL = [(-np.inf, -1.5, "z ≤ −1,5"), (-1.5, -0.5, "z −1,5…−0,5"), (-0.5, 0.5, "z −0,5…+0,5"),
           (0.5, 1.5, "z +0,5…+1,5"), (1.5, np.inf, "z ≥ +1,5")]


def markt_erwartung(h: pd.DataFrame, lern: pd.Series) -> pd.DataFrame:
    """Je Lauf: wie gut das Ergebnis gegen die Erwartung des damaligen Markts war.

    Pos+ = (Starter − Platz) / (Starter − 1), nicht im Ziel = 0 (wie power_modell.ziel).
    ue_lin = Pos+ − (1 − Quotenrang relativ)    – die bisherige lineare Fassung (form5_ue)
    ue_z   = (Pos+ − E[Pos+]) / SD[Pos+]        – Variante B
    pit    = P(Pos+ < x) + ½ P(Pos+ = x)        – Variante C (0,5 = wie erwartet; gleichverteilt, wenn der Markt stimmt)
    E, SD und die Verteilung je Zelle Marktchance (Quantilklassen) × Feldgröße, nur aus den Lern-Läufen; Zellen mit
    weniger als H7_MIN Läufen nehmen die Werte der Marktchance-Klasse allein."""
    n = pd.to_numeric(h["n_runners"], errors="coerce")
    rp = pd.to_numeric(h["rel_place"], errors="coerce").fillna(0.0).where(n > 1)
    p = pd.to_numeric(h["p_mkt"], errors="coerce")
    ok = rp.notna() & (p > 0)
    rang = p.where(ok).groupby(h["race_id"]).rank(ascending=False, method="average")
    m = ok.groupby(h["race_id"]).transform("sum")
    ue_lin = rp - (1 - ((rang - 1) / (m - 1)).where(m > 1))

    lp = np.log(p.where(ok))
    l_ok = ok & lern.reindex(h.index, fill_value=False)
    kanten = np.unique(np.quantile(lp[l_ok], np.linspace(0, 1, H7_P_BINS + 1)[1:-1])) if l_ok.any() else np.array([])
    pb = pd.Series(np.digitize(lp.fillna(0), kanten), index=h.index)
    fg = pd.Series(np.digitize(n.fillna(0), H7_FELD[1:-1], right=True), index=h.index)
    zelle = pb * 10 + fg

    def tabelle(schluessel):
        vert = {k: np.sort(v.to_numpy()) for k, v in rp[l_ok].groupby(schluessel[l_ok])}
        return {k: v for k, v in vert.items() if len(v) >= (H7_MIN if schluessel is zelle else 2)}
    t_zelle, t_pb = tabelle(zelle), tabelle(pb)
    ue_z, pit = pd.Series(np.nan, index=h.index), pd.Series(np.nan, index=h.index)
    for z, idx in h.index[ok].groupby(zelle[ok].to_numpy()).items():
        v = t_zelle.get(z)
        v = v if v is not None else t_pb.get(z // 10)
        if v is None:
            continue
        x = rp.loc[idx].to_numpy()
        sd = v.std()
        ue_z.loc[idx] = (x - v.mean()) / sd if sd > 0 else np.nan
        pit.loc[idx] = (np.searchsorted(v, x, "left") + np.searchsorted(v, x, "right")) / (2 * len(v))
    return pd.DataFrame({"pos_plus": rp, "ue_lin": ue_lin.where(ok), "ue_z": ue_z, "pit": pit})


def h7_merkmale(h: pd.DataFrame) -> pd.DataFrame:
    """Merkmale aus den Vorläufen (nur Läufe vor dem Renntag, höchstens H7_TAGE alt)."""
    me = markt_erwartung(h, ~h["test"])
    h = h.drop(columns=me.columns, errors="ignore").join(me)
    h = h.sort_values(["date", "race_id", "saddle_no"])
    g = h.groupby("horse_id", sort=False)
    vor = {k: {c: g[c].shift(k) for c in ["date", "ue_z", "pit", "ue_lin", "p_mkt"]} for k in range(1, H7_ZG_N + 1)}
    for k in vor:
        alt = (h["date"] - vor[k]["date"]).dt.days
        frisch = alt <= H7_TAGE
        for c in ["ue_z", "pit", "ue_lin", "p_mkt"]:
            vor[k][c] = vor[k][c].where(frisch)
        vor[k]["w"] = (0.5 ** (alt / H7_ZG_HALB)).where(frisch & vor[k]["ue_z"].notna())
    out = pd.DataFrame(index=h.index)
    for c in ["ue_z", "pit", "ue_lin", "p_mkt"]:
        out[c + "_vor"] = vor[1][c]
    z5 = pd.concat([vor[k]["ue_z"] for k in range(1, H7_FORM + 1)], axis=1)
    out["ue_z_5"] = z5.mean(axis=1)
    out["ue_z_plus5"] = z5.clip(lower=0).mean(axis=1)
    out["ue_z_minus5"] = z5.clip(upper=0).mean(axis=1)
    out["ue_z_abs5"] = z5.abs().mean(axis=1)
    out["ue_z_n5"] = z5.notna().sum(axis=1)
    zs = sum(vor[k]["ue_z"].fillna(0) * vor[k]["w"].fillna(0) for k in vor)
    ws = sum(vor[k]["w"].fillna(0) for k in vor)
    out["ue_z_zg"] = (zs / (ws + 1)).where(ws > 0)        # zum Ausgangswert 0 geschrumpft wie mit einem heutigen Lauf
    return out


def h7(h: pd.DataFrame):
    """Form gegen die Quotenerwartung: z-Wert (B) und Perzentil (C) des Vorlaufs und der letzten Läufe gegen den Sieg
    im nächsten Lauf; Klassen je Niveau des Vorlaufs (Favorit/Mitte/Außenseiter) beantworten, ob dieselbe Abweichung
    beim Favoriten so viel wert ist wie in der Feldmitte."""
    m7 = h7_merkmale(h)
    d = h.drop(columns=m7.columns, errors="ignore").join(m7)          # eigene Fassung (z. B. p_mkt_vor ≤ 365 T) gilt
    d = d[d["test"]].copy()
    da = d["ue_z_vor"].notna()
    d["vor_da"], d["form_da"] = da.astype(float), d["ue_z_5"].notna().astype(float)
    z = d["ue_z_vor"]
    d["ue_z"], d["ue_z_q"] = z.fillna(0), (z ** 2 - 1).where(da, 0)          # quadratisch: U-Form
    d["ue_lin"] = d["ue_lin_vor"].fillna(0)
    d["pit_c"] = (d["pit_vor"] - 0.5).fillna(0)
    d["pit_abs"] = (2 * (d["pit_vor"] - 0.5).abs() - 0.5).where(da & d["pit_vor"].notna(), 0)  # 0 = Zufall
    for c in ["ue_z_5", "ue_z_plus5", "ue_z_minus5", "ue_z_zg"]:
        d[c] = d[c].fillna(0)
    d["ue_z_abs5"] = (d["ue_z_abs5"] - 0.8).fillna(0)                     # ≈ Ø |z| bei Zufall (√(2/π))
    gruppen, niveau = [], {}
    for lo, hi, name in H7_NIVEAU:
        niveau[name] = da & d["p_mkt_vor"].ge(lo) & d["p_mkt_vor"].lt(hi)
        d["ue_z_x_" + name.split()[0].lower()] = z.where(niveau[name], 0).fillna(0)
    for lo, hi, kl in H7_Z_KL:
        gruppen.append(("H7B", f"Vorlauf {kl}", da & z.gt(lo) & z.le(hi)))
    for name, m in niveau.items():
        for lo, hi, kl in H7_Z_KL:
            gruppen.append(("H7B", f"{name} · {kl}", m & z.gt(lo) & z.le(hi)))
    for k in range(5):
        lo, hi = k / 5, (k + 1) / 5
        gruppen.append(("H7C", f"Vorlauf Perzentil {lo:.1f}–{hi:.1f}", d["pit_vor"].ge(lo) & (d["pit_vor"].lt(hi) | (k == 4))))
    gruppen += [("H7B", "letzte 5: Ø z ≥ +0,5 (mind. 3 Läufe)", (d["ue_z_n5"] >= 3) & (d["ue_z_5"] >= 0.5)),
                ("H7B", "letzte 5: Ø z ≤ −0,5 (mind. 3 Läufe)", (d["ue_z_n5"] >= 3) & (d["ue_z_5"] <= -0.5)),
                ("H7B", "letzte 5: unberechenbar (Ø |z| ≥ 1,2, mind. 3)", (d["ue_z_n5"] >= 3) & (d["ue_z_abs5"] >= 0.4))]
    x_niv = [c for c in d if c.startswith("ue_z_x_")]
    # Kennzeichen „Vorlauf da“ nur, wenn es auch Starter ohne gibt (sonst im bedingten Logit nicht schätzbar)
    vd = ["vor_da"] if int((d["vor_da"] == 0).sum()) >= MIN_AKTIV else []
    fd = ["form_da"] if int((d["form_da"] == 0).sum()) >= MIN_AKTIV else []
    modelle = [("H7 linear (bisher, Quotenrang)", d, ["ue_lin"] + vd),
               ("H7B z Vorlauf + U-Form", d, ["ue_z", "ue_z_q"] + vd),
               ("H7B z Vorlauf je Niveau", d, x_niv + vd),
               ("H7B letzte 5: plus/minus", d, ["ue_z_plus5", "ue_z_minus5"] + fd),
               ("H7B letzte 5: Ø und Streuung", d, ["ue_z_5", "ue_z_abs5"] + fd),
               ("H7B zeitgewichtet", d, ["ue_z_zg"] + fd),
               ("H7C Perzentil Vorlauf + U-Form", d, ["pit_c", "pit_abs"] + vd)]
    return gruppen, modelle


# --------------------------------------------------------------------------
def run(base: Path | None = None, *, hist: pd.DataFrame | None = None, out: Path | None = None):
    if hist is None:
        print("Historie laden (wie die Race Card) …")
        hist = rb.laden(Path(base))
    h = merkmale(hist)
    print(f"{h['race_id'].nunique():,} Rennen, Test ab {h.loc[h['test'], 'date'].min():%d.%m.%Y} (H1, H4, H6 nur im Testteil)")
    zeilen, koef = [], []
    for name, fn in [("H1", h1), ("H2", h2), ("H3", h3), ("H4", h4), ("H5", lambda x: h5(x, base)), ("H6", h6), ("H7", h7)]:
        try:
            gruppen, modelle = fn(h)
        except Exception as e:                       # eine Hypothese darf die anderen nicht aufhalten
            print(f"{name}: Fehler {type(e).__name__}: {e}")
            continue
        for hyp, gruppe, maske in gruppen:
            ziel = modelle[0][1] if modelle else h
            zeilen.append({"hypothese": hyp, "gruppe": gruppe, **rb.kennzahlen(ziel[maske.reindex(ziel.index, fill_value=False)])})
        for mname, d, spalten in modelle:
            try:
                koef.append(clogit(d, spalten).assign(modell=mname))
            except Exception as e:
                print(f"{mname}: Logit nicht berechnet ({type(e).__name__}: {e})")
    gr = pd.DataFrame(zeilen)
    ko = pd.concat(koef, ignore_index=True)[["modell", "variable", "koef", "se", "z", "n_aktiv", "rennen"]] if koef else pd.DataFrame()
    with pd.option_context("display.width", 200, "display.max_rows", 300, "display.max_colwidth", 70):
        print("\nA/E-Gruppen (gegen die Endquote)\n" + gr.to_string(index=False))
        if len(ko):
            print("\nBedingtes Logit: Zusatzeffekt bei gegebenem Markt (koef > 0 = zu wenig gewettet)\n" + ko.to_string(index=False))
    if base is not None or out is not None:
        ziel = Path(out) if out else Path(base) / "auswertung"
        ziel.mkdir(parents=True, exist_ok=True)
        tag = f"{pd.Timestamp.today():%Y%m%d}"
        gr.to_csv(ziel / f"hypothesen_gruppen_{tag}.csv", index=False)
        ko.to_csv(ziel / f"hypothesen_logit_{tag}.csv", index=False)
        print(f"\ngespeichert: {ziel}/hypothesen_*_{tag}.csv")
    return {"gruppen": gr, "logit": ko}
