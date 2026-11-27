"""Ergebnisanalyse: Durchgänge eines Renntags gegen den Einlauf (ADR 0003, Skill ergebnis-analyse).

Mechanik, die kein Urteil braucht: je Rennen mit Durchgang den Sieger einer Siegergruppe zuordnen (treffer,
verpasster_sieger, massstab, sonstig), die Fälle für die Analyse sammeln (verpasste Sieger, verlorene Claude-Tipps,
Treffer), das Regelprotokoll fortschreiben und auswerten, analysierte Tage und Vorschläge ablegen. Alles Urteil
(welcher Datenpunkt hätte geholfen, welcher Vorschlag) macht der Skill.

Nur Standardbibliothek, außer zum Lesen des Parquets (pyarrow, in der Aufgabe per pip).

Aufruf:
    python3 -I ergebnis_analyse.py material KARTE RUNNERS.parquet DURCHGANG.json … --aus analyse_JJJJMMTT.json
        Tagesmaterial (Datum aus der Karte).
    python3 -I ergebnis_analyse.py faelle analyse_JJJJMMTT.json [RxCy]
        Zählung und je Fall eine Zeile; mit RxCy der Materialeintrag dieses Rennens (Pro/Gegen, Maßstäbe).
    python3 -I ergebnis_analyse.py gegenprobe KARTE analyse_JJJJMMTT.json MUSTER
        Verlierer des Tages (Kandidaten, Maßstäbe), deren Blatt MUSTER (Regex) enthält: Anzahl, Namen, Zeile.
    python3 -I ergebnis_analyse.py protokoll analyse_JJJJMMTT.json [--ordner auswertung]
        Regelprotokoll mit den Kennungen des Tages fortschreiben (ersetzt Zeilen desselben Tages).
    python3 -I ergebnis_analyse.py bericht [--ordner auswertung]
        Regelprotokoll je Kennung und Richtung als JSON (n, Siege, erwartet, A/E, z, unter_druck).
    python3 -I ergebnis_analyse.py rueckschau [KENNUNG …] [--ordner auswertung]
        Je Kennung bisherige Tipps und abgelehnte Kandidaten, die sie zitierten, mit Siegen und Siegern (JSON);
        ohne Kennung alle bisherigen Treffer mit ihren Kennungen.
    python3 -I ergebnis_analyse.py drift [--ordner auswertung]
        Je Tag und für die letzten 7 Tage gegen davor: Kandidaten, wette/klein/nein, Tipp-Anteil, anlass; dazu
        angenommene Vorschläge nach wirkung (JSON).
    python3 -I ergebnis_analyse.py verdichtung [--ordner auswertung]
        Anlässe zum Verdichten von EINSICHTEN.md als JSON (Abschnitt voll, Datei lang, vorläufige Einsicht mit 20 Fällen).
    python3 -I ergebnis_analyse.py naechster-tag JJJJMMTT … [--ordner auswertung]
        Ältester der genannten Tage, der noch nicht analysiert ist (oder „keiner“).
    python3 -I ergebnis_analyse.py tag-abschliessen JJJJMMTT --commit SHA --vorschlaege N [--ordner auswertung]
    python3 -I ergebnis_analyse.py vorschlaege VORSCHLAEGE.json [--ordner auswertung]
        Vorschläge anlegen oder Entscheidungen eintragen (Schlüssel id).
    python3 -I ergebnis_analyse.py offen [--ordner auswertung]
        Unentschiedene Vorschläge als JSON.
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import durchgang as dg  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")
ORDNER = Path(__file__).resolve().parent / "auswertung"
PROTOKOLL = "regelprotokoll.csv"
TAGE = "ergebnisanalyse_tage.csv"
VORSCHLAEGE = "vorschlaege.csv"
TIPP = {"wette", "klein"}
DRUCK_N, DRUCK_Z = 20, 2.0          # Regel unter Druck: mindestens so viele Fälle und |z| gegen ihre Richtung

PROTOKOLL_FELDER = ["datum", "race_id", "no", "horse", "kennung", "richtung", "urteil", "fk", "p_markt", "gewonnen"]
TAGE_FELDER = ["datum", "analysiert", "commit", "vorschlaege"]
VORSCHLAG_FELDER = ["id", "datum", "titel", "fall", "rennen", "race_id", "no", "horse", "durchgang", "datenpunkt",
                    "gegenprobe", "art", "zieldatei", "kennung", "alt", "text", "gewicht", "wirkung", "entscheidung",
                    "notiz", "entschieden"]
ENTSCHEIDUNGEN = {"offen", "ja", "nein", "geaendert"}
WIRKUNGEN = {"strenger", "lockerer", "neutral"}     # leer bei Vorschlägen vor dem 27.11.2026


# ---------------------------------------------------------------- Einlauf

def einlauf(zeilen: list[dict]) -> dict[str, dict]:
    """race_id → {sieger: [Nr.], starter: {Nr.: {horse, pos, odds_final, nichtstarter}}} aus pmu_runners-Zeilen.
    Dead Heat: mehrere Sieger."""
    out: dict[str, dict] = {}
    for z in zeilen:
        r = out.setdefault(str(z["race_id"]), {"sieger": [], "starter": {}})
        no = int(z["saddle_no"])
        st = f"{z.get('status') or ''} {z.get('incident') or ''}".upper()
        pos = z.get("finish_pos")
        pos = int(pos) if pos is not None and not (isinstance(pos, float) and math.isnan(pos)) else None
        r["starter"][no] = {"horse": z.get("horse"), "pos": pos, "odds_final": z.get("odds_final"),
                            "nichtstarter": "NON_PARTANT" in st}
        if pos == 1:
            r["sieger"].append(no)
    for r in out.values():
        r["sieger"].sort()
    return out


def einlauf_laden(parquet: str | Path) -> dict[str, dict]:
    import pyarrow.parquet as pq   # nur hier gebraucht
    spalten = ["race_id", "saddle_no", "horse", "finish_pos", "odds_final", "status", "incident"]
    return einlauf(pq.read_table(str(parquet), columns=spalten).to_pylist())


# ---------------------------------------------------------------- Tagesmaterial

def _overround(rennen: dict, ein: dict) -> float:
    """Σ 1/Festkurs (Karte) über die Starter, die gelaufen sind."""
    s = 0.0
    for x in rennen.get("runners") or []:
        fk = (x.get("fk") or {}).get("sieg")
        st = ein["starter"].get(int(x["no"])) if x.get("no") is not None else None
        if fk and fk > 1 and not x.get("nr") and not (st and st["nichtstarter"]):
            s += 1 / fk
    return s


def _gruppe(no: int, kand: dict[int, dict], massstab: set[int]) -> str:
    if no in kand:
        return "treffer" if kand[no]["urteil"] in TIPP else "verpasster_sieger"
    return "massstab" if no in massstab else "sonstig"


def material(datum: str, karte: dict, durchgaenge: dict[str, dict], ein: dict[str, dict]) -> dict:
    """Tagesmaterial für den Skill ergebnis-analyse. ``durchgaenge`` = durchgang.je_rennen(...).
    Marktchance eines Kandidaten = (1/Festkurs beim Durchgang) / Σ 1/Festkurs der Karte über die Starter."""
    datum = str(datum).replace("-", "")
    zaehlung = dict.fromkeys(["treffer", "verpasster_sieger", "massstab", "sonstig", "ohne_durchgang",
                              "verlorener_tipp"], 0)
    rennen_out, faelle = [], []
    for r in sorted(dg.rennen_liste(karte), key=lambda r: (r.get("time") or "", str(r.get("race_id")))):
        rid = str(r.get("race_id"))
        e = ein.get(rid)
        if not e or not e["sieger"]:
            continue                                   # nicht gelaufen oder ohne Einlauf
        d = durchgaenge.get(rid)
        kurz = f"R{r.get('reunion')}C{r.get('race_no')}"
        if not d:
            if not dg.ist_araber(r):
                zaehlung["ohne_durchgang"] += 1
            continue
        over = _overround(r, e) or 1.0
        kand = {}
        for k in d.get("kandidaten") or []:
            st = e["starter"].get(int(k["no"]), {})
            fk = k.get("fk")
            kand[int(k["no"])] = {
                **{f: k.get(f) for f in ("no", "horse", "urteil", "fk", "mq", "spanne", "p_modell", "value", "pro",
                                         "gegen", "fragen", "ausschlag")},
                "pos": st.get("pos"), "nichtstarter": bool(st.get("nichtstarter")),
                "gewonnen": int(k["no"]) in e["sieger"],
                "p_markt": (1 / fk) / over if fk and fk > 1 else None,
                "kennungen": dg.zitierte(k)}
        ms = {int(m["no"]): m for m in d.get("massstab") or []}
        massstab = [{**m, "pos": e["starter"].get(no, {}).get("pos"), "gewonnen": no in e["sieger"]}
                    for no, m in ms.items()]
        sieger = []
        for no in e["sieger"]:
            g = _gruppe(no, kand, set(ms))
            zaehlung[g] += 1
            sieger.append({"no": no, "horse": e["starter"].get(no, {}).get("horse"), "gruppe": g,
                           "odds_final": e["starter"].get(no, {}).get("odds_final")})
        eintrag = {"race_id": rid, "rennen": kurz, "zeit": r.get("time"), "bahn": r.get("course"),
                   "stand": d.get("stand"), "vergleich": d.get("vergleich"), "sieger": sieger,
                   "kandidaten": list(kand.values()), "massstab": massstab}
        rennen_out.append(eintrag)
        for k in kand.values():
            if k["nichtstarter"]:
                continue
            art = ("treffer" if k["gewonnen"] else "verlorener_tipp") if k["urteil"] in TIPP else \
                ("verpasster_sieger" if k["gewonnen"] else None)
            if art == "verlorener_tipp":
                zaehlung["verlorener_tipp"] += 1
            if art:
                faelle.append({"art": art, "race_id": rid, "rennen": kurz, "bahn": r.get("course"),
                               **{f: k[f] for f in ("no", "horse", "urteil", "fk", "pos", "ausschlag", "kennungen")}})
    return {"datum": datum, "rennen": rennen_out, "faelle": faelle, "zaehlung": zaehlung}


# ---------------------------------------------------------------- Fälle und Gegenprobe (sparsam lesen)

def faelle_kurz(m: dict) -> str:
    """Zählung und je Fall eine Zeile – statt das ganze Material zu lesen."""
    z = [json.dumps(m["zaehlung"], ensure_ascii=False)]
    for f in m["faelle"]:
        z.append(f"{f['art']:<18} {f['rennen']:<6} {f['no']:>2} {f['horse']} · {f['urteil']} · FK {f.get('fk')} · "
                 f"Platz {f.get('pos')} · {' '.join(f.get('kennungen') or []) or '–'} · {f.get('ausschlag') or ''}")
    return "\n".join(z)


def verlierer(m: dict) -> list[dict]:
    """Verlierer des Tages für die Gegenprobe: Kandidaten (ohne Nichtstarter) und Maßstäbe, die nicht gewonnen haben."""
    aus = []
    for r in m["rennen"]:
        for k in r["kandidaten"]:
            if not k["gewonnen"] and not k.get("nichtstarter"):
                aus.append({"rennen": r["rennen"], "no": int(k["no"]), "horse": k["horse"], "rolle": k["urteil"]})
        for ms in r["massstab"]:
            if not ms.get("gewonnen"):
                aus.append({"rennen": r["rennen"], "no": int(ms["no"]), "horse": ms.get("horse"), "rolle": "massstab"})
    return aus


BLOCK = re.compile(r"^### (?:MASSSTAB [^–]*– )?(\d+) ")


def bloecke(text: str) -> dict[tuple[str, int], str]:
    """Ausgabe von blatt.py → {(RxCy, Nr.): Blatt des Pferdes}."""
    aus: dict[tuple[str, int], str] = {}
    rennen, key = None, None
    for zeile in text.splitlines():
        if zeile.startswith("## "):
            rennen, key = zeile[3:].split()[0].upper(), None
            continue
        mt = BLOCK.match(zeile)
        if mt and rennen:
            key = (rennen, int(mt.group(1)))
            aus[key] = ""
        if key:
            aus[key] += zeile + "\n"
    return aus


def gegenprobe(m: dict, blaetter: dict[tuple[str, int], str], muster: str) -> dict:
    """Verlierer, deren Blatt ``muster`` (regulärer Ausdruck, ohne Groß/klein) enthält, mit der ersten passenden Zeile."""
    rx = re.compile(muster, re.IGNORECASE)
    alle = verlierer(m)
    treffer = []
    for v in alle:
        b = blaetter.get((v["rennen"].upper(), v["no"]), "")
        zeile = next((z.strip() for z in b.splitlines() if rx.search(z)), None)
        if zeile:
            treffer.append({**v, "zeile": zeile[:200]})
    return {"muster": muster, "verlierer": len(alle), "mit_muster": len(treffer), "treffer": treffer,
            "ohne_blatt": [f"{v['rennen']} {v['no']}" for v in alle if (v["rennen"].upper(), v["no"]) not in blaetter]}


def blaetter_lesen(karte: str, rennen: list[str]) -> dict[tuple[str, int], str]:
    """blatt.py des Durchgang-Skills für die Rennen ausführen und in Blöcke je Pferd zerlegen."""
    import contextlib
    import importlib.util
    import io
    spec = importlib.util.spec_from_file_location("blatt", dg.SKILL_ORDNER / "scripts" / "blatt.py")
    blatt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(blatt)
    puffer = io.StringIO()
    with contextlib.redirect_stdout(puffer):
        blatt.main(["blatt.py", karte, *rennen])
    return bloecke(puffer.getvalue())


# ---------------------------------------------------------------- Regelprotokoll

def _richtung(feld: str, urteil: str) -> str:
    if feld == "pro":
        return "pro"
    if feld in ("gegen", "fragen"):
        return "gegen"
    return "pro" if urteil in TIPP else "gegen"        # Ausschlag: Richtung des Urteils


def protokoll_zeilen(m: dict) -> list[dict]:
    """Je Kandidat (gelaufen) und zitierter Kennung eine Zeile; dieselbe Kennung in derselben Richtung zählt einmal."""
    out = []
    for r in m["rennen"]:
        for k in r["kandidaten"]:
            if k["nichtstarter"] or k["p_markt"] is None:
                continue
            gesehen = set()
            for feld in dg.ZITAT_FELDER:
                for ken in k["kennungen"][feld]:
                    rt = _richtung(feld, k["urteil"])
                    if (ken, rt) in gesehen:
                        continue
                    gesehen.add((ken, rt))
                    out.append({"datum": m["datum"], "race_id": r["race_id"], "no": k["no"], "horse": k["horse"],
                                "kennung": ken, "richtung": rt, "urteil": k["urteil"], "fk": k["fk"],
                                "p_markt": round(k["p_markt"], 5), "gewonnen": int(k["gewonnen"])})
    return out


def _csv_lesen(pfad: Path) -> list[dict]:
    if not pfad.exists():
        return []
    with pfad.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _csv_schreiben(pfad: Path, felder: list[str], zeilen: list[dict]) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with pfad.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=felder, extrasaction="ignore")
        w.writeheader()
        w.writerows(zeilen)


def protokoll_lesen(ordner: str | Path = ORDNER) -> list[dict]:
    return _csv_lesen(Path(ordner) / PROTOKOLL)


def protokoll_fortschreiben(ordner: str | Path, m: dict) -> int:
    alt = [z for z in protokoll_lesen(ordner) if z["datum"] != m["datum"]]
    neu = protokoll_zeilen(m)
    _csv_schreiben(Path(ordner) / PROTOKOLL, PROTOKOLL_FELDER,
                   sorted(alt + neu, key=lambda z: (str(z["datum"]), str(z["race_id"]), int(z["no"]))))
    return len(neu)


def bericht(zeilen: list[dict], stillgelegt: dict[str, str] | None = None) -> list[dict]:
    """Je Kennung und Richtung: n, Siege, erwartete Siege (Σ Marktchance), A/E, z; unter_druck, wenn n ≥ DRUCK_N und
    z gegen die Richtung (Pro-Regel: z ≤ −2; Gegen-Regel: z ≥ +2)."""
    stillgelegt = stillgelegt or {}
    gruppen: dict[tuple[str, str], list[dict]] = {}
    for z in zeilen:
        ken = _aktuell(z["kennung"], stillgelegt)     # zusammengefasste Einsicht zählt unter der verbleibenden
        gruppen.setdefault((ken, z["richtung"]), []).append(z)
    out = []
    for (ken, rt), zs in sorted(gruppen.items()):
        n = len(zs)
        siege = sum(int(z["gewonnen"]) for z in zs)
        p = [float(z["p_markt"]) for z in zs]
        erw = sum(p)
        var = sum(x * (1 - x) for x in p)
        zwert = (siege - erw) / math.sqrt(var) if var > 0 else 0.0
        druck = n >= DRUCK_N and (zwert <= -DRUCK_Z if rt == "pro" else zwert >= DRUCK_Z)
        out.append({"kennung": ken, "richtung": rt, "n": n, "siege": siege, "erwartet": round(erw, 2),
                    "ae": round(siege / erw, 2) if erw else None, "z": round(zwert, 2), "unter_druck": druck})
    return out


def _aktuell(ken: str, stillgelegt: dict[str, str]) -> str:
    while ken in stillgelegt:
        ken = stillgelegt[ken]
    return ken


def _zeitraum(zeilen: list[dict]) -> str | None:
    tage = sorted({str(z["datum"]) for z in zeilen})
    return f"{tage[0]}–{tage[-1]}" if tage else None


def _pferd(z: dict) -> dict:
    return {f: z.get(f) for f in ("datum", "race_id", "no", "horse", "urteil", "fk")}


def rueckschau(zeilen: list[dict], kennungen: list[str], stillgelegt: dict[str, str] | None = None) -> dict:
    """Je Kennung: wie viele bisherige Claude-Tipps und abgelehnte Kandidaten sie zitierten (je Pferd einmal, gleich in
    welcher Richtung), wie viele gewannen, wie viele der Markt erwartete, und die Sieger mit Namen. Zeigt bei einem
    verschärfenden Vorschlag, welche früheren Treffer die Regel gestrichen hätte. Ohne Kennung: alle bisherigen
    Treffer mit ihren Kennungen (für eine neue Kennung, die noch nicht im Regelprotokoll steht)."""
    stillgelegt = stillgelegt or {}
    pferde: dict[tuple, dict] = {}
    for z in zeilen:
        p = pferde.setdefault((str(z["datum"]), str(z["race_id"]), str(z["no"])),
                              {**_pferd(z), "gewonnen": int(z["gewonnen"]), "p_markt": float(z["p_markt"] or 0),
                               "kennungen": {}})
        p["kennungen"].setdefault(_aktuell(z["kennung"], stillgelegt), set()).add(z["richtung"])
    aus: dict = {"zeitraum": _zeitraum(zeilen)}
    if not kennungen:
        aus["treffer"] = [{**_pferd(p), "kennungen": sorted(p["kennungen"])}
                          for k, p in sorted(pferde.items()) if p["gewonnen"] and p["urteil"] in TIPP]
        return aus
    aus["kennungen"] = []
    for ken in dict.fromkeys(_aktuell(k, stillgelegt) for k in kennungen):
        eintrag = {"kennung": ken}
        for gruppe, urteile in (("tipps", TIPP), ("abgelehnt", {"nein"})):
            ps = [p for _, p in sorted(pferde.items()) if ken in p["kennungen"] and p["urteil"] in urteile]
            eintrag[gruppe] = {
                "n": len(ps), "siege": sum(p["gewonnen"] for p in ps),
                "erwartet": round(sum(p["p_markt"] for p in ps), 2),
                "sieger": [f"{p['horse']} {p['datum']} {str(p['race_id'])[8:]} ({p['urteil']}, FK {p['fk']}, "
                           f"{'/'.join(sorted(p['kennungen'][ken]))})" for p in ps if p["gewonnen"]]}
        aus["kennungen"].append(eintrag)
    return aus


# ---------------------------------------------------------------- Drift

DRIFT_FENSTER = 7          # Tage bis einschließlich des letzten Tages
DRIFT_GRENZE = 0.5         # Tipp-Anteil im Fenster unter diesem Bruchteil des Anteils davor → Anlass


def _anteile(urteile: list[str]) -> dict:
    n = len(urteile)
    aus = {"n": n, **{u: urteile.count(u) for u in ("wette", "klein", "nein")}}
    aus["tipp_anteil"] = round((aus["wette"] + aus["klein"]) / n, 3) if n else None
    return aus


def drift(pferde: list[dict], vorschlaege: list[dict], fenster: int = DRIFT_FENSTER) -> dict:
    """Wird der Durchgang strenger? Je Tag und für die letzten ``fenster`` Tage gegen die Zeit davor: Zahl der Kandidaten
    und wie viele wette / klein / nein (je Pferd einmal); dazu die angenommenen Vorschläge nach ``wirkung``. Anlass,
    wenn der Tipp-Anteil im Fenster unter DRIFT_GRENZE × Anteil davor fällt. ``pferde``: Zeilen mit datum, race_id,
    no, urteil (Regelprotokoll oder Kandidatenprotokoll; doppelte Pferde zählen einmal)."""
    je: dict[tuple, str] = {}
    for z in pferde:
        je[(str(z["datum"]), str(z["race_id"]), str(z["no"]))] = z["urteil"]
    tage = sorted({d for d, _, _ in je})
    aus: dict = {"tage": [{"datum": t, **_anteile([u for (d, _, _), u in je.items() if d == t])} for t in tage]}
    if tage:
        ende = datetime.strptime(tage[-1], "%Y%m%d")
        im = {t for t in tage if (ende - datetime.strptime(t, "%Y%m%d")).days < fenster}
        aus["fenster"] = {"von": min(im), "bis": tage[-1], **_anteile([u for (d, _, _), u in je.items() if d in im])}
        aus["davor"] = _anteile([u for (d, _, _), u in je.items() if d not in im])
        jetzt, vorher = aus["fenster"]["tipp_anteil"], aus["davor"]["tipp_anteil"]
        aus["anlass"] = bool(vorher and jetzt is not None and jetzt < DRIFT_GRENZE * vorher)
    angenommen = [v for v in vorschlaege if v.get("entscheidung") in ("ja", "geaendert")]
    aus["vorschlaege_angenommen"] = {w: sum((v.get("wirkung") or "unbekannt") == w for v in angenommen)
                                     for w in ("strenger", "lockerer", "neutral", "unbekannt")}
    return aus


# ---------------------------------------------------------------- Verdichtung

ABSCHNITT_MAX = 8          # mehr Einsichten in einem Abschnitt → Verdichtung vorschlagen
ZEILEN_MAX = 200           # EINSICHTEN.md länger → Verdichtung vorschlagen
GEWICHT_KENNUNG = re.compile(r"\*\*\[([^\]]+)\]\*\* `([FGPU]-[A-Z0-9-]+)`")   # auch zweite Kennung in einem Eintrag


def verdichtung(skill_ordner: str | Path, zeilen: list[dict]) -> dict:
    """Anlässe zum Verdichten von EINSICHTEN.md (ADR 0003, Skill ergebnis-analyse): Abschnitt mit mehr als ABSCHNITT_MAX
    Einsichten, Datei länger als ZEILEN_MAX Zeilen, vorläufige Einsicht mit mindestens DRUCK_N Fällen im
    Regelprotokoll (bestätigt oder unter Druck)."""
    text = (Path(skill_ordner) / "EINSICHTEN.md").read_text(encoding="utf-8")
    abschnitte: dict[str, int] = {}
    vorlaeufig: list[str] = []
    titel = None
    for z in text.split("\n"):
        if z.startswith("## "):
            titel = z[3:].strip()
            continue
        if not titel:
            continue
        if z.startswith("- **["):
            abschnitte[titel] = abschnitte.get(titel, 0) + 1
        vorlaeufig += [k for g, k in GEWICHT_KENNUNG.findall(z) if "vorläufig" in g]
    anlaesse = [{"art": "abschnitt_voll", "abschnitt": a, "n": n} for a, n in abschnitte.items() if n > ABSCHNITT_MAX]
    zeilen_n = len(text.rstrip("\n").split("\n"))
    if zeilen_n > ZEILEN_MAX:
        anlaesse.append({"art": "datei_lang", "zeilen": zeilen_n})
    for b in bericht(zeilen, dg.stillgelegt(skill_ordner)):
        if b["kennung"] in vorlaeufig and b["n"] >= DRUCK_N:
            art = "vorlaeufig_unter_druck" if b["unter_druck"] else "vorlaeufig_bestaetigt"
            anlaesse.append({"art": art, "kennung": b["kennung"], "n": b["n"], "z": b["z"]})
    return {"abschnitte": abschnitte, "zeilen": zeilen_n, "vorlaeufig": vorlaeufig, "anlaesse": anlaesse}


# ---------------------------------------------------------------- Tage und Vorschläge

def naechster_tag(ordner: str | Path, verfuegbar) -> str | None:
    erledigt = {z["datum"] for z in _csv_lesen(Path(ordner) / TAGE)}
    offen = sorted({str(t).replace("-", "") for t in verfuegbar} - erledigt)
    return offen[0] if offen else None


def tag_abschliessen(ordner: str | Path, datum: str, commit: str, vorschlaege: int) -> None:
    pfad = Path(ordner) / TAGE
    zeilen = [z for z in _csv_lesen(pfad) if z["datum"] != datum]
    zeilen.append({"datum": datum, "analysiert": datetime.now(PARIS).strftime("%Y-%m-%dT%H:%M"), "commit": commit,
                   "vorschlaege": vorschlaege})
    _csv_schreiben(pfad, TAGE_FELDER, sorted(zeilen, key=lambda z: z["datum"]))


def vorschlaege_lesen(ordner: str | Path = ORDNER) -> list[dict]:
    return _csv_lesen(Path(ordner) / VORSCHLAEGE)


def vorschlaege_ablegen(ordner: str | Path, neue: list[dict]) -> None:
    """Vorschläge anlegen oder aktualisieren (Schlüssel id). Eine Entscheidung außer „offen“ bekommt einen Zeitstempel."""
    je = {z["id"]: z for z in vorschlaege_lesen(ordner)}
    for v in neue:
        e = str(v.get("entscheidung") or "offen")
        if e not in ENTSCHEIDUNGEN:
            raise ValueError(f"{v.get('id')}: entscheidung {e!r} (erlaubt: {', '.join(sorted(ENTSCHEIDUNGEN))})")
        if not v.get("id"):
            raise ValueError("Vorschlag ohne id")
        if v.get("wirkung") and v["wirkung"] not in WIRKUNGEN:
            raise ValueError(f"{v['id']}: wirkung {v['wirkung']!r} (erlaubt: {', '.join(sorted(WIRKUNGEN))})")
        z = {**je.get(v["id"], {}), **{k: v[k] for k in VORSCHLAG_FELDER if k in v}, "entscheidung": e}
        if e != "offen" and not z.get("entschieden"):
            z["entschieden"] = datetime.now(PARIS).strftime("%Y-%m-%dT%H:%M")
        je[v["id"]] = z
    _csv_schreiben(Path(ordner) / VORSCHLAEGE, VORSCHLAG_FELDER, sorted(je.values(), key=lambda z: z["id"]))


# ---------------------------------------------------------------- CLI

def _ordner(argv: list[str]) -> Path:
    return Path(argv[argv.index("--ordner") + 1]) if "--ordner" in argv else ORDNER


def _ohne_optionen(argv: list[str], *mit_wert: str) -> list[str]:
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
        elif a in mit_wert:
            skip = True
        else:
            out.append(a)
    return out


def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__)
        return
    cmd, rest = argv[0], argv[1:]
    ordner = _ordner(rest)
    args = _ohne_optionen(rest, "--ordner", "--aus", "--commit", "--vorschlaege")
    if cmd == "material":
        karte = dg.laden(args[0])
        m = material(str(karte.get("date") or ""), karte, dg.je_rennen(args[2:]), einlauf_laden(args[1]))
        aus = Path(rest[rest.index("--aus") + 1])
        aus.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"datei": str(aus), "zaehlung": m["zaehlung"], "faelle": len(m["faelle"])}, ensure_ascii=False))
    elif cmd == "faelle":
        m = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        if len(args) > 1:
            r = [x for x in m["rennen"] if x["rennen"].upper() == args[1].upper()]
            print(json.dumps(r[0] if r else None, ensure_ascii=False, indent=1))
        else:
            print(faelle_kurz(m))
    elif cmd == "gegenprobe":
        m = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        b = blaetter_lesen(args[0], sorted({r["rennen"] for r in m["rennen"]}))
        print(json.dumps(gegenprobe(m, b, args[2]), ensure_ascii=False, indent=1))
    elif cmd == "protokoll":
        m = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        print(f"{protokoll_fortschreiben(ordner, m)} Zeilen für {m['datum']}")
    elif cmd == "bericht":
        print(json.dumps(bericht(protokoll_lesen(ordner), dg.stillgelegt()), ensure_ascii=False, indent=1))
    elif cmd == "rueckschau":
        print(json.dumps(rueckschau(protokoll_lesen(ordner), args, dg.stillgelegt()), ensure_ascii=False, indent=1))
    elif cmd == "drift":
        print(json.dumps(drift(protokoll_lesen(ordner), vorschlaege_lesen(ordner)), ensure_ascii=False, indent=1))
    elif cmd == "verdichtung":
        print(json.dumps(verdichtung(dg.SKILL_ORDNER, protokoll_lesen(ordner)), ensure_ascii=False, indent=1))
    elif cmd == "naechster-tag":
        print(naechster_tag(ordner, args) or "keiner")
    elif cmd == "tag-abschliessen":
        tag_abschliessen(ordner, args[0], rest[rest.index("--commit") + 1], int(rest[rest.index("--vorschlaege") + 1]))
    elif cmd == "vorschlaege":
        vorschlaege_ablegen(ordner, json.loads(Path(args[0]).read_text(encoding="utf-8")))
    elif cmd == "offen":
        print(json.dumps([v for v in vorschlaege_lesen(ordner) if v["entscheidung"] == "offen"], ensure_ascii=False,
                         indent=1))
    else:
        raise SystemExit(f"Unbekannter Befehl {cmd!r}\n{__doc__}")


if __name__ == "__main__":
    main(sys.argv[1:])
