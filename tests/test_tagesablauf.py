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


# ------------------------------------------------------------ Ergebnisse holen / taeglich.py

class _TP:
    def __init__(self, fehler=False):
        self.aufrufe, self.fehler = [], fehler

    def fortschritt(self, base):
        return {"20261110": {}, "_meta": 1}

    def run(self, von, bis, **kw):
        if self.fehler:
            raise ConnectionError("PMU weg")
        self.aufrufe.append((von, kw["max_tage"]))
        return pd.DataFrame({"tag": [von]})


class _PB:
    def __init__(self):
        self.aufrufe = []

    def _fortschritt(self, base):
        return {"erledigt": {}}

    def run(self, base, von):
        self.aufrufe.append(von)
        return {}


class _SZ:
    def __init__(self):
        self.n = 0

    def run(self, base, ab, sammeln_ok=True):
        self.n += 1


def test_ergebnisse_holen_einmal_am_tag(tmp_path, monkeypatch):
    monkeypatch.setattr(ta.pmu, "heute", lambda: date(2026, 11, 15))
    tp, pb, sz = _TP(), _PB(), _SZ()
    e = ta.ergebnisse_holen(tmp_path, log=lambda *a: None, _tp=tp, _pb=pb, _sz=sz)
    assert e["ok"] and not e["uebersprungen"]
    assert tp.aufrufe == [("2026-11-01", 15)]                 # neuester Tag 10.11., aber mindestens 14 Tage zurück
    assert pb.aufrufe == ["2026-11-01"] and sz.n == 1
    assert json.loads((tmp_path / ta.STAND_DATEI).read_text())["datum"] == "2026-11-15"
    e2 = ta.ergebnisse_holen(tmp_path, log=lambda *a: None, _tp=tp, _pb=pb, _sz=sz)
    assert e2["uebersprungen"] and len(tp.aufrufe) == 1      # zweiter Lauf am selben Tag: übersprungen
    ta.ergebnisse_holen(tmp_path, erzwingen=True, log=lambda *a: None, _tp=tp, _pb=pb, _sz=sz)
    assert len(tp.aufrufe) == 2


def test_ergebnisse_holen_fehler_ohne_stand(tmp_path, monkeypatch):
    monkeypatch.setattr(ta.pmu, "heute", lambda: date(2026, 11, 15))
    pb, sz = _PB(), _SZ()
    e = ta.ergebnisse_holen(tmp_path, log=lambda *a: None, _tp=_TP(fehler=True), _pb=pb, _sz=sz)
    assert not e["ok"] and pb.aufrufe and sz.n == 1          # die anderen Schritte laufen trotzdem
    assert not (tmp_path / ta.STAND_DATEI).exists()          # Stand nicht vermerkt: nächster Lauf holt erneut


def test_taeglich_protokoll_und_push(tmp_path, monkeypatch):
    import taeglich
    gesendet = []
    monkeypatch.setenv("NTFY_TOPIC", "test-thema")
    monkeypatch.setattr(taeglich.requests, "post", lambda url, data=None, **kw: gesendet.append((url, data.decode())))
    monkeypatch.setattr(ta, "ergebnisse_holen", lambda base, **kw: {"ok": True})

    def morgen(base, tag, log=print, **kw):
        log("Rennkarte gebaut: racecard_20261115.html")
        log("irgendwas Unwichtiges")
        raise RuntimeError("kaputt")
    monkeypatch.setattr(ta, "morgen", morgen)
    rc = taeglich.main(["--base", str(tmp_path)])
    assert rc == 1
    log = next((tmp_path / "logs").glob("taeglich_*.log")).read_text()
    assert "Rennkarte gebaut" in log and "Tagesablauf fehlgeschlagen: RuntimeError: kaputt" in log
    texte = [t for _, t in gesendet]
    assert all(u == "https://ntfy.sh/test-thema" for u, _ in gesendet)
    assert any("Rennkarte gebaut" in t for t in texte) and any("fehlgeschlagen" in t for t in texte)
    assert not any("Unwichtiges" in t for t in texte)


class _Antwort:
    def __init__(self, code=200):
        self.status_code, self.text = code, "x"

    def json(self):
        return {"claude_code_session_url": "https://claude.ai/code/session_x"}


def test_durchgang_nach_festkursen(tmp_path, monkeypatch):
    monkeypatch.setenv("DURCHGANG_TOKEN", "sk-ant-oat01-test")
    aufrufe = []

    def post(url, headers=None, json=None, timeout=None):
        aufrufe.append((url, headers, json["text"]))
        return _Antwort()
    races = {r["race_id"]: r for r in [_r("20261115R1C1", 1, "13:00", fk=5.0), _r("20261115R1C2", 1, "13:30"),
                                       _r("20261115R1C3", 1, "14:00", fk=4.0, name="PRIX DES PUR-SANG ARABES"),
                                       _r("20261115R2C1", 2, "11:00", fk=3.0, course="LYON")]}
    daten = {"races": races}
    neu = ta.durchgang_nach_festkursen(tmp_path, TAG, daten, "12:00", log=lambda *a: None, _post=post)
    assert neu == ["20261115R1C1"]                     # ohne Festkurs, Araber, schon gestartet: nicht
    url, h, text = aufrufe[0]
    assert url == "https://api.anthropic.com/v1/claude_code/routines/trig_018LVkAy3xCAZHjqQUB9AcDu/fire"
    assert h["Authorization"] == "Bearer sk-ant-oat01-test" and "R1C1" in text
    assert ta.durchgang_nach_festkursen(tmp_path, TAG, daten, "12:05", log=lambda *a: None, _post=post) == []
    races["20261115R1C2"]["runners"][0]["fk"] = {"sieg": 6.0}   # zweite Etappe: neue Festkurse -> neuer Start
    assert ta.durchgang_nach_festkursen(tmp_path, TAG, daten, "12:30", log=lambda *a: None, _post=post) == ["20261115R1C2"]
    assert len(aufrufe) == 2
    # Fehler beim Start: kein Merker, der nächste Aufruf versucht es erneut
    races["20261115R2C1"]["time"] = "18:00"
    assert ta.durchgang_nach_festkursen(tmp_path, TAG, daten, "12:40", log=lambda *a: None,
                                        _post=lambda *a, **k: _Antwort(500)) == []
    assert ta.durchgang_nach_festkursen(tmp_path, TAG, daten, "12:45", log=lambda *a: None, _post=post) == ["20261115R2C1"]


def test_durchgang_ohne_token_oder_fehler(monkeypatch):
    monkeypatch.delenv("DURCHGANG_TOKEN", raising=False)
    meld = []
    assert ta.durchgang_ausloesen("x", log=meld.append, _post=lambda *a, **k: _Antwort()) is False
    assert "kein DURCHGANG_TOKEN" in meld[-1]
    monkeypatch.setenv("DURCHGANG_TOKEN", "t")
    assert ta.durchgang_ausloesen("x", log=meld.append, _post=lambda *a, **k: _Antwort(401)) is False
    assert "HTTP 401" in meld[-1]


def test_durchgang_nur_fuer_heute(tmp_path, monkeypatch):
    monkeypatch.setenv("DURCHGANG_TOKEN", "t")
    daten = {"races": {"20200101R1C1": _r("20200101R1C1", 1, "23:59", fk=5.0)}}
    assert ta.durchgang_nach_festkursen(tmp_path, date(2020, 1, 1), daten, log=lambda *a: None,
                                        _post=lambda *a, **k: _Antwort()) == []


def test_pause_vor_karte_und_zwischen_veranstaltungen(tmp_path):
    """VM-Modus: langer Leerlauf -> Wecken planen und enden; der nächste Lauf setzt mit karte=False fort."""
    rennen = [_r("20261115R1C1", 1, "13:00"), _r("20261115R2C1", 2, "19:00", course="LYON")]
    geweckt = []
    uhr = Uhr("06:50")
    k, d = Karte(tmp_path, uhr, rennen, {"R1": "12:20", "R2": "18:20"}), Dash()
    lauf = lambda **kw: ta.morgen(tmp_path, TAG, jetzt=uhr.jetzt, schlafen=uhr.schlafen, log=lambda *a: None,
                                  pause=lambda z: geweckt.append(z.strftime("%H:%M")) or True,
                                  _racecard=k, _value_bets=d, _boden_fg=FG({}), **kw)
    erg = lauf()
    assert d.n == 1 and not k.runs and geweckt == ["11:20"]      # Karte 11:30, 10 min vorher wecken
    assert erg["pause"] and not uhr.schlaf                       # nicht gewartet
    uhr.t = uhr.t.replace(hour=11, minute=21)                    # nach dem Wecken: Karte bauen, R1-Festkurse
    erg = lauf(dashboard=False)
    assert d.n == 1 and k.runs == ["11:30"] and geweckt[-1] == "18:00"   # R2-Festkurse ab 18:10
    assert erg["festkurse"] == {"R1": "da"} and erg["pause"]
    uhr.t = uhr.t.replace(hour=18, minute=1)
    erg = lauf(dashboard=False, karte=False)
    assert k.runs == ["11:30"] and erg["festkurse"] == {"R1": "da", "R2": "da"} and not erg["pause"]


def test_pause_kurz_oder_nicht_geplant_wartet(tmp_path):
    uhr = Uhr("11:00")                                           # Karte 11:30: nur 30 min -> warten
    k = Karte(tmp_path, uhr, [_r("20261115R1C1", 1, "13:00")], {"R1": "12:20"})
    erg = ta.morgen(tmp_path, TAG, dashboard=False, jetzt=uhr.jetzt, schlafen=uhr.schlafen, log=lambda *a: None,
                    pause=lambda z: 1 / 0, _racecard=k, _boden_fg=FG({}))
    assert k.runs == ["11:30"] and not erg["pause"]
    uhr2 = Uhr("07:00")                                          # Planen schlägt fehl -> wie bisher warten
    k2 = Karte(tmp_path / "b", uhr2, [_r("20261115R1C1", 1, "13:00")], {"R1": "12:20"})
    erg = ta.morgen(tmp_path / "b", TAG, dashboard=False, jetzt=uhr2.jetzt, schlafen=uhr2.schlafen,
                    log=lambda *a: None, pause=lambda z: False, _racecard=k2, _boden_fg=FG({}))
    assert k2.runs == ["11:30"] and not erg["pause"] and erg["festkurse"] == {"R1": "da"}


def test_wecken_planen_gcloud(monkeypatch):
    import types
    import taeglich
    aufrufe = []
    monkeypatch.setenv("PT2026_WECKJOB", "mein-job")
    ok = taeglich.wecken_planen(datetime(2026, 11, 15, 11, 20, tzinfo=PARIS), log=lambda *a: None,
                                _run=lambda cmd, **kw: aufrufe.append(cmd) or types.SimpleNamespace(returncode=0))
    assert ok and aufrufe[0][:6] == ["gcloud", "scheduler", "jobs", "update", "http", "mein-job"]
    assert "--schedule=20 11 15 11 *" in aufrufe[0] and "--time-zone=Europe/Paris" in aufrufe[0]
    nein = taeglich.wecken_planen(datetime(2026, 11, 15, 11, 20, tzinfo=PARIS), log=lambda *a: None,
                                  _run=lambda cmd, **kw: types.SimpleNamespace(returncode=1, stderr="denied", stdout=""))
    assert nein is False


def test_taeglich_fortsetzung_nach_pause(tmp_path, monkeypatch):
    import taeglich
    holen, laeufe = [], []
    monkeypatch.setattr(ta, "ergebnisse_holen", lambda base, **kw: holen.append(1) or {"ok": True})

    def morgen(base, tag, log=print, **kw):
        laeufe.append({k: v for k, v in kw.items() if k != "pause"} | {"pause": "pause" in kw})
        return {"pause": "2026-11-15T11:20:00+01:00"} if len(laeufe) == 1 else {"pause": None}
    monkeypatch.setattr(ta, "morgen", morgen)
    assert taeglich.main(["--base", str(tmp_path), "--pausen"]) == 0
    (tmp_path / "racecards").mkdir()
    (tmp_path / "racecards" / f"racecard_{taeglich.pmu.heute():%Y%m%d}_daten.json").write_text("{}")
    assert taeglich.main(["--base", str(tmp_path), "--pausen"]) == 0
    assert holen == [1]                                          # Ergebnisse nur im ersten Lauf
    assert laeufe[0] == {"dashboard": True, "karte": True, "pause": True}
    assert laeufe[1] == {"dashboard": False, "karte": False, "pause": True}
    assert "Pause" in next((tmp_path / "logs").glob("taeglich_*.log")).read_text()


def test_karte_wiederholt_bei_pmu_fehler(tmp_path):
    uhr = Uhr("11:30")
    k = Karte(tmp_path, uhr, [_r("20261115R1C1", 1, "13:00")], {"R1": "12:10"})
    echt, fehler = k.programm, {"n": 0}

    def programm(tag):
        fehler["n"] += 1
        if fehler["n"] < 3:
            raise RuntimeError("PMU-Programm nicht erreichbar")
        return echt(tag)
    k.programm = programm
    zeilen = []
    erg = ta.morgen(tmp_path, TAG, dashboard=False, jetzt=uhr.jetzt, schlafen=uhr.schlafen, log=lambda *a: zeilen.append(" ".join(map(str, a))),
                    _racecard=k, _boden_fg=FG({}))
    assert fehler["n"] == 3 and k.runs == ["11:36"]              # zwei Fehlversuche, je 3 min Pause
    assert erg["festkurse"] == {"R1": "da"} and sum("neuer Versuch" in z for z in zeilen) == 2
