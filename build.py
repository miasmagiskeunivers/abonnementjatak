#!/usr/bin/env python3
"""Bygger abonnementjatak.dk som statiske sider i docs/ ud fra filerne i data/.

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
MAANEDS_FILER = ["legetoej.json", "hundekasser.json"]

# Menuen sættes i main(), når alle kategorier er læst.
MENU = [(KATEGORI_STI, "Måltidskasser"), ("om/", "Om sitet")]

HVER = {1: "hver måned", 2: "hver anden måned", 3: "hver tredje måned",
        4: "hver fjerde måned", 6: "hver sjette måned"}

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
    """Fx "25 % rabat på første levering, 15 % på anden og 10 % på tredje" eller
    "30 % rabat på første levering og 20 % på de fire næste"."""
    grupper = []
    for procent in intro["procenter"]:
        if grupper and grupper[-1][0] == procent:
            grupper[-1][1] += 1
        else:
            grupper.append([procent, 1])
    dele = []
    nummer = 1
    for procent, antal in grupper:
        if nummer == 1:
            hvor = "første levering" if antal == 1 else f"de {TAL.get(antal, antal)} første leveringer"
            dele.append(f"{procent} % rabat på {hvor}")
        else:
            hvor = ORDENSTAL[nummer] if antal == 1 else f"de {TAL.get(antal, antal)} næste"
            dele.append(f"{procent} % på {hvor}")
        nummer += antal
    return oprems(dele)


def tilbud_kort(intro):
    """Tilbuddet med udbyderens egne tal, som en sætning for sig."""
    if intro["type"] == "op_til_kr":
        n = intro["leveringer"]
        return f"Spar op til {kr(intro['beloeb'])} på de {TAL.get(n, n)} første kasser."
    if intro["type"] == "procent_pr_levering":
        return procent_raekke(intro) + "."
    if intro["type"] == "foerste_kasse":
        return f"Første kasse koster {kr(intro['pris'])} med fragt."
    if intro["type"] == "maaneder_til_pris":
        n = intro["maaneder"]
        return f"De {TAL.get(n, n)} første måneder koster {kr(intro['pris'])} om måneden."
    raise ValueError(intro["type"])


def tilbud_til_nye(intro):
    if intro["type"] == "op_til_kr":
        n = intro["leveringer"]
        return f"Som ny kunde kan du spare op til {kr(intro['beloeb'])} på de {TAL.get(n, n)} første kasser."
    if intro["type"] == "procent_pr_levering":
        return f"Som ny kunde får du {procent_raekke(intro)}."
    if intro["type"] == "foerste_kasse":
        return f"Som ny kunde betaler du {kr(intro['pris'])} for første kasse med fragt."
    if intro["type"] == "maaneder_til_pris":
        n = intro["maaneder"]
        note = f" {intro['note']}" if intro.get("note") else ""
        return (f"Som ny kunde betaler du {kr(intro['pris'])} om måneden de {TAL.get(n, n)} "
                f"første måneder.{note}")
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
    for href, tekst in MENU:
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


def beloeb_html(beloeb, hoejst=False, ca=False):
    if beloeb is None:
        return '<span class="ukendt-tal">Ukendt</span>'
    if hoejst:
        foran = '<span class="forbehold">højst</span>'
    elif ca:
        foran = '<span class="forbehold">ca.</span>'
    else:
        foran = ""
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


# Kasser, der kommer med faste mellemrum: legetøj og hundekasser

def euro(beloeb):
    """Fx "88 €" eller "7,90 €" med hårdt mellemrum."""
    d = Decimal(str(beloeb)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    tekst = str(int(d)) if d == d.to_integral_value() else f"{d:.2f}".replace(".", ",")
    return tekst + " €"


def valuta_beloeb(beloeb, valuta):
    return euro(beloeb) if valuta == "EUR" else kr(beloeb)


def kurs_tekst(kurs):
    """Fx "7,46 kr."."""
    d = Decimal(str(kurs)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{d:.2f}".replace(".", ",") + " kr."


def beregn_maaned(u, plan, kurs):
    """Regner prisen ud for én udbyder og én plan, fx en aldersgruppe.

    Giver None, når udbyderen ikke har noget til planen. Beløb i euro omregnes til kroner
    med kurs, og omregnet bliver True, så siden kan skrive ca. foran.
    """
    p = u["priser"].get(plan["id"])
    if p is None:
        return None
    valuta = u.get("valuta", "DKK")
    faktor = kurs if valuta == "EUR" else 1
    b = {"kontrolleret": p.get("kontrolleret"), "kilde": p.get("kilde"), "valuta": valuta,
         "omregnet": valuta != "DKK", "note": p.get("note", "")}
    if p.get("kasse") is None:
        b["status"] = "ukendt"
        return b
    kasse, fragt, hver = p["kasse"], p.get("fragt", 0), p.get("hver", 1)
    fragt_foerste = p.get("fragt_foerste", fragt)
    intro = u.get("intro")
    if not intro:
        foerste = kasse + fragt_foerste
    elif intro["type"] in ("foerste_kasse", "maaneder_til_pris"):
        if valuta != "DKK":
            raise ValueError(f"Introtilbud skal stå i kroner hos {u['id']}")
        foerste = intro["pris"]
    else:
        raise ValueError(f"Ukendt type introtilbud hos {u['id']}: {intro['type']}")
    pr_kasse = kasse + fragt
    b.update(status="kendt", kasse=kasse, fragt=fragt, fragt_foerste=fragt_foerste, hver=hver,
             foerste_valuta=foerste, pr_kasse_valuta=pr_kasse,
             foerste=foerste * faktor, pr_kasse=pr_kasse * faktor, pr_maaned=pr_kasse * faktor / hver)
    return b


def sorteringsnoegle_maaned(u, b):
    """Billigste pris pr. måned først. Udbydere uden kendt pris står nederst."""
    if b["status"] == "ukendt":
        return (1, 0, u["navn"].lower())
    return (0, b["pr_maaned"], u["navn"].lower())


def kontroldatoer_maaned(beregninger):
    return [b["kontrolleret"] for pr in beregninger.values() for b in pr.values()
            if b and b.get("kontrolleret")]


def undertekst(u):
    """Linjen under navnet, fx alder og om man beholder legetøjet."""
    if u.get("undertekst"):
        return u["undertekst"]
    dele = []
    if u.get("alder"):
        dele.append(f"Til børn {u['alder']}.")
    if u.get("legetoej") == "beholdes":
        dele.append("I beholder legetøjet.")
    elif u.get("legetoej") == "lejes":
        dele.append("I lejer legetøjet og bytter det hver måned.")
    return " ".join(dele)


def regnestykke_maaned(u, b, kat):
    v = b["valuta"]
    kasse = valuta_beloeb(b["kasse"], v)
    if u.get("fragt_tekst"):
        saetninger = [punktum(f"Kassen koster {kasse}, og {u['fragt_tekst']}")]
    elif b["fragt"]:
        saetninger = [punktum(f"Kassen koster {kasse}, og fragten koster {valuta_beloeb(b['fragt'], v)}")]
    else:
        saetninger = [punktum(f"Kassen koster {kasse}, og levering er gratis")]
    hvor_tit = HVER.get(b["hver"]) or f"hver {b['hver']}. måned"
    if len(kat["planer"]) > 1 or b["hver"] != 1:
        saetninger.append(f"Den kommer {hvor_tit}.")
    if b["fragt_foerste"] != b["fragt"]:
        saetninger.append(punktum(f"Første gang koster fragten {valuta_beloeb(b['fragt_foerste'], v)}"))
    elif not u.get("intro"):
        saetninger.append("Der er ikke noget introtilbud, så første kasse koster det samme som de næste.")
    if b["omregnet"]:
        saetninger.append(f"{u['navn']} tager betaling i euro, og vi har omregnet med "
                          f"{kurs_tekst(kat['kurs_eur'])} pr. euro.")
    if b.get("note"):
        saetninger.append(b["note"])
    return saetninger


CELLE_NAVNE = {"foerste": "Første kasse", "pr_kasse": "Pris pr. kasse", "pr_maaned": "Pr. måned"}


def vilkaar_maaned_html(u, kat):
    punkter = [("Binding", u.get("binding")), ("Levering", u.get("levering")),
               ("Størrelse", u.get("stoerrelse"))]
    raekker = "\n".join(f"<div><dt>{navn}</dt><dd>{e(vaerdi)}</dd></div>"
                        for navn, vaerdi in punkter if vaerdi)
    return f"""<details class="vilkaar">
<summary>{e(kat["vilkaar_titel"])}</summary>
<dl>
{raekker}
</dl>
</details>"""


def udbyder_maaned_html(u, b, kat):
    intro = u.get("intro")
    if b["status"] == "ukendt":
        tekst = f"Vi kunne ikke se prisen, da vi kontrollerede {dansk_dato(b['kontrolleret'])}."
        pris = f'<p class="ukendt">{e(tekst)}</p>'
        kontrol = ""
    else:
        # Listen er sorteret efter prisen pr. måned, så den kolonne er farvet.
        celler = []
        for navn in kat["celler"]:
            klasse = ' class="valgt"' if navn == "pr_maaned" else ""
            celler.append(f'<div{klasse}><dt>{CELLE_NAVNE[navn]}</dt>'
                          f'<dd>{beloeb_html(b[navn], ca=b["omregnet"])}</dd></div>')
        celle_html = "\n".join(celler)
        pris = (f'<dl class="priser priser-{len(celler)}">\n{celle_html}\n</dl>\n'
                f'<p class="regnestykke">{e(" ".join(regnestykke_maaned(u, b, kat)))}</p>')
        kontrol = kontrol_html(b)
    noter = []
    if intro:
        noter.append(tilbud_til_nye(intro))
    if u.get("andet_tilbud"):
        noter.append(u["andet_tilbud"])
    tilbud = f'<p class="tilbud-boks">{e(" ".join(noter))}</p>\n' if noter else ""
    return f"""<li class="udbyder">
<h3>{e(u["navn"])}</h3>
<p class="loesning">{e(u["loesning"])}</p>
<p class="undertekst">{e(undertekst(u))}</p>
{pris}
{tilbud}<p class="beskrivelse">{e(u["beskrivelse"])}</p>
{vilkaar_maaned_html(u, kat)}
{knap(u)}
{kontrol}
</li>"""


def maanedsside(data, beregninger, opdateret):
    kat = data["kategori"]
    sti = kat["sti"]
    planer = kat["planer"]
    udbydere = data["udbydere"]
    dato = kontrol_periode(kontroldatoer_maaned(beregninger))
    flere = len(planer) > 1

    lister = []
    for plan in planer:
        med = [u for u in udbydere if beregninger[u["id"]][plan["id"]] is not None]
        uden = [u for u in udbydere if beregninger[u["id"]][plan["id"]] is None]
        raekke = sorted(med, key=lambda u: sorteringsnoegle_maaned(u, beregninger[u["id"]][plan["id"]]))
        status = f"{plan['tekst']}. Lavest pris pr. måned står øverst."
        punkter = "\n".join(udbyder_maaned_html(u, beregninger[u["id"]][plan["id"]], kat) for u in raekke)
        mangler = "\n".join(
            f'<p class="liste-note">{e(u["navn"])} er ikke med her, fordi kasserne er til børn {e(u["alder"])}.</p>'
            for u in uden if u.get("alder"))
        if flere:
            aabning = f'<div class="liste" data-vis="{plan["id"]}">'
        else:
            aabning = '<div class="liste-fast">'
        lister.append(f"""{aabning}
<p class="liste-status">{e(status)}</p>
<ol class="udbydere">
{punkter}
</ol>
{mangler}
</div>""")

    valg = ""
    stil = ""
    if flere:
        plan_valg = "\n".join(
            f'<input type="radio" name="plan" id="plan-{p["id"]}" value="{p["id"]}"'
            f'{" checked" if i == 0 else ""}><label for="plan-{p["id"]}">{e(p["navn"])}</label>'
            for i, p in enumerate(planer))
        valg = f"""<div class="valg">
<fieldset class="segment">
<legend>{e(kat["valg_spoergsmaal"])}</legend>
<div class="segment-valg">
{plan_valg}
</div>
</fieldset>
</div>"""
        vis_regler = ",\n".join(
            f'.sammenligning:has(#plan-{p["id"]}:checked) [data-vis="{p["id"]}"]' for p in planer)
        stil = f"@supports selector(:has(a)) {{\n{vis_regler} {{\n  display: block;\n}}\n}}"

    ikke_med = ""
    if data.get("ikke_med"):
        punkter = "\n".join(f"<li><strong>{e(navn)}.</strong> {e(grund)}</li>" for navn, grund in data["ikke_med"])
        ikke_med = f"""<h2 id="ikke-med">Ikke med lige nu</h2>
<ul class="ikke-med">
{punkter}
</ul>"""

    alle = [b for pr in beregninger.values() for b in pr.values() if b and b["status"] == "kendt"]
    metode = list(kat.get("metode_start", []))
    if any(b["hver"] != 1 for b in alle):
        metode.append("Prisen pr. kasse er kassen plus levering. Prisen pr. måned er prisen pr. kasse delt med "
                      "antallet af måneder mellem kasserne. Så kan kasser, der kommer hver måned, sammenlignes "
                      "med kasser, der kommer sjældnere.")
    else:
        metode.append("Prisen pr. måned er kassen plus levering, uden tilvalg.")
    metode.append("Første kasse er det, du betaler første gang, med introtilbud og fragt.")
    if any(b["omregnet"] for b in alle):
        metode.append(f"Nogle udbydere tager betaling i euro. Vi omregner til kroner med Nationalbankens "
                      f"centralkurs, {kurs_tekst(kat['kurs_eur'])} pr. euro, og skriver ca. foran beløbet. "
                      f"Din bank kan tage et gebyr, når du betaler i euro.")
    metode.append("Listen er sorteret efter prisen pr. måned, fordi det er den, du betaler, når tilbuddet er "
                  "brugt. Om en udbyder betaler os for et link, ændrer ikke rækkefølgen.")
    metode.append("Beløbene er afrundet til hele kroner. Vi sammenligner pris og vilkår og siger ikke noget om "
                  "kvaliteten. Tjek altid prisen hos udbyderen, før du bestiller, for den kan have ændret sig.")
    metode_html = "\n".join(f"<p>{e(s)}</p>" for s in metode)

    log = "\n".join(
        f'<li><time datetime="{e(d)}">{dansk_dato(d)}</time> {e(t)}</li>'
        for d, t in sorted(data.get("opdateringer", []), reverse=True))

    datafil = kat["datafil"]
    indhold = f"""<div class="sammenligning">
<section class="intro">
<div class="ramme">
<h1>{e(kat.get("overskrift", kat["navn"]))}</h1>
<p class="lead">{e(kat["lead"])}</p>
<p class="dato">Alle priser er med levering. De er kontrolleret {dato}.</p>
{valg}
</div>
</section>
<div class="ramme lister">
{chr(10).join(lister)}
</div>
</div>
<div class="ramme">
{ikke_med}
<h2 id="metode">Sådan regner vi</h2>
<div class="tekst">
{metode_html}
</div>
<h2 id="data">Hent tallene</h2>
<p>Alle tallene ligger også som <a href="../data/{datafil}.csv">CSV-fil</a> og som <a href="../data/{datafil}.json">JSON</a>, hvis du vil regne selv.</p>
<h2 id="aendringer">Ændringer</h2>
<ul class="log">
{log}
</ul>
</div>"""

    url = SITE_URL + sti
    alfabetisk = sorted(udbydere, key=lambda u: u["navn"].lower())
    navne = oprems(u["navn"] for u in alfabetisk)
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebPage", "@id": url, "url": url, "name": kat["navn"], "inLanguage": "da",
             "dateModified": opdateret, "isPartOf": {"@id": SITE_URL + "#site"}},
            {"@type": "ItemList", "name": f"{kat['navn']} i Danmark",
             "itemListOrder": "https://schema.org/ItemListUnordered",
             "numberOfItems": len(alfabetisk),
             "itemListElement": [{"@type": "ListItem", "position": i, "name": f'{u["navn"]}, {u["loesning"]}',
                                  "url": u["link"]} for i, u in enumerate(alfabetisk, start=1)]},
            {"@type": "Dataset", "name": f"Priser på {kat['navn'].lower()} i Danmark",
             "description": "Pris på første kasse, pris pr. kasse og pris pr. måned med levering, "
                            "aflæst hos udbyderne.",
             "url": url, "inLanguage": "da", "dateModified": opdateret,
             "creator": {"@type": "Organization", "name": UDGIVER},
             "distribution": [
                 {"@type": "DataDownload", "encodingFormat": "text/csv",
                  "contentUrl": f"{SITE_URL}data/{datafil}.csv"},
                 {"@type": "DataDownload", "encodingFormat": "application/json",
                  "contentUrl": f"{SITE_URL}data/{datafil}.json"}]},
        ],
    }
    return side(sti=sti,
                titel=f"{kat['navn']} fra {navne} | {SITE_NAVN}",
                beskrivelse=f"Sammenlign {kat['navn'].lower()} fra {navne}. Se prisen på første kasse og "
                            f"prisen pr. måned med levering. Kontrolleret {dato}.",
                indhold=indhold, jsonld=jsonld, aktiv=sti, stil=stil)


def datafiler_maaned(data, beregninger, opdateret):
    kat = data["kategori"]
    kolonner = ["id", "udbyder", "loesning", "plan", "valuta", "kassepris", "levering", "maaneder_mellem_kasser",
                "foerste_kasse_kr", "pris_pr_kasse_kr", "pris_pr_maaned_kr", "omregnet_fra_euro", "status",
                "introtilbud", "kontrolleret", "kilde", "link"]
    raekker = []
    for u in sorted(data["udbydere"], key=lambda u: u["navn"].lower()):
        for plan in kat["planer"]:
            b = beregninger[u["id"]][plan["id"]]
            if b is None:
                continue

            def tal(navn, b=b):
                v = b.get(navn)
                return "" if v is None else hele_kroner(v)

            raekker.append({
                "id": u["id"], "udbyder": u["navn"], "loesning": u["loesning"], "plan": plan["navn"],
                "valuta": b["valuta"], "kassepris": b.get("kasse", ""), "levering": b.get("fragt", ""),
                "maaneder_mellem_kasser": b.get("hver", ""),
                "foerste_kasse_kr": tal("foerste"), "pris_pr_kasse_kr": tal("pr_kasse"),
                "pris_pr_maaned_kr": tal("pr_maaned"),
                "omregnet_fra_euro": "ja" if b["omregnet"] else "",
                "status": b["status"],
                "introtilbud": tilbud_kort(u["intro"]).replace(" ", " ") if u.get("intro") else "",
                "kontrolleret": b.get("kontrolleret") or "", "kilde": b.get("kilde") or "",
                "link": u["link"],
            })
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=kolonner, delimiter=";", lineterminator="\n")
    w.writeheader()
    w.writerows(raekker)
    skriv(f"data/{kat['datafil']}.csv", buf.getvalue())
    ud = {
        "navn": f"Priser på {kat['navn'].lower()} i Danmark",
        "kilde": SITE_URL + kat["sti"],
        "opdateret": opdateret,
        "forklaring": {
            "kassepris": "Kassens pris i udbyderens valuta, uden levering.",
            "pris_pr_kasse_kr": "Kassen plus levering i kroner.",
            "pris_pr_maaned_kr": "Prisen pr. kasse delt med antallet af måneder mellem kasserne.",
            "foerste_kasse_kr": "Det, du betaler første gang, med introtilbud og fragt.",
            "omregnet_fra_euro": f"ja: beløbet er omregnet med {kat['kurs_eur']} kr. pr. euro.",
            "status": "kendt: prisen kunne ses. ukendt: vi kunne ikke se prisen.",
        },
        "priser": raekker,
    }
    skriv(f"data/{kat['datafil']}.json", json.dumps(ud, ensure_ascii=False, indent=2) + "\n")


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
{f'<p class="tilbud-boks">{e(tilbud_til_nye(f["intro"]))}</p>' if f.get("intro") else ""}
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


def menukort_html(raekker):
    """raekker: [(navn, beloeb, ca)]. Beløb None betyder ukendt og springes over."""
    punkter = []
    for navn, beloeb, ca in raekker:
        foran = '<span class="forbehold-lille">ca.</span> ' if ca else ""
        punkter.append(f'<li><span class="navn">{e(navn)}</span><span class="prikker" aria-hidden="true"></span>'
                       f'<span class="pris">{foran}{kr(beloeb)}</span></li>')
    return f'<ol class="menukort">\n{chr(10).join(punkter)}\n</ol>'


def smagsproeve_html(noegle, titel, under, raekker, ukendte, datoer, sti):
    note = f"Priserne er kontrolleret {kontrol_periode(datoer)}."
    if ukendte:
        note = f"Vi kunne ikke se prisen hos {oprems(ukendte)}. " + note
    return f"""<section class="smagsproeve" data-vis="{noegle}" aria-labelledby="eksempel-{noegle}">
<h2 id="eksempel-{noegle}">{e(titel)}</h2>
<p class="smagsproeve-under">{e(under)}</p>
{menukort_html(raekker)}
<p class="smagsproeve-note">{e(note)} <a href="{sti}">Se hele sammenligningen</a></p>
</section>"""


def tilbud_grupper_html(grupper):
    """grupper: [(overskrift, sti, udbydere)]. Tilbuddene står under hver kategori."""
    blokke = []
    datoer = []
    for overskrift, sti, udbydere in grupper:
        punkter = []
        for u in sorted(udbydere, key=lambda u: u["navn"].lower()):
            if u.get("intro"):
                punkter.append((u["navn"], tilbud_kort(u["intro"]), "Gælder nye kunder."))
                datoer.append(u["intro"].get("kontrolleret"))
            if u.get("andet_tilbud"):
                punkter.append((u["navn"], u["andet_tilbud"], ""))
        if not punkter:
            continue
        li = "\n".join(
            f'<li><span class="tilbud-navn">{e(navn)}</span> {e(tekst)}'
            f'{" <span class=\"tilbud-note\">" + e(note) + "</span>" if note else ""}</li>'
            for navn, tekst, note in punkter)
        blokke.append(f"""<h3 class="tilbud-gruppe"><a href="{sti}">{e(overskrift)}</a></h3>
<ul class="tilbud-liste">
{li}
</ul>""")
    if not blokke:
        return ""
    datoer = [d for d in datoer if d]
    dato = f" Vi har tjekket dem {dansk_dato(max(datoer))}." if datoer else ""
    return f"""<section class="tilbud" aria-labelledby="tilbud">
<h2 id="tilbud">Tilbud lige nu</h2>
<p class="tilbud-intro">Tilbuddene kan ændre sig fra uge til uge.{dato}</p>
{chr(10).join(blokke)}
</section>"""


def forside(data, beregninger, maanedsdata, opdateret):
    kat = data["kategori"]
    plan = kat["planer"][0]
    udbydere = data["udbydere"]

    # Måltidskasser: pris pr. portion for den mindste kasse.
    raekke = sorted(udbydere, key=lambda u: sorteringsnoegle(u, beregninger[u["id"]][plan["id"]]))
    raekker, ukendte = [], []
    for u in raekke:
        b = beregninger[u["id"]][plan["id"]]
        if b["status"] == "ukendt":
            ukendte.append(u["navn"])
        else:
            raekker.append((u["navn"], b["pr_portion"], False))
    proever = [("mad", "Måltidskasser", smagsproeve_html(
        "mad", f"Vegetarisk måltidskasse til {plan['personer']} personer",
        f"Pris pr. portion med levering, når I får {plan['retter']} retter om ugen.",
        raekker, ukendte, alle_kontroldatoer(beregninger), KATEGORI_STI))]

    # De andre kategorier: pris pr. måned for den første plan.
    for mdata, mberegn in maanedsdata:
        mkat = mdata["kategori"]
        mplan = mkat["planer"][0]
        med = [u for u in mdata["udbydere"] if mberegn[u["id"]][mplan["id"]] is not None]
        raekke = sorted(med, key=lambda u: sorteringsnoegle_maaned(u, mberegn[u["id"]][mplan["id"]]))
        raekker, ukendte = [], []
        for u in raekke:
            b = mberegn[u["id"]][mplan["id"]]
            if b["status"] == "ukendt":
                ukendte.append(u["navn"])
            else:
                raekker.append((u["navn"], b["pr_maaned"], b["omregnet"]))
        under = "Pris pr. måned med levering."
        if len(mkat["planer"]) == 1:
            under = f"Pris pr. måned med levering. {mplan['tekst']}."
        proever.append((mkat["id"], mkat["menunavn"], smagsproeve_html(
            mkat["id"], mkat["forside_titel"], under, raekker, ukendte,
            kontroldatoer_maaned(mberegn), mkat["sti"])))

    knapper = "\n".join(
        f'<input type="radio" name="eksempel" id="eksempel-valg-{n}"{" checked" if i == 0 else ""}>'
        f'<label for="eksempel-valg-{n}">{e(navn)}</label>'
        for i, (n, navn, _) in enumerate(proever))
    vis_regler = ",\n".join(f'.smagsproever:has(#eksempel-valg-{n}:checked) [data-vis="{n}"]'
                            for n, _, _ in proever)
    stil = f"@supports selector(:has(a)) {{\n{vis_regler} {{\n  display: block;\n}}\n}}"
    kategorinavne = oprems(["vegetariske måltidskasser"] +
                           [m[0]["kategori"]["menunavn"].lower() for m in maanedsdata])

    grupper = [("Måltidskasser", KATEGORI_STI, udbydere + data.get("faerdigretter", []))]
    grupper += [(m[0]["kategori"]["menunavn"], m[0]["kategori"]["sti"], m[0]["udbydere"]) for m in maanedsdata]

    indhold = f"""<section class="intro forside-intro">
<div class="ramme">
<h1>Abonnementer på det, du bruger igen og igen</h1>
<p class="lead">Vi sammenligner abonnementer på ting, der kommer af sig selv, og viser, hvad de koster med levering. Lige nu kan du sammenligne {e(kategorinavne)}.</p>
<div class="smagsproever">
<fieldset class="segment forside-valg">
<legend>Se et eksempel</legend>
<div class="segment-valg">
{knapper}
</div>
</fieldset>
{chr(10).join(p for _, _, p in proever)}
</div>
</div>
</section>
<div class="ramme">
{tilbud_grupper_html(grupper)}
<h2 id="saadan">Sådan regner vi</h2>
<div class="principper">
<div>
<h3>Vi regner levering med</h3>
<p>Alle priser er med levering, så du kan sammenligne direkte.</p>
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
                beskrivelse=f"Vi sammenligner abonnementer på {kategorinavne} og viser, hvad de koster "
                            "med levering.",
                indhold=indhold, jsonld=jsonld, stil=stil)


def omside(alle_udbydere):
    reklame = any(u.get("reklamelink") for u in alle_udbydere)
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
<p>Vi siger ikke noget om, hvordan maden smager, eller hvor godt legetøjet og kasserne er. Vi sammenligner pris og vilkår.</p>
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
<p class="lead">Adressen passer ikke til nogen side her. Gå til <a href="/">forsiden</a>, eller vælg en kategori i menuen.</p>
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


def maskinfiler(data, maanedsdata, opdateret):
    urls = ["", KATEGORI_STI] + [m[0]["kategori"]["sti"] for m in maanedsdata] + ["om/"]
    sitemap = "\n".join(f"<url><loc>{SITE_URL}{u}</loc><lastmod>{opdateret}</lastmod></url>" for u in urls)
    skriv("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"{sitemap}\n</urlset>\n")
    skriv("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n")
    navne = oprems(sorted(u["navn"] for u in data["udbydere"]))
    afsnit = [f"Vegetariske måltidskasser fra {navne}. For 2 og 4 personer med 3 retter om ugen viser sitet "
              f"prisen på første levering, normalprisen pr. uge og prisen pr. portion, alle med levering."]
    sider = [f"- [Vegetariske måltidskasser]({SITE_URL}{KATEGORI_STI}): sammenligning af priser, introtilbud, "
             f"binding og levering"]
    hent = [f"- [Vegetariske måltidskasser som CSV]({SITE_URL}data/{DATAFIL}.csv)",
            f"- [Vegetariske måltidskasser som JSON]({SITE_URL}data/{DATAFIL}.json)"]
    for mdata, _ in maanedsdata:
        mkat = mdata["kategori"]
        mnavne = oprems(sorted(u["navn"] for u in mdata["udbydere"]))
        planer = oprems(p["tekst"][0].lower() + p["tekst"][1:] for p in mkat["planer"])
        afsnit.append(f"{mkat['navn']} fra {mnavne}. Sitet viser prisen på første kasse og prisen pr. måned "
                      f"med levering for {planer}.")
        sider.append(f"- [{mkat['navn']}]({SITE_URL}{mkat['sti']}): sammenligning af priser, tilbud, binding "
                     f"og levering")
        hent.append(f"- [{mkat['navn']} som CSV]({SITE_URL}data/{mkat['datafil']}.csv)")
        hent.append(f"- [{mkat['navn']} som JSON]({SITE_URL}data/{mkat['datafil']}.json)")
    beskrivelse = " ".join(afsnit)
    skriv("llms.txt", f"""# {SITE_NAVN}

> Dansk oversigt over abonnementer på det, man bruger igen og igen. {beskrivelse} Priserne er aflæst hos udbyderne, senest {dansk_dato(opdateret)}. Hvor en pris ikke kunne ses, står der det.

## Sider

{chr(10).join(sider)}
- [Om sitet]({SITE_URL}om/): hvem står bag, hvordan tallene findes, og hvordan sitet tjener penge

## Data

{chr(10).join(hent)}
""")
    skriv(".nojekyll", "")


def main():
    global MENU
    with open(DATA / "maaltidskasser.json", encoding="utf-8") as fh:
        data = json.load(fh)
    kat = data["kategori"]
    beregninger = {u["id"]: {p["id"]: beregn(u, p) for p in kat["planer"]} for u in data["udbydere"]}

    maanedsdata = []
    for filnavn in MAANEDS_FILER:
        with open(DATA / filnavn, encoding="utf-8") as fh:
            mdata = json.load(fh)
        mkat = mdata["kategori"]
        mberegn = {u["id"]: {p["id"]: beregn_maaned(u, p, mkat["kurs_eur"]) for p in mkat["planer"]}
                   for u in mdata["udbydere"]}
        maanedsdata.append((mdata, mberegn))

    datoer = alle_kontroldatoer(beregninger)
    for _, mberegn in maanedsdata:
        datoer += kontroldatoer_maaned(mberegn)
    opdateret = max(datoer)

    MENU = ([(KATEGORI_STI, "Måltidskasser")]
            + [(m[0]["kategori"]["sti"], m[0]["kategori"]["menunavn"]) for m in maanedsdata]
            + [("om/", "Om sitet")])

    if UD.exists():
        shutil.rmtree(UD)
    UD.mkdir()
    for navn in ["styles.css", "favicon.svg", "logo.svg", "CNAME"]:
        if (SRC / navn).exists():
            shutil.copy(SRC / navn, UD / navn)
    shutil.copytree(SRC / "fonts", UD / "fonts")

    alle_udbydere = data["udbydere"] + data.get("faerdigretter", [])
    for mdata, _ in maanedsdata:
        alle_udbydere += mdata["udbydere"]

    mad_opdateret = max(alle_kontroldatoer(beregninger))
    skriv("index.html", forside(data, beregninger, maanedsdata, opdateret))
    skriv(KATEGORI_STI + "index.html", kategoriside(data, beregninger, mad_opdateret))
    for mdata, mberegn in maanedsdata:
        mopdateret = max(kontroldatoer_maaned(mberegn))
        skriv(mdata["kategori"]["sti"] + "index.html", maanedsside(mdata, mberegn, mopdateret))
        datafiler_maaned(mdata, mberegn, mopdateret)
    skriv("om/index.html", omside(alle_udbydere))
    skriv("404.html", side404())
    datafiler(data, beregninger, mad_opdateret)
    maskinfiler(data, maanedsdata, opdateret)

    for u in data["udbydere"]:
        for p in kat["planer"]:
            b = beregninger[u["id"]][p["id"]]
            if b["status"] == "ukendt":
                print(f"  {u['navn']} {p['id']}: pris ukendt")
            else:
                foerste = "ukendt" if b["foerste"] is None else ("højst " if b["hoejst"] else "") + kr(b["foerste"])
                print(f"  {u['navn']} {p['id']}: første {foerste}, uge {kr(b['uge'])}, "
                      f"portion {kr(b['pr_portion'])}")
    for mdata, mberegn in maanedsdata:
        print(f"{mdata['kategori']['navn']}:")
        for u in mdata["udbydere"]:
            for p in mdata["kategori"]["planer"]:
                b = mberegn[u["id"]][p["id"]]
                if b is None:
                    continue
                if b["status"] == "ukendt":
                    print(f"  {u['navn']} {p['id']}: pris ukendt")
                    continue
                ca = "ca. " if b["omregnet"] else ""
                print(f"  {u['navn']} {p['id']}: første {ca}{kr(b['foerste'])}, kasse {ca}{kr(b['pr_kasse'])}, "
                      f"måned {ca}{kr(b['pr_maaned'])}")
    antal = len(data["udbydere"]) + sum(len(m[0]["udbydere"]) for m in maanedsdata)
    print(f"Bygget {antal} udbydere i {1 + len(maanedsdata)} kategorier, opdateret {opdateret}, i {UD}")


if __name__ == "__main__":
    main()
