"""
Vult fractie_correcties.json automatisch aan vanuit de officiële verkiezingsresultaten
van de Vlaamse gemeenteraadsverkiezingen van 14 oktober 2018.

Bron XLS: https://assets.vlaanderen.be/raw/upload/v1699019526/
          resultaten_verkiezing_gemeenteraad_20181014_na_20190702_bldgwf.xlsx

Werkwijze
---------
1. Laad alle kandidaten uit het tabblad 'kandidaten' (verkozen én opvolgers — ook
   opvolgers kunnen tijdens de legislatuur raadslid worden).
2. Bouw een opzoektabel: (gemeente_genorm, achternaam_genorm, voornaam_genorm) -> lijst.
3. Voor elke 'Onbekend'-entry in fractie_correcties.json: zoek de persoon op via
   genormaliseerde naam + gemeente.  Normalisatie: lowercase, accenten verwijderd,
   leestekens verwijderd.  Voornaam: enkel het eerste token (roepnaam kan afwijken
   van de volledige voornaam in het rijksregister).
4. Schrijf de aangevulde correcties terug naar fractie_correcties.json.

Gebruik
-------
    pip install openpyxl
    python 4_vul_correcties_uit_xls.py
    python 4_vul_correcties_uit_xls.py --xls resultaten_verkiezing_...xlsx
                                        --correcties fractie_correcties.json
"""

import argparse
import json
import sys
import unicodedata
from collections import defaultdict

try:
    import openpyxl
except ImportError:
    print("Installeer openpyxl: pip install openpyxl")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

def normaliseer(tekst: str) -> str:
    """Lowercase, accenten weg, leestekens weg, overtollige spaties weg."""
    if not tekst:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(tekst))
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_str.lower().split())


def eerste_token(tekst: str) -> str:
    """Geeft het eerste woord terug (voor voornamen met meerdere namen)."""
    return normaliseer(tekst).split()[0] if tekst and tekst.strip() else ""


# ---------------------------------------------------------------------------
# Hoofdlogica
# ---------------------------------------------------------------------------

# Gemeenten waarvan de naam in de Mandatendatabank afwijkt van de naam in het XLS.
# Gemeenten waarvan de naam in de Mandatendatabank afwijkt van de naam in het XLS.
_GEMEENTE_ALIASSEN = {
    "tongeren-borgloon": "tongeren",
}

# Hardcoded correcties voor personen die niet via naammatching gevonden worden
# (roepnamen, typografische varianten in één van de bronnen).
_HARDCODED = {
    ("Brecht", "Christel Covents"): "CD&V-CDB",   # XLS: Covens (zonder t)
    ("Essen",  "Bob Konings"):      "N-VA/PLE",    # XLS: Johan Konings; Bob is roepnaam
}


def laad_kandidaten(xls_pad: str) -> dict:
    """
    Leest het kandidatentabblad en bouwt een opzoektabel:
        (gemeente_genorm, achternaam_genorm, voornaam_eerste_token) -> lijst_naam

    Bevat alle kandidaten (verkozen én opvolgers) zodat ook raadsleden die
    tijdens de legislatuur instroomden gekoppeld worden.
    """
    wb = openpyxl.load_workbook(xls_pad, read_only=True, data_only=True)
    ws = wb["kandidaten"]
    rows = ws.iter_rows(values_only=True)

    # Sla de twee notitierijen en de headerrij over
    for _ in range(3):
        next(rows)

    lookup: dict = {}           # sleutel -> lijst_naam
    ambiguous: set = set()      # sleutels met meerdere verschillende lijsten

    for r in rows:
        if not r[3]:            # lege rij
            continue
        gemeente   = normaliseer(r[3])   # col 3: kieskring
        lijst      = str(r[9]).strip()   # col 9: lijst
        achternaam = normaliseer(r[25])  # col 25: RRachternaam
        voornaam   = eerste_token(r[26]) # col 26: RRvoornaam (eerste token)

        if not achternaam or not voornaam:
            continue

        sleutel = (gemeente, achternaam, voornaam)
        if sleutel in lookup:
            if lookup[sleutel] != lijst:
                ambiguous.add(sleutel)   # zelfde naam, verschillende lijst → onzeker
        else:
            lookup[sleutel] = lijst

    # Verwijder ambigue sleutels om foute koppelingen te vermijden
    for s in ambiguous:
        del lookup[s]

    return lookup


def match_persoon(naam: str, gemeente: str, lookup: dict) -> str | None:
    """
    Probeert een persoon uit fractie_correcties.json te koppelen aan een lijst.

    Strategie (van strikt naar soepel):
    1. Exacte match op (gemeente, achternaam, voornaam_eerste_token).
    2. Achternaam-only match binnen de gemeente (enkel als er precies 1 treffer is).
    """
    delen = naam.strip().split()
    if len(delen) < 2:
        return None

    gemeente_n = normaliseer(gemeente)
    # Pas eventueel een alias toe (bv. Tongeren-Borgloon -> Tongeren)
    gemeente_xls = _GEMEENTE_ALIASSEN.get(gemeente_n, gemeente_n)
    voornaam_n = eerste_token(delen[0])
    # Achternaam = alle tokens na de voornaam (samengestelde namen zoals "Van der X")
    achternaam_n = normaliseer(" ".join(delen[1:]))

    for gem in ([gemeente_xls] if gemeente_xls == gemeente_n
                else [gemeente_n, gemeente_xls]):
        # Strategie 1: exacte sleutelMatch
        sleutel = (gem, achternaam_n, voornaam_n)
        if sleutel in lookup:
            return lookup[sleutel]

        # Strategie 2: achternaam-only binnen gemeente (unieke treffer)
        treffers = {v for (g, a, _), v in lookup.items()
                    if g == gem and a == achternaam_n}
        if len(treffers) == 1:
            return treffers.pop()

        # Strategie 3: fuzzy achternaam (verwijder dubbele letters, bv. Mattys/Matthys)
        ach_fuzzy = achternaam_n.replace("tt", "t").replace("th", "t")
        treffers = {v for (g, a, _), v in lookup.items()
                    if g == gem
                    and a.replace("tt", "t").replace("th", "t") == ach_fuzzy}
        if len(treffers) == 1:
            return treffers.pop()

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Vul fractie_correcties.json aan vanuit verkiezings-XLS"
    )
    parser.add_argument(
        "--xls", "-x",
        default="resultaten_verkiezing_gemeenteraad_20181014_na_20190702_bldgwf.xlsx",
    )
    parser.add_argument("--correcties", "-c", default="fractie_correcties.json")
    args = parser.parse_args()

    print(f"XLS laden: {args.xls} ...")
    lookup = laad_kandidaten(args.xls)
    print(f"  {len(lookup)} kandidatensleutels opgebouwd.\n")

    print(f"Correcties laden: {args.correcties} ...")
    with open(args.correcties, encoding="utf-8") as f:
        correcties = json.load(f)

    gevonden = 0
    niet_gevonden = 0

    for gemeente, personen in correcties.items():
        for naam, fractie in personen.items():
            if fractie != "Onbekend":
                continue
            resultaat = _HARDCODED.get((gemeente, naam)) or match_persoon(naam, gemeente, lookup)
            if resultaat:
                personen[naam] = resultaat
                gevonden += 1
                print(f"  OK {gemeente} - {naam} -> {resultaat}")
            else:
                niet_gevonden += 1

    print(f"\nGevonden  : {gevonden}")
    print(f"Nog open  : {niet_gevonden}")

    print(f"\nWegschrijven naar {args.correcties} ...")
    with open(args.correcties, "w", encoding="utf-8") as f:
        json.dump(correcties, f, ensure_ascii=False, indent=2)
    print("Klaar.")


if __name__ == "__main__":
    main()
