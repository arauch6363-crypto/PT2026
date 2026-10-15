"""Claude-Version der Race Card: JSON für den Skill „rennkarten-durchgang“ in zwei Dateien.

* racecard_JJJJMMTT_claude.json – **blind** für Teil 1 des Skills: alle Daten der Karte ohne Markt- und Presseangaben
  (PMU-Prognose, cote probable, p_prog, Marge, Tipps, Konsens, Cribles, Rennkommentar – OHNE_MARKT). Starter in der
  Reihenfolge des Power-Modells (stärkste zuerst; ohne Modell nach Startnummer), nie nach Prognose-Rang.
* racecard_JJJJMMTT_markt.json – **Markt** für Teil 2: je Rennen prono (Text, Tipps, Konsens, Cribles), Marge,
  Reihenfolge nach Prognose-Rang und je Starter prono und p_prog.

Enthält **alle Daten der Race Card** (racecard.baue_daten) – auch Detailinfos, die der Skill heute noch nicht nutzt,
damit eine spätere Fassung des Skills sie ohne Codeänderung lesen kann. Neue Felder der Karte kommen automatisch mit,
weil nicht ausgewählt, sondern nur ausgelassen wird (selftest prüft das).

Ausgelassen wird nur, was keine Information für die Analyse trägt oder ausdrücklich nicht genutzt werden soll:
* Trikots (`silks`, base64-Bilder),
* Morgen- und Totokurs (`odds`, `odds_morning`) nur noch als Sicherheitsnetz: Die Karte enthält seit 10/2026 keine
  aktuellen Kurse mehr. Historische Endquoten in den Formzeilen und bei den Gegnern bleiben.
* je Formzeile die volle Gegnerliste (statt dessen `rivals_nah` und `rivals_stat`) und die Zwischenwerte der
  Berechnung (OHNE_FORMZEILE: Rohtempo, Klassenkorrektur, Bestandteile des TR, Perzentile für die Farbe …).

Umgeordnet und vorgerechnet, damit Claude nicht selbst rechnen muss:
* je Rennen `offen` (Status PROGRAMMEE), Starter nach Power (sonst Startnummer), Nichtstarter getrennt in `nichtstarter`
  (vollständig) und ihre Nummern in `nr`,
* `vorgerechnet`: Reihenfolge nach Power (sonst Startnummer), Bias gegen den Schnitt aller Bahnen (Marktdatei: Marge der cote
  probable, Reihenfolge nach Prognose-Rang),
* je Starter `luecke` (PMU-Starts − Datenbank-Läufe); in der Marktdatei `p_prog` (Potenzmethode),
* je Formzeile `rivals_nah`: die zwei wieder gelaufenen Gegner direkt davor und dahinter (mit ihrem nächsten Start und
  dessen Klasse epr_idx/val_idx; die Race Card zeigt schon nur diese, rivals_stat zählt über das ganze Feld).

Mit trainiertem Power-Modell (power_modell):
* blind: je Starter `modell` (Siegchance, faire Quote, Power, Rang, Treiber), oben `modelle.power` (Verlässlichkeit aus
  dem Trainingsbericht). Starter mit roter Power (≤ ROT_AB) ohne Value-Hinweis nur als Kurzzeile in `weitere`
  (Anzahl, Siegchancen) – spart Tokens, die KI weiß trotzdem, wer mitläuft.
* blind, je Rennen `vergleich_365`: ARR und TR der letzten 365 Tage im Feldvergleich (bester, Median, letzter, bester
  unter heutigen Bedingungen, Rang, Abstand zum Besten – das ARR/TR-Overlay der Karte) und `verbindungen` (Trainer und
  Jockey 365 Tage mit Rang im Feld und Trend – die A/E-Matrix der Karte), jeweils für alle Starter.
* Markt: je Starter `value` (Value-Faktor, goldener Rahmen, faire Quote gegen Prognose-Cote ohne Marge), oben
  `modelle.value` und `modelle.vorwaerts_test`.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

OHNE_STARTER = {"silks", "odds", "odds_morning", "kpi", "pref_ref", "power"}   # Trikots; Kurse nur Sicherheitsnetz; kpi/pref_ref: nur für Overlays der Karte
# Nur für die Overlays der HTML-Karte, nicht für Claude: Vorlieben-Gesamttabellen, Overlay-Parameter, Matrix-Werte
OHNE_OBEN = {"pref_alle", "modelle"}                # modelle: aufgeteilt (power blind, value + Vorwärts-Test Markt)
OHNE_PARAMS = {"kpi_days", "kpi_window"}
OHNE_AE = {"pos_idx", "prev"}
OHNE_DUELL = {"race_id"}                             # direkte Duelle: Rennen nur für die Knöpfe in den Formzeilen
OHNE_INDIREKT = {"via"}                              # indirekte Duelle: Vergleiche je Rennen nur für die Karte
OHNE_MARKT = {"prono"}                               # Prognose, Tipps, Konsens, Cribles, Rennkommentar: nur Marktdatei
GEGNER_NAH = 2                                       # rivals_nah: so viele Gegner davor und dahinter
OFFEN = "PROGRAMMEE"
ROT_AB = 95                                          # Power bis hier = rot: Starter nur als Kurzzeile („weitere“)
VALUE_HALTEN = 1.1                                   # … außer Value-Faktor darüber oder goldener Rahmen
VERGLEICH_DIST_M = 200                               # ARR/TR „unter heutigen Bedingungen“: gleiche Bodengruppe, ±200 m
TREND_AE = 0.10                                      # Verbindungen: A/E 365 Tage gegen den Zeitraum davor
TREND_MIN_LAEUFE = 10
FAIR_WERT, COTE_MAX = 1.3, 31                        # ▲/▼ gegen die Prognose wie in der Karte
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


def _starter(x: dict) -> dict:
    """Starter vollständig ohne OHNE_STARTER und Marktangaben, Formzeilen ohne OHNE_FORMZEILE; dazu luecke und
    rivals_nah."""
    y = {k: copy.deepcopy(v) for k, v in x.items() if k not in OHNE_STARTER | OHNE_MARKT | {"form_lines"}}
    y["form_lines"] = [{**{k: copy.deepcopy(v) for k, v in f.items() if k not in OHNE_FORMZEILE},
                        "rivals_nah": _gegner_nah(f)} for f in x.get("form_lines") or []]
    for rolle in ("trainer", "jockey", "owner", "breeder"):          # Matrix-Werte (pos_idx, prev) nur in der Karte
        for fenster in ((y.get("ae") or {}).get(rolle) or {}).values():
            if isinstance(fenster, dict):
                for k in OHNE_AE:
                    fenster.pop(k, None)
    for d in y.get("duels") or []:
        for k in OHNE_DUELL:
            d.pop(k, None)
    for e in ((y.get("indirect") or {}).get("rivals") or []):
        for k in OHNE_INDIREKT:
            e.pop(k, None)
    db = (x.get("career") or {}).get("all", {}).get("runs")
    y["luecke"] = (x["starts"] - db) if isinstance(x.get("starts"), int) and isinstance(db, int) else None
    return y


def _prognose(starter: list[dict]) -> tuple[dict, list]:
    """p_prog je Startnummer (Potenzmethode), Marge-Rohwerte und Reihenfolge nach Prognose-Rang."""
    roh = {x["no"]: 1 / x["prono"]["sel"]["cote_dec"] for x in starter
           if ((x.get("prono") or {}).get("sel") or {}).get("cote_dec")}
    reihenfolge = [x["no"] for x in sorted(
        starter, key=lambda x: (((x.get("prono") or {}).get("sel") or {}).get("rank") or 99, x["no"]))]
    return roh, reihenfolge


def _rang(werte: dict, hoch_gut: bool = True) -> dict:
    """{no: Wert} -> {no: Rang} (1 = bester), Gleichstand gleicher Rang; None ohne Rang."""
    mit = {k: v for k, v in werte.items() if v is not None}
    return {k: 1 + sum((w > v) if hoch_gut else (w < v) for w in mit.values()) for k, v in mit.items()}


def _modell(x: dict, rang: dict, n: int) -> dict | None:
    """Power-Modell je Starter für Teil 1 (blind): Siegchance, faire Quote, Rang im Feld, stärkste Treiber."""
    pw = x.get("power")
    if not pw or pw.get("sieg") is None:
        return None
    return {"sieg": pw["sieg"], "fair": round(1 / max(pw["sieg"], 1e-3), 1), "power": pw.get("p"),
            "rang": rang.get(x["no"]), "von": n, "treiber": pw.get("treiber")}


def _halten(x: dict) -> bool:
    """Starter in Teil 1 vollständig zeigen? Nein nur bei roter Power ohne Value-Hinweis."""
    pw = x.get("power") or {}
    if pw.get("p") is None or pw["p"] > ROT_AB:
        return True
    return bool(pw.get("gold")) or (pw.get("wert") is not None and pw["wert"] > VALUE_HALTEN)


def _kpi_vergleich(starter: list[dict], r: dict) -> dict:
    """ARR/TR der letzten 365 Tage je Starter (heutiges Gewicht, ohne ausgerittene) als Feldvergleich – die Zahlen
    des ARR/TR-Overlays der Karte: Anzahl, bester, Median, letzter Wert, bester unter heutigen Bedingungen (gleiche
    Bodengruppe, ±200 m), Rang des besten Werts im Feld und Abstand zum Feldbesten. TR gedeckelt zählt nicht als bester."""
    going, dist = r.get("going_pmu"), r.get("distance")
    out = {}
    for name, i in (("arr", 4), ("tr", 5)):
        zeilen = {}
        for x in starter:
            kpi = [k for k in (x.get("kpi") or []) if k[i] is not None]
            if not kpi:
                zeilen[x["no"]] = None
                continue
            werte = [k[i] for k in kpi]
            gut = [k for k in kpi if not (name == "tr" and k[6])]
            bed = [k[i] for k in gut if k[3] == going and dist and k[2] and abs(k[2] - dist) <= VERGLEICH_DIST_M]
            s_ = sorted(werte)
            zeilen[x["no"]] = {"n": len(werte), "best": max((k[i] for k in gut), default=None),
                               "median": round(s_[len(s_) // 2] if len(s_) % 2 else (s_[len(s_) // 2 - 1] + s_[len(s_) // 2]) / 2, 1),
                               "last": werte[0], "best_heute_bed": max(bed) if bed else None,
                               "n_heute_bed": len(bed)}
        rang = _rang({no: (z or {}).get("best") for no, z in zeilen.items()})
        top = max((z["best"] for z in zeilen.values() if z and z["best"] is not None), default=None)
        for no, z in zeilen.items():
            if z and z["best"] is not None:
                z["rang"], z["abstand_zum_besten"] = rang.get(no), round(z["best"] - top, 1)
        out[name] = [{"no": no, **z} for no, z in zeilen.items() if z]
    return out


def _verbindungen(starter: list[dict]) -> list[dict]:
    """Trainer und Jockey (365 Tage) im Feldvergleich – die Zahlen der A/E-Matrix der Karte: A/E Platz, A/E Sieg,
    Pos+ (Platzanteil-Index), €/L+, Starts, Rang im Feld, Trend gegen den Zeitraum davor und Form der letzten 30 Tage."""
    rows = {x["no"]: {"no": x["no"]} for x in starter}
    for rolle in ("trainer", "jockey"):
        d = {x["no"]: ((x.get("ae") or {}).get(rolle) or {}) for x in starter}
        jahr = {no: v.get("d365") or {} for no, v in d.items()}
        raenge = {k: _rang({no: j.get(k) for no, j in jahr.items()}) for k in ("ae", "pos_idx", "epr_idx")}
        for x in starter:
            j, no = jahr[x["no"]], x["no"]
            if not j.get("runs"):
                rows[no][rolle] = {"name": x.get(rolle), "runs": 0}
                continue
            prev = j.get("prev") or {}
            trend = None
            if prev.get("ae") is not None and j.get("ae") is not None and (prev.get("runs") or 0) >= TREND_MIN_LAEUFE:
                trend = ("steigend" if j["ae"] - prev["ae"] >= TREND_AE else
                         "fallend" if j["ae"] - prev["ae"] <= -TREND_AE else "gleich")
            rows[no][rolle] = {"name": x.get(rolle), "runs": j.get("runs"), "ae": j.get("ae"), "ae_win": j.get("ae_win"),
                               "pos_idx": j.get("pos_idx"), "epr_idx": j.get("epr_idx"),
                               "rang_ae": raenge["ae"].get(no), "rang_pos": raenge["pos_idx"].get(no),
                               "rang_epr": raenge["epr_idx"].get(no), "trend_vorjahr": trend,
                               "form_30t": d[no].get("trend")}
    return list(rows.values())


def rennen(r: dict, bias_alle: float | None) -> dict:
    """Ein Rennen blind: vollständig ohne Marktangaben; Starter nach Power (sonst Startnummer), Nichtstarter getrennt."""
    alle = r.get("runners") or []
    starter = [x for x in alle if not x.get("nr")]
    nicht = [x for x in alle if x.get("nr")]
    # Reihenfolge: nach dem Power-Modell (stärkste zuerst), ohne Modell nach Startnummer
    reihe = sorted((x["no"] for x in starter),
                   key=lambda no: (-(next(x for x in starter if x["no"] == no).get("power") or {}).get("p", -1e9), no))
    b = (r.get("bias") or {}).get("bias")
    out = {k: copy.deepcopy(v) for k, v in r.items() if k not in {"runners"} | OHNE_MARKT}
    out["offen"] = r.get("status") == OFFEN
    out["nr"] = [x["no"] for x in nicht]
    nach_no = {x["no"]: x for x in starter}
    mit_power = [x for x in starter if (x.get("power") or {}).get("p") is not None]
    rang = _rang({x["no"]: x["power"]["p"] for x in mit_power})
    halten = [no for no in reihe if _halten(nach_no[no])] if mit_power else reihe
    weg = [no for no in reihe if no not in halten]
    out["vorgerechnet"] = {
        "reihenfolge": halten,                                       # nach Power (sonst Startnummer), vollständig gezeigt
        "bias_rel": round(b - bias_alle, 2) if b is not None and bias_alle is not None else None,
    }
    out["runners"] = []
    for no in halten:
        y = _starter(nach_no[no])
        m = _modell(nach_no[no], rang, len(mit_power))
        if m:
            y["modell"] = m
        out["runners"].append(y)
    if weg:                                                          # rote Starter ohne Value-Hinweis: nur Kurzzeile
        kurz = [{"no": no, "horse": nach_no[no].get("horse"), **{k: v for k, v in (_modell(nach_no[no], rang,
                 len(mit_power)) or {}).items() if k in ("sieg", "fair", "power", "rang")}} for no in weg]
        out["weitere"] = {"anzahl": len(weg), "starter_gesamt": len(reihe),
                          "sieg_summe": round(sum(k.get("sieg") or 0 for k in kurz), 3),
                          "hinweis": f"Power ≤ {ROT_AB} (Modell: klar unter dem Feldschnitt) ohne Value-Hinweis – nicht "
                                     "vollständig gezeigt, um Tokens zu sparen. Sie laufen mit: Siegchancen des Feldes "
                                     "inklusive dieser Starter auf 100 % rechnen.",
                          "starter": kurz}
    out["vergleich_365"] = {**_kpi_vergleich(starter, r), "verbindungen": _verbindungen(starter)}
    out["nichtstarter"] = [_starter(x) for x in nicht]
    return out


def rennen_markt(r: dict) -> dict:
    """Ein Rennen für Teil 2: Prognose, Tipps, Konsens, Cribles, Rennkommentar; Marge, Reihenfolge, p_prog."""
    alle = r.get("runners") or []
    starter = [x for x in alle if not x.get("nr")]
    roh, reihenfolge = _prognose(starter)
    p = potenz_normierung(roh)
    nach_no = {x["no"]: x for x in starter}
    mit_power = any((x.get("power") or {}).get("p") is not None for x in starter)
    marge = sum(roh.values()) if len(roh) >= 2 else None

    def value(x: dict) -> dict | None:
        pw = x.get("power") or {}
        if pw.get("wert") is None and pw.get("sieg") is None:
            return None
        cote = ((x.get("prono") or {}).get("sel") or {}).get("cote_dec")
        cf = cote * marge if cote and marge else None               # Prognose-Cote ohne Marge
        fair = 1 / max(pw["sieg"], 1e-3) if pw.get("sieg") else None
        v = cf / fair if cf and fair and cote <= COTE_MAX else None
        return {"faktor": pw.get("wert"), "gold": bool(pw.get("gold")), "fair": round(fair, 1) if fair else None,
                "cote_ohne_marge": round(cf, 1) if cf else None,
                "vs_prognose": ("Modell stärker" if v and v >= FAIR_WERT else
                                "Modell schwächer" if v and v <= 1 / FAIR_WERT else None),
                "cote_3_10": bool(cote and 3 <= cote <= 10)}
    return {"race_id": r.get("race_id"), "offen": r.get("status") == OFFEN, "prono": copy.deepcopy(r.get("prono")),
            "vorgerechnet": {"marge": round(sum(roh.values()), 3) if roh else None,   # Σ 1/cote_dec, typisch 1,15–1,50
                             "reihenfolge": reihenfolge},                          # Startnummern nach Prognose-Rang
            "nr": [x["no"] for x in alle if x.get("nr")],
            "runners": [{"no": no, "horse": nach_no[no].get("horse"), "prono": copy.deepcopy(nach_no[no].get("prono")),
                         "p_prog": round(p[no], 4) if no in p else None,
                         **({"value": value(nach_no[no]), "blind_nur_kurz": not _halten(nach_no[no])} if mit_power else {})}
                        for no in reihenfolge]}


def export(daten: dict) -> dict:
    """Blinde Claude-Version aus dem Ergebnis von racecard.baue_daten: alle Felder außer Trikots, Kursen und
    Marktangaben (OHNE_MARKT)."""
    bias_alle = (daten.get("bias_all") or {}).get("bias")
    out = {"hinweis": "Claude-Version der Race Card, Teil 1 (blind): alle Daten der Karte außer Trikots, Kursen und "
                      "Marktangaben (Prognose, p_prog, Tipps, Konsens, Cribles, Rennkommentar – die stehen in "
                      "racecard_JJJJMMTT_markt.json). Starter nach Power-Modell sortiert (stärkste zuerst, ohne "
                      "Modell nach Startnummer), Nichtstarter getrennt in "
                      "nichtstarter (Nummern in nr); vorgerechnet: reihenfolge, bias_rel, luecke; je Formzeile "
                      "zusätzlich rivals_nah. Mit Power-Modell: je Starter modell (Siegchance, faire Quote, Rang, "
                      "Treiber), oben modelle.power (Verlässlichkeit); rote Starter ohne Value-Hinweis nur als "
                      "Kurzzeile in weitere (Anzahl, Siegchancen); je Rennen vergleich_365 (ARR, TR, Verbindungen "
                      "im Feldvergleich)."}
    out.update({k: copy.deepcopy(v) for k, v in daten.items() if k != "races" and k not in OHNE_OBEN})
    out["params"] = {k: v for k, v in (out.get("params") or {}).items() if k not in OHNE_PARAMS}
    if (daten.get("modelle") or {}).get("power"):
        out["modelle"] = {"power": copy.deepcopy(daten["modelle"]["power"])}
    out["races"] = {rid: rennen(r, bias_alle) for rid, r in (daten.get("races") or {}).items()}
    return out


def export_markt(daten: dict) -> dict:
    """Marktdatei für Teil 2 des Skills (erst nach der blinden Einschätzung laden)."""
    return {"hinweis": "Claude-Version der Race Card, Teil 2 (Markt): je Rennen PMU-Prognose mit Rennkommentar, "
                       "Tipps, Konsens und Cribles, Marge, Reihenfolge nach Prognose-Rang; je Starter prono und "
                       "p_prog (Potenzmethode); mit Value-Modell je Starter value (Faktor, goldener Rahmen, faire "
                       "Quote gegen Prognose-Cote ohne Marge) und oben modelle.value / vorwaerts_test "
                       "(Verlässlichkeit). Erst nach der blinden Einschätzung lesen.",
            "date": daten.get("date"), "generated": daten.get("generated"),
            **({"modelle": {k: copy.deepcopy(v) for k, v in daten["modelle"].items() if k in ("value", "vorwaerts_test")}}
               if (daten.get("modelle") or {}).get("value") else {}),
            "races": {rid: rennen_markt(r) for rid, r in (daten.get("races") or {}).items()}}


def markt_pfad(pfad: Path) -> Path:
    """racecard_JJJJMMTT_claude.json -> racecard_JJJJMMTT_markt.json"""
    pfad = Path(pfad)
    return pfad.with_name(pfad.name.replace("_claude.json", "_markt.json")) if pfad.name.endswith("_claude.json") \
        else pfad.with_name(pfad.stem + "_markt.json")


def schreiben(daten: dict, pfad: Path) -> Path:
    """Blinde Datei nach `pfad`, Marktdatei daneben (markt_pfad)."""
    pfad = Path(pfad)
    pfad.write_text(json.dumps(export(daten), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    markt_pfad(pfad).write_text(json.dumps(export_markt(daten), ensure_ascii=False, separators=(",", ":")),
                                encoding="utf-8")
    return pfad
