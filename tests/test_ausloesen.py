"""Payload für den Wett-Agenten aus einem Durchgang (agent_wettstar/ausloesen.py)."""
import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parents[1] / "agent_wettstar" / "ausloesen.py"
_spec = importlib.util.spec_from_file_location("ausloesen", _p)
au = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(au)


def _l(no, horse, p, sieg, fk, nr=False):
    return {"no": no, "horse": horse, "nr": nr, "power": {"p": p, "sieg": sieg}, "fk": {"sieg": fk}}


LAEUFER = {
    1: [_l(16, "STARAC", 110, 0.162, 8.5), _l(13, "ROULETTE", 105, 0.154, 8.5), _l(3, "NR-PFERD", 130, 0.3, 9.0, nr=True)],
    4: [_l(8, "VEGAWAN", 120, 0.30, 3.0), _l(2, "SALMY", 100, 0.204, 12.0)],          # Rang 1 ohne Value
    6: [_l(14, "SUPERCLASS", 115, 0.217, 6.5), _l(1, "CHERRY PIE", 90, 0.15, 6.0)],   # Rang 1, von Claude abgelehnt
}


def _karte():
    rennen = {f"20261124R1C{i}": {"race_id": f"20261124R1C{i}", "reunion": 1, "race_no": i, "time": t,
                                  "course": "DEAUVILLE", "runners": LAEUFER[i]}
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
        ("SALMY", "BET", "15:40", "DEAUVILLE", "R1C4", 7.0),
        ("SUPERCLASS", "MODELL", "16:50", "DEAUVILLE", "R1C6", 4.61)]
    assert len(weg) == 1 and "nicht in der Karte" in weg[0]          # „nein“ nie, unbekanntes Rennen weggelassen


def test_gestartete_rennen_fallen_weg():
    ts, weg = au.tipps(_karte(), _dg(), "13:53")                     # 13:55 liegt in der Vorlaufgrenze
    assert [t["name"] for t in ts] == ["SALMY", "SUPERCLASS"]
    assert sum("zu nah oder vorbei" in w for w in weg) == 2


def test_payload_dry_run():
    ts, _ = au.tipps(_karte(), _dg(), "13:00")
    assert "dry_run" not in au.payload(_dg(), "durchgang_20261124_1310.json", ts)
    assert au.payload(_dg(), "x.json", ts, dry_run=True)["dry_run"] is True


def test_doppelte_tipps_fallen_weg():
    ts, _ = au.tipps(_karte(), _dg(), "13:00")
    sessions = [
        {"metadata": {"wett_datum": "2026-11-24", "dry_run": "0", "wett_tipps": "20261124R1C1-16"}},
        {"metadata": {"wett_datum": "2026-11-24", "dry_run": "1", "wett_tipps": "20261124R1C4-2"}},   # Dry-Run zählt nicht
        {"metadata": {"wett_datum": "2026-11-23", "dry_run": "0", "wett_tipps": "20261124R1C1-13"}},  # anderer Tag
        {"metadata": {}},
    ]
    geschickt = au.schon_geschickt(sessions, "2026-11-24")
    assert geschickt == {"20261124R1C1-16"}
    neu, weg = au.ohne_doppelte(ts, geschickt)
    assert [t["name"] for t in neu] == ["ROULETTE", "SALMY", "SUPERCLASS"]
    assert len(weg) == 1 and "STARAC" in weg[0]


def test_modell_erster():
    assert au.modell_erster({"runners": LAEUFER[1]}) == [
        {"no": 16, "horse": "STARAC", "fk": 8.5, "p": 0.162, "min_fk": 6.18}]       # NR-Pferd zählt nicht
    assert au.modell_erster({"runners": LAEUFER[4]}) == []                             # Value 3,0 × 0,30 − 1 < 0
    gleich = [_l(1, "A", 100, 0.25, 5.0), _l(2, "B", 100, 0.25, 4.5)]
    assert [(m["no"], m["min_fk"]) for m in au.modell_erster({"runners": gleich})] == [(1, 4.01), (2, 4.01)]  # Gleichstand: beide Rang 1, Break-even 4,0 → 4,01


def test_p_im_tipp_und_startbank():
    karte, dg = _karte(), _dg()
    dg["rennen"][0]["kandidaten"][1]["p_modell"] = 0.154               # ROULETTE: p aus dem Durchgang
    ts, _ = au.tipps(karte, dg, "13:00")
    p = {t["name"]: t["p"] for t in ts}
    assert p["ROULETTE"] == 0.154                                      # p_modell aus dem Durchgang
    assert p["STARAC"] == 0.162                                        # sonst power.sieg aus der Karte
    assert p["SALMY"] == 0.204                                         # power.sieg aus der Karte
    assert p["SUPERCLASS"] == 0.217                                    # MODELL: power.sieg
    ev = [{"type": "agent.message", "content": [{"type": "text", "text": "Ich starte."}]},
          {"type": "agent.tool_result", "content": [{"type": "text", "text": "Guthaben 174.21, benötigt gesamt 68.25\nX"}]}]
    assert au.startbank_aus_events(ev) == 174.21
    assert au.startbank_aus_events([]) is None
