# Gemeenteraad analyse 2018–2024

## Doel

Analyseer per Vlaamse gemeente de volledige evolutie van de gemeenteraad en het schepencollege doorheen de legislatuur 2018–2024: welke fracties hadden hoeveel leden en hoe lang duurde elke unieke samenstelling?

## Databronnen

| Bestand | Beschrijving |
|---------|-------------|
| `mandaten-20260412031500084.ttl` | ~1,69 miljoen RDF-triples uit de Mandatendatabank Vlaanderen |
| `resultaten_verkiezing_gemeenteraad_20181014_na_20190702_bldgwf.xlsx` | Officiële verkiezingsresultaten gemeenteraadsverkiezingen 14 oktober 2018 (Vlaanderen) |

De Mandatendatabank is beschikbaar via [mandaten.lokaalbestuur.vlaanderen.be](https://mandaten.lokaalbestuur.vlaanderen.be).
Het XLS-bestand is afkomstig van [assets.vlaanderen.be](https://assets.vlaanderen.be/raw/upload/v1699019526/resultaten_verkiezing_gemeenteraad_20181014_na_20190702_bldgwf.xlsx).

## Script: `1_analyseer_mandatendatabank.py`

Genereert `gemeenteraad_analyse_2018_2024.json`.

```
python 1_analyseer_mandatendatabank.py --input mandaten-20260412031500084.ttl
```

### Legislatuur-afbakening (100% correct)

De 2018–2024 organen worden geïdentificeerd via `mandaat:bindingStart` en `mandaat:bindingEinde` op `besluit:Bestuursorgaan`:

- `bindingStart = 2019-01-01` — installatiedatum na de gemeenteraadsverkiezingen van oktober 2018
- `bindingEinde` in november 2024 – februari 2025 — varieert per gemeente naargelang de installatiedatum van de nieuwe raad na oktober 2024

Alleen organen van het type **Gemeenteraad** en **College van Burgemeester en Schepenen** worden meegenomen (bepaald via `isTijdspecialisatieVan` → `skos:prefLabel`). OCMW, districten, provincieraden en burgemeester-organen worden uitgesloten.

Mandaten die vóór de legislatuur begonnen (ononderbroken carrières zonder nieuwe startdatum in de databank) worden geknipt op `bindingStart` van het orgaan.

### Werkwijze

1. Laad optioneel de verkiezings-XLS (kandidatentabblad) en bouw een opzoektabel op naam + gemeente voor de fractie-fallback (zie *Fractie-fallback* hieronder).
2. Verzamel alle mandaten per gemeente met hun start- en einddatum. `mandaat:einde` is inclusief → +1 dag voor intern gebruik (exclusief eindpunt). Ontbrekende einddatum → `bindingEinde + 1 dag`. Mandaten worden geknipt op de grenzen van het orgaan.
3. Bouw per gemeente een tijdlijn van alle unieke grenspunten (alle start- en einddatums). Elk interval `[d_i, d_{i+1})` heeft een vaste samenstelling.
4. Bepaal voor elk interval de actieve mandaten (`start ≤ datum < einde`), tel per fractie in gemeenteraad en schepencollege.
5. **Installatiefilter**: laat alle intervallen vallen vóór het eerste interval waarop de gemeenteraad haar *stabiele* ledenaantal bereikt. Het stabiele ledenaantal is het hoogste ledenaantal dat gedurende minstens 365 dagen (gesommeerd) aanwezig was; valt terug op het absolute maximum als geen enkel ledenaantal 365 dagen haalt. Zo verdwijnt de installatieperiode automatisch, zonder dat een tijdelijke verhoging van slechts enkele dagen als referentie wordt gebruikt.
6. Samenstellingen met identieke gemeenteraad + schepencollege worden samengevoegd; hun dagentelling wordt opgeteld.
7. Sorteer per gemeente op aantal dagen (desc).

### Fractie-fallback

Voor elke mandataris wordt de fractie in drie stappen bepaald:

1. **Directe registratie**: `org:hasMembership` → `org:organisation` op het mandaat zelf.
2. **GR-mandaat van dezelfde persoon**: als het college-mandaat geen fractie heeft, gebruik dan de fractie van het gemeenteraadslid-mandaat van dezelfde persoon.
3. **Verkiezings-XLS**: als ook de GR-fallback ontbreekt, zoek de persoon op via genormaliseerde naam (lowercase, accenten weg) en gemeente in de officiële verkiezingsuitslag. Matching: exact → achternaam-only → fuzzy (tt/th-normalisatie). Hardcoded uitzonderingen voor roepnamen en typografische varianten.

### Relevante rollen

| Rol | URI-suffix | Telt mee in |
|-----|-----------|-------------|
| Gemeenteraadslid | `…5e000011` | gemeenteraad |
| ~~Voorzitter gemeenteraad~~ | `…5e000012` | *(genegeerd — zie hieronder)* |
| Burgemeester | `…5e000013` | schepencollege |
| Schepen | `…5e000014` | schepencollege |
| Toegevoegd schepen | `…59a9…` | schepencollege |

De rol **Voorzitter gemeenteraad** wordt niet meegeteld: de voorzitter heeft altijd ook een actief Gemeenteraadslid-mandaat; beide rollen tegelijk meetellen geeft een dubbeltelling van 1 zetel per gemeente.

De **burgemeester** wordt niet apart bijgehouden. Hij/zij telt mee in de gemeenteraad via het Gemeenteraadslid-mandaat (aanwezig bij 387 van de burgemeesters in de dataset) en in het schepencollege via het Burgemeester-mandaat.

### Output-formaat (`gemeenteraad_analyse_2018_2024.json`)

Toplevel object: gemeentenaam (alfabetisch) → lijst van samenstellingsobjecten, gesorteerd op `dagen` (desc):

```json
{
  "Aalst": [
    {
      "dagen": 980,
      "gemeenteraad":   { "N-VA": 17, "Vlaams Belang": 7, "CD&V": 4 },
      "schepencollege": { "N-VA": 6, "Open VLD": 1 }
    }
  ]
}
```

Fracties in `gemeenteraad` en `schepencollege` zijn gesorteerd groot→klein, bij gelijke stand alfabetisch.

## Script: `2_aggregeer_gegevens.py`

Genereert `gemeenteraad_aggregatie_2018_2024.json` vanuit de tijdlijn-analyse.

```
python 2_aggregeer_gegevens.py
python 2_aggregeer_gegevens.py --input gemeenteraad_analyse_2018_2024.json \
                               --output gemeenteraad_aggregatie_2018_2024.json
```

### Werkwijze

Per gemeente berekent het script per sectie (gemeenteraad, schepencollege) het **gewogen gemiddeld aantal zetels** per fractie over de volledige legislatuur, waarbij het gewicht gelijk is aan het aantal dagen van elke periode:

```
gemiddeld_zetels(fractie) = Σ(dagen_i × zetels_i) / Σ(dagen_i)
```

### Output-formaat (`gemeenteraad_aggregatie_2018_2024.json`)

```json
{
  "Aalst": {
    "gemeenteraad":   { "N-VA": 16.0, "Vlaams Belang": 7.07, "CD&V": 4.3 },
    "schepencollege": { "N-VA": 6.0, "Open VLD": 1.0 }
  }
}
```

Fracties gesorteerd van hoog naar laag gemiddeld zetelgetal.

## Bekende beperkingen

- **Fractienamen**: de Mandatendatabank gebruikt de naam zoals geregistreerd door de gemeente. Hernoemingen (bv. sp.a → Vooruit) kunnen als aparte fracties verschijnen in opeenvolgende perioden.
- **`"Onbekend"` als fractienaam**: treedt op wanneer een mandataris geen fractielidmaatschap heeft én niet via GR-fallback of XLS gevonden wordt (bv. Poperinge: alle fracties ontbreken in de brondata).
- **URI-correcties**: fractie-URI's zonder label worden gecorrigeerd via `_FRACTIE_URI_CORRECTIES` in het script. Vastgesteld met `diagnose_fracties.py`; naam opgezocht via algemene websearch.
  | Fractie-URI | Gemeente | Gecorrigeerde naam | Leden |
  |-------------|----------|--------------------|-------|
  | `cdd79247-de17-405a-b0d6-1aacb12db93f` | Aartselaar | N-VA | Jan Van der Heyden, Sophie De Wit |
- **Variërend zetelgetal per gemeente**: tussentijdse vervangingen kunnen korte intervallen (1–5 dagen) veroorzaken met een afwijkend zetelgetal door overlap of een kleine gap in de registratie.
- **Herstappe**: ontbreekt in de dataset (te kleine gemeente, geen eigen registratie).
