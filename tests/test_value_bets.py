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

def _runner(no, sieg, fk=None, platz=None, gold=None, wert=None, cote=None, nr=False, blind=None, **power):
    return {"no": no, "horse": f"H{no}", "nr": nr,
            "power": None if sieg is None else {"sieg": sieg, "gold": gold, "wert": wert, "sieg_blind": blind, **power},
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
                               cote=rnd.choice([None, 4.0, 9.0, 15.0]),
                               blind=round(s * rnd.uniform(0.5, 1.8), 3),
                               sieg_schatten=round(s * rnd.uniform(0.6, 1.6), 4) if t % 2 else None)
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
          "console.log(JSON.stringify(faelle.map(([f, v, w]) => simulieren(pool, f, v, 1000, w || 'ew'))));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_html_simulation_gleich_python(tmp_path):
    pool = _zufallspool(tmp_path)
    faelle = []
    for v in vb.VARIANTEN:
        faelle.append((vb.FilterConfig(), v))
    for mode, x in (("none", 0), ("rank", 0.5), ("rel", 1.2), ("max", 25)):
        for top in vb.TOP_WAHL:
            faelle.append((vb.FilterConfig(minw=0.3, mode=mode, mode_value=x, top=top), "kelly2"))
    faelle += [(vb.FilterConfig(), "kelly4", "sieg"), (vb.FilterConfig(minw=0.2, mode="none"), "level10", "sieg")]
    faelle += [(vb.FilterConfig(chance="schatten"), "kelly4", "sieg"),
               (vb.FilterConfig(chance="karte_schatten_tage", minw=0.2, mode="none"), "level10", "ew"),
               (vb.FilterConfig(chance="schatten", minw=0.2, mode="none", min_kelly=0.05, je_veranstaltung=7,
                                eins_je_rennen=True), "kelly8", "sieg")]
    faelle += [(vb.FilterConfig(minw=0.2, mode="none", min_kelly=0.05, je_veranstaltung=6, eins_je_rennen=True), "kelly8", "sieg"),
               (vb.FilterConfig(minw=0.0, mode="none", min_kelly=0.02), "level10", "ew"),
               (vb.FilterConfig(minw=0.2, mode="none", je_veranstaltung=4, eins_je_rennen=True), "kelly8", "sieg"),
               (vb.FilterConfig(minw=0.0, mode="none", je_veranstaltung=3), "level10", "sieg"),
               (vb.FilterConfig(minw=0.3, mode="max", mode_value=15, eins_je_rennen=True), "kelly4", "ew")]
    faelle = [(x[0], x[1], x[2] if len(x) > 2 else "ew") for x in faelle]
    js = _node_sim(pool, [[vars(f), v, w] for f, v, w in faelle])
    for (f, v, w), j in zip(faelle, js):
        py = vb.simulate(pool, f, vb.StakingConfig(v, wettart=w))
        assert j["kpi"]["bets"] == py.kpi_dict["bets"], (f, v)
        assert j["kpi"]["bank"] == py.kpi_dict["bank"], (f, v)
        assert [d["bank"] for d in j["days"]] == list(py.days_df["bank"]), (f, v)
        if py.kpi_dict["bets"]:
            assert [b["profit"] for b in j["bets"]] == list(py.bets_df["profit"])
            assert [b["horse"] for b in j["bets"]] == list(py.bets_df["horse"])
            for k in ("roi", "tax", "wins", "places", "exp_wins_fk", "edge_win", "edge_place", "exp_places_model",
                      "kurs_n", "kurs_gefallen", "clv", "clv_rel", "kurs_besser", "kurs_rel_se", "kurs_z",
                      "pool_clv_rel", "mt_n", "mt_b1", "mt_b2", "mt_se", "mt_t", "mt_n_presse", "mt_b2_presse",
                      "mt_t_presse", "toto_fehlt"):
                assert j["kpi"][k] == pytest.approx(py.kpi_dict[k]), k
    assert any(j["kpi"]["bets"] > 10 for j in js)
    # Kursvorteil im Verlauf: JS gleich Python
    for (f, v, w), j in zip(faelle, js):
        py = vb.simulate(pool, f, vb.StakingConfig(v, wettart=w))
        pc = vb.mit_wert(vb.chance_waehlen(pool, f.chance))
        kv = vb.kurs_verlauf(py.bets_df, pc[pc["date"].isin(py.days_df["date"])])
        assert len(j["kurs"]) == len(kv)
        for spalte in ("lauf", "lauf_lo", "lauf_hi", "pool_lauf"):
            erw = [None if pd.isna(x) else x for x in kv[spalte]]
            ist = [r[spalte] for r in j["kurs"]]
            assert [x is None for x in ist] == [x is None for x in erw], spalte
            assert [x for x in ist if x is not None] == pytest.approx([x for x in erw if x is not None]), spalte
    assert any(len(j["kurs"]) > 5 for j in js)
    # Modell → Toto im Verlauf: JS gleich Python
    for (f, v, w), j in zip(faelle, js):
        py = vb.simulate(pool, f, vb.StakingConfig(v, wettart=w)).modell_toto
        assert [x["date"] for x in j["mt"]] == [x["date"] for x in py]
        for a_, b_ in zip(j["mt"], py):
            for k_ in ("b2", "t", "t_presse", "n", "n_tag"):
                assert (a_[k_] is None) == (b_[k_] is None) and (a_[k_] is None or a_[k_] == pytest.approx(b_[k_])), k_
    assert any(j["kpi"]["mt_t"] is not None for j in js) and any(len(j["mt"]) >= 2 for j in js)


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
    res = vb.simulate(pool.reset_index(), vb.FilterConfig(mode="none", minw=0.0))
    k = res.kpi_dict
    assert k["kurs_n"] == k["bets"] and 0 <= k["kurs_gefallen"] <= 1
    b = res.bets_df
    assert k["clv_rel"] == pytest.approx(np.exp(b["kurs_rel"].mean()) - 1)
    ohne = vb.load_folder(tmp_path, ab=None, starter_ordner=tmp_path / "fehlt")
    assert ohne["toto_end"].isna().all() and vb.simulate(ohne).kpi_dict["kurs_n"] == 0


def test_kurs_verlauf_hand():
    bets = pd.DataFrame({"date": ["20250101", "20250101", "20250102"], "race_id": ["A", "B", "C"], "no": [1, 1, 2],
                         "race": ["R1C1", "R1C2", "R1C1"], "horse": ["X", "Y", "Z"], "fk_sieg": [5.0, 8.0, 4.0],
                         "toto_end": [4.0, 9.0, 3.0], "fk_toto": [1.25, 8 / 9, 4 / 3], "kurs_rel": [0.2, -0.1, 0.3]})
    pool = pd.DataFrame({"date": ["20250101", "20250101", "20250101", "20250102", "20250102"],
                         "race_id": ["A", "A", "B", "C", "C"], "no": [1, 2, 1, 1, 2], "settled": True,
                         "fk_toto": 1.0, "kurs_rel": [0.2, 0.0, -0.1, 0.1, 0.3]})
    kv = vb.kurs_verlauf(bets, pool)
    assert list(kv["lauf"]) == pytest.approx([np.exp(0.2) - 1, np.exp(0.05) - 1, np.exp(0.4 / 3) - 1])
    se2 = np.std([0.2, -0.1], ddof=1) / np.sqrt(2)
    assert np.isnan(kv["lauf_lo"][0]) and kv["lauf_hi"][1] == pytest.approx(np.exp(0.05 + se2) - 1)
    # Pool bis einschließlich der Wette: (A,1) → 0.2; (B,1) → Ø(0.2, 0, −0.1); (C,2) → Ø aller fünf
    assert list(kv["pool_lauf"]) == pytest.approx([np.exp(0.2) - 1, np.exp(0.1 / 3) - 1, np.exp(0.5 / 5) - 1])
    k = vb.kurs_kpis(bets, pool)
    rel = np.array([0.2, -0.1, 0.3])
    assert k["pool_clv_rel"] == pytest.approx(np.exp(0.1) - 1)
    assert k["kurs_rel_se"] == pytest.approx(np.std(rel, ddof=1) / np.sqrt(3))
    assert k["kurs_z"] == pytest.approx(rel.mean() / k["kurs_rel_se"])


def test_modell_toto_gegen_numpy():
    rng = np.random.default_rng(3)
    n = 60
    fk = np.exp(rng.uniform(1, 3.5, n)); p = np.exp(rng.uniform(-3, -1, n)); cote = fk * np.exp(rng.normal(0, .3, n))
    toto = np.exp(0.3 + 0.8 * np.log(fk) - 0.5 * np.log(p) + rng.normal(0, .4 * (1 + np.log(fk) / 3), n))
    rows = pd.DataFrame({"date": "20250101", "toto_end": toto, "fk_sieg": fk, "p_model": p * 2, "p_blind": p,
                         "cote_dec": cote})
    k = vb.modell_toto(rows)
    X = np.column_stack([np.ones(n), np.log(fk), np.log(p)]); y = np.log(toto)
    xi = np.linalg.inv(X.T @ X); b = xi @ X.T @ y; e = y - X @ b
    v = xi @ (X.T * e ** 2) @ X @ xi * n / (n - 3)
    assert k["mt_b1"] == pytest.approx(b[1]) and k["mt_b2"] == pytest.approx(b[2])     # Power allein, nicht p_model
    assert k["mt_t"] == pytest.approx(b[2] / np.sqrt(v[2, 2]))
    X4 = np.column_stack([X, np.log(cote)]); xi4 = np.linalg.inv(X4.T @ X4); b4 = xi4 @ X4.T @ y; e4 = y - X4 @ b4
    v4 = xi4 @ (X4.T * e4 ** 2) @ X4 @ xi4 * n / (n - 4)
    assert k["mt_b2_presse"] == pytest.approx(b4[2]) and k["mt_t_presse"] == pytest.approx(b4[2] / np.sqrt(v4[2, 2]))
    assert vb.modell_toto(rows.iloc[:19])["mt_t"] is None                       # n < 20
    sing = rows.assign(p_blind=rows["fk_sieg"] ** 2)                             # log p = 2·log fk: singulär
    assert vb.modell_toto(sing)["mt_t"] is None


def test_modell_toto_verlauf_und_hinweis():
    rng = np.random.default_rng(4)
    tage = ["20250101"] * 15 + ["20250102"] * 10 + ["20250103"] * 12
    n = len(tage)
    fk = np.exp(rng.uniform(1, 3, n)); p = np.exp(rng.uniform(-3, -1, n))
    sel = pd.DataFrame({"date": tage, "fk_sieg": fk, "p_blind": p, "p_model": p, "cote_dec": None,
                        "toto_end": np.exp(np.log(fk) - .4 * np.log(p) + rng.normal(0, .3, n))})
    sel.loc[3, "toto_end"] = None
    vl = vb.modell_toto_verlauf(sel)
    assert [x["date"] for x in vl] == ["20250102", "20250103"]               # 1. Tag: 14 < 20 Picks
    assert vl[0]["n"] == 24 and vl[0]["n_tag"] == 10 and vl[1]["n"] == 36
    assert vl[1]["t"] == pytest.approx(vb.modell_toto(sel)["mt_t"]) and vl[1]["t_presse"] is None
    k = vb._mt_kpis(sel)
    assert k["toto_fehlt"] == 1


def test_nur_sieg(tmp_path):
    r = _rennen("20250910R1C1", [_runner(1, 0.5, fk=3.0, platz=1.5), _runner(2, 0.3, fk=2.0, platz=1.2),
                                 _runner(3, 0.2, fk=6.0, platz=2.5)])
    j, pq = _tag(tmp_path, "20250910", [r], {"20250910R1C1": "2 - 1 - 3"})
    pool = vb.load_day(j, pq)
    ew = vb.simulate(pool, vb.FilterConfig(mode="none"), vb.StakingConfig("level10")).bets_df.iloc[0]
    s = vb.simulate(pool, vb.FilterConfig(mode="none"), vb.StakingConfig("level10", wettart="sieg"))
    b = s.bets_df.iloc[0]
    assert ew["stake_place"] == 10 and ew["profit_place"] == pytest.approx(10 * 0.5 - 0.5)
    assert b["stake_win"] == 10 and b["stake_place"] == 0 and b["profit_place"] == 0 and b["fk_platz"] == 1.5
    assert b["tax"] == pytest.approx(0.5) and s.kpi_dict["profit"] == pytest.approx(-10.5)
    assert s.kpi_dict["places"] == 0 and s.kpi_dict["edge_place"] is None
    with pytest.raises(ValueError):
        vb.StakingConfig(wettart="platz")


def test_morgenquote_raus_und_aenderungen(tmp_path):
    # Karte mit Morgenquote (sieg_quelle „morgen“): faire Quote aus sieg_blind (Power-Mischung ohne Morgenquote)
    r = _rennen("20250910R1C1", [_runner(1, 0.5, fk=3.0, platz=1.5, blind=0.2, sieg_quelle="morgen"),
                                 _runner(2, 0.3, fk=3.0, platz=2.0, blind=0.6, sieg_quelle="morgen"),
                                 _runner(3, 0.2, fk=6.0, platz=2.5, blind=0.2, sieg_quelle="morgen")])
    j, pq = _tag(tmp_path, "20250910", [r], {"20250910R1C1": "2 - 1 - 3"})
    pool = vb.load_day(j, pq).set_index("no")
    assert pool.loc[2, "p"] == pytest.approx(0.6) and pool.loc[2, "wert"] == pytest.approx(3 * 0.6 - 1)
    assert 1 not in pool.index and pool["ohne_morgenquote"].all()               # Nr 1: Wert 3·0,2−1 < 0
    assert pool["verfahren"].iloc[0].startswith("Power (Karte mit Morgenquote")
    assert list(vb.simulate(pool.reset_index(), vb.FilterConfig(mode="none", minw=0.4)).bets_df["no"]) == [2]
    # spätere Karten: Power-Mischung (Treiber in Power-Punkten), dann mit Value, dann neu trainiert
    for d, pw in (("20250911", {"treiber_einheit": "power"}), ("20250912", {"treiber_einheit": "power", "value_pct": 3.0}),
                  ("20250913", {"treiber_einheit": "power", "value_pct": 3.0})):
        rid = f"{d}R1C1"
        _tag(tmp_path, d, [_rennen(rid, [_runner(1, 0.6, fk=3.0, platz=1.5, blind=0.5, sieg_quelle="power", **pw),
                                         _runner(2, 0.4, fk=3.0, platz=2.0, blind=0.5, sieg_quelle="power", **pw)])],
             {rid: "1 - 2"})
    daten = json.loads((tmp_path / "racecard_20250913_daten.json").read_text())
    daten["modelle"] = {"faire_quote": {"quellen": ["Power", "Power-sieg"], "power_trainiert": "2025-09-12 20:00",
                                        "value_kappa": 0.4}}
    (tmp_path / "racecard_20250913_daten.json").write_text(json.dumps(daten))
    tag12 = json.loads((tmp_path / "racecard_20250912_daten.json").read_text())
    tag12["modelle"] = {"faire_quote": {"quellen": ["Power", "Power-sieg"], "power_trainiert": "2025-09-01 10:00"}}
    (tmp_path / "racecard_20250912_daten.json").write_text(json.dumps(tag12))
    alle = vb.load_folder(tmp_path, ab=None)
    ae = vb.aenderungen(alle)
    assert [a["date"] for a in ae] == ["20250910", "20250911", "20250912", "20250913"]
    assert ae[1]["text"].endswith("→ Power × Power-sieg") and ae[2]["text"].endswith("Power × Power-sieg × Value")
    assert ae[3]["text"] == "Power neu trainiert (2025-09-12 20:00)"
    assert vb.dashboard_daten(alle)["aenderungen"] == ae
    assert "gold" not in vb.dashboard_daten(alle)["spalten"]
    with pytest.raises(ValueError):
        vb.FilterConfig(chance="power")                                  # alter Umschalter (ohne Value) gibt es nicht mehr


def test_beste_je_veranstaltung_und_tipps(tmp_path):
    # R1: zwei Rennen, R2: ein Rennen; Kelly-Anteil = Wert ÷ (FK − 1)
    r11 = _rennen("20250920R1C1", [_runner(1, 0.5, fk=3.0), _runner(2, 0.3, fk=5.0), _runner(3, 0.2, fk=4.0)])
    r12 = _rennen("20250920R1C2", [_runner(1, 0.6, fk=2.5), _runner(2, 0.4, fk=3.0)])
    r21 = {**_rennen("20250920R2C1", [_runner(1, 0.7, fk=2.0), _runner(2, 0.3, fk=4.0)]), "reunion": 2}
    j, pq = _tag(tmp_path, "20250920", [r11, r12, r21], {"20250920R1C1": "1 - 2", "20250920R1C2": "2 - 1",
                                                           "20250920R2C1": "1 - 2"})
    pool = vb.load_day(j, pq)
    k = dict(zip(zip(pool["race"], pool["no"]), vb.kelly_anteil(pool)))
    assert k[("R1C1", 1)] == pytest.approx(0.5 / 2) and k[("R1C1", 2)] == pytest.approx(0.5 / 4)
    zwei = vb.beste_je_veranstaltung(pool, 2)
    assert sorted(zip(zwei["race"], zwei["no"])) == [("R1C1", 1), ("R1C2", 1), ("R2C1", 1), ("R2C1", 2)]
    eins = vb.beste_je_veranstaltung(pool, 2, eins_je_rennen=True)
    assert sorted(zip(eins["race"], eins["no"])) == [("R1C1", 1), ("R1C2", 1), ("R2C1", 1)]
    assert len(vb.beste_je_veranstaltung(pool, 0)) == len(pool)
    # Schwelle: Kelly-Anteil ≥ 0,3 lässt nur R1C2 Nr 1 (0,5 ÷ 1,5) und R2C1 Nr 1 (0,4 ÷ 1) übrig
    sk = vb.simulate(pool, vb.FilterConfig(mode="none", minw=0.0, min_kelly=0.3))
    assert sorted(zip(sk.bets_df["race"], sk.bets_df["no"])) == [("R1C2", 1), ("R2C1", 1)]
    sim = vb.simulate(pool, vb.FilterConfig(mode="none", minw=0.0, je_veranstaltung=1))
    assert sorted(zip(sim.bets_df["race"], sim.bets_df["no"])) == [("R1C2", 1), ("R2C1", 1)]   # Kelly 0,33 > 0,25
    # Karte: Tipps mit Rang und Kelly-Anteil; Wert unter der Schwelle fällt weg
    daten = json.loads(j.read_text())
    n = vb.tipps_setzen(daten, n=4, min_wert=0.2)
    tipps = {(rid, x["no"]): x["power"]["tipp"] for rid, r in daten["races"].items() for x in r["runners"]
             if (x.get("power") or {}).get("tipp")}
    assert n == 3 and set(tipps) == {("20250920R1C1", 1), ("20250920R1C2", 1), ("20250920R2C1", 1)}
    t = tipps[("20250920R1C1", 1)]
    assert t["rang"] == 2 and t["von"] == 2 and t["kelly"] == pytest.approx(0.25) and t["fk"] == 3.0
    assert tipps[("20250920R1C2", 1)]["rang"] == 1                     # Kelly 0,5 ÷ 1,5 > 0,5 ÷ 2
    assert daten["tipp_regel"]["je_veranstaltung"] == 4
    # erneut mit höherer Schwelle: alte Tipps werden entfernt
    assert vb.tipps_setzen(daten, n=4, min_wert=0.45) == 2
    assert not daten["races"]["20250920R2C1"]["runners"][0]["power"].get("tipp")  # Wert 0,4 < 0,45
    # Vorgabe (Karte): alle Kandidaten mit Rang, die Karte zeigt die ersten N; n = 1: nur der erste je Veranstaltung
    assert vb.tipps_setzen(daten) == 3 and daten["tipp_regel"]["je_veranstaltung"] == vb.TIPP_N
    assert vb.tipps_setzen(daten, n=1) == 2


def test_wochenblick_js(tmp_path):
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("node fehlt")
    pool = _zufallspool(tmp_path)
    # Toto-Endquoten ergänzen (der Zufallspool hat keine): je Pick ein Kurs um den Festkurs
    rnd = np.random.default_rng(3)
    pool = pool.copy()
    pool["toto_end"] = np.where(pool["fk_sieg"].notna(), pool["fk_sieg"] * rnd.uniform(0.6, 1.3, len(pool)), np.nan)
    pool["fk_toto"] = pool["fk_sieg"] / pool["toto_end"]
    f = vb.FilterConfig(minw=0.2, mode="none")
    t = vb.TEMPLATE.read_text(encoding="utf-8")
    sim = t[t.index("// SIM-START"):t.index("// SIM-END")]
    daten = json.dumps(vb.dashboard_daten(pool))
    js = (sim + f"\nconst pool = zeilen({daten});\nconst r = simulieren(pool, {json.dumps(vars(f))}, 'level10', 1000, 'sieg');\n"
          "console.log(JSON.stringify([r.woche, isoWoche('20261026'), isoWoche('20210103'), isoWoche('20241230')]));")
    w, kw1, kw2, kw3 = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert kw1["key"] == "2026-W44" and kw1["von"] == "20261026" and kw1["bis"] == "20261101"
    assert kw2["key"] == "2020-W53" and kw3["key"] == "2025-W01"                 # Jahreswechsel nach ISO 8601
    assert w["schwelle"] == pytest.approx(1.05 / 0.77)
    sel = vb.auswahl(vb.mit_wert(pool), f)
    sel = sel[sel["settled"].astype(bool)].copy()
    sel["kw"] = pd.to_datetime(sel["date"]).dt.isocalendar().week
    assert [x["kw"] for x in w["wochen"]] == sorted(sel["kw"].unique())
    for x in w["wochen"]:
        s = sel[sel["kw"] == x["kw"]]
        s = s[(s["fk_toto"] > 0) & (s["toto_end"] > 0)]
        g = float(np.exp(np.log(s["fk_toto"]).mean()))
        p = 0.77 / s["toto_end"]
        assert x["n"] == len(s) and x["fk_toto"] == pytest.approx(g) and x["edge_toto"] == pytest.approx(g * 0.77 - 1.05)
        assert x["sieger"] == int(s["won"].sum()) and x["erw_toto"] == pytest.approx(p.sum())
        assert x["z_toto"] == pytest.approx((s["won"].sum() - p.sum()) / np.sqrt((p * (1 - p)).sum()))
    alle = sel[(sel["fk_toto"] > 0) & (sel["toto_end"] > 0)]
    assert w["wochen"][-1]["kum"]["n"] == len(alle)
    assert w["wochen"][-1]["kum"]["fk_toto"] == pytest.approx(float(np.exp(np.log(alle["fk_toto"]).mean())))


def test_schattenversion(tmp_path):
    # Tag 1 mit Schattenversion (Nr 2 dort stärker), Tag 2 ohne
    r1 = _rennen("20250930R1C1", [_runner(1, 0.5, fk=3.0, platz=1.5, sieg_schatten=0.4),
                                  _runner(2, 0.3, fk=3.0, platz=2.0, sieg_schatten=0.5),
                                  _runner(3, 0.2, fk=6.0, platz=2.5, sieg_schatten=0.1)])
    r2 = _rennen("20251001R1C1", [_runner(1, 0.6, fk=2.0, platz=1.2), _runner(2, 0.4, fk=4.0, platz=1.8)])
    _tag(tmp_path, "20250930", [r1], {"20250930R1C1": "2 - 1 - 3"})
    _tag(tmp_path, "20251001", [r2], {"20251001R1C1": "1 - 2"})
    pool = vb.load_folder(tmp_path, ab=None)
    t1 = pool[pool["date"] == "20250930"].set_index("no")
    assert t1.loc[2, "p_sh"] == pytest.approx(0.5) and t1.loc[2, "wert_sh"] == pytest.approx(0.5)
    assert t1.loc[2, "wert"] == pytest.approx(3 * 0.3 - 1)                # unter der Karte < 0, im Pool wegen Schatten
    assert pool.loc[pool["date"] == "20251001", "p_sh"].isna().all()
    k = vb.chance_waehlen(pool, "karte_schatten_tage")
    s = vb.chance_waehlen(pool, "schatten")
    assert set(k["date"]) == set(s["date"]) == {"20250930"} and len(vb.chance_waehlen(pool, "karte")) == len(pool)
    assert s.set_index("no").loc[2, "wert"] == pytest.approx(0.5)
    f = dict(mode="none", minw=0.3)
    assert list(vb.simulate(pool, vb.FilterConfig(**f)).bets_df["no"]) == [1, 2]          # Karte: Tag 2 Nr 2 (Wert 0,6)
    assert list(vb.simulate(pool, vb.FilterConfig(chance="schatten", **f)).bets_df["no"]) == [2]
    assert list(vb.simulate(pool, vb.FilterConfig(chance="karte_schatten_tage", **f)).bets_df["no"]) == [1]


def test_kombiblick_js(tmp_path):
    import shutil
    import subprocess
    import sys
    if not shutil.which("node"):
        pytest.skip("node fehlt")
    sys.path.insert(0, str(Path(__file__).parent))
    import kombi
    import kombi_fall
    kombi_fall.bauen(tmp_path, tage=8)
    v = kombi.vorwaertstest(tmp_path, n_sim=2000, log=lambda *a: None)
    daten = vb.dashboard_daten(pd.DataFrame(), v)
    assert daten["kombi"]["spalten"] == kombi.VORWAERTS_SPALTEN and len(daten["kombi"]["zeilen"]) == len(v)
    t = vb.TEMPLATE.read_text(encoding="utf-8")
    sim = t[t.index("// SIM-START"):t.index("// SIM-END")]
    js = (sim + f"\nconst rows = zeilen({json.dumps(daten['kombi'])});\n"
          "console.log(JSON.stringify(['couple_place', '2sur4'].flatMap(a => ['modell', 'schatten'].map(q => kombiBlick(rows, a, q, 0.2)))));")
    (tmp_path / "kombi.js").write_text(js, encoding="utf-8")
    ergebnisse = json.loads(subprocess.run(["node", str(tmp_path / "kombi.js")], capture_output=True, text=True,
                                           check=True).stdout)
    for (art, quelle), k in zip([(a, q) for a in ("couple_place", "2sur4") for q in ("modell", "schatten")], ergebnisse):
        s = v[v["settled"] & (v["art"] == art) & (v["quelle"] == quelle) & (v["ew"] >= 0.2 - 1e-9)]
        g = k["gesamt"]
        assert g["tickets"] == len(s) and g["treffer"] == int(s["treffer"].sum())
        assert g["erw_modell"] == pytest.approx(s["p_modell"].sum()) and g["erw_publikum"] == pytest.approx(s["p_publikum"].sum())
        if len(s):
            assert g["roi"] == pytest.approx(s["div"].sum() / len(s) - 1)
            assert g["abschlag"] == pytest.approx(s["treffer"].sum() / s["p_modell"].sum() - 1)
            assert sum(w["tickets"] for w in k["wochen"]) == len(s)
