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
"""
from __future__ import annotations

import argparse
import os
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
              "Boden nur angenommen", "erstes Rennen gelaufen, ohne Festkurse")

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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Täglicher Lauf: Ergebnisse, Dashboard, Rennkarte, Festkurse.")
    ap.add_argument("--base", required=True, help="Daten-Ordner (wie BASE im Notebook)")
    ap.add_argument("--tag", default=None, help="JJJJ-MM-TT statt heute (nur Karte/Festkurse)")
    ap.add_argument("--nur-ergebnisse", action="store_true")
    ap.add_argument("--ohne-ergebnisse", action="store_true")
    ap.add_argument("--erzwingen", action="store_true", help="Ergebnisse auch holen, wenn heute schon geholt")
    a = ap.parse_args(argv)
    base = Path(a.base)
    log = Protokoll(base / "logs" / f"taeglich_{pmu.heute():%Y%m%d}.log")
    log(f"Start taeglich.py (base {base})")
    import tagesablauf
    ok = True
    try:
        if not a.ohne_ergebnisse:
            e = tagesablauf.ergebnisse_holen(base, erzwingen=a.erzwingen, log=log)
            if not e.get("ok"):
                ok = False
                log("Ergebnisse holen fehlgeschlagen (Details oben) – Tagesablauf läuft trotzdem weiter.")
        if not a.nur_ergebnisse:
            tag = datetime.strptime(a.tag, "%Y-%m-%d").date() if a.tag else None
            tagesablauf.morgen(base, tag, log=log)
    except Exception as e:
        ok = False
        log(f"Tagesablauf fehlgeschlagen: {type(e).__name__}: {e}")
        log(traceback.format_exc())
    log("Ende taeglich.py" + ("" if ok else " (mit Fehlern)"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
