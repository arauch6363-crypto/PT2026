"""
Wettstar – Toto und Festkurse (Sieg, Platz) der französischen Flachrennen eines Tages, auch Veranstaltungen nur mit
Toto (ohne FK-Kennzeichen).

Liest wettstar-pferdewetten.de mit Playwright über die festen CSS-Klassen aus:
  Übersicht:      .ttml__country[data-country=FRA] .ttml__meeting
  Veranstaltung:  .meetinginfo  (Rennnummer, Start, Rennart, Status)
  Rennen:         .race__grid__row  mit
                  .c-runner-odd--type-tote        = Toto
                  .c-runner-odd--type-fix         = Festkurs Sieg
                  .c-runner-odd--type-plcodd_fix  = Festkurs Platz

Und ordnet die Kurse den Startern der PMU-Karte zu (anhaengen): Veranstaltung über den Bahnnamen (ohne Akzente,
Bindestriche, Leerzeichen; ähnlichster Name), Rennen über die Rennnummer (sonst die Startzeit), Pferd über die
Startnummer – nur, wenn auch der Name passt (Schreibweisen weichen ab: Akzente, Apostrophe, Bindestriche,
Leerzeichen, „(FR)“ …); sonst über den ähnlichsten Namen im Rennen.

Colab:
    !pip install -q playwright && playwright install --with-deps chromium     # einmal je Laufzeit
    import wettstar
    df = wettstar.festkurse("2026-10-17")                 # Tabelle wie das Notebook
    racecard.run(BASE)                                    # holt die Festkurse selbst (festkurse=True)
"""
from __future__ import annotations

import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

from pathlib import Path

import pandas as pd

BASE_URL = "https://wettstar-pferdewetten.de"
LAND_CODE = "FRA"
RENNARTEN = ("Flachrennen",)       # () = alle
WORKER = 2                         # parallele Browser (mehr führte zu Zeitüberschreitungen)
VERSUCHE = 3                       # Seitenaufruf so oft versuchen, mit wachsender Pause
LADE_TIMEOUT_MS = 45000
# Ausländische Bahnen, die Wettstar unter „Frankreich“ listet (französische Toto-Pools) – nur der Rückfall, wenn
# festkurse() ohne die Bahnen der PMU-Karte läuft (sonst zählen nur Veranstaltungen, die zu einer Bahn passen)
AUSLAND_BAHNEN = (
    "Ascot", "Newmarket", "Doncaster", "York", "Epsom", "Goodwood", "Sandown", "Kempton", "Lingfield", "Chelmsford",
    "Wolverhampton", "Newcastle", "Haydock", "Cheltenham", "Aintree", "Leopardstown", "Curragh", "Dundalk",
    "Fairyhouse", "Punchestown", "Belmont Park", "Aqueduct", "Saratoga", "Keeneland", "Churchill Downs",
    "Gulfstream Park", "Santa Anita Park", "Del Mar", "Laurel Park", "Delaware Park", "Woodbine", "Far Hills",
    "San Isidro", "Palermo", "La Plata", "Gavea", "Cidade Jardim", "Maronas", "Hipodromo Chile", "Meydan", "Sha Tin",
    "Happy Valley", "Tokyo", "Kyoto", "Randwick", "Flemington", "Mons", "Wolvega", "Vincennes Int.", "Ankara", "Izmir",
    "Istanbul")
NAME_MIN = 0.80                    # Name gilt als gleich ab dieser Ähnlichkeit (nach Normalisierung)
NAME_MIN_NR = 0.60                 # bei gleicher Startnummer reicht weniger (Abkürzungen, Tippfehler)
BAHN_MIN = 0.80                    # Bahnname: Mindestähnlichkeit (Marseille-Borely ≠ Marseille-Vivaux)

# ---------- JavaScript: Daten direkt über die CSS-Klassen holen ----------
JS_MEETINGS = r"""
(land) => [...document.querySelectorAll(`.ttml__country[data-country="${land}"] .ttml__meeting`)]
  .map(m => {
    const id = ((m.className.match(/meeting-id--(\d+)/)) || [])[1];
    const rt = m.querySelector('.c-race-type');
    return {
      id,
      name: (m.querySelector('.ttml__meeting__title--subject')?.innerText || '').replace(/\s*\(\d+\)\s*$/, '').trim(),
      art: rt?.getAttribute('title') || (m.querySelector('.icon--r-gallop') ? 'Galopp' :
           m.querySelector('.icon--r-trot') ? 'Trab' : ''),
      fk: !!m.querySelector('.ttml__meeting__icon__fixcourse'),
      zeit: (m.querySelector('.ttml__meeting__time__text')?.innerText || '').replace(/\s+/g, ' ').trim()
    };
  }).filter(m => m.id)
"""

JS_RACES = r"""
(mid) => [...document.querySelectorAll(`.ttml__meeting.meeting-id--${mid} .meetinginfo`)]
  .map(c => {
    const a = c.querySelector('a.meetinginfo__racenumber') || c.querySelector('a[href*="/race/"]');
    const st = [...c.classList].find(k => /^meetinginfo--[A-Z]/.test(k)) || '';
    return {
      id: ((a?.getAttribute('href') || '').match(/\/race\/(\d+)/) || [])[1],
      nr: (a?.innerText || '').trim(),
      start: (c.querySelector('.ttml__race__time .val')?.innerText || '').replace('Uhr', '').trim(),
      art: (c.querySelector('.ttml__race__body__info2 span')?.innerText || '').trim(),
      titel: (c.querySelector('.ttml__race__body__name__race')?.innerText || '').trim(),
      status: st.replace('meetinginfo--', '')
    };
  }).filter(r => r.id)
"""

JS_RUNNERS = r"""
() => [...document.querySelectorAll('.race__grid__row')]
  .filter(r => r.querySelector('.race__grid__row__name'))
  .map(r => {
    const parts = [...r.querySelector('.race__grid__row__name').children]
      .map(e => (e.innerText || '').trim()).filter(Boolean);
    const odd = k => (r.querySelector(`.c-runner-odd--type-${k} .c-runner-odd__value`)?.innerText || '').trim();
    const kg = [...r.querySelectorAll('.race__grid__row__vars__pills')]
      .map(e => e.innerText).find(t => /kg/.test(t)) || '';
    return {
      nr: parts[0] || '', name: parts[1] || '', box: parts[2] || '',
      toto: odd('tote'), fix: odd('fix'), platz: odd('plcodd_fix'),
      starter: r.classList.contains('--rg-is-starter'),
      gewicht: (kg.match(/[\d,]+\s*kg/) || [''])[0],
      jockey: (r.querySelector('.race__grid__row__humans__jockey')?.innerText || '').trim(),
      tipp: (r.querySelector('.race__grid__row__badge .tipp')?.innerText || '').trim()
    };
  })
"""

SPALTEN = ["Veranstaltung", "Rennen", "Start", "Rennart", "Status", "Titel", "Rennen_ID", "Nr", "Pferd", "Box",
           "Toto", "FK_Sieg", "FK_Platz", "NS", "Gewicht", "Jockey", "Tipp"]


def num(s) -> float | None:
    """'5,5' / '1.234,5' / '3.90' -> Zahl; leer oder ≤ 0 -> None."""
    s = str(s or "").strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        v = float(s)
        return v if v > 0 else None
    except ValueError:
        return None


# ---------- Browser ----------
def _new_page(p):
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(**p.devices["Pixel 7"], locale="de-DE")
    # Bilder, Schriften, Medien nicht laden: nur Text und Skripte werden gebraucht, Seiten laden so deutlich schneller
    ctx.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "font", "media")
              else route.continue_())
    return browser, ctx.new_page()


def _load(page, url, selector, versuche: int = VERSUCHE):
    """Seite laden und auf `selector` warten; bei Zeitüberschreitung bis zu `versuche` Mal mit wachsender Pause."""
    import time
    for n in range(1, versuche + 1):
        try:
            page.goto(url, wait_until="commit", timeout=LADE_TIMEOUT_MS)
            page.wait_for_selector(selector, timeout=LADE_TIMEOUT_MS)
            page.wait_for_timeout(1500)    # Kurse nachladen lassen
            return
        except Exception:
            if n == versuche:
                raise
            time.sleep(5 * n)


def veranstaltungen_waehlen(meetings: list[dict], bahnen=None, nur_fk: bool = False,
                            ausland=AUSLAND_BAHNEN) -> list[dict]:
    """Galopp-Veranstaltungen (mit oder ohne Festkurse, nur_fk=True: nur mit FK-Kennzeichen). Mit `bahnen` (Bahnen
    der PMU-Karte: französische Flachrennen des Tages) nur die, deren Name zu einer davon passt – ausländische Bahnen
    unter „Frankreich“ fallen so von selbst weg; ohne `bahnen` alle außer der Liste `ausland`."""
    aus = {norm(b) for b in ausland or ()}
    out = []
    for m in meetings:
        if m.get("art") != "Galopp" or (nur_fk and not m.get("fk")):
            continue
        if bahnen:
            if max((bahn_aehnlich(m.get("name"), b) for b in bahnen), default=0) < BAHN_MIN:
                continue
        elif norm(m.get("name")) in aus:
            continue
        out.append(m)
    return out


def _collect(overview, land, rennarten, nur_fk, nur_offen, bahnen, log):
    from playwright.sync_api import sync_playwright
    races = {}
    with sync_playwright() as p:
        browser, page = _new_page(p)
        _load(page, overview, ".ttml__meeting")
        meetings = page.evaluate(JS_MEETINGS, land)
        chosen = veranstaltungen_waehlen(meetings, bahnen, nur_fk)
        log(f"Wettstar: {len(meetings)} Veranstaltungen in {land}:")
        for m in meetings:                                 # Übersicht: warum geladen bzw. nicht
            best = max(bahnen or [None], key=lambda b: bahn_aehnlich(m.get("name"), b) if b else 0)
            log(f"   {'✔' if m in chosen else '·'} {m.get('name', ''):<20} {m.get('art', ''):<7} "
                f"{'FK' if m.get('fk') else 'nur Toto':<8}"
                + (f" ähnlichste Bahn der Karte: {best} ({bahn_aehnlich(m.get('name'), best):.2f})" if best else ""))
        for m in chosen:
            try:
                _load(page, f"{overview}&meeting={m['id']}", f".ttml__meeting.meeting-id--{m['id']} .meetinginfo")
            except Exception as e:
                log(f"   Wettstar {m.get('name')}: Rennen nicht geladen – {str(e).splitlines()[0]}")
                continue
            for r in page.evaluate(JS_RACES, m["id"]):
                art_ok = not rennarten or (r["art"] or "").lower() in [a.lower() for a in rennarten]
                if not art_ok or (nur_offen and r["status"] == "OFFICIAL"):
                    continue
                races[int(r["id"])] = {"Veranstaltung": m["name"], "Rennen": r["nr"], "Start": r["start"],
                                       "Rennart": r["art"], "Titel": r["titel"], "Status": r["status"]}
        browser.close()
    return races


def _scrape(items, total, done, lock, log):
    from playwright.sync_api import sync_playwright
    out = []
    with sync_playwright() as p:
        browser, page = _new_page(p)
        for rid, meta in items:
            try:
                _load(page, f"{BASE_URL}/race/{rid}", ".race__grid__row__name")
                for r in page.evaluate(JS_RUNNERS):
                    nr = r["nr"].rstrip(".")
                    box = r["box"].strip("()")
                    out.append({**meta, "Rennen_ID": rid, "Nr": int(nr) if nr.isdigit() else None,
                                "Pferd": r["name"], "Box": int(box) if box.isdigit() else None,
                                "Toto": num(r["toto"]), "FK_Sieg": num(r["fix"]), "FK_Platz": num(r["platz"]),
                                "NS": not r["starter"], "Gewicht": r["gewicht"], "Jockey": r["jockey"],
                                "Tipp": r["tipp"]})
            except Exception as e:                                # ein Rennen darf den Rest nicht verhindern
                log(f"   Wettstar {meta.get('Veranstaltung')} R{meta.get('Rennen')}: Fehler – {str(e).splitlines()[0]}")
            with lock:
                done[0] += 1
        browser.close()
    return out


def festkurse(datum, *, land: str = LAND_CODE, rennarten=RENNARTEN, nur_fk: bool = False, nur_offen: bool = False,
              bahnen=None, worker: int = WORKER, log=print) -> pd.DataFrame:
    """Toto und Festkurse der französischen Flachrennen eines Tages als Tabelle (SPALTEN) – auch Veranstaltungen nur
    mit Toto (FK-Spalten dann leer; nur_fk=True: nur mit FK-Kennzeichen). bahnen: Bahnnamen der PMU-Karte – dann nur
    passende Veranstaltungen (sonst alle Galopp-Veranstaltungen außer AUSLAND_BAHNEN).
    Läuft auch in Colab/Jupyter (Playwright-Sync-API in eigenen Threads, nicht im Notebook-Event-Loop)."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        log("Wettstar: Playwright fehlt (pip install playwright && playwright install --with-deps chromium) – ohne Festkurse.")
        return pd.DataFrame(columns=SPALTEN)
    datum = pd.Timestamp(datum).strftime("%Y-%m-%d")
    overview = f"{BASE_URL}/races/{datum}?country={land}"
    with ThreadPoolExecutor(1) as ex:
        races = ex.submit(_collect, overview, land, tuple(rennarten or ()), nur_fk, nur_offen,
                          list(bahnen or ()), log).result()
    if not races:
        log("Wettstar: keine passenden Rennen gefunden.")
        return pd.DataFrame(columns=SPALTEN)
    items = list(races.items())
    chunks = [c for c in (items[i::worker] for i in range(worker)) if c]
    done, lock = [0], threading.Lock()
    with ThreadPoolExecutor(len(chunks)) as ex:
        res = list(ex.map(lambda c: _scrape(c, len(items), done, lock, log), chunks))
    df = pd.DataFrame([r for part in res for r in part], columns=SPALTEN)
    if df.empty:
        return df
    df["_rn"] = pd.to_numeric(df["Rennen"], errors="coerce")
    df = df.sort_values(["Veranstaltung", "_rn", "Nr"]).drop(columns="_rn").reset_index(drop=True)
    log(f"Wettstar: {df['Veranstaltung'].nunique()} Veranstaltungen, {df['Rennen_ID'].nunique()} Rennen, "
        f"{len(df)} Pferde – {int(df['Toto'].notna().sum())} mit Toto, {int(df['FK_Sieg'].notna().sum())} mit Festkurs")
    return df


# ---------- Zuordnung zur PMU-Karte ----------
def norm(s) -> str:
    """Für den Vergleich: ohne Akzente, Herkunft „(FR)“, Satzzeichen und Leerzeichen, groß."""
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"\((?:[A-Z]{2,3})\)", "", t.upper())          # (FR), (IRE), (GB) …
    return re.sub(r"[^A-Z0-9]", "", t)


def aehnlich(a, b) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


BAHN_TEIL_MIN = 5                  # Bahnname ganz im anderen enthalten (Longchamp ⊂ ParisLongchamp) ab so vielen Zeichen
BAHN_TEIL_WERT = 0.95


def bahn_aehnlich(a, b) -> float:
    """Wie aehnlich, aber für Bahnnamen: steckt der kürzere Name ganz im längeren (Longchamp / PARISLONGCHAMP,
    La Teste / LA TESTE DE BUCH), zählt das als Treffer (BAHN_TEIL_WERT)."""
    na, nb = norm(a), norm(b)
    kurz, lang = sorted((na, nb), key=len)
    if len(kurz) >= BAHN_TEIL_MIN and kurz != lang and kurz in lang:
        return BAHN_TEIL_WERT
    return aehnlich(a, b)


def _zeit(s) -> str | None:
    m = re.search(r"(\d{1,2})[:h.](\d{2})", str(s or ""))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def zuordnen(daten: dict, df: pd.DataFrame) -> dict:
    """{(race_id, Startnummer): {"sieg", "platz", "toto", "name", "ns", "sicher"}} für die Starter der Karte.
    Bahn: ähnlichster Name (≥ BAHN_MIN); Rennen: gleiche Rennnummer, sonst gleiche Startzeit; Pferd: gleiche
    Startnummer mit passendem Namen (≥ NAME_MIN_NR), sonst ähnlichster Name im Rennen (≥ NAME_MIN)."""
    if df is None or df.empty:
        return {}
    out = {}
    bahnen = df["Veranstaltung"].dropna().unique().tolist()
    for rid, r in (daten.get("races") or {}).items():
        bahn = max(bahnen, key=lambda b: bahn_aehnlich(b, r.get("course")), default=None)
        if bahn is None or bahn_aehnlich(bahn, r.get("course")) < BAHN_MIN:
            continue
        w = df[df["Veranstaltung"] == bahn]
        rn = pd.to_numeric(w["Rennen"], errors="coerce")
        rennen = w[rn == r.get("race_no")]
        if rennen.empty and _zeit(r.get("time")):
            rennen = w[w["Start"].map(_zeit) == _zeit(r.get("time"))]
        if rennen.empty:
            continue
        frei = rennen.copy()
        for x in r.get("runners") or []:
            kand = frei[frei["Nr"] == x.get("no")]
            treffer, sicher = None, False
            if len(kand) and aehnlich(kand.iloc[0]["Pferd"], x.get("horse")) >= NAME_MIN_NR:
                treffer, sicher = kand.iloc[0], True
            elif len(frei):                                    # Nummer passt nicht: ähnlichster Name im Rennen
                sim = frei["Pferd"].map(lambda n: aehnlich(n, x.get("horse")))
                if sim.max() >= NAME_MIN:
                    treffer, sicher = frei.loc[sim.idxmax()], True
            if treffer is None:
                continue
            frei = frei.drop(index=treffer.name)
            out[(rid, x.get("no"))] = {"sieg": treffer["FK_Sieg"] if pd.notna(treffer["FK_Sieg"]) else None,
                                       "platz": treffer["FK_Platz"] if pd.notna(treffer["FK_Platz"]) else None,
                                       "toto": treffer["Toto"] if pd.notna(treffer["Toto"]) else None,
                                       "name": treffer["Pferd"], "ns": bool(treffer["NS"]), "sicher": sicher}
    return out


def lesen(pfad) -> pd.DataFrame:
    """CSV aus dem Wettstar-Notebook (Semikolon, Dezimalkomma) oder aus df.to_csv() als Tabelle wie festkurse()."""
    txt = open(pfad, encoding="utf-8-sig").readline()
    df = pd.read_csv(pfad, sep=";", decimal=",") if ";" in txt else pd.read_csv(pfad)
    for c in ("Toto", "FK_Sieg", "FK_Platz"):
        if c in df:
            df[c] = df[c].map(lambda v: num(v) if isinstance(v, str) else (v if pd.notna(v) and v > 0 else None))
    df["Nr"] = pd.to_numeric(df.get("Nr"), errors="coerce").astype("Int64")
    if "NS" in df:
        df["NS"] = df["NS"].astype(str).str.lower().isin(["true", "1", "ja"])
    return df.reindex(columns=SPALTEN)


def anhaengen(daten: dict, df=None, tag=None, log=print) -> int:
    """Festkurse an die Starter der Kartendaten hängen (x["fk"]); df: fertige Tabelle (festkurse), Pfad zu einer
    CSV aus dem Wettstar-Notebook oder None = jetzt holen. Rückgabe: Zahl zugeordneter Starter. Fehler oder
    fehlendes Playwright: Karte ohne Festkurse."""
    try:
        if isinstance(df, (str, Path)):
            log(f"Festkurse aus {df}")
            df = lesen(df)
        if df is None:                                   # nur Veranstaltungen, die zu den Bahnen der Karte passen
            bahnen = sorted({r.get("course") for r in (daten.get("races") or {}).values() if r.get("course")})
            log(f"Bahnen der Karte: {', '.join(bahnen)}")
            df = festkurse(tag or daten.get("date"), bahnen=bahnen, log=log)
        je = zuordnen(daten, df)
    except Exception as e:
        log(f"Wettstar: Festkurse nicht geholt ({str(e).splitlines()[0]}) – Karte ohne Festkurse.")
        return 0
    n_alle = 0
    ohne = []
    for rid, r in (daten.get("races") or {}).items():
        for x in r.get("runners") or []:
            if x.get("nr"):
                continue
            n_alle += 1
            fk = je.get((rid, x.get("no")))
            if fk:
                x["fk"] = fk
            elif len(df) and any(bahn_aehnlich(b, r.get("course")) >= BAHN_MIN for b in df["Veranstaltung"].dropna().unique()):
                ohne.append(f"{r.get('course')} C{r.get('race_no')} Nr. {x.get('no')} {x.get('horse')}")
    log(f"Festkurse zugeordnet: {len(je)} von {n_alle} Startern"
        + (f" – ohne Zuordnung: {'; '.join(ohne[:8])}{' …' if len(ohne) > 8 else ''}" if ohne else ""))
    return len(je)
