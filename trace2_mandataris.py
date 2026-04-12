"""Zoek hoe bestuursorgaan gelinkt is aan bestuurseenheid, en wat rol-URI bevat"""
from rdflib import Graph, Namespace, RDF, URIRef
from rdflib.namespace import SKOS, RDFS
import sys

MANDAAT = Namespace("http://data.vlaanderen.be/ns/mandaat#")
BESLUIT = Namespace("http://data.vlaanderen.be/ns/besluit#")
ORG     = Namespace("http://www.w3.org/ns/org#")

ttl = sys.argv[1]
print(f"Laden...")
g = Graph()
g.parse(ttl, format="turtle")
print(f"  {len(g)} triples\n")

# 1. Alle predikaten van een bestuursorgaan
orgaan = URIRef("http://data.lblod.info/id/bestuursorganen/5a31c5ba9b705947d729dc261b7062e31d3124ad70eea230754b2e35102d421a")
print("=== Bestuursorgaan predikaten ===")
for p, o in g.predicate_objects(orgaan):
    print(f"  {str(p):<60} {str(o)[:80]}")

# 2. Wat wijst NAAR dit orgaan?
print("\n=== Wie wijst naar dit bestuursorgaan? ===")
for s, p in g.subject_predicates(orgaan):
    print(f"  subject={str(s)[:70]}  pred={str(p)[:60]}")

# 3. Rol URI label
rol = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2c")
print(f"\n=== Rol URI: {rol} ===")
for p, o in g.predicate_objects(rol):
    print(f"  {str(p):<50} {str(o)[:80]}")

# 4. Toon alle BestuursfunctieCodes met hun labels
print("\n=== Alle BestuursfunctieCodes ===")
BFCODE1 = URIRef("http://mu.semte.ch/vocabularies/ext/BestuursfunctieCode")
BFCODE2 = URIRef("http://lblod.data.gift/vocabularies/organisatie/BestuursfunctieCode")
for bf_type in (BFCODE1, BFCODE2):
    for code in g.subjects(RDF.type, bf_type):
        lbl = g.value(code, SKOS.prefLabel) or g.value(code, RDFS.label) or "?"
        print(f"  {str(code)[-40:]:<45} {lbl}")

# 5. Zoek via isTijdspecialisatieVan
print("\n=== isTijdspecialisatieVan van orgaan ===")
tijdspec = g.value(orgaan, MANDAAT.isTijdspecialisatieVan)
print(f"  isTijdspecialisatieVan -> {tijdspec}")
if tijdspec:
    for p, o in g.predicate_objects(tijdspec):
        print(f"    {str(p):<55} {str(o)[:70]}")

# 6. Zoek bestuurseenheid direct
print("\n=== Bestuurseenheden (eerste 5) ===")
for i, eenheid in enumerate(g.subjects(RDF.type, BESLUIT.Bestuurseenheid)):
    lbl = g.value(eenheid, SKOS.prefLabel)
    print(f"  {eenheid}  label={lbl}")
    # Wat linkt naar deze eenheid?
    for s, p in g.subject_predicates(eenheid):
        print(f"    <-[{str(p).split('#')[-1].split('/')[-1]}]-- {str(s)[:70]}")
    if i >= 2:
        break

