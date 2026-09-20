"""
Ablauf je Lauf – PMU zuerst, France Galop danach.

run(start, ende, base, pdf_dir)
    Arbeitet von **heute rückwärts** bis `start`, höchstens `max_tage` neue Tage
    pro Lauf, und merkt sich den Fortschritt in <base>/fortschritt.json.

Pro Tag:
    1. PMU-Programm holen  -> französische Flachrennen, die bereits gelaufen sind
    2. Rennen + Starter    -> pmu_races / pmu_runners
    3. je Rennen bei France Galop nachsehen, ob es ein Tracking-PDF gibt
                           -> tracking_status (eine Zeile je Rennen, mit/ohne Tracking)
    4. gefundene PDFs auswerten
                           -> tracking_races / tracking_runners / tracking_sections / tracking_leader

Alles landet als Parquet unter <base>/parquet/<tabelle>/<JJJJMMTT>.parquet,
also in Google Drive, wenn `base` auf einen Drive-Ordner zeigt.

Ein Tag gilt nicht als abgeschlossen, solange noch Rennen ohne Tracking-PDF
offen sind: France Galop veröffentlicht die Dateien teils mit Verzögerung.
Deshalb werden Tage der letzten `nachzuegler_tage` bei jedem Lauf erneut
angefragt – und zwar nur für die Rennen, die noch fehlen.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

import france_galop as fg
import parse_tracking as pt
import pmu

TABELLEN = ["pmu_races", "pmu_runners", "tracking_status", "tracking_races", "tracking_runners",
            "tracking_sections", "tracking_obstacles", "tracking_leader", "fehler"]


# --------------------------------------------------------------------------
# Fortschritt
# --------------------------------------------------------------------------
def _state_path(base: Path) -> Path:
    return Path(base) / "fortschritt.json"


def fortschritt(base: Path) -> dict:
    p = _state_path(base)
    return json.loads(p.read_text()) if p.exists() else {}


def _save_state(base: Path, state: dict) -> None:
    p = _state_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1, sort_keys=True))


def parser_version() -> str:
    """Prüfsumme von parse_tracking.py – ändert sich bei jedem Parser-Update."""
    return hashlib.md5(Path(pt.__file__).read_bytes()).hexdigest()[:10]


def zuruecksetzen(tage: list[str], base: Path) -> None:
    """Tage erneut abholen lassen, z. B. zuruecksetzen(['2026-09-17'], BASE)."""
    state = fortschritt(base)
    for t in tage:
        state.pop(pd.to_datetime(t).strftime("%Y%m%d"), None)
    _save_state(base, state)
    print(f"{len(tage)} Tag(e) zurückgesetzt – beim nächsten Lauf werden sie neu geholt.")


def reset(base: Path, *, pdfs_loeschen: bool = False, codes_loeschen: bool = False) -> None:
    """Historie neu starten: löscht Fortschritt und alle Parquet-Dateien.
    PDFs bleiben standardmäßig liegen (werden dann nur neu ausgewertet).
    Gelernte Bahncodes bleiben ebenfalls, außer codes_loeschen=True."""
    base = Path(base)
    _state_path(base).unlink(missing_ok=True)
    shutil.rmtree(base / "parquet", ignore_errors=True)
    if pdfs_loeschen:
        shutil.rmtree(base / "pdfs", ignore_errors=True)
    if codes_loeschen:
        (base / "track_codes.csv").unlink(missing_ok=True)
    print("Zurückgesetzt: Fortschritt und Parquet gelöscht"
          + (", PDFs gelöscht" if pdfs_loeschen else ", PDFs behalten")
          + (", Bahncodes gelöscht" if codes_loeschen else ", Bahncodes behalten") + ".")


# --------------------------------------------------------------------------
# Parquet
# --------------------------------------------------------------------------
def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Spalten mit gemischten Typen als Text speichern (sonst scheitert Parquet)."""
    df = df.copy()
    for c in df.columns[df.dtypes == object]:
        types = {type(v) for v in df[c].dropna()}
        if len(types) > 1 or (types and not types <= {str}):
            df[c] = df[c].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
    return df


def _write(base: Path, tabelle: str, ymd: str, rows) -> int:
    folder = Path(base) / "parquet" / tabelle
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / f"{ymd}.parquet"
    df = pd.DataFrame(rows)
    if df.empty:
        f.unlink(missing_ok=True)
        return 0
    _clean(df).to_parquet(f, index=False)
    return len(df)


def lade(tabelle: str, base: Path) -> pd.DataFrame:
    """Alle Tagesdateien einer Tabelle zu einem DataFrame zusammenfassen."""
    folder = Path(base) / "parquet" / tabelle
    files = sorted(folder.glob("*.parquet")) if folder.exists() else []
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _bool(spalte: pd.Series) -> pd.Series:
    """'tracking' robust als Wahrheitswert lesen – auch wenn Parquet Text geliefert hat."""
    if spalte.dtype == bool:
        return spalte
    return spalte.map(lambda v: str(v).strip().lower() in ("true", "1", "ja", "yes"))


def _tages_tabelle(base: Path, tabelle: str, ymd: str) -> pd.DataFrame:
    f = Path(base) / "parquet" / tabelle / f"{ymd}.parquet"
    return pd.read_parquet(f) if f.exists() else pd.DataFrame()


# --------------------------------------------------------------------------
# PDFs eines Tages auswerten
# --------------------------------------------------------------------------
def pdfs_auswerten(ymd: str, base: Path, pdf_dir: Path) -> dict:
    """Wertet die Tracking-PDFs aus, die zu den Rennen dieses Tages gehören.

    Die Zuordnung PDF -> race_id kommt aus tracking_status, damit Tracking- und
    PMU-Tabellen dieselbe Rennkennung benutzen. Braucht kein Internet.
    """
    status = _tages_tabelle(base, "tracking_status", ymd)
    t = {k: [] for k in ("races", "leader", "runners", "sections", "obstacles", "errors")}
    if status.empty:
        return {k: _write(base, n, ymd, []) for k, n in
                (("races", "tracking_races"), ("runners", "tracking_runners"),
                 ("sections", "tracking_sections"), ("obstacles", "tracking_obstacles"),
                 ("leader", "tracking_leader"), ("errors", "fehler"))} | {"parser": parser_version()}

    treffer = status[_bool(status["tracking"])]
    for _, z in treffer.iterrows():
        f = Path(pdf_dir) / str(z["pdf"])
        if not f.exists():
            t["errors"].append({"race_id": z["race_id"], "date": ymd, "error": f"PDF fehlt: {f.name}"})
            continue
        try:
            r = pt.parse_pdf(f, race_id=z["race_id"])
        except Exception as e:
            t["errors"].append({"race_id": z["race_id"], "date": ymd, "error": f"{f.name}: {e}"})
            continue
        r["race"].update({"date_ymd": ymd, "hippodrome_pmu": z["hippodrome"], "fg_code": z["fg_code"],
                          "reunion": z["reunion"], "race_no_pmu": z["race_no"]})
        t["races"].append(r["race"])
        t["leader"] += r["leader"]
        t["runners"] += r["runners"]
        t["sections"] += r["sections"]
        t["obstacles"] += r.get("obstacles", [])
        t["errors"] += [{"date": ymd, **e} for e in r["errors"]]
    return {
        "tracking_races": _write(base, "tracking_races", ymd, t["races"]),
        "tracking_runners": _write(base, "tracking_runners", ymd, t["runners"]),
        "tracking_sections": _write(base, "tracking_sections", ymd, t["sections"]),
        "tracking_obstacles": _write(base, "tracking_obstacles", ymd, t["obstacles"]),
        "tracking_leader": _write(base, "tracking_leader", ymd, t["leader"]),
        "fehler": _write(base, "fehler", ymd, t["errors"]),
        "parser": parser_version(),
    }


def neu_auswerten(base: Path, pdf_dir: Path, *, nur_fehlertage: bool = True) -> pd.DataFrame:
    """PDFs erneut auswerten (ohne Download), z. B. nach einem Parser-Update.
    (Vorher im Notebook die Vorbereitungszelle laufen lassen, damit der neue
    Parser auch wirklich geladen ist.)"""
    state = fortschritt(base)
    if nur_fehlertage:
        tage = sorted(k for k, v in state.items() if v.get("fehler", 0) > 0)
    else:
        tage = sorted(f.stem for f in (Path(base) / "parquet" / "tracking_status").glob("*.parquet"))
    out = []
    for ymd in tage:
        n = pdfs_auswerten(ymd, base, pdf_dir)
        state.setdefault(ymd, {}).update(n)
        out.append({"tag": ymd, **n})
        print(f"{ymd}: {n['tracking_runners']} Tracking-Starter, {n['fehler']} Fehler")
    _save_state(base, state)
    return pd.DataFrame(out)


# --------------------------------------------------------------------------
# Ein Tag
# --------------------------------------------------------------------------
def tag_verarbeiten(tag: date, base: Path, pdf_dir: Path, *, nur_flach: bool = True,
                    nur_gelaufen: bool = True, pause: float = 0.3, code_suche: bool = True,
                    log=print) -> dict | None:
    """Einen Renntag komplett verarbeiten. None = PMU-Programm nicht erreichbar."""
    base, pdf_dir = Path(base), Path(pdf_dir)
    ymd = tag.strftime("%Y%m%d")
    s = requests.Session()

    # 1) PMU: welche Rennen gab es überhaupt?
    meets = pmu.meetings(tag, s, nur_flach=nur_flach, nur_gelaufen=nur_gelaufen)
    if meets is None:
        return None
    if not meets:
        for tab in TABELLEN:
            _write(base, tab, ymd, [])
        return {"am": datetime.now().isoformat(timespec="seconds"), "pmu": True, "rennen": 0,
                "mit_tracking": 0, "offen": [], "bahnen": [], "parser": parser_version()}

    # 2) Rennen + Starter aus dem PMU-Programm
    races, runners = pmu.starter(tag, s, meets, pause=pause)
    n_races = _write(base, "pmu_races", ymd, races)
    n_runners = _write(base, "pmu_runners", ymd, pmu.add_lengths(pd.DataFrame(runners)).to_dict("records"))

    # 3) je Rennen bei France Galop nach dem Tracking-PDF sehen
    store = fg.CodeStore(base)
    status = fg.tracking_fuer_tag(tag, meets, s, store, pdf_dir, pause=pause,
                                  code_suche=code_suche, log=log)
    _write(base, "tracking_status", ymd, status)

    # 4) gefundene PDFs auswerten
    n = pdfs_auswerten(ymd, base, pdf_dir)

    offen = [z["race_id"] for z in status if not z["tracking"]]
    offen_bahnen = sorted({(z["hippodrome"], z["pmu_code"]) for z in status
                           if not z["tracking"] and not z["fg_code"]})
    return {"am": datetime.now().isoformat(timespec="seconds"), "pmu": True,
            "neue_codes": store.gelernt,
            "rennen": len(status), "mit_tracking": sum(z["tracking"] for z in status),
            "offen": offen, "offen_bahnen": [list(x) for x in offen_bahnen], "bahnen": sorted({m["hippodrome"] for m in meets}),
            "pmu_races": n_races, "pmu_runners": n_runners, **n}


# --------------------------------------------------------------------------
# Lauf
# --------------------------------------------------------------------------
def _key(d: date) -> str:
    return d.strftime("%Y%m%d")


def offene_tage(start, ende=None, base: Path = None) -> list[date]:
    """Noch nie abgeholte Tage, neueste zuerst."""
    state = fortschritt(base)
    return [d for d in pmu.tage_rueckwaerts(start, ende) if _key(d) not in state]


def _offen_bahnen(k: str, state: dict, base: Path) -> list[list[str]]:
    """Bahnen, wegen deren unbekanntem Code an diesem Tag Rennen offen blieben.
    Steht der Eintrag noch nicht im Fortschritt (Tage aus älteren Ständen), wird er
    einmalig aus der Tagesdatei nachgetragen – danach kostet die Prüfung nichts mehr."""
    if "offen_bahnen" in state[k]:
        return state[k]["offen_bahnen"]
    st = _tages_tabelle(base, "tracking_status", k)
    if st.empty:
        state[k]["offen_bahnen"] = []
        return []
    luecke = st[(st["fg_code"].fillna("") == "") & (~_bool(st["tracking"]))]
    codes = (luecke["pmu_code"].fillna("") if "pmu_code" in luecke.columns
             else pd.Series([""] * len(luecke), index=luecke.index))
    state[k]["offen_bahnen"] = sorted({(h, c) for h, c in zip(luecke["hippodrome"], codes)})
    state[k]["offen_bahnen"] = [list(x) for x in state[k]["offen_bahnen"]]
    return state[k]["offen_bahnen"]


def _tage_mit_nachtrag(zeitraum: list[date], state: dict, base: Path) -> list[date]:
    """Bereits erledigte Tage, deren offene Rennen auf Bahnen liegen, für die
    inzwischen ein France-Galop-Code bekannt ist."""
    store = fg.CodeStore(base)
    out = []
    for d in zeitraum:
        k = _key(d)
        if k not in state or not state[k].get("offen"):
            continue
        if any(store.code(h, c) for h, c in _offen_bahnen(k, state, base)):
            out.append(d)
    return out


def run(start, ende=None, *, base: Path, pdf_dir: Path, max_tage: int = 10,
        nur_flach: bool = True, nur_gelaufen: bool = True, pause: float = 0.3,
        nachzuegler_tage: int = 10, code_suche: bool = True) -> pd.DataFrame:
    """Ein Lauf, immer von heute rückwärts:

    0) Tage mit Parser-Fehlern neu auswerten, falls sich der Parser geändert hat
    1) Tage, an denen das PMU-Programm nicht erreichbar war, nachholen
    2) Tage der letzten `nachzuegler_tage` Tage: fehlende Tracking-PDFs erneut abfragen
       (heute und gestern gehören immer dazu – da laufen noch Rennen bzw. fehlen PDFs)
    3) bis zu `max_tage` noch nicht abgeholte Tage, von heute rückwärts bis `start`
    """
    base, pdf_dir = Path(base), Path(pdf_dir)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    heute = pmu.heute()
    ende_d = min(pd.to_datetime(ende).date(), heute) if ende else heute
    zeitraum = list(pmu.tage_rueckwaerts(start, ende_d))          # neueste zuerst
    state = fortschritt(base)
    version = parser_version()
    bericht: list[dict] = []

    # 0) Fehler-Tage nach Parser-Update neu auswerten (ohne Download)
    reparse = [d for d in zeitraum if state.get(_key(d), {}).get("fehler", 0) > 0
               and state[_key(d)].get("parser") != version]
    if reparse:
        print(f"Parser geändert -> {len(reparse)} Tage mit Fehlern werden neu ausgewertet")
        for d in reparse:
            n = pdfs_auswerten(_key(d), base, pdf_dir)
            state[_key(d)].update(n)
            _save_state(base, state)
            print(f"{d}: {n['tracking_runners']} Tracking-Starter, {n['fehler']} Fehler")
            bericht.append({"tag": str(d), "status": "neu ausgewertet", **n})

    # Arbeitsvorrat
    grenze = heute - timedelta(days=max(nachzuegler_tage, 1))
    pmu_offen = [d for d in zeitraum if state.get(_key(d), {}).get("pmu") is False]
    nachzuegler = [d for d in zeitraum if d >= grenze and _key(d) in state
                   and d not in pmu_offen
                   and (state[_key(d)].get("offen") or d >= heute - timedelta(days=1))]
    neu = [d for d in zeitraum if _key(d) not in state][:max_tage]

    pmu_fehler_folge = 0
    neu_gelernt: set[tuple[str, str]] = set()

    def verarbeite(d: date, art: str) -> bool:
        """True = weitermachen, False = PMU streikt, Lauf abbrechen."""
        nonlocal pmu_fehler_folge
        try:
            res = tag_verarbeiten(d, base, pdf_dir, nur_flach=nur_flach, nur_gelaufen=nur_gelaufen,
                                  pause=pause, code_suche=code_suche)
        except Exception as e:
            print(f"{d}: FEHLER {e} – wird beim nächsten Lauf erneut versucht")
            bericht.append({"tag": str(d), "status": "FEHLER", "fehler_text": str(e)})
            return True
        if res is None:
            pmu_fehler_folge += 1
            state.setdefault(_key(d), {})["pmu"] = False
            _save_state(base, state)
            print(f"{d}: PMU-Programm nicht erreichbar ({pmu.LETZTER_FEHLER})")
            bericht.append({"tag": str(d), "status": "PMU nicht erreichbar"})
            if pmu_fehler_folge >= 3:
                print("   ! PMU dreimal hintereinander nicht erreichbar – Lauf beendet, "
                      "beim nächsten Lauf geht es weiter.")
                return False
            return True
        pmu_fehler_folge = 0
        neu_gelernt.update(res.pop("neue_codes", []))
        alt = state.get(_key(d), {})
        state[_key(d)] = {**alt, **res}
        _save_state(base, state)
        offen = len(res["offen"])
        print(f"{d} [{art}]: {res['rennen']} Flachrennen · {res['mit_tracking']} mit Tracking"
              + (f" · {offen} ohne" if offen else "")
              + f" · {res.get('tracking_runners', 0)} Tracking-Starter"
              + f" · {res.get('pmu_runners', 0)} PMU-Starter"
              + (f" · {res['fehler']} Parser-Fehler" if res.get("fehler") else ""))
        bericht.append({"tag": str(d), "status": art, "rennen": res["rennen"],
                        "mit_tracking": res["mit_tracking"], "ohne_tracking": offen,
                        "pmu_runners": res.get("pmu_runners", 0),
                        "tracking_runners": res.get("tracking_runners", 0),
                        "fehler": res.get("fehler", 0)})
        return True

    if pmu_offen:
        print(f"\nPMU nachholen: {len(pmu_offen)} Tage")
        for d in pmu_offen[:max_tage]:
            if not verarbeite(d, "PMU nachgeholt"):
                return pd.DataFrame(bericht)

    if nachzuegler:
        print(f"\nNachzügler prüfen: {len(nachzuegler)} Tage (fehlende Tracking-PDFs erneut abfragen)")
        for d in nachzuegler:
            if not verarbeite(d, "nachzügler"):
                return pd.DataFrame(bericht)

    if neu:
        print(f"\nNeue Tage: {neu[0]} rückwärts bis {neu[-1]} ({len(neu)} Tage)")
        for d in neu:
            if not verarbeite(d, "neu"):
                return pd.DataFrame(bericht)

    # 4) Wurde unterwegs ein Bahncode gelernt, können frühere Tage Lücken haben,
    #    die jetzt zu schließen sind – auch außerhalb des Nachzügler-Fensters.
    if neu_gelernt:
        print(f"\nNeue Bahncodes gelernt: {', '.join(sorted(f'{h} = {c}' for h, c in neu_gelernt))}")
    nachtrag = _tage_mit_nachtrag(zeitraum, state, base)
    _save_state(base, state)
    if nachtrag:
        print(f"\nBahncode inzwischen bekannt -> {len(nachtrag)} frühere Tage nachtragen"
              + (f" (davon {max_tage} in diesem Lauf)" if len(nachtrag) > max_tage else ""))
        for d in nachtrag[:max_tage]:
            if not verarbeite(d, "Bahncode nachgetragen"):
                break

    if not bericht:
        print("Alles aktuell – nichts zu tun.")
    rest = sum(_key(d) not in state for d in zeitraum)
    ohne = sum(len(state.get(_key(d), {}).get("offen") or []) for d in zeitraum)
    print(f"\nStand {zeitraum[-1] if zeitraum else start} bis {ende_d}: "
          f"offen {rest} Tage" + (f" (ca. {-(-rest // max(max_tage, 1))} Läufe)" if rest else "")
          + f" · Rennen ohne Tracking-PDF: {ohne}")
    return pd.DataFrame(bericht)


# --------------------------------------------------------------------------
# Auswertung / Kontrolle
# --------------------------------------------------------------------------
def abdeckung(base: Path, nach: str = "hippodrome") -> pd.DataFrame:
    """Wie viele der gelaufenen Flachrennen haben ein Tracking-PDF – je Bahn (oder Monat)."""
    st = lade("tracking_status", base)
    if st.empty:
        return pd.DataFrame()
    st = st.copy()
    st["tracking"] = _bool(st["tracking"])
    st["monat"] = st["date"].astype(str).str[:6]
    g = st.groupby(nach).agg(rennen=("race_id", "count"), mit_tracking=("tracking", "sum"),
                             renntage=("date", "nunique"))
    g["quote_%"] = (g["mit_tracking"] / g["rennen"] * 100).round(1)
    return g.sort_values("rennen", ascending=False)


def ohne_tracking(base: Path) -> pd.DataFrame:
    """Alle gelaufenen Flachrennen, für die kein Tracking-PDF gefunden wurde."""
    st = lade("tracking_status", base)
    if st.empty:
        return st
    return st[~_bool(st["tracking"])].sort_values(["date", "hippodrome", "race_no"])


def bahnen_nachpruefen(base: Path, pdf_dir: Path, *, pause: float = 0.3,
                       max_tage: int | None = None) -> pd.DataFrame:
    """Für alle bereits erledigten Tage die Bahnen ohne bekannten Code erneut prüfen.

    Sinnvoll, wenn ein Bahncode inzwischen gelernt wurde oder eine Bahn neu
    Tracking bekommen hat. Gefundene PDFs werden geladen und der Tag neu ausgewertet.
    """
    base, pdf_dir = Path(base), Path(pdf_dir)
    state = fortschritt(base)
    store = fg.CodeStore(base)
    tage = sorted(state, reverse=True)[: max_tage or len(state)]
    s = requests.Session()
    out, pmu_fehler = [], 0
    print(f"Prüfe {len(tage)} erledigte Tage …")
    for ymd in tage:
        st = _tages_tabelle(base, "tracking_status", ymd)
        if st.empty:
            continue
        # Bahnen ohne Code, für die es inzwischen einen gelernten Code gibt oder die neu gesucht werden dürfen
        tag = datetime.strptime(ymd, "%Y%m%d").date()
        ohne_code = sorted(set(st.loc[st["fg_code"].fillna("") == "", "hippodrome"]))
        pruefen = [h for h in ohne_code if store.code(h) or store.soll_suchen(h, tag, force=True)]
        if not pruefen:
            continue
        meets = pmu.meetings(tag, s)
        if meets is None:
            pmu_fehler += 1
            if pmu_fehler >= 3:
                print(f"PMU nicht erreichbar ({pmu.LETZTER_FEHLER}) – Abbruch, später erneut ausführen.")
                break
            continue
        pmu_fehler = 0
        meets = [m for m in meets if m["hippodrome"] in pruefen]
        if not meets:
            continue
        neu_status = fg.tracking_fuer_tag(tag, meets, s, store, pdf_dir, pause=pause)
        rest = st[~st["hippodrome"].isin([m["hippodrome"] for m in meets])]
        _write(base, "tracking_status", ymd, pd.concat([rest, pd.DataFrame(neu_status)],
                                                       ignore_index=True).to_dict("records"))
        n = pdfs_auswerten(ymd, base, pdf_dir)
        gefunden = sum(z["tracking"] for z in neu_status)
        state.setdefault(ymd, {}).update(n)
        state[ymd]["offen"] = [z["race_id"] for z in neu_status if not z["tracking"]] + \
                              list(rest.loc[~_bool(rest["tracking"]), "race_id"])
        _save_state(base, state)
        if gefunden:
            print(f"{tag}: {gefunden} Tracking-PDFs nachgetragen ({', '.join(m['hippodrome'] for m in meets)})")
            out.append({"tag": str(tag), "bahnen": ", ".join(m["hippodrome"] for m in meets),
                        "neu": gefunden, **n})
    print("Fertig.")
    return pd.DataFrame(out)
