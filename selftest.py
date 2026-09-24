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

    print("\n7) Race Card: A/E, Vorlieben, Formzeilen")
    racecard_pruefen()

    pt.read_pages = requests_session_orig
    print("\n" + ("Alle Prüfungen bestanden." if not fehler else f"{len(fehler)} Prüfung(en) fehlgeschlagen:"))
    for f in fehler:
        print("  -", f)
    return 1 if fehler else 0


def racecard_pruefen() -> None:
    import numpy as np
    import racecard as rc
    import speedfig as sf
    tag = date(2026, 9, 23)
    rid = lambda d, n: f"{tag - timedelta(days=d):%Y%m%d}R1C{n}"
    races = pd.DataFrame([
        {"race_id": rid(10, 1), "hippodrome": "DEAUVILLE", "distance_m": 1200, "going": "Bon",
         "going_value": "3,1", "prize_eur": 27000, "categorie": "HANDICAP"},
        {"race_id": rid(100, 1), "hippodrome": "VICHY", "distance_m": 2000, "going": "Lourd",
         "going_value": "4,5", "prize_eur": 15000, "categorie": "A_RECLAMER"},
    ])
    lauf = lambda r, no, horse, tr, pos, odds, **kw: {
        "race_id": r, "saddle_no": no, "horse": horse, "sire": "VATER", "jockey": "J. OCKEY", "trainer": tr,
        "status": "PARTANT", "finish_pos": pos, "odds_final": odds, "weight_kg": 57, "age": 4, "sex": "MALES",
        "blinkers": "SANS_OEILLERES", "lengths_prev": None if pos == 1 else 2.0,
        "lengths_behind": None if pos == 1 else 2.0, **kw}
    runners = pd.DataFrame([lauf(rid(10, 1), 1, "X", "TR", 1, 4.0), lauf(rid(10, 1), 2, "Y", "TR", 2, 2.0),
                            lauf(rid(100, 1), 1, "X", "TR", 2, 5.0), lauf(rid(100, 1), 2, "Y", "AND", 1, 3.0),
                            lauf(rid(100, 1), 3, "Z", "AND", 2, 9.0)])       # totes Rennen um Platz 2
    # Abschnitte 1200 m: DEP-1000, 1000-800, ... je 200 m; Pferd 1 sauber, Pferd 2 mit falscher Zeit
    splits = {1: (12.6, 11.9, 11.7, 11.5, 11.3, 11.6), 2: (12.6, 11.9, 11.7, 11.5, 11.3, 9.0)}
    sections = pd.DataFrame([{"race_id": rid(10, 1), "saddle_no": no, "m_to_go": m, "seg_len_m": 200,
                              "split_s": t, "cum_s": sum(splits[no][:k + 1]),
                              "position": {800: 2, 400: 1, 200: 1, 0: 1}.get(m)}
                             for no in (1, 2) for k, (m, t) in enumerate(zip((1000, 800, 600, 400, 200, 0), splits[no]))])
    leader = pd.DataFrame([{"race_id": rid(10, 1), "seg": f"T{k + 1}", "from": f_, "to": to, "leader_cum_s": c,
                            "leader_split_s": None}
                           for k, (f_, to, c) in enumerate(zip(("DEP", "1000m", "800m", "600m", "400m", "200m"),
                                                               ("1000m", "800m", "600m", "400m", "200m", "ARR"),
                                                               (12.4, 24.2, 35.8, 47.2, 58.4, 70.0)))])
    hist = rc.vorbereiten(races, runners, pd.DataFrame([{"race_id": rid(10, 1), "pace_ratio": 97.0}]),
                          pd.DataFrame([{"race_id": rid(10, 1), "saddle_no": 1, "finish_index": 104.0,
                                         "dist_vs_winner_m": 0.0, "speed_last600_kmh": 55.0,
                                         "distance_covered_m": 1212.0, "last600_s": 34.4},
                                        {"race_id": rid(10, 1), "saddle_no": 2, "dist_vs_winner_m": 13.31,
                                         "speed_last600_kmh": 63.0, "last600_s": 34.5}]), sections, leader)
    im_rennen = hist["race_id"] == rid(10, 1)
    hx = hist[im_rennen & (hist["horse"] == "X")].iloc[0]
    pruefe(abs(hx["speed_last600_kmh"] - 600 / 34.4 * 3.6 * 1.01) < 0.02 and hx["path_factor"] == 1.01,
           "L600 aus den Abschnitten neu gebildet (geparster Wert 55 ersetzt) und mit Wegfaktor skaliert")
    pruefe(abs(hx["finish_index"] - (400 / 22.9) / (800 / 47.7) * 100) < 0.1,
           "Finish-Index = Endspeed ÷ Tempo davor (nicht der geparste 104.0)")
    pruefe(hist.loc[hist["horse"] == "Y", "speed_last600_kmh"].isna().all()
           and bool(hist.loc[im_rennen & (hist["horse"] == "Y"), "last600_mismatch"].all()),
           "Gegenprobe: L600 verworfen, wenn die Abschnitte von der offiziellen Angabe abweichen")
    pruefe(abs(hx["pace_early_kmh"] - 600 / 35.8 * 3.6) < 0.02,
           "frühes Tempo ohne Spalte pace_early_kmh aus tracking_leader ersetzt")
    heute_r = pd.DataFrame([{"race_id": f"{tag:%Y%m%d}R1C1", "reunion": 1, "race_no": 1, "hippodrome": "DEAUVILLE",
                             "distance_m": 1200, "going": "Bon", "going_value": "4,8", "categorie": "HANDICAP"}])
    heute_s = pd.DataFrame([{**lauf(f"{tag:%Y%m%d}R1C1", 1, "X", "TR", None, 3.0, blinkers="OEILLERES_CLASSIQUE"),
                             "finish_pos": None},
                            {**lauf(f"{tag:%Y%m%d}R1C1", 2, "Y", "NEU", None, 3.0, sex="HONGRES"),
                             "finish_pos": None}])
    d = rc.baue_daten(hist, heute_r, heute_s, tag)
    x, y = d["races"][f"{tag:%Y%m%d}R1C1"]["runners"]
    pruefe(x["ae"]["trainer"]["d90"] == {"runs": 2, "wins": 1, "places": 2, "exp": 0.75, "ae": 1.33},
           "Trainer-A/E 90 Tage = 1 Sieg / (1/4 + 1/2) = 1,33")
    pruefe(x["ae"]["trainer"]["d365"]["runs"] == 3 and x["ae"]["trainer"]["d365"]["ae"] == 1.05,
           "Trainer-A/E 365 Tage schließt den Lauf vor 100 Tagen ein (1 / 0,95 = 1,05)")
    pruefe(rc._ae_trend({"runs": 6, "ae": 1.6}, {"runs": 90, "ae": 1.0}) == "hot"
           and rc._ae_trend({"runs": 12, "ae": 0.3}, {"runs": 90, "ae": 1.0}) == "cold"
           and rc._ae_trend({"runs": 3, "ae": 3.0}, {"runs": 90, "ae": 1.0}) is None,
           "Feuer/Eis: 30 Tage deutlich über/unter 365 Tagen, erst ab 5 Starts")
    boden = x["pref"]["horse"]["going"]
    pruefe(boden[0]["label"] == "Bon" and boden[0]["today"] and (boden[0]["runs"], boden[0]["wins"]) == (1, 1)
           and {z["label"] for z in boden} == {"Bon", "Lourd"},
           "Pferd nach Boden: alle Böden, der heutige (Bon laut PMU) oben markiert")
    dist = x["pref"]["horse"]["distance"]
    pruefe(dist[0]["label"] == "1200 m" and dist[0]["today"] and len(dist) == 2, "Pferd nach Distanz: 1200 m heute markiert")
    pruefe(x["pref"]["trainer"]["course"]["runs"] == 2, "Trainer in Deauville: 2 Läufe (letzte zwei Jahre)")
    pruefe(x["badges"] == ["CD"] and "BF" in y["badges"],
           "CD für den Bahn-/Distanzsieger, BF für den geschlagenen Favoriten")
    wx = {c["key"] for c in x["changes"]}
    wy = {c["key"] for c in y["changes"]}
    pruefe(wx == {"b1"} and wy == {"TR", "g1"}, "Wechsel: erstmals Scheuklappen, Trainerwechsel, erstmals Wallach")
    f = x["form_lines"][0]
    pruefe((f["pos"], f["ran"], f["fifth"], f["pos_before"], f["pace_ratio"], f["margin"]) == (1, 2, 3, 1, 97.0, 2.0),
           "Formzeile: 1/2, Siegabstand 2 L, Position 400 m vor dem Ziel = 1 -> Fünftel 3, Pace 97")
    pruefe(y["form_lines"][0]["weg_med"] == 6.7, "Weg: Meter gegenüber dem Median des Feldes (13,31 − 6,66)")
    pruefe(x["days"] == 10 and len(x["form_lines"]) == 2, "10 Tage seit dem letzten Lauf, 2 Formzeilen")
    g = x["form_lines"][1]["rivals"]
    pruefe(len(g) == 1 and g[0]["horse"] == "Y" and g[0]["next"]["pos"] == 2 and g[0]["next"]["odds_rank"] == 1
           and g[0]["next"]["verdict"] == "schlechter",
           "Gegner: Y lief danach wieder, Platz 2 bei Quotenrang 1 -> schlechter als erwartet; Z lief nicht wieder")
    pruefe(rc.going_klasse("Très souple", None) == "TRES SOUPLE" and rc.going_klasse("Souple", None) == "SOUPLE"
           and rc.going_klasse(None, 3.5) == "BON SOUPLE", "Bodenbegriffe: Très souple ≠ Souple")
    fy = y["form_lines"]
    pruefe((fy[1]["rpr"], x["form_lines"][1]["rpr"]) == (70, 67) and fy[1]["rpr_prov"]
           and (f["rpr"], fy[0]["rpr"]) == (68, 64) and not f["rpr_prov"],
           "RPR: erstes Rennen vorläufig aus dem Klassenwert (2 L auf Lourd über 2000 m = 2,55 lb), "
           "danach dienen die früheren RPRs als Anker (2 L über 1200 m = 5 lb)")
    pruefe(x["rpr"]["best"] == 68 and y["rpr"] == {"best": 70, "last": 64, "avg3": 67, "runs": 2, "rank": 1, "n": 2},
           "RPR in der Übersicht: bestes, letztes, Ø und Rang im Feld")
    pruefe(x["style"] == "H" and f["early_pos"] == 2,
           "Laufstil aus der frühen Position (erster Messpunkt 800 m: 2. von 2 -> hinten)")

    # Pace-Kalibrierung: Tempomacher und Feldgröße, Bahn-Bias
    zeilen, tempo = [], {}
    for i in range(300):
        rid_i, nf, nr = f"2025{i:04d}R1C1", i % 4, 6 + (i % 3) * 3     # nf Frontrenner, nr Starter
        tempo[rid_i] = 98 + 1.5 * (nf - 1.5) + 0.3 * (nr - 10)
        for no in range(nr):
            front = no < nf
            zeilen.append({"race_id": rid_i, "saddle_no": no, "horse_id": f"P{(i * 8 + no) % 40}" if not front
                           else f"F{no}", "date": pd.Timestamp("2025-01-01") + timedelta(days=i),
                           "early_pct": 0.05 if front else 0.3 + 0.7 * no / nr, "won": int(no == 0),
                           "dist_bucket": "mile", "course_key": "BAHN", "distance_m": 1600, "n_runners": nr})
    hh = pd.DataFrame(zeilen)
    hh["pace_ratio"] = hh["race_id"].map(tempo)
    kal = rc.pace_kalibrierung(hh)
    pruefe(kal["coef"] and abs(kal["coef"]["front"] - 1.5) < 0.2 and abs(kal["coef"]["field"] - 0.3) < 0.1,
           f"Pace-Kalibrierung: +1,5 je Tempomacher und +0,3 je Starter wiedergefunden ({kal['coef']})")
    viele = [{"no": n, "style": "F", "early": 0.05} for n in (1, 2, 3)] + [{"no": 9, "style": "H", "early": 0.9}] * 11
    wenige = [{"no": n, "style": "F", "early": 0.05} for n in (1, 2, 3)] + [{"no": 9, "style": "H", "early": 0.9}] * 3
    sv, sw = rc.pace_szenario(viele, "mile", kal), rc.pace_szenario(wenige, "mile", kal)
    pruefe(sv["label"] == "schnell" and sv["expected"] > sw["expected"],
           "gleich viele Tempomacher, größeres Feld -> höhere erwartete Pace")
    bb = rc.bahn_bias(hh)
    pruefe(bb["exakt"][("BAHN", 1600)]["bias"] > 0, "Bahn-Bias positiv, wenn meist die Frontrenner gewinnen")

    # Bereinigte Kennzahlen (speedfig): bekannte Rennbedingungen müssen herausgerechnet werden
    rng = np.random.default_rng(3)
    koennen = {f"H{k}": rng.normal(0, 0.25) for k in range(300)}
    zeilen, secs = [], []
    for i in range(500):
        rid_i = f"2024{i:05d}"
        dist_i, gv, pace = rng.choice([1200, 1600, 2400]), rng.uniform(2.8, 4.8), rng.normal(98, 3)
        bahn = rng.choice(["A", "B", "C"])
        v_early = 16.8 + 0.15 * (pace - 98)          # frühes Tempo des Führenden (m/s), Ursache des Verlaufs
        basis = 17.2 - 0.9 * (dist_i - 1200) / 1200 - 0.5 * (gv - 3.5) - 0.08 * (pace - 98) \
            + {"A": 0.2, "B": 0.0, "C": -0.2}[bahn]
        feld = rng.choice(list(koennen), 10, replace=False)
        v = {p: basis + koennen[p] + rng.normal(0, 0.08) for p in feld}
        for pos, (p, vv) in enumerate(sorted(v.items(), key=lambda t: -t[1]), 1):
            zeilen.append({"race_id": rid_i, "saddle_no": pos, "horse_id": p, "date": pd.Timestamp("2024-01-01")
                           + timedelta(days=i), "finish_pos": pos, "n_runners": 10, "lengths_behind": (pos - 1) * 0.8,
                           "speed_last400_kmh": vv * 3.6, "speed_last600_kmh": (vv - 0.3) * 3.6,
                           "speed_600_400_kmh": (vv - 0.9) * 3.6, "path_factor": 1.0,
                           "finish_index": 100 + (vv - basis) * 5, "distance_m": dist_i, "going_value": gv,
                           "going_class": "SOUPLE", "course_key": bahn, "pace_ratio": pace,
                           "pace_early_kmh": v_early * 3.6, "true": koennen[p]})
            secs += [{"race_id": rid_i, "saddle_no": pos, "m_to_go": mtg, "seg_len_m": 200,
                      "split_s": 200 / (vv + (1.5 if mtg >= 800 else 0))} for mtg in (1000, 600, 400, 200, 0)]
    sim = sf.berechnen(pd.DataFrame(zeilen), pd.DataFrame(secs))
    r_roh = sim["speed_last400_kmh"].corr(sim["true"])
    r_adj = sim["v400_adj_l"].corr(sim["true"])
    pruefe(r_adj > 0.85 and r_adj > r_roh + 0.2,
           f"L400 bereinigt trifft das Können deutlich besser als roh (r = {r_adj:.2f} statt {r_roh:.2f})")
    pruefe(sim["best_seg_to_go_m"].max() <= 800 and sim["best_seg_s"].notna().all(),
           "Best Seg nur aus den letzten 800 m – der schnellere frühe Abschnitt zählt nicht")
    pruefe(sim["accel_adj"].notna().all() and sim["peak_adj"].notna().all()
           and abs(sim["accel_kmh"].mean() - 0.9 * 3.6) < 0.05,
           "Δ400 = L400 − Tempo 600–400 m und Peak = Best Seg − L600 werden gebildet und bereinigt")
    val = sf.validierung(sim.assign(ausgeritten=False))
    z = val.set_index("Kennzahl").loc["L400"]
    pruefe(z["Wiederholbarkeit bereinigt"] > z["Wiederholbarkeit roh"], "Validierung: bereinigt wiederholbarer als roh")
    pruefe(set(val["Kennzahl"]) >= {"Δ400", "Peak", "Best Seg"}, "Validierung deckt auch Δ400 und Peak ab")

    # Rohwerte aus den Abschnitten: fehlender Split -> kein Tempo (statt zu hohem), 600–400 m bleibt
    secs = pd.DataFrame([{"race_id": "R", "saddle_no": 1, "m_to_go": m, "seg_len_m": 200, "split_s": t, "cum_s": None}
                         for m, t in ((1000, 12.5), (800, 11.8), (600, 11.6), (400, 11.4), (200, None), (0, 11.5))])
    k = sf.rohwerte_aus_abschnitten(pd.DataFrame([{"race_id": "R", "saddle_no": 1, "distance_m": 1200,
                                                   "speed_last400_kmh": 70.0, "speed_last600_kmh": 68.0}]), secs).iloc[0]
    pruefe(pd.isna(k["speed_last400_kmh"]) and pd.isna(k["speed_last600_kmh"]) and pd.isna(k["finish_index"])
           and k["speed_600_400_kmh"] == round(200 / 11.4 * 3.6, 2),
           "fehlender Split: kein L400/L600/Finish-Index statt zu hohem Tempo; 600–400 m bleibt")

    class BildSession:
        def get(self, url, headers=None, timeout=None):
            r = FakeResponse(b"\x89PNG-trikot" if "ok" in url else b"", 200 if "ok" in url else 404)
            r.headers = {"Content-Type": "image/png"}
            return r
    tr = rc.trikots(["https://x/ok.png", "https://x/fehlt.png", None], BildSession())
    pruefe(list(tr) == ["https://x/ok.png"] and tr["https://x/ok.png"].startswith("data:image/png;base64,"),
           "Trikots werden als data:-URI eingebettet, fehlende übersprungen")
    pruefe(pmu.runner_row("R", {"urlCasaque": "https://x/c.png"})["silks_url"] == "https://x/c.png",
           "PMU-Starterzeile übernimmt die Trikot-Adresse (urlCasaque)")

    seite = rc.html(d)
    pruefe(seite.startswith("<!doctype html>") and "/*__DATA__*/null" not in seite, "HTML mit eingesetzten Daten")


if __name__ == "__main__":
    sys.exit(main())
