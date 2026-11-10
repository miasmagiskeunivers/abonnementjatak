#!/usr/bin/env python3
"""Bygger abonnementjatak.dk som statiske sider i docs/ ud fra filerne i data/.

Kør med:  python3 build.py
Scriptet bruger kun Pythons standardbibliotek.
"""

import csv
import html
import io
import json
import shutil
from datetime import date
from pathlib import Path

ROD = Path(__file__).resolve().parent
DATA = ROD / "data"
SRC = ROD / "src"
UD = ROD / "docs"

SITE_URL = "https://abonnementjatak.dk/"
SITE_NAVN = "Abonnement ja tak"
UDGIVER = "Mias Magiske Univers"
KONTAKT = "velkommentil@miasmagiskeunivers.dk"
KATEGORI_STI = "vegetariske-maaltidskasser/"
DATAFIL = "vegetariske-maaltidskasser"

MAANEDER = ["januar", "februar", "marts", "april", "maj", "juni", "juli",
            "august", "september", "oktober", "november", "december"]
TAL = {1: "én", 2: "to", 3: "tre", 4: "fire", 5: "fem", 6: "seks",
       7: "syv", 8: "otte", 9: "ni", 10: "ti"}

# De kolonner, der må stå i de downloadbare filer og på sitet.
OFFENTLIGE = ["id", "type", "udbyder", "loesning", "beskrivelse", "pris", "pris_note",
              "intro", "binding_kort", "binding", "oekologi", "levering", "link", "aflaest"]

STICKER = """<svg class="sticker" viewBox="0 0 240 132" role="img" aria-label="Abonnement ja tak">
<ellipse cx="120" cy="66" rx="114" ry="60" fill="#fff" stroke="currentColor" stroke-width="7"/>
<ellipse cx="120" cy="66" rx="102" ry="48" fill="none" stroke="currentColor" stroke-width="1.5"/>
<text x="120" y="60" text-anchor="middle" font-size="23" font-weight="700" fill="currentColor">Abonnement</text>
<text x="120" y="96" text-anchor="middle" font-size="42" font-weight="800" fill="currentColor">ja tak</text>
</svg>"""


def e(tekst):
    return html.escape(tekst or "", quote=True)


def dansk_dato(iso):
    d = date.fromisoformat(iso)
    return f"{d.day}. {MAANEDER[d.month - 1]} {d.year}"


def antal(n, ental, flertal):
    ord_ = TAL.get(n, str(n))
    return f"{ord_} {ental if n == 1 else flertal}"


def laes(navn):
    with open(DATA / navn, encoding="utf-8", newline="") as fh:
        return [{k: (v or "").strip() for k, v in r.items()}
                for r in csv.DictReader(fh, delimiter=";")]


def skriv(sti, indhold):
    fil = UD / sti
    fil.parent.mkdir(parents=True, exist_ok=True)
    fil.write_text(indhold, encoding="utf-8")


def jsonld_tag(data):
    tekst = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{tekst}\n</script>\n'


def side(*, sti, titel, beskrivelse, indhold, jsonld=None, aktiv=None,
         vis_maerke=True, prefiks=None):
    dybde = sti.count("/")
    pre = prefiks if prefiks is not None else "../" * dybde
    hjem = pre or "./"
    kanonisk = SITE_URL + sti
    menu = []
    for href, tekst in [(KATEGORI_STI, "Måltidskasser"), ("om/", "Om sitet")]:
        markering = ' aria-current="page"' if href == aktiv else ""
        menu.append(f'<a href="{pre}{href}"{markering}>{e(tekst)}</a>')
    maerke = ""
    if vis_maerke:
        maerke = f'<a class="maerke" href="{hjem}" aria-label="{SITE_NAVN}, forsiden">{STICKER}</a>\n'
    ld = jsonld_tag(jsonld) if jsonld else ""
    return f"""<!doctype html>
<html lang="da">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titel)}</title>
<meta name="description" content="{e(beskrivelse)}">
<link rel="canonical" href="{e(kanonisk)}">
<meta property="og:type" content="website">
<meta property="og:locale" content="da_DK">
<meta property="og:site_name" content="{SITE_NAVN}">
<meta property="og:title" content="{e(titel)}">
<meta property="og:description" content="{e(beskrivelse)}">
<meta property="og:url" content="{e(kanonisk)}">
<meta name="theme-color" content="#a31a55">
<link rel="icon" href="{pre}favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{pre}styles.css">
{ld}</head>
<body>
<a class="spring" href="#indhold">Gå til indholdet</a>
<header class="top">
{maerke}<nav aria-label="Hovedmenu">{"".join(menu)}</nav>
</header>
<main id="indhold">
{indhold}
</main>
<footer class="bund">
<div class="bund-indre">
<p>{SITE_NAVN} er en del af {UDGIVER}. Skriv til <a href="mailto:{KONTAKT}">{KONTAKT}</a>, hvis du ser en fejl.</p>
<p>Sitet sætter ingen cookies. <a href="{pre}om/">Læs om, hvordan sitet tjener penge</a>.</p>
</div>
</footer>
</body>
</html>
"""


def udbyder_html(u):
    annonce = bool(u.get("affiliate_link"))
    href = u["affiliate_link"] if annonce else u["link"]
    rel = ' rel="sponsored"' if annonce else ""
    maerkat = ' <span class="annonce">Annoncelink</span>' if annonce else ""
    pris = e(u["pris"])
    if u["pris_note"]:
        pris += f'<span class="note">{e(u["pris_note"])}</span>'
    fakta = [
        ("Pris", pris),
        ("Introtilbud", e(u["intro"])),
        ("Binding", e(u["binding"])),
        ("Økologi", e(u["oekologi"])),
        ("Levering", e(u["levering"])),
    ]
    fakta_html = "\n".join(f"<div><dt>{navn}</dt><dd>{vaerdi}</dd></div>"
                           for navn, vaerdi in fakta if vaerdi)
    return f"""<article class="udbyder" id="{e(u["id"])}">
<h3>{e(u["udbyder"])}</h3>
<p class="loesning">{e(u["loesning"])}</p>
<p>{e(u["beskrivelse"])}</p>
<dl class="fakta">
{fakta_html}
</dl>
<p class="videre"><a class="knap" href="{e(href)}"{rel}>Gå til {e(u["udbyder"])}</a>{maerkat}</p>
</article>"""


def efter_navn(udbydere):
    return sorted(udbydere, key=lambda u: u["udbyder"].lower())


def kategoriside(udbydere, ikke_med, opdateringer, opdateret):
    kasser = efter_navn([u for u in udbydere if u["type"] == "måltidskasse"])
    faerdig = efter_navn([u for u in udbydere if u["type"] == "færdigretter"])
    dato = dansk_dato(opdateret)

    raekker = "\n".join(
        f'<tr><th scope="row"><a href="#{e(u["id"])}">{e(u["udbyder"])}</a></th>'
        f'<td>{e(u["pris"])}</td><td>{e(u["binding_kort"])}</td></tr>'
        for u in kasser)

    dele = [f"""<h1>Vegetariske måltidskasser</h1>
<p class="lead">Her er de måltidskasser, hvor hele leverancen kan være uden kød og fisk. Vi har aflæst priser og vilkår hos udbyderne den {dato}.</p>

<h2 id="overblik">Overblik</h2>
<table class="overblik">
<caption>Priser og binding, aflæst {dato}</caption>
<thead><tr><th scope="col">Udbyder</th><th scope="col">Pris</th><th scope="col">Binding</th></tr></thead>
<tbody>
{raekker}
</tbody>
</table>

<h2 id="kasserne">Kasserne en for en</h2>
""" + "\n".join(udbyder_html(u) for u in kasser)]

    if faerdig:
        dele.append("""<h2 id="faerdigretter">Færdigretter, hvis du ikke vil lave mad</h2>
<p>Vil du helst slippe for at lave mad, kan færdigretter være et alternativ. De skal bare varmes.</p>
""" + "\n".join(udbyder_html(u) for u in faerdig))

    if ikke_med:
        punkter = "\n".join(f'<li><strong>{e(r["udbyder"])}.</strong> {e(r["grund"])}</li>'
                            for r in ikke_med)
        dele.append(f"""<h2 id="ikke-med">Ikke med lige nu</h2>
<ul class="ikke-med">
{punkter}
</ul>""")

    dele.append(f"""<h2 id="metode">Sådan sammenligner vi</h2>
<p>Vi aflæser priser og vilkår på udbydernes egne sider og skriver datoen på. Fra-prisen er den laveste pris, udbyderen selv viser, og den gælder som regel den største kasse. Introtilbud står for sig, fordi de kun gælder de første leveringer.</p>
<p>Vi rangerer ikke udbyderne. De står i alfabetisk rækkefølge, og alle står på samme måde, uanset om vi har en aftale med dem. Tjek altid prisen hos udbyderen, før du bestiller, for den kan have ændret sig siden.</p>

<h2 id="data">Hent tabellen</h2>
<p>Oversigten ligger også som <a href="../data/{DATAFIL}.csv">CSV-fil</a> og som <a href="../data/{DATAFIL}.json">JSON</a>, så du kan bruge den i dit eget regneark.</p>""")

    log = "\n".join(
        f'<li><time datetime="{e(r["dato"])}">{dansk_dato(r["dato"])}</time>: {e(r["tekst"])}</li>'
        for r in sorted(opdateringer, key=lambda r: r["dato"], reverse=True))
    dele.append(f"""<h2 id="aendringer">Ændringer</h2>
<ul class="log">
{log}
</ul>""")

    url = SITE_URL + KATEGORI_STI
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebPage", "@id": url, "url": url, "name": "Vegetariske måltidskasser",
             "inLanguage": "da", "dateModified": opdateret, "isPartOf": {"@id": SITE_URL + "#site"}},
            {"@type": "ItemList", "name": "Vegetariske måltidskasser i Danmark",
             "itemListOrder": "https://schema.org/ItemListOrderAscending",
             "numberOfItems": len(kasser),
             "itemListElement": [{"@type": "ListItem", "position": i, "name": u["udbyder"],
                                  "url": u["link"]} for i, u in enumerate(kasser, start=1)]},
            {"@type": "Dataset", "name": "Vegetariske måltidskasser i Danmark",
             "description": "Priser, introtilbud, binding, økologi og levering for vegetariske "
                            "måltidskasser og færdigretter i Danmark, aflæst hos udbyderne og "
                            "opdateret hver måned.",
             "url": url, "inLanguage": "da", "dateModified": opdateret,
             "creator": {"@type": "Organization", "name": UDGIVER},
             "distribution": [
                 {"@type": "DataDownload", "encodingFormat": "text/csv",
                  "contentUrl": f"{SITE_URL}data/{DATAFIL}.csv"},
                 {"@type": "DataDownload", "encodingFormat": "application/json",
                  "contentUrl": f"{SITE_URL}data/{DATAFIL}.json"}]},
        ],
    }
    navne = [u["udbyder"] for u in kasser]
    opremsning = navne[0] if len(navne) == 1 else ", ".join(navne[:-1]) + " og " + navne[-1]
    return side(sti=KATEGORI_STI, titel="Vegetariske måltidskasser i Danmark | Abonnement ja tak",
                beskrivelse=f"Sammenligning af vegetariske måltidskasser fra {opremsning}. "
                            f"Priser, introtilbud og binding aflæst {dato}.",
                indhold="\n\n".join(dele), jsonld=jsonld, aktiv=KATEGORI_STI)


def forside(udbydere, opdateret):
    n_kasser = sum(1 for u in udbydere if u["type"] == "måltidskasse")
    n_faerdig = sum(1 for u in udbydere if u["type"] == "færdigretter")
    omfang = antal(n_kasser, "måltidskasse", "måltidskasser").capitalize()
    if n_faerdig:
        omfang += " og " + antal(n_faerdig, "udbyder", "udbydere") + " af færdigretter"
    indhold = f"""<section class="hero">
<div class="forside-maerke">{STICKER}</div>
<h1>Abonnementer, der gør hverdagen nemmere</h1>
<p class="lead">Vi samler de abonnementer, der sparer dig for en indkøbstur eller en beslutning, og tjekker priserne hos udbyderne hver måned. Vi er startet med vegetariske måltidskasser.</p>
<p><a class="knap" href="{KATEGORI_STI}">Se de vegetariske måltidskasser</a></p>
</section>

<section aria-labelledby="kategorier">
<h2 id="kategorier">Det kan du sammenligne nu</h2>
<a class="kort" href="{KATEGORI_STI}">
<span class="kort-titel">Vegetariske måltidskasser</span>
<span class="kort-tekst">{omfang}. Opdateret {dansk_dato(opdateret)}.</span>
</a>
<p class="snart">Bagefter kommer bleer, shampoo og andre ting, der kan komme af sig selv.</p>
</section>

<section class="principper" aria-labelledby="saadan">
<h2 id="saadan">Sådan arbejder vi</h2>
<h3>Vi tjekker priserne selv</h3>
<p>Hver måned aflæser vi priser og vilkår direkte hos udbyderne og skriver datoen på, så du kan se, hvor friske tallene er.</p>
<h3>Vi er strenge med, hvad der kommer med</h3>
<p>I måltidskasserne er det kun kasser, hvor hele leverancen kan være uden kød og fisk. Dem, der ikke lever op til det, står på en liste for sig med en forklaring.</p>
<h3>Vi siger, hvordan vi tjener penge</h3>
<p>Nogle links kan give os en provision, når du køber. De bliver mærket med ordet Annoncelink, og de afgør ikke, hvem der er med.</p>
</section>"""
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "@id": SITE_URL + "#site", "url": SITE_URL, "name": SITE_NAVN,
             "inLanguage": "da", "publisher": {"@id": SITE_URL + "#udgiver"}},
            {"@type": "Organization", "@id": SITE_URL + "#udgiver", "name": UDGIVER,
             "email": KONTAKT},
        ],
    }
    return side(sti="", titel="Abonnement ja tak | Abonnementer, der gør hverdagen nemmere",
                beskrivelse="Uafhængig oversigt over abonnementer, der gør hverdagen nemmere. "
                            "Vi starter med vegetariske måltidskasser og tjekker priserne hver måned.",
                indhold=indhold, jsonld=jsonld, vis_maerke=False)


def omside():
    indhold = f"""<h1>Om Abonnement ja tak</h1>
<p class="lead">Abonnement ja tak samler de abonnementer, der gør hverdagen nemmere, og holder øje med priserne, så du ikke selv skal.</p>

<h2>Hvem står bag</h2>
<p>Sitet er en del af {UDGIVER}, som laver uafhængige guider til hverdagen. Du kan skrive til os på <a href="mailto:{KONTAKT}">{KONTAKT}</a>.</p>

<h2>Sådan tjener vi penge</h2>
<p>Det er gratis at bruge sitet. Vi er ved at lave aftaler med udbyderne, så vi kan få en provision, når nogen køber gennem vores links. Det koster ikke dig noget ekstra.</p>
<p>Et link, der kan give os provision, bliver mærket med ordet Annoncelink lige ved siden af knappen. En aftale afgør ikke, om en udbyder kommer med, eller hvad vi skriver om den, og udbydere uden aftale står på siden på samme måde som de andre.</p>

<h2>Sådan finder vi tallene</h2>
<p>Vi aflæser priser og vilkår på udbydernes egne sider og skriver datoen på hver gang. Tallene kan have ændret sig siden, så tjek altid prisen hos udbyderen, før du bestiller.</p>

<h2>Cookies</h2>
<p>Sitet sætter ingen cookies og bruger ingen statistik. Når du klikker videre til en udbyder, gælder udbyderens egne regler.</p>"""
    return side(sti="om/", titel="Om sitet | Abonnement ja tak",
                beskrivelse="Hvem står bag Abonnement ja tak, hvordan vi finder priserne, og hvordan sitet tjener penge.",
                indhold=indhold, aktiv="om/")


def side404():
    indhold = f"""<h1>Siden findes ikke</h1>
<p>Adressen passer ikke til nogen side her. Gå til <a href="/">forsiden</a> eller til <a href="/{KATEGORI_STI}">de vegetariske måltidskasser</a>.</p>"""
    return side(sti="404.html", titel="Siden findes ikke | Abonnement ja tak",
                beskrivelse="Siden findes ikke.", indhold=indhold, prefiks="/")


def datafiler(udbydere, opdateret):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(OFFENTLIGE)
    for u in udbydere:
        w.writerow([u[k] for k in OFFENTLIGE])
    skriv(f"data/{DATAFIL}.csv", buf.getvalue())
    data = {
        "navn": "Vegetariske måltidskasser i Danmark",
        "kilde": SITE_URL + KATEGORI_STI,
        "opdateret": opdateret,
        "udbydere": [{k: u[k] for k in OFFENTLIGE} for u in udbydere],
    }
    skriv(f"data/{DATAFIL}.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def maskinfiler(opdateret):
    urls = ["", KATEGORI_STI, "om/"]
    sitemap = "\n".join(f"<url><loc>{SITE_URL}{u}</loc><lastmod>{opdateret}</lastmod></url>"
                        for u in urls)
    skriv("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"{sitemap}\n</urlset>\n")
    skriv("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n")
    skriv("llms.txt", f"""# {SITE_NAVN}

> Uafhængig dansk oversigt over abonnementer, der gør hverdagen nemmere. Første kategori er vegetariske måltidskasser. Priser og vilkår aflæses hos udbyderne hver måned, senest {dansk_dato(opdateret)}.

## Sider

- [Vegetariske måltidskasser]({SITE_URL}{KATEGORI_STI}): måltidskasser, hvor hele leverancen kan være uden kød og fisk, med priser, introtilbud, binding og levering
- [Om sitet]({SITE_URL}om/): hvem står bag, og hvordan sitet tjener penge

## Data

- [Vegetariske måltidskasser som CSV]({SITE_URL}data/{DATAFIL}.csv)
- [Vegetariske måltidskasser som JSON]({SITE_URL}data/{DATAFIL}.json)
""")
    skriv(".nojekyll", "")


def main():
    udbydere = [u for u in laes(f"{DATAFIL}.csv") if u["vis"] == "ja"]
    ikke_med = laes("ikke-med.csv")
    opdateringer = laes("opdateringer.csv")
    opdateret = max(u["aflaest"] for u in udbydere)

    if UD.exists():
        shutil.rmtree(UD)
    UD.mkdir()
    for navn in ["styles.css", "favicon.svg", "CNAME"]:
        if (SRC / navn).exists():
            shutil.copy(SRC / navn, UD / navn)

    skriv("index.html", forside(udbydere, opdateret))
    skriv(KATEGORI_STI + "index.html", kategoriside(udbydere, ikke_med, opdateringer, opdateret))
    skriv("om/index.html", omside())
    skriv("404.html", side404())
    datafiler(efter_navn(udbydere), opdateret)
    maskinfiler(opdateret)
    print(f"Bygget {len(udbydere)} udbydere, opdateret {opdateret}, i {UD}")


if __name__ == "__main__":
    main()
