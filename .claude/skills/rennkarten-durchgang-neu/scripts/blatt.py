"""Kandidaten-Blätter für den Skill rennkarten-durchgang-neu.

Liest die Kartendaten von racecard.py – ``racecard_JJJJMMTT_daten.json.gz`` (Normalfall), ``…_daten.json`` oder die
HTML-Karte (eingebettetes ``const DATA = …``) – und druckt je Rennen die Fakten, die die Prüfliste des Skills braucht – für Kandidaten (Value ≥ +5 %) und je Rennen bis zu
zwei Maßstäbe (die zwei Besten im Festkurs, die keine Kandidaten sind; nie eine Wette).

Aufruf (aus einem beliebigen Ordner, Karte als Argument):
    python3 -I blatt.py KARTE.html                 # Übersicht: alle Rennen mit Kandidaten
    python3 -I blatt.py KARTE.html STRASBOURG      # Blätter aller Rennen einer Bahn
    python3 -I blatt.py KARTE.html R2C5 R2C7       # Blätter einzelner Rennen
"""
from __future__ import annotations

import json
import sys
from datetime import date

# Bodenangabe → Bodengruppe der Karte (wie rtr_arr.GOING_MAP: Bon souple zählt zu Fast, Très souple zu Slow; die
# PSF-Zustände standard/lente/rapide stehen in älteren Daten ohne „PSF“). Eigene Kopie, weil der Skill in claude.ai
# ohne das Repo läuft.
GRUPPE = {"lourd": "Very slow", "très lourd": "Very slow", "tres lourd": "Very slow", "collant": "Very slow",
          "très souple": "Slow", "tres souple": "Slow", "souple": "Slow", "bon souple": "Fast", "bon": "Fast",
          "bon léger": "Very fast", "bon leger": "Very fast", "léger": "Very fast", "leger": "Very fast",
          "très léger": "Very fast", "tres leger": "Very fast", "sec": "Very fast",
          "standard": "PSF", "lente": "PSF", "rapide": "PSF"}
SEHR_WEICH = {"très souple", "tres souple", "collant", "lourd", "très lourd", "tres lourd"}
TRAINER_NEU_LAEUFE = 5       # Trainerwechsel in so vielen letzten Läufen eigens zeigen
FENSTER_STARTS = 42          # Tage für die Startfolge (Gegenargument ab etwa 4 Starts)
VALUE_MIN = 0.05             # Kandidat ab +5 % Value (5 % Steuer auf den Gewinn)
MASSSTAEBE = 2               # so viele Maßstäbe je Rennen
SAME = {"K": "Bahn", "D": "Distanz", "B": "Boden"}   # Kennzeichen der angehängten älteren Läufe
DIST_TOL = 200               # Meter für „ähnliche Distanz“ beim Referenzlauf


def laden(pfad: str) -> dict:
    if pfad.endswith(".json.gz"):                        # komprimierte Kartendaten racecard_JJJJMMTT_daten.json.gz
        import gzip
        with gzip.open(pfad, "rt", encoding="utf-8") as f:
            return json.load(f)
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


def ist_handicap(r: dict) -> bool:
    return "handicap" in f"{r.get('type') or ''} {r.get('name') or ''}".lower()


def drittel(rang: int, n: int) -> str:
    if n <= 1:
        return "vorne"
    a = (rang - 1) / (n - 1)
    return "vorderes Drittel" if a < 1 / 3 else "mittleres Drittel" if a < 2 / 3 else "hinteres Drittel"


def uebersicht(d: dict) -> None:
    print(f"Karte {d.get('date')} · erzeugt {d.get('generated')} · Festkurse {d.get('festkurse_bahnen') or d.get('festkurse_stand')}")
    for r in rennen_liste(d):
        k = [z for z in kennzahlen(r) if ist_kandidat(z)]
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
    top_adj = sorted(((x.get("rating_adj") or 0), x["no"]) for x in st if x.get("rating_adj") is not None)[::-1][:3]
    top_kg = max((x.get("weight") or 0) for x in st) if st else None
    fav = min((z for z in kz if z["fk"]), key=lambda z: z["fk"], default=None)
    print(f"\n## {r['race_id'][-4:]} {r.get('course')} {r.get('time')} – {r.get('name')}")
    print(f"{r.get('type')} · {r.get('age')} · {r.get('distance')} m · Bodenangabe {r.get('going')} (Gruppe {r.get('going_label')}, Quelle {r.get('going_source')}) · "
          f"{r.get('corde')} · {len(st)} Starter · Klassenindex {cls.get('val_idx')} · Preis {r.get('prize')} €")
    print(f"Tempo {pace.get('label')} · Laufstile {pace.get('groups')} · unbekannt {pace.get('unknown') or '–'}")
    if fav:
        print(f"FK-Favorit {fav['x']['no']} {fav['x']['horse']} FK {zahl(fav['fk'])}, Modell {pct(fav['p'], 1)} · "
              f"Top-ARR (gew.-bereinigt) {', '.join(f'{zahl(a)} (#{n})' for a, n in top_arr)} · Top-Valeur {', '.join(f'{zahl(v)} (#{n})' for v, n in top_val)}"
              + (f" · Top-Valeur bereinigt {', '.join(f'{zahl(v)} (#{n})' for v, n in top_adj)}" if top_adj and not ist_handicap(r) else "")
              + f" · Höchstgewicht {top_kg} kg")
    print("Handicap: Marke gegen letzte Sieg-/Platzmarke zählt." if ist_handicap(r)
          else "Kein Handicap: Marken-Vergleich ohne Belang, es zählt die gewichtsbereinigte Valeur im Feld.")


def ist_heute(f: dict, r: dict) -> bool:
    """Lauf unter heutigen Bedingungen: gleiche Bodengruppe (PSF eigene Gruppe), Distanz höchstens DIST_TOL entfernt."""
    gr, dist, d0 = gruppe(f.get("going")), f.get("dist"), r.get("distance")
    return bool(gr and gr == r.get("going_label") and dist and d0 and abs(dist - d0) <= DIST_TOL)


def _arr_raenge(f: dict, r: dict, no=None) -> str | None:
    """Rang des ARR dieses Laufs unter allen Läufen der heutigen Starter (kpi: ARR aufs heutige Gewicht) in den
    Fenstern 30/90/365 Tage, soweit der Lauf darin liegt; der Lauf selbst zählt als einer von n (wie die Karte)."""
    wert, tag = f.get("arr_adj"), (r.get("race_id") or "")[:8]
    if wert is None or not f.get("date") or len(tag) != 8:
        return None
    try:
        d0 = date(int(tag[:4]), int(tag[4:6]), int(tag[6:8]))
        alter = (d0 - date.fromisoformat(f["date"])).days
    except ValueError:
        return None
    pool = []
    for x in r.get("runners") or []:
        for e in x.get("kpi") or []:
            if x.get("no") == no and len(e) > 7 and e[7] == f.get("race_id"):
                continue                                 # der Lauf selbst
            try:
                pool.append(((d0 - date.fromisoformat(e[0])).days, e[4]))
            except (ValueError, TypeError, IndexError):
                continue
    teile = []
    for t in (30, 90, 365):
        if alter > t:
            continue
        werte = [v for a, v in pool if a <= t and v is not None]
        if werte:
            teile.append(f"{t} T {1 + sum(v > wert for v in werte)}/{len(werte) + 1}")
    return "ARR-Rang unter den Läufen der heutigen Starter: " + " · ".join(teile) if teile else None


def laufanalyse(f: dict, r: dict, x: dict) -> str | None:
    """Zusatzzeile für Referenzlauf und letzten Lauf: Position, Plätze ab 800 m, Weg, Tempo, ARR-Rang im Feld, TR,
    Gegner danach, heutige Gegner direkt und indirekt. None, wenn die Karte nichts davon hat."""
    t = []
    if f.get("early_pos") or f.get("pos_before"):
        s = (f"früh {f['early_pos']}. → " if f.get("early_pos") else "") + \
            (f"{f.get('pos_before_m') or 400} m vor dem Ziel {f['pos_before']}." if f.get("pos_before") else "")
        t3 = [str(v) for v in f.get("top3_fifth") or [] if v]
        zus = ([f"Fünftel {f['fifth']}/5"] if f.get("fifth") else []) + ([f"erste drei aus {', '.join(t3)}"] if t3 else [])
        t.append(s.strip() + (f" ({'; '.join(zus)})" if zus else ""))
    if f.get("pos_gain") is not None:
        t.append(f"{f['pos_gain']:+d} Plätze ab 800 m")
    if f.get("weg_med") is not None:
        t.append(f"Weg {f['weg_med']:+.0f} m" + (" (außen herum)" if f["weg_med"] >= 7.5 else ""))
    pr = f.get("pace_ratio")
    if pr is not None:
        t.append("Tempo " + ("schnell früh" if pr >= 102 else "langsam früh" if pr <= 98 else "gleichmäßig"))
    rang = _arr_raenge(f, r, x.get("no"))
    if rang:
        t.append(rang)
    tr = f.get("tr_heute") if f.get("tr_heute") is not None else f.get("tr")
    if tr is not None:
        t.append(f"TR {tr}")
    rs = f.get("rivals_stat") or {}
    if rs.get("better") or rs.get("worse"):
        t.append(f"Gegner danach {rs.get('better', 0)}↑ {rs.get('worse', 0)}↓")
    sieger = next((g for g in f.get("rivals") or [] if g.get("pos") == 1 and g.get("next")), None)
    if sieger:
        n = sieger["next"]
        t.append(f"Sieger {sieger.get('horse')} danach {n.get('pos') or '–'}./{n.get('ran') or '–'}")
    rid = f.get("race_id")
    for d in (x.get("duels") or []) if rid else []:
        if d.get("race_id") == rid and d.get("diff_l") is not None:
            t.append(f"{'vor' if d['diff_l'] > 0 else 'hinter'} {d.get('rival_no')} {d.get('rival')} "
                     f"{zahl(abs(d['diff_l']))} L")
    for e in ((x.get("indirect") or {}).get("rivals") or []) if rid else []:
        if any(v and v[0] == rid for v in e.get("via") or []) and e.get("exp_kg") is not None:
            t.append(f"indirekt {'vor' if e['exp_kg'] > 0 else 'hinter'} {e.get('rival_no')} {e.get('rival')} "
                     f"(über {', '.join(e.get('common') or [])})")
    return "       Lauf: " + " · ".join(t) if t else None


def formzeile(f: dict, r: dict) -> str:
    gr, heute_gr = gruppe(f.get("going")), r.get("going_label")
    dist, d0 = f.get("dist"), r.get("distance")
    ref = []
    if ist_heute(f, r):
        ref.append("≈heute")
    if f.get("course") == r.get("course"):
        ref.append("gleiche Bahn")
    if (f.get("going") or "").lower() in SEHR_WEICH:
        ref.append("Very slow" if gr == "Very slow" else "Très souple")
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
    kommentar = f.get("comment_de") or f.get("comment")    # Original (französisch), wenn die Übersetzung fehlt
    if kommentar:
        s += f"\n       „{kommentar[:220]}“"
    return s


def trainerwechsel(liste) -> str | None:
    """Hinweis, wenn das Pferd erst seit wenigen Läufen beim heutigen Trainer ist (aus der Bilanz je Trainer)."""
    liste = liste or []
    h = heute(liste)
    alle = sum((e.get("runs") or 0) for e in liste)
    n = (h or {}).get("runs") or 0
    if not alle or n >= alle:
        return None                                      # nie gewechselt (oder keine Daten)
    if n == 0:
        return f"Trainer: erster Start beim heutigen Trainer (vorher {alle} Läufe bei anderen)"
    if n <= TRAINER_NEU_LAEUFE:
        return f"Trainer erst seit {n} Läufen (von {alle} in der Datenbank), dort {h.get('wins', 0)} S/{h.get('places', 0)} P"
    return None


def ist_kandidat(z: dict) -> bool:
    """Kandidat = Value (Festkurs × Modell-Siegchance − 1) mindestens VALUE_MIN."""
    return z["value"] is not None and z["value"] >= VALUE_MIN - 1e-9


def massstaebe(kz: list[dict]) -> list[tuple[dict, str]]:
    """Vergleichsmaßstäbe je Rennen: die MASSSTAEBE Besten nach Festkurs, die keine Kandidaten sind (Kandidaten werden
    übersprungen, sie werden ohnehin geprüft). Rückgabe [(Kennzahlen, Grund)], leer ohne Festkurse."""
    nach_fk = sorted((z for z in kz if z["fk"]), key=lambda z: z["fk"])
    out = []
    for i, z in enumerate(nach_fk, 1):
        if len(out) == MASSSTAEBE:
            break
        if not ist_kandidat(z):
            out.append((z, "FK-Favorit" if i == 1 else f"{i}. im Festkurs"))
    return out


def blatt(z: dict, r: dict, top_kg: float, titel: str = "") -> None:
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
    val = "–" if z["value"] is None else f"{z['value'] * 100:+.0f} %"
    print(f"\n### {titel}{x['no']} {x['horse']} – FK {zahl(z['fk'])} · Modell {pct(z['p'], 1)} · Modell-Rang {z['rang']}/{z['n']} ({drittel(z['rang'], z['n'])}) · "
          f"Value {val} · Value-Faktor {vf_txt}")
    print(f"- Pferd: {x.get('age')}j {x.get('sex')}, {x.get('starts')} Starts, {x.get('wins')} S, {x.get('places')} P · "
          f"{x.get('weight')} kg (Höchstgewicht {top_kg}) · Marke {zahl(x.get('rating'))} · Box {x.get('draw')} · Laufstil {x.get('style_label')} · "
          f"{x.get('days')} Tage seit letztem Start · {dicht} Starts in {FENSTER_STARTS} Tagen")
    if not ist_handicap(r) and x.get("rating_adj") is not None:
        print(f"- Valeur bereinigt (Valeur − Gewicht + 55): {zahl(x.get('rating_adj'))}, Rang {x.get('rating_rank')}/{x.get('rating_n')} im Feld")
    if hm and ist_handicap(r):
        print(f"- Marke: letzte {'Sieg' if hm.get('kind') == 'sieg' else 'Platz'}-Marke {zahl(hm.get('val'))} ({hm.get('date')}, {hm.get('course')}), heute {hm.get('diff'):+.1f} kg")
    print(f"- Kennzeichen CGD {x.get('cgd') or '–'} · Badges {x.get('badges') or '–'} · Änderungen {[c.get('text') for c in x.get('changes') or []] or '–'} · Ausrüstung {x.get('blinkers')}")
    gs = ph.get("going") or []
    print(f"- Vorlieben Boden (Very slow = Collant und Lourd): " + "; ".join(f"{e['label']}{' (heute)' if e.get('today') else ''} {bilanz(e)}" for e in gs) if gs else "- Vorlieben Boden: –")
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
    ped = (x.get("ae") or {}).get("pedigree") or {}
    q = [f"{name} max. Valeur-Index {ped[k].get('max_val3_idx')}, Gewinn/Lauf-Index {ped[k].get('epr_idx')} ({ped[k].get('horses')} Nachkommen)"
         for k, name in (("sire", "Vater"), ("dam_sire", "Muttervater")) if isinstance(ped.get(k), dict)]
    if q:
        print("- Qualität der Linie (v. a. bei jungen Pferden): " + " · ".join(q))
    for k, name in (("sire", "Vater"), ("dam_sire", "Muttervater")):
        teile = []
        for skala, label in (("boden", "Boden"), ("dist", "Distanz"), ("belag", "Belag"), ("reife", "Reife")):
            e = (ab.get(k) or {}).get(skala) or {}
            if e:
                teile.append(f"{label} {e.get('passung') or '–'}" + (f" ({e.get('runs')} L)" if skala == "boden" else ""))
        if teile:
            print(f"- Abstammung {name} ({x.get(k)}): " + " · ".join(teile))
    tw = trainerwechsel(ph.get("trainer"))
    if tw:
        print(f"- {tw}")
    t30, ttr = (ae.get("trainer") or {}).get("d30") or {}, (ae.get("trainer") or {}).get("trend")
    print(f"- Trainer {x.get('trainer')}: 30 Tage {bilanz(t30)}{f', Trend {ttr}' if ttr else ''} · Bahn {bilanz(pt.get('course'))} · "
          f"Rennart {bilanz(pt.get('racetype'))} · Alter {bilanz(pt.get('age'))} · mit diesem Pferd {bilanz(heute(ph.get('trainer')))}")
    j365 = (ae.get("jockey") or {}).get("d365") or {}
    print(f"- Jockey {x.get('jockey')}: 365 Tage A/E {zahl(j365.get('ae'), 2)} · Bahn {bilanz(pj.get('course'))} · auf diesem Pferd {bilanz(pj.get('horse'))} · "
          f"Gespann mit Trainer {bilanz(pj.get('trainer'))}")
    a, t, du, ds = x.get("arr") or {}, x.get("tr") or {}, x.get("duel_rank") or {}, x.get("draw_stat") or {}
    print(f"- Ratings: ARR ber. {zahl(a.get('adj'))} (Rang {a.get('rank')}/{a.get('n')}, Bestwert roh {zahl(a.get('best'))}) · TR Rang {t.get('rank')}/{t.get('n')} · "
          f"RTR Rang {(x.get('rtr') or {}).get('rank')} · Duelle {zahl(du.get('score_l'))} L (Rang {du.get('rank')}/{du.get('of')}) · "
          f"Box {zahl(ds.get('dev'), 2)}"
          + ((" signifikant " + ("besser" if (ds.get("dev") or 0) > 0 else "schlechter")) if ds.get("sig") else ""))
    crib = ((x.get("prono") or {}).get("crible_de") or "").strip()
    if crib:
        print(f"- Crible (Kontext): „{crib[:240]}“")
    letzte = [f for f in fl if not f.get("extra")][:7]
    aeltere = [f for f in fl if f.get("extra")]          # von der Karte angehängt: letzter Lauf auf Bahn/Distanz/Boden
    referenz = next((f for f in letzte + aeltere if ist_heute(f, r)), None)
    tief = {id(f) for f in (letzte[:1] + [referenz]) if f is not None}   # ausführlich nur Referenz- und letzter Lauf

    def zeile(f):
        print(formzeile(f, r))
        analyse = laufanalyse(f, r, x) if id(f) in tief else None
        if analyse:
            print(analyse)
    print("- Formzeilen (neueste zuerst):")
    for f in letzte:
        zeile(f)
    if aeltere:
        merkmale = sorted({k for f in aeltere for k in f["extra"]}, key="KDB".index)
        print("- Ältere Läufe (zuletzt mit gleicher " + ", ".join(SAME[k] for k in merkmale) + "):")
        for f in aeltere:
            zeile(f)


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
        kand = sorted((z for z in kz if ist_kandidat(z)), key=lambda z: z["rang"])
        if not kand:
            continue
        kopf(r, kz)
        top_kg = max((x.get("weight") or 0) for x in starter(r))
        for z in kand:
            blatt(z, r, top_kg)
        ms = massstaebe(kz)
        for j, (m, grund) in enumerate(ms, 1):
            blatt(m, r, top_kg, titel=f"MASSSTAB {j}/{len(ms)} · {grund} · kein Kandidat, nie eine Wette – ")
        if not ms:
            print("\n### Maßstab: keine Festkurse")


if __name__ == "__main__":
    main(sys.argv)
