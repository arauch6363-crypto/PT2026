"""Französische PMU-Kommentare ins Deutsche übersetzen – nur, wenn es geht.

Übersetzt wird mit DeepL, wenn die Umgebungsvariable DEEPL_API_KEY gesetzt ist (direkt über die API, die
kostenlose reicht), sonst über deep-translator (`pip install deep-translator`) mit Google, als letzter Ausweg MyMemory (mit
MYMEMORY_EMAIL mehr Kontingent). Stößt ein Dienst an ein Limit, wird der nächste genommen. Jede Übersetzung landet
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
LETZTER_FEHLER = ""             # Grund, falls nichts übersetzt werden konnte


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


GOOGLE_PAUSE_S = 0.25           # Google erlaubt etwa 5 Anfragen je Sekunde
SPERRE = ("TooManyRequests", "QuotaExceeded", "AuthorizationException", "ApiKeyException", "ServerException",
          "DeeplFehler")


class DeeplFehler(Exception):
    """Antwort der DeepL-API mit Fehlerstatus (403 Schlüssel abgelehnt, 456 Kontingent erschöpft …)."""


def _deepl(key: str) -> Callable[[str], str]:
    """DeepL direkt über die REST-API (POST, Schlüssel im Header). deep-translator sendet den Schlüssel noch als
    URL-Parameter auth_key – das lehnt DeepL inzwischen mit 403 ab."""
    import requests
    key = key.strip().strip('"').strip("'")
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"   # Free-Schlüssel enden auf ':fx'
    url = f"https://{host}/v2/translate"
    kopf = {"Authorization": f"DeepL-Auth-Key {key}", "Content-Type": "application/json"}

    def uebersetzen(t: str) -> str:
        r = requests.post(url, headers=kopf, json={"text": [t], "source_lang": "FR", "target_lang": "DE"}, timeout=30)
        if r.status_code != 200:
            grund = {403: "Schlüssel abgelehnt (falscher Schlüssel oder Free/Pro vertauscht)",
                     456: "Kontingent erschöpft", 429: "zu viele Anfragen"}.get(r.status_code, "Fehler")
            raise DeeplFehler(f"HTTP {r.status_code} {grund} – {host}: {r.text[:120]}")
        return r.json()["translations"][0]["text"]
    return uebersetzen


def _dienste() -> list[tuple[str, Callable[[str], str]]]:
    """Verfügbare Übersetzungsdienste in Reihenfolge der Qualität:
    DeepL (Umgebungsvariable DEEPL_API_KEY, direkt über die API), Google und MyMemory (über deep-translator,
    MyMemory optional mit MYMEMORY_EMAIL). ImportError nur, wenn weder DeepL noch deep-translator verfügbar ist."""
    import os
    import time
    out = []
    key = os.getenv("DEEPL_API_KEY")
    if key and key.strip():
        out.append(("DeepL", _deepl(key)))
    try:
        from deep_translator import GoogleTranslator, MyMemoryTranslator
    except ImportError:
        if out:
            return out
        raise
    g = GoogleTranslator(source="fr", target="de")

    def google(t: str) -> str:
        time.sleep(GOOGLE_PAUSE_S)
        return g.translate(t)
    out.append(("Google", google))
    m = MyMemoryTranslator(source="french", target="german", email=os.getenv("MYMEMORY_EMAIL"))
    out.append(("MyMemory", m.translate))
    return out


def _standard_uebersetzer() -> Callable[[list[str]], list[str | None]] | None:
    """Übersetzer über deep-translator mit Ausweichen: Stößt ein Dienst an ein Limit oder lehnt ab,
    wird er für den Rest des Laufs übersprungen und der nächste genommen. None, wenn das Paket fehlt."""
    global HINWEIS_GEZEIGT, LETZTER_FEHLER
    try:
        dienste = _dienste()
    except ImportError as e:
        LETZTER_FEHLER = f"deep-translator nicht installiert ({e})"
        if not HINWEIS_GEZEIGT:
            print("Kommentare: keine Übersetzung – `pip install deep-translator` installieren, dann auf Deutsch.")
            HINWEIS_GEZEIGT = True
        return None
    gesperrt: set[str] = set()
    genutzt: dict[str, int] = {}

    def einzeln(t: str) -> str | None:
        global LETZTER_FEHLER
        for name, fn in dienste:
            if name in gesperrt:
                continue
            try:
                de = fn(t)
                if isinstance(de, str) and de.strip():
                    genutzt[name] = genutzt.get(name, 0) + 1
                    return de
            except Exception as e:
                LETZTER_FEHLER = f"{name}: {type(e).__name__}: {str(e)[:160]}"
                if type(e).__name__ in SPERRE or "429" in str(e) or "quota" in str(e).lower():
                    gesperrt.add(name)
                    print(f"Kommentare: {name} nicht nutzbar ({type(e).__name__}: {str(e)[:160]}) – nächster Dienst.")
        return None

    def batch(texte: list[str]) -> list[str | None]:
        return [einzeln(t) for t in texte]
    batch.genutzt = genutzt
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
                quelle = getattr(fn, "genutzt", None)
                print(f"Kommentare: {neu} neu übersetzt ({len(cache)} im Cache)"
                      + (f" – {', '.join(f'{k} {v}' for k, v in quelle.items())}" if quelle else "") + ".")
            if neu < len(offen):
                print(f"Kommentare: {len(offen) - neu} von {len(offen)} nicht übersetzt"
                      + (f" – Grund: {LETZTER_FEHLER}" if LETZTER_FEHLER else ""))
    return {t: cache.get(t) for t in alle}


def pruefen(text: str = "Il a terminé fort à l'extérieur.") -> str | None:
    """Schnelltest: übersetzt einen Satz direkt (ohne Cache) und nennt den Fehler, wenn es nicht klappt."""
    fn = _standard_uebersetzer()
    if fn is None:
        print("Übersetzung nicht möglich:", LETZTER_FEHLER)
        return None
    de = fn([text])[0]
    print(f"{text!r} -> {de!r}" if de else f"Übersetzung fehlgeschlagen: {LETZTER_FEHLER}")
    return de
