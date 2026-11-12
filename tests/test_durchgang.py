"""Tests für durchgang.py (Durchgang-Dateien neben der Karte) und die Strategie Claude-Tipps im Value-Dashboard."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import durchgang as dg  # noqa: E402
import value_bets as vb  # noqa: E402
from test_value_bets import _zufallspool  # noqa: E402


def _karte():
    def r(no, sieg, fk):
        return {"no": no, "horse": f"H{no}", "power": {"sieg": sieg}, "fk": {"sieg": fk} if fk else None}
    races = {
        "20261112R1C1": {"race_id": "20261112R1C1", "reunion": 1, "race_no": 1, "time": "12:00", "name": "PRIX A",
                         "runners": [r(1, 0.5, 3.0), r(2, 0.5, 1.5)]},
        "20261112R1C2": {"race_id": "20261112R1C2", "reunion": 1, "race_no": 2, "time": "15:00", "name": "PRIX B",
                         "runners": [r(1, 0.4, 3.0), r(2, 0.6, 1.5), {"no": 3, "nr": True, "power": {"sieg": 0.1}, "fk": {"sieg": 30}}]},
        "20261112R1C3": {"race_id": "20261112R1C3", "reunion": 1, "race_no": 3, "time": "15:30", "name": "PRIX C",
                         "runners": [r(1, 0.5, None), r(2, 0.5, None)]},
        "20261112R1C4": {"race_id": "20261112R1C4", "reunion": 1, "race_no": 4, "time": "16:00", "name": "PRIX D",
                         "runners": [r(1, 0.5, 1.8), r(2, 0.5, 1.9)]},
        "20261112R1C5": {"race_id": "20261112R1C5", "reunion": 1, "race_no": 5, "time": "16:30",
                         "name": "PRIX DES PUR-SANG ARABES", "runners": [r(1, 0.5, 3.0)]},
        "20261112R1C6": {"race_id": "20261112R1C6", "reunion": 1, "race_no": 6, "time": "17:00", "name": "PRIX E",
                         "runners": [r(1, 0.3, 5.0), r(2, 0.7, 1.2)]},
    }
    return {"date": "2026-11-12", "races": races}


def _rennen(rid, *kand, status="bearbeitet"):
    return {"race_id": rid, "status": status, "vergleich": "A > B",
            "kandidaten": [{"no": no, "horse": f"H{no}", "urteil": u, "fk": fk, "mq": mq, "spanne": [mq - 1, mq],
                            "pro": ["p"], "gegen": ["g"], "fragen": ["f"], "ausschlag": "x"} for no, u, fk, mq in kand]}


def _schreiben(ordner, name, rennen, stand="2026-11-12T14:00+0100"):
    p = Path(ordner) / name
    p.write_text(json.dumps(dg.zusammenfuehren("2026-11-12", rennen, stand)), encoding="utf-8")
    return p


def test_plan_status():
    st = {p["rennen"]: (p["status"], p["kandidaten"]) for p in dg.plan(_karte(), {"20261112R1C6"}, "14:30")}
    assert st["R1C1"][0] == "gelaufen"
    assert st["R1C2"] == ("offen", [1])                 # Nr. 3 Nichtstarter, Nr. 2 Value < 0
    assert st["R1C3"][0] == "kein_festkurs"
    assert st["R1C4"][0] == "keine_kandidaten"
    assert st["R1C5"][0] == "araber"
    assert st["R1C6"][0] == "erledigt"


def test_zusammenfuehren_prueft():
    d = dg.zusammenfuehren("2026-11-12", [_rennen("X", (1, "wette", 3.0, 2.5), (2, "klein", 6.0, 5.0), (3, "nein", 9.0, 12))])
    k = d["rennen"][0]["kandidaten"]
    assert [x["einheiten"] for x in k] == [1.0, 0.5, 0.0]
    with pytest.raises(ValueError):
        dg.zusammenfuehren("2026-11-12", [_rennen("X", (1, "halb", 3.0, 2.5))])
    with pytest.raises(ValueError):
        dg.zusammenfuehren("2026-11-12", [_rennen("X", (1, "wette", None, 2.5))])
    with pytest.raises(ValueError):
        dg.zusammenfuehren("2026-11-12", [_rennen("X")])


def test_neuester_durchgang_gilt_und_anwenden(tmp_path):
    a = _schreiben(tmp_path, "durchgang_20261112_1400.json", [_rennen("20261112R1C2", (1, "wette", 3.0, 2.5)),
                                                              _rennen("20261112R1C6", (1, "klein", 5.0, 4.0))])
    b = _schreiben(tmp_path, "durchgang_20261112_1500.json", [_rennen("20261112R1C2", (1, "nein", 3.2, 4.0)),
                                                              {"race_id": "20261112R1C6", "status": "gelaufen"}],
                   stand="2026-11-12T15:00+0100")
    (tmp_path / "durchgang_20261111_0900.json").write_text("{}")          # anderer Tag
    assert dg.dateien(tmp_path, "2026-11-12") == [a, b]
    je = dg.je_rennen([b, a])
    assert je["20261112R1C2"]["kandidaten"][0]["urteil"] == "nein"        # neuerer Durchgang
    assert je["20261112R1C6"]["kandidaten"][0]["urteil"] == "klein"       # im neueren nicht bearbeitet
    karte = _karte()
    d = dg.mit_durchgaengen(karte, tmp_path)
    assert "claude" not in json.dumps(karte)                              # Original unberührt (blinde JSONs)
    c6 = d["races"]["20261112R1C6"]
    assert c6["runners"][0]["claude"]["kennzeichen"] == "BET" and c6["claude"]["vergleich"] == "A > B"
    assert d["races"]["20261112R1C2"]["runners"][0]["claude"]["kennzeichen"] is None
    assert "TABLE" not in dg.tabelle([a, b]) and "R1C6" in dg.tabelle([a, b]) and "R1C2" not in dg.tabelle([a, b])


def test_markieren_html(tmp_path):
    tpl = tmp_path / "tpl.html"
    tpl.write_text("<script>\nconst DATA = /*__DATA__*/null;\n</script>")
    karte = tmp_path / "racecard_20261112.html"
    karte.write_text(dg.html(_karte(), tpl))
    p = _schreiben(tmp_path, "durchgang_20261112_1400.json", [_rennen("20261112R1C2", (1, "wette", 3.0, 2.5))])
    aus = tmp_path / "markiert.html"
    assert dg.markieren(karte, aus, tpl, [p]) == 1
    d = dg.laden(aus)
    assert d["races"]["20261112R1C2"]["runners"][0]["claude"]["kennzeichen"] == "NAP"


def test_template_rendert_kennzeichen():
    t = (Path(dg.__file__).with_name("racecard_template.html")).read_text(encoding="utf-8")
    assert "claudeVals(x, ctx.race)" in t and "r.cTxt" in t and "claude: r.claude || null" in t


# ------------------------------------------------------------ Value-Dashboard: Claude-Tipps

def _claude_pool(tmp_path):
    pool = _zufallspool(tmp_path)
    fertig = pool[pool["settled"]].sort_values(["date", "race_id", "no"])
    rennen: dict[str, list] = {}
    urteile = ["wette", "klein", "nein", "nein", "wette"]
    for i, r in enumerate(fertig.head(40).itertuples()):
        rennen.setdefault(r.date, []).append((r.race_id, int(r.no), urteile[i % 5], float(r.fk_sieg) * 0.9))
    for d, ks in rennen.items():
        je: dict[str, list] = {}
        for rid, no, u, fk in ks:
            je.setdefault(rid, []).append((no, u, round(fk, 2), 2.0))
        (tmp_path / f"durchgang_{d}_1200.json").write_text(json.dumps(dg.zusammenfuehren(
            d, [_rennen(rid, *k) for rid, k in je.items()])))
    with pytest.warns(UserWarning):
        return vb.load_folder(tmp_path, ab=None)


def test_claude_strategie_python(tmp_path):
    pool = _claude_pool(tmp_path)
    assert set(pool["claude"].dropna()) == {"wette", "klein", "nein"}
    res = vb.simulate(pool, vb.FilterConfig(claude=True), vb.StakingConfig("kelly8", wettart="ew"))
    b = res.bets_df
    sel = pool[pool["claude"].isin(["wette", "klein"]) & pool["settled"] & ~pool["nr"].astype(bool)]
    assert len(b) == len(sel) and set(b["stake_win"]) <= {1.0, 0.5} and (b["stake_place"] == 0).all()
    erw = sum(round(e * (fk - 1) - 0.05 * e, 2) if w else round(-e - 0.05 * e, 2)
              for e, fk, w in zip(sel["claude_einh"], sel["claude_fk"], sel["won"]))
    assert res.kpi_dict["profit"] == pytest.approx(erw, abs=0.05)         # Rundung je Wette
    a = {g["gruppe"]: g for g in vb.claude_auswertung(pool)}
    assert a["NAP"]["einsatz"] + a["BET"]["einsatz"] == pytest.approx(b["stake_win"].sum())
    assert a["NAP"]["gewinn_fk"] + a["BET"]["gewinn_fk"] == pytest.approx(res.kpi_dict["profit"])
    assert a["Abgelehnt"]["n"] > 0 and a["Abgelehnt"]["einsatz"] == a["Abgelehnt"]["n"]


def test_claude_strategie_js_gleich_python(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node fehlt")
    pool = _claude_pool(tmp_path)
    t = vb.TEMPLATE.read_text(encoding="utf-8")
    sim = t[t.index("// SIM-START"):t.index("// SIM-END")]
    f = {**vars(vb.FilterConfig(claude=True))}
    (tmp_path / "t.js").write_text(sim + f"\nconst pool = zeilen({json.dumps(vb.dashboard_daten(pool))});\n"
                                   f"console.log(JSON.stringify([simulieren(pool, {json.dumps(f)}, 'kelly8', 1000, 'ew'), claudeAuswertung(pool)]));",
                                   encoding="utf-8")
    js, ausw = json.loads(subprocess.run(["node", str(tmp_path / "t.js")], capture_output=True, text=True, check=True).stdout)
    py = vb.simulate(pool, vb.FilterConfig(claude=True), vb.StakingConfig("kelly8", wettart="ew"))
    assert js["kpi"]["bets"] == py.kpi_dict["bets"] > 5
    assert js["kpi"]["bank"] == pytest.approx(py.kpi_dict["bank"])
    assert [b["profit"] for b in js["bets"]] == pytest.approx(list(py.bets_df["profit"]))
    for a, b in zip(ausw, vb.claude_auswertung(pool)):
        for k in ("gruppe", "n", "siege"):
            assert a[k] == b[k]
        for k in ("einsatz", "gewinn_fk", "roi_fk", "gewinn_toto", "roi_toto"):
            assert a[k] == pytest.approx(b[k]), k
    # ohne Claude-Strategie unverändert: Kandidaten mit gefallenem Kurs zählen nicht als Value-Wetten
    ohne = vb.simulate(pool, vb.FilterConfig(minw=0, mode="none"), vb.StakingConfig("level10"))
    assert ohne.bets_df["wert"].min() > 0
