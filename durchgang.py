"""Durchgänge (Skill rennkarten-durchgang-neu) als eigene Dateien neben der Race Card.

Ein Durchgang ist ein Lauf der Aufgabe „Racecard-Durchgang“ über die offenen Rennen einer Karte. Sein Ergebnis liegt
als ``racecards/durchgang_JJJJMMTT_HHMM.json`` neben der Karte – nie nur in der HTML, weil racecard.run und
festkurse_aktualisieren die HTML neu schreiben (siehe docs/adr/0001-durchgang-in-eigener-datei.md). Je Rennen gilt
der neueste Durchgang, in dem es bearbeitet wurde.

Nur Standardbibliothek: läuft in der geplanten Aufgabe ohne Installation.

Aufruf:
    python3 -I durchgang.py plan KARTE.html [DURCHGANG.json …] [--jetzt HH:MM]
        Rennen der Karte mit Status (offen, gelaufen, kein_festkurs, keine_kandidaten, araber, erledigt) als JSON.
    python3 -I durchgang.py zusammenfuehren AUSGABE.json --datum JJJJ-MM-TT RENNEN.json …
        Ergebnisse der Subagenten (je Rennen eine Datei) prüfen und zu einem Durchgang zusammenfassen.
    python3 -I durchgang.py markieren KARTE.html AUSGABE.html --template racecard_template.html DURCHGANG.json …
        Karte mit den Urteilen (NAP/BET, Begründung) neu rendern.
    python3 -I durchgang.py tabelle DURCHGANG.json …
        Claude-Tipps als Markdown-Tabelle (für den Chat).
"""
from __future__ import annotations

import copy
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
DATEI = re.compile(r"durchgang_(\d{8})_(\d{4})\.json$")
URTEILE = {"wette": 1.0, "klein": 0.5, "nein": 0.0}          # Urteil des Skills → Einheiten
KENNZEICHEN = {"wette": "NAP", "klein": "BET"}               # Kennzeichen auf der Karte
STATUS = ("bearbeitet", "kein_festkurs", "gelaufen", "araber", "keine_kandidaten", "fehler")


# ---------------------------------------------------------------- Karte

def laden(pfad: str | Path) -> dict:
    """Kartendaten aus der HTML-Karte (Zeile ``const DATA = …``) oder einer JSON-Datei."""
    pfad = Path(pfad)
    if pfad.suffix == ".json":
        return json.loads(pfad.read_text(encoding="utf-8"))
    with pfad.open(encoding="utf-8") as f:
        for zeile in f:
            s = zeile.strip()
            if s.startswith("const DATA ="):
                return json.loads(s[len("const DATA ="):].rstrip(";").strip())
    raise ValueError(f"Keine Daten in {pfad} (weder JSON noch 'const DATA =').")


def rennen_liste(daten: dict) -> list[dict]:
    rs = daten.get("races") or {}
    return list(rs.values()) if isinstance(rs, dict) else list(rs)


def _starter(r: dict) -> list[dict]:
    return [x for x in r.get("runners") or [] if not x.get("nr")]


def kandidaten(r: dict) -> list[int]:
    """Startnummern mit Value > 0 (Festkurs × Modell-Siegchance − 1), wie blatt.py."""
    out = []
    for x in _starter(r):
        fk, p = (x.get("fk") or {}).get("sieg"), (x.get("power") or {}).get("sieg")
        if fk and p and fk * p - 1 > 0:
            out.append(int(x["no"]))
    return out


def ist_araber(r: dict) -> bool:
    t = " ".join(str(r.get(k) or "") for k in ("name", "type", "age")).upper()
    return "ARABE" in t or "ARABIAN" in t or "AQPS" in t or "A.Q.P.S" in t


# ---------------------------------------------------------------- Dateien

def dateien(ordner: str | Path, datum: str) -> list[Path]:
    """Durchgang-Dateien eines Tages (datum JJJJ-MM-TT oder JJJJMMTT), älteste zuerst."""
    d = str(datum).replace("-", "")
    return sorted((p for p in Path(ordner).glob(f"durchgang_{d}_*.json") if DATEI.search(p.name)),
                  key=lambda p: p.name)


def je_rennen(pfade) -> dict[str, dict]:
    """race_id → Rennen aus dem neuesten Durchgang, in dem es bearbeitet wurde (Dateiname = Zeitstempel).
    Jedes Rennen bekommt ``stand`` (Zeit des Durchgangs). Unlesbare Dateien werden übergangen."""
    out: dict[str, dict] = {}
    for p in sorted((Path(x) for x in pfade), key=lambda p: p.name):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in d.get("rennen") or []:
            if r.get("status") == "bearbeitet" and r.get("race_id"):
                out[str(r["race_id"])] = {**r, "stand": d.get("stand")}
    return out


# ---------------------------------------------------------------- Plan

def plan(daten: dict, erledigt: set[str] | None = None, jetzt: str | None = None) -> list[dict]:
    """Je Rennen der Karte: Status für diesen Durchgang. ``jetzt`` = HH:MM französischer Zeit (Vorgabe: jetzt).
    offen = zu bearbeiten (noch nicht gestartet, Festkurs vorhanden, Kandidaten, nicht schon erledigt)."""
    erledigt = erledigt or set()
    jetzt = jetzt or datetime.now(PARIS).strftime("%H:%M")
    out = []
    for r in sorted(rennen_liste(daten), key=lambda r: (r.get("time") or "", r.get("race_id") or "")):
        rid = str(r.get("race_id"))
        mit_fk = any((x.get("fk") or {}).get("sieg") for x in _starter(r))
        k = kandidaten(r)
        if rid in erledigt:
            st = "erledigt"
        elif (r.get("time") or "99:99") <= jetzt:
            st = "gelaufen"
        elif ist_araber(r):
            st = "araber"
        elif not mit_fk:
            st = "kein_festkurs"
        elif not k:
            st = "keine_kandidaten"
        else:
            st = "offen"
        out.append({"race_id": rid, "rennen": f"R{r.get('reunion')}C{r.get('race_no')}", "zeit": r.get("time"),
                    "bahn": r.get("course"), "status": st, "kandidaten": k})
    return out


# ---------------------------------------------------------------- Zusammenführen

def _zahl(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def rennen_pruefen(r: dict) -> dict:
    """Ergebnis eines Subagenten prüfen und vereinheitlichen; ValueError bei unbrauchbarem Inhalt."""
    if not r.get("race_id"):
        raise ValueError("race_id fehlt")
    st = r.get("status", "bearbeitet")
    if st not in STATUS:
        raise ValueError(f"{r['race_id']}: Status {st!r} unbekannt")
    kand = []
    for k in r.get("kandidaten") or []:
        u = str(k.get("urteil", "")).lower()
        if u not in URTEILE:
            raise ValueError(f"{r['race_id']} Nr. {k.get('no')}: Urteil {u!r} (erlaubt: wette, klein, nein)")
        fk, mq = _zahl(k.get("fk")), _zahl(k.get("mq"))
        if u != "nein" and not (fk and fk > 1):
            raise ValueError(f"{r['race_id']} Nr. {k.get('no')}: Festkurs fehlt")
        sp = k.get("spanne") or []
        kand.append({
            "no": int(k["no"]), "horse": k.get("horse"), "urteil": u, "einheiten": URTEILE[u],
            "fk": fk, "mq": mq, "spanne": [_zahl(x) for x in sp][:2] if sp else None,
            "p_modell": _zahl(k.get("p_modell")), "value": _zahl(k.get("value")),
            "pro": [str(x) for x in k.get("pro") or []], "gegen": [str(x) for x in k.get("gegen") or []],
            "fragen": [str(x) for x in k.get("fragen") or []], "ausschlag": str(k.get("ausschlag") or ""),
        })
    if st == "bearbeitet" and not kand:
        raise ValueError(f"{r['race_id']}: bearbeitet, aber ohne Kandidaten")
    return {"race_id": str(r["race_id"]), "status": st, "vergleich": str(r.get("vergleich") or ""),
            "hinweis": str(r.get("hinweis") or ""), "kandidaten": kand}


def zusammenfuehren(datum: str, rennen: list[dict], stand: str | None = None, skill: str | None = None) -> dict:
    stand = stand or datetime.now(PARIS).strftime("%Y-%m-%dT%H:%M%z")
    return {"datum": str(datum), "stand": stand, "skill": skill or "rennkarten-durchgang-neu",
            "rennen": [rennen_pruefen(r) for r in rennen]}


def dateiname(datum: str, stand: datetime | None = None) -> str:
    stand = stand or datetime.now(PARIS)
    return f"durchgang_{str(datum).replace('-', '')}_{stand:%H%M}.json"


# ---------------------------------------------------------------- Karte markieren

def anwenden(daten: dict, rennen: dict[str, dict]) -> int:
    """Urteile in die Kartendaten schreiben: je Starter ``claude`` = {urteil, kennzeichen, einheiten, fk, mq, spanne,
    p_modell, value, pro, gegen, fragen, ausschlag, stand}, je Rennen ``claude`` = {stand, vergleich}. Alte Urteile
    werden vorher entfernt. Rückgabe: Zahl der Starter mit Urteil."""
    n = 0
    for r in rennen_liste(daten):
        r.pop("claude", None)
        for x in r.get("runners") or []:
            x.pop("claude", None)
        d = rennen.get(str(r.get("race_id")))
        if not d:
            continue
        r["claude"] = {"stand": d.get("stand"), "vergleich": d.get("vergleich") or ""}
        je_nr = {int(x["no"]): x for x in r.get("runners") or [] if x.get("no") is not None}
        for k in d.get("kandidaten") or []:
            x = je_nr.get(int(k["no"]))
            if x is None:
                continue
            x["claude"] = {**{f: k.get(f) for f in ("urteil", "einheiten", "fk", "mq", "spanne", "p_modell", "value",
                                                    "pro", "gegen", "fragen", "ausschlag")},
                           "kennzeichen": KENNZEICHEN.get(k.get("urteil")), "stand": d.get("stand")}
            n += 1
    return n


def mit_durchgaengen(daten: dict, ordner: str | Path) -> dict:
    """Kopie der Kartendaten mit den Urteilen aller Durchgänge des Tages aus ``ordner`` (fürs Rendern der HTML;
    die gespeicherten Kartendaten und die Claude-JSONs bleiben ohne Urteile – der blinde Teil darf sie nie sehen)."""
    pf = dateien(ordner, daten.get("date") or "")
    if not pf:
        return daten
    d = copy.deepcopy(daten)
    anwenden(d, je_rennen(pf))
    return d


def html(daten: dict, template: str | Path) -> str:
    """Wie racecard.html: Template mit eingesetzten Daten als eigenständige Seite."""
    js = json.dumps(daten, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    seite = Path(template).read_text(encoding="utf-8").replace("/*__DATA__*/null", js, 1)
    return f'<!doctype html>\n<html lang="de">\n{seite}\n</html>\n'


def markieren(karte: str | Path, aus: str | Path, template: str | Path, pfade, titel: str = "Racecard heute") -> int:
    """Karte mit den Urteilen neu rendern (für das Artefakt „Racecard heute“; der Seitentitel wird zum Artefakt-Titel)."""
    daten = laden(karte)
    n = anwenden(daten, je_rennen(pfade))
    seite = re.sub(r"<title>.*?</title>", f"<title>{titel}</title>", html(daten, template), count=1, flags=re.S)
    Path(aus).write_text(seite, encoding="utf-8")
    return n


# ---------------------------------------------------------------- Ausgabe

def _q(x) -> str:
    return "–" if x is None else f"{x:g}".replace(".", ",")


def tabelle(pfade) -> str:
    """Claude-Tipps (NAP/BET) aller Durchgänge des Tages als Markdown-Tabelle, nach Startzeit der race_id sortiert."""
    zeilen = []
    for rid, r in sorted(je_rennen(pfade).items()):
        for k in r.get("kandidaten") or []:
            if k["urteil"] in KENNZEICHEN:
                sp = k.get("spanne") or [None, None]
                zeilen.append(f"| {rid[-4:]} | {k['no']} {k.get('horse') or ''} | **{KENNZEICHEN[k['urteil']]}** | "
                              f"{_q(k.get('fk'))} | {_q(sp[0])}–{_q(sp[1])} | {_q(k.get('mq'))} | {k.get('ausschlag') or ''} |")
    if not zeilen:
        return "Keine Claude-Tipps."
    return "\n".join(["| Rennen | Pferd | | FK | Spanne | MQ | Ausschlag |", "|---|---|---|---|---|---|---|", *zeilen])


# ---------------------------------------------------------------- CLI

def _opt(args: list[str], name: str, vorgabe=None):
    if name in args:
        i = args.index(name)
        v = args[i + 1]
        del args[i:i + 2]
        return v
    return vorgabe


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        raise SystemExit(__doc__)
    cmd, args = argv[1], argv[2:]
    if cmd == "plan":
        jetzt = _opt(args, "--jetzt")
        daten = laden(args[0])
        print(json.dumps(plan(daten, set(je_rennen(args[1:])), jetzt), ensure_ascii=False, indent=1))
    elif cmd == "zusammenfuehren":
        datum, stand = _opt(args, "--datum"), _opt(args, "--stand")
        aus, quellen = args[0], args[1:]
        rennen, fehler = [], []
        for q in quellen:
            try:
                rennen.append(json.loads(Path(q).read_text(encoding="utf-8")))
            except (OSError, ValueError) as e:
                fehler.append(f"{q}: {e}")
        d = zusammenfuehren(datum, rennen, stand)
        Path(aus).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"datei": aus, "rennen": len(d["rennen"]), "unlesbar": fehler}, ensure_ascii=False))
    elif cmd == "markieren":
        tpl = _opt(args, "--template", str(Path(__file__).with_name("racecard_template.html")))
        n = markieren(args[0], args[1], tpl, args[2:])
        print(json.dumps({"datei": args[1], "urteile": n}))
    elif cmd == "tabelle":
        print(tabelle(args))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
