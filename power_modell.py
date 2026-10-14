"""Power-Modell: ein einmal trainiertes LightGBM-Modell sagt den Platzanteil jedes Starters voraus
(pos_perc = (Starter − Platz) / (Starter − 1), nicht im Ziel = 0). Die Race Card zeigt daraus „Power“ =
100 + 10 × z der Vorhersage im heutigen Feld (100 = Feldschnitt).

Merkmale entstehen für jedes Rennen nur aus Läufen VOR dem Renntag (merkmale). Dieselbe Funktion rechnet im Training
über die ganze Historie und in der Karte für die heutigen Starter – Training und Vorhersage passen so zusammen.
Bewusst nicht drin: heutige PMU-Prognose und heutige Quote (Power ist eine eigene, marktunabhängige Meinung).
Fehlende Werte bleiben NaN; LightGBM entscheidet je Baum selbst, wohin sie gehen.

Merkmale (Gruppen wie in der Karte):
  Rennen      Typ, Starter, Altersklasse, Distanz und Distanzgruppe, Bodengruppe, Tempo-Szenario (Anzahl Führende, Ø frühe
              Position des Feldes)
  Pferd       Alter, Geschlecht, €/Lauf 365 Tage, Gewicht, Rating (roh und bereinigt), Tage seit dem letzten Lauf, Läufe,
              RTR / ARR / TR / ΔL600 A / ΔB200 A wie die Kacheln, Duell-Rang (wie die Kachel), Startbox (Ø Platzanteil der
              Box auf der Konfiguration), Laufstil (Ø frühe Position der letzten 5 Läufe, auch relativ zum Feld)
  Vorlieben   schon gewonnen / platziert auf Kurs, Distanzgruppe, Bodengruppe; beste Distanz-/Bodengruppe des Pferdes
              (Platzanteil, €/Lauf, A/E Platz)
  Verbindung  Trainer, Jockey, Besitzer, Züchter: Score aus A/E Platz, Platzanteil und €/Lauf (365 Tage, je 100 = Schnitt)
  Abstammung  Vater, Muttervater: Score, €/Lauf+, Valeur der 3-Jährigen+, beste Distanz-/Bodengruppe (ohne 2-Jährige bei
              der Distanz)
  Form        letzte drei Läufe: Klasse (Ø Valeur, Rennstärke), Längen zurück, Platzanteil, gleicher Boden / gleiche
              Distanzgruppe wie heute, ARR und TR (heutiges Gewicht), Finish-Index, ±800, Weg m, Endquote, Tage davor,
              Gegner-Score (wie liefen die Gegner danach gegen ihre Quote), direkter Vergleich mit heutigen Gegnern

Colab:
    import power_modell as pm
    erg = pm.trainieren(BASE)        # einmalig (~1 h): Merkmale, Prüfung auf den letzten 25 % der Tage, Modell speichern
    erg = pm.trainieren(BASE, ab="2024-01-01")   # danach schnell: Merkmale aus BASE/modelle/merkmale.parquet,
                                                 # lernen/prüfen nur ab dem Datum (z. B. ab da, wo es Tracking gibt)
Die Race Card (racecard.run) lädt das Modell danach aus BASE/modelle/ und ersetzt den bisherigen Power-Wert.
"""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

import racecard as rc
import timeform_ratings

MODELL_ORDNER = "modelle"
MODELL_DATEI = "power_modell.txt"
META_DATEI = "power_modell.json"
MERKMAL_DATEI = "merkmale.parquet"   # Zwischenspeicher der Merkmale (Bauen dauert ~30 min)
MERKMAL_VERSION = 2                   # hochzählen, wenn merkmale() neue Spalten bekommt -> Zwischenspeicher wird neu gebaut
# Merkmale, die zusätzlich relativ zum heutigen Feld eingehen: Rang im Feld (0..1) und Abstand zum Feldschnitt
RELATIV = ["rating_adj", "weight", "epr365", "rtr", "arr", "tr", "f1_pos", "f1_lb", "f1_pm", "f2_pos", "trainer_score",
           "jockey_score", "owner_score", "duel_score", "sire_score"]
RANG_STUFEN = 10            # Lern-Ziel für „rang“: Platzanteil in 11 Stufen (0 … 10)
RANG_GAIN = [round(2 ** (s / 2) - 1, 3) for s in range(RANG_STUFEN + 1)]   # Sieg zählt am meisten, ohne alles andere zu erdrücken
LERN_ANTEIL = 0.75          # zeitlich vorne: lernen; die übrigen Tage: prüfen
FORM_N = 3                  # so viele letzte Läufe als eigene Merkmale
VERB_TAGE = 365             # Verbindungen: Fenster
VERB_K = 10                 # Verbindungs-Score zur 100 hin geschrumpft wie mit so vielen Läufen bei 100
ABST_K = 20                 # dasselbe für Vater/Muttervater
ABST_MIN = 30               # beste Gruppe von Vater/Muttervater erst ab so vielen Läufen in der Gruppe
PFERD_MIN = 2               # beste Gruppe des Pferdes erst ab so vielen Läufen in der Gruppe
KATEGORISCH = ["racetype", "going", "dist_group", "cond_age", "sex"]
LGB_PARAMS = dict(objective="regression", learning_rate=0.03, num_leaves=63, min_data_in_leaf=50, bagging_fraction=0.8,
                  bagging_freq=1, feature_fraction=0.8, lambda_l2=1.0, verbosity=-1)
LGB_RUNDEN = 3000           # höchstens so viele Bäume; Abbruch, wenn sich die Prüfung 100 Runden nicht verbessert
LB_PER_KG = timeform_ratings.LB_PER_KG
REF_KG = timeform_ratings.REF_WEIGHT_KG

# Gruppen für die Treiber im Tooltip der Karte (Präfix der Merkmale -> Anzeige)
GRUPPEN = [("f1_", "letzter Lauf"), ("f2_", "vorletzter Lauf"), ("f3_", "Lauf davor"), ("trainer_", "Trainer"),
           ("jockey_", "Jockey"), ("owner_", "Besitzer"), ("breeder_", "Züchter"), ("sire_", "Vater"),
           ("dam_sire_", "Muttervater"), ("arr", "ARR"), ("tr", "TR"), ("rtr", "RTR"), ("dl600", "ΔL600 A"),
           ("db200", "ΔB200 A"), ("duel", "Duell"), ("box", "Startbox"), ("early", "Laufstil"), ("pace", "Tempo-Szenario"),
           ("won_", "Sieg-Vorlieben"), ("placed_", "Platz-Vorlieben"), ("best_", "beste Gruppe Pferd"),
           ("rating", "Rating"), ("weight", "Gewicht"), ("epr365", "€/Lauf 365"), ("days", "Tage seit Lauf"),
           ("runs", "Läufe"), ("age", "Alter"), ("sex", "Geschlecht"), ("draw", "Startbox")]


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------
def _spalte(h: pd.DataFrame, c: str, standard=np.nan) -> pd.Series:
    return h[c] if c in h else pd.Series(standard, index=h.index)


def _zahl(h: pd.DataFrame, c: str) -> np.ndarray:
    return pd.to_numeric(_spalte(h, c), errors="coerce").to_numpy(dtype=float, copy=True)


def _text(h: pd.DataFrame, c: str) -> np.ndarray:
    return _spalte(h, c, None).astype(object).where(_spalte(h, c, None).notna(), None).to_numpy()


def _going_w(a, b) -> float:
    return rc.going_gewicht(a, b) if a is not None and b is not None else 1.0


def _score(placed, exp, rp, lp, n, g_rp, g_lp) -> float:
    """Score aus A/E Platz, Platzanteil und €/Lauf (log), je 100 = Schnitt; Mittel der vorhandenen Teile."""
    teile = []
    if exp > 0:
        teile.append(100 * placed / exp)
    if n and g_rp:
        teile.append(100 * (rp / n) / g_rp)
    if n and g_lp:
        teile.append(100 * (lp / n) / g_lp)
    return float(np.mean(teile)) if teile else np.nan


def ziel(h: pd.DataFrame) -> pd.Series:
    """Abhängige Variable: Platzanteil, nicht im Ziel = 0; ohne Ergebnis oder Feld < 2: NaN."""
    n = pd.to_numeric(_spalte(h, "n_runners"), errors="coerce")
    rp = pd.to_numeric(_spalte(h, "rel_place"), errors="coerce").fillna(0.0)
    return rp.where(n > 1)


# --------------------------------------------------------------------------
# Merkmale
# --------------------------------------------------------------------------
def merkmale(h: pd.DataFrame, ziel_maske: pd.Series | None = None, heute: pd.Series | None = None,
             duelle: bool = True, log=print) -> pd.DataFrame:
    """Merkmale je Starter aus Läufen vor dem Renntag. h: vorbereitete Historie (racecard.vorbereiten), optional mit
    heutigen Zeilen ohne Ergebnis (heute=True – sie fließen nie in die Historie anderer ein). ziel_maske: nur für diese
    Zeilen ausgeben (Vorgabe: alle). Rückgabe mit dem Index von h."""
    t0 = time.time()
    h = h.copy()
    h["date"] = pd.to_datetime(h["date"])
    heute = (heute.reindex(h.index).fillna(False).astype(bool) if heute is not None
             else pd.Series(False, index=h.index))
    ziel_maske = (ziel_maske.reindex(h.index).fillna(False).astype(bool) if ziel_maske is not None
                  else pd.Series(True, index=h.index))
    h = h.sort_values(["date", "race_id", "saddle_no"], kind="stable")
    idx = h.index.to_numpy()
    zm, hm = ziel_maske.loc[idx].to_numpy(), heute.loc[idx].to_numpy()
    n = len(h)

    # Grundspalten als Arrays (Position = Reihenfolge nach Datum)
    tag = (h["date"] - pd.Timestamp("2000-01-01")).dt.days.to_numpy()
    rid = h["race_id"].astype(str).to_numpy()
    hid = h["horse_id"].astype(str).to_numpy()
    dist, gew = _zahl(h, "distance_m"), _zahl(h, "weight_kg")
    going, dgrp, course = _text(h, "going_pmu"), _text(h, "dist_group"), _text(h, "course_key")
    fpos = _zahl(h, "finish_pos")
    nrun = pd.to_numeric(_spalte(h, "n_runners"), errors="coerce")
    nrun = nrun.fillna(h.groupby("race_id")["race_id"].transform("count")).to_numpy(dtype=float)
    rp0 = np.where(hm, np.nan, ziel(h).to_numpy(dtype=float))
    prize = np.where(hm, np.nan, _zahl(h, "prize_won"))
    lp = np.log1p(np.clip(np.nan_to_num(prize, nan=0.0), 0, None))
    lp[hm] = np.nan
    placed = np.where(hm, np.nan, _zahl(h, "placed"))
    expp = np.where(hm, np.nan, _zahl(h, "exp_place"))
    won = np.where(hm, np.nan, _zahl(h, "won"))
    ausg = _spalte(h, "ausgeritten", False).fillna(False).astype(bool).to_numpy()
    trk = _spalte(h, "tracking", False).fillna(False).astype(bool).to_numpy()
    trcap = _zahl(h, "tr_gedeckelt")
    werte = {c: _zahl(h, c) for c in ["arr", "tr", "rtr", "d_L600_A", "d_B200_A", "early_pct", "cls_val", "cls_epr_kl",
                                       "lengths_behind", "fi_adj", "pos_gain_800_finish", "weg_med", "odds_final",
                                       "odds_rank", "valeur", "age", "draw"]}
    for c in ["arr", "tr", "rtr", "d_L600_A", "d_B200_A", "early_pct", "fi_adj", "pos_gain_800_finish", "weg_med",
              "lengths_behind"]:
        werte[c][hm] = np.nan                                     # heutige Zeilen haben keine Laufwerte
    lb = np.where(fpos == 1, 0.0, werte["lengths_behind"])
    F: dict[str, np.ndarray] = {}

    def feld(name, wert=np.nan):
        F[name] = np.full(n, wert, dtype=float)
        return F[name]

    # ---- Rennen und Pferd (heute bekannt) ---------------------------------------------------------------------
    F["n_runners"], F["distance_m"], F["weight"] = nrun, dist, gew
    F["rating"] = werte["valeur"]
    F["rating_adj"] = werte["valeur"] - gew + rc.GEWICHT_REF
    F["age"], F["draw"] = werte["age"], werte["draw"]
    F["draw_rel"] = werte["draw"] / nrun
    kat = {"racetype": _text(h, "racetype"), "going": going, "dist_group": dgrp,
           "cond_age": _text(h, "conditions_age"),
           "sex": np.array([str(s)[:1].upper() if s is not None else None for s in _text(h, "sex")], dtype=object)}

    # ---- je Pferd: Kacheln, Form, Vorlieben ----------------------------------------------------------------------
    for c in ["runs", "days", "rtr", "arr", "tr", "dl600", "db200", "early", "epr365",
              "won_course", "won_dist", "won_going", "placed_course", "placed_dist", "placed_going", "best_dist", "best_going"]:
        feld(c)
    for k in range(1, FORM_N + 1):
        for c in ["val", "epr", "lb", "pos", "same_going", "same_dist", "arr", "tr", "fi", "g800", "weg", "odds", "orank",
                  "pm", "tage", "gegner", "duell"]:
            feld(f"f{k}_{c}")
    # nächster Start jedes Laufs (für den Gegner-Score): Datum und Urteil gegen den Quotenrang
    ord_h = np.lexsort((tag, hid))
    naechst_tag, naechst_urteil = np.full(n, np.nan), np.full(n, np.nan)
    for a, b in zip(ord_h[:-1], ord_h[1:]):
        if hid[a] == hid[b] and not hm[b]:
            naechst_tag[a] = tag[b]
            if not np.isnan(fpos[b]) and not np.isnan(werte["odds_rank"][b]):
                naechst_urteil[a] = np.sign(werte["odds_rank"][b] - fpos[b])
    rennen_pos = pd.Series(np.arange(n)).groupby(rid).apply(lambda s: s.to_numpy()).to_dict()
    # Quote vergleichbar über Feldgrößen: Quotenrang relativ (0 = Favorit … 1 = Außenseiter) und Marktchance
    # (1/Quote, im Rennen auf Summe 1 gebracht)
    inv = pd.Series(np.where(werte["odds_final"] > 1, 1.0 / werte["odds_final"], np.nan))
    p_markt = (inv / inv.groupby(rid).transform("sum")).to_numpy(dtype=float)
    o_rang = inv.groupby(rid).rank(ascending=False, method="average")
    o_n = inv.notna().groupby(rid).transform("sum")
    o_rel = ((o_rang - 1) / (o_n - 1)).where(o_n > 1).to_numpy(dtype=float)
    feld_heute = {r: set(hid[p]) for r, p in rennen_pos.items()}
    g_lp = float(np.nanmean(lp[~hm])) if (~hm).any() else np.nan

    def gew_schnitt(vor, spalte, i, gueltig, prior=0.0):
        """Kachel-Schnitt: letzte 5 gültige Läufe, Gewicht Distanz × Boden zu heute (racecard.lauf_gewichte)."""
        ws, vs = [], []
        for j in vor:
            if gueltig(j) and not np.isnan(spalte[j]):
                wd = 1.0 / (1.0 + abs(dist[j] - dist[i]) / rc.SCHNITT_DIST_M) if not (np.isnan(dist[j]) or np.isnan(dist[i])) else 1.0
                ws.append(wd * _going_w(going[j], going[i]))
                vs.append(spalte[j])
                if len(vs) == rc.SCHNITT_LAEUFE:
                    break
        if not vs:
            return np.nan
        ws, vs = np.array(ws), np.array(vs)
        return float((ws * vs).sum() / (ws.sum() + prior))

    def gruppen_best(vor, schluessel, heute_k):
        """1, wenn die heutige Gruppe die beste des Pferdes ist (Score aus A/E Platz, Platzanteil, €/Lauf), sonst 0."""
        if heute_k is None:
            return np.nan
        g: dict = {}
        for j in vor:
            k = schluessel[j]
            if k is None:
                continue
            s = g.setdefault(k, [0, 0.0, 0.0, 0.0, 0.0])
            s[0] += 1
            s[1] += np.nan_to_num(placed[j])
            s[2] += np.nan_to_num(expp[j])
            s[3] += np.nan_to_num(rp0[j])
            s[4] += np.nan_to_num(lp[j])
        sc = {k: _score(s[1], s[2], s[3], s[4], s[0], 0.5, g_lp) for k, s in g.items() if s[0] >= PFERD_MIN}
        sc = {k: v for k, v in sc.items() if not np.isnan(v)}
        if heute_k not in sc:
            return np.nan
        return float(sc[heute_k] >= max(sc.values()))

    pferde = {}
    for p in ord_h:
        pferde.setdefault(hid[p], []).append(p)
    mit_ziel = set(hid[zm])
    for pid, laeufe in pferde.items():
        if pid not in mit_ziel:
            continue
        for pos_i, i in enumerate(laeufe):
            if not zm[i]:
                continue
            vor = [j for j in reversed(laeufe[:pos_i]) if tag[j] < tag[i] and not hm[j]]   # neueste zuerst
            F["runs"][i] = len(vor)
            if not vor:
                continue
            F["days"][i] = tag[i] - tag[vor[0]]
            ok = lambda j: not ausg[j]
            a = gew_schnitt(vor, werte["arr"], i, ok)
            F["arr"][i] = a - gew[i] + rc.GEWICHT_REF
            t = gew_schnitt(vor, werte["tr"], i, lambda j: not ausg[j] and trcap[j] != 1)
            F["tr"][i] = t - (gew[i] - REF_KG) * LB_PER_KG if not np.isnan(gew[i]) else t
            zuv = lambda j: trk[j] and not ausg[j]
            F["dl600"][i] = gew_schnitt(vor, werte["d_L600_A"], i, zuv, rc.SCHNITT_PRIOR)
            F["db200"][i] = gew_schnitt(vor, werte["d_B200_A"], i, zuv, rc.SCHNITT_PRIOR)
            rtr_v = [werte["rtr"][j] for j in vor if not np.isnan(werte["rtr"][j])]
            if rtr_v:
                F["rtr"][i] = rtr_v[0] - gew[i] + rc.GEWICHT_REF
            fr = [werte["early_pct"][j] for j in vor if not np.isnan(werte["early_pct"][j])][:rc.STIL_LAEUFE]
            if fr:
                F["early"][i] = float(np.mean(fr))
            j365 = [prize[j] for j in vor if tag[i] - tag[j] <= 365]
            if j365:
                F["epr365"][i] = float(np.mean(j365))
            sieg = [j for j in vor if won[j] == 1]
            platz = [j for j in vor if placed[j] == 1]
            for name, menge in (("won", sieg), ("placed", platz)):
                F[f"{name}_course"][i] = float(any(course[j] == course[i] for j in menge)) if course[i] is not None else np.nan
                F[f"{name}_dist"][i] = float(any(dgrp[j] == dgrp[i] for j in menge)) if dgrp[i] is not None else np.nan
                F[f"{name}_going"][i] = float(any(going[j] == going[i] for j in menge)) if going[i] is not None else np.nan
            F["best_dist"][i] = gruppen_best(vor, dgrp, dgrp[i])
            F["best_going"][i] = gruppen_best(vor, going, going[i])
            gegner_heute = feld_heute.get(rid[i], set()) - {hid[i]}
            for k, j in enumerate(vor[:FORM_N], 1):
                F[f"f{k}_val"][i], F[f"f{k}_epr"][i] = werte["cls_val"][j], werte["cls_epr_kl"][j]
                F[f"f{k}_lb"][i], F[f"f{k}_pos"][i] = lb[j], rp0[j]
                F[f"f{k}_same_going"][i] = float(going[j] == going[i]) if going[i] is not None and going[j] is not None else np.nan
                F[f"f{k}_same_dist"][i] = float(dgrp[j] == dgrp[i]) if dgrp[i] is not None and dgrp[j] is not None else np.nan
                F[f"f{k}_arr"][i] = werte["arr"][j] - gew[i] + rc.GEWICHT_REF
                F[f"f{k}_tr"][i] = werte["tr"][j] - (gew[i] - REF_KG) * LB_PER_KG if not np.isnan(gew[i]) else werte["tr"][j]
                F[f"f{k}_fi"][i], F[f"f{k}_g800"][i] = werte["fi_adj"][j], werte["pos_gain_800_finish"][j]
                F[f"f{k}_weg"][i], F[f"f{k}_odds"][i] = werte["weg_med"][j], werte["odds_final"][j]
                F[f"f{k}_orank"][i], F[f"f{k}_pm"][i] = o_rel[j], p_markt[j]
                F[f"f{k}_tage"][i] = tag[i] - tag[j]
                feld_j = rennen_pos.get(rid[j], np.array([], dtype=int))
                andere = feld_j[hid[feld_j] != hid[j]]
                if len(andere):                                    # Gegner danach: nur Starts vor heute zählen
                    v = naechst_urteil[andere][naechst_tag[andere] < tag[i]]
                    v = v[~np.isnan(v)]
                    if len(v):
                        F[f"f{k}_gegner"][i] = float(v.mean())
                    hg = andere[np.isin(hid[andere], list(gegner_heute))] if gegner_heute else andere[:0]
                    if len(hg) and not np.isnan(rp0[j]):           # heutige Gegner in diesem Rennen: Anteil geschlagen
                        F[f"f{k}_duell"][i] = float(np.mean(rp0[hg] < rp0[j]))
    log(f"  Pferde-Merkmale: {time.time() - t0:.0f} s")

    # ---- Tempo-Szenario je Rennen aus dem Laufstil der Starter --------------------------------------------------
    fr = pd.Series(F["early"])
    F["pace_front"] = fr.le(rc.TEMPOMACHER).groupby(rid).transform("sum").where(zm).to_numpy(dtype=float)
    F["pace_early_mean"] = fr.groupby(rid).transform("mean").to_numpy(dtype=float)
    F["early_rel"] = F["early"] - F["pace_early_mean"]

    # ---- Tag für Tag: Verbindungen, Abstammung, Startbox (Stand vor dem Renntag) --------------------------------
    t1 = time.time()
    rollen = {r_: _text(h, r_ + "_key") for r_ in ("trainer", "jockey", "owner", "breeder")}
    linien = {l_: _text(h, l_ + "_key") for l_ in ("sire", "dam_sire")}
    konfig = _text(h, "konfig")
    for r_ in rollen:
        feld(f"{r_}_score"), feld(f"{r_}_runs")
    for l_ in linien:
        for c in ("score", "epr", "val3", "runs", "best_dist", "best_going"):
            feld(f"{l_}_{c}")
    feld("box_mean"), feld("box_runs")
    verb = {r_: {} for r_ in rollen}                     # Schlüssel -> [deque, n, placed, exp, rp, lp]
    glob = [deque(), 0, 0.0, 0.0]                        # 365-Tage-Schnitt aller Läufe: n, rp, lp
    abst = {l_: {} for l_ in linien}                     # Schlüssel -> [n, placed, exp, rp, lp, n3, val3]
    abst_kat = {l_: {"dist": {}, "going": {}} for l_ in linien}   # Schlüssel -> Gruppe -> [n, placed, exp, rp, lp]
    pop_kat = {"dist": {}, "going": {}}                  # Gruppe -> [n, rp, lp] aller Läufe
    g_all = [0, 0.0, 0.0, 0, 0.0]                        # alle Läufe: n, rp, lp, n3, val3
    box: dict = {}
    alter = werte["age"]
    tage_pos = pd.Series(np.arange(n)).groupby(tag).apply(lambda s: s.to_numpy())

    def kat_score(s, pk):
        if not s[0] or not pk or not pk[0]:
            return np.nan
        return _score(s[1], s[2], s[3], s[4], s[0], pk[1] / pk[0], pk[2] / pk[0])

    for d_, pos in tage_pos.items():
        while glob[0] and glob[0][0][0] < d_ - VERB_TAGE:     # globales Fenster nachziehen
            _, rp_, lp_ = glob[0].popleft()
            glob[1] -= 1; glob[2] -= rp_; glob[3] -= lp_
        g_rp = glob[2] / glob[1] if glob[1] else np.nan
        g_lpw = glob[3] / glob[1] if glob[1] else np.nan
        for i in pos[zm[pos]]:
            for r_, keys in rollen.items():
                s = verb[r_].get(keys[i])
                if s is None:
                    continue
                q = s[0]
                while q and q[0][0] < d_ - VERB_TAGE:
                    _, pl_, ex_, rp_, lp_ = q.popleft()
                    s[1] -= 1; s[2] -= pl_; s[3] -= ex_; s[4] -= rp_; s[5] -= lp_
                if s[1]:
                    sc = _score(s[2], s[3], s[4], s[5], s[1], g_rp, g_lpw)
                    F[f"{r_}_score"][i] = (s[1] * sc + VERB_K * 100) / (s[1] + VERB_K) if not np.isnan(sc) else np.nan
                    F[f"{r_}_runs"][i] = s[1]
            ga_rp = g_all[1] / g_all[0] if g_all[0] else np.nan
            ga_lp = g_all[2] / g_all[0] if g_all[0] else np.nan
            for l_, keys in linien.items():
                s = abst[l_].get(keys[i])
                if s is None or not s[0]:
                    continue
                sc = _score(s[1], s[2], s[3], s[4], s[0], ga_rp, ga_lp)
                F[f"{l_}_score"][i] = (s[0] * sc + ABST_K * 100) / (s[0] + ABST_K) if not np.isnan(sc) else np.nan
                F[f"{l_}_epr"][i] = 100 * (s[4] / s[0]) / ga_lp if ga_lp else np.nan
                F[f"{l_}_val3"][i] = 100 * (s[6] / s[5]) / (g_all[4] / g_all[3]) if s[5] and g_all[3] else np.nan
                F[f"{l_}_runs"][i] = s[0]
                for dim, heute_k in (("dist", dgrp[i]), ("going", going[i])):
                    kats = abst_kat[l_][dim].get(keys[i], {})
                    gesamt = sc
                    werte_k = {}
                    for kk, ks in kats.items():
                        if ks[0] >= ABST_MIN:
                            v = kat_score(ks, pop_kat[dim].get(kk))
                            if not np.isnan(v):
                                werte_k[kk] = (ks[0] * v + ABST_K * gesamt) / (ks[0] + ABST_K) if not np.isnan(gesamt) else v
                    if heute_k in werte_k:
                        F[f"{l_}_best_{dim}"][i] = float(werte_k[heute_k] >= max(werte_k.values()))
            bs = box.get((konfig[i], werte["draw"][i]))
            if bs and bs[0]:
                F["box_mean"][i], F["box_runs"][i] = bs[1] / bs[0], bs[0]
        # Tag fertig: Ergebnisse in den Stand übernehmen (heutige Zeilen nie)
        for i in pos[~hm[pos]]:
            pl_, ex_, rp_, lp_ = (np.nan_to_num(placed[i]), np.nan_to_num(expp[i]), np.nan_to_num(rp0[i]),
                                  np.nan_to_num(lp[i]))
            if np.isnan(rp0[i]):
                continue
            glob[0].append((d_, rp_, lp_)); glob[1] += 1; glob[2] += rp_; glob[3] += lp_
            for r_, keys in rollen.items():
                if keys[i] is None:
                    continue
                s = verb[r_].setdefault(keys[i], [deque(), 0, 0.0, 0.0, 0.0, 0.0])
                s[0].append((d_, pl_, ex_, rp_, lp_)); s[1] += 1; s[2] += pl_; s[3] += ex_; s[4] += rp_; s[5] += lp_
            drei = alter[i] == 3 and not np.isnan(werte["valeur"][i])
            g_all[0] += 1; g_all[1] += rp_; g_all[2] += lp_
            if drei:
                g_all[3] += 1; g_all[4] += werte["valeur"][i]
            for dim, kk in (("dist", dgrp[i] if alter[i] != 2 else None), ("going", going[i])):
                if kk is not None:
                    pk = pop_kat[dim].setdefault(kk, [0, 0.0, 0.0])
                    pk[0] += 1; pk[1] += rp_; pk[2] += lp_
            for l_, keys in linien.items():
                if keys[i] is None:
                    continue
                s = abst[l_].setdefault(keys[i], [0, 0.0, 0.0, 0.0, 0.0, 0, 0.0])
                s[0] += 1; s[1] += pl_; s[2] += ex_; s[3] += rp_; s[4] += lp_
                if drei:
                    s[5] += 1; s[6] += werte["valeur"][i]
                for dim, kk in (("dist", dgrp[i] if alter[i] != 2 else None), ("going", going[i])):
                    if kk is not None:
                        ks = abst_kat[l_][dim].setdefault(keys[i], {}).setdefault(kk, [0, 0.0, 0.0, 0.0, 0.0])
                        ks[0] += 1; ks[1] += pl_; ks[2] += ex_; ks[3] += rp_; ks[4] += lp_
            if konfig[i] is not None and not np.isnan(werte["draw"][i]):
                bs = box.setdefault((konfig[i], werte["draw"][i]), [0, 0.0])
                bs[0] += 1; bs[1] += rp_
    log(f"  Verbindungen, Abstammung, Startbox: {time.time() - t1:.0f} s")

    # ---- Duell-Rang wie die Kachel (direkte und indirekte Duelle vor dem Renntag) ------------------------------
    for c in ("duel_score", "duel_rank_rel", "duel_weight"):
        feld(c)
    if duelle:
        import hypothesen_backtest as hb
        t2 = time.time()
        dm = hb.duell_merkmale(h, pd.Series(zm, index=h.index), log_alle=5000 if log else 0)
        dm = dm.reindex(h.index)
        F["duel_score"] = dm["duel_score"].to_numpy(dtype=float)
        F["duel_rank_rel"] = (dm["duel_rank"] / dm["duel_of"]).to_numpy(dtype=float)
        F["duel_weight"] = dm["duel_weight"].to_numpy(dtype=float)
        log(f"  Duelle: {time.time() - t2:.0f} s")

    out = pd.DataFrame(F, index=idx)
    for c, v in kat.items():
        out[c] = v
    out = out.loc[idx[zm]]
    log(f"Merkmale: {len(out):,} Starter × {out.shape[1]} Spalten in {time.time() - t0:.0f} s")
    return out.reindex(ziel_maske[ziel_maske].index)


def _kategorien(X: pd.DataFrame, stufen: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Kategorische Spalten als pandas-Kategorie mit festen Stufen (aus dem Training)."""
    X = X.copy()
    stufen = dict(stufen or {})
    for c in KATEGORISCH:
        if c not in X:
            X[c] = None
        werte = X[c].astype(object).where(X[c].notna(), None)
        if c not in stufen:
            stufen[c] = sorted({str(v) for v in werte if v is not None})
        X[c] = pd.Categorical(werte.map(lambda v: str(v) if v is not None else None), categories=stufen[c])
    return X, stufen


def feld_relativ(X: pd.DataFrame, rennen: pd.Series) -> pd.DataFrame:
    """Je Merkmal aus RELATIV: Rang im Feld (0 = kleinster … 1 = größter Wert, Gleichstand gemittelt) und Abstand zum
    Feldschnitt. Fehlende Werte bleiben NaN und zählen beim Rang und Schnitt nicht mit. rennen: race_id je Zeile von X.
    Schnell (Sekunden) – läuft deshalb nach dem Zwischenspeicher, im Training wie in der Karte."""
    X = X.copy()
    r = pd.Series(rennen.to_numpy(), index=X.index).astype(str)
    for c in RELATIV:
        if c not in X:
            continue
        v = pd.to_numeric(X[c], errors="coerce")
        g = v.groupby(r)
        rang, anz = g.rank(method="average"), g.transform("count")
        X[f"{c}_rk"] = ((rang - 1) / (anz - 1)).where(anz > 1)
        X[f"{c}_dz"] = v - g.transform("mean")
    return X


# --------------------------------------------------------------------------
# Training
# --------------------------------------------------------------------------
def _bewerten(df: pd.DataFrame, spalte: str) -> dict:
    """Je Rennen: Rangkorrelation Vorhersage ~ Platzanteil, Sieger getroffen, Sieger unter den Top 3.
    Gleichstände zählen anteilig (3 Pferde gleich oben, einer davon Sieger = 1/3 Treffer) – sonst entschiede die
    Zeilenreihenfolge der Historie (nach Einlauf sortiert) und ein Rating mit vielen Gleichständen sähe zu gut aus.
    Rennen, in denen die Spalte überall gleich ist, zählen nicht zur Rangkorrelation."""
    rho, sieg, top3, n = [], 0.0, 0.0, 0
    for _, g in df.groupby("race_id"):
        g = g.dropna(subset=[spalte, "y"])
        if len(g) < 3:
            continue
        n += 1
        v, gewinner = g[spalte].to_numpy(float), g["y"].to_numpy(float) >= 0.999
        if np.ptp(v) > 0 and np.ptp(g["y"].to_numpy(float)) > 0:
            rho.append(g[spalte].rank().corr(g["y"].rank()))
        # Chance, dass der Sieger bei zufälliger Auflösung von Gleichständen unter den ersten k landet:
        # (k − Anzahl echt besser) / Anzahl gleich, begrenzt auf 0..1
        def chance(k: int) -> float:
            return max((min(1.0, max(0.0, (k - (v > w).sum()) / (v == w).sum())) for w in v[gewinner]), default=0.0)
        sieg += chance(1)
        top3 += chance(3)
    return {"rennen": n, "rang_korr": round(float(np.mean(rho)), 3) if rho else None,
            "sieger_getroffen": round(sieg / n, 3) if n else None, "sieger_in_top3": round(top3 / n, 3) if n else None}


# Merkmale aus Tracking-Daten (nur da, wo es ein Tracking-PDF gab) – für die Abdeckungs-Übersicht im Training
TRACKING_MERKMALE = ["dl600", "db200", "early", "f1_fi", "f1_g800", "f1_weg"]


def abdeckung(X: pd.DataFrame, tage: pd.Series) -> pd.DataFrame:
    """Anteil Starter mit Wert je Jahr – zeigt, ab wann Tracking (und ARR/TR) in der Historie überhaupt vorliegen."""
    spalten = [c for c in TRACKING_MERKMALE + ["arr", "tr", "rtr"] if c in X.columns]
    a = X[spalten].notna().groupby(pd.to_datetime(tage).dt.year.to_numpy()).mean().mul(100).round(0)
    a.insert(0, "starter", X.groupby(pd.to_datetime(tage).dt.year.to_numpy()).size())
    return a


def _lgb_daten(lgb, Xk, y, rennen, art, ref=None):
    """LightGBM-Datensatz; für „rang“ nach Rennen gruppiert (Zeilen eines Rennens hintereinander) mit Stufen-Ziel."""
    if art == "rang":
        return lgb.Dataset(Xk, np.rint(y.to_numpy() * RANG_STUFEN).astype(int), reference=ref,
                           group=rennen.groupby(rennen, sort=False).size().to_numpy(),
                           categorical_feature=KATEGORISCH, free_raw_data=False)
    return lgb.Dataset(Xk, y, reference=ref, categorical_feature=KATEGORISCH, free_raw_data=False)


def _lgb_params(art, params):
    if art == "rang":
        return {**LGB_PARAMS, "objective": "lambdarank", "metric": "ndcg", "eval_at": [3], "label_gain": RANG_GAIN,
                **(params or {})}
    return {**LGB_PARAMS, **(params or {})}


def trainieren(base: Path | None = None, *, hist: pd.DataFrame | None = None, out: Path | None = None,
               X: pd.DataFrame | None = None, params: dict | None = None, runden: int = LGB_RUNDEN,
               ab: str | None = None, neu: bool = False, art: str = "beide", log=print) -> dict:
    """Einmal trainieren: Merkmale über die ganze Historie, lernen auf den ersten LERN_ANTEIL der Tage, prüfen auf dem
    Rest (gegen den Marktfavoriten und das Rating), dann auf allen Tagen neu lernen und speichern.

    ab:  nur Rennen ab diesem Datum lernen/prüfen (z. B. "2024-01-01", wenn Tracking erst ab da vorliegt). Die Merkmale
         nutzen trotzdem die ganze Historie davor (Form, Verbindungen, Abstammung).
    neu: Merkmale neu bauen, auch wenn BASE/modelle/merkmale.parquet schon da ist (nötig nach neuen Renntagen).
    art: "regression" (Platzanteil je Pferd schätzen), "rang" (LightGBM lambdarank: Reihenfolge im Rennen lernen) oder
         "beide" – beide prüfen, das mit der besseren Rangkorrelation auf den Prüftagen wird gespeichert."""
    import lightgbm as lgb
    if hist is None:
        import regel_backtest as rb
        log("Historie laden …")
        hist = rb.laden(Path(base))
    ordner = Path(out) if out else (Path(base) / MODELL_ORDNER if base is not None else None)
    zwischen = ordner / MERKMAL_DATEI if ordner is not None else None
    version = zwischen.with_suffix(".json") if zwischen is not None else None
    if X is None and zwischen is not None and zwischen.exists() and not neu:
        v = json.loads(version.read_text()).get("version") if version.exists() else None
        X = pd.read_parquet(zwischen)
        if v != MERKMAL_VERSION:
            log(f"Zwischengespeicherte Merkmale sind von einer älteren Version ({v}) – baue neu.")
            X = None
        elif not X.index.isin(hist.index).all():
            log("Zwischengespeicherte Merkmale passen nicht zur Historie – baue neu.")
            X = None
        else:
            log(f"Merkmale aus {zwischen} ({len(X):,} Starter; neu bauen mit neu=True)")
    if X is None:
        log("Merkmale bauen (einmalig, dauert) …")
        X = merkmale(hist, log=log)
        if zwischen is not None:
            zwischen.parent.mkdir(parents=True, exist_ok=True)
            X.to_parquet(zwischen)
            version.write_text(json.dumps({"version": MERKMAL_VERSION}))
    y = ziel(hist).reindex(X.index)
    ok = y.notna()
    X, y = X[ok], y[ok]
    X = feld_relativ(X, hist.loc[X.index, "race_id"])
    tage = pd.to_datetime(hist.loc[X.index, "date"])
    log("Abdeckung je Jahr (% der Starter mit Wert):")
    log(abdeckung(X, tage).to_string())
    if ab:
        drin = tage >= pd.Timestamp(ab)
        X, y, tage = X[drin], y[drin], tage[drin]
        log(f"Nur Rennen ab {ab}: {len(X):,} Starter")
    # nach Datum und Rennen sortieren: für „rang“ müssen die Zeilen eines Rennens zusammenstehen
    rennen = hist.loc[X.index, "race_id"].astype(str)
    reihe = pd.DataFrame({"t": tage, "r": rennen}).sort_values(["t", "r"], kind="stable").index
    X, y, tage, rennen = X.loc[reihe], y.loc[reihe], tage.loc[reihe], rennen.loc[reihe]
    grenze = np.sort(tage.unique())[int(len(tage.unique()) * LERN_ANTEIL)]
    lern, test = (tage < grenze).to_numpy(), (tage >= grenze).to_numpy()
    Xk, stufen = _kategorien(X)
    log(f"Lernen: {int(lern.sum()):,} Starter bis {pd.Timestamp(grenze):%Y-%m-%d}, prüfen: {int(test.sum()):,}")
    pt = pd.DataFrame({"race_id": rennen[test].to_numpy(), "y": y[test].to_numpy(),
                       "markt": -pd.to_numeric(hist.loc[X.index[test], "odds_final"], errors="coerce").to_numpy(),
                       "rating": X.loc[test, "rating_adj"].to_numpy()})
    arten = ["regression", "rang"] if art == "beide" else [art]
    bericht: dict = {}
    modelle = {}
    for a_ in arten:
        p = _lgb_params(a_, params)
        d_lern = _lgb_daten(lgb, Xk[lern], y[lern], rennen[lern], a_)
        d_test = _lgb_daten(lgb, Xk[test], y[test], rennen[test], a_, ref=d_lern)
        m = lgb.train(p, d_lern, num_boost_round=runden, valid_sets=[d_test],
                      callbacks=[lgb.early_stopping(100, first_metric_only=True, verbose=False)])
        best = int(m.best_iteration or runden)
        pt[a_] = m.predict(Xk[test], num_iteration=best)
        bericht[f"modell ({a_})"] = {**_bewerten(pt, a_), "baeume": best}
        modelle[a_] = (m, best, p)
    bericht["markt (Endquote)"] = _bewerten(pt, "markt")
    bericht["rating (bereinigt)"] = _bewerten(pt, "rating")
    sieger = max(arten, key=lambda a_: bericht[f"modell ({a_})"]["rang_korr"] or -1)
    bericht.update({"gewaehlt": sieger, "lernen_bis": f"{pd.Timestamp(grenze):%Y-%m-%d}", "ab": ab})
    log("Prüfung auf den letzten Tagen (je Rennen):")
    for k, v in bericht.items():
        log(f"  {k}: {v}")
    m, best, p = modelle[sieger]
    imp = pd.Series(m.feature_importance("gain"), index=Xk.columns).sort_values(ascending=False)
    log(f"Wichtigste Merkmale ({sieger}, Gain): " + ", ".join(f"{k} {v / imp.sum():.1%}" for k, v in imp.head(15).items()))
    # endgültig: alle Tage, gleiche Baumzahl
    final = lgb.train(p, _lgb_daten(lgb, Xk, y, rennen, sieger), num_boost_round=best)
    ordner.mkdir(parents=True, exist_ok=True)
    final.save_model(str(ordner / MODELL_DATEI))
    meta = {"spalten": list(Xk.columns), "stufen": stufen, "art": sieger, "bericht": bericht,
            "wichtig": {k: round(float(v / imp.sum()), 4) for k, v in imp.head(30).items()},
            "trainiert": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), "starter": int(len(X))}
    (ordner / META_DATEI).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Modell gespeichert ({sieger}): {ordner / MODELL_DATEI}")
    return bericht


# --------------------------------------------------------------------------
# Vorhersage (Race Card)
# --------------------------------------------------------------------------
def laden(base: Path | None) -> dict | None:
    """Gespeichertes Modell aus BASE/modelle/ – None, wenn (noch) keins da ist oder lightgbm fehlt."""
    if base is None:
        return None
    ordner = Path(base) / MODELL_ORDNER
    if not (ordner / MODELL_DATEI).exists() or not (ordner / META_DATEI).exists():
        return None
    try:
        import lightgbm as lgb
    except ImportError:
        return None
    return {"booster": lgb.Booster(model_file=str(ordner / MODELL_DATEI)),
            "meta": json.loads((ordner / META_DATEI).read_text(encoding="utf-8"))}


def _gruppe(spalte: str) -> str:
    for pre, name in GRUPPEN:
        if spalte.startswith(pre):
            return name
    return {"n_runners": "Starterzahl", "distance_m": "Distanz", "going": "Boden", "dist_group": "Distanz",
            "racetype": "Renntyp", "cond_age": "Altersklasse"}.get(spalte, spalte)


def vorhersage(hist: pd.DataFrame, heute_zeilen: pd.DataFrame, modell: dict, log=print) -> dict:
    """Power je heutigem Starter: {(race_id, Startnummer): {"p": Power, "pred": Platzanteil (nur beim Regressions-Modell,
    sonst None), "treiber": [[Name, Beitrag]]}}.
    heute_zeilen: Spalten wie die Historie (Schlüssel, Gewicht, Rating, Box, Alter, Rennen …), ohne Ergebnis."""
    if modell is None or heute_zeilen is None or not len(heute_zeilen):
        return {}
    hz = heute_zeilen.copy()
    hz.index = [f"heute_{i}" for i in range(len(hz))]
    alle = pd.concat([hist, hz], axis=0, sort=False)
    heute = pd.Series(alle.index.isin(hz.index), index=alle.index)
    X = merkmale(alle, ziel_maske=heute, heute=heute, log=log)
    X = feld_relativ(X, alle.loc[X.index, "race_id"])
    meta = modell["meta"]
    Xk, _ = _kategorien(X.reindex(columns=[c for c in meta["spalten"]]), meta["stufen"])
    Xk = Xk[meta["spalten"]]
    pred = modell["booster"].predict(Xk)
    beitr = modell["booster"].predict(Xk, pred_contrib=True)[:, :-1]
    out = {}
    df = pd.DataFrame({"race_id": hz["race_id"].astype(str).to_numpy(), "no": hz["saddle_no"].to_numpy(), "pred": pred})
    for r_, g in df.groupby("race_id"):
        mu, sd = g["pred"].mean(), g["pred"].std(ddof=0)
        for k, z in g.iterrows():
            gr: dict = {}
            for spalte, b in zip(meta["spalten"], beitr[k]):
                gr[_gruppe(spalte)] = gr.get(_gruppe(spalte), 0.0) + float(b)
            top = sorted(gr.items(), key=lambda kv: -abs(kv[1]))[:4]
            p = 100 + 10 * (z["pred"] - mu) / sd if sd and sd > 0 else 100.0
            out[(r_, int(z["no"]))] = {"p": int(round(p)),
                                       "pred": round(float(z["pred"]), 3) if meta.get("art", "regression") == "regression" else None,
                                       "treiber": [[n_, round(v_ * 100, 1)] for n_, v_ in top]}
    return out
