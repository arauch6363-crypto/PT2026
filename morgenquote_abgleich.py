"""Abgleich: Morgenquoten der gespeicherten Karten (racecard_JJJJMMTT_daten.json) gegen die PMU-Tagesdaten.

    import morgenquote_abgleich as mq
    erg = mq.run(BASE)                 # letzte 7 Tage mit Ergebnissen
    erg = mq.run(BASE, tage=14)

Je Starter werden aus der Karte gelesen:
    prono_cote  – PMU-Prognose „cote probable“ (x["prono"]["sel"]["cote_dec"]), steht am Morgen fest
    fk_sieg     – Wettstar-Festkurs Sieg zum Zeitpunkt der Karte (x["fk"]["sieg"])
    fk_toto     – Wettstar-Toto zum Zeitpunkt der Karte (x["fk"]["toto"])
und mit pmu_runners verglichen:
    odds_morning – PMU dernierRapportReference (Referenz-/Morgenkurs, nach dem Rennen geholt)
    odds_final   – PMU-Endquote (dernierRapportDirect)

Ausgabe je Quelle und Tag: Abdeckung, Anteil gleich (±0,05), Anteil innerhalb ±10 % / ±25 %, mittlere absolute
Log-Abweichung, Rangkorrelation (Spearman) und welcher PMU-Kurs näher liegt (Morgen oder End).
Reine Auswertung: nichts davon fließt ins Modell.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

QUELLEN = {"prono_cote": "PMU-Prognose (cote probable)", "fk_sieg": "Festkurs Sieg (Wettstar)",
           "fk_toto": "Toto zur Kartenzeit (Wettstar)"}


def _zahl(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return np.nan
    return v if np.isfinite(v) and v > 1.0 else np.nan


def karte_lesen(pfad: Path) -> pd.DataFrame:
    """Je Starter der Karte: race_id, saddle_no, horse, nr und die Kurse aus QUELLEN."""
    d = json.loads(Path(pfad).read_text(encoding="utf-8"))
    out = []
    for rid, r in (d.get("races") or {}).items():
        for x in r.get("runners") or []:
            sel = (x.get("prono") or {}).get("sel") or {}
            fk = x.get("fk") or {}
            out.append({"race_id": str(r.get("race_id") or rid), "saddle_no": x.get("no"), "horse": x.get("horse"),
                        "nr": bool(x.get("nr")), "prono_cote": _zahl(sel.get("cote_dec")),
                        "fk_sieg": _zahl(fk.get("sieg")), "fk_toto": _zahl(fk.get("toto")),
                        "karte_odds_morning": _zahl(x.get("odds_morning"))})   # alte Karten (< 10/2026) hatten es noch
    k = pd.DataFrame(out)
    if not k.empty:
        k["saddle_no"] = pd.to_numeric(k["saddle_no"], errors="coerce")
    return k


def pmu_tag(base: Path, ymd: str) -> pd.DataFrame:
    f = Path(base) / "parquet" / "pmu_runners" / f"{ymd}.parquet"
    if not f.exists():
        return pd.DataFrame()
    h = pd.read_parquet(f)
    h["race_id"] = h["race_id"].astype(str)
    for c in ("saddle_no", "odds_morning", "odds_final", "finish_pos"):
        h[c] = pd.to_numeric(h.get(c), errors="coerce")
    st = h.get("status", pd.Series("", index=h.index)).astype("string").str.upper().fillna("")
    h["pmu_nr"] = st.eq("NON_PARTANT")
    return h[["race_id", "saddle_no", "odds_morning", "odds_final", "finish_pos", "pmu_nr"]].drop_duplicates(
        ["race_id", "saddle_no"], keep="last")


def tage_mit_ergebnis(base: Path, tage: int, bis: str | None = None) -> list[str]:
    """Die letzten `tage` Tage, für die es eine Karte UND PMU-Starter mit Platzierungen gibt."""
    karten = {p.stem.split("_")[1] for p in (Path(base) / "racecards").glob("racecard_*_daten.json")}
    ok = []
    for ymd in sorted(karten, reverse=True):
        if bis and ymd > bis:
            continue
        h = pmu_tag(base, ymd)
        if not h.empty and h["finish_pos"].notna().any():
            ok.append(ymd)
        if len(ok) >= tage:
            break
    return sorted(ok)


def _kennzahlen(z: pd.DataFrame, spalte: str) -> dict:
    m = z[[spalte, "odds_morning", "odds_final"]].dropna(subset=[spalte])
    mm = m.dropna(subset=["odds_morning"])
    if mm.empty:
        return {"n_karte": len(m), "n_paar": 0}
    lr = np.log(mm[spalte] / mm["odds_morning"])
    rel = (mm[spalte] / mm["odds_morning"] - 1).abs()
    beide = mm.dropna(subset=["odds_final"])
    naeher_morgen = (np.abs(np.log(beide[spalte] / beide["odds_morning"]))
                     < np.abs(np.log(beide[spalte] / beide["odds_final"]))).mean() if len(beide) else np.nan
    return {"n_karte": len(m), "n_paar": len(mm),
            "gleich": float((np.abs(mm[spalte] - mm["odds_morning"]) <= 0.05).mean()),
            "pm10": float((rel <= 0.10).mean()), "pm25": float((rel <= 0.25).mean()),
            "mae_log": float(lr.abs().mean()), "bias_log": float(lr.mean()),
            "spearman": float(mm[spalte].corr(mm["odds_morning"], method="spearman")) if len(mm) > 2 else np.nan,
            "naeher_morgen_als_end": float(naeher_morgen)}


def run(base: Path, tage: int = 7, bis: str | None = None, top: int = 15, log=print) -> dict:
    """Abgleich für die letzten `tage` Tage mit Ergebnissen. Rückgabe: {"zeilen", "je_tag", "gesamt", "abweichungen"}."""
    base = Path(base)
    liste = tage_mit_ergebnis(base, tage, bis)
    if not liste:
        log("Keine Tage mit Karte und PMU-Ergebnissen gefunden.")
        return {}
    teile = []
    for ymd in liste:
        k = karte_lesen(base / "racecards" / f"racecard_{ymd}_daten.json")
        h = pmu_tag(base, ymd)
        z = k.merge(h, on=["race_id", "saddle_no"], how="left", indicator=True)
        z["tag"] = ymd
        teile.append(z)
    z = pd.concat(teile, ignore_index=True)
    ohne = z["_merge"].eq("left_only")
    z = z[~z["nr"] & ~z["pmu_nr"].eq(True)].drop(columns="_merge")
    log(f"Tage: {', '.join(liste)}  |  Starter auf den Karten: {len(z):,}  |  ohne PMU-Zeile: {int(ohne.sum())}")
    log(f"PMU odds_morning vorhanden: {z['odds_morning'].notna().mean():.0%}  |  odds_final: {z['odds_final'].notna().mean():.0%}")

    spalten = [s for s in [*QUELLEN, "karte_odds_morning"] if z[s].notna().any()]
    gesamt = pd.DataFrame({s: _kennzahlen(z, s) for s in spalten}).T
    je_tag = pd.concat({s: pd.DataFrame({t: _kennzahlen(g, s) for t, g in z.groupby("tag")}).T for s in spalten},
                       names=["quelle", "tag"])
    fmt = {"gleich": "{:.0%}", "pm10": "{:.0%}", "pm25": "{:.0%}", "mae_log": "{:.3f}", "bias_log": "{:+.3f}",
           "spearman": "{:.2f}", "naeher_morgen_als_end": "{:.0%}"}

    def zeigen(df):
        d = df.copy()
        for c, f in fmt.items():
            if c in d:
                d[c] = d[c].map(lambda v: f.format(v) if pd.notna(v) else "–")
        return d.to_string()

    log("\n=== Gesamt (Karte vs. PMU odds_morning) ===")
    log(zeigen(gesamt))
    log("\n=== Je Tag ===")
    log(zeigen(je_tag))

    abw = []
    for s in spalten:
        m = z.dropna(subset=[s, "odds_morning"]).copy()
        m["quelle"] = s
        m["karte"] = m[s]
        m["faktor"] = m[s] / m["odds_morning"]
        abw.append(m)
    abw = pd.concat(abw, ignore_index=True) if abw else pd.DataFrame()
    if not abw.empty:
        abw["abs_log"] = np.log(abw["faktor"]).abs()
        abw = abw.sort_values("abs_log", ascending=False)
        log(f"\n=== Größte Abweichungen (Top {top}) ===")
        log(abw.head(top)[["tag", "race_id", "saddle_no", "horse", "quelle", "karte", "odds_morning", "odds_final",
                           "faktor"]].round(2).to_string(index=False))
    log("\nLesart: gleich = |Δ| ≤ 0,05; pm10/pm25 = Anteil innerhalb ±10 %/±25 %; mae_log 0,10 ≈ 10 % typische "
        "Abweichung; bias_log > 0 = Karte höher als PMU; naeher_morgen_als_end = Anteil, bei dem der Kartenkurs "
        "näher am PMU-Morgenkurs liegt als an der Endquote.")
    return {"zeilen": z, "je_tag": je_tag, "gesamt": gesamt, "abweichungen": abw}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--tage", type=int, default=7)
    a = ap.parse_args()
    run(Path(a.base), a.tage)
