"""Wett-Agent (Managed Agent „Toto Value Bettor“) mit den NAP/BET eines Durchgangs starten.

Aufruf am Ende der Aufgabe „Racecard-Durchgang“ (Schritt 8 in claude_projekt/aufgabe_durchgang.md):
    python3 -I agent_wettstar/ausloesen.py KARTE DURCHGANG.json [--jetzt HH:MM] [--dry-run] [--zeige]

- Tipps = Kandidaten mit Urteil „wette“ (NAP, 10 €) oder „klein“ (BET, 5 €) aus DURCHGANG.json – nur die Datei
  dieses Durchgangs übergeben, damit kein Tipp zweimal gespielt wird. Bahn, Zeit und RxCy kommen aus der Karte.
- Dazu MODELL-Tipps (5 €): in jedem Rennen dieses Durchgangs das Pferd mit Modell-Rang 1 (nach power.p, wie
  blatt.py), wenn sein Value (Festkurs × power.sieg − 1) über 0 liegt und es nicht schon NAP/BET ist.
  Mindestkurs = Break-even 1/power.sieg (aufgerundet), damit auch beim Wetten noch Value > 0 gilt.
- Rennen, die in weniger als VORLAUF_MIN Minuten starten (Paris), werden weggelassen.
- Keine Tipps: keine Session, Ausgabe {"gestartet": false, ...}.
- Doppelschutz: Jede echte Wett-Session trägt in metadata Datum und Tipps (race_id-nr). Vor dem Start werden die
  heutigen Sessions des Agenten gelesen; schon geschickte Tipps fallen weg. Ist die Liste nicht lesbar: kein Start.
- --zeige: nur den Payload ausgeben, nichts senden. --dry-run: Payload mit "dry_run": true (Agent setzt nichts).
- API-Key aus der Umgebungsvariable WETT_AGENT_API_KEY (nie ausgeben).

Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import re
import math
import os
import sys
import urllib.error
import urllib.parse
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


def modell_erster(r: dict) -> list[dict]:
    """Starter mit Modell-Rang 1 (nach power.p, Gleichstand zählt) und Value > 0: no, horse, fk, p, min_fk."""
    st = [x for x in r.get("runners") or [] if not x.get("nr")]
    ps = [((x.get("power") or {}).get("p") or 0) for x in st]
    out = []
    for x in st:
        pw, fk = x.get("power") or {}, (x.get("fk") or {}).get("sieg")
        p = pw.get("sieg")
        if pw.get("p") is None or sum(1 for q in ps if q > pw["p"]) or not (fk and p) or fk * p - 1 <= 0:
            continue
        out.append({"no": int(x["no"]), "horse": x.get("horse"), "fk": fk, "p": p,
                    "min_fk": round(math.ceil(round(100 / p, 9)) / 100 + (0.01 if round(100 / p, 9).is_integer() else 0), 2)})
    return out


def tipps(karte: dict, dg: dict, jetzt: str) -> tuple[list[dict], list[str]]:
    """NAP/BET des Durchgangs plus MODELL-Tipps, mit Bahn und Zeit aus der Karte. Rückgabe: (tipps, weggelassen)."""
    info = {p["race_id"]: p for p in durchgang.plan(karte, set(), "00:00")}
    rennen = {str(r.get("race_id")): r for r in durchgang.rennen_liste(karte)}
    grenze = (datetime.strptime(jetzt, "%H:%M") + timedelta(minutes=VORLAUF_MIN)).strftime("%H:%M")
    out, weg = [], []
    for r in dg.get("rennen") or []:
        if r.get("status") != "bearbeitet":
            continue
        kand = [{**k, "kz": durchgang.KENNZEICHEN.get(k.get("urteil"))} for k in r.get("kandidaten") or []]
        claude = {int(k["no"]) for k in kand if k["kz"]}
        kand = [k for k in kand if k["kz"]] + [
            {"no": m["no"], "horse": m["horse"], "fk": m["fk"], "mq": m["min_fk"], "kz": "MODELL", "p_modell": m["p"]}
            for m in modell_erster(rennen.get(str(r["race_id"])) or {}) if m["no"] not in claude]
        laeufer = {int(x["no"]): x for x in (rennen.get(str(r["race_id"])) or {}).get("runners") or []
                   if x.get("no") is not None}
        for k in kand:
            kz = k["kz"]
            pm = k.get("p_modell") or ((laeufer.get(int(k["no"])) or {}).get("power") or {}).get("sieg")
            rid, p = str(r["race_id"]), info.get(str(r["race_id"]))
            name = f"{rid} Nr. {k.get('no')} {k.get('horse')}"
            if not p or not p.get("bahn") or not p.get("zeit"):
                weg.append(f"{name}: Rennen nicht in der Karte"); continue
            if p["zeit"] <= grenze:
                weg.append(f"{name}: Start {p['zeit']} zu nah oder vorbei"); continue
            out.append({"race_id": rid, "rennen": p["rennen"], "bahn": p["bahn"], "zeit": p["zeit"],
                        "nr": int(k["no"]), "name": k.get("horse"), "kennzeichen": kz,
                        "fk": k.get("fk"), "mq": k.get("mq") or k.get("fk"),
                        "p": round(float(pm), 4) if pm else None})
    out.sort(key=lambda t: (t["zeit"], t["race_id"], t["nr"]))
    return out, weg


def schluessel(t: dict) -> str:
    return f"{t['race_id']}-{int(t['nr'])}"


def schon_geschickt(sessions: list[dict], datum: str) -> set[str]:
    """Tipps (race_id-nr), die heutige echte Wett-Sessions schon bekommen haben (Dry-Runs zählen nicht)."""
    out: set[str] = set()
    for s in sessions:
        m = s.get("metadata") or {}
        if m.get("wett_datum") == datum and m.get("dry_run") != "1":
            out |= {x for x in str(m.get("wett_tipps") or "").split(",") if x}
    return out


def ohne_doppelte(ts: list[dict], geschickt: set[str]) -> tuple[list[dict], list[str]]:
    neu, weg = [], []
    for t in ts:
        if schluessel(t) in geschickt:
            weg.append(f"{t['race_id']} Nr. {t['nr']} {t['name']}: heute schon an den Wett-Agenten geschickt")
        else:
            neu.append(t)
    return neu, weg


GUTHABEN = re.compile(r"Guthaben (\d+(?:\.\d+)?), benötigt")


def _texte(c) -> list[str]:
    if isinstance(c, str):
        return [c]
    out = []
    for x in c or []:
        if isinstance(x, dict):
            if isinstance(x.get("text"), str):
                out.append(x["text"])
            elif "content" in x:
                out += _texte(x["content"])
    return out


def startbank_aus_events(events: list[dict]) -> float | None:
    """Erstes „Guthaben X, benötigt …“ aus der Skriptausgabe einer Wett-Session."""
    for e in events:
        for t in _texte(e.get("content")):
            m = GUTHABEN.search(t)
            if m:
                return float(m.group(1))
    return None


def payload(dg: dict, dateiname: str, ts: list[dict], dry_run: bool = False) -> dict:
    p = {"datum": dg.get("datum"), "durchgang": dateiname, "tipps": ts}
    if dry_run:
        p["dry_run"] = True
    return p


def _http(methode: str, url: str, key: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=methode,
                                 headers={"Content-Type": "application/json", "x-api-key": key,
                                          "anthropic-version": "2026-10-21",
                                          "anthropic-beta": "managed-agents-2026-04-01"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def heutige_sessions(key: str) -> list[dict]:
    """Sessions des Wett-Agenten seit heute 00:00 Paris (auch archivierte)."""
    ab = datetime.now(durchgang.PARIS).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    q = {"agent_id": AGENT_ID, "created_at[gte]": ab, "include_archived": "true", "limit": "100"}
    out, seite = [], None
    for _ in range(20):
        d = _http("GET", API + "?" + urllib.parse.urlencode({**q, **({"page": seite} if seite else {})}), key)
        out += d.get("data") or []
        seite = d.get("next_page")
        if not seite:
            break
    return out


def startbank_heute(sessions: list[dict], datum: str, key: str) -> float | None:
    """Guthaben beim ersten echten Wett-Lauf des Tages (älteste Session mit wett_datum = datum, kein Dry-Run)."""
    echte = sorted((s for s in sessions if (s.get("metadata") or {}).get("wett_datum") == datum
                    and (s.get("metadata") or {}).get("dry_run") != "1"), key=lambda s: s.get("created_at") or "")
    for s in echte:
        events, seite = [], None
        for _ in range(20):
            d = _http("GET", f"{API}/{s['id']}/events" + (f"?page={seite}" if seite else ""), key)
            events += d.get("data") or []
            seite = d.get("next_page")
            if not seite:
                break
        sb = startbank_aus_events(events)
        if sb:
            return sb
    return None


def starten(p: dict, key: str) -> dict:
    text = ("NUR DRY-RUN, KEINE WETTE ABGEBEN: Skript ohne LIVE aufrufen, nichts bestätigen.\n" if p.get("dry_run")
            else "") + json.dumps(p, ensure_ascii=False)
    body = {"agent": AGENT_ID, "environment_id": ENVIRONMENT_ID, "vault_ids": [VAULT_ID],
            "title": f"Wetten {p['durchgang']}" + (" (Dry-Run)" if p.get("dry_run") else ""),
            "budget": {"type": "limit", "max_list_cost": {"amount": BUDGET_CENT, "currency": "USD"}},
            "metadata": {"wett_datum": str(p.get("datum")), "dry_run": "1" if p.get("dry_run") else "0",
                         "wett_tipps": ",".join(schluessel(t) for t in p["tipps"])[:512]},
            "initial_events": [{"type": "user.message", "content": [{"type": "text", "text": text}]}]}
    try:
        d = _http("POST", API, key, body)
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
    startbank = None
    if not dry:
        try:
            sessions = heutige_sessions(key)
            geschickt = schon_geschickt(sessions, str(dg.get("datum")))
            startbank = startbank_heute(sessions, str(dg.get("datum")), key)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise SystemExit(json.dumps({"gestartet": False, "fehler": f"Doppelprüfung nicht möglich: {e}",
                                         "payload": p}, ensure_ascii=False))
        ts, doppelt = ohne_doppelte(ts, geschickt)
        weg += doppelt
        p = payload(dg, dgp.name, ts, dry)
        if startbank:
            p["startbank"] = startbank
        if not ts:
            print(json.dumps({"gestartet": False, "grund": "alle Tipps heute schon geschickt", "weggelassen": weg},
                             ensure_ascii=False))
            return
    print(json.dumps({**starten(p, key), "tipps": len(ts), "weggelassen": weg}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
