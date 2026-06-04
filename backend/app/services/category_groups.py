"""
Category group mappings for each supplier.

Maps individual subcategories to broader category groups,
matching the structure shown on supplier websites (e.g., EasyGifts, MACMA).
"""

# EASYGIFTS: Romanian subcategories → broad groups
EASYGIFTS_GROUPS: dict[str, str] = {
    # PRODUSE TEXTILE
    "Tricou": "PRODUSE TEXTILE",
    "Pulovar": "PRODUSE TEXTILE",
    "Tricou polo": "PRODUSE TEXTILE",
    "Polar": "PRODUSE TEXTILE",
    "Geaca": "PRODUSE TEXTILE",
    "Vesta": "PRODUSE TEXTILE",
    "Softshell": "PRODUSE TEXTILE",
    "Tricou cu maneca lunga": "PRODUSE TEXTILE",
    "Camasa": "PRODUSE TEXTILE",
    "Pantaloni": "PRODUSE TEXTILE",
    "Pantaloni cu talie inalta": "PRODUSE TEXTILE",
    "Prosop": "PRODUSE TEXTILE",
    "Imbracaminte sport": "PRODUSE TEXTILE",
    "Vesta de lucru": "PRODUSE TEXTILE",
    "Geaca de lucru": "PRODUSE TEXTILE",
    "Sepci baseball": "PRODUSE TEXTILE",
    "Sapca": "PRODUSE TEXTILE",
    "Imbracaminte si accesorii protectia muncii": "PRODUSE TEXTILE",
    "Tricou polo de lucru": "PRODUSE TEXTILE",
    "Pulovar de lucru": "PRODUSE TEXTILE",
    "Pelerine de ploaie": "PRODUSE TEXTILE",
    "Salopeta": "PRODUSE TEXTILE",
    "Pantaloni scurti": "PRODUSE TEXTILE",
    "Halat": "PRODUSE TEXTILE",
    # GENTI, CALATORII, WELLNESS
    "Genti Eco": "GENTI, CALATORII, WELLNESS",
    "Rucsaci si genti umar": "GENTI, CALATORII, WELLNESS",
    "Geanta sport": "GENTI, CALATORII, WELLNESS",
    "Accesorii pentru calatorii": "GENTI, CALATORII, WELLNESS",
    "Genti pentru cumparaturi, sacose": "GENTI, CALATORII, WELLNESS",
    "Geanta frigorifica": "GENTI, CALATORII, WELLNESS",
    "Genti sport si calatorii": "GENTI, CALATORII, WELLNESS",
    "Geanta documente, geanta laptop": "GENTI, CALATORII, WELLNESS",
    "Borseta": "GENTI, CALATORII, WELLNESS",
    "Genti rezistent la apa": "GENTI, CALATORII, WELLNESS",
    "Accesorii cosmetice": "GENTI, CALATORII, WELLNESS",
    # DRINK TO GO
    "Sticle de baut": "DRINK TO GO",
    "Termosuri si cani termos": "DRINK TO GO",
    "Cani, pahare, carafe": "DRINK TO GO",
    "Seturi si accesori pentru baut": "DRINK TO GO",
    "Plosca metalica": "DRINK TO GO",
    "Dozatoare de băuturi": "DRINK TO GO",
    "Vin, bar": "DRINK TO GO",
    # ELECTRONICE SI ACCESORII
    "Pendriveuri": "ELECTRONICE SI ACCESORII",
    "Powerbankuri": "ELECTRONICE SI ACCESORII",
    "Accesorii mobil": "ELECTRONICE SI ACCESORII",
    "Difuzoare": "ELECTRONICE SI ACCESORII",
    "Încărcătoare wireless": "ELECTRONICE SI ACCESORII",
    "Căști": "ELECTRONICE SI ACCESORII",
    "Laserpointere": "ELECTRONICE SI ACCESORII",
    # PIXURI SI INSTRUMENTE DE SCRIS
    "Pixuri si instrumente de scris din metal": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Pixuri din plastic": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Pixuri ecologice": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Creioane si crete": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Seturi de scris si penare": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Markere": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Pixuri touchscreen": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Cuttere": "PIXURI SI INSTRUMENTE DE SCRIS",
    # BIROU SI CEASURI
    "Caiete de notite, mape": "BIROU SI CEASURI",
    "Calculatoare si ceasuri": "BIROU SI CEASURI",
    "Suport carti de vizita": "BIROU SI CEASURI",
    "Accesorii birou": "BIROU SI CEASURI",
    # BRELOCURI SI ALTELE
    "Brelocuri": "BRELOCURI SI ALTELE",
    "Deschizătoare sticlă": "BRELOCURI SI ALTELE",
    "Brichete": "BRELOCURI SI ALTELE",
    "Accesorii": "BRELOCURI SI ALTELE",
    "Accesorii auto": "BRELOCURI SI ALTELE",
    "Accesorii de securitate": "BRELOCURI SI ALTELE",
    "Trofee și greuatți de hartie": "BRELOCURI SI ALTELE",
    "Pușculițe": "BRELOCURI SI ALTELE",
    # TIMP LIBER, SPORT SI JUCARII
    "Jucarii": "TIMP LIBER, SPORT SI JUCARII",
    "Accesorii plaja": "TIMP LIBER, SPORT SI JUCARII",
    "Barbecue, picnic și outdoor": "TIMP LIBER, SPORT SI JUCARII",
    "Accesorii sport si fitness": "TIMP LIBER, SPORT SI JUCARII",
    "Ochelari de soare": "TIMP LIBER, SPORT SI JUCARII",
    "Accesorii de bicicleta": "TIMP LIBER, SPORT SI JUCARII",
    # UNELTE SI LANTERNE
    "Cutite de buzunar, briceaguri": "UNELTE SI LANTERNE",
    "Multitooluri": "UNELTE SI LANTERNE",
    "Lanterne de buzunar": "UNELTE SI LANTERNE",
    "Rulete": "UNELTE SI LANTERNE",
    # UMBRELE SI PELERINE DE PLOAIE
    "Umbrele": "UMBRELE SI PELERINE DE PLOAIE",
    # PENTRU CASA SI BUCATARIE
    "Accesorii bucătărie": "PENTRU CASA SI BUCATARIE",
    "Accesorii pentru casă": "PENTRU CASA SI BUCATARIE",
    "Caserole, cutii pentru mâncare": "PENTRU CASA SI BUCATARIE",
    "Cuțite și tocătoare": "PENTRU CASA SI BUCATARIE",
    "Solniță și piperniță": "PENTRU CASA SI BUCATARIE",
    "Pentru casă și bucătărie": "PENTRU CASA SI BUCATARIE",
}

# MACMA: English subcategories → broad groups
MACMA_GROUPS: dict[str, str] = {
    # TEXTILE PRODUCTS
    "T-Shirt": "PRODUSE TEXTILE",
    "Sweater": "PRODUSE TEXTILE",
    "Polos": "PRODUSE TEXTILE",
    "Polar": "PRODUSE TEXTILE",
    "Softshell": "PRODUSE TEXTILE",
    "Jackets": "PRODUSE TEXTILE",
    "Long sleeve t-shirt": "PRODUSE TEXTILE",
    "Vests": "PRODUSE TEXTILE",
    "Shirt": "PRODUSE TEXTILE",
    "Waist pants": "PRODUSE TEXTILE",
    "Pants": "PRODUSE TEXTILE",
    "Sportswear": "PRODUSE TEXTILE",
    "Workwears vests": "PRODUSE TEXTILE",
    "Workwears jackets": "PRODUSE TEXTILE",
    "Workwears polo shirts": "PRODUSE TEXTILE",
    "Workwears sweatshirts": "PRODUSE TEXTILE",
    "Raincoats": "PRODUSE TEXTILE",
    "Shorts": "PRODUSE TEXTILE",
    "Overalls": "PRODUSE TEXTILE",
    "Cloaks": "PRODUSE TEXTILE",
    "Towel": "PRODUSE TEXTILE",
    "CAPS": "PRODUSE TEXTILE",
    "Baseball caps": "PRODUSE TEXTILE",
    "Baseballcaps": "PRODUSE TEXTILE",
    # BAGS, TRAVEL, WELLNESS
    "Eco-friendly bags": "GENTI, CALATORII, WELLNESS",
    "Shopping bags, canvas bags": "GENTI, CALATORII, WELLNESS",
    "Backpacks and shoulder bags": "GENTI, CALATORII, WELLNESS",
    "Gym bags": "GENTI, CALATORII, WELLNESS",
    "Travel accessories": "GENTI, CALATORII, WELLNESS",
    "Cooler bags": "GENTI, CALATORII, WELLNESS",
    "Travel and sports bags": "GENTI, CALATORII, WELLNESS",
    "Document bags, laptop bags": "GENTI, CALATORII, WELLNESS",
    "Belt bags": "GENTI, CALATORII, WELLNESS",
    "Waterproof bags": "GENTI, CALATORII, WELLNESS",
    "Cosmetic accessories": "GENTI, CALATORII, WELLNESS",
    "Gift bags": "GENTI, CALATORII, WELLNESS",
    # DRINK TO GO
    "Thermoses and thermos mugs": "DRINK TO GO",
    "Mugs, cups, jugs": "DRINK TO GO",
    "Bottles": "DRINK TO GO",
    "Sets and drinking accessories": "DRINK TO GO",
    "Bottles, hip flasks": "DRINK TO GO",
    "Drinking straws": "DRINK TO GO",
    # ELECTRONICS AND ACCESSORIES
    "Pendrives": "ELECTRONICE SI ACCESORII",
    "Powerbanks": "ELECTRONICE SI ACCESORII",
    "Mobile accessories": "ELECTRONICE SI ACCESORII",
    "Speakers": "ELECTRONICE SI ACCESORII",
    "Wireless chargers": "ELECTRONICE SI ACCESORII",
    "Earphones and headphones": "ELECTRONICE SI ACCESORII",
    "Laser pointers": "ELECTRONICE SI ACCESORII",
    # PENS AND WRITING INSTRUMENTS
    "Metal pens and writing instrument": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Plastic pens": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Eco-friendly pens": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Pencils and chalks": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Pen sets and pen holders": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Highlighters": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Touch pens": "PIXURI SI INSTRUMENTE DE SCRIS",
    "Paper cutters": "PIXURI SI INSTRUMENTE DE SCRIS",
    # OFFICE AND CLOCKS
    "Notebooks and folders": "BIROU SI CEASURI",
    "Calculators and clocks": "BIROU SI CEASURI",
    "Business card holders": "BIROU SI CEASURI",
    "Desktop accessories": "BIROU SI CEASURI",
    # KEYCHAINS AND OTHERS
    "Keychains": "BRELOCURI SI ALTELE",
    "Bottle opener, glass opener": "BRELOCURI SI ALTELE",
    "Lighters": "BRELOCURI SI ALTELE",
    "Accessories": "BRELOCURI SI ALTELE",
    "Car accessories": "BRELOCURI SI ALTELE",
    "Security accessories": "BRELOCURI SI ALTELE",
    "Glass trophies and paperweights": "BRELOCURI SI ALTELE",
    "Money boxes": "BRELOCURI SI ALTELE",
    # LEISURE, SPORT AND GAMES
    "Games": "TIMP LIBER, SPORT SI JUCARII",
    "Beach sccessories": "TIMP LIBER, SPORT SI JUCARII",
    "Beach accessories": "TIMP LIBER, SPORT SI JUCARII",
    "Barbecue, picnic and outdoor": "TIMP LIBER, SPORT SI JUCARII",
    "Sports and fitness accessories": "TIMP LIBER, SPORT SI JUCARII",
    "Sunglasses": "TIMP LIBER, SPORT SI JUCARII",
    "Bicycle accessories": "TIMP LIBER, SPORT SI JUCARII",
    # TOOLS AND FLASHLIGHTS
    "Pocket knives": "UNELTE SI LANTERNE",
    "Multitools": "UNELTE SI LANTERNE",
    "Flashlights": "UNELTE SI LANTERNE",
    "Measuring tapes and foldig rules": "UNELTE SI LANTERNE",
    # UMBRELLAS
    "Umbrellas": "UMBRELE SI PELERINE DE PLOAIE",
    # HOME AND KITCHEN
    "Kitchen accessories": "PENTRU CASA SI BUCATARIE",
    "Home accessories": "PENTRU CASA SI BUCATARIE",
    "Snack and lunch boxes, food containers": "PENTRU CASA SI BUCATARIE",
    "Knives and cutting boards": "PENTRU CASA SI BUCATARIE",
    "Salt and pepper mills": "PENTRU CASA SI BUCATARIE",
}

# MIDOCEAN: subcategories are already broad enough — each one IS a group
# No further grouping needed; we'll treat each subcategory as its own group
MIDOCEAN_GROUPS: dict[str, str] = {}  # empty = use subcategory as-is

# ROLY / STAMINA: subcategories from Excel are descriptive enough
# The CATEGORIES column already provides good grouping
ROLY_GROUPS: dict[str, str] = {}    # use subcategory as-is
STAMINA_GROUPS: dict[str, str] = {}  # use subcategory as-is

# MALFINI: Romanian category names → broad groups
MALFINI_GROUPS: dict[str, str] = {
    "Tricouri": "PRODUSE TEXTILE",
    "Tricouri polo": "PRODUSE TEXTILE",
    "Cămăşi": "PRODUSE TEXTILE",
    "Hanorace": "PRODUSE TEXTILE",
    "Fleece": "PRODUSE TEXTILE",
    "Jachete-Veste": "PRODUSE TEXTILE",
    "Pantaloni": "PRODUSE TEXTILE",
    "Prosoape": "PRODUSE TEXTILE",
    "Şepci": "PRODUSE TEXTILE",
    " Încălțăminte": "PRODUSE TEXTILE",
    "Încălțăminte": "PRODUSE TEXTILE",
    "Sacoşe": "GENTI, CALATORII, WELLNESS",
    "Accesorii": "BRELOCURI SI ALTELE",
    "Materiale promoționale": "BRELOCURI SI ALTELE",
    "OUTLET": "PRODUSE TEXTILE",
}

# MAKITO: English categories from XML feed → broad groups
MAKITO_GROUPS: dict[str, str] = {
    # TEXTILE
    "Textile": "PRODUSE TEXTILE",
    "Caps and Hats": "PRODUSE TEXTILE",
    "Woman": "PRODUSE TEXTILE",
    "Kids": "PRODUSE TEXTILE",
    # BAGS, TRAVEL
    "Backpacks": "GENTI, CALATORII, WELLNESS",
    "Bags": "GENTI, CALATORII, WELLNESS",
    "Travel": "GENTI, CALATORII, WELLNESS",
    "Personal Care and Pharma": "GENTI, CALATORII, WELLNESS",
    # DRINK TO GO
    "Mugs, jars and thermos": "DRINK TO GO",
    "Take Away": "DRINK TO GO",
    "Wine, Drink and Bar Accessories": "DRINK TO GO",
    # ELECTRONICS
    "Technology and Accessories": "ELECTRONICE SI ACCESORII",
    # WRITING
    "Writing": "PIXURI SI INSTRUMENTE DE SCRIS",
    # OFFICE
    "Office and Business": "BIROU SI CEASURI",
    # KEYCHAINS, GIFTS
    "Gifts and Premiums": "BRELOCURI SI ALTELE",
    "Special Packaging": "BRELOCURI SI ALTELE",
    "Christmas": "BRELOCURI SI ALTELE",
    "Pet products": "BRELOCURI SI ALTELE",
    # LEISURE, SPORT
    "Sport and Adventure": "TIMP LIBER, SPORT SI JUCARII",
    "Leisure and Entertainment": "TIMP LIBER, SPORT SI JUCARII",
    "Summer and Beach": "TIMP LIBER, SPORT SI JUCARII",
    "Events and Party": "TIMP LIBER, SPORT SI JUCARII",
    # TOOLS
    "Tools, Brico and Car": "UNELTE SI LANTERNE",
    "Agriculture": "UNELTE SI LANTERNE",
    # UMBRELLAS
    "Rain and Cold": "UMBRELE SI PELERINE DE PLOAIE",
    # HOME
    "Home and Decoration": "PENTRU CASA SI BUCATARIE",
    # OTHER / GENERIC
    "Sustainable Articles": "BRELOCURI SI ALTELE",
    "Sublimation Line": "BRELOCURI SI ALTELE",
    "Brands": "BRELOCURI SI ALTELE",
    "New Arrivals": "BRELOCURI SI ALTELE",
    "Limited Edition": "BRELOCURI SI ALTELE",
    "Outlet": "BRELOCURI SI ALTELE",
    "Made in europe": "BRELOCURI SI ALTELE",
    "Spain Line": "BRELOCURI SI ALTELE",
}

# UTT (TShirt Europe): Romanian categories from JSON → broad groups
UTT_GROUPS: dict[str, str] = {
    "Tricouri": "PRODUSE TEXTILE",
    "Tricouri polo": "PRODUSE TEXTILE",
    "Hanorace și bluze": "PRODUSE TEXTILE",
    "Cămăși și tricotaje": "PRODUSE TEXTILE",
    "Pantaloni": "PRODUSE TEXTILE",
    "Veste": "PRODUSE TEXTILE",
    "Jachete și geci de vânt": "PRODUSE TEXTILE",
    "Jachete softshell": "PRODUSE TEXTILE",
    "Jachete polar": "PRODUSE TEXTILE",
    "Îmbrăcăminte de lucru": "PRODUSE TEXTILE",
    "Îmbrăcăminte sport": "PRODUSE TEXTILE",
    "Șepci": "PRODUSE TEXTILE",
    "Ospitalitate și îngrijire": "PRODUSE TEXTILE",
    "Prosoape": "PENTRU CASA SI BUCATARIE",
    "Genți": "GENTI, CALATORII, WELLNESS",
    "Accesorii": "BRELOCURI SI ALTELE",
    "Jucării de pluș": "TIMP LIBER, SPORT SI JUCARII",
    "Materiale de marketing": "BRELOCURI SI ALTELE",
}

# Master lookup: supplier name → mapping dict
SUPPLIER_GROUP_MAPS: dict[str, dict[str, str]] = {
    "EASYGIFTS": EASYGIFTS_GROUPS,
    "MACMA": MACMA_GROUPS,
    "MIDOCEAN": MIDOCEAN_GROUPS,
    "ROLY": ROLY_GROUPS,
    "STAMINA": STAMINA_GROUPS,
    "MALFINI": MALFINI_GROUPS,
    "MAKITO": MAKITO_GROUPS,
    "UTT": UTT_GROUPS,
}

# Preferred display order for groups
GROUP_ORDER = [
    "PRODUSE TEXTILE",
    "GENTI, CALATORII, WELLNESS",
    "DRINK TO GO",
    "ELECTRONICE SI ACCESORII",
    "PIXURI SI INSTRUMENTE DE SCRIS",
    "BIROU SI CEASURI",
    "BRELOCURI SI ALTELE",
    "TIMP LIBER, SPORT SI JUCARII",
    "UNELTE SI LANTERNE",
    "UMBRELE SI PELERINE DE PLOAIE",
    "PENTRU CASA SI BUCATARIE",
]


def get_group(supplier: str, subcategory: str) -> str:
    """Get the broad group name for a subcategory, or the subcategory itself."""
    mapping = SUPPLIER_GROUP_MAPS.get(supplier, {})
    return mapping.get(subcategory, subcategory)
