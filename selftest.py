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
    print("\n11) Regel-Backtest: Skill-Regeln gegen den Markt")
    regel_backtest_pruefen()
    print("\n12) Tipp-Auswertung: Claude-Ausgabe gegen Ergebnis")
    tipp_auswertung_pruefen()
    print("\n13) Hypothesen-Backtest: bedingtes Logit")
    hypothesen_pruefen()

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


def hypothesen_pruefen() -> None:
    import numpy as np
    import hypothesen_backtest as hb
    rng = np.random.default_rng(0)
    z = []
    for r in range(3000):                         # wahrer Markt-Koeffizient 1,0, Zusatzeffekt 0,5
        q, x = rng.dirichlet(np.ones(10) * 2), (rng.random(10) < 0.2).astype(float)
        u = np.log(q) + 0.5 * x
        w = rng.choice(10, p=np.exp(u) / np.exp(u).sum())
        z += [{"race_id": r, "ln_p": np.log(q[i]), "x": x[i], "selten": float(i == 0 and r < 5), "won": int(i == w)}
              for i in range(10)]
    k = hb.clogit(pd.DataFrame(z), ["x", "selten"]).set_index("variable")
    pruefe(abs(k.loc["ln p_mkt (Markt)", "koef"] - 1) < 0.1 and abs(k.loc["x", "koef"] - 0.5) < 0.12
           and np.isnan(k.loc["selten", "koef"]) and k.loc["selten", "n_aktiv"] == 5,
           "Bedingtes Logit findet Markt- und Zusatzeffekt; zu seltene Merkmale werden nicht geschätzt")
    pruefe(bool(hb.PECH.search("A été enfermé dans la ligne droite")) and bool(hb.PECH.search("a manqué de place"))
           and not hb.PECH.search("a fini fort"), "Pech im Kommentar erkannt (enfermé, manqué de place)")


def tipp_auswertung_pruefen() -> None:
    import io, contextlib, json as _json, tempfile
    import tipp_auswertung as ta
    base = Path(tempfile.mkdtemp())
    (base / "tipps").mkdir(); (base / "racecards").mkdir()
    (base / "parquet" / "pmu_runners").mkdir(parents=True)
    block = {"tipps": [{"race_id": "20261007R4C1", "no": 1, "p": 0.5, "stufe": "0", "mq": 2.5, "angles": ["ratings"]},
                       {"race_id": "20261007R4C1", "no": 2, "p": 0.3, "stufe": "++", "mq": 4.0, "angles": ["klasse", "duell"]},
                       {"race_id": "20261007R4C1", "no": 3, "p": 0.2, "stufe": "−", "mq": None, "angles": ["pause"]}]}
    (base / "tipps" / "neu.md").write_text("Text\n```json\n" + _json.dumps(block) + "\n```\n", encoding="utf-8")
    alt = ("# Renntag 07.10.2026 – Réunion 4 – TEST\n\n## Rennen 2 – X\n\n| Pferd | a | b | c | d | e | f |\n"
           "| #5 ALPHA | 2/1 / 33% | 40% (35–45) | 2.5 | **3.0** | + (Edge +20%) | x |\n"
           "| #6 BETA | 3/1 / 25% | 60% (55–65) | 1.7 | **–** | − (Edge -5%) | y |\n")
    (base / "tipps" / "alt.md").write_text(alt, encoding="utf-8")
    pd.DataFrame([{"race_id": "20261007R4C1", "saddle_no": n, "finish_pos": f, "odds_final": o}
                  for n, f, o in [(1, 2, 2.0), (2, 1, 5.0), (3, 3, 6.0)]]
                 + [{"race_id": "20261007R4C2", "saddle_no": n, "finish_pos": f, "odds_final": o}
                    for n, f, o in [(5, 2, 3.0), (6, 1, 2.0)]]).to_parquet(base / "parquet" / "pmu_runners" / "20261007.parquet")
    karte = {"races": {"20261007R4C1": {"type": "Handicap", "runners": [
        {"no": 1, "p_prog": 0.5, "prono": {"sel": {"rank": 1}}}, {"no": 2, "p_prog": 0.2, "prono": {"sel": {"rank": 2}}},
        {"no": 3, "p_prog": 0.3, "prono": {"sel": {"rank": 3}}}]}}}
    (base / "racecards" / "racecard_20261007_claude.json").write_text(_json.dumps(karte), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        erg = ta.run(base)
    p = pd.read_parquet(base / "auswertung" / "tipps_protokoll.parquet")
    st = erg["stufe"].set_index("stufe")
    w = erg["wetten"].set_index("wetten")
    pruefe(len(p) == 5 and set(p["quelle"]) == {"block", "tabelle"} and st.loc["++", "siege"] == 1
           and st.loc["+", "n"] == 1 and {"klasse", "duell"} <= set(erg["angle"]["angle"])
           and w.iloc[0]["n"] == 2 and abs(w.iloc[0]["ergebnis"] - 3.0) < 1e-9,
           "Tipp-Auswertung: Protokoll-Block und alte Tabelle gelesen, Stufen, Angle-Typen und Wett-Ergebnis stimmen")


def regel_backtest_pruefen() -> None:
    """Zufallsdaten mit eingebautem Effekt: Wallache gewinnen im Claimer häufiger, als ihre Quote sagt."""
    import io, contextlib
    import numpy as np
    import regel_backtest as rb
    rng = np.random.default_rng(7)
    zeilen, pferde = [], [f"P{i}" for i in range(300)]
    for d in range(200):
        dt = pd.Timestamp("2025-01-01") + pd.Timedelta(days=d)
        for c, typ in enumerate(["Claimer", "Handicap"]):
            n = 10
            hs, odds = rng.choice(pferde, n, replace=False), rng.uniform(2, 20, n)
            sex = rng.choice(["HONGRES", "MALES", "FEMELLES"], n)
            w = (np.flatnonzero(sex == "HONGRES")[:1] if typ == "Claimer" and (sex == "HONGRES").any() and rng.random() < .5
                 else rng.choice(n, 1))[0]
            pos = np.r_[[1], rng.permutation(n - 1) + 2]
            pos = np.roll(pos, w)
            for i in range(n):
                zeilen.append(dict(race_id=f"{dt:%Y%m%d}R1C{c + 1}", date=dt, saddle_no=i + 1, horse_id=hs[i] + "|V",
                                   finish_pos=pos[i], odds_final=odds[i], starts=5, distance_m=1600, going_pmu="FAST",
                                   trainer_key="T", blinkers="SANS_OEILLERES", sex=sex[i], early_pct=rng.random(),
                                   n_runners=n, pace_ratio=100.0, weg_med=0.0, pos_gain_800_finish=0, d_L600_A=0.0,
                                   cls_epr_kl=1000.0, tr=80.0, arr=40.0, rtr=30.0, konfig=f"K{c}|1600", draw=i + 1,
                                   rel_place=(n - pos[i]) / (n - 1), course_key="BAHN", dist_bucket="mile",
                                   sire_key="S", age=4, valeur=30.0, racetype=typ, exp_place=0.3))
    h = pd.DataFrame(zeilen)
    h["won"], h["placed"] = (h["finish_pos"] == 1).astype(int), (h["finish_pos"] <= 3).astype(int)
    h["odds_rank"] = h.groupby("race_id")["odds_final"].rank(method="min")
    with contextlib.redirect_stdout(io.StringIO()):
        erg = rb.run(hist=h).set_index("gruppe")
    pruefe(erg.loc["Wallach · Claimer", "ae_sieg"] > 1.5 and 0.7 < erg.loc["Wallach · Handicap", "ae_sieg"] < 1.3,
           "Regel-Backtest erkennt den eingebauten Effekt (Wallach im Claimer) und nicht im Handicap")
    m = rb.merkmale(h)
    erst = m.drop_duplicates("horse_id")
    pruefe((erst["n_vor"] == 0).all() and erst["tage"].isna().all() and erst["tr_vor"].isna().all(),
           "Regel-Backtest: Merkmale nur aus früheren Läufen (erster Lauf ohne Vorwerte)")
    # Rennverlauf: Rennen, in dem die ersten drei früh vorne lagen -> „vorne begünstigt“; Pferd von hinten = „gegen“
    zz = []
    for k in range(40):
        ep = rng.permutation(10) / 9
        pos = np.arange(1, 11) if k == 39 else rng.permutation(10) + 1
        if k == 39:
            ep = np.r_[0.0, 0.05, 0.1, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
        for i in range(10):
            zz.append(dict(race_id=f"R{k}", early_pct=ep[i], finish_pos=pos[i], course_key="B", distance_m=1600,
                           dist_bucket="mile"))
    v = rb.rennverlauf(pd.DataFrame(zz), pd.DataFrame(zz[:390]))
    r39 = v[v["race_id"] == "R39"].set_index("finish_pos")
    pruefe(r39["verlauf_kl"].iloc[0] == "vorne" and r39.loc[10, "verlauf_pferd"] == "gegen"
           and r39.loc[1, "verlauf_pferd"] == "mit",
           "Rennverlauf: vorne gewonnen -> Vorne-Rennen; Pferd von hinten läuft gegen, Führender mit dem Verlauf")


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
    pruefe({"verlauf", "verlauf_wert", "verlauf_pferd", "verlauf_plus"} <= set(x["form_lines"][0])
           and x["form_lines"][0]["verlauf_plus"] is False,
           "Formzeile mit Rennverlauf (zu kleines Feld: kein Urteil, kein „gegen V.“)")
    pruefe(not {"odds", "odds_morning"} & set(x) and x["form_lines"][0]["odds"] is not None,
           "Karte ohne aktuelle Kurse (Morgen-/Totokurs); historische Endquote in den Formzeilen bleibt")
    pruefe(x["ae"]["trainer"]["d90"] == {"runs": 2, "wins": 1, "places": 2, "exp": 2.0, "ae": 1.0, "ae_win": 1.33,
                                         "epr": round((13500 + 5130) / 2), "epr_idx": None,
                                         "pl_exp": 2, "n_exp": 2},
           "A/E Platz 90 Tage: 2 Starter -> beide sicher platziert (erwartet 2, A/E 1,00); A/E Sieg 1,33 zum Vergleich")
    # Rating (Valeur) bereinigt nach dem heutigen Gewicht wie ARR: 30 bei 58 kg -> 27; 29 bei 54 kg -> 30 (vorne)
    hs = heute_s.assign(rating=[30.0, 29.0], weight_kg=[58.0, 54.0])
    xr, yr = rc.baue_daten(hist, heute_r, hs, tag)["races"][f"{tag:%Y%m%d}R1C1"]["runners"]
    pruefe(xr["rating_adj"] == 27.0 and yr["rating_adj"] == 30.0 and xr["rating"] == 30.0
           and (yr["rating_rank"], xr["rating_rank"], xr["rating_n"]) == (1, 2, 2),
           "Rating bereinigt: Valeur − heutiges Gewicht + 55, Rang im Feld nach dem bereinigten Wert")
    hs = heute_s.assign(rating=[30.0, None], weight_kg=[None, 57.0])
    xr, yr = rc.baue_daten(hist, heute_r, hs, tag)["races"][f"{tag:%Y%m%d}R1C1"]["runners"]
    pruefe(xr["rating_adj"] is None and xr["rating"] == 30.0 and yr["rating_adj"] is None,
           "Rating bereinigt: ohne Gewicht oder ohne Valeur kein bereinigter Wert")
    # Rennen vor 100 Tagen: 3 Starter (Quoten 3 / 5 / 9) -> Platz = 1.–2.; X wurde (zeitgleich) Zweiter
    px = rc.harville_platz(np.array([1 / 3, 1 / 5, 1 / 9]), 2)[1]
    t365 = x["ae"]["trainer"]["d365"]
    pruefe(t365["runs"] == 3 and abs(t365["exp"] - (2 + px)) < 0.01 and t365["ae"] == round(3 / (2 + px), 2),
           f"A/E Platz 365 Tage = 3 Plätze ÷ (2 + {px:.3f}) – Harville mit Korrektur, Marge herausgerechnet")
    q_ = [2.5, 4, 6, 10, 20, 30]
    rest_ = 1.19 - sum(1 / v for v in q_)
    p_ = np.array([1 / v for v in q_] + [rest_ / 2] * 2)
    roh_, korr_ = 1 / rc.harville_platz(p_, 3, 1, 1), 1 / rc.harville_platz(p_, 3)
    pruefe(np.allclose(roh_[:6], [1.29, 1.62, 2.15, 3.31, 6.30, 9.30], atol=0.02)
           and np.allclose(korr_[:6], [1.41, 1.76, 2.23, 3.13, 5.10, 6.84], atol=0.02)
           and abs(rc.harville_platz(p_, 3).sum() - 3) < 1e-9 and abs(rc.harville_platz(p_[:6], 2).sum() - 2) < 1e-9,
           "Harville-Platzquoten wie in der Tabelle (roh 1,29 … 9,30; korrigiert 1,41 … 6,84), Summe = Zahl der Plätze")
    pruefe(hist.loc[hist["race_id"] == rid(100, 1), "is_place"].tolist() == [1, 1, 1]
           and rc.PLATZ_GRENZE == 7, "is_place: bis 7 Starter 1.–2. (totes Rennen um Platz 2 zählt doppelt), ab 8 1.–3.")
    pruefe(rc._ae_trend({"runs": 6, "ae": 1.3}, {"runs": 90, "ae": 1.0}) == "hot"
           and rc._ae_trend({"runs": 12, "ae": 0.7}, {"runs": 90, "ae": 1.0}) == "cold"
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
    pruefe(len(g) == 1 and g[0]["horse"] == "Y" and g[0]["next"]["pos"] == 2 and g[0]["next"]["odds_rank"] == 1
           and g[0]["next"]["verdict"] == "schlechter" and "epr_idx" in g[0]["next"] and "val_idx" in g[0]["next"]
           and x["form_lines"][1]["rivals_stat"] == {"better": 0, "worse": 1, "same": 0, "ran": 1, "n": 2},
           "Gegner: gezeigt nur wieder gelaufene (Y, danach Platz 2 bei Quotenrang 1 -> schlechter, mit €/L+/Val+), "
           "Z ohne weiteren Start nicht; Bilanz über das ganze Feld 0 besser / 1 schlechter")
    nx_ = {"pos": 1}
    feld_ = [{"horse": c, "pos": p_, "next": nx_ if c != "C" else None} for c, p_ in
             [("A", 1), ("B", 2), ("C", 3), ("D", 4), ("E", 6), ("F", 7), ("G", 8)]]
    pruefe([z_["horse"] for z_ in rc.gegner_auswahl(feld_, 5)] == ["B", "D", "E", "F"]
           and [z_["horse"] for z_ in rc.gegner_auswahl(feld_, 8)] == ["E", "F", "G"],
           "Gegner-Auswahl: je 2 wieder gelaufene direkt davor und dahinter (C ohne Start übersprungen)")
    pruefe(f["top3_fifth"][0] == f["fifth"] and len(f["top3_fifth"]) == 3,
           "Pos. vor Finish: Fünftel des 1., 2., 3. im Ziel je Formzeile (Sieger X = eigenes Fünftel)")
    k = x["career"]["all"]
    pruefe((k["runs"], k["wins"], k["places"], k["earn"], k["epr"]) == (2, 1, 2, 16350, 8175)
           and x["career"]["d365"]["runs"] == 2,
           "Karriere aus der Datenbank: 2-1-2, Preisgeld 27000 × 50 % + 15000 × 19 % = 16350, je Lauf 8175")
    hx_a = hist[(hist["race_id"] == rid(10, 1)) & (hist["horse"] == "X")].iloc[0]
    geo = lambda *w: float(np.expm1(np.mean(np.log1p(w))))
    pruefe(hx_a["cls_epr"] == (2850 + 7500) / 2 and np.isnan(hist.loc[hist["race_id"] == rid(100, 1), "cls_epr"]).all()
           and hx_a["cls_epr_kl"] == round(geo(2850, 7500)) and bool(hx_a["epr_eigen"])
           and np.isnan(hist.loc[hist["race_id"] == rid(100, 1), "cls_epr_kl"]).all(),
           "Klasse früherer Rennen: angezeigt Ø Gewinn je Lauf der Teilnehmer (365 Tage davor, X 2850, Y 7500); "
           "Basis für €/L+ log-gemittelt (4623), Historie unter einem Jahr: 4-Jährige zählen als erfahren")
    kl = d["races"][f"{tag:%Y%m%d}R1C1"]["class"]
    pruefe(kl["epr"] == round((8175 + (7500 + 5130) / 2) / 2) and kl["epr_n"] == 2
           and kl["epr_base"] == round(geo(8175, (7500 + 5130) / 2)) and kl["epr_own"] == 2,
           "Klasse heute: angezeigt Ø Gewinn je Lauf (365 Tage) der Starter = (8175 + 6315) / 2, Basis €/L+ log-Ø 7185")
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
    ts_ = pd.Timestamp
    kz = pd.DataFrame(
        [{"horse_id": "A", "date": ts_("2025-01-01"), "prize_won": 0.0, "trainer_key": "T2", "owner_key": "O2"},
         {"horse_id": "A", "date": ts_("2026-03-01"), "prize_won": 500.0, "trainer_key": "T2", "owner_key": "O2"},
         {"horse_id": "A", "date": ts_("2026-09-01"), "prize_won": 0.0, "trainer_key": "T2", "owner_key": "O2"}]
        + [{"horse_id": f"H{i}", "date": ts_(f"2026-06-0{i}"), "prize_won": [0, 0, 0, 1200, 1200, 1200][i - 1],
            "trainer_key": "T", "owner_key": "O" if i < 6 else "O3"} for i in range(1, 7)]
        + [{"horse_id": "N", "date": ts_(d_), "prize_won": 0.0, "trainer_key": "T", "owner_key": "O"}
           for d_ in ("2026-08-01", "2026-09-01")]
        + [{"horse_id": "L", "date": ts_(d_), "prize_won": p_, "trainer_key": "TL", "owner_key": "OL"}
           for d_, p_ in (("2024-12-01", 900.0), ("2025-01-02", 300.0), ("2026-09-01", 0.0))]).assign(breeder_key=None, age=3)
    kz = rc.klassen_wert(rc.gewinn_vorher(kz))
    an = kz[kz["date"] == ts_("2026-09-01")].set_index("horse_id")
    soll_n = (0.5 * np.log1p(3600 / 7) + 0.3 * np.log1p(2400 / 6)) / 0.8
    pruefe(bool(an.loc["A", "epr_eigen"]) and abs(an.loc["A", "epr_kl"] - np.log1p(500)) < 1e-9
           and not an.loc["N", "epr_eigen"] and abs(an.loc["N", "epr_kl"] - soll_n) < 1e-9
           and bool(an.loc["L", "epr_eigen"]) and abs(an.loc["L", "epr_kl"] - np.log1p(600)) < 1e-9
           and (kz.loc[(kz["horse_id"] == "A") & (kz["date"] == ts_("2026-03-01")), "epr_kl"] == 0).all(),
           "Basis €/L+ je Pferd: ab einem Jahr seit dem ersten Start immer das eigene €/L (log; ohne Lauf im letzten "
           "Jahr über alle früheren Läufe), davor Trainer 50 % / Besitzer 30 % (Züchter fehlt -> hochgerechnet), "
           "Verbindungen erst ab 5 Läufen")
    ds = x["draw_stat"]
    pruefe(ds["mean"] == 1.0 and ds["dev"] == 0.5 and ds["n"] == 1 and not ds["ok"]
           and y["draw_stat"]["mean"] == 0.0 and y["draw_stat"]["n"] == 1,
           "Startbox: Ø relative Platzierung (Starter − Platz) / (Starter − 1) je Konfiguration × Box, Abweichung zu 0,5")
    pruefe(x["ae"]["owner"]["d365"]["runs"] == 5 and x["ae"]["breeder"]["d365"]["runs"] == 0,
           "A/E für Besitzer (und Züchter, hier ohne Angabe)")
    pv = x["ae"]["pedigree"]["sire"]
    pruefe(pv["horses"] == 3 and pv["horses3"] == 0 and pv["max_val3"] is None
           and x["ae"]["pedigree"]["dam_sire"]["horses"] == 1,
           "Abstammung: 3 verschiedene Pferde vom Vater, max Val nur aus 3-jährigen Nachkommen (hier keine)")
    alt_min = rc.POP_MIN_LAEUFE
    rc.POP_MIN_LAEUFE = 1
    try:
        d3 = rc.baue_daten(hist.assign(age=3), heute_r, heute_s, tag)
    finally:
        rc.POP_MIN_LAEUFE = alt_min
    x3 = d3["races"][f"{tag:%Y%m%d}R1C1"]["runners"][0]
    p3 = x3["ae"]["pedigree"]["sire"]
    t365 = x3["ae"]["trainer"]["d365"]
    pop_t = ((13500 + 5130 + 2850) / 3 + (7500 + 2850) / 2) / 2
    pruefe(p3["horses3"] == 1 and p3["max_val3"] == 40.0 and p3["max_val3_idx"] is None
           and x3["ae"]["trainer"]["d90"]["epr_idx"] == 100
           and t365["epr_idx"] == round(100 * t365["epr"] / pop_t)
           and d3["params"]["pop"]["trainer_d365"] == round(pop_t, 1),
           f"€/L+ = 100 × €/Lauf ÷ Ø der Population (Trainer 365 Tage: {t365['epr_idx']}); "
           "max Val 3j nur aus 3-Jährigen, Val+ erst ab 3 Linien-Pferden")
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
    hm = x["hcp_mark"]
    pruefe(hm["kind"] == "sieg" and hm["val"] == 40.0 and y["hcp_mark"] is None
           and rc.handicap_marke(hist[(hist["horse"] == "X") & (hist["won"] == 0)].assign(valeur=36.0, racetype="Handicap")
                                 .sort_values("date", ascending=False), 38)["kind"] == "platz",
           "Letzte Siegmarke im Handicap (Valeur 40), ohne Sieg die letzte Platzmarke")
    bl = {z["label"]: z["runs"] for z in x["pref"]["horse"]["blinkers"]}
    pruefe(bl == {"ohne": 1, "australisch": 1}, "Pferd nach Scheuklappen: ohne / australisch")
    sel_ = {"selection": [{"cote_prob": "4/1", "id_nav_partant": "x-3", "rang": 1, "num_partant": 2},
                          {"cote_prob": "7/2", "rang": 2, "num_partant": 1}]}
    det_ = {"commentaire": {"texte": "Y devrait s'imposer."},
            "avis": [{"societe": "Turf-fr.com", "journaliste": "Rédaction",
                      "pronostics": [{"numPmu": 2, "nom": "Y"}, {"numPmu": 1, "nom": "X"}]},
                     {"societe": "Equidia", "pronostics": [{"numPmu": 1, "nom": "X"}, {"numPmu": 2, "nom": "Y"}]},
                     {"societe": "Paris-Turf", "pronostics": [{"numPmu": 2, "nom": "Y"}]}],
            "cribles": [{"numPmu": 1, "nom": "X", "commentaire": "Bien placé."}, {"commentaire": "Sans numéro."}]}
    pg_ = pmu.prognose(sel_, det_)
    pruefe(pg_["selection"][0] == {"no": 2, "rank": 1, "cote": "4/1", "cote_dec": 4.0}
           and pg_["selection"][1]["cote_dec"] == 3.5 and pg_["text"] == "Y devrait s'imposer."
           and pg_["cribles"] == {1: "Bien placé."} and len(pg_["cribles_ohne"]) == 1 and len(pg_["tips"]) == 3,
           "PMU-Prognose: cote probable 4/1 -> 4,0 (Rückzahlung je 1 €), Kommentar, Tipps, Kurzkommentare je Starter")
    dp = rc.baue_daten(hist, heute_r, heute_s, tag, prognosen={(1, 1): pg_})["races"][f"{tag:%Y%m%d}R1C1"]
    xp, yp = dp["runners"][0]["prono"], dp["runners"][1]["prono"]
    pruefe(dp["prono"]["consensus"] == [2, 1] and xp["sel"]["cote_dec"] == 3.5 and xp["crible"] == "Bien placé."
           and xp["tips"] == {"n": 2, "of": 3, "top3": 2, "avg": 1.5} and yp["tips"]["n"] == 3 and yp["sel"]["rank"] == 1,
           "Prognose in der Race Card: Konsens der Tipps (Borda), cote probable und Kurzkommentar je Starter")
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
    alt_d = ue._dienste
    try:
        def sperre(t):
            raise type("TooManyRequests", (Exception,), {})("zu viele Anfragen")
        ue._dienste = lambda: [("Google", sperre), ("MyMemory", lambda t: "DE: " + t)]
        erg = ue.uebersetze(["Ça va."], None)
    finally:
        ue._dienste = alt_d
    pruefe(erg == {"Ça va.": "DE: Ça va."},
           "Übersetzung weicht aus: Google gesperrt (TooManyRequests) -> nächster Dienst")
    import requests as rq_
    gesendet = {"urls": []}

    class Antwort:
        def __init__(self, code, daten=None):
            self.status_code, self._d, self.text = code, daten, "" if daten else "Forbidden"
        def json(self):
            return self._d

    def post_(url, headers=None, json=None, timeout=None):
        gesendet["urls"].append(url)
        gesendet.update(headers=headers, json=json)
        ok = headers["Authorization"] == "DeepL-Auth-Key abc:fx"
        return Antwort(200, {"translations": [{"text": "Stark beendet."}]}) if ok else Antwort(403)
    alt_post = rq_.post
    rq_.post = post_
    try:
        de_ok = ue._deepl(' abc:fx ')("A fini fort.")
        try:
            ue._deepl("falsch")("A fini fort.")
            fehler = None
        except ue.DeeplFehler as e:
            fehler = str(e)
    finally:
        rq_.post = alt_post
    pruefe(de_ok == "Stark beendet." and gesendet["urls"] == ["https://api-free.deepl.com/v2/translate",
                                                              "https://api.deepl.com/v2/translate"]
           and gesendet["json"] == {"text": ["A fini fort."], "source_lang": "FR", "target_lang": "DE"}
           and fehler is not None and "403" in fehler,
           "DeepL direkt über die API: Schlüssel im Header (nicht als auth_key-Parameter), Free-Schlüssel (:fx) -> "
           "api-free, 403 wird als Grund gemeldet")
    ow = rc._wechsel({"owner_key": "NEU", "owner": "NEU"}, {"owner_key": "ALT", "owner": "ALT"})
    pruefe([c["key"] for c in ow] == ["OW"] and "Besitzerwechsel" in ow[0]["text"],
           "Hinweis Besitzerwechsel gegenüber dem letzten Lauf")
    b1, b2, b3 = rc.box_urteil(0.6, 100), rc.box_urteil(0.6, 10), rc.box_urteil(0.53, 2000)
    pruefe(b1["sig"] and not b2["sig"] and not b3["sig"] and b1["dev"] == 0.1,
           "Startbox auffällig nur bei ≥ 2 Standardfehlern und ≥ 0,05 Abweichung (0,60 aus 100 ja, aus 10 nein; 0,53 nein)")
    pruefe(f["draw_stat"]["n"] == 1 and not f["draw_stat"]["sig"],
           "Startbox-Urteil auch je früherem Lauf (Konfiguration und Box dieses Laufs)")

    # Bahnart fehlt im Tagesprogramm: Schlüssel an die Historie angleichen bzw. aus der Detailseite nachladen
    hk = pd.Series(["DEAUVILLE|1300|PSF|PISTE EN SABLE FIBRE|CORDE_DROITE"] * 50
                   + ["DEAUVILLE|1300|?|PISTE EN SABLE FIBRE|CORDE_DROITE"] * 2
                   + ["DEAUVILLE|1300|HERBE|LIGNE DROITE|CORDE_DROITE"] * 80)
    ang = rc.konfig_angleichen(pd.Series(["DEAUVILLE|1300|?|PISTE EN SABLE FIBRE|CORDE_DROITE",
                                          "DEAUVILLE|1300|HERBE|LIGNE DROITE|CORDE_DROITE",
                                          "MANS|1600|?||CORDE_GAUCHE"]), hk)
    pruefe(ang.tolist() == ["DEAUVILLE|1300|PSF|PISTE EN SABLE FIBRE|CORDE_DROITE",
                            "DEAUVILLE|1300|HERBE|LIGNE DROITE|CORDE_DROITE", "MANS|1600|?||CORDE_GAUCHE"],
           "Startbox: fehlende Bahnart heute wird aus der Historie gleicher Bahn/Distanz/Parcours/Corde ergänzt")

    class DetailSession:
        def get(self, url, headers=None, timeout=None):
            import json as _j
            if "R4/C3" in url:
                return FakeResponse(text=_j.dumps({"typePiste": "PSF", "parcours": "Piste en sable fibré"}))
            return FakeResponse(status=404)
    rz2 = rc.bahnart_nachladen([{"reunion": 4, "race_no": 3, "track_type": None, "parcours": None},
                                {"reunion": 3, "race_no": 1, "track_type": None, "parcours": None},
                                {"reunion": 1, "race_no": 1, "track_type": "HERBE"}],
                               date(2026, 10, 5), DetailSession(), pause=0)
    pruefe(rz2[0]["track_type"] == "PSF" and rz2[0]["parcours"] == "Piste en sable fibré"
           and rz2[1]["track_type"] is None and rz2[2]["track_type"] == "HERBE",
           "Startbox: Bahnart aus der Detailseite des Rennens nachgeladen (fehlt sie dort, bleibt sie leer)")
    pc, ptr = x["pref"]["horse"]["course"], y["pref"]["horse"]["trainer"]
    pruefe(len(pc) == 1 and pc[0]["today"] and {z["label"] for z in ptr} == {"Tr", "And"}
           and not any(z["today"] for z in ptr),
           "Pferd nach Kurs: nur die heutige Bahn; Pferd nach Trainer: alle bisherigen Trainer")
    pruefe(f["cls_epr_idx"] == 100 and f["cls_epr"] == 5175 and "cls_epr_kl" not in f
           and kl["epr_idx"] == round(100 * kl["epr_base"] / round(geo(2850, 7500)))
           and abs(d["params"]["pop"]["rennen_epr"] - round(geo(2850, 7500))) < 0.01,
           f"Rennstärke €/L+: log-Ø Gewinn je Lauf der Teilnehmer ÷ Ø aller früheren Rennen (heute {kl['epr_idx']}); "
           "Formzeile zeigt weiter den einfachen Ø")
    pruefe(f["cls_val_idx"] == 100 and d["params"]["pop"]["rennen_val"] == 40.0,
           "Val+: Ø Valeur der Teilnehmer ÷ Ø aller früheren Rennen (einziges Rennen mit Valeur -> 100)")
    pruefe(len(x["duels"]) == 1 and x["duels"][0]["date"] == str(tag - timedelta(days=10)),
           "Direkte Duelle: nur ≤ 120 Tage, ±200 m zu heute, Boden innerhalb einer Stufe (Duell über 2000 m Lourd fällt weg)")
    alt = (rc.DUELL_TAGE, rc.DUELL_DIST_M, rc.DUELL_BODEN)
    rc.DUELL_TAGE, rc.DUELL_DIST_M, rc.DUELL_BODEN = 365, 10_000, False          # Rechnung ohne Filter
    x_d = rc.baue_daten(hist, heute_r, heute_s, tag)["races"][f"{tag:%Y%m%d}R1C1"]["runners"][0]
    rc.DUELL_TAGE, rc.DUELL_DIST_M, rc.DUELL_BODEN = alt
    ds_ = x_d["duels_sum"]
    pruefe(ds_["n"] == 1 and ds_["ahead"] == 1 and ds_["rivals"][0]["exp_l"] == 2.0 and ds_["rivals"][0]["n"] == 2,
           "Duell-Bilanz: letztes Duell je Gegner, Abstand ± Gewichtsverschiebung (1 kg = 1 L) -> vorne erwartet")
    sim = rc._duell_bilanz([{"rival": "A", "rival_no": 3, "date": "2026-05-01", "diff_l": 1.0, "shift": 2.5},
                            {"rival": "A", "rival_no": 3, "date": "2026-01-01", "diff_l": 5.0, "shift": 0.0}])
    pruefe(sim["rivals"][0]["exp_l"] == -1.5 and sim["behind"] == 1,
           "Duell-Bilanz: 1 L vorn, heute 2,5 kg ungünstiger -> 1,5 L hinten erwartet (älteres Duell zählt nicht)")
    tt = y["pref"]["horse"]["trainer"]
    pruefe([z["label"] for z in tt] == ["Tr", "And"] and tt[0]["from"] == tt[0]["to"] == str(tag - timedelta(days=10))
           and tt[1]["to"] == str(tag - timedelta(days=100)),
           "Pferd nach Trainer: Zeitraum je Trainer, neuester zuerst")
    T0 = pd.Timestamp(tag)
    def lf(race, tage, going, dist, pferde):
        n = len(pferde)
        return [{"race_id": race, "date": T0 - timedelta(days=tage), "going_pmu": going, "distance_m": dist,
                 "horse_id": hid, "horse": hid, "finish_pos": pos, "lengths_behind": lb, "weight_kg": w,
                 "rel_place": (n - pos) / (n - 1)} for pos, (hid, lb, w) in enumerate(pferde, 1)]
    hi = pd.DataFrame(lf("A", 30, "FAST", 1600, [("H", None, 58), ("C", 2.0, 56), ("F1", 3, 55), ("F2", 4, 55)])
                      + lf("B", 20, "SLOW", 1700, [("R", None, 57), ("C", 1.0, 57), ("F3", 2, 55), ("F4", 3, 55)])
                      + lf("P", 10, "PSF", 1600, [("R", None, 57), ("C", 9.0, 57), ("F5", 10, 55), ("F6", 11, 55)])
                      + lf("O", 200, "FAST", 1600, [("R", None, 57), ("C", 9.0, 57), ("F7", 10, 55), ("F8", 11, 55)]))
    ib = rc.indirekte_basis(hi, T0)
    ind = rc._indirekte_duelle(ib, {"H": {"weight": 60.0, "no": 1}, "R": {"weight": 56.0, "no": 2}}, "Bon", 1600)
    e_h, e_r = ind["H"]["rivals"][0], ind["R"]["rivals"][0]
    pruefe(e_h["rival"] == "R" and e_h["n"] == 1 and e_h["common"] == ["C"] and e_h["then_kg"] == 3.4
           and e_h["w_today"] == 4.0 and e_h["exp_kg"] == -0.6 and e_h["exp_l"] == -0.5
           and ind["H"]["behind"] == 1 and e_r["exp_kg"] == 0.6,
           "Indirekte Duelle: über gemeinsamen Gegner (2 L × 1,2 + 2 kg = 4,4 vs 1 L × 1,0 = 1,0 -> 3,4 kg), "
           "heute 4 kg mehr -> 0,6 kg / 0,5 L hinten; PSF-Rennen und Rennen > 120 Tage zählen nicht")
    pruefe(rc._boden_nah("Bon", "Souple") and not rc._boden_nah("Bon", "Lourd") and not rc._boden_nah("PSF", "Bon")
           and rc._boden_nah("Bon léger", "Bon"), "Boden innerhalb einer Stufe, PSF nur mit PSF")
    du = x_d["duels"]
    pruefe(len(du) == 2 and du[0]["rival"] == "Y" and du[0]["diff_l"] == 2.0 and du[0]["shift"] == 0.0
           and du[0]["rival_no"] == 2 and du[1]["pos"] == 2 and du[1]["rival_pos"] == 1
           and du[0]["exp_l"] == 2.0 and du[1]["exp_l"] == -2.0,
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

    pruefe(len(x["form_lines"]) <= rc.LETZTE_LAEUFE + 3 and rc.LETZTE_LAEUFE == 7
           and all("same" in f and "extra" in f for f in x["form_lines"]),
           "höchstens 7 + 3 Formzeilen, je Zeile Kennzeichen K/D/B und ob zusätzlich")

    # Letzte Läufe: Kennzeichen K/D/B; fehlt ein Merkmal unter den letzten 7, der letzte ältere Lauf dazu
    vv = pd.DataFrame([{"race_id": f"r{i}", "course_key": c, "distance_m": d, "going_pmu": g}
                       for i, (c, d, g) in enumerate(
                           [("A", 1600, "SLOW")] * 7 + [("A", 1600, "FAST"), ("X", 1950, "FAST"),
                            ("X", 1600, "SLOW"), ("X", 1900, "VERY SLOW")])])
    aus = rc.formzeilen_auswahl(vv, "X", 1850, "FAST")
    pruefe([z["race_id"] for z, _ in aus] == [f"r{i}" for i in range(7)] + ["r7", "r8"]
           and [e for _, e in aus][7:] == [["B"], ["K", "D"]]
           and rc.gleich_heute(vv.iloc[8], "X", 1850, "FAST") == ["K", "D", "B"]
           and rc.gleich_heute(vv.iloc[8], "X", 1849, "FAST") == ["K", "B"]
           and rc.gleich_heute(vv.iloc[0], "X", 1850, "FAST") == [],
           "Formzeilen: letzter Lauf auf Boden bzw. Kurs+Distanz (±100 m) zusätzlich (ein Lauf deckt mehrere ab)")
    pruefe(rc.gleich_heute(pd.Series({"course_key": "X", "distance_m": 1900, "going_pmu": "PSF"}), "X", 1900, "FAST")
           == ["D"] and rc.gleich_heute(pd.Series({"course_key": "X", "distance_m": 1900, "going_pmu": "PSF"}),
                                         "X", 1900, "PSF") == ["K", "D", "B"],
           "Formzeilen: Kurs nur bei gleichem Belag (PSF gegen Gras)")
    aus = rc.formzeilen_auswahl(vv, "A", 1600, "SLOW")
    pruefe(len(aus) == 7 and all(e is None for _, e in aus), "Formzeilen: alles unter den letzten 7 -> nichts dazu")
    aus = rc.formzeilen_auswahl(vv.head(5), "X", 1850, "FAST")
    pruefe(len(aus) == 5, "Formzeilen: weniger als 7 Läufe -> nur diese")

    # PMU-Prognose: Platz im Konsens der Tippgeber (Borda), gleiche Punkte = gleicher Platz
    _, je = rc._prognose_rennen({"selection": [{"no": 3, "rank": 1, "cote": "3/1", "cote_dec": 3.0}],
                                 "tips": [{"source": "A", "nos": [3, 5, 7]}, {"source": "B", "nos": [5, 3, 8]}]})
    pruefe(je[3]["konsens"] == {"pos": 1, "of": 4, "pts": 5} and je[5]["konsens"]["pos"] == 1
           and je[7]["konsens"]["pos"] == 3 and je[8]["konsens"]["pos"] == 3 and "konsens" not in je.get(9, {}),
           "Prognose: Platz im Konsens der Tippgeber je Pferd (Gleichstand = gleicher Platz)")

    # Claude-Version der Karte (claude_export): alle Daten außer Trikots/Kursen, vorgerechnet
    import claude_export as ce, copy as _copy, json
    dd = _copy.deepcopy(d)
    rr = next(iter(dd["races"].values()))
    rr["status"] = "PROGRAMMEE"
    for i_, x_ in enumerate(rr["runners"]):
        x_["prono"] = {"sel": {"rank": 2 - i_, "cote": f"{2 + i_}/1", "cote_dec": 3.0 + i_}}
        x_["odds"], x_["odds_morning"], x_["silks"] = 4.0, 5.0, "data:image/png;base64,AAAA"
    nr_ = _copy.deepcopy(rr["runners"][0]); nr_["no"], nr_["nr"] = 9, True
    rr["runners"].append(nr_)
    fertig = _copy.deepcopy(rr); fertig.update(race_id="FERTIG", status="ARRIVEE_DEFINITIVE")
    dd["races"]["FERTIG"] = fertig
    ex = ce.export(dd)
    eo, ef = ex["races"][rr["race_id"]], ex["races"]["FERTIG"]
    txt = json.dumps(ex, ensure_ascii=False)
    pruefe(eo["offen"] and not ef["offen"] and len(ef["runners"]) == 2 and eo["nr"] == [9]
           and [x_["no"] for x_ in eo["nichtstarter"]] == [9]
           and [x_["no"] for x_ in eo["runners"]] == eo["vorgerechnet"]["reihenfolge"] == [2, 1]
           and abs(sum(x_["p_prog"] for x_ in eo["runners"]) - 1) < 1e-3
           and eo["runners"][0]["p_prog"] < eo["runners"][1]["p_prog"]       # 4,0 dezimal < 3,0 dezimal
           and eo["vorgerechnet"]["marge"] == round(1 / 3 + 1 / 4, 3)
           and "odds_morning" not in txt and '"silks"' not in txt and "base64" not in txt
           and all("odds" not in x_ for x_ in eo["runners"])
           and all("rivals" not in f_ and "rivals_nah" in f_ and "rivals_stat" in f_
                   and not (set(f_) & ce.OHNE_FORMZEILE) for x_ in eo["runners"] for f_ in x_["form_lines"]),
           "Claude-Version: Starter nach Prognose-Rang, p_prog (Potenzmethode) und Marge vorgerechnet, ohne "
           "Kurse/Trikots; Formzeilen mit nächsten Gegnern statt voller Liste, ohne Zwischenwerte; Nichtstarter und "
           "gelaufene Rennen vollständig dabei")

    def _pfade(o, pre=""):
        """Alle Schlüsselpfade (Listenindizes zu [] zusammengefasst)."""
        if isinstance(o, dict):
            return {q for k, v in o.items() for q in {f"{pre}.{k}"} | _pfade(v, f"{pre}.{k}")}
        if isinstance(o, list):
            return {q for v in o for q in _pfade(v, pre + "[]")}
        return set()
    def _norm(q):            # Rennschlüssel (Datum…/FERTIG) weg, Nichtstarter zählen wie Starter
        q = q.replace(".nichtstarter[]", ".runners[]")
        return ".".join(t for t in q.split(".") if not t.startswith(("20", "FERTIG")))
    ausgelassen = (".runners[].silks", ".runners[].odds", ".runners[].odds_morning",
                   *(f".form_lines[].{k}" for k in ce.OHNE_FORMZEILE))
    weg = lambda q: q.endswith(ausgelassen) or any(o + "." in q or o + "[]" in q for o in ausgelassen)  # + Unterfelder
    fehlend = sorted({_norm(q) for q in _pfade(dd)} - {_norm(q) for q in _pfade(ex)}
                     - {q for q in {_norm(q) for q in _pfade(dd)} if weg(q)})
    pruefe(not fehlend, "Claude-Version vollständig: jedes Feld der Race Card außer Trikots/Kursen/Gegnerliste/Zwischenwerten"
           + (f" – fehlt: {fehlend[:5]}" if fehlend else ""))
    dn = _copy.deepcopy(dd)
    x_ = next(iter(dn["races"].values()))["runners"][0]
    x_["neues_feld"] = {"a": 1}; x_["form_lines"][0]["neu_fz"] = 2; next(iter(dn["races"].values()))["neu_r"] = 3
    en = ce.export(dn)
    eon = en["races"][rr["race_id"]]
    pruefe(any(y_.get("neues_feld") == {"a": 1} for y_ in eon["runners"] + eon["nichtstarter"])
           and any(f_.get("neu_fz") == 2 for y_ in eon["runners"] for f_ in y_["form_lines"]) and eon["neu_r"] == 3,
           "Claude-Version: neue Felder der Race Card kommen automatisch mit")
    p_ = ce.potenz_normierung({1: 1 / 3.4, 2: 1 / 17, 3: 1 / 3, 4: 1 / 5, 5: 1 / 9, 6: 1 / 6, 7: 1 / 12, 8: 1 / 7})
    pruefe(abs(sum(p_.values()) - 1) < 1e-6 and p_[2] < (1 / 17) / sum([1 / 3.4, 1 / 17, 1 / 3, 1 / 5, 1 / 9, 1 / 6,
                                                                          1 / 12, 1 / 7]),
           "Claude-Version: Potenzmethode zieht die Marge stärker beim Außenseiter ab als proportional")
    skill = (Path(__file__).parent / ".claude/skills/rennkarten-durchgang/SKILL.md").read_text(encoding="utf-8")
    x0 = eo["runners"][0]
    pruefe(all(k in x0 for k in ("form_lines", "pref", "ae", "career", "rating_adj", "prono", "duels", "starts",
                                 "days", "changes", "badges", "hcp_mark", "tr", "arr", "rtr", "summary", "luecke"))
           and all(k in eo for k in ("prono", "pace", "bias", "class", "going_source", "going_assumed", "declared"))
           and all(k in skill for k in ("_claude.json", "p_prog", "vorgerechnet", "rivals_nah", "luecke")),
           "Claude-Version: Felder, die der Skill liest, sind da; der Skill kennt die Claude-Version")

    # Vorlieben: A/E deutlich und signifikant anders als der Rest derselben Person/Linie
    ges = {"n_exp": 400, "exp": 100.0, "pl_exp": 100}                       # A/E gesamt 1,0
    gut = rc.ae_abweichung({"n_exp": 60, "exp": 15.0, "pl_exp": 30}, ges)    # Teil A/E 2,0, Rest 70/85
    pruefe(gut["sig"] and gut["dir"] == 1 and gut["ratio"] > 1.2 and gut["z"] >= 2,
           "Vorlieben: deutlich und signifikant besser als der Rest -> ▲")
    schlecht = rc.ae_abweichung({"n_exp": 80, "exp": 20.0, "pl_exp": 8}, ges)
    pruefe(schlecht["sig"] and schlecht["dir"] == -1, "Vorlieben: deutlich und signifikant schlechter -> ▼")
    pruefe(not rc.ae_abweichung({"n_exp": 6, "exp": 1.5, "pl_exp": 3}, ges)["sig"],
           "Vorlieben: deutlich, aber zu wenige Läufe -> nicht auffällig")
    gross = {"n_exp": 40000, "exp": 10000.0, "pl_exp": 10000}
    knapp = rc.ae_abweichung({"n_exp": 20000, "exp": 5000.0, "pl_exp": 5400}, gross)
    pruefe(abs(knapp["z"]) >= 2 and not knapp["sig"], "Vorlieben: signifikant, aber unter ×1,2 -> nicht auffällig")
    pruefe(rc.ae_abweichung({"n_exp": 10, "exp": 2.5, "pl_exp": 3}, {"n_exp": 10, "exp": 2.5, "pl_exp": 3}) is None
           and rc.ae_abweichung(rc._leer(), ges) is None and rc.ae_abweichung({"n_exp": 5, "exp": 1.0, "pl_exp": 1}, None)
           is None, "Vorlieben: ohne Rest oder ohne Läufe kein Urteil")
    pruefe(all("dev" in x["pref"][g][k] for g, ks in (("trainer", ("jockey", "course", "racetype", "age")),
                                                      ("jockey", ("course", "trainer", "horse")),
                                                      ("sire", ("distance", "going", "age")),
                                                      ("dam_sire", ("distance", "going", "age"))) for k in ks),
           "Vorlieben: jeder Eintrag von Trainer, Jockey, Vater, Muttervater mit Abweichungs-Urteil")

    # Manuelle Bodenangaben (boden_manuell.json): nur wenn PMU keine hat, nie für PSF, Tippfehler übergangen
    import json as _json, tempfile as _tf
    from datetime import date as _date
    with _tf.TemporaryDirectory() as td:
        f = Path(td) / "b.json"
        f.write_text(_json.dumps({"datum": "", "bahnen": {"Chantilly": "Souple", "Saint-Cloud": "Bon soupe",
                                                          "Deauville": "PSF Standard", "Toulouse": "Lourd",
                                                          "Vichy": ""}}), encoding="utf-8")
        m = rc.boden_manuell_laden(f, _date(2026, 10, 3))
        pruefe(m == {"CHANTILLY": "Souple", "TOULOUSE": "Lourd"},
               "Boden manuell: gültige Gras-Angaben gelesen, Tippfehler/PSF/leer übergangen")
        f.write_text(_json.dumps({"datum": "2026-10-02", "bahnen": {"Chantilly": "Souple"}}), encoding="utf-8")
        pruefe(rc.boden_manuell_laden(f, _date(2026, 10, 3)) == {}
               and rc.boden_manuell_laden(f, _date(2026, 10, 2)) == {"CHANTILLY": "Souple"},
               "Boden manuell: mit Datum nur für die Rennkarte dieses Tages")
        f.write_text("{kaputt", encoding="utf-8")
        pruefe(rc.boden_manuell_laden(f, _date(2026, 10, 3)) == {}, "Boden manuell: kaputte Datei -> nicht verwendet")
    rr = pd.DataFrame([
        {"hippodrome": "CHANTILLY", "going": "Bon", "track_type": "HERBE", "parcours": None},
        {"hippodrome": "CHANTILLY", "going": None, "track_type": "HERBE", "parcours": None},
        {"hippodrome": "CHANTILLY", "going": None, "track_type": "PSF", "parcours": None},
        {"hippodrome": "CHANTILLY", "going": None, "track_type": None, "parcours": "Piste en sable fibré"},
        {"hippodrome": "TOULOUSE LA CEPIERE", "going": "", "track_type": "HERBE", "parcours": None},
        {"hippodrome": "VICHY", "going": None, "track_type": "HERBE", "parcours": None},
        {"hippodrome": "SABLE SUR SARTHE", "going": None, "track_type": "HERBE", "parcours": "Sablé"}])
    ra = rc.boden_manuell_anwenden(rr, {"CHANTILLY": "Souple", "TOULOUSE": "Lourd", "SABLE SUR SARTHE": "Collant"})
    pruefe(list(ra["going_quelle"]) == ["PMU", "manuell", "PSF", "PSF", "manuell", "Annahme", "manuell"]
           and list(ra["going"])[:5] == ["Bon", "Souple", "PSF", "PSF", "Lourd"] and ra["going"].iloc[6] == "Collant"
           and [rc.going_klasse(g) for g in ra["going"]] == ["FAST", "SLOW", "PSF", "PSF", "VERY SLOW", "FAST",
                                                               "VERY SLOW"],
           "Boden manuell: PMU hat Vorrang, PSF nach Bahnart, Bahnname auch verkürzt, sonst Annahme FAST")
    bd = _json.loads(rc.BODEN_DATEI.read_text(encoding="utf-8"))
    alle = [w for ws in bd["moegliche_angaben"].values() for w in ws]
    pruefe(all(rc.rtr_arr.boden_gruppe(w) == g for g, ws in bd["moegliche_angaben"].items() for w in ws)
           and set(alle) == {k for k, v in rc.rtr_arr.GOING_MAP.items() if v != "PSF"}
           and all(rc.rtr_arr.boden_gruppe(v) for v in bd["bahnen"].values()),
           "boden_manuell.json: Liste der möglichen Angaben = GOING_MAP (Gras), alle Bahnen gültig")

    seite = rc.html(d)
    pruefe(seite.startswith("<!doctype html>") and "/*__DATA__*/null" not in seite, "HTML mit eingesetzten Daten")


if __name__ == "__main__":
    sys.exit(main())
