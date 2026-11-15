"""Täglicher Lauf ohne Notebook (z. B. auf einer VM, gestartet um 7:00 per cron/systemd):

    python3 taeglich.py --base /daten/PT_tracking
    python3 taeglich.py --base /daten/PT_tracking --nur-ergebnisse      # nur Ergebnisse holen
    python3 taeglich.py --base /daten/PT_tracking --ohne-ergebnisse     # nur Dashboard/Karte/Festkurse

Ablauf: tagesablauf.ergebnisse_holen (wie Abschnitt 2 des Notebooks), danach tagesablauf.morgen (wie Abschnitt 3a):
Dashboard, Rennkarte 90 min vor dem ersten Rennen, Festkurse je Reunion. Alles wird zusätzlich nach
<BASE>/logs/taeglich_JJJJMMTT.log geschrieben.

Push-Nachrichten (optional): Umgebungsvariable NTFY_TOPIC (Thema bei ntfy.sh, z. B. ein langer Zufallsname; die
App „ntfy“ auf dem Handy abonniert es) – gemeldet werden Karte fertig, Festkurse je Reunion, Fehler und Ende.
Rückgabewert 0 = alles gelaufen, 1 = Fehler (steht im Log).

Maschine zwischendurch aus (VM, --pausen oder PT2026_PAUSEN=1): Liegt bis zur Karte oder zu den Festkursen einer
späteren Veranstaltung mehr als eine Stunde Leerlauf, stellt taeglich.py den Cloud-Scheduler-Job PT2026_WECKJOB
(Vorgabe pt2026-wecken, Region PT2026_REGION, Vorgabe europe-west3) auf die Weckzeit und endet; vm/lauf.sh fährt die
Maschine dann herunter, der Job startet sie wieder. Der nächste Lauf erkennt am Stand <BASE>/logs/.tag_JJJJMMTT.json,
dass Ergebnisse und Dashboard schon erledigt sind, und an den Kartendaten, dass die Karte schon gebaut ist.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

import requests

import pmu


def push(text: str, titel: str = "PT2026", prioritaet: str = "default") -> None:
    """Kurze Nachricht über ntfy.sh, wenn NTFY_TOPIC gesetzt ist; Fehler beim Senden werden ignoriert."""
    thema = os.getenv("NTFY_TOPIC", "").strip()
    if not thema:
        return
    try:
        requests.post(f"https://ntfy.sh/{thema}", data=text.encode("utf-8"), timeout=10,
                      headers={"Title": titel, "Priority": prioritaet})
    except Exception:
        pass


class Protokoll:
    """print-Ersatz: schreibt auf die Konsole und in die Log-Datei; wichtige Zeilen gehen zusätzlich als Push."""
    MELDEN = ("Rennkarte gebaut", "Rennkarte neu gebaut", "Festkurse da", "Tagesablauf fertig", "nicht gebaut", "fehlgeschlagen", "Keine französischen",
              "Boden nur angenommen", "erstes Rennen gelaufen, ohne Festkurse", "Pause bis", "Wecken nicht geplant")

    def __init__(self, datei: Path):
        datei.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(datei, "a", encoding="utf-8")

    def __call__(self, *teile) -> None:
        text = " ".join(str(t) for t in teile)
        zeile = f"{datetime.now(pmu.PARIS):%H:%M:%S} {text}"
        print(zeile, flush=True)
        self.f.write(zeile + "\n")
        self.f.flush()
        if any(m in text for m in self.MELDEN):
            push(text[:300], prioritaet="high" if "fehlgeschlagen" in text or "nicht gebaut" in text else "default")


def wecken_planen(zeit: datetime, log=print, _run=subprocess.run) -> bool:
    """Cloud-Scheduler-Job (startet die VM) auf genau diese Minute stellen; True, wenn gcloud es bestätigt."""
    job = os.getenv("PT2026_WECKJOB", "pt2026-wecken")
    region = os.getenv("PT2026_REGION", "europe-west3")
    z = zeit.astimezone(pmu.PARIS)
    cmd = ["gcloud", "scheduler", "jobs", "update", "http", job, f"--location={region}",
           f"--schedule={z.minute} {z.hour} {z.day} {z.month} *", "--time-zone=Europe/Paris", "--quiet"]
    try:
        r = _run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        log(f"Wecken nicht geplant: {type(e).__name__}: {e}")
        return False
    if r.returncode != 0:
        log(f"Wecken nicht geplant: gcloud {r.returncode}: {(r.stderr or r.stdout or '').strip()[:300]}")
        return False
    log(f"Wecken geplant: {job} um {z:%d.%m. %H:%M}")
    return True


def _stand_lesen(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Täglicher Lauf: Ergebnisse, Dashboard, Rennkarte, Festkurse.")
    ap.add_argument("--base", required=True, help="Daten-Ordner (wie BASE im Notebook)")
    ap.add_argument("--tag", default=None, help="JJJJ-MM-TT statt heute (nur Karte/Festkurse)")
    ap.add_argument("--nur-ergebnisse", action="store_true")
    ap.add_argument("--ohne-ergebnisse", action="store_true")
    ap.add_argument("--erzwingen", action="store_true", help="Ergebnisse auch holen, wenn heute schon geholt")
    ap.add_argument("--pausen", action="store_true",
                    help="bei langem Leerlauf Wecken planen und enden (VM geht aus); auch PT2026_PAUSEN=1")
    a = ap.parse_args(argv)
    base = Path(a.base)
    log = Protokoll(base / "logs" / f"taeglich_{pmu.heute():%Y%m%d}.log")
    log(f"Start taeglich.py (base {base})")
    import tagesablauf
    pausen = a.pausen or os.getenv("PT2026_PAUSEN", "").strip() == "1"
    stand_p = base / "logs" / f".tag_{pmu.heute():%Y%m%d}.json"
    stand = _stand_lesen(stand_p)
    ok = True
    try:
        if not a.ohne_ergebnisse and not stand.get("morgen"):
            e = tagesablauf.ergebnisse_holen(base, erzwingen=a.erzwingen, log=log)
            if not e.get("ok"):
                ok = False
                log("Ergebnisse holen fehlgeschlagen (Details oben) – Tagesablauf läuft trotzdem weiter.")
        if not a.nur_ergebnisse:
            tag = datetime.strptime(a.tag, "%Y-%m-%d").date() if a.tag else None
            karte_da = (base / "racecards" / f"racecard_{(tag or pmu.heute()):%Y%m%d}_daten.json").exists()
            if stand.get("morgen") or karte_da:
                log("Fortsetzung: " + ("Karte ist schon gebaut – nur noch Festkurse." if karte_da
                                       else "Ergebnisse und Dashboard schon erledigt."))
            weiter = dict(dashboard=not stand.get("morgen"), karte=not karte_da)
            if pausen:
                weiter["pause"] = lambda zeit: wecken_planen(zeit, log=log)
            try:
                erg = tagesablauf.morgen(base, tag, log=log, **weiter)
            finally:
                if not stand.get("morgen"):
                    stand_p.parent.mkdir(parents=True, exist_ok=True)
                    stand_p.write_text(json.dumps({"morgen": True}), encoding="utf-8")
            if (erg or {}).get("pause"):
                log("Ende taeglich.py (Pause)")
                return 0
    except Exception as e:
        ok = False
        log(f"Tagesablauf fehlgeschlagen: {type(e).__name__}: {e}")
        log(traceback.format_exc())
    log("Ende taeglich.py" + ("" if ok else " (mit Fehlern)"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
