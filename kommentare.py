"""Kategorien aus den PMU-Kommentaren nach dem Rennen (Spalte comment, französisch, seit Ende August 2026).

Fester Katalog aus Suchmustern statt KI je Kommentar: reproduzierbar, schnell, im Training und auf der Karte gleich.
Je Kommentar 0/1 je Kategorie (kategorien); fürs Modell zählen nur Kommentare zu FRÜHEREN Läufen (kein Blick in die
Zukunft – der Kommentar entsteht erst nach dem Rennen).

    import kommentare as km
    K = km.kategorien(hist["comment"])          # DataFrame 0/1, Index wie hist
    km.uebersicht(hist)                         # Häufigkeit und Ø Platzanteil je Kategorie
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# (Schlüssel, Bedeutung, Suchmuster) – Muster auf den kleingeschriebenen Kommentar, Apostrophe vereinheitlicht
KATEGORIEN = [
    ("start_schlecht", "schlecht gestartet",
     r"mal (?:parti|sorti)e?|lentement des stalles|(?:parti|sorti)e? lentement|(?:manqué|raté) son départ"
     r"|départ (?:manqué|raté|laborieux|difficile)|en retard au départ|surpris au départ|s'est fait surprendre"
     r"|tardé à (?:se mettre|partir)|lent à se mettre en action|dernière? à (?:sortir|quitter)|temps de retard"
     r"|moins bien (?:parti|sorti)e?|(?:parti|sorti)e? moyennement|écart (?:sur sa (?:droite|gauche) )?(?:au départ|à la sortie"
     r"|à l'ouverture)|(?:parti|sorti)e? sur sa (?:droite|gauche) à l'ouverture|cabrée?|hésitation à la sortie"
     r"|restée? dans sa boite|gênée? (?:au départ|à la sortie des stalles)"),
    ("vorne", "vorne / Tempo gemacht",
     r"\ben tête\b|pris la tête|(?:^|grande? |principale? |seule? |co-?)animat(?:eur|rice)|aux avant-postes|a animé"
     r"|animant|a mené|au commandement|imprim\w+ (?:un|le) (?:bon )?(?:rythme|train)|tête et corde"),
    ("hinten", "hinten gelaufen",
     r"queue (?:de|d'un) peloton|arrière du peloton|arrière[- ]garde|lanterne rouge|dernier tiers|fermait la marche"
     r"|^(?:avant-)?derni(?:er|ère)\b"),
    ("ohne_deckung", "ohne Deckung / weiter Weg",
     r"nez au vent|sans abri|sans couverture|sans dos|(?:troisième|quatrième|cinquième) épaisseur(?![^,.]{0,25}(?:abri|caché))"
     r"|largement (?:en )?dehors|perdu du terrain dans le tournant|à flanc de peloton"
     r"|contrainte? (?:de|d') (?:progresser|évoluer|conduire|mener)"),
    ("tempo_langsam", "langsames Rennen",
     r"peu rythmée|rythme (?:très )?(?:lent|modéré|moyen)|train (?:très )?(?:lent|modéré)|faux rythme|sans rythme"
     r"|course tactique|petit train|allure modérée|rythme peu soutenu|sans se presser|train de sénateur"),
    ("tempo_schnell", "schnelles Rennen",
     r"(?<!peu )(?<!très peu )rythmée|rythme (?:très )?(?:soutenu|élevé|rapide)|train (?:très )?(?:soutenu|rapide)"
     r"|train d'enfer|vive allure"),
    ("behindert", "behindert / keine Lücke",
     r"(?<!sans être )(?<!pas été )(?:gêné|bousculé|heurté|chahuté|tassé)e?(?! à un roc)"
     r"|enfermée?|barrée?|sans (?:trouver d'|)ouverture|(?:pas|jamais) (?:pu )?trouvé (?:l'|d'|une )?ouverture"
     r"|n'a trouvé (?:l'|une |d')?ouverture qu|manqué de place|pas eu de place|coudées franches|à contretemps"
     r"|dû reprendre|sans espace|pas de passage|a dû (?:patienter|attendre) (?:pour|avant)|trop tard"
     r"|coincée? (?:derrière|le long|à la corde|entre|contre|dans)|n'a pu se dégager|dans l'impasse"
     r"|contrainte? de (?:le |la )?reprendre|pour éviter (?:un|l')|passage se refermer|dérobade|par une vague"
     r"|serrée? (?:contre|à la corde|le long)|sans pouvoir (?:passer|se frayer)|pas eu (?:toutes )?ses aises"
     r"|bloquée? (?:derrière|le long|à la corde|contre)|temporiser|cherché (?:le|un) passage"),
    ("stark", "stark beendet",
     r"fini fort|terminé fort|fini le plus vite|(?:terminé|fini) en trombe|très bien (?:terminé|fini)"
     r"|remarquablement|superbement|très fort|longue accélération|(?:vivement|très bien|fortement) accéléré"
     r"|fini très vite|regagn\w+ du terrain|plus vite que|beau finish|fourni un (?:bon|bel|gros) effort"),
    ("gut_beendet", "ordentlich beendet",
     r"bien (?:terminé|fini)|(?:terminé|fini) courageusement|très correctement|honorablement|convenablement"
     r"|s'est bien défendue?|bien allongée?"),
    ("nachgelassen", "nachgelassen / abgehängt",
     r"cédé|rend\w* les armes|baiss\w+ pavillon|plafonné|s'est éteinte?|\bcoincer\b|avant de coincer|marqu\w+ le pas"
     r"|\bcalé|décramponnée?|lâchée?\b|faibli|sans réaction|incapable|n'a jamais pu|n'a pu suivre|perdu pied"
     r"|affiché ses limites|nettement dominée?|vite dominée?|net retrait|dans le lointain|à distance|jamais (?:été )?dans le coup"
     r"|(?:terminé|fini|finir|terminer) à son rythme"
     r"|aucun rôle|démunie?|fléchi|craqué|sombré|effondrée?|molli|en perdition"),
    ("unruhig", "unruhig / gezogen / ausgebrochen",
     r"\btendue?\b|a tiré|tirait|ardente?|fougueu|nerveu|difficile à (?:tenir|maîtriser)|en désaccord|bataillé"
     r"|rétif|récalcitrant|a versé|s'est déportée?|a manqué de tenue"),
    ("geschont", "nicht ausgeritten / geschont",
     r"n'insistant|sans insister|n'a pas insisté|ménagée?|(?:sans être|pas été) sollicitée?|laissée? finir"
     r"|pas inutilement|sans (?:être )?(?:poussée?|brusquée?)|ne l'a pas brusqué|n'a pas cherché à"),
    ("problem", "Problem / Zwischenfall",
     r"boiteu|boitill|blessée?|perdu un fer|déferrée?|saign|trébuch|fauté|glissée?|chute|tombée?|accident"
     r"|mal respir|n'a pas aimé le terrain|a buté|perdu l'équilibre|a fait une faute|s'est arrêtée?|a été arrêtée?"
     r"|pulled up|ne s'est pas employée?|désarçonn|se dérober|sauté le passage|problème|incident"),
    ("leicht", "überlegen / leicht",
     r"facilement|aisément|avec autorité|avec facilité|sans être inquiétée?|s'est promenée?|en se jouant|d'autorité"
     r"|sans forcer|bien plus sûrement|impressionn|nettement détachée?|creusé l'écart"),
    ("knapp", "knapp geschlagen",
     r"de peu|d'un rien|du minimum|sur le poteau|sur le fil|in extremis|d'une (?:courte )?(?:tête|encolure)"),
    ("merken", "Hinweis der Kommentatoren (merken)",
     r"à suivre|à revoir|malchanc|sans réussite|n'a pas eu de chance|mérite (?:mieux|un)|vaut mieux"
     r"|à retenir|prometteu|encourageant|plein d'enseignements|peut mieux|bonne rentrée|meilleur que (?:son|sa)"),
]
_RE = [(k, re.compile(m)) for k, _, m in KATEGORIEN]
NAMEN = {k: b for k, b, _ in KATEGORIEN}


def _norm(t) -> str:
    return str(t).lower().replace("’", "'").replace("`", "'") if isinstance(t, str) and t.strip() else ""


def kategorien(texte: pd.Series) -> pd.DataFrame:
    """Je Kommentar 0/1 je Kategorie; ohne Kommentar NaN (unbekannt, nicht „nichts passiert“)."""
    t = texte.map(_norm)
    hat = t.ne("")
    out = pd.DataFrame({k: t.map(lambda s, r=r: float(bool(r.search(s)))) for k, r in _RE}, index=texte.index)
    return out.where(hat)


def uebersicht(d: pd.DataFrame) -> pd.DataFrame:
    """Häufigkeit und Ø Platzanteil (Pos+) je Kategorie – Kontrolle, ob der Katalog trifft, was er soll."""
    k = kategorien(d["comment"])
    n = pd.to_numeric(d["n_runners"], errors="coerce")
    pos = ((n - pd.to_numeric(d["finish_pos"], errors="coerce")) / (n - 1)).where(n > 1).fillna(0)
    zeilen = [{"kategorie": c, "bedeutung": NAMEN[c], "anteil_%": round(100 * k[c].mean(), 1),
               "pos_mit": round(float(pos[k[c] == 1].mean()), 3), "pos_ohne": round(float(pos[k[c] == 0].mean()), 3)}
              for c in k.columns]
    return pd.DataFrame(zeilen)


def beispiele(d: pd.DataFrame, kategorie: str, n: int = 8, seed: int = 0) -> list[str]:
    """Zufällige Kommentare mit Treffer in einer Kategorie (zum Gegenlesen der Muster)."""
    k = kategorien(d["comment"])
    return d.loc[k[kategorie] == 1, "comment"].sample(min(n, int((k[kategorie] == 1).sum())), random_state=seed).tolist()
