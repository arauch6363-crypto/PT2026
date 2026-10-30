"""Kombiwetten aus den Siegchancen der Karte: Couplé Placé, 2sur4 und Quinté+ – Wahrscheinlichkeiten aus dem
Einlauf-Modell (einlauf.py) und Rückrechnung gegen die echten PMU-Dividenden (NATIONAL-Pool).

    import kombi
    r = kombi.rueckrechnung(BASE)          # alle gespeicherten Karten ab START_DATUM: Bericht je Wettart

Je Rennen das ganze Feld aus racecard_JJJJMMTT_daten.json (Modell: faire Siegchance der Karte; Karten mit
Morgenquote: sieg_blind), die Toto-Endquote aus pmu_runners (Sicht des Publikums) und die Dividenden aus
pmu_dividends. Gewonnen hat eine Kombination, wenn die PMU sie in den Dividenden listet (Zeilen „NP“ und
Rückzahlungen bleiben weg). Gezogene Einläufe: Modell mit den Modell-λ, Publikum mit den Markt-λ.

Paarwetten (Couplé Placé: beide unter den ersten 3; 2sur4: beide unter den ersten 4). Couplé Placé: jedes Gewinnpaar
hat ein eigenes Drittel des Pools, Dividende ≈ c ÷ P_Publikum(Paar), Erwartungswert = P_Modell × c ÷ P_Publikum − 1.
2sur4: die 6 Gewinnpaare teilen sich einen Topf, Dividende ≈ c × 6 ÷ S mit S = Σ P_Publikum der 6 Gewinnpaare –
ein Außenseiter-Paar zahlt wenig, wenn es mit Favoriten-Paaren gewinnt; Erwartungswert = c × 6 × E[1/S; Paar gewinnt]
− 1 über die gezogenen Einläufe des Modells. c = Auszahlungsfaktor (≈ 1 − Abzug), aus den echten Gewinnpaaren
geschätzt. Gewettet wird je Paar mit Erwartungswert ≥ Schwelle, 1 € je Ticket.
Quinté+: ein Ticket aus 5 Pferden je Quinté-Rennen – die 5 mit der höchsten Modellchance (zum Vergleich: die 5
Markt-Favoriten); gezahlt wird die höchste Stufe (Ordre, Désordre, Bonus 4sur5, Bonus 3).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import einlauf

START_DATUM = "20261018"
# Wettart: (PMU-Code, Plätze, Pool) – Couplé Placé: jedes der 3 Gewinnpaare bekommt ein eigenes Drittel des Pools;
# 2sur4: alle 6 Gewinnpaare teilen sich einen Topf und zahlen dieselbe Dividende
PAARE = {"couple_place": ("COUPLE_PLACE", 3, "einzeln"), "2sur4": ("DEUX_SUR_QUATRE", 4, "gemeinsam")}
QUINTE = "QUINTE_PLUS"
QUINTE_STUFEN = ("ordre", "desordre", "bonus4sur5", "bonus3")
N_SIM = 20000
# Auszahlungsfaktor c (≈ 1 − Abzug) für den Vorwärtstest, solange zu wenige frühere Rennen abgerechnet sind
# (Rückrechnung Okt. 2026 gegen die Toto-Endquote, NATIONAL-Pool); danach laufend aus den Vortagen
KOMBI_C = {"couple_place": 0.77, "2sur4": 0.66}


def _karte_feld(pfad: Path) -> pd.DataFrame:
    """Alle Starter (ohne Nichtstarter) mit Modell-Siegchance aus einer gespeicherten Karte."""
    d = json.loads(pfad.read_text(encoding="utf-8"))
    tag = str(d.get("date") or "").replace("-", "")
    rennen = d.get("races") or {}
    zeilen = []
    for r in (rennen.values() if isinstance(rennen, dict) else rennen):
        st = [x for x in r.get("runners") or [] if not x.get("nr") and (x.get("power") or {}).get("sieg")]
        if len(st) < 4:
            continue
        morgen = any(x["power"].get("sieg_quelle") in ("morgen", "mischung") for x in st)
        p = np.array([(x["power"].get("sieg_blind") if morgen else None) or x["power"]["sieg"] for x in st], float)
        sh = np.array([x["power"].get("sieg_schatten") or np.nan for x in st], float)   # Schattenversion (Prognose)
        sh = sh / sh.sum() if np.all(sh > 0) else np.full(len(st), np.nan)
        for x, pi, si in zip(st, p / p.sum(), sh):
            zeilen.append({"date": tag, "race_id": str(r.get("race_id")), "no": int(x["no"]), "horse": x.get("horse"),
                           "p": float(pi), "p_sh": float(si),
                           "fk_karte": (x.get("fk") or {}).get("sieg"),     # Festkurs Sieg der Karte
                           "toto_karte": (x.get("fk") or {}).get("toto")})   # Toto-Stand beim Holen der Festkurse
    return pd.DataFrame(zeilen)


def _parquets(ordner: Path, tage: set[str]) -> pd.DataFrame:
    teile = [pd.read_parquet(p) for p in sorted(Path(ordner).glob("*.parquet"))
             if re.search(r"(\d{8})", p.name) and re.search(r"(\d{8})", p.name).group(1) in tage]
    return pd.concat(teile, ignore_index=True) if teile else pd.DataFrame()


def daten_laden(base: Path, ab: str | None = START_DATUM, bis: str | None = None) -> dict:
    """Feld (Modellchance), Toto-Endquote und Dividenden (NATIONAL, ohne NP/Rückzahlung) aller Karten im Zeitraum."""
    base = Path(base)
    karten = {}
    for p in sorted((base / "racecards").rglob("racecard_*_daten.json")):
        m = re.search(r"racecard_(\d{8})_daten", p.name)
        if m and (ab is None or m.group(1) >= ab) and (bis is None or m.group(1) <= bis):
            karten[m.group(1)] = p
    feld = pd.concat([_karte_feld(p) for p in karten.values()], ignore_index=True) if karten else pd.DataFrame()
    tage = set(karten)
    ru = _parquets(base / "parquet" / "pmu_runners", tage)
    if len(ru):
        ru = ru.assign(race_id=ru["race_id"].astype(str), no=pd.to_numeric(ru["saddle_no"], errors="coerce"),
                       odds=pd.to_numeric(ru["odds_final"], errors="coerce"))[["race_id", "no", "odds"]].dropna()
        feld = feld.merge(ru.drop_duplicates(["race_id", "no"]), on=["race_id", "no"], how="left")
    else:
        feld["odds"] = np.nan
    dv = _parquets(base / "parquet" / "pmu_dividends", tage)
    if len(dv):
        lab = dv["label"].astype(str)
        dv = dv[dv["audience"].astype(str).eq("NATIONAL") & ~dv["refunded"].eq(True)
                & ~lab.str.contains(r"NP|Rembours", case=False, regex=True)
                & ~dv["combination"].astype(str).str.contains("NP", na=False)].copy()
        dv["race_id"] = dv["race_id"].astype(str)
        dv["div"] = pd.to_numeric(dv["dividend_eur_per_1eur"], errors="coerce")
        dv["einsatz_kombi"] = pd.to_numeric(dv["winners"], errors="coerce") * pd.to_numeric(dv["base_stake"], errors="coerce") / 100
    return {"feld": feld, "dividenden": dv, "tage": sorted(tage)}


def paar_chancen(p, plaetze: int, lam, n_sim: int = N_SIM, rng=None) -> np.ndarray:
    """Matrix P[i, j]: Chance, dass i und j beide unter den ersten `plaetze` sind (gezogene Einläufe)."""
    E = einlauf.einlaeufe(p, plaetze, lam, n_sim, rng)
    M = np.zeros((n_sim, len(p)), float)
    np.put_along_axis(M, E, 1.0, axis=1)
    P = M.T @ M / n_sim
    np.fill_diagonal(P, 0.0)
    return P


def _paare_rennen(g: pd.DataFrame, plaetze: int, lam_m, lam_p, n_sim, rng) -> pd.DataFrame:
    """Alle Paare eines Rennens mit P_Modell, P_Publikum (aus der Toto-Endquote; ohne Quote: NaN) und kehr_s =
    E[1/S; Paar gewinnt] über die Einläufe des Modells (S = Σ P_Publikum aller Gewinnpaare des Einlaufs; für 2sur4)."""
    nos, n = g["no"].to_numpy(), len(g)
    E = einlauf.einlaeufe(g["p"].to_numpy(), plaetze, lam_m, n_sim, rng)
    M = np.zeros((n_sim, n), float)
    np.put_along_axis(M, E, 1.0, axis=1)
    Pm = M.T @ M / n_sim
    q = g["odds"].to_numpy(float)
    Pp = paar_chancen((1 / q) / np.nansum(1 / q), plaetze, lam_p, n_sim, rng) if np.all(q > 1) else np.full((n, n), np.nan)
    a_, b_ = np.triu_indices(E.shape[1], 1)
    S = Pp[E[:, a_], E[:, b_]].sum(axis=1)                  # je gezogenem Einlauf: Σ P_Publikum der Gewinnpaare
    K = (M / np.where(S > 0, S, np.nan)[:, None]).T @ M / n_sim if np.all(np.isfinite(S)) else np.full((n, n), np.nan)
    i, j = np.triu_indices(n, 1)
    return pd.DataFrame({"race_id": g["race_id"].iloc[0], "date": g["date"].iloc[0], "a": nos[i], "b": nos[j],
                         "p_modell": Pm[i, j], "p_publikum": Pp[i, j], "kehr_s": K[i, j]})


def a_paare(plaetze: int) -> list[tuple[int, int]]:
    """Gewinnpaare eines Einlaufs: alle Paare unter den ersten `plaetze` (3 → 3 Paare, 4 → 6 Paare)."""
    return [(a, b) for a in range(plaetze) for b in range(a + 1, plaetze)]


def _paar_key(a, b) -> str:
    return "-".join(sorted([str(int(a)), str(int(b))], key=int))


def _bootstrap_roi(t: pd.DataFrame, n: int = 2000, seed: int = 0) -> tuple[float | None, float | None]:
    """90-%-Intervall des ROI (Rennen als Cluster gezogen)."""
    if t.empty:
        return None, None
    je = t.groupby("race_id").agg(e=("einsatz", "sum"), r=("rueck", "sum"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(je), (n, len(je)))
    roi = je["r"].to_numpy()[idx].sum(1) / je["e"].to_numpy()[idx].sum(1) - 1
    return round(float(np.quantile(roi, 0.05)), 3), round(float(np.quantile(roi, 0.95)), 3)


def _auswertung(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"tickets": 0}
    lo, hi = _bootstrap_roi(t)
    return {"tickets": int(len(t)), "rennen": int(t["race_id"].nunique()), "treffer": int(t["treffer"].sum()),
            "trefferquote": round(float(t["treffer"].mean()), 3),
            "erwartet_modell": round(float(t["p_modell"].sum()), 1),
            "erwartet_publikum": round(float(t["p_publikum"].sum()), 1) if t["p_publikum"].notna().any() else None,
            "roi": round(float(t["rueck"].sum() / t["einsatz"].sum() - 1), 3), "roi_90": [lo, hi]}


def paarwetten(daten: dict, art: str, schwellen=(0.0, 0.2, 0.5), lam=None, n_sim: int = N_SIM, seed: int = 0) -> dict:
    """Rückrechnung einer Paarwette (couple_place, 2sur4) über alle Rennen, in denen die PMU sie anbot."""
    code, plaetze, pool = PAARE[art]
    lam = lam or {"modell": einlauf.VORGABE, "markt": einlauf.VORGABE}
    dv = daten["dividenden"]
    dv = dv[dv["bet_type"].eq(code)] if len(dv) else dv
    if dv.empty:
        return {"art": art, "rennen": 0, "grund": "keine Dividenden dieser Wettart"}
    gew = {(r, _paar_key(*c.split("-"))): (d, e) for r, c, d, e in zip(dv["race_id"], dv["combination"], dv["div"], dv["einsatz_kombi"])}
    rng = np.random.default_rng(seed)
    feld = daten["feld"]
    feld = feld[feld["race_id"].isin(set(dv["race_id"]))]
    P = pd.concat([_paare_rennen(g, plaetze, lam["modell"], lam["markt"], n_sim, rng)
                   for _, g in feld.groupby("race_id", sort=False)], ignore_index=True) if len(feld) else pd.DataFrame()
    if P.empty:
        return {"art": art, "rennen": 0, "grund": "keine Karten zu diesen Rennen"}
    k = [gew.get((r, _paar_key(a, b))) for r, a, b in zip(P["race_id"], P["a"], P["b"])]
    P["treffer"] = [x is not None for x in k]
    P["div"] = [x[0] if x else 0.0 for x in k]
    P["einsatz_kombi"] = [x[1] if x else np.nan for x in k]
    P = P[P["p_publikum"].notna()]
    # Auszahlungsfaktor c (≈ 1 − Abzug, Median über die Gewinnpaare bzw. -rennen)
    w = P[P["treffer"] & (P["div"] > 0)]
    if pool == "einzeln":                                  # Dividende = c / P_Publikum des Paars
        c = float(np.median(w["div"] * w["p_publikum"])) if len(w) else np.nan
        P["ew"] = P["p_modell"] * c / P["p_publikum"] - 1
    else:                                                  # Dividende = c × m / S, S = Σ P_Publikum der m Gewinnpaare
        je = w.groupby("race_id").agg(d=("div", "first"), s=("p_publikum", "sum"), m=("div", "size"))
        c = float(np.median(je["d"] * je["s"] / je["m"])) if len(je) else np.nan
        P["ew"] = c * len(a_paare(plaetze)) * P["kehr_s"] - 1
    P["einsatz"], P["rueck"] = 1.0, P["div"]
    out = {"art": art, "pmu_code": code, "plaetze": plaetze, "pool": pool, "rennen": int(P["race_id"].nunique()),
           "paare": int(len(P)), "auszahlungsfaktor_c": round(c, 3),
           "einsatz_auf_gewinnkombi_median": round(float(np.nanmedian(w["einsatz_kombi"])), 0) if len(w) else None,
           "eichung": eichung(P), "alle_paare": _auswertung(P)}
    out["je_schwelle"] = {f"ew_ab_{s:g}": _auswertung(P[P["ew"] >= s]) for s in schwellen}
    out["paare_tabelle"] = P
    return out


def eichung(P: pd.DataFrame, gruppen=(0, 0.02, 0.05, 0.1, 0.2, 1.01)) -> list[dict]:
    """Treffer gegen Σ P_Modell und Σ P_Publikum je Gruppe der Modell-Wahrscheinlichkeit des Paars."""
    g = pd.cut(P["p_modell"], list(gruppen), right=False)
    return [{"p_modell": str(b), "paare": int(len(s)), "treffer": int(s["treffer"].sum()),
             "erwartet_modell": round(float(s["p_modell"].sum()), 1), "erwartet_publikum": round(float(s["p_publikum"].sum()), 1)}
            for b, s in P.groupby(g, observed=True)]


def _quinte_stufe(ticket: set, reihe: list, zeilen: pd.DataFrame) -> tuple[str | None, float]:
    """Höchste Stufe, die ein Ticket (5 Pferde, Reihe = in Modell-Reihenfolge) laut Dividenden gewinnt."""
    best = (None, 0.0)
    for lab, comb, d in zip(zeilen["label"].astype(str), zeilen["combination"].astype(str), zeilen["div"]):
        nos = [int(x) for x in re.findall(r"\d+", comb)]
        l_ = lab.lower()
        if "ordre" in l_ and "dés" not in l_ and "des" not in l_:
            ok, st = reihe[:5] == nos[:5], "ordre"
        elif "dés" in l_ or "desordre" in l_:
            ok, st = set(nos) <= ticket, "desordre"
        elif "4sur5" in l_ or "4 sur 5" in l_:
            ok, st = set(nos) <= ticket, "bonus4sur5"
        elif "bonus 3" in l_ or "bonus3" in l_:
            ok, st = set(nos) <= ticket, "bonus3"
        else:
            continue
        if ok and (best[0] is None or QUINTE_STUFEN.index(st) < QUINTE_STUFEN.index(best[0])):
            best = (st, float(d or 0))
    return best


def quinte(daten: dict, lam=None, n_sim: int = N_SIM, seed: int = 0) -> dict:
    """Quinté+: je Quinté-Rennen ein Ticket aus den 5 Pferden mit der höchsten Modellchance (Vergleich: die 5
    Markt-Favoriten); Treffer je Stufe, ROI und die Modell-Wahrscheinlichkeit, dass das Ticket überhaupt zahlt."""
    lam = lam or {"modell": einlauf.VORGABE, "markt": einlauf.VORGABE}
    dv = daten["dividenden"]
    dv = dv[dv["bet_type"].eq(QUINTE)] if len(dv) else dv
    feld = daten["feld"]
    rng = np.random.default_rng(seed)
    zeilen = []
    for rid, z in dv.groupby("race_id") if len(dv) else []:
        g = feld[feld["race_id"] == rid].sort_values("p", ascending=False)
        if len(g) < 6:
            continue
        E = einlauf.einlaeufe(g["p"].to_numpy(), 5, lam["modell"], n_sim, rng)
        for name, ord_ in (("modell", g), ("markt", g.sort_values("odds"))):
            if name == "markt" and g["odds"].isna().any():
                continue
            reihe = [int(x) for x in ord_["no"].head(5)]
            idx = [int(np.flatnonzero(g["no"].to_numpy() == n)[0]) for n in reihe]
            p_zahlt = float((np.isin(E[:, :3], idx).all(1) | (np.isin(E, idx).sum(1) >= 4)).mean())
            st, d = _quinte_stufe(set(reihe), reihe, z)
            zeilen.append({"race_id": rid, "date": g["date"].iloc[0], "ticket": name, "pferde": "-".join(map(str, reihe)),
                           "stufe": st, "rueck": d, "einsatz": 1.0, "treffer": st is not None,
                           "p_modell": p_zahlt, "p_publikum": np.nan})
    T = pd.DataFrame(zeilen)
    if T.empty:
        return {"rennen": 0, "grund": "keine Quinté-Rennen mit Karte"}
    out = {"rennen": int(T["race_id"].nunique()), "tickets": T}
    for name, s in T.groupby("ticket"):
        a = _auswertung(s)
        a["stufen"] = {k: int((s["stufe"] == k).sum()) for k in QUINTE_STUFEN}
        out[name] = a
    return out


VORWAERTS_SPALTEN = ["date", "race_id", "art", "quelle", "a", "b", "p_modell", "p_publikum", "c", "ew", "settled",
                     "treffer", "div"]
C_MIN_RENNEN = 30          # ab so vielen früher abgerechneten Rennen wird c aus ihnen geschätzt


def _c_probe(P: pd.DataFrame, pool: str) -> float | None:
    """Auszahlungsfaktor eines abgerechneten Rennens: Couplé Placé Median Dividende × P_Publikum der Gewinnpaare,
    2sur4 Dividende × S ÷ Zahl der Gewinnpaare (S = Σ P_Publikum der Gewinnpaare)."""
    w = P[P["treffer"] & (P["div"] > 0)]
    if w.empty:
        return None
    if pool == "einzeln":
        return float(np.median(w["div"] * w["p_publikum"]))
    return float(w["div"].iloc[0] * w["p_publikum"].sum() / len(w))


def vorwaertstest(base: Path, ab: str | None = START_DATUM, bis: str | None = None, *, publikum: str = "fk",
                  n_sim: int = 10000, ew_min: float = 0.0, c_min_rennen: int = C_MIN_RENNEN, seed: int = 0,
                  log=print) -> pd.DataFrame:
    """Kombiwetten wie beim Wetten: unsere Chance nur aus dem Modell (quelle "modell") bzw. der Schattenversion mit
    Prognose-Schicht ("schatten", ab Karten mit sieg_schatten); Publikum = Preis, nicht Teil unserer Chance – Vorgabe
    die Festkurse Sieg der Karte (publikum="fk"), sonst der Toto-Stand der Karte ("toto"), nie die Endquote.
    Auszahlungsfaktor c je Tag als Median aus allen früher abgerechneten Rennen (mit derselben Publikumsquelle;
    unter c_min_rennen die Vorgabe KOMBI_C) – kein Tag nutzt seine eigenen Ergebnisse. Je Paar mit Erwartungswert ≥
    ew_min eine Zeile; abgerechnet gegen die PMU-Dividenden (settled = Wettart in diesem Rennen abgerechnet)."""
    if publikum not in ("fk", "toto"):
        raise ValueError("publikum: 'fk' oder 'toto'")
    lam = einlauf.laden(base)
    daten = daten_laden(base, ab, bis)
    feld, dv = daten["feld"], daten["dividenden"]
    sp_pub = "fk_karte" if publikum == "fk" else "toto_karte"
    if feld.empty or sp_pub not in feld:
        return pd.DataFrame(columns=VORWAERTS_SPALTEN)
    feld = feld.assign(odds=pd.to_numeric(feld[sp_pub], errors="coerce"))
    rng = np.random.default_rng(seed)
    teile = []
    for art, (code, plaetze, pool) in PAARE.items():
        d_ = dv[dv["bet_type"].eq(code)] if len(dv) else dv
        gew = ({(r, _paar_key(*c.split("-"))): d for r, c, d in zip(d_["race_id"], d_["combination"], d_["div"])}
               if len(d_) else {})
        abgerechnet = set(d_["race_id"]) if len(d_) else set()
        proben: list[tuple[str, float]] = []                 # (Tag, c) der abgerechneten Rennen
        for tag, ft in feld.groupby("date", sort=True):
            frueher = [c_ for t_, c_ in proben if t_ < tag]
            c = float(np.median(frueher)) if len(frueher) >= c_min_rennen else KOMBI_C[art]
            for rid, g in ft.groupby("race_id", sort=False):
                if len(g) <= plaetze or not np.all(g["odds"] > 1):
                    continue
                for quelle, sp in (("modell", "p"), ("schatten", "p_sh")):
                    if not np.all(g[sp] > 0):
                        continue
                    P = _paare_rennen(g.assign(p=g[sp]), plaetze, lam["modell"], lam["markt"], n_sim, rng)
                    k = [gew.get((rid, _paar_key(a, b))) for a, b in zip(P["a"], P["b"])]
                    P = P.assign(art=art, quelle=quelle, settled=rid in abgerechnet, c=c,
                                 treffer=[x is not None for x in k], div=[x if x is not None else 0.0 for x in k])
                    if quelle == "modell" and rid in abgerechnet:
                        probe = _c_probe(P, pool)
                        if probe is not None:
                            proben.append((tag, probe))
                    P["ew"] = (P["p_modell"] * c / P["p_publikum"] - 1 if pool == "einzeln"
                               else c * len(a_paare(plaetze)) * P["kehr_s"] - 1)
                    P = P[P["ew"] >= ew_min]
                    if len(P):
                        teile.append(P)
    out = pd.concat(teile, ignore_index=True)[VORWAERTS_SPALTEN] if teile else pd.DataFrame(columns=VORWAERTS_SPALTEN)
    n_ab = out.loc[out["settled"], "race_id"].nunique() if len(out) else 0
    log(f"Kombiwetten (Vorwärtstest, Publikum = {'Festkurse' if publikum == 'fk' else 'Toto-Stand'} der Karte): "
        f"{len(out)} Paare mit Erwartungswert ≥ {ew_min:g}, {n_ab} Rennen abgerechnet")
    return out


def rueckrechnung(base: Path, ab: str | None = START_DATUM, bis: str | None = None, *, n_sim: int = N_SIM,
                  schwellen=(0.0, 0.2, 0.5), publikum: str = "endquote", log=print) -> dict:
    """Alle Karten im Zeitraum: Couplé Placé, 2sur4 (Paare mit Erwartungswert ≥ Schwelle) und Quinté+ gegen die
    echten Dividenden; Bericht mit Eichung, Auszahlungsfaktor, Kapazität und ROI mit 90-%-Intervall. publikum:
    Sicht des Publikums aus der Toto-Endquote ("endquote"), den Festkursen der Karte ("fk") oder dem Toto-Stand der
    Karte ("toto")."""
    lam = einlauf.laden(base)
    daten = daten_laden(base, ab, bis)
    if publikum in ("fk", "toto") and len(daten["feld"]):
        daten["feld"]["odds"] = pd.to_numeric(daten["feld"]["fk_karte" if publikum == "fk" else "toto_karte"], errors="coerce")
    log(f"Publikum aus: {dict(endquote='Toto-Endquote', fk='Festkursen der Karte', toto='Toto-Stand der Karte')[publikum]}")
    log(f"Karten: {len(daten['tage'])} Tage, {daten['feld']['race_id'].nunique() if len(daten['feld']) else 0} Rennen; "
        f"λ Modell {lam['modell'][1:]}, Markt {lam['markt'][1:]}")
    out = {}
    for art in PAARE:
        r = paarwetten(daten, art, schwellen, lam, n_sim)
        out[art] = r
        if not r.get("rennen"):
            log(f"\n{art}: {r.get('grund')}")
            continue
        log(f"\n{art} ({r['pmu_code']}, beide unter den ersten {r['plaetze']}, Pool {r['pool']}): {r['rennen']} Rennen, {r['paare']} Paare, "
            f"Auszahlungsfaktor c ≈ {r['auszahlungsfaktor_c']}, Ø Einsatz auf der Gewinnkombination (Median) "
            f"{r['einsatz_auf_gewinnkombi_median']} €")
        log("  Eichung (Treffer gegen erwartet):")
        log(pd.DataFrame(r["eichung"]).to_string(index=False))
        log("  Tickets je Schwelle (1 € je Paar mit Erwartungswert ≥ Schwelle):")
        log(pd.DataFrame({"alle Paare": r["alle_paare"], **r["je_schwelle"]}).T.to_string())
    q = quinte(daten, lam, n_sim)
    out["quinte"] = q
    if q.get("rennen"):
        log(f"\nQuinté+: {q['rennen']} Rennen, je ein Ticket (5 Pferde, 1 €)")
        log(pd.DataFrame({k: v for k, v in q.items() if k in ("modell", "markt")}).T.to_string())
    else:
        log(f"\nQuinté+: {q.get('grund')}")
    return out


# ---------------------------------------------------------------------------------------------------------------
# Kombiwetten im Value-Dashboard: Vollkombi aller Pferde, die sich für Kombiwetten qualifizieren (Filter im Browser,
# Vorgabe Wert > 0), 1 € je Kombination. Hier je Rennen die Dividenden und die Chancen jeder Kombination der
# Kandidaten (Pferde mit Wert ≥ 0) aus gezogenen Einläufen – Modell (faire Chance der Karte bzw. Schattenversion,
# Modell-λ) und Festkurs (1/FK der Karte normiert, Markt-λ) für „erwartet Modell“ und „erwartet Festkurs“.
DASH_ARTEN = {                  # Schlüssel: (PMU-Code, Pferde je Kombination, Reihenfolge zählt, unter den ersten …)
    "dreier": ("TRIO_ORDRE", 3, True, 3),           # die ersten drei in richtiger Reihenfolge
    "zwilling": ("COUPLE_GAGNANT", 2, False, 2),    # die ersten zwei, Reihenfolge egal
    "drilling": ("TRIO", 3, False, 3),              # die ersten drei, Reihenfolge egal
    "platzzwilling": ("COUPLE_PLACE", 2, False, 3), # zwei unter den ersten drei
    "2sur4": ("DEUX_SUR_QUATRE", 2, False, 4),      # zwei unter den ersten vier
}
DASH_MAX_KANDIDATEN = 8         # je Rennen höchstens so viele Kandidaten (höchster Wert zuerst)
DASH_N_SIM = 10000


def kombi_schluessel(nos, ordnung: bool) -> str:
    """Kombination als Text wie in den Dividenden: Reihenfolge zählt → wie gegeben, sonst aufsteigend."""
    z = [int(x) for x in nos]
    return "-".join(map(str, z if ordnung else sorted(z)))


def _zaehlen(codes: np.ndarray, n_sim: int) -> dict[int, float]:
    u, c = np.unique(codes, return_counts=True)
    return dict(zip(u.tolist(), (c / n_sim).tolist()))


def kombi_chancen(E: np.ndarray, nos: np.ndarray, kand: np.ndarray, stellen: int = 5) -> dict[str, dict[str, float]]:
    """Aus gezogenen Einläufen E (Indizes der Starter auf Platz 1 …, mindestens 4 Plätze) je Wettart die Chance jeder
    Kombination, deren Pferde alle Kandidaten sind (kand: bool je Starter); Kombinationen ohne Treffer fehlen."""
    n_sim, n = E.shape[0], len(nos)
    ist = kand[E]
    out = {}
    for art, (_, k, ordnung, plaetze) in DASH_ARTEN.items():
        if E.shape[1] < plaetze:
            out[art] = {}
            continue
        if k == plaetze:                                     # Dreier, Zwilling, Drilling: genau die ersten k
            sel = E[:, :k] if ordnung else np.sort(E[:, :k], axis=1)
            ok = ist[:, :k].all(axis=1)
            code = sel[ok] @ (n ** np.arange(k - 1, -1, -1))
        else:                                                # zwei unter den ersten 3 bzw. 4
            teile = []
            for a, b in a_paare(plaetze):
                ok = ist[:, a] & ist[:, b]
                lo, hi = np.minimum(E[ok, a], E[ok, b]), np.maximum(E[ok, a], E[ok, b])
                teile.append(lo * n + hi)
            code = np.concatenate(teile) if teile else np.empty(0, int)
        ch = _zaehlen(code, n_sim)
        d = {}
        for c, p in ch.items():
            idx = [(c // n ** i) % n for i in range(k - 1, -1, -1)]
            d[kombi_schluessel(nos[idx], ordnung)] = round(p, stellen)
        out[art] = d
    return out


def dashboard_daten(base: Path, pool: pd.DataFrame, ab: str | None = START_DATUM, *, n_sim: int = DASH_N_SIM,
                    seed: int = 0, log=print) -> dict:
    """Je Rennen mit Karte: Dividenden der fünf Wettarten (NATIONAL, ohne NP/Rückzahlung; fehlt die Wettart, wurde
    sie nicht angeboten oder ist noch nicht abgerechnet) und je faire Quote ("karte", "schatten") die Kandidaten
    (Wert ≥ 0 gegen den Festkurs, aus dem Pool des Dashboards) mit den Chancen ihrer Kombinationen nach Modell ("m")
    sowie nach Festkurs ("f", nur wenn alle Starter einen Festkurs haben)."""
    lam = einlauf.laden(base)
    daten = daten_laden(base, ab)
    feld, dv = daten["feld"], daten["dividenden"]
    out = {"arten": {a: {"code": c, "pferde": k, "ordnung": o, "plaetze": p} for a, (c, k, o, p) in DASH_ARTEN.items()},
           "rennen": {}}
    if feld.empty or pool is None or pool.empty:
        return out
    div: dict[str, dict[str, list]] = {}
    codes = {c: a for a, (c, *_r) in DASH_ARTEN.items()}
    if len(dv):
        for rid, typ, komb, d in zip(dv["race_id"], dv["bet_type"], dv["combination"], dv["div"]):
            art = codes.get(typ)
            if art is None or pd.isna(d) or not re.fullmatch(r"\d+(-\d+)+", str(komb)):
                continue
            key = kombi_schluessel(str(komb).split("-"), DASH_ARTEN[art][2])
            liste = div.setdefault(str(rid), {}).setdefault(art, [])
            if key not in {x[0] for x in liste}:
                liste.append([key, float(d)])
    werte = pool.assign(race_id=pool["race_id"].astype(str)).set_index(["race_id", "no"])
    rng = np.random.default_rng(seed)
    n_r = 0
    for rid, g in feld.groupby("race_id", sort=False):
        g = g.reset_index(drop=True)
        if len(g) < 4:
            continue
        nos = g["no"].to_numpy(int)
        r_out: dict = {"div": div.get(str(rid), {}), "c": {}}
        alle = np.zeros(len(g), bool)
        for chance, sp, spw in (("karte", "p", "wert"), ("schatten", "p_sh", "wert_sh")):
            if not np.all(g[sp] > 0) or spw not in werte:
                continue
            w = np.array([werte[spw].get((str(rid), int(no)), np.nan) for no in nos], float)
            ok = np.where(np.isfinite(w) & (w >= -1e-9))[0]
            if len(ok) < 2:
                continue
            ok = ok[np.argsort(-w[ok], kind="stable")][:DASH_MAX_KANDIDATEN]
            kand = np.zeros(len(g), bool)
            kand[ok] = True
            alle |= kand
            E = einlauf.einlaeufe(g[sp].to_numpy(float), 4, lam["modell"], n_sim, rng)
            r_out["c"][chance] = {"no": sorted(nos[ok].tolist()), "m": kombi_chancen(E, nos, kand)}
        if not r_out["c"]:
            continue
        fk = pd.to_numeric(g["fk_karte"], errors="coerce").to_numpy(float)
        if np.all(fk > 1):
            q = (1 / fk) / np.sum(1 / fk)
            E = einlauf.einlaeufe(q, 4, lam["markt"], n_sim, rng)
            r_out["f"] = kombi_chancen(E, nos, alle)
        out["rennen"][str(rid)] = r_out
        n_r += 1
    n_div = sum(1 for r in out["rennen"].values() if r["div"])
    log(f"Kombiwetten (Dashboard): {n_r} Rennen mit Kandidaten, davon {n_div} mit Dividenden; "
        f"Wettarten in den Dividenden: {', '.join(a for a in DASH_ARTEN if any(a in r['div'] for r in out['rennen'].values())) or 'keine'}")
    return out
