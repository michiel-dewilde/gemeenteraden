# Gemeenteraad samenstelling 2018–2024

## Doel

Bepaal per Vlaamse gemeente de samenstelling van de gemeenteraad voor de legislatuur 2018–2024: welke fracties hebben hoeveel leden, wie zit in het schepencollege, wie is voorzitter, en welke fracties zijn coalitiepartner?

## Databronnen

| Bron | Gebruik |
|------|---------|
| `mandaten-20260412031500084.ttl` | Ruwe data — ~1,69 miljoen RDF-triples uit de Mandatendatabank Vlaanderen |
| Wikipedia — *Belgische lokale verkiezingen 2018* | Verificatie zeteltelling + officieuze coalitie-annotatie |

De Mandatendatabank is beschikbaar via [mandaten.lokaalbestuur.vlaanderen.be](https://mandaten.lokaalbestuur.vlaanderen.be).

## Scripts

### `gemeenteraad_samenstelling.py`  ← hoofdscript
Genereert `gemeenteraad_samenstelling_2018_2024.csv`.

```
python gemeenteraad_samenstelling.py --input mandaten-20260412031500084.ttl
```

**Werkwijze:**
- Filtert mandatarissen met `mandaat:start` tussen 2018-10-01 en 2019-06-01
- Rollen: gemeenteraadslid (`…5e000011`) **en** voorzitter gemeenteraad (`…5e000012`) tellen mee in `aantal_leden`
- Deduplicatie via `mandaat:isBestuurlijkeAliasVan` (persoon-URI): meerdere mandataris-records voor dezelfde persoon tellen als 1
- Gemeente-label via `mandaat:isTijdspecialisatieVan` → tijdloos orgaan → `skos:prefLabel`
- Schepencollege: rollen burgemeester (`…5e000013`), schepen (`…5e000014`), toegevoegd schepen (`…59a9…`)

**Output-kolommen:**

| Kolom | Beschrijving |
|-------|-------------|
| `gemeente` | Gemeentenaam |
| `fractie` | Fractienaam |
| `aantal_leden` | Unieke personen (gemeenteraadslid + voorzitter) |
| `totaal_raad` | Totaal voor die gemeente |
| `in_schepencollege` | ja/nee — fractie leverde schepen of burgemeester |
| `voorzitter_gemeenteraad` | ja/nee — fractie leverde de voorzitter |
| `in_coalitie_volgens_wikipedia` | ja/nee/onbekend — coalitie-annotatie uit Wikipedia |

---

### `wikipedia_coalitie.py`
Voegt `in_coalitie_volgens_wikipedia` toe aan de CSV via de Wikipedia-pagina *Belgische lokale verkiezingen 2018*.

```
python wikipedia_coalitie.py
```

Matcht fractienamen heuristisch (normalisatie + aliassen voor hernoemde partijen, bv. Vooruit = sp.a).

---

### `verifieer_zetels.py`
Vergelijkt `aantal_leden` in de CSV met de zeteltelling op Wikipedia.

```
python verifieer_zetels.py
```

Rapporteert afwijkingen per gemeente/fractie en geeft een overzicht van de match-score.

## Bekende beperkingen

- **`ext:isBestuurspartij`** bestaat in het datamodel maar is door geen enkel lokaal bestuur ingevuld — coalitiedetectie via schepencollege of Wikipedia.
- **4 fusiegemeenten** ontbreken in Wikipedia (`Bilzen-Hoeselt`, `Overpelt`, `Tessenderlo-Ham`, `Tongeren-Borgloon`).
- **±1 afwijkingen** t.o.v. Wikipedia zijn normaal: Wikipedia toont verkiezingszetels, de mandatendatabank registreert ook tussentijdse vervangingen.
- Voorzitter gemeenteraad telt mee in `aantal_leden` maar zit zelden in `in_schepencollege` (tenzij dezelfde persoon ook schepen is).
