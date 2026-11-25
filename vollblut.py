"""Rennen nicht für Vollblüter erkennen (Araber, Anglo-Araber, AQPS) – eine Quelle für Value-Dashboard, Race Card
und Wett-Agent. Nur Standardbibliothek (läuft auch in der geplanten Aufgabe ohne pandas)."""
from __future__ import annotations

import math
import re
from typing import Any

# Rennen nicht für Vollblüter: Araber (Stud-Book arabe, WAHO, ACCAF), Anglo-Araber, AQPS („n'étant pas de race
# pur-sang“) – das Modell kennt nur Vollblüter, solche Rennen zählen im Dashboard nicht und werden nicht gewettet
NICHT_VOLLBLUT = re.compile(
    r"stud[- ]?book\s+(?:anglo[- ])?arabe|anglo[- ]arabe|sang\s+arabe|pur[- ]sang\s+arabe|\bWAHO\b|\bACCAF\b|"
    r"\bAQPS\b|autres?\s+que\s+de\s+pur[- ]sang|(?:n'[ée]tant\s+pas|non)\s+(?:de\s+race\s+)?pur[- ]sang|"
    r"\bARABIAN\b|\bpur[- ]sang\s+arabes?\b", re.I)


def ist_nicht_vollblut(*texte: Any) -> bool:
    """True, wenn Bedingungen, Kategorie oder Rennname auf ein Rennen für Araber/Anglo-Araber/AQPS deuten."""
    return any(NICHT_VOLLBLUT.search(str(t)) for t in texte if t is not None and not (isinstance(t, float) and math.isnan(t)))


def karte_nicht_vollblut(r: dict) -> bool:
    """Rennen der Race Card: Kennzeichen nicht_vollblut (aus der Ausschreibung, mit ist_nicht_vollblut berechnet)
    oder Name/Art/Alter."""
    return bool(r.get("nicht_vollblut")) or ist_nicht_vollblut(r.get("name"), r.get("type"), r.get("age"))
