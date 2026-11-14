"""Bodenangaben von France Galop (Seiten „Hier“, „Aujourd'hui“, „Demain“) – für die Rennkarte, wenn PMU noch keine hat.

France Galop veröffentlicht den Boden je Veranstaltung meist schon am Vortag (Messung 48 h vorher) und aktualisiert
ihn am Morgen. Die Übersichtsseiten zeigen je Veranstaltung einen Block

    TOULOUSE
    Horaire : 16h40
    Terrain tr souple (3,8)
    Plat : 8

Abkürzungen („tr“ = très) und Groß/Klein-Schreibung löst rtr_arr.boden_gruppe auf; hier wird der Begriff auf die
Schreibweise aus rtr_arr.GOING_MAP gebracht („Très souple“) und der Penetrometer-Wert als Zahl gelesen.

    import boden_fg
    boden_fg.tag(date(2026, 11, 15))   # {"TOULOUSE": {"terrain": "Très souple", "wert": 3.8, "psf": False}, …}

Nur Standardbibliothek und requests. Fehler (Netz, Seite umgebaut, falscher Tag) -> {} mit Meldung.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import pmu
import rtr_arr

PARIS = ZoneInfo("Europe/Paris")
SEITEN = {-1: "hier", 0: "aujourdhui", 1: "demain"}
URL = "https://www.france-galop.com/fr/courses/{seite}"
HEADERS = {"User-Agent": "Mozilla/5.0 (private racing analysis)"}
MONATE = {"janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
          "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12}
TERRAIN = re.compile(r"^Terrain\s+(.+?)\s*(?:\(\s*([\d]+(?:[.,]\d+)?)\s*\))?\s*$", re.I)
KANON = {rtr_arr._norm_boden(k): k for k in rtr_arr.GOING_MAP}         # "TRES SOUPLE" -> "Très souple"


def _zeilen(seite_html: str) -> list[str]:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", seite_html, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    return [z.strip() for z in t.split("\n") if z.strip()]


def _datum(zeilen: list[str]) -> date | None:
    """Datum der Seite aus „Aujourd'hui / 14 novembre 2026“."""
    for z in zeilen[:400]:
        m = re.search(r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", z, re.I)
        if m and m.group(2).lower() in MONATE:
            return date(int(m.group(3)), MONATE[m.group(2).lower()], int(m.group(1)))
    return None


def terrain_begriff(text: str) -> str | None:
    """'tr souple' -> 'Très souple', 'collant' -> 'Collant', 'PSF STANDARD' -> 'PSF Standard'; unbekannt -> None."""
    t = rtr_arr._norm_boden(re.sub(r"(?i)\btr\b\.?", "très", text or ""))
    if t in KANON:
        return KANON[t]
    return "PSF" if rtr_arr.boden_gruppe(text) == "PSF" else None


def lesen(seite_html: str) -> tuple[date | None, dict[str, dict]]:
    """(Datum der Seite, {Bahn (pmu.norm): {"terrain", "wert", "psf", "roh"}}) – nur Veranstaltungen mit Terrain;
    terrain None = Begriff nicht erkannt (Schreibweise neu)."""
    z = _zeilen(seite_html)
    out: dict[str, dict] = {}
    for i in range(len(z) - 1):
        if not z[i + 1].lower().startswith("horaire"):
            continue
        for k in range(i + 2, min(i + 5, len(z))):           # Terrain steht direkt unter der Uhrzeit (falls schon da)
            m = TERRAIN.match(z[k])
            if not m:
                continue
            begriff = terrain_begriff(m.group(1))           # None: unbekannter Begriff (tag() meldet ihn)
            wert = float(m.group(2).replace(",", ".")) if m.group(2) else None
            out[pmu.norm(z[i])] = {"terrain": begriff, "wert": wert,
                                   "psf": bool(begriff) and rtr_arr.boden_gruppe(begriff) == "PSF", "roh": z[k]}
            break
    return _datum(z), out


def tag(d: date | None = None, session: requests.Session | None = None, log=print) -> dict[str, dict]:
    """Bodenangaben von France Galop für den Tag d (gestern, heute oder morgen, französische Zeit); sonst {}."""
    heute = datetime.now(PARIS).date()
    d = d or heute
    seite = SEITEN.get((d - heute).days)
    if seite is None:
        return {}
    try:
        r = (session or requests).get(URL.format(seite=seite), headers=HEADERS, timeout=20)
        r.raise_for_status()
        datum, boden = lesen(r.text)
    except Exception as e:                                   # Netz oder Seite: Karte läuft ohne diese Quelle
        log(f"Boden France Galop: nicht abrufbar ({type(e).__name__}: {str(e)[:120]})")
        return {}
    if datum is not None and datum != d:
        log(f"Boden France Galop: Seite zeigt {datum}, gesucht {d} – nicht verwendet.")
        return {}
    for bahn, v in boden.items():
        if v["terrain"] is None:
            log(f"Boden France Galop: {bahn}: {v['roh']!r} nicht erkannt – übergangen (bitte melden).")
    return {k: v for k, v in boden.items() if v["terrain"]}
