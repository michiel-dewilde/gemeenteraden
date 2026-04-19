"""
Genereert fractie_correcties.json: een opzoektabel van personen waarvan de fractie
onbekend is in de Mandatendatabank, per gemeente.

Het bestand dient als manuele correctielijst: vul de "Onbekend"-waarden in met de
werkelijke fractienaam. Het analysescript (1_analyseer_mandatendatabank.py) leest
dit bestand en past de fracties toe vóór de verdere analyse.

Uitvoerformaat
--------------
{
  "Poperinge": {
    "Christophe Dewaele": "Onbekend",
    "Lien Demeulenaere":  "Onbekend",
    ...
  },
  ...
}

Een persoon verschijnt alleen als zijn/haar fractie na alle terugvalmechanismen
(directe fractieregistratie + fallback op GR-mandaat) nog steeds "Onbekend" is.

Gebruik
-------
    python 3_genereer_correctielijst.py --input mandaten-20260412031500084.ttl
    # Vul fractie_correcties.json manueel aan.
    # Herrun daarna 1_analyseer_mandatendatabank.py en 2_aggregeer_gegevens.py.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date

try:
    from rdflib import Graph, Namespace, RDF, URIRef
    from rdflib.namespace import SKOS, FOAF
except ImportError:
    print("Installeer rdflib: pip install rdflib")
    sys.exit(1)

MANDAAT = Namespace("http://data.vlaanderen.be/ns/mandaat#")
BESLUIT = Namespace("http://data.vlaanderen.be/ns/besluit#")
ORG     = Namespace("http://www.w3.org/ns/org#")
REGORG  = Namespace("https://www.w3.org/ns/regorg#")
GVN     = URIRef("http://data.vlaanderen.be/ns/persoon#gebruikteVoornaam")

ROL_GEMEENTERAADSLID = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000011")
ROL_BURGEMEESTER     = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000013")
ROL_SCHEPEN          = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000014")
ROL_TOE_SCHEPEN      = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/59a90e03-4f22-4bb9-8c91-132618db4b38")
ALLE_ROLLEN = {ROL_GEMEENTERAADSLID, ROL_BURGEMEESTER, ROL_SCHEPEN, ROL_TOE_SCHEPEN}

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

_FRACTIE_CORRECTIES = {
    "http://data.lblod.info/id/fracties/cdd79247-de17-405a-b0d6-1aacb12db93f": "N-VA",
}


def parse_date(literal):
    if literal is None:
        return None
    try:
        return date.fromisoformat(str(literal).strip()[:10])
    except ValueError:
        return None


def best_label(g, uri):
    if str(uri) in _FRACTIE_CORRECTIES:
        return _FRACTIE_CORRECTIES[str(uri)]
    for pred in (SKOS.prefLabel, REGORG.legalName, FOAF.name, SKOS.altLabel):
        for obj in g.objects(uri, pred):
            if str(obj).strip():
                return str(obj).strip()
    frag = str(uri).split("/")[-1]
    if _UUID_RE.match(frag):
        return "Onbekend"
    return frag


def gemeentenaam(g, orgaan):
    tijdloos = g.value(orgaan, MANDAAT.isTijdspecialisatieVan)
    if not tijdloos:
        return None
    lbl = best_label(g, tijdloos)
    for prefix in ("Gemeenteraad ", "College van Burgemeester en Schepenen "):
        if lbl.startswith(prefix):
            return lbl[len(prefix):]
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Genereer correctielijst voor onbekende fracties"
    )
    parser.add_argument("--input",  "-i", required=True,
                        help="Turtle-bestand van de Mandatendatabank")
    parser.add_argument("--output", "-o", default="fractie_correcties.json",
                        help="Uitvoerbestand (standaard: fractie_correcties.json)")
    args = parser.parse_args()

    print(f"Laden: {args.input} ...")
    g = Graph()
    g.parse(args.input, format="turtle")
    print(f"  {len(g)} triples\n")

    post_rol = {p: g.value(p, ORG.role) for p in g.subjects(RDF.type, ORG.Post)}

    # Selecteer 2018-2024 organen
    organen = {}
    for orgaan in g.subjects(RDF.type, BESLUIT.Bestuursorgaan):
        bs = parse_date(g.value(orgaan, MANDAAT.bindingStart))
        be = parse_date(g.value(orgaan, MANDAAT.bindingEinde))
        if bs != date(2019, 1, 1):
            continue
        if be is None or not (date(2024, 11, 1) <= be <= date(2025, 3, 1)):
            continue
        gem = gemeentenaam(g, orgaan)
        if gem:
            organen[orgaan] = gem

    # Bouw GR-fractie fallback: persoon -> fractielabel van het GR-mandaat
    persoon_fractie_gr = {}
    for orgaan, gem in organen.items():
        for post in g.objects(orgaan, ORG.hasPost):
            if post_rol.get(post) != ROL_GEMEENTERAADSLID:
                continue
            for mandataris in g.subjects(ORG.holds, post):
                persoon = g.value(mandataris, MANDAAT.isBestuurlijkeAliasVan)
                if not persoon:
                    continue
                lid = g.value(mandataris, ORG.hasMembership)
                frac_uri = g.value(lid, ORG.organisation) if lid else None
                if frac_uri:
                    persoon_fractie_gr[persoon] = best_label(g, frac_uri)

    # Zoek alle mandatarissen waarvan de fractie na alle terugvalmechanismen Onbekend blijft
    onbekend = defaultdict(dict)
    gezien   = defaultdict(set)

    for orgaan, gem in organen.items():
        for post in g.objects(orgaan, ORG.hasPost):
            if post_rol.get(post) not in ALLE_ROLLEN:
                continue
            for mandataris in g.subjects(ORG.holds, post):
                lid      = g.value(mandataris, ORG.hasMembership)
                frac_uri = g.value(lid, ORG.organisation) if lid else None
                if frac_uri:
                    fractie = best_label(g, frac_uri)
                else:
                    persoon = g.value(mandataris, MANDAAT.isBestuurlijkeAliasVan)
                    fractie = persoon_fractie_gr.get(persoon, "Onbekend")

                if fractie != "Onbekend":
                    continue

                persoon = g.value(mandataris, MANDAAT.isBestuurlijkeAliasVan)
                if persoon in gezien[gem]:
                    continue
                gezien[gem].add(persoon)

                fn   = str(g.value(persoon, FOAF.familyName) or "") if persoon else ""
                gn   = str(g.value(persoon, GVN) or "") if persoon else ""
                naam = f"{gn} {fn}".strip() or str(mandataris).split("/")[-1]
                onbekend[gem][naam] = "Onbekend"

    resultaat = {gem: dict(sorted(v.items())) for gem, v in sorted(onbekend.items())}

    print(f"Gemeenten met onbekende fracties : {len(resultaat)}")
    print(f"Totaal personen                  : {sum(len(v) for v in resultaat.values())}")
    print(f"Wegschrijven naar {args.output} ...")
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(resultaat, f, ensure_ascii=False, indent=2)
    print("Klaar.")


if __name__ == "__main__":
    main()
