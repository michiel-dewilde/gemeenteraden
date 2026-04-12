"""
Gemeenteraad samenstelling 2018-2024 uit Mandatendatabank Vlaanderen (Turtle)
=============================================================================
Gebruik:
    pip install rdflib
    python gemeenteraad_samenstelling.py --input mandaten.ttl --output resultaat.csv

Bevestigde structuur:
  Mandataris  --mandaat:start-->          datetime (2019-01-xx)
              --org:holds-->              Post/Mandaat
                                              --org:role-->  BestuursfunctieCode
                                                               URI eindigt op 5ab0e9b8a3b2ca7c5e000011 = Gemeenteraadslid
              --org:hasMembership-->      Lidmaatschap
                                              --org:organisation-->  Fractie
                                                                        --regorg:legalName / skos:prefLabel
  Post        <--org:hasPost--           Bestuursorgaan (tijdgebonden)
                                              --mandaat:isTijdspecialisatieVan-->  Bestuursorgaan (tijdloos)
                                                                                       --skos:prefLabel-->  "Gemeenteraad X"
                                                                                       --besluit:bestuurt-->  Bestuurseenheid
  Fractie     --org:memberOf-->          Bestuursorgaan (tijdgebonden)
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone

try:
    from rdflib import Graph, Namespace, RDF, URIRef
    from rdflib.namespace import SKOS, FOAF
except ImportError:
    print("Installeer rdflib eerst:  pip install rdflib")
    sys.exit(1)

MANDAAT = Namespace("http://data.vlaanderen.be/ns/mandaat#")
BESLUIT = Namespace("http://data.vlaanderen.be/ns/besluit#")
ORG     = Namespace("http://www.w3.org/ns/org#")
REGORG  = Namespace("https://www.w3.org/ns/regorg#")

# URI van de rol "Gemeenteraadslid" in de codelijst
ROL_GEMEENTERAADSLID = URIRef(
    "http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000011"
)
# Ook de voorzitter van de gemeenteraad meetellen (optioneel, staat uit)
ROL_VOORZITTER = URIRef(
    "http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000012"
)

# Legislatuur 2018-2024: start tussen 1 okt 2018 en 1 jun 2019
PERIODE_START = datetime(2018, 10, 1, tzinfo=timezone.utc)
PERIODE_EINDE = datetime(2019,  6, 1, tzinfo=timezone.utc)


def parse_dt(literal):
    """Parset RDF datum/datetime naar timezone-aware datetime, of None."""
    if literal is None:
        return None
    s = str(literal).strip()[:19]   # knip subseconden en offset weg
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
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
    parser = argparse.ArgumentParser(
        description="Gemeenteraad samenstelling 2018-2024 uit Mandatendatabank Turtle"
    )
    parser.add_argument("--input",  "-i", required=True,
                        help="Pad naar het Turtle-bestand")
    parser.add_argument("--output", "-o",
                        default="gemeenteraad_samenstelling_2018_2024.csv",
                        help="Uitvoer CSV (standaard: gemeenteraad_samenstelling_2018_2024.csv)")
    parser.add_argument("--voorzitter", action="store_true",
                        help="Ook de voorzitter van de gemeenteraad meetellen")
    args = parser.parse_args()

    toegelaten_rollen = {ROL_GEMEENTERAADSLID}
    if args.voorzitter:
        toegelaten_rollen.add(ROL_VOORZITTER)

    # ------------------------------------------------------------------
    # 1. Laad het bestand
    # ------------------------------------------------------------------
    print(f"Bestand laden: {args.input}  (dit kan even duren...)")
    g = Graph()
    g.parse(args.input, format="turtle")
    print(f"  → {len(g)} triples geladen.\n")

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
    # Pad: orgaan_tijdgeb --isTijdspecialisatieVan--> orgaan_tijdloos --skos:prefLabel--> label
    # We strippen "Gemeenteraad " prefix om enkel de gemeentenaam te krijgen
    orgaan_gemeente = {}
    for orgaan_tijdgeb in g.subjects(RDF.type, BESLUIT.Bestuursorgaan):
        tijdloos = g.value(orgaan_tijdgeb, MANDAAT.isTijdspecialisatieVan)
        if tijdloos is None:
            continue
        lbl = best_label(g, tijdloos)
        # Label is bv. "Gemeenteraad Nieuwerkerken" → strip prefix
        for prefix in ("Gemeenteraad ", "OCMW ", "District ", "Provincieraad "):
            if lbl.startswith(prefix):
                lbl = lbl[len(prefix):]
                break
        orgaan_gemeente[orgaan_tijdgeb] = lbl

    # Post -> tijdgebonden bestuursorgaan (omgekeerde richting van hasPost)
    post_orgaan = {}
    for orgaan, post in g.subject_objects(ORG.hasPost):
        post_orgaan[post] = orgaan

    # Lidmaatschap -> fractie-label
    lid_fractie = {}
    for lid in g.subjects(RDF.type, ORG.Membership):
        frac_uri = g.value(lid, ORG.organisation)
        if frac_uri:
            lid_fractie[lid] = best_label(g, frac_uri)

    print(f"  Post→rol:          {len(post_rol)}")
    print(f"  Orgaan→gemeente:   {len(orgaan_gemeente)}")
    print(f"  Post→orgaan:       {len(post_orgaan)}")
    print(f"  Lid→fractie:       {len(lid_fractie)}\n")

    # ------------------------------------------------------------------
    # 3. Verwerk mandatarissen
    # ------------------------------------------------------------------
    print("Mandatarissen verwerken...")

    # gemeente -> fractie -> set van mandataris-URIs
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

        # Post ophalen
        post = g.value(mandataris, ORG.holds)
        if post is None:
            skip_rol += 1
            continue

        # Rol filteren
        rol = post_rol.get(post)
        if rol not in toegelaten_rollen:
            skip_rol += 1
            continue

        # Bestuursorgaan → gemeente
        orgaan = post_orgaan.get(post)
        if orgaan is None:
            skip_orgaan += 1
            continue
        gemeente = orgaan_gemeente.get(orgaan)
        if not gemeente:
            skip_orgaan += 1
            continue

        # Fractie
        lid_uri = g.value(mandataris, ORG.hasMembership)
        fractie = lid_fractie.get(lid_uri, "Onbekend") if lid_uri else "Onbekend"

        data[gemeente][fractie].add(mandataris)
        gevonden += 1

    print(f"\nResultaat: {gevonden} gemeenteraadsleden in {len(data)} gemeenten.\n")

    if gevonden == 0:
        print("Debug – eerste 5 mandaat#start waarden:")
        for i, (_, _, o) in enumerate(g.triples((None, MANDAAT.start, None))):
            print(f"  raw={str(o)!r}  parse={parse_dt(o)}")
            if i >= 4:
                break
        print("\nRol URI's die voorkomen op Posts (eerste 10):")
        rollen = set()
        for post, rol in list(post_rol.items())[:500]:
            rollen.add(str(rol))
        for r in list(rollen)[:10]:
            print(f"  {r}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 4. Schrijf CSV
    # ------------------------------------------------------------------
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
        w = csv.DictWriter(
            f, fieldnames=["gemeente", "fractie", "aantal_leden", "totaal_raad"]
        )
        w.writeheader()
        w.writerows(rows)

    print(f"CSV geschreven → {args.output}  ({len(rows)} rijen)\n")

    # Voorbeeld op scherm
    print(f"{'Gemeente':<30} {'Fractie':<35} {'Leden':>6} {'Totaal':>7}")
    print("-" * 82)
    for row in rows[:30]:
        print(f"{row['gemeente']:<30} {row['fractie']:<35} "
              f"{row['aantal_leden']:>6} {row['totaal_raad']:>7}")
    if len(rows) > 30:
        print(f"  ... en nog {len(rows)-30} rijen in het CSV.")


if __name__ == "__main__":
    main()
