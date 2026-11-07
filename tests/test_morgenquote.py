import json

import pandas as pd

import morgenquote_abgleich as mq


def test_morgenquote_abgleich(tmp_path):
    (tmp_path / "racecards").mkdir()
    (tmp_path / "parquet" / "pmu_runners").mkdir(parents=True)
    karte = {"races": {"20261101R1C1": {"race_id": "20261101R1C1", "runners": [
        {"no": 1, "horse": "A", "prono": {"sel": {"cote_dec": 3.0}}, "fk": {"sieg": 3.2, "toto": 2.9}},
        {"no": 2, "horse": "B", "prono": {"sel": {"cote_dec": 6.0}}, "fk": {"sieg": 5.0}},
        {"no": 3, "horse": "C", "nr": True, "prono": {"sel": {"cote_dec": 9.0}}},
        {"no": 4, "horse": "D"}]}}}
    (tmp_path / "racecards" / "racecard_20261101_daten.json").write_text(json.dumps(karte))
    pd.DataFrame({"race_id": ["20261101R1C1"] * 4, "saddle_no": [1, 2, 3, 4], "status": ["PARTANT"] * 3 + ["PARTANT"],
                  "odds_morning": [3.0, 12.0, 9.0, 20.0], "odds_final": [2.5, 6.5, 9.0, 18.0],
                  "finish_pos": [1, 2, None, 3]}).to_parquet(tmp_path / "parquet" / "pmu_runners" / "20261101.parquet")
    erg = mq.run(tmp_path, tage=7, log=lambda *a: None)
    g = erg["gesamt"]
    assert g.loc["prono_cote", "n_paar"] == 2                 # Nichtstarter C fällt raus, D ohne Prognose
    assert g.loc["prono_cote", "gleich"] == 0.5               # A gleich, B halb so hoch
    assert g.loc["prono_cote", "naeher_morgen_als_end"] == 0.5
    assert erg["abweichungen"].iloc[0]["horse"] == "B"
