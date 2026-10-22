"""Value-Wetten-Simulation und Dashboard (für Google Colab).

Eingaben je Renntag (gepaart über YYYYMMDD im Dateinamen):
  * ``racecard_YYYYMMDD_daten.json`` – Power-Modell (``power.sieg``), Festkurse
    (``fk.sieg``/``fk.platz``) und Presse-Kurs (``prono.sel.cote_dec``),
  * ``YYYYMMDD.parquet`` aus ``pmu_races`` – Einlauf (``finish_order``).

Die Simulationsfunktionen sind rein (keine UI). ``dashboard`` schreibt eine
eigenständige HTML-Seite (wie die Racecard), in der dieselbe Simulation im
Browser läuft; ``start()`` baut sie aus der Drive-Ablage.

Hinweise:
  * Die Kurse sind Festkurse zum Stand ``festkurse_stand`` – keine Endkurse.
  * Kleine Stichproben (unter etwa 30 Wetten) sagen wenig aus.
  * Sehr hoher Wert (über 3) deutet oft auf einen Kursfehler hin.
"""
from __future__ import annotations

import json
import math
import re
import warnings
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

TOL = 1e-6              # Toleranz für Filtervergleiche
TOP_TOL = 1e-9          # Toleranz für „höchster Wert im Rennen“
START_BANK = 1000.0
STEUER = 0.05           # Steuer je Wett-Bein (Anteil am Einsatz)
GOLD_WERT = 1.2         # Ersatzregel, wenn power.gold fehlt
GOLD_MAX_COTE = 10.0
HARVILLE_L2, HARVILLE_L3 = 0.8, 0.65   # wie racecard.py
START_DATUM = "20261018"   # ab hier liegen Karten mit Festkursen vor
BASE_DRIVE = "/content/drive/MyDrive/PT_tracking"
HINWEIS_LEER = "keine Wette bei diesem Filter"
HINWEISE = (
    "Kurse = Festkurse zum Stand festkurse_stand, keine Endkurse.",
    "Unter etwa 30 Wetten ist das Ergebnis kaum belastbar.",
    "Wert über 3 deutet oft auf einen Kursfehler hin.",
)

MODI = ("max", "rank", "rel", "none")
TOP_WAHL = ("beides", "ja", "nein")
KELLY = {"kelly8": 1 / 8, "kelly4": 1 / 4, "kelly2": 1 / 2, "kelly1": 1.0}
VARIANTEN = (*KELLY, "level10", "level1p")
# Schieberegler je Modus: (min, max, Schritt, Vorgabe)
MODUS_REGLER = {
    "max": (5.0, 100.0, 5.0, 10.0),
    "rank": (0.0, 1.0, 0.05, 0.5),
    "rel": (0.0, 4.0, 0.1, 1.0),
}

_DATUM = re.compile(r"(\d{8})")


# ---------------------------------------------------------------- Hilfen

def round_half_up(x: float, stellen: int = 0) -> float:
    """Kaufmännisch runden (0,5 immer weg von null), über Decimal ohne Float-Rest."""
    q = Decimal(1).scaleb(-stellen)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def _zahl(x: Any) -> Optional[float]:
    """Endliche Zahl oder None."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _einlauf(finish_order: Any) -> Optional[list[int]]:
    """'2 - 8 - 3 - 9' → [2, 8, 3, 9]; leer/fehlend → None."""
    if finish_order is None or (isinstance(finish_order, float) and math.isnan(finish_order)):
        return None
    nums = [int(t) for t in re.findall(r"\d+", str(finish_order))]
    return nums or None


def _datum_aus_name(pfad: Path) -> Optional[str]:
    m = _DATUM.search(pfad.name)
    return m.group(1) if m else None


# ---------------------------------------------------------------- Laden

def harville_platz(p, plaetze: int, l2: float = HARVILLE_L2, l3: float = HARVILLE_L3) -> np.ndarray:
    """Platzchance je Starter aus den Siegchancen (Harville mit Korrektur, wie racecard.harville_platz)."""
    p = np.asarray(p, float)
    p = p / p.sum()
    n = len(p)
    if plaetze >= n:
        return np.ones(n)
    q2 = p ** l2
    q2 = q2 / q2.sum()
    A = p[:, None] * q2[None, :] / np.clip(1 - q2[:, None], 1e-12, None)
    np.fill_diagonal(A, 0.0)
    P = p + A.sum(axis=0)
    if plaetze >= 3:
        q3 = p ** l3
        q3 = q3 / q3.sum()
        nenner = 1 - q3[:, None] - q3[None, :]
        B = np.where(nenner > 1e-12, A / np.where(nenner > 1e-12, nenner, 1.0), 0.0)
        np.fill_diagonal(B, 0.0)
        P = P + q3 * (B.sum() - B.sum(axis=1) - B.sum(axis=0))
    return np.clip(P, 0.0, 1.0)


def _pferde_rennen(rennen: dict, datum: str) -> list[dict]:
    """Abgeleitete Werte für alle Starter eines Rennens (ohne Ergebnis)."""
    starter = []
    for r in rennen.get("runners") or []:
        pw = r.get("power") or {}
        sieg = _zahl(pw.get("sieg"))
        if r.get("nr") or sieg is None or sieg <= 0:
            continue
        starter.append((r, pw, sieg))
    if not starter:
        return []
    summe = sum(s for _, _, s in starter)
    n = len(starter)
    p = np.array([s / summe for _, _, s in starter])
    # Power allein (ohne Morgenquote) für den Test „Modell → Toto“: sieg_blind, ältere Karten nur sieg
    sb = [_zahl(pw.get("sieg_blind")) for _, pw, _ in starter]
    p_blind = (np.array(sb) / sum(sb)) if all(x is not None and x > 0 for x in sb) else p
    fair = 1.0 / p
    # Wettkampf-Rang (1, 2, 2, 4 …) nach fairer Quote aufsteigend
    rang = [1 + int(np.sum(fair < f - TOP_TOL)) for f in fair]
    plaetze = 3 if n >= 8 else 2
    p_platz = harville_platz(p, plaetze)

    zeilen = []
    for (r, pw, _), pi, fi, rg, pp, pbl in zip(starter, p, fair, rang, p_platz, p_blind):
        fk = r.get("fk") or {}
        fk_sieg = _zahl(fk.get("sieg"))
        fk_platz = _zahl(fk.get("platz"))
        if fk_sieg is not None and fk_sieg <= 1:
            fk_sieg = None
        if fk_platz is not None and fk_platz <= 1:
            fk_platz = None
        cote = _zahl(((r.get("prono") or {}).get("sel") or {}).get("cote_dec"))
        gold_roh = pw.get("gold")
        if gold_roh is not None:
            gold_modell = bool(gold_roh)
        else:
            pwert = _zahl(pw.get("wert"))
            gold_modell = pwert is not None and pwert >= GOLD_WERT - TOL
        gold = gold_modell and (cote is None or cote <= GOLD_MAX_COTE + TOL)
        zeilen.append({
            "date": datum,
            "race_id": rennen.get("race_id"),
            "race": f"R{rennen.get('reunion')}C{rennen.get('race_no')}",
            "course": rennen.get("course"),
            "no": int(r["no"]),
            "horse": r.get("horse"),
            "n": n,
            "p": float(pi),
            "fair": float(fi),
            "rank_fq": rg,
            "rank_pct": (n - rg) / (n - 1) if n > 1 else 1.0,
            "rel": float(pi * n),
            "fk_sieg": fk_sieg,
            "fk_platz": fk_platz,
            "cote_dec": cote,
            "wert": fk_sieg * pi - 1 if fk_sieg is not None else None,
            "gold": bool(gold),
            "p_fk": 1 / fk_sieg if fk_sieg is not None else None,
            "p_model": float(pi),
            "p_blind": float(pbl),
            "p_pq": 1 / fk_platz if fk_platz is not None else None,
            "p_platz": float(pp),
            "fair_platz": 1 / float(pp) if pp > 0 else None,
            "paid_places": plaetze,
        })
    # Top-Wert des Rennens – vor jedem Filter, alle Gleichstände
    werte = [z["wert"] for z in zeilen if z["wert"] is not None]
    top = max(werte) if werte else None
    for z in zeilen:
        z["is_top"] = int(z["wert"] is not None and top is not None
                          and abs(z["wert"] - top) <= TOP_TOL)
    return zeilen


def _karte_lesen(pfad: Path) -> dict:
    """Kartendaten aus ``racecard_*_daten.json`` oder aus der HTML-Karte (``const DATA = …``)."""
    text = pfad.read_text(encoding="utf-8")
    if pfad.suffix.lower() != ".html":
        return json.loads(text)
    marke = "const DATA = "
    i = text.find(marke)
    if i < 0:
        raise ValueError(f"{pfad.name}: keine Kartendaten (const DATA) gefunden")
    daten, _ = json.JSONDecoder().raw_decode(text, i + len(marke))
    return daten


def _endquoten(starter_path: str | Path | None) -> dict[tuple[str, int], float]:
    """Toto-Endquote (letzte Siegquote vor dem Start, pmu_runners.odds_final) je (race_id, Startnummer)."""
    if starter_path is None or not Path(starter_path).exists():
        return {}
    s = pd.read_parquet(starter_path, columns=["race_id", "saddle_no", "odds_final"])
    q = pd.to_numeric(s["odds_final"], errors="coerce")
    no = pd.to_numeric(s["saddle_no"], errors="coerce")
    ok = q.gt(1) & no.notna()
    return {(str(r), int(n)): float(x) for r, n, x in zip(s["race_id"][ok], no[ok], q[ok])}


def load_day(json_path: str | Path, parquet_path: str | Path | None,
             starter_path: str | Path | None = None) -> pd.DataFrame:
    """Pool eines Renntags: alle Starter mit Festkurs und Wert ≥ 0, samt Ergebnis.

    ``json_path`` darf auch die HTML-Karte ``racecard_YYYYMMDD.html`` sein – sie
    enthält dieselben Daten.

    Ohne Ergebnis-Parquet (oder ohne Einlauf für ein Rennen) bleiben ``pos``,
    ``won`` und ``placed`` leer und ``settled`` ist False – solche Wetten werden
    nicht simuliert (der Tag gilt als offen).

    ``starter_path``: pmu_runners-Parquet des Tages mit der Toto-Endquote. Daraus je Starter ``toto_end``,
    ``fk_toto`` (Festkurs ÷ Endquote; > 1 = Kurs bis zum Start gefallen) und ``kurs_rel`` (ln fk_toto minus
    Ø ln fk_toto aller Starter des Rennens – bereinigt den grundsätzlichen Abstand Festkurs ↔ Toto).
    """
    json_path = Path(json_path)
    daten = _karte_lesen(json_path)
    datum = str(daten.get("date") or _datum_aus_name(json_path) or "").replace("-", "")
    rennen = daten.get("races") or {}
    if isinstance(rennen, dict):
        rennen = list(rennen.values())

    zeilen: list[dict] = []
    for rn in rennen:
        zeilen.extend(_pferde_rennen(rn, datum))
    pool = pd.DataFrame(zeilen)
    if pool.empty:
        return _leerer_pool()
    pool["festkurse_stand"] = daten.get("festkurse_stand")
    endq = _endquoten(starter_path)
    pool["toto_end"] = [endq.get((str(r), int(n))) for r, n in zip(pool["race_id"], pool["no"])]
    pool["toto_end"] = pd.to_numeric(pool["toto_end"], errors="coerce")
    lv = np.log(pool["fk_sieg"].astype(float) / pool["toto_end"])
    pool["fk_toto"] = np.exp(lv)
    pool["kurs_rel"] = lv - lv.groupby(pool["race_id"]).transform("mean")       # alle Starter des Rennens
    pool = pool[pool["fk_sieg"].notna() & (pool["wert"] >= -TOP_TOL)].copy()

    einlauf: dict[str, list[int]] = {}
    if parquet_path is not None and Path(parquet_path).exists():
        erg = pd.read_parquet(parquet_path, columns=["race_id", "finish_order"])
        for rid, fo in zip(erg["race_id"], erg["finish_order"]):
            e = _einlauf(fo)
            if e:
                einlauf[str(rid)] = e

    def platz(row) -> Optional[int]:
        e = einlauf.get(str(row["race_id"]))
        if e is None:
            return None
        return e.index(row["no"]) + 1 if row["no"] in e else None

    pool["settled"] = pool["race_id"].astype(str).isin(einlauf)
    pool["pos"] = pool.apply(platz, axis=1).astype("Int64")
    pool["won"] = pool["settled"] & (pool["pos"] == 1).fillna(False)
    pool["placed"] = pool["settled"] & (pool["pos"] <= pool["paid_places"]).fillna(False)
    return pool.reset_index(drop=True)


def _leerer_pool() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "date", "race_id", "race", "course", "no", "horse", "n", "p", "fair", "rank_fq",
        "rank_pct", "rel", "fk_sieg", "fk_platz", "cote_dec", "wert", "gold", "p_fk",
        "p_model", "p_blind", "p_pq", "p_platz", "fair_platz", "paid_places", "is_top", "festkurse_stand",
        "toto_end", "fk_toto", "kurs_rel", "settled", "pos", "won", "placed"])


def _hat_endquote(pfad: Path) -> bool:
    """Ist das Parquet eine pmu_runners-Datei (Spalten race_id, saddle_no, odds_final)?"""
    try:
        import pyarrow.parquet as pq
        namen = set(pq.read_schema(pfad).names)
    except Exception:
        return False
    return {"race_id", "saddle_no", "odds_final"} <= namen


def _hat_einlauf(pfad: Path) -> bool:
    """Ist das Parquet eine pmu_races-Datei (Spalten race_id und finish_order)?"""
    try:
        import pyarrow.parquet as pq
        namen = set(pq.read_schema(pfad).names)
    except Exception:
        return False
    return {"race_id", "finish_order"} <= namen


def load_folder(ordner: str | Path, ergebnis_ordner: str | Path | None = None,
                cache: str | Path | None = None, ab: str | None = START_DATUM,
                bis: str | None = None, starter_ordner: str | Path | None = None) -> pd.DataFrame:
    """Alle Renntage eines Ordners laden (rekursiv), gepaart über das Datum.

    ``ergebnis_ordner``: wo die pmu_races-Parquets liegen (Vorgabe: ``ordner``).
    ``starter_ordner``: pmu_runners-Parquets mit der Toto-Endquote (Vorgabe: Nachbarordner ``pmu_runners`` des
    Ergebnisordners, sonst der Ergebnisordner selbst).
    ``ab``/``bis``: Zeitraum als YYYYMMDD (Vorgabe: ab ``START_DATUM``, ``None`` = alle).

    Karte: ``racecard_YYYYMMDD_daten.json``, sonst ``racecard_YYYYMMDD.html``;
    Ergebnis: ``*YYYYMMDD*.parquet`` (bei mehreren gewinnt eines in einem Ordner
    ``pmu_races``). Fehlt das Ergebnis eines Tages, gibt es eine Warnung und der
    Tag bleibt offen. Mit ``cache`` wird der Pool zusätzlich als Parquet gespeichert.
    """
    ordner = Path(ordner)
    jsons: dict[str, Path] = {}
    for p in sorted(ordner.rglob("racecard_*.html")):
        if re.fullmatch(r"racecard_\d{8}\.html", p.name):
            jsons[p.name[9:17]] = p
    for p in sorted(ordner.rglob("racecard_*_daten.json")):
        d = _datum_aus_name(p)
        if d:
            jsons[d] = p          # JSON vor HTML
    jsons = {d: p for d, p in jsons.items()
             if (ab is None or d >= str(ab).replace("-", ""))
             and (bis is None or d <= str(bis).replace("-", ""))}
    heute = pd.Timestamp.now().strftime("%Y%m%d")
    parquets = {}
    erg_ordner = Path(ergebnis_ordner) if ergebnis_ordner is not None else ordner
    for p in sorted(erg_ordner.rglob("*.parquet"), key=lambda q: "pmu_races" not in q.parts):
        d = _datum_aus_name(p)
        if (d and d in jsons and d not in parquets and _hat_einlauf(p)
                and (cache is None or p.resolve() != Path(cache).resolve())):
            parquets[d] = p
    if starter_ordner is None:
        nachbar = erg_ordner.parent / "pmu_runners"
        starter_ordner = nachbar if nachbar.is_dir() else erg_ordner
    starter = {}
    for p in sorted(Path(starter_ordner).rglob("*.parquet"), key=lambda q: "pmu_runners" not in q.parts):
        d = _datum_aus_name(p)
        if d and d in jsons and d not in starter and _hat_endquote(p):
            starter[d] = p
    teile = []
    for d in sorted(jsons):
        if d not in parquets and d < heute:
            warnings.warn(f"{d}: kein Ergebnis-Parquet – Tag bleibt offen", stacklevel=2)
        tag = load_day(jsons[d], parquets.get(d), starter.get(d))
        if d in parquets and d < heute and not tag.empty and not tag["settled"].all():
            offen = tag.loc[~tag["settled"], "race"].unique()
            warnings.warn(f"{d}: kein Einlauf für {', '.join(offen)}", stacklevel=2)
        teile.append(tag)
    pool = pd.concat(teile, ignore_index=True) if teile else _leerer_pool()
    if cache is not None:
        pool.to_parquet(cache, index=False)
    return pool


# ---------------------------------------------------------------- Simulation

@dataclass
class FilterConfig:
    """Auswahl der Wetten.

    minw: Mindest-Wert (0–1,5); gold_on: Gold-Pferde schon ab min(0,2; minw);
    mode: genau einer von "max" (faire Quote < X), "rank" (rank_pct ≥ X),
    "rel" (rel ≥ X) oder "none"; top: "beides", "ja" (nur Top-Wert) oder "nein".
    """
    minw: float = 0.5
    gold_on: bool = True
    mode: str = "max"
    mode_value: float = 10.0
    top: str = "beides"

    def __post_init__(self) -> None:
        if self.mode not in MODI:
            raise ValueError(f"mode muss einer von {MODI} sein")
        if self.top not in TOP_WAHL:
            raise ValueError(f"top muss einer von {TOP_WAHL} sein")


@dataclass
class StakingConfig:
    """Einsatz-Variante: kelly8/kelly4/kelly2/kelly1, level10 (10 €) oder level1p (1 %)."""
    variant: str = "kelly4"
    start_bank: float = START_BANK

    def __post_init__(self) -> None:
        if self.variant not in VARIANTEN:
            raise ValueError(f"variant muss einer von {VARIANTEN} sein")


@dataclass
class SimResult:
    """Ergebnis: Wetten, Tagesverlauf und Kennzahlen (gesamt, ``kpi['tage']`` je Tag)."""
    bets_df: pd.DataFrame
    days_df: pd.DataFrame
    kpi_dict: dict = field(default_factory=dict)
    modell_toto: list = field(default_factory=list)       # „Modell → Toto“ je Renntag (kumuliert)


def auswahl(pool: pd.DataFrame, f: FilterConfig) -> pd.DataFrame:
    """Gefilterte Zeilen des Pools (ohne Rücksicht auf Ergebnis)."""
    if pool.empty:
        return pool.copy()
    w = pool["wert"].astype(float)
    schwelle_gold = min(0.2, f.minw)
    ok = (w > TOL) & ((w >= f.minw - TOL)
                      | (f.gold_on & pool["gold"].astype(bool) & (w >= schwelle_gold - TOL)))
    x = f.mode_value
    if f.mode == "max":
        ok &= pool["fair"] < x - TOL
    elif f.mode == "rank":
        ok &= pool["rank_pct"] >= x - TOL
    elif f.mode == "rel":
        ok &= pool["rel"] >= x - TOL
    if f.top == "ja":
        ok &= pool["is_top"] == 1
    elif f.top == "nein":
        ok &= pool["is_top"] == 0
    return pool[ok].copy()


def einsatz(bank_start: float, p: float, fk: float, s: StakingConfig) -> float:
    """Einsatz je Bein in ganzen Euro (kaufmännisch gerundet)."""
    if s.variant == "level10":
        roh = 10.0
    elif s.variant == "level1p":
        roh = 0.01 * bank_start
    else:
        f = max(0.0, (p * fk - 1) / (fk - 1))
        roh = bank_start * KELLY[s.variant] * f
    return max(0.0, round_half_up(roh))


def _bein(stake: float, quote: Optional[float], treffer: bool) -> tuple[float, float]:
    """(Gewinn nach Steuer, Steuer) eines Beins."""
    if quote is None or stake <= 0:
        return 0.0, 0.0
    steuer = STEUER * stake
    brutto = stake * (quote - 1) if treffer else -stake
    return round_half_up(brutto - steuer, 2), steuer


def simulate(pool: pd.DataFrame, filters: FilterConfig = None,
             staking: StakingConfig = None) -> SimResult:
    """Wetten chronologisch durchspielen; Einsätze aus der Bank zu Tagesbeginn."""
    filters = filters or FilterConfig()
    staking = staking or StakingConfig()
    sel = auswahl(pool, filters)
    sel = sel[sel["settled"].astype(bool)] if not sel.empty else sel
    sel = sel.sort_values(["date", "race_id", "no"]) if not sel.empty else sel

    bank = staking.start_bank
    wetten, tage = [], []
    tage_alle = sorted(pool.loc[pool["settled"].astype(bool), "date"].unique()) if not pool.empty else []
    for tag in tage_alle:
        bank_start = bank
        gw_s = gw_p = 0.0
        n_tag = 0
        for _, r in sel[sel["date"] == tag].iterrows():
            st = einsatz(bank_start, r["p"], r["fk_sieg"], staking)
            if st <= 0:
                continue
            fk_platz = None if pd.isna(r["fk_platz"]) else float(r["fk_platz"])
            g_s, t_s = _bein(st, float(r["fk_sieg"]), bool(r["won"]))
            g_p, t_p = _bein(st, fk_platz, bool(r["placed"]))
            st_p = st if fk_platz is not None else 0.0
            gw_s += g_s
            gw_p += g_p
            n_tag += 1
            wetten.append({
                "date": tag, "race": r["race"], "race_id": r["race_id"], "course": r["course"],
                "no": int(r["no"]), "horse": r["horse"], "n": int(r["n"]),
                "fk_sieg": float(r["fk_sieg"]), "fk_platz": fk_platz,
                "cote_dec": r["cote_dec"], "p": r["p"], "fair": r["fair"],
                "wert": r["wert"], "rank_fq": int(r["rank_fq"]), "rank_pct": r["rank_pct"],
                "rel": r["rel"], "gold": bool(r["gold"]), "is_top": int(r["is_top"]),
                "pos": None if pd.isna(r["pos"]) else int(r["pos"]),
                "won": bool(r["won"]), "placed": bool(r["placed"]),
                "stake_win": st, "stake_place": st_p, "stake": st + st_p,
                "tax": round_half_up(t_s + t_p, 2),
                "profit_win": g_s, "profit_place": g_p,
                "profit": round_half_up(g_s + g_p, 2),
                "p_fk": r["p_fk"], "p_model": r["p_model"],
                "p_platz": r["p_platz"], "fair_platz": r["fair_platz"],
                "toto_end": None if pd.isna(r["toto_end"]) else float(r["toto_end"]),
                "fk_toto": None if pd.isna(r["fk_toto"]) else float(r["fk_toto"]),
                "kurs_rel": None if pd.isna(r["kurs_rel"]) else float(r["kurs_rel"]),
                "p_pq": r["p_pq"] if fk_platz is not None else None,
                "bank_start": bank_start,
            })
        bank = round_half_up(bank_start + gw_s + gw_p, 2)
        tage.append({"date": tag, "bank_start": bank_start, "bets": n_tag,
                     "profit_win": round_half_up(gw_s, 2), "profit_place": round_half_up(gw_p, 2),
                     "profit": round_half_up(gw_s + gw_p, 2), "bank": bank})

    bets = pd.DataFrame(wetten)
    days = pd.DataFrame(tage, columns=["date", "bank_start", "bets", "profit_win",
                                       "profit_place", "profit", "bank"])
    p_sim = pool[pool["date"].isin(days["date"])] if not pool.empty else pool        # Pool der simulierten Tage
    kpi = kpis(bets, days, staking.start_bank, p_sim, sel)
    kpi["tage"] = {
        t: kpis(bets[bets["date"] == t] if not bets.empty else bets,
                days[days["date"] == t], float(days.loc[days["date"] == t, "bank_start"].iloc[0]),
                p_sim[p_sim["date"] == t], sel[sel["date"] == t] if not sel.empty else sel)
        for t in days["date"]
    }
    return SimResult(bets, days, kpi, modell_toto_verlauf(sel))


def _quote(a: float, b: float) -> Optional[float]:
    return a / b if b else None


def kpis(bets: pd.DataFrame, days: pd.DataFrame, start_bank: float, pool: pd.DataFrame | None = None,
         sel: pd.DataFrame | None = None) -> dict:
    """Kennzahlen; bei 0 Wetten sind die Verhältniswerte None plus Hinweis. sel: abgerechnete Auswahl des Filters
    (unabhängig vom Einsatz) für „Modell → Toto“ und den Hinweis auf fehlende Toto-Endquoten."""
    bank = float(days["bank"].iloc[-1]) if len(days) else start_bank
    k: dict[str, Any] = {"days": int(len(days)), "bets": int(len(bets)),
                         "start_bank": start_bank, "bank": bank}
    if bets.empty:
        k.update({x: None for x in (
            "profit", "profit_win", "profit_place", "roi", "roi_win", "roi_place", "stake",
            "stake_win", "stake_place", "tax", "wins", "places", "strike_rate", "place_rate",
            "exp_wins_fk", "exp_wins_model", "exp_places_pq", "exp_places_model",
            "edge_win", "edge_place")})
        k["hinweis"] = HINWEIS_LEER
        k.update(kurs_kpis(bets, pool))
        k.update(_mt_kpis(sel))
        return k
    pw, pp = float(bets["profit_win"].sum()), float(bets["profit_place"].sum())
    sw, sp = float(bets["stake_win"].sum()), float(bets["stake_place"].sum())
    mit_platz = bets["stake_place"] > 0
    wins, places = int(bets["won"].sum()), int((bets["placed"] & mit_platz).sum())
    e_fk, e_mod = float(bets["p_fk"].sum()), float(bets["p_model"].sum())
    e_pq = float(bets.loc[mit_platz, "p_pq"].astype(float).sum())
    e_pm = float(bets.loc[mit_platz, "p_platz"].astype(float).sum())
    k.update({
        "profit": round_half_up(pw + pp, 2), "profit_win": round_half_up(pw, 2),
        "profit_place": round_half_up(pp, 2),
        "roi": _quote(pw + pp, sw + sp), "roi_win": _quote(pw, sw), "roi_place": _quote(pp, sp),
        "stake": sw + sp, "stake_win": sw, "stake_place": sp,
        "tax": round_half_up(float(bets["tax"].sum()), 2),
        "wins": wins, "places": places,
        "strike_rate": wins / len(bets), "place_rate": _quote(places, int(mit_platz.sum())),
        "exp_wins_fk": e_fk, "exp_wins_model": e_mod, "exp_places_pq": e_pq, "exp_places_model": e_pm,
        # Edge = Σ 1/faire Quote ÷ Σ 1/Festkurs (Modell gegen Markt, vor dem Rennen)
        "edge_win": _quote(e_mod, e_fk), "edge_place": _quote(e_pm, e_pq),
        "hinweis": "Stichprobe klein (< 30 Wetten)" if len(bets) < 30 else None,
    })
    k.update(kurs_kpis(bets, pool))
    k.update(_mt_kpis(sel))
    fehlt = k["toto_fehlt"]
    if fehlt:
        k["hinweis"] = " · ".join(x for x in (k["hinweis"], f"Toto-Endquote fehlt für {fehlt} Picks") if x)
    return k


def _mt_kpis(sel: pd.DataFrame | None) -> dict:
    """„Modell → Toto“ über die Auswahl des Filters und Zahl der Picks ohne Toto-Endquote."""
    if sel is None or sel.empty:
        return {**modell_toto(None), "toto_fehlt": 0}
    fehlt = int((pd.to_numeric(sel["toto_end"], errors="coerce").isna()).sum()) if "toto_end" in sel else 0
    return {**modell_toto(sel), "toto_fehlt": fehlt}


_KURS_LEER = {"kurs_n": 0, "kurs_gefallen": None, "clv": None, "clv_rel": None, "kurs_besser": None,
              "kurs_rel_se": None, "kurs_z": None}


def _kurs_reihe(df: pd.DataFrame) -> pd.DataFrame:
    """Zeilen mit Kursvergleich, zeitlich sortiert (Tag, Rennen, Startnummer – wie die Wetten)."""
    if df is None or df.empty or "kurs_rel" not in df:
        return pd.DataFrame(columns=["date", "race_id", "no", "kurs_rel"])
    m = df["kurs_rel"].notna() & (df["fk_toto"].notna() if "fk_toto" in df else True)
    return df[m].sort_values(["date", "race_id", "no"], kind="stable")


def _se(x: np.ndarray) -> Optional[float]:
    """Standardfehler des Mittelwerts (Stichproben-Streuung, ab 2 Werten)."""
    return float(np.std(x, ddof=1) / np.sqrt(len(x))) if len(x) >= 2 else None


def kurs_kpis(bets: pd.DataFrame, pool: pd.DataFrame | None = None) -> dict:
    """Kursbewegung der Picks bis zum Start (Festkurs gegen Toto-Endquote).
    kurs_gefallen: Anteil mit Endquote unter dem Festkurs; clv: Ø (geometrisch) Festkurs ÷ Endquote − 1;
    clv_rel: dasselbe gegen den Schnitt aller Starter des Rennens (> 0: Picks fallen stärker als das Feld);
    kurs_besser: Anteil der Picks, die stärker fallen als der Rennschnitt; kurs_rel_se: Standardfehler von
    Ø kurs_rel; kurs_z = Ø kurs_rel ÷ kurs_rel_se; pool_clv_rel: clv_rel aller abgerechneten Starter des Pools
    (Wert ≥ 0) derselben Tage, unabhängig vom Filter – zeigt, was die Auswahl darüber hinaus bringt."""
    pr = _kurs_reihe(pool[pool["settled"].astype(bool)] if pool is not None and len(pool) else None)
    k = dict(_KURS_LEER, pool_clv_rel=float(np.exp(pr["kurs_rel"].astype(float).mean()) - 1) if len(pr) else None)
    b = _kurs_reihe(bets)
    if b.empty:
        return k
    lv = np.log(b["fk_toto"].astype(float).to_numpy())
    rel = b["kurs_rel"].astype(float).to_numpy()
    se = _se(rel)
    k.update({"kurs_n": int(len(rel)), "kurs_gefallen": float((lv > 0).mean()),
              "clv": float(np.exp(lv.mean()) - 1), "clv_rel": float(np.exp(rel.mean()) - 1),
              "kurs_besser": float((rel > 0).mean()), "kurs_rel_se": se,
              "kurs_z": float(rel.mean() / se) if se else None})
    return k


def kurs_verlauf(bets: pd.DataFrame, pool: pd.DataFrame | None = None) -> pd.DataFrame:
    """Kursvorteil im Verlauf: je Wette mit Kursvergleich (zeitlich) der laufende Wert exp(Ø kurs_rel) − 1,
    das Band exp(Ø ± 1 Standardfehler) − 1 und derselbe laufende Wert für den Pool (abgerechnete Starter
    mit Wert ≥ 0 bis einschließlich dieser Wette in derselben Reihenfolge)."""
    b = _kurs_reihe(bets)
    spalten = ["n", "date", "race", "horse", "fk_sieg", "toto_end", "kurs_rel", "lauf", "lauf_lo", "lauf_hi",
               "pool_lauf"]
    if b.empty:
        return pd.DataFrame(columns=spalten)
    rel = b["kurs_rel"].astype(float).to_numpy()
    n = np.arange(1, len(rel) + 1)
    mittel = np.cumsum(rel) / n
    se = np.array([_se(rel[:i]) if i >= 2 else np.nan for i in n], dtype=float)
    pr = _kurs_reihe(pool[pool["settled"].astype(bool)] if pool is not None and len(pool) else None)
    pool_lauf = np.full(len(rel), np.nan)
    if len(pr):
        import bisect
        schl = list(zip(pr["date"].astype(str), pr["race_id"].astype(str), pr["no"].astype(int)))
        cum = np.cumsum(pr["kurs_rel"].astype(float).to_numpy())
        for i, key in enumerate(zip(b["date"].astype(str), b["race_id"].astype(str), b["no"].astype(int))):
            j = bisect.bisect_right(schl, key)
            if j:
                pool_lauf[i] = np.exp(cum[j - 1] / j) - 1
    return pd.DataFrame({"n": n, "date": b["date"].to_numpy(), "race": b["race"].to_numpy(),
                         "horse": b["horse"].to_numpy(), "fk_sieg": b["fk_sieg"].to_numpy(),
                         "toto_end": b["toto_end"].to_numpy(), "kurs_rel": rel, "lauf": np.exp(mittel) - 1,
                         "lauf_lo": np.exp(mittel - se) - 1, "lauf_hi": np.exp(mittel + se) - 1,
                         "pool_lauf": pool_lauf})


MT_MIN_N = 20      # „Modell → Toto“ erst ab so vielen Picks


def _inv(a: list[list[float]]) -> Optional[list[list[float]]]:
    """Kleine Matrix invertieren (Gauß-Jordan mit Pivotsuche); None bei (fast) singulärer Matrix.
    Gleicher Rechenweg wie im Dashboard (JS), damit beide dieselben Zahlen liefern."""
    k = len(a)
    m = [list(map(float, z)) + [1.0 if i == j else 0.0 for j in range(k)] for i, z in enumerate(a)]
    skala = max((abs(v) for z in a for v in z), default=0.0) or 1.0
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12 * skala:
            return None
        m[c], m[p] = m[p], m[c]
        d = m[c][c]
        m[c] = [v / d for v in m[c]]
        for r in range(k):
            if r != c and m[r][c] != 0.0:
                f = m[r][c]
                m[r] = [v - f * w for v, w in zip(m[r], m[c])]
    return [z[k:] for z in m]


def _ols_hc1(y: list[float], xs: list[list[float]]) -> Optional[dict]:
    """OLS y = a + Σ b_j·x_j mit zentrierten Werten (Achsenabschnitt herausgerechnet) und robustem Standardfehler
    HC1. Rückgabe: b und se je Regressor, n; None bei zu wenigen Zeilen oder singulärer Matrix."""
    n, k = len(y), len(xs)
    if n < MT_MIN_N or n <= k + 1:
        return None
    my = sum(y) / n
    mx = [sum(x) / n for x in xs]
    yc = [v - my for v in y]
    xc = [[v - m for v in x] for x, m in zip(xs, mx)]
    xtx = [[sum(a * b for a, b in zip(xc[i], xc[j])) for j in range(k)] for i in range(k)]
    inv = _inv(xtx)
    if inv is None:
        return None
    xty = [sum(a * b for a, b in zip(xc[i], yc)) for i in range(k)]
    b = [sum(inv[i][j] * xty[j] for j in range(k)) for i in range(k)]
    e = [yc[t] - sum(b[i] * xc[i][t] for i in range(k)) for t in range(n)]
    mitte = [[sum(xc[i][t] * xc[j][t] * e[t] * e[t] for t in range(n)) for j in range(k)] for i in range(k)]
    f = n / (n - k - 1)
    v = [[f * sum(inv[i][a] * mitte[a][c] * inv[c][j] for a in range(k) for c in range(k)) for j in range(k)]
         for i in range(k)]
    se = [v[i][i] ** 0.5 if v[i][i] > 0 else None for i in range(k)]
    return {"n": n, "b": b, "se": se}


def _mt_zeilen(rows: pd.DataFrame) -> pd.DataFrame:
    """Picks für „Modell → Toto“: Toto-Endquote, Festkurs und Power-Chance (ohne Morgenquote) vorhanden."""
    if rows is None or rows.empty or "toto_end" not in rows:
        return pd.DataFrame(columns=["toto_end", "fk_sieg", "p_blind", "cote_dec"])
    pb = rows["p_blind"] if "p_blind" in rows else rows["p_model"]
    m = (pd.to_numeric(rows["toto_end"], errors="coerce") > 0) & (pd.to_numeric(rows["fk_sieg"], errors="coerce") > 0) \
        & (pd.to_numeric(pb, errors="coerce") > 0)
    out = rows[m].copy()
    out["p_blind"] = pd.to_numeric(pb[m], errors="coerce")
    return out


def modell_toto(rows: pd.DataFrame) -> dict:
    """Erklärt das Modell die Toto-Endquote bei festgehaltenem Festkurs?
    log(toto_end) = a + b1·log(fk_sieg) + b2·log(p_power) (OLS, t nach HC1); zweite Variante zusätzlich mit
    log(cote_dec) (Presse). b2 < 0: Pferde, die Power bei gleichem Festkurs höher einschätzt, enden kürzer im Toto –
    bereinigt um den Auswahleffekt von „Kurs ±“ (hoher Festkurs wird bevorzugt). p_power = Power allein (sieg_blind),
    nicht die Mischung mit der Morgenquote."""
    leer = {"mt_n": 0, "mt_b1": None, "mt_b2": None, "mt_se": None, "mt_t": None,
            "mt_n_presse": 0, "mt_b2_presse": None, "mt_t_presse": None}
    d = _mt_zeilen(rows)
    if len(d) < MT_MIN_N:
        return {**leer, "mt_n": int(len(d))}
    lg = lambda c: [float(np.log(v)) for v in d[c].astype(float)]
    r = _ols_hc1(lg("toto_end"), [lg("fk_sieg"), lg("p_blind")])
    out = dict(leer, mt_n=int(len(d)))
    if r:
        out.update({"mt_b1": r["b"][0], "mt_b2": r["b"][1], "mt_se": r["se"][1],
                    "mt_t": r["b"][1] / r["se"][1] if r["se"][1] else None})
    dp = d[pd.to_numeric(d["cote_dec"], errors="coerce") > 0] if "cote_dec" in d else d.iloc[:0]
    out["mt_n_presse"] = int(len(dp))
    if len(dp) >= MT_MIN_N:
        lp = lambda c: [float(np.log(v)) for v in dp[c].astype(float)]
        r2 = _ols_hc1(lp("toto_end"), [lp("fk_sieg"), lp("p_blind"), lp("cote_dec")])
        if r2:
            out.update({"mt_b2_presse": r2["b"][1], "mt_t_presse": r2["b"][1] / r2["se"][1] if r2["se"][1] else None})
    return out


def modell_toto_verlauf(sel: pd.DataFrame) -> list[dict]:
    """„Modell → Toto“ je Renntag, kumuliert über alle Picks bis einschließlich dieses Tages (wachsendes Fenster);
    Tage mit weniger als MT_MIN_N Picks insgesamt fallen weg."""
    d = _mt_zeilen(sel)
    out = []
    for tag in sorted(d["date"].unique()) if len(d) else []:
        bis = d[d["date"] <= tag]
        if len(bis) < MT_MIN_N:
            continue
        k = modell_toto(bis)
        out.append({"date": tag, "b2": k["mt_b2"], "t": k["mt_t"], "t_presse": k["mt_t_presse"],
                    "n": k["mt_n"], "n_tag": int((d["date"] == tag).sum())})
    return out


# ---------------------------------------------------------------- Dashboard (HTML)

TEMPLATE = Path(__file__).with_name("value_dashboard_template.html")
DASHBOARD_DATEI = "value_dashboard.html"
_HTML_SPALTEN = [
    "date", "race_id", "race", "course", "no", "horse", "n", "p", "fair", "rank_fq", "rank_pct",
    "rel", "fk_sieg", "fk_platz", "cote_dec", "wert", "gold", "is_top", "p_fk", "p_model", "p_pq",
    "p_platz", "fair_platz", "toto_end", "fk_toto", "kurs_rel", "p_blind", "settled", "pos", "won", "placed"]


def _json_wert(v: Any) -> Any:
    if v is None or v is pd.NA:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if math.isnan(v) else float(v)
    return str(v)


def dashboard_daten(pool: pd.DataFrame) -> dict:
    """Pool kompakt (Spalten + Zeilen, volle Float-Genauigkeit) für die HTML-Seite."""
    zeilen = [[_json_wert(v) for v in r] for r in pool.reindex(columns=_HTML_SPALTEN).itertuples(index=False)] \
        if not pool.empty else []
    return {"spalten": _HTML_SPALTEN, "zeilen": zeilen,
            "erstellt": pd.Timestamp.now(tz="Europe/Paris").strftime("%d.%m.%Y %H:%M")}


def dashboard_html(pool: pd.DataFrame) -> str:
    """Eigenständige HTML-Seite: Filter, Kennzahlen, Grafiken und Tabelle laufen im Browser
    (gleiche Regeln wie ``simulate``)."""
    js = json.dumps(dashboard_daten(pool), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    seite = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", js, 1)
    return f'<!doctype html>\n<html lang="de">\n{seite}\n</html>\n'


def dashboard(pool: pd.DataFrame, pfad: str | Path) -> Path:
    """Dashboard als HTML-Datei schreiben (überschreibt eine vorhandene)."""
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(dashboard_html(pool), encoding="utf-8")
    return pfad


def start(base: str | Path = BASE_DRIVE, ab: str | None = START_DATUM) -> Path:
    """Dashboard aus der Drive-Ablage bauen: alle Renntage ab ``ab``.

    Karten aus ``<base>/racecards``, Ergebnisse aus ``<base>/parquet/pmu_races``;
    geschrieben wird ``<base>/racecards/value_dashboard.html`` (immer dieselbe Datei,
    bei neuen Daten überschrieben). Tage ohne Einlauf bleiben offen.
    """
    base = Path(base)
    pool = load_folder(base / "racecards", base / "parquet" / "pmu_races", ab=ab,
                       starter_ordner=base / "parquet" / "pmu_runners")
    pfad = dashboard(pool, base / "racecards" / DASHBOARD_DATEI)
    tage = pool.loc[pool["settled"].astype(bool), "date"].nunique() if not pool.empty else 0
    k = simulate(pool).kpi_dict
    print(f"Value-Dashboard: {tage} Renntage mit Ergebnis, Standard (¼ Kelly) "
          f"{k['bets']} Wetten, Bank {k['bank']:.2f} € → {pfad}")
    return pfad
