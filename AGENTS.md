# Gemeenteraad analyse 2018–2024

## Doel

Analyseer per Vlaamse gemeente de volledige evolutie van de gemeenteraad en het schepencollege doorheen de legislatuur 2018–2024: welke fracties hadden hoeveel leden, wie was burgemeester, en hoe lang duurde elke unieke samenstelling?

## Databron

| Bestand | Beschrijving |
|---------|-------------|
| `mandaten-20260412031500084.ttl` | ~1,69 miljoen RDF-triples uit de Mandatendatabank Vlaanderen |

De Mandatendatabank is beschikbaar via [mandaten.lokaalbestuur.vlaanderen.be](https://mandaten.lokaalbestuur.vlaanderen.be).

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

1. Verzamel alle mandaten per gemeente met hun start- en einddatum. `mandaat:einde` is inclusief → +1 dag voor intern gebruik (exclusief eindpunt). Ontbrekende einddatum → `bindingEinde + 1 dag`.
2. Bouw per gemeente een tijdlijn van alle unieke grenspunten (start- en einddatums).
3. Bepaal voor elk interval de actieve mandaten (`start ≤ datum < einde`), tel per fractie in gemeenteraad en schepencollege, en registreer de burgemeesterfractie.
4. Samenstellingen met identieke burgemeester + gemeenteraad + schepencollege worden samengevoegd; hun dagentelling wordt opgeteld.
5. Sorteer per gemeente op aantal dagen (desc).

### Relevante rollen

| Rol | URI-suffix | Telt mee in |
|-----|-----------|-------------|
| Gemeenteraadslid | `…5e000011` | gemeenteraad |
| Voorzitter gemeenteraad | `…5e000012` | gemeenteraad |
| Burgemeester | `…5e000013` | schepencollege + burgemeester |
| Schepen | `…5e000014` | schepencollege |
| Toegevoegd schepen | `…59a9…` | schepencollege |

### Output-formaat (`gemeenteraad_analyse_2018_2024.json`)

Toplevel object: gemeentenaam (alfabetisch) → lijst van samenstellingsobjecten, gesorteerd op `dagen` (desc):

```json
{
  "Aalst": [
    {
      "dagen": 980,
      "burgemeester": "N-VA",
      "gemeenteraad":   { "N-VA": 17, "Vlaams Belang": 7, "CD&V": 4 },
      "schepencollege": { "N-VA": 6, "Open VLD": 1 }
    }
  ]
}
```

Fracties in `gemeenteraad` en `schepencollege` zijn gesorteerd groot→klein, bij gelijke stand alfabetisch.

## Bekende beperkingen

- **Fractienamen**: de Mandatendatabank gebruikt de naam zoals geregistreerd door de gemeente. Hernoemingen (bv. sp.a → Vooruit) kunnen als aparte fracties verschijnen in opeenvolgende perioden.
- **`"Onbekend"` als fractienaam**: treedt op wanneer een mandataris geen fractielidmaatschap heeft, of wanneer de fractie-URI in de TTL-dump geen label heeft (data-lek in de bron).
- **`"Onbekend"` als burgemeester**: de burgemeesteraanstelling is een apart administratief besluit dat soms later geregistreerd wordt; voor sommige perioden ontbreekt de fractielink.
- **Variërend zetelgetal per gemeente**: tussentijdse vervangingen kunnen korte intervallen (1–5 dagen) veroorzaken met een afwijkend zetelgetal door overlap of een kleine gap in de registratie.
- **Herstappe**: ontbreekt in de dataset (te kleine gemeente, geen eigen registratie).
