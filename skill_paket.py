"""Packt den Skill rennkarten-durchgang-neu als ZIP zum Hochladen in claude.ai (Einstellungen → Skills).

Der Skill nutzt GLOSSARY.md aus dem Repo-Hauptordner; im Paket liegt eine Kopie im Skill-Ordner, damit er auch
außerhalb des Repos vollständig ist.

Aufruf:
    python3 skill_paket.py [ZIELORDNER]      # Standard: dist/
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent
SKILL = REPO / ".claude" / "skills" / "rennkarten-durchgang-neu"
EXTRA = [REPO / "GLOSSARY.md"]
AUSLASSEN = {"__pycache__", ".DS_Store"}


def pruefen(skill_md: Path) -> str:
    """Frontmatter wie von claude.ai verlangt: name (Kleinbuchstaben, Bindestriche, ≤ 64) und description (≤ 1024)."""
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise SystemExit("SKILL.md ohne Frontmatter")
    kopf = m.group(1)
    name = re.search(r"^name:\s*(.+)$", kopf, re.M)
    beschr = re.search(r"^description:\s*\"?(.+?)\"?$", kopf, re.M)
    if not name or not re.fullmatch(r"[a-z0-9-]{1,64}", name.group(1).strip()):
        raise SystemExit("name fehlt oder ist ungültig (nur a-z, 0-9, -; höchstens 64 Zeichen)")
    if not beschr or len(beschr.group(1)) > 1024:
        raise SystemExit("description fehlt oder ist länger als 1024 Zeichen")
    if re.search(r"[<>]", beschr.group(1)):
        raise SystemExit("description darf keine spitzen Klammern (< >) enthalten")
    return name.group(1).strip()


def main(argv: list[str]) -> None:
    ziel = Path(argv[1]) if len(argv) > 1 else REPO / "dist"
    ziel.mkdir(parents=True, exist_ok=True)
    name = pruefen(SKILL / "SKILL.md")
    datei = ziel / f"{name}.zip"
    with zipfile.ZipFile(datei, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(SKILL.rglob("*")):
            if p.is_file() and not (set(p.relative_to(SKILL).parts) & AUSLASSEN) and p.suffix != ".pyc":
                z.write(p, Path(name) / p.relative_to(SKILL))
        for p in EXTRA:
            z.write(p, Path(name) / p.name)
    print(f"{datei} ({datei.stat().st_size // 1024} KB)")
    with zipfile.ZipFile(datei) as z:
        for n in z.namelist():
            print("  ", n)


if __name__ == "__main__":
    main(sys.argv)
