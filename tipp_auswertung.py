"""Auswertung der Tipps aus dem Skill „rennkarten-durchgang“ gegen die Ergebnisse – Grundlage, um den Skill zu verbessern.

Eingang (alles in <BASE>):
* `tipps/*.md` (oder .json/.txt): die Ausgabe von Claude je Renntag. Gelesen wird der Protokoll-Block
  (```json {"tipps": [...]}``` mit race_id, no, p, stufe, mq, sicherheit, eingepreist, angles, fk, value, siehe Skill C2;
  fk = Festkurs und value = p × fk − 1 werden nach der Analyse nachgetragen).
  Ältere Dateien ohne Block: Ersatz aus den Markdown-Tabellen („## Rennen N“, Zeilen „| #Nr Name | … |“).
* `racecards/racecard_JJJJMMTT_claude.json`: Prognose-Chance p_prog und Prognose-Rang je Starter.
* `parquet/pmu_runners/JJJJMMTT.parquet`: Einlauf und Endquote; `parquet/pmu_dividends/…`: Sieg-Dividende.

Ausgabe: laufendes Protokoll `auswertung/tipps_protokoll.parquet` (+ .csv) und ein Bericht:
Treffsicherheit (Claude gegen Prognose), Siege/Plätze je Stufe, je Angle-Typ und je Prognose-Rang,
Wett-Ergebnis zur Mindestquote (gewettet, wenn die Endquote die Mindestquote erreicht).

Colab:
    import tipp_auswertung as ta
    erg = ta.run(BASE)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

TIPP_ORDNER = "tipps"
PLATZ_GRENZE = 7                 # bis so viele Starter Platz = 1.–2., sonst 1.–3. (wie racecard)
KANDIDAT = {"+", "++"}
ABWERTUNG = {"−", "−−", "-", "--"}

BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
ZEILE = re.compile(r"^\|\s*#(\d+)\s+([^|]+?)\s*\|[^|]*\|\s*(\d+(?:[.,]\d+)?)\s*%[^|]*\|[^|]*\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+?)\s*\|")


# --------------------------------------------------------------------------
# Tipps lesen
# --------------------------------------------------------------------------
def _stufe(s: str) -> str:
    s = (s or "").strip().split()[0] if (s or "").strip() else ""
    return s.replace("--", "−−").replace("-", "−") if s and set(s) <= {"-", "−"} else s


def _zahl(s) -> float | None:
    m = re.match(r"\s*(\d+(?:[.,]\d+)?)", str(s or ""))
    return float(m[1].replace(",", ".")) if m else None


def _aus_tabellen(text: str) -> list[dict]:
    """Ersatz für Dateien ohne Protokoll-Block: Datum/Réunion aus der Überschrift, Rennen aus „## Rennen N“."""
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4}).*?R[ée]union\s+(\d+)", text)
    if not m:
        return []
    tag, reunion = f"{m[3]}{int(m[2]):02d}{int(m[1]):02d}", int(m[4])
    out = []
    for blk in re.split(r"\n##\s+Rennen\s+", text)[1:]:
        rn = int(re.match(r"\d+", blk)[0])
        for zeile in blk.splitlines():
            z = ZEILE.match(zeile)
            if z:
                out.append({"race_id": f"{tag}R{reunion}C{rn}", "no": int(z[1]), "horse": z[2].strip(),
                            "p": float(z[3].replace(",", ".")) / 100, "mq": _zahl(z[4]), "stufe": _stufe(z[5]),
                            "angles": None, "quelle": "tabelle"})
    return out


def tipps_aus_text(text: str) -> pd.DataFrame:
    zeilen = []
    for b in BLOCK.findall(text):
        try:
            j = json.loads(b)
        except ValueError:
            continue
        for t in j.get("tipps") or []:
            zeilen.append({**t, "quelle": "block"})
    if not zeilen:
        zeilen = _aus_tabellen(text)
    df = pd.DataFrame(zeilen)
    if df.empty:
        return df
    df["no"] = pd.to_numeric(df["no"], errors="coerce").astype("Int64")
    df["p"] = pd.to_numeric(df["p"], errors="coerce")
    df["p"] = np.where(df["p"] > 1, df["p"] / 100, df["p"])           # 26 statt 0,26
    df["mq"] = pd.to_numeric(df.get("mq"), errors="coerce")
    # Festkurs (fk) und value (= p × fk − 1) werden nachgetragen; fehlt value, wird es aus fk gerechnet
    df["fk"] = pd.to_numeric(df["fk"], errors="coerce") if "fk" in df else np.nan
    df["value"] = pd.to_numeric(df["value"], errors="coerce") if "value" in df else np.nan
    df["value"] = df["value"].fillna(df["p"] * df["fk"] - 1)
    df["stufe"] = df["stufe"].map(_stufe)
    return df


def laden_tipps(base: Path) -> pd.DataFrame:
    ordner = Path(base) / TIPP_ORDNER
    teile = []
    for f in sorted(ordner.glob("*")) if ordner.exists() else []:
        if f.suffix.lower() not in (".md", ".json", ".txt"):
            continue
        df = tipps_aus_text(f.read_text(encoding="utf-8", errors="replace"))
        if len(df):
            teile.append(df.assign(datei=f.name, stand=f.stat().st_mtime))
    if not teile:
        return pd.DataFrame()
    t = pd.concat(teile, ignore_index=True).sort_values("stand")
    return t.drop_duplicates(["race_id", "no"], keep="last").reset_index(drop=True)   # neueste Datei gilt


# --------------------------------------------------------------------------
# Prognose und Ergebnis
# --------------------------------------------------------------------------
def _prognose(base: Path, tag: str) -> pd.DataFrame:
    f = Path(base) / "racecards" / f"racecard_{tag}_claude.json"
    if not f.exists():
        return pd.DataFrame()
    d = json.loads(f.read_text(encoding="utf-8"))
    z = []
    for rid, r in (d.get("races") or {}).items():
        for x in r.get("runners") or []:
            z.append({"race_id": rid, "no": x.get("no"), "p_prog": x.get("p_prog"),
                      "prog_rang": ((x.get("prono") or {}).get("sel") or {}).get("rank"),
                      "typ": r.get("type"), "horse_karte": x.get("horse")})
    return pd.DataFrame(z)


def _ergebnis(base: Path, tag: str) -> pd.DataFrame:
    f = Path(base) / "parquet" / "pmu_runners" / f"{tag}.parquet"
    fd = Path(base) / "parquet" / "pmu_dividends" / f"{tag}.parquet"
    if not f.exists():
        return _ergebnis_dividenden(fd)
    r = pd.read_parquet(f)
    r = r.assign(no=pd.to_numeric(r["saddle_no"], errors="coerce"),
                 pos=pd.to_numeric(r.get("finish_pos"), errors="coerce"),
                 odds=pd.to_numeric(r.get("odds_final"), errors="coerce"))
    r["starter"] = r.groupby("race_id")["pos"].transform("count")
    r["W"] = (r["pos"] == 1).astype(int)
    r["P"] = (r["pos"] <= np.where(r["starter"] <= PLATZ_GRENZE, 2, 3)).astype(int)
    out = r[["race_id", "no", "pos", "odds", "W", "P"]].drop_duplicates(["race_id", "no"])
    if fd.exists():                                   # Sieg-Dividende (Toto) für den Sieger
        d = pd.read_parquet(fd)
        d = d[d["bet_type"] == "SIMPLE_GAGNANT"].assign(no=lambda x: pd.to_numeric(x["combination"], errors="coerce"))
        out = out.merge(d[["race_id", "no", "dividend_eur_per_1eur"]].rename(columns={"dividend_eur_per_1eur": "div"}),
                        on=["race_id", "no"], how="left")
    else:
        out["div"] = np.nan
    return out


def _ergebnis_dividenden(fd: Path) -> pd.DataFrame:
    """Ersatz ohne pmu_runners: Sieger und Platzierte aus den Dividenden (Sieg, Platz); Endquote fehlt dann."""
    if not fd.exists():
        return pd.DataFrame()
    d = pd.read_parquet(fd).assign(no=lambda x: pd.to_numeric(x["combination"], errors="coerce"))
    s = d[d["bet_type"] == "SIMPLE_GAGNANT"][["race_id", "no", "dividend_eur_per_1eur"]].rename(
        columns={"dividend_eur_per_1eur": "div"}).assign(W=1)
    pl = d[d["bet_type"] == "SIMPLE_PLACE"][["race_id", "no"]].assign(P=1)
    out = pl.merge(s, on=["race_id", "no"], how="outer")
    out["W"], out["P"] = out["W"].fillna(0).astype(int), out["P"].fillna(1).astype(int)
    return out.assign(pos=np.where(out["W"] == 1, 1, np.nan), odds=np.nan, nur_dividenden=True)


def protokoll(base: Path) -> pd.DataFrame:
    t = laden_tipps(base)
    if t.empty:
        return t
    t["tag"] = t["race_id"].str[:8]
    teile = []
    for tag, g in t.groupby("tag"):
        e, pr = _ergebnis(base, tag), _prognose(base, tag)
        if e.empty:
            continue                                  # Ergebnis noch nicht geholt
        if "nur_dividenden" in e:                     # nur Platzierte bekannt: übrige Starter = unplatziert
            g = g[g["race_id"].isin(e["race_id"])].merge(e.drop(columns="nur_dividenden"), on=["race_id", "no"], how="left")
            g[["W", "P"]] = g[["W", "P"]].fillna(0).astype(int)
        else:
            g = g.merge(e, on=["race_id", "no"], how="inner")
        g = g.merge(pr, on=["race_id", "no"], how="left") if len(pr) else g.assign(p_prog=np.nan, prog_rang=np.nan, typ=None)
        teile.append(g)
    if not teile:
        return pd.DataFrame()
    p = pd.concat(teile, ignore_index=True)
    p = p[p["race_id"].isin(p.loc[p["W"] == 1, "race_id"])]            # nur Rennen mit Sieger
    return p.drop(columns=["stand"], errors="ignore")


# --------------------------------------------------------------------------
# Bericht
# --------------------------------------------------------------------------
def _gruppe(g: pd.DataFrame) -> pd.Series:
    erw, erw_p = g["p"].sum(), g["p_prog"].sum()
    return pd.Series({"n": len(g), "siege": int(g["W"].sum()), "erw_claude": round(erw, 1),
                      "erw_prognose": round(erw_p, 1), "ae_claude": round(g["W"].sum() / erw, 2) if erw else np.nan,
                      "plaetze": int(g["P"].sum()), "platzquote": round(g["P"].mean(), 2)})


def treffsicherheit(p: pd.DataFrame) -> pd.DataFrame:
    """Log-Loss des Siegers und Brier je Rennen: Claude gegen Prognose (nur Rennen, in denen beide vollständig sind)."""
    ok = p.groupby("race_id").filter(lambda g: g["p"].notna().all() and g["p_prog"].notna().all())
    if ok.empty:
        return pd.DataFrame()
    z = []
    for name, c in [("Claude", "p"), ("Prognose", "p_prog")]:
        q = ok[c] / ok.groupby("race_id")[c].transform("sum")          # je Rennen auf 100 % normiert
        sieger = q[ok["W"] == 1].clip(lower=1e-3)
        z.append({"quelle": name, "rennen": ok["race_id"].nunique(), "log_loss": round(float(-np.log(sieger).mean()), 3),
                  "brier": round(float(((q - ok["W"]) ** 2).groupby(ok["race_id"]).sum().mean()), 4)})
    return pd.DataFrame(z)


def wetten(p: pd.DataFrame) -> pd.DataFrame:
    """Kandidaten (+/++) zur Mindestquote: gewettet, wenn die Endquote sie erreicht (Sieg = Toto-Dividende, sonst Endquote).
    Mit nachgetragenem Festkurs (fk) zusätzlich: gewettet zum Festkurs, wenn er die Mindestquote erreicht."""
    k = p[p["stufe"].isin(KANDIDAT) & p["mq"].notna()].copy()
    if k.empty:
        return pd.DataFrame()
    k["quote"] = k["div"].where(k["div"].notna(), k["odds"])
    z = []
    ohne = k["odds"].isna().sum()
    for name, m in [("alle Kandidaten", pd.Series(True, index=k.index)),
                    (f"nur Endquote ≥ Mindestquote{f' ({ohne} ohne Endquote)' if ohne else ''}", k["odds"] >= k["mq"])]:
        g = k[m]
        gewinn = (g["W"] * g["quote"]).sum() - len(g)
        z.append({"wetten": name, "n": len(g), "siege": int(g["W"].sum()), "einsatz": len(g),
                  "ergebnis": round(float(gewinn), 2), "roi": round(float(gewinn / len(g)), 2) if len(g) else np.nan})
    if "fk" in k and k["fk"].notna().any():
        for name, m in [("Festkurs ≥ Mindestquote (zum Festkurs)", k["fk"] >= k["mq"]),
                        ("Festkurs mit value > 0 (zum Festkurs)", k["value"] > 0)]:
            g = k[m & k["fk"].notna()]
            gewinn = (g["W"] * g["fk"]).sum() - len(g)
            z.append({"wetten": name, "n": len(g), "siege": int(g["W"].sum()), "einsatz": len(g),
                      "ergebnis": round(float(gewinn), 2), "roi": round(float(gewinn / len(g)), 2) if len(g) else np.nan})
    return pd.DataFrame(z)


def _je(df: pd.DataFrame, keys) -> pd.DataFrame:
    out = df.groupby(keys, observed=True).apply(_gruppe, include_groups=False).reset_index()
    return out.astype({"n": int, "siege": int, "plaetze": int})


def bericht(p: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {"treffsicherheit": treffsicherheit(p)}
    out["stufe"] = _je(p, "stufe")
    a = p.assign(angle=p["angles"].map(lambda v: list(v) if isinstance(v, (list, tuple, np.ndarray)) and len(v) else None))
    a = a.dropna(subset=["angle"]).explode("angle")
    if len(a):
        a["rolle"] = np.select([a["stufe"].isin(KANDIDAT), a["stufe"].isin(ABWERTUNG)], ["Kandidat", "Abwertung"], "neutral")
        out["angle"] = _je(a, ["angle", "rolle"])
    rang = pd.cut(pd.to_numeric(p["prog_rang"], errors="coerce"), [0, 1, 3, 5, 99], labels=["Favorit", "2–3", "4–5", "6+"])
    out["prognose_rang"] = _je(p.assign(rang=rang), "rang")
    if p["typ"].notna().any():
        k = p[p["stufe"].isin(KANDIDAT) & p["typ"].notna()]
        out["rennart"] = _je(k, "typ") if len(k) else None
    out["wetten"] = wetten(p)
    return out


def run(base: Path, *, zeigen: bool = True) -> dict[str, pd.DataFrame]:
    base = Path(base)
    p = protokoll(base)
    if p.empty:
        print(f"Keine auswertbaren Tipps: Claude-Ausgaben nach {base / TIPP_ORDNER} legen; "
              "das Ergebnis eines Renntags gibt es ab dem Folgetag (Abschnitt 2 des Notebooks).")
        return {}
    ziel = base / "auswertung"
    ziel.mkdir(parents=True, exist_ok=True)
    p.to_parquet(ziel / "tipps_protokoll.parquet", index=False)
    p.drop(columns=["angles"], errors="ignore").assign(
        angles=p["angles"].map(lambda v: ",".join(v) if isinstance(v, (list, tuple, np.ndarray)) else "")
    ).to_csv(ziel / "tipps_protokoll.csv", index=False)
    erg = bericht(p)
    if zeigen:
        print(f"{p['race_id'].nunique()} Rennen an {p['race_id'].str[:8].nunique()} Tagen, {len(p)} Starter, "
              f"{int(p['stufe'].isin(KANDIDAT).sum())} Kandidaten (+/++); "
              f"{int((p['quelle'] == 'block').sum())} Starter mit Protokoll-Block (Angle-Typen)")
        titel = {"treffsicherheit": "Treffsicherheit (kleiner = besser)", "stufe": "Je Angle-Stufe",
                 "angle": "Je Angle-Typ", "prognose_rang": "Je Prognose-Rang", "rennart": "Kandidaten je Rennart",
                 "wetten": "Wett-Ergebnis Kandidaten (1 € je Wette)"}
        with pd.option_context("display.width", 200, "display.max_rows", 300):
            for k, df in erg.items():
                if df is not None and len(df):
                    print(f"\n{titel.get(k, k)}\n{df.to_string(index=False)}")
        print(f"\nProtokoll: {ziel / 'tipps_protokoll.parquet'}")
    return erg
