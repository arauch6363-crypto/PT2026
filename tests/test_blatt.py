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
