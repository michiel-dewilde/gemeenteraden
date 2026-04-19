"""
Aggregeert de tijdlijn-analyse per gemeente naar gewogen gemiddelden over de legislatuur.

Invoer : gemeenteraad_analyse_2018_2024.json  (uitvoer van 1_analyseer_mandatendatabank.py)
Uitvoer: gemeenteraad_aggregatie_2018_2024.json

Werkwijze
---------
Per gemeente bevat de invoer een lijst van perioden, elk met een dagentelling en
de samenstelling van gemeenteraad en schepencollege.

Voor elke sectie wordt per fractie het gewogen gemiddeld aantal zetels berekend,
waarbij het gewicht gelijk is aan het aantal dagen van de periode:

    gemiddeld_zetels(fractie) = Σ(dagen_i × zetels_i) / Σ(dagen_i)

Uitvoerformaat
--------------
{
  "Aalst": {
    "gemeenteraad":   { "N-VA": 16.8, "Vlaams Belang": 7.0, ... },
    "schepencollege": { "N-VA": 5.9, ... }
  },
  ...
}

Fracties zijn gesorteerd van hoog naar laag gemiddeld zetelgetal.

Gebruik
-------
    python 2_aggregeer_gegevens.py
    python 2_aggregeer_gegevens.py --input  gemeenteraad_analyse_2018_2024.json
                                   --output gemeenteraad_aggregatie_2018_2024.json
"""

import argparse
import json
import sys
from collections import defaultdict


def aggregeer_gemeente(perioden):
    """
    Berekent gewogen gemiddelden voor één gemeente.

    Parameters
    ----------
    perioden : lijst van dicts met sleutels 'dagen', 'gemeenteraad', 'schepencollege'

    Geeft terug : dict met sleutels 'gemeenteraad' en 'schepencollege',
                  elk een {fractie: gemiddeld_zetels}-dict gesorteerd hoog→laag.
    """
    totaal_dagen = sum(p["dagen"] for p in perioden)
    if totaal_dagen == 0:
        return {"gemeenteraad": {}, "schepencollege": {}}

    gr_gewogen  = defaultdict(float)
    col_gewogen = defaultdict(float)

    for p in perioden:
        w = p["dagen"]
        for fractie, zetels in p["gemeenteraad"].items():
            gr_gewogen[fractie] += w * zetels
        for fractie, zetels in p["schepencollege"].items():
            col_gewogen[fractie] += w * zetels

    def afronden_en_sorteren(gewogen):
        gemiddelden = {f: round(s / totaal_dagen, 4) for f, s in gewogen.items()}
        return dict(sorted(gemiddelden.items(), key=lambda kv: (-kv[1], kv[0])))

    return {
        "gemeenteraad":   afronden_en_sorteren(gr_gewogen),
        "schepencollege": afronden_en_sorteren(col_gewogen),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Aggregeer gemeenteraad-analyse naar gewogen gemiddelden per gemeente"
    )
    parser.add_argument(
        "--input", "-i",
        default="gemeenteraad_analyse_2018_2024.json",
        help="Invoerbestand (standaard: gemeenteraad_analyse_2018_2024.json)",
    )
    parser.add_argument(
        "--output", "-o",
        default="gemeenteraad_aggregatie_2018_2024.json",
        help="Uitvoerbestand (standaard: gemeenteraad_aggregatie_2018_2024.json)",
    )
    args = parser.parse_args()

    print(f"Lezen: {args.input} ...")
    try:
        with open(args.input, encoding="utf-8") as f:
            analyse = json.load(f)
    except FileNotFoundError:
        print(f"Bestand niet gevonden: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"Aggregeren voor {len(analyse)} gemeenten ...")
    resultaat = {
        gemeente: aggregeer_gemeente(perioden)
        for gemeente, perioden in sorted(analyse.items())
    }

    print(f"Wegschrijven naar {args.output} ...")
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(resultaat, f, ensure_ascii=False, indent=2)

    print("Klaar.\n")

    # Voorbeelduitvoer voor de eerste gemeente
    eerste, data = next(iter(resultaat.items()))
    print(f"Voorbeeld: {eerste}")
    print(f"  Gemeenteraad   : {dict(list(data['gemeenteraad'].items())[:4])} ...")
    print(f"  Schepencollege : {data['schepencollege']}")


if __name__ == "__main__":
    main()
