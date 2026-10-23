"""Lage der französischen Rennbahnen (Breite, Länge; auf wenige Kilometer genau) – für die Reise des Trainers von
seiner Heimatbahn zur heutigen Bahn (power_modell: trainer_reise_km). Bahnen, die hier fehlen, ergeben NaN.

Zuordnung über den Bahnkern (racecard.bahn_kern: ohne Akzente, Satzzeichen, Füllwörter): erst gleicher Kern, dann der
längste Eintrag, der als ganze Wörter im Kern steht ('ANGERS EVENTARD' → ANGERS), dann ein Kern ab 4 Zeichen, der in
einem Eintrag steht.
"""
from __future__ import annotations

import math
from functools import lru_cache

ORTE = {
    # Paris und Umgebung
    "PARISLONGCHAMP": (48.857, 2.233), "LONGCHAMP": (48.857, 2.233), "SAINT CLOUD": (48.857, 2.200),
    "CHANTILLY": (49.193, 2.470), "COMPIEGNE": (49.405, 2.836), "FONTAINEBLEAU": (48.403, 2.680),
    "MAISONS LAFFITTE": (48.952, 2.149), "AUTEUIL": (48.850, 2.255), "ENGHIEN": (48.970, 2.300),
    # Normandie, Norden
    "DEAUVILLE": (49.353, 0.083), "CLAIREFONTAINE": (49.336, 0.078), "CABOURG": (49.280, -0.120),
    "CAEN": (49.180, -0.370), "ARGENTAN": (48.740, -0.020), "HARAS PIN": (48.740, 0.150), "PIN AU HARAS": (48.740, 0.150),
    "DIEPPE": (49.920, 1.080), "EVREUX": (49.020, 1.150), "ROUEN": (49.400, 1.080), "GRANVILLE": (48.840, -1.590),
    "VIRE": (48.840, -0.890), "LISIEUX": (49.150, 0.230), "AMIENS": (49.890, 2.300), "TOUQUET": (50.520, 1.590),
    "CROISE LAROCHE": (50.680, 3.130), "ARRAS": (50.290, 2.780), "BEAUMONT LOMAGNE": (43.880, 0.990),
    # Bretagne
    "SAINT MALO": (48.650, -2.000), "SAINT BRIEUC": (48.510, -2.760), "DINAN": (48.450, -2.050),
    "VANNES": (47.660, -2.760), "LOUDEAC": (48.180, -2.750), "LANDIVISIAU": (48.510, -4.070),
    "MORLAIX": (48.580, -3.830), "PLOUESCAT": (48.660, -4.170), "ROSTRENEN": (48.240, -3.320),
    "GUERLESQUIN": (48.520, -3.590), "CORLAY": (48.320, -3.060), "JOSSELIN": (47.950, -2.550),
    "MAURON": (48.080, -2.280), "GACILLY": (47.770, -2.130), "MAURE BRETAGNE": (47.890, -1.990),
    "LANDERNEAU": (48.450, -4.250), "QUIMPER": (47.980, -4.100), "PONTCHATEAU": (47.430, -2.090),
    # Pays de la Loire, Centre
    "MANS": (47.950, 0.220), "ANGERS": (47.500, -0.490), "LION ANGERS": (47.630, -0.720),
    "NANTES": (47.245, -1.540), "PORNICHET": (47.270, -2.340), "CHATEAUBRIANT": (47.720, -1.380),
    "CRAON": (47.850, -0.950), "SENONNES POUANCE": (47.780, -1.170), "SABLE SARTHE": (47.840, -0.340),
    "SABLES OLONNE": (46.500, -1.780), "ROCHE YON": (46.670, -1.430), "SAVENAY": (47.360, -1.940),
    "MACHECOUL": (46.990, -1.820), "NORT ERDRE": (47.440, -1.500), "ERBRAY": (47.650, -1.320),
    "DURTAL": (47.670, -0.240), "CHOLET": (47.060, -0.880), "BEAUPREAU": (47.200, -0.990),
    "ROCHEFORT LOIRE": (47.360, -0.660), "SILLE GUILLAUME": (48.180, -0.130), "LAVAL": (48.070, -0.770),
    "SEGRE": (47.690, -0.870), "CORDEMAIS": (47.290, -1.880), "SAINT JEAN MONTS": (46.790, -2.060),
    "ORLEANS": (47.900, 1.900), "LIGNIERES": (46.750, 2.170), "CHATRE": (46.580, 1.990),
    "TOURS": (47.390, 0.690), "VENDOME": (47.790, 1.070),
    # Westen, Südwesten
    "ROCHE POSAY": (46.790, 0.810), "NIORT": (46.320, -0.460), "ROYAN PALMYRE": (45.650, -1.120),
    "ROYAN": (45.650, -1.120), "CHATELAILLON": (46.070, -1.090), "SAINTES": (45.750, -0.630),
    "JARNAC": (45.680, -0.170), "ANGOULEME": (45.650, 0.150), "MONTIGNAC": (45.780, 0.120),
    "BORDEAUX": (44.870, -0.598), "BOUSCAT": (44.870, -0.598), "TESTE BUCH": (44.630, -1.140),
    "LANGON LIBOURNE": (44.550, -0.250), "LIBOURNE": (44.920, -0.240), "MONT MARSAN": (43.890, -0.500),
    "DAX": (43.710, -1.050), "PAU": (43.300, -0.370), "TARBES": (43.230, 0.070), "AGEN": (44.200, 0.620),
    "CASTERA VERDUZAN": (43.800, 0.430), "MONTAUBAN": (44.020, 1.350), "TOULOUSE": (43.590, 1.410),
    "VILLENEUVE LOT": (44.410, 0.700), "DAMAZAN": (44.290, 0.270), "GRAMAT": (44.780, 1.720),
    "BIARRITZ": (43.470, -1.540), "AURILLAC": (44.930, 2.440), "POMPADOUR": (45.400, 1.380),
    "LIMOGES": (45.830, 1.260),
    # Mitte, Osten
    "VICHY": (46.120, 3.418), "MOULINS": (46.565, 3.330), "MONTLUCON": (46.340, 2.600), "NEVERS": (46.990, 3.160),
    "LYON": (45.718, 4.912), "PARILLY": (45.718, 4.912), "LYON SOIE": (45.765, 4.920), "FEURS": (45.740, 4.230),
    "ROANNE": (46.040, 4.070), "CLUNY": (46.430, 4.660), "MACON": (46.310, 4.830), "MACON CLUNY": (46.430, 4.660),
    "CHATILLON CHALARONNE": (46.120, 4.960), "AIX BAINS": (45.690, 5.910), "STRASBOURG": (48.690, 7.780),
    "HOERDT": (48.690, 7.780), "WISSEMBOURG": (49.040, 7.950), "NANCY": (48.660, 6.150), "BRABOIS": (48.660, 6.150),
    "VITTEL": (48.200, 5.950), "VITTEAUX": (47.400, 4.540), "DIJON": (47.320, 5.040),
    # Süden
    "MARSEILLE": (43.259, 5.375), "BORELY": (43.259, 5.375), "MARSEILLE VIVAUX": (43.277, 5.405),
    "PONT VIVAUX": (43.277, 5.405), "CAGNES": (43.651, 7.163), "SALON PROVENCE": (43.640, 5.100),
    "CAVAILLON": (43.840, 5.040), "NIMES": (43.840, 4.360), "HYERES": (43.100, 6.150), "AVIGNON": (43.950, 4.810),
    "CARPENTRAS": (44.050, 5.050), "BEZIERS": (43.340, 3.250), "PRUNELLI": (42.000, 9.400),
}


@lru_cache(maxsize=None)
def koordinaten(hippodrome) -> tuple[float, float] | None:
    """(Breite, Länge) der Bahn oder None."""
    import racecard
    k = racecard.bahn_kern(hippodrome)
    if not k:
        return None
    if k in ORTE:
        return ORTE[k]
    t = f" {k} "
    drin = [e for e in ORTE if f" {e} " in t]
    if drin:
        return ORTE[max(drin, key=len)]
    if len(k) >= 4:
        um = [e for e in ORTE if t in f" {e} "]
        if um:
            return ORTE[min(um, key=len)]
    return None


def km(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float:
    """Luftlinie in km (Haversine); NaN, wenn eine Lage fehlt."""
    if a is None or b is None:
        return float("nan")
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(x))
