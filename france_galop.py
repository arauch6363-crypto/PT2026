"""
Tracking-PDFs bei France Galop suchen – ausgehend von den PMU-Rennen.

Ablauf je Rennen: aus Datum + France-Galop-Bahncode + Rennnummer ergibt sich
der Dateiname   <JJJJMMTT><COD><NN>_last_times_fr.pdf .

Wichtig (und der Grund für den ganzen Aufwand hier):

* Tracking ist eine Eigenschaft von **Renntag + Rennen**, nicht von der Bahn.
  Eine Bahn kann heute Tracking haben und morgen nicht. Deshalb wird nie
  gespeichert "Bahn X hat kein Tracking". Gespeichert wird nur, welcher
  France-Galop-Code zu welcher Bahn gehört (positives Wissen) – und für jedes
  einzelne Rennen, ob an diesem Tag ein PDF gefunden wurde.

* Eine Bahn kann Flach- und Hindernisrennen am selben Tag austragen. Ein
  fehlendes PDF für ein Rennen sagt deshalb nichts über die anderen Rennen
  desselben Tages aus – jedes Rennen wird einzeln geprüft.

* Beim Suchen eines unbekannten Bahncodes wird der Treffer gegengeprüft: im
  PDF-Kopf steht der Bahnname. Nur wenn der zum PMU-Namen passt, wird der Code
  gelernt. Sonst würde z. B. CHATEAUBRIANT den Code "CHA" von CHANTILLY erben.
"""
from __future__ import annotations

import tempfile
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

import parse_tracking as pt
import pmu
from pmu import norm

TRACK_URL = "https://www7.france-galop.com/Casaques/Tracking//{name}.pdf"
DATEI = "{ymd}{code}{no:02d}_last_times_fr"
HEADERS = {"User-Agent": "Mozilla/5.0 (private racing analysis)"}

# Aus echten Tracking-Dateinamen bestätigt – diese Codes sind gesichert.
SEED_CODES = {
    "DIEPPE": "DIE",
    "CHANTILLY": "CHA",
    "PARISLONGCHAMP": "LON",
    "DEAUVILLE": "DEA",
    "LE LION D ANGERS": "LLA",
    "NANCY": "BRA",
}

# Zusätzliche Kandidaten für Bahnen, deren Code sich nicht aus dem Namen ergibt.
# Das sind nur Vorschläge zum Ausprobieren – gelernt wird ein Code erst nach
# erfolgreicher Gegenprüfung des Bahnnamens im PDF.
HINWEISE = {
    "SAINT CLOUD": ["CLO", "STC", "SCL"],
    "MAISONS LAFFITTE": ["MLA", "LAF", "MAI"],
    "LONGCHAMP": ["LON"],
    "CAGNES SUR MER": ["CAG", "CSM"],
    "MARSEILLE BORELY": ["BOR", "MBO"],
    "MARSEILLE VIVAUX": ["VIV", "MVI"],
    "BORDEAUX LE BOUSCAT": ["BOU", "LEB", "BLB"],
    "LYON PARILLY": ["PAR", "LYP"],
    "LYON LA SOIE": ["SOI", "LYS"],
    "LA TESTE DE BUCH": ["TES", "LTB"],
    "LE CROISE LAROCHE": ["CRO", "LCL"],
    "CROISE LAROCHE": ["CRO", "LCL"],
    "MANS": ["MAN", "LEM"],
    "SABLES D OLONNE": ["SAO", "LSO"],
    "CLAIREFONTAINE": ["CLA", "CLF"],
    "MONT DE MARSAN": ["MDM", "MAR"],
    "LA PALMYRE ROYAN": ["PAL", "ROY"],
    "ROYAN LA PALMYRE": ["PAL", "ROY"],
    "SABLE SUR SARTHE": ["SAB", "SSS"],
    "SAINT MALO": ["MAL", "STM"],
    "CLERMONT FERRAND": ["CLF", "CLE"],
    "LES SABLES D OLONNE": ["SAO", "LSO"],
    "CHATEAUBRIANT": ["CTB", "CHB"],
    "FONTAINEBLEAU": ["FON", "FBL"],
    "SAINT BRIEUC": ["BRI", "STB"],
    "MOULINS": ["MOU"],
    "PORNICHET LA BAULE": ["POR", "PLB"],
}

STOPWORDS = {"LE", "LA", "LES", "DE", "DU", "DES", "D", "L", "SUR", "EN", "MIDI", "SOIR", "HIPPODROME"}

# Wie hartnäckig wird nach einem noch unbekannten Bahncode gesucht?
ERSTE_VERSUCHE = 12      # so oft wird an verschiedenen Renntagen ohne Pause gesucht
WIEDER_NACH_TAGEN = 21   # danach nur noch alle X Tage erneut (die Bahn kann später Tracking bekommen)


# --------------------------------------------------------------------------
# Codetabelle (wächst mit, enthält nur bestätigtes Wissen)
# --------------------------------------------------------------------------
SPALTEN = ["hippodrome", "pmu_code", "fg_code", "gefunden_am", "versuche", "letzter_versuch", "quelle"]


class CodeStore:
    """track_codes.csv: Bahnname -> France-Galop-Code.

    Es wird bewusst **kein** "hat kein Tracking" gespeichert, nur Zähler für die
    bisherigen Suchversuche, damit unbekannte Bahnen nicht endlos abgefragt werden,
    aber auch nie dauerhaft ausgeschlossen sind.
    """

    def __init__(self, base: Path):
        self.path = Path(base) / "track_codes.csv"
        if self.path.exists():
            df = pd.read_csv(self.path, dtype=str).fillna("")
            for s in SPALTEN:
                if s not in df.columns:
                    df[s] = ""
            self.df = self._aufraeumen(df[SPALTEN].copy())
        else:
            self.df = pd.DataFrame([{"hippodrome": h, "pmu_code": "", "fg_code": c, "gefunden_am": "",
                                     "versuche": "0", "letzter_versuch": "", "quelle": "seed"}
                                    for h, c in SEED_CODES.items()], columns=SPALTEN)

    @staticmethod
    def _aufraeumen(df: pd.DataFrame) -> pd.DataFrame:
        """Alte Tabellen instand setzen: Namen vereinheitlichen und Dubletten zusammenführen,
        die durch die früheren Schreibweisen entstanden sind (z. B. "TOULOUSE LA CEPIERE"
        und "LA CEPIERE"). Zeilen mit bekanntem Code haben Vorrang."""
        df["hippodrome"] = df["hippodrome"].map(norm)
        df["pmu_code"] = df["pmu_code"].map(lambda x: norm(x) if x else "")
        df = df.sort_values("fg_code", ascending=False, kind="stable")
        mit_code = df[df["pmu_code"] != ""].drop_duplicates("pmu_code", keep="first")
        ohne_code = df[df["pmu_code"] == ""]
        ohne_code = ohne_code[~ohne_code["hippodrome"].isin(mit_code["hippodrome"])]
        df = pd.concat([mit_code, ohne_code], ignore_index=True)
        return df.drop_duplicates("hippodrome", keep="first").reset_index(drop=True)

    # -- lesen -------------------------------------------------------------
    def _zeile(self, name: str = "", pmu_code: str = ""):
        """Zeile zu einer Bahn finden.

        Schlüssel ist der PMU-Bahncode: das Programm nennt dieselbe Bahn je nach Feld
        "HIPPODROME DE TOULOUSE LA CEPIERE" oder "LA CEPIERE", der Code bleibt derselbe.
        Nur wenn kein Code vorliegt (z. B. bei den mitgelieferten Bahnen), wird über den
        vereinheitlichten Namen gesucht – und dann nur exakt: DEAUVILLE CLAIREFONTAINE
        ist eine andere Bahn als DEAUVILLE, ebenso LYON PARILLY und LYON LA SOIE."""
        if pmu_code:
            c = norm(pmu_code)
            for i, x in enumerate(self.df["pmu_code"]):
                if x and norm(x) == c:
                    return i
        if name:
            n = norm(name)
            for i, h in enumerate(self.df["hippodrome"]):
                if norm(h) == n:
                    return i
        return None

    def code(self, name: str, pmu_code: str = "") -> str:
        i = self._zeile(name, pmu_code)
        return self.df.at[i, "fg_code"] if i is not None else ""

    def notiere(self, name: str, pmu_code: str) -> int:
        """Bahn anlegen bzw. den PMU-Code nachtragen, ohne Bekanntes zu überschreiben."""
        i = self._zeile(name, pmu_code)
        if i is None:
            i = self._neu(name)
        if pmu_code and not self.df.at[i, "pmu_code"]:
            self.df.at[i, "pmu_code"] = norm(pmu_code)
        if not self.df.at[i, "hippodrome"]:
            self.df.at[i, "hippodrome"] = norm(name)
        return i

    def belegte_codes(self, ausser: str = "", pmu_code: str = "") -> set[str]:
        """Codes, die bereits einer anderen Bahn gehören – die dürfen nicht doppelt vergeben werden.
        Die eigene Zeile wird über den Zeilentreffer ausgeschlossen, nicht über Namensgleichheit:
        sonst sperrt sich eine Bahn bei abweichender Schreibweise ihren eigenen Code."""
        eigen = self._zeile(ausser, pmu_code) if (ausser or pmu_code) else None
        return {c for i, c in enumerate(self.df["fg_code"]) if c and i != eigen}

    def soll_suchen(self, name: str, tag: date, *, pmu_code: str = "", force: bool = False) -> bool:
        """Lohnt sich heute ein neuer Code-Suchlauf für diese Bahn?"""
        i = self._zeile(name, pmu_code)
        if i is None:
            return True
        if self.df.at[i, "fg_code"]:
            return False
        if force:
            return True
        versuche = int(self.df.at[i, "versuche"] or 0)
        if versuche < ERSTE_VERSUCHE:
            return True
        letzter = self.df.at[i, "letzter_versuch"]
        if not letzter:
            return True
        try:
            alter = (tag - datetime.strptime(letzter, "%Y-%m-%d").date()).days
        except ValueError:
            return True
        return abs(alter) >= WIEDER_NACH_TAGEN

    # -- schreiben ---------------------------------------------------------
    def _neu(self, name: str) -> int:
        self.df.loc[len(self.df)] = [norm(name), "", "", "", "0", "", ""]
        return len(self.df) - 1

    def treffer(self, name: str, pmu_code: str, fg_code: str, tag: date, quelle: str = "gefunden"):
        i = self.notiere(name, pmu_code)
        self.df.loc[i, ["fg_code", "gefunden_am", "quelle"]] = [fg_code, tag.isoformat(), quelle]

    def fehlversuch(self, name: str, pmu_code: str, tag: date):
        i = self.notiere(name, pmu_code)
        self.df.loc[i, "versuche"] = str(int(self.df.at[i, "versuche"] or 0) + 1)
        self.df.loc[i, "letzter_versuch"] = tag.isoformat()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.df.sort_values("hippodrome").to_csv(self.path, index=False)


# --------------------------------------------------------------------------
# Kandidaten für einen unbekannten Code
# --------------------------------------------------------------------------
def kandidaten(name: str, pmu_code: str = "", *, verboten: set[str] = frozenset()) -> list[str]:
    n = norm(name)
    woerter = [w for w in n.split() if w not in STOPWORDS]
    alle = n.split()
    c: list[str] = []
    if pmu_code:
        c.append(norm(pmu_code)[:3])
    c += HINWEISE.get(n, [])
    c += [w[:3] for w in woerter if len(w) >= 3]
    if len(woerter) >= 2:
        c.append("".join(w[0] for w in woerter)[:3])
        c.append(woerter[0][:2] + woerter[1][0])
    if len(alle) >= 2:
        c.append("".join(w[0] for w in alle)[:3])
    for w in woerter:
        if len(w) > 6:                       # PARISLONGCHAMP -> LON, NGC, GCH …
            c += [w[i:i + 3] for i in (5, 4, 3, 6)]
    out, gesehen = [], set()
    for x in c:
        x = (x or "").strip().upper()
        if len(x) == 3 and x.isalpha() and x not in gesehen and x not in verboten:
            gesehen.add(x)
            out.append(x)
    return out


# --------------------------------------------------------------------------
# PDF holen und gegenprüfen
# --------------------------------------------------------------------------
def dateiname(ymd: str, code: str, no: int) -> str:
    return DATEI.format(ymd=ymd, code=code, no=no)


def hole_pdf(session: requests.Session, name: str) -> bytes | None:
    """Gibt den PDF-Inhalt zurück, sonst None (fehlende PDFs liefern HTML oder 404)."""
    try:
        r = session.get(TRACK_URL.format(name=name), headers=HEADERS, timeout=30)
    except requests.RequestException:
        return None
    if r.ok and r.content[:4] == b"%PDF" and len(r.content) > 1000:
        return r.content
    return None


def _kopf(pdf: bytes) -> dict:
    """Kopfzeile der ersten PDF-Seite lesen (Bahn, Rennnummer, Distanz, Datum)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf)
        tmp = Path(f.name)
    try:
        for engine in ("plumber", "pypdf"):
            try:
                texte, _ = pt.read_pages(tmp, engine)
            except Exception:
                continue
            if texte:
                h = pt.parse_header(texte[0])
                if h.get("track"):
                    return h
        return {}
    finally:
        tmp.unlink(missing_ok=True)


# Wörter, die in vielen Bahnnamen vorkommen und deshalb keinen Treffer begründen dürfen
GENERISCH = {"HIPPODROME", "HIPP", "COURSES", "SOCIETE", "RACECOURSE", "SAINT", "NOTRE", "GRAND"}


def passt_bahn(pdf: bytes, hippodrome: str) -> bool | None:
    """True = Bahnname im PDF passt, False = passt nicht, None = nicht lesbar."""
    track = _kopf(pdf).get("track")
    if not track:
        return None
    a, b = norm(track), norm(hippodrome)
    if not a or not b:
        return None
    if a == b or a.startswith(b + " ") or b.startswith(a + " "):
        return True
    ta = {w for w in a.split() if len(w) >= 4 and w not in GENERISCH}
    tb = {w for w in b.split() if len(w) >= 4 and w not in GENERISCH}
    if not ta or not tb:
        return None                      # nichts Aussagekräftiges zum Vergleichen
    return bool(ta & tb)


# --------------------------------------------------------------------------
# Code einer Bahn suchen
# --------------------------------------------------------------------------
def suche_code(m: dict, tag: date, session: requests.Session, store: CodeStore, pdf_dir: Path, *,
               pause: float = 0.3, max_kandidaten: int = 8, rennen_je_kandidat: int = 3,
               tabu: set[str] = frozenset(), log=print) -> tuple[str | None, dict]:
    """Unbekannten France-Galop-Code über Probe-Downloads ermitteln.

    Rückgabe: (code oder None, {dateiname: pdf-bytes} der dabei gefundenen PDFs).
    Ein Treffer zählt nur, wenn der Bahnname im PDF-Kopf passt.
    """
    ymd = tag.strftime("%Y%m%d")
    verboten = store.belegte_codes(ausser=m["hippodrome"], pmu_code=m["pmu_code"]) | set(tabu)
    gefunden: dict[str, bytes] = {}
    for i, cand in enumerate(kandidaten(m["hippodrome"], m["pmu_code"], verboten=verboten)[:max_kandidaten]):
        rennen = m["races"] if i == 0 else m["races"][:rennen_je_kandidat]
        for r in rennen:
            name = dateiname(ymd, cand, r)
            pdf = hole_pdf(session, name)
            time.sleep(pause)
            if not pdf:
                continue
            ok = passt_bahn(pdf, m["hippodrome"])
            if ok is False:
                log(f"    Code {cand} gehört zu einer anderen Bahn – verworfen")
                break                      # dieser Kandidat ist belegt, nächster
            if ok is None:
                log(f"    Code {cand}: PDF-Kopf nicht lesbar, Code wird trotzdem übernommen")
            (pdf_dir / f"{name}.pdf").write_bytes(pdf)
            gefunden[name] = pdf
            store.treffer(m["hippodrome"], m["pmu_code"], cand, tag)
            log(f"    Bahncode gelernt: {m['hippodrome']} = {cand}")
            return cand, gefunden
    store.fehlversuch(m["hippodrome"], m["pmu_code"], tag)
    return None, gefunden


# --------------------------------------------------------------------------
# Tracking für die Rennen eines Tages
# --------------------------------------------------------------------------
def tracking_fuer_tag(tag: date, meets: list[dict], session: requests.Session, store: CodeStore,
                      pdf_dir: Path, *, pause: float = 0.3, code_suche: bool = True,
                      log=print) -> list[dict]:
    """Prüft für jedes Rennen des Tages einzeln, ob es ein Tracking-PDF gibt.

    Abgefragt wird jedes Rennen, dessen PDF noch nicht auf der Platte liegt – damit
    werden nachträglich veröffentlichte PDFs bei einem späteren Lauf von selbst
    gefunden, ohne dass etwas doppelt geladen wird.
    Rückgabe: eine Statuszeile je Rennen.
    """
    ymd = tag.strftime("%Y%m%d")
    pdf_dir.mkdir(parents=True, exist_ok=True)
    tabu: set[str] = set()                     # Codes, die heute schon einer anderen Bahn gehören
    for m in meets:
        c = store.code(m["hippodrome"], m["pmu_code"])
        if c:
            tabu.add(c)

    status: list[dict] = []
    for m in meets:
        store.notiere(m["hippodrome"], m["pmu_code"])      # Bahn bekannt machen / PMU-Code nachtragen
        code = store.code(m["hippodrome"], m["pmu_code"])
        vorab: dict[str, bytes] = {}
        if not code and code_suche and store.soll_suchen(m["hippodrome"], tag, pmu_code=m["pmu_code"]):
            log(f"  {m['hippodrome']}: Bahncode unbekannt – suche …")
            code, vorab = suche_code(m, tag, session, store, pdf_dir, pause=pause, tabu=tabu, log=log)
        if code:
            tabu.add(code)

        for c in m["courses"]:
            r = pmu.race_no(c)
            rid = pmu.race_id(tag, m, c)
            zeile = {"race_id": rid, "date": ymd, "hippodrome": m["hippodrome"],
                     "reunion": m["reunion"], "race_no": r, "fg_code": code or "",
                     "specialite": c.get("specialite"),
                     "pdf": "", "tracking": False, "geprueft_am": datetime.now().isoformat(timespec="seconds")}
            if not code:
                zeile["grund"] = "Bahncode unbekannt"
                status.append(zeile)
                continue
            name = dateiname(ymd, code, r)
            ziel = pdf_dir / f"{name}.pdf"
            zeile["pdf"] = ziel.name
            if ziel.exists() or name in vorab:
                zeile["tracking"] = True
                status.append(zeile)
                continue
            pdf = hole_pdf(session, name)
            time.sleep(pause)
            if pdf:
                ziel.write_bytes(pdf)
                zeile["tracking"] = True
            else:
                zeile["grund"] = "kein Tracking-PDF veröffentlicht"
            status.append(zeile)
    store.save()
    return status
