"""Aufbau des Skills rennkarten-durchgang-neu: der ausführende Agent liest nur verdichtete Dateien, nie die Fallsammlung."""
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import skill_paket  # noqa: E402

SKILL = skill_paket.SKILL
REPO = skill_paket.REPO


def test_paket_enthaelt_einsichten_und_keine_fallsammlung(tmp_path):
    skill_paket.main(["skill_paket.py", str(tmp_path)])
    with zipfile.ZipFile(tmp_path / "rennkarten-durchgang-neu.zip") as z:
        namen = {Path(n).relative_to("rennkarten-durchgang-neu").as_posix() for n in z.namelist()}
    assert {"SKILL.md", "EINSICHTEN.md", "DATEN.md", "GLOSSARY.md", "scripts/blatt.py"} <= namen
    assert "FAELLE.md" not in namen


def test_fallsammlung_liegt_im_archiv():
    assert not (SKILL / "FAELLE.md").exists()
    assert (REPO / "docs" / "faelle_rennkarten_durchgang.md").exists()


def test_skill_verweist_auf_einsichten_nicht_auf_faelle():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "EINSICHTEN.md" in text
    assert "faelle" not in text.lower()


def test_automatische_aufgabe_liest_einsichten_nicht_faelle():
    text = (REPO / "claude_projekt" / "aufgabe_durchgang.md").read_text(encoding="utf-8")
    assert "EINSICHTEN.md" in text
    assert "faelle" not in text.lower()


def test_einsichten_nennen_nur_gueltige_gewichte():
    text = (SKILL / "EINSICHTEN.md").read_text(encoding="utf-8")
    gewichte = re.findall(r"\*\*\[([^\]]+)\]\*\*", text)
    assert gewichte, "keine Gewichte in EINSICHTEN.md"
    assert set(gewichte) <= {"ausschlaggebend", "gewichtig", "leicht"}
