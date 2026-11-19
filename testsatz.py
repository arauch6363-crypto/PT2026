"""Testsatz des Skills rennkarten-durchgang-neu: Urteile des Skills gegen die Urteile des Nutzers (ADR 0002).

Ein Testfall ist ein Rennen: Kartenausschnitt ``tests/testsatz_durchgang/karten/<race_id>.json.gz`` und die Urteile
des Nutzers in ``tests/testsatz_durchgang/erwartet.json``. Eine Fehlwette zählt doppelt so schwer wie ein verpasster
Kandidat; Wette gegen Kleine Wette zählt halb. Ablauf: ``claude_projekt/aufgabe_testsatz.md``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # auch mit python3 -I aufrufbar
from durchgang import URTEILE, _opt, laden, rennen_liste  # noqa: E402

GEWICHT_FEHLWETTE = 2.0     # Skill spielt, der Nutzer hätte nicht (je Einheit Abstand)
GEWICHT_VERPASST = 1.0      # Skill spielt nicht, der Nutzer hätte (je Einheit Abstand)


def fehlerpunkte(erwartet: dict, urteil: str) -> float:
    """Fehlerpunkte eines Kandidaten: ``erwartet`` = {urteil, erlaubt?}; ein Urteil aus ``erlaubt`` (Ermessen) ist
    kein Fehler. Gemessen in Einheiten (Wette 1, Kleine Wette ½, nein 0)."""
    def punkte(ziel: str) -> float:
        d = URTEILE[urteil] - URTEILE[ziel]
        return d * GEWICHT_FEHLWETTE if d > 0 else -d * GEWICHT_VERPASST
    return min(punkte(z) for z in [erwartet["urteil"], *(erwartet.get("erlaubt") or [])])


def testfall(erwartet: dict, laeufe: list[dict]) -> dict:
    """Ein Testfall über mehrere Läufe des Skills (je Lauf ein Rennen-JSON wie im Durchgang). Gewertet werden nur
    Kandidaten mit Urteil des Nutzers; fehlt einer im Lauf, gilt er als nicht gespielt. ``punkte`` = Mittel der
    Fehlerpunkte je Lauf; ``stand``: stabil richtig (alle Läufe), mehrheitlich falsch, sonst schwankend."""
    je_lauf, richtig, fehlt = [], [], set()
    for lauf in laeufe:
        urteile = {int(k["no"]): k["urteil"] for k in lauf.get("kandidaten") or []}
        p = 0.0
        for no, e in erwartet["kandidaten"].items():
            if int(no) not in urteile:
                fehlt.add(int(no))
            p += fehlerpunkte(e, urteile.get(int(no), "nein"))
        je_lauf.append(p)
        richtig.append(p == 0)
    if all(richtig):
        stand = "stabil richtig"
    elif sum(richtig) * 2 < len(richtig):
        stand = "mehrheitlich falsch"
    else:
        stand = "schwankend"
    return {"punkte": sum(je_lauf) / len(je_lauf), "je_lauf": je_lauf, "richtig": richtig, "stand": stand,
            "fehlt": sorted(fehlt)}


def bewerten(erwartet: dict[str, dict], laeufe: dict[str, list[dict]]) -> dict:
    """Alle Testfälle: ``trefferquote`` = Anteil der Testfälle ohne Fehlerpunkte, über die Läufe gemittelt (Anteil
    richtiger Läufe), ``punkte`` = Summe der mittleren Fehlerpunkte je Testfall."""
    fehlen = [rid for rid in erwartet if not laeufe.get(rid)]
    if fehlen:
        raise ValueError(f"Kein Lauf für: {', '.join(fehlen)}")
    faelle = {rid: testfall(e, laeufe[rid]) for rid, e in erwartet.items()}
    richtig = [x for t in faelle.values() for x in t["richtig"]]
    return {"trefferquote": sum(richtig) / len(richtig), "punkte": sum(t["punkte"] for t in faelle.values()),
            "faelle": faelle}


KOPF = ("date", "generated", "festkurse_bahnen", "festkurse_stand")   # Kartenkopf im Ausschnitt


def ausschnitt(daten: dict, race_id: str) -> dict:
    """Kartenausschnitt eines Rennens – genug für blatt.py (es liest je Rennen nur ``races``)."""
    r = [x for x in rennen_liste(daten) if x.get("race_id") == race_id]
    if not r:
        raise KeyError(race_id)
    return {**{k: daten[k] for k in KOPF if k in daten}, "races": r}


def laeufe_laden(ordner: str | Path) -> dict[str, list[dict]]:
    """Läufe ``<race_id>_<n>.json`` aus einem Ordner, je race_id in der Reihenfolge von n."""
    aus: dict[str, list[dict]] = {}
    pfade = [(*p.stem.rsplit("_", 1), p) for p in Path(ordner).glob("*_*.json")]
    for rid, _, p in sorted(pfade, key=lambda x: (x[0], int(x[1]))):
        aus.setdefault(rid, []).append(json.loads(p.read_text(encoding="utf-8")))
    return aus


def rueckschritte(vorher: dict, jetzt: dict) -> list[str]:
    """Testfälle, die vorher stabil richtig waren und jetzt mehrheitlich falsch sind."""
    return sorted(rid for rid, t in jetzt["faelle"].items()
                  if t["stand"] == "mehrheitlich falsch"
                  and vorher.get("faelle", {}).get(rid, {}).get("stand") == "stabil richtig")


def letztes(ordner: str | Path) -> dict:
    """Zuletzt abgelegtes Ergebnis (= Stand des zuletzt übernommenen Skills; letzte Zeile von verlauf.csv), sonst {}."""
    verlauf = Path(ordner) / "verlauf.csv"
    zeilen = verlauf.read_text(encoding="utf-8").splitlines()[1:] if verlauf.exists() else []
    if not zeilen:
        return {}
    datum, commit = zeilen[-1].split(",")[:2]
    return json.loads((Path(ordner) / "ergebnisse" / f"{datum}_{commit}.json").read_text(encoding="utf-8"))


def uebernehmen(vorher: dict, ergebnis: dict) -> bool:
    """Übernahmeregel (ADR 0002): Fehlerpunkte steigen nicht und kein Rückschritt; ohne früheren Stand immer."""
    return not vorher or (not rueckschritte(vorher, ergebnis) and ergebnis["punkte"] <= vorher["punkte"])


def ablegen(ordner: str | Path, ergebnis: dict, commit: str, datum: str) -> None:
    """Ergebnis eines übernommenen Skill-Stands unter ``ergebnisse/<datum>_<commit>.json`` ablegen und eine Zeile an
    ``verlauf.csv`` anhängen. ValueError, wenn die Übernahmeregel gegen den letzten Stand nicht erfüllt ist."""
    ordner = Path(ordner)
    vorher = letztes(ordner)
    if not uebernehmen(vorher, ergebnis):
        raise ValueError(f"Stand {commit} nicht übernehmen: Fehlerpunkte {ergebnis['punkte']:.2f} gegen "
                         f"{vorher['punkte']:.2f}, Rückschritte {rueckschritte(vorher, ergebnis) or 'keine'}")
    (ordner / "ergebnisse").mkdir(parents=True, exist_ok=True)
    (ordner / "ergebnisse" / f"{datum}_{commit}.json").write_text(
        json.dumps({"datum": datum, "commit": commit, **ergebnis}, ensure_ascii=False, indent=1), encoding="utf-8")
    verlauf = ordner / "verlauf.csv"
    neu = not verlauf.exists()
    with verlauf.open("a", encoding="utf-8") as f:
        if neu:
            f.write("datum,commit,testfaelle,trefferquote,punkte,rueckschritte\n")
        f.write(f"{datum},{commit},{len(ergebnis['faelle'])},{ergebnis['trefferquote']:.3f},"
                f"{ergebnis['punkte']:.2f},{' '.join(rueckschritte(vorher, ergebnis))}\n")


def bericht(ergebnis: dict, vorher: dict, erwartet: dict) -> str:
    """Kurzbericht: Gesamtwerte, Vergleich mit dem vorher abgelegten Ergebnis, je Testfall Stand und Punkte."""
    z = [f"Trefferquote {ergebnis['trefferquote']:.0%} · Fehlerpunkte {ergebnis['punkte']:.2f} · "
         f"{len(ergebnis['faelle'])} Testfälle"]
    if vorher:
        z.append(f"Vorher ({vorher['datum']}, {vorher['commit']}): Trefferquote {vorher['trefferquote']:.0%} · "
                 f"Fehlerpunkte {vorher['punkte']:.2f}")
        rs = rueckschritte(vorher, ergebnis)
        z.append(f"Rückschritte: {', '.join(rs) if rs else 'keine'}")
        z.append("Übernehmen: " + ("ja" if uebernehmen(vorher, ergebnis) else "nein"))
    for rid, t in ergebnis["faelle"].items():
        namen = ", ".join(f"{e['horse']} {e['urteil']}" for e in erwartet[rid]["kandidaten"].values())
        fehlt = f" · fehlt im Lauf: {t['fehlt']}" if t["fehlt"] else ""
        z.append(f"  {rid} {t['stand']:<19} {t['punkte']:.2f}  ({namen}){fehlt}")
    return "\n".join(z)


ORDNER = Path(__file__).resolve().parent / "tests" / "testsatz_durchgang"
AUFRUF = """Aufruf:
    python3 -I testsatz.py ausschnitt KARTE RACE_ID…           # Kartenausschnitte nach tests/testsatz_durchgang/karten/
    python3 -I testsatz.py bewerten LAUFORDNER [--ablegen COMMIT]   # Läufe gegen erwartet.json und den letzten Stand"""


def main(argv: list[str]) -> None:
    import gzip
    from datetime import date

    if len(argv) < 3 or argv[1] not in ("ausschnitt", "bewerten"):
        raise SystemExit(AUFRUF)
    if argv[1] == "ausschnitt":
        daten = laden(argv[2])
        (ORDNER / "karten").mkdir(parents=True, exist_ok=True)
        for rid in argv[3:]:
            ziel = ORDNER / "karten" / f"{rid}.json.gz"
            with gzip.open(ziel, "wt", encoding="utf-8") as f:
                json.dump(ausschnitt(daten, rid), f, ensure_ascii=False, separators=(",", ":"))
            print(ziel)
        return
    erwartet = json.loads((ORDNER / "erwartet.json").read_text(encoding="utf-8"))["testfaelle"]
    ergebnis = bewerten(erwartet, laeufe_laden(argv[2]))
    print(bericht(ergebnis, letztes(ORDNER), erwartet))
    commit = _opt(argv, "--ablegen")
    if commit:
        ablegen(ORDNER, ergebnis, commit=commit, datum=date.today().isoformat())
        print(f"Abgelegt: {ORDNER / 'verlauf.csv'}")


if __name__ == "__main__":
    main(sys.argv)
