"""
Analyseert de samenstelling van gemeenteraad en schepencollege per Vlaamse gemeente
voor de volledige legislatuur 2018-2024.

Werkwijze
---------
1. ORGANEN IDENTIFICEREN  (correcte legislatuur-afbakening)
   Selecteer alle besluit:Bestuursorgaan met:
     - mandaat:bindingStart = 2019-01-01  (installatiedatum na gemeenteraadsverkiezingen okt 2018)
     - mandaat:bindingEinde in nov 2024 – feb 2025  (einde na gemeenteraadsverkiezingen okt 2024)
   Dit is de correcte methode; een filter op mandaat:start van de mandataris zelf zou
   mid-legislatuur vervangingen niet correct afbakenen.

2. MANDATEN VERZAMELEN
   Relevante rollen per orgaan:
     Gemeenteraad : gemeenteraadslid (…000011) en voorzitter gemeenteraad (…000012)
     Schepencollege: burgemeester (…000013), schepen (…000014), toegevoegd schepen (…59a9…)
   Per mandaat: fractie, startdatum, einddatum (exclusief = mandaat:einde + 1 dag).
   Ontbrekende einddatum → orgaan.bindingEinde + 1 dag.

3. WIJZIGINGSMOMENTEN
   De unieke verzameling van alle start- en einddatums per gemeente vormt de
   "tijdlijn". Elk interval [d_i, d_{i+1}) heeft een vaste samenstelling.

4. SAMENSTELLING PER INTERVAL
   Actieve mandaten op datum d: start ≤ d < einde (exclusief).
   Per interval:
     - burgemeester : fractienaam van de actieve burgemeester
     - gemeenteraad : {fractie: aantal_leden}, gesorteerd groot→klein, dan alfabetisch
     - schepencollege: {fractie: aantal_leden}, zelfde sortering
   Fracties met identieke naam worden samengevoegd.

5. DEDUPLICATIE EN AGGREGATIE
   Perioden met exact dezelfde samenstelling (zelfde burgemeester, gemeenteraad én
   schepencollege) worden samengevoegd; hun dagentelling wordt opgeteld.
   Eindresultaat per gemeente: lijst gesorteerd op aantal dagen (desc).

6. JSON-UITVOER
   Toplevel: gemeentenaam (alfabetisch) → lijst van objecten:
     { "dagen": int, "burgemeester": str,
       "gemeenteraad":   {fractie: aantal, ...},
       "schepencollege": {fractie: aantal, ...} }

Gebruik
-------
    pip install rdflib
    python 1_analyseer_mandatendatabank.py --input mandaten-20260412031500084.ttl
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta

try:
    from rdflib import Graph, Namespace, RDF, URIRef
    from rdflib.namespace import SKOS, FOAF
except ImportError:
    print("Installeer rdflib: pip install rdflib")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------
MANDAAT = Namespace("http://data.vlaanderen.be/ns/mandaat#")
BESLUIT = Namespace("http://data.vlaanderen.be/ns/besluit#")
ORG     = Namespace("http://www.w3.org/ns/org#")
REGORG  = Namespace("https://www.w3.org/ns/regorg#")

# ---------------------------------------------------------------------------
# Rollen (BestuursfunctieCode URI's)
# ---------------------------------------------------------------------------
ROL_GEMEENTERAADSLID = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000011")
ROL_VOORZITTER_GR    = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000012")
ROL_BURGEMEESTER     = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000013")
ROL_SCHEPEN          = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000014")
ROL_TOE_SCHEPEN      = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/59a90e03-4f22-4bb9-8c91-132618db4b38")

ROLLEN_GR      = {ROL_GEMEENTERAADSLID, ROL_VOORZITTER_GR}
ROLLEN_COLLEGE = {ROL_BURGEMEESTER, ROL_SCHEPEN, ROL_TOE_SCHEPEN}
ALLE_ROLLEN    = ROLLEN_GR | ROLLEN_COLLEGE

# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

def parse_date(literal):
    """Zet een RDF-literal om naar een Python date-object (neemt enkel de datumcomponent)."""
    if literal is None:
        return None
    s = str(literal).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE
)

def best_label(g, uri):
    """
    Geeft het beste beschikbare tekstlabel voor een URI terug.
    Geeft "Onbekend" als er geen label bestaat of de URI enkel een UUID bevat
    (wat betekent dat de fractie-beschrijving ontbreekt in de TTL-dump).
    """
    for pred in (SKOS.prefLabel, REGORG.legalName, FOAF.name, SKOS.altLabel):
        for obj in g.objects(uri, pred):
            lbl = str(obj).strip()
            if lbl:
                return lbl
    fragment = str(uri).split("/")[-1]
    if _UUID_RE.match(fragment):
        return "Onbekend"  # fractie bestaat maar heeft geen label in de data
    return fragment


def gemeentenaam_van_orgaan(g, orgaan):
    """
    Haalt de gemeentenaam op via:
        orgaan -> mandaat:isTijdspecialisatieVan -> tijdloos orgaan -> skos:prefLabel
    Geeft enkel een naam terug voor gemeenteraad- en schepencollegeorganen.
    Alle andere organen (OCMW, district, provincieraad, burgemeester-organen, ...)
    worden uitgesloten door None terug te geven.
    """
    tijdloos = g.value(orgaan, MANDAAT.isTijdspecialisatieVan)
    if tijdloos is None:
        return None
    lbl = best_label(g, tijdloos)
    for prefix in (
        "Gemeenteraad ",
        "College van Burgemeester en Schepenen ",
    ):
        if lbl.startswith(prefix):
            return lbl[len(prefix):]
    return None  # OCMW, District, Provincieraad, Burgemeester-organen, ... -> uitsluiten


def sorteer_op_grootte(telling):
    """Sorteert een {fractie: aantal}-dict: groot naar klein, bij gelijke stand alfabetisch."""
    return dict(sorted(telling.items(), key=lambda kv: (-kv[1], kv[0])))


def samenstelling_sleutel(burgemeester, gemeenteraad, schepencollege):
    """Maakt een hashbare sleutel van een samenstelling voor deduplicatie."""
    return (
        burgemeester,
        tuple(sorted(gemeenteraad.items())),
        tuple(sorted(schepencollege.items())),
    )


# ---------------------------------------------------------------------------
# Stap 1 & 2: mandaten laden
# ---------------------------------------------------------------------------

def laad_mandaten(g):
    """
    Identificeert de 2018-2024 organen en verzamelt alle relevante mandaten per gemeente.

    Geeft terug: dict  gemeente_naam -> list van dicts
        { "start": date, "einde": date (exclusief), "rol": URIRef, "fractie": str }
    """
    # Opzoektabel: post URI -> rol URI
    post_rol = {post: g.value(post, ORG.role) for post in g.subjects(RDF.type, ORG.Post)}

    # Opzoektabel: orgaan URI -> gemeentenaam
    orgaan_gemeente = {}
    for orgaan in g.subjects(RDF.type, BESLUIT.Bestuursorgaan):
        naam = gemeentenaam_van_orgaan(g, orgaan)
        if naam:
            orgaan_gemeente[orgaan] = naam

    # Selecteer 2018-2024 organen op basis van bindingStart en bindingEinde
    #   bindingStart = 2019-01-01 : de installatiedatum van de nieuwe raden na de
    #                                gemeenteraadsverkiezingen van oktober 2018
    #   bindingEinde  in [nov 2024, feb 2025]: einde na de gemeenteraadsverkiezingen
    #                                          van oktober 2024 (varieert per gemeente)
    organen_2018_2024 = {}  # orgaan URI -> (inclusief startdatum, exclusief eindedatum)
    for orgaan in g.subjects(RDF.type, BESLUIT.Bestuursorgaan):
        bs = parse_date(g.value(orgaan, MANDAAT.bindingStart))
        be = parse_date(g.value(orgaan, MANDAAT.bindingEinde))
        if bs is None or be is None:
            continue
        if bs != date(2019, 1, 1):
            continue
        if not (date(2024, 11, 1) <= be <= date(2025, 3, 1)):
            continue
        organen_2018_2024[orgaan] = (bs, be + timedelta(days=1))  # (start_incl, einde_excl)

    print(f"  2018-2024 organen gevonden : {len(organen_2018_2024)}")

    # Mandaten verzamelen
    mandaten_per_gemeente = defaultdict(list)
    teller = 0

    for orgaan, (orgaan_start, orgaan_einde_excl) in organen_2018_2024.items():
        gemeente = orgaan_gemeente.get(orgaan)
        if not gemeente:
            continue

        for post in g.objects(orgaan, ORG.hasPost):
            rol = post_rol.get(post)
            if rol not in ALLE_ROLLEN:
                continue

            for mandataris in g.subjects(ORG.holds, post):
                start = parse_date(g.value(mandataris, MANDAAT.start))
                if start is None:
                    continue

                einde_raw = parse_date(g.value(mandataris, MANDAAT.einde))
                # mandaat:einde is een inclusieve datum -> voeg 1 dag toe voor exclusief gebruik
                einde_excl = (einde_raw + timedelta(days=1)
                              if einde_raw is not None
                              else orgaan_einde_excl)

                # Clip op orgaanperiode: mandaten die vóór de legislatuur begonnen of erna
                # eindigen (databank registreert soms ononderbroken carrières zonder nieuwe
                # startdatum) worden bijgesneden tot de grenzen van het orgaan.
                start      = max(start,      orgaan_start)
                einde_excl = min(einde_excl, orgaan_einde_excl)
                if start >= einde_excl:
                    continue  # mandaat valt volledig buiten de orgaanperiode

                lid_uri  = g.value(mandataris, ORG.hasMembership)
                frac_uri = g.value(lid_uri, ORG.organisation) if lid_uri else None
                fractie  = best_label(g, frac_uri) if frac_uri else "Onbekend"

                mandaten_per_gemeente[gemeente].append({
                    "start":   start,
                    "einde":   einde_excl,
                    "rol":     rol,
                    "fractie": fractie,
                })
                teller += 1

    print(f"  Mandaten verzameld         : {teller}")
    print(f"  Gemeenten                  : {len(mandaten_per_gemeente)}")
    return mandaten_per_gemeente


# ---------------------------------------------------------------------------
# Stap 3-5: analyseer een gemeente
# ---------------------------------------------------------------------------

def analyseer_gemeente(mandaten):
    """
    Berekent per gemeente de unieke samenstellingsperioden met hun dagentelling.

    Input:  lijst van mandate-dicts { start, einde (excl.), rol, fractie }
    Output: lijst van dicts { "dagen", "burgemeester", "gemeenteraad", "schepencollege" },
            gesorteerd op aantal dagen (desc)
    """
    # Alle unieke grenspunten op de tijdlijn
    datums = sorted({m["start"] for m in mandaten} | {m["einde"] for m in mandaten})

    # Deduplicatietabel: samenstelling_sleutel -> samenstellingsdict
    unieke_samenstellingen = {}

    for i in range(len(datums) - 1):
        d_start = datums[i]
        d_einde = datums[i + 1]
        dagen   = (d_einde - d_start).days

        # Actieve mandaten: start <= d_start < einde (exclusief)
        actief = [m for m in mandaten if m["start"] <= d_start < m["einde"]]
        if not actief:
            continue

        # Tel per fractie in gemeenteraad en schepencollege
        gr_telling  = defaultdict(int)
        col_telling = defaultdict(int)
        burgemeester_fractie = None

        for m in actief:
            if m["rol"] in ROLLEN_GR:
                gr_telling[m["fractie"]] += 1
            if m["rol"] in ROLLEN_COLLEGE:
                col_telling[m["fractie"]] += 1
            if m["rol"] == ROL_BURGEMEESTER:
                burgemeester_fractie = m["fractie"]

        gr_gesorteerd  = sorteer_op_grootte(dict(gr_telling))
        col_gesorteerd = sorteer_op_grootte(dict(col_telling))

        sleutel = samenstelling_sleutel(
            burgemeester_fractie or "Onbekend",
            gr_gesorteerd,
            col_gesorteerd,
        )

        if sleutel in unieke_samenstellingen:
            # Zelfde samenstelling: tel dagen bij
            unieke_samenstellingen[sleutel]["dagen"] += dagen
        else:
            unieke_samenstellingen[sleutel] = {
                "dagen":          dagen,
                "burgemeester":   burgemeester_fractie or "Onbekend",
                "gemeenteraad":   gr_gesorteerd,
                "schepencollege": col_gesorteerd,
            }

    return sorted(unieke_samenstellingen.values(), key=lambda s: -s["dagen"])


# ---------------------------------------------------------------------------
# Hoofdprogramma
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Gemeenteraad/schepencollege analyse 2018-2024")
    parser.add_argument("--input",  "-i", required=True,
                        help="Pad naar het Turtle-bestand van de Mandatendatabank")
    parser.add_argument("--output", "-o", default="gemeenteraad_analyse_2018_2024.json",
                        help="Pad voor het JSON-uitvoerbestand")
    args = parser.parse_args()

    print(f"Laden: {args.input} ...")
    g = Graph()
    g.parse(args.input, format="turtle")
    print(f"  {len(g)} triples geladen.\n")

    print("Mandaten verzamelen voor legislatuur 2018-2024...")
    mandaten_per_gemeente = laad_mandaten(g)
    print()

    print("Analyseren per gemeente...")
    resultaat = {
        gemeente: analyseer_gemeente(mandaten_per_gemeente[gemeente])
        for gemeente in sorted(mandaten_per_gemeente)
    }

    print(f"Wegschrijven naar {args.output} ...")
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(resultaat, f, ensure_ascii=False, indent=2)

    print("Klaar.\n")

    # Voorbeeldoutput voor de eerste gemeente
    eerste_gemeente, perioden = next(iter(resultaat.items()))
    print(f"Voorbeeld: {eerste_gemeente}  ({len(perioden)} unieke samenstellingen)")
    for p in perioden[:3]:
        print(f"  {p['dagen']:>4} dagen | burgemeester: {p['burgemeester']}")
        print(f"    Gemeenteraad   : {p['gemeenteraad']}")
        print(f"    Schepencollege : {p['schepencollege']}")


if __name__ == "__main__":
    main()
