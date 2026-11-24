"""Vergleich Bahn/Name im Wett-Skript (agent_wettstar): PMU-Schreibweise der Karte gegen Wettstar-Seite."""
import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parents[1] / "agent_wettstar" / "wettstar-bettor" / "scripts" / "bet_multi.py"
_spec = importlib.util.spec_from_file_location("bet_multi", _p)
bm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bm)


def test_bahn_karte_gegen_wettstar():
    assert bm.bahn_passt("MANS", "Le Mans\nFrankreich")
    assert bm.bahn_passt("SAINT CLOUD", "Saint-Cloud FK")
    assert bm.bahn_passt("MARSEILLE BORELY", "Marseille-Borély")
    assert bm.bahn_passt("Deauville", "Deauville")
    assert not bm.bahn_passt("MARSEILLE BORELY", "Marseille-Vivaux")
    assert not bm.bahn_passt("CHANTILLY", "Deauville")


def test_name_karte_gegen_wettstar():
    assert bm.name_passt(1, "DRACO", "1.Draco(4)")
    assert bm.name_passt(2, "THE CAT'S", "2.The Cat’s (FR)(7)\nJ: X. Muster")
    assert bm.name_passt(3, "LE CHAT BOTTE", "3.Le Chat Botté(1)")
    assert bm.name_passt(14, "SUPERCLASS", "14.Superclass")
    assert not bm.name_passt(1, "DRACO", "11.Draco(4)")       # andere Startnummer
    assert not bm.name_passt(1, "DRACO", "1.Superclass(4)")   # anderes Pferd
