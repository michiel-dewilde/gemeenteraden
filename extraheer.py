"""
Gemeenteraad samenstelling 2018-2024 uit Mandatendatabank Vlaanderen (Turtle-formaat)
======================================================================================
Gebruik:
    pip install rdflib
    python gemeenteraad_samenstelling.py --input mandaten.ttl --output resultaat.csv

Het script:
1. Laadt het Turtle-bestand van mandaten.lokaalbestuur.vlaanderen.be
2. Filtert op gemeenteraadsleden (niet schepenen, burgemeesters, ...)
3. Filtert op de legislatuur 2018-2024 (start tussen 2018-10-01 en 2019-06-01)
4. Groepeert per gemeente en per fractie
5. Schrijft het resultaat naar een CSV-bestand
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date

try:
    from rdflib import Graph, Namespace, RDF, RDFS, OWL
    from rdflib.namespace import XSD
except ImportError:
    print("Installeer rdflib eerst:  pip install rdflib")
    sys.exit(1)

# -------------------------------------------------------------------
# Namespaces die de Mandatendatabank gebruikt
# -------------------------------------------------------------------
MANDAAT  = Namespace("http://data.vlaanderen.be/ns/mandaat#")
BESLUIT  = Namespace("http://data.vlaanderen.be/ns/besluit#")
ORG      = Namespace("http://www.w3.org/ns/org#")
SKOS     = Namespace("http://www.w3.org/2004/02/skos/core#")
GENERIEK = Namespace("http://data.vlaanderen.be/ns/generiek#")
EXT      = Namespace("http://mu.semte.ch/vocabularies/ext/")
SCHEMA   = Namespace("http://schema.org/")
FOAF     = Namespace("http://xmlns.com/foaf/0.1/")
LBLOD    = Namespace("http://data.lblod.info/id/")

# URI-fragment dat gemeenteraden identificeert
# De rol "Gemeenteraadslid" heeft een vaste URI in de codelijst
GEMEENTERAADSLID_LABEL = "Gemeenteraadslid"

# Legislatuur 2018-2024: mandaat start na 1 okt 2018 en vóór 1 jun 2019
PERIODE_START = date(2018, 10, 1)
PERIODE_EINDE = date(2019, 6, 1)


def parse_date(literal):
    """Zet een RDF-datum literal om naar een Python date, of None."""
    if literal is None:
        return None
    try:
        s = str(literal)[:10]   # "YYYY-MM-DD"
        return date.fromisoformat(s)
    except Exception:
        return None


def label_of(g, uri, default="?"):
    """Haal het beste beschikbare label op voor een URI."""
    for pred in (SKOS.prefLabel, RDFS.label, SKOS.altLabel, FOAF.name):
        for obj in g.objects(uri, pred):
            lbl = str(obj).strip()
            if lbl:
                return lbl
    return default


def main():
    parser = argparse.ArgumentParser(
        description="Gemeenteraad samenstelling 2018-2024 uit Mandatendatabank Turtle"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Pad naar het Turtle-bestand (bijv. mandaten.ttl)"
    )
    parser.add_argument(
        "--output", "-o",
        default="gemeenteraad_samenstelling_2018_2024.csv",
        help="Pad naar het uitvoer-CSV-bestand (standaard: gemeenteraad_samenstelling_2018_2024.csv)"
    )
    parser.add_argument(
        "--format", "-f",
        default="turtle",
        choices=["turtle", "n3", "nt", "xml", "json-ld"],
        help="RDF-serialisatieformaat (standaard: turtle)"
    )
    args = parser.parse_args()

    # -------------------------------------------------------------------
    # 1. Laad het RDF-bestand
    # -------------------------------------------------------------------
    print(f"Bestand laden: {args.input}  (dit kan even duren voor grote bestanden...)")
    g = Graph()
    try:
        g.parse(args.input, format=args.format)
    except Exception as e:
        print(f"Fout bij laden van bestand: {e}")
        sys.exit(1)
    print(f"  → {len(g)} triples geladen.")

    # -------------------------------------------------------------------
    # 2. Zoek alle Mandataris-instanties die Gemeenteraadslid zijn
    #    en die starten in de legislatuur 2018-2024
    # -------------------------------------------------------------------
    # Structuur in de databank:
    #   <mandataris> a mandaat:Mandataris ;
    #       mandaat:isBestuurlijkeAliasVan <persoon> ;
    #       org:holds <mandaat_uri> ;
    #       mandaat:start "2019-01-01"^^xsd:date ;
    #       mandaat:einde "2024-12-31"^^xsd:date .
    #   <mandaat_uri> mandaat:bestuursfunctie <rol> ;
    #       org:unitOf <bestuursorgaan> .
    #   <bestuursorgaan> besluit:isOrgaanVan <bestuurseenheid> ;
    #       generiek:isTijdspecialisatieVan <bestuursorgaan_type> .
    #   <bestuurseenheid> skos:prefLabel "Gemeente X" .
    #   <rol> skos:prefLabel "Gemeenteraadslid" .
    #   <mandataris> org:memberOf <fractie> .
    #   <fractie> skos:prefLabel "Partij Y" .

    # Verzamel: gemeente -> fractie -> count
    data = defaultdict(lambda: defaultdict(int))
    # Bijhouden welke gemeente-labels we vonden
    gemeente_labels = {}

    mandataris_type = MANDAAT.Mandataris

    print("Mandatarissen verwerken...")
    teller = 0
    gevonden = 0

    for mandataris in g.subjects(RDF.type, mandataris_type):
        teller += 1
        if teller % 10000 == 0:
            print(f"  {teller} mandatarissen verwerkt, {gevonden} gevonden...")

        # -- Startdatum controleren --
        start_raw = g.value(mandataris, MANDAAT.start)
        start = parse_date(start_raw)
        if start is None:
            # Probeer alternatieve predikaten
            start_raw = g.value(mandataris, MANDAAT.generiekStart) or \
                        g.value(mandataris, GENERIEK.start)
            start = parse_date(start_raw)

        # Filter op legislatuur 2018-2024
        if start is None or not (PERIODE_START <= start <= PERIODE_EINDE):
            continue

        # -- Mandaat ophalen (om rol en bestuursorgaan te vinden) --
        mandaat_uri = g.value(mandataris, ORG.holds)
        if mandaat_uri is None:
            continue

        # -- Rol controleren: moet Gemeenteraadslid zijn --
        rol_uri = g.value(mandaat_uri, MANDAAT.bestuursfunctie)
        if rol_uri is None:
            continue
        rol_label = label_of(g, rol_uri, "")
        if GEMEENTERAADSLID_LABEL.lower() not in rol_label.lower():
            continue

        # -- Bestuursorgaan → Bestuurseenheid (= gemeente) --
        bestuursorgaan = g.value(mandaat_uri, ORG.unitOf)
        if bestuursorgaan is None:
            # Alternatief pad
            bestuursorgaan = g.value(mandaat_uri, BESLUIT.bestuurt)
        if bestuursorgaan is None:
            continue

        bestuurseenheid = g.value(bestuursorgaan, BESLUIT.isOrgaanVan)
        if bestuurseenheid is None:
            continue

        gemeente_label = label_of(g, bestuurseenheid, str(bestuurseenheid))
        gemeente_labels[str(bestuurseenheid)] = gemeente_label

        # -- Fractie ophalen --
        fractie_uri = g.value(mandataris, ORG.memberOf)
        if fractie_uri is not None:
            fractie_label = label_of(g, fractie_uri, str(fractie_uri))
        else:
            fractie_label = "Onbekend"

        data[gemeente_label][fractie_label] += 1
        gevonden += 1

    print(f"\nResultaat: {gevonden} gemeenteraadsleden gevonden in {len(data)} gemeenten.")

    if gevonden == 0:
        print("\nGeen resultaten gevonden. Mogelijke oorzaken:")
        print("  - Het bestand bevat enkel de huidige legislatuur (2025-2030)")
        print("  - De startdatum staat onder een ander predikaat")
        print("  - Het Turtle-bestand is niet van mandaten.lokaalbestuur.vlaanderen.be")
        print("\nProbeer het script opnieuw met --format nt of --format xml als het bestand")
        print("in een ander formaat is opgeslagen.")
        sys.exit(0)

    # -------------------------------------------------------------------
    # 3. Schrijf resultaat naar CSV
    # -------------------------------------------------------------------
    rows = []
    for gemeente in sorted(data.keys()):
        fracties = data[gemeente]
        totaal = sum(fracties.values())
        for fractie in sorted(fracties.keys()):
            rows.append({
                "gemeente": gemeente,
                "fractie": fractie,
                "aantal_leden": fracties[fractie],
                "totaal_raad": totaal,
            })

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["gemeente", "fractie", "aantal_leden", "totaal_raad"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"CSV geschreven naar: {args.output}")
    print(f"  → {len(rows)} rijen ({len(data)} gemeenten)")

    # Kort overzicht op scherm
    print("\n--- Voorbeeld (eerste 20 rijen) ---")
    print(f"{'Gemeente':<30} {'Fractie':<30} {'Leden':>6} {'Totaal':>7}")
    print("-" * 75)
    for row in rows[:20]:
        print(f"{row['gemeente']:<30} {row['fractie']:<30} "
              f"{row['aantal_leden']:>6} {row['totaal_raad']:>7}")
    if len(rows) > 20:
        print(f"  ... en nog {len(rows) - 20} rijen in het CSV-bestand.")


if __name__ == "__main__":
    main()
