#!/usr/bin/env python3
"""
France-Galop / McLloyd Tracking-PDFs ("*_last_times_fr.pdf") -> Analyse-Tabellen

Aufruf:
    pip install pdfplumber pypdf pandas
    python parse_tracking.py <ordner_mit_pdfs> -o <ausgabeordner> [--de] [--parquet]

Ergebnis (im Ausgabeordner):
    races.csv          1 Zeile pro Rennen (Bahn, Datum, Distanz, Tempo-Kennzahlen)
    leader_splits.csv  Zwischenzeiten des jeweils Führenden (T1..T6)
    runners.csv        1 Zeile pro Pferd (Platz, Zeiten, Wegverlust, abgeleitete Kennzahlen)
    sections.csv       1 Zeile pro Pferd und 200-m-Abschnitt (Zeit, km/h, Sprünge, Position)
    errors.csv         Dateien/Pferde, die nicht sauber gelesen werden konnten

--de       CSV mit ';' und Dezimalkomma (für deutsches Excel)
--parquet  zusätzlich Parquet-Dateien (z. B. für Databricks/PowerBI)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------
TIME = r"\d{2}:\d{2}\.\d{2}"          # 00:50.46
OFFTIME = r"\d+'\d{2}\"\d{2}"         # 1'53"70
NUM = r"-?\d+(?:,\d+)?"               # 62,17 / -9,45 / 60

MONTHS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
          "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
          "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}


def t2s(t: str | None) -> float | None:
    """'01:53.70' oder 1'53\"70 -> Sekunden."""
    if not t:
        return None
    m = re.fullmatch(r"(\d+):(\d{2})\.(\d{2})", t)
    if m:
        return int(m[1]) * 60 + int(m[2]) + int(m[3]) / 100
    m = re.fullmatch(r"(\d+)'(\d{2})\"(\d{2})", t)
    if m:
        return int(m[1]) * 60 + int(m[2]) + int(m[3]) / 100
    return None


def num(x: str | None) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x.replace(",", "."))
    except ValueError:
        return None


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def mark_to_m(mark: str, distance: int) -> int:
    """'DEP' -> Distanz, 'ARR' -> 0, '1600m' -> 1600 (Meter bis zum Ziel)."""
    if mark == "DEP":
        return distance
    if mark == "ARR":
        return 0
    return int(mark.rstrip("m"))


# --------------------------------------------------------------------------
# PDF -> Text pro Seite (zwei Engines, weil das Layout je nach Tool anders kommt)
# --------------------------------------------------------------------------
def read_pages(path: Path, engine: str) -> tuple[list[str], list[str]]:
    texts, links = [], []
    if engine == "plumber":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                # use_text_flow = Reihenfolge des PDF-Inhaltsstroms (Zellen bleiben zusammen)
                texts.append(p.extract_text(use_text_flow=True) or "")
                for h in (p.hyperlinks or []):
                    if h.get("uri"):
                        links.append(h["uri"])
    else:
        from pypdf import PdfReader
        r = PdfReader(str(path))
        for p in r.pages:
            texts.append(p.extract_text() or "")
            for a in (p.get("/Annots") or []):
                try:
                    uri = a.get_object().get("/A", {}).get("/URI")
                    if uri:
                        links.append(str(uri))
                except Exception:
                    pass
    return texts, links


# --------------------------------------------------------------------------
# Kopfbereich (auf jeder Seite gleich)
# --------------------------------------------------------------------------
def parse_header(text: str) -> dict:
    t = norm(text)
    h = {}
    m = re.search(r"Statistiques Tracking (.+?) C(\d+) - (.+) - (\d+)m (\w+) (\d{1,2}) (\w+) (\d{4}) - (\d{2}:\d{2})", t)
    if m:
        h["track"] = m[1].strip()
        h["race_no"] = int(m[2])
        h["race_name"] = m[3].strip()
        h["distance_m"] = int(m[4])
        mon = MONTHS.get(m[7].lower())
        if mon:
            h["date"] = f"{m[8]}-{mon:02d}-{int(m[6]):02d}"
        h["post_time"] = m[9]
        # Bodenangabe steht (falls vorhanden) zwischen Datum und "Redk du 1er"
        g = re.match(r" ?(.+?) \((\d+(?:,\d+)?)\) Redk du 1er", t[m.end():])
        if g:
            h["going"], h["going_value"] = g[1].strip(), num(g[2])
    m = re.search(r"Redk du 1er: ?(" + OFFTIME + ")", t)
    if m:
        h["winner_redk"] = m[1]
    m = re.search(r"Tronçons de (\d+)m", t)
    h["segment_m"] = int(m[1]) if m else None
    return h


# --------------------------------------------------------------------------
# Seite 1 (Übersicht)
# Zwei Layouts:
#   A (Flach):      Nr (Box) Pferd Jockey Platz Vmax Tx best Tx | T: Zeit Split Pos | Endzeit Letzte600 [vs1er]
#   B (Hindernis):  Nr Pferd Jockey Platz Vmax Tx [best Tx]     | T: Zeit Split Pos Sprünge | Endzeit Redk Distanz [vs1er]
# --------------------------------------------------------------------------
RUNNER_START = re.compile(r"(?:^| )(\d{1,2})(?: \((\d{1,2})\))? (?=[A-Z][A-Z' .()-])")


def _is_time(x): return re.fullmatch(TIME, x) is not None
def _is_off(x): return re.fullmatch(OFFTIME, x) is not None
def _is_int(x): return re.fullmatch(r"\d+", x) is not None
def _is_num(x): return re.fullmatch(NUM, x) is not None


def parse_summary(text: str, distance: int) -> tuple[list[dict], list[dict], list[str]]:
    t = norm(text)
    errors: list[str] = []

    segs = re.findall(r"(DEP|\d+m) - (\d+m|ARR)", t.split("Temps passage")[0])
    seg_end = [mark_to_m(b, distance) for _, b in segs]      # Meter bis Ziel am Ende von T1, T2, ...
    leader = []
    m = re.search(r"Durée du tronçon (.+?) Partant", t)
    if m:
        times = re.findall(TIME, m[1])
        for i in range(0, len(times) - 1, 2):
            k = i // 2
            leader.append({
                "seg": f"T{k + 1}",
                "from": segs[k][0] if k < len(segs) else None,
                "to": segs[k][1] if k < len(segs) else None,
                "leader_cum_s": t2s(times[i]),
                "leader_split_s": t2s(times[i + 1]),
            })

    body = t.split("vs. 1er", 1)[-1].split("Tracking data powered")[0]
    starts = list(RUNNER_START.finditer(body))
    runners = []
    for i, s in enumerate(starts):
        block = body[s.end(): starts[i + 1].start() if i + 1 < len(starts) else len(body)].strip()
        tok = block.split()
        k = next((j for j, x in enumerate(tok) if _is_num(x) or _is_time(x) or _is_off(x)), len(tok))
        r = {"saddle_no": int(s[1]), "draw": int(s[2]) if s[2] else None,
             "names_blob": " ".join(tok[:k]), "status": "gelaufen"}
        rest = tok[k:]
        if "NON PARTANT" in r["names_blob"]:
            r["status"] = "Nichtstarter"
            r["names_blob"] = r["names_blob"].replace("NON PARTANT", "").strip()
        if not rest:
            if r["status"] != "Nichtstarter":
                r["status"] = "ohne Daten"
            runners.append(r)
            continue
        try:
            j = 0
            # Platz (optional): Ganzzahl, auf die NICHT direkt ein "Tx" folgt (sonst ist es Vmax)
            r["place"] = None
            if _is_int(rest[0]) and (len(rest) == 1 or not re.fullmatch(r"T\d+", rest[1])):
                r["place"] = rest[0] if rest[0] != "0" else None
                j = 1
            # Vmax + Tx (optional)
            if j + 1 < len(rest) and _is_num(rest[j]) and re.fullmatch(r"T\d+", rest[j + 1]):
                r["vmax_kmh"] = num(rest[j]); r["vmax_seg"] = rest[j + 1]; j += 2
            if j + 1 < len(rest) and _is_time(rest[j]) and re.fullmatch(r"T\d+", rest[j + 1]):
                r["best_seg_s"], r["best_seg"] = t2s(rest[j]), rest[j + 1]; j += 2

            groups = []
            while j + 1 < len(rest) and _is_time(rest[j]) and _is_time(rest[j + 1]):
                g = {"cum": t2s(rest[j]), "split": t2s(rest[j + 1]), "ints": []}
                j += 2
                while j < len(rest) and _is_int(rest[j]) and len(g["ints"]) < 2:
                    g["ints"].append(int(rest[j])); j += 1
                groups.append(g)
            layout_b = any(len(g["ints"]) == 2 for g in groups)
            r["summary_pos"] = {}
            for n, g in enumerate(groups, 1):
                r[f"T{n}_cum_s"], r[f"T{n}_split_s"] = g["cum"], g["split"]
                pos = strides = None
                if layout_b:
                    if len(g["ints"]) == 2:
                        pos, strides = g["ints"]
                    elif len(g["ints"]) == 1:
                        strides = g["ints"][0]
                elif g["ints"]:
                    pos = g["ints"][0]
                r[f"T{n}_pos"] = pos
                if layout_b:
                    r[f"T{n}_strides"] = strides
                if pos is not None and n - 1 < len(seg_end):
                    r["summary_pos"][seg_end[n - 1]] = pos

            # Rest: Endzeit / Redk (OFFTIME), letzte 600 m (TIME), Distanz (>300) bzw. vs. 1er
            # (Werte ab der Endzeit lesen – davor stehen evtl. leere Nullspalten)
            tail = rest[j:]
            first_off = next((i for i, x in enumerate(tail) if _is_off(x)), None)
            if first_off is not None:
                tail = tail[first_off:]
            offs = [x for x in tail if _is_off(x)]
            times = [x for x in tail if _is_time(x)]
            nums = [num(x) for x in tail if _is_num(x) and x != "0"]
            r["official_time_s"] = t2s(offs[0]) if offs else None
            r["redk_official"] = offs[1] if len(offs) > 1 else None
            r["last600_s"] = t2s(times[0]) if times else None
            dist = [x for x in nums if x is not None and abs(x) > 300]
            vs = [x for x in nums if x is not None and abs(x) <= 300]
            r["distance_covered_m"] = dist[0] if dist else None
            r["dist_vs_winner_m"] = vs[0] if vs else (0.0 if r["place"] == "1" else None)
            r["time_is_official"] = r["official_time_s"] is not None
            if r["official_time_s"] is None and groups:
                r["official_time_s"] = groups[-1]["cum"]
            if not groups and not offs:
                r["status"] = "ohne Daten"
            elif r["place"] is None:
                r["status"] = "nicht platziert/ausgeschieden"
            elif not groups:
                r["status"] = "gelaufen (ohne Zwischenzeiten)"
            runners.append(r)
        except Exception as e:
            errors.append(f"Übersicht Nr. {s[1]}: {e}")
    return runners, leader, errors


# --------------------------------------------------------------------------
# Detailseite pro Pferd
# --------------------------------------------------------------------------
def _chart_positions(tokens: list[str], n: int) -> tuple[list[int | None], int]:
    """Positionsgrafik lesen: km/h-Beschriftungen (Kommazahl oder > 40) überspringen,
    je Abschnitt die nächste kleine Ganzzahl als Position nehmen."""
    pos, j = [], 0
    for _ in range(n):
        while j < len(tokens) and not (_is_int(tokens[j]) and int(tokens[j]) <= 40):
            j += 1
        if j < len(tokens):
            pos.append(int(tokens[j])); j += 1
        else:
            pos.append(None)
    return pos, j


def parse_detail(text: str, distance: int) -> dict:
    t = norm(text)
    d: dict = {}
    m = re.search(r"Cheval (.+?) Jockey (.+?) (?=Rang d'arrivée|Temps de parcours)", t)
    if not m:
        raise ValueError("Kopf der Detailseite nicht erkannt")
    d["horse"], d["jockey"] = m[1].strip(), m[2].strip()
    m = re.search(r"Rang d'arrivée (\S+)", t) or re.search(r"\(rang (\S+?),", t)
    d["place_detail"] = m[1] if m else None
    m = re.search(rf"Temps de parcours ({TIME})", t)
    d["race_time_s"] = t2s(m[1]) if m else None
    m = re.search(rf"redk ?: ?({OFFTIME})", t)
    d["redk"] = m[1] if m else None
    m = re.search(rf"Vitesse moyenne ({NUM}) ", t + " ")
    d["avg_speed_kmh"] = num(m[1]) if m else None
    m = re.search(r"Distance parcourue (\d+(?:,\d+)?)m", t)
    d["distance_covered_detail_m"] = num(m[1]) if m else None
    m = re.search(r"Nombre de foulées (\d+)", t)
    d["strides_total"] = int(m[1]) if m else None

    row = re.compile(rf"(DEP|\d{{3,4}}m) (\d{{2,4}}m|ARR) ({TIME}) ({TIME}) ({NUM}) (\d+)")
    rows = list(row.finditer(t))
    secs = []
    for r in rows:
        f, to = mark_to_m(r[1], distance), mark_to_m(r[2], distance)
        length, strides = f - to, int(r[6])
        secs.append({"seg_from": r[1], "seg_to": r[2], "m_to_go": to, "seg_len_m": length,
                     "cum_s": t2s(r[3]), "split_s": t2s(r[4]), "speed_kmh": num(r[5]), "strides": strides,
                     "stride_len_m": round(length / strides, 3) if strides else None, "position": None})

    # Hindernis-Abschnitte (von Sprung zu Sprung). Beschriftung: "1/13 2/13" oder Hindernisnamen
    obs = []
    names = re.search(r"Départ (.+?) Arrivée Tronçons", t)
    d["obstacles"] = names[1].strip() if names else None
    otab = re.search(r"Longueurs foulées Vitesse moyenne \(km/h\) Position en course (.*)", t)
    last_end = None
    if otab:
        body = otab[1].split("Tracking data powered")[0]
        orow = re.compile(rf"(.+?) ({TIME}) ({TIME})(?: ({NUM}) ({NUM}) ({NUM}) (\d+) ({NUM}))?(?= |$)")
        prev_to, pos0 = "Départ", 0
        for r in orow.finditer(body):
            label = r[1].strip()
            if label.startswith(prev_to + " "):
                f_, to = prev_to, label[len(prev_to) + 1:]
            else:
                parts = label.split(" ", 1)
                f_, to = parts[0], (parts[1] if len(parts) > 1 else "")
            sl = num(r[8])
            obs.append({"obs_no": len(obs) + 1, "obs_from": f_, "obs_to": to,
                        "cum_s": t2s(r[2]), "split_s": t2s(r[3]),
                        "speed_kmh": num(r[4]), "dist_m": num(r[5]), "dist_covered_m": num(r[6]),
                        "strides": int(r[7]) if r[7] else None,
                        "stride_len_m": sl if sl is not None and 3 <= sl <= 12 else None,   # offensichtliche Messfehler raus
                        "position": None})
            prev_to = to
            last_end = otab.start(1) + r.end()

    # Positionsgrafiken am Seitenende
    last = last_end if last_end is not None else (rows[-1].end() if rows else None)
    if last is not None:
        tail = t[last:].split("Tracking data powered")[0].split()
        p1, used = _chart_positions(tail, len(secs))
        p2, _ = _chart_positions(tail[used:], len(obs))
        if secs and all(p is not None for p in p1):
            for s_, p in zip(secs, p1):
                s_["position"] = p
        for o, p in zip(obs, p2):
            o["position"] = p
    d["sections"], d["obstacle_sections"] = secs, obs
    d["positions_from_chart"] = bool(secs) and all(s_["position"] is not None for s_ in secs)
    return d


# --------------------------------------------------------------------------
# Ein PDF komplett
# --------------------------------------------------------------------------
def _is_detail_page(x: str) -> bool:
    return "Données de tracking" in x or "Rang d'arrivée" in x


def parse_pages(texts: list[str], race_id: str, links: list[str]) -> dict:
    header = parse_header(texts[0])
    distance = header.get("distance_m") or 0
    summary_txt = [x for x in texts if not _is_detail_page(x)]
    detail_txt = [x for x in texts if _is_detail_page(x)]

    summ, leader, errors = parse_summary("\n".join(summary_txt), distance)
    details = []
    for x in detail_txt:
        try:
            details.append(parse_detail(x, distance))
        except Exception as e:
            errors.append(f"Detailseite: {e}")

    by_name = {d["horse"]: d for d in details}
    runners, sections, obstacles = [], [], []
    for s in summ:
        d = next((v for k, v in sorted(by_name.items(), key=lambda kv: -len(kv[0]))
                  if s["names_blob"].startswith(k)), None)
        if d:
            horse, jockey = d["horse"], d["jockey"]
        else:
            jm = re.search(r" ((?:Mme |Mlle |Mr |M\. )?[A-Z]\.(?:-?[A-Z]\.)* \S.*)$", s["names_blob"])
            horse = s["names_blob"][: jm.start()] if jm else s["names_blob"]
            jockey = jm[1] if jm else None
            if s["status"] in ("gelaufen",):
                errors.append(f"Keine Detailseite für Nr. {s['saddle_no']} ({s['names_blob']})")
        if jockey == "NON PARTANT":
            jockey = None

        if d and d["sections"]:
            secs = d["sections"]
            sp = s.get("summary_pos", {})
            ok = d["positions_from_chart"] and all(
                next((x["position"] for x in secs if x["m_to_go"] == m), v) == v for m, v in sp.items())
            if not ok:  # Fallback: Positionen aus der Übersicht
                for sec in secs:
                    sec["position"] = sp.get(sec["m_to_go"])
                    if sec["m_to_go"] == 0 and str(s.get("place") or "").isdigit():
                        sec["position"] = int(s["place"])
            for sec in secs:
                sections.append({"race_id": race_id, "horse": horse, "saddle_no": s["saddle_no"], **sec})
        if d:
            for o in d["obstacle_sections"]:
                obstacles.append({"race_id": race_id, "horse": horse, "saddle_no": s["saddle_no"], **o})

        r = {"race_id": race_id, "horse": horse, "jockey": jockey,
             **{k: v for k, v in s.items() if k not in ("names_blob", "summary_pos")}}
        if r["status"] == "ohne Daten" and d and (d["sections"] or d["obstacle_sections"]):
            r["status"] = "nicht platziert/ausgeschieden"      # Übersicht leer, aber Streckendaten vorhanden
        if d:
            for k in ("redk", "avg_speed_kmh", "strides_total"):
                r[k] = d.get(k)
            if r.get("distance_covered_m") is None:
                r["distance_covered_m"] = d.get("distance_covered_detail_m")
            if r.get("avg_speed_kmh") is None and r.get("official_time_s") and distance:
                r["avg_speed_kmh"] = round(distance / r["official_time_s"] * 3.6, 2)
            basis = d["sections"] or _pseudo_sections(d["obstacle_sections"])
            if basis:
                r.update(derive_runner(basis, r.get("avg_speed_kmh")))
        runners.append(r)

    times = [r["official_time_s"] for r in runners if r.get("official_time_s") and r.get("place")]
    if times:
        best = min(times)
        for r in runners:
            if r.get("official_time_s"):
                r["behind_winner_s"] = round(r["official_time_s"] - best, 2)

    obstacles_line = next((d["obstacles"] for d in details if d.get("obstacles")), None)
    n_obs = max((len(d["obstacle_sections"]) for d in details), default=0)
    race = {"race_id": race_id, **header,
            "race_type": "Hindernis" if (obstacles_line or n_obs) else "Flach",
            "obstacles": obstacles_line,
            "n_obstacles": max(n_obs - 1, 0),
            "runners": sum(r["status"] != "Nichtstarter" for r in runners),
            "dataset_link": next((l for l in links if "france-galop" not in l), links[0] if links else None)}
    race.update(derive_race(leader, distance))
    return {"race": race,
            "leader": [{"race_id": race_id, **l} for l in leader],
            "runners": runners, "sections": sections, "obstacles": obstacles,
            "errors": [{"race_id": race_id, "error": e} for e in errors]}


# --------------------------------------------------------------------------
# Abgeleitete Kennzahlen
# --------------------------------------------------------------------------
def _pseudo_sections(obs: list[dict]) -> list[dict]:
    """Aus Hindernis-Abschnitten Abschnitte im Format von 'sections' bauen (Meter bis Ziel rückwärts)."""
    rows = [o for o in obs if o.get("dist_m") and o.get("split_s")]
    out, to_go = [], 0
    for o in reversed(rows):
        out.append({"m_to_go": to_go, "seg_len_m": o["dist_m"], "split_s": o["split_s"],
                    "position": o["position"], "stride_len_m": o["stride_len_m"]})
        to_go += o["dist_m"]
    return list(reversed(out))


def _speed_last(secs: list[dict], min_len: int) -> tuple[float | None, int]:
    """Durchschnittstempo über die letzten Abschnitte, bis mindestens min_len Meter erreicht sind."""
    t = dist = 0
    for s in reversed(secs):
        t += s["split_s"] or 0; dist += s["seg_len_m"]
        if dist >= min_len:
            break
    return (round(dist / t * 3.6, 2) if t else None), dist


def derive_runner(secs: list[dict], avg_speed: float | None) -> dict:
    out = {}
    v_fin, basis = _speed_last(secs, 400)
    out["speed_finish_kmh"], out["finish_basis_m"] = v_fin, basis   # Flach: 400 m, Hindernis: 1000 m
    out["speed_last400_kmh"] = v_fin if basis == 400 else None
    v600, b600 = _speed_last(secs, 600)
    out["speed_last600_kmh"] = v600 if b600 == 600 else None
    if avg_speed and v_fin:
        out["finish_index"] = round(v_fin / avg_speed * 100, 1)
    pos = {s["m_to_go"]: s["position"] for s in secs}
    ref = min((m for m in pos if m >= 800 and pos[m]), default=None)   # Messpunkt ab 800 m vor dem Ziel
    if ref is not None and pos.get(0):
        out["pos_gain_800_finish"] = pos[ref] - pos[0]
    body = [s["stride_len_m"] for s in secs[1:] if s["m_to_go"] >= 400 and s["stride_len_m"]]
    last = [s["stride_len_m"] for s in secs if s["m_to_go"] < 400 and s["stride_len_m"]]
    if body and last:
        out["stride_len_mid_m"] = round(sum(body) / len(body), 3)
        out["stride_len_last_m"] = round(sum(last) / len(last), 3)
        out["stride_change_pct"] = round((out["stride_len_last_m"] / out["stride_len_mid_m"] - 1) * 100, 1)
    return out


def derive_race(leader: list[dict], distance: int) -> dict:
    """Tempo aus den Zeiten des Führenden: früher Teil vs. letzter Abschnitt(e) (mind. 600 m)."""
    if not leader or not distance:
        return {}
    total = leader[-1]["leader_cum_s"]
    seg_len = []
    prev = distance
    for l in leader:
        to = 0 if l["to"] == "ARR" else int(str(l["to"]).rstrip("m")) if l["to"] else None
        if to is None:
            return {}
        seg_len.append(prev - to); prev = to
    late_t = late_d = 0
    for l, d in zip(reversed(leader), reversed(seg_len)):
        late_t += l["leader_split_s"]; late_d += d
        if late_d >= 600:
            break
    early_t, early_d = total - late_t, distance - late_d
    if early_t <= 0 or late_t <= 0 or early_d <= 0:
        return {}
    v_early, v_late = early_d / early_t * 3.6, late_d / late_t * 3.6
    return {"leader_time_s": total, "leader_late_s": round(late_t, 2), "leader_late_m": late_d,
            "leader_last600_s": round(late_t, 2) if late_d == 600 else None,
            "pace_early_kmh": round(v_early, 2), "pace_late_kmh": round(v_late, 2),
            "pace_ratio": round(v_early / v_late * 100, 1)}


def parse_pdf(path: Path, race_id: str | None = None) -> dict:
    """race_id: wird von der Pipeline aus dem PMU-Programm vorgegeben, damit
    Tracking- und PMU-Tabellen dieselbe Kennung haben. Ohne Vorgabe wird sie
    aus dem Dateinamen abgeleitet."""
    if race_id is None:
        m = re.search(r"(\d{8})([A-Z]{3})(\d{2})", path.name)
        race_id = f"{m[1]}_{m[2]}_R{int(m[3])}" if m else path.stem
    last_err = None
    for engine in ("plumber", "pypdf"):      # zweite Engine, falls die erste nichts liefert
        try:
            texts, links = read_pages(path, engine)
            res = parse_pages(texts, race_id, links)
            if res["runners"] and (res["sections"] or res["obstacles"]):
                res["race"]["file"] = path.name
                res["race"]["engine"] = engine
                return res
            last_err = "keine Starter/Abschnitte erkannt"
        except Exception as e:
            last_err = str(e)
    raise ValueError(last_err)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help="Ordner mit PDFs (wird rekursiv durchsucht) oder einzelne PDF")
    ap.add_argument("-o", "--out", type=Path, default=Path("tracking_out"))
    ap.add_argument("--de", action="store_true", help="CSV mit ; und Dezimalkomma")
    ap.add_argument("--parquet", action="store_true", help="zusätzlich Parquet schreiben")
    a = ap.parse_args()

    files = [a.input] if a.input.is_file() else sorted(a.input.rglob("*.pdf"))
    if not files:
        sys.exit("Keine PDFs gefunden.")
    tables = {k: [] for k in ("races", "leader_splits", "runners", "sections", "obstacles", "errors")}
    for i, f in enumerate(files, 1):
        try:
            r = parse_pdf(f)
            tables["races"].append(r["race"])
            tables["leader_splits"] += r["leader"]
            tables["runners"] += r["runners"]
            tables["sections"] += r["sections"]
            tables["obstacles"] += r["obstacles"]
            tables["errors"] += r["errors"]
            print(f"[{i}/{len(files)}] {f.name}: {len(r['runners'])} Starter")
        except Exception as e:
            tables["errors"].append({"race_id": f.name, "error": str(e)})
            print(f"[{i}/{len(files)}] {f.name}: FEHLER {e}")

    a.out.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        df = pd.DataFrame(rows)
        kw = {"sep": ";", "decimal": ","} if a.de else {}
        df.to_csv(a.out / f"{name}.csv", index=False, encoding="utf-8-sig", **kw)
        if a.parquet and name != "errors" and not df.empty:
            df.to_parquet(a.out / f"{name}.parquet", index=False)
    print(f"\nFertig: {len(tables['races'])} Rennen, {len(tables['runners'])} Starter, "
          f"{len(tables['errors'])} Warnungen -> {a.out}/")


if __name__ == "__main__":
    main()
