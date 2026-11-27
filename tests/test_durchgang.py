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


def test_naechster_durchgang():
    k = _karte()                                        # R1: 12:00 … 16:30 (C5 Araber), C3 ohne Festkurs
    k["date"] = "2026-11-12"
    k["races"]["20261112R2C1"] = {"race_id": "20261112R2C1", "reunion": 2, "race_no": 1, "time": "17:00", "name": "PRIX X",
                                  "course": "LYON", "runners": [{"no": 1, "power": {"sieg": 0.5}, "fk": None}]}
    # offene Rennen (Festkurs da, Kandidat): sofort
    n = dg.naechster(k, set(), "11:00")
    assert n["start"] == "2026-11-12T11:02:00[Europe/Paris]" and "R1" in n["grund"]
    # R1 erledigt bis auf C3 ohne Festkurs, erstes R1-Rennen gelaufen -> R1 aufgegeben; R2: 35 min vor 17:00
    erl = {"20261112R1C2", "20261112R1C6"}
    n = dg.naechster(k, erl, "14:30")
    assert n["start"] == "2026-11-12T16:25:00[Europe/Paris]"
    r1 = next(x for x in n["je_reunion"] if x["reunion"] == "R1")
    assert r1["start"] is None and r1["ohne_festkurs"] == ["R1C3"]
    # im Vorlauf-Fenster ohne Festkurse: alle 10 min erneut, bis das erste Rennen startet
    assert dg.naechster(k, erl, "16:40")["start"] == "2026-11-12T16:50:00[Europe/Paris]"
    assert dg.naechster(k, erl, "17:05")["start"] is None
    # Araber allein lösen keinen Durchgang aus
    nur_araber = {"date": "2026-11-12", "races": {"a": {**k["races"]["20261112R1C5"], "time": "18:00"}}}
    assert dg.naechster(nur_araber, set(), "10:00")["start"] is None


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


def test_massstab_wird_uebernommen_und_ist_kein_tipp():
    r = _rennen("X", (1, "nein", 2.2, 2.5))
    r["massstab"] = {"no": "5", "horse": "EL LAGAR", "fk": 2.8, "befund": "sieglos, erstmals 2000 m und PSF"}
    d = dg.zusammenfuehren("2026-11-18", [r])["rennen"][0]
    # früheres Format (ein Objekt) wird zur Liste
    assert d["massstab"] == [{"no": 5, "horse": "EL LAGAR", "fk": 2.8, "befund": "sieglos, erstmals 2000 m und PSF"}]
    assert [k["no"] for k in d["kandidaten"]] == [1]
    assert dg.zusammenfuehren("2026-11-18", [_rennen("X", (1, "nein", 2.2, 2.5))])["rennen"][0]["massstab"] == []
    r["massstab"] = {"horse": "OHNE NUMMER"}
    with pytest.raises(ValueError):
        dg.zusammenfuehren("2026-11-18", [r])


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
    assert "MQ" not in dg.tabelle([a, b])                                   # Mindestquote entfällt (mq nur in alten Dateien)


def test_ohne_mindestquote_lesbar():
    r = _rennen("X", (1, "wette", 3.0, 2.5))
    del r["kandidaten"][0]["mq"]
    k = dg.zusammenfuehren("2026-11-27", [r])["rennen"][0]["kandidaten"][0]
    assert k["mq"] is None and k["fk"] == 3.0


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
    sel = pool[pool["claude"].isin(["wette", "klein"]) & pool["settled"] & ~pool["nr"].astype(bool)]
    # 50 € fest: NAP 50 €, BET 25 €, nur Sieg zum Festkurs beim Durchgang
    res = vb.simulate(pool, vb.FilterConfig(claude=True), vb.StakingConfig("level50", wettart="sieg"))
    b = res.bets_df
    assert len(b) == len(sel) and set(b["stake_win"]) <= {50.0, 25.0} and (b["stake_place"] == 0).all()
    assert (b.loc[b["stake_win"] == 25.0, "horse"].isin(sel.loc[sel["claude"] == "klein", "horse"])).all()
    erw = sum(round(50 * e * (fk - 1) - 0.05 * 50 * e, 2) if w else round(-50 * e - 0.05 * 50 * e, 2)
              for e, fk, w in zip(sel["claude_einh"], sel["claude_fk"], sel["won"]))
    assert res.kpi_dict["profit"] == pytest.approx(erw, abs=0.5)          # Rundung je Wette
    assert res.days_df["bank_start"].iloc[0] == 1000
    a = {g["gruppe"]: g for g in vb.claude_auswertung(pool)}
    assert a["NAP"]["einsatz"] + a["BET"]["einsatz"] == pytest.approx(b["stake_win"].sum())
    assert a["NAP"]["gewinn_fk"] + a["BET"]["gewinn_fk"] == pytest.approx(res.kpi_dict["profit"])
    assert a["Abgelehnt"]["n"] > 0 and a["Abgelehnt"]["einsatz"] == 50 * a["Abgelehnt"]["n"]
    # Each-Way: Platzbein mit gleichem Einsatz zum Platz-Festkurs der Karte
    ew = vb.simulate(pool, vb.FilterConfig(claude=True), vb.StakingConfig("level50", wettart="ew")).bets_df
    mit_p = ew["fk_platz"].notna()
    assert mit_p.any() and (ew.loc[mit_p, "stake_place"] == ew.loc[mit_p, "stake_win"]).all()
    # Kelly: BET ist die Hälfte der vollen Kelly-Wette (vor dem Runden)
    k = vb.simulate(pool, vb.FilterConfig(claude=True), vb.StakingConfig("kelly4", wettart="sieg")).bets_df
    for _, r in k.iterrows():
        voll = 1000 * 0.25 * max(0.0, (r["p"] * r["fk_sieg"] - 1) / (r["fk_sieg"] - 1)) if r["date"] == k["date"].min() else None
        if voll is not None:
            e = float(sel.loc[(sel["race_id"] == r["race_id"]) & (sel["no"] == r["no"]), "claude_einh"].iloc[0])
            assert r["stake_win"] == vb.round_half_up(voll * e)


def test_claude_strategie_js_gleich_python(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node fehlt")
    pool = _claude_pool(tmp_path)
    t = vb.TEMPLATE.read_text(encoding="utf-8")
    sim = t[t.index("// SIM-START"):t.index("// SIM-END")]
    f = {**vars(vb.FilterConfig(claude=True))}
    faelle = [("level50", "sieg"), ("level50", "ew"), ("kelly4", "ew"), ("kelly1", "sieg")]
    (tmp_path / "t.js").write_text(sim + f"\nconst pool = zeilen({json.dumps(vb.dashboard_daten(pool))});\n"
                                   f"console.log(JSON.stringify({json.dumps(faelle)}.map(([v, w]) => "
                                   f"[simulieren(pool, {json.dumps(f)}, v, 1000, w), claudeAuswertung(pool, v, w, 1000)])));",
                                   encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(tmp_path / "t.js")], capture_output=True, text=True, check=True).stdout)
    for (v, w), (js, ausw) in zip(faelle, out):
        py = vb.simulate(pool, vb.FilterConfig(claude=True), vb.StakingConfig(v, wettart=w))
        assert js["kpi"]["bets"] == py.kpi_dict["bets"] > 5, (v, w)
        assert js["kpi"]["bank"] == pytest.approx(py.kpi_dict["bank"]), (v, w)
        assert [b["profit"] for b in js["bets"]] == pytest.approx(list(py.bets_df["profit"])), (v, w)
        for a, b in zip(ausw, vb.claude_auswertung(pool, v, w, 1000)):
            for k in ("gruppe", "n", "siege"):
                assert a[k] == b[k], (v, w, k)
            for k in ("einsatz", "gewinn_fk", "roi_fk", "gewinn_toto", "roi_toto"):
                assert a[k] == pytest.approx(b[k]), (v, w, k)
    # ohne Claude-Strategie unverändert: Kandidaten mit gefallenem Kurs zählen nicht als Value-Wetten
    ohne = vb.simulate(pool, vb.FilterConfig(minw=0, mode="none"), vb.StakingConfig("level10"))
    assert ohne.bets_df["wert"].min() > 0


def test_araber_ueber_ausschreibung():
    import pandas as pd
    import racecard
    r = pd.Series({"race_name": "PRIX DE LA GARONNE", "categorie": "COURSE_A_CONDITIONS",
                   "conditions": "Pour chevaux de 4 ans et au-dessus de pur sang arabe, inscrits au Stud-Book arabe."})
    assert racecard._nicht_vollblut_rennen(r)
    assert not racecard._nicht_vollblut_rennen(pd.Series({"race_name": "PRIX X", "conditions": "Pour tous chevaux de 3 ans."}))
    assert dg.ist_araber({"name": "PRIX DE LA GARONNE", "nicht_vollblut": True})
    assert not dg.ist_araber({"name": "PRIX DE LA GARONNE", "nicht_vollblut": False})


def test_zwei_massstaebe_als_liste():
    r = _rennen("X", (1, "nein", 2.2, 2.5))
    r["massstab"] = [{"no": 5, "horse": "A", "fk": 2.8, "befund": "a"}, {"no": "7", "horse": "B", "fk": 4.0, "befund": "b"}]
    d = dg.zusammenfuehren("2026-11-19", [r])["rennen"][0]
    assert [m["no"] for m in d["massstab"]] == [5, 7]
    r["massstab"] = r["massstab"] + [{"no": 9, "horse": "C", "fk": 6.0, "befund": "c"}]
    with pytest.raises(ValueError):                     # höchstens zwei Maßstäbe
        dg.zusammenfuehren("2026-11-19", [r])


def test_kandidat_braucht_mindestens_fuenf_prozent_value():
    def x(no, p, fk):
        return {"no": no, "power": {"sieg": p}, "fk": {"sieg": fk}}
    r = {"runners": [x(1, 0.25, 4.2), x(2, 0.25, 4.0), x(3, 0.25, 4.19)]}   # Value +5 %, 0 %, +4,75 %
    assert dg.kandidaten(r) == [1]


# ---------------------------------------------------------------- Regelkennungen

def test_kennungen_aus_dem_skill():
    k = dg.kennungen()
    assert {"G-AUSRUESTUNG-WEG", "P-CGD", "F-PAUSE", "U-LEITFRAGE", "G-EXPOSED-ALT"} <= k
    assert all(x[0] in "FGPU" and x[1] == "-" for x in k)


def test_zitierte_kennungen():
    k = {"pro": ["Auf Collant gewonnen (P-BODEN-BEWAEHRT)", "ohne Kennung"], "gegen": ["(G-BOX, G-STUTE)"],
         "fragen": [], "ausschlag": "CGD (P-CGD)"}
    assert dg.zitierte(k) == {"pro": ["P-BODEN-BEWAEHRT"], "gegen": ["G-BOX", "G-STUTE"], "fragen": [],
                              "ausschlag": ["P-CGD"]}


LF = {"referenzlauf": "2026-11-01", "ref_arr": 30.5, "top_arr": 32.0, "massstab_arr": [31.0, None]}


def _streng(*kand, rid="X"):
    r = _rennen(rid, *kand)
    for k in r["kandidaten"]:
        k.update(anker="Modell fair 4, Festkurs 5; nichts verschiebt", leitfrage=dict(LF), ausschlag="Ermessen")
    return r


def test_streng_prueft_kennungen():
    r = _streng((1, "nein", 3.0, 4.0))
    r["kandidaten"][0].update(pro=["gut (P-CGD)"], ausschlag="Leitfrage verneint (U-LEITFRAGE)")
    dg.rennen_pruefen_streng(r)
    r["kandidaten"][0]["ausschlag"] = "Bauchgefühl"
    with pytest.raises(ValueError, match="Ausschlag"):
        dg.rennen_pruefen_streng(r)
    r["kandidaten"][0]["ausschlag"] = "Ermessen: beides vertretbar"
    dg.rennen_pruefen_streng(r)
    r["kandidaten"][0]["gegen"] = ["erfunden (G-GIBT-ES-NICHT)"]
    with pytest.raises(ValueError, match="G-GIBT-ES-NICHT"):
        dg.rennen_pruefen_streng(r)


def test_stillgelegte_kennungen(tmp_path):
    (tmp_path / "SKILL.md").write_text("- `G-A` eins\n- `G-B` zwei\n", encoding="utf-8")
    (tmp_path / "EINSICHTEN.md").write_text(
        "- **[leicht]** `G-A` x\n- **[leicht]** `P-C` y\n\n## Stillgelegte Kennungen\n\n- `G-B` → `G-A`\n",
        encoding="utf-8")
    assert dg.stillgelegt(tmp_path) == {"G-B": "G-A"}
    assert dg.kennungen(tmp_path) == {"G-A", "P-C"}
    echt = dg.stillgelegt()                # im echten Skill: jede stillgelegte zählt unter einer gültigen weiter
    assert set(echt.values()) <= dg.kennungen()
    assert not set(echt) & dg.kennungen()


def test_gestrichene_kennungen(tmp_path):
    (tmp_path / "SKILL.md").write_text("- `G-A` eins\n", encoding="utf-8")
    (tmp_path / "EINSICHTEN.md").write_text(
        "- **[leicht]** `G-A` x\n\n## Stillgelegte Kennungen\n\n- `G-B` → `G-A`\n- `G-X` → gestrichen\n",
        encoding="utf-8")
    assert dg.gestrichen(tmp_path) == {"G-X"}
    assert dg.stillgelegt(tmp_path) == {"G-B": "G-A"}
    assert dg.kennungen(tmp_path) == {"G-A"}
    assert "G-SELTEN-SIEG" in dg.gestrichen() and "G-SELTEN-SIEG" not in dg.kennungen()


def test_veto_und_deckel_maschinenlesbar():
    v = dg.vermerke()
    assert {k for k, x in v.items() if x == "Veto"} == {
        "G-REFERENZ-SCHWACH", "G-DISTANZ-PROBLEME", "G-ABSTAMMUNG", "G-DEBUET-STALL", "G-AUSRUESTUNG-WEG",
        "G-GEWICHT-KLASSE-BODEN", "U-VALUE-DUENN"}
    assert {k for k, x in v.items() if x == "Deckel"} == {
        "G-ARR-UNTER", "G-UEBER-SIEGMARKE", "P-ERSTER-ANSATZ", "G-GESPANN-OHNE-SIEG", "G-MASSSTAB-BESSER"}
    assert set(v) <= dg.kennungen()
    # jede [ausschlaggebend]-Einsicht trägt genau ein Veto, Vetos nur dort
    text = (dg.SKILL_ORDNER / "EINSICHTEN.md").read_text(encoding="utf-8")
    for z in text.splitlines():
        if z.startswith("- **["):
            assert (z.count("**Veto**") == 1) == z.startswith("- **[ausschlaggebend"), z[:60]


def test_streng_kursspanne_bei_tipps():
    r = _streng((1, "wette", 6.0, 5.0))                 # Spanne [4, 5], Festkurs 6 darüber
    dg.rennen_pruefen_streng(r)
    r["kandidaten"][0]["spanne"] = [5, 6.5]
    with pytest.raises(ValueError, match="nicht über der Kursspanne"):
        dg.rennen_pruefen_streng(r)
    r["kandidaten"][0]["spanne"] = []
    with pytest.raises(ValueError, match="ohne Kursspanne"):
        dg.rennen_pruefen_streng(r)
    r["kandidaten"][0].update(urteil="nein")            # nein braucht keine Spanne unter dem Festkurs
    dg.rennen_pruefen_streng(r)


def test_streng_veto_und_deckel():
    v = {"G-AUSRUESTUNG-WEG": "Veto", "G-ARR-UNTER": "Deckel", "P-ERSTER-ANSATZ": "Deckel"}
    r = _streng((1, "klein", 6.0, 5.0))
    k = r["kandidaten"][0]
    k["gegen"] = ["ohne Scheuklappen (G-AUSRUESTUNG-WEG)"]
    with pytest.raises(ValueError, match="Veto"):
        dg.rennen_pruefen_streng(r, vermerk=v)
    k["ausschlag"] = "Ausnahme: mit Scheuklappen nur ein Lauf (Ermessen)"
    dg.rennen_pruefen_streng(r, vermerk=v)
    k.update(gegen=[], fragen=["Scheuklappen weg, aber mit ihnen schwach (G-AUSRUESTUNG-WEG)"], ausschlag="Ermessen")
    dg.rennen_pruefen_streng(r, vermerk=v)              # unter Fragezeichen greift kein Veto
    k.update(urteil="wette", fragen=[], gegen=["ARR 4 unter dem Besten (G-ARR-UNTER)"])
    with pytest.raises(ValueError, match="Deckel"):
        dg.rennen_pruefen_streng(r, vermerk=v)
    k["urteil"] = "klein"
    dg.rennen_pruefen_streng(r, vermerk=v)
    k.update(urteil="wette", gegen=[], pro=["erster Ansatz (P-ERSTER-ANSATZ)"])
    with pytest.raises(ValueError, match="P-ERSTER-ANSATZ"):
        dg.rennen_pruefen_streng(r, vermerk=v)


def test_streng_anker_und_leitfrage():
    r = _streng((1, "nein", 6.0, 5.0))
    k = r["kandidaten"][0]
    k["anker"] = ""
    with pytest.raises(ValueError, match="anker"):
        dg.rennen_pruefen_streng(r)
    k["anker"] = "x"
    del k["leitfrage"]
    with pytest.raises(ValueError, match="leitfrage"):
        dg.rennen_pruefen_streng(r)
    k["leitfrage"] = {**LF, "referenzlauf": "keiner", "ref_arr": None, "massstab_arr": []}
    dg.rennen_pruefen_streng(r)
    k["leitfrage"] = {**LF, "referenzlauf": "1.11."}
    with pytest.raises(ValueError, match="Datum"):
        dg.rennen_pruefen_streng(r)


def test_streng_leitfrage_gegen_karte():
    karte = {"races": {"X": {"race_id": "X", "runners": [
        {"no": 1, "arr": {"adj": 30.04}, "form_lines": [{"date": "2026-11-01"}, {"date": "2026-10-01"}]},
        {"no": 2, "arr": {"adj": 32.0}}, {"no": 3, "nr": True, "arr": {"adj": 40.0}}]}}}
    r = _streng((1, "nein", 6.0, 5.0))
    dg.rennen_pruefen_streng(r, karte=karte)
    r["kandidaten"][0]["leitfrage"]["top_arr"] = 30.0
    with pytest.raises(ValueError, match="Top-ARR 32"):
        dg.rennen_pruefen_streng(r, karte=karte)
    r["kandidaten"][0]["leitfrage"].update(top_arr=32.0, referenzlauf="2026-09-01")
    with pytest.raises(ValueError, match="kein Lauf"):
        dg.rennen_pruefen_streng(r, karte=karte)
    with pytest.raises(ValueError, match="nicht in der Karte"):
        dg.rennen_pruefen_streng(_streng((1, "nein", 6.0, 5.0), rid="Y"), karte=karte)


def test_pruefung_darf_nur_senken():
    r = _streng((1, "klein", 6.0, 5.0))
    k = r["kandidaten"][0]
    k.update(urteil_vor_pruefung="wette", pruefung="Referenzlauf falsch gelesen: 3. statt 1.")
    out = dg.rennen_pruefen_streng(r)
    assert out["kandidaten"][0]["urteil_vor_pruefung"] == "wette"
    k["pruefung"] = ""
    with pytest.raises(ValueError, match="pruefung"):
        dg.rennen_pruefen_streng(r)
    k.update(urteil_vor_pruefung="nein", pruefung="x")
    with pytest.raises(ValueError, match="nur senken"):
        dg.rennen_pruefen_streng(r)


def test_neue_felder_kommen_an_und_alte_dateien_bleiben_lesbar(tmp_path):
    r = _streng((1, "klein", 6.0, 5.0), rid="20261112R1C6")
    r["kandidaten"][0].update(urteil_vor_pruefung="wette", pruefung="Veto übersehen")
    p = _schreiben(tmp_path, "durchgang_20261112_1400.json", [r])
    k = json.loads(p.read_text())["rennen"][0]["kandidaten"][0]
    assert k["leitfrage"] == LF and k["anker"] and k["pruefung"] == "Veto übersehen" and k["urteil_vor_pruefung"] == "wette"
    alt = _rennen("20261112R1C2", (1, "wette", 3.0, 2.5))      # ohne neue Felder, mit mq
    q = _schreiben(tmp_path, "durchgang_20261112_1300.json", [alt])
    d = dg.mit_durchgaengen(_karte(), tmp_path)
    c6 = d["races"]["20261112R1C6"]["runners"][0]["claude"]
    assert c6["pruefung"] == "Veto übersehen" and c6["leitfrage"]["top_arr"] == 32.0
    c2 = d["races"]["20261112R1C2"]["runners"][0]["claude"]
    assert c2["mq"] == 2.5 and c2["leitfrage"] is None and c2["urteil_vor_pruefung"] is None
    assert "R1C6" in dg.tabelle([p, q]) and "R1C2" in dg.tabelle([p, q])


def test_pruefen_cli(tmp_path):
    f = tmp_path / "r.json"
    f.write_text(json.dumps(_streng((1, "nein", 6.0, 5.0))), encoding="utf-8")
    aus = subprocess.run([sys.executable, "-I", str(Path(dg.__file__)), "pruefen", str(f)], capture_output=True, text=True)
    assert aus.returncode == 0 and aus.stdout.startswith("ok X")
    f.write_text(json.dumps(_rennen("X", (1, "nein", 6.0, 5.0))), encoding="utf-8")
    aus = subprocess.run([sys.executable, "-I", str(Path(dg.__file__)), "pruefen", str(f)], capture_output=True, text=True)
    assert aus.returncode != 0 and "FEHLER" in aus.stderr
