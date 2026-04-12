"""
Vergelijkt aantal_leden in de CSV met de zeteltelling op Wikipedia (2018).
Rapporteert afwijkingen per gemeente/fractie.
"""

import csv
import re
import time
import unicodedata
import urllib.request
import json
from collections import defaultdict
from pathlib import Path
from bs4 import BeautifulSoup

WIKIPEDIA_PAGINA = "Belgische_lokale_verkiezingen_2018"
VLAAMSE_SECTIES  = {"Antwerpen": 19, "Limburg": 23,
                    "Oost-Vlaanderen": 26, "Vlaams-Brabant": 29,
                    "West-Vlaanderen": 32}
UA        = "Mozilla/5.0 (gemeenteraad-research/1.0)"
CACHE_DIR = Path("wikipedia_cache")

# Mapping Wikipedia-kolomnamen -> genormaliseerde partijnamen + aliassen
# Waarde = set van genormaliseerde namen die mogen matchen
PARTIJ_MAP = {
    "cd v":     {"cd v", "cdv"},
    "n va":     {"n va", "nva"},
    "open vld": {"open vld", "open vl", "vld"},
    "sp a":     {"sp a", "spa", "vooruit", "one"},
    "groen":    {"groen"},
    "vb":       {"vb", "vlaams belang"},
    "pvda":     {"pvda", "ptb"},
}


def fetch_section_html(idx):
    """Haalt HTML op voor een Wikipedia-sectie; gebruikt lokale cache indien aanwezig."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{WIKIPEDIA_PAGINA}_sectie{idx}.html"

    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    url = (f"https://nl.wikipedia.org/w/api.php?action=parse"
           f"&page={WIKIPEDIA_PAGINA}&prop=text&section={idx}&format=json")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r:
        html = json.load(r)["parse"]["text"]["*"]

    cache_file.write_text(html, encoding="utf-8")
    return html


def normaliseer(s):
    s = s.lower()
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[.\-–/&+]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_int(tekst):
    """Eerste getal in tekst, of 0 bij '-' / 'i.s.m.' / leeg."""
    tekst = tekst.strip()
    if not tekst or tekst == "-":
        return 0
    m = re.match(r"(\d+)", tekst)
    return int(m.group(1)) if m else 0


def parse_andere(tekst):
    """
    Parset de 'Andere'-cel: '13 (SamenPlus) 8 (Anders) ...'
    Geeft dict {naam_norm: zetels}.
    """
    resultaat = {}
    for m in re.finditer(r"(\d+)\s*\(([^)]+)\)", tekst):
        zetels = int(m.group(1))
        naam   = normaliseer(m.group(2))
        if zetels > 0:
            resultaat[naam] = resultaat.get(naam, 0) + zetels
    return resultaat


def parse_tabel(html):
    """
    Geeft dict: gemeente_lower -> {partij_norm: zetels, ...}
    """
    soup  = BeautifulSoup(html, "html.parser")
    data  = {}
    for tabel in soup.find_all("table", class_="wikitable"):
        ths     = tabel.find_all("th")
        headers = [th.get_text(strip=True) for th in ths]
        if "Coalitie" not in headers:
            continue
        # kolomindexen
        coalitie_idx = headers.index("Coalitie")
        andere_idx   = headers.index("Andere") if "Andere" in headers else None
        partij_cols  = {}   # kolomindex -> partij_norm
        for i, h in enumerate(headers):
            if h in ("Gemeente/Zetels", "Andere", "Coalitie"):
                continue
            partij_cols[i] = normaliseer(h)

        for row in tabel.find_all("tr")[1:]:
            cellen = row.find_all(["td", "th"])
            if len(cellen) <= coalitie_idx:
                continue
            gemeente_raw = cellen[0].get_text(strip=True)
            gemeente     = re.sub(r"\s*\(\d+\)\s*$", "", gemeente_raw).strip()
            if not gemeente:
                continue
            gem_lower = gemeente.lower()
            data[gem_lower] = {}

            # Standaard partijkolommen
            for col_idx, partij_norm in partij_cols.items():
                if col_idx < len(cellen):
                    tekst = cellen[col_idx].get_text(strip=True)
                    # 'i.s.m.' = zit mee op lijst van andere partij
                    if "i.s.m" in tekst.lower():
                        data[gem_lower][partij_norm] = 0
                    else:
                        data[gem_lower][partij_norm] = parse_int(tekst)

            # Andere-kolom
            if andere_idx is not None and andere_idx < len(cellen):
                andere_tekst = cellen[andere_idx].get_text(separator=" ", strip=True)
                for naam, zetels in parse_andere(andere_tekst).items():
                    data[gem_lower][naam] = zetels
    return data


def csv_matches_wiki(fractie_norm, wiki_zetels):
    """
    Zoek de best passende Wikipedia-partijnaam voor een CSV-fractienaam.
    Geeft (wiki_naam, wiki_zetels) of (None, None).
    """
    STOPWOORDEN = {"van", "de", "het", "en", "in", "voor", "met", "der"}

    # 1. Directe of substring match
    for wiki_naam, z in wiki_zetels.items():
        if fractie_norm == wiki_naam or fractie_norm in wiki_naam or wiki_naam in fractie_norm:
            return wiki_naam, z

    # 2. Partij-aliassen (sp.a = vooruit, vb = vlaams belang, enz.)
    for wiki_naam, z in wiki_zetels.items():
        for canonical, aliassen in PARTIJ_MAP.items():
            if (wiki_naam in aliassen or canonical in wiki_naam) and \
               (fractie_norm in aliassen or any(a in fractie_norm for a in aliassen)):
                return wiki_naam, z

    # 3. Woordoverlap
    frac_woorden = {w for w in fractie_norm.split() if len(w) >= 3 and w not in STOPWOORDEN}
    for wiki_naam, z in wiki_zetels.items():
        wiki_woorden = {w for w in wiki_naam.split() if len(w) >= 3 and w not in STOPWOORDEN}
        if frac_woorden & wiki_woorden:
            return wiki_naam, z

    return None, None


def main():
    # --- Haal Wikipedia-data op ---
    print("Wikipedia ophalen...")
    wiki = {}
    for provincie, sectie in VLAAMSE_SECTIES.items():
        print(f"  {provincie}...", end=" ", flush=True)
        html = fetch_section_html(sectie)
        deel = parse_tabel(html)
        wiki.update(deel)
        print(f"{len(deel)} gemeenten")
        time.sleep(0.3)
    print(f"Totaal: {len(wiki)} gemeenten\n")

    # --- Lees CSV ---
    with open("gemeenteraad_samenstelling_2018_2024.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # --- Vergelijk ---
    afwijkingen = []
    geen_match  = []
    overeenkomsten = 0

    # Groepeer per gemeente
    per_gemeente = defaultdict(list)
    for r in rows:
        per_gemeente[r["gemeente"]].append(r)

    for gemeente, gem_rows in sorted(per_gemeente.items()):
        wiki_zetels = wiki.get(gemeente.lower())
        if wiki_zetels is None:
            for r in gem_rows:
                geen_match.append((gemeente, r["fractie"], r["aantal_leden"]))
            continue

        totaal_wiki  = sum(v for v in wiki_zetels.values() if v > 0)
        totaal_csv   = sum(int(r["aantal_leden"]) for r in gem_rows)

        for r in gem_rows:
            frac_norm    = normaliseer(r["fractie"])
            csv_zetels   = int(r["aantal_leden"])
            wiki_naam, wz = csv_matches_wiki(frac_norm, wiki_zetels)

            if wiki_naam is None:
                geen_match.append((gemeente, r["fractie"], csv_zetels))
            elif wz == csv_zetels:
                overeenkomsten += 1
            else:
                afwijkingen.append({
                    "gemeente":    gemeente,
                    "fractie":     r["fractie"],
                    "csv":         csv_zetels,
                    "wikipedia":   wz,
                    "wiki_naam":   wiki_naam,
                    "verschil":    csv_zetels - wz,
                })

    # --- Rapport ---
    totaal = overeenkomsten + len(afwijkingen)
    print(f"Overeenkomsten : {overeenkomsten}/{totaal} ({100*overeenkomsten//totaal if totaal else 0}%)")
    print(f"Afwijkingen    : {len(afwijkingen)}")
    print(f"Geen wiki-match: {len(geen_match)}")

    if afwijkingen:
        print(f"\n{'Gemeente':<25} {'Fractie':<28} {'CSV':>4} {'Wiki':>5} {'dif':>4}  Wiki-naam")
        print("-" * 90)
        for a in sorted(afwijkingen, key=lambda x: abs(x["verschil"]), reverse=True):
            print(f"{a['gemeente']:<25} {a['fractie']:<28} "
                  f"{a['csv']:>4} {a['wikipedia']:>5} {a['verschil']:>+4}  {a['wiki_naam']}")

    # Wetteren detail
    print("\n--- Wetteren detail ---")
    gem = "wetteren"
    wz  = wiki.get(gem, {})
    print(f"Wikipedia zetels: {wz}")
    for r in per_gemeente["Wetteren"]:
        fn = normaliseer(r["fractie"])
        wn, wv = csv_matches_wiki(fn, wz)
        ok = "OK" if wv == int(r["aantal_leden"]) else f"AFWIJKING (wiki={wv})"
        print(f"  {r['fractie']:<25} CSV={r['aantal_leden']}  wiki={wv}  {ok}")


if __name__ == "__main__":
    main()
