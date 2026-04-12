"""
Gemeenteraad samenstelling 2018-2024 uit Mandatendatabank Vlaanderen (Turtle)
=============================================================================
Gebruik:
    pip install rdflib
    python gemeenteraad_samenstelling.py --input mandaten.ttl --output resultaat.csv

Output CSV kolommen:
    gemeente, fractie, aantal_leden, totaal_raad, in_schepencollege, voorzitter_gemeenteraad

- in_schepencollege:        "ja" als de fractie minstens 1 schepen of de burgemeester leverde
- voorzitter_gemeenteraad:  "ja" als de fractie de voorzitter van de gemeenteraad leverde
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone

try:
    from rdflib import Graph, Namespace, RDF, URIRef, Literal
    from rdflib.namespace import SKOS, FOAF
except ImportError:
    print("Installeer rdflib eerst:  pip install rdflib")
    sys.exit(1)

MANDAAT = Namespace("http://data.vlaanderen.be/ns/mandaat#")
BESLUIT = Namespace("http://data.vlaanderen.be/ns/besluit#")
ORG     = Namespace("http://www.w3.org/ns/org#")
REGORG  = Namespace("https://www.w3.org/ns/regorg#")

# Rollen
ROL_GEMEENTERAADSLID = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000011")
ROL_VOORZITTER_GR    = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000012")
ROL_BURGEMEESTER     = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000013")
ROL_SCHEPEN          = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000014")
ROL_TOE_SCHEPEN      = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/59a90e03-4f22-4bb9-8c91-132618db4b38")

ROLLEN_GEMEENTERAAD   = {ROL_GEMEENTERAADSLID, ROL_VOORZITTER_GR}
ROLLEN_SCHEPENCOLLEGE = {ROL_BURGEMEESTER, ROL_SCHEPEN, ROL_TOE_SCHEPEN}

# Legislatuur 2018-2024
PERIODE_START = datetime(2018, 10, 1, tzinfo=timezone.utc)
PERIODE_EINDE = datetime(2019,  6, 1, tzinfo=timezone.utc)


def parse_dt(literal):
    if literal is None:
        return None
    s = str(literal).strip()[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def best_label(g, uri):
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
    parser.add_argument("--voorzitter", action="store_true",
                        help="Tel ook de voorzitter van de gemeenteraad mee")
    args = parser.parse_args()

    toegelaten_rollen = {ROL_GEMEENTERAADSLID}
    if args.voorzitter:
        toegelaten_rollen.add(ROL_VOORZITTER_GR)

    # ------------------------------------------------------------------
    # 1. Laden
    # ------------------------------------------------------------------
    print(f"Bestand laden: {args.input}  (dit kan even duren...)")
    g = Graph()
    g.parse(args.input, format="turtle")
    print(f"  {len(g)} triples geladen.\n")

    # ------------------------------------------------------------------
    # 2. Opzoektabellen
    # ------------------------------------------------------------------
    print("Opzoektabellen bouwen...")

    # Post -> rol URI
    post_rol = {}
    for post in g.subjects(RDF.type, ORG.Post):
        rol = g.value(post, ORG.role)
        if rol:
            post_rol[post] = rol

    # Tijdgebonden bestuursorgaan -> gemeente-label
    # Pad: orgaan --isTijdspecialisatieVan--> tijdloos_orgaan --prefLabel--> "Gemeenteraad X"
    orgaan_gemeente = {}
    for orgaan in g.subjects(RDF.type, BESLUIT.Bestuursorgaan):
        tijdloos = g.value(orgaan, MANDAAT.isTijdspecialisatieVan)
        if tijdloos is None:
            continue
        lbl = best_label(g, tijdloos)
        for prefix in ("Gemeenteraad ", "OCMW ", "District ", "Provincieraad ",
                        "College van Burgemeester en Schepenen ",
                        "Raad voor Maatschappelijk Welzijn "):
            if lbl.startswith(prefix):
                lbl = lbl[len(prefix):]
                break
        orgaan_gemeente[orgaan] = lbl

    # Post -> tijdgebonden bestuursorgaan
    post_orgaan = {}
    for orgaan, post in g.subject_objects(ORG.hasPost):
        post_orgaan[post] = orgaan

    # Lidmaatschap -> (fractie_uri, fractie_label)
    lid_fractie = {}
    for lid in g.subjects(RDF.type, ORG.Membership):
        frac_uri = g.value(lid, ORG.organisation)
        if frac_uri:
            lid_fractie[lid] = (frac_uri, best_label(g, frac_uri))

    print(f"  Post->rol:          {len(post_rol)}")
    print(f"  Orgaan->gemeente:   {len(orgaan_gemeente)}")
    print(f"  Post->orgaan:       {len(post_orgaan)}")
    print(f"  Lid->fractie:       {len(lid_fractie)}\n")

    # ------------------------------------------------------------------
    # 3. Loop over mandatarissen — gemeenteraadsleden EN in_schepencollege
    # ------------------------------------------------------------------
    print("Mandatarissen verwerken...")

    # gemeente -> fractie_uri -> set van persoon-URIs (deduplicatie via isBestuurlijkeAliasVan)
    raad_data        = defaultdict(lambda: defaultdict(set))
    # gemeente -> set(fractie_uri) die in schepencollege zitten
    college_fracties = defaultdict(set)
    # gemeente -> set(fractie_uri) die de voorzitter van de gemeenteraad leveren
    voorzitter_fracties = defaultdict(set)
    # fractie_uri -> fractie_label (cache)
    fractie_labels = {}

    teller = 0
    for mandataris in g.subjects(RDF.type, MANDAAT.Mandataris):
        teller += 1
        if teller % 10000 == 0:
            print(f"  {teller:>6} mandatarissen verwerkt...")

        start = parse_dt(g.value(mandataris, MANDAAT.start))
        if start is None or not (PERIODE_START <= start <= PERIODE_EINDE):
            continue

        post = g.value(mandataris, ORG.holds)
        if post is None:
            continue

        rol = post_rol.get(post)
        if rol is None:
            continue

        orgaan = post_orgaan.get(post)
        if orgaan is None:
            continue
        gemeente = orgaan_gemeente.get(orgaan)
        if not gemeente:
            continue

        # Fractie
        lid_uri = g.value(mandataris, ORG.hasMembership)
        if lid_uri and lid_uri in lid_fractie:
            frac_uri, frac_lbl = lid_fractie[lid_uri]
        else:
            frac_uri, frac_lbl = None, "Onbekend"

        if frac_uri:
            fractie_labels[frac_uri] = frac_lbl

        persoon    = g.value(mandataris, MANDAAT.isBestuurlijkeAliasVan)
        identifier = persoon if persoon is not None else mandataris

        if rol == ROL_GEMEENTERAADSLID:
            raad_data[gemeente][frac_uri].add(identifier)
        elif rol == ROL_VOORZITTER_GR:
            if frac_uri:
                voorzitter_fracties[gemeente].add(frac_uri)
            if args.voorzitter:
                raad_data[gemeente][frac_uri].add(identifier)
        elif rol in ROLLEN_SCHEPENCOLLEGE:
            if frac_uri:
                college_fracties[gemeente].add(frac_uri)

    print(f"\nGemeenteraadsleden gevonden in {len(raad_data)} gemeenten.")
    print(f"Schepencollege-fracties gevonden in {len(college_fracties)} gemeenten.")
    print(f"Voorzitters gevonden in {len(voorzitter_fracties)} gemeenten.\n")

    # ------------------------------------------------------------------
    # 4. Schrijf CSV
    # ------------------------------------------------------------------
    rows = []
    for gemeente in sorted(raad_data):
        fracties = raad_data[gemeente]
        totaal = sum(len(v) for v in fracties.values())
        col_fracties      = college_fracties.get(gemeente, set())
        voorz_fracties    = voorzitter_fracties.get(gemeente, set())

        for frac_uri in sorted(fracties, key=lambda u: fractie_labels.get(u, "Onbekend")):
            frac_lbl = fractie_labels.get(frac_uri, "Onbekend") if frac_uri else "Onbekend"
            aantal   = len(fracties[frac_uri])

            rows.append({
                "gemeente":               gemeente,
                "fractie":                frac_lbl,
                "aantal_leden":           aantal,
                "totaal_raad":            totaal,
                "in_schepencollege":      "ja" if frac_uri in col_fracties   else "nee",
                "voorzitter_gemeenteraad": "ja" if frac_uri in voorz_fracties else "nee",
            })

    fieldnames = ["gemeente", "fractie", "aantal_leden", "totaal_raad",
                  "in_schepencollege", "voorzitter_gemeenteraad"]

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"CSV geschreven -> {args.output}  ({len(rows)} rijen)\n")

    # Voorbeeld
    print(f"{'Gemeente':<25} {'Fractie':<30} {'Leden':>5} {'Tot':>4} {'Schepen':>8} {'Voorz':>6}")
    print("-" * 84)
    for row in rows[:30]:
        print(f"{row['gemeente']:<25} {row['fractie']:<30} "
              f"{row['aantal_leden']:>5} {row['totaal_raad']:>4} "
              f"{row['in_schepencollege']:>8} {row['voorzitter_gemeenteraad']:>6}")
    if len(rows) > 30:
        print(f"  ... en nog {len(rows)-30} rijen in het CSV.")


if __name__ == "__main__":
    main()
