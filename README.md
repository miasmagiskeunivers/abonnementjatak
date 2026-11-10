# Abonnement ja tak

Kildekoden til abonnementjatak.dk, en uafhængig oversigt over abonnementer, der gør hverdagen nemmere. Første kategori er vegetariske måltidskasser. Sitet er en del af Mias Magiske Univers.

## Sådan hænger det sammen

- `data/vegetariske-maaltidskasser.csv` er tabellen, som siderne bygges af. Priser og vilkår rettes her. Kolonnen `vis` styrer, om en udbyder står på sitet.
- `data/ikke-med.csv` er listen over udbydere, der ikke er med, og hvorfor.
- `data/opdateringer.csv` er ændringsloggen nederst på kategorisiden.
- `src/` indeholder stylesheet og ikon.
- `build.py` bygger sitet i `docs/` og kræver kun Python 3.
- `docs/` er det færdige site, som GitHub Pages viser. Den overskrives ved hver bygning, så ret ikke i den direkte.

Provisioner, netværk og interne noter ligger ikke her, fordi repoet er offentligt.

## Byg sitet

    python3 build.py

## Den månedlige opdatering

1. Aflæs priser og vilkår hos udbyderne, ret dem i `data/vegetariske-maaltidskasser.csv`, og sæt datoen i `aflaest`.
2. Skriv en linje i `data/opdateringer.csv` om, hvad der er ændret.
3. Kør `python3 build.py`, og commit både `data/` og `docs/`.

## Annoncelinks

Når en udbyder har godkendt sitet, skrives tracking-linket i kolonnen `affiliate_link`. Knappen bruger så det link, får `rel="sponsored"` og mærkes med ordet Annoncelink. Er feltet tomt, går knappen direkte til udbyderen.

## Udgivelse

GitHub Pages skal vise grenen `main` og mappen `/docs` (Settings, Pages, Deploy from a branch). Domænet abonnementjatak.dk kobles på senere med en fil `src/CNAME`, som bygningen kopierer med, og DNS-opsætning hos one.com.
