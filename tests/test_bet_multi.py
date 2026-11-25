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


def test_einsatz_achtel_kelly():
    # Kelly = (p·fk − 1)/(fk − 1); 1/8 davon × Bank, auf volle Euro, nie unter dem Mindesteinsatz
    assert bm.einsatz(5, 0.162, 8.5, 174.21) == 5        # Kelly 0,050 → 1,10 € < 5
    assert bm.einsatz(10, 0.30, 6.0, 1000) == 20         # Kelly 0,16 → 20,0 €
    assert bm.einsatz(5, 0.204, 12.0, 400) == 7          # Kelly 0,1316 → 6,58 → 7 €
    assert bm.einsatz(5, 0.25, 5.0, 900) == 7            # Kelly 0,0625 → 7,03 → 7 €
    assert bm.einsatz(5, 0.20, 5.5, 1000) == 5           # Kelly (1,1 − 1)/4,5 = 0,022 → 2,78 € < 5
    assert bm.einsatz(5, None, 9.0, 1000) == 5           # ohne p nur Mindesteinsatz
