"""
Wissensbasis aus der PMU-Schnittstelle: Rennen, Starter, Dividenden und Zeiten über eine lange Historie.

    import pmu_basis as pb
    pb.run(BASE, "2019-01-01", max_tage=100)      # in Etappen; erneut aufrufen setzt fort

Je Tag (französische, gelaufene Flachrennen wie in der Pipeline) werden geschrieben – eine Datei je Tag:

    <BASE>/parquet/pmu_races/<JJJJMMTT>.parquet      Rennen: alle Felder wie bisher (pmu.race_row), dazu
                                                     Siegerzeit race_time_s (dureeCourse, Einheit am Tempo
                                                     erkannt), Piste, Parcours, Rennkommentar und alle übrigen
                                                     einfachen Felder der PMU-Rennseite mit Präfix c_
    <BASE>/parquet/pmu_runners/<JJJJMMTT>.parquet    Starter: alle Felder wie bisher (pmu.runner_row, Längen),
                                                     dazu Kommentar nach dem Rennen (comment), Zeit time_s (von
                                                     PMU, falls geliefert – sonst geschätzt aus Siegerzeit und
                                                     Längen, time_est = True) und alle übrigen einfachen Felder
                                                     mit Präfix p_
    <BASE>/parquet/pmu_dividends/<JJJJMMTT>.parquet  Dividenden (rapports-definitifs): je Wette und Kombination

Existiert eine Tagesdatei schon, wird sie überschrieben (die Spalten der Pipeline bleiben erhalten, es kommen
nur welche dazu); fehlt ein Ordner, wird er angelegt. Tracking-Tabellen bleiben unberührt.
Fortschritt in <BASE>/pmu_basis_fortschritt.json – erledigte Tage werden nicht erneut abgefragt (neu holen:
neu=True). Antwortet PMU an MAX_STUMM Tagen in Folge nicht, bricht der Lauf ab (keine Dauerschleife gegen
eine Sperre). Die Schnittstelle ist inoffiziell: PAUSE_S zwischen den Anfragen, sparsam bleiben.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import pmu
import speedfig
import standardzeiten

HOSTS = ["https://online.turfinfo.api.pmu.fr/rest/client/61",
         "https://offline.turfinfo.api.pmu.fr/rest/client/7",
         "https://online.turfinfo.api.pmu.fr/rest/client/1"]
RACE_PFAD = "programme/{d}/R{r}/C{c}"
PAUSE_S = 0.4
MAX_STUMM = 3
NACHZUEGLER_TAGE = 2        # so nah an heute nicht als erledigt markieren (Dividenden/Kommentare kommen später)
FORTSCHRITT = "pmu_basis_fortschritt.json"
TABELLEN = ["pmu_races", "pmu_runners", "pmu_dividends"]
LETZTER_STATUS: dict = {}


# --------------------------------------------------------------------------
# Abruf
# --------------------------------------------------------------------------
def _hole(s: requests.Session, pfad: str, hosts=HOSTS):
    """Erste Antwort mit JSON über die Hosts; None, wenn keiner liefert. LETZTER_STATUS merkt sich den Grund."""
    for h in hosts:
        url = f"{h}/{pfad}"
        try:
            r = s.get(url, headers=pmu.HEADERS, timeout=25)
        except requests.RequestException as e:
            LETZTER_STATUS[pfad] = type(e).__name__
            continue
        if r.ok and r.text.lstrip()[:1] in "{[":
            return r.json()
        LETZTER_STATUS[pfad] = r.status_code
    return None


def _skalar(d: dict, praefix: str, ohne: set) -> dict:
    """Alle einfachen Felder (Zahl, Text, Wahrheitswert) eines PMU-Objekts, mit Präfix."""
    return {f"{praefix}{k}": v for k, v in (d or {}).items()
            if k not in ohne and (v is None or isinstance(v, (str, int, float, bool)))}


def kommentar(obj) -> str | None:
    """Kommentar in jeder Form, die PMU liefert: Text, {'texte': …}, {'commentaire': …} oder Liste davon."""
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj.strip() or None
    if isinstance(obj, dict):
        for k in ("texte", "text", "commentaire", "libelle", "contenu"):
            if isinstance(obj.get(k), str) and obj[k].strip():
                return obj[k].strip()
        return None
    if isinstance(obj, list):
        teile = [t for t in (kommentar(x) for x in obj) if t]
        return " ".join(teile) or None
    return None


def _kommentar_teilnehmer(p: dict) -> str | None:
    for k in ("commentaireApresCourse", "commentaire", "commentaires", "commentaireCourse"):
        t = kommentar(p.get(k))
        if t:
            return t
    return None


def dividenden_zeilen(rid: str, data) -> list[dict]:
    """rapports-definitifs -> eine Zeile je Wette und Kombination (Beträge wie geliefert, meist in Cent)."""
    wetten = data if isinstance(data, list) else (data or {}).get("rapportsDefinitifs") or (data or {}).get("rapports") or []
    zeilen = []
    for w in wetten if isinstance(wetten, list) else []:
        if not isinstance(w, dict):
            continue
        kopf = {"race_id": rid, "bet_type": w.get("typePari"), "bet_family": w.get("famillePari"),
                "base_stake": w.get("miseBase"), "audience": w.get("audience"), "refunded": w.get("rembourse")}
        for r in w.get("rapports") or [{}]:
            if not isinstance(r, dict):
                continue
            kombi = r.get("combinaison")
            div1 = r.get("dividendePourUnEuro")
            zeilen.append({**kopf, "label": r.get("libelle"),
                           "combination": "-".join(map(str, kombi)) if isinstance(kombi, list) else kombi,
                           "dividend": r.get("dividende"), "dividend_per_1eur": div1,
                           "dividend_eur_per_1eur": round(div1 / 100, 2) if isinstance(div1, (int, float)) else None,
                           "dividend_base_stake": r.get("dividendePourUneMiseDeBase"),
                           "winners": r.get("nombreGagnants")})
    return zeilen


def _zeit_teilnehmer(p: dict, distanz) -> float | None:
    for k in ("tempsObtenu", "temps", "tempsCourse"):
        t = standardzeiten.zeit_s(p.get(k), distanz)
        if t is not None:
            return t
    return None


# --------------------------------------------------------------------------
# Ein Tag
# --------------------------------------------------------------------------
def tag_holen(tag: date, s: requests.Session, *, pause: float = PAUSE_S, dividenden: bool = True,
              kommentare_nachladen: bool = True) -> dict | None:
    """Rennen, Starter und Dividenden eines Tages. None = Programm nicht erreichbar."""
    meets = pmu.meetings(tag, s, nur_flach=True, nur_gelaufen=True)
    if meets is None:
        return None
    d = tag.strftime("%d%m%Y")
    races, runners, divs = [], [], []
    for m in meets:
        for c in m["courses"]:
            r_no = pmu.race_no(c)
            pfad = RACE_PFAD.format(d=d, r=m["reunion"], c=r_no)
            detail = _hole(s, pfad) or {}
            time.sleep(pause)
            voll = {**c, **{k: v for k, v in detail.items() if v is not None}} if isinstance(detail, dict) else c
            z = pmu.race_row(tag, m, voll)
            rid = z["race_id"]
            z.update({
                "race_time_s": standardzeiten.zeit_s(voll.get("dureeCourse"), voll.get("distance")),
                "track_type": voll.get("typePiste"),
                "parcours_norm": standardzeiten.parcours_norm(voll.get("parcours")),
                "race_comment": kommentar(voll.get("commentaireApresCourse")),
                **_skalar(voll, "c_", set()),
            })
            races.append(z)

            # Starter; fehlen die Kommentare, einmal die Starterliste eines anderen Clients versuchen
            data = _hole(s, f"{pfad}/participants") or {}
            time.sleep(pause)
            teilnehmer = data.get("participants", []) if isinstance(data, dict) else []
            if kommentare_nachladen and teilnehmer and not any(_kommentar_teilnehmer(p) for p in teilnehmer):
                for h in HOSTS[1:]:
                    alt = _hole(s, f"{pfad}/participants", hosts=[h]) or {}
                    time.sleep(pause)
                    alt_t = alt.get("participants", []) if isinstance(alt, dict) else []
                    kom = {p.get("numPmu"): _kommentar_teilnehmer(p) for p in alt_t}
                    if any(kom.values()):
                        for p in teilnehmer:
                            if kom.get(p.get("numPmu")):
                                p["commentaireApresCourse"] = {"texte": kom[p.get("numPmu")]}
                        break
            for p in teilnehmer:
                zr = pmu.runner_row(rid, p)
                zr["comment"] = _kommentar_teilnehmer(p)
                zr["time_s"] = _zeit_teilnehmer(p, z.get("distance_m"))
                zr.update(_skalar(p, "p_", set()))
                runners.append(zr)

            if dividenden:
                divs += dividenden_zeilen(rid, _hole(s, f"{pfad}/rapports-definitifs"))
                time.sleep(pause)

    ru = pmu.add_lengths(pd.DataFrame(runners)) if runners else pd.DataFrame()
    if len(ru):
        ru = _zeiten_schaetzen(ru, pd.DataFrame(races))
    return {"races": races, "runners": ru.to_dict("records") if len(ru) else [], "dividends": divs}


def _zeiten_schaetzen(ru: pd.DataFrame, races: pd.DataFrame) -> pd.DataFrame:
    """Zeit je Starter, wenn PMU keine liefert: Siegerzeit + Längen × Sekunden je Länge (Länge = speedfig.LAENGE_M
    bei der Durchschnittsgeschwindigkeit des Siegers). time_est = True markiert geschätzte Zeiten."""
    ru = ru.copy()
    info = races.set_index("race_id")[["race_time_s", "distance_m"]] if len(races) else pd.DataFrame()
    T = ru["race_id"].map(info["race_time_s"]) if len(info) else np.nan
    D = pd.to_numeric(ru["race_id"].map(info["distance_m"]), errors="coerce") if len(info) else np.nan
    s_je_laenge = speedfig.LAENGE_M / (D / T)
    geschaetzt = T + pd.to_numeric(ru["lengths_behind"], errors="coerce") * s_je_laenge
    ru["time_est"] = ru["time_s"].isna() & geschaetzt.notna()
    ru["time_s"] = ru["time_s"].fillna(geschaetzt.round(2))
    return ru


# --------------------------------------------------------------------------
# Ablage und Lauf
# --------------------------------------------------------------------------
def _schreiben(base: Path, tabelle: str, ymd: str, zeilen) -> int:
    """Tagesdatei <BASE>/parquet/<tabelle>/<ymd>.parquet schreiben (vorhandene überschreiben, Ordner anlegen)."""
    import pipeline
    return pipeline._write(base, tabelle, ymd, zeilen)


def _fortschritt(base: Path) -> dict:
    f = Path(base) / FORTSCHRITT
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"erledigt": {}}
    except ValueError:
        return {"erledigt": {}}


def run(base: Path, von, bis=None, *, max_tage: int | None = None, neu: bool = False, pause: float = PAUSE_S,
        dividenden: bool = True, kommentare_nachladen: bool = True,
        session: requests.Session | None = None) -> dict:
    """Tage von `bis` (Vorgabe: gestern) rückwärts bis `von` holen und schreiben; erledigte überspringen
    (neu=True holt sie erneut). max_tage begrenzt die Tage je Aufruf."""
    base = Path(base)
    s = session or requests.Session()
    st = _fortschritt(base)
    heute = pmu.heute()
    ende = pd.to_datetime(bis).date() if bis else heute - pd.Timedelta(days=1)
    tage = [t for t in pmu.tage_rueckwaerts(von, ende) if neu or t.strftime("%Y%m%d") not in st["erledigt"]]
    if max_tage:
        tage = tage[:max_tage]
    stat = {"tage": 0, "rennen": 0, "starter": 0, "mit_kommentar": 0, "mit_zeit": 0, "zeit_geschaetzt": 0,
            "dividenden": 0, "abgebrochen": False}
    stumm = 0
    print(f"PMU-Basis: {len(tage)} Tage zu holen ({tage[0] if tage else '–'} … {tage[-1] if tage else '–'})")
    for i, tag in enumerate(tage, 1):
        daten = tag_holen(tag, s, pause=pause, dividenden=dividenden, kommentare_nachladen=kommentare_nachladen)
        if daten is None:
            stumm += 1
            print(f"  {tag}: PMU nicht erreichbar ({pmu.LETZTER_FEHLER})")
            if stumm >= MAX_STUMM:
                print(f"  {stumm} Tage in Folge ohne Antwort – abgebrochen (IP-Sperre? später erneut).")
                stat["abgebrochen"] = True
                break
            continue
        stumm = 0
        ymd = tag.strftime("%Y%m%d")
        n_r = _schreiben(base, "pmu_races", ymd, daten["races"])
        n_s = _schreiben(base, "pmu_runners", ymd, daten["runners"])
        n_d = _schreiben(base, "pmu_dividends", ymd, daten["dividends"])
        ru = pd.DataFrame(daten["runners"])
        stat["tage"] += 1
        stat["rennen"] += n_r
        stat["starter"] += n_s
        stat["dividenden"] += n_d
        if len(ru):
            stat["mit_kommentar"] += int(ru["comment"].notna().sum())
            stat["mit_zeit"] += int(ru["time_s"].notna().sum())
            stat["zeit_geschaetzt"] += int(ru.get("time_est", pd.Series(dtype=bool)).fillna(False).sum())
        if (heute - tag).days > NACHZUEGLER_TAGE:
            st["erledigt"][ymd] = {"am": datetime.now().isoformat(timespec="seconds"), "rennen": n_r,
                                   "starter": n_s, "dividenden": n_d}
            (base / FORTSCHRITT).write_text(json.dumps(st, indent=0), encoding="utf-8")
        if i % 10 == 0:
            print(f"  {i}/{len(tage)} Tage · {stat['rennen']} Rennen · {stat['starter']} Starter "
                  f"({stat['mit_kommentar']} mit Kommentar) · {stat['dividenden']} Dividenden")
    print(f"Fertig: {stat['tage']} Tage, {stat['rennen']} Rennen, {stat['starter']} Starter – Kommentar bei "
          f"{stat['mit_kommentar']}, Zeit bei {stat['mit_zeit']} (davon geschätzt {stat['zeit_geschaetzt']}), "
          f"{stat['dividenden']} Dividenden-Zeilen" + (" – abgebrochen" if stat["abgebrochen"] else ""))
    return stat


def abdeckung(base: Path) -> pd.DataFrame:
    """Je Monat: Tage, Rennen, Starter und Anteil mit Siegerzeit, Kommentar und Dividenden."""
    import pipeline
    r, ru, dv = (pipeline.lade(t, Path(base)) for t in TABELLEN)
    if r.empty:
        return pd.DataFrame()
    monat = lambda df: df["race_id"].astype(str).str[:6]
    out = pd.DataFrame({"tage": r.groupby(monat(r))["race_id"].apply(lambda x: x.astype(str).str[:8].nunique()),
                        "rennen": r.groupby(monat(r))["race_id"].nunique()})
    if "race_time_s" in r:
        out["mit_siegerzeit"] = r["race_time_s"].notna().groupby(monat(r)).mean()
    if len(ru):
        out["starter"] = ru.groupby(monat(ru)).size()
        if "comment" in ru:
            out["mit_kommentar"] = ru["comment"].notna().groupby(monat(ru)).mean()
    if len(dv):
        out["rennen_mit_dividenden"] = dv.groupby(monat(dv))["race_id"].nunique() / out["rennen"]
    return out.round(3)
