"""Claude-Version der Race Card: JSON für den Skill „rennkarten-durchgang“ (racecard_JJJJMMTT_claude.json).

Enthält **alle Daten der Race Card** (racecard.baue_daten) – auch Detailinfos, die der Skill heute noch nicht nutzt,
damit eine spätere Fassung des Skills sie ohne Codeänderung lesen kann. Neue Felder der Karte kommen automatisch mit,
weil nicht ausgewählt, sondern nur ausgelassen wird (selftest prüft das).

Ausgelassen wird nur, was keine Information für die Analyse trägt oder ausdrücklich nicht genutzt werden soll:
* Trikots (`silks`, base64-Bilder),
* Morgen- und Totokurs (`odds`, `odds_morning` des Starters; die Karte zeigt sie nicht, der Skill soll sie nicht
  nutzen). Historische Endquoten in den Formzeilen und bei den Gegnern bleiben.
* je Formzeile die volle Gegnerliste (statt dessen `rivals_nah` und `rivals_stat`) und die Zwischenwerte der
  Berechnung (OHNE_FORMZEILE: Rohtempo, Klassenkorrektur, Bestandteile des TR, Perzentile für die Farbe …).

Umgeordnet und vorgerechnet, damit Claude nicht selbst rechnen muss:
* je Rennen `offen` (Status PROGRAMMEE), Starter in Prognose-Reihenfolge, Nichtstarter getrennt in `nichtstarter`
  (vollständig) und ihre Nummern in `nr`,
* `vorgerechnet`: Marge der cote probable, Reihenfolge nach Prognose-Rang, Bias gegen den Schnitt aller Bahnen,
* je Starter `p_prog` (Prognose-Chance nach der Potenzmethode) und `luecke` (PMU-Starts − Datenbank-Läufe),
* je Formzeile `rivals_nah`: die zwei Gegner direkt davor und dahinter (mit ihrem nächsten Start).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

OHNE_STARTER = {"silks", "odds", "odds_morning"}     # Trikots, Morgen-/Totokurs
GEGNER_NAH = 2                                       # rivals_nah: so viele Gegner davor und dahinter
OFFEN = "PROGRAMMEE"
# Formzeile: volle Gegnerliste (dafür rivals_nah + rivals_stat) und Zwischenwerte der Berechnung weglassen
OHNE_FORMZEILE = {
    "rivals",                                        # alle Gegner -> rivals_nah
    "l600", "b200", "b200_seg",                      # Rohtempo, daraus ΔL600 A / ΔB200 A
    "dl600_k", "db200_k",                            # Klassenkorrektur in ΔL600 A / ΔB200 A
    "fs_par", "fs_race", "path_factor", "sec_mismatch",   # Zwischenwerte FS% / Weg / Gegenprobe
    "tr_ga", "tr_zeit", "tr_upg",                    # Bestandteile des TR (Going Allowance, Zeit-Rating, Upgrade)
    "rating_filled",                                 # ARR: Rating der Referenz ergänzt
    "cls_val_pct", "cls_epr_pct",                    # Perzentile nur für die Farbe (Index cls_*_idx bleibt)
    "pos_before_m",                                  # Konstante (params.pos_before_m)
}


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


def _starter(x: dict, p: dict) -> dict:
    """Starter vollständig ohne OHNE_STARTER, Formzeilen ohne OHNE_FORMZEILE; dazu p_prog, luecke, rivals_nah."""
    y = {k: copy.deepcopy(v) for k, v in x.items() if k not in OHNE_STARTER | {"form_lines"}}
    y["form_lines"] = [{**{k: copy.deepcopy(v) for k, v in f.items() if k not in OHNE_FORMZEILE},
                        "rivals_nah": _gegner_nah(f)} for f in x.get("form_lines") or []]
    db = (x.get("career") or {}).get("all", {}).get("runs")
    y["luecke"] = (x["starts"] - db) if isinstance(x.get("starts"), int) and isinstance(db, int) else None
    y["p_prog"] = round(p[x["no"]], 4) if x.get("no") in p else None
    return y


def rennen(r: dict, bias_alle: float | None) -> dict:
    """Ein Rennen vollständig; Starter nach Prognose-Rang, Nichtstarter getrennt, Vorgerechnetes dazu."""
    alle = r.get("runners") or []
    starter = [x for x in alle if not x.get("nr")]
    nicht = [x for x in alle if x.get("nr")]
    roh = {x["no"]: 1 / x["prono"]["sel"]["cote_dec"] for x in starter
           if ((x.get("prono") or {}).get("sel") or {}).get("cote_dec")}
    p = potenz_normierung(roh)
    reihenfolge = [x["no"] for x in sorted(
        starter, key=lambda x: (((x.get("prono") or {}).get("sel") or {}).get("rank") or 99, x["no"]))]
    b = (r.get("bias") or {}).get("bias")
    out = {k: copy.deepcopy(v) for k, v in r.items() if k != "runners"}
    out["offen"] = r.get("status") == OFFEN
    out["nr"] = [x["no"] for x in nicht]
    out["vorgerechnet"] = {
        "marge": round(sum(roh.values()), 3) if roh else None,      # Σ 1/cote_dec, typisch 1,15–1,50
        "reihenfolge": reihenfolge,                                  # Startnummern nach Prognose-Rang
        "bias_rel": round(b - bias_alle, 2) if b is not None and bias_alle is not None else None,
    }
    nach_no = {x["no"]: x for x in starter}
    out["runners"] = [_starter(nach_no[no], p) for no in reihenfolge]
    out["nichtstarter"] = [_starter(x, {}) for x in nicht]
    return out


def export(daten: dict) -> dict:
    """Claude-Version aus dem Ergebnis von racecard.baue_daten: alle Felder außer Trikots und Kursen."""
    bias_alle = (daten.get("bias_all") or {}).get("bias")
    out = {"hinweis": "Claude-Version der Race Card für den Skill rennkarten-durchgang: alle Daten der Karte außer "
                      "Trikots und Morgen-/Totokurs. Starter nach Prognose-Rang sortiert, Nichtstarter getrennt in "
                      "nichtstarter (Nummern in nr); vorgerechnet: p_prog (Potenzmethode), marge, reihenfolge, "
                      "bias_rel, luecke; je Formzeile zusätzlich rivals_nah."}
    out.update({k: copy.deepcopy(v) for k, v in daten.items() if k != "races"})
    out["races"] = {rid: rennen(r, bias_alle) for rid, r in (daten.get("races") or {}).items()}
    return out


def schreiben(daten: dict, pfad: Path) -> Path:
    pfad = Path(pfad)
    pfad.write_text(json.dumps(export(daten), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return pfad
