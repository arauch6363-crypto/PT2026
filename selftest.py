#!/usr/bin/env python3
"""
Selbsttest ohne Internet.

PMU und France Galop werden durch eine kleine Attrappe ersetzt, damit die
Logik nachvollziehbar prüfbar ist:

  * nur französische Flachrennen, die bereits gelaufen sind
  * Tracking wird je Rennen geprüft, nicht je Bahn
  * eine Bahn ohne Tracking an einem Tag wird am nächsten Tag wieder geprüft
  * ein Bahncode wird nur gelernt, wenn der Bahnname im PDF dazu passt
  * nachträglich veröffentlichte PDFs werden beim nächsten Lauf gefunden

Aufruf:  python selftest.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

import france_galop as fg
import parse_tracking as pt
import pipeline as tp
import pmu

HEUTE = date.today()
T1 = HEUTE - timedelta(days=1)          # gestern
T2 = HEUTE - timedelta(days=2)


# --------------------------------------------------------------------------
# Attrappe: PMU-Programm
# --------------------------------------------------------------------------
def _course(no, spec="PLAT", statut="FIN_COURSE", arrivee=(3, 1, 2)):
    return {"numOrdre": no, "libelle": f"PRIX NR {no}", "specialite": spec, "discipline": spec,
            "statut": statut, "distance": 1600, "montantPrix": 25000,
            "heureDepart": int(datetime(2026, 1, 1, 13, 0).timestamp() * 1000),
            "nombreDeclaresPartants": 3, "ordreArrivee": [[a] for a in arrivee] if arrivee else None}


def _reunion(num, bahn, code, courses, pays="FRA"):
    return {"numOfficiel": num, "pays": {"code": pays},
            "hippodrome": {"libelleLong": bahn, "libelleCourt": bahn, "code": code},
            "courses": courses}


PROGRAMM = {
    T1: [
        _reunion(1, "HIPPODROME DE CHANTILLY", "CHY", [
            _course(1), _course(2),
            _course(3, spec="HAIE"),                      # Hindernis -> raus
            _course(4, statut="COURSE_ANNULEE", arrivee=None),   # abgesagt -> raus
            _course(5),                                   # gelaufen, aber ohne Tracking-PDF
        ]),
        _reunion(2, "HIPPODROME DE MOULINS", "MOU", [_course(1), _course(2)]),      # Code noch unbekannt
        _reunion(3, "HIPPODROME DE CHATEAUBRIANT", "CTB", [_course(1)]),            # Code unbekannt, kein Tracking
        _reunion(4, "VINCENNES", "VIN", [_course(1, spec="ATTELE")]), # Trab -> raus
        _reunion(5, "ASCOT", "ASC", [_course(1)], pays="GBR"),        # Ausland -> raus
        _reunion(6, "CRAON", "ZZZ", [_course(i) for i in (1, 2, 3, 4, 5)]),
        _reunion(7, "HIPPODROME DE SAINT-MALO", "S-M", [_course(1), _course(2)]),
    ],
    T2: [
        # gleiche Bahn, an diesem Tag ohne Tracking – darf nicht dauerhaft ausgeschlossen werden
        _reunion(1, "HIPPODROME DE MOULINS", "MOU", [_course(1)]),
        _reunion(2, "CHANTILLY", "CHY", [_course(1)]),      # anderes Namensfeld, gleicher PMU-Code
        _reunion(3, "CRAON", "ZZZ", [_course(1)]),
    ],
}

# Welche Tracking-PDFs gibt es bei France Galop? name -> Bahnname im PDF-Kopf
PDFS: dict[str, str] = {
    f"{T1:%Y%m%d}CHA01_last_times_fr": "CHANTILLY",
    f"{T1:%Y%m%d}CHA02_last_times_fr": "CHANTILLY",
    f"{T1:%Y%m%d}CHA03_last_times_fr": "CHANTILLY",     # Hindernisrennen, wird gar nicht angefragt
    f"{T1:%Y%m%d}MOU01_last_times_fr": "MOULINS",
    f"{T1:%Y%m%d}MOU02_last_times_fr": "MOULINS",
    f"{T2:%Y%m%d}CHA01_last_times_fr": "CHANTILLY",
    f"{T1:%Y%m%d}CRA04_last_times_fr": "CRAON",     # nur hintere Rennen -> am T1 nicht auffindbar
    f"{T1:%Y%m%d}CRA05_last_times_fr": "CRAON",
    f"{T2:%Y%m%d}CRA01_last_times_fr": "CRAON",     # hier wird der Code gelernt
    f"{T1:%Y%m%d}S-M01_last_times_fr": "SAINT-MALO",
    f"{T1:%Y%m%d}S-M02_last_times_fr": "SAINT-MALO",
}
ANGEFRAGT: list[str] = []
SUCHLOG: list[str] = []


def merk_log(text):
    SUCHLOG.append(str(text))
    print(text)


def wurde_geraten(bahn: str) -> bool:
    """Wurde für diese Bahn geraten? (Erfolgsmeldungen zählen nicht.)"""
    return any(bahn in z and "rate Kandidaten" in z for z in SUCHLOG)


def _fake_pdf(track: str) -> bytes:
    kopf = (f"Statistiques Tracking {track} C1 - PRIX DU TEST - 1600m samedi 19 septembre 2026 - 14:30 "
            "Redk du 1er: 1'35\"40 Tronçons de 200m")
    return b"%PDF-1.4\n" + kopf.encode() + b"\n" + b"x" * 2000


class FakeResponse:
    def __init__(self, content=b"", status=200, text=""):
        self.content, self.status_code, self._text = content, status, text

    @property
    def ok(self):
        return self.status_code < 400

    @property
    def text(self):
        return self._text or self.content.decode("latin-1", "ignore")

    def json(self):
        import json
        return json.loads(self._text)


class FakeSession:
    def get(self, url, headers=None, timeout=None, **kw):
        import json
        if "turfinfo" in url:
            if "/participants" in url:
                return FakeResponse(text=json.dumps({"participants": [
                    {"numPmu": i, "nom": f"PFERD {i}", "statut": "PARTANT", "age": 4, "sexe": "M",
                     "jockey": "A. Test", "entraineur": "B. Test", "ordreArrivee": i,
                     "handicapPoids": 570, "distanceChevalPrecedent": {"libelleCourt": "1 L"},
                     "dernierRapportDirect": {"rapport": 3.4 + i}} for i in (1, 2, 3)]}))
            d = url.rstrip("/").split("/")[-1]
            tag = datetime.strptime(d, "%d%m%Y").date()
            return FakeResponse(text=json.dumps({"programme": {"reunions": PROGRAMM.get(tag, [])}}))
        if "france-galop" in url:
            name = url.split("/")[-1][:-4]
            ANGEFRAGT.append(name)
            track = PDFS.get(name)
            return FakeResponse(_fake_pdf(track)) if track else FakeResponse(b"<html>404</html>", 404)
        return FakeResponse(status=404)


# --------------------------------------------------------------------------
# Attrappe: PDF lesen / auswerten
# --------------------------------------------------------------------------
def fake_read_pages(path: Path, engine: str):
    return [path.read_bytes().decode("latin-1", "ignore").split("\n")[1]], []


def fake_parse_pdf(path: Path, race_id: str | None = None):
    track = path.read_bytes().decode("latin-1", "ignore").split("\n")[1].split("Tracking ")[1].split(" C1")[0]
    return {"race": {"race_id": race_id, "track": track, "race_type": "Flach", "file": path.name,
                     "distance_m": 1600, "runners": 3},
            "leader": [{"race_id": race_id, "seg": "T1", "leader_cum_s": 12.3, "leader_split_s": 12.3}],
            "runners": [{"race_id": race_id, "horse": f"PFERD {i}", "saddle_no": i, "place": str(i),
                         "official_time_s": 95.0 + i, "status": "gelaufen"} for i in (1, 2, 3)],
            "sections": [{"race_id": race_id, "horse": "PFERD 1", "saddle_no": 1, "m_to_go": 0,
                          "seg_len_m": 200, "split_s": 11.5}],
            "obstacles": [], "errors": []}


# --------------------------------------------------------------------------
# Prüfungen
# --------------------------------------------------------------------------
fehler: list[str] = []


def pruefe(bedingung, text):
    print(("  OK   " if bedingung else "  FEHL ") + text)
    if not bedingung:
        fehler.append(text)


def main() -> int:
    requests_session_orig = pt.read_pages
    fg.requests.Session = FakeSession
    tp.requests.Session = FakeSession
    pmu.requests.Session = FakeSession
    pt.read_pages = fake_read_pages
    pt.parse_pdf = fake_parse_pdf

    _orig_tracking = fg.tracking_fuer_tag
    fg.tracking_fuer_tag = lambda *a, **kw: _orig_tracking(*a, **{**kw, "log": merk_log})

    tmp = Path(tempfile.mkdtemp(prefix="pt_selftest_"))
    base, pdfs = tmp / "drive", tmp / "drive" / "pdfs"
    base.mkdir(parents=True)

    print("\n1) Bahnnamen-Gegenprüfung (verhindert, dass CHATEAUBRIANT den Code CHA von CHANTILLY erbt)")
    pruefe(fg.passt_bahn(_fake_pdf("CHANTILLY"), "CHANTILLY") is True, "CHANTILLY-PDF passt zu CHANTILLY")
    pruefe(fg.passt_bahn(_fake_pdf("CHANTILLY"), "CHATEAUBRIANT") is False,
           "CHANTILLY-PDF passt NICHT zu CHATEAUBRIANT")
    pruefe(fg.passt_bahn(_fake_pdf("PARISLONGCHAMP"), "PARISLONGCHAMP") is True, "PARISLONGCHAMP passt")
    pruefe("CHA" not in fg.kandidaten("CHATEAUBRIANT", "CTB", verboten={"CHA"}),
           "bereits vergebene Codes werden als Kandidat ausgeschlossen")

    print("\n1b) Bahnnamen aus dem PMU-Programm")
    pruefe(pmu.norm("HIPPODROME DE CHANTILLY") == "CHANTILLY", "Vorsatz 'Hippodrome de' wird entfernt")
    pruefe(pmu.norm("HIPPODROME DU MANS") == "MANS", "auch 'Hippodrome du'")
    pruefe(pmu.norm("HIPPODROME BORDEAUX LE BOUSCAT") == "BORDEAUX LE BOUSCAT", "auch ohne 'de'")
    pruefe(pmu.norm("DEAUVILLE") == "DEAUVILLE", "kurze Namen bleiben unverändert")
    s_ = fg.CodeStore(tmp / "leer"); (tmp / "leer").mkdir(exist_ok=True)
    pruefe(s_.code("HIPPODROME DE CHANTILLY") == "CHA",
           "bekannter Bahncode greift auch beim langen PMU-Namen")
    pruefe("CHA" not in s_.belegte_codes(ausser="HIPPODROME DE CHANTILLY"),
           "eine Bahn sperrt sich ihren eigenen Code nicht selbst")
    pruefe(s_.code("DEAUVILLE CLAIREFONTAINE") == "",
           "DEAUVILLE CLAIREFONTAINE erbt nicht den Code von DEAUVILLE")

    print("\n1c) PMU-Bahncode als Schlüssel (Namensfelder wechseln, der Code bleibt)")
    d2 = tmp / "codes2"; d2.mkdir()
    pd.DataFrame([
        {"hippodrome": "TOULOUSE LA CEPIERE", "pmu_code": "CEP", "fg_code": "CEP",
         "gefunden_am": "2026-09-16", "versuche": "0", "letzter_versuch": "", "quelle": "gefunden"},
        {"hippodrome": "LA CEPIERE", "pmu_code": "CEP", "fg_code": "",
         "gefunden_am": "", "versuche": "1", "letzter_versuch": "2026-09-16", "quelle": ""},
    ]).to_csv(d2 / "track_codes.csv", index=False)
    s2 = fg.CodeStore(d2)
    pruefe(len(s2.df) == 1, "Dubletten aus alten Schreibweisen werden zusammengeführt")
    pruefe(s2.code("LA CEPIERE", "CEP") == "CEP" and s2.code("TOULOUSE LA CEPIERE", "CEP") == "CEP",
           "Bahn wird unter beiden Namensvarianten gefunden")
    pruefe("CEP" not in s2.belegte_codes(ausser="LA CEPIERE", pmu_code="CEP"),
           "auch bei abweichendem Namen sperrt die Bahn ihren eigenen Code nicht")
    pruefe(not s2.soll_suchen("LA CEPIERE", T1, pmu_code="CEP"),
           "für eine Bahn mit bekanntem Code wird nicht erneut gesucht")

    print("\n1d) Der France-Galop-Code ist der PMU-Bahncode")
    echte_paare = [("TOULOUSE LA CEPIERE", "CEP"), ("NANTES", "PET"), ("SAINT MALO", "S-M"),
                   ("LES SABLES D OLONNE", "LSO"), ("LE MANS", "MAN"), ("BORELY", "BOR"),
                   ("GUADELOUPE", "KRK"), ("LE BOUSCAT", "BOU")]
    pruefe(all(fg.code_aus_pmu(c) == c for _, c in echte_paare),
           "bestätigte Codes werden unverändert übernommen (auch 'S-M')")
    pruefe(fg.code_aus_pmu("XX/Y") == "" and fg.code_aus_pmu("") == "",
           "unbrauchbare Codes werden verworfen statt in einen Dateinamen gebaut")

    print("\n2) Erster Lauf (gestern)")
    bericht = tp.run(T2, T1, base=base, pdf_dir=pdfs, max_tage=1, pause=0)
    st = tp.lade("tracking_status", base)
    pr = tp.lade("pmu_races", base)
    pruefe(set(st["date"]) == {T1.strftime("%Y%m%d")}, "nur der eine angeforderte Tag wurde geholt")
    pruefe(set(st["hippodrome"]) == {"CHANTILLY", "MOULINS", "CHATEAUBRIANT", "CRAON", "SAINT MALO"},
           "Trab (VINCENNES) und Ausland (ASCOT) sind draußen")
    ch = st[st["hippodrome"] == "CHANTILLY"]
    pruefe(sorted(ch["race_no"]) == [1, 2, 5],
           "CHANTILLY: Hindernisrennen (C3) und abgesagtes Rennen (C4) sind draußen")
    pruefe(bool(ch.set_index("race_no").loc[1, "tracking"]) and bool(ch.set_index("race_no").loc[2, "tracking"])
           and not bool(ch.set_index("race_no").loc[5, "tracking"]),
           "CHANTILLY: C1/C2 mit Tracking, C5 ohne – pro Rennen entschieden")
    pruefe(not any(n.endswith("CHA03_last_times_fr") for n in ANGEFRAGT),
           "das Hindernisrennen C3 wurde gar nicht erst angefragt")
    pruefe(not wurde_geraten("CHANTILLY"),
           "für CHANTILLY wurde kein Bahncode gesucht – der Seed-Code greift sofort")
    mo = st[st["hippodrome"] == "MOULINS"]
    pruefe(list(mo["fg_code"].unique()) == ["MOU"] and mo["tracking"].all(),
           "MOULINS: unbekannter Bahncode wurde gefunden und beide Rennen geladen")
    cb = st[st["hippodrome"] == "CHATEAUBRIANT"]
    pruefe(len(cb) == 1 and not cb["tracking"].iloc[0] and cb["fg_code"].iloc[0] == "",
           "CHATEAUBRIANT: kein Code gefunden – und kein fremder Code untergeschoben")
    codes = pd.read_csv(base / "track_codes.csv").fillna("")
    cbz = codes[codes["hippodrome"] == "CHATEAUBRIANT"]
    pruefe(len(cbz) == 1 and cbz["fg_code"].iloc[0] == "" and int(cbz["versuche"].iloc[0]) == 1,
           "CHATEAUBRIANT ist als Fehlversuch vermerkt, nicht als 'kein Tracking'")
    pruefe(len(pr) == len(st) == 13, "zu jedem gelaufenen Flachrennen gibt es eine PMU- und eine Statuszeile")
    pruefe(set(tp.lade("tracking_races", base)["race_id"]) <= set(pr["race_id"]),
           "Tracking- und PMU-Tabellen benutzen dieselbe race_id")
    pruefe(len(tp.lade("pmu_runners", base)) == 39, "Starterdaten zu allen 13 Rennen geholt")
    sm = st[st["hippodrome"] == "SAINT MALO"]
    pruefe(list(sm["fg_code"].unique()) == ["S-M"] and sm["tracking"].all(),
           "SAINT MALO: Code 'S-M' aus dem PMU-Code übernommen, Bindestrich bleibt erhalten")
    pruefe(not wurde_geraten("SAINT MALO"),
           "für SAINT MALO wurde nichts geraten – der PMU-Code genügt")
    cr = st[st["hippodrome"] == "CRAON"]
    pruefe(not cr["tracking"].any() and set(cr["fg_code"]) == {""},
           "CRAON: Code an diesem Tag nicht gefunden, obwohl es PDFs gäbe")

    print("\n3) Zweiter Lauf (Tag davor) – Bahn ohne Tracking an diesem Tag")
    tp.run(T2, T1, base=base, pdf_dir=pdfs, max_tage=1, pause=0)
    st2 = tp.lade("tracking_status", base)
    mo2 = st2[(st2["date"] == T2.strftime("%Y%m%d")) & (st2["hippodrome"] == "MOULINS")]
    pruefe(len(mo2) == 1 and not mo2["tracking"].iloc[0] and mo2["fg_code"].iloc[0] == "MOU",
           "MOULINS wurde trotz bekanntem Code geprüft und hat an diesem Tag kein Tracking")
    ch2 = st2[(st2["date"] == T2.strftime("%Y%m%d")) & (st2["hippodrome"] == "CHANTILLY")]
    pruefe(bool(ch2["tracking"].iloc[0]), "CHANTILLY hat am Vortag Tracking – Bahn bleibt in Betrieb")
    pruefe(f"{T2:%Y%m%d}MOU01_last_times_fr" in ANGEFRAGT,
           "die Bahn wurde am zweiten Tag erneut abgefragt und nicht ausgeschlossen")
    pruefe(not wurde_geraten("CHANTILLY"),
           "CHANTILLY unter kurzem Namen: keine erneute Codesuche")

    print("\n3b) Ein später gelernter Bahncode trägt frühere Tage nach")
    st_cr = tp.lade("tracking_status", base)
    cr1 = st_cr[(st_cr["date"] == T1.strftime("%Y%m%d")) & (st_cr["hippodrome"] == "CRAON")]
    pruefe(cr1["fg_code"].iloc[0] == "CRA", "CRAON hat am ersten Tag jetzt den gelernten Code")
    pruefe(int(cr1["tracking"].sum()) == 2,
           "die beiden zunächst verfehlten CRAON-Rennen wurden nachgetragen")

    print("\n4) Nachzügler: France Galop veröffentlicht ein PDF verspätet")
    PDFS[f"{T1:%Y%m%d}CHA05_last_times_fr"] = "CHANTILLY"
    tp.run(T2, T1, base=base, pdf_dir=pdfs, max_tage=1, pause=0)
    st3 = tp.lade("tracking_status", base)
    c5 = st3[(st3["date"] == T1.strftime("%Y%m%d")) & (st3["hippodrome"] == "CHANTILLY") & (st3["race_no"] == 5)]
    pruefe(bool(c5["tracking"].iloc[0]), "das nachgereichte PDF wurde beim nächsten Lauf gefunden")
    state = tp.fortschritt(base)
    pruefe(f"{T1:%Y%m%d}R3C1" in state[T1.strftime("%Y%m%d")]["offen"],
           "das Rennen in CHATEAUBRIANT bleibt offen")

    print("\n5) Abdeckung")
    ab = tp.abdeckung(base)
    print(ab.to_string())
    pruefe(ab.loc["CHANTILLY", "mit_tracking"] == 4, "CHANTILLY: 4 Rennen mit Tracking")
    pruefe(ab.loc["CRAON", "mit_tracking"] == 3, "CRAON: 3 Rennen mit Tracking (2 nachgetragen + 1)")
    pruefe(ab.loc["CHATEAUBRIANT", "quote_%"] == 0.0, "CHATEAUBRIANT: 0 %")
    pruefe(len(tp.ohne_tracking(base)) == 5, "fünf Rennen ohne Tracking-PDF übrig")
    pruefe(ab.loc["SAINT MALO", "quote_%"] == 100.0, "SAINT MALO: 100 %")

    print("\n6) Doppelte Läufe schreiben nichts doppelt")
    vorher = len(tp.lade("pmu_races", base))
    tp.run(T2, T1, base=base, pdf_dir=pdfs, max_tage=5, pause=0)
    pruefe(len(tp.lade("pmu_races", base)) == vorher, "Rennanzahl unverändert")

    pt.read_pages = requests_session_orig
    print("\n" + ("Alle Prüfungen bestanden." if not fehler else f"{len(fehler)} Prüfung(en) fehlgeschlagen:"))
    for f in fehler:
        print("  -", f)
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
