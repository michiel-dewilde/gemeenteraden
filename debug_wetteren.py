"""
Debug script: analyseer alle gemeenteraadsleden voor Wetteren in de Mandatendatabank
Toont alle mandataris-records met naam, start, einde, fractie en status
zodat dubbels en anomalieën zichtbaar worden.

Gebruik:
    python debug_wetteren.py --input mandaten.ttl
"""

import argparse
import sys
from datetime import datetime, timezone

try:
    from rdflib import Graph, Namespace, RDF, URIRef
    from rdflib.namespace import SKOS, FOAF
except ImportError:
    print("pip install rdflib")
    sys.exit(1)

MANDAAT = Namespace("http://data.vlaanderen.be/ns/mandaat#")
BESLUIT = Namespace("http://data.vlaanderen.be/ns/besluit#")
ORG     = Namespace("http://www.w3.org/ns/org#")
REGORG  = Namespace("https://www.w3.org/ns/regorg#")
PERSOON = Namespace("http://data.vlaanderen.be/ns/persoon#")

ROL_GEMEENTERAADSLID = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000011")
ROL_VOORZITTER_GR    = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000012")
ROLLEN_GEMEENTERAAD  = {ROL_GEMEENTERAADSLID, ROL_VOORZITTER_GR}

PERIODE_START = datetime(2018, 10, 1, tzinfo=timezone.utc)
PERIODE_EINDE = datetime(2019,  6, 1, tzinfo=timezone.utc)

GEMEENTE_FILTER = "wetteren"


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


def fmt_dt(dt):
    return dt.strftime("%Y-%m-%d") if dt else "—"


def best_label(g, uri):
    for pred in (SKOS.prefLabel, REGORG.legalName, FOAF.name, SKOS.altLabel):
        for obj in g.objects(uri, pred):
            lbl = str(obj).strip()
            if lbl:
                return lbl
    return str(uri).split("/")[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--gemeente", "-g", default=GEMEENTE_FILTER,
                        help="Gemeente om te analyseren (default: wetteren)")
    args = parser.parse_args()

    gem_filter = args.gemeente.lower()

    print(f"Laden: {args.input} ...")
    g = Graph()
    g.parse(args.input, format="turtle")
    print(f"  {len(g)} triples\n")

    # --- Opzoektabellen (zelfde als hoofdscript) ---
    post_rol = {}
    for post in g.subjects(RDF.type, ORG.Post):
        rol = g.value(post, ORG.role)
        if rol:
            post_rol[post] = rol

    orgaan_gemeente = {}
    orgaan_naam = {}
    for orgaan in g.subjects(RDF.type, BESLUIT.Bestuursorgaan):
        tijdloos = g.value(orgaan, MANDAAT.isTijdspecialisatieVan)
        if tijdloos is None:
            continue
        lbl = best_label(g, tijdloos)
        naam_clean = lbl
        for prefix in ("Gemeenteraad ", "OCMW ", "District ", "Provincieraad ",
                        "College van Burgemeester en Schepenen ",
                        "Raad voor Maatschappelijk Welzijn "):
            if lbl.startswith(prefix):
                naam_clean = lbl[len(prefix):]
                break
        orgaan_gemeente[orgaan] = naam_clean
        orgaan_naam[orgaan] = lbl  # volledige naam incl. prefix

    post_orgaan = {}
    for orgaan, post in g.subject_objects(ORG.hasPost):
        post_orgaan[post] = orgaan

    lid_fractie = {}
    for lid in g.subjects(RDF.type, ORG.Membership):
        frac_uri = g.value(lid, ORG.organisation)
        if frac_uri:
            lid_fractie[lid] = best_label(g, frac_uri)

    # --- Verzamel alle records voor de gevraagde gemeente ---
    records = []

    for mandataris in g.subjects(RDF.type, MANDAAT.Mandataris):
        start_raw = g.value(mandataris, MANDAAT.start)
        start = parse_dt(start_raw)
        if start is None or not (PERIODE_START <= start <= PERIODE_EINDE):
            continue

        post = g.value(mandataris, ORG.holds)
        if post is None:
            continue

        rol = post_rol.get(post)
        if rol not in ROLLEN_GEMEENTERAAD:
            continue

        orgaan = post_orgaan.get(post)
        if orgaan is None:
            continue
        gemeente = orgaan_gemeente.get(orgaan, "")
        if gem_filter not in gemeente.lower():
            continue

        # Naam persoon
        persoon = g.value(mandataris, MANDAAT.isBestuurlijkeAliasVan)
        if persoon:
            voornaam  = str(g.value(persoon, PERSOON.gebruikteVoornaam) or "")
            familienaam = str(g.value(persoon, FOAF.familyName) or "")
            naam = f"{voornaam} {familienaam}".strip()
        else:
            naam = "?"

        einde = parse_dt(g.value(mandataris, MANDAAT.einde))
        status_uri = g.value(mandataris, MANDAAT.status)
        status = str(status_uri).split("/")[-1] if status_uri else "—"

        lid_uri = g.value(mandataris, ORG.hasMembership)
        fractie = lid_fractie.get(lid_uri, "Onbekend") if lid_uri else "Onbekend"

        orgaan_volledig = orgaan_naam.get(orgaan, gemeente)
        rol_lbl = "Voorzitter GR" if rol == ROL_VOORZITTER_GR else "Gemeenteraadslid"

        records.append({
            "naam":     naam,
            "fractie":  fractie,
            "start":    start,
            "einde":    einde,
            "status":   status,
            "rol":      rol_lbl,
            "orgaan":   orgaan_volledig,
            "mandataris_uri": str(mandataris),
        })

    records.sort(key=lambda r: (r["fractie"], r["naam"], r["start"]))

    print(f"{'='*80}")
    print(f" ALLE GEMEENTERAADSLEDEN GEVONDEN VOOR: {args.gemeente.upper()}")
    print(f" Startdatum filter: {fmt_dt(PERIODE_START)} → {fmt_dt(PERIODE_EINDE)}")
    print(f"{'='*80}")
    print(f" Totaal records: {len(records)}")
    print(f"{'='*80}\n")

    # --- Per fractie weergeven ---
    from collections import defaultdict
    per_fractie = defaultdict(list)
    for r in records:
        per_fractie[r["fractie"]].append(r)

    for fractie in sorted(per_fractie):
        leden = per_fractie[fractie]
        print(f"{'─'*80}")
        print(f"  FRACTIE: {fractie}  ({len(leden)} records)")
        print(f"{'─'*80}")
        print(f"  {'Naam':<28} {'Start':<12} {'Einde':<12} {'Status':<15} {'Rol':<16} {'Orgaan'}")
        print(f"  {'-'*28} {'-'*11} {'-'*11} {'-'*14} {'-'*15} {'-'*30}")
        for r in sorted(leden, key=lambda x: (x["naam"], x["start"])):
            print(f"  {r['naam']:<28} {fmt_dt(r['start']):<12} {fmt_dt(r['einde']):<12} "
                  f"{r['status'][:14]:<15} {r['rol']:<16} {r['orgaan']}")
        print()

    # --- Detecteer dubbels (zelfde naam, meerdere records) ---
    print(f"\n{'='*80}")
    print(f" DUBBELE NAMEN (zelfde persoon, meerdere mandataris-records)")
    print(f"{'='*80}")
    from collections import Counter
    naam_count = Counter(r["naam"] for r in records)
    dubbels = {n: c for n, c in naam_count.items() if c > 1}
    if dubbels:
        for naam, count in sorted(dubbels.items()):
            print(f"\n  ⚠️  {naam}  ({count}x)")
            for r in [r for r in records if r["naam"] == naam]:
                print(f"       fractie={r['fractie']:<25} start={fmt_dt(r['start'])}  "
                      f"einde={fmt_dt(r['einde'])}  status={r['status']}")
                print(f"       uri={r['mandataris_uri']}")
    else:
        print("  Geen dubbels gevonden.")

    # --- Samenvatting per fractie ---
    print(f"\n{'='*80}")
    print(f" SAMENVATTING (unieke namen per fractie)")
    print(f"{'='*80}")
    uniek_per_fractie = defaultdict(set)
    for r in records:
        uniek_per_fractie[r["fractie"]].add(r["naam"])
    totaal_uniek = 0
    for fractie in sorted(uniek_per_fractie):
        n = len(uniek_per_fractie[fractie])
        totaal_uniek += n
        print(f"  {fractie:<30} {n} unieke personen  "
              f"({len(per_fractie[fractie])} records)")
    print(f"  {'─'*50}")
    print(f"  {'TOTAAL':<30} {totaal_uniek} unieke personen  "
          f"({len(records)} records)")


if __name__ == "__main__":
    main()
