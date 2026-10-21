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
  Pferd       Alter, Geschlecht, €/Lauf 365 Tage, Gewicht, Rating (roh und bereinigt), Tage seit dem letzten Lauf, Läufe
              (gesamt und 365 Tage), letzter Lauf auf heutiger Boden- bzw. Distanzgruppe (Platzanteil, ARR heutiges Gewicht),
              RTR / ARR / TR / ΔL600 A / ΔB200 A wie die Kacheln, Duell-Rang (wie die Kachel), Startbox (Ø Platzanteil der
              Box auf der Konfiguration), Laufstil (Ø frühe Position der letzten 5 Läufe, auch relativ zum Feld)
  Vorlieben   schon gewonnen / platziert auf Kurs, Distanzgruppe, Bodengruppe; beste Distanz-/Bodengruppe des Pferdes
              (Platzanteil, €/Lauf, A/E Platz)
  Verbindung  Trainer, Jockey, Besitzer, Züchter: Score aus A/E Platz, Platzanteil und €/Lauf (365 Tage, je 100 = Schnitt)
  Abstammung  Vater, Muttervater: Score, €/Lauf+, Valeur der 3-Jährigen+, beste Distanz-/Bodengruppe (ohne 2-Jährige bei
              der Distanz)
  Form        letzte drei Läufe: Klasse (Ø Valeur, Rennstärke), Längen zurück, Platzanteil, gleicher Boden / gleiche
              Distanzgruppe wie heute, ARR und TR (heutiges Gewicht), Finish-Index, ±800, Weg m, Endquote (dazu Quotenrang
              und Marktchance), mit/gegen den Rennverlauf (+1 gegen, −1 mit, 0 neutral), Tage davor,
              Gegner-Score (wie liefen die Gegner danach gegen ihre Quote), direkter Vergleich mit heutigen Gegnern

Colab:
    import power_modell as pm
    erg = pm.trainieren(BASE)        # einmalig (~1 h): Merkmale, 1 Jahr Aufwärmen, Rest 60/20/20 lernen/validieren/testen
    erg = pm.trainieren(BASE, ab="2024-01-01")   # danach schnell: Merkmale aus BASE/modelle/merkmale.parquet,
                                                 # lernen/prüfen nur ab dem Datum (z. B. ab da, wo es Tracking gibt)
Die Race Card (racecard.run) lädt das Modell danach aus BASE/modelle/ und ersetzt den bisherigen Power-Wert.
"""
from __future__ import annotations

import bisect
import json
import re
import time
import warnings
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

import racecard as rc
import rtr_arr
import timeform_ratings

MODELL_ORDNER = "modelle"
MODELL_DATEI = "power_modell.txt"
META_DATEI = "power_modell.json"
WERT_DATEI, WERT_META = "power_wert.txt", "power_wert.json"   # zweites Modell: A/E Platz gegen den Markt
WERT_PARAMS = dict(objective="binary", learning_rate=0.02, num_leaves=15, min_data_in_leaf=300, feature_fraction=0.7,
                   bagging_fraction=0.8, bagging_freq=1, lambda_l2=10.0, verbosity=-1)   # vorsichtig: kleines Signal
WERT_TOP = [0.20, 0.10, 0.05, 0.02]   # Rendite-Tabelle: oberste Anteile des Value-Faktors
WERT_GOLD = 0.10            # goldener Rahmen in der Karte: oberste 10 % des Faktors (Grenze aus der Validierung)
QUOTEN_STUFEN = [1, 3, 6, 10, 20, 1000]
GOLD_COTE_MAX = 10.0       # goldener Rahmen nur bis zu dieser Prognose-Cote: darüber verlor die Auswahl im Test klar
WARN_FAKTOR = 0.8           # Warnsignal (unterstes Fünftel), falls das Modell keine eigene Grenze gespeichert hat
QUOTE_BEREICH = (1.0, GOLD_COTE_MAX)  # Vorwärts-Test: Gold mit Prognose-Cote in diesem Bereich (im Test ≈ ausgeglichen)
PROTOKOLL = "auswertung/value_protokoll.csv"   # Vorwärts-Test: jede Karte schreibt ihre Value-Faktoren hierher
WERT_STUFEN = 5             # Prüfung: Starter nach vorhergesagtem Value-Faktor in so viele gleich große Gruppen
MERKMAL_DATEI = "merkmale.parquet"   # Zwischenspeicher der Merkmale (Bauen dauert ~30 min)
SCHLUESSEL_DATEI = "merkmale_schluessel.parquet"   # je Zeile des Zwischenspeichers: race_id, horse_id
MERKMAL_VERSION = 15                   # hochzählen, wenn merkmale() neue Spalten bekommt -> Zwischenspeicher wird neu gebaut
# Merkmale, die zusätzlich relativ zum heutigen Feld eingehen: Rang im Feld (0..1) und Abstand zum Feldschnitt
RELATIV = ["rating_adj", "weight", "epr365", "rtr", "arr", "tr", "f1_pos", "f1_lb", "f1_pm", "f2_pos", "trainer_score",
           "jockey_score", "owner_score", "duel_score", "sire_score", "lgo_pos", "ldi_pos",
           "form5_pos", "form5_best", "form5_lb", "form5_arr", "runs", "age", "arr_best365", "trainer_30_score",
           "dam_score", "form5_ue", "formz_pos", "formz_arr", "formz_ue", "form_steig_pos", "form_steig_arr",
           "form_pos_hoeher", "abst_pass", "formz_pos_pmu"]
# Value-Modell: Merkmale aus der Morgenquote (PMU-Referenzquote, am Morgen bekannt) – nie im Power-Modell
MORGEN_MERKMALE = ["m_pm", "m_log", "m_rk", "m_marge"]
# Segment-Modelle: lernen je Rennart nur die Korrektur zum gemeinsamen Modell (Ausgangswert = dessen Vorhersage)
SEGMENT_SPALTEN = ("racetype", "age_group")
SEG_PARAMS = dict(learning_rate=0.02, num_leaves=15, min_data_in_leaf=200, feature_fraction=0.7, bagging_fraction=0.8,
                  bagging_freq=1, lambda_l2=10.0)
SEG_MIN_STARTER = 2000      # Segment-Modell erst ab so vielen Lern-Startern im Segment
SEG_MIN_GEWINN = 0.003      # Power: Segment-Modell nur, wenn die Rangkorrelation auf der Validierung so viel steigt
SEG_MIN_VERLUST = 0.0003    # Value: ... wenn der Verlust auf der Validierung relativ um so viel sinkt
RANG_STUFEN = 10            # Lern-Ziel für „rang“: Platzanteil in 11 Stufen (0 … 10)
RANG_GAIN = [round(2 ** (s / 2) - 1, 3) for s in range(RANG_STUFEN + 1)]   # Sieg zählt am meisten, ohne alles andere zu erdrücken
# Lern-Ziel für „vorn“: nur die Spitze zählt, hinten alles 0 (Rauschen der hinteren Plätze bleibt außen vor):
# Platzanteil ≥ 0,7 → 1, ≥ 0,8 → 2, ≥ 0,9 → 3, Sieg → 4
VORN_GRENZEN = (0.7, 0.8, 0.9)
VORN_GAIN = [0.0, 1.0, 3.0, 7.0, 15.0]
ARTEN = ("regression", "rang", "vorn")
AUFWAERM_TAGE = 365         # erstes Jahr der Historie: nur Vorgeschichte für die Merkmale, nicht gelernt
ANTEILE = (0.6, 0.2, 0.2)   # übrige Renntage zeitlich: lernen / validieren (Abbruch, Modellwahl, Eichung) / testen (Bericht)
ROT_AB = 95                 # Power bis hier = rot (klar unter dem Feldschnitt)
FORM_N = 3                  # so viele letzte Läufe als eigene Merkmale
FORM_VERDICHTET = 5         # verdichtete Form (Ø, Bestwert, Streuung …) über so viele letzte Läufe
FORM_TREND_N = 6            # Formtrend: Steigung über so viele letzte Läufe (ab 3 Werten)
FORM_ZEIT_N = 10            # zeitgewichtete Form: höchstens so viele letzte Läufe …
FORM_HWZ = 90               # … mit Gewicht 0,5 ^ (Tage / FORM_HWZ)
FORM_ZEIT_K = 1.0           # … und zum Ausgangswert hin geschrumpft wie mit so vielen Läufen von heute
FORM_ZEIT_PRIOR = {"pos": 0.5, "ue": 0.0}   # Ausgangswerte (Pos: Feldmitte, über Erwartung: 0); ARR ungeschrumpft
FORM_TOP = 0.75             # „Spitzenlauf“: Pos ab hier
ABST_STAND_MIN = 2000       # Abstammungs-Passung: Monatsstand erst ab so vielen Läufen davor
FORM_KLASSE_TOL = 0.2       # Form in gleicher/höherer Klasse: Preisgeld (log) höchstens so viel unter heute
VERB_TAGE = 365             # Verbindungen: Fenster
KURZ_TAGE = 30              # Stallform / Jockeyform: kurzes Fenster
PAUSE_TAGE = 60             # ab so vielen Tagen ohne Start gilt ein Lauf als „nach Pause“
VERB_K = 10                 # Verbindungs-Score zur 100 hin geschrumpft wie mit so vielen Läufen bei 100
ABST_K = 20                 # dasselbe für Vater/Muttervater
ABST_MIN = 30               # beste Gruppe von Vater/Muttervater erst ab so vielen Läufen in der Gruppe
PFERD_MIN = 2               # beste Gruppe des Pferdes erst ab so vielen Läufen in der Gruppe
KATEGORISCH = ["racetype", "going", "dist_group", "age_group", "sex", "f1_typ", "f2_typ", "f3_typ"]
# Altersklasse (conditions_age) -> Altersgruppe des Rennens; nicht aufgeführte Werte über die Alter im Feld
ALTERSGRUPPE = {"DEUX_ANS": "2yo", "TROIS_ANS": "3yo", "TROIS_ANS_ET_PLUS": "3yo+", "TROIS_QUATRE_CINQ_ANS": "3yo+",
                "QUATRE_ANS": "4yo+", "QUATRE_ANS_ET_PLUS": "4yo+", "QUATRE_CINQ_ANS": "4yo+", "CINQ_ANS_ET_PLUS": "4yo+"}
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
           ("form5_", "Form letzte 5"), ("formz_", "Form zeitgewichtet"), ("form_steig", "Formtrend"),
           ("form5_klasse", "Klasse der letzten Läufe"), ("form5_preis", "Klasse der letzten Läufe"),
           ("formz_klasse", "Klasse der letzten Läufe"), ("formz_preis", "Klasse der letzten Läufe"),
           ("chg_prize", "Klassenwechsel"), ("chg_class", "Klassenwechsel"), ("chg_weight", "Gewichtswechsel"),
           ("chg_dist", "Distanzwechsel"), ("chg_rating", "Rating seit letztem Lauf"), ("chg_jockey", "Jockeywechsel"),
           ("chg_trainer", "Trainerwechsel"),
           ("form_best3", "Formtrend"), ("form_pos_hoeher", "Form in gleicher/höherer Klasse"), ("season", "Jahreszeit"), ("feld_aelter", "Erfahrung im Feld"),
           ("feld_erfahrener", "Erfahrung im Feld"), ("chg_", "Wechsel zum letzten Lauf"),
           ("kennt_jockey", "Jockey kennt Pferd"), ("trainerwechsel5", "Trainerwechsel"),
           ("dam_", "Mutter (Geschwister)"), ("hcp_", "Handicap-Marke"), ("seit_pause", "Läufe seit Pause"),
           ("erst_wallach", "erstmals Wallach"), ("arr_best", "Bestform ARR"), ("blink", "Scheuklappen"),
           ("race_prize", "Preisgeld des Rennens"), ("m_", "Morgenquote"), ("abst_", "Abstammungs-Passung"),
           ("cgd_", "Bilanz Kurs/Boden/Distanz (CGD)"), ("erst_", "erstmals Kurs/Boden/Distanz/Belag"), ("feld_val", "Klasse des Feldes"),
           ("lgo_", "letzter Lauf auf heutigem Boden"), ("ldi_", "letzter Lauf auf heutiger Distanz"),
           ("won_", "Sieg-Vorlieben"), ("placed_", "Platz-Vorlieben"), ("best_", "beste Gruppe Pferd"),
           ("rating", "Rating"), ("weight", "Gewicht"), ("epr365", "€/Lauf 365"), ("days", "Tage seit Lauf"),
           ("runs", "Läufe"), ("age_group", "Altersgruppe"), ("age", "Alter"), ("sex", "Geschlecht"), ("draw", "Startbox")]


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------
def _spalte(h: pd.DataFrame, c: str, standard=np.nan) -> pd.Series:
    return h[c] if c in h else pd.Series(standard, index=h.index)


def _zahl(h: pd.DataFrame, c: str) -> np.ndarray:
    return pd.to_numeric(_spalte(h, c), errors="coerce").to_numpy(dtype=float, copy=True)


def _text(h: pd.DataFrame, c: str) -> np.ndarray:
    return _spalte(h, c, None).astype(object).where(_spalte(h, c, None).notna(), None).to_numpy()


def renntyp3(t) -> str | None:
    """Renntyp für das Modell in vier Gruppen: alles mit „Handicap“ -> Handicap (auch Handicap Categorie Divise,
    Handicap A Reclamer), Claimer -> Claimer, Gruppe 1–3 und Listed -> Blacktype, alles andere (Conditions,
    International, Accaf …) -> Conditions; innerhalb der Gruppen trennt das Preisgeld die Klasse."""
    if t is None or (isinstance(t, float) and np.isnan(t)):
        return None
    t = str(t).strip().lower()
    if not t or t == "inconnu":
        return None
    if "handicap" in t:
        return "Handicap"
    if "claim" in t or "reclam" in t:
        return "Claimer"
    if re.search(r"\b(group|groupe|listed|liste)\b", t):
        return "Blacktype"
    return "Conditions"


def altersgruppe(klasse, alter_min=np.nan, alter_max=np.nan) -> str | None:
    """Altersgruppe des Rennens (2yo, 3yo, 3yo+, 4yo+) aus der Altersklasse, sonst aus den Altern im Feld."""
    g = ALTERSGRUPPE.get(str(klasse).strip().upper()) if klasse is not None else None
    if g is not None or np.isnan(alter_min):
        return g
    if alter_min >= 4:
        return "4yo+"
    if alter_max <= alter_min:
        return {2: "2yo", 3: "3yo"}.get(int(alter_min))
    return "3yo+"


def _going_w(a, b) -> float:
    return rc.going_gewicht(a, b) if a is not None and b is not None else 1.0


SCORE_EXP_MIN = 0.05        # A/E-Teil eines Scores erst ab so viel erwarteten Plätzen (≈ ein Lauf mit kleiner Chance)


def _score(placed, exp, rp, lp, n, g_rp, g_lp) -> float:
    """Score aus A/E Platz, Platzanteil und €/Lauf (log), je 100 = Schnitt; Mittel der vorhandenen Teile."""
    teile = []
    if exp > SCORE_EXP_MIN:                  # rollende Fenster: Rundungsreste nahe 0 nicht als Erwartung werten
        teile.append(100 * placed / exp)
    if n and g_rp:
        teile.append(100 * (rp / n) / g_rp)
    if n and g_lp:
        teile.append(100 * (lp / n) / g_lp)
    return float(np.mean(teile)) if teile else np.nan


def _verlauf(h: pd.DataFrame) -> np.ndarray:
    """Rennverlauf je Starter als Zahl: +1 gegen den Verlauf gelaufen, −1 mit dem Verlauf, 0 neutral, sonst NaN.
    Nimmt verlauf_pferd aus h (Race Card), sonst rechnet racecard.rennverlauf es nach (Norm aus der ganzen Historie,
    wie in der Karte). Fehlen die nötigen Spalten, bleibt alles NaN."""
    if "verlauf_pferd" in h:
        vp = h["verlauf_pferd"].to_numpy()
    else:
        try:
            d = h.reset_index(drop=True)
            vp = rc.rennverlauf(d, d)["verlauf_pferd"].to_numpy()        # Left-Merge: Reihenfolge bleibt
        except (KeyError, ValueError):
            vp = np.full(len(h), None, dtype=object)
    return np.array([{"gegen": 1.0, "mit": -1.0, "neutral": 0.0}.get(v, np.nan) for v in vp], dtype=float)


def ziel(h: pd.DataFrame) -> pd.Series:
    """Abhängige Variable: Platzanteil, nicht im Ziel = 0; ohne Ergebnis oder Feld < 2: NaN."""
    n = pd.to_numeric(_spalte(h, "n_runners"), errors="coerce")
    rp = pd.to_numeric(_spalte(h, "rel_place"), errors="coerce").fillna(0.0)
    return rp.where(n > 1)


# --------------------------------------------------------------------------
# Merkmale
# --------------------------------------------------------------------------
def _steigung(y: np.ndarray) -> float:
    """Steigung je Lauf (Kleinste Quadrate), y neueste zuerst; > 0 = Werte steigen zu den jüngsten Läufen hin.
    Erst ab 3 gültigen Werten."""
    x = -np.arange(len(y), dtype=float)
    m = np.isfinite(y)
    if m.sum() < 3:
        return np.nan
    x, y = x[m], y[m]
    xc = x - x.mean()
    return float((xc * (y - y.mean())).sum() / (xc * xc).sum())


def _abst_zeitpunkt(h: pd.DataFrame, hm: np.ndarray, zm: np.ndarray, f_pos: np.ndarray, F: dict, log=print) -> None:
    """Abstammungs-Passung ohne Blick in die Zukunft: je Monat der Zielzeilen ein Stand der Abstammungsprofile
    (racecard.abstammung_profil) aus allen Läufen VOR dem Monatsersten. Damit für heute (alle vier Skalen) und für die
    letzten FORM_N Läufe (ohne Reife, racecard.ABST_PASS_LAUF); Wechsel = heute ohne Reife − letzter Lauf."""
    t0 = time.time()
    monat = h["date"].dt.to_period("M").to_numpy()
    ziel_pos = np.flatnonzero(zm)
    datum = h["date"].to_numpy()
    staende = 0
    for m in sorted(set(monat[ziel_pos])):
        drin = (datum < np.datetime64(m.start_time)) & ~hm
        if drin.sum() < ABST_STAND_MIN:
            continue
        stand = h[drin]
        prof = {r_: rc.abstammung_profil(stand, r_ + "_key") for r_ in rc.ABST_PASS_ROLLE}
        staende += 1
        ii = ziel_pos[monat[ziel_pos] == m]
        w = rc.abst_passung_werte(prof, h.iloc[ii])
        F["abst_pass"][ii] = w["pass"].to_numpy()
        for r_ in rc.ABST_PASS_ROLLE:
            F[f"abst_pass_{r_}"][ii] = w[f"pass_{r_}"].to_numpy()
        for d in rc.ABST_SKALEN:
            F[f"abst_pass_{d}"][ii] = w[f"pass_{d}"].to_numpy()
        heute_lauf = rc.abst_passung_werte(prof, h.iloc[ii], rc.ABST_PASS_LAUF)["pass"].to_numpy()
        for k in range(1, FORM_N + 1):
            jj = f_pos[ii, k - 1]
            ok = jj >= 0
            if ok.any():
                F[f"f{k}_abst_pass"][ii[ok]] = rc.abst_passung_werte(prof, h.iloc[jj[ok]], rc.ABST_PASS_LAUF)["pass"].to_numpy()
        F["abst_pass_wechsel"][ii] = heute_lauf - F["f1_abst_pass"][ii]
    log(f"  Abstammungs-Passung: {staende} Monatsstände, {time.time() - t0:.0f} s")


def merkmale(h: pd.DataFrame, ziel_maske: pd.Series | None = None, heute: pd.Series | None = None,
             duelle: bool = True, abst: bool = True, log=print) -> pd.DataFrame:
    """Merkmale je Starter aus Läufen vor dem Renntag. h: vorbereitete Historie (racecard.vorbereiten), optional mit
    heutigen Zeilen ohne Ergebnis (heute=True – sie fließen nie in die Historie anderer ein). ziel_maske: nur für diese
    Zeilen ausgeben (Vorgabe: alle). Rückgabe mit dem Index von h."""
    t0 = time.time()
    h = h.copy()
    h["date"] = pd.to_datetime(h["date"])
    heute = (heute.reindex(h.index).fillna(False).astype(bool) if heute is not None
             else pd.Series(False, index=h.index))
    extern = _spalte(h, "extern", False).eq(True)            # externe Läufe (PMH/Ausland): nur Vorgeschichte
    ziel_maske = (ziel_maske.reindex(h.index).fillna(False).astype(bool) if ziel_maske is not None
                  else ~extern)
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
    ausg = _spalte(h, "ausgeritten", False).eq(True).to_numpy()
    trk = _spalte(h, "tracking", False).eq(True).to_numpy()
    trcap = _zahl(h, "tr_gedeckelt")
    werte = {c: _zahl(h, c) for c in ["arr", "tr", "rtr", "d_L600_A", "d_B200_A", "early_pct", "cls_val", "cls_epr_kl",
                                       "lengths_behind", "fi_adj", "pos_gain_800_finish", "weg_med", "odds_final",
                                       "odds_rank", "valeur", "age", "draw"]}
    for c in ["arr", "tr", "rtr", "d_L600_A", "d_B200_A", "early_pct", "fi_adj", "pos_gain_800_finish", "weg_med",
              "lengths_behind"]:
        werte[c][hm] = np.nan                                     # heutige Zeilen haben keine Laufwerte
    lb = np.where(fpos == 1, 0.0, werte["lengths_behind"])
    bgrp = np.array([rtr_arr.boden_gruppe(g) for g in going], dtype=object)      # Bodengruppe (FAST, SLOW, PSF …)
    vlf = _verlauf(h)                                                             # +1 gegen / −1 mit / 0 neutral
    vlf[hm] = np.nan
    preis = np.log1p(np.clip(_zahl(h, "prize_eur"), 0, None))                      # Preisgeld des Rennens (vorab bekannt)
    feld_val = pd.Series(werte["valeur"]).groupby(rid).transform("mean").to_numpy(dtype=float)   # Ø Rating des Feldes
    blink = np.array([{"ohne": 0.0, "klassisch": 1.0, "australisch": 2.0}.get(rc.scheuklappen_gruppe(b), np.nan)
                      for b in _text(h, "blinkers")], dtype=float)
    jk, tk = _text(h, "jockey_key"), _text(h, "trainer_key")
    ext_ = extern.loc[idx].to_numpy(dtype=float)             # externer Lauf (PMH/Ausland) je Zeile
    # Kennzeichen „extern“ für die Merkmale: nur PMH/Ausland/Übersee – externe Läufe auf PMU-Bahnen (v. a. vor Beginn
    # der Historie) zählen wie PMU-Läufe, sonst hätte das Kennzeichen vor und nach Oktober 2022 eine andere Bedeutung
    ekz_ = rc.extern_kennzeichen(h).loc[idx].to_numpy(dtype=float)
    ausl_ = np.array([rc.ist_ausland(b) if e_ else False
                      for b, e_ in zip(_text(h, "hippodrome"), ext_)], dtype=float)
    cgd = rc.cgd_berechnen(h)                                # Bilanz vor jedem Lauf auf Kurs / Boden / Distanz
    cgd_code = cgd["cgd"].to_numpy()
    cgd_z = cgd[["cgd_sieg", "cgd_platz", "cgd_neu"]].to_numpy(dtype=float)
    belag = np.array([rc.abst_belag_kat(g) for g in going], dtype=object)
    f_pos = np.full((n, FORM_N), -1, dtype=int)            # Zeile des k-ten letzten Laufs
    letzter_jk = np.full(n, None, dtype=object)                                    # Jockey des letzten Laufs (je Zeile)
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
    typ3 = np.array([renntyp3(t) for t in _text(h, "racetype")], dtype=object)
    a_min = pd.Series(werte["age"]).groupby(rid).transform("min").to_numpy(dtype=float)
    a_max = pd.Series(werte["age"]).groupby(rid).transform("max").to_numpy(dtype=float)
    kat = {"racetype": typ3, "going": going, "dist_group": dgrp,
           "age_group": np.array([altersgruppe(k, a, b) for k, a, b in zip(_text(h, "conditions_age"), a_min, a_max)],
                                 dtype=object),
           "sex": np.array([str(s)[:1].upper() if s is not None else None for s in _text(h, "sex")], dtype=object)}

    # ---- je Pferd: Kacheln, Form, Vorlieben ----------------------------------------------------------------------
    F["race_prize"], F["feld_val"], F["blink"] = preis, feld_val, blink
    for c in ["form5_pos", "form5_best", "form5_lb", "form5_arr", "form5_ue", "form5_std", "form5_top", "form5_klasse",
              "form5_preis", "formz_pos", "formz_arr", "formz_ue", "formz_n", "formz_klasse", "formz_preis",
              "form_steig_pos", "form_steig_arr", "form_steig_lb",
              "form_steig_ue", "form_best3_diff", "form_pos_hoeher", "chg_weight", "chg_dist", "chg_class",
              "chg_prize", "chg_jockey", "chg_trainer", "blink_first", "blink_change", "kennt_jockey", "trainerwechsel5",
              "chg_rating", "hcp_sieg_diff", "hcp_platz_diff", "seit_pause", "arr_best365", "arr_best_dist",
              "arr_best_abst", "erst_wallach", "cgd_sieg", "cgd_platz", "cgd_neu", "erst_kurs", "erst_boden",
              "erst_dist", "erst_belag", "abst_pass", "abst_pass_sire", "abst_pass_dam_sire", "abst_pass_dist",
              "abst_pass_boden", "abst_pass_belag", "abst_pass_reife", "abst_pass_wechsel", "form5_extern",
              "f1_ausland", "formz_pos_pmu"]:
        feld(c)
    for c in ["runs", "runs365", "lgo_pos", "lgo_arr", "ldi_pos", "ldi_arr", "days", "rtr", "arr", "tr", "dl600", "db200", "early", "epr365",
              "won_course", "won_dist", "won_going", "placed_course", "placed_dist", "placed_going", "best_dist", "best_going"]:
        feld(c)
    for k in range(1, FORM_N + 1):
        for c in ["val", "epr", "lb", "pos", "same_going", "same_dist", "arr", "tr", "fi", "g800", "weg", "odds", "orank",
                  "pm", "verlauf", "tage", "gegner", "duell", "cgd_sieg", "cgd_platz", "cgd_neu", "abst_pass", "extern"]:
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
    oq = werte["odds_final"]
    inv = pd.Series(np.divide(1.0, oq, out=np.full(len(oq), np.nan), where=oq > 1))
    p_markt = (inv / inv.groupby(rid).transform("sum")).to_numpy(dtype=float)
    o_rang = inv.groupby(rid).rank(ascending=False, method="average")
    o_n = inv.notna().groupby(rid).transform("sum")
    o_rel = ((o_rang - 1) / (o_n - 1)).where(o_n > 1).to_numpy(dtype=float)
    feld_heute = {r: set(hid[p]) for r, p in rennen_pos.items()}
    ue = rp0 - (1.0 - o_rel)                     # Pos über Erwartung: erwartete Pos aus dem damaligen Quotenrang
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
            if np.isfinite(expp[j]):                       # A/E nur über Läufe mit Erwartung (nicht extern)
                s[1] += np.nan_to_num(placed[j])
                s[2] += expp[j]
            s[3] += np.nan_to_num(rp0[j])
            s[4] += np.nan_to_num(lp[j])
        sc = {k: _score(s[1], s[2], s[3], s[4], s[0], 0.5, g_lp) for k, s in g.items() if s[0] >= PFERD_MIN}
        sc = {k: v for k, v in sc.items() if not np.isnan(v)}
        if heute_k not in sc:
            return np.nan
        return float(sc[heute_k] >= max(sc.values()))

    f_typ = {k: np.full(n, None, dtype=object) for k in range(1, FORM_N + 1)}   # Renntyp der letzten Läufe
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
            # CGD heute (Stand vor dem Renntag) und erstmals auf Kurs / Boden / Distanz / Belag
            F["cgd_sieg"][i], F["cgd_platz"][i], F["cgd_neu"][i] = cgd_z[i]
            if cgd_code[i] is not None:
                for name, zeichen in zip(("erst_kurs", "erst_boden", "erst_dist"), cgd_code[i]):
                    if zeichen != "–":
                        F[name][i] = float(zeichen == "◦")
            if belag[i] is not None:
                F["erst_belag"][i] = float(all(belag[j] != belag[i] for j in vor))
            if jk[i] is not None:                              # Jockey hat das Pferd schon geritten
                F["kennt_jockey"][i] = float(any(jk[j] == jk[i] for j in vor))
            if not vor:
                continue
            # Läufe seit der letzten Pause (≥ PAUSE_TAGE): 0 = heute erster Start nach Pause, höchstens 10
            c_, vt = 0, tag[i]
            for j in vor:
                if vt - tag[j] >= PAUSE_TAGE:
                    break
                c_, vt = c_ + 1, tag[j]
            F["seit_pause"][i] = min(c_, 10)
            # Rating: Änderung seit dem letzten Lauf und Abstand zur letzten Sieg-/Platzmarke im Handicap
            val_i = werte["valeur"][i]
            if not np.isnan(val_i):
                F["chg_rating"][i] = val_i - werte["valeur"][vor[0]]
                for name, menge in (("sieg", won), ("platz", placed)):
                    j = next((j for j in vor if typ3[j] == "Handicap" and menge[j] == 1
                              and not np.isnan(werte["valeur"][j])), None)
                    if j is not None:
                        F[f"hcp_{name}_diff"][i] = val_i - werte["valeur"][j]
            # Bestform: bester ARR der letzten 365 Tage und auf heutiger Distanzgruppe (heutiges Gewicht)
            a365 = [werte["arr"][j] for j in vor if tag[i] - tag[j] <= 365 and not ausg[j] and not np.isnan(werte["arr"][j])]
            if a365:
                F["arr_best365"][i] = max(a365) - gew[i] + rc.GEWICHT_REF
                if not np.isnan(werte["arr"][vor[0]]):
                    F["arr_best_abst"][i] = werte["arr"][vor[0]] - max(a365)          # letzter Lauf unter Bestform: < 0
            if dgrp[i] is not None:
                ad = [werte["arr"][j] for j in vor if dgrp[j] == dgrp[i] and not ausg[j] and not np.isnan(werte["arr"][j])]
                if ad:
                    F["arr_best_dist"][i] = max(ad) - gew[i] + rc.GEWICHT_REF
            # erstmals als Wallach (Hengst beim letzten Lauf, heute Wallach)
            if kat["sex"][i] is not None and kat["sex"][vor[0]] is not None:
                F["erst_wallach"][i] = float(kat["sex"][i] == "H" and kat["sex"][vor[0]] == "M")
            # Trainerwechsel innerhalb der letzten 5 Starts (heute eingeschlossen)
            tz = [t_ for t_ in [tk[i]] + [tk[j] for j in vor[:4]] if t_ is not None]
            if len(tz) > 1:
                F["trainerwechsel5"][i] = float(len(set(tz)) > 1)
            F["days"][i] = tag[i] - tag[vor[0]]
            F["runs365"][i] = sum(tag[i] - tag[j] <= 365 for j in vor)
            # verdichtete Form der letzten FORM_VERDICHTET Läufe (fehlende Werte zählen nicht)
            v5 = vor[:FORM_VERDICHTET]
            pos5, lb5 = rp0[v5], lb[v5]
            arr5 = werte["arr"][v5] - gew[i] + rc.GEWICHT_REF
            if np.isfinite(pos5).any():
                F["form5_pos"][i], F["form5_best"][i] = np.nanmean(pos5), np.nanmax(pos5)
                F["form5_top"][i] = float(np.mean(pos5[np.isfinite(pos5)] >= FORM_TOP))
                if np.isfinite(pos5).sum() >= 3:
                    F["form5_std"][i] = np.nanstd(pos5)                         # Konstanz: klein = beständig
            F["form5_extern"][i] = float(ekz_[v5].mean())             # Anteil externer Läufe (PMH/Ausland/Übersee)
            F["f1_ausland"][i] = ausl_[vor[0]]
            if np.isfinite(lb5).any():
                F["form5_lb"][i] = np.nanmean(lb5)
            if np.isfinite(arr5).any():
                F["form5_arr"][i] = np.nanmean(arr5)
            if np.isfinite(ue[v5]).any():                                        # Pos über der Erwartung des damaligen Markts
                F["form5_ue"][i] = np.nanmean(ue[v5])
            if np.isfinite(feld_val[v5]).any() and not np.isnan(feld_val[i]):    # > 0: zuletzt in stärkeren Feldern als heute
                F["form5_klasse"][i] = np.nanmean(feld_val[v5]) - feld_val[i]
            if np.isfinite(preis[v5]).any() and not np.isnan(preis[i]):
                F["form5_preis"][i] = np.nanmean(preis[v5]) - preis[i]
            # zeitgewichtete Form: jüngere Läufe zählen mehr (Halbwertszeit FORM_HWZ Tage)
            vz = np.array(vor[:FORM_ZEIT_N])
            wz = 0.5 ** ((tag[i] - tag[vz]) / FORM_HWZ)
            for name, y in (("pos", rp0[vz]), ("arr", werte["arr"][vz] - gew[i] + rc.GEWICHT_REF), ("ue", ue[vz])):
                m_ = np.isfinite(y)
                if m_.any():                                # wenige / alte Läufe: zum Ausgangswert hin geschrumpft
                    k_ = FORM_ZEIT_K if name in FORM_ZEIT_PRIOR else 0.0
                    F[f"formz_{name}"][i] = float(((wz[m_] * y[m_]).sum() + k_ * FORM_ZEIT_PRIOR.get(name, 0.0))
                                                  / (wz[m_].sum() + k_))
            m_ = np.isfinite(rp0[vz])
            F["formz_n"][i] = float(wz[m_].sum())             # wie viele „heutige“ Läufe stecken in der Form
            m_ = np.isfinite(rp0[vz]) & (ekz_[vz] == 0)        # dieselbe Form nur aus PMU-Läufen (ohne PMH/Ausland)
            if m_.any():
                F["formz_pos_pmu"][i] = float(((wz[m_] * rp0[vz][m_]).sum() + FORM_ZEIT_K * FORM_ZEIT_PRIOR["pos"])
                                              / (wz[m_].sum() + FORM_ZEIT_K))
            for name, y, h_ in (("klasse", feld_val[vz], feld_val[i]), ("preis", preis[vz], preis[i])):
                m_ = np.isfinite(y)
                if m_.any() and not np.isnan(h_):           # > 0: zuletzt (zeitgewichtet) in stärkeren Rennen als heute
                    F[f"formz_{name}"][i] = float((wz[m_] * y[m_]).sum() / wz[m_].sum()) - h_
            # Formtrend: Steigung je Lauf über die letzten FORM_TREND_N (> 0: wird besser bzw. bei lb: mehr Längen zurück)
            vt_ = vor[:FORM_TREND_N]
            for name, y in (("pos", rp0[vt_]), ("arr", werte["arr"][vt_]), ("lb", lb[vt_]), ("ue", ue[vt_])):
                F[f"form_steig_{name}"][i] = _steigung(y)
            p3, p_alt = rp0[vor[:3]], rp0[vor[3:8]]
            if np.isfinite(p3).any() and np.isfinite(p_alt).any():              # > 0: jüngste Spitze über der früheren
                F["form_best3_diff"][i] = np.nanmax(p3) - np.nanmax(p_alt)
            if not np.isnan(preis[i]):                                           # Form in gleicher oder höherer Klasse
                hk = [rp0[j] for j in vor[:FORM_ZEIT_N] if preis[j] >= preis[i] - FORM_KLASSE_TOL and not np.isnan(rp0[j])]
                if hk:
                    F["form_pos_hoeher"][i] = float(np.mean(hk))
            # Wechsel gegenüber dem letzten Lauf
            j = vor[0]
            F["chg_weight"][i], F["chg_dist"][i] = gew[i] - gew[j], dist[i] - dist[j]
            F["chg_class"][i], F["chg_prize"][i] = feld_val[i] - feld_val[j], preis[i] - preis[j]
            if jk[i] is not None and jk[j] is not None:
                F["chg_jockey"][i] = float(jk[i] != jk[j])
                letzter_jk[i] = jk[j]
            if tk[i] is not None and tk[j] is not None:
                F["chg_trainer"][i] = float(tk[i] != tk[j])
            if not np.isnan(blink[i]):
                frueher = blink[vor][~np.isnan(blink[vor])]
                if len(frueher):
                    F["blink_first"][i] = float(blink[i] > 0 and (frueher == 0).all())
                if not np.isnan(blink[j]):
                    F["blink_change"][i] = float(blink[i] != blink[j])
            # letzter Lauf auf heutiger Bodengruppe / Distanzgruppe: Platzanteil und ARR (heutiges Gewicht)
            for name, gruppe in (("lgo", bgrp), ("ldi", dgrp)):
                if gruppe[i] is None:
                    continue
                j = next((j for j in vor if gruppe[j] == gruppe[i]), None)
                if j is not None:
                    F[f"{name}_pos"][i] = rp0[j]
                    F[f"{name}_arr"][i] = werte["arr"][j] - gew[i] + rc.GEWICHT_REF
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
                F[f"f{k}_verlauf"][i] = vlf[j]
                F[f"f{k}_tage"][i] = tag[i] - tag[j]
                F[f"f{k}_cgd_sieg"][i], F[f"f{k}_cgd_platz"][i], F[f"f{k}_cgd_neu"][i] = cgd_z[j]
                F[f"f{k}_extern"][i] = ekz_[j]
                f_pos[i, k - 1] = j
                f_typ[k][i] = typ3[j]
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
    if abst:
        _abst_zeitpunkt(h, hm, zm, f_pos, F, log)

    # ---- Tempo-Szenario je Rennen aus dem Laufstil der Starter --------------------------------------------------
    fr = pd.Series(F["early"])
    F["pace_front"] = fr.le(rc.TEMPOMACHER).groupby(rid).transform("sum").where(zm).to_numpy(dtype=float)
    F["pace_early_mean"] = fr.groupby(rid).transform("mean").to_numpy(dtype=float)
    F["early_rel"] = F["early"] - F["pace_early_mean"]

    # ---- Tag für Tag: Verbindungen, Abstammung, Startbox (Stand vor dem Renntag) --------------------------------
    t1 = time.time()
    rollen = {r_: _text(h, r_ + "_key") for r_ in ("trainer", "jockey", "owner", "breeder")}
    tr_, jo_ = rollen["trainer"], rollen["jockey"]

    def paar(a, b):
        return np.array([f"{x}|{y}" if x is not None and y is not None else None for x, y in zip(a, b)], dtype=object)
    # Erststart / Start nach Pause je Zeile (auch Historie): für die Trainer-Scores in diesen Lagen
    erst_l, pause_l = np.zeros(n, bool), np.zeros(n, bool)
    for laeufe in pferde.values():
        frueher = []
        for i in laeufe:
            k_ = bisect.bisect_left(frueher, tag[i])
            erst_l[i] = k_ == 0
            pause_l[i] = k_ > 0 and tag[i] - frueher[k_ - 1] >= PAUSE_TAGE
            if not hm[i]:
                bisect.insort(frueher, tag[i])
    rollen.update({
        "trainer_30": tr_, "jockey_30": jo_,                                        # Form im kurzen Fenster
        "trainer_typ": paar(tr_, typ3), "trainer_kurs": paar(tr_, course), "jockey_trainer": paar(jo_, tr_),
        "trainer_debuet": np.where(erst_l, tr_, None), "trainer_pause": np.where(pause_l, tr_, None)})
    fenster = {"trainer_30": KURZ_TAGE, "jockey_30": KURZ_TAGE}
    mutter = _spalte(h, "dam", None)
    if "p_nomMere" in h:
        mutter = mutter.where(mutter.notna() & (mutter.astype("string").str.strip() != ""), h["p_nomMere"])
    mutter = rc.norm_name(mutter.astype(object).where(mutter.notna(), None))
    mutter = mutter.where(~mutter.fillna("").isin(["", "NAN", "NONE"]))
    linien = {l_: _text(h, l_ + "_key") for l_ in ("sire", "dam_sire")}
    linien["dam"] = mutter.astype(object).where(mutter.notna(), None).to_numpy()
    abst_pferd: dict = {}                                # (Mutter, Pferd) -> eigene Läufe (Geschwister ohne das Pferd selbst)
    konfig = _text(h, "konfig")
    for r_ in rollen:
        feld(f"{r_}_score"), feld(f"{r_}_runs")
    for l_ in linien:
        for c in ("score", "epr", "val3", "runs") + (("best_dist", "best_going") if l_ != "dam" else ()):
            feld(f"{l_}_{c}")
    feld("box_mean"), feld("box_runs"), feld("chg_jockey_score")
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
        def verb_score(r_, key):
            """Verbindungs-Score (365 Tage, geschrumpft) und Läufe für einen Schlüssel, Stand vor dem Tag d_."""
            s = verb[r_].get(key)
            if s is None:
                return np.nan, np.nan
            q = s[0]
            while q and q[0][0] < d_ - fenster.get(r_, VERB_TAGE):
                _, pl_, ex_, rp_, lp_ = q.popleft()
                s[1] -= 1; s[2] -= pl_; s[3] -= ex_; s[4] -= rp_; s[5] -= lp_
            if not s[1]:
                return np.nan, np.nan
            sc = _score(s[2], s[3], s[4], s[5], s[1], g_rp, g_lpw)
            return ((s[1] * sc + VERB_K * 100) / (s[1] + VERB_K) if not np.isnan(sc) else np.nan), s[1]

        for i in pos[zm[pos]]:
            for r_, keys in rollen.items():
                F[f"{r_}_score"][i], F[f"{r_}_runs"][i] = verb_score(r_, keys[i])
            if letzter_jk[i] is not None:                 # Jockey besser/schlechter als beim letzten Lauf (Score heute)
                F["chg_jockey_score"][i] = F["jockey_score"][i] - verb_score("jockey", letzter_jk[i])[0]
            ga_rp = g_all[1] / g_all[0] if g_all[0] else np.nan
            ga_lp = g_all[2] / g_all[0] if g_all[0] else np.nan
            for l_, keys in linien.items():
                s = abst[l_].get(keys[i])
                eigen = abst_pferd.get((keys[i], hid[i])) if l_ == "dam" else None
                if s is not None and eigen is not None:
                    s = [a_ - b_ for a_, b_ in zip(s, eigen)]
                if s is None or not s[0]:
                    continue
                sc = _score(s[1], s[2], s[3], s[4], s[0], ga_rp, ga_lp)
                F[f"{l_}_score"][i] = (s[0] * sc + ABST_K * 100) / (s[0] + ABST_K) if not np.isnan(sc) else np.nan
                F[f"{l_}_epr"][i] = 100 * (s[4] / s[0]) / ga_lp if ga_lp else np.nan
                F[f"{l_}_val3"][i] = 100 * (s[6] / s[5]) / (g_all[4] / g_all[3]) if s[5] and g_all[3] else np.nan
                F[f"{l_}_runs"][i] = s[0]
                if l_ == "dam":
                    continue
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
        for i in pos[~hm[pos] & (ext_[pos] == 0)]:          # externe Läufe zählen nicht für Verbindungen/Basis
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
                if l_ == "dam":
                    e_ = abst_pferd.setdefault((keys[i], hid[i]), [0, 0.0, 0.0, 0.0, 0.0, 0, 0.0])
                    e_[0] += 1; e_[1] += pl_; e_[2] += ex_; e_[3] += rp_; e_[4] += lp_
                    if drei:
                        e_[5] += 1; e_[6] += werte["valeur"][i]
                    continue
                for dim, kk in (("dist", dgrp[i] if alter[i] != 2 else None), ("going", going[i])):
                    if kk is not None:
                        ks = abst_kat[l_][dim].setdefault(keys[i], {}).setdefault(kk, [0, 0.0, 0.0, 0.0, 0.0])
                        ks[0] += 1; ks[1] += pl_; ks[2] += ex_; ks[3] += rp_; ks[4] += lp_
            if konfig[i] is not None and not np.isnan(werte["draw"][i]):
                bs = box.setdefault((konfig[i], werte["draw"][i]), [0, 0.0])
                bs[0] += 1; bs[1] += rp_
    F["trainer_form"] = F["trainer_30_score"] - F["trainer_score"]            # Stall gerade besser/schlechter als im Jahr
    F["jockey_form"] = F["jockey_30_score"] - F["jockey_score"]
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
    kat.update({f"f{k}_typ": v for k, v in f_typ.items()})
    for c, v in kat.items():
        out[c] = v
    out = out.loc[idx[zm]]
    log(f"Merkmale: {len(out):,} Starter × {out.shape[1]} Spalten in {time.time() - t0:.0f} s")
    return out.reindex(ziel_maske[ziel_maske].index)


def _kategorien(X: pd.DataFrame, stufen: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Kategorische Spalten als pandas-Kategorie mit festen Stufen (aus dem Training)."""
    X = X.copy()
    stufen = dict(stufen or {})
    for c in (list(stufen) if stufen else KATEGORISCH):     # gespeichertes Modell: seine eigenen Kategorien
        if c not in X:
            X[c] = None
        werte = X[c].astype(object).where(X[c].notna(), None)
        if c not in stufen:
            stufen[c] = sorted({str(v) for v in werte if v is not None})
        X[c] = pd.Categorical(werte.map(lambda v: str(v) if v is not None else None), categories=stufen[c])
    return X, stufen


def feld_relativ(X: pd.DataFrame, rennen: pd.Series, datum: pd.Series | None = None) -> pd.DataFrame:
    """Je Merkmal aus RELATIV: Rang im Feld (0 = kleinster … 1 = größter Wert, Gleichstand gemittelt) und Abstand zum
    Feldschnitt. Fehlende Werte bleiben NaN und zählen beim Rang und Schnitt nicht mit. rennen: race_id je Zeile von X.
    Dazu Erfahrung im Feld – Anteil der Gegner, die älter sind (feld_aelter) bzw. mehr Starts haben (feld_erfahrener) –
    und mit datum die Jahreszeit (season_doy = Tag im Jahr; z. B. reifen Dreijährige im Lauf der Saison).
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
    for c, name in (("age", "feld_aelter"), ("runs", "feld_erfahrener")):
        if c not in X:
            continue
        v = pd.to_numeric(X[c], errors="coerce")
        g = v.groupby(r)
        anz = g.transform("count")
        mehr = anz - g.rank(method="max")                      # Gegner mit echt größerem Wert
        X[name] = (mehr / (anz - 1)).where(anz > 1)
    if datum is not None:
        X["season_doy"] = pd.to_datetime(pd.Series(np.asarray(datum), index=X.index)).dt.dayofyear.astype(float)
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


def _z_im_rennen(pred, rennen) -> np.ndarray:
    """Vorhersage als z-Wert im eigenen Rennen (so wie Power daraus entsteht)."""
    s = pd.Series(np.asarray(pred, dtype=float))
    g = s.groupby(np.asarray(rennen))
    sd = g.transform("std", ddof=0)
    return ((s - g.transform("mean")) / sd.where(sd > 0)).fillna(0.0).to_numpy()


def _softmax_im_rennen(eta, rennen) -> np.ndarray:
    g = pd.factorize(np.asarray(rennen))[0]
    eta = np.asarray(eta, dtype=float)
    eta = eta - pd.Series(eta).groupby(g).transform("max").to_numpy()
    e = np.exp(eta)
    return e / np.bincount(g, weights=e)[g]


def _a_schaetzen(z, won, rennen, iter_max: int = 50) -> float:
    """Siegchance = Softmax(a × z) je Rennen: a per Maximum-Likelihood (nur Rennen mit genau einem Sieger)."""
    d = pd.DataFrame({"z": z, "w": won, "r": rennen})
    d = d[d.groupby("r")["w"].transform("sum") == 1]
    if d.empty:
        return 1.0
    zz, w, g = d["z"].to_numpy(float), d["w"].to_numpy(float), pd.factorize(d["r"])[0]
    a = 1.0
    for _ in range(iter_max):
        p = _softmax_im_rennen(a * zz, g)
        m1 = np.bincount(g, weights=p * zz)
        grad = (w * zz).sum() - m1.sum()
        hess = -(np.bincount(g, weights=p * zz * zz) - m1 ** 2).sum()
        if hess >= 0:
            break
        schritt = grad / hess
        a -= schritt
        if abs(schritt) < 1e-8:
            break
    return float(a)


def markt_test(pred, rennen, won, odds, a: float | None = None) -> dict:
    """Siegchance aus Power (Softmax(a × z), a geschätzt) gegen den Markt (1/Quote, je Rennen normiert):
    mittlerer Log-Loss des Siegers (kleiner = besser) und bedingtes Logit mit ln(Marktchance) und Power-z.
    power_koef > 0 mit |z| ≥ 2: Power weiß etwas, das die Endquote noch nicht enthält."""
    import hypothesen_backtest as hb
    rennen = np.asarray(rennen).astype(str)
    z = _z_im_rennen(pred, rennen)
    won = np.asarray(won, dtype=float)
    inv = pd.Series(np.where(np.asarray(odds, dtype=float) > 1, 1.0 / np.asarray(odds, dtype=float), np.nan))
    p_mkt = (inv / inv.groupby(rennen).transform("sum")).to_numpy()
    d = pd.DataFrame({"race_id": rennen, "won": won, "z": z, "p_mkt": p_mkt})
    d = d[d.groupby("race_id")["p_mkt"].transform(lambda s: s.notna().all())]       # nur Rennen mit allen Quoten
    d = d[d.groupby("race_id")["won"].transform("sum") == 1]
    if d.empty:
        return {}
    a = _a_schaetzen(d["z"], d["won"], d["race_id"]) if a is None else float(a)   # a vorgegeben: aus der Validierung
    p_mod = _softmax_im_rennen(a * d["z"].to_numpy(), d["race_id"])
    sieger = d["won"].to_numpy() == 1
    d["ln_p"] = np.log(d["p_mkt"])
    cl = hb.clogit(d, ["z"]).set_index("variable")
    return {"rennen": int(d["race_id"].nunique()), "a": round(a, 3),
            "logloss_power": round(float(-np.log(p_mod[sieger]).mean()), 4),
            "logloss_markt": round(float(-np.log(d["p_mkt"].to_numpy()[sieger]).mean()), 4),
            "markt_koef": float(cl.loc["ln p_mkt (Markt)", "koef"]),
            "power_koef": float(cl.loc["z", "koef"]) if "z" in cl.index else None,
            "power_z": float(cl.loc["z", "z"]) if "z" in cl.index else None}


def vorn_stufe(y) -> np.ndarray:
    """Ziel „vorn“ aus dem Platzanteil: 0 hinten, 1 ab 0,7, 2 ab 0,8, 3 ab 0,9, 4 Sieg (Platzanteil 1)."""
    y = np.asarray(y, dtype=float)
    s = sum((y >= g - 1e-9).astype(int) for g in VORN_GRENZEN)
    return np.where(y >= 1 - 1e-9, len(VORN_GRENZEN) + 1, s).astype(int)


def _lgb_daten(lgb, Xk, y, rennen, art, ref=None, init=None):
    """LightGBM-Datensatz; für „rang“/„vorn“ nach Rennen gruppiert (Zeilen eines Rennens hintereinander) mit
    Stufen-Ziel. init: Ausgangswert je Zeile (Segment-Modelle lernen nur die Korrektur dazu)."""
    if art in ("rang", "vorn"):
        stufe = np.rint(y.to_numpy() * RANG_STUFEN).astype(int) if art == "rang" else vorn_stufe(y.to_numpy())
        return lgb.Dataset(Xk, stufe, reference=ref, init_score=init,
                           group=rennen.groupby(rennen, sort=False).size().to_numpy(),
                           categorical_feature=KATEGORISCH, free_raw_data=False)
    return lgb.Dataset(Xk, y, reference=ref, init_score=init, categorical_feature=KATEGORISCH, free_raw_data=False)


def _seg_text(X: pd.DataFrame, spalte: str) -> np.ndarray:
    return X[spalte].astype(object).where(X[spalte].notna(), None).to_numpy() if spalte in X else np.full(len(X), None)


def _seg_datei(stamm: str, s_: str) -> str:
    return f"{stamm}_seg_{str(s_).lower().replace('+', 'plus').replace(' ', '_')}.txt"


def segment_tabelle(df: pd.DataFrame, segment: np.ndarray, spalten: list[str]) -> pd.DataFrame:
    """Prüfung je Segment (Rennart): Rennen, Rangkorrelation und Sieger getroffen für jede Spalte (Modell, Markt …)."""
    zeilen = []
    for s_ in sorted({v for v in segment if v is not None}):
        t = df[segment == s_]
        z = {"segment": s_, "rennen": int(t["race_id"].nunique())}
        for c in spalten:
            b = _bewerten(t, c)
            z[f"korr_{c}"], z[f"sieger_{c}"] = b["rang_korr"], b["sieger_getroffen"]
        zeilen.append(z)
    return pd.DataFrame(zeilen)


def _lgb_params(art, params):
    if art in ("rang", "vorn"):
        return {**LGB_PARAMS, "objective": "lambdarank", "metric": "ndcg", "eval_at": [3],
                "label_gain": RANG_GAIN if art == "rang" else VORN_GAIN, **(params or {})}
    return {**LGB_PARAMS, **(params or {})}


def _merkmale_holen(base, hist, out, X, neu, log):
    """Historie laden (falls nötig) und Merkmale aus dem Zwischenspeicher BASE/modelle/merkmale.parquet holen –
    neu gebaut, wenn er fehlt, veraltet ist (MERKMAL_VERSION) oder nicht zur Historie passt. Rückgabe: hist, X, ordner."""
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
        sf = zwischen.with_name(SCHLUESSEL_DATEI)
        if v != MERKMAL_VERSION:
            log(f"Zwischengespeicherte Merkmale sind von einer älteren Version ({v}) – baue neu.")
            X = None
        elif sf.exists():
            # Zeilen über (race_id, horse_id) zuordnen: neue externe Läufe verschieben die Zeilennummern der Historie
            alt = pd.read_parquet(sf)
            jetzt = pd.Series(hist.index, index=pd.MultiIndex.from_arrays([hist["race_id"].astype(str),
                                                                          hist["horse_id"].astype(str)]))
            jetzt = jetzt[~jetzt.index.duplicated()]
            neu_idx = jetzt.reindex(pd.MultiIndex.from_arrays([alt["race_id"].astype(str), alt["horse_id"].astype(str)]))
            if neu_idx.isna().any():
                log("Zwischengespeicherte Merkmale passen nicht zur Historie – baue neu.")
                X = None
            else:
                X.index = neu_idx.to_numpy().astype(int)
                log(f"Merkmale aus {zwischen} ({len(X):,} Starter; neu bauen mit neu=True)")
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
            hist.loc[X.index, ["race_id", "horse_id"]].astype(str).reset_index(drop=True).to_parquet(
                zwischen.with_name(SCHLUESSEL_DATEI))
            version.write_text(json.dumps({"version": MERKMAL_VERSION}))
    return hist, X, ordner


def aufteilung(tage: pd.Series, beginn, ab: str | None = None, aufwaermen: int | None = None) -> dict:
    """Zeitliche Aufteilung: die ersten `aufwaermen` Tage ab Beginn der Historie (und alles vor `ab`) nur Vorgeschichte,
    die übrigen Renntage nach ANTEILE in lernen / validieren / testen. Rückgabe: Masken und Grenzdaten."""
    tage = pd.to_datetime(pd.Series(tage))
    start = pd.Timestamp(beginn) + pd.Timedelta(days=AUFWAERM_TAGE if aufwaermen is None else aufwaermen)
    if ab:
        start = max(start, pd.Timestamp(ab))
    drin = tage >= start
    tg = np.sort(tage[drin].unique())
    if len(tg) < 3:
        raise ValueError(f"Zu wenige Renntage nach dem Aufwärmen (ab {start:%Y-%m-%d}): {len(tg)}")
    g1 = tg[min(max(int(len(tg) * ANTEILE[0]), 1), len(tg) - 2)]
    g2 = tg[min(max(int(len(tg) * (ANTEILE[0] + ANTEILE[1])), 1), len(tg) - 1)]
    g2 = max(g2, tg[np.searchsorted(tg, g1) + 1])
    t = lambda x: f"{pd.Timestamp(x):%Y-%m-%d}"
    return {"drin": drin.to_numpy(), "lern": (drin & (tage < g1)).to_numpy(),
            "valid": ((tage >= g1) & (tage < g2)).to_numpy(), "test": (tage >= g2).to_numpy(),
            "grenzen": {"aufwaermen_bis": t(start), "lernen": f"{t(tg[0])} – {t(tg[np.searchsorted(tg, g1) - 1])}",
                        "validieren": f"{t(g1)} – {t(tg[np.searchsorted(tg, g2) - 1])}", "testen": f"{t(g2)} – {t(tg[-1])}"},
            "test_ab": t(g2)}


def trainieren(base: Path | None = None, *, hist: pd.DataFrame | None = None, out: Path | None = None,
               X: pd.DataFrame | None = None, params: dict | None = None, runden: int = LGB_RUNDEN,
               ab: str | None = None, neu: bool = False, art: str = "alle", aufwaermen: int | None = None,
               segmente: str | None = None, log=print) -> dict:
    """Einmal trainieren: Merkmale über die ganze Historie; das erste Jahr (AUFWAERM_TAGE) dient nur als Vorgeschichte,
    die übrigen Renntage zeitlich 60/20/20 (ANTEILE): lernen, validieren (Abbruch, Wahl Regression/Rang, Siegchance-a),
    testen (nur Bericht, gegen den Marktfavoriten und das Rating). Danach auf allen Tagen nach dem Aufwärmen neu lernen
    und speichern.

    ab:  zusätzlich erst ab diesem Datum lernen/prüfen (z. B. "2024-01-01"). Die Merkmale nutzen trotzdem die ganze
         Historie davor (Form, Verbindungen, Abstammung).
    neu: Merkmale neu bauen, auch wenn BASE/modelle/merkmale.parquet schon da ist (nötig nach neuen Renntagen).
    art: "regression" (Platzanteil je Pferd schätzen), "rang" (LightGBM lambdarank: Reihenfolge im ganzen Feld lernen),
         "vorn" (lambdarank nur über die Spitze: Platzanteil ≥ 0,7/0,8/0,9 und Sieg, hinten alles gleich), "beide"
         (regression + rang) oder "alle" – geprüft werden die genannten, gespeichert wird das mit dem kleinsten
         Log-Loss der Siegchance auf der Validierung (Rangkorrelation nur zur Information).
    segmente: "racetype" oder "age_group" – je Segment ein Zusatzmodell, das nur die Korrektur zum gemeinsamen Modell
         lernt; behalten nur, wo es auf der Validierung die Rangkorrelation um SEG_MIN_GEWINN verbessert. Der Bericht
         zeigt je Segment gemeinsam gegen mit Segment-Modell (Validierung und Test)."""
    import lightgbm as lgb
    if segmente is not None and segmente not in SEGMENT_SPALTEN:
        raise ValueError(f"segmente: eins von {SEGMENT_SPALTEN}")
    hist, X, ordner = _merkmale_holen(base, hist, out, X, neu, log)
    y = ziel(hist).reindex(X.index)
    ok = y.notna()
    X, y = X[ok], y[ok]
    X = feld_relativ(X, hist.loc[X.index, "race_id"], hist.loc[X.index, "date"])
    tage = pd.to_datetime(hist.loc[X.index, "date"])
    log("Abdeckung je Jahr (% der Starter mit Wert):")
    log(abdeckung(X, tage).to_string())
    auf = aufteilung(tage, rc.historie_beginn(hist), ab, aufwaermen)
    X, y, tage = X[auf["drin"]], y[auf["drin"]], tage[auf["drin"]]
    # nach Datum und Rennen sortieren: für „rang“ müssen die Zeilen eines Rennens zusammenstehen
    rennen = hist.loc[X.index, "race_id"].astype(str)
    reihe = pd.DataFrame({"t": tage, "r": rennen}).sort_values(["t", "r"], kind="stable").index
    X, y, tage, rennen = X.loc[reihe], y.loc[reihe], tage.loc[reihe], rennen.loc[reihe]
    auf = aufteilung(tage, rc.historie_beginn(hist), ab, aufwaermen)
    lern, valid, test = auf["lern"], auf["valid"], auf["test"]
    Xk, stufen = _kategorien(X)
    gr = auf["grenzen"]
    log(f"Aufwärmen bis {gr['aufwaermen_bis']} (nur Vorgeschichte) · lernen {gr['lernen']}: {int(lern.sum()):,} Starter · "
        f"validieren {gr['validieren']}: {int(valid.sum()):,} · testen {gr['testen']}: {int(test.sum()):,}")

    def tafel(maske):
        return pd.DataFrame({"race_id": rennen[maske].to_numpy(), "y": y[maske].to_numpy(),
                             "markt": -pd.to_numeric(hist.loc[X.index[maske], "odds_final"], errors="coerce").to_numpy(),
                             "rating": X.loc[maske, "rating_adj"].to_numpy()})
    pv, pt = tafel(valid), tafel(test)
    arten = list(ARTEN) if art == "alle" else ["regression", "rang"] if art == "beide" else [art]
    if any(a_ not in ARTEN for a_ in arten):
        raise ValueError(f"art: eins von {ARTEN}, 'beide' oder 'alle'")
    bericht: dict = {}
    validierung: dict = {}
    modelle = {}
    for a_ in arten:
        p = _lgb_params(a_, params)
        d_lern = _lgb_daten(lgb, Xk[lern], y[lern], rennen[lern], a_)
        d_val = _lgb_daten(lgb, Xk[valid], y[valid], rennen[valid], a_, ref=d_lern)
        m = lgb.train(p, d_lern, num_boost_round=runden, valid_sets=[d_val],
                      callbacks=[lgb.early_stopping(100, first_metric_only=True, verbose=False)])
        best = int(m.best_iteration or runden)
        pv[a_] = m.predict(Xk[valid], num_iteration=best)
        pt[a_] = m.predict(Xk[test], num_iteration=best)
        mv_ = markt_test(pv[a_].to_numpy(), pv["race_id"].to_numpy(), hist.loc[X.index[valid], "won"].to_numpy(),
                         hist.loc[X.index[valid], "odds_final"].to_numpy())
        mt_ = markt_test(pt[a_].to_numpy(), pt["race_id"].to_numpy(), hist.loc[X.index[test], "won"].to_numpy(),
                         hist.loc[X.index[test], "odds_final"].to_numpy(), a=mv_.get("a"))
        kurz = lambda m_: {"logloss": m_.get("logloss_power"), "power_z": round(m_["power_z"], 1)
                           if m_.get("power_z") is not None else None}
        validierung[f"modell ({a_})"] = {**_bewerten(pv, a_), **kurz(mv_), "baeume": best}
        bericht[f"modell ({a_})"] = {**_bewerten(pt, a_), **kurz(mt_), "baeume": best}
        modelle[a_] = (m, best, p)
    bericht["markt (Endquote)"] = _bewerten(pt, "markt")
    bericht["rating (bereinigt)"] = _bewerten(pt, "rating")
    # Wahl auf der Validierung: kleinster Log-Loss der Siegchance (das, wofür Power am Ende gebraucht wird); die
    # Rangkorrelation über das ganze Feld belohnt auch die Reihenfolge hinten und benachteiligte „vorn“
    sieger = min(arten, key=lambda a_: validierung[f"modell ({a_})"].get("logloss") or np.inf)
    m, best, p = modelle[sieger]
    # Segment-Modelle: Korrektur zum gemeinsamen Modell je Rennart, nur wo sie auf der Validierung hilft
    spalte_p = sieger
    seg_bericht, seg_behalten = {}, {}
    if segmente:
        sv = _seg_text(X, segmente)
        roh = m.predict(Xk, num_iteration=best, raw_score=True)
        korr = roh.copy()
        ps = {**p, **SEG_PARAMS}
        bew = lambda maske, w: _bewerten(pd.DataFrame({"race_id": rennen[maske].to_numpy(), "y": y[maske].to_numpy(),
                                                       "x": w}), "x")["rang_korr"]
        for s_ in sorted({v for v in sv if v is not None}):
            ms = sv == s_
            l_, v_, t_ = lern & ms, valid & ms, test & ms
            if l_.sum() < SEG_MIN_STARTER or not v_.any() or not t_.any():
                seg_bericht[s_] = {"starter_lernen": int(l_.sum()), "behalten": False, "grund": "zu wenige Starter"}
                continue
            d_l = _lgb_daten(lgb, Xk[l_], y[l_], rennen[l_], sieger, init=roh[l_])
            d_v = _lgb_daten(lgb, Xk[v_], y[v_], rennen[v_], sieger, ref=d_l, init=roh[v_])
            sm = lgb.train(ps, d_l, num_boost_round=runden, valid_sets=[d_v],
                           callbacks=[lgb.early_stopping(100, first_metric_only=True, verbose=False)])
            b_ = int(sm.best_iteration or 0)
            delta = sm.predict(Xk[ms], num_iteration=b_, raw_score=True) if b_ else np.zeros(int(ms.sum()))
            neu_ = roh.copy()
            neu_[ms] += delta
            vb, vs, tb, ts = bew(v_, roh[v_]), bew(v_, neu_[v_]), bew(t_, roh[t_]), bew(t_, neu_[t_])
            halten = b_ > 0 and vb is not None and vs is not None and vs - vb >= SEG_MIN_GEWINN
            seg_bericht[s_] = {"starter_lernen": int(l_.sum()), "baeume": b_, "valid_gemeinsam": vb, "valid_segment": vs,
                               "test_gemeinsam": tb, "test_segment": ts, "behalten": bool(halten)}
            if halten:
                korr[ms] = neu_[ms]
                seg_behalten[s_] = b_
        if seg_behalten:
            pv["segment"], pt["segment"] = korr[valid], korr[test]
            spalte_p = "segment"
            validierung["modell (mit Segmenten)"] = _bewerten(pv, "segment")
            bericht["modell (mit Segmenten)"] = _bewerten(pt, "segment")
        bericht["segmente"] = {"spalte": segmente, "je_segment": seg_bericht}
    # Prüfung je Rennart (gemeinsames Modell bzw. mit Segment-Modellen gegen die Endquote)
    je_art = {}
    for sp in SEGMENT_SPALTEN:
        st = segment_tabelle(pt, _seg_text(X, sp)[test], [spalte_p, "markt"])
        je_art[sp] = st.to_dict("records")
    bericht["je_rennart"] = je_art
    # Siegchance aus Power: a auf der Validierung geschätzt, Test gegen den Markt mit diesem a
    mv = markt_test(pv[spalte_p].to_numpy(), pv["race_id"].to_numpy(), hist.loc[X.index[valid], "won"].to_numpy(),
                    hist.loc[X.index[valid], "odds_final"].to_numpy())
    validierung["markt_test"] = mv
    bericht["markt_test"] = markt_test(pt[spalte_p].to_numpy(), pt["race_id"].to_numpy(),
                                       hist.loc[X.index[test], "won"].to_numpy(),
                                       hist.loc[X.index[test], "odds_final"].to_numpy(), a=mv.get("a"))
    # Rote Starter (Power ≤ 95): wie oft gewinnen / platzieren sie sich? (fürs Weglassen in der Claude-JSON)
    pw_test = 100 + 10 * _z_im_rennen(pt[spalte_p].to_numpy(), pt["race_id"].to_numpy())
    rot = pw_test <= ROT_AB
    w_t = pd.to_numeric(hist.loc[X.index[test], "won"], errors="coerce").fillna(0).to_numpy() == 1
    p_t = pd.to_numeric(hist.loc[X.index[test], "placed"], errors="coerce").fillna(0).to_numpy() == 1
    bericht["rot"] = {"anteil_starter": round(float(rot.mean()), 3),
                      "anteil_sieger": round(float(rot[w_t].mean()), 3) if w_t.any() else None,
                      "anteil_platz": round(float(rot[p_t].mean()), 3) if p_t.any() else None}
    bericht.update({"gewaehlt": sieger, "test_ab": auf["test_ab"], "aufteilung": gr, "ab": ab,
                    "validierung": validierung})
    log("Validierung (Abbruch, Modellwahl, Siegchance-a):")
    for k, v in validierung.items():
        log(f"  {k}: {v}")
    log("Test (unberührt, je Rennen):")
    for k, v in bericht.items():
        if k not in ("validierung", "aufteilung", "segmente", "je_rennart"):
            log(f"  {k}: {v}")
    for sp, zeilen in je_art.items():
        log(f"  Test je {'Renntyp' if sp == 'racetype' else 'Altersgruppe'} (Modell gegen Endquote):")
        log(pd.DataFrame(zeilen).to_string(index=False))
    if segmente:
        log(f"  Segment-Modelle je {segmente} (Rangkorrelation gemeinsam → mit Segment-Modell):")
        log(pd.DataFrame(seg_bericht).T.to_string())
    imp = pd.Series(m.feature_importance("gain"), index=Xk.columns).sort_values(ascending=False)
    log(f"Wichtigste Merkmale ({sieger}, Gain): " + ", ".join(f"{k} {v / imp.sum():.1%}" for k, v in imp.head(15).items()))
    # endgültig: alle Tage nach dem Aufwärmen, gleiche Baumzahl
    final = lgb.train(p, _lgb_daten(lgb, Xk, y, rennen, sieger), num_boost_round=best)
    ordner.mkdir(parents=True, exist_ok=True)
    final.save_model(str(ordner / MODELL_DATEI))
    for alt in ordner.glob(_seg_datei(Path(MODELL_DATEI).stem, "*")):        # alte Segment-Modelle weg
        alt.unlink()
    seg_meta = None
    if seg_behalten:
        roh_f = final.predict(Xk, raw_score=True)
        sv = _seg_text(X, segmente)
        seg_meta = {"spalte": segmente, "modelle": {}}
        for s_, b_ in seg_behalten.items():
            ms = sv == s_
            sm = lgb.train({**p, **SEG_PARAMS}, _lgb_daten(lgb, Xk[ms], y[ms], rennen[ms], sieger, init=roh_f[ms]),
                           num_boost_round=b_)
            datei = _seg_datei(Path(MODELL_DATEI).stem, s_)
            sm.save_model(str(ordner / datei))
            seg_meta["modelle"][s_] = datei
        log(f"Segment-Modelle gespeichert ({segmente}): {', '.join(seg_meta['modelle'])}")
    meta = {"spalten": list(Xk.columns), "stufen": stufen, "art": sieger, "bericht": bericht, "segmente": seg_meta,
            "sieg_a": mv.get("a", 1.0),
            "wichtig": {k: round(float(v / imp.sum()), 4) for k, v in imp.head(30).items()},
            "trainiert": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), "starter": int(len(X))}
    (ordner / META_DATEI).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Modell gespeichert ({sieger}): {ordner / MODELL_DATEI}")
    return bericht


# --------------------------------------------------------------------------
# Zweites Modell: Value (A/E Platz gegen den Markt)
# --------------------------------------------------------------------------
def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def wert_tabelle(f, placed, exp_place, won, p_sieg, stufen: int = WERT_STUFEN) -> pd.DataFrame:
    """Starter nach vorhergesagtem Value-Faktor in gleich große Gruppen (1 = niedrigster): je Gruppe Anzahl,
    Ø Faktor, tatsächliche A/E Platz (Platzierte / erwartete Platzierte laut Endquote), A/E Sieg und A/E Kombi
    ((Siege + Platzierte) / (erwartete Siege + erwartete Platzierte) – ein Sieg zählt doppelt)."""
    d = pd.DataFrame({"f": f, "pl": placed, "ep": exp_place, "w": won, "pw": p_sieg}).dropna()
    d["gruppe"] = pd.qcut(d["f"].rank(method="first"), stufen, labels=False) + 1
    g = d.groupby("gruppe")
    return pd.DataFrame({"starter": g.size(), "faktor": np.exp(g["f"].mean()).round(2),
                         "ae_platz": (g["pl"].sum() / g["ep"].sum()).round(3),
                         "ae_sieg": (g["w"].sum() / g["pw"].sum()).round(3),
                         "ae_kombi": ((g["pl"].sum() + g["w"].sum()) / (g["ep"].sum() + g["pw"].sum())).round(3)})


def _kalibrieren(f, basis, y, iter_max: int = 50) -> float:
    """Eichung des Value-Modells: Platzchance = sigmoid(Markt-log-odds + k × f), k per Maximum-Likelihood auf der
    Validierung. k < 1 heißt: das Modell war zu selbstbewusst, der geeichte Faktor exp(k × f) liegt näher an 1."""
    f, basis, y = (np.asarray(v, dtype=float) for v in (f, basis, y))
    k = 1.0
    for _ in range(iter_max):
        q = 1 / (1 + np.exp(-(basis + k * f)))
        grad, hess = ((y - q) * f).sum(), -(q * (1 - q) * f * f).sum()
        if hess >= 0:
            break
        schritt = grad / hess
        k -= schritt
        if abs(schritt) < 1e-8:
            break
    return float(k)


def _kalibrieren_poisson(f, basis, y, iter_max: int = 50) -> float:
    """Eichung für das Kombi-Ziel: Erwartung = exp(basis + k × f) (Poisson), k per Maximum-Likelihood."""
    f, basis, y = (np.asarray(v, dtype=float) for v in (f, basis, y))
    k = 1.0
    for _ in range(iter_max):
        mu = np.exp(basis + k * f)
        grad, hess = ((y - mu) * f).sum(), -(mu * f * f).sum()
        if hess >= 0:
            break
        schritt = grad / hess
        k -= schritt
        if abs(schritt) < 1e-8:
            break
    return float(k)


def rendite_tabelle(f, won, odds, gruppe=None, anteile=WERT_TOP) -> pd.DataFrame:
    """Gedachte Siegwette 1 € zur Endquote auf die obersten Anteile des Value-Faktors: Wetten, Siege, Trefferquote,
    Ø Quote, Rendite je 1 € (Gewinn − Einsatz). Mit gruppe: dieselbe Rechnung je Gruppe für den ersten Anteil."""
    d = pd.DataFrame({"f": f, "w": won, "q": odds}).dropna()
    d = d[d["q"] > 1]
    if gruppe is not None:
        d["g"] = pd.Series(gruppe).reindex(d.index)
    zeilen = []

    def zeile(name, t):
        return {"auswahl": name, "wetten": len(t), "siege": int(t["w"].sum()),
                "treffer": round(float(t["w"].mean()), 3) if len(t) else None,
                "quote_o": round(float(t["q"].mean()), 1) if len(t) else None,
                "rendite": round(float((t["w"] * t["q"]).sum() / len(t) - 1), 3) if len(t) else None}
    if gruppe is None:
        zeilen.append(zeile("alle", d))
        for a in anteile:
            zeilen.append(zeile(f"oberste {round(a * 100)} %", d[d["f"] >= d["f"].quantile(1 - a)]))
    else:
        top = d[d["f"] >= d["f"].quantile(1 - anteile[0])]
        for g_, t in top.groupby("g", sort=True, observed=True):      # Kategorien (Quotenbereiche) in ihrer Reihenfolge
            zeilen.append(zeile(str(g_), t))
    return pd.DataFrame(zeilen)


def morgen_merkmale(zeilen: pd.DataFrame) -> pd.DataFrame:
    """Merkmale aus der Morgenquote (odds_morning) je Starter: Marktchance (1/Quote, je Rennen auf Summe 1), log-Quote,
    Quotenrang im Feld (0 = Favorit … 1 = Außenseiter) und Marge des Rennens (Σ 1/Quote). Nur fürs Value-Modell."""
    q = pd.to_numeric(_spalte(zeilen, "odds_morning"), errors="coerce").astype(float)
    q = q.where((q > 1) & (q < 1000))
    rid = zeilen["race_id"].astype(str)
    inv = 1 / q
    summe = inv.groupby(rid).transform("sum").where(inv.notna())
    rang = inv.groupby(rid).rank(ascending=False, method="average")
    n = inv.notna().groupby(rid).transform("sum")
    return pd.DataFrame({"m_pm": inv / summe, "m_log": np.log(q), "m_rk": ((rang - 1) / (n - 1)).where(n > 1),
                         "m_marge": summe}, index=zeilen.index)


def trainieren_wert(base: Path | None = None, *, hist: pd.DataFrame | None = None, out: Path | None = None,
                    X: pd.DataFrame | None = None, params: dict | None = None, runden: int = LGB_RUNDEN,
                    ab: str | None = None, neu: bool = False, ziel_art: str = "platz", aufwaermen: int | None = None,
                    segmente: str | None = None, morgenquote: bool = True, log=print) -> dict:
    """Value-Modell: lernt, wann ein Pferd öfter platziert ist, als seine Endquote erwarten lässt.
    ziel_art="platz": Ziel platziert 0/1 gegen die Platzchance des Marktes (binär, Faktor ≈ A/E Platz).
    ziel_art="kombi": Ziel Sieg + Platz (Sieger = 2, Platzierter = 1, sonst 0) gegen Siegchance + Platzchance des
    Marktes (Poisson, Faktor ≈ A/E Kombi) – ein Sieg zählt doppelt, das Signal bleibt dank der Plätze stabil.
    Ziel: platziert (0/1); Ausgangswert je Starter: die Platzchance des Marktes (exp_place, Harville aus der Endquote) –
    LightGBM lernt nur die Abweichung davon. Die Endquote ist nur im Lern-Ziel, nie Merkmal; als Marktmerkmal dient
    höchstens die Morgenquote (morgenquote=True, am Morgen bekannt). Merkmale wie Power (Zwischenspeicher), gleiche Aufteilung
    (Aufwärmen, 60/20/20): Abbruch, Eichung und Gold-Grenze auf der Validierung; Bericht (A/E je Fünftel, Rendite,
    bedingtes Logit Sieg mit Markt + Value) nur auf den Testtagen.
    morgenquote=True: zusätzlich Merkmale aus der Morgenquote (MORGEN_MERKMALE) – das Modell lernt so, wo der Markt am
    Morgen danebenliegt; Ziel bleibt der Vergleich mit der Endquote. Die Karte braucht dann die Morgenquote."""
    import lightgbm as lgb
    import hypothesen_backtest as hb
    if segmente is not None and segmente not in SEGMENT_SPALTEN:
        raise ValueError(f"segmente: eins von {SEGMENT_SPALTEN}")
    hist, X, ordner = _merkmale_holen(base, hist, out, X, neu, log)
    if ziel_art not in ("platz", "kombi"):
        raise ValueError("ziel_art: 'platz' oder 'kombi'")
    ep = pd.to_numeric(hist.loc[X.index, "exp_place"], errors="coerce")
    pl = pd.to_numeric(hist.loc[X.index, "placed"], errors="coerce")
    wn = pd.to_numeric(hist.loc[X.index, "won"], errors="coerce")
    q_all = pd.to_numeric(hist["odds_final"], errors="coerce")                # Siegchance des Marktes je Rennen
    inv_all = (1 / q_all).where(q_all > 1)
    ps = (inv_all / inv_all.groupby(hist["race_id"].astype(str)).transform("sum")).reindex(X.index)
    ok = (ep > 0) & (ep < 1) & pl.notna() & ziel(hist).reindex(X.index).notna()
    if ziel_art == "kombi":
        ok &= ps.notna() & wn.notna()
    X = feld_relativ(X[ok], hist.loc[X.index[ok], "race_id"], hist.loc[X.index[ok], "date"])
    if morgenquote:
        X = pd.concat([X, morgen_merkmale(hist.loc[X.index])], axis=1)
    ep, pl, wn, ps = ep[ok], pl[ok], wn[ok], ps[ok]
    tage = pd.to_datetime(hist.loc[X.index, "date"])
    auf = aufteilung(tage, rc.historie_beginn(hist), ab, aufwaermen)
    drin = auf["drin"]
    X, ep, pl, wn, ps, tage = X[drin], ep[drin], pl[drin], wn[drin], ps[drin], tage[drin]
    lern, valid, test = auf["lern"][drin], auf["valid"][drin], auf["test"][drin]
    gr = auf["grenzen"]
    Xk, stufen = _kategorien(X)
    if ziel_art == "kombi":
        y_all, basis = pl + wn, np.log((ep + ps).to_numpy())
        p = {**WERT_PARAMS, "objective": "poisson", **(params or {})}
    else:
        y_all, basis = pl, _logit(ep)
        p = {**WERT_PARAMS, **(params or {})}
    log(f"Value-Modell ({ziel_art}) – Aufwärmen bis {gr['aufwaermen_bis']} · lernen {gr['lernen']}: {int(lern.sum()):,} "
        f"Starter · validieren {gr['validieren']}: {int(valid.sum()):,} · testen {gr['testen']}: {int(test.sum()):,}")
    d_lern = lgb.Dataset(Xk[lern], y_all[lern], init_score=basis[lern], categorical_feature=KATEGORISCH, free_raw_data=False)
    d_val = lgb.Dataset(Xk[valid], y_all[valid], init_score=basis[valid], reference=d_lern, categorical_feature=KATEGORISCH,
                        free_raw_data=False)
    m = lgb.train(p, d_lern, num_boost_round=runden, valid_sets=[d_val],
                  callbacks=[lgb.early_stopping(100, verbose=False)])
    best = int(m.best_iteration or runden)
    f = m.predict(Xk[test], num_iteration=best, raw_score=True)          # Abweichung vom Markt (log-odds bzw. log)
    f_val = m.predict(Xk[valid], num_iteration=best, raw_score=True)

    def verlust(eta, y):
        if ziel_art == "kombi":
            return float(np.mean(np.exp(eta) - y * eta))
        q = 1 / (1 + np.exp(-eta))
        return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))
    # Segment-Modelle: Korrektur zum gemeinsamen Value-Modell je Rennart, nur wo sie auf der Validierung hilft
    seg_bericht, seg_behalten = {}, {}
    if segmente:
        sv = _seg_text(X, segmente)
        roh = m.predict(Xk, num_iteration=best, raw_score=True)
        korr = roh.copy()
        for s_ in sorted({v for v in sv if v is not None}):
            ms = sv == s_
            l_, v_, t_ = lern & ms, valid & ms, test & ms
            if l_.sum() < SEG_MIN_STARTER or not v_.any() or not t_.any():
                seg_bericht[s_] = {"starter_lernen": int(l_.sum()), "behalten": False, "grund": "zu wenige Starter"}
                continue
            d_l = lgb.Dataset(Xk[l_], y_all[l_], init_score=basis[l_] + roh[l_], categorical_feature=KATEGORISCH,
                              free_raw_data=False)
            d_v = lgb.Dataset(Xk[v_], y_all[v_], init_score=basis[v_] + roh[v_], reference=d_l,
                              categorical_feature=KATEGORISCH, free_raw_data=False)
            sm = lgb.train({**p, **SEG_PARAMS}, d_l, num_boost_round=runden, valid_sets=[d_v],
                           callbacks=[lgb.early_stopping(100, verbose=False)])
            b_ = int(sm.best_iteration or 0)
            neu_ = roh.copy()
            if b_:
                neu_[ms] += sm.predict(Xk[ms], num_iteration=b_, raw_score=True)
            yv, yt = y_all[v_].to_numpy(), y_all[t_].to_numpy()
            vb, vs = verlust(basis[v_] + roh[v_], yv), verlust(basis[v_] + neu_[v_], yv)
            tb, ts = verlust(basis[t_] + roh[t_], yt), verlust(basis[t_] + neu_[t_], yt)
            halten = b_ > 0 and (vb - vs) / vb >= SEG_MIN_VERLUST
            seg_bericht[s_] = {"starter_lernen": int(l_.sum()), "baeume": b_, "valid_gemeinsam": round(vb, 5),
                               "valid_segment": round(vs, 5), "test_gemeinsam": round(tb, 5), "test_segment": round(ts, 5),
                               "behalten": bool(halten)}
            if halten:
                korr[ms] = neu_[ms]
                seg_behalten[s_] = b_
        if seg_behalten:
            f, f_val = korr[test], korr[valid]

    # Güte des Lern-Ziels: Markt allein gegen Markt + Value-Modell (Platz: Log-Loss, Kombi: Poisson-Abweichung)
    def ll(eta):
        y = y_all[test].to_numpy()
        if ziel_art == "kombi":
            mu = np.exp(eta)
            return float(np.mean(mu - y * eta))
        q = 1 / (1 + np.exp(-eta))
        return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))
    # Sieg: Marktchance aus der Endquote, bedingtes Logit mit Value-z
    rennen = hist.loc[X.index[test], "race_id"].astype(str).to_numpy()
    odds = pd.to_numeric(hist.loc[X.index[test], "odds_final"], errors="coerce").to_numpy()
    inv = pd.Series(np.where(odds > 1, 1 / odds, np.nan))
    p_sieg = (inv / inv.groupby(rennen).transform("sum")).to_numpy()
    won = pd.to_numeric(hist.loc[X.index[test], "won"], errors="coerce").to_numpy()
    tab = wert_tabelle(f, pl[test].to_numpy(), ep[test].to_numpy(), won, p_sieg)
    # Rendite zur echten Endquote (mit Marge des Totalisators) und Aufteilung der obersten 10 %
    rt = rendite_tabelle(f, won, odds)
    typ = np.array([v if v is not None else "unbekannt" for v in _seg_text(X, "racetype")[test]], dtype=object)
    q_st = pd.cut(odds, QUOTEN_STUFEN, right=False,
                  labels=[f"{a}–{b}" if b < 1000 else f"≥ {a}" for a, b in zip(QUOTEN_STUFEN[:-1], QUOTEN_STUFEN[1:])])
    monat = tage[test].dt.strftime("%Y-%m").to_numpy()
    teil = {"renntyp": rendite_tabelle(f, won, odds, typ, [0.10]),
            "quote": rendite_tabelle(f, won, odds, q_st, [0.10]),
            "monat": rendite_tabelle(f, won, odds, monat, [0.10])}
    # Eichung: geeichter Faktor exp(k × f); goldener Rahmen ab der Grenze der obersten WERT_GOLD – beides auf der
    # Validierung, damit der Test unberührt bleibt
    k_ = (_kalibrieren_poisson if ziel_art == "kombi" else _kalibrieren)(f_val, basis[valid], y_all[valid].to_numpy())
    gold_ab = float(np.quantile(f_val, 1 - WERT_GOLD))
    warn_ab = float(np.quantile(f_val, 1 / WERT_STUFEN))                   # Grenze des untersten Fünftels
    gold_test = f >= gold_ab
    d = pd.DataFrame({"race_id": rennen, "won": won, "z": _z_im_rennen(f, rennen), "p_mkt": p_sieg})
    d = d[d.groupby("race_id")["p_mkt"].transform(lambda s_: s_.notna().all())]
    d = d[d.groupby("race_id")["won"].transform("sum") == 1]
    d["ln_p"] = np.log(d["p_mkt"])
    cl = hb.clogit(d, ["z"]).set_index("variable") if len(d) else pd.DataFrame()
    bericht = {"ziel": ziel_art, "baeume": best, f"verlust_{ziel_art}_markt": round(ll(basis[test]), 4),
               f"verlust_{ziel_art}_mit_value": round(ll(basis[test] + f), 4),
               "sieg_value_koef": float(cl.loc["z", "koef"]) if "z" in cl.index else None,
               "sieg_value_z": float(cl.loc["z", "z"]) if "z" in cl.index else None,
               "fuenftel": tab.reset_index().to_dict("records"),
               "rendite": rt.to_dict("records"), "rendite_top10": {k: v.to_dict("records") for k, v in teil.items()},
               "kalib_k": round(k_, 3), "gold_ab_roh": round(gold_ab, 4),
               "gold_ab_faktor": round(float(np.exp(k_ * gold_ab)), 3),
               "gold_test": {"anteil": round(float(gold_test.mean()), 3),
                             **(rendite_tabelle(f[gold_test], won[gold_test], odds[gold_test], None, [1.0])
                                .iloc[0].to_dict() if gold_test.any() else {})},
               "test_ab": auf["test_ab"], "aufteilung": gr, "ab": ab}
    # Prüfung je Rennart: A/E im untersten und obersten Fünftel (Fünftel über alle Testtage) und Gold-Rendite
    fuenf = pd.qcut(pd.Series(f).rank(method="first"), WERT_STUFEN, labels=False).to_numpy() + 1
    pl_t, ep_t = pl[test].to_numpy(), ep[test].to_numpy()
    je_art = {}
    for sp in SEGMENT_SPALTEN:
        sv_t = _seg_text(X, sp)[test]
        zeilen = []
        for s_ in sorted({v for v in sv_t if v is not None}):
            z = {"segment": s_, "starter": int((sv_t == s_).sum())}
            for name, g_ in (("unten", 1), ("oben", WERT_STUFEN)):
                mk = (sv_t == s_) & (fuenf == g_) & np.isfinite(p_sieg) & np.isfinite(won)
                z[f"ae_platz_{name}"] = round(float(pl_t[mk].sum() / ep_t[mk].sum()), 3) if mk.any() else None
                z[f"ae_kombi_{name}"] = (round(float((pl_t[mk].sum() + won[mk].sum()) / (ep_t[mk].sum() + p_sieg[mk].sum())), 3)
                                         if mk.any() else None)
            g_m = (sv_t == s_) & gold_test
            z["gold_wetten"] = int(g_m.sum())
            z["gold_rendite"] = (rendite_tabelle(f[g_m], won[g_m], odds[g_m], None, [1.0]).iloc[0]["rendite"]
                                 if g_m.any() else None)
            zeilen.append(z)
        je_art[sp] = zeilen
    bericht["je_rennart"] = je_art
    if segmente:
        bericht["segmente"] = {"spalte": segmente, "je_segment": seg_bericht}
    log(f"Value-Modell ({ziel_art}) – Test (unberührt; Eichung und Gold-Grenze aus der Validierung):")
    for k2, v2 in bericht.items():
        if k2 not in ("fuenftel", "rendite", "rendite_top10", "je_rennart", "segmente"):
            log(f"  {k2}: {v2}")
    for sp, zeilen in je_art.items():
        log(f"  Test je {'Renntyp' if sp == 'racetype' else 'Altersgruppe'} (A/E unterstes/oberstes Fünftel, Gold):")
        log(pd.DataFrame(zeilen).to_string(index=False))
    if segmente:
        log(f"  Segment-Modelle je {segmente} (Verlust gemeinsam → mit Segment-Modell, kleiner = besser):")
        log(pd.DataFrame(seg_bericht).T.to_string())
    log("  A/E je Fünftel des Value-Faktors (1 = niedrigster, 5 = höchster):")
    log(tab.to_string())
    log("  Siegwette 1 € zur Endquote (Rendite = Gewinn − Einsatz je 1 €):")
    log(rt.to_string(index=False))
    for name, t in teil.items():
        log(f"  Oberste 10 % nach {name}:")
        log(t.to_string(index=False))
    imp = pd.Series(m.feature_importance("gain"), index=Xk.columns).sort_values(ascending=False)
    log("Wichtigste Merkmale (Value, Gain): " + ", ".join(f"{k} {v / imp.sum():.1%}" for k, v in imp.head(15).items()))
    final = lgb.train(p, lgb.Dataset(Xk, y_all, init_score=basis, categorical_feature=KATEGORISCH), num_boost_round=best)
    ordner.mkdir(parents=True, exist_ok=True)
    final.save_model(str(ordner / WERT_DATEI))
    for alt in ordner.glob(_seg_datei(Path(WERT_DATEI).stem, "*")):          # alte Segment-Modelle weg
        alt.unlink()
    seg_meta = None
    if seg_behalten:
        roh_f = final.predict(Xk, raw_score=True)
        sv = _seg_text(X, segmente)
        seg_meta = {"spalte": segmente, "modelle": {}}
        for s_, b_ in seg_behalten.items():
            ms = sv == s_
            sm = lgb.train({**p, **SEG_PARAMS}, lgb.Dataset(Xk[ms], y_all[ms], init_score=basis[ms] + roh_f[ms],
                                                            categorical_feature=KATEGORISCH), num_boost_round=b_)
            datei = _seg_datei(Path(WERT_DATEI).stem, s_)
            sm.save_model(str(ordner / datei))
            seg_meta["modelle"][s_] = datei
        log(f"Value-Segment-Modelle gespeichert ({segmente}): {', '.join(seg_meta['modelle'])}")
    meta = {"spalten": list(Xk.columns), "stufen": stufen, "bericht": bericht, "kalib_k": k_, "gold_ab": gold_ab,
            "warn_ab": warn_ab, "segmente": seg_meta,
            "ziel": ziel_art, "morgenquote": bool(morgenquote),
            "wichtig": {k: round(float(v / imp.sum()), 4) for k, v in imp.head(30).items()},
            "trainiert": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), "starter": int(len(X))}
    (ordner / WERT_META).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Value-Modell gespeichert: {ordner / WERT_DATEI}")
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
    def seg(meta):                                                           # Segment-Modelle, falls behalten
        sm = (meta.get("segmente") or {}).get("modelle") or {}
        return {s_: lgb.Booster(model_file=str(ordner / d_)) for s_, d_ in sm.items() if (ordner / d_).exists()}
    meta = json.loads((ordner / META_DATEI).read_text(encoding="utf-8"))
    out = {"booster": lgb.Booster(model_file=str(ordner / MODELL_DATEI)), "meta": meta, "segmente": seg(meta)}
    if (ordner / WERT_DATEI).exists() and (ordner / WERT_META).exists():      # Value-Modell, falls trainiert
        wm = json.loads((ordner / WERT_META).read_text(encoding="utf-8"))
        out["wert"] = {"booster": lgb.Booster(model_file=str(ordner / WERT_DATEI)), "meta": wm, "segmente": seg(wm)}
    return out


def _seg_korrektur(modell: dict, X: pd.DataFrame, Xk: pd.DataFrame) -> np.ndarray:
    """Korrektur der Segment-Modelle je Zeile (0, wo es für die Rennart keins gibt)."""
    d = np.zeros(len(Xk))
    sm = modell.get("segmente") or {}
    spalte = (modell["meta"].get("segmente") or {}).get("spalte")
    if not sm or not spalte:
        return d
    sv = _seg_text(X, spalte)
    for s_, b in sm.items():
        ms = sv == s_
        if ms.any():
            d[ms] = b.predict(Xk[ms], raw_score=True)
    return d


def _gruppe(spalte: str) -> str:
    """Anzeigegruppe eines Merkmals: der längste passende Präfix aus GRUPPEN (z. B. arr_best… = Bestform ARR, nicht ARR)."""
    treffer = [(len(pre), name) for pre, name in GRUPPEN if spalte.startswith(pre)]
    if treffer:
        return max(treffer)[1]
    return {"n_runners": "Starterzahl", "distance_m": "Distanz", "going": "Boden", "dist_group": "Distanz",
            "racetype": "Renntyp", "cond_age": "Altersklasse"}.get(spalte, spalte)


def treiber_relativ(beitr: np.ndarray, spalten: list, rennen: np.ndarray, korr: np.ndarray | None = None) -> pd.DataFrame:
    """Merkmalsbeiträge (SHAP, Zeilen × Spalten) je Anzeigegruppe summiert und je Rennen um den Ø der Gruppe
    vermindert: Treiber erklären den Abstand zum heutigen Feld, nicht zum Schnitt aller Starter der Historie."""
    namen = [_gruppe(c) for c in spalten]
    G = pd.DataFrame({g_: beitr[:, [i for i, n_ in enumerate(namen) if n_ == g_]].sum(axis=1) for g_ in sorted(set(namen))})
    if korr is not None and np.any(korr):
        G["Rennart-Korrektur"] = korr
    return G - G.groupby(np.asarray(rennen)).transform("mean")


def vorhersage(hist: pd.DataFrame, heute_zeilen: pd.DataFrame, modell: dict, log=print) -> dict:
    """Power je heutigem Starter: {(race_id, Startnummer): {"p": Power, "pred": Platzanteil (nur beim Regressions-Modell,
    sonst None), "sieg": Siegchance, "wert": Value-Faktor (≈ A/E Platz gegen den Markt; None ohne Value-Modell),
    "treiber": [[Name, Beitrag]]}}.
    heute_zeilen: Spalten wie die Historie (Schlüssel, Gewicht, Rating, Box, Alter, Rennen …), ohne Ergebnis."""
    if modell is None or heute_zeilen is None or not len(heute_zeilen):
        return {}
    hz = heute_zeilen.copy()
    hz.index = [f"heute_{i}" for i in range(len(hz))]
    with warnings.catch_warnings():                # heutige Zeilen ohne Ergebnis: leere Spalten sind gewollt
        warnings.simplefilter("ignore", FutureWarning)
        alle = pd.concat([hist, hz], axis=0, sort=False)
    heute = pd.Series(alle.index.isin(hz.index), index=alle.index)
    X = merkmale(alle, ziel_maske=heute, heute=heute, log=log)
    X = feld_relativ(X, alle.loc[X.index, "race_id"], alle.loc[X.index, "date"])
    meta = modell["meta"]
    Xk, _ = _kategorien(X.reindex(columns=[c for c in meta["spalten"]]), meta["stufen"])
    Xk = Xk[meta["spalten"]]
    korr = _seg_korrektur(modell, X, Xk)                                     # Rennart-Korrektur (Segment-Modelle)
    pred = modell["booster"].predict(Xk) + korr
    beitr = modell["booster"].predict(Xk, pred_contrib=True)[:, :-1]
    out = {}
    df = pd.DataFrame({"race_id": hz["race_id"].astype(str).to_numpy(), "no": hz["saddle_no"].to_numpy(), "pred": pred})
    df["sieg"] = _softmax_im_rennen(meta.get("sieg_a", 1.0) * _z_im_rennen(df["pred"], df["race_id"]), df["race_id"])
    df["wert"], df["gold"], df["warn"] = np.nan, False, False
    if modell.get("wert"):                      # Value-Faktor ≈ erwartete A/E Platz gegen den Markt (exp der Abweichung)
        wm = modell["wert"]["meta"]
        Xw_ = X
        if wm.get("morgenquote"):                  # Value-Modell mit Morgenquote: Merkmale aus den heutigen Zeilen
            mq = morgen_merkmale(alle.loc[X.index])
            Xw_ = pd.concat([X, mq], axis=1)
            if mq["m_pm"].isna().all():
                log("  Value-Modell: keine Morgenquote – Value-Faktor ohne Marktmerkmale (weniger verlässlich)")
        Xw, _ = _kategorien(Xw_.reindex(columns=wm["spalten"]), wm["stufen"])
        fw = (modell["wert"]["booster"].predict(Xw[wm["spalten"]], raw_score=True)
              + _seg_korrektur(modell["wert"], X, Xw[wm["spalten"]]))
        df["wert"] = np.exp(wm.get("kalib_k", 1.0) * fw)                 # geeicht: was auf der Validierung eintrat
        df["gold"] = fw >= wm["gold_ab"] if "gold_ab" in wm else df["wert"] >= 1.2
        # Warnsignal: unterstes Fünftel (Grenze aus der Validierung, ältere Modelle: geeichter Faktor ≤ WARN_FAKTOR)
        df["warn"] = fw <= wm["warn_ab"] if "warn_ab" in wm else df["wert"] <= WARN_FAKTOR
    # Treiber relativ zum Feld: Beitrag je Gruppe minus Ø der Gruppe im Rennen (was alle gleich haben, z. B. „keine
    # Form“ im Debütantenrennen, hebt sich auf – wie bei Power und Siegchance)
    G = treiber_relativ(beitr, meta["spalten"], df["race_id"].to_numpy(), korr)
    for r_, g in df.groupby("race_id"):
        mu, sd = g["pred"].mean(), g["pred"].std(ddof=0)
        for k, z in g.iterrows():
            top = G.loc[k].reindex(G.loc[k].abs().sort_values(ascending=False).index)[:4].items()
            p = 100 + 10 * (z["pred"] - mu) / sd if sd and sd > 0 else 100.0
            out[(r_, int(z["no"]))] = {"p": int(round(p)),
                                       "pred": round(float(z["pred"]), 3) if meta.get("art", "regression") == "regression" else None,
                                       "sieg": round(float(z["sieg"]), 3),
                                       "wert": round(float(z["wert"]), 2) if pd.notna(z["wert"]) else None,
                                       "gold": bool(z["gold"]), "warn": bool(z["warn"]),
                                       "treiber": [[n_, round(v_ * 100, 1)] for n_, v_ in top]}
    return out


# --------------------------------------------------------------------------
# Vorwärts-Test: Protokoll der Karten und laufende Auswertung
# --------------------------------------------------------------------------
def protokollieren(daten: dict, base: Path) -> Path | None:
    """Value-Faktor, goldener Rahmen, Siegchance und Cote der PMU-Prognose je Starter der Karte ins Protokoll
    (BASE/auswertung/value_protokoll.csv). Rennen, die schon drinstehen, werden ersetzt (Karte neu erstellt)."""
    zeilen = []
    for r in daten.get("races", {}).values():
        for x in r.get("runners", []):
            pw = x.get("power") or {}
            if x.get("nr") or pw.get("wert") is None:
                continue
            sel = (x.get("prono") or {}).get("sel") or {}
            zeilen.append({"date": daten.get("date"), "race_id": r.get("race_id"), "saddle_no": x.get("no"),
                           "horse": x.get("horse"), "racetype": r.get("type"), "wert": pw.get("wert"),
                           "gold": bool(pw.get("gold")), "warn": bool(pw.get("warn")), "sieg": pw.get("sieg"),
                           "fair": round(1 / pw["sieg"], 2) if pw.get("sieg") else None,
                           "cote_prono": sel.get("cote_dec"), "festkurs": (x.get("fk") or {}).get("sieg"),
                           "festkurs_platz": (x.get("fk") or {}).get("platz")})
    if not zeilen:
        return None
    pfad = Path(base) / PROTOKOLL
    pfad.parent.mkdir(parents=True, exist_ok=True)
    neu = pd.DataFrame(zeilen)
    if pfad.exists():
        alt = pd.read_csv(pfad, dtype={"race_id": str})
        neu = pd.concat([alt[~alt["race_id"].isin(neu["race_id"])], neu], ignore_index=True)
    neu.sort_values(["date", "race_id", "saddle_no"]).to_csv(pfad, index=False)
    return pfad


def value_auswertung(base: Path, hist: pd.DataFrame | None = None, log=print) -> pd.DataFrame:
    """Vorwärts-Test: Protokoll mit den Ergebnissen der Historie verbinden und gedachte 1-€-Siegwetten auswerten –
    alle Starter, goldener Rahmen, goldener Rahmen mit Prognose-Cote im Bereich QUOTE_BEREICH. Rendite zur Endquote,
    zur Morgenquote und – wenn in der Spalte „festkurs“ eingetragen – zum Festkurs."""
    pfad = Path(base) / PROTOKOLL
    if not pfad.exists():
        log(f"Noch kein Protokoll ({pfad}) – entsteht mit jeder Karte, sobald ein Value-Modell trainiert ist.")
        return pd.DataFrame()
    if hist is None:
        import regel_backtest as rb
        hist = rb.laden(Path(base))
    p = pd.read_csv(pfad, dtype={"race_id": str})
    erg = hist[["race_id", "saddle_no", "won", "placed", "finish_pos", "odds_final", "odds_morning"]].copy()
    erg["race_id"] = erg["race_id"].astype(str)
    d = p.merge(erg, on=["race_id", "saddle_no"], how="inner")
    d = d[d["finish_pos"].notna() | d["won"].notna()]
    lo, hi = QUOTE_BEREICH
    warn = d["warn"].eq(True) if "warn" in d else pd.Series(False, index=d.index)
    auswahl = [("alle", d), ("Warnsignal (unterstes Fünftel)", d[warn]), ("goldener Rahmen", d[d["gold"]]),
               (f"gold · Prognose {lo:g}–{hi:g}", d[d["gold"] & d["cote_prono"].between(lo, hi)]),
               (f"gold · Endquote {lo:g}–{hi:g}", d[d["gold"] & d["odds_final"].between(lo, hi)])]
    zeilen = []
    for name, t in auswahl:
        z = {"auswahl": name, "wetten": len(t), "siege": int(t["won"].sum()) if len(t) else 0,
             "tage": t["date"].nunique() if len(t) else 0}
        for spalte, label in (("odds_final", "endquote"), ("odds_morning", "morgenquote"), ("festkurs", "festkurs")):
            q = pd.to_numeric(t[spalte], errors="coerce") if spalte in t else pd.Series(dtype=float)
            m = q.notna() & (q > 1)
            z[f"rendite_{label}"] = round(float((t.loc[m, "won"] * q[m]).sum() / m.sum() - 1), 3) if m.sum() else None
            if label == "festkurs":
                z["wetten_festkurs"] = int(m.sum())
        zeilen.append(z)
    out = pd.DataFrame(zeilen)
    zeit = f"{d['date'].min()} bis {d['date'].max()}" if len(d) else "–"
    log(f"Vorwärts-Test Value-Modell ({zeit}, {d['race_id'].nunique()} Rennen mit Ergebnis):")
    log(out.to_string(index=False))
    return out


# --------------------------------------------------------------------------
# Verlässlichkeit der Modelle für die Claude-JSON (aus den gespeicherten Trainingsberichten)
# --------------------------------------------------------------------------
def _power_einordnung(luecke: float | None, rennen: int) -> str | None:
    """Klartext zum Abstand der Rangkorrelation Markt − Modell in einem Segment."""
    if luecke is None:
        return None
    t = ("fast so gut wie der Markt" if luecke < 0.025 else "etwas schwächer als der Markt" if luecke < 0.04 else
         "klar schwächer als der Markt – Abweichungen von der Prognose skeptischer sehen")
    return t + (" (wenige Testrennen, unsicher)" if rennen < 200 else "")


def _je_rennart_power(je: dict) -> dict:
    """Power je Renntyp/Altersgruppe auf den Testtagen, kompakt mit Einordnung gegen die Endquote."""
    out = {}
    for sp, zeilen in je.items():
        out[sp] = {}
        for z in zeilen:
            km = next((k for k in z if k.startswith("korr_") and k != "korr_markt"), None)
            sm = next((k for k in z if k.startswith("sieger_") and k != "sieger_markt"), None)
            ko, kmkt = z.get(km), z.get("korr_markt")
            luecke = round(kmkt - ko, 3) if ko is not None and kmkt is not None else None
            out[sp][z["segment"]] = {
                "rennen": z.get("rennen"), "rang_korr": ko, "rang_korr_markt": kmkt,
                "sieger_getroffen": z.get(sm), "sieger_getroffen_markt": z.get("sieger_markt"),
                "einordnung": _power_einordnung(luecke, z.get("rennen") or 0)}
    return out


def _je_rennart_value(je: dict) -> dict:
    """Value je Renntyp/Altersgruppe auf den Testtagen: Warnsignal (A/E unterstes Fünftel), A/E oberstes Fünftel,
    Gold-Rendite zur Endquote, mit Einordnung."""
    out = {}
    for sp, zeilen in je.items():
        out[sp] = {}
        for z in zeilen:
            au, gw, gr_ = z.get("ae_kombi_unten"), z.get("gold_wetten") or 0, z.get("gold_rendite")
            teile = []
            if au is not None:
                teile.append(f"Warnsignal {'verlässlich' if au <= 0.85 else 'schwach'} (A/E unten {au:.2f})")
            if gr_ is not None:
                teile.append(("Gold wenige Fälle, Rendite unsicher" if gw < 300 else
                              "Gold etwa ausgeglichen zur Endquote" if gr_ >= -0.05 else
                              f"Gold verlor im Test deutlich ({gr_:+.0%}) – Value hier nur als Warnsignal nutzen"))
            out[sp][z["segment"]] = {"starter": z.get("starter"), "ae_kombi_unten": au,
                                     "ae_kombi_oben": z.get("ae_kombi_oben"), "gold_wetten": gw, "gold_rendite": gr_,
                                     "einordnung": "; ".join(teile) or None}
    return out


def rennart(typ, alter_klasse=None, alter=None) -> tuple[str | None, str | None]:
    """Renntyp (4 Gruppen) und Altersgruppe eines heutigen Rennens – wie im Modell."""
    a = [v for v in (alter or []) if v is not None and not (isinstance(v, float) and np.isnan(v))]
    return renntyp3(typ), altersgruppe(alter_klasse, min(a) if a else np.nan, max(a) if a else np.nan)


def modell_info(modell: dict | None, vorwaerts: list | None = None) -> dict | None:
    """Kurzfassung der Prüfung beider Modelle mit Einordnung im Klartext – für Claude (Skill rennkarten-durchgang).
    power: Stärke-Einschätzung (blind nutzbar); value: Abweichung vom Markt (nur Marktteil); vorwaerts: laufender
    Vorwärts-Test aus dem Protokoll (value_auswertung), falls vorhanden."""
    if not modell:
        return None
    b = (modell.get("meta") or {}).get("bericht") or {}
    art = b.get("gewaehlt", "regression")
    m, mk, mt = b.get(f"modell ({art})") or b.get("modell") or {}, b.get("markt (Endquote)") or {}, b.get("markt_test") or {}
    z = mt.get("power_z")
    rot = b.get("rot") or {}
    power = {
        "pruefung": {"rennen": m.get("rennen"), "rang_korr": m.get("rang_korr"), "rang_korr_markt": mk.get("rang_korr"),
                     "sieger_getroffen": m.get("sieger_getroffen"), "sieger_getroffen_markt": mk.get("sieger_getroffen"),
                     "markt_test_z": z, "test_ab": b.get("test_ab") or b.get("lernen_bis")},
        "rote_starter": rot or None,
        "einordnung": ("Stärke-Einschätzung aus Form, Kennzahlen, Verbindungen und Abstammung (ohne heutige Quote). "
                       "Ordnet das Feld fast so gut wie die Endquote"
                       + (", weiß aber nichts, was der Markt nicht schon einpreist (Markttest z < 2): als eine Meinung "
                          "neben den Kennzahlen nutzen, nicht als Edge." if z is None or z < 2 else
                          "; der Markttest zeigt Zusatzwissen gegenüber der Endquote (z ≥ 2).")
                       + (f" Rote Starter (Power ≤ {ROT_AB}) stellten auf den Testtagen {rot['anteil_sieger']:.0%} der "
                          f"Sieger bei {rot['anteil_starter']:.0%} der Starter." if rot.get("anteil_sieger") is not None
                          else " Anteil roter Starter an den Siegern: erst nach neuem Training (power_modell.trainieren)."))}
    power["je_rennart"] = _je_rennart_power(b.get("je_rennart") or {})
    out = {"power": power}
    w = modell.get("wert")
    if w:
        bw = (w.get("meta") or {}).get("bericht") or {}
        f5 = bw.get("fuenftel") or []
        rt = {z_["auswahl"]: z_.get("rendite") for z_ in bw.get("rendite") or []}
        zw = bw.get("sieg_value_z")
        out["value"] = {
            "pruefung": {"ziel": bw.get("ziel", "platz"), "sieg_z": zw,
                         "ae_unterstes_fuenftel": {k: f5[0].get(k) for k in ("ae_platz", "ae_sieg", "ae_kombi")} if f5 else None,
                         "ae_oberstes_fuenftel": {k: f5[-1].get(k) for k in ("ae_platz", "ae_sieg", "ae_kombi")} if f5 else None,
                         "rendite_endquote": {k: rt.get(k) for k in ("alle", "oberste 10 %", "oberste 5 %")},
                         "gold_ab_faktor": bw.get("gold_ab_faktor"),
                         "test_ab": bw.get("test_ab") or bw.get("lernen_bis")},
            "einordnung": ("Value-Faktor ≈ wie oft das Pferd im Vergleich zur Erwartung des Marktes ins Geld kommt "
                           "(1 = wie der Markt, geeicht auf die Validierung, geprüft auf unberührten Testtagen). "
                           + ("Signal gegenüber der Endquote belegt (z ≥ 2). " if zw is not None and zw >= 2 else
                              "Signal gegenüber der Endquote nicht belegt. ")
                           + "Warnsignal (warnung, unterstes Fünftel) ist das verlässlichste Value-Signal: der Markt "
                             "überschätzt diese Pferde klar (A/E ≈ 0,7). Goldener Rahmen (oberste 10 %, nur bis "
                             f"Prognose-Cote {GOLD_COTE_MAX:g}) ist ein Hinweis, zur PMU-Endquote im Test ungefähr "
                             "ausgeglichen, darüber klar verlustreich (Außenseiter überwettet) – am ehesten zum Festkurs. "
                             "Nie alleinige Begründung für einen Angle.")}
        out["value"]["je_rennart"] = _je_rennart_value(bw.get("je_rennart") or {})
    if vorwaerts:
        out["vorwaerts_test"] = vorwaerts
    return out
