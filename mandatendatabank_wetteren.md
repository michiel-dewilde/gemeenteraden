# Mandatendatabank Vlaanderen — Gemeenteraad samenstelling 2018-2024

## Context

Data afkomstig van de **Mandatendatabank Vlaanderen**:
- Download (Turtle-formaat): [mandaten.lokaalbestuur.vlaanderen.be](https://mandaten.lokaalbestuur.vlaanderen.be)
- Bestand: `mandaten-20260412031500084.ttl` (~1,69 miljoen triples)

Doel: per gemeente, per fractie het aantal gemeenteraadsleden bepalen voor de legislatuur **2018–2024**, inclusief indicatie van meerderheid.

---

## Bevestigde datastructuur (uit diagnose)

```
Mandataris
  --mandaat:start-->          datetime (bv. 2019-01-03T19:14:00+00:00)
  --mandaat:einde-->          datetime
  --mandaat:status-->         URI (MandatarisStatusCode)
  --org:holds-->              Post / Mandaat
                                  --org:role-->  BestuursfunctieCode URI
  --org:hasMembership-->      Lidmaatschap
                                  --org:organisation-->  Fractie
                                                           --regorg:legalName / skos:prefLabel

Post (= mandaat:Mandaat + org:Post)
  --org:role-->               BestuursfunctieCode
  <--org:hasPost--            Bestuursorgaan (tijdgebonden, met bindingStart/bindingEinde)
                                  --mandaat:isTijdspecialisatieVan-->  Bestuursorgaan (tijdloos)
                                                                           --skos:prefLabel-->  "Gemeenteraad X"
                                                                           --besluit:bestuurt-->  Bestuurseenheid

Fractie
  --org:memberOf-->           Bestuursorgaan (tijdgebonden)
  --regorg:legalName-->       naam
```

### Namespaces

| Prefix   | URI |
|----------|-----|
| mandaat  | `http://data.vlaanderen.be/ns/mandaat#` |
| besluit  | `http://data.vlaanderen.be/ns/besluit#` |
| org      | `http://www.w3.org/ns/org#` |
| regorg   | `https://www.w3.org/ns/regorg#` |
| skos     | `http://www.w3.org/2004/02/skos/core#` |
| foaf     | `http://xmlns.com/foaf/0.1/` |
| persoon  | `http://data.vlaanderen.be/ns/persoon#` |

### Relevante BestuursfunctieCodes

| URI (einde) | Label |
|-------------|-------|
| `...5ab0e9b8a3b2ca7c5e000011` | Gemeenteraadslid |
| `...5ab0e9b8a3b2ca7c5e000012` | Voorzitter van de gemeenteraad |
| `...5ab0e9b8a3b2ca7c5e000013` | Burgemeester |
| `...5ab0e9b8a3b2ca7c5e000014` | Schepen |
| `...59a90e03-4f22-4bb9-8c91-132618db4b38` | Toegevoegde schepen |

### Periode filter (legislatuur 2018–2024)

Mandatarissen waarvan `mandaat:start` valt tussen **2018-10-01** en **2019-06-01**.

---

## Aandachtspunten / bekende problemen

### 1. Dubbele records (oorzaak afwijking Wetteren)
De Mandatendatabank bevat soms **meerdere mandataris-records voor dezelfde persoon** in dezelfde periode (bv. bij een correctie of herbenoeming halverwege de legislatuur). Dit leidt tot overtelling.

**Wetteren voorbeeld** (verwacht: 29 raadsleden, script geeft 31):
- Groen&Co: 5 records maar slechts 4 unieke personen
- Totaal: 31 records, 29 unieke personen

**Oplossing**: dedupliceer op `mandaat:isBestuurlijkeAliasVan` (= persoon-URI) per gemeente per fractie, of filter op eindstatus.

### 2. `coalitiefractie`-veld vaak leeg
Het veld `ext:isBestuurspartij` op `mandaat:Fractie` is niet altijd ingevuld door lokale besturen → waarde "onbekend" voor de meeste gemeenten.

### 3. Betrouwbaarste meerderheidsdetectie
Via schepencollege: fracties met minstens 1 mandataris met rol Burgemeester, Schepen of Toegevoegde Schepen in dezelfde gemeente en periode.

### 4. Gemeente-label ophalen
Het tijdgebonden `Bestuursorgaan` heeft **geen** directe `besluit:bestuurt` link. Die zit op het **tijdloze** orgaan, bereikbaar via `mandaat:isTijdspecialisatieVan`. Het tijdloze orgaan heeft ook `skos:prefLabel` met bv. "Gemeenteraad Wetteren" — strip de prefix "Gemeenteraad " voor de gemeentenaam.

---

## Verificatie Wetteren

Verwachte samenstelling na verificatie via VRT NWS (2023/2024 bronnen):

| Fractie | Zetels | Meerderheid |
|---------|--------|-------------|
| CD&V | 7 | ✅ ja |
| Groen&Co | 4 | ✅ ja |
| Eén | 3 | ✅ ja |
| Vooruit | 1 | ✅ ja |
| N-VA | 6 | ❌ nee |
| Open VLD | 6 | ❌ nee |
| Vlaams Belang | 3 | ❌ nee |
| **Totaal** | **30** | (29 raadsleden + 1 voorzitter) |

Script gaf 31 i.p.v. 29/30 → oorzaak: dubbel record bij Groen&Co.

---

## Scripts

### Vereiste installatie

```bash
pip install rdflib
```

---

### Script 1: `gemeenteraad_samenstelling.py`

Hoofdscript. Genereert CSV met per gemeente/fractie het aantal leden + meerderheidskolommen.

**Gebruik:**
```bash
python gemeenteraad_samenstelling.py --input mandaten.ttl --output resultaat.csv
python gemeenteraad_samenstelling.py --input mandaten.ttl --voorzitter  # ook voorzitter GR meetellen
```

**Output CSV kolommen:**
| Kolom | Beschrijving |
|-------|-------------|
| `gemeente` | Gemeentenaam |
| `fractie` | Fractienaam |
| `aantal_leden` | Aantal mandataris-records (⚠️ kan dubbels bevatten) |
| `totaal_raad` | Totaal records in die gemeente |
| `schepencollege` | ja/nee — fractie leverde schepen of burgemeester |
| `coalitiefractie` | ja/nee/onbekend — uit `ext:isBestuurspartij` veld |

```python
"""
Gemeenteraad samenstelling 2018-2024 uit Mandatendatabank Vlaanderen (Turtle)
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
EXT     = Namespace("http://mu.semte.ch/vocabularies/ext/")

ROL_GEMEENTERAADSLID = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000011")
ROL_VOORZITTER_GR    = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000012")
ROL_BURGEMEESTER     = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000013")
ROL_SCHEPEN          = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/5ab0e9b8a3b2ca7c5e000014")
ROL_TOE_SCHEPEN      = URIRef("http://data.vlaanderen.be/id/concept/BestuursfunctieCode/59a90e03-4f22-4bb9-8c91-132618db4b38")

ROLLEN_GEMEENTERAAD   = {ROL_GEMEENTERAADSLID, ROL_VOORZITTER_GR}
ROLLEN_SCHEPENCOLLEGE = {ROL_BURGEMEESTER, ROL_SCHEPEN, ROL_TOE_SCHEPEN}

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
    parser.add_argument("--output", "-o", default="gemeenteraad_samenstelling_2018_2024.csv")
    parser.add_argument("--voorzitter", action="store_true")
    args = parser.parse_args()

    toegelaten_rollen = {ROL_GEMEENTERAADSLID}
    if args.voorzitter:
        toegelaten_rollen.add(ROL_VOORZITTER_GR)

    print(f"Bestand laden: {args.input}  (dit kan even duren...)")
    g = Graph()
    g.parse(args.input, format="turtle")
    print(f"  → {len(g)} triples geladen.\n")

    print("Opzoektabellen bouwen...")

    post_rol = {}
    for post in g.subjects(RDF.type, ORG.Post):
        rol = g.value(post, ORG.role)
        if rol:
            post_rol[post] = rol

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

    post_orgaan = {}
    for orgaan, post in g.subject_objects(ORG.hasPost):
        post_orgaan[post] = orgaan

    lid_fractie = {}
    for lid in g.subjects(RDF.type, ORG.Membership):
        frac_uri = g.value(lid, ORG.organisation)
        if frac_uri:
            lid_fractie[lid] = (frac_uri, best_label(g, frac_uri))

    fractie_coalitie = {}
    for frac in g.subjects(RDF.type, MANDAAT.Fractie):
        val = (g.value(frac, EXT.isBestuurspartij) or
               g.value(frac, MANDAAT.isBestuurspartij))
        if val is not None:
            fractie_coalitie[frac] = str(val).lower() in ("true", "1", "yes", "ja")
        else:
            fractie_coalitie[frac] = None

    print(f"  Post→rol:          {len(post_rol)}")
    print(f"  Orgaan→gemeente:   {len(orgaan_gemeente)}")
    print(f"  Post→orgaan:       {len(post_orgaan)}")
    print(f"  Lid→fractie:       {len(lid_fractie)}")
    print(f"  Fracties totaal:   {len(fractie_coalitie)}\n")

    print("Mandatarissen verwerken...")

    raad_data        = defaultdict(lambda: defaultdict(set))
    college_fracties = defaultdict(set)
    fractie_labels   = {}

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

        lid_uri = g.value(mandataris, ORG.hasMembership)
        if lid_uri and lid_uri in lid_fractie:
            frac_uri, frac_lbl = lid_fractie[lid_uri]
        else:
            frac_uri, frac_lbl = None, "Onbekend"

        if frac_uri:
            fractie_labels[frac_uri] = frac_lbl

        if rol in toegelaten_rollen:
            raad_data[gemeente][frac_uri].add(mandataris)
        elif rol in ROLLEN_SCHEPENCOLLEGE:
            if frac_uri:
                college_fracties[gemeente].add(frac_uri)

    print(f"\nGemeenteraadsleden gevonden in {len(raad_data)} gemeenten.")

    rows = []
    for gemeente in sorted(raad_data):
        fracties = raad_data[gemeente]
        totaal   = sum(len(v) for v in fracties.values())
        col_fracties = college_fracties.get(gemeente, set())

        for frac_uri in sorted(fracties, key=lambda u: fractie_labels.get(u, "Onbekend")):
            frac_lbl   = fractie_labels.get(frac_uri, "Onbekend") if frac_uri else "Onbekend"
            in_college = "ja" if frac_uri in col_fracties else "nee"

            if frac_uri and frac_uri in fractie_coalitie:
                cv = fractie_coalitie[frac_uri]
                coalitie = "ja" if cv is True else ("nee" if cv is False else "onbekend")
            else:
                coalitie = "onbekend"

            rows.append({
                "gemeente":        gemeente,
                "fractie":         frac_lbl,
                "aantal_leden":    len(fracties[frac_uri]),
                "totaal_raad":     totaal,
                "schepencollege":  in_college,
                "coalitiefractie": coalitie,
            })

    fieldnames = ["gemeente", "fractie", "aantal_leden", "totaal_raad",
                  "schepencollege", "coalitiefractie"]

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"CSV geschreven → {args.output}  ({len(rows)} rijen)")


if __name__ == "__main__":
    main()
```

---

### Script 2: `debug_wetteren.py`

Analyseert één gemeente in detail: alle mandataris-records met naam, start, einde, status, fractie. Detecteert dubbele records.

**Gebruik:**
```bash
python debug_wetteren.py --input mandaten.ttl
python debug_wetteren.py --input mandaten.ttl --gemeente Gent
```

```python
"""
Debug script: analyseer alle gemeenteraadsleden voor één gemeente in de Mandatendatabank.
Toont alle records per fractie + detecteert dubbele personen.
"""

import argparse
import sys
from collections import Counter, defaultdict
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
    parser.add_argument("--input",    "-i", required=True)
    parser.add_argument("--gemeente", "-g", default="wetteren")
    args = parser.parse_args()

    gem_filter = args.gemeente.lower()

    print(f"Laden: {args.input} ...")
    g = Graph()
    g.parse(args.input, format="turtle")
    print(f"  {len(g)} triples\n")

    post_rol = {}
    for post in g.subjects(RDF.type, ORG.Post):
        rol = g.value(post, ORG.role)
        if rol:
            post_rol[post] = rol

    orgaan_gemeente = {}
    orgaan_naam     = {}
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
        orgaan_naam[orgaan]     = lbl

    post_orgaan = {}
    for orgaan, post in g.subject_objects(ORG.hasPost):
        post_orgaan[post] = orgaan

    lid_fractie = {}
    for lid in g.subjects(RDF.type, ORG.Membership):
        frac_uri = g.value(lid, ORG.organisation)
        if frac_uri:
            lid_fractie[lid] = best_label(g, frac_uri)

    records = []
    for mandataris in g.subjects(RDF.type, MANDAAT.Mandataris):
        start = parse_dt(g.value(mandataris, MANDAAT.start))
        if start is None or not (PERIODE_START <= start <= PERIODE_EINDE):
            continue

        post = g.value(mandataris, ORG.holds)
        if post is None:
            continue

        rol = post_rol.get(post)
        if rol not in ROLLEN_GEMEENTERAAD:
            continue

        orgaan  = post_orgaan.get(post)
        if orgaan is None:
            continue
        gemeente = orgaan_gemeente.get(orgaan, "")
        if gem_filter not in gemeente.lower():
            continue

        persoon = g.value(mandataris, MANDAAT.isBestuurlijkeAliasVan)
        if persoon:
            voornaam    = str(g.value(persoon, PERSOON.gebruikteVoornaam) or "")
            familienaam = str(g.value(persoon, FOAF.familyName) or "")
            naam = f"{voornaam} {familienaam}".strip()
        else:
            naam = "?"

        einde      = parse_dt(g.value(mandataris, MANDAAT.einde))
        status_uri = g.value(mandataris, MANDAAT.status)
        status     = str(status_uri).split("/")[-1] if status_uri else "—"
        lid_uri    = g.value(mandataris, ORG.hasMembership)
        fractie    = lid_fractie.get(lid_uri, "Onbekend") if lid_uri else "Onbekend"
        rol_lbl    = "Voorzitter GR" if rol == ROL_VOORZITTER_GR else "Gemeenteraadslid"

        records.append({
            "naam":           naam,
            "fractie":        fractie,
            "start":          start,
            "einde":          einde,
            "status":         status,
            "rol":            rol_lbl,
            "orgaan":         orgaan_naam.get(orgaan, gemeente),
            "mandataris_uri": str(mandataris),
        })

    records.sort(key=lambda r: (r["fractie"], r["naam"], r["start"]))

    print(f"{'='*80}")
    print(f" GEMEENTE: {args.gemeente.upper()}  —  {len(records)} records gevonden")
    print(f"{'='*80}\n")

    per_fractie = defaultdict(list)
    for r in records:
        per_fractie[r["fractie"]].append(r)

    for fractie in sorted(per_fractie):
        leden = per_fractie[fractie]
        print(f"  FRACTIE: {fractie}  ({len(leden)} records)")
        print(f"  {'Naam':<28} {'Start':<12} {'Einde':<12} {'Status':<15} {'Rol'}")
        print(f"  {'-'*28} {'-'*11} {'-'*11} {'-'*14} {'-'*15}")
        for r in sorted(leden, key=lambda x: (x["naam"], x["start"])):
            print(f"  {r['naam']:<28} {fmt_dt(r['start']):<12} {fmt_dt(r['einde']):<12} "
                  f"{r['status'][:14]:<15} {r['rol']}")
        print()

    print(f"{'='*80}")
    print(f" DUBBELE NAMEN")
    print(f"{'='*80}")
    naam_count = Counter(r["naam"] for r in records)
    dubbels    = {n: c for n, c in naam_count.items() if c > 1}
    if dubbels:
        for naam, count in sorted(dubbels.items()):
            print(f"\n  ⚠️  {naam}  ({count}x)")
            for r in [r for r in records if r["naam"] == naam]:
                print(f"     fractie={r['fractie']:<25} start={fmt_dt(r['start'])}  "
                      f"einde={fmt_dt(r['einde'])}  status={r['status']}")
    else:
        print("  Geen dubbels gevonden.")

    print(f"\n{'='*80}")
    print(f" SAMENVATTING")
    print(f"{'='*80}")
    uniek_per_fractie = defaultdict(set)
    for r in records:
        uniek_per_fractie[r["fractie"]].add(r["naam"])
    totaal_uniek = 0
    for fractie in sorted(uniek_per_fractie):
        n = len(uniek_per_fractie[fractie])
        totaal_uniek += n
        print(f"  {fractie:<30} {n} unieke personen  ({len(per_fractie[fractie])} records)")
    print(f"  {'─'*50}")
    print(f"  {'TOTAAL':<30} {totaal_uniek} uniek  ({len(records)} records)")


if __name__ == "__main__":
    main()
```

---

### Script 3: `diagnose_ttl.py`

Onderzoekt de structuur van een onbekend Turtle-bestand (types, predikaten, datumvelden, ...).

**Gebruik:**
```bash
python diagnose_ttl.py --input mandaten.ttl
```

---

## Volgende stappen / TODO

- [ ] **Deduplicatie** toevoegen aan `gemeenteraad_samenstelling.py`: tel unieke personen via `mandaat:isBestuurlijkeAliasVan` i.p.v. mandataris-URIs
- [ ] Controleren of `coalitiefractie` (`ext:isBestuurspartij`) ergens wél ingevuld is en in welke gemeenten
- [ ] Verificatie uitbreiden naar meer gemeenten via `verkiezingsresultaten.belgium.be`
- [ ] Eventueel filter op `mandaat:status` toevoegen om vervangingen te onderscheiden van originele mandaten
- [ ] Script uitbreiden voor andere legislaturen (2012–2018, 2025–2030)

---

## Bronnen

- Mandatendatabank download: https://mandaten.lokaalbestuur.vlaanderen.be
- Documentatie lokaal bestuur: https://lb.binnenlandsbestuur.vlaanderen/mandatarissen/mandatendatabank
- Verkiezingsuitslagen 2018: https://verkiezingsresultaten.belgium.be/nl/search/gemeenteraden
- VRT NWS Wetteren 2024: https://www.vrt.be/vrtnws/nl/2024/09/09/gemeenteraadsverkiezingen-13-oktober-2024-hierover-gaan-de-ver0/
