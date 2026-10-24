"""PMU-Prognosen (cote probable, Presse-Tipps) als eigene Tabelle – für die Prognose-Schicht der fairen Quote.

    import prognose_basis as pb
    pb.nachholen_rueckwaerts(BASE)            # einmalig: ab gestern zurück, bis 7 Renntage in Folge ohne Prognose

Je Tag eine Datei <BASE>/parquet/pmu_prognosen/<JJJJMMTT>.parquet, je Starter:
    race_id, saddle_no, prono_rang (Platz in der Auswahl), prono_cote (cote probable dezimal),
    tipps_n (Tippgeber, die das Pferd nennen), tipps_von (Tippgeber im Rennen), tipps_pos (Ø Position in deren Listen)
Die Prognose steht am Vortag/Morgen fest – auf der Karte und im Training dieselbe. Jede Karte (racecard.run) schreibt
ihre Prognosen ebenfalls hierher. Bereits vorhandene Tage werden beim Nachholen übersprungen (neu=True: erneut).
"""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import pmu

TABELLE = "pmu_prognosen"
SPALTEN = ["race_id", "saddle_no", "prono_rang", "prono_cote", "tipps_n", "tipps_von", "tipps_pos"]


def _sitzung() -> requests.Session:
    s = requests.Session()
    if hasattr(s, "headers"):
        s.headers.update(pmu.HEADERS)
    return s


def zeilen(tag: date, prognosen: dict) -> pd.DataFrame:
    """{(Reunion, Rennen): pmu.prognose(...)} -> eine Zeile je Starter mit Auswahl oder Tipp."""
    out = []
    for (r, c), pg in (prognosen or {}).items():
        rid = f"{pd.Timestamp(tag):%Y%m%d}R{int(r)}C{int(c)}"
        je: dict[int, dict] = {}
        for z in pg.get("selection") or []:
            je.setdefault(int(z["no"]), {}).update({"prono_rang": z.get("rank"), "prono_cote": z.get("cote_dec")})
        tipps = pg.get("tips") or []
        for t in tipps:
            for pos, no in enumerate(t["nos"], 1):
                e = je.setdefault(int(no), {})
                e["tipps_n"] = e.get("tipps_n", 0) + 1
                e.setdefault("_pos", []).append(pos)
        for no, e in je.items():
            out.append({"race_id": rid, "saddle_no": no, "prono_rang": e.get("prono_rang"),
                        "prono_cote": e.get("prono_cote"), "tipps_n": e.get("tipps_n", 0), "tipps_von": len(tipps),
                        "tipps_pos": float(np.mean(e["_pos"])) if e.get("_pos") else np.nan})
    d = pd.DataFrame(out, columns=SPALTEN)
    for c in SPALTEN[1:]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def speichern(base: Path, tag: date, prognosen: dict) -> int:
    """Prognosen eines Tages in die Tabelle schreiben (überschreibt den Tag); Rückgabe: Zeilen."""
    d = zeilen(tag, prognosen)
    if d.empty:
        return 0
    ordner = Path(base) / "parquet" / TABELLE
    ordner.mkdir(parents=True, exist_ok=True)
    d.to_parquet(ordner / f"{pd.Timestamp(tag):%Y%m%d}.parquet", index=False)
    return len(d)


def nachholen(base: Path, von, bis=None, *, neu: bool = False, pause: float = 0.3, log=print) -> pd.DataFrame:
    """Prognosen für alle Tage von … bis (Vorgabe: gestern) holen und speichern; vorhandene Tage überspringen."""
    s = _sitzung()
    ende = pd.Timestamp(bis).date() if bis else (pd.Timestamp(pmu.heute()) - pd.Timedelta(days=1)).date()
    ordner = Path(base) / "parquet" / TABELLE
    bericht = []
    for tag in pd.date_range(pd.Timestamp(von), pd.Timestamp(ende), freq="D").date:
        if not neu and (ordner / f"{tag:%Y%m%d}.parquet").exists():
            continue
        meets = pmu.meetings(tag, s, nur_flach=True, nur_gelaufen=True)
        if not meets:
            bericht.append({"tag": tag, "rennen": 0, "mit_prognose": 0, "starter": 0})
            continue
        rennen = [(m["reunion"], pmu.race_no(c)) for m in meets for c in m["courses"]]
        pg = pmu.prognosen(tag, s, rennen, pause=pause)
        n = speichern(base, tag, pg)
        bericht.append({"tag": tag, "rennen": len(rennen), "mit_prognose": len(pg), "starter": n})
        log(f"{tag}: {len(pg)} von {len(rennen)} Rennen mit Prognose, {n} Starter")
        time.sleep(pause)
    return pd.DataFrame(bericht)


def nachholen_rueckwaerts(base: Path, ab=None, *, stopp_tage: int = 7, pause: float = 0.3, log=print) -> pd.DataFrame:
    """Ab `ab` (Vorgabe: gestern) Tag für Tag zurück nachholen, bis an STOPP_TAGE Renntagen in Folge keine Prognose
    mehr kommt (PMU hält sie nur eine Zeit lang vor). Tage ohne Flachrennen zählen nicht; schon gespeicherte Tage
    werden nicht erneut abgefragt (zählen als „mit Prognose“)."""
    s = _sitzung()
    tag = pd.Timestamp(ab).date() if ab else (pd.Timestamp(pmu.heute()) - pd.Timedelta(days=1)).date()
    ordner = Path(base) / "parquet" / TABELLE
    bericht, leer_folge = [], 0
    while leer_folge < stopp_tage:
        datei = ordner / f"{tag:%Y%m%d}.parquet"
        if datei.exists():
            leer_folge = 0
        else:
            meets = pmu.meetings(tag, s, nur_flach=True, nur_gelaufen=True)
            if meets:
                rennen = [(m["reunion"], pmu.race_no(c)) for m in meets for c in m["courses"]]
                pg = pmu.prognosen(tag, s, rennen, pause=pause)
                n = speichern(base, tag, pg)
                bericht.append({"tag": tag, "rennen": len(rennen), "mit_prognose": len(pg), "starter": n})
                leer_folge = 0 if pg else leer_folge + 1
                log(f"{tag}: {len(pg)} von {len(rennen)} Rennen mit Prognose, {n} Starter"
                    + (f" – {leer_folge}. Renntag in Folge ohne Prognose" if not pg else ""))
                time.sleep(pause)
        tag = tag - pd.Timedelta(days=1)
    log(f"Ende: {stopp_tage} Renntage in Folge ohne Prognose – frühester Tag mit Prognose "
        f"{min((b_['tag'] for b_ in bericht if b_['mit_prognose']), default='–')}")
    return pd.DataFrame(bericht)


def anfuegen(h: pd.DataFrame, prog: pd.DataFrame | None) -> pd.DataFrame:
    """Prognose-Spalten an Starterzeilen (race_id, saddle_no) hängen; ohne Tabelle leere Spalten."""
    h = h.drop(columns=[c for c in SPALTEN[2:] if c in h])
    if prog is None or not len(prog):
        for c in SPALTEN[2:]:
            h[c] = np.nan
        return h
    p = prog[SPALTEN].copy()
    p["race_id"] = p["race_id"].astype(str)
    p["saddle_no"] = pd.to_numeric(p["saddle_no"], errors="coerce")
    p = p.drop_duplicates(["race_id", "saddle_no"], keep="last")
    sn = pd.to_numeric(h["saddle_no"], errors="coerce")
    m = pd.DataFrame({"race_id": h["race_id"].astype(str).to_numpy(), "saddle_no": sn.to_numpy()}).merge(
        p, on=["race_id", "saddle_no"], how="left")
    for c in SPALTEN[2:]:
        h[c] = m[c].to_numpy()
    return h


def merkmale(h: pd.DataFrame) -> pd.DataFrame:
    """Merkmale der Prognose-Schicht je Starter (Index wie h): pr_lp = log Prognose-Chance (1/cote, je Rennen auf 1)
    minus Ø im Rennen, pr_tipp = Anteil der Tippgeber, die das Pferd nennen. NaN, wo das Rennen keine vollständige
    Auswahl mit Cote bzw. keine Tipps hat."""
    rid = h["race_id"].astype(str)
    q = pd.to_numeric(h.get("prono_cote"), errors="coerce") if "prono_cote" in h else pd.Series(np.nan, index=h.index)
    inv = (1 / q).where(q > 1)
    voll = inv.notna().groupby(rid).transform("all")
    lp = np.log(inv / inv.groupby(rid).transform("sum"))
    lp = (lp - lp.groupby(rid).transform("mean")).where(voll)
    tn = pd.to_numeric(h.get("tipps_n"), errors="coerce") if "tipps_n" in h else pd.Series(np.nan, index=h.index)
    tv = pd.to_numeric(h.get("tipps_von"), errors="coerce") if "tipps_von" in h else pd.Series(np.nan, index=h.index)
    tv = tv.groupby(rid).transform("max")
    tipp = (tn.fillna(0) / tv).where(tv > 0)
    return pd.DataFrame({"pr_lp": lp, "pr_tipp": tipp}, index=h.index)
