"""
Gemeenteraad samenstelling 2018-2024 uit Mandatendatabank Vlaanderen (Turtle-formaat)
======================================================================================
Gebruik:
    pip install rdflib
    python gemeenteraad_samenstelling.py --input mandaten.ttl --output resultaat.csv

Structuur in de data:
    Mandataris  --mandaat:start-->        datetime
                --org:holds-->            Post (Mandaat)
                --org:hasMembership-->    Lidmaatschap
                                              --org:organisation-->  Fractie (legalName / prefLabel)
    Post        --org:role-->             BestuursfunctieCode (prefLabel = "Gemeenteraadslid")
    Bestuursorgaan --org:hasPost-->       Post
                   --besluit:bestuurt-->  Bestuurseenheid (prefLabel = gemeente)
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone

try:
    from rdflib import Graph, Namespace, RDF
    from rdflib.namespace import SKOS, FOAF
except ImportError:
    print("Installeer rdflib eerst:  pip install rdflib")
    sys.exit(1)

MANDAAT = Namespace("http://data.vlaanderen.be/ns/mandaat#")
BESLUIT = Namespace("http://data.vlaanderen.be/ns/besluit#")
ORG     = Namespace("http://www.w3.org/ns/org#")
REGORG  = Namespace("https://www.w3.org/ns/regorg#")

# Legislatuur 2018-2024: start tussen 1 okt 2018 en 1 jun 2019
PERIODE_START = datetime(2018, 10, 1, tzinfo=timezone.utc)
PERIODE_EINDE = datetime(2019,  6, 1, tzinfo=timezone.utc)

ROL_FILTER = "gemeenteraadslid"


def parse_dt(literal):
    """Parset RDF datum/datetime naar timezone-aware datetime, of None."""
    if literal is None:
        return None
    s = str(literal).strip()
    # Verwijder subseconden en normaliseer offset
    s = s[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def best_label(g, uri):
    """Beste beschikbare label voor een URI."""
    for pred in (SKOS.prefLabel, REGORG.legalName, FOAF.name, SKOS.altLabel):
        for obj in g.objects(uri, pred):
            lbl = str(obj).strip()
            if lbl:
                return lbl
    return str(uri).split("/")[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  "-i", required=True)
    parser.add_argument("--output", "-o",
                        default="gemeenteraad_samenstelling_2018_2024.csv")
    args = parser.parse_args()

    print(f"Bestand laden: {args.input}  (dit kan even duren...)")
    g = Graph()
    g.parse(args.input, format="turtle")
    print(f"  → {len(g)} triples geladen.\n")

    # --- Opzoektabellen bouwen ---
    print("Opzoektabellen bouwen...")

    # Post -> rol (lowercase string)
    post_rol = {}
    for post in g.subjects(RDF.type, ORG.Post):
        rol_uri = g.value(post, ORG.role)
        if rol_uri:
            post_rol[post] = best_label(g, rol_uri).lower()

    # Post -> gemeente_label  (via Bestuursorgaan)
    post_gemeente = {}
    for orgaan in g.subjects(RDF.type, BESLUIT.Bestuursorgaan):
        eenheid = g.value(orgaan, BESLUIT.bestuurt)
        if eenheid is None:
            continue
        gemeente_lbl = best_label(g, eenheid)
        for post in g.objects(orgaan, ORG.hasPost):
            post_gemeente[post] = gemeente_lbl

    # Lidmaatschap -> fractie_label
    lid_fractie = {}
    for lid in g.subjects(RDF.type, ORG.Membership):
        frac_uri = g.value(lid, ORG.organisation)
        if frac_uri:
            lid_fractie[lid] = best_label(g, frac_uri)

    print(f"  Post→rol:         {len(post_rol)}")
    print(f"  Post→gemeente:    {len(post_gemeente)}")
    print(f"  Lid→fractie:      {len(lid_fractie)}\n")

    # --- Verwerk mandatarissen ---
    print("Mandatarissen verwerken...")
    data = defaultdict(lambda: defaultdict(set))
    teller = gevonden = skip_datum = skip_rol = skip_orgaan = 0

    for mandataris in g.subjects(RDF.type, MANDAAT.Mandataris):
        teller += 1
        if teller % 10000 == 0:
            print(f"  {teller:>6} | gevonden:{gevonden} "
                  f"| skip datum:{skip_datum} rol:{skip_rol} orgaan:{skip_orgaan}")

        # Startdatum filteren
        start = parse_dt(g.value(mandataris, MANDAAT.start))
        if start is None or not (PERIODE_START <= start <= PERIODE_EINDE):
            skip_datum += 1
            continue

        # Post (mandaat) ophalen
        post = g.value(mandataris, ORG.holds)
        if post is None:
            skip_rol += 1
            continue

        # Rol filteren
        if ROL_FILTER not in post_rol.get(post, ""):
            skip_rol += 1
            continue

        # Gemeente ophalen
        gemeente = post_gemeente.get(post)
        if not gemeente:
            skip_orgaan += 1
            continue

        # Fractie ophalen
        lid_uri = g.value(mandataris, ORG.hasMembership)
        fractie = lid_fractie.get(lid_uri, "Onbekend") if lid_uri else "Onbekend"

        data[gemeente][fractie].add(mandataris)
        gevonden += 1

    print(f"\nResultaat: {gevonden} gemeenteraadsleden in {len(data)} gemeenten.")

    if gevonden == 0:
        print("\nDebug – eerste 5 mandaat#start waarden in het bestand:")
        for i, (_, _, o) in enumerate(g.triples((None, MANDAAT.start, None))):
            print(f"  raw={str(o)!r}  →  parse={parse_dt(o)}")
            if i >= 4:
                break
        sys.exit(1)

    # --- Schrijf CSV ---
    rows = []
    for gemeente in sorted(data):
        totaal = sum(len(v) for v in data[gemeente].values())
        for fractie in sorted(data[gemeente]):
            rows.append({
                "gemeente":     gemeente,
                "fractie":      fractie,
                "aantal_leden": len(data[gemeente][fractie]),
                "totaal_raad":  totaal,
            })

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["gemeente","fractie","aantal_leden","totaal_raad"])
        w.writeheader()
        w.writerows(rows)

    print(f"CSV geschreven → {args.output}  ({len(rows)} rijen)\n")

    print(f"{'Gemeente':<30} {'Fractie':<30} {'Leden':>6} {'Totaal':>7}")
    print("-" * 76)
    for row in rows[:30]:
        print(f"{row['gemeente']:<30} {row['fractie']:<30} "
              f"{row['aantal_leden']:>6} {row['totaal_raad']:>7}")
    if len(rows) > 30:
        print(f"  ... en nog {len(rows)-30} rijen in het CSV.")


if __name__ == "__main__":
    main()
