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
   Rennen gestartet ist.
6. Die Claude-Tipps startet racecard.festkurse_aktualisieren selbst: Rennen mit neuen Festkursen, die noch nicht
   gestartet sind, gehen per API-Trigger an die Aufgabe „Racecard-Durchgang“ (durchgang_nach_festkursen) – auch wenn
   die Festkurse von Hand geholt werden.

Pause (VM): Mit pause=… gibt morgen() den Tag ab, wenn bis zum nächsten Schritt (Karte oder Festkurse einer späteren
Veranstaltung) mehr als PAUSE_AB_MIN Minuten Leerlauf sind: pause(weckzeit) plant das Wecken (WECK_VORLAUF_MIN vor
dem Schritt) und gibt True zurück, morgen() endet mit erg["pause"]; die Maschine geht aus. Nach dem Wecken setzt ein
neuer Lauf mit karte=False (Kartendaten des Tages schon da) bzw. dashboard=False fort. Klappt das Planen nicht
(False), wird wie bisher gewartet.

Der bisherige Ablauf im Notebook (Rennkarte von Hand, festkurse_aktualisieren von Hand) bleibt als Rückfall erhalten.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import pmu

KARTE_VORLAUF_MIN = 90      # Rennkarte so viele Minuten vor dem ersten Rennen des Tages bauen
FK_VORLAUF_MIN = 50         # Festkurse je Veranstaltung ab so vielen Minuten vor ihrem ersten Rennen abfragen
FK_TAKT_MIN = 5             # … alle so viele Minuten
PAUSE_AB_MIN = 60           # mit pause=…: Leerlauf ab so vielen Minuten -> Maschine aus, statt zu warten
WECK_VORLAUF_MIN = 10       # … und so viele Minuten vor dem nächsten Schritt wieder wecken (Hochfahren, Drive)
KARTE_VERSUCHE = 4          # PMU-Programm/Kartenbau bei Fehlern (Netz, PMU antwortet nicht) so oft versuchen …
KARTE_PAUSE_MIN = 3         # … mit so vielen Minuten Pause dazwischen
DURCHGANG_ID = "trig_018LVkAy3xCAZHjqQUB9AcDu"   # Aufgabe „Racecard-Durchgang API“ (Claude), per API gestartet
DURCHGANG_URL = "https://api.anthropic.com/v1/claude_code/routines/{id}/fire"
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


def durchgang_ausloesen(text: str, log=print, _post=None) -> bool:
    """Aufgabe „Racecard-Durchgang“ über ihren API-Trigger starten (Claude Code, experimentell). Schlüssel aus der
    Umgebungsvariablen DURCHGANG_TOKEN (Colab-Secret bzw. ~/.pt2026.env), Aufgabe aus DURCHGANG_ID (Vorgabe oben).
    text: Anlass (landet im Lauf als Kontext). Ohne Schlüssel oder bei Fehlern: Meldung, False – der Tag läuft weiter."""
    token = os.getenv("DURCHGANG_TOKEN", "").strip()
    if not token:
        log("Durchgang nicht ausgelöst: kein DURCHGANG_TOKEN – bitte von Hand starten.")
        return False
    if _post is None:
        import requests
        _post = requests.post
    tid = os.getenv("DURCHGANG_ID", "").strip() or DURCHGANG_ID
    if not tid:
        log("Durchgang nicht ausgelöst: keine Aufgaben-ID (DURCHGANG_ID) – bitte von Hand starten.")
        return False
    url = DURCHGANG_URL.format(id=tid)
    try:
        r = _post(url, headers={"Authorization": f"Bearer {token}", "anthropic-version": "2026-10-21",
                                "Content-Type": "application/json"}, json={"text": text[:2000]}, timeout=30)
        if getattr(r, "status_code", 0) != 200:
            log(f"Durchgang nicht ausgelöst: HTTP {getattr(r, 'status_code', '?')} {str(getattr(r, 'text', ''))[:200]}")
            return False
        log(f"Durchgang ausgelöst: {(r.json() or {}).get('claude_code_session_url', '')}")
        return True
    except Exception as e:
        log(f"Durchgang nicht ausgelöst: {type(e).__name__}: {e}")
        return False


RCLONE_RC = "http://127.0.0.1:5572"   # Fernsteuerung von rclone auf der VM (vm/lauf.sh: --rc)
DRIVE_WARTEN_MAX_S = 300              # höchstens so lange auf Uploads warten
DRIVE_WARTEN_OHNE_RC_S = 60           # ohne rclone (Colab): so lange warten, damit Drive die Karte hat


def drive_abwarten(log=print, _post=None, _schlafen=time.sleep) -> None:
    """Warten, bis die gerade geschriebene Karte in Google Drive angekommen ist – sonst lädt der Durchgang (in der
    Cloud, liest aus Drive) noch die alte Karte ohne die neuen Festkurse. VM: rclone meldet offene Uploads
    (vfs/stats); Colab/sonst: feste Wartezeit."""
    if _post is None:
        import requests
        _post = requests.post
    try:
        _post(f"{RCLONE_RC}/vfs/stats", json={}, timeout=5)
    except Exception:
        _schlafen(DRIVE_WARTEN_OHNE_RC_S)
        return
    _schlafen(10)                                        # rclone lädt erst ein paar Sekunden nach dem Schließen hoch
    leer, gewartet = 0, 10
    while gewartet < DRIVE_WARTEN_MAX_S:
        try:
            d = (_post(f"{RCLONE_RC}/vfs/stats", json={}, timeout=5).json() or {}).get("diskCache") or {}
            offen = int(d.get("uploadsInProgress", 0)) + int(d.get("uploadsQueued", 0))
        except Exception:
            offen = 0
        leer = leer + 1 if offen == 0 else 0
        if leer >= 2:
            return
        _schlafen(5)
        gewartet += 5
    log(f"Drive-Upload nach {DRIVE_WARTEN_MAX_S} s noch nicht fertig – Durchgang startet trotzdem.")


def _ausgeloest_pfad(base: Path, tag: date) -> Path:
    return Path(base) / "racecards" / f".durchgang_ausgeloest_{tag:%Y%m%d}.json"


def durchgang_nach_festkursen(base, tag: date, daten: dict, jetzt: str | None = None, log=print, _post=None) -> list[str]:
    """Nach dem Holen der Festkurse (racecard.festkurse_aktualisieren): Rennen mit Festkurs, die noch nicht gestartet
    und noch keinem Durchgang übergeben sind, an die Aufgabe „Racecard-Durchgang“ geben (durchgang_ausloesen, ein Start
    für alle). Merker je Tag: racecards/.durchgang_ausgeloest_JJJJMMTT.json (race_ids) – kommen Festkurse einer Reunion
    in Etappen, startet der Durchgang für die neuen Rennen erneut. Araber zählen nicht. Rückgabe: übergebene race_ids."""
    import durchgang
    import wettstar
    if jetzt is None:                                    # Durchgang bearbeitet nur die Karte von heute
        if tag != datetime.now(PARIS).date():
            return []
        jetzt = datetime.now(PARIS).strftime("%H:%M")
    ap = _ausgeloest_pfad(base, tag)
    try:
        schon = set(json.loads(ap.read_text(encoding="utf-8"))) if ap.exists() else set()
    except ValueError:
        schon = set()
    mit_fk = wettstar.rennen_mit_festkurs(daten)
    neu = sorted(rid for rid, r in (daten.get("races") or {}).items()
                 if rid in mit_fk and rid not in schon and not durchgang.ist_araber(r)
                 and _hm(r.get("time")) is not None and _hm(r["time"]) > _hm(jetzt))
    if not neu:
        return []
    races = daten["races"]
    text = "Festkurse da für " + ", ".join(f"{races[k].get('course')} R{races[k].get('reunion')}C{races[k].get('race_no')} "
                                            f"({races[k].get('time')})" for k in neu) + f" – {tag}"
    if _post is None:                                    # echter Lauf: erst die Karte in Drive ankommen lassen
        drive_abwarten(log=log)
    if not durchgang_ausloesen(text, log=log, _post=_post):
        return []
    try:
        ap.parent.mkdir(parents=True, exist_ok=True)
        ap.write_text(json.dumps(sorted(schon | set(neu))), encoding="utf-8")
    except OSError:
        pass
    return neu


# --------------------------------------------------------------------------
# Ergebnisse holen (wie Abschnitt 2 des Notebooks)
# --------------------------------------------------------------------------
STAND_DATEI = "notebook_stand.json"     # dieselbe Datei wie im Notebook: holt das eine, überspringt das andere


def _neuester_tag(tage) -> date | None:
    """Neuester Tag aus Schlüsseln im Format JJJJMMTT (andere Schlüssel werden ignoriert)."""
    t = sorted(k for k in tage if isinstance(k, str) and len(k) == 8 and k.isdigit())
    return datetime.strptime(t[-1], "%Y%m%d").date() if t else None


def ergebnisse_holen(base, *, erstlauf_tage: int = 14, nachzuegler_tage: int = 0, nur_flach: bool = True,
                     nur_gelaufen: bool = True, code_suche: bool = True, pause: float = 0.3, erzwingen: bool = False,
                     log=print, _tp=None, _pb=None, _sz=None) -> dict:
    """Fehlende Ergebnisse holen – einmal am Tag, genau wie Abschnitt 2 des Notebooks:
    Tracking (pipeline.run), PMU-Basis (pmu_basis.run), danach Standardzeiten neu rechnen. Ausgangspunkt je Quelle ist
    der neueste erledigte Tag, mindestens aber erstlauf_tage zurück. Nach Erfolg steht das Datum in
    <BASE>/notebook_stand.json; läuft es am selben Tag noch einmal, wird übersprungen (erzwingen=True: trotzdem).
    Rückgabe: {"uebersprungen": bool, "ok": bool, ...}."""
    if _tp is None:
        import pipeline as _tp
    if _pb is None:
        import pmu_basis as _pb
    if _sz is None:
        import standardzeiten as _sz
    base = Path(base)
    pdf_dir = base / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    stand_datei = base / STAND_DATEI
    heute = pmu.heute()
    try:
        stand = json.loads(stand_datei.read_text(encoding="utf-8")) if stand_datei.exists() else {}
    except ValueError:
        stand = {}
    if stand.get("datum") == str(heute) and not erzwingen:
        log(f"Heute ({heute}) schon aktualisiert um {stand.get('um', '?')} – Holen übersprungen.")
        return {"uebersprungen": True, "ok": True, **stand}

    def ab(tag) -> str:
        frueh = heute - timedelta(days=erstlauf_tage)
        return str(min(tag, frueh) if tag else frueh)

    ergebnis = {"datum": str(heute), "um": datetime.now(PARIS).strftime("%H:%M")}
    ok = True
    try:                                                 # Tracking: offene Tage seit dem letzten Stand + Nachzügler
        von_tp = ab(_neuester_tag(_tp.fortschritt(base)))
        n_tage = (heute - date.fromisoformat(von_tp)).days + 1
        log(f"— Tracking ab {von_tp} ({n_tage} Tage) —")
        bericht = _tp.run(von_tp, None, base=base, pdf_dir=pdf_dir, max_tage=n_tage, nur_flach=nur_flach,
                          nur_gelaufen=nur_gelaufen, nachzuegler_tage=nachzuegler_tage, code_suche=code_suche,
                          pause=pause)
        log(bericht.to_string() if hasattr(bericht, "to_string") else str(bericht))
        ergebnis["tracking_ab"] = von_tp
    except Exception as e:
        ok = False
        log(f"Tracking fehlgeschlagen: {type(e).__name__}: {e}")
    try:                                                 # PMU-Basis: Rennen/Starter/Kommentare/Dividenden
        von_pb = ab(_neuester_tag(_pb._fortschritt(base).get("erledigt", {})))
        log(f"— PMU-Basis ab {von_pb} —")
        stat = _pb.run(base, von_pb)
        ergebnis["pmu_ab"] = von_pb
        if (stat or {}).get("abgebrochen"):
            ok = False
    except Exception as e:
        ok = False
        log(f"PMU-Basis fehlgeschlagen: {type(e).__name__}: {e}")
    try:                                                 # Standardzeiten mit den neuen Rennen (nichts herunterladen)
        log("— Standardzeiten —")
        _sz.run(base, "2019-01-01", sammeln_ok=False)
    except Exception as e:
        ok = False
        log(f"Standardzeiten fehlgeschlagen: {type(e).__name__}: {e}")
    if ok:
        stand_datei.write_text(json.dumps(ergebnis, indent=1), encoding="utf-8")
        log(f"Stand vermerkt: {ergebnis}")
    else:
        log("Nicht alles hat geklappt – Stand NICHT vermerkt, der nächste Lauf heute holt erneut.")
    return {"uebersprungen": False, "ok": ok, **ergebnis}


def _warten_bis(ziel: datetime, jetzt: Callable[[], datetime], schlafen: Callable[[float], None], log, was: str):
    s = (ziel - jetzt()).total_seconds()
    if s > 0:
        log(f"Warte bis {ziel:%H:%M} ({was}) – {s / 60:.0f} min.")
        while s > 0:                                    # in Stücken, damit die Ausgabe lebendig bleibt
            schlafen(min(s, 600))
            s = (ziel - jetzt()).total_seconds()
            if s > 0:
                log(f"  … noch {s / 60:.0f} min bis {was}")


def _pausieren(ziel: datetime, jetzt: Callable[[], datetime], pause, log, was: str) -> datetime | None:
    """Lange Leerlaufzeit bis ziel: pause(weckzeit) aufrufen; Weckzeit, wenn die Maschine ausgehen darf, sonst None."""
    if pause is None or (ziel - jetzt()).total_seconds() <= PAUSE_AB_MIN * 60:
        return None
    weck = ziel - timedelta(minutes=WECK_VORLAUF_MIN)
    try:
        ok = pause(weck)
    except Exception as e:
        log(f"Wecken nicht geplant ({type(e).__name__}: {e}) – warte stattdessen.")
        ok = False
    if not ok:
        return None
    log(f"Pause bis {weck:%H:%M} ({was} um {ziel:%H:%M}) – Maschine geht aus.")
    return weck


def _versuchen(was: str, fn, log, schlafen, versuche: int = KARTE_VERSUCHE, pause_min: float = KARTE_PAUSE_MIN):
    """fn() bei Fehlern (PMU/Netz antwortet nicht) mehrmals versuchen; der letzte Fehler geht durch."""
    for n in range(1, versuche + 1):
        try:
            return fn()
        except Exception as e:
            if n == versuche:
                log(f"{was} fehlgeschlagen nach {versuche} Versuchen: {type(e).__name__}: {str(e)[:200]}")
                raise
            log(f"{was}: Fehler ({type(e).__name__}: {str(e)[:150]}) – neuer Versuch in {pause_min:g} min ({n}/{versuche}).")
            schlafen(pause_min * 60)


def morgen(base, tag: date | None = None, *, dashboard: bool = True, karte: bool = True, festkurse: bool = True,
           pause: Callable[[datetime], bool] | None = None,
           jetzt: Callable[[], datetime] = _jetzt, schlafen: Callable[[float], None] = time.sleep,
           log=print, _racecard=None, _value_bets=None, _boden_fg=None) -> dict:
    """Tagesablauf (siehe Modulbeschreibung). Rückgabe: Zusammenfassung {karte, boden_neu, festkurse: {Rx: Status},
    pause: Weckzeit ISO oder None}. Die Claude-Tipps startet racecard.festkurse_aktualisieren selbst
    (durchgang_nach_festkursen). pause: siehe Modulbeschreibung (VM).
    jetzt/schlafen/_racecard/_value_bets/_boden_fg sind nur für Tests austauschbar."""
    if _racecard is None:
        import racecard as _racecard
    if _value_bets is None and dashboard:
        import value_bets as _value_bets
    if _boden_fg is None:
        import boden_fg as _boden_fg
    base = Path(base)
    tag = tag or jetzt().date()
    erg: dict = {"tag": str(tag), "karte": None, "boden_neu": False, "festkurse": {}, "pause": None}
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
        races, _ = _versuchen("PMU-Programm", lambda: _racecard.programm(tag), log, schlafen)
        erstes = erstes_rennen(races)
        if erstes is None:
            log(f"Keine französischen Flachrennen am {tag} – nichts zu tun.")
            return erg
        log(f"— Rennkarte: erstes Rennen {erstes}, Karte {KARTE_VORLAUF_MIN} min vorher —")
        ziel = um(erstes) - timedelta(minutes=KARTE_VORLAUF_MIN)
        weck = _pausieren(ziel, jetzt, pause, log, "Rennkarte")
        if weck:
            erg["pause"] = weck.isoformat()
            return erg
        _warten_bis(ziel, jetzt, schlafen, log, "Rennkarte")
        erg["karte"] = str(_versuchen("Rennkarte", lambda: _racecard.run(base, tag, festkurse=False,
                                                                           uebersetzen_aktiv=False), log, schlafen))
        log(f"Rennkarte gebaut: {Path(erg['karte']).name}")
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
                log(f"Rennkarte neu gebaut (Boden): {Path(erg['karte']).name}")
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
            naechste = um(_uhr(min(_hm(v["erstes"]) - FK_VORLAUF_MIN for v in offen.values())))
            weck = _pausieren(naechste, jetzt, pause, log, "Festkurse")
            if weck:
                erg["pause"] = weck.isoformat()
                return erg
            _warten_bis(naechste, jetzt, schlafen, log, "Festkurse")
    for k, s in erg["festkurse"].items():
        log(f"{k} {alle.get(k, {}).get('bahn', '')}: {s}")
    log("Tagesablauf fertig.")
    return erg
