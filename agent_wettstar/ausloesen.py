"""Wett-Agent (Managed Agent „Toto Value Bettor“) mit den NAP/BET eines Durchgangs starten.

Aufruf am Ende der Aufgabe „Racecard-Durchgang“ (Schritt 8 in claude_projekt/aufgabe_durchgang.md):
    python3 -I agent_wettstar/ausloesen.py KARTE DURCHGANG.json [--jetzt HH:MM] [--dry-run] [--zeige]

- Tipps = Kandidaten mit Urteil „wette“ (NAP, 10 €) oder „klein“ (BET, 5 €) aus DURCHGANG.json – nur die Datei
  dieses Durchgangs übergeben, damit kein Tipp zweimal gespielt wird. Bahn, Zeit und RxCy kommen aus der Karte.
- Rennen, die in weniger als VORLAUF_MIN Minuten starten (Paris), werden weggelassen.
- Keine Tipps: keine Session, Ausgabe {"gestartet": false, ...}.
- --zeige: nur den Payload ausgeben, nichts senden. --dry-run: Payload mit "dry_run": true (Agent setzt nichts).
- API-Key aus der Umgebungsvariable WETT_AGENT_API_KEY (nie ausgeben).

Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import durchgang  # noqa: E402

AGENT_ID = "agent_01E62Qu6PGWmTDfkUXsGVxxz"
ENVIRONMENT_ID = "env_01P35yMGS2L2ZQsEDLcetUwS"   # wettstar-playwright-env-v2
VAULT_ID = "vlt_011ChMVZx3URCk1W6K8tTkwr"         # wettstar (WS_USER, WS_PASS)
API = "https://api.anthropic.com/v1/sessions"
KEY_VAR = "WETT_AGENT_API_KEY"
BUDGET_CENT = "500"                               # Kostengrenze je Session: 5 $
VORLAUF_MIN = 3                                   # Start mindestens so viele Minuten entfernt


def tipps(karte: dict, dg: dict, jetzt: str) -> tuple[list[dict], list[str]]:
    """NAP/BET des Durchgangs mit Bahn und Zeit aus der Karte. Rückgabe: (tipps, weggelassen mit Grund)."""
    info = {p["race_id"]: p for p in durchgang.plan(karte, set(), "00:00")}
    grenze = (datetime.strptime(jetzt, "%H:%M") + timedelta(minutes=VORLAUF_MIN)).strftime("%H:%M")
    out, weg = [], []
    for r in dg.get("rennen") or []:
        if r.get("status") != "bearbeitet":
            continue
        for k in r.get("kandidaten") or []:
            kz = durchgang.KENNZEICHEN.get(k.get("urteil"))
            if not kz:
                continue
            rid, p = str(r["race_id"]), info.get(str(r["race_id"]))
            name = f"{rid} Nr. {k.get('no')} {k.get('horse')}"
            if not p or not p.get("bahn") or not p.get("zeit"):
                weg.append(f"{name}: Rennen nicht in der Karte"); continue
            if p["zeit"] <= grenze:
                weg.append(f"{name}: Start {p['zeit']} zu nah oder vorbei"); continue
            out.append({"race_id": rid, "rennen": p["rennen"], "bahn": p["bahn"], "zeit": p["zeit"],
                        "nr": int(k["no"]), "name": k.get("horse"), "kennzeichen": kz,
                        "fk": k.get("fk"), "mq": k.get("mq") or k.get("fk")})
    out.sort(key=lambda t: (t["zeit"], t["race_id"], t["nr"]))
    return out, weg


def payload(dg: dict, dateiname: str, ts: list[dict], dry_run: bool = False) -> dict:
    p = {"datum": dg.get("datum"), "durchgang": dateiname, "tipps": ts}
    if dry_run:
        p["dry_run"] = True
    return p


def starten(p: dict, key: str) -> dict:
    text = ("NUR DRY-RUN, KEINE WETTE ABGEBEN: Skript ohne LIVE aufrufen, nichts bestätigen.\n" if p.get("dry_run")
            else "") + json.dumps(p, ensure_ascii=False)
    body = {"agent": AGENT_ID, "environment_id": ENVIRONMENT_ID, "vault_ids": [VAULT_ID],
            "title": f"Wetten {p['durchgang']}" + (" (Dry-Run)" if p.get("dry_run") else ""),
            "budget": {"type": "limit", "max_list_cost": {"amount": BUDGET_CENT, "currency": "USD"}},
            "initial_events": [{"type": "user.message", "content": [{"type": "text", "text": text}]}]}
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2026-10-21",
        "anthropic-beta": "managed-agents-2026-04-01"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(json.dumps({"gestartet": False, "fehler": f"HTTP {e.code}",
                                     "antwort": e.read().decode(errors="replace")[:500]}, ensure_ascii=False))
    return {"gestartet": True, "session_id": d.get("id"), "status": d.get("status")}


def main(argv: list[str]) -> None:
    args = argv[1:]
    jetzt = durchgang._opt(args, "--jetzt") or datetime.now(durchgang.PARIS).strftime("%H:%M")
    dry, zeige = "--dry-run" in args, "--zeige" in args
    args = [a for a in args if a not in ("--dry-run", "--zeige")]
    if len(args) != 2:
        raise SystemExit(__doc__)
    karte, dgp = durchgang.laden(args[0]), Path(args[1])
    dg = json.loads(dgp.read_text(encoding="utf-8"))
    ts, weg = tipps(karte, dg, jetzt)
    p = payload(dg, dgp.name, ts, dry)
    if zeige or not ts:
        print(json.dumps({"gestartet": False, "grund": "nur anzeigen" if zeige else "keine Tipps",
                          "weggelassen": weg, "payload": p}, ensure_ascii=False, indent=1))
        return
    key = os.environ.get(KEY_VAR)
    if not key:
        raise SystemExit(json.dumps({"gestartet": False, "fehler": f"{KEY_VAR} fehlt", "payload": p},
                                    ensure_ascii=False))
    print(json.dumps({**starten(p, key), "tipps": len(ts), "weggelassen": weg}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
