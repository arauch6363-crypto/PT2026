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
import rtr_arr
import tempo_delta
import timeform_ratings

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
    print("\n9) Standardzeiten je Konfiguration")
    standardzeiten_pruefen()
    print("\n10) PMU-Basis: Rennen, Starter, Dividenden, Zeiten")
    pmu_basis_pruefen()

    pt.read_pages = requests_session_orig
    print("\n" + ("Alle Prüfungen bestanden." if not fehler else f"{len(fehler)} Prüfung(en) fehlgeschlagen:"))
    for f in fehler:
        print("  -", f)
    return 1 if fehler else 0


def standardzeiten_pruefen() -> None:
    """standardzeiten.py: Sammeln gegen eine nachgebaute Schnittstelle, Standardzeiten je Konfiguration."""
    import json as _json
    import numpy as np
    import standardzeiten as sz

    def kurs(no, dist, parcours, piste, dauer, going="Bon souple"):
        c = {"numOrdre": no, "libelle": f"PRIX {no}", "specialite": "PLAT", "discipline": "PLAT", "statut": "FIN_COURSE",
             "distance": dist, "parcours": parcours, "corde": "CORDE_DROITE", "typePiste": piste, "montantPrix": 20000,
             "conditionAge": "TROIS_ANS", "penetrometre": {"intitule": going, "valeurMesure": "3,4"},
             "heureDepart": int(datetime(2026, 1, 1, 13).timestamp() * 1000), "ordreArrivee": [[1], [2]]}
        if dauer is not None:
            c["dureeCourse"] = dauer
        return c

    class Sess:
        def __init__(self):
            self.urls = []

        def get(self, url, headers=None, timeout=None):
            self.urls.append(url)
            if url.endswith("/R1/C3"):
                return FakeResponse(text=_json.dumps({"dureeCourse": 101230}))
            return FakeResponse(text=_json.dumps({"programme": {"reunions": [_reunion(1, "HIPPODROME DE CHANTILLY", "CHY", [
                kurs(1, 1600, "1600 M. (GRANDE PISTE)", "GAZON", 95400),
                kurs(2, 1600, "1600 M. (PISTE RONDE)", "GAZON", 96800),
                kurs(3, 1900, "PISTE EN SABLE FIBRE", "PSF", None, "PSF Standard")])]}}))

    with tempfile.TemporaryDirectory() as tmp:
        s_ = Sess()
        st = sz.sammeln(Path(tmp), "2026-09-20", "2026-09-22", session=s_, pause=0)
        r = sz.laden(Path(tmp)).set_index("race_id")
        n = len(s_.urls)
        st2 = sz.sammeln(Path(tmp), "2026-09-20", "2026-09-22", session=s_, pause=0)
        pruefe(st["rennen"] == 9 and st["mit_zeit"] == 9 and r.at["20260922R1C1", "zeit_s"] == 95.4
               and r.at["20260922R1C3", "zeit_s"] == 101.23 and st2["tage"] == 0 and len(s_.urls) == n,
               "Standardzeiten sammeln: Zeit in ms erkannt, fehlende Zeit von der Rennseite, erledigte Tage nicht erneut")
        sz.run(Path(tmp), "2026-09-20", "2026-09-22", sammeln_ok=False)
        je = sz.je_rennen(Path(tmp)).set_index("race_id")
        pruefe(len(je) == 9 and je.loc["20260922R1C1", "konfiguration"] != je.loc["20260922R1C2", "konfiguration"]
               and je["ga_skm"].notna().all(),
               "je_rennen: jedes gesammelte Rennen mit der Standardzeit seiner Konfiguration und der Allowance des Tages")
        pruefe(r.at["20260922R1C1", "parcours_n"] == "GRANDE PISTE" and r.at["20260922R1C2", "parcours_n"] == "PISTE RONDE"
               and r.at["20260922R1C3", "piste"] == "PSF" and r.at["20260922R1C1", "going_klasse"] == "BON SOUPLE",
               "Konfiguration des Tages: Piste, Parcours, Corde und offizieller Boden je Rennen")

    rng = np.random.default_rng(5)
    konf = {("CHANTILLY", 1600, "GAZON", "GRANDE PISTE"): 59.5, ("CHANTILLY", 1600, "GAZON", "PISTE RONDE"): 60.6,
            ("CHANTILLY", 1900, "PSF", "PISTE EN SABLE FIBRE"): 61.0, ("DEAUVILLE", 1200, "GAZON", "LIGNE DROITE"): 58.2}
    zeilen = []
    for tag_i in range(300):
        for bahn in ("CHANTILLY", "DEAUVILLE"):
            if rng.random() < .5:
                continue
            boden = rng.choice(["BON", "BON SOUPLE", "SOUPLE", "LOURD"], p=[.35, .3, .2, .15])
            ga = {"BON": 0, "BON SOUPLE": .6, "SOUPLE": 1.8, "LOURD": 3.5}[boden] + rng.normal(0, .5)
            for rn in range(1, 6):
                k = [x for x in konf if x[0] == bahn][rng.integers(0, 3 if bahn == "CHANTILLY" else 1)]
                prize = [8000, 16000, 32000, 64000][int(rng.integers(0, 4))]
                skm = konf[k] + ga * (k[2] == "GAZON") - 0.35 * np.log2(prize / 16000) + rng.normal(0, .4)
                zeilen.append(dict(race_id=f"{tag_i}{bahn[:2]}{rn}", date=(date(2024, 1, 1) + timedelta(days=tag_i)).strftime("%Y%m%d"),
                                   bahn=bahn, pmu_code=bahn[:3], distance_m=k[1], piste=k[2], parcours_n=k[3],
                                   corde="CORDE_DROITE", going_klasse=boden if k[2] == "GAZON" else "PSF",
                                   zeit_s=skm * k[1] / 1000, prize_eur=prize, conditions_age="TROIS_ANS"))
    std, ga_df, info = sz.berechnen(pd.DataFrame(zeilen))
    w = lambda b, d, pa: float(std[(std.bahn == b) & (std.distance_m == d) & (std.parcours == pa)]["std_skm"].iloc[0])
    diff = w("CHANTILLY", 1600, "PISTE RONDE") - w("CHANTILLY", 1600, "GRANDE PISTE")
    pruefe(len(std) == 4 and abs(diff - 1.1) < 0.2 and abs(w("DEAUVILLE", 1200, "LIGNE DROITE") - 58.2) < 0.3
           and abs(info["preis_x2_skm"] + 0.35) < 0.08,
           f"Standardzeit je Konfiguration: gleiche Distanz, anderer Parcours getrennt ({diff:+.2f} s/km, wahr +1,10), "
           f"Klasse Preisgeld ×2 {info['preis_x2_skm']:+.2f} s/km (wahr −0,35)")
    gg = ga_df.groupby("boden")["ga_skm"].median()
    pruefe(gg["VERY SLOW"] > gg["SLOW"] > gg["FAST"] and abs(gg["FAST"]) < 0.4 and abs(gg.get("PSF", 0.0)) < 0.2,
           f"Going Allowance je Bodengruppe (Lourd = VERY SLOW {gg['VERY SLOW']:+.2f}, Souple = SLOW {gg['SLOW']:+.2f}, "
           f"Bon/Bon souple = FAST {gg['FAST']:+.2f} s/km), PSF eigener Nullpunkt")


def pmu_basis_pruefen() -> None:
    """pmu_basis.py: Rennen, Starter (Kommentar, Zeit), Dividenden je Tag schreiben; Pipeline behält Zusatzspalten."""
    import json as _json
    import pmu_basis as pb
    kurs = {"numOrdre": 1, "libelle": "PRIX TEST", "specialite": "PLAT", "discipline": "PLAT", "statut": "FIN_COURSE",
            "distance": 1600, "parcours": "1600 M. (GRANDE PISTE)", "corde": "CORDE_DROITE", "typePiste": "GAZON",
            "montantPrix": 20000, "conditionAge": "TROIS_ANS", "penetrometre": {"intitule": "Bon souple"},
            "heureDepart": int(datetime(2026, 1, 1, 13).timestamp() * 1000), "ordreArrivee": [[2], [1], [3]]}

    class Sess:
        def __init__(self):
            self.urls = []

        def get(self, url, headers=None, timeout=None):
            self.urls.append(url)
            if url.endswith("/R1/C1"):
                return FakeResponse(text=_json.dumps({**kurs, "dureeCourse": 96120,
                                                      "commentaireApresCourse": {"texte": "Course menée par 3."}}))
            if url.endswith("/R1/C1/participants"):
                mit = "/client/1/" in url
                return FakeResponse(text=_json.dumps({"participants": [
                    {"numPmu": n, "nom": f"PFERD {n}", "statut": "PARTANT", "age": 4, "sexe": "MALES", "handicapPoids": 570,
                     "ordreArrivee": pos, "distanceChevalPrecedent": {"libelleCourt": lab}, "nomPere": "PAPA",
                     **({"commentaireApresCourse": {"texte": f"A bien fini ({n})."}} if mit else {})}
                    for n, pos, lab in ((2, 1, None), (1, 2, "1 L"), (3, 3, "2 L"))]}))
            if url.endswith("/rapports-definitifs"):
                return FakeResponse(text=_json.dumps([
                    {"typePari": "SIMPLE_GAGNANT", "miseBase": 200,
                     "rapports": [{"libelle": "Gagnant", "combinaison": ["2"], "dividende": 920, "dividendePourUnEuro": 460}]},
                    {"typePari": "COUPLE_GAGNANT", "miseBase": 200, "rapports": [{"combinaison": ["2", "1"], "dividendePourUnEuro": 1530}]}]))
            if url.rstrip("/").split("/")[-1].isdigit():
                return FakeResponse(text=_json.dumps({"programme": {"reunions": [
                    _reunion(1, "HIPPODROME DE CHANTILLY", "CHY", [kurs])]}}))
            return FakeResponse(status=404)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        tp._write(base, "pmu_races", "20260922", [{"race_id": "20260922R1C1", "alt": 1}])
        s_ = Sess()
        pb.run(base, "2026-09-22", "2026-09-22", session=s_, pause=0)
        r, ru, dv = (tp.lade(t, base) for t in ("pmu_races", "pmu_runners", "pmu_dividends"))
        ru = ru.set_index("saddle_no")
        pruefe("alt" not in r and r.at[0, "race_time_s"] == 96.12 and r.at[0, "race_comment"] == "Course menée par 3."
               and r.at[0, "track_type"] == "GAZON",
               "PMU-Basis: Tagesdatei überschrieben, Siegerzeit, Rennkommentar und Piste im Rennen")
        pruefe(ru.loc[1, "comment"] == "A bien fini (1)." and ru["comment"].notna().all()
               and abs(ru.loc[1, "time_s"] - (96.12 + 2.4 / (1600 / 96.12))) < 0.01 and bool(ru.loc[1, "time_est"]),
               "PMU-Basis: Kommentar je Pferd (von einem anderen Client nachgeladen), Zeit aus Siegerzeit + Längen geschätzt")
        pruefe(len(dv) == 2 and set(dv["combination"]) == {"2", "2-1"} and dv["dividend_eur_per_1eur"].tolist() == [4.6, 15.3],
               "PMU-Basis: Dividenden je Wette und Kombination in pmu_dividends")
        n = len(s_.urls)
        pb.run(base, "2026-09-22", "2026-09-22", session=s_, pause=0)
        pruefe(len(s_.urls) == n, "PMU-Basis: erledigte Tage werden nicht erneut abgefragt")
        teiln = [u for u in s_.urls if u.endswith("/participants")]
        s2 = Sess()
        pb.run(base, "2026-09-22", "2026-09-22", session=s2, pause=0, neu=True)
        teiln2 = [u for u in s2.urls if u.endswith("/participants")]
        pruefe(len(teiln) == 3 and len(teiln2) == 1 and "/client/1/" in teiln2[0],
               "PMU-Basis: Kommentar-Client gemerkt – danach nur noch eine Anfrage für die Starterliste")
        tp._write_behalten(base, "pmu_runners", "20260922",
                           [{"race_id": "20260922R1C1", "saddle_no": k, "horse": f"NEU {k}"} for k in (1, 2, 3)],
                           ["race_id", "saddle_no"])
        ru2 = tp.lade("pmu_runners", base).set_index("saddle_no")
        pruefe(ru2.loc[1, "horse"] == "NEU 1" and ru2.loc[1, "comment"] == "A bien fini (1)." and "time_s" in ru2,
               "Pipeline überschreibt die Starter, behält aber Kommentar und Zeiten aus pmu_basis")


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
        "blinkers": "SANS_OEILLERES", "lengths_prev": None if pos == 1 else 2.0, "draw": no, "owner": "STALL",
        "lengths_behind": None if pos == 1 else 2.0, **kw}
    runners = pd.DataFrame([lauf(rid(10, 1), 1, "X", "TR", 1, 4.0, p_nomPereMere="MV", rating=40,
                                 comment="A fini fort à l'extérieur."),
                            lauf(rid(10, 1), 2, "Y", "TR", 2, 2.0),
                            lauf(rid(100, 1), 1, "X", "TR", 2, 5.0, p_nomPereMere="MV",
                                 blinkers="OEILLERES_AUSTRALIENNES"),
                            lauf(rid(100, 1), 2, "Y", "AND", 1, 3.0),
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
    heute_s = pd.DataFrame([{**lauf(f"{tag:%Y%m%d}R1C1", 1, "X", "TR", None, 3.0, blinkers="OEILLERES_CLASSIQUE",
                                  dam_sire="MV"),
                             "finish_pos": None},
                            {**lauf(f"{tag:%Y%m%d}R1C1", 2, "Y", "NEU", None, 3.0, sex="HONGRES"),
                             "finish_pos": None}])
    d = rc.baue_daten(hist, heute_r, heute_s, tag)
    x, y = d["races"][f"{tag:%Y%m%d}R1C1"]["runners"]
    pruefe(x["ae"]["trainer"]["d90"] == {"runs": 2, "wins": 1, "places": 2, "exp": 0.75, "ae": 1.33,
                                         "epr": round((13500 + 5130) / 2)},
           "Trainer-A/E 90 Tage = 1 Sieg / (1/4 + 1/2) = 1,33; Gewinn je Lauf (13500 + 5130) / 2")
    pruefe(x["ae"]["trainer"]["d365"]["runs"] == 3 and x["ae"]["trainer"]["d365"]["ae"] == 1.05,
           "Trainer-A/E 365 Tage schließt den Lauf vor 100 Tagen ein (1 / 0,95 = 1,05)")
    pruefe(rc._ae_trend({"runs": 6, "ae": 1.6}, {"runs": 90, "ae": 1.0}) == "hot"
           and rc._ae_trend({"runs": 12, "ae": 0.3}, {"runs": 90, "ae": 1.0}) == "cold"
           and rc._ae_trend({"runs": 3, "ae": 3.0}, {"runs": 90, "ae": 1.0}) is None,
           "Feuer/Eis: 30 Tage deutlich über/unter 365 Tagen, erst ab 5 Starts")
    boden = x["pref"]["horse"]["going"]
    pruefe(boden[0]["label"] == "Fast" and boden[0]["today"] and (boden[0]["runs"], boden[0]["wins"]) == (1, 1)
           and {z["label"] for z in boden} == {"Fast", "Very slow"},
           "Pferd nach Boden: Bodengruppen (Bon -> FAST, Lourd -> VERY SLOW), die heutige oben markiert")
    dist = x["pref"]["horse"]["distance"]
    pruefe(dist[0]["label"] == "1001-1200 m" and dist[0]["today"] and {z["label"] for z in dist} == {"1001-1200 m", "1801-2000 m"},
           "Pferd nach Distanz: Distanzgruppen (1200 m -> 1001-1200, 2000 m -> 1801-2000), heute markiert")
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
    pruefe(len(g) == 2 and g[0]["horse"] == "Y" and g[0]["next"]["pos"] == 2 and g[0]["next"]["odds_rank"] == 1
           and g[0]["next"]["verdict"] == "schlechter" and g[1]["horse"] == "Z" and g[1]["next"] is None
           and x["form_lines"][1]["rivals_stat"] == {"better": 0, "worse": 1, "same": 0, "ran": 1, "n": 2},
           "Gegner: alle aufgeführt – Y (danach Platz 2 bei Quotenrang 1 -> schlechter), Z ohne weiteren Start; "
           "Bilanz 0 besser / 1 schlechter")
    k = x["career"]["all"]
    pruefe((k["runs"], k["wins"], k["places"], k["earn"], k["epr"]) == (2, 1, 2, 16350, 8175)
           and x["career"]["d365"]["runs"] == 2,
           "Karriere aus der Datenbank: 2-1-2, Preisgeld 27000 × 50 % + 15000 × 19 % = 16350, je Lauf 8175")
    hx_a = hist[(hist["race_id"] == rid(10, 1)) & (hist["horse"] == "X")].iloc[0]
    pruefe(hx_a["cls_epr"] == (2850 + 7500) / 2 and np.isnan(hist.loc[hist["race_id"] == rid(100, 1), "cls_epr"]).all(),
           "Klasse früherer Rennen: Ø Gewinn je Lauf der Teilnehmer in den 365 Tagen davor (X 2850, Y 7500)")
    kl = d["races"][f"{tag:%Y%m%d}R1C1"]["class"]
    pruefe(kl["epr"] == round((8175 + (7500 + 5130) / 2) / 2) and kl["epr_n"] == 2,
           "Klasse heute: Ø Gewinn je Lauf (365 Tage) der Starter = (8175 + 6315) / 2")
    ped = x["ae"]["pedigree"]
    pruefe(ped["dam_sire"]["runs"] == 2 and ped["dam_sire"]["wins"] == 1 and ped["cross"]["runs"] == 2
           and ped["sire"]["runs"] == 5 and y["ae"]["pedigree"]["dam_sire"]["runs"] == 0 and "sire" not in x["ae"],
           "A/E Abstammung über die ganze Historie: Vater, Muttervater (p_nomPereMere) und Cross Vater × Muttervater")
    pr = x["pref"]
    pruefe(pr["trainer"]["age_label"] == "4j+" and pr["trainer"]["age"]["runs"] == 3
           and pr["jockey"]["horse"]["runs"] == 2 and pr["dam_sire"]["going"]["runs"] == 1
           and pr["horse"]["course"][0]["label"] == "Deauville" and pr["horse"]["course"][0]["today"],
           "Vorlieben: Trainer nach Altersgruppe, Jockey auf dem Pferd, Muttervater nach Boden, Pferd nach Kurs")
    pruefe(pr["sire"]["age"]["runs"] == 5 and pr["dam_sire"]["age"]["runs"] == 2
           and x["ae"]["pedigree"]["sire"]["epr"] == round((13500 + 5130 + 7500 + 2850 + 2850) / 5),
           "Vorlieben Vater/Muttervater nach Altersgruppe (4j+), Gewinn je Lauf des Vaters (totes Rennen: beide 2.)")
    kx, ky = x["career"]["all"], y["career"]["all"]
    pruefe(kx["rank"] == 1 and ky["rank"] == 2 and kx["rel"] == round(8175 / ((8175 + 6315) / 2), 2),
           "Gewinn je Lauf im Vergleich zum Feld: Rang und Verhältnis zum Median")
    pruefe(f["cls_epr_pct"] == 100 and kl["epr_pct"] == 100,
           "Klasse eingeordnet als Perzentil aller früheren Rennen")
    ds = x["draw_stat"]
    pruefe(ds["mean"] == 1.0 and ds["dev"] == 0.5 and ds["n"] == 1 and not ds["ok"]
           and y["draw_stat"]["mean"] == 0.0 and y["draw_stat"]["n"] == 1,
           "Startbox: Ø relative Platzierung (Starter − Platz) / (Starter − 1) je Konfiguration × Box, Abweichung zu 0,5")
    pruefe(x["ae"]["owner"]["d365"]["runs"] == 5 and x["ae"]["breeder"]["d365"]["runs"] == 0,
           "A/E für Besitzer (und Züchter, hier ohne Angabe)")
    pv = x["ae"]["pedigree"]["sire"]
    pruefe(pv["horses"] == 3 and pv["max_val"] == 40.0 and x["ae"]["pedigree"]["dam_sire"]["horses"] == 1,
           "Abstammung: 3 verschiedene Pferde vom Vater, Ø höchste Valeur je Pferd")
    pruefe(f["valeur"] == 40.0 and x["form_lines"][1]["blinkers"] == "OEILLERES_AUSTRALIENNES" and f["odds"] == 4.0,
           "Formzeile mit Valeur, Scheuklappen und Endquote")
    rz = pd.DataFrame([{"race_id": "20260901R1C1", "hippodrome": "DEAUVILLE", "distance_m": 1600, "corde": "CORDE_DROITE",
                        "track_type": "HERBE", "parcours_norm": "LIGNE DROITE", "race_time_s": 96.4, "going": "Bon souple"},
                       {"race_id": "20260901R1C2", "hippodrome": "DEAUVILLE", "distance_m": 1600, "corde": "CORDE_DROITE",
                        "track_type": "HERBE", "parcours": "1600 M. (Grande piste)", "race_time_s": None}])
    import standardzeiten as sz_
    az = sz_.aus_pmu_races(rz)
    pruefe(len(az) == 1 and sz_.konfiguration(az).iloc[0] == "DEAUVILLE|1600|HERBE|LIGNE DROITE|CORDE_DROITE"
           and az["zeit_s"].iloc[0] == 96.4 and az["going_klasse"].iloc[0] == "BON SOUPLE"
           and rc.konfig_schluessel(rz).tolist() == ["DEAUVILLE|1600|HERBE|LIGNE DROITE|CORDE_DROITE",
                                                   "DEAUVILLE|1600|HERBE|GRANDE PISTE|CORDE_DROITE"],
           "Standardzeiten auch aus pmu_races: Bahn | Distanz | track_type | parcours_norm | Corde -> race_time_s; "
           "Startbox nutzt dieselbe Konfiguration")
    rn = rc.baue_daten(hist, heute_r.assign(going=None, going_value=None), heute_s, tag)["races"][f"{tag:%Y%m%d}R1C1"]
    pruefe(rn["going_pmu"] == "FAST" and rn["going_assumed"] and rn["runners"][0]["pref"]["horse"]["going"][0]["today"]
           and not d["races"][f"{tag:%Y%m%d}R1C1"]["going_assumed"],
           "Bodenangabe fehlt (noch): FAST angenommen und so markiert, Vorlieben rechnen mit FAST")
    import uebersetzen as ue
    tmp_k = Path(tempfile.mkdtemp(prefix="pt_ue_"))
    fake = lambda texte: [{"A fini fort à l'extérieur.": "Stark außen beendet."}[t] for t in texte]
    n_k = rc.kommentare_uebersetzen(d, tmp_k, uebersetzer=fake)
    pruefe(n_k == 1 and f["comment"] == "A fini fort à l'extérieur." and f["comment_de"] == "Stark außen beendet."
           and "race_comment" not in f and x["form_lines"][1]["comment_de"] is None
           and (tmp_k / ue.CACHE).exists(),
           "Kommentare je Starter in den Formzeilen auf Deutsch, Cache in BASE")
    def kaputt(texte):
        raise ConnectionError("offline")
    pruefe(ue.uebersetze(["A fini fort à l'extérieur.", "Neu."], tmp_k, uebersetzer=kaputt)
           == {"A fini fort à l'extérieur.": "Stark außen beendet.", "Neu.": None},
           "Übersetzung nur falls möglich: Cache greift, ohne Dienst bleibt der Text französisch")
    du = x["duels"]
    pruefe(len(du) == 2 and du[0]["rival"] == "Y" and du[0]["diff_l"] == 2.0 and du[0]["shift"] == 0.0
           and du[0]["rival_no"] == 2 and du[1]["pos"] == 2 and du[1]["rival_pos"] == 1,
           "Heutige Gegner: X traf Y zweimal – zuletzt 2 L vor ihm bei gleichem Gewicht, davor hinter ihm")
    import rtr_arr as ra
    pruefe(all(rc.going_klasse(k) == v for k, v in ra.GOING_MAP.items())
           and rc.going_klasse("BON SOUPLE") == "FAST" and rc.going_klasse("Bon léger") == "VERY FAST"
           and rc.going_klasse("PSF") == "PSF" and rc.going_klasse(None, 3.5) == "FAST" and rc.going_klasse("FAST") == "FAST"
           and rc.going_klasse("") == "FAST",
           "Bodengruppen nach GOING_MAP (auch ohne Akzente, PSF-Varianten); fehlt der Begriff: FAST (Penetrometer zählt nicht)")
    pruefe(ra.distance_group(1000) == "0-1000" and ra.distance_group(1001) == "1001-1200"
           and ra.distance_group(1600) == "1401-1600" and ra.distance_group(3601) == ">3600",
           "Distanzgruppen der Vorlieben: 0-1000, 1001-1200, …, >3600")
    fy = y["form_lines"]
    # RTR von Hand: Rennen vor 100 Tagen (2000 m Lourd -> 0,85 kg/L), alle Start 30, Y vor X (2 L) vor Z (4 L):
    # Stufe(1,7) = 3,2009, Stufe(3,4) = 4,1413, erwartet je Paar Stufe(0) = 1; Preisbonus (4/6 − 0,5)·5·e^−0,07
    # -> Y 31,7, X 30,4.  Dann 1200 m Bon (1,4 kg/L): X schlägt Y um 2 L -> X 34,3, Y 28,9
    pruefe((fy[1]["rtr"], x["form_lines"][1]["rtr"], f["rtr"], fy[0]["rtr"]) == (31.7, 30.4, 34.3, 28.9),
           "RTR (rating after race) wie im Notebook: Elo über alle Paare, Stufen und Preisbonus")
    pruefe(f["rtr_adj"] == 32.3 and x["rtr"]["raw"] == 34.3 and x["rtr"]["adj"] == 32.3 and x["rtr"]["rank"] == 1
           and y["rtr"]["adj"] == 26.9 and x["rtr"]["prev"] == 30.4,
           "RTR bereinigt = RTR − Gewicht (57) + 55, Rang im Feld")
    z = hist.iloc[0].copy()
    z["arr"], z["rtr"], z["weight_kg"] = 36.0, 40.0, 58.0          # damals 58 kg getragen
    fz = rc._formzeile(z, 52.0)                              # heute 52 kg
    pruefe(fz["arr_adj"] == 39.0 and fz["rtr_adj"] == 43.0 and fz["arr"] == 36.0
           and rc._formzeile(z, None)["arr_adj"] is None,
           "Formzeile: bereinigt mit dem heutigen Gewicht, nicht dem damaligen (ARR 36, heute 52 kg -> 39)")
    z["tr"] = 100.0
    pruefe(rc._formzeile(z, 52.0)["tr_heute"] == 107 and rc._formzeile(z, 60.0)["tr_heute"] == 89
           and rc._formzeile(z, None)["tr_heute"] == 100,
           "TR in der Formzeile auf das heutige Gewicht umgerechnet (100 lb bei 55 kg: heute 52 kg -> 107, 60 kg -> 89)")
    lf = pd.DataFrame({"tr": [100.0, 90.0, 80.0], "distance_m": [1600, 2400, 1600],
                       "going_pmu": ["BON", "LOURD", "PSF"]})
    k_ = rc.tr_schnitt(lf, 1600, "BON")
    gw = [1.0, 1 / 3 * 1 / (1 + 2 / 1), 0.25]          # Lourd = VERY SLOW, zwei Gruppen von FAST entfernt
    pruefe(np.allclose(k_["gewichte"], gw, atol=0.005)
           and abs(k_["avg"] - (100 + 90 * gw[1] + 80 * gw[2]) / sum(gw)) < 1e-9 and k_["runs"] == 3
           and rc.going_gewicht(None, "BON") == 1.0 and rc.going_gewicht("BON SOUPLE", "BON") == 1.0
           and rc.going_gewicht("SLOW", "FAST") == 0.5,
           f"TR-Kachel: Ø gewichtet nach Distanz × Bodengruppe (2400 m Lourd bei heute 1600 m Bon: {gw[1]:.3f}, "
           f"PSF: 0,25) = {k_['avg']:.1f}")
    lw = rc.lauf_gewichte(pd.DataFrame({"distance_m": [1600, 2000, 1600], "going_pmu": ["SOUPLE", "BON", None]}), 1600, "BON")
    pruefe(np.allclose(lw, [1 / (1 + 2 / 2), 1 / (1 + 400 / 400), 1.0]),
           "Kacheln ΔL600 A / ΔB200 A / TR: gleiche Gewichte nach Distanz × Going (Souple bei heute Bon: 0,5)")
    ak = rc.gewichteter_schnitt(pd.DataFrame({"arr": [36.0, 30.0], "distance_m": [1600, 1600],
                                              "going_pmu": ["BON", "SOUPLE"]}), "arr", 1600, "BON")
    pruefe(abs(ak["avg"] - (36 + 30 * 0.5) / 1.5) < 1e-9 and ak["best"] == 36.0 and rc._adj(ak["avg"], 52.0) == 37.0,
           "ARR-Kachel: gleicher gewichteter Ø (36 auf Bon, 30 auf Souple -> 34,0), bereinigt auf heute 52 kg -> 37,0")
    ra_df = pd.DataFrame({"race_id": "R", "date": pd.Timestamp("2026-01-01"), "horse": list("ABCD"),
                          "finish_pos": [1, 2, 3, 4], "lengths_back": [0, 1, 3, 7], "weight_kg": [58, 57, 56, 55],
                          "rating": [40, 38, 35, 30], "age": 4, "going_category": "FAST",
                          "distance_group": rtr_arr.distance_group(1600), "prize": 20000, "categorie": "HANDICAP",
                          "horse_run": 5})
    ra = rtr_arr.berechnen(ra_df)
    pruefe(ra["arr"].tolist() == [40.2, 37.8, 34.2, 28.2],
           "ARR von Hand: Referenzen A, B (vorderes Drittel, pos_perc > 0,66), 1,2 kg/L; B = Ø(40 − 1,2 − 1,2; 38), D = Ø(40 − 8,4 − 3,6; 38 − 7,2 − 2,4) = 28,2")
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
        dist_i, pace = rng.choice([1200, 1600, 2400]), rng.normal(98, 3)
        boden_i = rng.choice(["VERY FAST", "FAST", "SLOW", "VERY SLOW"])       # Boden nur als Gruppe bekannt
        gv = {"VERY FAST": 2.8, "FAST": 3.3, "SLOW": 4.0, "VERY SLOW": 4.8}[boden_i]
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
                           "going_class": boden_i, "course_key": bahn, "pace_ratio": pace,
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

    # ΔL600 A / ΔB200 A (tempo_delta): Gruppe Tag × Kurs × Going, Klassenkorrektur der Gruppe
    rng = np.random.default_rng(7)
    pferde = pd.Series(rng.normal(0, 1, 1600))
    nach_koennen = pferde.sort_values().index.to_numpy()
    zeilen, secs = [], []
    for tag_i in range(150):
        for bahn in ("COMPIEGNE", "DEAUVILLE"):
            schwach = rng.random() < .3                           # an diesem Tag nur schwache Klasse
            for going, n_r in (("BON", 4), ("SOUPLE", 2)):       # Boden wechselt am selben Tag auf demselben Kurs
                boden = {"BON": 0.0, "SOUPLE": -2.0}[going] + rng.normal(0, 1)
                for rn in range(n_r):
                    stufe = 0 if schwach else int(rng.integers(0, 4))
                    feld = rng.choice(nach_koennen[stufe * 400:stufe * 400 + 400], 8, replace=False)
                    rid_i = f"{(pd.Timestamp('2025-01-01') + timedelta(days=tag_i)):%Y%m%d}{bahn[:2]}{going[0]}{rn}"
                    dist_i, pace = int(rng.choice([1200, 1600, 2000])), rng.normal(100, 4)
                    for no, pf in enumerate(feld, 1):
                        v = 62 + boden - 0.15 * (pace - 100) - (dist_i - 1200) / 800 + pferde[pf] + rng.normal(0, .3)
                        zeilen.append(dict(race_id=rid_i, saddle_no=no, date=pd.Timestamp("2025-01-01") + timedelta(days=tag_i),
                                           course_key=bahn, going_pmu=going, distance_m=dist_i, pace_ratio=pace,
                                           prize_eur=[8000, 16000, 32000, 64000][stufe], conditions_age="TROIS_ANS",
                                           speed_last600_kmh=v, wahr=pferde[pf], schwach=schwach))
                        for mtg, extra in ((1000, 3.0), (600, -1.0), (400, 0.6), (200, 0.2), (0, -0.8)):
                            secs.append(dict(race_id=rid_i, saddle_no=no, m_to_go=mtg, seg_len_m=200, seg_from=f"{mtg + 200}m",
                                             seg_to=f"{mtg}m" if mtg else "ARR", speed_kmh=v + extra))
    td = tempo_delta.berechnen(pd.DataFrame(zeilen), pd.DataFrame(secs))
    err = td["d_L600_roh"] - td["wahr"]
    boden_fehler = err[td["going_pmu"] == "SOUPLE"].mean() - err[td["going_pmu"] == "BON"].mean()
    pruefe(td.groupby(["course_key", "date", "going_pmu"])["d_L600_roh"].mean().abs().max() < 1e-6
           and abs(boden_fehler) < 0.3,
           f"ΔL600: verglichen innerhalb Tag × Kurs × Going – SOUPLE-Rennen am selben Tag nicht um den "
           f"Bodeneffekt (−2 km/h) benachteiligt ({boden_fehler:+.2f})")
    f_ = td[td["schwach"]]
    fehler = lambda c: (f_[c] - f_["wahr"]).mean() - (td[c] - td["wahr"]).mean()
    pruefe(fehler("d_L600_roh") > 0.5 and abs(fehler("d_L600_A")) < 0.15
           and td["d_L600_A"].corr(td["wahr"]) > td["d_L600_roh"].corr(td["wahr"]) + 0.15,
           f"Klassenkorrektur: Tage mit nur schwacher Klasse nicht mehr überbewertet "
           f"({fehler('d_L600_roh'):+.2f} -> {fehler('d_L600_A'):+.2f} km/h, r {td['d_L600_roh'].corr(td['wahr']):.2f} "
           f"-> {td['d_L600_A'].corr(td['wahr']):.2f})")
    pruefe(np.allclose(td["d_L600_A"], td["d_L600_roh"] + td["k_L600"], equal_nan=True)
           and td.groupby(["course_key", "date", "going_pmu"])["k_L600"].nunique().max() == 1,
           "Δ A = rohes Δ + Klassenkorrektur, eine Korrektur je Gruppe")
    pruefe((td["best200_seg"] == "600m→400m").all() and np.allclose(td["best200_kmh"], td["speed_last600_kmh"] + 0.6),
           "B200: schnellstes 200-m-Segment nur aus den letzten 800 m (das schnellere bei 1000 m zählt nicht)")

    # TR (timeform_ratings): Können, Going Allowance, Längen je Sekunde und Upgrade-Koeffizient wiederfinden
    rng = np.random.default_rng(11)
    LPS, C_TRUE = 5.5, 2.0
    koennen = pd.Series(rng.normal(85, 8, 1500), index=[f"P{i}" for i in range(1500)])
    sortiert = koennen.sort_values().index.to_numpy()
    std_v = {1200: 16.9, 1600: 16.5, 2000: 16.1}
    O_true = {1200: 96.0, 1600: 101.0, 2000: 104.0}
    zeilen, secs, leader = [], [], []
    for tag_i in range(220):
        for bahn in ("COMPIEGNE", "DEAUVILLE"):
            for going, n_r in (("BON", 4), ("SOUPLE", 2)):
                ga = rng.normal(0, 1.2) + (2.0 if going == "SOUPLE" else 0)
                for rn in range(n_r):
                    stufe = int(rng.integers(0, 3))
                    feld = rng.choice(sortiert[stufe * 500:stufe * 500 + 500], 8, replace=False)
                    D = int(rng.choice(list(std_v))); km = D / 1000; dd = 400 if D <= 1600 else 600
                    pace, lb_s = rng.normal(0, 3.5), timeform_ratings.lb_je_laenge(D) * LPS
                    rid_i = f"{tag_i:04d}{bahn[:2]}{going[0]}{rn}"
                    runs = []
                    for no, pf_ in enumerate(feld, 1):
                        w = round(rng.uniform(52, 60), 1)
                        fs = O_true[D] + pace + rng.normal(0, 2.0)
                        P = koennen[pf_] - C_TRUE * (dd / D) * (O_true[D] - fs) ** 2 + rng.normal(0, 1.5)
                        T = km * (1000 / std_v[D] + ga) + (100 - P + (w - 55) * 2.2046) / lb_s
                        runs.append((no, pf_, w, fs, T))
                    Tw = min(r[4] for r in runs)
                    for pos, (no, pf_, w, fs, T) in enumerate(sorted(runs, key=lambda r: r[4]), 1):
                        zeilen.append(dict(race_id=rid_i, saddle_no=no, horse_id=pf_, date=pd.Timestamp("2024-01-01") + timedelta(days=tag_i),
                                           course_key=bahn, going_pmu=going, distance_m=D, prize_eur=[8000, 16000, 32000][stufe],
                                           conditions_age="TROIS_ANS", finish_pos=pos, lengths_behind=(T - Tw) * LPS,
                                           weight_kg=w, official_time_s=T, behind_winner_s=T - Tw, path_factor=1.0,
                                           wahr=koennen[pf_], ga_wahr=ga))
                        t = T * dd / (D * fs / 100)
                        secs += [dict(race_id=rid_i, saddle_no=no, m_to_go=m, seg_len_m=200, split_s=t / (dd / 200)) for m in range(0, dd, 200)]
                        if pos == 1:
                            leader += [dict(race_id=rid_i, to="ARR", leader_cum_s=T), dict(race_id=rid_i, to=f"{dd}m", leader_cum_s=T - t)]
    tr = timeform_ratings.berechnen(pd.DataFrame(zeilen), pd.DataFrame(secs), pd.DataFrame(leader))
    info = timeform_ratings.LETZTE_INFO
    g_ = tr.dropna(subset=["tr_ga"]).drop_duplicates(["course_key", "date", "going_pmu"])
    z_df = pd.DataFrame(zeilen)
    std_ext = (z_df.drop_duplicates("race_id")
                   .assign(std_skm=lambda x: 1000 / x["distance_m"].map(std_v), ga_skm=lambda x: x["ga_wahr"])
                   [["race_id", "std_skm", "ga_skm"]])
    tr_ext = timeform_ratings.berechnen(z_df, pd.DataFrame(secs), pd.DataFrame(leader), std_ext)
    info_ext = timeform_ratings.LETZTE_INFO
    pruefe(info_ext["std_konfig"] == info_ext["rennen"] and info_ext["ga_extern"] > 0
           and tr_ext["tr_zeit"].corr(tr_ext["wahr"]) >= tr["tr_zeit"].corr(tr["wahr"]) - 0.01
           and abs((tr_ext["tr"] - tr_ext["wahr"]).mean()) < abs((tr["tr"] - tr["wahr"]).mean()),
           f"TR mit Standardzeiten je Konfiguration (standardzeiten.py): alle {info_ext['rennen']} Rennen zugeordnet, "
           f"r(Zeit-Rating, Können) {tr['tr_zeit'].corr(tr['wahr']):.3f} -> {tr_ext['tr_zeit'].corr(tr_ext['wahr']):.3f}, "
           f"Niveau TR − Können {(tr['tr'] - tr['wahr']).mean():+.1f} -> {(tr_ext['tr'] - tr_ext['wahr']).mean():+.1f} lb")
    pruefe(tr["tr"].corr(tr["wahr"]) > 0.84 and tr["tr"].corr(tr["wahr"]) > tr["tr_zeit"].corr(tr["wahr"]) + 0.05
           and g_["tr_ga"].corr(g_["ga_wahr"]) > 0.95,
           f"TR: Können wiedergefunden (r {tr['tr_zeit'].corr(tr['wahr']):.2f} Zeit -> {tr['tr'].corr(tr['wahr']):.2f} mit Upgrade), "
           f"Going Allowance nach Timeform (r {g_['tr_ga'].corr(g_['ga_wahr']):.2f})")
    pruefe(all(abs(v - LPS) < 0.3 for v in info["laengen_je_s"].values()) and 1.2 < info["c_sym"] < 2.6
           and (tr.groupby("distance_m")["fs_opt"].median() - pd.Series(O_true)).abs().max() < 0.7,
           f"TR: Längen je Sekunde ({min(info['laengen_je_s'].values()):.1f}–{max(info['laengen_je_s'].values()):.1f}, wahr 5,5), "
           f"Upgrade-Koeffizient {info['c_sym']:.2f} (wahr 2,0), optimaler FS% je Distanz wiedergefunden")
    pruefe(tr["tr_upgrade"].max() <= timeform_ratings.UPGRADE_MAX_LB + 1e-9 and (tr["tr_gedeckelt"] == 1).any()
           and np.allclose(timeform_ratings.daempfung([0, 2, 3, 4, 16]), [0, 4, 9, 15, 87]),
           f"Upgrade gedämpft (ab {timeform_ratings.UPGRADE_KNIE:g} FS-Punkten linear) und gedeckelt "
           f"(max. {tr['tr_upgrade'].max():.1f} lb, {int((tr['tr_gedeckelt'] == 1).sum())} Läufe gedeckelt)")
    c_ = 1.77
    pruefe(min(c_ * 600 / 2800 * float(timeform_ratings.daempfung(16)), timeform_ratings.UPGRADE_MAX_LB) == 12.0
           and round(c_ * 600 / 2800 * 16 ** 2, 1) == 97.1,
           "sehr langsam gelaufenes Rennen (2800 m, FS% 16 Punkte über dem Optimum): 12 lb statt 97 lb Upgrade")
    pruefe(np.allclose(tr["fs_race"].dropna(), tr.loc[tr["finish_pos"] == 1].set_index("race_id")["fs_pct"]
                       .reindex(tr.loc[tr["fs_race"].notna(), "race_id"]).to_numpy()),
           "Rennen-FS% aus den Zeiten des Führenden (hier der Sieger) = FS% des Siegers")

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

    pruefe(len(x["form_lines"]) <= rc.LETZTE_LAEUFE == 7, "höchstens 7 Formzeilen")

    seite = rc.html(d)
    pruefe(seite.startswith("<!doctype html>") and "/*__DATA__*/null" not in seite, "HTML mit eingesetzten Daten")


if __name__ == "__main__":
    sys.exit(main())
