"""Automatischer Tagesablauf ab dem Morgen: Dashboard, Rennkarte 90 min vor dem ersten Rennen, Festkurse je Veranstaltung.

    import tagesablauf
    tagesablauf.morgen(BASE)          # läuft bis alle Veranstaltungen Festkurse haben (oder ihr erstes Rennen lief)

Ablauf (Zeiten französisch):
1. Value-Dashboard bauen (die Ergebnisse des Vortags holt vorher Abschnitt 2 des Notebooks).
2. Startzeit des ersten Rennens des Tages aus dem PMU-Programm; warten bis KARTE_VORLAUF_MIN davor
   (schon später: sofort).
3. Rennkarte bauen – ohne Festkurse (die gibt es so früh nicht) und ohne Übersetzung. Den Boden holt die Karte selbst
   (PMU, boden_manuell.json, France Galop).
4. Hatte eine Gras-Bahn dabei nur die Annahme, aber France Galop meldet inzwischen einen Boden: Karte einmal neu
   bauen, bevor die Festkurs-Schleife beginnt.
5. Je Veranstaltung (Reunion) ab FK_VORLAUF_MIN vor ihrem ersten Rennen alle FK_TAKT_MIN Wettstar abfragen
   (racecard.festkurse_aktualisieren, nur fehlende Rennen), bis alle ihre Rennen Festkurse haben oder ihr erstes
   Rennen gestartet ist. Danach plant die Aufgabe „Racecard-Durchgang“ die Claude-Tipps selbst ein.

Der bisherige Ablauf im Notebook (Rennkarte von Hand, festkurse_aktualisieren von Hand) bleibt als Rückfall erhalten.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import pmu

KARTE_VORLAUF_MIN = 90      # Rennkarte so viele Minuten vor dem ersten Rennen des Tages bauen
FK_VORLAUF_MIN = 50         # Festkurse je Veranstaltung ab so vielen Minuten vor ihrem ersten Rennen abfragen
FK_TAKT_MIN = 5             # … alle so viele Minuten
PARIS = pmu.PARIS


def _hm(t: str | None) -> int | None:
    try:
        return int(str(t)[:2]) * 60 + int(str(t)[3:5])
    except (TypeError, ValueError):
        return None


def _uhr(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def erstes_rennen(races) -> str | None:
    """Früheste Startzeit HH:MM aus dem PMU-Programm (DataFrame mit post_time)."""
    zeiten = [z for z in (races["post_time"] if "post_time" in races else []) if _hm(z) is not None]
    return min(zeiten, key=_hm) if zeiten else None


def veranstaltungen(daten: dict) -> dict[str, dict]:
    """Je Veranstaltung der Karte: Bahn, erstes Rennen (HH:MM), Rennen (ohne Araber) und ob alle Festkurse haben."""
    import durchgang
    import wettstar
    mit_fk = wettstar.rennen_mit_festkurs(daten)
    out: dict[str, dict] = {}
    for rid, r in (daten.get("races") or {}).items():
        if durchgang.ist_araber(r) or _hm(r.get("time")) is None:
            continue
        v = out.setdefault(f"R{r.get('reunion')}", {"bahn": r.get("course"), "erstes": r.get("time"), "rennen": [],
                                                    "ohne_fk": []})
        if _hm(r["time"]) < _hm(v["erstes"]):
            v["erstes"] = r["time"]
        v["rennen"].append(rid)
        if rid not in mit_fk:
            v["ohne_fk"].append(rid)
    return out


def offene_veranstaltungen(daten: dict, jetzt: str) -> dict[str, dict]:
    """Veranstaltungen, für die noch Festkurse fehlen und deren erstes Rennen noch nicht gestartet ist."""
    return {k: v for k, v in veranstaltungen(daten).items() if v["ohne_fk"] and _hm(v["erstes"]) > _hm(jetzt)}


def boden_annahme(daten: dict) -> list[str]:
    """Bahnen, deren Gras-Rennen nur die Boden-Annahme haben (going_source 'Annahme')."""
    return sorted({r.get("course") for r in (daten.get("races") or {}).values()
                   if r.get("going_source") == "Annahme" and r.get("course")})


def _jetzt() -> datetime:
    return datetime.now(PARIS)


def _warten_bis(ziel: datetime, jetzt: Callable[[], datetime], schlafen: Callable[[float], None], log, was: str):
    s = (ziel - jetzt()).total_seconds()
    if s > 0:
        log(f"Warte bis {ziel:%H:%M} ({was}) – {s / 60:.0f} min.")
        while s > 0:                                    # in Stücken, damit die Ausgabe lebendig bleibt
            schlafen(min(s, 600))
            s = (ziel - jetzt()).total_seconds()
            if s > 0:
                log(f"  … noch {s / 60:.0f} min bis {was}")


def morgen(base, tag: date | None = None, *, dashboard: bool = True, karte: bool = True, festkurse: bool = True,
           jetzt: Callable[[], datetime] = _jetzt, schlafen: Callable[[float], None] = time.sleep, log=print,
           _racecard=None, _value_bets=None, _boden_fg=None) -> dict:
    """Tagesablauf (siehe Modulbeschreibung). Rückgabe: Zusammenfassung {karte, boden_neu, festkurse: {Rx: Status}}.
    jetzt/schlafen/_racecard/_value_bets/_boden_fg sind nur für Tests austauschbar."""
    if _racecard is None:
        import racecard as _racecard
    if _value_bets is None and dashboard:
        import value_bets as _value_bets
    if _boden_fg is None:
        import boden_fg as _boden_fg
    base = Path(base)
    tag = tag or jetzt().date()
    erg: dict = {"tag": str(tag), "karte": None, "boden_neu": False, "festkurse": {}}
    tz = jetzt().tzinfo or PARIS
    um = lambda hhmm: datetime.combine(tag, datetime.min.time(), tz) + timedelta(minutes=_hm(hhmm))

    if dashboard:
        log("— Value-Dashboard —")
        try:
            _value_bets.start(base)
        except Exception as e:                           # darf den Tag nicht aufhalten
            log(f"Dashboard nicht gebaut: {type(e).__name__}: {e}")

    out = base / "racecards" / f"racecard_{tag:%Y%m%d}.html"
    sp = _racecard.daten_pfad(out)
    if karte:
        races, _ = _racecard.programm(tag)
        erstes = erstes_rennen(races)
        if erstes is None:
            log(f"Keine französischen Flachrennen am {tag} – nichts zu tun.")
            return erg
        log(f"— Rennkarte: erstes Rennen {erstes}, Karte {KARTE_VORLAUF_MIN} min vorher —")
        _warten_bis(um(erstes) - timedelta(minutes=KARTE_VORLAUF_MIN), jetzt, schlafen, log, "Rennkarte")
        erg["karte"] = str(_racecard.run(base, tag, festkurse=False, uebersetzen_aktiv=False))
        daten = json.loads(sp.read_text(encoding="utf-8"))
        ohne = boden_annahme(daten)
        if ohne:
            log(f"Boden nur angenommen: {', '.join(ohne)} – prüfe France Galop vor den Festkursen erneut.")
            vor_fk = min((um(v["erstes"]) for v in veranstaltungen(daten).values()), default=None)
            if vor_fk is not None:
                _warten_bis(vor_fk - timedelta(minutes=FK_VORLAUF_MIN + 5), jetzt, schlafen, log, "Boden-Prüfung")
            fg = _boden_fg.tag(tag)
            neu = [b for b in ohne if _racecard._bahn_schluessel(b, fg) is not None]
            if neu:
                log(f"France Galop hat jetzt Boden für {', '.join(neu)} – Karte neu bauen.")
                erg["karte"] = str(_racecard.run(base, tag, festkurse=False, uebersetzen_aktiv=False))
                erg["boden_neu"] = True
            else:
                log("Kein neuer Boden – Karte bleibt.")

    if not festkurse:
        return erg
    if not sp.exists():
        log(f"Keine Kartendaten {sp.name} – Festkurse übersprungen.")
        return erg
    log(f"— Festkurse je Veranstaltung ab {FK_VORLAUF_MIN} min vor dem ersten Rennen, alle {FK_TAKT_MIN} min —")
    while True:
        daten = json.loads(sp.read_text(encoding="utf-8"))
        hhmm = jetzt().strftime("%H:%M")
        alle = veranstaltungen(daten)
        for k, v in alle.items():
            if not v["ohne_fk"]:
                erg["festkurse"][k] = "da"
            elif _hm(v["erstes"]) <= _hm(hhmm):
                erg["festkurse"].setdefault(k, "erstes Rennen gelaufen, ohne Festkurse")
        offen = offene_veranstaltungen(daten, hhmm)
        if not offen:
            break
        faellig = {k: v for k, v in offen.items() if _hm(v["erstes"]) - FK_VORLAUF_MIN <= _hm(hhmm)}
        if faellig:
            namen = ", ".join(f"{k} {v['bahn']} ({len(v['ohne_fk'])} Rennen)" for k, v in faellig.items())
            log(f"{hhmm} Festkurse holen für {namen}")
            try:
                _racecard.festkurse_aktualisieren(base, tag)
            except Exception as e:                       # Wettstar/Netz: beim nächsten Takt erneut
                log(f"  Festkurse nicht geholt: {type(e).__name__}: {e}")
            daten = json.loads(sp.read_text(encoding="utf-8"))
            nach = offene_veranstaltungen(daten, jetzt().strftime("%H:%M"))
            for k in faellig:
                if k not in nach:
                    log(f"  {k} {faellig[k]['bahn']}: Festkurse da.")
            if not nach:
                continue
            schlafen(FK_TAKT_MIN * 60)
        else:
            naechste = min(_hm(v["erstes"]) - FK_VORLAUF_MIN for v in offen.values())
            _warten_bis(um(_uhr(naechste)), jetzt, schlafen, log, "Festkurse")
    for k, s in erg["festkurse"].items():
        log(f"{k} {alle.get(k, {}).get('bahn', '')}: {s}")
    log("Tagesablauf fertig.")
    return erg
