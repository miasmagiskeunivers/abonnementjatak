# Abonnement, ja tak

Instruktioner til Claude, der arbejder på abonnementjatak.dk. Sitet sammenligner abonnementer på det, man bruger igen og igen. Første kategori er vegetariske måltidskasser. Mia ejer sitet og bestemmer. Claude bygger og vedligeholder det. Mia skal bruge så lidt tid som muligt på sitet, så løs selv det, der kan løses, og spørg kun om det, der kræver hendes beslutning.

## Repoet er offentligt

Skriv aldrig provisioner, aftaler med netværk, interne noter, passwords, tokens eller personlige oplysninger i en fil eller en commit-besked. Interne tal og noter ligger i Mias Claude-projekt.

## Det kræver Mias ja

- Faste opdateringer af priser, tilbud og datoer må udgives uden at spørge, når tallene er kontrolleret hos udbyderen.
- Nye udbydere, nye kategorier, nye reklamelinks og ændringer i design eller tekster kræver Mias ja. Det samme gælder alt, der sendes til andre.
- Når GitHub Pages er slået til, bliver en ændring udgivet, så snart den er pushet til main.

## Data og udregning

- Alle tal står i `data/maaltidskasser.json`. `build.py` regner resten ud og skriver sitet i `docs/`. Ret aldrig direkte i `docs/`. Felterne er beskrevet i `README.md`.
- Brug kun priser, du selv har set hos udbyderen. Skriv datoen i `kontrolleret` og siden i `kilde`.
- Kan en pris ikke ses, så sæt `kasse` til `null`. Gæt ikke, og brug ikke tal fra andre sites.
- Standardkasserne er til 2 og 4 personer med 3 retter om ugen. Alle priser er med levering.
- Siden viser prisen på første levering, normalprisen pr. uge og prisen pr. portion. Vis ikke samlede beløb for flere uger.
- Listen sorteres efter normalprisen. En aftale med en udbyder må aldrig ændre rækkefølgen.
- En måltidskasse er kun med, hvis hele kassen kan være uden kød og fisk.
- Skriv en linje under `opdateringer`, når priser, tilbud eller udbydere ændres.

## Tekst

- Skriv på dansk, klart og venligt, med én pointe pr. sætning og uden salgssprog.
- Skriv aldrig, at vi har smagt eller testet produkterne.
- Skriv udbydernes tekster om med egne ord, og link til kilden.

## Design

- Sitet skal være roligt og overskueligt. Der skal ikke være bannere, billeder, klistermærker eller søgefelt.
- Farverne er mint, lyserød, bordeaux, dyb grøn og guld. Sitet er altid lyst, også når telefonen står i mørk tilstand.
- Overskrifter og priser bruger AJT Serif fra `src/fonts`. Tilbud står på lyserød baggrund.
- Når feltet `reklamelink` er udfyldt, giver `build.py` knappen `rel="sponsored"` og skriver Reklamelink ved siden af. Den mærkning må aldrig fjernes.

## Byg og tjek

1. Kør `python3 build.py`, og sammenlign tallene i terminalen med kilderne.
2. Start en lokal server i `docs/` med `python3 -m http.server`, for skriften indlæses ikke fra `file://`.
3. Se forsiden og kategorisiden i 390 og 1280 pixels bredde, og tjek, at valget mellem 2 og 4 personer virker.
4. Commit både `data/` og `docs/`.

## Faste kontroller

- Tilbud kontrolleres hver uge og priser hver måned.
- Tjek samtidig, om en udbyder er lukket, eller om der er kommet nye vegetariske kasser. Foreslå nye udbydere til Mia, og tilføj dem først, når hun har sagt ja.
