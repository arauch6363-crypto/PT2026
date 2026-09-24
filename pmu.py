"""
PMU-Programm als Ausgangspunkt.

Das PMU-Programm ist die Wahrheit darüber, welche Rennen es gab:
    meetings(tag)   -> alle französischen Galopp-Veranstaltungen eines Tages
                       (auf Wunsch nur Flachrennen, nur bereits gelaufene)
    starter(...)    -> Rennen- und Starterzeilen (Jockey, Trainer, Quote, Einlauf …)

Erst danach wird bei France Galop geschaut, ob es zu einem Rennen ein
Tracking-PDF gibt (siehe france_galop.py).

Hinweis: Die PMU-Schnittstelle ist nicht offiziell dokumentiert. Nur für
private Auswertung nutzen und nicht im Sekundentakt abfragen.
"""
from __future__ import annotations

import re
import time
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

PARIS = ZoneInfo("Europe/Paris")

PROGRAMM_URLS = [
    "https://online.turfinfo.api.pmu.fr/rest/client/61/programme/{d}",
    "https://offline.turfinfo.api.pmu.fr/rest/client/7/programme/{d}",
    "https://online.turfinfo.api.pmu.fr/rest/client/1/programme/{d}",
]
PARTICIPANTS_URLS = [
    "https://online.turfinfo.api.pmu.fr/rest/client/61/programme/{d}/R{r}/C{c}/participants",
    "https://offline.turfinfo.api.pmu.fr/rest/client/7/programme/{d}/R{r}/C{c}/participants",
]
# Replay: die Rennseite der PMU-Schnittstelle meldet nur, ob es ein Replay gibt ("replayDisponible"),
# keine Video-Adresse (geprüft 23.09.2026). /replay-Endpunkte und online.pmu.fr liefern aus Colab nichts.
# Das Replay selbst spielt die Rennseite auf pmu.fr (PMU_SEITE).
REPLAY_URLS = [
    "https://online.turfinfo.api.pmu.fr/rest/client/61/programme/{d}/R{r}/C{c}",
    "https://offline.turfinfo.api.pmu.fr/rest/client/7/programme/{d}/R{r}/C{c}",
]
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
PMU_SEITE = "https://www.pmu.fr/turf/{d}/R{r}/C{c}/"     # Rennseite, Ersatz ohne Replay-Adresse
HEADERS = {"User-Agent": "Mozilla/5.0 (private racing analysis)"}

TROT = {"ATTELE", "MONTE", "TROT_ATTELE", "TROT_MONTE"}
FRANKREICH = {"FRA", "FR", "FRANCE"}
PUFFER_MIN = 25          # so lange nach dem angesetzten Start gilt ein Rennen als noch nicht gelaufen

LETZTER_FEHLER = ""      # Diagnose, wenn das Programm nicht erreichbar war


# --------------------------------------------------------------------------
# Kleinkram
# --------------------------------------------------------------------------
# PMU nennt dieselbe Bahn mal "CHANTILLY", mal "HIPPODROME DE CHANTILLY",
# mal "HIPPODROME DU LION D'ANGERS" (wo der Artikel eigentlich "LE" lautet).
# Vorsatz und führende Artikel müssen deshalb einheitlich weg, sonst findet die
# Codetabelle dieselbe Bahn unter zwei Namen nicht wieder.
PRAEFIX = re.compile(r"^HIPP(?:ODROME)?\s+")
ARTIKEL = re.compile(r"^(?:DE|DU|DES|D|LE|LA|LES|L)\s+")


def norm(name: str) -> str:
    """Bahnname vereinheitlichen: Akzente, Sonderzeichen, den Vorsatz "Hippodrome"
    und führende Artikel entfernen.
    'Hippodrome du Lion d\'Angers' und 'Le Lion-d\'Angers' -> 'LION D ANGERS'."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s.upper())).strip()
    roh = s
    s = PRAEFIX.sub("", s)
    while True:                       # "DE LA TESTE DE BUCH" -> "TESTE DE BUCH"
        gekuerzt = ARTIKEL.sub("", s, count=1)
        if gekuerzt == s:
            break
        s = gekuerzt
    return s.strip() or roh


def norm_code(code) -> str:
    """Bahncode vereinheitlichen – nur Großschreibung und Leerzeichen weg.
    Sonderzeichen bleiben: Saint-Malo hat den Code 'S-M'."""
    return re.sub(r"\s+", "", str(code or "")).upper()


def bahn_name(hip: dict) -> str:
    """Einheitlicher Bahnname. Der lange Name ist der aussagekräftigere
    ("TOULOUSE LA CEPIERE" statt "LA CEPIERE"); die Zuordnung in der Codetabelle
    hängt ohnehin am PMU-Bahncode, nicht am Namen."""
    return norm(hip.get("libelleLong") or hip.get("libelleCourt") or "?")


def heute() -> date:
    """Heutiges Datum in Frankreich – Colab läuft nach UTC und wäre spätabends einen Tag zurück."""
    return datetime.now(PARIS).date()


def tage_rueckwaerts(start, ende=None):
    """Tage von ende (Vorgabe: heute) rückwärts bis start – neueste zuerst."""
    d1 = pd.to_datetime(ende).date() if ende else heute()
    d0 = pd.to_datetime(start).date()
    d = d1
    while d >= d0:
        yield d
        d -= timedelta(days=1)


def _g(d, *keys):
    """Sicher verschachtelt lesen: _g(x, 'a', 'b') = x['a']['b'] oder None."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _json(session: requests.Session, urls: list[str], *, runden: int = 2, **fmt):
    """Erste Adresse, die JSON liefert. None = keine erreichbar."""
    global LETZTER_FEHLER
    fehler = []
    for runde in range(runden):
        for u in urls:
            kurz = u.split("//")[1].split(".")[0] + "/" + u.split("/client/")[1].split("/")[0]
            try:
                r = session.get(u.format(**fmt), headers=HEADERS, timeout=30)
                if r.ok and r.text.lstrip()[:1] in "{[":
                    LETZTER_FEHLER = ""
                    return r.json()
                fehler.append(f"{kurz}: HTTP {r.status_code}")
            except (requests.RequestException, ValueError) as e:
                fehler.append(f"{kurz}: {type(e).__name__}")
        if runde + 1 < runden:
            time.sleep(5)
    LETZTER_FEHLER = "; ".join(fehler[-len(urls):])
    return None


# --------------------------------------------------------------------------
# Programm eines Tages
# --------------------------------------------------------------------------
def ist_galopp(c: dict) -> bool:
    disc = {str(c.get("discipline") or "").upper(), str(c.get("specialite") or "").upper()}
    return not (disc & TROT)


def ist_flach(c: dict) -> bool:
    disc = f"{c.get('discipline') or ''} {c.get('specialite') or ''}".upper()
    return "PLAT" in disc


def ist_gelaufen(c: dict, tag: date, jetzt: datetime | None = None) -> bool:
    """Ist das Rennen wirklich schon gelaufen? Abgesagte Rennen zählen nicht."""
    jetzt = jetzt or datetime.now(PARIS)
    st = str(c.get("statut") or "").upper()
    if "ANNUL" in st:
        return False
    if c.get("ordreArrivee"):
        return True
    if any(k in st for k in ("ARRIVEE", "FIN_COURSE", "COURSE_ARRETEE")):
        return True
    t = c.get("heureDepart")
    if isinstance(t, (int, float)):
        return datetime.fromtimestamp(t / 1000, PARIS) + timedelta(minutes=PUFFER_MIN) <= jetzt
    return tag < jetzt.date()


def meetings(tag: date, session: requests.Session, *, nur_flach: bool = True,
             nur_gelaufen: bool = True) -> list[dict] | None:
    """Französische Galopp-Veranstaltungen eines Tages.

    [{'hippodrome': 'DIEPPE', 'pmu_code': 'DIE', 'reunion': 3,
      'races': [1, 2, ...], 'courses': [<rohdaten>, ...]}, ...]
    None = PMU-Programm nicht erreichbar (Tag wird später erneut versucht).
    """
    data = _json(session, PROGRAMM_URLS, d=tag.strftime("%d%m%Y"))
    if data is None or "programme" not in data:
        return None
    jetzt = datetime.now(PARIS)
    out = []
    for reu in data.get("programme", {}).get("reunions", []):
        if ((reu.get("pays") or {}).get("code") or "FRA").upper() not in FRANKREICH:
            continue
        hip = reu.get("hippodrome") or {}
        name = bahn_name(hip)
        reunion = reu.get("numOfficiel") or reu.get("numExterne")
        if reunion is None:
            continue
        courses = []
        for c in reu.get("courses", []):
            if not ist_galopp(c):
                continue
            if nur_flach and not ist_flach(c):
                continue
            if nur_gelaufen and not ist_gelaufen(c, tag, jetzt):
                continue
            if c.get("numOrdre") or c.get("numExterne"):
                courses.append(c)
        if courses:
            out.append({
                "hippodrome": name,
                "hippodrome_pmu": hip.get("libelleLong") or hip.get("libelleCourt") or "",
                "pmu_code": hip.get("code") or "",
                "reunion": int(reunion),
                "courses": courses,
                "races": sorted(int(c.get("numOrdre") or c.get("numExterne")) for c in courses),
            })
    return out


def race_no(c: dict) -> int:
    return int(c.get("numOrdre") or c.get("numExterne"))


def race_id(tag: date, m: dict, c: dict) -> str:
    """Eindeutig und unabhängig vom France-Galop-Code: '20260919R3C5'."""
    return f"{tag.strftime('%Y%m%d')}R{m['reunion']}C{race_no(c)}"


# --------------------------------------------------------------------------
# Rennen- und Starterzeilen
# --------------------------------------------------------------------------
def _kg(x):
    if x in (None, ""):
        return None
    x = float(x)
    return x / 10 if x > 200 else x          # PMU liefert Gewicht meist in Hektogramm (585 = 58,5 kg)


def race_row(tag: date, m: dict, c: dict) -> dict:
    t = c.get("heureDepart")
    return {
        "race_id": race_id(tag, m, c),
        "date": tag.strftime("%Y%m%d"),
        "hippodrome": m["hippodrome"],
        "pmu_code": m["pmu_code"],
        "reunion": m["reunion"],
        "race_no": race_no(c),
        "race_name": c.get("libelle"),
        "post_time": (datetime.fromtimestamp(t / 1000, PARIS).strftime("%H:%M")
                      if isinstance(t, (int, float)) else None),
        "discipline": c.get("discipline"), "specialite": c.get("specialite"),
        "statut": c.get("statut"),
        "distance_m": c.get("distance"), "corde": c.get("corde"), "parcours": c.get("parcours"),
        "prize_eur": c.get("montantPrix"),
        "categorie": c.get("categorieParticularite"), "conditions_age": c.get("conditionAge"),
        "conditions_sexe": c.get("conditionSexe"),
        "going": _g(c, "penetrometre", "intitule"), "going_value": _g(c, "penetrometre", "valeurMesure"),
        "runners_declared": c.get("nombreDeclaresPartants"),
        "finish_order": " - ".join(str(x[0]) if isinstance(x, list) and x else str(x)
                                   for x in (c.get("ordreArrivee") or [])),
    }


def runner_row(rid: str, p: dict) -> dict:
    return {
        "race_id": rid,
        "saddle_no": p.get("numPmu"),
        "horse": p.get("nom"),
        "status": p.get("statut"),
        "age": p.get("age"), "sex": p.get("sexe"),
        "jockey": p.get("driver") or p.get("jockey"),
        "trainer": p.get("entraineur"), "owner": p.get("proprietaire"),
        "breeder": p.get("eleveur"),
        "draw": p.get("placeCorde"),
        "weight_kg": _kg(p.get("handicapPoids") or p.get("poidsConditionMonte")),
        "rating": p.get("handicapValeur"),
        "blinkers": p.get("oeilleres"),
        "form": p.get("musique"),
        "starts": p.get("nombreCourses"), "wins": p.get("nombreVictoires"), "places": p.get("nombrePlaces"),
        "earnings_eur": (_g(p, "gainsParticipant", "gainsCarriere") or 0) / 100 or None,
        "sire": p.get("nomPere"), "dam": p.get("nomMere"),
        "odds_final": _g(p, "dernierRapportDirect", "rapport"),
        "odds_morning": _g(p, "dernierRapportReference", "rapport"),
        "finish_pos": p.get("ordreArrivee"),
        "dist_prev_label": (_g(p, "distanceChevalPrecedent", "libelleCourt")
                            or _g(p, "distanceChevalPrecedent", "libelleLong")
                            or (p.get("distanceChevalPrecedent")
                                if isinstance(p.get("distanceChevalPrecedent"), str) else None)
                            or p.get("ecart")),
        "incident": p.get("incident"),
        "silks_url": p.get("urlCasaque"),
        "comment": _g(p, "commentaireApresCourse", "texte"),
    }


def starter(tag: date, session: requests.Session, meets: list[dict], *,
            pause: float = 0.3) -> tuple[list[dict], list[dict]]:
    """Rennen- und Starterzeilen für die übergebenen Veranstaltungen."""
    d = tag.strftime("%d%m%Y")
    races, runners = [], []
    for m in meets:
        for c in m["courses"]:
            row = race_row(tag, m, c)
            races.append(row)
            data = _json(session, PARTICIPANTS_URLS, runden=1, d=d, r=m["reunion"], c=race_no(c))
            time.sleep(pause)
            for p in (data or {}).get("participants", []):
                runners.append(runner_row(row["race_id"], p))
    return races, runners


# --------------------------------------------------------------------------
# Abstände in Längen
# --------------------------------------------------------------------------
# Französische Abstandsangaben -> Längen (übliche Umrechnung)
SHORT_MARGINS = [
    (r"DEAD ?HEAT|DH|EX ?AEQUO|E ?P", 0.0),
    (r"NEZ|NSE|NOSE", 0.05),
    (r"(COURTE|CTE|CT|C) ?TETE|SH(ORT)? ?HEAD|SHD", 0.1),
    (r"TETE|TET|HEAD|HD", 0.2),
    (r"(COURTE|CTE|CT|C) ?ENC(OLURE)?", 0.25),
    (r"ENC(OLURE)?|NECK|NK", 0.3),
    (r"LOIN|DIST(ANCE)?|DIS", 30.0),
]


def margin_to_lengths(label) -> float | None:
    """'NEZ' -> 0.05, '1 1/2' -> 1.5, '3/4 L' -> 0.75, '2L1/2' -> 2.5, 'LOIN' -> 30"""
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return None
    t = unicodedata.normalize("NFKD", str(label)).encode("ascii", "ignore").decode().upper().strip()
    t = re.sub(r"\.", "", t)
    for pat, val in SHORT_MARGINS:
        if re.fullmatch(rf"(?:{pat})", t):
            return val
    t = re.sub(r"LONGUEURS?|LONG|LGS?|L(?![A-Z])", " ", t)     # Einheit entfernen
    t = t.replace(",", ".")
    t = re.sub(r"(\d)(\d/\d)", r"\1 \2", t.replace(" ", "")) if re.fullmatch(r"\d+ ?\d/\d", t.strip()) else t
    total, found = 0.0, False
    for part in t.split():
        m = re.fullmatch(r"(\d+)/(\d+)", part)
        if m:
            total += int(m[1]) / int(m[2]); found = True
        elif re.fullmatch(r"\d+(\.\d+)?", part):
            total += float(part); found = True
    return total if found else None


def add_lengths(df: pd.DataFrame) -> pd.DataFrame:
    """lengths_prev = Abstand zum Vordermann, lengths_behind = Abstand zum Sieger (kumuliert)."""
    if df.empty or "dist_prev_label" not in df.columns:
        return df
    df = df.copy()
    df["lengths_prev"] = df["dist_prev_label"].map(margin_to_lengths)
    df["finish_pos"] = pd.to_numeric(df["finish_pos"], errors="coerce")
    df["lengths_behind"] = None
    for rid, g in df[df["finish_pos"].notna()].groupby("race_id"):
        g = g.sort_values("finish_pos")
        cum, out = 0.0, []
        for pos, lp in zip(g["finish_pos"], g["lengths_prev"]):
            if pos == 1:
                cum = 0.0
            elif cum is not None and pd.notna(lp):
                cum += lp
            else:
                cum = None                            # Lücke: dahinter nicht mehr berechenbar
            out.append(round(cum, 2) if cum is not None else None)
        df.loc[g.index, "lengths_behind"] = out
    df["lengths_behind"] = pd.to_numeric(df["lengths_behind"], errors="coerce")
    return df


# --------------------------------------------------------------------------
# Replay-Videos
# --------------------------------------------------------------------------
_VIDEO_DATEI = re.compile(r"\.(mp4|m3u8|webm|mov)(\?|$)", re.I)
_VIDEO_WORT = re.compile(r"video|replay|vod|media|stream|film", re.I)


def _race_teile(rid: str) -> tuple[str, int, int]:
    """'20260919R3C5' -> ('19092026', 3, 5)"""
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})R(\d+)C(\d+)", str(rid))
    if not m:
        raise ValueError(f"race_id nicht lesbar: {rid}")
    j, mo, t, r, c = m.groups()
    return f"{t}{mo}{j}", int(r), int(c)


def pmu_seite(rid: str) -> str | None:
    try:
        d, r, c = _race_teile(rid)
    except ValueError:
        return None
    return PMU_SEITE.format(d=d, r=r, c=c)


def video_urls(obj, pfad: str = "") -> list[tuple[str, str]]:
    """Alle Adressen in einer JSON-Antwort, die nach Video aussehen: (Pfad, URL).
    Videodateien (mp4, m3u8 …) zuerst, dann Adressen unter Schlüsseln wie 'video' / 'replay'.
    Die Antwort von /replay ist nicht dokumentiert – deshalb wird gesucht statt ein Feld gelesen."""
    treffer = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            treffer += video_urls(v, f"{pfad}.{k}" if pfad else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            treffer += video_urls(v, f"{pfad}[{i}]")
    elif isinstance(obj, str) and obj.startswith(("http://", "https://", "//")):
        url = "https:" + obj if obj.startswith("//") else obj
        if _VIDEO_DATEI.search(url) or _VIDEO_WORT.search(pfad) or _VIDEO_WORT.search(url):
            treffer.append((pfad, url))
    if pfad == "":
        treffer.sort(key=lambda t: (not _VIDEO_DATEI.search(t[1]), not _VIDEO_WORT.search(t[0])))
    return treffer


def _papi(session: requests.Session, url: str):
    """JSON von online.pmu.fr (papi) oder None."""
    try:
        r = session.get(url, headers=BROWSER_HEADERS, timeout=15)
        if r.ok and r.text.lstrip()[:1] in "{[":
            return r.json()
    except (requests.RequestException, ValueError):
        pass
    return None


def replay(rid: str, session: requests.Session | None = None) -> dict | None:
    """Gibt es ein Replay? {"available": bool, "url": Video-Adresse oder None}.
    None, wenn keine Adresse der Schnittstelle geantwortet hat (dann ist nichts bekannt)."""
    d, r, c = _race_teile(rid)
    s = session or requests.Session()
    for u in REPLAY_URLS:
        data = _papi(s, u.format(d=d, r=r, c=c))
        if not isinstance(data, dict):
            continue
        urls = video_urls(data)
        return {"available": bool(data.get("replayDisponible")) or bool(urls),
                "url": urls[0][1] if urls else None}
    return None


def replay_diagnose(rid: str, session: requests.Session | None = None) -> None:
    """Zeigt, was die Schnittstelle zum Replay eines Rennens liefert."""
    d, r, c = _race_teile(rid)
    s = session or requests.Session()
    print("Rennseite pmu.fr:", pmu_seite(rid))
    for u in REPLAY_URLS:
        url = u.format(d=d, r=r, c=c)
        try:
            resp = s.get(url, headers=BROWSER_HEADERS, timeout=15)
        except requests.RequestException as e:
            print(url, "->", type(e).__name__)
            continue
        print(url, "-> HTTP", resp.status_code)
        try:
            data = resp.json()
        except ValueError:
            print(resp.text[:500])
            continue
        if isinstance(data, dict):
            print("  replayDisponible:", data.get("replayDisponible"))
            felder = [k for k in data if _VIDEO_WORT.search(k)]
            print("  Felder mit Video-Bezug:", {k: data[k] for k in felder})
        print("  Video-Adressen:", video_urls(data) or "keine")
        print("  ->", replay(rid, s))
        return
