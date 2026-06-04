"""Unified product category taxonomy for StyleQuote.

Maps raw (group, subcategory) tuples from 17 different suppliers into a single
Romanian-language taxonomy used by the storefront and search facets.

The mapping is intentionally keyword-based and order-sensitive: more specific
rules MUST come before more generic ones (e.g. "tricou polo" before "tricou").
"""
from __future__ import annotations

import re
import unicodedata


# ---------------------------------------------------------------------------
# Unified taxonomy
# ---------------------------------------------------------------------------

UNIFIED_TAXONOMY: dict[str, list[str]] = {
    "Textile": [
        "Tricouri",
        "Tricouri polo",
        "Tricouri maneca lunga",
        "Hanorace",
        "Pulovere si fleece",
        "Jachete",
        "Softshell",
        "Veste",
        "Camasi",
        "Pantaloni",
        "Pantaloni scurti",
        "Sorturi",
        "Sepci si palarii",
        "Imbracaminte sport",
        "Imbracaminte de lucru",
        "Imbracaminte reflectorizanta",
        "Sorturi bucatarie",
        "Incaltaminte",
        "Prosoape",
        "Accesorii vestimentare",
    ],
    "Pixuri si Birou": [
        "Pixuri metalice",
        "Pixuri plastic",
        "Pixuri ecologice",
        "Creioane si markere",
        "Seturi de scris",
        "Carnetele si agende",
        "Mape si dosare",
        "Accesorii birou",
        "Sticky notes",
        "Penare",
    ],
    "Drinkware": [
        "Cani",
        "Cani termice",
        "Termosuri",
        "Sticle apa",
        "Sticle sport",
        "Pahare",
        "Accesorii vin si bar",
        "Cutii pranz",
    ],
    "Genti si Calatorie": [
        "Rucsacuri",
        "Rucsacuri laptop",
        "Rucsacuri cu snur",
        "Genti shopping",
        "Genti sport",
        "Genti termoizolante",
        "Genti laptop",
        "Genti cosmetice",
        "Trolere si bagaje",
        "Portofele",
    ],
    "Tehnologie": [
        "Power banks",
        "USB sticks",
        "Casti si boxe",
        "Incarcatoare si cabluri",
        "Accesorii telefon",
        "Accesorii tehnologie",
    ],
    "Casa si Bucatarie": [
        "Accesorii bucatarie",
        "Lumanari",
        "Decoratiuni casa",
        "Patururi si textile casa",
    ],
    "Sport si Outdoor": [
        "Mingi si articole sport",
        "Articole fitness",
        "Articole plaja",
        "Articole camping",
        "Lanterne",
        "Unelte si cutite",
    ],
    "Brelocuri si Cadouri mici": [
        "Brelocuri",
        "Insigne si lanyarduri",
        "Reflectorizante",
        "Cadouri promotionale",
    ],
    "Umbrele": [
        "Umbrele",
        "Pelerine de ploaie",
    ],
    "Copii si Jocuri": [
        "Jucarii",
        "Jocuri",
        "Carti de colorat",
    ],
    "Sanatate si Frumusete": [
        "Cosmetice",
        "Articole sanatate",
        "Ingrijire personala",
    ],
    "Evenimente si Craciun": [
        "Articole Craciun",
        "Articole petrecere",
    ],
    "Auto si Siguranta": [
        "Accesorii auto",
        "Articole siguranta",
    ],
    "Diverse": [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_diacritics(s: str) -> str:
    nf = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nf if not unicodedata.combining(c))


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = _strip_diacritics(s).lower()
    # collapse non-alnum to single space, with leading/trailing spaces so
    # we can do simple word-boundary checks via " kw " in " text ".
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return f" {s.strip()} "


def _has(text: str, *keywords: str) -> bool:
    """True if any keyword (whole word/phrase) appears in text as a whole word.

    text MUST already be normalised by _norm (so it has surrounding spaces).
    Strict word-boundary matching: "pen" will NOT match "pendrive" or "pencil".
    For plural forms, callers should pass both singular and plural explicitly.
    """
    for kw in keywords:
        k = _strip_diacritics(kw).lower()
        k = re.sub(r"[^a-z0-9]+", " ", k).strip()
        if not k:
            continue
        if f" {k} " in text:
            return True
    return False


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

def map_to_unified(supplier: str, raw_group: str, raw_subcategory: str) -> tuple[str, str]:
    """Map a raw supplier (group, subcategory) to a unified (category, subcategory).

    Returns ("Diverse", <original sub or "Altele">) when no rule matches.
    """
    supplier = (supplier or "").upper()
    g = _norm(raw_group)
    s = _norm(raw_subcategory)
    t = g + s  # combined search space

    # ── TEXTILE ────────────────────────────────────────────────────────────
    # Most specific first.
    if _has(t, "polo", "polos", "polo shirt", "polo shirts", "tricou polo", "tricouri polo"):
        return ("Textile", "Tricouri polo")
    if _has(t, "long sleeve", "maneca lunga", "long sleeves"):
        return ("Textile", "Tricouri maneca lunga")
    if _has(t, "hanorac", "hanorace", "sweatshirt", "sweatshirts", "sweats", "sweater", "pulover", "pulovar", "pulovere", "pullover", "pullovers", "knitwear"):
        # hanorace vs pulovere — keep hanorac when explicit, else pulovere
        if _has(t, "hanorac", "hanorace", "hooded", "hoodie", "gluga"):
            return ("Textile", "Hanorace")
        return ("Textile", "Pulovere si fleece")
    if _has(t, "fleece", "polar"):
        return ("Textile", "Pulovere si fleece")
    if _has(t, "softshell", "softshells", "soft shell"):
        return ("Textile", "Softshell")
    if _has(t, "geaca", "geci", "jacheta", "jachete", "jacket", "jackets", "coat", "coats", "outerwear", "duvet", "duvets", "windproof", "iarna", "winter"):
        return ("Textile", "Jachete")
    if _has(t, "vesta", "veste", "vest", "vests"):
        return ("Textile", "Veste")
    if _has(t, "camasa", "camasi", "shirt", "shirts") and not _has(t, "tshirt", "t shirt"):
        # 'shirt' alone — only treat as camasa if not part of tshirt
        return ("Textile", "Camasi")
    if _has(t, "tricou", "tricouri", "tshirt", "t shirt", "tshirts", "tee", "tees", "maiou", "maiouri", "tank top"):
        return ("Textile", "Tricouri")
    if _has(t, "pantaloni scurti", "pantalon scurt", "shorts", "short pant"):
        return ("Textile", "Pantaloni scurti")
    if _has(t, "pantaloni", "pants", "trousers", "waist pants"):
        return ("Textile", "Pantaloni")
    if _has(t, "sapca", "sepci", "cap", "caps", "hat", "hats", "headwear", "beanie", "panama"):
        return ("Textile", "Sepci si palarii")
    if _has(t, "workwear", "work wear", "imbracaminte de lucru", "lucru", "vesta de lucru", "ospitalitate"):
        return ("Textile", "Imbracaminte de lucru")
    if _has(t, "hi vis", "hivis", "reflective wear", "reflectorizant"):
        return ("Textile", "Imbracaminte reflectorizanta")
    if _has(t, "sport collection", "sportwear", "sportswear", "imbracaminte sport", "echipamente", "trening", "treninguri"):
        return ("Textile", "Imbracaminte sport")
    if _has(t, "sort bucatarie", "apron", "aprons", "smock"):
        return ("Textile", "Sorturi bucatarie")
    if _has(t, "incaltaminte", "footwear", "shoes", "boots"):
        return ("Textile", "Incaltaminte")
    if _has(t, "prosop", "prosoape", "towel", "towels"):
        return ("Textile", "Prosoape")
    if _has(t, "ochelari", "sunglasses", "manusi", "fular", "fulare", "esarfa", "scarf", "gloves"):
        return ("Textile", "Accesorii vestimentare")
    if _has(t, "bucket", "palarii de paie", "palarie", "palarii"):
        return ("Textile", "Sepci si palarii")
    if _has(t, "outlet", "noutati", "new arrivals", "novelties", "specials", "name it", "impression", "noutati", "creabox", "creapack"):
        return ("Brelocuri si Cadouri mici", "Cadouri promotionale")
    if supplier == "XDCONNECTS" and _has(t, "textile"):
        return ("Textile", "Tricouri")
    if supplier == "MAKITO" and _has(t, "textile"):
        return ("Textile", "Tricouri")
    if _has(t, "sols", "sol s"):
        return ("Textile", "Tricouri")
    if _has(t, "baseballcap", "baseballcaps", "baseball cap", "baseball caps"):
        return ("Textile", "Sepci si palarii")
    if _has(t, "chapeus", "panamas", "panama"):
        return ("Textile", "Sepci si palarii")
    if _has(t, "raincoat", "raincoats"):
        return ("Umbrele", "Pelerine de ploaie")
    if _has(t, "work overalls", "overalls", "halat", "halate", "salopeta", "salopete", "cloak", "cloaks", "protectia muncii"):
        return ("Textile", "Imbracaminte de lucru")
    if _has(t, "sort", "sorturi", "sortulet", "sortulete") and _has(t, "bucatarie", "alimentare", "produse alimentare"):
        return ("Textile", "Sorturi bucatarie")
    if _has(t, "fashion accessories", "fashion accessory", "scarves", "echarpes", "curea", "curele", "belt", "belts"):
        return ("Textile", "Accesorii vestimentare")
    if _has(t, "costum de baie", "costume de baie", "swimwear", "swim"):
        return ("Sport si Outdoor", "Articole plaja")
    if _has(t, "fotbal", "football", "soccer"):
        return ("Sport si Outdoor", "Mingi si articole sport")
    if _has(t, "magnet", "magneti"):
        return ("Brelocuri si Cadouri mici", "Cadouri promotionale")
    if _has(t, "caserol", "caserole", "cutii depozitare", "depozitare"):
        return ("Casa si Bucatarie", "Accesorii bucatarie")

    # ── PIXURI SI BIROU ────────────────────────────────────────────────────
    # Order matters: specific subtypes BEFORE generic pen fallback.
    # USB drives that contain "pen" as in "pen drives" must NOT match pen rules.
    if _has(t, "usb stick", "usb sticks", "usb memory", "pendrive", "pendriveuri", "pendrives", "memory stick", "pen drive", "pen drives", "udp pen drives", "usb stock"):
        return ("Tehnologie", "USB sticks")

    # Pencils, mechanical pencils, crayons, colored pencils — keep separate from pens.
    if _has(t, "creion", "creioane", "creion mecanic", "creioane mecanice", "creioane colorate",
            "creioane grafit", "creioane cerate", "pencil", "pencils", "mechanical pencil",
            "mechanical pencils", "colouring pencils", "coloring pencils", "crayon", "crayons",
            "pencils and rulers", "pencils and chalks", "creioane si crete",
            "pencils and mechanical pencils", "pastels and drawing", "pastel", "pastels",
            "chalk", "chalks", "crete"):
        return ("Pixuri si Birou", "Creioane si markere")
    if _has(t, "highlighter", "highlighters", "higlighter", "higlighters", "evidentiator",
            "evidentiatoare", "evidentatoare", "text marker", "text markers", "marker",
            "markere", "markers"):
        return ("Pixuri si Birou", "Creioane si markere")
    # Pen pouches / cases / etui pixuri / suporturi pixuri → penare
    if _has(t, "penar", "penare", "pencil case", "pencil cases", "pen pouch", "pen pouches",
            "etui pixuri", "etui pentru pixuri", "suport pixuri", "suporturi pentru pixuri",
            "cases and pouches", "writing cases and pouches"):
        return ("Pixuri si Birou", "Penare")
    # Writing/stationery/pen sets — must come before generic pen fallback
    if _has(t, "writing set", "writing sets", "writting set", "writting sets",
            "stationery set", "stationery sets", "set de scris", "seturi de scris",
            "seturi de scris cadou", "seturi de pixuri", "pen set", "pen sets",
            "pen sets and pen holders", "writting sets and cases",
            "writing writing sets"):
        return ("Pixuri si Birou", "Seturi de scris")
    # ECO pens (wood, bamboo, recycled) — MUST come before generic pen fallback.
    if _has(t, "pixuri ecologice", "pixuri eco", "pixuri din lemn", "pixuri din bambus",
            "pixuri lemn bambus", "pixuri din lemn bambus", "eco pen", "eco pens",
            "eco friendly pen", "eco friendly pens", "ecological pen", "ecological pens",
            "ecological ball pens", "ecologic ball pens", "ecologic pens",
            "eco wooden pens", "eco and wooden pens", "eco wooden pen",
            "wooden pen", "wooden pens", "bamboo pen", "bamboo pens",
            "eco style pen", "eco style pens", "recycled pen", "recycled pens",
            "cardboard pen", "cardboard pens", "paper pen", "paper pens",
            "seed pen", "seed pens", "r abs pen", "recycled abs pen", "recycled abs pens"):
        return ("Pixuri si Birou", "Pixuri ecologice")
    # Plastic pens — note "plastic and metal" prefers plastic.
    if _has(t, "plastic pen", "plastic pens", "pixuri plastic", "pixuri din plastic",
            "plastic ball pen", "plastic ball pens", "plastic and metal ball pens",
            "pen abs", "abs pen", "abs pens"):
        return ("Pixuri si Birou", "Pixuri plastic")
    # Metal / aluminium / stylus / luxury / fountain / multifunction / roller / lid metal pens
    if _has(t, "metal pen", "metal pens", "metal ball pen", "metal ball pens",
            "metallstifte", "metall stifte", "pixuri din metal", "pixuri metal",
            "pixuri metalice", "pixuri din metal aluminiu", "pixuri aluminiu",
            "pix metalic", "aluminium pen", "aluminium pens", "aluminum pen",
            "aluminum pens", "luxury pen", "luxury pens", "fountain pen", "fountain pens",
            "roller pen", "roller pens", "rollerball", "metal rollers",
            "ball pens with lid", "ball pens with roller", "ball pens lid roller",
            "multifunction pen", "multifunction pens", "pixuri multifunctionale",
            "pixuri fara cerneala", "pixuri multicolore",
            "stylus pen", "stylus pens", "pixuri stylus", "pixuri cu touch",
            "pixuri touchscreen", "touch pen", "touch pens", "pen with stylus",
            "pens with touchscreen stylus"):
        return ("Pixuri si Birou", "Pixuri metalice")
    # Generic pen fallback → metalice (default).
    if _has(t, "pix", "pixuri", "pen", "pens", "ball pen", "ball pens", "ballpen", "ballpens",
            "pixuri cu bila", "writing", "writings", "writing instruments",
            "instrumente de scris", "boligrafos"):
        return ("Pixuri si Birou", "Pixuri metalice")

    # Notebooks / agendas / blocnotes
    if _has(t, "carnetel", "carnetele", "notebook", "notebooks", "notepad", "notepads",
            "agenda", "agende", "agendas", "block note", "block notes", "blocnotes",
            "blocnotesuri", "bloc notite", "blocuri de notite", "caiet", "caiete",
            "hard cover", "soft cover", "coperta tare", "coperta moale", "diary", "diaries",
            "diaries and notepads", "notebooks and folders", "notebooks and block notes",
            "portfolios and notebooks", "carnete de birou", "carnete", "legat cu inele",
            "spirala"):
        return ("Pixuri si Birou", "Carnetele si agende")
    # Sticky notes / memo / blocnotes adezive
    if _has(t, "sticky note", "sticky notes", "post it", "memo holder", "memo holders",
            "notite adezive", "notite cu adeziv", "blocuri de notite si notite adezive",
            "blocnotesuri notite cu adeziv", "blocnotesuri si notite cu adeziv"):
        return ("Pixuri si Birou", "Sticky notes")
    # Mape / folders / portfolios / document bags / conference folders
    if _has(t, "mape", "mapa", "folder", "folders", "document bag", "document bags",
            "document folder", "document folders", "portfolio", "portfolios",
            "conference folder", "conference folders", "mape de conferinta",
            "mape documente", "port documente", "port-documente", "dosare inteligente",
            "folders and document bag", "folders and document bags",
            "pc tablet folders and pouches", "pc tablet folders pouches"):
        return ("Pixuri si Birou", "Mape si dosare")
    # Office accessories — broad bucket: rulers, bookmarks, calculators, clocks, lamps,
    # business card holders, mousepads, hubs, gift sets, trofee, paper cutters
    if _has(t, "office", "birou", "birotica", "desk equipment", "desktop accessories",
            "office accessories", "office and business", "stationery", "stationery sets",
            "articole de birou", "accesorii birou", "ruler", "rulers", "rigla", "rigle",
            "bookmark", "bookmarks", "semne de carte", "ruler bookmark",
            "calculator", "calculators", "calculatoare", "clock", "clocks",
            "ceas de birou", "ceasuri de birou", "ceasuri birou", "ceasuri perete",
            "ceasuri si calculatoare", "calculators and clocks",
            "lampa de birou", "lampi de birou", "lampi de masa", "desk lamp", "desk lamps",
            "office lamps",
            "business card holder", "business card holders", "card holder", "card holders",
            "credit card holder", "credit card holders", "suport carti de vizita",
            "suporturi carti de vizita", "wallet", "wallets", "wallets card cases",
            "card case", "card cases", "wallets and card holders",
            "mousepad", "mousepad uri", "mousepaduri", "mouse pad", "hub", "hub uri",
            "hub-uri", "hubs", "magnifying glass", "magnifying glasses",
            "trofee", "trofeu", "awards", "trofee si greutati", "paperweight",
            "paper cutter", "paper cutters", "cutter", "cuttere",
            "clipsuri", "clipsuri notite", "planseta", "planset",
            "office supplies", "office supply", "refills", "refill",
            "stations meteorologice", "statii meteorologice",
            "computer accessories", "pc accessories",
            "seturi combinate", "blocnotesuri si notite", "accesorii si cutii",
            "memo holder", "memo holders", "menu holder", "menus and bill holders",
            "gift set", "gift sets"):
        return ("Pixuri si Birou", "Accesorii birou")

    # ── DRINKWARE ──────────────────────────────────────────────────────────
    if _has(t, "thermos", "termos", "termosuri", "thermo mug", "thermo mugs", "thermal bottle", "thermal bottles", "sticle termice", "sticle termice si termosuri", "thermal bottles and thermos", "flask", "flasks"):
        if _has(t, "mug", "cana", "cani", "cup"):
            return ("Drinkware", "Cani termice")
        return ("Drinkware", "Termosuri")
    if _has(t, "double walled", "perete dublu", "cana cu perete dublu", "cani cu perete dublu"):
        return ("Drinkware", "Cani termice")
    if _has(t, "sport bottle", "sport bottles", "sticle sport", "sticle de apa si sport", "waterbottle", "waterbottles"):
        return ("Drinkware", "Sticle sport")
    if _has(t, "bottle", "bottles", "sticla", "sticle", "drinking bottle", "drinking bottles", "sticle de baut"):
        return ("Drinkware", "Sticle apa")
    if _has(t, "mug", "mugs", "cana", "cani", "ceramic mug", "ceramic mugs", "cup", "cups"):
        return ("Drinkware", "Cani")
    if _has(t, "pahar", "pahare", "glass", "glasses", "tumbler"):
        return ("Drinkware", "Pahare")
    if _has(t, "wine", "vin", "bar accessor", "wine accessor", "alcohol accessor", "wine and cheese"):
        return ("Drinkware", "Accesorii vin si bar")
    if _has(t, "lunch box", "cutie de pranz", "cutii de pranz", "lunch"):
        return ("Drinkware", "Cutii pranz")
    if _has(t, "drinkware", "take away", "drink to go"):
        return ("Drinkware", "Cani")
    if _has(t, "espresor", "espressor", "espresoare", "espressoare", "capsule", "tea infuser",
            "infuzor ceai", "infuzor de ceai", "coffee accessor", "accesorii cafea",
            "accesorii cafea ceai", "cesti de cafea", "cesti cafea", "coffee cup",
            "coffee cups", "cesti", "cup warmer"):
        return ("Drinkware", "Cani")
    if _has(t, "drinking straw", "drinking straws", "paie", "straw", "straws"):
        return ("Drinkware", "Accesorii vin si bar")
    if _has(t, "alcohol accessor", "alcohol accessories", "bar accessor",
            "drinks bar accessories", "cocktail", "accesorii cocktail",
            "hip flask", "plosca", "plosca metalica", "carafa"):
        return ("Drinkware", "Accesorii vin si bar")
    if _has(t, "sets and drinking accessories", "seturi si accesori pentru baut",
            "seturi accesori pentru baut", "drinking accessories"):
        return ("Drinkware", "Accesorii vin si bar")

    # ── GENTI SI CALATORIE ─────────────────────────────────────────────────
    if _has(t, "rucsac laptop", "laptop backpack", "pc tablet backpack", "pc tablet backpacks", "rucsacuri pentru laptop"):
        return ("Genti si Calatorie", "Rucsacuri laptop")
    if _has(t, "drawstring", "rucsac cu snur", "rucsacuri drawstring", "cu cordon", "genti cu cordon"):
        return ("Genti si Calatorie", "Rucsacuri cu snur")
    if _has(t, "rucsac", "rucsaci", "rucsacuri", "backpack", "backpacks", "rucksack", "rucksacks"):
        return ("Genti si Calatorie", "Rucsacuri")
    if _has(t, "thermal bag", "thermal bags", "cooler bag", "cooler bags", "geanta termo", "genti termoizolante", "genti termizolante", "genti frigorifice", "frigorific"):
        return ("Genti si Calatorie", "Genti termoizolante")
    if _has(t, "sport bag", "sport bags", "geanta sport"):
        return ("Genti si Calatorie", "Genti sport")
    if _has(t, "geanta laptop", "genti laptop", "computer rucksack", "laptop bag"):
        return ("Genti si Calatorie", "Genti laptop")
    if _has(t, "cosmetic", "cosmetice", "beauty case", "geanta de toaleta", "toiletry", "geanta pentru cosmetice", "personal care bag", "genti pentru cosmetice"):
        return ("Genti si Calatorie", "Genti cosmetice")
    if _has(t, "shopping bag", "shopping bags", "sacosa", "sacose", "shopper", "tote", "cotton bag", "cotton bags", "non woven", "grocery bag", "eco bag", "eco friendly bag", "genti eco", "sacose de cumparaturi"):
        return ("Genti si Calatorie", "Genti shopping")
    if _has(t, "trole", "trolere", "luggage", "suitcase", "bagaj", "bagaje"):
        return ("Genti si Calatorie", "Trolere si bagaje")
    if _has(t, "portofel", "portofele", "wallet", "borseta", "borsete"):
        return ("Genti si Calatorie", "Portofele")
    if _has(t, "travel", "calatorie", "calatorii", "voiaj", "bags travel", "bags and travel"):
        return ("Genti si Calatorie", "Rucsacuri")
    if _has(t, "geanta", "genti", "bag", "bags"):
        return ("Genti si Calatorie", "Genti shopping")

    # ── TEHNOLOGIE ─────────────────────────────────────────────────────────
    if _has(t, "power bank", "powerbank", "powerbanks"):
        return ("Tehnologie", "Power banks")
    if _has(t, "usb stick", "usb sticks", "usb memory", "pendrive", "pendriveuri", "pendrives", "memory stick"):
        return ("Tehnologie", "USB sticks")
    if _has(t, "headset", "headsets", "earphone", "earphones", "casti", "speaker", "boxa", "boxe", "audio"):
        return ("Tehnologie", "Casti si boxe")
    if _has(t, "charger", "chargers", "incarcator", "incarcatoare", "cable", "cables", "charging cable"):
        return ("Tehnologie", "Incarcatoare si cabluri")
    if _has(t, "phone case", "huse pentru telefon", "huse telefon", "phone tablet", "phone and tablet", "tablet accessor"):
        return ("Tehnologie", "Accesorii telefon")
    if _has(t, "headphone", "headphones"):
        return ("Tehnologie", "Casti si boxe")
    if _has(t, "speaker", "speakers"):
        return ("Tehnologie", "Casti si boxe")
    if _has(t, "wireless charging", "wireless charger", "wireless chargers", "inductie", "induction charger"):
        return ("Tehnologie", "Incarcatoare si cabluri")
    if _has(t, "huse pentru smartphone", "huse smartphone", "smartphone case", "smartphone cases"):
        return ("Tehnologie", "Accesorii telefon")
    if _has(t, "tehnologie", "technology", "electronic", "electronice", "electronics", "accesorii tehnologice", "it accesorii", "accesorii it"):
        return ("Tehnologie", "Accesorii tehnologie")

    # ── BRELOCURI / CADOURI MICI ───────────────────────────────────────────
    if _has(t, "brelocuri", "breloc", "keychain", "keychains", "key chain", "key chains", "key ring", "keyring"):
        return ("Brelocuri si Cadouri mici", "Brelocuri")
    if _has(t, "lanyard", "lanyarduri", "ecuson", "ecusoane", "badge", "identification", "insigna", "insigne"):
        return ("Brelocuri si Cadouri mici", "Insigne si lanyarduri")
    if _has(t, "reflective", "reflectives", "reflectorizant"):
        return ("Brelocuri si Cadouri mici", "Reflectorizante")
    if _has(t, "giveaway", "giveaways", "gifts and premium", "promotional", "promotionale", "materiale promo", "sublimation"):
        return ("Brelocuri si Cadouri mici", "Cadouri promotionale")

    # ── UMBRELE ────────────────────────────────────────────────────────────
    if _has(t, "umbrela", "umbrele", "umbrella", "umbrellas"):
        return ("Umbrele", "Umbrele")
    if _has(t, "pelerina", "pelerine", "raincoat", "rain coat", "rain and cold", "pelerine de ploaie", "rainwear", "imbracaminte de ploaie"):
        return ("Umbrele", "Pelerine de ploaie")

    # ── COPII SI JOCURI ────────────────────────────────────────────────────
    if _has(t, "stuffed animal", "stuffed animals", "plush", "plus", "jucarii de plus"):
        return ("Copii si Jocuri", "Jucarii")
    if _has(t, "jucarii", "jucarie", "toy", "toys"):
        return ("Copii si Jocuri", "Jucarii")
    if _has(t, "jocuri", "joc", "game", "games"):
        return ("Copii si Jocuri", "Jocuri")
    if _has(t, "carti de colorat", "coloring", "colouring"):
        return ("Copii si Jocuri", "Carti de colorat")
    if _has(t, "kids", "copii", "children"):
        return ("Copii si Jocuri", "Jucarii")

    # ── SANATATE & FRUMUSETE ───────────────────────────────────────────────
    if _has(t, "lip balm", "balsam de buze", "balsamuri de buze"):
        return ("Sanatate si Frumusete", "Cosmetice")
    if _has(t, "personal care", "ingrijire personala", "ingrijire", "pharma", "personal care and pharma"):
        return ("Sanatate si Frumusete", "Ingrijire personala")
    if _has(t, "sanatate", "health", "healthy living", "vitalitate"):
        return ("Sanatate si Frumusete", "Articole sanatate")
    if _has(t, "cosmetic", "cosmetice", "beauty"):
        return ("Sanatate si Frumusete", "Cosmetice")

    # ── SPORT SI OUTDOOR ───────────────────────────────────────────────────
    if _has(t, "minge", "mingi", "ball", "balls"):
        return ("Sport si Outdoor", "Mingi si articole sport")
    if _has(t, "fitness", "yoga", "gym"):
        return ("Sport si Outdoor", "Articole fitness")
    if _has(t, "plaja", "beach", "summer and beach", "summer"):
        return ("Sport si Outdoor", "Articole plaja")
    if _has(t, "camping", "outdoor", "adventure", "sport and adventure"):
        return ("Sport si Outdoor", "Articole camping")
    if _has(t, "lanterna", "lanterne", "torch", "torches", "flashlight", "flashlights", "lights and torches"):
        return ("Sport si Outdoor", "Lanterne")
    if _has(t, "tool", "tools", "unelte", "unealta", "knife", "knives", "multitool", "multitools", "pocket knife", "pocket knives", "tape measure", "tape measures", "instrumente"):
        return ("Sport si Outdoor", "Unelte si cutite")
    if _has(t, "biking", "bicicleta", "biciclete", "bike", "bicycle", "accesorii pentru biciclete", "cycling"):
        return ("Sport si Outdoor", "Articole camping")
    if _has(t, "hiking", "drumetii", "alergare", "running", "trekking", "accesorii pentru alergare si drumetii"):
        return ("Sport si Outdoor", "Articole camping")
    if _has(t, "hamac", "hamace", "hammock", "hammocks", "hamace si scaune", "covorase pentru scaune"):
        return ("Sport si Outdoor", "Articole camping")
    if _has(t, "sport", "sport accessories", "leisure", "timp liber"):
        return ("Sport si Outdoor", "Mingi si articole sport")

    # ── CASA SI BUCATARIE ──────────────────────────────────────────────────
    if _has(t, "kitchen", "bucatarie", "kitchen accessor", "kitchen equipment", "eating", "dining", "eating dining"):
        return ("Casa si Bucatarie", "Accesorii bucatarie")
    if _has(t, "candle", "candles", "lumanare", "lumanari"):
        return ("Casa si Bucatarie", "Lumanari")
    if _has(t, "home", "casa", "decoration", "decoratiuni", "home and living", "home and decoration", "home and garden", "garden"):
        return ("Casa si Bucatarie", "Decoratiuni casa")
    if _has(t, "patura", "paturi", "patur", "blanket", "blankets"):
        return ("Casa si Bucatarie", "Patururi si textile casa")
    if _has(t, "tocator", "tocatoare", "cutting board", "chopping board", "placa lemn",
            "tacam", "tacamuri", "cutlery", "fiambreras", "lunch box", "lunchbox",
            "containers", "depozitare alimente", "food container", "food containers",
            "solnite", "sare si piper", "salt and pepper", "salt pepper",
            "grill accessor", "gratar", "barbecue", "bbq", "accesorii bbq",
            "kitchen accessor", "kitchen equipment"):
        return ("Casa si Bucatarie", "Accesorii bucatarie")
    if _has(t, "fridge magnet", "fridge magnets", "magnet de frigider", "magneti de frigider"):
        return ("Casa si Bucatarie", "Decoratiuni casa")

    # ── EVENIMENTE / CRACIUN ───────────────────────────────────────────────
    if _has(t, "christmas", "craciun", "ornament", "ornaments"):
        return ("Evenimente si Craciun", "Articole Craciun")
    if _has(t, "petrecere", "petreceri", "party", "events", "evenimente", "evantai", "evantaie", "esarfe", "panglica", "panglici", "fan"):
        return ("Evenimente si Craciun", "Articole petrecere")

    # ── AUTO / SIGURANTA ───────────────────────────────────────────────────
    if _has(t, "car", "auto", "car and safety"):
        return ("Auto si Siguranta", "Accesorii auto")
    if _has(t, "safety", "siguranta", "visibility", "visibilitate", "antibacterial", "hand gel", "sanitizer", "dezinfectant", "hygienic protection", "protectie igienica", "masks and mask holders", "masca", "first aid", "prim ajutor", "saturimeters", "thermometer", "termometru"):
        return ("Sanatate si Frumusete", "Articole sanatate")

    # ── DEFAULT ────────────────────────────────────────────────────────────
    return ("Diverse", (raw_subcategory or raw_group or "Altele").strip() or "Altele")


def apply_unified_category(product_dict: dict) -> None:
    """Mutate product_dict to add unified_category/unified_subcategory."""
    cat, sub = map_to_unified(
        product_dict.get("category", ""),
        product_dict.get("category_group", ""),
        product_dict.get("subcategory", ""),
    )
    product_dict["unified_category"] = cat
    product_dict["unified_subcategory"] = sub


# ---------------------------------------------------------------------------
# Self-test / coverage report
# ---------------------------------------------------------------------------

def _run_coverage_report() -> None:
    import json
    import os
    import sys
    from collections import Counter, defaultdict

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    here = os.path.dirname(os.path.abspath(__file__))
    # Walk up to repo root: backend/app/services -> backend/app -> backend -> repo
    candidate = os.path.normpath(os.path.join(here, "..", "..", "..", "all_categories.json"))

    with open(candidate, encoding="utf-8") as f:
        data = json.load(f)

    total_products = 0
    matched_products = 0
    total_entries = 0
    matched_entries = 0
    cat_counter: Counter[str] = Counter()
    sub_counter: Counter[tuple[str, str]] = Counter()
    unmatched: list[tuple[str, str, str, int]] = []
    per_supplier: dict[str, dict[str, int]] = defaultdict(lambda: {"matched": 0, "total": 0})

    for supplier, items in data.items():
        for it in items:
            grp = it.get("group") or ""
            sub = it.get("sub") or ""
            cnt = int(it.get("cnt") or 0)
            total_entries += 1
            total_products += cnt
            cat, ucat_sub = map_to_unified(supplier, grp, sub)
            cat_counter[cat] += cnt
            sub_counter[(cat, ucat_sub)] += cnt
            per_supplier[supplier]["total"] += cnt
            if cat != "Diverse":
                matched_products += cnt
                matched_entries += 1
                per_supplier[supplier]["matched"] += cnt
            else:
                unmatched.append((supplier, grp, sub, cnt))

    print("=" * 70)
    print("STYLEQUOTE UNIFIED TAXONOMY — COVERAGE REPORT")
    print("=" * 70)
    print(f"Total entries:  {total_entries}")
    print(f"Total products: {total_products}")
    pct_p = (matched_products / total_products * 100) if total_products else 0
    pct_e = (matched_entries / total_entries * 100) if total_entries else 0
    print(f"Matched entries:  {matched_entries} ({pct_e:.1f}%)")
    print(f"Matched products: {matched_products} ({pct_p:.1f}%)")
    print()
    print("── Distribution per unified top-level category ──")
    for cat, cnt in cat_counter.most_common():
        pct = cnt / total_products * 100 if total_products else 0
        print(f"  {cat:<32} {cnt:>8}  ({pct:5.1f}%)")
    print()
    print("── Per-supplier coverage ──")
    for sup in sorted(per_supplier):
        m = per_supplier[sup]["matched"]
        t = per_supplier[sup]["total"]
        pct = (m / t * 100) if t else 0
        print(f"  {sup:<16} {m:>7}/{t:<7} ({pct:5.1f}%)")
    print()
    print("── Top 20 unmatched (supplier, group, sub, count) ──")
    unmatched.sort(key=lambda x: -x[3])
    for sup, grp, sub, cnt in unmatched[:20]:
        print(f"  [{cnt:>5}] {sup:<14} | {grp[:40]:<40} | {sub[:40]}")
    print()
    print("── Top 30 unified subcategories by product count ──")
    for (cat, sub), cnt in sub_counter.most_common(30):
        print(f"  {cnt:>7}  {cat} → {sub}")


if __name__ == "__main__":
    _run_coverage_report()
