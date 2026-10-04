"""Claude-Version der Race Card: kompakte JSON für den Skill „rennkarten-durchgang“.

Aus denselben Daten wie die HTML-Karte (racecard.baue_daten), aber ohne das, was der Skill nicht braucht oder
ausdrücklich nicht nutzen soll:
* keine Trikots (base64), keine Morgen-/Totokurse (`odds`, `odds_morning`),
* je Formzeile statt aller Gegner nur die direkt davor und dahinter (`rivals_nah`) plus `rivals_stat`,
* Nichtstarter gestrichen (Nummern in `nr`), gelaufene Rennen nur als eine Zeile.
Dazu vorgerechnet, was der Skill sonst selbst rechnet: Prognose-Chance nach der Potenzmethode (`p_prog`), Marge,
Reihenfolge nach Prognose-Rang, Bias gegen den Schnitt aller Bahnen, Lücke `starts` − Datenbank-Läufe.
racecard.run schreibt die Datei als racecard_JJJJMMTT_claude.json neben die HTML-Karte.
"""
from __future__ import annotations

import json
from pathlib import Path

OHNE_STARTER = {"silks", "odds", "odds_morning"}     # nicht für Claude
GEGNER_NAH = 2                                       # je Formzeile: so viele Gegner davor und dahinter
OFFEN = "PROGRAMMEE"
# Felder der Formzeilen, die der Skill liest (Rest – Rohwerte, Zwischenwerte der Berechnung – bleibt weg)
FORM_FELDER = ("date", "course", "dist", "going", "type", "prize", "won_eur", "pos", "ran", "margin", "incident",
               "unreliable", "weight", "jockey", "blinkers", "odds", "odds_rank", "fav", "valeur", "draw",
               "draw_stat", "comment", "comment_de", "tracking", "early_pos", "pos_before", "fifth", "pos_gain",
               "weg_med", "pace_ratio", "finish_index", "fs", "fs_opt", "dl600_a", "db200_a", "arr", "arr_adj",
               "tr", "tr_heute", "tr_cap", "cls_val", "cls_epr", "cls_val_idx", "cls_epr_idx", "rivals_stat",
               "same", "extra")


def _formzeile(f: dict) -> dict:
    """Formzeile für Claude: nur FORM_FELDER, leere Werte weg, Box-Urteil nur wenn auffällig (sig)."""
    out = {k: f[k] for k in FORM_FELDER if f.get(k) not in (None, [], "")}
    if not (f.get("draw_stat") or {}).get("sig"):
        out.pop("draw_stat", None)
    out["rivals_nah"] = _gegner_nah(f)
    return out


def potenz_normierung(q: dict) -> dict:
    """{no: 1/cote_dec} -> {no: p} mit Σ p = 1: Exponent k, für den Σ q^k = 1 (Marge stärker bei Außenseitern)."""
    if not q:
        return {}
    lo, hi = 0.2, 6.0
    for _ in range(80):
        k = (lo + hi) / 2
        lo, hi = (k, hi) if sum(v ** k for v in q.values()) > 1 else (lo, k)
    k = (lo + hi) / 2
    return {no: v ** k for no, v in q.items()}


def _gegner_nah(f: dict) -> list[dict]:
    """Gegner direkt vor und hinter dem Pferd (nach Einlauf) – die definieren das Niveau der Leistung (B5)."""
    riv = f.get("rivals") or []
    pos = f.get("pos")
    if not riv or pos is None:
        return riv[:GEGNER_NAH * 2]
    vor = [g for g in riv if g.get("pos") is not None and g["pos"] < pos][-GEGNER_NAH:]
    nach = [g for g in riv if g.get("pos") is None or g["pos"] > pos][:GEGNER_NAH]
    return vor + nach


def _starter(x: dict) -> dict:
    y = {k: v for k, v in x.items() if k not in OHNE_STARTER}
    y["form_lines"] = [_formzeile(f) for f in x.get("form_lines") or []]
    db = (x.get("career") or {}).get("all", {}).get("runs")
    y["luecke"] = (x["starts"] - db) if isinstance(x.get("starts"), int) and isinstance(db, int) else None
    return y


def rennen(r: dict, bias_alle: float | None) -> dict:
    """Ein Rennen für Claude; gelaufene/abgebrochene Rennen nur mit Kopf und Ergebnis."""
    kopf = {k: r.get(k) for k in ("race_id", "reunion", "race_no", "time", "name", "course", "status", "result")}
    if r.get("status") != OFFEN:
        return {**kopf, "offen": False}
    starter = [x for x in r.get("runners") or [] if not x.get("nr")]
    roh = {x["no"]: 1 / x["prono"]["sel"]["cote_dec"] for x in starter
           if ((x.get("prono") or {}).get("sel") or {}).get("cote_dec")}
    p = potenz_normierung(roh)
    out = {**{k: v for k, v in r.items() if k != "runners"}, "offen": True}
    out["nr"] = [x["no"] for x in r.get("runners") or [] if x.get("nr")]
    b = (r.get("bias") or {}).get("bias")
    out["vorgerechnet"] = {
        "marge": round(sum(roh.values()), 3) if roh else None,      # Σ 1/cote_dec, typisch 1,15–1,50
        "reihenfolge": [x["no"] for x in sorted(
            starter, key=lambda x: (((x.get("prono") or {}).get("sel") or {}).get("rank") or 99, x["no"]))],
        "bias_rel": round(b - bias_alle, 2) if b is not None and bias_alle is not None else None,
    }
    out["runners"] = []
    for x in sorted(starter, key=lambda x: out["vorgerechnet"]["reihenfolge"].index(x["no"])):
        y = _starter(x)
        y["p_prog"] = round(p[x["no"]], 4) if x["no"] in p else None
        out["runners"].append(y)
    return out


def export(daten: dict) -> dict:
    """Claude-Version aus dem Ergebnis von racecard.baue_daten."""
    bias_alle = (daten.get("bias_all") or {}).get("bias")
    races = {rid: rennen(r, bias_alle) for rid, r in (daten.get("races") or {}).items()}
    return {
        "hinweis": "Claude-Version der Race Card für den Skill rennkarten-durchgang: ohne Trikots und ohne "
                   "Morgen-/Totokurse, Nichtstarter gestrichen (Nummern in nr), Starter nach Prognose-Rang sortiert; "
                   "vorgerechnet: p_prog (Potenzmethode), marge, reihenfolge, bias_rel, luecke; je Formzeile nur "
                   "die nächsten Gegner (rivals_nah) und rivals_stat.",
        "date": daten.get("date"), "generated": daten.get("generated"), "history": daten.get("history"),
        "bias_all": daten.get("bias_all"), "params": daten.get("params"), "meetings": daten.get("meetings"),
        "races": races,
    }


def schreiben(daten: dict, pfad: Path) -> Path:
    pfad = Path(pfad)
    pfad.write_text(json.dumps(export(daten), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return pfad
