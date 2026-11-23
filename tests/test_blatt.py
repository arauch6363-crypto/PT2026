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
