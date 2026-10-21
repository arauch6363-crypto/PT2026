"""Value-Wetten-Simulation und Dashboard (für Google Colab).

Eingaben je Renntag (gepaart über YYYYMMDD im Dateinamen):
  * ``racecard_YYYYMMDD_daten.json`` – Power-Modell (``power.sieg``), Festkurse
    (``fk.sieg``/``fk.platz``) und Presse-Kurs (``prono.sel.cote_dec``),
  * ``YYYYMMDD.parquet`` aus ``pmu_races`` – Einlauf (``finish_order``).

Die Simulationsfunktionen sind rein (keine UI); ``dashboard`` baut darauf die
Oberfläche mit ipywidgets und Plotly.

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
    fair = 1.0 / p
    # Wettkampf-Rang (1, 2, 2, 4 …) nach fairer Quote aufsteigend
    rang = [1 + int(np.sum(fair < f - TOP_TOL)) for f in fair]

    zeilen = []
    for (r, pw, _), pi, fi, rg in zip(starter, p, fair, rang):
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
            "p_pq": 1 / fk_platz if fk_platz is not None else None,
            "paid_places": 3 if n >= 8 else 2,
        })
    # Top-Wert des Rennens – vor jedem Filter, alle Gleichstände
    werte = [z["wert"] for z in zeilen if z["wert"] is not None]
    top = max(werte) if werte else None
    for z in zeilen:
        z["is_top"] = int(z["wert"] is not None and top is not None
                          and abs(z["wert"] - top) <= TOP_TOL)
    return zeilen


def load_day(json_path: str | Path, parquet_path: str | Path | None) -> pd.DataFrame:
    """Pool eines Renntags: alle Starter mit Festkurs und Wert ≥ 0, samt Ergebnis.

    Ohne Ergebnis-Parquet (oder ohne Einlauf für ein Rennen) bleiben ``pos``,
    ``won`` und ``placed`` leer und ``settled`` ist False – solche Wetten werden
    nicht simuliert (der Tag gilt als offen).
    """
    json_path = Path(json_path)
    with open(json_path, encoding="utf-8") as fh:
        daten = json.load(fh)
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
        "p_model", "p_pq", "paid_places", "is_top", "festkurse_stand", "settled", "pos",
        "won", "placed"])


def load_folder(ordner: str | Path, cache: str | Path | None = None) -> pd.DataFrame:
    """Alle Renntage eines Ordners laden (rekursiv), gepaart über das Datum.

    JSON: ``racecard_YYYYMMDD_daten.json``; Ergebnis: ``*YYYYMMDD*.parquet``.
    Fehlt das Ergebnis eines Tages, gibt es eine Warnung und der Tag bleibt
    offen. Mit ``cache`` wird der Pool zusätzlich als Parquet gespeichert.
    """
    ordner = Path(ordner)
    jsons = {}
    for p in sorted(ordner.rglob("racecard_*_daten.json")):
        d = _datum_aus_name(p)
        if d:
            jsons[d] = p
    parquets = {}
    for p in sorted(ordner.rglob("*.parquet")):
        d = _datum_aus_name(p)
        if d and d in jsons and (cache is None or p.resolve() != Path(cache).resolve()):
            parquets.setdefault(d, p)
    teile = []
    for d in sorted(jsons):
        if d not in parquets:
            warnings.warn(f"{d}: kein Ergebnis-Parquet – Tag bleibt offen", stacklevel=2)
        tag = load_day(jsons[d], parquets.get(d))
        if d in parquets and not tag.empty and not tag["settled"].all():
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
    kpi = kpis(bets, days, staking.start_bank)
    kpi["tage"] = {
        t: kpis(bets[bets["date"] == t] if not bets.empty else bets,
                days[days["date"] == t], float(days.loc[days["date"] == t, "bank_start"].iloc[0]))
        for t in days["date"]
    }
    return SimResult(bets, days, kpi)


def _quote(a: float, b: float) -> Optional[float]:
    return a / b if b else None


def kpis(bets: pd.DataFrame, days: pd.DataFrame, start_bank: float) -> dict:
    """Kennzahlen; bei 0 Wetten sind die Verhältniswerte None plus Hinweis."""
    bank = float(days["bank"].iloc[-1]) if len(days) else start_bank
    k: dict[str, Any] = {"days": int(len(days)), "bets": int(len(bets)),
                         "start_bank": start_bank, "bank": bank}
    if bets.empty:
        k.update({x: None for x in (
            "profit", "profit_win", "profit_place", "roi", "roi_win", "roi_place", "stake",
            "stake_win", "stake_place", "tax", "wins", "places", "strike_rate", "place_rate",
            "exp_wins_fk", "exp_wins_model", "exp_places_pq", "edge_wins_fk",
            "edge_wins_model", "edge_places_pq")})
        k["hinweis"] = HINWEIS_LEER
        return k
    pw, pp = float(bets["profit_win"].sum()), float(bets["profit_place"].sum())
    sw, sp = float(bets["stake_win"].sum()), float(bets["stake_place"].sum())
    mit_platz = bets["stake_place"] > 0
    wins, places = int(bets["won"].sum()), int((bets["placed"] & mit_platz).sum())
    e_fk, e_mod = float(bets["p_fk"].sum()), float(bets["p_model"].sum())
    e_pq = float(bets.loc[mit_platz, "p_pq"].astype(float).sum())
    k.update({
        "profit": round_half_up(pw + pp, 2), "profit_win": round_half_up(pw, 2),
        "profit_place": round_half_up(pp, 2),
        "roi": _quote(pw + pp, sw + sp), "roi_win": _quote(pw, sw), "roi_place": _quote(pp, sp),
        "stake": sw + sp, "stake_win": sw, "stake_place": sp,
        "tax": round_half_up(float(bets["tax"].sum()), 2),
        "wins": wins, "places": places,
        "strike_rate": wins / len(bets), "place_rate": _quote(places, int(mit_platz.sum())),
        "exp_wins_fk": e_fk, "exp_wins_model": e_mod, "exp_places_pq": e_pq,
        "edge_wins_fk": _quote(wins, e_fk), "edge_wins_model": _quote(wins, e_mod),
        "edge_places_pq": _quote(places, e_pq),
        "hinweis": "Stichprobe klein (< 30 Wetten)" if len(bets) < 30 else None,
    })
    return k


# ---------------------------------------------------------------- Dashboard

_TABELLE = [
    ("date", "Tag"), ("race", "Rennen"), ("course", "Bahn"), ("no", "Nr"), ("horse", "Pferd"),
    ("n", "Starter"), ("fk_sieg", "FK Sieg"), ("fk_platz", "FK Platz"), ("cote_dec", "Presse"),
    ("p", "p"), ("fair", "Fair"), ("wert", "Wert"), ("rank_pct", "Rang%"), ("rel", "Rel"),
    ("gold", "Gold"), ("is_top", "Top"), ("pos", "Platz"), ("stake_win", "Einsatz S"),
    ("stake_place", "Einsatz P"), ("profit_win", "G/V Sieg"), ("profit_place", "G/V Platz"),
    ("profit", "G/V"),
]


def _fmt(v: Any, nk: int = 2) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    if isinstance(v, (bool, np.bool_)):
        return "✓" if v else ""
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        return f"{v:,.{nk}f}".replace(",", " ")
    return str(v)


def _tabelle_html(bets: pd.DataFrame) -> str:
    """Sortierbare HTML-Tabelle; Gewinne grün, Verluste rot."""
    if bets.empty:
        return f"<p><i>{HINWEIS_LEER}</i></p>"
    kopf = "".join(f"<th onclick='vbSort(this)'>{t}</th>" for _, t in _TABELLE)
    zeilen = []
    for _, r in bets.iterrows():
        zellen = []
        for sp, _ in _TABELLE:
            v = r[sp]
            stil = ""
            if sp.startswith("profit") and v is not None and not pd.isna(v):
                stil = " style='color:#1a7f37'" if v > 0 else (" style='color:#cf222e'" if v < 0 else "")
            if sp == "wert" and v is not None and v > 3:
                stil = " style='color:#9a6700' title='Wert > 3 – Kursfehler?'"
            roh = "" if v is None or (isinstance(v, float) and math.isnan(v)) else v
            zellen.append(f"<td data-v='{roh}'{stil}>{_fmt(v, 3 if sp in ('p', 'rank_pct') else 2)}</td>")
        zeilen.append("<tr>" + "".join(zellen) + "</tr>")
    js = """<script>
function vbSort(th){const t=th.closest('table'),b=t.tBodies[0],i=[...th.parentNode.children].indexOf(th);
const asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
const rows=[...b.rows];rows.sort((x,y)=>{let a=x.cells[i].dataset.v,c=y.cells[i].dataset.v;
const na=parseFloat(a),nc=parseFloat(c);if(!isNaN(na)&&!isNaN(nc)){a=na;c=nc;}
return (a>c?1:a<c?-1:0)*(asc?1:-1);});rows.forEach(r=>b.appendChild(r));}
</script>"""
    css = ("<style>.vb td,.vb th{padding:2px 6px;text-align:right;font-size:12px;white-space:nowrap}"
           ".vb th{cursor:pointer;border-bottom:1px solid #888}.vb tr:nth-child(even){background:rgba(127,127,127,.08)}</style>")
    return (css + js + "<div style='max-height:420px;overflow:auto'><table class='vb'><thead><tr>"
            + kopf + "</tr></thead><tbody>" + "".join(zeilen) + "</tbody></table></div>")


def _kpi_html(k: dict) -> str:
    def pct(v):
        return "–" if v is None else f"{100 * v:.1f} %"

    def eur(v):
        return "–" if v is None else f"{v:,.2f} €".replace(",", " ")

    def num(v, nk=2):
        return "–" if v is None else f"{v:.{nk}f}"

    karten = [
        ("Bank", eur(k["bank"])), ("Gewinn", eur(k.get("profit"))),
        ("Sieg / Platz", f"{eur(k.get('profit_win'))} / {eur(k.get('profit_place'))}"),
        ("ROI", pct(k.get("roi"))), ("ROI Sieg / Platz", f"{pct(k.get('roi_win'))} / {pct(k.get('roi_place'))}"),
        ("Tage / Wetten", f"{k['days']} / {k['bets']}"), ("Einsatz", eur(k.get("stake"))),
        ("Steuer", eur(k.get("tax"))),
        ("Sieger", f"{k.get('wins', '–') if k.get('wins') is not None else '–'} ({pct(k.get('strike_rate'))})"),
        ("Platziert", f"{k.get('places') if k.get('places') is not None else '–'} ({pct(k.get('place_rate'))})"),
        ("Erw. Sieger FK / Modell", f"{num(k.get('exp_wins_fk'))} / {num(k.get('exp_wins_model'))}"),
        ("Edge Sieg FK / Modell", f"{num(k.get('edge_wins_fk'))} / {num(k.get('edge_wins_model'))}"),
        ("Erw. Plätze / Edge", f"{num(k.get('exp_places_pq'))} / {num(k.get('edge_places_pq'))}"),
    ]
    html = "".join(
        "<div style='border:1px solid rgba(127,127,127,.4);border-radius:6px;padding:6px 10px;min-width:130px'>"
        f"<div style='font-size:11px;opacity:.7'>{t}</div><div style='font-size:15px;font-weight:600'>{w}</div></div>"
        for t, w in karten)
    hinweis = f"<p style='color:#cf222e'><b>{k['hinweis']}</b></p>" if k.get("hinweis") else ""
    return f"<div style='display:flex;flex-wrap:wrap;gap:6px'>{html}</div>{hinweis}"


def _grafiken(res: SimResult, start_bank: float):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    d, b = res.days_df, res.bets_df
    fig = make_subplots(rows=2, cols=2, subplot_titles=(
        "Bank", "Gewinn je Tag", "Sieger kumuliert", "Platzierte kumuliert"))
    x0 = list(d["date"])
    fig.add_trace(go.Scatter(x=["Start"] + x0, y=[start_bank] + list(d["bank"]),
                             mode="lines+markers", name="Bank"), 1, 1)
    fig.add_hline(y=start_bank, line_dash="dash", line_color="gray", row=1, col=1)
    fig.add_trace(go.Bar(x=x0, y=d["profit_win"], name="Sieg"), 1, 2)
    fig.add_trace(go.Bar(x=x0, y=d["profit_place"], name="Platz"), 1, 2)
    if not b.empty:
        i = list(range(1, len(b) + 1))
        fig.add_trace(go.Scatter(x=i, y=b["won"].cumsum(), name="Sieger echt"), 2, 1)
        fig.add_trace(go.Scatter(x=i, y=b["p_fk"].cumsum(), name="erwartet FK", line_dash="dot"), 2, 1)
        fig.add_trace(go.Scatter(x=i, y=b["p_model"].cumsum(), name="erwartet Modell", line_dash="dash"), 2, 1)
        mp = b[b["stake_place"] > 0]
        j = list(range(1, len(mp) + 1))
        fig.add_trace(go.Scatter(x=j, y=mp["placed"].cumsum(), name="Platz echt"), 2, 2)
        fig.add_trace(go.Scatter(x=j, y=mp["p_pq"].astype(float).cumsum(), name="erwartet Platzkurs",
                                 line_dash="dot"), 2, 2)
    fig.update_layout(height=620, barmode="relative", margin=dict(l=40, r=20, t=40, b=30),
                      legend=dict(orientation="h", y=-0.08))
    return fig


def dashboard(pool: pd.DataFrame):
    """Interaktives Dashboard (ipywidgets + Plotly) über einen geladenen Pool."""
    import ipywidgets as w
    from IPython.display import HTML, display

    tage = sorted(pool.loc[pool["settled"].astype(bool), "date"].unique()) if not pool.empty else []
    st = w.Dropdown(options=list(VARIANTEN), value="kelly4", description="Einsatz")
    minw = w.FloatSlider(value=0.5, min=0, max=1.5, step=0.1, description="Min. Wert", readout_format=".1f")
    gold = w.Checkbox(value=True, description="Gold ab 0,2")
    modus = w.ToggleButtons(options=list(MODI), value="max", description="Modus")
    regler = {m: w.FloatSlider(value=v, min=a, max=b, step=s, description={
        "max": "Fair <", "rank": "Rang% ≥", "rel": "Rel ≥"}[m], readout_format=".2f")
        for m, (a, b, s, v) in MODUS_REGLER.items()}
    top = w.ToggleButtons(options=list(TOP_WAHL), value="beides", description="Top")
    tag = w.Dropdown(options=["alle"] + list(tage), value="alle", description="Tag")
    suche = w.Text(placeholder="Pferd …", description="Suche")
    out = w.Output()

    def sichtbar(*_):
        for m, r in regler.items():
            r.layout.display = "" if m == modus.value else "none"

    def neu(*_):
        sichtbar()
        p = pool if tag.value == "alle" else pool[pool["date"] == tag.value]
        f = FilterConfig(minw=minw.value, gold_on=gold.value, mode=modus.value,
                         mode_value=regler[modus.value].value if modus.value in regler else 0.0,
                         top=top.value)
        s = StakingConfig(variant=st.value)
        res = simulate(p, f, s)
        b = res.bets_df
        if suche.value.strip() and not b.empty:
            b = b[b["horse"].str.contains(suche.value.strip(), case=False, na=False)]
        with out:
            out.clear_output(wait=True)
            display(HTML(_kpi_html(res.kpi_dict)))
            _grafiken(res, s.start_bank).show()
            display(HTML(_tabelle_html(b)))
            display(HTML("<p style='font-size:11px;opacity:.7'>" + " · ".join(HINWEISE) + "</p>"))

    for c in [st, minw, gold, modus, top, tag, suche, *regler.values()]:
        c.observe(neu, names="value")
    neu()
    display(w.VBox([w.HBox([st, tag, suche]), w.HBox([minw, gold]),
                    w.HBox([modus, *regler.values()]), top, out]))
