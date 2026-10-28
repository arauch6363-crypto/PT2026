"""Einlauf-Modell: aus Siegchancen die Wahrscheinlichkeit jeder Reihenfolge – Grundlage für Platzchance und
Kombiwetten (Couplé Placé, 2sur4, Quinté+).

Der Einlauf entsteht Platz für Platz: Platz k gewinnt unter den noch übrigen Pferden das Pferd i mit Chance
∝ p_i^λ_k (λ_1 = 1: die Siegchance selbst). λ_k = 1 ist das reine Harville-Modell, das Favoriten auf den hinteren
Plätzen überschätzt; λ_k < 1 rückt die Chancen dort zusammen (Henery / Lo–Bacon-Shone). λ_2 … λ_5 werden aus echten
Einläufen per Maximum-Likelihood geschätzt – für die Modellchancen (power_oos.parquet: gelernt auf der Validierung,
geprüft auf dem Test) und für den Markt (Endquoten der Historie: gelernt auf allen Tagen bis zum letzten Jahr,
geprüft auf dem letzten Jahr).

    import einlauf
    e = einlauf.aus_historie(BASE)            # schätzt beide, Bericht, speichert modelle/einlauf_lambda.json
    einlauf.laden(BASE)                       # {"modell": [1, λ2, …, λ5], "markt": […]} (ohne Datei: Vorgabe)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

STUFEN = 5                         # Plätze 1–5 (Quinté+)
VORGABE = [1.0, 0.8, 0.65, 0.65, 0.65]   # bisherige feste Werte (Lo / Bacon-Shone), ohne geschätzte Datei
DATEI = "einlauf_lambda.json"
PLATZ_GRENZE = 7                   # bis 7 Starter: Platz = 1.–2., sonst 1.–3. (wie racecard.PLATZ_GRENZE)


def _stufe(d: pd.DataFrame, k: int) -> pd.DataFrame:
    """Zeilen für Platz k: alle Pferde, die noch nicht auf Platz 1 … k−1 sind, in Rennen mit genau einem Pferd auf
    jedem Platz 1 … k (kein totes Rennen) und mehr als k Startern; w = 1 beim Pferd auf Platz k."""
    pos = d["pos"]
    je = d.assign(_v=pos.le(k), _g=pos.eq(k)).groupby("race_id")
    ok = (je["_v"].transform("sum") == k) & (je["_g"].transform("sum") == 1) & (je["pos"].transform("size") > k)
    for j in range(1, k):
        ok &= d.assign(_e=pos.eq(j)).groupby("race_id")["_e"].transform("sum") == 1
    s = d[ok & ~pos.lt(k)]
    return s.assign(w=s["pos"].eq(k).astype(float))


def _lambda_mle(s: pd.DataFrame, iter_max: int = 50) -> float:
    """λ einer Stufe: maximiert Σ_Rennen [λ · log p_Sieger − log Σ_übrig p^λ] (Newton; konkav in λ)."""
    lp = np.log(np.clip(s["p"].to_numpy(float), 1e-9, 1))
    g = pd.factorize(s["race_id"].to_numpy())[0]
    w = s["w"].to_numpy()
    lam = 1.0
    for _ in range(iter_max):
        e = np.exp(lam * lp - np.maximum.reduceat(lam * lp, np.r_[0, np.flatnonzero(np.diff(g)) + 1])[g])
        sm = np.bincount(g, e)
        q = e / sm[g]
        m1 = np.bincount(g, q * lp)
        m2 = np.bincount(g, q * lp * lp)
        grad = float((w * lp).sum() - m1.sum())
        hess = -float((m2 - m1 ** 2).sum())
        if hess >= 0:
            break
        schritt = grad / hess
        lam = float(np.clip(lam - schritt, 0.05, 3.0))
        if abs(schritt) < 1e-8:
            break
    return lam


def _loglik(s: pd.DataFrame, lam: float) -> float:
    """Ø −log Wahrscheinlichkeit des Pferdes auf Platz k (je Rennen) bei Exponent lam."""
    lp = np.log(np.clip(s["p"].to_numpy(float), 1e-9, 1))
    g = pd.factorize(s["race_id"].to_numpy())[0]
    z = lam * lp
    zmax = np.zeros(g.max() + 1)
    np.maximum.at(zmax, g, z)
    lse = np.log(np.bincount(g, np.exp(z - zmax[g]))) + zmax
    return float(-(z[s["w"].to_numpy() == 1] - lse).mean())


def _vorbereiten(d: pd.DataFrame) -> pd.DataFrame:
    d = d[["race_id", "p", "pos"] + [c for c in ("date",) if c in d]].copy()
    d["race_id"] = d["race_id"].astype(str)
    d["p"] = pd.to_numeric(d["p"], errors="coerce")
    d["pos"] = pd.to_numeric(d["pos"], errors="coerce")
    d.loc[d["pos"] <= 0, "pos"] = np.nan
    d = d[d["p"] > 0]
    d["p"] = d["p"] / d.groupby("race_id")["p"].transform("sum")
    return d.sort_values("race_id", kind="stable").reset_index(drop=True)


def platz_chance(p, plaetze: int, lam=None, n_sim: int = 0, rng=None) -> np.ndarray:
    """Chance je Starter, unter die ersten `plaetze` zu kommen, aus Siegchancen p und Exponenten lam (Liste ab λ_1).
    Bis 3 Plätze exakt (Summe über alle Reihenfolgen), sonst per Simulation (einlaeufe)."""
    lam = list(lam or VORGABE)
    p = np.asarray(p, float)
    p = p / p.sum()
    n = len(p)
    if plaetze >= n:
        return np.ones(n)
    if plaetze > 3:
        E = einlaeufe(p, plaetze, lam, n_sim or 20000, rng)
        return np.bincount(E.ravel(), minlength=n) / len(E)
    q = [None] + [p ** lam[k] / (p ** lam[k]).sum() for k in range(1, 3)]
    out = p.copy()                                         # Platz 1
    if plaetze >= 2:                                       # Platz 2: Σ_j P(j Erster) · q2_i / (1 − q2_j)
        A = p[:, None] * q[1][None, :] / np.clip(1 - q[1][:, None], 1e-12, None)
        np.fill_diagonal(A, 0.0)
        out = out + A.sum(axis=0)
    if plaetze >= 3:                                       # Platz 3: Σ_{j,k} P(j, k) · q3_i / (1 − q3_j − q3_k)
        nenner = 1 - q[2][:, None] - q[2][None, :]
        B = np.where(nenner > 1e-12, A / np.where(nenner > 1e-12, nenner, 1.0), 0.0)
        np.fill_diagonal(B, 0.0)
        out = out + q[2] * (B.sum() - B.sum(axis=1) - B.sum(axis=0))
    return np.clip(out, 0.0, 1.0)


def einlaeufe(p, plaetze: int = STUFEN, lam=None, n_sim: int = 20000, rng=None) -> np.ndarray:
    """n_sim gezogene Einläufe (Indizes der Starter auf Platz 1 … plaetze) aus Siegchancen p und Exponenten lam."""
    rng = np.random.default_rng(rng)
    p = np.asarray(p, float)
    p = p / p.sum()
    n, k_max = len(p), min(plaetze, len(p))
    lam = list(lam or VORGABE)
    lam = lam + [lam[-1]] * max(0, k_max - len(lam))        # hinter Platz 5: letzter Exponent
    lp = np.log(np.clip(p, 1e-12, 1))
    frei = np.ones((n_sim, n), bool)
    out = np.empty((n_sim, k_max), int)
    for k in range(k_max):
        g = np.where(frei, np.exp(lam[k] * lp)[None, :], 0.0)
        c = g.cumsum(axis=1)
        u = rng.random(n_sim) * c[:, -1]
        wahl = (c < u[:, None]).sum(axis=1)
        out[:, k] = wahl
        frei[np.arange(n_sim), wahl] = False
    return out


def lambda_schaetzen(lern: pd.DataFrame, pruef: pd.DataFrame | None = None, stufen: int = STUFEN) -> dict:
    """λ_2 … λ_stufen aus Einläufen (Spalten race_id, p = Siegchance, pos = Platz; p wird je Rennen auf 1 normiert)
    per Maximum-Likelihood auf `lern`; auf `pruef` (falls da) der Ø Log-Loss je Stufe für Harville (λ = 1), die
    bisherigen festen Werte und die geschätzten sowie die Eichung der Platzchance (Plätze erwartet gegen echt)."""
    L, P = _vorbereiten(lern), _vorbereiten(pruef) if pruef is not None else None
    lam, je_stufe = [1.0], []
    for k in range(2, stufen + 1):
        s = _stufe(L, k)
        if s["race_id"].nunique() < 50:
            lam.append(VORGABE[min(k, len(VORGABE)) - 1])
            je_stufe.append({"platz": k, "rennen_lern": int(s["race_id"].nunique()), "lambda": lam[-1], "grund": "zu wenige Rennen"})
            continue
        lam.append(round(_lambda_mle(s), 4))
        z = {"platz": k, "rennen_lern": int(s["race_id"].nunique()), "lambda": lam[-1]}
        if P is not None:
            t = _stufe(P, k)
            if t["race_id"].nunique():
                z.update({"rennen_pruef": int(t["race_id"].nunique()),
                          "logloss_harville": round(_loglik(t, 1.0), 4),
                          "logloss_vorgabe": round(_loglik(t, VORGABE[min(k, len(VORGABE)) - 1]), 4),
                          "logloss_geschaetzt": round(_loglik(t, lam[-1]), 4)})
        je_stufe.append(z)
    out = {"lambda": lam, "je_stufe": je_stufe}
    if P is not None:
        out["platz_eichung"] = platz_eichung(P, lam)
    return out


def platz_eichung(d: pd.DataFrame, lam, gruppen=(0, 0.1, 0.2, 0.35, 1.01)) -> list[dict]:
    """Plätze erwartet (Harville, bisherige Vorgabe, geschätzte λ) gegen echt, je Gruppe der Siegchance – zeigt, wo
    die Platzchance zu optimistisch ist (Platz = 1.–2. bis PLATZ_GRENZE Starter, sonst 1.–3.)."""
    d = _vorbereiten(d)
    d = d[d.groupby("race_id")["pos"].transform(lambda s_: s_.notna().any())]
    zeilen = []
    for rid, g in d.groupby("race_id", sort=False):
        k = 2 if len(g) <= PLATZ_GRENZE else 3
        p = g["p"].to_numpy()
        zeilen.append(pd.DataFrame({"p": p, "echt": (g["pos"] <= k).to_numpy(float),
                                    "harville": platz_chance(p, k, [1.0] * STUFEN),
                                    "vorgabe": platz_chance(p, k, VORGABE),
                                    "geschaetzt": platz_chance(p, k, lam)}))
    if not zeilen:
        return []
    a = pd.concat(zeilen, ignore_index=True)
    a["gruppe"] = pd.cut(a["p"], list(gruppen), right=False)
    out = []
    for name, s in [("alle", a)] + [(str(b), s) for b, s in a.groupby("gruppe", observed=True)]:
        out.append({"siegchance": name, "starter": int(len(s)), "plaetze_echt": int(s["echt"].sum()),
                    **{f"erwartet_{m}": round(float(s[m].sum()), 1) for m in ("harville", "vorgabe", "geschaetzt")}})
    return out


def aus_historie(base: Path, hist: pd.DataFrame | None = None, *, speichern: bool = True, log=print) -> dict:
    """λ für Modell und Markt schätzen, berichten und (speichern=True) nach BASE/modelle/einlauf_lambda.json schreiben.
    Modell: faire Siegchance außerhalb der Lerndaten (power_oos.parquet, von power_modell.trainieren) – gelernt auf
    der Validierung, geprüft auf dem Test. Markt: Endquoten aller PMU-Rennen – gelernt bis vor einem Jahr, geprüft
    auf dem letzten Jahr."""
    import power_modell as pm
    import regel_backtest as rb
    base = Path(base)
    if hist is None:
        log("Historie laden …")
        hist = rb.laden(base)
    h = hist[~hist["extern"].eq(True)] if "extern" in hist else hist
    pos = pd.to_numeric(h["finish_pos"], errors="coerce")
    bericht = {}
    oos_pfad = base / pm.MODELL_ORDNER / pm.OOS_DATEI
    if oos_pfad.exists():
        o = pd.read_parquet(oos_pfad)
        e = h[["race_id", "horse_id"]].astype(str).assign(pos=pos.to_numpy())
        o = o.astype({"race_id": str, "horse_id": str}).merge(e.drop_duplicates(["race_id", "horse_id"]),
                                                              on=["race_id", "horse_id"], how="left")
        o = o.rename(columns={"p_fair": "p"})
        bericht["modell"] = lambda_schaetzen(o[o["teil"] == "valid"], o[o["teil"] == "test"])
    else:
        log(f"  {oos_pfad} fehlt – zuerst power_modell.trainieren; Modell-λ bleibt bei der Vorgabe")
    q = pd.to_numeric(h["odds_final"], errors="coerce")
    m = pd.DataFrame({"race_id": h["race_id"].astype(str).to_numpy(), "p": (1 / q.where(q > 1)).to_numpy(),
                      "pos": pos.to_numpy(), "date": pd.to_datetime(h["date"]).to_numpy()})
    m = m[m.groupby("race_id")["p"].transform(lambda s_: s_.notna().all())]
    grenze = m["date"].max() - pd.Timedelta(days=365)
    bericht["markt"] = lambda_schaetzen(m[m["date"] < grenze], m[m["date"] >= grenze])
    for quelle, b in bericht.items():
        log(f"\n{quelle.capitalize()}: λ = " + ", ".join(f"Platz {i + 1}: {v:g}" for i, v in enumerate(b["lambda"])))
        log(pd.DataFrame(b["je_stufe"]).to_string(index=False))
        if b.get("platz_eichung"):
            log("  Platzchance – Plätze erwartet gegen echt (Prüfteil):")
            log(pd.DataFrame(b["platz_eichung"]).to_string(index=False))
    out = {q_: b["lambda"] for q_, b in bericht.items()}
    out.update({"bericht": bericht, "geschaetzt": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")})
    if speichern:
        pfad = base / pm.MODELL_ORDNER / DATEI
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        log(f"\nGespeichert: {pfad}")
    return out


def laden(base: Path | None) -> dict:
    """Geschätzte λ ({"modell": [...], "markt": [...]}); fehlt die Datei oder eine Quelle: VORGABE."""
    out = {"modell": list(VORGABE), "markt": list(VORGABE), "geschaetzt": None}
    if base is None:
        return out
    pfad = Path(base) / "modelle" / DATEI
    if pfad.exists():
        d = json.loads(pfad.read_text(encoding="utf-8"))
        out.update({k: d[k] for k in ("modell", "markt", "geschaetzt") if d.get(k)})
    return out
