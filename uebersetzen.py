"""Französische PMU-Kommentare ins Deutsche übersetzen – nur, wenn es geht.

Übersetzt wird mit deep-translator (Google Translate, `pip install deep-translator`). Jede Übersetzung landet
im Cache <BASE>/uebersetzungen_fr_de.json und wird nur einmal abgefragt. Fehlt das Paket oder ist der Dienst
nicht erreichbar, bleibt der Text unübersetzt (Rückgabe None) – die Race Card zeigt dann das Original.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

CACHE = "uebersetzungen_fr_de.json"
BLOCK = 40                      # so viele Texte je Anfrage
MAX_ZEICHEN = 4500              # längere Texte werden nicht übersetzt (Grenze des Dienstes ~5000)

HINWEIS_GEZEIGT = False


def _cache_laden(base: Path | None) -> dict:
    if base is None:
        return {}
    f = Path(base) / CACHE
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        return {}


def _cache_schreiben(base: Path | None, cache: dict) -> None:
    if base is None:
        return
    try:
        (Path(base) / CACHE).write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    except OSError:
        pass


def _standard_uebersetzer() -> Callable[[list[str]], list[str | None]] | None:
    """deep-translator, falls installiert; sonst None."""
    global HINWEIS_GEZEIGT
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        if not HINWEIS_GEZEIGT:
            print("Kommentare: keine Übersetzung – `pip install deep-translator` installieren, dann auf Deutsch.")
            HINWEIS_GEZEIGT = True
        return None
    tr = GoogleTranslator(source="fr", target="de")

    def batch(texte: list[str]) -> list[str | None]:
        try:
            return list(tr.translate_batch(texte))
        except Exception:
            out = []
            for t in texte:                       # einzeln weiter, damit ein fehlerhafter Text nicht alle kostet
                try:
                    out.append(tr.translate(t))
                except Exception:
                    out.append(None)
            return out
    return batch


def uebersetze(texte: Iterable, base: Path | None = None, *,
               uebersetzer: Callable[[list[str]], list[str | None]] | None = None,
               aktiv: bool = True) -> dict[str, str | None]:
    """{französischer Text: deutscher Text oder None}. Bereits übersetzte kommen aus dem Cache."""
    cache = _cache_laden(base)
    alle = sorted({str(t).strip() for t in texte if isinstance(t, str) and str(t).strip()})
    offen = [t for t in alle if t not in cache and len(t) <= MAX_ZEICHEN]
    if offen and aktiv:
        fn = uebersetzer or _standard_uebersetzer()
        if fn is not None:
            neu = 0
            for i in range(0, len(offen), BLOCK):
                teil = offen[i:i + BLOCK]
                try:
                    ergebnis = fn(teil)
                except Exception as e:                # Dienst nicht erreichbar: Rest unübersetzt lassen
                    print(f"Kommentare: Übersetzung abgebrochen ({type(e).__name__}) – Rest bleibt französisch.")
                    break
                for fr, de in zip(teil, ergebnis or []):
                    if isinstance(de, str) and de.strip():
                        cache[fr] = de.strip()
                        neu += 1
            if neu:
                _cache_schreiben(base, cache)
                print(f"Kommentare: {neu} neu übersetzt ({len(cache)} im Cache).")
    return {t: cache.get(t) for t in alle}
