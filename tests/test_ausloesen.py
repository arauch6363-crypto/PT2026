"""Payload für den Wett-Agenten aus einem Durchgang (agent_wettstar/ausloesen.py)."""
import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parents[1] / "agent_wettstar" / "ausloesen.py"
_spec = importlib.util.spec_from_file_location("ausloesen", _p)
au = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(au)


def _karte():
    rennen = {f"20261124R1C{i}": {"race_id": f"20261124R1C{i}", "reunion": 1, "race_no": i, "time": t,
                                  "course": "DEAUVILLE", "runners": []}
              for i, t in ((1, "13:55"), (4, "15:40"), (6, "16:50"))}
    return {"date": "2026-11-24", "races": rennen}


def _dg():
    k = lambda no, h, u, fk, mq: {"no": no, "horse": h, "urteil": u, "fk": fk, "mq": mq}
    return {"datum": "2026-11-24", "rennen": [
        {"race_id": "20261124R1C1", "status": "bearbeitet",
         "kandidaten": [k(16, "STARAC", "wette", 8.5, 6.0), k(13, "ROULETTE", "klein", 8.5, 7.0), k(8, "TAMYZ", "nein", 12, 13)]},
        {"race_id": "20261124R1C4", "status": "bearbeitet", "kandidaten": [k(2, "SALMY", "klein", 12.0, 7.0)]},
        {"race_id": "20261124R1C6", "status": "bearbeitet", "kandidaten": [k(14, "SUPERCLASS", "nein", 6.5, 7.0)]},
        {"race_id": "20261124R1C9", "status": "bearbeitet", "kandidaten": [k(1, "NIRGENDS", "wette", 5.0, 4.0)]},
    ]}


def test_nap_bet_mit_bahn_und_zeit():
    ts, weg = au.tipps(_karte(), _dg(), "13:00")
    assert [(t["name"], t["kennzeichen"], t["zeit"], t["bahn"], t["rennen"], t["mq"]) for t in ts] == [
        ("ROULETTE", "BET", "13:55", "DEAUVILLE", "R1C1", 7.0),
        ("STARAC", "NAP", "13:55", "DEAUVILLE", "R1C1", 6.0),
        ("SALMY", "BET", "15:40", "DEAUVILLE", "R1C4", 7.0)]
    assert len(weg) == 1 and "nicht in der Karte" in weg[0]          # „nein“ nie, unbekanntes Rennen weggelassen


def test_gestartete_rennen_fallen_weg():
    ts, weg = au.tipps(_karte(), _dg(), "13:53")                     # 13:55 liegt in der Vorlaufgrenze
    assert [t["name"] for t in ts] == ["SALMY"]
    assert sum("zu nah oder vorbei" in w for w in weg) == 2


def test_payload_dry_run():
    ts, _ = au.tipps(_karte(), _dg(), "13:00")
    assert "dry_run" not in au.payload(_dg(), "durchgang_20261124_1310.json", ts)
    assert au.payload(_dg(), "x.json", ts, dry_run=True)["dry_run"] is True
