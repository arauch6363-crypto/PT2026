"""
Standardzeiten französischer Flachrennen – je Konfiguration des Tages.

Eine Standardzeit gilt nicht für "Bahn × Distanz", sondern für die Konfiguration, auf der an diesem Tag
gelaufen wurde: Bahn, Distanz, Piste (Gras / PSF), Parcours (z. B. GRANDE PISTE, PISTE RONDE, LIGNE DROITE)
und Corde. Dieselbe Distanz auf einer anderen Piste oder mit anderem Parcours ist ein anderer Kurs.

1. sammeln()  – Siegerzeiten über eine lange Historie aus dem PMU-Programm
       je Tag das Programm (französische, gelaufene Flachrennen), je Rennen die Siegerzeit (dureeCourse),
       die Konfiguration, Boden (offizieller Begriff), Preisgeld, Altersklasse, Kategorie.
       Fehlt die Zeit im Programm, wird einmal die Rennseite abgefragt. Ablage je Monat in
       <BASE>/standardzeiten/rennen/<JJJJMM>.parquet, Fortschritt in <BASE>/standardzeiten/fortschritt.json –
       es lässt sich in Etappen beliebig weit zurück sammeln, erledigte Tage werden nicht erneut abgefragt.
       Antwortet PMU an MAX_STUMM Tagen in Folge nicht, bricht die Sammlung ab (keine Dauerschleife gegen
       eine Sperre).

2. berechnen() – Standardzeit je Konfiguration (s/km, guter Boden, Referenzklasse)
       Siegerzeit in s/km, auf eine Referenzklasse umgerechnet (β aus Altersklasse und log. Preisgeld wie in
       tempo_delta, geschätzt innerhalb Tag × Bahn × Boden). Dann abwechselnd (Mediane, robust):
           Standard je Konfiguration = Median(Zeit − Going Allowance)
           Going Allowance je Tag × Bahn × Boden = Median(Zeit − Standard), zu 0 gezogen wie n / (n + 1)
       Nullpunkt der Allowance je Bahn und Belag: auf Gras der Median der Gruppen auf gutem Boden (BON,
       BON SOUPLE, BON LEGER) – die Standardzeit gilt damit für guten Boden –, auf PSF der Median der PSF-Gruppen. Konfigurationen mit wenigen Rennen werden zur Standardzeit
       derselben Bahn und Distanz gezogen: (n · eigene + K · Bahn×Distanz) / (n + K).

3. run() – beides und Ablage: <BASE>/standardzeiten/standards.parquet und .csv, going_allowances.parquet.

    import standardzeiten as sz
    sz.run(BASE, "2019-01-01")              # sammelt (in Etappen: max_tage) und berechnet
    sz.laden_standards(BASE)                # fertige Standardzeiten
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import pmu
import tempo_delta

ORDNER = "standardzeiten"
RACE_URLS = [
    "https://online.turfinfo.api.pmu.fr/rest/client/61/programme/{d}/R{r}/C{c}",
    "https://offline.turfinfo.api.pmu.fr/rest/client/7/programme/{d}/R{r}/C{c}",
]
PAUSE_S = 0.5               # zwischen Anfragen – die Schnittstelle ist inoffiziell, sparsam bleiben
MAX_STUMM = 3               # so viele Tage in Folge ohne Antwort -> Sammlung abbrechen
NACHZUEGLER_TAGE = 2        # Tage so nah an heute werden nicht als erledigt markiert (Zeiten kommen evtl. später)
SPEED_KMH = (40.0, 75.0)    # plausibles Durchschnittstempo einer Siegerzeit
GUTER_BODEN = {"BON", "BON SOUPLE", "BON LEGER"}
MIN_RENNEN = 5              # ab so vielen Rennen gilt eine Standardzeit als belastbar
SHRINK_K = 5.0              # Konfiguration zur Bahn×Distanz ziehen wie n / (n + K)
GA_SHRINK = 1.0
ITERATIONEN = 12
GUTE_KLASSE_Q = 0.5

# offizieller Bodenbegriff (penetrometre.intitule) -> Klasse, längste zuerst
GOING_KLASSEN = ["TRES LEGER", "BON LEGER", "BON SOUPLE", "TRES SOUPLE", "TRES LOURD", "COLLANT", "LOURD",
                 "LEGER", "SOUPLE", "BON"]


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------
def ordner(base: Path) -> Path:
    return Path(base) / ORDNER


def going_klasse(text) -> str | None:
    t = tempo_delta.norm(text or "")
    t = re.sub(r"[^A-Z]+", " ", t).strip()
    if not t:
        return None
    if "PSF" in t:
        return "PSF"
    return next((k for k in GOING_KLASSEN if re.search(rf"\b{k}\b", t)), None)


def parcours_norm(text) -> str:
    """'1600 M. (Grande piste)' -> 'GRANDE PISTE'; ohne Angabe ''."""
    t = tempo_delta.norm(text or "")
    t = re.sub(r"^\s*\d[\d\s.]*\s*M\b\.?", " ", t)
    t = re.sub(r"[^A-Z0-9]+", " ", t).strip()
    return t


def zeit_s(roh, distanz) -> float | None:
    """dureeCourse in Sekunden – die Einheit ist nicht dokumentiert: ms, 1/100 s oder s, je nachdem, welche
    ein plausibles Tempo ergibt."""
    try:
        v, d = float(roh), float(distanz)
    except (TypeError, ValueError):
        return None
    if not (v > 0 and d > 0):
        return None
    for teiler in (1000.0, 100.0, 1.0):
        t = v / teiler
        if SPEED_KMH[0] <= d / t * 3.6 <= SPEED_KMH[1]:
            return round(t, 2)
    return None


def konfiguration(df: pd.DataFrame) -> pd.Series:
    """Schlüssel der Konfiguration des Tages: Bahn | Distanz | Piste | Parcours | Corde."""
    return (df["bahn"].astype(str) + "|" + df["distance_m"].astype("Int64").astype(str) + "|"
            + df["piste"].fillna("?").astype(str) + "|" + df["parcours_n"].fillna("").astype(str) + "|"
            + df["corde"].fillna("?").astype(str))


def rennen_zeile(tag: date, m: dict, c: dict) -> dict:
    """Eine Zeile je Rennen aus den Rohdaten des Programms (pmu.race_row + Zeit und Konfiguration)."""
    z = pmu.race_row(tag, m, c)
    pen = c.get("penetrometre") or {}
    z.update({
        "bahn": pmu.norm(m.get("hippodrome") or "") or m.get("hippodrome"),
        "piste": c.get("typePiste"),
        "parcours_n": parcours_norm(c.get("parcours")),
        "going_klasse": going_klasse(pen.get("intitule")),
        "duree_roh": c.get("dureeCourse"),
        "zeit_s": zeit_s(c.get("dureeCourse"), c.get("distance")),
    })
    return z


# --------------------------------------------------------------------------
# 1) Sammeln
# --------------------------------------------------------------------------
def _fortschritt(base: Path) -> dict:
    f = ordner(base) / "fortschritt.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"erledigt": []}


def _speichern_fortschritt(base: Path, st: dict) -> None:
    ordner(base).mkdir(parents=True, exist_ok=True)
    (ordner(base) / "fortschritt.json").write_text(json.dumps(st, indent=0), encoding="utf-8")


def _ablegen(base: Path, zeilen: list[dict]) -> None:
    """Zeilen je Monat anhängen (race_id eindeutig, neuere Zeile gewinnt)."""
    if not zeilen:
        return
    df = pd.DataFrame(zeilen)
    ziel = ordner(base) / "rennen"
    ziel.mkdir(parents=True, exist_ok=True)
    for monat, g in df.groupby(df["date"].astype(str).str[:6]):
        f = ziel / f"{monat}.parquet"
        alt = pd.read_parquet(f) if f.exists() else pd.DataFrame()
        neu = pd.concat([alt, g], ignore_index=True).drop_duplicates("race_id", keep="last")
        for c in neu.columns:
            if neu[c].dtype == object:
                neu[c] = neu[c].map(lambda x: x if x is None or isinstance(x, str) else str(x))
        neu.to_parquet(f, index=False)


def rennen_eines_tages(tag: date, session: requests.Session, *, nachladen: bool = True,
                       pause: float = PAUSE_S) -> list[dict] | None:
    """Alle französischen, gelaufenen Flachrennen eines Tages mit Zeit und Konfiguration.
    None = Programm nicht erreichbar."""
    meets = pmu.meetings(tag, session, nur_flach=True, nur_gelaufen=True)
    if meets is None:
        return None
    zeilen = []
    for m in meets:
        for c in m["courses"]:
            z = rennen_zeile(tag, m, c)
            if z["zeit_s"] is None and nachladen:
                time.sleep(pause)
                detail = pmu._json(session, RACE_URLS, runden=1, d=tag.strftime("%d%m%Y"),
                                   r=m["reunion"], c=pmu.race_no(c))
                if isinstance(detail, dict):
                    z = rennen_zeile(tag, m, {**c, **{k: v for k, v in detail.items() if v is not None}})
            zeilen.append(z)
    return zeilen


def sammeln(base: Path, von, bis=None, *, max_tage: int | None = None, nachladen: bool = True,
            pause: float = PAUSE_S, session: requests.Session | None = None) -> dict:
    """Siegerzeiten von `bis` (Vorgabe: gestern) rückwärts bis `von` sammeln, erledigte Tage überspringen.
    max_tage begrenzt die Tage je Aufruf (in Etappen sammeln). Rückgabe: kurze Statistik."""
    base = Path(base)
    s = session or requests.Session()
    st = _fortschritt(base)
    erledigt = set(st["erledigt"])
    heute = pmu.heute()
    ende = pd.to_datetime(bis).date() if bis else heute - pd.Timedelta(days=1)
    tage = [t for t in pmu.tage_rueckwaerts(von, ende) if t.strftime("%Y%m%d") not in erledigt]
    if max_tage:
        tage = tage[:max_tage]
    stat = {"tage": 0, "rennen": 0, "mit_zeit": 0, "abgebrochen": False}
    stumm = 0
    for i, tag in enumerate(tage, 1):
        zeilen = rennen_eines_tages(tag, s, nachladen=nachladen, pause=pause)
        if zeilen is None:
            stumm += 1
            print(f"  {tag}: PMU nicht erreichbar ({pmu.LETZTER_FEHLER})")
            if stumm >= MAX_STUMM:
                print(f"  {stumm} Tage in Folge ohne Antwort – Sammlung abgebrochen (IP-Sperre? später erneut).")
                stat["abgebrochen"] = True
                break
            continue
        stumm = 0
        _ablegen(base, zeilen)
        stat["tage"] += 1
        stat["rennen"] += len(zeilen)
        stat["mit_zeit"] += sum(z["zeit_s"] is not None for z in zeilen)
        if (heute - tag).days > NACHZUEGLER_TAGE:
            erledigt.add(tag.strftime("%Y%m%d"))
            st["erledigt"] = sorted(erledigt)
            _speichern_fortschritt(base, st)
        if i % 25 == 0:
            print(f"  {i}/{len(tage)} Tage, {stat['rennen']} Rennen, {stat['mit_zeit']} mit Zeit")
        time.sleep(pause)
    return stat


def laden(base: Path) -> pd.DataFrame:
    """Alle gesammelten Rennen."""
    d = ordner(Path(base)) / "rennen"
    teile = [pd.read_parquet(f) for f in sorted(d.glob("*.parquet"))] if d.exists() else []
    return pd.concat(teile, ignore_index=True).drop_duplicates("race_id", keep="last") if teile else pd.DataFrame()


# --------------------------------------------------------------------------
# 2) Berechnen
# --------------------------------------------------------------------------
def _nullpunkt(ga: pd.Series, g_info: pd.DataFrame) -> pd.Series:
    """Nullpunkt der Going Allowance je Bahn und Belag: Standardzeit und Allowance sind je Bahn nur bis auf eine
    Konstante bestimmt. Gras: Median der Gruppen auf gutem Boden (ersatzweise aller Gras-Gruppen) = 0 – der
    Standard gilt für guten Boden; PSF: Median der PSF-Gruppen = 0."""
    info = g_info.reindex(ga.index)
    belag = np.where(info["boden"] == "PSF", "PSF", "GRAS")
    df = pd.DataFrame({"ga": ga, "bahn": info["bahn"], "belag": belag, "gut": info["boden"].isin(GUTER_BODEN)})
    ref = df[df["gut"] | (df["belag"] == "PSF")].groupby(["bahn", "belag"])["ga"].median()
    ersatz = df.groupby(["bahn", "belag"])["ga"].median()
    null = ref.reindex(ersatz.index).fillna(ersatz)
    return pd.Series([null.get((b, l), 0.0) for b, l in zip(df["bahn"], df["belag"])], index=ga.index)


def berechnen(rennen: pd.DataFrame, *, min_rennen: int = MIN_RENNEN, shrink_k: float = SHRINK_K,
              iterationen: int = ITERATIONEN) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Standardzeiten je Konfiguration. Rückgabe: (standards, going_allowances, info)."""
    d = rennen.copy()
    for c in ["distance_m", "zeit_s", "prize_eur"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[d["zeit_s"].notna() & (d["distance_m"] > 0)]
    d = d[(d["distance_m"] / d["zeit_s"] * 3.6).between(*SPEED_KMH)].copy()
    if d.empty:
        return pd.DataFrame(), pd.DataFrame(), {"rennen": 0}
    d["date"] = pd.to_datetime(d["date"].astype(str), format="%Y%m%d", errors="coerce")
    d["konfig"] = konfiguration(d)
    d["bahn_dist"] = d["bahn"].astype(str) + "|" + d["distance_m"].astype("Int64").astype(str)
    d["boden"] = d["going_klasse"].fillna("UNBEKANNT")
    d["gruppe"] = d["bahn"].astype(str) + "_" + d["date"].dt.strftime("%Y-%m-%d") + "_" + d["boden"]
    d["skm"] = d["zeit_s"] / (d["distance_m"] / 1000)
    d = d.set_index("race_id", drop=False)

    # Klasse: β (s/km) innerhalb Tag × Bahn × Boden, auf eine Referenzklasse umrechnen
    d = tempo_delta.klasse(d)
    cols, ref_age = tempo_delta.klassen_spalten(d)
    d["meeting"], d["cell"] = d["gruppe"], d["konfig"]
    _, _, beta = tempo_delta._fit_fe_ab(d, "skm", cols, cols)
    beta = beta.fillna(0.0)
    d["kl"] = d[cols].to_numpy(float) @ beta.to_numpy(float)
    kl_ref = float(d.loc[d["kl"] <= d["kl"].quantile(GUTE_KLASSE_Q), "kl"].median())
    d["y"] = d["skm"] - (d["kl"] - kl_ref)

    # Standard je Konfiguration und Going Allowance je Gruppe, abwechselnd (Mediane)
    g_info = d.drop_duplicates("gruppe").set_index("gruppe")[["bahn", "boden"]]
    ga = pd.Series(0.0, index=g_info.index)
    for _ in range(iterationen):
        std = (d["y"] - d["gruppe"].map(ga)).groupby(d["konfig"]).median()
        rest = (d["y"] - d["konfig"].map(std)).groupby(d["gruppe"]).agg(["median", "count"])
        ga = rest["median"] * rest["count"] / (rest["count"] + GA_SHRINK)
        ga = ga - _nullpunkt(ga, g_info)

    d["ga"] = d["gruppe"].map(ga)
    d["y_gut"] = d["y"] - d["ga"]
    k = d.groupby("konfig").agg(
        bahn=("bahn", "first"), pmu_code=("pmu_code", "first"), distance_m=("distance_m", "first"),
        piste=("piste", "first"), parcours=("parcours_n", "first"), corde=("corde", "first"),
        n_rennen=("race_id", "count"), n_tage=("date", "nunique"), von=("date", "min"), bis=("date", "max"),
        std_eigen=("y_gut", "median"),
        streuung=("y_gut", lambda x: float((x - x.median()).abs().median() * 1.4826)),
        bahn_dist=("bahn_dist", "first"))
    pool = d.groupby("bahn_dist")["y_gut"].median()
    n = k["n_rennen"].astype(float)
    k["std_skm"] = (n * k["std_eigen"] + shrink_k * k["bahn_dist"].map(pool)) / (n + shrink_k)
    k["std_zeit_s"] = k["std_skm"] * k["distance_m"] / 1000
    k["std_kmh"] = 3600 / k["std_skm"]
    k["belastbar"] = k["n_rennen"] >= min_rennen
    standards = (k.reset_index().rename(columns={"konfig": "konfiguration"})
                  .sort_values(["bahn", "distance_m", "piste", "parcours"]).reset_index(drop=True))
    for c in ["std_eigen", "std_skm", "std_zeit_s", "std_kmh", "streuung"]:
        standards[c] = standards[c].round(3)
    ga_df = (d.drop_duplicates("gruppe")[["gruppe", "bahn", "date", "boden"]]
              .assign(ga_skm=lambda x: x["gruppe"].map(ga).round(3),
                      n_rennen=lambda x: x["gruppe"].map(d["gruppe"].value_counts()))
              .sort_values(["date", "bahn"]).reset_index(drop=True))
    info = {"rennen": int(len(d)), "konfigurationen": int(len(standards)),
            "belastbar": int(standards["belastbar"].sum()), "gruppen": int(len(ga_df)),
            "preis_x2_skm": float(beta.get("log_prize_c", np.nan) * np.log(2)), "ref_age": ref_age,
            "von": str(d["date"].min().date()), "bis": str(d["date"].max().date())}
    return standards, ga_df, info


def standard_fuer(standards: pd.DataFrame, bahn, distanz, piste=None, parcours=None, corde=None) -> pd.Series | None:
    """Standardzeit der passenden Konfiguration; ohne genaue Übereinstimmung die meistgelaufene
    Konfiguration derselben Bahn und Distanz."""
    s = standards[(standards["bahn"] == pmu.norm(bahn)) & (standards["distance_m"] == float(distanz))]
    if s.empty:
        return None
    for spalte, wert in (("piste", piste), ("parcours", parcours_norm(parcours) if parcours else None),
                         ("corde", corde)):
        if wert is not None and (s[spalte] == wert).any():
            s = s[s[spalte] == wert]
    return s.sort_values("n_rennen", ascending=False).iloc[0]


# --------------------------------------------------------------------------
# 3) Alles zusammen
# --------------------------------------------------------------------------
def run(base: Path, von, bis=None, *, max_tage: int | None = None, sammeln_ok: bool = True,
        nachladen: bool = True, pause: float = PAUSE_S) -> pd.DataFrame:
    """Sammeln (optional) und Standardzeiten berechnen; Ablage in <BASE>/standardzeiten/."""
    base = Path(base)
    if sammeln_ok:
        print(f"Siegerzeiten sammeln {von} … {bis or 'gestern'} …")
        stat = sammeln(base, von, bis, max_tage=max_tage, nachladen=nachladen, pause=pause)
        print(f"  {stat['tage']} Tage, {stat['rennen']} Rennen, davon {stat['mit_zeit']} mit Siegerzeit"
              + (" – abgebrochen" if stat["abgebrochen"] else ""))
    rennen = laden(base)
    if rennen.empty:
        print("Noch keine Rennen gesammelt.")
        return pd.DataFrame()
    standards, ga_df, info = berechnen(rennen)
    if standards.empty:
        print("Keine Rennen mit plausibler Siegerzeit – keine Standardzeiten.")
        return standards
    ziel = ordner(base)
    standards.to_parquet(ziel / "standards.parquet", index=False)
    standards.to_csv(ziel / "standards.csv", index=False, sep=";", decimal=",")
    ga_df.to_parquet(ziel / "going_allowances.parquet", index=False)
    (ziel / "info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print(f"Standardzeiten: {info['konfigurationen']} Konfigurationen ({info['belastbar']} mit ≥ {MIN_RENNEN} Rennen) "
          f"aus {info['rennen']:,} Rennen {info['von']} … {info['bis']}, {info['gruppen']:,} Going Allowances; "
          f"Klasse: Preisgeld ×2 {info['preis_x2_skm']:+.3f} s/km -> {ziel}")
    return standards


def je_rennen(base: Path) -> pd.DataFrame:
    """Je gesammeltem Rennen die Standardzeit seiner Konfiguration des Tages und die Going Allowance seines
    Renntags (Tag × Bahn × Boden): race_id, konfiguration, std_skm, ga_skm, belastbar. Grundlage für TR.
    Leer, wenn noch nichts gesammelt oder berechnet wurde (sz.run)."""
    base = Path(base)
    rennen, std = laden(base), laden_standards(base)
    if rennen.empty or std.empty:
        return pd.DataFrame(columns=["race_id", "konfiguration", "std_skm", "ga_skm", "belastbar"])
    r = rennen.copy()
    r["distance_m"] = pd.to_numeric(r["distance_m"], errors="coerce")
    r = r[r["distance_m"] > 0]
    r["konfiguration"] = konfiguration(r)
    s = std.set_index("konfiguration")
    out = r[["race_id", "konfiguration"]].copy()
    out["std_skm"] = out["konfiguration"].map(s["std_skm"])
    out["belastbar"] = out["konfiguration"].map(s["belastbar"]).fillna(False).astype(bool)
    f = ordner(base) / "going_allowances.parquet"
    if f.exists():
        ga = pd.read_parquet(f)
        schluessel = lambda b, d, g: b.astype(str) + "_" + pd.to_datetime(d.astype(str), format="mixed").dt.strftime("%Y-%m-%d") + "_" + g
        ga_map = pd.Series(ga["ga_skm"].to_numpy(), index=schluessel(ga["bahn"], ga["date"], ga["boden"].astype(str)))
        k = schluessel(r["bahn"], r["date"], r["going_klasse"].fillna("UNBEKANNT").astype(str))
        out["ga_skm"] = k.map(ga_map).to_numpy()
    else:
        out["ga_skm"] = np.nan
    return out.dropna(subset=["std_skm"]).reset_index(drop=True)


def laden_standards(base: Path) -> pd.DataFrame:
    f = ordner(Path(base)) / "standards.parquet"
    return pd.read_parquet(f) if f.exists() else pd.DataFrame()
