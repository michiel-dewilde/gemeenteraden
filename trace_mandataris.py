"""Traceer exact de keten van 1 mandataris uit 2018-2019"""
from rdflib import Graph, Namespace, RDF
from rdflib.namespace import SKOS
import sys

MANDAAT = Namespace("http://data.vlaanderen.be/ns/mandaat#")
BESLUIT = Namespace("http://data.vlaanderen.be/ns/besluit#")
ORG     = Namespace("http://www.w3.org/ns/org#")
REGORG  = Namespace("https://www.w3.org/ns/regorg#")

ttl = sys.argv[1]
print(f"Laden {ttl}...")
g = Graph()
g.parse(ttl, format="turtle")
print(f"  {len(g)} triples\n")

# Zoek mandatarissen met start in 2018/2019
gevonden = 0
for mandataris in g.subjects(RDF.type, MANDAAT.Mandataris):
    start_raw = g.value(mandataris, MANDAAT.start)
    if start_raw is None:
        continue
    s = str(start_raw)[:10]
    if not (s >= "2018-10-01" and s <= "2019-06-01"):
        continue

    post = g.value(mandataris, ORG.holds)
    if post is None:
        continue

    print(f"=== Mandataris: {mandataris}")
    print(f"  start: {start_raw}")
    print(f"  org:holds -> Post: {post}")
    print(f"  Post types: {list(g.objects(post, RDF.type))}")
    print(f"  Post predicaten:")
    for p, o in g.predicate_objects(post):
        print(f"    {str(p):<55} {str(o)[:70]}")

    # Zoek orgaan dat hasPost -> post heeft
    organen = list(g.subjects(ORG.hasPost, post))
    print(f"  Bestuursorganen die hasPost->dit post: {organen}")
    for orgaan in organen:
        eenheid = g.value(orgaan, BESLUIT.bestuurt)
        print(f"    orgaan.bestuurt -> {eenheid}")
        if eenheid:
            for p2, o2 in g.predicate_objects(eenheid):
                print(f"      {str(p2):<50} {str(o2)[:60]}")

    # Lidmaatschap
    lid = g.value(mandataris, ORG.hasMembership)
    print(f"  hasMembership -> {lid}")
    if lid:
        for p, o in g.predicate_objects(lid):
            print(f"    {str(p):<55} {str(o)[:70]}")

    print()
    gevonden += 1
    if gevonden >= 3:
        break

print(f"Klaar. {gevonden} mandatarissen getoond.")
