# Abonnement, ja tak

Kildekoden til abonnementjatak.dk, en oversigt over abonnementer på det, man bruger igen og igen. Første kategori er vegetariske måltidskasser. Sitet er en del af Mias Magiske Univers.

## Sådan hænger det sammen

- `data/maaltidskasser.json` er datafilen, som siderne bygges af. Her står kassepriser, levering, introtilbud, vilkår og datoen for hver kontrol.
- `build.py` regner priserne ud og bygger sitet i `docs/`. Det kræver kun Python 3.
- `src/` indeholder stylesheet, navnetræk (`logo.svg`), ikon og skrift.
- `docs/` er det færdige site, som GitHub Pages viser. Mappen overskrives ved hver bygning, så ret ikke i den direkte.

Provisioner, netværk og interne noter ligger ikke her, fordi repoet er offentligt.

## Sådan regnes priserne

- Normalprisen pr. uge er kassens pris plus levering.
- Første levering og de første 8 uger får introtilbuddet trukket fra.
- Et introtilbud skrives på en af to måder:
  - `procent_pr_levering` med en liste af procenter, fx `[25, 15, 10]`. Sæt `rabat_paa_fragt` til `true` eller `false`, når det vides. Står den til `null`, trækkes rabatten kun fra kassen, og tallene vises med højst foran.
  - `op_til_kr` med `beloeb` og `leveringer`, når udbyderen kun oplyser den samlede rabat. Så står første levering som ukendt, og de 8 uger står med højst foran.
- Sæt `kasse` til `null`, hvis prisen ikke kan ses. Udbyderen står så nederst med en forklaring.

## Byg sitet

    python3 build.py

Scriptet skriver de udregnede tal i terminalen, så de kan sammenlignes med kilderne.

## Den månedlige opdatering

1. Aflæs kassepriser, levering og introtilbud hos udbyderne, og ret dem i `data/maaltidskasser.json`. Sæt datoen i `kontrolleret`.
2. Skriv en linje under `opdateringer` om, hvad der er ændret.
3. Kør `python3 build.py`, og commit både `data/` og `docs/`.

## Reklamelinks

Når en udbyder har godkendt sitet, skrives tracking-linket i feltet `reklamelink`. Knappen bruger så det link, får `rel="sponsored"` og mærkes med ordet Reklamelink. Er feltet tomt, går knappen direkte til udbyderen.

## Skrift

Overskrifter og priser bruger AJT Serif, et udsnit af Lora under SIL Open Font License. Licensen ligger i `src/fonts/OFL.txt`.

## Udgivelse

GitHub Pages skal vise grenen `main` og mappen `/docs` (Settings, Pages, Deploy from a branch). Domænet abonnementjatak.dk kobles på senere med en fil `src/CNAME`, som bygningen kopierer med, og DNS-opsætning hos one.com.
