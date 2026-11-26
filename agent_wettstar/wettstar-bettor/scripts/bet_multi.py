"""Usage: WS_USER=.. WS_PASS=.. python3 bet_multi.py bets.json [LIVE]
bets.json: [{"bahn":"Deauville","zeit":"16:50","nr":14,"name":"Superclass","min_fk":6.5,"stake":10}]
bahn und name dürfen wie auf der PMU-Karte geschrieben sein („MANS“, „THE CAT'S“): verglichen wird ohne
Groß-/Kleinschreibung, Akzente, Satzzeichen, Leerzeichen und Herkunft „(FR)“.

Guthaben: Gewettet wird in der Reihenfolge von bets.json, solange das Guthaben Einsatz + 5 % Steuer deckt. Ab dem
ersten Tipp, der nicht mehr gedeckt ist, wird nichts mehr gewettet (auch keine späteren kleineren Einsätze).
Exit-Code 2 = Guthaben reichte nicht für alle Tipps (die gedeckten davor sind platziert). Nie eine Einzahlung."""
import json, os, re, sys, unicodedata
from difflib import SequenceMatcher

BASE = "https://www.wettstar-pferdewetten.de"
OUT = "/tmp/ws"
NAME_MIN = 0.80   # Mindestähnlichkeit des Namens bei gleicher Startnummer (Schreibweisen PMU-Karte vs. Wettstar)
STEUER = 0.05     # Wettsteuer kommt zum Einsatz hinzu


def norm(t): return re.sub(r"\s+", " ", (t or "").replace("\xa0", " ")).strip()
def num(s): return float(s.replace(".", "").replace(",", "."))


def key(s):
    """Vergleichsschlüssel wie wettstar.norm: ohne Akzente, Herkunft „(FR)“, Satzzeichen, Leerzeichen; groß."""
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"\((?:[A-Z]{2,3})\)", "", t.upper())
    return re.sub(r"[^A-Z0-9]", "", t)


def ohne_artikel(s): return re.sub(r"^\s*(?:LES|LE|LA|L)(?:\s+|['’])", "", str(s or ""), flags=re.I)


def bahn_passt(bahn, text):
    """Bahn der Karte („MANS“, „SAINT CLOUD“) steckt im Linktext der Veranstaltung („Le Mans“, „Saint-Cloud“)."""
    t = key(text)
    return any(k and k in t for k in (key(bahn), key(ohne_artikel(bahn))))


def name_passt(nr, name, zeile):
    """Erste Zeile „<nr>.<Name>(<Box>)“ der Wettstar-Tabelle passt zu Startnummer und Name."""
    erste = norm((zeile or "").replace("\xa0", " ").split("\n")[0])
    m = re.match(rf"{int(nr)}\.\s*(.*?)\s*(?:\(\d+\))?$", erste)
    if not m: return False
    a, b = key(m.group(1)), key(name)
    return bool(a and b) and (a == b or a.startswith(b) or SequenceMatcher(None, a, b).ratio() >= NAME_MIN)


def kosten(stake): return round(float(stake) * (1 + STEUER), 2)


class Kasse:
    """Guthaben während eines Laufs. Deckt Wetten der Reihe nach; sobald eine nicht mehr gedeckt ist, ist die Kasse
    zu und es wird bis zum Ende des Laufs nichts mehr gewettet. Gelesenes Guthaben (Seitenkopf) zählt nur nach unten:
    der Rest ist immer das Minimum aus eigener Rechnung und Anzeige."""

    def __init__(self, guthaben):
        self.rest, self.zu = round(float(guthaben), 2), False

    def deckt(self, stake, gelesen=None):
        if gelesen is not None:
            self.rest = min(self.rest, round(float(gelesen), 2))
        if self.zu or self.rest + 1e-9 < kosten(stake):
            self.zu = True
        return not self.zu

    def abbuchen(self, stake):
        self.rest = round(self.rest - kosten(stake), 2)


class Skip(Exception): pass


def main():
    from playwright.sync_api import sync_playwright
    bets = json.load(open(sys.argv[1]))
    LIVE = len(sys.argv) > 2 and sys.argv[2] == "LIVE"
    os.makedirs(OUT, exist_ok=True)

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
        pg.goto(BASE, wait_until="networkidle")
        try: pg.get_by_text("Ablehnen", exact=True).first.click(timeout=10000)
        except Exception: pass

        # 1) Rennlinks auflösen (ohne Login)
        def resolve(bt):
            if bt.get("race_url"): return bt["race_url"]
            pg.goto(BASE, wait_until="networkidle")
            ms = {h for h, t in pg.eval_on_selector_all("a[href*='meeting=']", "e=>e.map(a=>[a.href,a.innerText])")
                  if bahn_passt(bt["bahn"], t)}
            if len(ms) != 1: raise Skip(f"Meeting für {bt['bahn']} nicht eindeutig: {len(ms)}")
            pg.goto(ms.pop(), wait_until="networkidle")
            rs = {h for h, t in pg.eval_on_selector_all("a[href*='/race/']", "e=>e.map(a=>[a.href,a.innerText])")
                  if norm(t).startswith(f"Start {bt['zeit']}")}
            if len(rs) != 1: raise Skip(f"Rennen {bt['zeit']} nicht eindeutig: {len(rs)}")
            return rs.pop()

        for bt in bets:
            try: bt["url"] = resolve(bt)
            except Skip as e: bt["url"] = None; bt["status"] = f"ABBRUCH: {e}"

        # 2) Login einmalig
        pg.locator("header").get_by_role("button", name="Login").first.click(timeout=8000)
        pg.wait_for_selector("#login-username", state="visible", timeout=15000)
        assert pg.url.split("/")[2].endswith("wettstar-pferdewetten.de")
        pg.fill("#login-username", os.environ["WS_USER"]); pg.fill("#login-password", os.environ["WS_PASS"])
        pg.get_by_role("button", name="Einloggen").click()
        pg.wait_for_selector("#login-username", state="detached", timeout=20000)
        pg.wait_for_load_state("networkidle")

        def balance():
            m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2}) ?€", norm(pg.locator("header").first.inner_text()))
            if not m: raise Skip("Guthaben nicht lesbar")
            return num(m.group(1))

        kasse = Kasse(balance())
        need = sum(kosten(x["stake"]) for x in bets if x["url"])
        print(f"Guthaben {kasse.rest:.2f}, benötigt gesamt {need:.2f}")
        if kasse.rest < need:
            print(f"HINWEIS: Guthaben reicht nicht für alle Tipps (fehlen {need - kasse.rest:.2f}). Gewettet wird von "
                  "oben, bis ein Tipp nicht mehr gedeckt ist, danach nichts mehr. KEINE Einzahlung.")

        # 3) Wetten (Reihenfolge von bets.json)
        for bt in bets:
            if kasse.zu:
                print(f"{bt['name']}: ABBRUCH: nicht gewettet, Guthaben aufgebraucht (KEINE Einzahlung)"); continue
            if not bt["url"]: print(bt["name"], bt["status"]); continue
            tag = re.sub(r"\W+", "_", f"{bt['name']}_{bt['zeit']}")
            nr, stake, min_fk = int(bt["nr"]), float(bt["stake"]), float(bt["min_fk"])
            try:
                pg.goto(bt["url"], wait_until="networkidle")
                try: gelesen = balance()
                except Skip: gelesen = 0.0   # nicht lesbar: als leer behandeln, ab hier nichts mehr wetten
                if not kasse.deckt(stake, gelesen):
                    print(f"{bt['name']}: ABBRUCH: zu wenig Guthaben ({kasse.rest:.2f} < {kosten(stake):.2f}), "
                          "ab hier keine Wetten mehr. KEINE Einzahlung."); continue
                if pg.get_by_text("Start " + bt["zeit"], exact=False).count() == 0 and bt["zeit"] not in norm(pg.locator("body").inner_text()):
                    raise Skip("Startzeit nicht auf Seite")
                pg.get_by_role("button", name="Festkurs", exact=True).click()
                try: pg.get_by_role("button", name="Sieg FK", exact=True).click(timeout=5000)
                except Exception: pass
                pg.wait_for_timeout(800)
                rows = pg.locator(".race__grid__row__columns").filter(
                    has=pg.locator(".race__grid__row__name strong", has_text=re.compile(rf"^{nr}\.$")))
                if rows.count() != 1: raise Skip("Zeile nicht eindeutig")
                row = rows.first
                zeile = row.locator(".race__grid__row__name").inner_text()
                if not name_passt(nr, bt["name"], zeile):
                    raise Skip(f"Name passt nicht (Seite: {norm(zeile.split(chr(10))[0])})")
                fk = num(norm(row.locator(".c-runner-odd--type-fix .c-runner-odd__value").first.inner_text()))
                print(f"{bt['name']}: FK {fk}")
                if fk < min_fk: raise Skip(f"FK {fk} < {min_fk}")
                if int(stake) not in (1, 3, 5, 10, 20) or stake != int(stake): raise Skip("Einsatz kein einzelner Chip")
                row.locator(".c-runner-odd--type-fix").first.click(); pg.wait_for_timeout(400)
                pg.get_by_role("button", name=re.compile(rf"^{int(stake)}\s*€$")).first.click(); pg.wait_for_timeout(400)
                pg.get_by_role("button", name="Wettabgabe", exact=True).click()
                dlg = pg.locator("[role=dialog], .modal").filter(has_text="Meine Wette").first
                dlg.wait_for(state="visible", timeout=15000); pg.wait_for_timeout(400)
                t = norm(dlg.inner_text()); print("DIALOG:", t)
                errs = []
                if not re.search(rf"Rang 1:? ?{nr}\b", t): errs.append("Rang 1 != Nr")
                if "Sieg FK" not in t: errs.append("Wettart != Sieg FK")
                m = re.search(r"Festkurs:? ?(\d+,\d+)", t)
                if not m or num(m.group(1)) < min_fk: errs.append("Festkurs im Dialog zu niedrig")
                m = re.search(r"Grundeinsatz:? ?(\d+,\d{2})", t)
                if not m or abs(num(m.group(1)) - stake) > 0.001: errs.append("Grundeinsatz falsch")
                m = re.search(r"Wettanzahl:? ?(\d+)", t)
                if not m or m.group(1) != "1": errs.append("Wettanzahl != 1")
                if errs:
                    pg.screenshot(path=f"{OUT}/{tag}_abbruch.png"); raise Skip("Dialog: " + "; ".join(errs))
                pg.screenshot(path=f"{OUT}/{tag}_dialog.png")
                if not LIVE:
                    kasse.abbuchen(stake); print(f"DRY-RUN: nicht bestätigt (Rest gerechnet {kasse.rest:.2f})"); continue
                dlg.get_by_role("button", name=re.compile("Wettabgabe bestätigen")).click()
                try: pg.get_by_text("Vielen Dank für Ihre Wette").first.wait_for(timeout=20000)
                except Exception:
                    print("WARNUNG: keine Bestätigung gesehen, NICHT erneut ausführen, Tickets prüfen"); sys.exit(3)
                bt_txt = norm(pg.locator("body").inner_text())
                mt = re.search(r"Ticket (\d+)", bt_txt)
                kasse.abbuchen(stake)
                print(f"PLATZIERT {bt['name']}: Ticket {mt.group(1) if mt else '?'}")
                pg.screenshot(path=f"{OUT}/{tag}_bestaetigung.png")
            except Skip as e:
                print(f"{bt['name']}: ABBRUCH: {e}")
        pg.reload(wait_until="networkidle")
        try: print(f"Guthaben danach: {balance():.2f}")
        except Skip: print(f"Guthaben danach: nicht lesbar (gerechnet {kasse.rest:.2f})")
        b.close()
        if kasse.zu:
            print("ENDE: Guthaben reichte nicht für alle Tipps. Übrige NICHT nachholen, KEINE Einzahlung."); sys.exit(2)


if __name__ == "__main__":
    main()
