"""
Voegt 'in_coalitie_volgens_wikipedia' toe aan de gemeenteraad CSV
door de coalitietabel van de Wikipedia-pagina 'Belgische lokale verkiezingen 2018' te parsen.
"""

import csv
import re
import sys
import time
import unicodedata
import urllib.request
import json
from pathlib import Path
from bs4 import BeautifulSoup

WIKIPEDIA_PAGINA = "Belgische_lokale_verkiezingen_2018"

# Sectie-indexen voor Vlaamse gemeenten (niet stadsdistricten)
VLAAMSE_SECTIES = {
    "Antwerpen": 19,
    "Limburg":   23,
    "Oost-Vlaanderen":   26,
    "Vlaams-Brabant":    29,
    "West-Vlaanderen":   32,
}

UA        = "Mozilla/5.0 (gemeenteraad-research/1.0)"
CACHE_DIR = Path("wikipedia_cache")


def fetch_section_html(pagina, section_index):
    """Haalt HTML op voor een Wikipedia-sectie; gebruikt lokale cache indien aanwezig."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{pagina}_sectie{section_index}.html"

    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    url = (
        f"https://nl.wikipedia.org/w/api.php"
        f"?action=parse&page={pagina}&prop=text&section={section_index}&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r:
        html = json.load(r)["parse"]["text"]["*"]

    cache_file.write_text(html, encoding="utf-8")
    return html


def parse_coalitie_tabel(html):
    """
    Geeft een dict terug: gemeente_lower -> coalitie_string
    De eerste kolom is 'Gemeente/Zetels' (naam gevolgd door ' (N)'), laatste kolom 'Coalitie'.
    """
    soup = BeautifulSoup(html, "html.parser")
    resultaat = {}
    for tabel in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text(strip=True) for th in tabel.find_all("th")]
        if "Coalitie" not in headers:
            continue
        coalitie_idx = headers.index("Coalitie")
        for row in tabel.find_all("tr")[1:]:
            cellen = row.find_all(["td", "th"])
            if len(cellen) <= coalitie_idx:
                continue
            gemeente_cel = cellen[0].get_text(strip=True)
            # strip ' (N zetels)' suffix
            gemeente = re.sub(r"\s*\(\d+\)\s*$", "", gemeente_cel).strip()
            coalitie = cellen[coalitie_idx].get_text(separator=" ", strip=True)
            if gemeente:
                resultaat[gemeente.lower()] = coalitie
    return resultaat


# Partijen die hernoemd zijn tussen 2018 en nu.
# Sleutel = genormaliseerde huidige naam (of alias), waarde = lijst van 2018-namen.
PARTIJ_ALIASSEN = {
    "vooruit":       ["sp a", "spa", "sp a plus", "one"],
    "one":           ["sp a", "spa"],
    "vlaams belang": ["vb"],
    "vb":            ["vlaams belang"],
}


def normaliseer(s):
    """Lowercase, strip accenten en leestekens voor vergelijking."""
    s = s.lower()
    # Verwijder accenten (é -> e, ë -> e, …)
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[.\-–/&+]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def partijen_in_coalitie(coalitie_str):
    """
    Splits coalitie-string in losse partijnamen.
    Formaten: 'N-VA, CD&V, Open Vld' of 'CD&V-N-VA' of 'Lijst Burgemeester'
    """
    # Splits op komma of middenpunt; verwijder lege
    delen = re.split(r"[,·•]", coalitie_str)
    return [d.strip() for d in delen if d.strip()]


def fractie_in_coalitie(fractie_naam, partijen):
    """
    Heuristiek: fractienaam matcht als:
    1. genormaliseerde naam is substring van de coalitiestring
    2. minstens één significant woord overlapt
    3. een bekende alias (hernoeming) matcht
    """
    STOPWOORDEN = {"van", "de", "het", "en", "in", "voor", "met", "der", "en"}

    frac_norm     = normaliseer(fractie_naam)
    coalitie_norm = normaliseer(" ".join(partijen))

    # 1. Directe substring
    if frac_norm in coalitie_norm:
        return True

    # 2. Woordoverlap (beide richtingen)
    frac_woorden = [w for w in frac_norm.split() if len(w) >= 3 and w not in STOPWOORDEN]
    for woord in frac_woorden:
        if any(woord in normaliseer(p) for p in partijen):
            return True
    for partij in partijen:
        for woord in normaliseer(partij).split():
            if len(woord) >= 3 and woord not in STOPWOORDEN and woord in frac_norm:
                return True

    # 3. Partij-aliassen (hernoemingen: Vooruit = sp.a, enz.)
    for alias, oud_namen in PARTIJ_ALIASSEN.items():
        if alias in frac_norm or frac_norm in alias:
            for oud in oud_namen:
                if oud in coalitie_norm:
                    return True

    return False


def main():
    csv_in  = "gemeenteraad_samenstelling_2018_2024.csv"
    csv_uit = "gemeenteraad_samenstelling_2018_2024.csv"

    # ------------------------------------------------------------------
    # 1. Wikipedia data ophalen
    # ------------------------------------------------------------------
    print("Wikipedia coalitietabellen ophalen...")
    wiki_data = {}   # gemeente_lower -> coalitie_string
    for provincie, sectie in VLAAMSE_SECTIES.items():
        print(f"  {provincie} (sectie {sectie})...", end=" ", flush=True)
        html = fetch_section_html(WIKIPEDIA_PAGINA, sectie)
        deel = parse_coalitie_tabel(html)
        wiki_data.update(deel)
        print(f"{len(deel)} gemeenten")
        time.sleep(0.3)   # beleefd crawlen

    print(f"\nTotaal: {len(wiki_data)} Vlaamse gemeenten met coalitiedata\n")

    # ------------------------------------------------------------------
    # 2. CSV inlezen
    # ------------------------------------------------------------------
    with open(csv_in, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys()) + ["in_coalitie_volgens_wikipedia"]

    # ------------------------------------------------------------------
    # 3. Matchen
    # ------------------------------------------------------------------
    niet_gevonden = set()
    for row in rows:
        gemeente   = row["gemeente"]
        fractie    = row["fractie"]
        gem_lower  = gemeente.lower()

        if gem_lower not in wiki_data:
            row["in_coalitie_volgens_wikipedia"] = "onbekend"
            niet_gevonden.add(gemeente)
            continue

        coalitie_str = wiki_data[gem_lower]
        partijen     = partijen_in_coalitie(coalitie_str)
        match        = fractie_in_coalitie(fractie, partijen)
        row["in_coalitie_volgens_wikipedia"] = "ja" if match else "nee"

    # ------------------------------------------------------------------
    # 4. CSV wegschrijven
    # ------------------------------------------------------------------
    with open(csv_uit, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"CSV bijgewerkt -> {csv_uit}  ({len(rows)} rijen)")
    if niet_gevonden:
        print(f"\nGemeenten niet gevonden in Wikipedia ({len(niet_gevonden)}):")
        for g in sorted(niet_gevonden)[:20]:
            print(f"  {g}")
        if len(niet_gevonden) > 20:
            print(f"  ... en {len(niet_gevonden)-20} meer")

    # Verificatie Wetteren
    print("\n--- Wetteren verificatie ---")
    gem = "Wetteren"
    print(f"Wikipedia coalitie: {wiki_data.get(gem.lower(), '—')}")
    for row in rows:
        if row["gemeente"] == gem:
            print(f"  {row['fractie']:<30} {row['in_schepencollege']:<5} {row['in_coalitie_volgens_wikipedia']}")


if __name__ == "__main__":
    main()
