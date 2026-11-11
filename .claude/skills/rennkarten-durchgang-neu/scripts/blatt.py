"""Kandidaten-Blätter für den Skill rennkarten-durchgang-neu.

Liest die von racecard.py erzeugte HTML-Karte (eingebettetes ``const DATA = …``) oder eine JSON-Datei mit
``races`` und druckt je Rennen die Fakten, die die Prüfliste des Skills braucht – nur für Kandidaten (Value > 0).

Aufruf (aus einem beliebigen Ordner, Karte als Argument):
    python3 -I blatt.py KARTE.html                 # Übersicht: alle Rennen mit Kandidaten
    python3 -I blatt.py KARTE.html STRASBOURG      # Blätter aller Rennen einer Bahn
    python3 -I blatt.py KARTE.html R2C5 R2C7       # Blätter einzelner Rennen
"""
from __future__ import annotations

import json
import sys
from datetime import date

# Bodenangabe → Bodengruppe der Karte (wie pmu/racecard: Bon souple zählt zu Fast, Très souple zu Slow)
GRUPPE = {"lourd": "Very slow", "collant": "Very slow", "très souple": "Slow", "tres souple": "Slow",
          "souple": "Slow", "bon souple": "Fast", "bon": "Fast", "bon léger": "Very fast", "bon leger": "Very fast",
          "léger": "Very fast", "leger": "Very fast", "sec": "Very fast"}
SEHR_WEICH = {"très souple", "tres souple", "collant", "lourd"}
FENSTER_STARTS = 42          # Tage für die Startfolge (Gegenargument ab etwa 4 Starts)
DIST_TOL = 200               # Meter für „ähnliche Distanz“ beim Referenzlauf


def laden(pfad: str) -> dict:
    with open(pfad, encoding="utf-8") as f:
        if pfad.endswith(".json"):
            return json.load(f)
        for zeile in f:
            s = zeile.strip()
            if s.startswith("const DATA ="):
                return json.loads(s[len("const DATA ="):].rstrip(";").strip())
    raise SystemExit("Keine Daten gefunden (weder JSON noch 'const DATA =' in der HTML-Karte).")


def rennen_liste(d: dict) -> list[dict]:
    rs = d.get("races") or []
    return list(rs.values()) if isinstance(rs, dict) else rs


def gruppe(going: str | None) -> str | None:
    if not going:
        return None
    g = going.strip().lower()
    return "PSF" if g.startswith("psf") else GRUPPE.get(g)


def pct(x, nk=0):
    return "–" if x is None else f"{x * 100:.{nk}f} %".replace(".", ",")


def zahl(x, nk=1):
    return "–" if x is None else f"{x:.{nk}f}".replace(".", ",")


def bilanz(e: dict | None) -> str:
    if not e:
        return "–"
    s = f"{e.get('runs', 0)} L/{e.get('wins', 0)} S/{e.get('places', 0)} P"
    if e.get("ae") is not None:
        s += f", A/E {zahl(e['ae'], 2)}"
    return s


def heute(liste, key="today"):
    return next((e for e in liste or [] if e.get(key)), None)


def starter(r: dict) -> list[dict]:
    return [x for x in r.get("runners") or [] if not x.get("nr")]


def kennzahlen(r: dict) -> list[dict]:
    """Je Starter: Power, Modell-Rang (nach power.p), Festkurs, Value."""
    st = starter(r)
    ps = [((x.get("power") or {}).get("p") or 0) for x in st]
    out = []
    for x in st:
        pw = x.get("power") or {}
        fk = (x.get("fk") or {}).get("sieg")
        p = pw.get("sieg")
        rang = 1 + sum(1 for q in ps if q > (pw.get("p") or 0))
        out.append({"x": x, "fk": fk, "p": p, "rang": rang, "n": len(st),
                    "value": fk * p - 1 if fk and p else None})
    return out


def drittel(rang: int, n: int) -> str:
    if n <= 1:
        return "vorne"
    a = (rang - 1) / (n - 1)
    return "vorderes Drittel" if a < 1 / 3 else "mittleres Drittel" if a < 2 / 3 else "hinteres Drittel"


def uebersicht(d: dict) -> None:
    print(f"Karte {d.get('date')} · erzeugt {d.get('generated')} · Festkurse {d.get('festkurse_bahnen') or d.get('festkurse_stand')}")
    for r in rennen_liste(d):
        k = [z for z in kennzahlen(r) if z["value"] is not None and z["value"] > 0]
        if not k:
            continue
        teile = ", ".join(f"{z['x']['no']} {z['x']['horse']} FK {zahl(z['fk'])} {z['value'] * 100:+.0f} % (Rang {z['rang']}/{z['n']})"
                          for z in sorted(k, key=lambda z: -z["value"]))
        print(f"{r.get('time')} {r['race_id'][-4:]} {r.get('course')} · {r.get('type')} · {len(starter(r))} St. → {teile}")


def kopf(r: dict, kz: list[dict]) -> None:
    st = starter(r)
    pace = r.get("pace") or {}
    cls = r.get("class") or {}
    top_arr = sorted((((x.get("arr") or {}).get("adj") or 0), x["no"]) for x in st)[::-1][:3]
    top_val = sorted(((x.get("rating") or 0), x["no"]) for x in st)[::-1][:3]
    top_kg = max((x.get("weight") or 0) for x in st) if st else None
    fav = min((z for z in kz if z["fk"]), key=lambda z: z["fk"], default=None)
    print(f"\n## {r['race_id'][-4:]} {r.get('course')} {r.get('time')} – {r.get('name')}")
    print(f"{r.get('type')} · {r.get('age')} · {r.get('distance')} m · Bodenangabe {r.get('going')} (Gruppe {r.get('going_label')}, Quelle {r.get('going_source')}) · "
          f"{r.get('corde')} · {len(st)} Starter · Klassenindex {cls.get('val_idx')} · Preis {r.get('prize')} €")
    print(f"Tempo {pace.get('label')} · Laufstile {pace.get('groups')} · unbekannt {pace.get('unknown') or '–'}")
    if fav:
        print(f"FK-Favorit {fav['x']['no']} {fav['x']['horse']} FK {zahl(fav['fk'])}, Modell {pct(fav['p'], 1)} · "
              f"Top-ARR (gew.-bereinigt) {', '.join(f'{zahl(a)} (#{n})' for a, n in top_arr)} · Top-Valeur {', '.join(f'{zahl(v)} (#{n})' for v, n in top_val)} · Höchstgewicht {top_kg} kg")


def formzeile(f: dict, r: dict) -> str:
    gr, heute_gr = gruppe(f.get("going")), r.get("going_label")
    dist, d0 = f.get("dist"), r.get("distance")
    ref = []
    if gr and gr == heute_gr and dist and d0 and abs(dist - d0) <= DIST_TOL:
        ref.append("≈heute")
    if f.get("course") == r.get("course"):
        ref.append("gleiche Bahn")
    if (f.get("going") or "").lower() in SEHR_WEICH:
        ref.append("sehr weich")
    rv = f.get("rivals_stat") or {}
    if rv.get("ran"):
        if rv.get("better", 0) * 2 >= rv["ran"]:
            ref.append(f"aufgewertet {rv['better']}/{rv['ran']}")
        elif rv.get("worse", 0) * 2 > rv["ran"]:
            ref.append(f"abgewertet {rv['worse']}/{rv['ran']}")
    verlauf = None
    if f.get("verlauf") in ("vorne", "hinten"):
        verlauf = f"Rennen begünstigte {f['verlauf']}"
        if f.get("verlauf_pferd") in ("mit", "gegen"):
            verlauf += f", Pferd lief {f['verlauf_pferd']} den Verlauf"
        if f.get("verlauf_plus"):
            verlauf += " und landete vorne (Plus)"
    warn = [w for w in (f"Zwischenfall {f['incident']}" if f.get("incident") else None,
                        "unzuverlässig (weit geschlagen)" if f.get("unreliable") else None,
                        verlauf, "externer Lauf (ohne volle Daten)" if f.get("extern") else None) if w]
    bl = (f.get("blinkers") or "")
    bl = "" if not bl or bl.startswith("SANS") else " Skl."
    s = (f"   - {f.get('date')} {f.get('course')} {dist or '?'} m {f.get('going') or '?'} {f.get('type') or '?'}: "
         f"{f.get('pos')}/{f.get('ran')}, {zahl(f.get('margin'))} L, Quote {zahl(f.get('odds'))}, Marke {zahl(f.get('valeur'))}, "
         f"{zahl(f.get('weight'))} kg{bl}, Kl.-Index {f.get('cls_val_idx')}, ARR {zahl(f.get('arr'))} (ber. {zahl(f.get('arr_adj'))})")
    if ref or warn:
        s += " [" + "; ".join(ref + warn) + "]"
    if f.get("comment_de"):
        s += f"\n       „{f['comment_de'][:220]}“"
    return s


def blatt(z: dict, r: dict, top_kg: float) -> None:
    x, pw = z["x"], z["x"].get("power") or {}
    ph = (x.get("pref") or {}).get("horse") or {}
    pt = (x.get("pref") or {}).get("trainer") or {}
    pj = (x.get("pref") or {}).get("jockey") or {}
    ae = x.get("ae") or {}
    hm = x.get("hcp_mark") or {}
    fl = x.get("form_lines") or []
    tag = r["race_id"][:8]
    try:
        d0 = date(int(tag[:4]), int(tag[4:6]), int(tag[6:8]))
        dicht = sum(1 for f in fl if f.get("date") and (d0 - date.fromisoformat(f["date"])).days <= FENSTER_STARTS)
    except ValueError:
        dicht = None
    vf = pw.get("wert")
    vf_txt = f"{zahl(vf, 2)}{' gold' if pw.get('gold') else ''}{' Warnung' if pw.get('warn') else ''}" if vf is not None else "–"
    print(f"\n### {x['no']} {x['horse']} – FK {zahl(z['fk'])} · Modell {pct(z['p'], 1)} · Modell-Rang {z['rang']}/{z['n']} ({drittel(z['rang'], z['n'])}) · "
          f"Value {z['value'] * 100:+.0f} % · Value-Faktor {vf_txt} · Prognose-Rang {((x.get('prono') or {}).get('sel') or {}).get('rank')}")
    print(f"- Pferd: {x.get('age')}j {x.get('sex')}, {x.get('starts')} Starts, {x.get('wins')} S, {x.get('places')} P · "
          f"{x.get('weight')} kg (Höchstgewicht {top_kg}) · Marke {zahl(x.get('rating'))} · Box {x.get('draw')} · Laufstil {x.get('style_label')} · "
          f"{x.get('days')} Tage seit letztem Start · {dicht} Starts in {FENSTER_STARTS} Tagen")
    if hm:
        print(f"- Marke: letzte {'Sieg' if hm.get('kind') == 'sieg' else 'Platz'}-Marke {zahl(hm.get('val'))} ({hm.get('date')}, {hm.get('course')}), heute {hm.get('diff'):+.1f} kg")
    print(f"- Kennzeichen CGD {x.get('cgd') or '–'} · Badges {x.get('badges') or '–'} · Änderungen {[c.get('text') for c in x.get('changes') or []] or '–'} · Ausrüstung {x.get('blinkers')}")
    gs = ph.get("going") or []
    print(f"- Vorlieben Boden: " + "; ".join(f"{e['label']}{' (heute)' if e.get('today') else ''} {bilanz(e)}" for e in gs) if gs else "- Vorlieben Boden: –")
    print(f"- Vorlieben Distanz heute: {bilanz(heute(ph.get('distance')))} · Bahn heute: {bilanz(heute(ph.get('course')))} · "
          f"Richtung heute: {bilanz(heute(ph.get('richtung')))} (andere: {bilanz(next((e for e in ph.get('richtung') or [] if not e.get('today')), None))})")
    bl = ph.get("blinkers") or []
    if len(bl) > 1:
        print("- Ausrüstung: " + "; ".join(f"{e['label']}{' (heute)' if e.get('today') else ''} {bilanz(e)}" for e in bl))
    ab = x.get("abst") or {}
    ap = x.get("abst_pass") or {}
    if ap:
        print(f"- Abstammung gesamt (Vater:Muttervater 2:1, ±15 Tendenz, ±40 deutlich): {ap.get('gesamt')} · "
              + " · ".join(f"{k} {ap[k]}" for k in ("boden", "dist", "belag", "reife") if ap.get(k) is not None))
    for k, name in (("sire", "Vater"), ("dam_sire", "Muttervater")):
        teile = []
        for skala, label in (("boden", "Boden"), ("dist", "Distanz"), ("belag", "Belag"), ("reife", "Reife")):
            e = (ab.get(k) or {}).get(skala) or {}
            if e:
                teile.append(f"{label} {e.get('passung') or '–'}" + (f" ({e.get('runs')} L)" if skala == "boden" else ""))
        if teile:
            print(f"- Abstammung {name} ({x.get(k)}): " + " · ".join(teile))
    t30, ttr = (ae.get("trainer") or {}).get("d30") or {}, (ae.get("trainer") or {}).get("trend")
    print(f"- Trainer {x.get('trainer')}: 30 Tage {bilanz(t30)}{f', Trend {ttr}' if ttr else ''} · Bahn {bilanz(pt.get('course'))} · "
          f"Rennart {bilanz(pt.get('racetype'))} · Alter {bilanz(pt.get('age'))} · mit diesem Pferd {bilanz(heute(ph.get('trainer')))}")
    j365 = (ae.get("jockey") or {}).get("d365") or {}
    print(f"- Jockey {x.get('jockey')}: 365 Tage A/E {zahl(j365.get('ae'), 2)} · Bahn {bilanz(pj.get('course'))} · auf diesem Pferd {bilanz(pj.get('horse'))} · "
          f"Gespann mit Trainer {bilanz(pj.get('trainer'))}")
    a, t, du, ds = x.get("arr") or {}, x.get("tr") or {}, x.get("duel_rank") or {}, x.get("draw_stat") or {}
    print(f"- Ratings: ARR ber. {zahl(a.get('adj'))} (Rang {a.get('rank')}/{a.get('n')}, Bestwert roh {zahl(a.get('best'))}) · TR Rang {t.get('rank')}/{t.get('n')} · "
          f"RTR Rang {(x.get('rtr') or {}).get('rank')} · Duelle {zahl(du.get('score_l'))} L (Rang {du.get('rank')}/{du.get('of')}) · "
          f"Box {zahl(ds.get('dev'), 2)}{' signifikant' if ds.get('sig') else ''}")
    crib = ((x.get("prono") or {}).get("crible_de") or "").strip()
    if crib:
        print(f"- Crible (Kontext): „{crib[:240]}“")
    print("- Formzeilen (neueste zuerst):")
    for f in fl[:7]:
        print(formzeile(f, r))


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        raise SystemExit(__doc__)
    d = laden(argv[1])
    filter_ = [a.upper() for a in argv[2:]]
    if not filter_:
        uebersicht(d)
        return
    for r in rennen_liste(d):
        rid, kurs = r["race_id"][-4:].upper(), (r.get("course") or "").upper()
        if not any(f == rid or f in kurs for f in filter_):
            continue
        kz = kennzahlen(r)
        kand = sorted((z for z in kz if z["value"] is not None and z["value"] > 0), key=lambda z: z["rang"])
        if not kand:
            continue
        kopf(r, kz)
        top_kg = max((x.get("weight") or 0) for x in starter(r))
        for z in kand:
            blatt(z, r, top_kg)


if __name__ == "__main__":
    main(sys.argv)
