"""Tests für ergebnis_analyse.py: Tagesmaterial der Ergebnisanalyse, Regelprotokoll, Tage und Vorschläge."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ergebnis_analyse as ea  # noqa: E402


def _karte():
    def r(no, fk):
        return {"no": no, "horse": f"H{no}", "fk": {"sieg": fk}, "power": {"sieg": 0.2}}
    return {"date": "2026-11-18", "races": {
        "20261118R1C1": {"race_id": "20261118R1C1", "reunion": 1, "race_no": 1, "time": "13:00", "course": "PAU",
                         "runners": [r(1, 2.0), r(2, 4.0), r(3, 8.0), r(4, 8.0)]},
        "20261118R1C2": {"race_id": "20261118R1C2", "reunion": 1, "race_no": 2, "time": "13:30", "course": "PAU",
                         "runners": [r(1, 2.0), r(2, 4.0), r(3, 4.0)]},
        "20261118R1C3": {"race_id": "20261118R1C3", "reunion": 1, "race_no": 3, "time": "14:00", "course": "PAU",
                         "runners": [r(1, 2.0), r(2, 2.0)]},
    }}


def _kand(no, urteil, fk, pro=(), gegen=(), ausschlag="Ermessen"):
    return {"no": no, "horse": f"H{no}", "urteil": urteil, "fk": fk, "mq": fk - 1, "spanne": [fk - 2, fk - 1],
            "p_modell": 0.3, "value": 0.2, "pro": list(pro), "gegen": list(gegen), "fragen": [], "ausschlag": ausschlag}


def _durchgaenge():
    return {
        # R1C1: Tipp Nr. 3 verliert, abgelehnter Kandidat Nr. 2 gewinnt -> verpasster Sieger
        "20261118R1C1": {"race_id": "20261118R1C1", "status": "bearbeitet", "stand": "2026-11-18T12:20+0100",
                         "vergleich": "3 > 2", "massstab": [{"no": 1, "horse": "H1", "fk": 2.0, "befund": "b"}],
                         "kandidaten": [_kand(3, "wette", 8.0, pro=["CGD (P-CGD)"], ausschlag="Boden (P-CGD)"),
                                        _kand(2, "nein", 4.0, gegen=["ohne Scheuklappen (G-AUSRUESTUNG-WEG)"],
                                              ausschlag="Ausrüstung weg (G-AUSRUESTUNG-WEG)")]},
        # R1C2: Tipp Nr. 2 gewinnt -> Treffer; Maßstab Nr. 1
        "20261118R1C2": {"race_id": "20261118R1C2", "status": "bearbeitet", "stand": "2026-11-18T12:50+0100",
                         "vergleich": "2", "massstab": [{"no": 1, "horse": "H1", "fk": 2.0, "befund": "b"}],
                         "kandidaten": [_kand(2, "klein", 4.0, pro=["Bahn (P-BAHN)"], ausschlag="Ermessen")]},
    }


def _einlauf():
    zeilen = [
        ("20261118R1C1", 1, 3, "PARTANT"), ("20261118R1C1", 2, 1, "PARTANT"), ("20261118R1C1", 3, 2, "PARTANT"),
        ("20261118R1C1", 4, None, "NON_PARTANT"),
        ("20261118R1C2", 1, 2, "PARTANT"), ("20261118R1C2", 2, 1, "PARTANT"), ("20261118R1C2", 3, 3, "PARTANT"),
        ("20261118R1C3", 1, 2, "PARTANT"), ("20261118R1C3", 2, 1, "PARTANT"),
    ]
    return ea.einlauf([{"race_id": r, "saddle_no": no, "horse": f"H{no}", "finish_pos": pos, "status": st,
                        "odds_final": 3.0, "incident": None} for r, no, pos, st in zeilen])


def test_einlauf_sieger_und_nichtstarter():
    e = _einlauf()
    assert e["20261118R1C1"]["sieger"] == [2]
    assert e["20261118R1C1"]["starter"][4]["nichtstarter"] is True
    assert e["20261118R1C1"]["starter"][1]["pos"] == 3


def test_einlauf_dead_heat():
    e = ea.einlauf([{"race_id": "X", "saddle_no": 1, "finish_pos": 1, "status": "PARTANT"},
                    {"race_id": "X", "saddle_no": 2, "finish_pos": 1, "status": "PARTANT"}])
    assert e["X"]["sieger"] == [1, 2]


def test_material_gruppen_und_faelle():
    m = ea.material("20261118", _karte(), _durchgaenge(), _einlauf())
    r1, r2 = m["rennen"]
    assert [s["gruppe"] for s in r1["sieger"]] == ["verpasster_sieger"]
    assert [s["gruppe"] for s in r2["sieger"]] == ["treffer"]
    arten = sorted((f["art"], f["race_id"][-4:], f["no"]) for f in m["faelle"])
    assert arten == [("treffer", "R1C2", 2), ("verlorener_tipp", "R1C1", 3), ("verpasster_sieger", "R1C1", 2)]
    # R1C3 ohne Durchgang: gezählt als sonstiger Sieger, kein Fall
    assert m["zaehlung"] == {"treffer": 1, "verpasster_sieger": 1, "massstab": 0, "sonstig": 0,
                             "ohne_durchgang": 1, "verlorener_tipp": 1}
    fall = next(f for f in m["faelle"] if f["art"] == "verpasster_sieger")
    assert fall["kennungen"]["ausschlag"] == ["G-AUSRUESTUNG-WEG"]
    assert fall["rennen"] == "R1C1" and fall["pos"] == 1


def test_material_marktchance_ohne_nichtstarter():
    m = ea.material("20261118", _karte(), _durchgaenge(), _einlauf())
    k = {k["no"]: k for k in m["rennen"][0]["kandidaten"]}
    # Starter R1C1 ohne Nr. 4: 1/2 + 1/4 + 1/8 = 0.875 -> Nr. 2: 0.25 / 0.875
    assert k[2]["p_markt"] == pytest.approx(0.25 / 0.875)
    assert k[3]["gewonnen"] is False and k[2]["gewonnen"] is True


def test_maßstab_als_sieger():
    d = _durchgaenge()
    e = _einlauf()
    e["20261118R1C2"]["sieger"] = [1]
    m = ea.material("20261118", _karte(), d, e)
    assert m["rennen"][1]["sieger"][0]["gruppe"] == "massstab"
    assert m["zaehlung"]["massstab"] == 1


def test_protokoll_zeilen_und_richtung():
    m = ea.material("20261118", _karte(), _durchgaenge(), _einlauf())
    z = ea.protokoll_zeilen(m)
    paare = sorted((x["kennung"], x["richtung"], x["no"], x["race_id"][-4:]) for x in z)
    # P-CGD in Pro und Ausschlag desselben Pferds zählt einmal; Ermessen erzeugt keine Zeile
    assert paare == [("G-AUSRUESTUNG-WEG", "gegen", 2, "R1C1"), ("P-BAHN", "pro", 2, "R1C2"),
                     ("P-CGD", "pro", 3, "R1C1")]
    g = next(x for x in z if x["kennung"] == "G-AUSRUESTUNG-WEG")
    assert g["gewonnen"] == 1 and g["datum"] == "20261118"


def test_bericht_unter_druck():
    zeilen = [{"kennung": "P-X", "richtung": "pro", "gewonnen": 0, "p_markt": 0.3} for _ in range(30)]
    zeilen += [{"kennung": "G-Y", "richtung": "gegen", "gewonnen": 1 if i < 12 else 0, "p_markt": 0.1}
               for i in range(25)]
    zeilen += [{"kennung": "P-Z", "richtung": "pro", "gewonnen": 0, "p_markt": 0.5} for _ in range(5)]
    b = {(x["kennung"], x["richtung"]): x for x in ea.bericht(zeilen)}
    assert b[("P-X", "pro")]["unter_druck"] is True          # 0 Siege bei 9 erwarteten
    assert b[("G-Y", "gegen")]["unter_druck"] is True        # Gegen-Pferde gewinnen weit öfter als erwartet
    assert b[("P-Z", "pro")]["unter_druck"] is False         # zu wenige Fälle
    assert b[("P-X", "pro")]["ae"] == 0 and b[("P-X", "pro")]["erwartet"] == pytest.approx(9.0)


def test_protokoll_fortschreiben_ersetzt_tag(tmp_path):
    m = ea.material("20261118", _karte(), _durchgaenge(), _einlauf())
    ea.protokoll_fortschreiben(tmp_path, m)
    ea.protokoll_fortschreiben(tmp_path, m)
    assert len(ea.protokoll_lesen(tmp_path)) == 3


def test_naechster_tag_und_abschliessen(tmp_path):
    assert ea.naechster_tag(tmp_path, ["20261117", "20261115", "20261116"]) == "20261115"
    ea.tag_abschliessen(tmp_path, "20261115", commit="abc", vorschlaege=2)
    assert ea.naechster_tag(tmp_path, ["20261117", "20261115", "20261116"]) == "20261116"
    ea.tag_abschliessen(tmp_path, "20261116", commit="abc", vorschlaege=0)
    ea.tag_abschliessen(tmp_path, "20261117", commit="abc", vorschlaege=0)
    assert ea.naechster_tag(tmp_path, ["20261117", "20261115", "20261116"]) is None


def test_vorschlaege_ablegen_upsert(tmp_path):
    v = {"id": "20261118-1", "datum": "20261118", "race_id": "20261118R1C1", "no": 2, "horse": "H2",
         "fall": "verpasster_sieger", "art": "neu", "zieldatei": "EINSICHTEN.md", "kennung": "P-NEU",
         "text": "…", "gewicht": "leicht", "entscheidung": "offen", "notiz": ""}
    ea.vorschlaege_ablegen(tmp_path, [v])
    ea.vorschlaege_ablegen(tmp_path, [{**v, "entscheidung": "nein", "notiz": "Zufall"}])
    alle = ea.vorschlaege_lesen(tmp_path)
    assert len(alle) == 1 and alle[0]["entscheidung"] == "nein" and alle[0]["entschieden"]
    with pytest.raises(ValueError, match="entscheidung"):
        ea.vorschlaege_ablegen(tmp_path, [{**v, "entscheidung": "vielleicht"}])


def _skill(tmp_path, abschnitt_n=3, extra_zeilen=0, vorl="G-V"):
    eintraege = "".join(f"- **[leicht]** `G-E{i}` Text.\n" for i in range(abschnitt_n))
    t = ("# Einsichten\n\n## 1. Ausgangslage\n\n" + eintraege +
         f"- **[gewichtig · vorläufig]** `{vorl}` Neu. *X 15.11.*\n\n## 2. Letzter Lauf\n\n- **[leicht]** `P-L` a\n"
         + "\n" * extra_zeilen + "\n## Stillgelegte Kennungen\n\n- `G-ALT` → `G-E0`\n")
    (tmp_path / "EINSICHTEN.md").write_text(t, encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("", encoding="utf-8")
    return tmp_path


def test_verdichtung_ohne_anlass(tmp_path):
    v = ea.verdichtung(_skill(tmp_path), [])
    assert v["anlaesse"] == []
    assert v["abschnitte"] == {"1. Ausgangslage": 4, "2. Letzter Lauf": 1}
    assert v["vorlaeufig"] == ["G-V"]


def test_verdichtung_abschnitt_und_laenge(tmp_path):
    v = ea.verdichtung(_skill(tmp_path, abschnitt_n=8, extra_zeilen=200), [])
    arten = sorted(a["art"] for a in v["anlaesse"])
    assert arten == ["abschnitt_voll", "datei_lang"]
    assert next(a for a in v["anlaesse"] if a["art"] == "abschnitt_voll")["abschnitt"] == "1. Ausgangslage"


def test_verdichtung_vorlaeufig_bestaetigt(tmp_path):
    zeilen = [{"kennung": "G-V", "richtung": "gegen", "gewonnen": 0, "p_markt": 0.2} for _ in range(20)]
    v = ea.verdichtung(_skill(tmp_path), zeilen)
    assert v["anlaesse"] == [{"art": "vorlaeufig_bestaetigt", "kennung": "G-V", "n": 20, "z": pytest.approx(-2.24, abs=0.01)}]


def test_bericht_zaehlt_stillgelegte_mit():
    zeilen = [{"kennung": "G-ALT", "richtung": "gegen", "gewonnen": 0, "p_markt": 0.2},
              {"kennung": "G-NEU", "richtung": "gegen", "gewonnen": 1, "p_markt": 0.2}]
    b = ea.bericht(zeilen, {"G-ALT": "G-NEU"})
    assert len(b) == 1 and b[0]["kennung"] == "G-NEU" and b[0]["n"] == 2


def test_verdichtung_zwei_kennungen_in_einem_eintrag(tmp_path):
    t = ("## 2. Letzter Lauf\n\n- **[leicht]** `P-L` Wird übergangen. *A.* Auf dem heutigen Boden gilt das nicht:\n"
         "  **[gewichtig · vorläufig]** `G-H` Gegenargument. *B 15.11.*\n")
    (tmp_path / "EINSICHTEN.md").write_text(t, encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("", encoding="utf-8")
    v = ea.verdichtung(tmp_path, [])
    assert v["abschnitte"] == {"2. Letzter Lauf": 1}
    assert v["vorlaeufig"] == ["G-H"]
