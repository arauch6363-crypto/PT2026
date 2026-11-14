from datetime import date

import pandas as pd

import boden_fg
import racecard as rc

SEITE = """<html><body><div>Aujourd'hui / 15 novembre 2026</div><div>Date</div>
<div>AUTEUIL</div><div>Horaire : 11h43</div><div>Terrain collant (4,2)</div><div>Obstacle : 8</div>
<div>TOULOUSE</div><div>Horaire : 16h40</div><div>Terrain tr souple (3,8)</div><div>Plat : 8</div>
<div>PORNICHET</div><div>Horaire : 16h47</div><div>Terrain PSF STANDARD</div><div>Plat : 8</div>
<div>MOULINS</div><div>Horaire : 12h30</div><div>Plat : 7</div><div>A noter :</div>
<div>CHELTENHAM</div><div>Horaire : 13h20</div><div>Plat : 1 , Obstacle : 5</div></body></html>"""


def test_lesen():
    d, b = boden_fg.lesen(SEITE)
    assert d == date(2026, 11, 15)
    assert b["TOULOUSE"] == {"terrain": "Très souple", "wert": 3.8, "psf": False, "roh": "Terrain tr souple (3,8)"}
    assert b["AUTEUIL"]["terrain"] == "Collant" and b["PORNICHET"]["psf"]
    assert "MOULINS" not in b and "CHELTENHAM" not in b             # noch ohne Terrain


def test_alle_werte_aus_boden_manuell():
    import json
    import rtr_arr
    m = json.loads(rc.BODEN_DATEI.read_text(encoding="utf-8"))["moegliche_angaben"]
    for gruppe, werte in m.items():
        for w in werte:
            for v in (w, w.lower(), w.upper(), w.lower().replace("très", "tr"), w.lower().replace("très", "tr.")):
                assert boden_fg.terrain_begriff(v) == w and rtr_arr.boden_gruppe(w) == gruppe, v


def test_unbekannter_begriff_wird_gemeldet(monkeypatch):
    seite = SEITE.replace("Terrain tr souple (3,8)", "Terrain gelé (3,8)")
    _, b = boden_fg.lesen(seite)
    assert b["TOULOUSE"]["terrain"] is None

    class Antwort:
        text = seite
        def raise_for_status(self):
            pass

    class S:
        def get(self, *a, **k):
            return Antwort()
    meldungen = []
    monkeypatch.setattr(boden_fg, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: pd.Timestamp(date(2026, 11, 15)))}))
    erg = boden_fg.tag(date(2026, 11, 15), S(), log=meldungen.append)
    assert "TOULOUSE" not in erg and any("gelé" in m for m in meldungen)


def test_begriffe():
    assert [boden_fg.terrain_begriff(x) for x in ("tr souple", "bon souple", "tr léger", "lourd", "xyz")] == \
        ["Très souple", "Bon souple", "Très léger", "Lourd", None]


def test_tag_falscher_tag_und_netzfehler(monkeypatch):
    class Antwort:
        text = SEITE
        def raise_for_status(self):
            pass

    class S:
        def get(self, *a, **k):
            return Antwort()
    heute = date(2026, 11, 15)
    monkeypatch.setattr(boden_fg, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: pd.Timestamp(heute))}))
    assert boden_fg.tag(heute, S(), log=lambda *a: None)["TOULOUSE"]["wert"] == 3.8
    assert boden_fg.tag(date(2026, 11, 16), S(), log=lambda *a: None) == {}       # Seite „demain“ zeigt den 15.

    class Kaputt:
        def get(self, *a, **k):
            raise ConnectionError("weg")
    assert boden_fg.tag(heute, Kaputt(), log=lambda *a: None) == {}
    assert boden_fg.tag(date(2026, 11, 20), S(), log=lambda *a: None) == {}       # nur gestern/heute/morgen


def test_reihenfolge_der_quellen():
    _, fg = boden_fg.lesen(SEITE)
    rr = pd.DataFrame([
        {"hippodrome": "TOULOUSE", "going": "Bon", "going_value": 3.1, "track_type": "HERBE", "parcours": None},
        {"hippodrome": "TOULOUSE LA CEPIERE", "going": None, "going_value": None, "track_type": "HERBE", "parcours": None},
        {"hippodrome": "PORNICHET", "going": None, "going_value": None, "track_type": "PSF", "parcours": None},
        {"hippodrome": "AUTEUIL", "going": None, "going_value": None, "track_type": "HERBE", "parcours": None},
        {"hippodrome": "VICHY", "going": None, "going_value": None, "track_type": "HERBE", "parcours": None}])
    ra = rc.boden_manuell_anwenden(rr, {"AUTEUIL": "Souple"}, fg)
    assert list(ra["going_quelle"]) == ["PMU", "France Galop", "PSF", "manuell", "Annahme"]
    assert list(ra["going"])[:4] == ["Bon", "Très souple", "PSF", "Souple"]
    assert ra["going_value"].iloc[0] == 3.1 and ra["going_value"].iloc[1] == 3.8    # PMU-Wert bleibt, sonst France Galop
    assert pd.isna(ra["going_value"].iloc[3])                                       # manuell: kein Wert
    assert rc.going_klasse(ra["going"].iloc[1]) == "SLOW"
