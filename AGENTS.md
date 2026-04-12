# Gemeenteraad samenstelling 2018–2024

## Doel

Bepaal per Vlaamse gemeente de samenstelling van de gemeenteraad voor de legislatuur 2018–2024: welke fracties hebben hoeveel leden, wie zit in het schepencollege, wie is voorzitter, en welke fracties zijn coalitiepartner?

## Databronnen

| Bron | Gebruik |
|------|---------|
| `mandaten-20260412031500084.ttl` | Ruwe data — ~1,69 miljoen RDF-triples uit de Mandatendatabank Vlaanderen |
| `wikipedia_cache/` | Gecachte HTML van Wikipedia *Belgische lokale verkiezingen 2018*, per provincie (5 bestanden) |

De Mandatendatabank is beschikbaar via [mandaten.lokaalbestuur.vlaanderen.be](https://mandaten.lokaalbestuur.vlaanderen.be).

## Scripts

### `gemeenteraad_samenstelling.py` ← hoofdscript

Genereert `gemeenteraad_samenstelling_2018_2024.csv`.

```
python gemeenteraad_samenstelling.py --input mandaten-20260412031500084.ttl
```

**Werkwijze:**
- Filtert mandatarissen met `mandaat:start` tussen **2018-10-01 en 2019-02-01** (enkel verkiezingszetels, geen mid-term vervangingen)
- Deduplicatie via `mandaat:isBestuurlijkeAliasVan` (persoon-URI): meerdere records voor dezelfde persoon tellen als 1
- Rollen die meetellen in `aantal_leden`: gemeenteraadslid (`…5e000011`) én voorzitter gemeenteraad (`…5e000012`)
- Gemeente-label via `mandaat:isTijdspecialisatieVan` → tijdloos orgaan → `skos:prefLabel`
- Schepencollege: rollen burgemeester (`…5e000013`), schepen (`…5e000014`), toegevoegd schepen (`…59a9…`)

**Output-kolommen:**

| Kolom | Beschrijving |
|-------|-------------|
| `gemeente` | Gemeentenaam |
| `fractie` | Fractienaam |
| `aantal_leden` | Unieke verkozenen (gemeenteraadslid + voorzitter) |
| `totaal_raad` | Totaal voor die gemeente |
| `in_schepencollege` | ja/nee — fractie leverde schepen of burgemeester |
| `voorzitter_gemeenteraad` | ja/nee — fractie leverde de voorzitter van de gemeenteraad |
| `in_coalitie_volgens_wikipedia` | ja/nee/onbekend — zie `wikipedia_coalitie.py` |

---

### `wikipedia_coalitie.py`

Voegt `in_coalitie_volgens_wikipedia` toe aan de CSV via de Wikipedia-pagina *Belgische lokale verkiezingen 2018*.

```
python wikipedia_coalitie.py
```

- Leest HTML uit `wikipedia_cache/`; downloadt enkel opnieuw als een bestand ontbreekt
- Matcht fractienamen heuristisch: normalisatie (accenten, leestekens) + aliassen voor hernoemde partijen (Vooruit = sp.a, VB = Vlaams Belang, …)
- 74% exacte zetelmatch met Wikipedia (995/1336 gematchte rijen)

---

### `verifieer_zetels.py`

Vergelijkt `aantal_leden` per fractie in de CSV met de zeteltelling op Wikipedia.

```
python verifieer_zetels.py
```

Rapporteert afwijkingen per gemeente/fractie gesorteerd op grootte van het verschil.

---

## Runvolgorde

```
python gemeenteraad_samenstelling.py --input mandaten-20260412031500084.ttl
python wikipedia_coalitie.py
```

`verifieer_zetels.py` is optioneel voor kwaliteitscontrole.

## Bekende beperkingen

- **`ext:isBestuurspartij`** bestaat in het datamodel maar is nergens ingevuld — coalitiedetectie via `in_schepencollege` of `in_coalitie_volgens_wikipedia`.
- **4 fusiegemeenten** ontbreken in Wikipedia (`Bilzen-Hoeselt`, `Overpelt`, `Tessenderlo-Ham`, `Tongeren-Borgloon`) → `in_coalitie_volgens_wikipedia = onbekend`.
- **Resterende ±1 afwijkingen** t.o.v. Wikipedia (26%): lokale kartels die als één fractie in de mandatendatabank staan maar gesplitst in Wikipedia, of omgekeerd.
- Voorzitter gemeenteraad telt mee in `aantal_leden` maar zit doorgaans niet in `in_schepencollege`.
