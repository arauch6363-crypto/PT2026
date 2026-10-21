"""Tests für value_bets.

Datentests brauchen die Karten vom 18.–20.10.2026 (racecard_*_daten.json oder
racecard_*.html) in VALUE_BETS_DATA und die pmu_races-Parquets in
VALUE_BETS_RESULTS (Vorgabe: derselbe Ordner); ohne sie werden sie übersprungen.
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import value_bets as vb  # noqa: E402

DATEN = os.environ.get("VALUE_BETS_DATA")
ERGEBNIS = os.environ.get("VALUE_BETS_RESULTS") or DATEN
TAGE = ("20261018", "20261019", "20261020")


# ------------------------------------------------------------ synthetisch

def _runner(no, sieg, fk=None, platz=None, gold=None, wert=None, cote=None, nr=False):
    return {"no": no, "horse": f"H{no}", "nr": nr,
            "power": None if sieg is None else {"sieg": sieg, "gold": gold, "wert": wert},
            "fk": None if fk is None else {"sieg": fk, "platz": platz},
            "prono": {"sel": {"cote_dec": cote}}}


def _tag(tmp, datum, rennen, einlauf):
    j = tmp / f"racecard_{datum}_daten.json"
    j.write_text(json.dumps({"date": datum, "festkurse_stand": "12:00", "races": {
        r["race_id"]: r for r in rennen}}))
    pq = tmp / f"{datum}.parquet"
    pd.DataFrame({"race_id": list(einlauf), "date": datum,
                  "finish_order": list(einlauf.values()),
                  "runners_declared": 8}).to_parquet(pq)
    return j, pq


def _rennen(rid, runners):
    return {"race_id": rid, "reunion": 1, "race_no": int(rid[-1]), "course": "X", "runners": runners}


def test_round_half_up():
    assert vb.round_half_up(10.5) == 11
    assert vb.round_half_up(11.5) == 12
    assert vb.round_half_up(2.675, 2) == 2.68
    assert vb.round_half_up(-0.5) == -1


def test_abgeleitete_werte(tmp_path):
    r = _rennen("20260101R1C1", [
        _runner(1, 0.5, fk=3.0, platz=1.5, gold=True, cote=4),
        _runner(2, 0.25, fk=6.0, platz=2.0, gold=None, wert=1.3, cote=12),
        _runner(3, 0.25, fk=2.0, platz=1.2),
        _runner(4, 0.2, fk=50.0, nr=True),     # Nichtstarter
        _runner(5, None, fk=9.0),              # ohne Power
    ])
    j, pq = _tag(tmp_path, "20260101", [r], {"20260101R1C1": "2 - 1 - 3"})
    pool = vb.load_day(j, pq).set_index("no")
    assert set(pool.index) == {1, 2}           # Nr 3: Wert −0,5 → nicht im Pool
    assert pool.loc[1, "p"] == pytest.approx(0.5)
    assert pool.loc[1, "wert"] == pytest.approx(0.5)
    assert pool.loc[2, "wert"] == pytest.approx(0.5)
    assert pool.loc[1, "is_top"] == 1 and pool.loc[2, "is_top"] == 1   # Gleichstand
    assert pool.loc[1, "rank_fq"] == 1 and pool.loc[2, "rank_fq"] == 2
    assert pool.loc[2, "rank_pct"] == pytest.approx(0.5)
    assert pool.loc[1, "rel"] == pytest.approx(1.5)
    assert bool(pool.loc[1, "gold"]) and not bool(pool.loc[2, "gold"])  # Presse 12 > 10
    assert pool.loc[1, "paid_places"] == 2
    assert pool.loc[2, "won"] and pool.loc[1, "placed"] and not pool.loc[1, "won"]


def test_filter_und_kelly(tmp_path):
    r = _rennen("20260101R1C1", [_runner(i, s, fk=f, platz=p) for i, s, f, p in [
        (1, 0.30, 5.0, 2.0), (2, 0.20, 4.0, 1.8), (3, 0.10, 12.0, 3.5), (4, 0.10, 8.0, 2.5),
        (5, 0.10, 9.0, 3.0), (6, 0.10, 10.0, 3.0), (7, 0.05, 30.0, 6.0), (8, 0.05, 25.0, 5.0)]])
    j, pq = _tag(tmp_path, "20260101", [r], {"20260101R1C1": "1 - 3 - 2 - 4"})
    pool = vb.load_day(j, pq)
    res = vb.simulate(pool, vb.FilterConfig(), vb.StakingConfig("kelly4"))
    # Nr 1: Wert 0,5, fair 3,33 → Wette; Nr 3: Wert 0,2 < 0,5; Nr 7: Wert 0,5, fair 20 ≥ 10
    assert list(res.bets_df["no"]) == [1]
    b = res.bets_df.iloc[0]
    f = (0.3 * 5 - 1) / 4
    assert b["stake_win"] == vb.round_half_up(1000 * 0.25 * f)
    assert b["profit_win"] == pytest.approx(b["stake_win"] * 4 - 0.05 * b["stake_win"])
    assert b["profit_place"] == pytest.approx(b["stake_win"] * 1 - 0.05 * b["stake_win"])
    assert res.kpi_dict["bank"] == pytest.approx(1000 + b["profit"])
    keine = vb.simulate(pool, vb.FilterConfig(minw=1.5))
    assert keine.kpi_dict["bets"] == 0 and keine.kpi_dict["roi"] is None
    assert keine.kpi_dict["hinweis"] == vb.HINWEIS_LEER
    # Modus none: auch Nr 7 (fair 20); top nein: ohne Nr 1/7 (beide Top mit Wert 0,5)
    assert set(vb.simulate(pool, vb.FilterConfig(mode="none")).bets_df["no"]) == {1, 7}
    assert vb.simulate(pool, vb.FilterConfig(mode="none", top="nein")).kpi_dict["bets"] == 0


def test_html_karte_und_ergebnisordner(tmp_path):
    r = _rennen("20260103R1C1", [_runner(1, 0.6, fk=3.0, platz=1.4), _runner(2, 0.4, fk=2.0)])
    daten = {"date": "2026-01-03", "races": {r["race_id"]: r}}
    js = json.dumps(daten).replace("</", "<\\/")
    (tmp_path / "racecard_20260103.html").write_text(
        f"<script>const DATA = {js};\nconst X = 1;</script>", encoding="utf-8")
    erg = tmp_path / "parquet" / "pmu_races"
    erg.mkdir(parents=True)
    pd.DataFrame({"race_id": ["20260103R1C1"], "finish_order": ["1 - 2"]}).to_parquet(erg / "20260103.parquet")
    anders = tmp_path / "parquet" / "pmu_runners"
    anders.mkdir()
    pd.DataFrame({"x": [1]}).to_parquet(anders / "20260103.parquet")     # ohne Einlauf → ignoriert
    pool = vb.load_folder(tmp_path, ab=None)
    assert pool["settled"].all() and pool.loc[pool["no"] == 1, "won"].all()
    assert list(pool["date"].unique()) == ["20260103"]


def test_ab_datum(tmp_path):
    rn = lambda rid: _rennen(rid, [_runner(1, 0.6, fk=3.0, platz=1.4), _runner(2, 0.4, fk=2.0)])
    for d in ("20261017", "20261018"):
        _tag(tmp_path, d, [rn(f"{d}R1C1")], {f"{d}R1C1": "1 - 2"})
    assert list(vb.load_folder(tmp_path)["date"].unique()) == ["20261018"]
    assert len(vb.load_folder(tmp_path, ab=None)["date"].unique()) == 2


def test_bank_tagesbeginn_und_offener_tag(tmp_path):
    rn = lambda rid: _rennen(rid, [_runner(1, 0.6, fk=3.0, platz=1.4), _runner(2, 0.4, fk=2.0, platz=1.2)])
    _tag(tmp_path, "20260101", [rn("20260101R1C1"), rn("20260101R1C2")],
         {"20260101R1C1": "1 - 2", "20260101R1C2": "2 - 1"})
    (tmp_path / "racecard_20260102_daten.json").write_text(json.dumps(
        {"date": "20260102", "races": {"20260102R1C1": rn("20260102R1C1")}}))
    with pytest.warns(UserWarning, match="20260102"):
        pool = vb.load_folder(tmp_path, ab=None)
    res = vb.simulate(pool, vb.FilterConfig(mode="none"), vb.StakingConfig("level1p"))
    assert list(res.days_df["date"]) == ["20260101"]      # offener Tag nicht simuliert
    assert (res.bets_df["stake_win"] == 10).all()         # beide aus Bank 1000
    assert res.bets_df["bank_start"].nunique() == 1


# ------------------------------------------------------------ echte Daten

def _ordner_ok():
    if not DATEN:
        return False
    p, e = Path(DATEN), Path(ERGEBNIS)
    return all((list(p.rglob(f"racecard_{t}_daten.json")) or list(p.rglob(f"racecard_{t}.html")))
               and list(e.rglob(f"*{t}*.parquet")) for t in TAGE)


daten = pytest.mark.skipif(not _ordner_ok(), reason="VALUE_BETS_DATA mit 18.–20.10.2026 fehlt")


@pytest.fixture(scope="module")
def pool():
    return vb.load_folder(DATEN, ERGEBNIS)


@daten
@pytest.mark.parametrize("variante,bank,wetten", [
    ("kelly4", 2404.00, 18), ("kelly8", 1658.10, None), ("kelly2", 4115.40, None),
    ("kelly1", 8545.60, None), ("level10", 1262.00, None), ("level1p", 1282.80, None)])
def test_einsatzvarianten(pool, variante, bank, wetten):
    k = vb.simulate(pool, vb.FilterConfig(), vb.StakingConfig(variante)).kpi_dict
    assert k["bank"] == pytest.approx(bank, abs=0.005)
    if wetten is not None:
        assert k["bets"] == wetten


@daten
@pytest.mark.parametrize("f,bank,wetten", [
    (vb.FilterConfig(mode="none"), 2017.70, 31),
    (vb.FilterConfig(top="ja"), 2597.90, 11),
    (vb.FilterConfig(top="nein"), 877.70, 7)])
def test_filter(pool, f, bank, wetten):
    k = vb.simulate(pool, f, vb.StakingConfig("kelly4")).kpi_dict
    assert k["bank"] == pytest.approx(bank, abs=0.005)
    assert k["bets"] == wetten


@daten
def test_tag1_allein(pool):
    res = vb.simulate(pool[pool["date"] == "20261018"], vb.FilterConfig(), vb.StakingConfig("kelly4"))
    b = res.bets_df
    assert len(b) == 1
    assert b.iloc[0]["horse"].lower() == "hello avenue" and b.iloc[0]["race"] == "R1C5"
    assert b.iloc[0]["stake_win"] == 11 and b.iloc[0]["stake_place"] == 11
    assert b.iloc[0]["profit"] == pytest.approx(12.10, abs=0.005)
    assert res.kpi_dict["bank"] == pytest.approx(1012.10, abs=0.005)
