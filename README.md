# Abonnement, ja tak

Kildekoden til abonnementjatak.dk, en oversigt over abonnementer på det, man bruger igen og igen. Kategorierne er vegetariske måltidskasser, legetøjsabonnementer og hundekasser. Sitet er en del af Mias Magiske Univers.

## Sådan hænger det sammen

- `data/maaltidskasser.json`, `data/legetoej.json` og `data/hundekasser.json` er datafilerne, som siderne bygges af. Her står kassepriser, levering, introtilbud, vilkår og datoen for hver kontrol.
- `build.py` regner priserne ud og bygger sitet i `docs/`. Det kræver kun Python 3.
- `src/` indeholder stylesheet, navnetræk (`logo.svg`), ikon og skrift.
- `docs/` er det færdige site, som GitHub Pages viser. Mappen overskrives ved hver bygning, så ret ikke i den direkte.

Provisioner, netværk og interne noter ligger ikke her, fordi repoet er offentligt.

## Sådan regnes priserne

- Normalprisen pr. uge er kassens pris plus levering. Listen sorteres efter den.
- Prisen pr. portion er normalprisen delt med antallet af portioner.
- Første levering er normalprisen med introtilbuddet trukket fra.
- Et introtilbud skrives på en af to måder:
  - `procent_pr_levering` med en liste af procenter, fx `[25, 15, 10]`. Sæt `rabat_paa_fragt` til `true` eller `false`, når det vides. Står den til `null`, trækkes rabatten kun fra kassen, og første levering vises med højst foran.
  - `op_til_kr` med `beloeb` og `leveringer`, når udbyderen kun oplyser den samlede rabat. Så står første levering som ukendt.
- Sæt `kasse` til `null`, hvis prisen ikke kan ses. Udbyderen står så nederst med en forklaring.

## Legetøj og hundekasser

Kasser, der kommer med faste mellemrum, regnes på en anden måde end måltidskasserne.

- Hver plan har sin pris under `priser`. For legetøj er planerne aldersgrupper. Har en udbyder ikke noget til en aldersgruppe, udelades planen, og siden skriver, at udbyderen ikke er med i gruppen.
- `kasse` er kassens pris uden levering, `fragt` er leveringen, og `hver` er antallet af måneder mellem kasserne. `fragt_foerste` bruges, når første levering koster noget andet.
- Prisen pr. kasse er kassen plus levering. Prisen pr. måned er prisen pr. kasse delt med `hver`. Listen sorteres efter prisen pr. måned.
- Første kasse er kassen plus første levering. Et introtilbud skrives som `foerste_kasse` med `pris`, når første kasse har en fast pris med fragt, eller som `maaneder_til_pris` med `pris` og `maaneder`, når de første måneder koster et fast beløb. Introtilbud står i kroner.
- Står `valuta` til `EUR`, skrives beløbene i euro, og `build.py` omregner dem med `kurs_eur` i kategorien. Siden skriver så ca. foran beløbet.
- `alder` og `legetoej` (`beholdes` eller `lejes`) bliver til linjen under navnet på legetøjssiden. Hundekasser bruger `undertekst` i stedet.

## Byg sitet

    python3 build.py

Scriptet skriver de udregnede tal i terminalen, så de kan sammenlignes med kilderne.

## Den månedlige opdatering

1. Aflæs kassepriser, levering og introtilbud hos udbyderne, og ret dem i datafilerne. Sæt datoen i `kontrolleret`.
2. Skriv en linje under `opdateringer` om, hvad der er ændret.
3. Kør `python3 build.py`, og commit både `data/` og `docs/`.

## Reklamelinks

Når en udbyder har godkendt sitet, skrives tracking-linket i feltet `reklamelink`. Knappen bruger så det link, får `rel="sponsored"` og mærkes med ordet Reklamelink. Er feltet tomt, går knappen direkte til udbyderen.

## Skrift

Overskrifter og priser bruger AJT Serif, et udsnit af Lora under SIL Open Font License. Licensen ligger i `src/fonts/OFL.txt`.

## Udgivelse

GitHub Pages skal vise grenen `main` og mappen `/docs` (Settings, Pages, Deploy from a branch). Domænet abonnementjatak.dk står i `src/CNAME`, som bygningen kopierer med. DNS sættes op hos one.com.
