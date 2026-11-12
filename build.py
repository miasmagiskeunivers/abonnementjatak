#!/usr/bin/env python3
"""Bygger abonnementjatak.dk som statiske sider i docs/ ud fra data/maaltidskasser.json.

Kør med:  python3 build.py
Scriptet bruger kun Pythons standardbibliotek. Alle priser regnes ud her, så tallene på
siderne og i de filer, man kan hente, altid passer med datafilen.
"""

import csv
import html
import io
import json
import shutil
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.parse import urlparse

ROD = Path(__file__).resolve().parent
DATA = ROD / "data"
SRC = ROD / "src"
UD = ROD / "docs"

SITE_URL = "https://abonnementjatak.dk/"
SITE_NAVN = "Abonnement, ja tak"
UDGIVER = "Mias Magiske Univers"
KONTAKT = "velkommentil@miasmagiskeunivers.dk"
KATEGORI_STI = "vegetariske-maaltidskasser/"
DATAFIL = "vegetariske-maaltidskasser"

MAANEDER = ["januar", "februar", "marts", "april", "maj", "juni", "juli",
            "august", "september", "oktober", "november", "december"]
TAL = {1: "én", 2: "to", 3: "tre", 4: "fire", 5: "fem", 6: "seks",
       7: "syv", 8: "otte", 9: "ni", 10: "ti"}
ORDENSTAL = {1: "første", 2: "anden", 3: "tredje", 4: "fjerde", 5: "femte",
             6: "sjette", 7: "syvende", 8: "ottende"}


# Små hjælpere

def e(tekst):
    return html.escape(str(tekst if tekst is not None else ""), quote=True)


def dansk_dato(iso):
    d = date.fromisoformat(iso)
    return f"{d.day}. {MAANEDER[d.month - 1]} {d.year}"


def kontrol_periode(datoer):
    """Fx "10. november 2026" eller "mellem 10. og 12. november 2026"."""
    aeldste, nyeste = min(datoer), max(datoer)
    if aeldste == nyeste:
        return dansk_dato(aeldste)
    a, n = date.fromisoformat(aeldste), date.fromisoformat(nyeste)
    if (a.year, a.month) == (n.year, n.month):
        return f"mellem {a.day}. og {dansk_dato(nyeste)}"
    return f"mellem {dansk_dato(aeldste)} og {dansk_dato(nyeste)}"


def alle_kontroldatoer(beregninger):
    return [b["kontrolleret"] for pr in beregninger.values() for b in pr.values() if b.get("kontrolleret")]


def hele_kroner(beloeb):
    return int(Decimal(str(beloeb)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def kr_tal(beloeb):
    return f"{hele_kroner(beloeb):,}".replace(",", ".")


def kr(beloeb):
    # Hårdt mellemrum, så tal og enhed ikke deles over to linjer.
    return kr_tal(beloeb) + " kr."


def punktum(saetning):
    """Sætter punktum, medmindre sætningen allerede slutter med et (fx 49 kr.)."""
    return saetning if saetning.endswith(".") else saetning + "."


def oprems(navne):
    navne = list(navne)
    if len(navne) <= 1:
        return "".join(navne)
    return ", ".join(navne[:-1]) + " og " + navne[-1]


def domaene(url):
    vaert = urlparse(url).netloc
    return vaert[4:] if vaert.startswith("www.") else vaert


def plan_tekst(plan):
    return f"{plan['personer']} personer med {plan['retter']} retter om ugen"


def skriv(sti, indhold):
    fil = UD / sti
    fil.parent.mkdir(parents=True, exist_ok=True)
    fil.write_text(indhold, encoding="utf-8")


def jsonld_tag(data):
    tekst = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{tekst}\n</script>\n'


# Udregningen

def beregn(u, plan):
    """Regner prisen ud for én udbyder og én kassestørrelse.

    status er "kendt", når vi kender kassens pris, og "ukendt", når vi ikke gør.
    foerste er None, når vi ikke kender rabatten på første levering. hoejst er True,
    når prisen på første levering er det højeste, den kan blive.
    """
    p = u["priser"].get(plan["id"]) or {}
    b = {"kontrolleret": p.get("kontrolleret"), "kilde": p.get("kilde"), "hoejst": False}
    kasse = p.get("kasse")
    if kasse is None:
        b["status"] = "ukendt"
        return b
    fragt = u["fragt"]
    uge = kasse + fragt
    b.update(status="kendt", kasse=kasse, fragt=fragt, uge=uge,
             pr_portion=uge / (plan["personer"] * plan["retter"]))
    intro = u.get("intro")
    if not intro:
        b["foerste"] = uge
    elif intro["type"] == "procent_pr_levering":
        # Uden at vide om rabatten også gælder leveringen, trækker vi den kun fra kassen.
        # Så er prisen det højeste, den kan blive.
        grundlag = uge if intro.get("rabat_paa_fragt") is True else kasse
        b["foerste"] = uge - grundlag * intro["procenter"][0] / 100
        b["hoejst"] = intro.get("rabat_paa_fragt") is None
    elif intro["type"] == "op_til_kr":
        # Vi kender kun den samlede rabat, ikke hvordan den fordeles på kasserne.
        b["foerste"] = None
    else:
        raise ValueError(f"Ukendt type introtilbud hos {u['id']}: {intro['type']}")
    return b


def sorteringsnoegle(u, b):
    """Billigste normalpris først. Udbydere uden kendt pris står nederst."""
    if b["status"] == "ukendt":
        return (1, 0, u["navn"].lower())
    return (0, b["uge"], u["navn"].lower())


# Tekster om tilbud

def procent_raekke(intro):
    dele = []
    for i, procent in enumerate(intro["procenter"], start=1):
        if i == 1:
            dele.append(f"{procent} % rabat på første levering")
        else:
            dele.append(f"{procent} % på {ORDENSTAL[i]}")
    return oprems(dele)


def tilbud_kort(intro):
    """Tilbuddet med udbyderens egne tal, som en sætning for sig."""
    if intro["type"] == "op_til_kr":
        n = intro["leveringer"]
        return f"Spar op til {kr(intro['beloeb'])} på de {TAL.get(n, n)} første kasser."
    if intro["type"] == "procent_pr_levering":
        return procent_raekke(intro) + "."
    raise ValueError(intro["type"])


def tilbud_til_nye(intro):
    if intro["type"] == "op_til_kr":
        n = intro["leveringer"]
        return f"Som ny kunde kan du spare op til {kr(intro['beloeb'])} på de {TAL.get(n, n)} første kasser."
    if intro["type"] == "procent_pr_levering":
        return f"Som ny kunde får du {procent_raekke(intro)}."
    raise ValueError(intro["type"])


def forbehold(intro):
    if not intro:
        return ""
    if intro["type"] == "op_til_kr":
        return ("Vi kunne ikke se, hvor stor rabatten er på hver kasse, uden at oprette en konto. "
                "Derfor kender vi ikke prisen på første levering.")
    if intro["type"] == "procent_pr_levering" and intro.get("rabat_paa_fragt") is None:
        return "Vi ved ikke, om rabatten også gælder leveringen, så vi har kun trukket den fra kassens pris."
    return ""


# Byggeklodser til siderne

def side(*, sti, titel, beskrivelse, indhold, jsonld=None, aktiv=None, prefiks=None,
         stil="", indekser=True):
    dybde = sti.count("/")
    pre = prefiks if prefiks is not None else "../" * dybde
    hjem = pre or "./"
    menu = []
    for href, tekst in [(KATEGORI_STI, "Måltidskasser"), ("om/", "Om sitet")]:
        markering = ' aria-current="page"' if href == aktiv else ""
        menu.append(f'<a href="{pre}{href}"{markering}>{e(tekst)}</a>')
    if indekser:
        kanonisk = SITE_URL + sti
        meta_url = (f'<link rel="canonical" href="{e(kanonisk)}">\n'
                    f'<meta property="og:url" content="{e(kanonisk)}">\n')
    else:
        meta_url = '<meta name="robots" content="noindex">\n'
    ld = jsonld_tag(jsonld) if jsonld else ""
    stil_tag = f"<style>\n{stil}\n</style>\n" if stil else ""
    return f"""<!doctype html>
<html lang="da">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{e(titel)}</title>
<meta name="description" content="{e(beskrivelse)}">
{meta_url}<meta property="og:type" content="website">
<meta property="og:locale" content="da_DK">
<meta property="og:site_name" content="{e(SITE_NAVN)}">
<meta property="og:title" content="{e(titel)}">
<meta property="og:description" content="{e(beskrivelse)}">
<meta name="theme-color" content="#e6f2eb">
<link rel="icon" href="{pre}favicon.svg" type="image/svg+xml">
<link rel="preload" href="{pre}fonts/ajt-serif.woff" as="font" type="font/woff" crossorigin>
<link rel="stylesheet" href="{pre}styles.css">
{stil_tag}{ld}</head>
<body>
<a class="spring" href="#indhold">Gå til indholdet</a>
<header class="top-baand">
<div class="ramme top">
<a class="maerke" href="{hjem}"><img src="{pre}logo.svg" width="564" height="83" alt="{e(SITE_NAVN)}, forsiden"></a>
<nav aria-label="Hovedmenu">{"".join(menu)}</nav>
</div>
</header>
<main id="indhold">
{indhold}
</main>
<footer class="bund">
<div class="ramme">
<p class="bund-navn">{e(SITE_NAVN)}</p>
<p>En oversigt fra {UDGIVER}. Skriv til <a href="mailto:{KONTAKT}">{KONTAKT}</a>, hvis du ser en fejl.</p>
<p>Sitet sætter ingen cookies. <a href="{pre}om/#penge">Sådan tjener vi penge</a>.</p>
</div>
</footer>
</body>
</html>
"""


def knap(udbyder):
    """Knappen videre til udbyderen. Er der et reklamelink, mærkes det lige ved knappen."""
    navn = e(udbyder["navn"])
    if udbyder.get("reklamelink"):
        return (f'<div class="videre"><a class="knap" href="{e(udbyder["reklamelink"])}" '
                f'rel="sponsored">Gå til {navn}</a> <span class="reklame">Reklamelink</span></div>')
    return f'<div class="videre"><a class="knap" href="{e(udbyder["link"])}">Gå til {navn}</a></div>'


def beloeb_html(beloeb, hoejst=False):
    if beloeb is None:
        return '<span class="ukendt-tal">Ukendt</span>'
    foran = '<span class="forbehold">højst</span>' if hoejst else ""
    return f'{foran}<span class="beloeb">{kr_tal(beloeb)}</span> <span class="enhed">kr.</span>'


def vilkaar_html(u):
    punkter = [("Binding", u.get("binding")), ("Levering", u.get("levering")),
               ("Økologi", u.get("oekologi"))]
    raekker = "\n".join(f"<div><dt>{navn}</dt><dd>{e(vaerdi)}</dd></div>"
                        for navn, vaerdi in punkter if vaerdi)
    return f"""<details class="vilkaar">
<summary>Binding, levering og økologi</summary>
<dl>
{raekker}
</dl>
</details>"""


def kontrol_html(b):
    if not b.get("kontrolleret"):
        return ""
    if b.get("kilde"):
        return (f'<p class="kontrol">Prisen er kontrolleret {dansk_dato(b["kontrolleret"])} på '
                f'<a href="{e(b["kilde"])}">{e(domaene(b["kilde"]))}</a>.</p>')
    return f'<p class="kontrol">Prisen er kontrolleret {dansk_dato(b["kontrolleret"])}.</p>'


def udbyder_html(u, b, plan):
    intro = u.get("intro")
    levering = f"levering koster {kr(u['fragt'])}" if u["fragt"] else "levering er gratis"
    if b["status"] == "ukendt":
        tekst = (f"Vi kunne ikke se prisen for {plan_tekst(plan)}, da vi kontrollerede "
                 f"{dansk_dato(b['kontrolleret'])}. " + punktum(levering[0].upper() + levering[1:]))
        pris = f'<p class="ukendt">{e(tekst)}</p>'
        kontrol = ""
    else:
        # Listen er sorteret efter normalprisen, så den kolonne er farvet.
        celler = [
            ("Første levering", beloeb_html(b["foerste"], b["hoejst"]), ""),
            ("Normalpris pr. uge", beloeb_html(b["uge"]), ' class="valgt"'),
            ("Pr. portion", beloeb_html(b["pr_portion"]), ""),
        ]
        celle_html = "\n".join(f"<div{klasse}><dt>{e(navn)}</dt><dd>{vaerdi}</dd></div>"
                               for navn, vaerdi, klasse in celler)
        saetninger = [punktum(f"Kassen koster {kr(b['kasse'])}, og {levering}")]
        if not intro:
            saetninger.append("Der er ikke noget introtilbud, så første levering koster det samme som de næste.")
        pris = (f'<dl class="priser">\n{celle_html}\n</dl>\n'
                f'<p class="regnestykke">{e(" ".join(saetninger))}</p>')
        kontrol = kontrol_html(b)
    # Tilbud står for sig på rosa, ligesom på forsiden.
    noter = []
    if intro:
        noter.append(tilbud_til_nye(intro))
        if b["status"] != "ukendt" and forbehold(intro):
            noter.append(forbehold(intro))
    if u.get("andet_tilbud"):
        noter.append(u["andet_tilbud"])
    tilbud = f'<p class="tilbud-boks">{e(" ".join(noter))}</p>\n' if noter else ""
    return f"""<li class="udbyder">
<h3>{e(u["navn"])}</h3>
<p class="loesning">{e(u["loesning"])}</p>
{pris}
{tilbud}<p class="beskrivelse">{e(u["beskrivelse"])}</p>
{vilkaar_html(u)}
{knap(u)}
{kontrol}
</li>"""


def tilbud_html(udbydere, overskrift="h2"):
    punkter = []
    datoer = []
    for u in sorted(udbydere, key=lambda u: u["navn"].lower()):
        if u.get("intro"):
            punkter.append((u["navn"], tilbud_kort(u["intro"]), "Gælder nye kunder."))
            datoer.append(u["intro"].get("kontrolleret"))
        if u.get("andet_tilbud"):
            punkter.append((u["navn"], u["andet_tilbud"], ""))
    if not punkter:
        return ""
    datoer = [d for d in datoer if d]
    dato = f" Vi har tjekket dem {dansk_dato(max(datoer))}." if datoer else ""
    li = "\n".join(
        f'<li><span class="tilbud-navn">{e(navn)}</span> {e(tekst)}'
        f'{" <span class=\"tilbud-note\">" + e(note) + "</span>" if note else ""}</li>'
        for navn, tekst, note in punkter)
    return f"""<section class="tilbud" aria-labelledby="tilbud">
<{overskrift} id="tilbud">Tilbud lige nu</{overskrift}>
<p class="tilbud-intro">Tilbuddene kan ændre sig fra uge til uge.{dato}</p>
<ul class="tilbud-liste">
{li}
</ul>
</section>"""


# Siderne

def kategoriside(data, beregninger, opdateret):
    kat = data["kategori"]
    planer = kat["planer"]
    udbydere = data["udbydere"]
    dato = kontrol_periode(alle_kontroldatoer(beregninger))

    plan_valg = "\n".join(
        f'<input type="radio" name="plan" id="plan-{p["id"]}" value="{p["id"]}"'
        f'{" checked" if i == 0 else ""}><label for="plan-{p["id"]}">{p["personer"]} personer</label>'
        for i, p in enumerate(planer))
    retter = sorted({p["retter"] for p in planer})
    retter_tekst = f"{retter[0]} retter om ugen" if len(retter) == 1 else "et fast antal retter om ugen"

    lister = []
    for plan in planer:
        raekke = sorted(udbydere, key=lambda u: sorteringsnoegle(u, beregninger[u["id"]][plan["id"]]))
        status = f"{plan_tekst(plan)}. Lavest normalpris står øverst."
        punkter = "\n".join(udbyder_html(u, beregninger[u["id"]][plan["id"]], plan) for u in raekke)
        lister.append(f"""<div class="liste" data-vis="{plan["id"]}">
<p class="liste-status">{e(status)}</p>
<ol class="udbydere">
{punkter}
</ol>
</div>""")

    vis_regler = ",\n".join(
        f'.sammenligning:has(#plan-{p["id"]}:checked) [data-vis="{p["id"]}"]' for p in planer)
    stil = f"@supports selector(:has(a)) {{\n{vis_regler} {{\n  display: block;\n}}\n}}"

    faerdig = ""
    if data.get("faerdigretter"):
        blokke = []
        for f in data["faerdigretter"]:
            fakta = "\n".join(f"<div><dt>{e(navn)}</dt><dd>{e(vaerdi)}</dd></div>" for navn, vaerdi in f["fakta"])
            blokke.append(f"""<div class="faerdig">
<h3>{e(f["navn"])}</h3>
<p class="loesning">{e(f["loesning"])}</p>
<p>{e(f["beskrivelse"])}</p>
<dl class="fakta">
{fakta}
</dl>
{knap(f)}
<p class="kontrol">Kontrolleret {dansk_dato(f["kontrolleret"])}.</p>
</div>""")
        faerdig = f"""<h2 id="faerdigretter">Hvis I hellere vil have færdigretter</h2>
<p>Færdigretter skal bare varmes. De er ikke med i sammenligningen ovenfor, fordi man ikke køber dem pr. ret og person på samme måde.</p>
{"".join(blokke)}"""

    ikke_med = ""
    if data.get("ikke_med"):
        punkter = "\n".join(f"<li><strong>{e(navn)}.</strong> {e(grund)}</li>" for navn, grund in data["ikke_med"])
        ikke_med = f"""<h2 id="ikke-med">Ikke med lige nu</h2>
<ul class="ikke-med">
{punkter}
</ul>"""

    log = "\n".join(
        f'<li><time datetime="{e(d)}">{dansk_dato(d)}</time> {e(t)}</li>'
        for d, t in sorted(data.get("opdateringer", []), reverse=True))

    indhold = f"""<div class="sammenligning">
<section class="intro">
<div class="ramme">
<h1>Vegetariske måltidskasser</h1>
<p class="lead">Her er måltidskasserne, hvor hele kassen kan være uden kød og fisk. Vælg, hvor mange I er, så viser vi prisen på første levering, normalprisen pr. uge og prisen pr. portion.</p>
<p class="dato">Alle priser er med levering og {retter_tekst}. De er kontrolleret {dato}.</p>
<div class="valg">
<fieldset class="segment">
<legend>Hvor mange er I?</legend>
<div class="segment-valg">
{plan_valg}
</div>
</fieldset>
</div>
</div>
</section>
<div class="ramme lister">
{chr(10).join(lister)}
</div>
</div>
<div class="ramme">
{faerdig}
{ikke_med}
<h2 id="metode">Sådan regner vi</h2>
<div class="tekst">
<p>Normalprisen pr. uge er kassen plus levering, uden tilvalg. Prisen pr. portion er normalprisen delt med antallet af portioner.</p>
<p>Første levering er normalprisen med introtilbuddet trukket fra. Kan vi ikke se rabatten på den første kasse, står der ukendt.</p>
<p>Listen er sorteret efter normalprisen, fordi det er den, du betaler, når tilbuddet er brugt. Kan vi slet ikke se en pris, står udbyderen nederst. Om en udbyder betaler os for et link, ændrer ikke rækkefølgen.</p>
<p>Beløbene er afrundet til hele kroner. Vi har ikke smagt maden, så vi siger ikke noget om, hvordan den smager. Tjek altid prisen hos udbyderen, før du bestiller, for den kan have ændret sig.</p>
</div>
<h2 id="data">Hent tallene</h2>
<p>Alle tallene ligger også som <a href="../data/{DATAFIL}.csv">CSV-fil</a> og som <a href="../data/{DATAFIL}.json">JSON</a>, hvis du vil regne selv.</p>
<h2 id="aendringer">Ændringer</h2>
<ul class="log">
{log}
</ul>
</div>"""

    url = SITE_URL + KATEGORI_STI
    alfabetisk = sorted(udbydere, key=lambda u: u["navn"].lower())
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebPage", "@id": url, "url": url, "name": kat["navn"], "inLanguage": "da",
             "dateModified": opdateret, "isPartOf": {"@id": SITE_URL + "#site"}},
            {"@type": "ItemList", "name": "Vegetariske måltidskasser i Danmark",
             "itemListOrder": "https://schema.org/ItemListUnordered",
             "numberOfItems": len(alfabetisk),
             "itemListElement": [{"@type": "ListItem", "position": i, "name": f'{u["navn"]}, {u["loesning"]}',
                                  "url": u["link"]} for i, u in enumerate(alfabetisk, start=1)]},
            {"@type": "Dataset", "name": "Priser på vegetariske måltidskasser i Danmark",
             "description": "Pris på første levering, normalpris pr. uge og pris pr. portion med levering "
                            "for vegetariske måltidskasser til 2 og 4 personer, aflæst hos udbyderne.",
             "url": url, "inLanguage": "da", "dateModified": opdateret,
             "creator": {"@type": "Organization", "name": UDGIVER},
             "distribution": [
                 {"@type": "DataDownload", "encodingFormat": "text/csv",
                  "contentUrl": f"{SITE_URL}data/{DATAFIL}.csv"},
                 {"@type": "DataDownload", "encodingFormat": "application/json",
                  "contentUrl": f"{SITE_URL}data/{DATAFIL}.json"}]},
        ],
    }
    navne = oprems(u["navn"] for u in alfabetisk)
    return side(sti=KATEGORI_STI,
                titel=f"Vegetariske måltidskasser til 2 og 4 personer | {SITE_NAVN}",
                beskrivelse=f"Sammenlign vegetariske måltidskasser fra {navne}. Se prisen på første levering, "
                            f"normalprisen pr. uge og prisen pr. portion for 2 og 4 personer. Kontrolleret {dato}.",
                indhold=indhold, jsonld=jsonld, aktiv=KATEGORI_STI, stil=stil)


def forside(data, beregninger, opdateret):
    kat = data["kategori"]
    plan = kat["planer"][0]
    udbydere = data["udbydere"]
    raekke = sorted(udbydere, key=lambda u: sorteringsnoegle(u, beregninger[u["id"]][plan["id"]]))
    menu = []
    ukendte = []
    for u in raekke:
        b = beregninger[u["id"]][plan["id"]]
        if b["status"] == "ukendt":
            ukendte.append(u["navn"])
            continue
        menu.append(f'<li><span class="navn">{e(u["navn"])}</span><span class="prikker" aria-hidden="true"></span>'
                    f'<span class="pris">{kr(b["pr_portion"])}</span></li>')
    note = f"Priserne er kontrolleret {kontrol_periode(alle_kontroldatoer(beregninger))}."
    if ukendte:
        note = f"Vi kunne ikke se prisen hos {oprems(ukendte)}. " + note
    indhold = f"""<section class="intro forside-intro">
<div class="ramme">
<h1>Abonnementer på det, du bruger igen og igen</h1>
<p class="lead">Vi sammenligner abonnementer på ting, der kommer af sig selv, og viser, hvad de koster med levering. Vi er startet med vegetariske måltidskasser.</p>
<p><a class="knap" href="{KATEGORI_STI}">Se de vegetariske måltidskasser</a></p>
<section class="smagsproeve" aria-labelledby="eksempel">
<h2 id="eksempel">Vegetarisk måltidskasse til {plan["personer"]} personer</h2>
<p class="smagsproeve-under">Pris pr. portion med levering, når I får {plan["retter"]} retter om ugen.</p>
<ol class="menukort">
{chr(10).join(menu)}
</ol>
<p class="smagsproeve-note">{e(note)} <a href="{KATEGORI_STI}">Se hele sammenligningen</a></p>
</section>
</div>
</section>
<div class="ramme">
{tilbud_html(udbydere)}
<h2 id="saadan">Sådan regner vi</h2>
<div class="principper">
<div>
<h3>Vi regner levering med</h3>
<p>Prisen pr. uge og pr. portion er med levering, så du kan sammenligne kasserne direkte.</p>
</div>
<div>
<h3>Vi skriver kun priser, vi selv har set</h3>
<p>Vi aflæser priserne hos udbyderne og skriver datoen på. Kan vi ikke se en pris, skriver vi det i stedet for at gætte.</p>
</div>
<div>
<h3>Vi mærker reklamelinks</h3>
<p>Kan et link give os penge, står der Reklamelink ved knappen. Det ændrer ikke rækkefølgen, som kun afgøres af prisen.</p>
</div>
</div>
<h2 id="senere">Det kommer senere</h2>
<p>Kaffe, bleer, shampoo og dyremad står på listen. Vi tilføjer en kategori, når vi har tjekket priserne.</p>
</div>"""
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "@id": SITE_URL + "#site", "url": SITE_URL, "name": SITE_NAVN,
             "inLanguage": "da", "publisher": {"@id": SITE_URL + "#udgiver"}},
            {"@type": "Organization", "@id": SITE_URL + "#udgiver", "name": UDGIVER, "email": KONTAKT},
        ],
    }
    return side(sti="", titel=f"{SITE_NAVN} | Abonnementer på det, du bruger igen og igen",
                beskrivelse="Vi sammenligner abonnementer på måltidskasser og andet, der kommer af sig selv, "
                            "og viser, hvad de koster med levering.",
                indhold=indhold, jsonld=jsonld)


def omside(data):
    reklame = any(u.get("reklamelink") for u in data["udbydere"] + data.get("faerdigretter", []))
    status = ("" if reklame else " Lige nu er ingen af knapperne reklamelinks.")
    indhold = f"""<section class="intro">
<div class="ramme">
<h1>Om {SITE_NAVN}</h1>
<p class="lead">{SITE_NAVN} sammenligner abonnementer på det, du bruger igen og igen. Vi regner ud, hvad de koster, så du ikke selv skal.</p>
</div>
</section>
<div class="ramme tekst">
<h2 id="hvem">Hvem står bag</h2>
<p>Sitet er en del af {UDGIVER}. Du kan skrive til os på <a href="mailto:{KONTAKT}">{KONTAKT}</a>.</p>
<h2 id="penge">Sådan tjener vi penge</h2>
<p>Det er gratis at bruge sitet. Nogle udbydere betaler os et beløb, når nogen bliver kunde gennem vores link. Det koster ikke dig noget ekstra.</p>
<p>Et link, der kan give os penge, er mærket med ordet Reklamelink lige ved knappen.{status}</p>
<p>En aftale afgør ikke, om en udbyder kommer med, eller hvor den står. Rækkefølgen afgøres kun af prisen.</p>
<h2 id="tal">Sådan finder vi tallene</h2>
<p>Vi aflæser priser og vilkår hos udbyderne selv. Nogle gange går vi bestillingen igennem, men vi stopper før betaling. Vi skriver datoen på hver pris.</p>
<p>Kan vi ikke se en pris, skriver vi det i stedet for at gætte.</p>
<h2 id="vurdering">Det vurderer vi ikke</h2>
<p>Vi har ikke smagt maden og siger ikke noget om kvaliteten. Vi sammenligner pris og vilkår.</p>
<h2 id="cookies">Cookies</h2>
<p>Sitet sætter ingen cookies og bruger ingen statistik. Når du klikker videre til en udbyder, gælder udbyderens egne regler.</p>
</div>"""
    return side(sti="om/", titel=f"Om sitet | {SITE_NAVN}",
                beskrivelse="Hvem står bag Abonnement, ja tak, hvordan vi finder priserne, og hvordan sitet tjener penge.",
                indhold=indhold, aktiv="om/")


def side404():
    indhold = f"""<section class="intro">
<div class="ramme">
<h1>Siden findes ikke</h1>
<p class="lead">Adressen passer ikke til nogen side her. Gå til <a href="/">forsiden</a> eller til <a href="/{KATEGORI_STI}">de vegetariske måltidskasser</a>.</p>
</div>
</section>"""
    return side(sti="404.html", titel=f"Siden findes ikke | {SITE_NAVN}", beskrivelse="Siden findes ikke.",
                indhold=indhold, prefiks="/", indekser=False)


# Filer til maskiner og regneark

def datafiler(data, beregninger, opdateret):
    kat = data["kategori"]
    kolonner = ["id", "udbyder", "loesning", "personer", "retter_om_ugen", "kassepris_kr", "levering_kr",
                "normalpris_pr_uge_kr", "pr_portion_kr", "foerste_levering_kr", "foerste_levering_er_hoejst",
                "status", "introtilbud", "kontrolleret", "kilde", "link"]
    raekker = []
    for u in sorted(data["udbydere"], key=lambda u: u["navn"].lower()):
        for plan in kat["planer"]:
            b = beregninger[u["id"]][plan["id"]]

            def tal(navn, b=b):
                v = b.get(navn)
                return "" if v is None else hele_kroner(v)

            raekker.append({
                "id": u["id"], "udbyder": u["navn"], "loesning": u["loesning"],
                "personer": plan["personer"], "retter_om_ugen": plan["retter"],
                "kassepris_kr": tal("kasse"), "levering_kr": u["fragt"],
                "normalpris_pr_uge_kr": tal("uge"), "pr_portion_kr": tal("pr_portion"),
                "foerste_levering_kr": tal("foerste"),
                "foerste_levering_er_hoejst": "ja" if b["hoejst"] else "",
                "status": b["status"],
                "introtilbud": tilbud_kort(u["intro"]).replace(" ", " ") if u.get("intro") else "",
                "kontrolleret": b.get("kontrolleret") or "", "kilde": b.get("kilde") or "",
                "link": u["link"],
            })
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=kolonner, delimiter=";", lineterminator="\n")
    w.writeheader()
    w.writerows(raekker)
    skriv(f"data/{DATAFIL}.csv", buf.getvalue())
    ud = {
        "navn": "Priser på vegetariske måltidskasser i Danmark",
        "kilde": SITE_URL + KATEGORI_STI,
        "opdateret": opdateret,
        "forklaring": {
            "normalpris_pr_uge_kr": "Kassen plus levering, uden tilvalg.",
            "pr_portion_kr": "Normalprisen pr. uge delt med antallet af portioner.",
            "foerste_levering_kr": "Normalprisen med introtilbuddet trukket fra. Tom, hvis rabatten "
                                   "på første kasse ikke kunne ses.",
            "status": "kendt: kassens pris kunne ses. ukendt: vi kunne ikke se prisen.",
        },
        "priser": raekker,
    }
    skriv(f"data/{DATAFIL}.json", json.dumps(ud, ensure_ascii=False, indent=2) + "\n")


def maskinfiler(data, opdateret):
    urls = ["", KATEGORI_STI, "om/"]
    sitemap = "\n".join(f"<url><loc>{SITE_URL}{u}</loc><lastmod>{opdateret}</lastmod></url>" for u in urls)
    skriv("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"{sitemap}\n</urlset>\n")
    skriv("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n")
    navne = oprems(sorted(u["navn"] for u in data["udbydere"]))
    skriv("llms.txt", f"""# {SITE_NAVN}

> Dansk oversigt over abonnementer på det, man bruger igen og igen. Første kategori er vegetariske måltidskasser fra {navne}. For 2 og 4 personer med 3 retter om ugen viser sitet prisen på første levering, normalprisen pr. uge og prisen pr. portion, alle med levering. Priserne er aflæst hos udbyderne, senest {dansk_dato(opdateret)}. Hvor en pris ikke kunne ses, står der det.

## Sider

- [Vegetariske måltidskasser]({SITE_URL}{KATEGORI_STI}): sammenligning af priser, introtilbud, binding og levering
- [Om sitet]({SITE_URL}om/): hvem står bag, hvordan tallene findes, og hvordan sitet tjener penge

## Data

- [Priser som CSV]({SITE_URL}data/{DATAFIL}.csv)
- [Priser som JSON]({SITE_URL}data/{DATAFIL}.json)
""")
    skriv(".nojekyll", "")


def main():
    with open(DATA / "maaltidskasser.json", encoding="utf-8") as fh:
        data = json.load(fh)
    kat = data["kategori"]
    beregninger = {u["id"]: {p["id"]: beregn(u, p) for p in kat["planer"]} for u in data["udbydere"]}
    datoer = [b["kontrolleret"] for pr in beregninger.values() for b in pr.values() if b.get("kontrolleret")]
    opdateret = max(datoer)

    if UD.exists():
        shutil.rmtree(UD)
    UD.mkdir()
    for navn in ["styles.css", "favicon.svg", "logo.svg", "CNAME"]:
        if (SRC / navn).exists():
            shutil.copy(SRC / navn, UD / navn)
    shutil.copytree(SRC / "fonts", UD / "fonts")

    skriv("index.html", forside(data, beregninger, opdateret))
    skriv(KATEGORI_STI + "index.html", kategoriside(data, beregninger, opdateret))
    skriv("om/index.html", omside(data))
    skriv("404.html", side404())
    datafiler(data, beregninger, opdateret)
    maskinfiler(data, opdateret)

    for u in data["udbydere"]:
        for p in kat["planer"]:
            b = beregninger[u["id"]][p["id"]]
            if b["status"] == "ukendt":
                print(f"  {u['navn']} {p['id']}: pris ukendt")
            else:
                foerste = "ukendt" if b["foerste"] is None else ("højst " if b["hoejst"] else "") + kr(b["foerste"])
                print(f"  {u['navn']} {p['id']}: første {foerste}, uge {kr(b['uge'])}, "
                      f"portion {kr(b['pr_portion'])}")
    print(f"Bygget {len(data['udbydere'])} udbydere, opdateret {opdateret}, i {UD}")


if __name__ == "__main__":
    main()
