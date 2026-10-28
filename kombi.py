"""Kombiwetten aus den Siegchancen der Karte: Couplé Placé, 2sur4 und Quinté+ – Wahrscheinlichkeiten aus dem
Einlauf-Modell (einlauf.py) und Rückrechnung gegen die echten PMU-Dividenden (NATIONAL-Pool).

    import kombi
    r = kombi.rueckrechnung(BASE)          # alle gespeicherten Karten ab START_DATUM: Bericht je Wettart

Je Rennen das ganze Feld aus racecard_JJJJMMTT_daten.json (Modell: faire Siegchance der Karte; Karten mit
Morgenquote: sieg_blind), die Toto-Endquote aus pmu_runners (Sicht des Publikums) und die Dividenden aus
pmu_dividends. Gewonnen hat eine Kombination, wenn die PMU sie in den Dividenden listet (Zeilen „NP“ und
Rückzahlungen bleiben weg). Gezogene Einläufe: Modell mit den Modell-λ, Publikum mit den Markt-λ.

Paarwetten (Couplé Placé: beide unter den ersten 3; 2sur4: beide unter den ersten 4): erwartete Dividende ≈
c ÷ P_Publikum(Paar), c = Auszahlungsfaktor der Wettart (aus den Gewinnpaaren geschätzt, ≈ 1 − Abzug); Erwartungswert
je 1 € = P_Modell × c ÷ P_Publikum − 1. Gewettet wird je Paar mit Erwartungswert ≥ Schwelle, 1 € je Ticket.
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
PAARE = {"couple_place": ("COUPLE_PLACE", 3), "2sur4": ("DEUX_SUR_QUATRE", 4)}   # Wettart: (PMU-Code, Plätze)
QUINTE = "QUINTE_PLUS"
QUINTE_STUFEN = ("ordre", "desordre", "bonus4sur5", "bonus3")
N_SIM = 20000


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
        for x, pi in zip(st, p / p.sum()):
            zeilen.append({"date": tag, "race_id": str(r.get("race_id")), "no": int(x["no"]), "horse": x.get("horse"),
                           "p": float(pi)})
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
    """Alle Paare eines Rennens mit P_Modell und P_Publikum (aus der Toto-Endquote; ohne Quote: NaN)."""
    nos = g["no"].to_numpy()
    Pm = paar_chancen(g["p"].to_numpy(), plaetze, lam_m, n_sim, rng)
    q = g["odds"].to_numpy(float)
    Pp = paar_chancen((1 / q) / np.nansum(1 / q), plaetze, lam_p, n_sim, rng) if np.all(q > 1) else np.full_like(Pm, np.nan)
    i, j = np.triu_indices(len(nos), 1)
    return pd.DataFrame({"race_id": g["race_id"].iloc[0], "date": g["date"].iloc[0], "a": nos[i], "b": nos[j],
                         "p_modell": Pm[i, j], "p_publikum": Pp[i, j]})


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
    code, plaetze = PAARE[art]
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
    # Auszahlungsfaktor c: Dividende × P_Publikum der Gewinnpaare (Median) – ≈ 1 − Abzug
    w = P[P["treffer"] & (P["div"] > 0)]
    c = float(np.median(w["div"] * w["p_publikum"])) if len(w) else np.nan
    P["ew"] = P["p_modell"] * c / P["p_publikum"] - 1
    P["einsatz"], P["rueck"] = 1.0, P["div"]
    out = {"art": art, "pmu_code": code, "plaetze": plaetze, "rennen": int(P["race_id"].nunique()),
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


def rueckrechnung(base: Path, ab: str | None = START_DATUM, bis: str | None = None, *, n_sim: int = N_SIM,
                  schwellen=(0.0, 0.2, 0.5), log=print) -> dict:
    """Alle Karten im Zeitraum: Couplé Placé, 2sur4 (Paare mit Erwartungswert ≥ Schwelle) und Quinté+ gegen die
    echten Dividenden; Bericht mit Eichung, Auszahlungsfaktor, Kapazität und ROI mit 90-%-Intervall."""
    lam = einlauf.laden(base)
    daten = daten_laden(base, ab, bis)
    log(f"Karten: {len(daten['tage'])} Tage, {daten['feld']['race_id'].nunique() if len(daten['feld']) else 0} Rennen; "
        f"λ Modell {lam['modell'][1:]}, Markt {lam['markt'][1:]}")
    out = {}
    for art in PAARE:
        r = paarwetten(daten, art, schwellen, lam, n_sim)
        out[art] = r
        if not r.get("rennen"):
            log(f"\n{art}: {r.get('grund')}")
            continue
        log(f"\n{art} ({r['pmu_code']}, beide unter den ersten {r['plaetze']}): {r['rennen']} Rennen, {r['paare']} Paare, "
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
