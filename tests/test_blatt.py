"""Maßstäbe und Kandidaten-Grenze im Skript blatt.py des Skills rennkarten-durchgang-neu."""
import importlib.util
from pathlib import Path

_PFAD = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "rennkarten-durchgang-neu" / "scripts" / "blatt.py"
_spec = importlib.util.spec_from_file_location("blatt", _PFAD)
blatt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(blatt)


def _z(no, fk, value):
    return {"x": {"no": no}, "fk": fk, "value": value}


def nummern(kz):
    return [z["x"]["no"] for z, _ in blatt.massstaebe(kz)]


def test_ist_kandidat_ab_fuenf_prozent():
    assert blatt.ist_kandidat(_z(1, 4.2, 0.05))
    assert not blatt.ist_kandidat(_z(1, 4.0, 0.049))
    assert not blatt.ist_kandidat(_z(1, None, None))


def test_zwei_beste_nach_festkurs_ohne_kandidaten():
    kz = [_z(1, 2.0, -0.1), _z(2, 3.0, -0.2), _z(3, 5.0, -0.3)]
    assert nummern(kz) == [1, 2]


def test_kandidaten_werden_uebersprungen_auch_mehrere():
    kz = [_z(1, 2.0, 0.2), _z(2, 3.0, 0.1), _z(3, 4.0, 0.02), _z(4, 6.0, -0.1), _z(5, 9.0, -0.4)]
    assert nummern(kz) == [3, 4]                        # Nr. 3 mit +2 % ist kein Kandidat mehr


def test_ohne_festkurs_kein_massstab():
    assert nummern([_z(1, None, None)]) == []
    assert nummern([_z(1, 2.0, 0.3), _z(2, 3.0, -0.1)]) == [2]   # nur einer übrig


def _lauf(**k):
    return {"date": "2026-11-01", "course": "PAU", "dist": 1600, "going": "Souple", "type": "Handicap", "pos": 3,
            "ran": 10, "margin": 1.5, **k}


RENNEN = {"course": "PAU", "distance": 1600, "going_label": "Slow"}


def test_kommentar_deutsch_sonst_original():
    assert "„Stark außen beendet.“" in blatt.formzeile(_lauf(comment="A fini fort.", comment_de="Stark außen beendet."), RENNEN)
    assert "„A fini fort.“" in blatt.formzeile(_lauf(comment="A fini fort."), RENNEN)     # ohne Übersetzung
    assert "„" not in blatt.formzeile(_lauf(), RENNEN)


def test_aeltere_laeufe_mit_gleicher_bahn_distanz_boden_bleiben(capsys):
    """Die Karte hängt nach den letzten sieben Läufen ältere mit gleicher Bahn/Distanz/Boden an (extra)."""
    fl = [_lauf(date=f"2026-10-{20 - i:02d}", dist=1200) for i in range(7)]
    fl += [_lauf(date="2025-06-01", extra=["K", "D"]), _lauf(date="2025-05-01", extra=["B"])]
    x = {"no": 3, "horse": "X", "form_lines": fl}
    blatt.blatt({"x": x, "fk": 5.0, "p": 0.2, "rang": 1, "n": 8, "value": 0.1}, {**RENNEN, "race_id": "20261121R1C1"}, 60)
    out = capsys.readouterr().out
    assert out.count("   - 2026-10-") == 7
    assert "Ältere Läufe (zuletzt mit gleicher Bahn, Distanz, Boden):" in out
    assert "   - 2025-06-01" in out and "   - 2025-05-01" in out


def test_laufanalyse_fuer_referenzlauf_und_letzten_lauf():
    rennen = {**RENNEN, "race_id": "20261121R1C1", "date": "2026-11-21",
              "runners": [{"no": 2, "kpi": [["2026-11-01", "PAU", 1600, "SLOW", 30.0], ["2026-06-01", "PAU", 1600, "SLOW", 25.0]]}]}
    f = _lauf(race_id="20261101R1C1", date="2026-11-01", early_pos=9, pos_before=4, pos_before_m=400, fifth=2,
              top3_fifth=[1, 1, 3], pos_gain=4, weg_med=9.0, pace_ratio=103.0, arr_adj=28.0, tr_heute=31,
              rivals_stat={"better": 5, "worse": 2, "ran": 7},
              rivals=[{"horse": "SIEGER", "pos": 1, "next": {"pos": 1, "ran": 9}}])
    x = {"no": 3, "duels": [{"race_id": "20261101R1C1", "rival_no": 4, "rival": "Y", "diff_l": 2.5}],
         "indirect": {"rivals": [{"rival_no": 2, "rival": "Z", "exp_kg": -1.0, "common": ["W"],
                                  "via": [["20261101R1C1", "W", 0.5]]}]}}
    z = blatt.laufanalyse(f, rennen, x)
    assert z.startswith("       Lauf: früh 9. → 400 m vor dem Ziel 4. (Fünftel 2/5; erste drei aus 1, 1, 3)")
    for teil in ("+4 Plätze ab 800 m", "Weg +9 m (außen herum)", "Tempo schnell früh",
                 "ARR-Rang unter den Läufen der heutigen Starter: 30 T 2/2", "TR 31", "Gegner danach 5↑ 2↓",
                 "Sieger SIEGER danach 1./9", "vor 4 Y 2,5 L", "indirekt hinter 2 Z (über W)"):
        assert teil in z, teil
    assert blatt.laufanalyse(_lauf(), rennen, {}) is None       # ohne Daten keine Zeile


def test_analyse_nur_unter_referenzlauf_und_letztem_lauf(capsys):
    fl = [_lauf(date="2026-11-10", dist=1200, pos_gain=1),                 # letzter Lauf, nicht ≈heute
          _lauf(date="2026-11-01", pos_gain=2),                            # Referenzlauf (≈heute)
          _lauf(date="2026-10-01", pos_gain=3)]                            # weder noch
    x = {"no": 3, "horse": "X", "form_lines": fl}
    blatt.blatt({"x": x, "fk": 5.0, "p": 0.2, "rang": 1, "n": 8, "value": 0.1}, {**RENNEN, "race_id": "20261121R1C1"}, 60)
    out = capsys.readouterr().out
    assert "+1 Plätze" in out and "+2 Plätze" in out and "+3 Plätze" not in out


def test_distanzklasse_und_wechsel():
    assert [blatt.distanzklasse(m) for m in (1100, 1400, 1401, 2399, 2400, 2800)] == \
        ["Sprint", "Sprint", "Mitteldistanz", "Mitteldistanz", "Steher", "Extremsteher"]
    assert blatt.distanzwechsel({"distance": 2000}, [_lauf(dist=1600)]) == "Distanz heute 2000 m, letzter Lauf 1600 m (+400 m)"
    assert blatt.distanzwechsel({"distance": 1700}, [_lauf(dist=1600)]) is None          # unter 250 m


def test_nachkommen_nach_distanzklasse():
    tabelle = [["1201-1400 m", 100, 10, 20, 1.0, 1], ["1801-2000 m", 300, 30, 90, 1.0, 1],
               ["2401-2600 m", 50, 5, 20, 1.0, 1], [">3600 m", 2, 1, 2, 1.0, 1]]
    assert blatt.split_distanz(tabelle) == "Sprint 100 L 20 % · Mitteldistanz 300 L 30 % · Steher 50 L 40 % · Extremsteher 2 L 100 %"


def test_vorlieben_mit_platzquote_statt_ae():
    assert blatt.bilanz({"runs": 8, "wins": 0, "places": 2, "ae": 0.93}, quote=True) == "8 L/0 S/2 P (25 %)"
    assert blatt.bilanz({"runs": 8, "wins": 0, "places": 2, "ae": 0.93}) == "8 L/0 S/2 P, A/E 0,93"


def test_qualitaet_der_linie_mit_rang_im_feld():
    def ped(pos, epr, val):
        return {"ae": {"pedigree": {"sire": {"pos_idx": pos, "epr_idx": epr, "max_val3_idx": val, "horses": 50}}}}
    r = {"runners": [{"no": 1, **ped(120, 90, 100)}, {"no": 2, **ped(100, 130, 110)}, {"no": 3, **ped(80, 70, 90)}]}
    assert blatt.linie(r["runners"][0], r) == ("Vater Pos+ 120 (1/3), €/L+ 90 (2/3), maxVal+ 100 (2/3), 50 Nachkommen")


def test_karriere_relativ_zum_feld():
    def k(runs, places, epr):
        return {"career": {"all": {"runs": runs, "wins": 1, "places": places, "epr": epr}}}
    r = {"runners": [{"no": 1, **k(20, 10, 3000)}, {"no": 2, **k(10, 2, 5000)}, {"no": 3, **k(0, 0, None)}]}
    assert blatt.karriere(r["runners"][0], r) == "Karriere 20 L/1 S/10 P: Platzquote 50 % (1/2), Gewinn je Lauf 3 000 € (2/2)"


def test_formzeile_klassenindex_gegen_heute_und_preis():
    z = blatt.formzeile(_lauf(cls_val_idx=82, prize=16300), {**RENNEN, "class": {"val_idx": 75}})
    assert "Kl.-Index 82 (+7)" in z and "Preis 16 k€" in z


def test_ratings_in_reihenfolge_des_nutzers():
    x = {"arr": {"adj": 30.0, "rank": 1, "n": 8, "best": 32.0}, "tr": {"heute": 31, "rank": 2, "n": 8},
         "summary": {"dl600_a": 0.8, "dl600_a_rank": 3, "dl600_a_n": 8}, "rtr": {"rank": 4},
         "duel_rank": {"score_l": 1.2, "rank": 2, "of": 8, "n_direct": 3, "n_indirect": 1}, "draw_stat": {"dev": 0.1}}
    z = blatt.ratings(x)
    assert z.index("ARR") < z.index("TR heute 31 (Rang 2/8)") < z.index("ΔL600 +0,8 km/h (Rang 3/8)") < z.index("RTR") < z.index("Duelle")
    assert "3 direkt, 1 indirekt" in z


def test_crible_original_wenn_uebersetzung_fehlt():
    assert blatt.crible({"prono": {"crible": "Il devrait lutter."}}) == "Il devrait lutter."
    assert blatt.crible({"prono": {"crible": "x", "crible_de": "Deutsch"}}) == "Deutsch"


def test_ae_matrix_relativ_zum_feld():
    def ae(rolle, a, pos, a30=None):
        return {"ae": {rolle: {"d365": {"runs": 100, "ae": a, "pos_idx": pos},
                               "d30": {"runs": 10, "wins": 1, "places": 3, "ae": a30}}}}
    r = {"runners": [{"no": 1, "trainer": "A", **ae("trainer", 1.2, 110, 0.5)}, {"no": 2, "trainer": "B", **ae("trainer", 0.9, 120)},
                     {"no": 3, "trainer": "A", **ae("trainer", 1.2, 110)}]}
    z = blatt.matrix(r["runners"][0], r, "trainer")
    assert z == "365 Tage A/E+ 120 (1/2), Pos+ 110 (2/2) · 30 Tage 10 L/1 S/3 P, A/E 0,50"
    assert blatt.matrix(r["runners"][0], r, "trainer", kurz=False) == "365 Tage A/E+ 120 (1/2), Pos+ 110 (2/2)"


def test_bahnkategorie_und_land():
    assert [blatt.bahnkategorie(b) for b in ("PARISLONGCHAMP", "SAINT CLOUD", "LYON LA SOIE", "MARSEILLE PONT DE VIVAUX",
                                              "TESTE DE BUCH", "MANS", "NEWMARKET")] == \
        ["groß", "groß", "mittel", "mittel", "mittel", "Provinz", None]
    assert [blatt.land(b) for b in ("NEWMARKET", "COLOGNE", "WAREGEM", "DUINDIGT", "MADRID", "PAU")] == \
        ["Großbritannien", "Deutschland", "Belgien", "Niederlande", "Spanien", None]


def test_toto_nur_als_warnung():
    assert blatt.toto({"fk": {"sieg": 18.0, "toto": 41.8}}) == "Toto 41,8 – am Toto kaum gespielt"
    assert blatt.toto({"fk": {"sieg": 18.0, "toto": 20.0}}) is None


def test_kopfzeile_ohne_value_faktor(capsys):
    x = {"no": 3, "horse": "X", "power": {"wert": 1.2, "gold": True}, "badges": ["BF"], "form_lines": []}
    blatt.blatt({"x": x, "fk": 5.0, "p": 0.2, "rang": 1, "n": 8, "value": 0.1}, {**RENNEN, "race_id": "20261121R1C1"}, 60)
    out = capsys.readouterr().out
    assert "Value-Faktor" not in out and "Badges" not in out


def test_starts_relativ_zum_feld():
    r = {"runners": [{"no": 1, "starts": 40}, {"no": 2, "starts": 12}, {"no": 3, "starts": 25}, {"no": 4, "starts": 50, "nr": True}]}
    assert blatt.starts_im_feld(r["runners"][2], r) == "25 Starts (2. meiste von 3 im Feld)"


# ---------------------------------------------------------------- Auslöser und Leitfrage

def _rennen_a(**k):
    return {**RENNEN, "race_id": "20261121R1C1", "type": "Handicap", "going": "Souple", **k}


def _z_a(x, rennen):
    x = {"no": 3, "horse": "X", **x}
    rennen.setdefault("runners", []).append(x)
    return {"x": x, "fk": 5.0, "p": 0.2, "rang": 1, "n": 8, "value": 0.1}


def kennungen_der_ausloeser(liste):
    return [s.split()[0] for s in liste]


def test_ausloeser_referenzlauf_arr_rueckstand_und_alter():
    r = _rennen_a(runners=[{"no": 1, "arr": {"adj": 30.0}}])
    z = _z_a({"arr": {"adj": 26.0}, "form_lines": [_lauf(date="2026-10-01", arr_adj=26.9)]}, r)
    assert blatt.ausloeser(z, r)[0] == "G-ARR-UNTER Referenz-ARR 26,9 liegt 3,1 unter dem Besten im Feld (30,0 #1)"
    z["x"]["form_lines"] = [_lauf(date="2026-10-01", arr_adj=27.1)]           # 2,9 Punkte: kein Auslöser
    assert "G-ARR-UNTER" not in kennungen_der_ausloeser(blatt.ausloeser(z, r))
    z["x"]["form_lines"] = [_lauf(date="2025-10-01", arr_adj=29.0)]           # älter als ein Jahr
    assert blatt.ausloeser(z, r)[0] == "G-KEIN-REFERENZ Referenzlauf 2025-10-01 ist 416 Tage alt"
    z["x"]["form_lines"] = [_lauf(date="2026-10-01", dist=1200)]              # kein Lauf ≈heute
    assert blatt.ausloeser(z, r)[0] == "G-KEIN-REFERENZ kein Lauf ≈heute im Blatt"
    z["x"]["form_lines"] = [_lauf(date="2026-10-01", dist=1200), _lauf(date="2026-03-01", arr_adj=29.0, extra=["D"])]
    assert blatt.ausloeser(z, r)[0] == "Referenzlauf 2026-03-01 steht unter „Ältere Läufe“"


def test_ausloeser_marke_gewicht_startfolge():
    r = _rennen_a(going="Collant", going_label="Very slow")
    fl = [_lauf(date=f"2026-11-{d:02d}", going="Collant") for d in (15, 8, 1)] + [_lauf(date="2026-10-20", going="Collant")]
    z = _z_a({"hcp_mark": {"kind": "sieg", "diff": 1.5}, "weight": 62.0, "form_lines": fl}, r)
    a = blatt.ausloeser(z, r)
    assert "F-AUFGEWICHT/G-UEBER-SIEGMARKE +1,5 kg über der letzten Siegmarke" in a
    assert "G-GEWICHT-BODEN 62,0 kg auf Collant" in a
    assert "G-GEWICHT-KLASSE-BODEN Aufgewicht und ab 62 kg auf Collant/Lourd – Klassenfrage?" in a
    assert "G-STARTFOLGE 4 Starts in 42 Tagen" in a
    z["x"].update(hcp_mark={"kind": "sieg", "diff": 0.5}, weight=61.5)
    a = blatt.ausloeser(z, r)
    assert "F-AUFGEWICHT +0,5 kg über der letzten Siegmarke" in a and "G-GEWICHT-BODEN" not in kennungen_der_ausloeser(a)
    z["x"]["hcp_mark"] = {"kind": "platz", "diff": 3.0}                     # Platzmarke: Siegmarke unbekannt
    assert not any("AUFGEWICHT" in s for s in blatt.ausloeser(z, r))
    r["type"] = "Conditions"                                               # nur im Handicap
    z["x"]["hcp_mark"] = {"kind": "sieg", "diff": 3.0}
    assert not any("AUFGEWICHT" in s for s in blatt.ausloeser(z, r))


def test_ausloeser_verbindungen_pause_trainerwechsel():
    r = _rennen_a()
    z = _z_a({"days": 60, "pref": {"jockey": {"trainer": {"runs": 20, "wins": 0}},
                                   "trainer": {"course": {"runs": 30, "ae": 0.5}},
                                   "horse": {"trainer": [{"runs": 2, "today": True}, {"runs": 9}]}}}, r)
    k = kennungen_der_ausloeser(blatt.ausloeser(z, r))
    assert {"G-GESPANN-OHNE-SIEG", "G-TRAINER-KALT", "F-PAUSE", "F-TRAINERWECHSEL"} <= set(k)
    z["x"].update(days=59, pref={"jockey": {"trainer": {"runs": 20, "wins": 1}},
                                 "trainer": {"course": {"runs": 29, "ae": 0.4}}})
    assert not {"G-GESPANN-OHNE-SIEG", "G-TRAINER-KALT", "F-PAUSE", "F-TRAINERWECHSEL"} & set(kennungen_der_ausloeser(blatt.ausloeser(z, r)))


def test_ausloeser_erstmals_und_abstammung():
    r = _rennen_a(going="Lourd", going_label="Very slow", distance=2400)
    z = _z_a({"cgd": "c◦◦", "abst_pass": {"gesamt": -15},
              "pref": {"horse": {"going": [{"label": "Slow", "runs": 4}, {"label": "Very slow", "runs": 0, "today": True}]}}}, r)
    a = blatt.ausloeser(z, r)
    assert "F-BODEN-NEU erstmals Lourd (Bodengruppe Very slow)" in a
    assert "F-DISTANZ-NEU erstmals diese Distanzgruppe (2400 m)" in a
    assert "G-ABSTAMMUNG gesamt -15, heute 1. Lauf auf Boden" in a
    assert "F-BELAG-NEU" not in kennungen_der_ausloeser(a)
    r2 = _rennen_a(going="PSF STANDARD", going_label="PSF")
    z2 = _z_a({"cgd": "◦◦·", "abst_pass": {"gesamt": -14}, "pref": {"horse": {"going": [{"label": "Slow", "runs": 2}]}}}, r2)
    a2 = blatt.ausloeser(z2, r2)
    assert "F-BELAG-NEU erstmals PSF" in a2 and "G-ABSTAMMUNG" not in kennungen_der_ausloeser(a2)
    assert "F-BODEN-NEU" not in kennungen_der_ausloeser(a2)                # PSF ist kein sehr weicher Boden


def test_ausloeser_ausruestung_cgd_box():
    r = _rennen_a()
    bil = [{"label": "ohne", "runs": 4, "places": 1}, {"label": "australisch", "runs": 5, "places": 5}]
    z = _z_a({"blinkers": "SANS_OEILLERES", "form_lines": [_lauf(blinkers="OEILLERES_AUSTRALIENNES")],
              "pref": {"horse": {"blinkers": bil}}, "cgd": "CgD", "draw": 1, "draw_stat": {"dev": -0.1, "sig": True}}, r)
    a = blatt.ausloeser(z, r)
    assert "G-AUSRUESTUNG-WEG heute ohne, zuletzt australisch: mit 5 L 100 %, ohne 4 L 25 %" in a
    assert "P-CGD CgD" in a and "G-BOX Box 1 signifikant schlechter" in a
    z["x"].update(blinkers="OEILLERES_AUSTRALIENNES", form_lines=[_lauf(blinkers="SANS_OEILLERES")])
    assert "P-AUSRUESTUNG-ZURUECK heute australisch: mit 5 L 100 %, ohne 4 L 25 %" in blatt.ausloeser(z, r)
    z["x"].update(blinkers="OEILLERES_CLASSIQUE")
    assert "F-AUSRUESTUNG-NEU erstmals klassisch" in blatt.ausloeser(z, r)
    bil.reverse(); bil[0]["places"] = 0                                   # mit ihr schwach: kein Auslöser
    z["x"].update(blinkers="SANS_OEILLERES", form_lines=[_lauf(blinkers="OEILLERES_AUSTRALIENNES")])
    assert "G-AUSRUESTUNG-WEG" not in kennungen_der_ausloeser(blatt.ausloeser(z, r))


def test_ausloeser_nennen_nur_gueltige_kennungen():
    import re
    import durchgang
    im_skript = set(re.findall(r"\b[FGPU]-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", _PFAD.read_text(encoding="utf-8")))
    assert im_skript and im_skript <= durchgang.kennungen(), im_skript - durchgang.kennungen()


def test_leitfrage_zeile(capsys):
    r = _rennen_a(runners=[{"no": 1, "horse": "TOP", "arr": {"adj": 30.0}}])
    k = _z_a({"form_lines": [_lauf(date="2026-10-01", arr_adj=27.5)]}, r)
    m = {"x": {"no": 1, "horse": "TOP", "form_lines": [_lauf(date="2025-06-01", arr_adj=30.5)]}}
    blatt.leitfrage(r, [k], [(m, "FK-Favorit")])
    assert capsys.readouterr().out.strip() == ("Leitfrage – Referenz-ARR (ber.) gegen Top-ARR 30,0 (#1): Kandidat 3 X 27,5 "
                                               "(2026-10-01, -2,5) · Maßstab 1: 1 TOP 30,5 (2025-06-01, +0,5, 538 Tage alt)")


def test_ausloeser_im_blatt(capsys):
    x = {"no": 3, "horse": "X", "form_lines": [], "days": 90}
    blatt.blatt({"x": x, "fk": 5.0, "p": 0.2, "rang": 1, "n": 8, "value": 0.1}, {**RENNEN, "race_id": "20261121R1C1"}, 60)
    assert "- Auslöser: G-KEIN-REFERENZ kein Lauf ≈heute im Blatt · F-PAUSE 90 Tage" in capsys.readouterr().out
