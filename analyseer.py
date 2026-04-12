"""
Diagnose script voor Mandatendatabank Turtle-bestand
Toont welke predikaten, types en waarden effectief in het bestand zitten.

Gebruik:
    python diagnose_ttl.py --input mandaten-20260412031500084.ttl
"""

import argparse
import sys
from collections import Counter

try:
    from rdflib import Graph, RDF, RDFS
    from rdflib.namespace import XSD
except ImportError:
    print("Installeer rdflib eerst:  pip install rdflib")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True)
    args = parser.parse_args()

    print(f"Laden: {args.input} ...")
    g = Graph()
    g.parse(args.input, format="turtle")
    print(f"  → {len(g)} triples\n")

    # 1. Alle RDF types
    print("=" * 60)
    print("TOP 30 RDF TYPES (rdf:type)")
    print("=" * 60)
    type_counts = Counter(str(o) for s, p, o in g.triples((None, RDF.type, None)))
    for uri, cnt in type_counts.most_common(30):
        print(f"  {cnt:>6}  {uri}")

    # 2. Alle predikaten
    print("\n" + "=" * 60)
    print("TOP 40 PREDIKATEN")
    print("=" * 60)
    pred_counts = Counter(str(p) for s, p, o in g)
    for uri, cnt in pred_counts.most_common(40):
        print(f"  {cnt:>6}  {uri}")

    # 3. Zoek iets dat lijkt op een datum
    print("\n" + "=" * 60)
    print("PREDIKATEN MET DATUMWAARDEN (eerste 10 voorbeelden)")
    print("=" * 60)
    datum_preds = Counter()
    datum_voorbeelden = {}
    for s, p, o in g:
        o_str = str(o)
        if len(o_str) >= 10 and o_str[:4].isdigit() and o_str[4] == "-":
            datum_preds[str(p)] += 1
            if str(p) not in datum_voorbeelden:
                datum_voorbeelden[str(p)] = o_str
    for pred, cnt in datum_preds.most_common(15):
        print(f"  {cnt:>6}  {pred}")
        print(f"           voorbeeld: {datum_voorbeelden[pred]}")

    # 4. Zoek iets dat lijkt op "gemeenteraad" of "mandataris"
    print("\n" + "=" * 60)
    print("URI's DIE 'mandataris' OF 'gemeenteraad' BEVATTEN (max 20)")
    print("=" * 60)
    gezien = set()
    for s, p, o in g:
        for val in (str(s), str(p), str(o)):
            v_low = val.lower()
            if ("mandataris" in v_low or "gemeenteraad" in v_low) and val not in gezien:
                gezien.add(val)
                if len(gezien) <= 20:
                    print(f"  {val}")

    # 5. Dump eerste Mandataris-achtig subject volledig
    print("\n" + "=" * 60)
    print("VOLLEDIGE TRIPLES VAN EERSTE 3 SUBJECTS MET 'mandataris' IN URI")
    print("=" * 60)
    count = 0
    for s in g.subjects():
        if "mandataris" in str(s).lower():
            print(f"\n  Subject: {s}")
            for p, o in g.predicate_objects(s):
                print(f"    {str(p):<60} {str(o)[:80]}")
            count += 1
            if count >= 3:
                break

    # 6. Zoek naar "start" of "begin" predikaten
    print("\n" + "=" * 60)
    print("PREDIKATEN MET 'start' OF 'begin' IN NAAM")
    print("=" * 60)
    start_preds = set()
    for s, p, o in g:
        p_str = str(p).lower()
        if "start" in p_str or "begin" in p_str:
            start_preds.add(str(p))
    for p in sorted(start_preds):
        print(f"  {p}")

    # 7. Zoek naar fractie/partij
    print("\n" + "=" * 60)
    print("PREDIKATEN MET 'fractie' OF 'partij' OF 'memberOf' IN NAAM")
    print("=" * 60)
    frac_preds = set()
    for s, p, o in g:
        p_str = str(p).lower()
        o_str = str(o).lower()
        if any(x in p_str or x in o_str for x in ("fractie", "partij", "memberof")):
            frac_preds.add(str(p))
    for p in sorted(frac_preds):
        print(f"  {p}")

    print("\nDiagnose klaar.")


if __name__ == "__main__":
    main()
    