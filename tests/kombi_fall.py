"""Simulierte Karten, Toto-Endquoten und PMU-Dividenden für den Selbsttest der Kombiwetten (kombi.py)."""
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

import einlauf as el
import kombi as kb


def _zeile(rid, typ, label, comb, div, winners, base_stake):
    return {"race_id": rid, "bet_type": typ, "audience": "NATIONAL", "refunded": False, "label": label,
            "combination": comb, "dividend_eur_per_1eur": div, "winners": winners, "base_stake": base_stake}


def bauen(base: Path, tage: int = 6, rennen: int = 8, seed: int = 0) -> None:
    """Je Tag eine Karte (racecard_JJJJMMTT_daten.json), pmu_runners (Toto-Endquote) und pmu_dividends: Einlauf aus
    der wahren Chance, Dividende Couplé Placé = 0,75 ÷ Publikums-Chance des Paars, 2sur4 = 0,70 × 6 ÷ Σ Publikums-
    Chance der 6 Gewinnpaare (ein Topf);
    je Rennen eine NP-Zeile (muss ignoriert werden), Rennen 4 jedes Tages ist das Quinté-Rennen."""
    rng = np.random.default_rng(seed)
    lam = [1.0, 0.85, 0.8, 0.7, 0.67]
    (base / "racecards").mkdir(parents=True)
    for t in ("pmu_runners", "pmu_dividends"):
        (base / "parquet" / t).mkdir(parents=True)
    for d in range(tage):
        tag = f"202610{18 + d:02d}"
        races, ru, dv = {}, [], []
        for c in range(1, rennen + 1):
            rid, n = f"{tag}R1C{c}", int(rng.integers(9, 15))
            wahr = rng.dirichlet(np.ones(n) * 0.9)
            modell = wahr ** 0.9 / (wahr ** 0.9).sum()
            publik = wahr * np.exp(rng.normal(0, 0.35, n))
            publik /= publik.sum()
            karte = publik * np.exp(rng.normal(0, 0.1, n))      # Toto-Stand der Karte: etwas neben der Endquote
            sh = modell * np.exp(rng.normal(0, 0.1, n)) if d % 2 else [None] * n   # Schattenversion jeden zweiten Tag
            races[rid] = {"race_id": rid, "reunion": 1, "race_no": c, "runners": [
                {"no": i + 1, "horse": f"H{i}", "nr": False,
                 "power": {"sieg": float(m), "sieg_schatten": None if s_ is None else float(s_)},
                 "fk": {"toto": round(float(0.85 / karte[i] * karte.sum()), 2),
                        "sieg": round(float(0.8 / (publik[i] * np.exp(rng.normal(0, 0.15)))), 1)}}
                for i, (m, s_) in enumerate(zip(modell, sh))]}
            ru += [{"race_id": rid, "saddle_no": i + 1, "odds_final": float(0.85 / publik[i])} for i in range(n)]
            E = el.einlaeufe(wahr, 5, lam, 1, rng)[0] + 1
            Pp, Pq = kb.paar_chancen(publik, 3, lam, 4000, rng), kb.paar_chancen(publik, 4, lam, 4000, rng)
            dv += [_zeile(rid, "COUPLE_PLACE", "Couplé placé", f"{a}-{b}", round(0.75 / max(Pp[a - 1, b - 1], 1e-3), 1), 100.0, 200)
                   for a, b in itertools.combinations(E[:3], 2)]
            paare4 = list(itertools.combinations(E[:4], 2))       # 2sur4: ein Topf, gleiche Dividende für alle 6
            d4 = round(0.7 * 6 / sum(Pq[a - 1, b - 1] for a, b in paare4), 1)
            dv += [_zeile(rid, "DEUX_SUR_QUATRE", "2sur4", f"{a}-{b}", d4, 300.0, 300) for a, b in paare4]
            dv.append(_zeile(rid, "COUPLE_PLACE", "Couplé Placé 1 NP", "1-NP", 2.0, 1.0, 200))
            if c == 4:
                arr = "-".join(map(str, E[:5]))
                dv += [_zeile(rid, "QUINTE_PLUS", "Quinté+ Ordre", arr, 5000.0, 10.0, 200),
                       _zeile(rid, "QUINTE_PLUS", "Quinté+ Désordre", arr, 100.0, 10.0, 200),
                       _zeile(rid, "QUINTE_PLUS", "Bonus 3", "-".join(map(str, E[:3])), 5.0, 10.0, 200)]
                dv += [_zeile(rid, "QUINTE_PLUS", "Bonus 4sur5", "-".join(map(str, s)), 12.0, 10.0, 200)
                       for s in itertools.combinations(E[:5], 4)]
        (base / "racecards" / f"racecard_{tag}_daten.json").write_text(json.dumps({"date": tag, "races": races}))
        pd.DataFrame(ru).to_parquet(base / "parquet" / "pmu_runners" / f"{tag}.parquet")
        pd.DataFrame(dv).to_parquet(base / "parquet" / "pmu_dividends" / f"{tag}.parquet")
