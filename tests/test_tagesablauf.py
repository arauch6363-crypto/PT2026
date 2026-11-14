import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

import tagesablauf as ta

PARIS = ta.PARIS
TAG = date(2026, 11, 15)


def _r(rid, reunion, zeit, fk=None, course="TOULOUSE", going_source="PMU", name="PRIX"):
    return {"race_id": rid, "reunion": reunion, "race_no": int(rid[-1]), "time": zeit, "course": course,
            "name": name, "going_source": going_source,
            "runners": [{"no": 1, "fk": {"sieg": fk} if fk else None}, {"no": 2, "fk": {"sieg": fk} if fk else None}]}


class Uhr:
    def __init__(self, hhmm):
        self.t = datetime.combine(TAG, datetime.min.time(), PARIS) + timedelta(minutes=ta._hm(hhmm))
        self.schlaf = []

    def jetzt(self):
        return self.t

    def schlafen(self, s):
        self.schlaf.append(s)
        self.t += timedelta(seconds=s)


class Karte:
    """Ersatz für racecard: run schreibt Kartendaten, festkurse_aktualisieren setzt Festkurse ab einer Uhrzeit."""
    def __init__(self, base, uhr, rennen, fk_ab, boden_annahme=False):
        self.base, self.uhr, self.rennen, self.fk_ab, self.annahme = base, uhr, rennen, fk_ab, boden_annahme
        self.runs, self.fk_aufrufe = [], []

    def programm(self, tag):
        return pd.DataFrame({"post_time": [r["time"] for r in self.rennen]}), pd.DataFrame()

    def daten_pfad(self, out):
        return Path(out).with_name(Path(out).stem + "_daten.json")

    def _pfad(self):
        return self.daten_pfad(self.base / "racecards" / f"racecard_{TAG:%Y%m%d}.html")

    def run(self, base, tag, festkurse=True, uebersetzen_aktiv=True):
        assert festkurse is False and uebersetzen_aktiv is False
        self.runs.append(self.uhr.jetzt().strftime("%H:%M"))
        quelle = "Annahme" if self.annahme and len(self.runs) == 1 else "PMU"
        d = {"races": {r["race_id"]: {**r, "going_source": quelle if r["course"] == "VICHY" else "PMU"} for r in self.rennen}}
        self._pfad().parent.mkdir(parents=True, exist_ok=True)
        self._pfad().write_text(json.dumps(d))
        return self._pfad().with_suffix("")

    def festkurse_aktualisieren(self, base, tag):
        jetzt = self.uhr.jetzt().strftime("%H:%M")
        self.fk_aufrufe.append(jetzt)
        d = json.loads(self._pfad().read_text())
        for rid, r in d["races"].items():
            if ta._hm(jetzt) >= ta._hm(self.fk_ab.get(f"R{r['reunion']}", "99:99")):
                for x in r["runners"]:
                    x["fk"] = {"sieg": 5.0}
        self._pfad().write_text(json.dumps(d))

    @staticmethod
    def _bahn_schluessel(name, eintraege):
        return name if name in eintraege else None


class Dash:
    def __init__(self):
        self.n = 0

    def start(self, base):
        self.n += 1


class FG:
    def __init__(self, boden):
        self.boden = boden

    def tag(self, d):
        return self.boden


def test_ablauf_zwei_veranstaltungen(tmp_path):
    uhr = Uhr("07:00")
    rennen = [_r("20261115R1C1", 1, "13:00"), _r("20261115R1C2", 1, "13:30"),
              _r("20261115R2C1", 2, "16:00", course="LYON"),
              _r("20261115R2C3", 2, "15:40", course="LYON", name="PRIX DES PUR-SANG ARABES")]
    k, d = Karte(tmp_path, uhr, rennen, {"R1": "12:20", "R2": "15:20"}), Dash()
    erg = ta.morgen(tmp_path, TAG, jetzt=uhr.jetzt, schlafen=uhr.schlafen, log=lambda *a: None,
                    _racecard=k, _value_bets=d, _boden_fg=FG({}))
    assert d.n == 1
    assert k.runs == ["11:30"]                                  # 90 min vor 13:00
    assert k.fk_aufrufe[0] == "12:10"                           # R1 ab 50 min vorher
    assert "12:20" in k.fk_aufrufe and "15:10" in k.fk_aufrufe and "15:20" in k.fk_aufrufe   # R2 ab 15:10 (Araber zählt nicht)
    assert not [t for t in k.fk_aufrufe if "12:20" < t < "15:10"]                           # dazwischen Ruhe
    assert erg["festkurse"] == {"R1": "da", "R2": "da"}


def test_festkurse_kommen_nicht_rechtzeitig(tmp_path):
    uhr = Uhr("12:00")
    k = Karte(tmp_path, uhr, [_r("20261115R1C1", 1, "13:00")], {"R1": "14:00"})
    erg = ta.morgen(tmp_path, TAG, dashboard=False, jetzt=uhr.jetzt, schlafen=uhr.schlafen, log=lambda *a: None,
                    _racecard=k, _boden_fg=FG({}))
    assert k.runs == ["12:00"]                                  # zu spät gestartet: sofort bauen
    assert k.fk_aufrufe[0] == "12:10" and k.fk_aufrufe[-1] < "13:00"
    assert erg["festkurse"]["R1"].startswith("erstes Rennen gelaufen")


def test_boden_annahme_wird_nachgeholt(tmp_path):
    uhr = Uhr("08:00")
    rennen = [_r("20261115R1C1", 1, "14:00", course="VICHY")]
    k = Karte(tmp_path, uhr, rennen, {"R1": "13:20"}, boden_annahme=True)
    erg = ta.morgen(tmp_path, TAG, dashboard=False, jetzt=uhr.jetzt, schlafen=uhr.schlafen, log=lambda *a: None,
                    _racecard=k, _boden_fg=FG({"VICHY": {"terrain": "Souple", "wert": 3.4, "psf": False}}))
    assert k.runs == ["12:30", "13:05"] and erg["boden_neu"]   # neu gebaut kurz vor den Festkursen
    assert erg["festkurse"]["R1"] == "da"


def test_kein_rennen(tmp_path):
    uhr = Uhr("08:00")
    k = Karte(tmp_path, uhr, [], {})
    erg = ta.morgen(tmp_path, TAG, dashboard=False, jetzt=uhr.jetzt, schlafen=uhr.schlafen, log=lambda *a: None,
                    _racecard=k, _boden_fg=FG({}))
    assert erg["karte"] is None and not k.runs
