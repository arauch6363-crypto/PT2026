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

import json
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
    print("\n14) Power-Modell: Merkmale ohne Blick in die Zukunft, Training, Vorhersage")
    power_modell_pruefen()
    abstammung_pruefen()
    festkurse_pruefen()
    festkurse_aktualisieren_pruefen()

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
    T = pd.Timestamp("2026-09-01")
    rennen_ = [("P1", 30, [("A", 1, None), ("B", 2, 2.0), ("F1", 3, 4.0), ("F2", 4, 6.0)]),
               ("P2", 20, [("B", 1, None), ("C", 2, 1.0), ("F3", 3, 3.0), ("F4", 4, 5.0)]),
               ("HEUTE", 0, [("A", None, None), ("B", None, None), ("C", None, None)])]
    hd = pd.DataFrame([{"race_id": rid_, "date": T - pd.Timedelta(days=t_), "horse_id": hn, "horse": hn, "saddle_no": i + 1,
                        "weight_kg": 57.0, "distance_m": 1600, "going": "Bon", "going_pmu": "FAST", "finish_pos": pos,
                        "lengths_behind": lb, "n_runners": len(feld), "hippodrome": "X", "racetype": "Handicap",
                        "rel_place": (len(feld) - pos) / (len(feld) - 1) if pos else np.nan}
                       for rid_, t_, feld in rennen_ for i, (hn, pos, lb) in enumerate(feld)])
    dm = hb.duell_merkmale(hd, hd["race_id"] == "HEUTE", log_alle=0)
    dh = dm.join(hd["horse"]).dropna(subset=["duel_rank"]).set_index("horse")
    pruefe(list(dh.sort_values("duel_rank").index) == ["A", "B", "C"] and (dh["duel_of"] == 3).all()
           and abs(dh.loc["A", "duel_score"] - dh.loc["B", "duel_score"] - 2.0) < 0.15,
           "H6: Duell-Rangfolge im Backtest aus früheren Läufen nachgerechnet (A schlägt B 2 L, B schlägt C 1 L, "
           "A–C indirekt über B -> A, B, C)")
    pruefe(bool(hb.PECH.search("A été enfermé dans la ligne droite")) and bool(hb.PECH.search("a manqué de place"))
           and not hb.PECH.search("a fini fort"), "Pech im Kommentar erkannt (enfermé, manqué de place)")


def _power_synth(tage=40, rennen=3, feld=8, pferde=90, seed=3) -> pd.DataFrame:
    """Kleine Historie wie racecard.vorbereiten mit eingebautem Signal: Stärke des Pferdes + Trainer-Effekt."""
    import numpy as np
    rng = np.random.default_rng(seed)
    fae, trn = rng.normal(0, 1, pferde), rng.integers(0, 8, pferde)
    t_eff = rng.normal(0, .6, 8)
    z = []
    for d in range(tage):
        dt = pd.Timestamp("2025-03-01") + pd.Timedelta(days=d)
        for c in range(rennen):
            ids = rng.choice(pferde, feld, replace=False)
            dist, going = int(rng.choice([1400, 1600, 2000])), str(rng.choice(["FAST", "SLOW"]))
            perf = fae[ids] + t_eff[trn[ids]] + rng.normal(0, 1, feld)
            pos = np.empty(feld, int); pos[np.argsort(-perf)] = np.arange(1, feld + 1)
            for k, i in enumerate(ids):
                fehlt = rng.random() < .25                 # Lücken wie in echt: kein Tracking, kein TR/ARR
                z.append(dict(race_id=f"{dt:%Y%m%d}R1C{c + 1}", date=dt, horse_id=f"P{i}|S", horse=f"P{i}",
                              saddle_no=k + 1, weight_kg=55.0 + k % 4, distance_m=dist, going=going, going_pmu=going,
                              dist_group=f"{dist - 199}-{dist}", course_key=f"B{c}", hippodrome=f"B{c}",
                              racetype=["Handicap Categorie Divise", "Group 3", "Claimer"][c],
                              conditions_age=None if fehlt else "TROIS_ANS_ET_PLUS", konfig=f"K{c}", draw=k + 1,
                              age=3 + i % 4, sex="HONGRES" if i % 7 == 0 and d >= 20 else "MALES", valeur=np.nan if fehlt else 30 + 5 * fae[i],
                              finish_pos=pos[k], n_runners=feld, rel_place=(feld - pos[k]) / (feld - 1),
                              won=int(pos[k] == 1), placed=int(pos[k] <= 3), exp_place=0.375,
                              prize_won=5000.0 if pos[k] == 1 else 0.0, odds_final=float(np.exp(-fae[i]) * 5 + 1.5),
                              lengths_behind=1.5 * (pos[k] - 1), arr=np.nan if fehlt else 40 + 5 * perf[k],
                              tr=np.nan if fehlt else 80 + 8 * perf[k], rtr=30 + 5 * fae[i], d_L600_A=np.nan if fehlt else .5 * perf[k],
                              d_B200_A=np.nan, early_pct=rng.random(), tracking=not fehlt, ausgeritten=False, cls_val=30.0,
                              cls_epr_kl=7.0, trainer_key=f"T{trn[i]}", jockey_key=None if fehlt else f"J{k}",
                              owner_key=f"O{i % 20}", breeder_key=None, sire_key=f"S{i % 10}", dam_sire_key=f"D{i % 12}",
                              dam=f"Mutter {i % 30}",
                              prize_eur=[8000, 15000, 30000][c],
                              blinkers=None if fehlt else ("OEILLERES_CLASSIQUE" if (i + d) % 9 == 0 else "SANS_OEILLERES")))
    h = pd.DataFrame(z)
    h["odds_rank"] = h.groupby("race_id")["odds_final"].rank(method="min")
    h["odds_morning"] = (h["odds_final"] * np.exp(np.random.default_rng(5).normal(0, 0.2, len(h)))).clip(lower=1.1)
    return h


def power_modell_pruefen() -> None:
    import io, contextlib, tempfile
    import numpy as np
    import power_modell as pm
    tg = pd.Series(pd.date_range("2022-09-01", periods=1500, freq="D"))
    auf = pm.aufteilung(tg, tg.min())
    rest = tg[auf["drin"]]
    pruefe(not auf["drin"][:365].any() and auf["drin"][365:].all()
           and abs(auf["lern"].sum() / len(rest) - .6) < .01 and abs(auf["valid"].sum() / len(rest) - .2) < .01
           and tg[auf["lern"]].max() < tg[auf["valid"]].min() and tg[auf["valid"]].max() < tg[auf["test"]].min()
           and (auf["lern"] | auf["valid"] | auf["test"]).sum() == len(rest),
           f"Power-Modell: Aufteilung 1 Jahr Aufwärmen, Rest 60/20/20 zeitlich ({auf['grenzen']})")
    pm.AUFWAERM_TAGE = 3                    # synthetische Historie hat nur 40 Tage
    h = _power_synth()
    with contextlib.redirect_stdout(io.StringIO()):
        X = pm.merkmale(h, log=print)
    erst = X.loc[h.drop_duplicates("horse_id").index]
    pruefe(len(X) == len(h) and erst["runs"].eq(0).all() and erst["arr"].isna().all() and erst["f1_pos"].isna().all()
           and erst["trainer_score"].iloc[:3].isna().all(),
           f"Power-Modell: {X.shape[1]} Merkmale je Starter; erster Lauf ohne Vorwerte, erster Tag ohne Verbindungs-Score")
    pruefe(X["arr"].isna().any() and X["arr"].notna().any() and X["f1_typ"].isna().any(),
           "Power-Modell: fehlende Werte bleiben leer (NaN), statt ersetzt zu werden")
    typen = [pm.renntyp3(t) for t in ["Handicap Categorie Divise", "Handicap A Reclamer", "Claimer", "Group 1",
                                      "Listed", "Conditions", "Course A Condition Qualif Hp", "Inconnu", None]]
    typen += [pm.renntyp3(t) for t in ["Group 3", "International", "Groupe II"]]
    pruefe(typen == ["Handicap", "Handicap", "Claimer", "Blacktype", "Blacktype", "Conditions", "Conditions", None, None,
                     "Blacktype", "Conditions", "Blacktype"]
           and set(X["racetype"].dropna()) == {"Handicap", "Blacktype", "Claimer"}
           and set(X["f1_typ"].dropna()) <= {"Handicap", "Blacktype", "Claimer", "Conditions"},
           "Power-Modell: Renntyp in vier Gruppen (Handicap/Conditions/Claimer/Blacktype = Gruppe und Listed), "
           "auch für die letzten Läufe")
    ag = [pm.altersgruppe("DEUX_ANS"), pm.altersgruppe("TROIS_ANS"), pm.altersgruppe("TROIS_QUATRE_CINQ_ANS"),
          pm.altersgruppe("QUATRE_ANS_ET_PLUS"), pm.altersgruppe(None, 3, 6), pm.altersgruppe(None, 2, 2),
          pm.altersgruppe(None, 4, 5), pm.altersgruppe(None)]
    pruefe(ag == ["2yo", "3yo", "3yo+", "4yo+", "3yo+", "2yo", "4yo+", None] and X["age_group"].notna().all(),
           "Power-Modell: Altersgruppe 2yo/3yo/3yo+/4yo+ aus der Altersklasse, sonst aus den Altern im Feld")
    neu = ["trainer_30_score", "trainer_form", "jockey_30_score", "trainer_typ_score", "trainer_kurs_score",
           "jockey_trainer_score", "trainer_debuet_score", "trainer_pause_score", "dam_score", "chg_rating",
           "hcp_sieg_diff", "starts_nach_pause60", "starts_nach_pause180", "letzte_pause_tage", "arr_best365", "arr_best_dist", "arr_best_abst", "erst_wallach"]
    deb = X["runs"] == 0
    wal = X.index[X["erst_wallach"] == 1]
    pruefe(all(c in X for c in neu) and X.loc[~deb, "trainer_debuet_score"].isna().all()
           and X.loc[deb, "trainer_debuet_score"].notna().any() and X["starts_nach_pause60"].dropna().between(0, 10).all()
           and X["dam_score"].notna().any() and len(wal) and (h.loc[wal, "sex"] == "HONGRES").all()
           and (X.loc[X["arr_best365"].notna(), "arr_best_abst"].dropna() <= 0).all(),
           f"Power-Modell: Stallform 30 Tage, Trainer-Lagen (Debüt, Pause, Renntyp, Kurs, Jockey), Mutter, "
           f"Handicap-Marke, Bestform, Läufe seit Pause, erstmals Wallach ({len(wal)} Fälle)")
    hs = h.sort_values(["date", "saddle_no"])
    i_ = X.index[(X["runs"] >= 5) & X["kennt_jockey"].notna()][-1]
    pid = h.loc[i_, "horse_id"]
    vor = hs[(hs["horse_id"] == pid) & (hs["date"] < h.loc[i_, "date"])].iloc[::-1]
    kj = float((vor["jockey_key"] == h.loc[i_, "jockey_key"]).any())
    tz = [h.loc[i_, "trainer_key"]] + list(vor["trainer_key"].iloc[:4])
    pruefe(X.loc[i_, "kennt_jockey"] == kj and X.loc[i_, "trainerwechsel5"] == float(len(set(tz)) > 1)
           and X["kennt_jockey"].isin([0.0, 1.0]).any() and X.loc[X["runs"] == 0, "kennt_jockey"].fillna(0).eq(0).all(),
           f"Power-Modell: kennt_jockey ({X['kennt_jockey'].mean():.0%} ja) und Trainerwechsel in den letzten 5 Starts "
           f"({X['trainerwechsel5'].mean():.0%} ja)")
    h2 = h.copy()
    letzt = h2["date"] == h2["date"].max()
    h2.loc[letzt, "finish_pos"] = h2.loc[letzt, "finish_pos"].to_numpy()[::-1]          # Ergebnis des letzten Tages ändern
    h2.loc[letzt, "rel_place"] = 1 - h2.loc[letzt, "rel_place"]
    h2.loc[letzt, "arr"] = 99.0
    with contextlib.redirect_stdout(io.StringIO()):
        X2 = pm.merkmale(h2, log=print)
    pruefe(X.equals(X2) or X.compare(X2).empty,
           "Power-Modell: ein anderes Ergebnis am letzten Tag ändert kein Merkmal (auch nicht an diesem Tag)")
    # CGD von Hand: Sieg auf Kurs A (Slow, 1600), Platz auf A (Fast, 2000), heute Kurs B (Slow, 1600) ohne Ergebnis
    import racecard as rc_
    hc = pd.DataFrame({"horse_id": ["X"] * 4 + ["Y"], "date": pd.to_datetime(["2025-01-01", "2025-02-01", "2025-02-01",
                                                                             "2025-03-01", "2025-01-01"]),
                       "course_key": ["A", "A", "C", "B", "A"], "going_pmu": ["SLOW", "FAST", "PSF", "SLOW", "SLOW"],
                       "dist_group": ["1401-1600", "1801-2000", "1401-1600", "1401-1600", None],
                       "won": [1, 0, 0, np.nan, 0], "placed": [1, 1, 0, np.nan, 0]})
    cg = rc_.cgd_berechnen(hc)
    st_ = rc_.cgd_stand(hc.iloc[:3])
    pruefe(cg["cgd"].tolist() == ["◦◦◦", "C◦◦", "◦◦D", "◦GD", "◦◦–"] and cg["cgd_sieg"].tolist()[:4] == [0, 1, 1, 2]
           and cg["cgd_platz"].tolist()[3] == 2 and cg["cgd_neu"].tolist()[3] == 1
           and rc_.cgd_kennung(st_, rc_._cgd_schluessel("A", "FAST", "1801-2000"))[0] == "Cgd",
           "CGD: Bilanz vor jedem Lauf (groß gewonnen, klein platziert, · ohne Platz, ◦ erstmals, – unbekannt); "
           "Läufe am selben Tag und ohne Ergebnis zählen nicht")
    # Abstammungs-Passung: Tabelle stimmt mit dem Profil (abst_pferd) überein; Monatsstände ohne Blick in die Zukunft
    pr_ = {r_: rc_.abstammung_profil(h.assign(date=pd.to_datetime(h["date"])), r_ + "_key") for r_ in ("sire", "dam_sire")}
    z_ = h.iloc[-1]
    ap_ = rc_.abst_pferd(pr_["sire"], z_["sire_key"], z_["distance_m"], z_["going_pmu"], z_["age"], 4)
    wv_ = rc_.abst_passung_werte(pr_, h.iloc[[-1]])
    soll_ = {d: (v["perzentil"] - 50) * (v["lage"] - 50) / 25 for d, v in ap_.items()
             if isinstance(v, dict) and v.get("lage") is not None and v.get("sicher")}
    alt_min = pm.ABST_STAND_MIN
    pm.ABST_STAND_MIN = 100
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            Xa, Xa2 = pm.merkmale(h, log=print), pm.merkmale(h2, log=print)
    finally:
        pm.ABST_STAND_MIN = alt_min
    sp_ = [c for c in Xa if "abst_pass" in c]
    i_ = Xa["f1_abst_pass"].dropna().index[-1]
    pruefe(soll_ and all(abs(wv_[f"p_sire_{d}"].iloc[0] - v) < 1e-9 for d, v in soll_.items())
           and Xa["abst_pass"].notna().any() and Xa["abst_pass"].dropna().between(-100, 100).all()
           and Xa.loc[pd.to_datetime(h["date"]) < "2025-04-01", "abst_pass"].isna().all()
           and Xa[sp_].equals(Xa2[sp_])
           and np.isfinite(Xa.at[i_, "abst_pass_wechsel"]) == np.isfinite(Xa.at[i_, "f1_abst_pass"])
           and Xa["f1_cgd_neu"].notna().any() and Xa["erst_kurs"].isin([0.0, 1.0]).any(),
           f"Abstammungs-Passung je Skala wie im Profil; im Modell aus Monatsständen (Läufe vor dem Monatsersten, "
           f"{len(sp_)} Spalten), ein anderes Ergebnis im selben Monat ändert nichts; CGD je letztem Lauf")
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        erg = pm.trainieren(hist=h, X=X, out=Path(tmp) / pm.MODELL_ORDNER, runden=60, log=print)
        mod = pm.laden(Path(tmp))
        heute = h[h["race_id"] == h["race_id"].iloc[-1]].drop(columns=["finish_pos", "rel_place", "won", "placed",
                                                                         "prize_won", "arr", "tr", "odds_final"])
        heute = heute.assign(race_id="20260601R1C1", date=pd.Timestamp("2026-06-01"))
        heute.loc[heute.index[0], "weight_kg"] = np.nan                   # Lücke auch heute
        v = pm.vorhersage(h, heute, mod, log=print)
    ps = [w["p"] for w in v.values()]
    bt = np.array([[1.0, 2.0, 0.5], [3.0, 2.0, 0.5], [5.0, 1.0, 0.5]])
    tg = pm.treiber_relativ(bt, ["formz_pos_dz", "formz_arr_dz", "trainer_score"], np.array(["A", "A", "B"]))
    pruefe(list(tg.columns) == ["Form zeitgewichtet", "Trainer"] and tg.iloc[:2].sum().abs().max() < 1e-12
           and tg.iloc[0].tolist() == [-1.0, 0.0] and tg.iloc[2].tolist() == [0.0, 0.0],
           "Treiber relativ zum Feld: Gruppen summiert, je Rennen um den Ø vermindert (was alle gleich haben, zählt nicht)")
    pruefe(mod is not None and len(v) == len(heute) and abs(np.mean(ps) - 100) < 2 and all(w["treiber"] for w in v.values()),
           f"Power-Modell: gespeichert, geladen, Power je heutigem Starter (Ø {np.mean(ps):.0f}, mit Treibern)")
    sg = [w["sieg"] for w in v.values()]
    pruefe(abs(sum(sg) - 1) < 1e-2 and sg[int(np.argmax(ps))] == max(sg),
           f"Power-Modell: Siegchance je Starter (Summe {sum(sg):.2f}, höchste Power = höchste Siegchance)")
    mt = erg["markt_test"]
    pruefe(mt and mt["a"] > 0 and mt["logloss_power"] > 0 and mt["power_koef"] is not None,
           f"Power-Modell: Test gegen den Markt (a {mt.get('a')}, Log-Loss Power {mt.get('logloss_power')} / Markt "
           f"{mt.get('logloss_markt')}, Power-Koeffizient {mt.get('power_koef')} z {mt.get('power_z')})")
    # Abbruch nach Log-Loss der Siegchance bzw. NDCG@3 (Spitze) statt quadratischem Fehler
    rng_a = np.random.default_rng(4)
    r_a = np.repeat(np.arange(60), 8).astype(str); p_a = rng_a.normal(size=480); w_a = np.zeros(480)
    for k_ in range(60):
        w_a[k_ * 8 + np.argmax(p_a[k_ * 8:k_ * 8 + 8] + rng_a.normal(size=8))] = 1
    y_a = rng_a.uniform(size=480)
    ab_ = {}
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        for a_ in ("sieg", "ndcg"):
            ab_[a_] = pm.trainieren(hist=h, X=X, out=Path(tmp) / pm.MODELL_ORDNER, runden=60, art="regression",
                                    abbruch=a_, speichern=False, log=print)
    pruefe(abs(pm.sieg_logloss_np(p_a, r_a, w_a) - pm.markt_test(p_a, r_a, w_a, np.full(480, 8.0))["logloss_power"]) < 1e-3
           and abs(pm.ndcg3_np(y_a, r_a, y_a) - 1) < 1e-12 and pm.ndcg3_np(-y_a, r_a, y_a) < pm.ndcg3_np(y_a, r_a, y_a)
           and all(b_["abbruch"] == a_ and b_["modell (regression)"]["baeume"] >= 1
                   and b_["modell (regression)"]["logloss"] > 0 for a_, b_ in ab_.items()),
           "Abbruch auf der Validierung wählbar: Log-Loss der Siegchance (wie markt_test, schnell) oder NDCG@3 der Spitze")
    # Tracking-Wert: Teilmodell nur aus Tracking-Merkmalen, je Zeitblock aus den früheren gelernt, als Merkmal trk_wert
    import lightgbm as lgb_
    alt_trk = (pm.TRACKING_BLOCK, pm.TRACKING_MIN_LERN)
    pm.TRACKING_BLOCK, pm.TRACKING_MIN_LERN = "W", 100            # kleine Historie: Wochen statt Quartale
    y_t = pm.ziel(h).reindex(X.index)
    Xr_t = pm.feld_relativ(X, h.loc[X.index, "race_id"], h.loc[X.index, "date"])
    with contextlib.redirect_stdout(io.StringIO()):
        Xt_, trk_ = pm.tracking_wert(Xr_t, y_t, h.loc[X.index, "date"], h.loc[X.index, "race_id"], log=print)
    blk_ = pd.to_datetime(h.loc[X.index, "date"]).dt.to_period("W")
    b_ = sorted(blk_.unique())[3]
    sp_t, kern_t = pm.tracking_spalten(Xr_t.columns)
    hat_t = Xr_t[kern_t].notna().any(axis=1)
    vor_t = hat_t & y_t.notna() & (blk_ < b_)
    Xl_t, st_t, kat_t = pm._tracking_matrix(Xr_t[vor_t], sp_t)
    m_t = lgb_.train(pm.TRACKING_PARAMS, lgb_.Dataset(Xl_t, y_t[vor_t].to_numpy(), categorical_feature=kat_t),
                     num_boost_round=pm.TRACKING_RUNDEN)
    hier_t = hat_t & (blk_ == b_)
    pruefe(np.allclose(m_t.predict(pm._tracking_matrix(Xr_t[hier_t], sp_t, st_t)[0]), Xt_.loc[hier_t, "trk_wert"])
           and Xt_.loc[blk_ == blk_.min(), "trk_wert"].isna().all() and Xt_.loc[~hat_t, "trk_wert"].isna().all()
           and Xt_["trk_wert"].corr(y_t) > 0.2 and Xt_["trk_wert_rk"].dropna().between(0, 1).all()
           and "trainer_score" not in trk_["spalten"] and "dl600" in trk_["spalten"],
           "Tracking-Wert: je Zeitblock ein Teilmodell nur aus früheren Blöcken (nachgerechnet), nur Tracking-Merkmale und "
           "Rennrahmen; erster Block und Starter ohne Tracking leer; Rang/Abstand im Feld")
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        o_t = Path(tmp) / pm.MODELL_ORDNER
        e_t = pm.trainieren(hist=h, X=X, out=o_t, runden=40, art="regression", tracking=True, log=print)
        e_0 = pm.trainieren(hist=h, X=X, out=o_t, runden=40, art="regression", speichern=False, log=print)
        mod_t = pm.laden(Path(tmp))
        heute_t = h[h["race_id"] == h["race_id"].iloc[-1]].drop(columns=["finish_pos", "rel_place", "won", "placed",
                                                                           "prize_won", "arr", "tr", "odds_final"])
        v_t = pm.vorhersage(h, heute_t.assign(race_id="20260601R1C1", date=pd.Timestamp("2026-06-01")), mod_t,
                            log=print)
        datei_t = (o_t / "power_modell_tracking.txt").exists()
    pm.TRACKING_BLOCK, pm.TRACKING_MIN_LERN = alt_trk
    pruefe(e_t["tracking"] and not e_0["tracking"] and datei_t and mod_t["tracking"] is not None
           and "trk_wert" in mod_t["meta"]["spalten"] and len(v_t) == len(heute_t),
           "Tracking-Wert im Hauptmodell: Teilmodell gespeichert (power_modell_tracking.txt), geladen und auf der Karte "
           "angewandt; Vorgabe ohne (tracking=False)")
    # Lern-Ziel „sieg“ (Softmax je Rennen auf den Sieger): Gradient gegen numerische Ableitung; gepaarter Vergleich
    class _D:
        def __init__(self, w): self.w = w
        def get_label(self): return self.w
    r_s = np.array(["a"] * 3 + ["b"] * 2 + ["c"] * 2); w_s = np.array([0, 1, 0, 1, 0, 0, 0], float)
    f_s = np.array([0.2, -0.1, 0.5, 0.3, 0.0, 0.1, -0.2])
    def verlust_(f):
        e = np.exp(f); p_ = e / pd.Series(e).groupby(r_s).transform("sum").to_numpy()
        return -np.log(p_[w_s == 1]).sum()
    num_ = np.array([(verlust_(f_s + 1e-6 * np.eye(7)[k]) - verlust_(f_s - 1e-6 * np.eye(7)[k])) / 2e-6 for k in range(7)])
    g_s, hs_ = pm.sieg_ziel(r_s)(f_s, _D(w_s))
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        e_s = pm.trainieren(hist=h, X=X, out=Path(tmp) / pm.MODELL_ORDNER, runden=60, art="sieg", log=print)
        mod_s = pm.laden(Path(tmp))
        v_s = pm.vorhersage(h, heute.assign(race_id="20260602R1C1", date=pd.Timestamp("2026-06-02")), mod_s, log=print)
        vg_ = pm.vergleich(e_s, erg, ("sieg", "regression"), log=print)
    ll_ = e_s["je_rennen"]["power"]
    pruefe(np.allclose(g_s, num_, atol=1e-5) and np.all(g_s[5:] == 0) and np.all(hs_ > 0)
           and mod_s["meta"]["art"] == "sieg" and len(v_s) == len(heute) and "je_rennen" not in mod_s["meta"]["bericht"]
           and abs(np.mean(list(ll_.values())) - e_s["markt_test"]["logloss_power"]) < 0.05
           and len(vg_) >= 1 and vg_["rennen"].iloc[0] > 0 and np.isfinite(vg_["differenz"].iloc[0]),
           "Lern-Ziel „sieg“: Gradient = numerische Ableitung von −log Siegchance (Rennen ohne Sieger zählen nicht), "
           "Training/Speichern/Karte; Log-Loss je Testrennen und gepaarter Vergleich zweier Läufe (pm.vergleich)")
    # Dreier-Mischung Morgenquote × Power × Power-sieg: übernommen nur nach Likelihood-Quotienten-Test
    alt_lr = pm.MISCH3_LR
    m3_ = {}
    for lr_ in (-1e9, 1e9):                                   # erzwungen übernommen / erzwungen verworfen
        pm.MISCH3_LR = lr_
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            e3_ = pm.trainieren(hist=h, X=X, out=Path(tmp) / pm.MODELL_ORDNER, runden=40, art="regression", log=print)
            mod3_ = pm.laden(Path(tmp))
            v3_ = pm.vorhersage(h, heute.assign(race_id="20260603R1C1", date=pd.Timestamp("2026-06-03")), mod3_,
                                log=print)
            m3_[lr_ > 0] = (e3_, mod3_, v3_, (Path(tmp) / pm.MODELL_ORDNER / pm.ZWEIT_DATEI).exists())
    pm.MISCH3_LR = alt_lr
    (e_j, mod_j, v_j, d_j), (e_n, mod_n, v_n, d_n) = m3_[False], m3_[True]
    b3_ = e_j["mischung3 (Morgenquote × Power × Power-sieg)"]
    pruefe(b3_["uebernommen"] and set(mod_j["meta"]["mischung"]) == {"morgen", "power", "sieg"} and d_j
           and mod_j.get("zweit") is not None and abs(sum(x["sieg"] for x in v_j.values()) - 1) < 0.01
           and not e_n["mischung3 (Morgenquote × Power × Power-sieg)"]["uebernommen"] and not d_n
           and "sieg" not in mod_n["meta"]["mischung"] and "gepaart_test" in b3_ and "mischung3" in e_j["je_rennen"]
           and pm.mischung_chance([.5, .5], [.4, .6], ["a", "a"], 1.0, 0.0, [.9, .1], 0.0).tolist() == [.5, .5],
           f"Dreier-Mischung Morgenquote^{b3_['morgen']} × Power^{b3_['power']} × Power-sieg^{b3_['sieg']}: nur nach "
           f"Likelihood-Quotienten-Test (χ² {b3_['lr_chi2']}) übernommen, dann zweites Modell gespeichert und auf der "
           "Karte gemischt; sonst Zweier-Mischung wie bisher; gepaarter Test im Bericht")
    # Value-Modell: Trainer-Effekt steckt nicht in der Quote -> oberes Fünftel A/E Platz > 1, unteres < 1
    import racecard as rc_
    hw = _power_synth(tage=80)
    hw["exp_place"] = rc_.platz_erwartung(hw)
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        Xw = pm.merkmale(hw, log=print)
        ew = pm.trainieren_wert(hist=hw, X=Xw, out=Path(tmp) / pm.MODELL_ORDNER, runden=300,
                                params={"min_data_in_leaf": 20}, log=print)
        pm.trainieren(hist=hw, X=Xw, out=Path(tmp) / pm.MODELL_ORDNER, runden=30, log=print)
        mw = pm.laden(Path(tmp))
        hz = hw[hw["race_id"] == hw["race_id"].iloc[-1]].drop(columns=["finish_pos", "rel_place", "won", "placed",
                                                                        "prize_won", "arr", "tr", "odds_final"])
        vw = pm.vorhersage(hw, hz.assign(race_id="20260601R1C1", date=pd.Timestamp("2026-06-01")), mw, log=print)
    f5 = {z["gruppe"]: z["ae_platz"] for z in ew["fuenftel"]}
    pruefe(f5[5] > 1.1 and f5[1] < 0.9 and ew["verlust_platz_mit_value"] < ew["verlust_platz_markt"]
           and mw.get("wert") is not None and all(w["wert"] and w["wert"] > 0 for w in vw.values())
           and all(isinstance(w["gold"], bool) for w in vw.values()) and 0 < ew["kalib_k"] < 2
           and [z["auswahl"] for z in ew["rendite"]] == ["alle", "oberste 20 %", "oberste 10 %", "oberste 5 %", "oberste 2 %"]
           and set(ew["rendite_top10"]) == {"renntyp", "quote", "monat"},
           f"Value-Modell findet, was die Quote nicht enthält (A/E Platz Fünftel 1 {f5[1]} … 5 {f5[5]}, "
           f"Sieg-z {ew['sieg_value_z']}); Karte bekommt den Value-Faktor je Starter")
    mi = pm.modell_info(mw)
    pruefe(mi and "Stärke-Einschätzung" in mi["power"]["einordnung"] and mi["power"]["rote_starter"]
           and mi["power"]["rote_starter"]["anteil_starter"] > 0 and "Warnsignal" in mi["value"]["einordnung"]
           and mi["value"]["pruefung"]["sieg_z"] is not None,
           "Modell-Info für die Claude-JSON: Verlässlichkeit Power (inkl. Anteil roter Starter an den Siegern) und Value")
    # externe Läufe: nur Vorgeschichte (keine Zielzeile); Zwischenspeicher bleibt über (race_id, horse_id) zugeordnet
    he = h.copy()
    he["extern"] = False
    zus = he.iloc[[5]].copy()
    zus["race_id"], zus["extern"], zus["date"] = "20250302XTEST", True, pd.Timestamp("2025-03-02")
    zus["hippodrome"], zus["course_key"] = "AURILLAC", "AURILLAC"              # PMH-Bahn (nicht im PMU-Programm)
    he2 = pd.concat([zus, he], ignore_index=True)                       # Zeilennummern verschieben sich
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        _, X1, _ = pm._merkmale_holen(None, he, Path(tmp), None, False, print)
        _, X2, _ = pm._merkmale_holen(None, he2, Path(tmp), None, False, print)
    with contextlib.redirect_stdout(io.StringIO()):
        Xe = pm.merkmale(he2, log=print)
    pid_ = zus["horse_id"].iloc[0]
    nach_ = he2[(he2["horse_id"] == pid_) & (pd.to_datetime(he2["date"]) > pd.Timestamp("2025-03-02"))
                & he2["extern"].eq(False)].sort_values("date").index[0]
    i5 = he.index[10]
    pruefe(len(X1) == len(he) and len(X2) == len(he) and "20250302XTEST" not in set(he2.loc[X2.index, "race_id"])
           and (he2.loc[X2.index, "race_id"].to_numpy() == he.loc[X1.index, "race_id"].to_numpy()).all()
           and X2.loc[i5 + 1].equals(X1.loc[i5]) and Xe.at[nach_, "f1_extern"] == 1.0
           and Xe["formz_pos_pmu"].notna().any() and (Xe["formz_pos_pmu"] != Xe["formz_pos"]).any()
           and Xe.at[nach_, "form5_extern"] > 0 and Xe["f1_extern"].fillna(0).sum() >= 1,
           "Externe Läufe: keine Zielzeilen; Merkmal-Zwischenspeicher nach eingefügten Zeilen über Rennen + Pferd "
           "richtig zugeordnet")
    zus2 = zus.copy()
    zus2["hippodrome"] = str(he.loc[he["horse_id"] == pid_, "hippodrome"].iloc[0])        # Bahn aus dem PMU-Programm
    zus2["course_key"] = rc_.norm_name(zus2["hippodrome"])
    he3 = pd.concat([zus2, he], ignore_index=True)
    with contextlib.redirect_stdout(io.StringIO()):
        Xp = pm.merkmale(he3, log=print)
    nach3 = he3[(he3["horse_id"] == pid_) & (pd.to_datetime(he3["date"]) > pd.Timestamp("2025-03-02"))
                & he3["extern"].eq(False)].sort_values("date").index[0]
    pruefe(Xp.at[nach3, "f1_extern"] == 0.0 and Xp.at[nach3, "form5_extern"] == 0.0
           and Xp.at[nach3, "formz_pos_pmu"] == Xp.at[nach3, "formz_pos"]
           and not rc_.extern_kennzeichen(he3).loc[0] and rc_.extern_kennzeichen(he2).loc[0],
           "Externe Läufe auf PMU-Bahnen (z. B. vor Beginn der Historie) zählen in den Merkmalen wie "
           "PMU-Läufe; nur PMH/Ausland/Übersee tragen das Kennzeichen extern")
    # Rennverlauf zeitlich sauber: spätere Rennen ändern die Einordnung früherer Läufe nicht
    rg_ = np.random.default_rng(1); zz_ = []
    st_ = rg_.normal(0, 1, 300)
    for t_ in range(260):
        d_ = pd.Timestamp("2024-01-01") + pd.Timedelta(days=t_)
        for r_ in range(4):
            ids_ = rg_.choice(300, 10, replace=False); fr_ = rg_.uniform(0, 1, 10); b_ = rg_.normal(0, 1)
            sc_ = st_[ids_] + b_ * (0.5 - fr_) + rg_.normal(0, 1, 10)
            ps_ = (-sc_).argsort().argsort() + 1
            for k_, i_ in enumerate(ids_):
                zz_.append(dict(race_id=f"{d_:%Y%m%d}R1C{r_}", date=d_, horse_id=f"P{i_}|V", course_key="ABC"[r_ % 3],
                                distance_m=[1600, 2000, 2400][(t_ + r_) % 3], early_pct=fr_[k_], finish_pos=ps_[k_],
                                rel_place=(10 - ps_[k_]) / 9, n_runners=10))
    hv_ = pd.DataFrame(zz_)
    v1_ = pm.verlauf_zeitlich(hv_)
    hv2_ = hv_.copy()
    spaet_ = hv2_["date"] >= pd.Timestamp("2024-07-01")
    hv2_.loc[spaet_, "early_pct"] = 1 - hv2_.loc[spaet_, "early_pct"]          # Zukunft umdrehen
    v2_ = pm.verlauf_zeitlich(hv2_)
    frueh_ = (~spaet_).to_numpy()
    vl_ = np.array([{"gegen": 1.0, "mit": -1.0, "neutral": 0.0}.get(x, np.nan) for x in v1_])
    tg_, kr_ = pm._verlauf_korrektur((hv_["date"] - pd.Timestamp("2000-01-01")).dt.days.to_numpy(), vl_,
                                     hv_["rel_place"].to_numpy(float), np.zeros(len(hv_), bool))
    pruefe(list(v1_[frueh_]) == list(v2_[frueh_]) and pd.Series(v1_).notna().mean() > 0.5
           and kr_[-1][0] > 0.05 and kr_[-1][1] < -0.05,
           f"Rennverlauf zeitlich sauber (Norm und Grenzen nur aus früheren Tagen): Zukunft ändert frühere Läufe nicht; "
           f"Form-Korrektur gegen den Verlauf {kr_[-1][0]:+.2f}, mit dem Verlauf {kr_[-1][1]:+.2f} Pos+")
    alt_ = (pm.VERLAUF_MIN_VORHER, pm.VB_MIN)
    pm.VERLAUF_MIN_VORHER, pm.VB_MIN = 20, 20                                   # kleine Testhistorie
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            Xv = pm.merkmale(h, log=print)
    finally:
        pm.VERLAUF_MIN_VORHER, pm.VB_MIN = alt_
    bd_ = Xv["box_dev"]
    mitb_ = Xv["box_runs"].notna()
    erw_ = (Xv.loc[mitb_, "box_mean"] * Xv.loc[mitb_, "box_runs"] + pm.BOX_K * 0.5) / (Xv.loc[mitb_, "box_runs"] + pm.BOX_K) - 0.5
    pruefe(all(Xv[c].notna().any() for c in ("verlauf5_gegen", "verlauf5_mit", "form5_pos_gegen", "form5_pos_mit"))
           and (Xv["formz_pos_vb"] - Xv["formz_pos"]).abs().max() > 0
           and np.allclose(bd_[mitb_], erw_) and bd_.abs().max() < 0.5 and (bd_[~mitb_].dropna() == 0).all(),
           "Neue Merkmale: Rennverlauf der letzten fünf (Anteil gegen/mit, Ø Pos+ je Klasse), Verlauf-bereinigte Form "
           "formz_pos_vb, geschrumpfte Box-Abweichung box_dev")
    # Trainer-/Besitzerwechsel: Läufe und Tage seitdem, Sprung neu − alt, Form beim neuen Trainer, Verkauf im Stall
    hw_ = h.copy()
    vc_ = hw_["horse_id"].value_counts()
    l1_ = hw_[hw_["horse_id"] == vc_.index[0]].sort_values("date").index
    l2_ = hw_[hw_["horse_id"] == vc_.index[1]].sort_values("date").index
    neu_tr_ = hw_.loc[hw_["trainer_key"] != hw_.loc[l1_[0], "trainer_key"], "trainer_key"].iloc[0]
    hw_.loc[l1_[4:], "trainer_key"] = neu_tr_
    hw_.loc[l1_[4:], "owner_key"] = "BESITZER_NEU"
    hw_.loc[l2_[5:], "owner_key"] = "BESITZER_ZWEI"
    with contextlib.redirect_stdout(io.StringIO()):
        Xw_ = pm.merkmale(hw_, log=print)
    pruefe(Xw_.loc[l1_[:4], "laeufe_seit_trainerwechsel"].isna().all()
           and Xw_.at[l1_[4], "laeufe_seit_trainerwechsel"] == 0 and Xw_.at[l1_[4], "chg_trainer"] == 1
           and Xw_.at[l1_[4], "form_neuer_trainer_n"] == 0 and np.isfinite(Xw_.at[l1_[4], "trainer_sprung"])
           and Xw_.at[l1_[5], "laeufe_seit_trainerwechsel"] == 1 and Xw_.at[l1_[5], "form_neuer_trainer_n"] == 1
           and Xw_.at[l1_[6], "tage_seit_trainerwechsel"] > Xw_.at[l1_[5], "tage_seit_trainerwechsel"] > 0
           and Xw_.at[l1_[4], "besitzer_ohne_trainer"] == 0
           and Xw_.at[l2_[5], "chg_owner"] == 1 and Xw_.at[l2_[5], "besitzer_ohne_trainer"] == 1
           and Xw_.at[l2_[6], "laeufe_seit_besitzerwechsel"] == 1 and np.isnan(Xw_.at[l2_[6], "laeufe_seit_trainerwechsel"]),
           "Trainer-/Besitzerwechsel: Läufe/Tage seit dem Wechsel, Trainer-Sprung (Score neu − alt), Form beim neuen "
           "Trainer, Besitzerwechsel ohne Trainerwechsel")
    # Starts nach Pause (≥ 60 / ≥ 180 Tage), Zählung beginnt mit jeder neuen Pause neu; 0 = keine Pause
    hp_ = h.copy()
    d0_ = pd.to_datetime(hp_["date"]); tg_ = sorted(d0_.unique())
    hp_["date"] = d0_ + pd.to_timedelta(np.where(d0_ >= tg_[len(tg_) // 3], 70, 0)
                                        + np.where(d0_ >= tg_[2 * len(tg_) // 3], 200, 0), unit="D")
    with contextlib.redirect_stdout(io.StringIO()):
        Xp_ = pm.merkmale(hp_, log=print)
    dp_ = pd.to_datetime(hp_["date"])
    ok_p = True
    for i in Xp_.index:
        fr_ = sorted(dp_[(hp_["horse_id"] == hp_.at[i, "horse_id"]) & (dp_ < dp_[i])], reverse=True)
        kette_ = [dp_[i]] + fr_
        for spalte_, grenze_ in (("starts_nach_pause60", 60), ("starts_nach_pause180", 180)):
            erw_, gap_ = (np.nan, np.nan) if not fr_ else (0.0, np.nan)
            for k_ in range(len(kette_) - 1):
                if (kette_[k_] - kette_[k_ + 1]).days >= grenze_:
                    erw_, gap_ = float(min(k_ + 1, 10)), float((kette_[k_] - kette_[k_ + 1]).days)
                    break
            ist_ = Xp_.at[i, spalte_]
            ok_p &= (np.isnan(erw_) and np.isnan(ist_)) or erw_ == ist_
            if grenze_ == 60:
                b_ = Xp_.at[i, "letzte_pause_tage"]
                ok_p &= (np.isnan(gap_) and np.isnan(b_)) or gap_ == b_
    pruefe(ok_p and Xp_["starts_nach_pause60"].gt(1).any() and Xp_["starts_nach_pause180"].eq(1).any()
           and Xp_["starts_nach_pause60"].eq(0).any() and Xp_.loc[Xp_["runs"] == 0, "starts_nach_pause60"].isna().all(),
           "Starts nach Pause ≥ 60 / ≥ 180 Tage (1 = erster Start danach, neue Pause beginnt neu, 0 = keine Pause, "
           "Debüt leer) und Länge der Pause, mit der die Serie begann")
    # Merkmale Version 19: Gewicht, Spielraum, Geschlecht, Meeting, Stall, Reise, Box × Stil, Penetrometer, Tracking
    hn_ = h.copy()
    rng_ = np.random.default_rng(11)
    nr_ = hn_["race_id"].str[-1].astype(int)                     # Rennen 1, 2 in Chantilly, 3 in Marseille
    hn_["course_key"] = np.where(nr_ <= 2, "CHANTILLY", "MARSEILLE BORELY")
    hn_["hippodrome"] = hn_["course_key"]
    pen_r = {r: round(float(rng_.uniform(2.5, 5.0)), 1) for r in hn_["race_id"].unique()}
    hn_["going_value"] = hn_["race_id"].map(pen_r)
    hn_["weight_assigned_kg"] = hn_["weight_kg"] + np.where(hn_["saddle_no"] == 1, 2.0, 0.0)
    hn_["sex"] = np.where(hn_["horse"].str[1:].astype(int) % 5 == 1, "FEMELLES", hn_["sex"])
    for c_ in ("stride_rel", "stride_change_pct", "vmax_rel"):
        hn_[c_] = np.where(hn_["tracking"], rng_.normal(0, 1, len(hn_)), np.nan)
    with contextlib.redirect_stdout(io.StringIO()):
        Xn_ = pm.merkmale(hn_, log=print)
    dn_ = pd.to_datetime(hn_["date"]); rp_ = pm.ziel(hn_)
    ok_n = True
    zeilen_ = Xn_.index[Xn_["runs"] >= 3][::37]
    for i in zeilen_:
        fr_ = hn_[(hn_["horse_id"] == hn_.at[i, "horse_id"]) & (dn_ < dn_[i])].assign(_d=dn_).sort_values("_d", ascending=False, kind="stable")
        if fr_["_d"].duplicated().any():                   # zwei Läufe an einem Tag (nur synthetisch): Reihenfolge offen
            continue
        a_ = fr_["arr"].dropna()
        erw_sp = hn_.at[i, "valeur"] - a_.max() if len(a_) else np.nan
        erw_nb = fr_["arr"].iloc[0] - fr_["arr"].iloc[1:].max() if pd.notna(fr_["arr"].iloc[0]) and fr_["arr"].iloc[1:].notna().any() else np.nan
        best_ = fr_.assign(_rp=rp_[fr_.index]).sort_values("_rp", ascending=False, kind="stable").head(3)
        erw_gp = hn_.at[i, "going_value"] - best_["going_value"].mean()
        for erw_, spalte_ in ((erw_sp, "hcp_spielraum"), (erw_nb, "arr_neue_best"), (erw_gp, "going_pref")):
            ist_ = Xn_.at[i, spalte_]
            if not ((np.isnan(erw_) and np.isnan(ist_)) or abs(erw_ - ist_) < 1e-9):
                ok_n = False; print("abw", i, spalte_, erw_, ist_)
        j_ = fr_.index[0]
        for spalte_, quelle_ in (("f1_stride_rel", "stride_rel"), ("f1_stride_change", "stride_change_pct"), ("f1_vmax_rel", "vmax_rel")):
            a1, b1 = Xn_.at[i, spalte_], hn_.at[j_, quelle_]
            ok_n &= (np.isnan(a1) and np.isnan(b1)) or a1 == b1
    pruefe(ok_n and Xn_["hcp_spielraum"].notna().any() and Xn_["arr_neue_best"].gt(0).any() and Xn_["arr_neue_best"].lt(0).any(),
           "Handicap-Spielraum (Rating − bester ARR 365), neue Bestleistung im letzten Lauf (ARR − bester davor), "
           "Boden-Vorliebe (Penetrometer heute − Ø der besten drei Läufe), Schritt/Vmax des letzten Laufs relativ zum Feld")
    # Geschlecht im Feld, Meeting, Stall, Erlaubnis
    ok_g = True
    for i in Xn_.index[::53]:
        rr_ = hn_[hn_["race_id"] == hn_.at[i, "race_id"]]
        m_ = rr_["sex"].isin(["MALES", "HONGRES"])
        andere_ = rr_.index != i
        erw_a = m_[andere_].mean()
        erw_s = float(m_.any()) if hn_.at[i, "sex"] == "FEMELLES" else 0.0
        tag_kurs_ = hn_[(hn_["date"] == hn_.at[i, "date"]) & (hn_["course_key"] == hn_.at[i, "course_key"])]
        erw_j = (tag_kurs_["jockey_key"] == hn_.at[i, "jockey_key"]).sum() if pd.notna(hn_.at[i, "jockey_key"]) else np.nan
        erw_t = (tag_kurs_["trainer_key"] == hn_.at[i, "trainer_key"]).sum()
        erw_st = (rr_["trainer_key"] == hn_.at[i, "trainer_key"]).sum() - 1
        for erw_, spalte_ in ((erw_a, "feld_anteil_maennlich"), (erw_s, "stute_gegen_hengste"), (erw_j, "jockey_ritte_meeting"),
                              (erw_t, "trainer_starter_meeting"), (erw_st, "stall_im_rennen"),
                              (hn_.at[i, "weight_assigned_kg"] - hn_.at[i, "weight_kg"], "gew_erlaubnis")):
            ist_ = Xn_.at[i, spalte_]
            if not ((np.isnan(erw_) and np.isnan(ist_)) or abs(erw_ - ist_) < 1e-9):
                ok_g = False; print("abw", i, spalte_, erw_, ist_)
        if erw_st > 0 and np.isfinite(Xn_.at[i, "jockey_score"]):
            js_ = Xn_.loc[rr_.index[rr_["trainer_key"] == hn_.at[i, "trainer_key"]], "jockey_score"]
            ok_g &= Xn_.at[i, "stall_erster"] == float(Xn_.at[i, "jockey_score"] >= js_.max() - 1e-9)
    pruefe(ok_g and Xn_["stute_gegen_hengste"].eq(1).any() and Xn_["jockey_ritte_meeting"].eq(2).any()
           and Xn_["stall_im_rennen"].gt(0).any() and Xn_["stall_erster"].isin([0, 1]).any(),
           "Geschlecht im Feld (Anteil männlicher Gegner, Stute gegen Hengste), Ritte des Jockeys / Starter des Trainers am "
           "Meeting, Stallgefährten (Nr. 1 = bester Jockey des Stalls), Gewichtserlaubnis")
    # Reise des Trainers: Heimatbahn = meiste Starter der 365 Tage davor
    ok_r = True
    for i in Xn_.index[::41]:
        fr_ = hn_[(hn_["trainer_key"] == hn_.at[i, "trainer_key"]) & (dn_ < dn_[i]) & (dn_ >= dn_[i] - pd.Timedelta(days=365))]
        if fr_.empty:
            ok_r &= np.isnan(Xn_.at[i, "trainer_reise_km"]); continue
        heim_ = fr_["course_key"].value_counts()
        if len(heim_) > 1 and heim_.iloc[0] == heim_.iloc[1]:
            continue
        erw_ = pm.bahn_orte.km(pm.bahn_orte.koordinaten(heim_.index[0]), pm.bahn_orte.koordinaten(hn_.at[i, "course_key"]))
        ok_r &= abs(erw_ - Xn_.at[i, "trainer_reise_km"]) < 1e-6
    pruefe(ok_r and Xn_["trainer_reise_km"].gt(600).any() and Xn_["trainer_reise_km"].eq(0).any(),
           "Reise des Trainers: Heimatbahn = Bahn mit den meisten Startern der 365 Tage davor, Luftlinie zur heutigen Bahn")
    # Box × Laufstil und Penetrometer der Spitzenläufe des Vaters
    def stil_(e):
        return -1 if np.isnan(e) else 0 if e <= pm.rc.VERLAUF_VORNE else 2 if e >= pm.rc.VERLAUF_HINTEN else 1
    dr_ = np.minimum(np.floor((hn_["draw"] - 1) / hn_["n_runners"] * 3), 2)
    ok_b = True
    for i in Xn_.index[::29]:
        s_h = stil_(Xn_.at[i, "early"])
        if s_h < 0:
            ok_b &= np.isnan(Xn_.at[i, "box_stil_dev"]); continue
        vor_ = hn_[(dn_ < dn_[i]) & (hn_["konfig"] == hn_.at[i, "konfig"]) & (dr_ == dr_[i])
                   & (hn_["early_pct"].map(stil_) == s_h)]
        erw_ = (rp_[vor_.index].sum() + 15) / (len(vor_) + 30) - 0.5
        ok_b &= abs(erw_ - Xn_.at[i, "box_stil_dev"]) < 1e-9 and Xn_.at[i, "box_stil_runs"] == len(vor_)
    gp_min_ = pm.GOING_PREF_ABST_MIN
    ok_v = True
    for i in Xn_.index[::31]:
        vor_ = hn_[(dn_ < dn_[i]) & (rp_ >= pm.FORM_TOP)]
        eig_ = vor_[vor_["sire_key"] == hn_.at[i, "sire_key"]]
        if len(eig_) < gp_min_:
            ok_v &= np.isnan(Xn_.at[i, "sire_going_pref"]); continue
        erw_ = hn_.at[i, "going_value"] - (eig_["going_value"].sum() + pm.ABST_K * vor_["going_value"].mean()) / (len(eig_) + pm.ABST_K)
        ok_v &= abs(erw_ - Xn_.at[i, "sire_going_pref"]) < 1e-9
    pruefe(ok_b and ok_v and Xn_["box_stil_dev"].notna().any() and Xn_["sire_going_pref"].notna().any(),
           "Box × Laufstil (Boxdrittel, Stil: Stand mit dem tatsächlichen frühen Platz, heute der erwartete Stil; "
           "geschrumpft) und Penetrometer der Spitzenläufe des Vaters (zum Schnitt aller Spitzenläufe geschrumpft)")
    sc_ = pm._score(1.0, 1e-17, 0.5, 5.0, 1, 0.5, 5.0)
    pruefe(abs(sc_ - 100) < 1e-9 and abs(pm._score(1.0, 0.5, 0.5, 5.0, 1, 0.5, 5.0) - 400 / 3) < 1e-9,
           "Verbindungs-Score: Rundungsrest der Erwartung (1e-17) zählt nicht als A/E (kein Wert wie 1e16)")
    # Morgenquote als Marktmerkmal (nur Value-Modell): von Hand, im Modell gespeichert, auf der Karte aus den heutigen Zeilen
    mm = pm.morgen_merkmale(pd.DataFrame({"race_id": ["A", "A", "A", "B"], "odds_morning": [2.0, 4.0, None, 3.0]}))
    pruefe(abs(mm["m_pm"].iloc[0] - 2 / 3) < 1e-9 and mm["m_rk"].tolist()[:2] == [0.0, 1.0]
           and abs(mm["m_marge"].iloc[0] - 0.75) < 1e-9 and mm.iloc[2].isna().all() and np.isnan(mm["m_rk"].iloc[3])
           and abs(mm["m_log"].iloc[3] - np.log(3)) < 1e-9
           and mw["wert"]["meta"].get("morgenquote") is True and "m_pm" in mw["wert"]["meta"]["spalten"]
           and not any(c.startswith("m_") for c in mw["meta"]["spalten"]),
           "Value-Modell: Morgenquote als Merkmal (Marktchance je Rennen, log-Quote, Quotenrang, Marge); Power-Modell ohne")
    # Kombi-Ziel (Sieg + Platz, Poisson): findet denselben Trainer-Effekt, Faktor ≈ A/E Kombi
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        ek = pm.trainieren_wert(hist=hw, X=Xw, out=Path(tmp) / pm.MODELL_ORDNER, runden=300, ziel_art="kombi",
                                params={"min_data_in_leaf": 20}, log=print)
    fk = {z["gruppe"]: z["ae_kombi"] for z in ek["fuenftel"]}
    pruefe(ek["ziel"] == "kombi" and fk[5] > 1.1 and fk[1] < 0.9
           and ek["verlust_kombi_mit_value"] < ek["verlust_kombi_markt"] and 0 < ek["kalib_k"] < 2,
           f"Value-Modell mit Kombi-Ziel (Sieg + Platz): A/E Kombi Fünftel 1 {fk[1]} … 5 {fk[5]}, Sieg-z {ek['sieg_value_z']}")
    # Segment-Modelle je Renntyp (Schwellen für die kleine Historie gesenkt, damit sie behalten werden)
    alt = (pm.SEG_MIN_STARTER, pm.SEG_MIN_GEWINN, pm.SEG_MIN_VERLUST, pm.SEG_PARAMS)
    pm.SEG_MIN_STARTER, pm.SEG_MIN_GEWINN, pm.SEG_MIN_VERLUST = 50, -1.0, -1.0
    pm.SEG_PARAMS = {**pm.SEG_PARAMS, "min_data_in_leaf": 20}
    try:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            es = pm.trainieren(hist=hw, X=Xw, out=Path(tmp) / pm.MODELL_ORDNER, runden=30, segmente="racetype",
                               log=print)
            ews = pm.trainieren_wert(hist=hw, X=Xw, out=Path(tmp) / pm.MODELL_ORDNER, runden=100, ziel_art="kombi",
                                     segmente="racetype", params={"min_data_in_leaf": 20}, log=print)
            ms_ = pm.laden(Path(tmp))
            dateien = sorted(q.name for q in (Path(tmp) / pm.MODELL_ORDNER).glob("*_seg_*.txt"))
            vs_ = pm.vorhersage(hw, hz.assign(race_id="20260601R1C1", date=pd.Timestamp("2026-06-01")), ms_, log=print)
    finally:
        pm.SEG_MIN_STARTER, pm.SEG_MIN_GEWINN, pm.SEG_MIN_VERLUST, pm.SEG_PARAMS = alt
    js = es["segmente"]["je_segment"]
    pruefe(set(js) == {"Handicap", "Blacktype", "Claimer"} and ms_["segmente"] and ms_["wert"]["segmente"]
           and len(dateien) == len(ms_["segmente"]) + len(ms_["wert"]["segmente"])
           and "modell (mit Segmenten)" in es and {z["segment"] for z in es["je_rennart"]["racetype"]} == set(js)
           and {z["segment"] for z in ews["je_rennart"]["age_group"]} and len(vs_) == len(hz)
           and abs(sum(w["sieg"] for w in vs_.values()) - 1) < 1e-2,
           f"Segment-Modelle je Renntyp: gelernt als Korrektur, gespeichert ({', '.join(dateien)}), geladen und in der "
           f"Vorhersage angewandt; Prüfung je Rennart im Bericht")
    try:
        pm.trainieren(hist=hw, X=Xw, out=None, segmente="kurs", log=lambda *a: None)
        falsch = False
    except ValueError:
        falsch = True
    pruefe(falsch, "Segment-Modelle: unbekannte Segment-Spalte wird abgelehnt")
    # Rendite-Tabelle von Hand: 4 Wetten, 1 Sieg zu 6,0 -> Rendite 6/4 − 1 = 0,5; Eichung erkennt zu starken Faktor
    rt = pm.rendite_tabelle(np.array([4.0, 3.0, 2.0, 1.0]), np.array([1, 0, 0, 0]), np.array([6.0, 5.0, 4.0, 3.0]),
                            anteile=[0.5])
    rg2 = np.random.default_rng(2)
    f_ = rg2.normal(0, 1, 20000); b_ = rg2.normal(-1, 0.5, 20000)
    y_ = (rg2.random(20000) < 1 / (1 + np.exp(-(b_ + 0.5 * f_)))).astype(float)
    k_ = pm._kalibrieren(f_, b_, y_)
    pruefe(rt.loc[0, "rendite"] == 0.5 and rt.loc[1, "wetten"] == 2 and rt.loc[1, "rendite"] == 2.0 and abs(k_ - 0.5) < 0.05,
           f"Value-Modell: Rendite-Tabelle zur Endquote stimmt, Eichung schrumpft zu starken Faktor (k {k_:.2f} statt 0,5)")
    # Vorwärts-Test: Protokoll aus den Kartendaten, zweimal geschrieben (Karte neu erstellt) ohne Doppelte;
    # Auswertung verbindet mit den Ergebnissen: gold-Pferd gewinnt zu 5,0 -> Rendite +4,0, alle 3: 5/3 − 1
    hp = pd.DataFrame({"race_id": ["20260601R1C1"] * 3, "saddle_no": [1, 2, 3], "won": [1, 0, 0], "placed": [1, 1, 0],
                       "finish_pos": [1, 2, 3], "odds_final": [5.0, 2.0, 9.0], "odds_morning": [6.0, 2.0, 8.0]})
    dk = {"date": "2026-06-01", "races": {"20260601R1C1": {"race_id": "20260601R1C1", "type": "Handicap", "runners": [
        {"no": 1, "horse": "A", "nr": False, "power": {"wert": 1.3, "gold": True, "sieg": 0.2}, "prono": {"sel": {"cote_dec": 4.0}}},
        {"no": 2, "horse": "B", "nr": False, "power": {"wert": 0.7, "gold": False, "warn": True, "sieg": 0.5}, "prono": None},
        {"no": 3, "horse": "C", "nr": False, "power": {"wert": 1.0, "gold": False, "sieg": 0.3}, "prono": None},
        {"no": 4, "horse": "D", "nr": True, "power": None}]}}}
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        pm.protokollieren(dk, Path(tmp))
        pf = pm.protokollieren(dk, Path(tmp))
        prot = pd.read_csv(pf)
        va = pm.value_auswertung(Path(tmp), hist=hp, log=print).set_index("auswahl")
    pruefe(len(prot) == 3 and va.loc["goldener Rahmen", "rendite_endquote"] == 4.0
           and va.loc["goldener Rahmen", "rendite_morgenquote"] == 5.0
           and abs(va.loc["alle", "rendite_endquote"] - (5 / 3 - 1)) < 1e-3
           and va.loc["gold · Prognose 1–10", "wetten"] == 1 and va.loc["gold · Endquote 1–10", "wetten"] == 1
           and va.loc["Warnsignal (unterstes Fünftel)", "wetten"] == 1
           and va.loc["Warnsignal (unterstes Fünftel)", "rendite_endquote"] == -1.0,
           "Vorwärts-Test: Karte protokolliert Value-Faktoren (ohne Doppelte), Auswertung rechnet Rendite zu End- und Morgenquote")
    # bekannter Fall: reines Markt-Signal -> Power-Koeffizient ≈ 0; Power mit Zusatzwissen -> deutlich positiv
    rg = np.random.default_rng(1)
    rr = np.repeat(np.arange(400), 8)
    st_ = rg.normal(0, 1, len(rr)); extra = rg.normal(0, 1, len(rr))
    wahr = _sm = pm._softmax_im_rennen(st_ + extra, rr)
    gew_ = np.zeros(len(rr))
    for r in range(400):
        k = np.flatnonzero(rr == r); gew_[rg.choice(k, p=wahr[k] / wahr[k].sum())] = 1
    quote = 1 / pm._softmax_im_rennen(st_, rr)
    m_mit = pm.markt_test(st_ + extra, rr, gew_, quote)
    pruefe(m_mit["power_koef"] > 0 and m_mit["power_z"] > 3 and m_mit["logloss_power"] < m_mit["logloss_markt"],
           f"Markt-Test erkennt Zusatzwissen (Power-Koeffizient {m_mit['power_koef']}, z {m_mit['power_z']})")
    rk = {a_: erg[f"modell ({a_})"]["rang_korr"] for a_ in pm.ARTEN}
    rv = {a_: erg["validierung"][f"modell ({a_})"]["logloss"] for a_ in pm.ARTEN}
    pruefe(min(rk.values()) > 0.2 and erg["gewaehlt"] == min(rv, key=rv.get) and mod["meta"]["art"] == erg["gewaehlt"]
           and mod["meta"]["sieg_a"] == erg["validierung"]["markt_test"]["a"] == erg["markt_test"]["a"]
           and all(erg[f"modell ({a_})"]["power_z"] is not None for a_ in pm.ARTEN),
           f"Power-Modell findet das eingebaute Signal als Regression, Rang- und Vorn-Modell (Rangkorrelation Test {rk}), "
           f"gewählt nach Log-Loss der Siegchance auf der Validierung {rv}: {erg['gewaehlt']}; Siegchance-a aus der "
           f"Validierung")
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        o_ = Path(tmp) / pm.MODELL_ORDNER
        em = pm.trainieren_morgen(hist=h, X=X, out=o_, runden=40, log=print)
        nur_morgen = (o_ / pm.MORGEN_DATEI).exists() and not (o_ / pm.MODELL_DATEI).exists()
        pm.trainieren(hist=h, X=X, out=o_, runden=40, art="regression", log=print)
        mod_m = pm.laden(Path(tmp))
        heute_m = h[h["race_id"] == h["race_id"].iloc[-1]].drop(columns=["finish_pos", "rel_place", "won", "placed",
                                                                           "prize_won", "arr", "tr", "odds_final"])
        heute_m = heute_m.assign(race_id="20260601R1C1", date=pd.Timestamp("2026-06-01"))
        vm = pm.vorhersage(h, heute_m, mod_m, log=print)
        ohne = heute_m.assign(race_id="20260601R1C2", odds_morning=np.nan)
        vo = pm.vorhersage(h, ohne, mod_m, log=print)
    mb = em.get("markt (Morgenquote allein)") or {}
    sm_ = [v_["sieg"] for v_ in vm.values()]
    pruefe(nur_morgen and "morgen" in mod_m and em["modell (regression)"]["logloss"] is not None
           and mb.get("logloss") is not None and mb.get("logloss_endquote") is not None
           and all(v_["sieg_quelle"] == "mischung" for v_ in vm.values()) and abs(sum(sm_) - 1) < 0.01
           and mod_m["meta"]["mischung"] and mod_m["meta"]["bericht"]["mischung (Morgenquote × Power)"]["logloss_mischung"]
           and any(abs(v_["sieg"] - v_["sieg_blind"]) > 1e-3 for v_ in vm.values())
           and all(v_["sieg_quelle"] == "power" and v_["sieg"] == v_["sieg_blind"] for v_ in vo.values()),
           f"Faire Siegchance: Mischung Morgenquote^{mod_m['meta']['mischung']['morgen']} × "
           f"Power^{mod_m['meta']['mischung']['power']} (Exponenten auf der Validierung, Power bleibt ohne Markt); "
           f"Kombi-Modell {pm.MORGEN_DATEI} als Bericht (Log-Loss {em['modell (regression)']['logloss']}, Morgenquote "
           f"allein {mb.get('logloss')}); auf der Karte je Rennen mit Morgenquote, sonst Power allein")
    pm_t = np.array([0.5, 0.3, 0.2, 0.6, 0.4]); pb_t = np.array([0.2, 0.5, 0.3, 0.5, 0.5]); r_t = ["a"] * 3 + ["b"] * 2
    mc_ = pm.mischung_chance(pm_t, pb_t, r_t, 1.0, 0.0)
    pruefe(np.allclose(mc_, pm_t) and np.allclose(pm.mischung_chance(pm_t, pb_t, r_t, 0.0, 1.0), pb_t)
           and abs(pm.mischung_chance(pm_t, pb_t, r_t, 0.5, 0.5)[:3].sum() - 1) < 1e-9,
           "Mischung Morgenquote × Power: Exponent 1/0 gibt die Quelle selbst, je Rennen auf 1")
    pruefe(pm.vorn_stufe([0.0, 0.5, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]).tolist() == [0, 0, 1, 1, 2, 2, 3, 3, 4]
           and pm.vorn_stufe([4 / 5, 13 / 15]).tolist() == [2, 2],
           "Ziel „vorn“: Platzanteil ≥ 0,7 / 0,8 / 0,9 → 1 / 2 / 3, Sieg → 4, hinten 0")
    # Feld-relative Merkmale: Rang 0..1 und Abstand zum Feldschnitt je Rennen, NaN bleibt NaN
    fr = pm.feld_relativ(pd.DataFrame({"rating_adj": [50.0, 60.0, np.nan, 70.0]}), pd.Series(["a", "a", "a", "b"]))
    pruefe(fr["rating_adj_rk"].tolist()[:2] == [0.0, 1.0] and np.isnan(fr["rating_adj_rk"][2])
           and np.isnan(fr["rating_adj_rk"][3]) and fr["rating_adj_dz"].tolist()[:2] == [-5.0, 5.0],
           "Power-Modell: Feld-relative Merkmale (Rang im Feld, Abstand zum Schnitt; Lücken bleiben leer)")
    ef = pm.feld_relativ(pd.DataFrame({"age": [3, 4, 5, 3], "runs": [5, 20, 30, 5]}), pd.Series(["a"] * 4),
                         pd.Series(pd.to_datetime(["2026-10-15"] * 4)))
    pruefe(ef["feld_aelter"].round(3).tolist() == [0.667, 0.333, 0.0, 0.667] and ef["feld_erfahrener"].tolist()[2] == 0.0
           and ef["season_doy"].eq(288).all() and ef["runs_dz"].tolist()[0] == -10.0,
           "Power-Modell: Erfahrung im Feld (Anteil älterer / erfahrenerer Gegner, Starts und Alter relativ) und Jahreszeit")
    # alte Quote vergleichbar: Quotenrang relativ und Marktchance des letzten Laufs
    q = X[["f1_odds", "f1_orank", "f1_pm"]].dropna()
    pruefe(len(q) and q["f1_orank"].between(0, 1).all() and q["f1_pm"].between(0, 1).all()
           and q[["f1_odds", "f1_pm"]].corr(method="spearman").iloc[0, 1] < -0.5,
           "Power-Modell: letzte Läufe mit Quotenrang (0 = Favorit) und Marktchance (1/Quote, je Rennen normiert)")
    # Starts 365 Tage ≤ Starts gesamt; letzter Lauf auf heutigem Boden/Distanz = der neueste frühere Lauf dieser Gruppe
    i = X["lgo_pos"].dropna().index[-1]
    hi = h.loc[i]
    vor = h[(h["horse_id"] == hi["horse_id"]) & (pd.to_datetime(h["date"]) < pd.to_datetime(hi["date"]))
            & (h["going_pmu"].map(pm.rtr_arr.boden_gruppe) == pm.rtr_arr.boden_gruppe(hi["going_pmu"]))]
    j = vor.sort_values("date").index[-1]
    pruefe((X["runs365"].fillna(0) <= X["runs"].fillna(0)).all() and abs(X.at[i, "lgo_pos"] - pm.ziel(h)[j]) < 1e-9
           and abs(X.at[i, "lgo_arr"] - (h.at[j, "arr"] - hi["weight_kg"] + pm.rc.GEWICHT_REF)) < 1e-9
           if pd.notna(h.at[j, "arr"]) else True,
           "Power-Modell: Starts 365 Tage, letzter Lauf auf heutigem Boden (Platzanteil, ARR mit heutigem Gewicht)")
    # verdichtete Form (letzte 5) und Wechsel zum letzten Lauf, von Hand nachgerechnet für einen Starter
    i = X["form_steig_pos"].dropna().index[-1]
    hi = h.loc[i]
    vor = h[(h["horse_id"] == hi["horse_id"]) & (pd.to_datetime(h["date"]) < pd.to_datetime(hi["date"]))]
    vor = vor.sort_values("date", ascending=False).head(pm.FORM_VERDICHTET)
    rp = pm.ziel(h)[vor.index].to_numpy()
    j = vor.index[0]
    fv = h.groupby("race_id")["valeur"].transform("mean")
    pruefe(abs(X.at[i, "form5_pos"] - np.nanmean(rp)) < 1e-9 and abs(X.at[i, "form5_best"] - np.nanmax(rp)) < 1e-9
           and abs(X.at[i, "form5_top"] - np.mean(rp[np.isfinite(rp)] >= pm.FORM_TOP)) < 1e-9
           and X.at[i, "chg_weight"] == hi["weight_kg"] - h.at[j, "weight_kg"]
           and X.at[i, "chg_dist"] == hi["distance_m"] - h.at[j, "distance_m"]
           and abs(X.at[i, "chg_prize"] - (np.log1p(hi["prize_eur"]) - np.log1p(h.at[j, "prize_eur"]))) < 1e-9
           and (np.isnan(X.at[i, "chg_class"]) if pd.isna(fv[i]) or pd.isna(fv[j]) else abs(X.at[i, "chg_class"] - (fv[i] - fv[j])) < 1e-9)
           and X.at[i, "chg_trainer"] == float(hi["trainer_key"] != h.at[j, "trainer_key"]),
           "Power-Modell: Form der letzten 5 (Ø, Bestwert, Spitzenläufe) und Wechsel zum letzten Lauf (Gewicht, Distanz, Klasse, Preisgeld, Trainer)")
    # Formtrend (Steigung je Lauf), zeitgewichtete Form und Form über Erwartung, von Hand nachgerechnet
    vt = h[(h["horse_id"] == hi["horse_id"]) & (pd.to_datetime(h["date"]) < pd.to_datetime(hi["date"]))]
    vt = vt.sort_values("date", ascending=False)
    y = pm.ziel(h)[vt.index[:pm.FORM_TREND_N]].to_numpy(dtype=float)
    x = -np.arange(len(y), dtype=float)
    m = np.isfinite(y)
    soll_st = np.polyfit(x[m], y[m], 1)[0]
    vz = vt.head(pm.FORM_ZEIT_N)
    tage = (pd.to_datetime(hi["date"]) - pd.to_datetime(vz["date"])).dt.days.to_numpy()
    yz = pm.ziel(h)[vz.index].to_numpy(dtype=float)
    wz = 0.5 ** (tage / pm.FORM_HWZ)
    mz = np.isfinite(yz)
    soll_z = ((wz[mz] * yz[mz]).sum() + pm.FORM_ZEIT_K * pm.FORM_ZEIT_PRIOR["pos"]) / (wz[mz].sum() + pm.FORM_ZEIT_K)
    pruefe(abs(X.at[i, "form_steig_pos"] - soll_st) < 1e-9 and abs(X.at[i, "formz_pos"] - soll_z) < 1e-9
           and pm._steigung(np.array([0.9, 0.5, 0.1])) > 0 and np.isnan(pm._steigung(np.array([0.9, np.nan, 0.1])))
           and X["form5_ue"].dropna().between(-1, 1).all() and X["form5_ue"].notna().any()
           and "form5_trend" not in X.columns and abs(X.at[i, "formz_n"] - wz[mz].sum()) < 1e-9
           and pm._gruppe("arr_best365_dz") == "Bestform ARR" and pm._gruppe("trainerwechsel5") == "Trainerwechsel"
           and pm._gruppe("form5_klasse") == "Klasse der letzten Läufe" and pm._gruppe("chg_prize") == "Klassenwechsel"
           and pm._gruppe("form5_pos_dz") == "Form letzte 5" and pm._gruppe("dam_sire_score") == "Muttervater",
           "Power-Modell: Formtrend (Steigung je Lauf, ab 3 Werten), zeitgewichtete Form (Halbwertszeit, zum Ausgangswert "
           "geschrumpft, Zahl der Läufe) und Pos über Erwartung; Treiber-Gruppen nach dem längsten Präfix")
    # Scheuklappen: erstmals nur, wenn vorher nie getragen; Jockey-Wechsel mit Score-Differenz
    ok_b = True
    for i in X["blink_first"].dropna().index:
        hi = h.loc[i]
        frueher = h[(h["horse_id"] == hi["horse_id"]) & (pd.to_datetime(h["date"]) < pd.to_datetime(hi["date"]))]
        fr = frueher["blinkers"].dropna()
        soll = float(hi["blinkers"] == "OEILLERES_CLASSIQUE" and (fr == "SANS_OEILLERES").all())
        ok_b &= X.at[i, "blink_first"] == soll
    pruefe(ok_b and X["blink_first"].eq(1).any() and X["chg_jockey"].eq(1).any()
           and X.loc[X["chg_jockey"].eq(0), "chg_jockey_score"].dropna().abs().max() < 1e-9,
           "Power-Modell: Scheuklappen erstmals, Jockey-Wechsel (gleicher Jockey -> Score-Differenz 0)")
    # Rennverlauf der Formzeilen: gegen = +1, mit = −1, neutral = 0, unbekannt = leer
    hv = h.assign(verlauf_pferd=np.where(h["saddle_no"] % 3 == 0, "gegen", np.where(h["saddle_no"] % 3 == 1, "mit", None)))
    _vz = pm.verlauf_zeitlich                                  # Einordnung vorgeben, geprüft wird die Umrechnung
    pm.verlauf_zeitlich = lambda d: d["verlauf_pferd"].to_numpy(dtype=object)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            Xv = pm.merkmale(hv, duelle=False, log=print)
    finally:
        pm.verlauf_zeitlich = _vz
    w = set(Xv["f1_verlauf"].dropna().unique())
    pruefe(w == {1.0, -1.0} and Xv["f1_verlauf"].isna().any(),
           "Power-Modell: Formzeilen mit Rennverlauf (gegen +1, mit −1, unbekannt leer)")
    # Gleichstände (z. B. viele gleiche Ratings) zählen anteilig, nicht nach Zeilenreihenfolge
    gl = pd.DataFrame({"race_id": [1] * 4 + [2] * 4, "y": [1, .66, .33, 0] * 2, "r": [5, 5, 5, 5, 1, 9, 8, 7]})
    b = pm._bewerten(gl, "r")
    pruefe(b["sieger_getroffen"] == 0.125 and b["sieger_in_top3"] == 0.375,
           "Power-Modell-Prüfung: Gleichstände zählen anteilig (4 gleiche Ratings -> ¼ Sieger-Treffer)")
    # Zwischenspeicher der Merkmale: zweiter Lauf liest merkmale.parquet statt neu zu bauen
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as aus:
        o = Path(tmp) / pm.MODELL_ORDNER
        o.mkdir()
        X.to_parquet(o / pm.MERKMAL_DATEI)
        (o / pm.MERKMAL_DATEI).with_suffix(".json").write_text(json.dumps({"version": pm.MERKMAL_VERSION}))
        pm.trainieren(hist=h, out=o, runden=10, ab=str(h["date"].min())[:10], log=print)
    pruefe("Merkmale aus" in aus.getvalue() and "Abdeckung je Jahr" in aus.getvalue(),
           "Power-Modell: Merkmale aus dem Zwischenspeicher, Abdeckung je Jahr im Protokoll")
    # Race Card: baue_daten mit Modell -> „power“ je heutigem Starter (Testkarte aus racecard_pruefen)
    import racecard as rc
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        pm.trainieren(hist=h, X=X, out=Path(tmp) / pm.MODELL_ORDNER, runden=30, log=print)
        mod = pm.laden(Path(tmp))
        d = rc.baue_daten(*_RC_FALL, power=mod)
    st = [x for r in d["races"].values() for x in r["runners"] if not x["nr"]]
    pruefe(st and all(x["power"] and isinstance(x["power"]["p"], int) for x in st),
           f"Race Card mit Power-Modell: Power für alle {len(st)} heutigen Starter")
    # Claude-JSON mit Modell: modell je Starter (blind), vergleich_365, value (Markt), rote Starter als Kurzzeile
    import claude_export as ce
    dk = json.loads(json.dumps(d, default=str))
    rr = next(iter(dk["races"].values()))
    rs = [x for x in rr["runners"] if not x["nr"]]
    rs[0]["power"].update(p=110, sieg=0.8, wert=1.0, gold=False); rs[1]["power"].update(p=90, sieg=0.2, wert=0.8, gold=False)
    dk["modelle"] = {"power": {"einordnung": "x"}, "value": {"einordnung": "y"}}
    eb, em = ce.export(dk), ce.export_markt(dk)
    rb_, rm_ = next(iter(eb["races"].values())), next(iter(em["races"].values()))
    pruefe([y["no"] for y in rb_["runners"]] == [rs[0]["no"]] and rb_["runners"][0]["modell"]["fair"] == 1.2
           and rb_["weitere"]["anzahl"] == 1 and rb_["weitere"]["starter"][0]["no"] == rs[1]["no"]
           and rb_["weitere"]["starter_gesamt"] == 2 and "vergleich_365" in rb_
           and {v["no"] for v in rb_["vergleich_365"]["verbindungen"]} == {x["no"] for x in rs}
           and eb["modelle"] == {"power": {"einordnung": "x"}} and em["modelle"] == {"value": {"einordnung": "y"}}
           and all("value" in x for x in rm_["runners"]) and any(x["blind_nur_kurz"] for x in rm_["runners"]),
           "Claude-JSON: Modell je Starter, rote Starter ohne Value als Kurzzeile (Anzahl, Siegchance), Feldvergleich "
           "ARR/TR/Verbindungen, Value nur in der Marktdatei, Verlässlichkeit aufgeteilt")
    rf = ce.rennen({"race_id": "x", "runners": [{"no": n, "nr": False, "power": {"p": p_, "sieg": 0.1}} for n, p_ in
                                                ((1, 100), (2, 120), (3, 110))]}, None)
    pruefe(not ce._halten({"power": {"p": 90, "wert": 1.05}}) and ce._halten({"power": {"p": 90, "wert": 1.15}})
           and ce._halten({"power": {"p": 90, "wert": 0.9, "gold": True}}) and ce._halten({"power": {"p": 96}})
           and rf["vorgerechnet"]["reihenfolge"] == [2, 3, 1] and [y["no"] for y in rf["runners"]] == [2, 3, 1],
           "Claude-JSON: rote Starter nur mit Value-Faktor > 1,1 oder Gold vollständig; Reihenfolge nach Power")
    # Verlässlichkeit je Rennart und Value-Kennzeichen (warnung, gold nur bis Prognose-Cote 10)
    je_p = pm._je_rennart_power({"racetype": [{"segment": "Handicap", "rennen": 1000, "korr_regression": 0.36,
                                              "sieger_regression": 0.21, "korr_markt": 0.41, "sieger_markt": 0.26}],
                                 "age_group": [{"segment": "3yo", "rennen": 900, "korr_regression": 0.46,
                                                "sieger_regression": 0.28, "korr_markt": 0.48, "sieger_markt": 0.33}]})
    je_v = pm._je_rennart_value({"racetype": [{"segment": "Handicap", "starter": 9000, "ae_kombi_unten": 0.79,
                                              "ae_kombi_oben": 1.09, "gold_wetten": 1182, "gold_rendite": -0.18}]})
    rh = {"race_id": "y", "type": "Handicap Categorie Divise", "age": "TROIS_ANS", "runners": [
        {"no": 1, "nr": False, "age": 3, "power": {"p": 110, "sieg": 0.5, "wert": 1.3, "gold": True, "warn": False},
         "prono": {"sel": {"cote_dec": 4.0}}},
        {"no": 2, "nr": False, "age": 3, "power": {"p": 100, "sieg": 0.3, "wert": 1.3, "gold": True, "warn": False},
         "prono": {"sel": {"cote_dec": 15.0}}},
        {"no": 3, "nr": False, "age": 3, "power": {"p": 90, "sieg": 0.2, "wert": 0.6, "gold": False, "warn": True},
         "prono": {"sel": {"cote_dec": 2.5}}}]}
    bh, mh = ce.rennen(rh, None, je_p), ce.rennen_markt(rh, je_v)
    vh = {y["no"]: y["value"] for y in mh["runners"]}
    pruefe(bh["modell_rennart"]["renntyp"] == "Handicap" and bh["modell_rennart"]["altersgruppe"] == "3yo"
           and "klar schwächer" in bh["modell_rennart"]["power_renntyp"]["einordnung"]
           and "fast so gut" in bh["modell_rennart"]["power_altersgruppe"]["einordnung"]
           and "Gold verlor" in mh["value_rennart"]["value_renntyp"]["einordnung"]
           and vh[1]["gold"] and not vh[2]["gold"] and vh[2]["oberste_10"] and vh[3]["warnung"]
           and "value_rennart" not in bh and "modell_rennart" not in mh,
           "Claude-JSON: Verlässlichkeit im heutigen Renntyp/Altersgruppe (blind Power, Markt Value), gold nur bis "
           "Prognose-Cote 10, Warnsignal je Starter")
    mi2 = pm.modell_info(mw)
    pruefe(set(mi2["power"]["je_rennart"]) == {"racetype", "age_group"} and set(mi2["value"]["je_rennart"]) == {"racetype", "age_group"}
           and all(isinstance(w["warn"], bool) for w in vw.values())
           and sum(w["warn"] for w in vw.values()) <= len(vw),
           "Modell-Info je Rennart aus dem Bericht; Value-Warnsignal (unterstes Fünftel) je Starter in der Vorhersage")


def _abst_population(seed=0, n_linien=36, laeufe=400) -> pd.DataFrame:
    """Väter mit eingebauter Neigung: Sprinter, Steher, frühreif (als 2-Jährige stark; 2-Jährige laufen nur kurz),
    PSF, weicher Boden, neutral."""
    import numpy as np
    rng = np.random.default_rng(seed)
    z = []
    for li in range(n_linien):
        typ = ["sprint", "steher", "frueh", "psf", "weich", "neutral"][li % 6]
        for _ in range(laeufe):
            a = int(rng.choice([2, 3, 4])); mon = int(rng.integers(3, 12))
            d = int(rng.choice([1200, 1300])) if a == 2 else int(rng.choice([1200, 2000, 2800]))
            g = str(rng.choice(["VERY FAST", "FAST", "SLOW", "VERY SLOW", "PSF"]))
            f = {"sprint": 1.5 if d <= 1400 else 0.7, "steher": 1.5 if d > 2400 else 0.8, "frueh": 1.7 if a == 2 else 1.0,
                 "psf": 1.6 if g == "PSF" else 0.9, "weich": 1.5 if "SLOW" in g else 0.8 if "FAST" in g else 1.0}.get(typ, 1.0)
            pl = rng.random() < min(0.95, 0.3 * f)
            pos = 1 if pl and rng.random() < 0.3 else (int(rng.integers(1, 4)) if pl else int(rng.integers(4, 11)))
            z.append(dict(sire_key=f"{typ}{li}", date=pd.Timestamp(2025, mon, 15), age=a, distance_m=d, going_pmu=g,
                          won=int(pos == 1), placed=int(pl), exp_place=0.3, n_runners=10, rel_place=(10 - pos) / 9,
                          prize_won=5000.0 * (pos == 1) + 1000.0 * pl))
    return pd.DataFrame(z)


def abstammung_pruefen() -> None:
    """Abstammungsprofil: Perzentile gegen alle Väter auf vier Skalen; Wert = Ø aus A/E+, Pos+, €/L+; die frühreife
    Linie (2-Jährige stark und nur auf kurzen Strecken) darf nach der Korrektur nicht als Sprinter erscheinen."""
    import racecard as rc
    p = rc.abstammung_profil(_abst_population(), "sire_key")
    pz = lambda typ, dim: [v[dim]["perzentil"] for k, v in p.items() if k.startswith(typ)]
    mid = lambda l: sorted(l)[len(l) // 2]
    z = p["steher1"]["dist"]["zeilen"][0]
    x = rc.abst_pferd(p, "steher1", 2800, "PSF", 3, 8)
    pruefe(mid(pz("sprint", "dist")) <= 20 and mid(pz("steher", "dist")) >= 80 and 25 <= mid(pz("frueh", "dist")) <= 75
           and mid(pz("frueh", "reife")) <= 30 and mid(pz("psf", "belag")) >= 80 and mid(pz("weich", "boden")) <= 20
           and len(z) == 8 and abs(z[4] - (z[5] + z[6] + z[7]) / 3) <= 1
           and x["dist"]["heute"] == "Steher" and x["dist"]["passung"] == "passt" and x["boden"]["heute"] is None
           and x["belag"]["heute"] == "PSF" and x["reife"]["heute"] == "3yo"
           and [rc.abst_dist_kat(m) for m in (1400, 1401, 2400, 2401)] == ["Sprinter", "Mitteldistanz", "Mitteldistanz", "Steher"]
           and [rc.abst_reife_kat(a_) for a_ in (2, 3, 4, 9)] == ["2yo", "3yo", "4yo+", "4yo+"],
           f"Abstammungsprofil: Perzentile gegen alle Väter – Distanz Sprinter P{mid(pz('sprint', 'dist'))} / Steher "
           f"P{mid(pz('steher', 'dist'))} / frühreife Linie P{mid(pz('frueh', 'dist'))} (korrigiert, kein Sprinter), "
           f"Alter 2yo-stark P{mid(pz('frueh', 'reife'))}, Belag PSF P{mid(pz('psf', 'belag'))}, Boden weich "
           f"P{mid(pz('weich', 'boden'))}; Wert = Ø aus A/E+, Pos+, €/L+; Passung zur heutigen Kategorie")
    lg = lambda *a_: rc.abst_pferd(p, "neutral5", *a_)
    l15, l18, l24 = (lg(m_, "FAST", 4, 8)["dist"]["lage"] for m_ in (1250, 1800, 2400))
    b_vs, b_s, b_vf = (lg(2000, g_, 4, 8)["boden"]["lage"] for g_ in ("VERY SLOW", "SLOW", "VERY FAST"))
    r2, r3, r4 = (lg(2000, "FAST", a_, m_)["reife"]["lage"] for a_, m_ in ((2, 6), (3, 7), (5, 7)))
    pruefe(l15 < l18 < l24 and b_vs < b_s < b_vf and r2 < r3 < r4 and lg(2000, "PSF", 4, 8)["belag"]["lage"] == 100,
           f"Abstammungsprofil: Lage heute stufenlos als Perzentil aller Läufe – 1250/1800/2400 m P{l15}/P{l18}/P{l24}, "
           f"Boden Very slow/Slow/Very fast P{b_vs}/P{b_s}/P{b_vf}, Alter 2yo/3yo/5j (4yo+) P{r2}/P{r3}/P{r4}")


def festkurse_pruefen() -> None:
    """Wettstar-Festkurse: Zuordnung zur PMU-Karte trotz anderer Schreibweise (Akzente, Apostroph, Bindestrich,
    Herkunft), vertauschter Startnummer und anderer Bahnschreibweise; Erwartungswert gegen das Modell in der
    Marktdatei, nichts davon in der blinden Datei."""
    import wettstar as ws
    import claude_export as ce
    df = pd.DataFrame([
        dict(Veranstaltung="Marseille-Borely", Rennen="2", Start="12:02", Nr=1, Pferd="Hugo Cabret", Toto=2.9, FK_Sieg=3.0, FK_Platz=1.5, NS=False),
        dict(Veranstaltung="Marseille-Borely", Rennen="2", Start="12:02", Nr=2, Pferd="L'Abbaye", Toto=8.1, FK_Sieg=7.0, FK_Platz=2.5, NS=False),
        dict(Veranstaltung="Marseille-Borely", Rennen="2", Start="12:02", Nr=4, Pferd="Saint Martin", Toto=15.8, FK_Sieg=25.0, FK_Platz=4.4, NS=False),
        dict(Veranstaltung="Marseille-Borely", Rennen="2", Start="12:02", Nr=3, Pferd="Ritzy Roxy", Toto=8.6, FK_Sieg=6.5, FK_Platz=2.4, NS=False),
        dict(Veranstaltung="Dax", Rennen="2", Start="14:30", Nr=1, Pferd="Jour De Coeur", Toto=3.9, FK_Sieg=5.5, FK_Platz=1.9, NS=False)])
    runner = lambda no, horse, sieg: {"no": no, "horse": horse, "nr": False, "power": {"p": 100, "sieg": sieg}}
    daten = {"races": {"R1C2": {"race_id": "R1C2", "course": "MARSEILLE BORELY", "race_no": 2, "time": "12h02", "runners": [
        runner(1, "HUGO CABRET", 0.4), runner(2, "L ABBAYE", 0.3), runner(3, "SAINT-MARTIN (FR)", 0.2),
        runner(4, "RITZY ROXY", 0.1), runner(5, "UNBEKANNT", None)]},
        "R2C1": {"race_id": "R2C1", "course": "PARISLONGCHAMP", "race_no": 1, "time": "13:50",
                 "runners": [runner(1, "JOUR DE COEUR", 0.5)]}}}
    n = ws.anhaengen(daten, df, log=lambda *a: None)
    x = {y["no"]: y for y in daten["races"]["R1C2"]["runners"]}
    p_ = [0.4, 0.3, 0.2, 0.1]
    summe = sum(ce.harville_platz(p_, i, 2) for i in range(4))
    mk = ce.rennen_markt(daten["races"]["R1C2"])
    fk = {y["no"]: y.get("festkurs") for y in mk["runners"]}
    bl = ce.rennen(daten["races"]["R1C2"], None)
    pruefe(n == 4 and x[1]["fk"]["sieg"] == 3.0 and x[2]["fk"]["sieg"] == 7.0 and x[3]["fk"]["sieg"] == 25.0
           and x[3]["fk"]["name"] == "Saint Martin" and x[4]["fk"]["sieg"] == 6.5 and "fk" not in x[5]
           and "fk" not in daten["races"]["R2C1"]["runners"][0]
           and abs(summe - 2) < 1e-9 and fk[1]["ev_sieg"] == 1.2 and fk[1]["value_sieg"] and not fk[4]["value_sieg"]
           and fk[3]["value_sieg"] and fk[1]["platz_bis"] == 2
           and not any("fk" in y or "festkurs" in y for y in bl["runners"]),
           "Festkurse (Wettstar): Zuordnung trotz Schreibweise (L'Abbaye/L ABBAYE, Saint Martin/SAINT-MARTIN (FR), "
           "Marseille-Borely/MARSEILLE BORELY) und vertauschter Startnummer, fremde Bahn ohne Zuordnung; "
           "Harville-Platzchancen summieren sich zu k; Erwartungswert gegen das Modell nur in der Marktdatei")
    pruefe(ws.num("57,0") == 57.0 and ws.num("3.90") == 3.9 and ws.num("1.234,5") == 1234.5 and ws.num("") is None
           and ws.aehnlich("Grisy April", "GRISY-APRIL") == 1.0 and ws.aehnlich("Hugo Cabret", "Ritzy Roxy") < 0.6,
           "Festkurse: Zahlen (Komma/Punkt) und Namensvergleich")
    mt = [dict(name="Marseille-Borely", art="Galopp", fk=True), dict(name="Dax", art="Galopp", fk=False),
          dict(name="Vincennes", art="Trab", fk=True), dict(name="Ascot", art="Galopp", fk=False),
          dict(name="Marseille-Vivaux", art="Galopp", fk=False)]
    nur_toto = {"races": {"R9C2": {"race_id": "R9C2", "course": "DAX", "race_no": 2, "time": "14:30",
                                   "runners": [runner(1, "JOUR DE COEUR", 0.3)]}}}
    df2 = df.assign(FK_Sieg=lambda d: d["FK_Sieg"].where(d["Veranstaltung"] != "Dax"),
                    FK_Platz=lambda d: d["FK_Platz"].where(d["Veranstaltung"] != "Dax"))
    ws.anhaengen(nur_toto, df2, log=lambda *a: None)
    jt = nur_toto["races"]["R9C2"]["runners"][0].get("fk") or {}
    pruefe([m["name"] for m in ws.veranstaltungen_waehlen(mt, ["MARSEILLE BORELY", "DAX"])] == ["Marseille-Borely", "Dax"]
           and [m["name"] for m in ws.veranstaltungen_waehlen(mt)] == ["Marseille-Borely", "Dax", "Marseille-Vivaux"]
           and [m["name"] for m in ws.veranstaltungen_waehlen(mt, nur_fk=True)] == ["Marseille-Borely"]
           and jt.get("toto") == 3.9 and jt.get("sieg") is None,
           "Festkurse: nur Galopp-Veranstaltungen, die zu den Bahnen der Karte passen (Trab, Ausland und "
           "Marseille-Vivaux ≠ Marseille-Borely fallen weg), auch ohne FK-Kennzeichen; reine Toto-Rennen werden zugeordnet")
    import time as _time

    class _Seite:                                          # Seite, die zweimal nicht antwortet
        def __init__(self, fehler):
            self.fehler, self.aufrufe = fehler, 0
        def goto(self, url, **k):
            self.aufrufe += 1
            if self.aufrufe <= self.fehler:
                raise TimeoutError("Page.goto: Timeout 45000ms exceeded.\nCall log: …")
        def wait_for_selector(self, sel, **k):
            pass
        def wait_for_timeout(self, ms):
            pass
    schlaf, _time.sleep = _time.sleep, lambda s_: None
    try:
        s2, s4 = _Seite(2), _Seite(4)
        ws._load(s2, "https://x", "body")
        try:
            ws._load(s4, "https://x", "body")
            aufgegeben = False
        except TimeoutError:
            aufgegeben = True
    finally:
        _time.sleep = schlaf
    pruefe(s2.aufrufe == 3 and aufgegeben and s4.aufrufe == ws.VERSUCHE,
           f"Festkurse: Seitenaufruf bei Zeitüberschreitung bis zu {ws.VERSUCHE}-mal wiederholt, danach Fehler (Karte ohne Kurse)")
    import tempfile as _tf
    with _tf.TemporaryDirectory() as tmp:
        csv = Path(tmp) / "kurse.csv"
        df.assign(Rennart="Flachrennen", Status="OPEN", Titel="", Rennen_ID=1, Box=1, Gewicht="", Jockey="", Tipp="") \
          .to_csv(csv, index=False, sep=";", decimal=",")             # wie Zelle 3 des Wettstar-Notebooks
        d_csv = {"races": {"R1C2": {**daten["races"]["R1C2"], "runners": [runner(1, "HUGO CABRET", 0.4)]}}}
        n_csv = ws.anhaengen(d_csv, str(csv), log=lambda *a: None)
    f_csv = d_csv["races"]["R1C2"]["runners"][0].get("fk") or {}
    pruefe(n_csv == 1 and f_csv.get("sieg") == 3.0 and f_csv.get("toto") == 2.9,
           "Festkurse aus der CSV des Wettstar-Notebooks (Semikolon, Dezimalkomma) übernommen")
    heute18 = [dict(name=n, art=a_, fk=f) for n, a_, f in [("Zurich", "Galopp", 0), ("Caen", "Trab", 1),
               ("Longchamp", "Galopp", 1), ("Tarbes", "Galopp", 0), ("Amiens", "Trab", 0), ("Maronas", "Galopp", 0)]]
    pruefe([m["name"] for m in ws.veranstaltungen_waehlen(heute18, ["HYERES", "PARISLONGCHAMP", "TARBES"])] == ["Longchamp", "Tarbes"]
           and ws.bahn_aehnlich("La Teste", "LA TESTE DE BUCH") >= ws.BAHN_MIN
           and ws.bahn_aehnlich("Marseille-Vivaux", "MARSEILLE BORELY") < ws.BAHN_MIN
           and ws.bahn_aehnlich("Les Sables", "SABLES D OLONNE") >= ws.BAHN_MIN
           and ws.bahn_aehnlich("Les Sables", "DEAUVILLE") < ws.BAHN_MIN
           and ws.bahn_aehnlich("Le Lion d'Angers", "LION D ANGERS") >= ws.BAHN_MIN
           and ws.aehnlich("Max", "Max Win") < ws.NAME_MIN,
           "Festkurse: Bahnname im anderen enthalten zählt (Longchamp = PARISLONGCHAMP, La Teste = LA TESTE DE BUCH; "
           "Liste vom 18.10.: Longchamp und Tarbes, nicht Zurich/Maronas/Trab); bei Pferdenamen nicht")


def festkurse_aktualisieren_pruefen() -> None:
    """Schneller zweiter Lauf: gespeicherte Kartendaten laden, Festkurse einfügen, neue Nichtstarter übernehmen
    (Siegchancen neu auf 100 %), HTML und Claude-JSONs neu schreiben – ohne Historie neu zu rechnen."""
    import io, contextlib, json as _json, tempfile
    import racecard as rc
    hist, heute_r, heute_s, tag = _RC_FALL
    with contextlib.redirect_stdout(io.StringIO()):
        d = rc.baue_daten(hist, heute_r, heute_s, tag)
    rid, r = next(iter(d["races"].items()))
    for i, x in enumerate(r["runners"]):
        x["power"] = {"p": 100, "sieg": [0.6, 0.4][i % 2], "treiber": []}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "racecards" / f"racecard_{tag:%Y%m%d}.html"
        out.parent.mkdir(parents=True)
        rc.daten_pfad(out).write_text(_json.dumps(d, default=str), encoding="utf-8")
        df = pd.DataFrame([dict(Veranstaltung=r["course"].title(), Rennen=str(r["race_no"]), Start=r["time"] or "",
                                Nr=x["no"], Pferd=x["horse"].title(), Toto=3.5 + i, FK_Sieg=None if i else 2.5,
                                FK_Platz=None, NS=False) for i, x in enumerate(r["runners"])])
        with contextlib.redirect_stdout(io.StringIO()) as aus:
            rc.festkurse_aktualisieren(Path(tmp), tag, out, festkurse=df, nichtstarter=False)
        neu = _json.loads(rc.daten_pfad(out).read_text(encoding="utf-8"))
        st = neu["races"][rid]["runners"]
        ok_dateien = out.exists() and out.with_name(out.stem + "_claude.json").exists()
    nr_df = pd.DataFrame([{"race_id": rid, "saddle_no": st[1]["no"], "status": "NON_PARTANT", "incident": None}])
    neu_nr = rc.nichtstarter_nachtragen(neu, nr_df)
    pruefe(ok_dateien and st[0]["fk"]["sieg"] == 2.5 and st[1]["fk"]["toto"] == 4.5 and st[1]["fk"]["sieg"] is None
           and neu.get("festkurse_stand") and "Kartendaten geladen" in aus.getvalue()
           and len(neu_nr) == 1 and neu["races"][rid]["runners"][1]["nr"]
           and neu["races"][rid]["runners"][0]["power"]["sieg"] == 1.0,
           "Festkurse nachträglich: gespeicherte Kartendaten + Wettstar-Kurse -> HTML und Claude-JSONs neu (ohne "
           "Neuberechnung); neue Nichtstarter markiert, Siegchancen der übrigen wieder auf 100 %")
    # Zwei Veranstaltungen: morgens nur die frühe mit Festkursen; der zweite Lauf ergänzt nur die späte
    import copy
    with contextlib.redirect_stdout(io.StringIO()):
        d = rc.baue_daten(hist, heute_r, heute_s, tag)
    rid, r = next(iter(d["races"].items()))
    r2 = copy.deepcopy(r)
    r2["course"], rid2 = "VICHY", rid + "X"
    d["races"][rid2] = r2
    r3 = copy.deepcopy(r)                                     # späteres Rennen derselben Bahn: morgens nur Toto
    r3["race_no"], rid3 = int(r["race_no"]) + 1, rid + "Y"
    d["races"][rid3] = r3

    def tab(rennen, kurs, nur_toto=()):
        return pd.DataFrame([dict(Veranstaltung=rr["course"].title(), Rennen=str(rr["race_no"]), Start=rr["time"] or "",
                                  Nr=x["no"], Pferd=x["horse"].title(), Toto=5.0,
                                  FK_Sieg=None if rr is nur_toto else kurs, FK_Platz=None, NS=False)
                             for rr in rennen for x in rr["runners"]])
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "racecards" / f"racecard_{tag:%Y%m%d}.html"
        out.parent.mkdir(parents=True)
        rc.daten_pfad(out).write_text(_json.dumps(d, default=str), encoding="utf-8")
        lies = lambda: _json.loads(rc.daten_pfad(out).read_text(encoding="utf-8"))
        with contextlib.redirect_stdout(io.StringIO()):
            rc.festkurse_aktualisieren(Path(tmp), tag, out, festkurse=tab([r, r3], 2.5, r3), nichtstarter=False)
            a = lies()
            rc.festkurse_aktualisieren(Path(tmp), tag, out, festkurse=tab([r, r2, r3], 9.0), nichtstarter=False)
            b = lies()
            rc.festkurse_aktualisieren(Path(tmp), tag, out, festkurse=tab([r, r2, r3], 7.0), nichtstarter=False,
                                       nur_fehlende=False)
            c = lies()
    fk = lambda dd, k: [(x.get("fk") or {}).get("sieg") for x in dd["races"][k]["runners"]]
    toto = lambda dd, k: {(x.get("fk") or {}).get("toto") for x in dd["races"][k]["runners"]}
    pruefe(set(fk(a, rid)) == {2.5} and set(fk(a, rid2)) == {None} and set(fk(a, rid3)) == {None}
           and toto(a, rid3) == {5.0}
           and set(fk(b, rid)) == {2.5} and set(fk(b, rid2)) == {9.0} and set(fk(b, rid3)) == {9.0}
           and set(b["festkurse_bahnen"]) == {r["course"], "VICHY"}
           and set(fk(c, rid)) == {7.0} and set(fk(c, rid2)) == {7.0} and set(fk(c, rid3)) == {7.0},
           "Festkurse nachträglich: Rennen mit Festkursen bleiben, alle übrigen werden geholt – auch spätere Rennen "
           "derselben Bahn, die bisher nur Toto zeigen, und die spätere Veranstaltung; nur_fehlende=False holt alle neu")


def tipp_auswertung_pruefen() -> None:
    import io, contextlib, json as _json, tempfile
    import tipp_auswertung as ta
    base = Path(tempfile.mkdtemp())
    (base / "tipps").mkdir(); (base / "racecards").mkdir()
    (base / "parquet" / "pmu_runners").mkdir(parents=True)
    block = {"tipps": [{"race_id": "20261007R4C1", "no": 1, "p": 0.5, "stufe": "0", "mq": 2.5, "angles": ["ratings"]},
                       {"race_id": "20261007R4C1", "no": 2, "p": 0.3, "stufe": "++", "mq": 4.0, "angles": ["klasse", "duell"], "fk": 6.0, "value": None},
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
           and w.iloc[0]["n"] == 2 and abs(w.iloc[0]["ergebnis"] - 3.0) < 1e-9
           and w.loc["Festkurs ≥ Mindestquote (zum Festkurs)", "ergebnis"] == 5.0
           and w.loc["Festkurs mit value > 0 (zum Festkurs)", "n"] == 1
           and abs(p.loc[p["no"] == 2, "value"].iloc[0] - (0.3 * 6.0 - 1)) < 1e-9,
           "Tipp-Auswertung: Protokoll-Block und alte Tabelle gelesen, Stufen, Angle-Typen und Wett-Ergebnis stimmen; "
           "nachgetragener Festkurs (fk) wird zum Festkurs gewertet, value = p × fk − 1")


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


def pmu_runner_gewicht_() -> tuple:
    """pmu.runner_row: (getragen, zugeteilt) für einen Reiter mit 2,5 kg Erlaubnis."""
    import pmu
    z = pmu.runner_row("R", {"numPmu": 1, "handicapPoids": 580, "poidsConditionMonte": 555})
    return z["weight_kg"], z["weight_assigned_kg"]


def pm_bahn_() -> float:
    """Abweichung der Bahnzuordnung: Summe der km zwischen Schreibweisen derselben Bahn."""
    import bahn_orte as bo
    paare = [("LE LION D'ANGERS", "LION D ANGERS"), ("DEAUVILLE-LA TOUQUES", "DEAUVILLE"), ("LA-ROCHE-POSAY", "LA ROCHE POSAY"),
             ("LYON-PARILLY", "LYON PARILLY"), ("ParisLongchamp", "PARISLONGCHAMP"), ("CAGNES-SUR-MER", "CAGNES MER")]
    if any(bo.koordinaten(a) is None for a, _ in paare) or bo.koordinaten("ASCOT") is not None:
        return float("inf")
    return sum(bo.km(bo.koordinaten(a), bo.koordinaten(b)) for a, b in paare) + abs(
        bo.km(bo.koordinaten("CHANTILLY"), bo.koordinaten("PARISLONGCHAMP")) - 41)


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
    # getragenes Gewicht (poidsConditionMonte, mit Erlaubnis) statt zugeteiltem; Schrittlänge und Vmax relativ zum Feld
    gw_ = rc.gewicht_getragen(pd.DataFrame({"weight_kg": [58.0, 57.0, 56.0], "p_handicapPoids": [580, 570, None],
                                            "p_poidsConditionMonte": [555, None, None]}))
    pruefe(gw_["weight_kg"].tolist() == [55.5, 57.0, 56.0] and gw_["weight_assigned_kg"].tolist()[:2] == [58.0, 57.0]
           and np.isnan(gw_["weight_assigned_kg"].iloc[2])
           and pmu_runner_gewicht_() == (55.5, 58.0),
           "Gewicht: getragen = poidsConditionMonte (Erlaubnis des Reiters), sonst handicapPoids; zugeteilt = handicapPoids "
           "(ältere Tagesdateien über die p_-Spalten korrigiert)")
    sec_s = sections.assign(stride_len_m=[6.5, 7.0, 7.2, 7.4, 7.0, 6.6] + [6.5, 6.9, 7.0, 7.2, 7.1, 7.1])
    sch_ = sf.schritt_aus_abschnitten(sec_s).set_index("saddle_no")
    hs_ = rc.vorbereiten(races, runners.assign(p_handicapPoids=[600, 570, 570, 570, 570],
                                               p_poidsConditionMonte=[580, None, None, None, None]),
                         pd.DataFrame([{"race_id": rid(10, 1), "pace_ratio": 97.0}]),
                         pd.DataFrame([{"race_id": rid(10, 1), "saddle_no": 1, "vmax_kmh": 64.0},
                                       {"race_id": rid(10, 1), "saddle_no": 2, "vmax_kmh": 61.0}]), sec_s, leader)
    z1_ = hs_[(hs_["race_id"] == rid(10, 1)) & (hs_["saddle_no"] == 1)].iloc[0]
    pruefe(abs(sch_.at[1, "stride_mid_m"] - 7.2) < 1e-9 and abs(sch_.at[1, "stride_last_m"] - 6.8) < 1e-9
           and abs(sch_.at[1, "stride_change_pct"] - (6.8 / 7.2 - 1) * 100) < 1e-9
           and z1_["weight_kg"] == 58.0 and z1_["weight_assigned_kg"] == 60.0
           and abs(z1_["stride_rel"] - (7.2 - (7.2 + sch_.at[2, "stride_mid_m"]) / 2)) < 1e-9 and abs(z1_["vmax_rel"] - 1.5) < 1e-9,
           "Tracking: Schrittlänge Rennmitte (ohne Startabschnitt) / letzte 400 m, Verkürzung im Finish in %, Schritt und "
           "Vmax relativ zum Feld; Historie mit getragenem Gewicht")
    pruefe(pm_bahn_() < 50 and np.isnan(__import__("bahn_orte").km(None, (48.0, 2.0))),
           "Bahnlagen: Bahnkern (auch mit Artikel/Bindestrich) → Breite/Länge, Luftlinie in km; unbekannt → leer")
    im_rennen = hist["race_id"] == rid(10, 1)
    # abgesagtes Rennen (vergangener Tag, kein Starter mit Platz) fällt weg; Nichtankommer im gelaufenen Rennen bleibt
    races_a = pd.concat([races, pd.DataFrame([{"race_id": rid(50, 1), "hippodrome": "LA TESTE", "distance_m": 1600,
                                               "going": "Bon", "going_value": "3,0", "prize_eur": 9000,
                                               "categorie": "HANDICAP"}])], ignore_index=True)
    runners_a = pd.concat([runners, pd.DataFrame([lauf(rid(50, 1), 1, "X", "TR", None, None),
                                                  lauf(rid(50, 1), 2, "Y", "TR", None, None),
                                                  lauf(rid(100, 1), 4, "W", "AND", None, 30.0, incident="ARRETE")])],
                          ignore_index=True)
    ha = rc.vorbereiten(races_a, runners_a)
    pruefe(rid(50, 1) not in set(ha["race_id"]) and ((ha["race_id"] == rid(100, 1)) & (ha["horse"] == "W")).sum() == 1,
           "Historie: abgesagte Rennen (vergangener Tag, niemand platziert) fallen weg – kein Phantom-Lauf mit Pos 0; "
           "Nichtankommer in gelaufenen Rennen bleiben")
    # externe Läufe (performances-detaillees): PMH-Lauf kommt dazu; schon bekannter Lauf und Hürdenlauf nicht
    import pmu as pmu_
    perf = {"participants": [{"numPmu": 1, "nomCheval": "X", "coursesCourues": [
        {"date": int(pd.Timestamp("2026-08-01").timestamp() * 1000) - 7200000, "timezoneOffset": 7200000,
         "hippodrome": "AURILLAC", "nomPrix": "PRIX TEST", "discipline": "PLAT", "allocation": 7500, "distance": 2400,
         "nbParticipants": 6, "etatTerrain": "Bon souple",
         "tempsDuPremier": 161380,
         "participants": [{"itsHim": True, "nomCheval": "X", "place": {"place": 1, "statusArrivee": "PLACE"},
                           "nomJockey": "A. B", "poidsJockey": 57.0, "corde": 2},
                          {"nomCheval": "R", "place": {"place": 2, "statusArrivee": "PLACE"},
                           "distanceAvecPrecedent": {"rawValue": "5 L"}}]},
        {"date": int(pd.Timestamp(tag - timedelta(days=100)).timestamp() * 1000) - 7200000, "timezoneOffset": 7200000,
         "hippodrome": "VICHY", "nomPrix": "SCHON DA", "discipline": "PLAT", "allocation": 15000, "distance": 2000,
         "nbParticipants": 3, "participants": [{"itsHim": True, "place": {"place": 2, "statusArrivee": "PLACE"}}]},
        {"date": int(pd.Timestamp("2026-07-01").timestamp() * 1000) - 7200000, "timezoneOffset": 7200000,
         "hippodrome": "AUTEUIL", "nomPrix": "HAIES", "discipline": "HAIES", "allocation": 20000, "distance": 3500,
         "nbParticipants": 9, "participants": [{"itsHim": True, "place": {"place": 3, "statusArrivee": "PLACE"}}]},
        {"date": int(pd.Timestamp("2026-07-20").timestamp() * 1000) - 7200000, "timezoneOffset": 7200000,
         "hippodrome": "JARNAC", "nomPrix": "AB SECHS", "discipline": "PLAT", "allocation": 7000, "distance": 2500,
         "nbParticipants": 12, "participants": [{"itsHim": True, "place": {"statusArrivee": "NON_PLACE"},
                                                 "distanceAvecPrecedent": {"rawValue": "Tête"}},
                                                {"nomCheval": "S", "place": {"place": 1, "statusArrivee": "PLACE"}},
                                                {"nomCheval": "T", "place": {"place": 2, "statusArrivee": "PLACE"},
                                                 "distanceAvecPrecedent": {"rawValue": "1 L 1/2"}}]},
        {"date": int(pd.Timestamp("2026-06-01").timestamp() * 1000) - 7200000, "timezoneOffset": 7200000,
         "hippodrome": "DORTMUND", "nomPrix": "PREIS", "discipline": "PLAT", "allocation": 9000, "distance": 2000,
         "nbParticipants": 8, "participants": [{"itsHim": True, "place": {"place": 3, "statusArrivee": "PLACE"},
                                                "distanceAvecPrecedent": {"rawValue": "1 L"}},
                                               {"nomCheval": "U", "place": {"place": 1, "statusArrivee": "PLACE"}},
                                               {"nomCheval": "V", "place": {"place": 2, "statusArrivee": "PLACE"},
                                                "distanceAvecPrecedent": {"rawValue": "Encolure"}}]}]}]}
    ext_ = pd.DataFrame(pmu_.perf_zeilen(rid(10, 1), perf) * 2)            # doppelt: aus zwei Quellen
    hext = rc.vorbereiten(races, runners, extern=ext_)
    ex_ = hext[hext["extern"].eq(True)]
    ab6_ = ex_[ex_["hippodrome"] == "JARNAC"]
    do_ = ex_[ex_["hippodrome"] == "DORTMUND"]
    ex_ = ex_[ex_["hippodrome"] == "AURILLAC"]
    pruefe(len(do_) == 1 and abs(do_["lengths_behind"].iloc[0] - 1.3) < 1e-9 and do_["ausland"].iloc[0]
           and not ex_["ausland"].iloc[0] and ex_["margin"].iloc[0] == 5.0 and ex_["lengths_behind"].iloc[0] == 0
           and ex_["zeit_sieger_s"].iloc[0] == 161.38 and abs(ab6_["lengths_min"].iloc[0] - 1.7) < 1e-9
           and pd.isna(ab6_["lengths_behind"].iloc[0]) and ab6_["sieger"].iloc[0] == "S",
           "Externe Läufe: Längen zum Sieger aus den Abständen der ersten fünf (3. in Dortmund: Encolure + 1 L), Sieger "
           "mit Vorsprung, ab Platz 6 nur Untergrenze; Dortmund = Ausland, Aurillac nicht")
    pruefe(len(ab6_) == 1 and pd.isna(ab6_["finish_pos"].iloc[0]) and ab6_["pos_ab"].iloc[0] == 6
           and abs(ab6_["rel_place"].iloc[0] - (12 - 9) / 11) < 1e-9 and ab6_["won"].iloc[0] == 0,
           "Externe Läufe: im Ziel ab Platz 6 (NON_PLACE, ohne Nummer) – Pos aus der Mitte der Plätze 6 … Starterzahl, "
           "nicht als Nichtankommer")
    pruefe(len(ex_) == 1 and ex_["date"].iloc[0] == pd.Timestamp("2026-08-01") and ex_["horse_id"].iloc[0] == "X|VATER"
           and ex_["won"].iloc[0] == 1 and ex_["rel_place"].iloc[0] == 1.0 and ex_["n_runners"].iloc[0] == 6
           and abs(ex_["prize_won"].iloc[0] - 3750) < 1e-9 and pd.isna(ex_["jockey_key"].iloc[0])
           and pd.isna(ex_["odds_final"].iloc[0]) and ex_["going_pmu"].iloc[0] is not None
           and (hext["extern"].eq(False)).sum() == len(hist) and hext["extern"].eq(True).sum() == 3
           and rc.historie_beginn(hext) == hist["date"].min() and hext["date"].min() < hist["date"].min(),
           "Externe Läufe: PMH-Lauf (Aurillac) aus den Detail-Leistungen als Zeile extern=True; schon bekannter Lauf, "
           "Hürdenlauf und Doppel aus zwei Quellen fallen weg; ohne Quote und ohne Verbindungen")
    import pipeline as tp_, json as js_, tempfile as tf_
    with tf_.TemporaryDirectory() as tmp_:
        (Path(tmp_) / "parquet" / "pmu_laeufe_extern").mkdir(parents=True)
        tp_._extern_stand(Path(tmp_)).write_text(js_.dumps(["20261001", "20261002"]))     # alte Fassung: Liste
        alt_ = tp_._extern_fertig(Path(tmp_))
        tp_._extern_erledigt(Path(tmp_), "20261003")
        neu_ = tp_._extern_fertig(Path(tmp_))
    pruefe(alt_ == set() and neu_ == {"20261003"},
           "Externe Läufe nachholen: mit älterer Fassung geholte Tage gelten als offen und werden neu geholt")
    pruefe([rc.extern_art(b) for b in ("HANOVRE", "VARSOVIE", "LA MARTINIQUE", "POMPADOUR", "DORTMUND", "AURILLAC")]
           == ["Ausland", "Ausland", "Übersee", "PMH", "Ausland", "PMH"],
           "Externe Läufe: Ausland auch unter französischem Namen (Hanovre, Varsovie), Übersee (Martinique), sonst PMH")
    bahnen_ = rc.pmu_bahnen(pd.DataFrame({"hippodrome": ["DEAUVILLE-LA TOUQUES", "LA TESTE DE BUCH", "PAU",
                                                         "PARISLONGCHAMP", "LYON-PARILLY"], "extern": False}))
    arten_ = rc.extern_arten(pd.Series(["DEAUVILLE", "TESTE DE BUCH", "Pau", "AURILLAC", "HANOVRE", "LYON PARILLY",
                                        "PAUILLAC", "SAINT MALO"]), bahnen_)
    pruefe(list(arten_) == ["PMU", "PMU", "PMU", "PMH", "Ausland", "PMU", "PMH", "PMH"],
           "Externe Läufe: Bahnen des PMU-Programms in anderer Schreibweise erkannt (Deauville-La Touques ↔ Deauville, "
           "La Teste de Buch ↔ Teste de Buch) → „nachgetragen“; PMH, Ausland und ähnliche Namen bleiben")
    ml, mj = rc.musique_laeufe("5p1h1h0hAh(25)0p8p")
    pruefe(ml[:5] == [(5, "p"), (1, "h"), (1, "h"), (10, "h"), (None, "h")] and mj == 5 and len(ml) == 7
           and rc.fehlende_laeufe("1p2p8p8p8p0p0p3p7p7p", 6) == 4 and rc.fehlende_laeufe("(25)3p", 0) == 0
           and rc.fehlende_laeufe(None, 3) == 0,
           "Musique: Läufe mit Platz (0 = 10.+, Buchstabe = nicht im Ziel) und Disziplin, Läufe im laufenden Jahr; "
           "fehlende Läufe = Musique dieses Jahres − Historie dieses Jahres")
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
    global _RC_FALL
    _RC_FALL = (hist, heute_r, heute_s, tag)                  # für den Power-Modell-Test
    dx = rc.baue_daten(hext, heute_r, heute_s, tag)
    fx_ = [f for r_ in dx["races"].values() for x_ in r_["runners"] if x_["horse"] == "X" for f in x_["form_lines"]]
    pruefe(any(f["extern"] and f["course"] == "AURILLAC" and f["pos"] == 1 and f["ran"] == 6 for f in fx_)
           and any(f["extern"] and f["course"] == "JARNAC" and f["pos"] is None and f["pos_ab"] == 6 for f in fx_)
           and any(f["extern"] and f["ausland"] and f["course"] == "DORTMUND" and f["margin"] == 1.3 for f in fx_)
           and any(f["course"] == "JARNAC" and f["lb_min"] == 1.7 and f["sieger"] == "S" for f in fx_)
           and not any(f["extern"] for f in fx_ if f["course"] not in ("AURILLAC", "JARNAC", "DORTMUND")),
           "Karte: externe Läufe als Formzeilen (Aurillac 1/6, Jarnac „6.+“/12) zwischen den PMU-Läufen")
    x, y = d["races"][f"{tag:%Y%m%d}R1C1"]["runners"]
    pruefe({"verlauf", "verlauf_wert", "verlauf_pferd", "verlauf_plus"} <= set(x["form_lines"][0])
           and x["form_lines"][0]["verlauf_plus"] is False,
           "Formzeile mit Rennverlauf (zu kleines Feld: kein Urteil, kein „gegen V.“)")
    pruefe(isinstance(x.get("cgd"), str) and len(x["cgd"]) == 3 and all(len(f["cgd"]) == 3 for f in x["form_lines"])
           and "abst_pass" in x and all("abst_pass" in f for f in x["form_lines"]),
           f"Karte: CGD heute ({x['cgd']}) und je Formzeile ({', '.join(f['cgd'] for f in x['form_lines'])}), "
           f"Abstammungs-Passung heute und je Lauf")
    pruefe(not {"odds", "odds_morning"} & set(x) and x["form_lines"][0]["odds"] is not None,
           "Karte ohne aktuelle Kurse (Morgen-/Totokurs); historische Endquote in den Formzeilen bleibt")
    d90 = {k: v for k, v in x["ae"]["trainer"]["d90"].items() if k not in ("pos_idx", "prev")}
    pruefe(d90 == {"runs": 2, "wins": 1, "places": 2, "exp": 2.0, "ae": 1.0, "ae_win": 1.33,
                                         "epr": round((13500 + 5130) / 2), "epr_idx": None,
                                         "pl_exp": 2, "n_exp": 2},
           "A/E Platz 90 Tage: 2 Starter -> beide sicher platziert (erwartet 2, A/E 1,00); A/E Sieg 1,33 zum Vergleich")
    rf = x["pref_ref"]["trainer"]["course"]
    zl = d["pref_alle"][rf[0]][rf[1]]
    hz = [z for z in zl if z[0] == rf[2]]
    pc = x["pref"]["trainer"]["course"]
    pruefe(rf[0] == "trainer_course" and len(hz) == 1 and hz[0][1:] == [pc["runs"], pc["wins"], pc["places"], pc["ae"], pc["exp"]]
           and [z[1] for z in zl] == sorted((z[1] for z in zl), reverse=True)
           and x["pref_ref"]["jockey"]["horse"][2] == x["horse"].title(),
           f"Vorlieben-Overlay: alle Bahnen des Trainers ({len(zl)}), heutige wie in der Vorliebe, nach Läufen sortiert")
    rs = x["pref_ref"]["sire"]["distance"]
    zs = [z for z in d["pref_alle"][rs[0]][rs[1]] if z[0] == rs[2]][0]
    ab = x["abst"]["sire"]
    rr_ = d["races"][f"{tag:%Y%m%d}R1C1"]
    hs_ = hist[(hist["date"] < pd.Timestamp(tag)) & (hist["sire_key"] == x["sire"])]
    pruefe(len(zs) == 6 and ab and {"dist", "boden", "reife"} <= set(ab)
           and ab["dist"]["heute"] == rc.abst_dist_kat(rr_["distance"])
           and sum(z[1] for z in ab["dist"]["zeilen"]) == int(hs_["distance_m"].notna().sum())
           and all(len(z) == 8 for dim in ("dist", "boden", "belag", "reife") if ab.get(dim) for z in ab[dim]["zeilen"])
           and x["ae"]["pedigree"]["sire"]["pos_idx"] == round(100 * hs_["rel_place"].fillna(0).where(hs_["n_runners"] > 1).mean()
                                                               / hist.loc[hist["date"] < pd.Timestamp(tag), "rel_place"].fillna(0)
                                                               .where(hist["n_runners"] > 1).mean()),
           f"Abstammungsprofil in der Karte: Vater mit Distanz/Boden/Reife ({ab['runs']} Läufe), heutige Kategorie markiert, "
           f"Pos+ der Abstammung {x['ae']['pedigree']['sire']['pos_idx']}; "
           f"Vorlieben-Overlay ohne Zusatzspalten")
    m90 = x["ae"]["trainer"]["d90"]
    hv = hist[hist["date"] < pd.Timestamp(tag)]
    rp = hv["rel_place"].fillna(0).where(hv["n_runners"] > 1)
    tk_ = hv.loc[hv["horse"].str.upper() == x["horse"].upper(), "trainer_key"].iloc[0]
    def _pi(von, bis):
        f_ = (hv["date"] >= pd.Timestamp(tag) - timedelta(days=von)) & (hv["date"] < pd.Timestamp(tag) - timedelta(days=bis))
        return round(100 * rp[f_ & (hv["trainer_key"] == tk_)].mean() / rp[f_].mean())
    pruefe(m90["pos_idx"] == _pi(90, 0) and m90["prev"] is not None and m90["prev"]["pos_idx"] == _pi(180, 90)
           and m90["prev"]["runs"] == int(((hv["trainer_key"] == tk_) & (hv["date"] >= pd.Timestamp(tag) - timedelta(days=180))
                                           & (hv["date"] < pd.Timestamp(tag) - timedelta(days=90))).sum()),
           f"Matrix: Pos+ (Ø Platzanteil, 100 = Ø aller Läufe im Fenster) {m90['pos_idx']}, Vorperiode 91–180 Tage {m90['prev']}")
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
    lpm = lambda *w: float(np.mean(np.log1p(w)))           # Ø log(1 + Preisgeld) je Lauf
    pruefe(hx_a["cls_epr"] == (2850 + 7500) / 2 and np.isnan(hist.loc[hist["race_id"] == rid(100, 1), "cls_epr"]).all()
           and hx_a["cls_epr_kl"] == round(lpm(2850, 7500), 3) and bool(hx_a["epr_eigen"])
           and np.isnan(hist.loc[hist["race_id"] == rid(100, 1), "cls_epr_kl"]).all(),
           "Klasse früherer Rennen: angezeigt Ø Gewinn je Lauf der Teilnehmer (365 Tage davor, X 2850, Y 7500); "
           "Basis für €/L+ Ø log-Preisgeld je Lauf, Historie unter einem Jahr: 4-Jährige zählen als erfahren")
    kl = d["races"][f"{tag:%Y%m%d}R1C1"]["class"]
    pruefe(kl["epr"] == round((8175 + (7500 + 5130) / 2) / 2) and kl["epr_n"] == 2
           and kl["epr_base"] == round((lpm(13500, 2850) + lpm(5130, 7500)) / 2, 3) and kl["epr_own"] == 2,
           "Klasse heute: angezeigt Ø Gewinn je Lauf (365 Tage) der Starter = (8175 + 6315) / 2, Basis €/L+ "
           "Ø log-Preisgeld je Lauf je Pferd, dann Ø der Starter")
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
    h2 = hist.copy()
    sk2 = h2.loc[h2["horse"].str.upper() == x["horse"].upper(), "sire_key"].iloc[0]
    dg2 = rc.rtr_arr.distance_group(d["races"][f"{tag:%Y%m%d}R1C1"]["distance"])
    i2 = h2[(h2["sire_key"] == sk2) & (h2["date"] < pd.Timestamp(tag)) & (h2["dist_group"] == dg2)].index[:1]
    h2.loc[i2, "age"] = 2
    p2 = rc.baue_daten(h2, heute_r, heute_s, tag)["races"][f"{tag:%Y%m%d}R1C1"]["runners"][0]["pref"]
    pruefe(len(i2) == 1 and p2["sire"]["distance"]["runs"] == pr["sire"]["distance"]["runs"] - 1
           and p2["sire"]["age"]["runs"] == pr["sire"]["age"]["runs"],
           "Vater nach Distanz ohne 2-Jährige (ein Lauf als 2-Jähriger fällt bei der Distanz weg, nicht beim Alter)")
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
    soll_n = (0.5 * 3 * np.log1p(1200) / 7 + 0.3 * 2 * np.log1p(1200) / 6) / 0.8
    pruefe(bool(an.loc["A", "epr_eigen"]) and abs(an.loc["A", "epr_kl"] - np.log1p(500)) < 1e-9
           and not an.loc["N", "epr_eigen"] and abs(an.loc["N", "epr_kl"] - soll_n) < 1e-9
           and bool(an.loc["L", "epr_eigen"]) and abs(an.loc["L", "epr_kl"] - lpm(900, 300)) < 1e-9
           and (kz.loc[(kz["horse_id"] == "A") & (kz["date"] == ts_("2026-03-01")), "epr_kl"] == 0).all(),
           "Basis €/L+ je Pferd = Ø log(1 + Preisgeld) je Lauf: ab einem Jahr seit dem ersten Start immer das eigene "
           "(ohne Lauf im letzten Jahr über alle früheren Läufe), davor Trainer 50 % / Besitzer 30 % aus Läufen ihrer "
           "Pferde im ersten Jahr (A erfahren zählt nicht mit; Züchter fehlt -> hochgerechnet), erst ab 5 Läufen")
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
    ha = hist.copy()
    ha["arr"] = np.where(ha["race_id"] == rid(10, 1), 0.0, 20.0)
    ha["ausgeritten"] = ha["race_id"] == rid(10, 1)
    xa = rc.baue_daten(ha, heute_r, heute_s, tag)["races"][f"{tag:%Y%m%d}R1C1"]["runners"][0]
    pruefe(xa["arr"]["avg"] == 20.0 and xa["arr"]["runs"] == 1,
           "ARR-Kachel ohne ausgerittene Läufe (letzter Lauf ARR 0 und weit geschlagen zählt nicht in den Schnitt)")
    fa = {f["race_id"]: f for f in xa["form_lines"]}
    pruefe(xa["kpi"] and rid(10, 1) not in {k[7] for k in xa["kpi"]}
           and all((tag - date.fromisoformat(k[0])).days <= rc.KPI_TAGE for k in xa["kpi"])
           and all(k[4] == fa[k[7]]["arr_adj"] and k[5] == fa[k[7]]["tr_heute"]
                   and k[8] == fa[k[7]]["cls_val_idx"] and k[9] == fa[k[7]]["cls_epr_idx"] for k in xa["kpi"] if k[7] in fa)
           and xa["kpi"] == sorted(xa["kpi"], key=lambda k: k[0], reverse=True),
           f"Vergleichs-Overlay: {len(xa['kpi'])} Läufe der letzten 365 Tage ohne ausgerittene, ARR/TR wie in der Formzeile bereinigt, Klasse Val+/€/L+ wie in der Formzeile")
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
           and kl["epr_idx"] == round(100 * kl["epr_base"] / round(lpm(2850, 7500), 3))
           and abs(d["params"]["pop"]["rennen_epr"] - lpm(2850, 7500)) < 0.05,
           f"Rennstärke €/L+: Ø log-Preisgeld je Lauf der Teilnehmer ÷ Ø aller früheren Rennen (heute {kl['epr_idx']}); "
           "Formzeile zeigt weiter den einfachen Ø")
    pruefe(f["cls_val_idx"] == 100 and d["params"]["pop"]["rennen_val"] == 40.0,
           "Val+: Ø Valeur der Teilnehmer ÷ Ø aller früheren Rennen (einziges Rennen mit Valeur -> 100)")
    pruefe(x["duels"][0]["race_id"] in {f_["race_id"] for f_ in x["form_lines"]},
           "Direktes Duell mit race_id der eigenen Formzeile (Knopf „Heutige Gegner“ in dieser Zeile)")
    pruefe(len(x["duels"]) == 1 and x["duels"][0]["date"] == str(tag - timedelta(days=10)),
           "Direkte Duelle: nur ≤ 180 Tage, ±200 m zu heute, Boden innerhalb einer Stufe (Duell über 2000 m Lourd fällt weg)")
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
    ind = rc._indirekte_duelle(ib, {"H": {"weight": 60.0, "no": 1}, "R": {"weight": 56.0, "no": 2}}, "Bon", 1600, T0)
    e_h, e_r = ind["H"]["rivals"][0], ind["R"]["rivals"][0]
    pruefe(e_h["rival"] == "R" and e_h["n"] == 1 and e_h["common"] == ["C"] and e_h["then_kg"] == 3.4
           and e_h["w_today"] == 4.0 and e_h["exp_kg"] == -0.6 and e_h["exp_l"] == -0.5
           and ind["H"]["behind"] == 1 and e_r["exp_kg"] == 0.6,
           "Indirekte Duelle: über gemeinsamen Gegner (2 L × 1,2 + 2 kg = 4,4 vs 1 L × 1,0 = 1,0 -> 3,4 kg), "
           "heute 4 kg mehr -> 0,6 kg / 0,5 L hinten; PSF-Rennen und Rennen > 180 Tage zählen nicht")
    pruefe(e_h["days"] == 25, "Indirektes Duell: Alter = Ø der beiden Vergleichsrennen (30 und 20 Tage)")
    rA, rB = (hi.loc[hi["horse_id"] == h_, "race_id"].iloc[0] for h_ in ("H", "R"))
    pruefe(e_h["via"] == [[rA, "C", 3.4, str(hi.loc[hi["race_id"] == rB, "date"].iloc[0].date()), rB]]
           and e_r["via"][0][0] == rB and e_r["via"][0][4] == rA,
           "Indirektes Duell: je Vergleich eigenes Rennen, gemeinsamer Gegner, Differenz und Rennen des Gegners (für die Formzeilen)")
    hz = "2026-10-09"
    dz = lambda no, liste, ind=None: {"no": no, "nr": False, "indirect": ind,
                                      "duels": [{"rival_no": j, "exp_l": m, "date": d_} for j, m, d_ in liste]}
    sz = [dz(1, [(2, 2.0, hz)]), dz(2, [(1, -2.0, hz), (3, 1.0, hz)]), dz(3, [(2, -1.0, hz)]), dz(4, []),
          {"no": 5, "nr": True, "duels": [], "indirect": None}]
    rz = rc.duell_rangfolge(sz, hz)
    pruefe(rz == [[1, 2, 3]] and [x["duel_rank"]["rank"] for x in sz[:3]] == [1, 2, 3] and sz[3]["duel_rank"] is None
           and sz[0]["duel_rank"]["score_l"] - sz[1]["duel_rank"]["score_l"] == 2.0 and sz[1]["duel_rank"]["n_direct"] == 2,
           "Duell-Rangfolge: A schlägt B um 2 L, B schlägt C um 1 L -> A 1., B 2., C 3. (Abstände bleiben erhalten); "
           "ohne Duell kein Rang")
    alt_ = "2026-08-10"                                    # 60 Tage alt: halbes Gewicht
    sw = [dz(1, [(2, 3.0, alt_)], {"rivals": [{"rival_no": 2, "exp_l": -3.0, "days": 0}]}), dz(2, [])]
    rc.duell_rangfolge(sw, hz)
    sg = [dz(1, [(2, 9.0, hz)]), dz(2, []), dz(3, [(4, 1.0, hz)]), dz(4, [])]
    rg = rc.duell_rangfolge(sg, hz)
    pruefe(sw[0]["duel_rank"]["score_l"] == 0.0 and sw[0]["duel_rank"]["weight"] == 2.0
           and sg[0]["duel_rank"]["score_l"] == 2.5 and rg == [[1, 2], [3, 4]] and sg[2]["duel_rank"]["group"] == 2,
           "Duell-Rangfolge: direktes Duell vor 60 Tagen (2 × ½) wiegt wie ein heutiges indirektes (1); "
           "Abstand auf 5 L begrenzt; Pferde ohne Verbindung in getrennten Gruppen")
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
    rr["prono"] = {"text": "GEHEIMTEXT", "consensus": [2, 1]}
    ex, mk = ce.export(dd), ce.export_markt(dd)
    eo, ef, mo = ex["races"][rr["race_id"]], ex["races"]["FERTIG"], mk["races"][rr["race_id"]]
    txt = json.dumps(ex, ensure_ascii=False)
    pruefe(eo["offen"] and not ef["offen"] and len(ef["runners"]) == 2 and eo["nr"] == [9]
           and [x_["no"] for x_ in eo["nichtstarter"]] == [9]
           and [x_["no"] for x_ in eo["runners"]] == eo["vorgerechnet"]["reihenfolge"] == [1, 2]
           and "odds_morning" not in txt and '"silks"' not in txt and "base64" not in txt
           and all("odds" not in x_ for x_ in eo["runners"])
           and all("rivals" not in f_ and "rivals_nah" in f_ and "rivals_stat" in f_
                   and not (set(f_) & ce.OHNE_FORMZEILE) for x_ in eo["runners"] for f_ in x_["form_lines"]),
           "Claude-Version blind: Starter nach Startnummer (Prognose hätte Nr. 2 vorne), ohne Kurse/Trikots; Formzeilen mit nächsten Gegnern statt "
           "voller Liste, ohne Zwischenwerte; Nichtstarter und gelaufene Rennen vollständig dabei")
    txt_r = json.dumps(ex["races"], ensure_ascii=False)                  # Renndaten (ohne den Hinweistext)
    pruefe('"prono"' not in txt_r and "p_prog" not in txt_r and "GEHEIMTEXT" not in txt_r and "cote" not in txt_r
           and "marge" not in eo["vorgerechnet"] and "konsens" not in txt_r,
           "Claude-Version blind: keine Prognose, cote probable, p_prog, Marge, Tipps, Konsens, Cribles oder "
           "Rennkommentar – auch die Reihenfolge verrät die Prognose nicht")
    pruefe([x_["no"] for x_ in mo["runners"]] == mo["vorgerechnet"]["reihenfolge"] == [2, 1]
           and abs(sum(x_["p_prog"] for x_ in mo["runners"]) - 1) < 1e-3
           and mo["runners"][0]["p_prog"] < mo["runners"][1]["p_prog"]       # Rang 1 hier mit 4,0 > 3,0
           and mo["vorgerechnet"]["marge"] == round(1 / 3 + 1 / 4, 3) and mo["prono"]["text"] == "GEHEIMTEXT"
           and mo["nr"] == [9] and ce.markt_pfad(Path("x/racecard_20261011_claude.json")).name == "racecard_20261011_markt.json",
           "Marktdatei: Prognose-Reihenfolge, p_prog (Potenzmethode), Marge, Rennkommentar und Tipps je Rennen")

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
    ausgelassen = (".runners[].silks", ".runners[].odds", ".runners[].odds_morning", ".runners[].kpi", ".runners[].pref_ref", ".runners[].power",
                   *(f".form_lines[].{k}" for k in ce.OHNE_FORMZEILE), *(f".{k}" for k in ce.OHNE_AE),
                   *(f".params.{k}" for k in ce.OHNE_PARAMS),
                   *(f".duels[].{k}" for k in ce.OHNE_DUELL), *(f".rivals[].{k}" for k in ce.OHNE_INDIREKT))
    oben_weg = {f".{k}" for k in ce.OHNE_OBEN}
    weg = lambda q: (q.endswith(ausgelassen) or any(o + "." in q or o + "[]" in q for o in ausgelassen)  # + Unterfelder
                     or any(q == o or q.startswith(o + ".") or q.startswith(o + "[") for o in oben_weg))
    fehlend = sorted({_norm(q) for q in _pfade(dd)} - {_norm(q) for q in _pfade(ex) | _pfade(mk)}
                     - {q for q in {_norm(q) for q in _pfade(dd)} if weg(q)})
    pruefe(not fehlend, "Claude-Version (blind + Markt) vollständig: jedes Feld der Race Card außer "
           "Trikots/Kursen/Gegnerliste/Zwischenwerten"
           + (f" – fehlt: {fehlend[:5]}" if fehlend else ""))
    pfade_ex = {_norm(q) for q in _pfade(ex) | _pfade(mk)}
    pruefe("pref_alle" in dd and not any(q.startswith(".pref_alle") or q.endswith((".kpi", ".pref_ref", ".pos_idx"))
                                         or ".prev." in q or q.startswith(".params.kpi") for q in pfade_ex
                                         if ".vergleich_365." not in q and ".pedigree." not in q)
           and any(q.endswith(".pos_idx") for q in {_norm(q) for q in _pfade(dd)}),
           "Claude-Version ohne Overlay-Daten der Karte (kpi, pref_ref, pref_alle, Matrix pos_idx/prev, kpi-Parameter)")
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
    pruefe(all(k in x0 for k in ("form_lines", "pref", "ae", "career", "rating_adj", "duels", "starts",
                                 "days", "changes", "badges", "hcp_mark", "tr", "arr", "rtr", "summary", "luecke"))
           and all(k in eo for k in ("pace", "bias", "class", "going_source", "going_assumed", "declared"))
           and all(k in skill for k in ("_claude.json", "_markt.json", "p_prog", "p_blind", "Startnummer",
                                        "vorgerechnet", "rivals_nah", "luecke")),
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
