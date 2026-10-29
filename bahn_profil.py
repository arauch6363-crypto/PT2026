"""Profil der französischen Galopp-Bahnen: Umfang des Rundkurses, Länge der Zielgeraden, Kurve (rechts/links), Profil
(flach/wellig, ansteigendes Ziel), gerade Bahn – Grundlage für Bahn-Eigenschaften als Merkmale (Version 20), die
anders als der Bahnname auch auf seltene Bahnen übertragbar sind.

Die Werte stammen aus den Bahnbeschreibungen von Turfoo und Zeturf (gegengeprüft mit France Galop) und werden einmal
recherchiert, geprüft und dann in PROFIL eingetragen – nichts davon wird geschätzt oder erfunden.

    import bahn_profil as bp
    t = bp.recherche(BASE)        # Colab (freies Internet): Bahnseiten lesen, Sätze mit Zahlen und erkannte Werte
                                  # -> BASE/bahn_profil_recherche.csv zum Prüfen
    bp.profil("CHANTILLY")        # eingetragene Werte (None, solange die Bahn noch nicht geprüft ist)

Die Liste der Bahnen kommt aus boden_manuell.json (alle Bahnen mit Flachrennen der Saison).
"""
from __future__ import annotations

import html
import json
import re
import time
import unicodedata
from pathlib import Path

QUELLEN = ("https://turfoo.fr/hippodromes/{slug}/", "https://www.zeturf.fr/fr/hippodromes/{slug}")
# abweichende Adressen der Quellen (Turfoo schreibt manche Bahnen anders)
SLUGS = {"PARISLONGCHAMP": ["longchamp", "parislongchamp"], "MAISONS LAFFITTE": ["maisons-laffites", "maisons-laffitte"],
         "LE CROISE LAROCHE": ["croise-laroche", "le-croise-laroche"], "LE PIN AU HARAS": ["le-pin-au-haras", "pin-au-haras"],
         "LE LION D ANGERS": ["le-lion-d-angers", "lion-d-angers"], "LES SABLES D OLONNE": ["les-sables-d-olonne", "sables-d-olonne"],
         "BORDEAUX LE BOUSCAT": ["bordeaux-le-bouscat", "le-bouscat"], "LA TESTE DE BUCH": ["la-teste-de-buch", "la-teste"],
         "PORNICHET LA BAULE": ["pornichet-la-baule", "pornichet"], "ROYAN LA PALMYRE": ["royan-la-palmyre", "royan"]}

# geprüfte Werte je Bahn (und, wo eine Bahn mehrere Pisten hat, je Piste unter "pisten"):
# umfang_m, zielgerade_m, kurve ("rechts"/"links"), profil ("flach"/"wellig"), ziel_ansteigend (bool), gerade_bahn (bool),
# quelle. Leer, bis die Recherche geprüft ist.
PROFIL: dict[str, dict] = {}

GROESSE = ((1600, "klein"), (2000, "mittel"))   # Umfang < 1600 m: klein/eng, < 2000 m: mittel, sonst groß


def bahnen(base_dir: Path | None = None) -> list[str]:
    """Bahnen aus boden_manuell.json (neben diesem Modul)."""
    pfad = Path(base_dir or Path(__file__).parent) / "boden_manuell.json"
    return sorted(json.loads(pfad.read_text(encoding="utf-8")).get("bahnen", {}))


def slugs(bahn: str) -> list[str]:
    """Mögliche Adressteile einer Bahn (ohne Akzente, Kleinbuchstaben, Bindestriche)."""
    roh = unicodedata.normalize("NFKD", bahn).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", roh).strip("-")
    ohne = re.sub(r"^(le|la|les)-", "", s)
    return list(dict.fromkeys(SLUGS.get(bahn, []) + [s, ohne]))


def text_aus_html(seite: str) -> str:
    seite = re.sub(r"<(script|style)\b.*?</\1>", " ", seite, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", seite))).strip()


_ZAHL = r"(\d[\d .  ]{2,6})\s*(?:m\b|mètres|metres)"


def _zahl(s: str) -> int | None:
    z = re.sub(r"\D", "", s)
    return int(z) if z else None


def auswerten(text: str) -> dict:
    """Aus einer Bahnbeschreibung: Sätze mit Piste/Zielgerade/Corde und daraus erkannte Werte (erste Fundstelle;
    mehrere Pisten erscheinen als mehrere Sätze – die Werte sind ein Vorschlag zum Prüfen, nicht geprüft)."""
    saetze = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text)
              if re.search(r"ligne (d.arriv|droite)|piste|corde|virage|montée|vallonn|dénivel", s, re.I)
              and re.search(r"\d", s) and len(s) < 600]
    t = " ".join(saetze)
    out = {"saetze": saetze}
    m = re.search(r"ligne (?:d.arriv\w*|droite)(?: finale)?[^.]{0,40}?" + _ZAHL, t, re.I) \
        or re.search(_ZAHL + r"[^.]{0,30}?ligne (?:d.arriv\w*|droite)", t, re.I)
    out["zielgerade_m"] = _zahl(m.group(1)) if m else None
    m = re.search(r"(?:piste|anneau|tour|circuit|développement|périmètre)[^.]{0,60}?" + _ZAHL, t, re.I)
    out["umfang_m"] = _zahl(m.group(1)) if m else None
    gauche, droite = re.search(r"corde à gauche", t, re.I), re.search(r"corde à droite", t, re.I)
    out["kurve"] = "beides" if gauche and droite else "links" if gauche else "rechts" if droite else None
    # Profil auch aus Sätzen ohne Zahl („Le terrain est plat.“)
    out["profil"] = ("wellig" if re.search(r"vallonn|ondul|dénivel|bosse", text, re.I)
                     else "flach" if re.search(r"\bplat(e)?\b(?! de)|parfaitement plat|sans relief", text, re.I) else None)
    out["ziel_ansteigend"] = True if re.search(r"(montée|côte|faux plat montant)[^.]{0,60}(arriv|poteau|ligne)", text, re.I) else None
    out["gerade_bahn"] = True if re.search(r"ligne droite (?:de|du|pour)[^.]{0,40}(1 ?000|1 ?100|1 ?200|sprint)|piste en ligne droite", t, re.I) else None
    return out


def recherche(base: Path | None = None, namen: list[str] | None = None, *, pause: float = 1.0,
              timeout: int = 20, log=print):
    """Je Bahn die Seiten der Quellen lesen und auswerten; Ergebnis als Tabelle (eine Zeile je Bahn und Quelle) und –
    mit base – als BASE/bahn_profil_recherche.csv zum Prüfen. Braucht freies Internet (Colab)."""
    import pandas as pd
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Recherche Bahnprofile)"
    zeilen = []
    for bahn in namen or bahnen():
        for vorlage in QUELLEN:
            treffer = None
            for slug in slugs(bahn):
                url = vorlage.format(slug=slug)
                try:
                    r = s.get(url, timeout=timeout)
                except Exception as e:                    # Netz oder Seite: Bahn weiter mit der nächsten Adresse
                    log(f"  {bahn}: {url} – {type(e).__name__}")
                    continue
                time.sleep(pause)
                if r.status_code == 200 and len(r.text) > 2000:
                    treffer = (url, text_aus_html(r.text))
                    break
            if treffer is None:
                zeilen.append({"bahn": bahn, "quelle": vorlage.split("/")[2], "url": None, "gefunden": False})
                continue
            a = auswerten(treffer[1])
            zeilen.append({"bahn": bahn, "quelle": vorlage.split("/")[2], "url": treffer[0], "gefunden": True,
                           **{k: v for k, v in a.items() if k != "saetze"}, "saetze": " | ".join(a["saetze"])[:3000]})
        z = [x for x in zeilen if x["bahn"] == bahn and x["gefunden"]]
        log(f"{bahn}: " + ("; ".join(f"{x['quelle']}: Umfang {x.get('umfang_m')} m, Zielgerade {x.get('zielgerade_m')} m, "
                                     f"{x.get('kurve')}" for x in z) if z else "keine Seite gefunden"))
    t = pd.DataFrame(zeilen)
    if base is not None and len(t):
        pfad = Path(base) / "bahn_profil_recherche.csv"
        t.to_csv(pfad, index=False, encoding="utf-8")
        log(f"Gespeichert: {pfad}")
    return t


def profil(bahn: str, parcours: str | None = None) -> dict | None:
    """Geprüfte Werte einer Bahn (bei mehreren Pisten die der Piste, sonst die der Bahn) mit Größenklasse aus dem
    Umfang; None, solange die Bahn nicht eingetragen ist."""
    p = PROFIL.get(bahn)
    if not p:
        return None
    if parcours and parcours in (p.get("pisten") or {}):
        p = {**{k: v for k, v in p.items() if k != "pisten"}, **p["pisten"][parcours]}
    u = p.get("umfang_m")
    groesse = None if u is None else next((name for grenze, name in GROESSE if u < grenze), "groß")
    return {**{k: v for k, v in p.items() if k != "pisten"}, "groesse": groesse}
