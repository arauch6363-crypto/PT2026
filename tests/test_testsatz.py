"""Tests für testsatz.py: Testsatz des Skills rennkarten-durchgang-neu (ADR 0002)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import testsatz as ts  # noqa: E402


@pytest.mark.parametrize("nutzer, skill, punkte", [
    ("nein", "nein", 0), ("klein", "klein", 0), ("wette", "wette", 0),
    ("nein", "wette", 2), ("nein", "klein", 1), ("klein", "wette", 1),      # Fehlwette: doppelt
    ("wette", "nein", 1), ("klein", "nein", 0.5), ("wette", "klein", 0.5),  # verpasster Kandidat
])
def test_fehlerpunkte(nutzer, skill, punkte):
    assert ts.fehlerpunkte({"urteil": nutzer}, skill) == punkte


def test_ermessen_naechstes_erlaubtes_urteil_zaehlt():
    e = {"urteil": "nein", "erlaubt": ["klein"]}
    assert ts.fehlerpunkte(e, "klein") == 0
    assert ts.fehlerpunkte(e, "wette") == 1       # Abstand zu klein, nicht zu nein


ERWARTET = {"R1": {"kandidaten": {"2": {"horse": "A", "urteil": "nein"}, "5": {"horse": "B", "urteil": "klein"}}}}


def _lauf(race_id, **urteile):
    return {"race_id": race_id, "status": "bearbeitet",
            "kandidaten": [{"no": int(no[1:]), "urteil": u} for no, u in urteile.items()]}


def test_testfall_ueber_drei_laeufe():
    laeufe = [_lauf("R1", n2="nein", n5="klein", n7="wette"),     # Nr. 7 ohne Urteil des Nutzers: zählt nicht
              _lauf("R1", n2="klein", n5="klein"),
              _lauf("R1", n2="nein", n5="nein")]
    t = ts.testfall(ERWARTET["R1"], laeufe)
    assert t["richtig"] == [True, False, False]
    assert t["punkte"] == pytest.approx((0 + 1 + 0.5) / 3)
    assert t["stand"] == "mehrheitlich falsch"


def test_testfall_stand():
    richtig = _lauf("R1", n2="nein", n5="klein")
    falsch = _lauf("R1", n2="wette", n5="klein")
    assert ts.testfall(ERWARTET["R1"], [richtig] * 3)["stand"] == "stabil richtig"
    assert ts.testfall(ERWARTET["R1"], [richtig, richtig, falsch])["stand"] == "schwankend"


def test_fehlender_kandidat_gilt_als_nicht_gespielt():
    t = ts.testfall(ERWARTET["R1"], [_lauf("R1", n2="nein")])
    assert t["punkte"] == 0.5 and t["fehlt"] == [5]


def test_ausschnitt_enthaelt_nur_das_rennen():
    daten = {"date": "2026-11-16", "generated": "x", "festkurse_bahnen": {"A": "11:00"}, "history": [1] * 9,
             "races": [{"race_id": "20261116R1C1"}, {"race_id": "20261116R1C2"}]}
    a = ts.ausschnitt(daten, "20261116R1C2")
    assert a == {"date": "2026-11-16", "generated": "x", "festkurse_bahnen": {"A": "11:00"},
                 "races": [{"race_id": "20261116R1C2"}]}
    with pytest.raises(KeyError):
        ts.ausschnitt(daten, "20261116R9C9")


def test_bewerten_und_rueckschritt(tmp_path):
    erwartet = {"R1": ERWARTET["R1"], "R2": {"kandidaten": {"1": {"horse": "C", "urteil": "wette"}}}}
    gut = {"R1": [_lauf("R1", n2="nein", n5="klein")] * 3, "R2": [_lauf("R2", n1="wette")] * 3}
    e1 = ts.bewerten(erwartet, gut)
    assert e1["trefferquote"] == 1 and e1["punkte"] == 0
    ts.ablegen(tmp_path, e1, commit="aaa", datum="2026-11-19")

    schlecht = {"R1": [_lauf("R1", n2="wette", n5="klein")] * 2 + [gut["R1"][0]], "R2": gut["R2"]}
    e2 = ts.bewerten(erwartet, schlecht)
    assert e2["trefferquote"] == pytest.approx(4 / 6) and e2["punkte"] == pytest.approx(4 / 3)
    assert ts.rueckschritte(ts.letztes(tmp_path), e2) == ["R1"]
    zeilen = (tmp_path / "verlauf.csv").read_text(encoding="utf-8").splitlines()
    assert zeilen == ["datum,commit,testfaelle,trefferquote,punkte,rueckschritte", "2026-11-19,aaa,2,1.000,0.00,"]


def test_bewerten_ohne_lauf_fuer_einen_testfall():
    with pytest.raises(ValueError, match="R1"):
        ts.bewerten({"R1": ERWARTET["R1"]}, {})


def test_laeufe_laden(tmp_path):
    import json
    for n in (1, 2):
        (tmp_path / f"20261116R4C1_{n}.json").write_text(json.dumps(_lauf("20261116R4C1", n1="nein")))
    l = ts.laeufe_laden(tmp_path)
    assert list(l) == ["20261116R4C1"] and len(l["20261116R4C1"]) == 2


def test_bericht_empfiehlt_nur_ohne_rueckschritt_und_mehr_punkte():
    erwartet = {"R1": ERWARTET["R1"]}
    gut = ts.bewerten(erwartet, {"R1": [_lauf("R1", n2="nein", n5="klein")] * 3})
    schlecht = ts.bewerten(erwartet, {"R1": [_lauf("R1", n2="wette", n5="klein")] * 3})
    vorher = {"datum": "2026-11-19", "commit": "aaa", **gut}
    assert "Übernehmen: ja" in ts.bericht(gut, vorher, erwartet)
    b = ts.bericht(schlecht, vorher, erwartet)
    assert "Übernehmen: nein" in b and "Rückschritte: R1" in b and "A nein, B klein" in b


def test_ausschnitt_aus_races_als_dict():
    daten = {"date": "2026-11-16", "races": {"20261116R1C1": {"race_id": "20261116R1C1"}}}
    assert ts.ausschnitt(daten, "20261116R1C1")["races"] == [{"race_id": "20261116R1C1"}]


def test_ablegen_verweigert_ohne_uebernahme_und_vergleicht_mit_letzter_ablage(tmp_path):
    erwartet = {"R1": ERWARTET["R1"]}
    gut = ts.bewerten(erwartet, {"R1": [_lauf("R1", n2="nein", n5="klein")] * 3})
    schlecht = ts.bewerten(erwartet, {"R1": [_lauf("R1", n2="wette", n5="klein")] * 3})
    ts.ablegen(tmp_path, gut, commit="zzz", datum="2026-11-19")
    ts.ablegen(tmp_path, gut, commit="aaa", datum="2026-11-19")      # gleicher Tag: zuletzt abgelegt zählt
    assert ts.letztes(tmp_path)["commit"] == "aaa"
    with pytest.raises(ValueError, match="nicht übernehmen"):
        ts.ablegen(tmp_path, schlecht, commit="bbb", datum="2026-11-20")
    assert ts.letztes(tmp_path)["commit"] == "aaa"
