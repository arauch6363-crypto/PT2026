"""Tests für value_bets.

Datentests brauchen die Karten vom 18.–20.10.2026 (racecard_*_daten.json oder
racecard_*.html) in VALUE_BETS_DATA und die pmu_races-Parquets in
VALUE_BETS_RESULTS (Vorgabe: derselbe Ordner); ohne sie werden sie übersprungen.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
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
    assert pool.loc[1, "fair_platz"] == pytest.approx(1 / pool.loc[1, "p_platz"])
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


# ------------------------------------------------------------ HTML-Dashboard

def _zufallspool(tmp_path, tage=4, seed=7):
    import random
    rnd = random.Random(seed)
    for t in range(tage):
        d = f"202509{10 + t:02d}"
        rennen, einlauf = [], {}
        for c in range(1, 7):
            n = rnd.randint(5, 14)
            sieg = [rnd.random() ** 2 + 0.01 for _ in range(n)]
            runners = [_runner(i + 1, round(s, 3), fk=rnd.choice([None] + [x / 2 for x in range(3, 80)]),
                               platz=rnd.choice([None, 1.1, 1.6, 2.4, 3.5, 6.0]),
                               gold=rnd.choice([True, False, None]), wert=round(rnd.uniform(0.6, 1.6), 2),
                               cote=rnd.choice([None, 4.0, 9.0, 15.0]))
                       for i, s in enumerate(sieg)]
            rid = f"{d}R1C{c}"
            rennen.append(_rennen(rid, runners))
            reihe = list(range(1, n + 1))
            rnd.shuffle(reihe)
            if t < tage - 1 or c < 6:          # letzter Tag: ein Rennen ohne Einlauf
                einlauf[rid] = " - ".join(map(str, reihe[:5]))
        _tag(tmp_path, d, rennen, einlauf)
        stz = [(r_["race_id"], x["no"]) for r_ in rennen for x in r_["runners"]]
        (tmp_path / "pmu_runners").mkdir(exist_ok=True)
        pd.DataFrame({"race_id": [a_ for a_, _ in stz], "saddle_no": [b_ for _, b_ in stz],
                      "odds_final": [rnd.choice([None, 1.8, 3.5, 6.0, 12.0, 25.0]) for _ in stz]}).to_parquet(
            tmp_path / "pmu_runners" / f"{d}.parquet")
    with pytest.warns(UserWarning):
        return vb.load_folder(tmp_path, ab=None)


def _node_sim(pool, faelle):
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    t = vb.TEMPLATE.read_text(encoding="utf-8")
    sim = t[t.index("// SIM-START"):t.index("// SIM-END")]
    daten = json.dumps(vb.dashboard_daten(pool))
    js = (sim + f"\nconst pool = zeilen({daten});\nconst faelle = {json.dumps(faelle)};\n"
          "console.log(JSON.stringify(faelle.map(([f, v]) => simulieren(pool, f, v))));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_html_simulation_gleich_python(tmp_path):
    pool = _zufallspool(tmp_path)
    faelle = []
    for v in vb.VARIANTEN:
        faelle.append((vb.FilterConfig(), v))
    for mode, x in (("none", 0), ("rank", 0.5), ("rel", 1.2), ("max", 25)):
        for top in vb.TOP_WAHL:
            faelle.append((vb.FilterConfig(minw=0.3, gold_on=top != "ja", mode=mode, mode_value=x, top=top), "kelly2"))
    js = _node_sim(pool, [[vars(f), v] for f, v in faelle])
    for (f, v), j in zip(faelle, js):
        py = vb.simulate(pool, f, vb.StakingConfig(v))
        assert j["kpi"]["bets"] == py.kpi_dict["bets"], (f, v)
        assert j["kpi"]["bank"] == py.kpi_dict["bank"], (f, v)
        assert [d["bank"] for d in j["days"]] == list(py.days_df["bank"]), (f, v)
        if py.kpi_dict["bets"]:
            assert [b["profit"] for b in j["bets"]] == list(py.bets_df["profit"])
            assert [b["horse"] for b in j["bets"]] == list(py.bets_df["horse"])
            for k in ("roi", "tax", "wins", "places", "exp_wins_fk", "edge_win", "edge_place", "exp_places_model",
                      "kurs_n", "kurs_gefallen", "clv", "clv_rel", "kurs_besser"):
                assert j["kpi"][k] == pytest.approx(py.kpi_dict[k]), k
    assert any(j["kpi"]["bets"] > 10 for j in js)


def test_rhu_js_gleich_python():
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("node fehlt")
    t = vb.TEMPLATE.read_text(encoding="utf-8")
    sim = t[t.index("// SIM-START"):t.index("// SIM-END")]
    werte = [0.5, 1.5, 2.5, -0.5, -2.5, 2.675, 1.005, 12.345, 10.125, -7.005, 1e-7, 123456.785, 0.045]
    js = sim + f"\nconsole.log(JSON.stringify({werte}.flatMap(x => [rhu(x), rhu(x, 2)])));"
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    erw = [y for x in werte for y in (vb.round_half_up(x), vb.round_half_up(x, 2))]
    assert out == pytest.approx(erw, abs=0)


def test_dashboard_datei(tmp_path):
    pool = _zufallspool(tmp_path)
    p = vb.dashboard(pool, tmp_path / "racecards" / vb.DASHBOARD_DATEI)
    html = p.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>") and "/*__DATA__*/null" not in html
    vb.dashboard(pool.iloc[:5], p)                       # überschreibt
    assert len(p.read_text(encoding="utf-8")) < len(html)


def test_harville_wie_racecard():
    rc = pytest.importorskip("racecard")
    import numpy as np
    for p, k in (([0.5, 0.2, 0.1, 0.1, 0.05, 0.05], 2), ([0.3, 0.2, 0.1, 0.1, 0.1, 0.1, 0.05, 0.05], 3)):
        assert np.allclose(vb.harville_platz(p, k), rc.harville_platz(p, k))
        assert vb.harville_platz(p, k).sum() == pytest.approx(k)


def test_edge_formel(tmp_path):
    pool = _zufallspool(tmp_path)
    res = vb.simulate(pool, vb.FilterConfig(mode="none"))
    b, k = res.bets_df, res.kpi_dict
    mp = b[b["stake_place"] > 0]
    assert k["edge_win"] == pytest.approx((1 / b["fair"]).sum() / (1 / b["fk_sieg"]).sum())
    assert k["edge_place"] == pytest.approx((1 / mp["fair_platz"]).sum() / (1 / mp["fk_platz"]).sum())


def test_kursbewegung(tmp_path):
    r = _rennen("20250910R1C1", [_runner(1, 0.5, fk=3.0, platz=1.5), _runner(2, 0.3, fk=5.0, platz=2.0),
                                 _runner(3, 0.2, fk=6.0, platz=2.5)])
    j, pq = _tag(tmp_path, "20250910", [r], {"20250910R1C1": "1 - 2 - 3"})
    st = tmp_path / "pmu_runners"
    st.mkdir()
    pd.DataFrame({"race_id": ["20250910R1C1"] * 3, "saddle_no": [1, 2, 3],
                  "odds_final": [2.0, 5.0, 9.0]}).to_parquet(st / "20250910.parquet")
    pool = vb.load_folder(tmp_path, ab=None, starter_ordner=st).set_index("no")
    lv = np.log([3.0 / 2.0, 5.0 / 5.0, 6.0 / 9.0])
    assert pool.loc[1, "toto_end"] == 2.0 and pool.loc[1, "fk_toto"] == pytest.approx(1.5)
    assert pool.loc[1, "kurs_rel"] == pytest.approx(lv[0] - lv.mean())
    res = vb.simulate(pool.reset_index(), vb.FilterConfig(mode="none", minw=0.0, gold_on=False))
    k = res.kpi_dict
    assert k["kurs_n"] == k["bets"] and 0 <= k["kurs_gefallen"] <= 1
    b = res.bets_df
    assert k["clv_rel"] == pytest.approx(np.exp(b["kurs_rel"].mean()) - 1)
    ohne = vb.load_folder(tmp_path, ab=None, starter_ordner=tmp_path / "fehlt")
    assert ohne["toto_end"].isna().all() and vb.simulate(ohne).kpi_dict["kurs_n"] == 0
