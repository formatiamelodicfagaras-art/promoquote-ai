"""
Parser for ANDA Present XML feeds (v2.8 manual).

ANDA provides separate XML feeds:
  - products   → product catalog (name, images, colors, specs, categories)
  - prices     → pricing per item number (listPrice + discountPrice)
  - inventories → stock levels per item number (central/external/incoming)
  - labeling   → printing positions, techniques, areas
"""
import logging
import re
from lxml import etree

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ANDA colour codes → (name, hex) from manual v2.8 Appendix
# ---------------------------------------------------------------------------
ANDA_COLOR_HEX: dict[str, tuple[str, str]] = {
    "00": ("beige", "#dfd9c9"),
    "01": ("white", "#ffffff"),
    "01T": ("transparent", "#ffffff"),
    "02": ("yellow", "#f0e44d"),
    "02F": ("fluorescent yellow", "#e8e95e"),
    "02V": ("light yellow", "#fceb9d"),
    "03": ("orange", "#f09b1f"),
    "03A": ("old light orange", "#cf6e4a"),
    "03F": ("fluorescent orange", "#f68a52"),
    "03V": ("light orange", "#ffd27f"),
    "04": ("rose", "#ef96bf"),
    "04V": ("light rose", "#f9cfe1"),
    "05": ("red", "#e93a4c"),
    "05A": ("dark red", "#a91e23"),
    "05V": ("light red", "#de6755"),
    "06": ("blue", "#366aa8"),
    "06A": ("dark blue", "#1b2e59"),
    "06V": ("light blue", "#aecae1"),
    "07": ("green", "#438c4a"),
    "07A": ("dark green", "#284e2b"),
    "07F": ("fluorescent green", "#53c83e"),
    "07V": ("mint green", "#b8db9a"),
    "08": ("claret", "#a12f38"),
    "08A": ("old claret", "#af4157"),
    "09": ("brown", "#5d4033"),
    "10": ("black", "#231f20"),
    "12": ("peach", "#f6b092"),
    "13": ("purple", "#6c4086"),
    "13A": ("dark purple", "#3b2640"),
    "13V": ("light purple", "#847598"),
    "20": ("safety yellow", "#e7e85b"),
    "21": ("silver", "#c7c7c7"),
    "22": ("gold yellow", "#fdbc29"),
    "22A": ("dark gold yellow", "#c79653"),
    "22V": ("light gold yellow", "#fbd074"),
    "23": ("natural", "#f4e9cc"),
    "24": ("butter yellow", "#f7e1b7"),
    "25": ("pink", "#ef5993"),
    "25A": ("dark pink", "#e01969"),
    "25F": ("fluorescent pink", "#ff56a2"),
    "25N": ("bright pink", "#ef4e94"),
    "25V": ("old pink", "#d15c8e"),
    "26": ("light purple", "#7d7dad"),
    "27": ("purple", "#8d429f"),
    "27A": ("dark purple", "#4d3863"),
    "28": ("eggplant", "#501e59"),
    "30": ("mandarine", "#f79225"),
    "30A": ("medium orange", "#f68a52"),
    "30V": ("old orange", "#cf6e4a"),
    "31": ("safety orange", "#f79225"),
    "61": ("old royal blue", "#546da2"),
    "62": ("old dark blue", "#4b4865"),
    "63": ("turquoise", "#1680bc"),
    "63A": ("old turquoise", "#166c92"),
    "63V": ("light turquoise", "#1698c8"),
    "64": ("sky blue", "#91b4df"),
    "64A": ("dark sky blue", "#1582be"),
    "65": ("medium blue", "#83a6d5"),
    "65A": ("midnight blue", "#23383e"),
    "66": ("indigo blue", "#4b6478"),
    "66A": ("cobalt", "#323393"),
    "71": ("lime green", "#9dce68"),
    "71N": ("bright lime green", "#97e444"),
    "72": ("kelly green", "#12a24c"),
    "72A": ("old kelly green", "#25b07b"),
    "73": ("kiwi green", "#93b03d"),
    "74": ("apple green", "#25b354"),
    "74A": ("old apple green", "#15af56"),
    "77": ("ash grey", "#cbcbcb"),
    "77V": ("medium ash grey", "#828589"),
    "78": ("medium grey", "#a3a2a2"),
    "79": ("dark ash grey", "#535b60"),
    "80": ("dark grey", "#464d52"),
    "81": ("grey", "#8a8a8b"),
    "82": ("light grey", "#dbdbdb"),
    "84": ("burgundy", "#683137"),
    "84A": ("maroon", "#4a2025"),
    "91": ("bronze", "#ae916c"),
    "92": ("bronze brown", "#91745d"),
    "93": ("medium brown", "#b39a76"),
    "94": ("dark brown", "#3f301c"),
    "94A": ("russet", "#583513"),
    "95": ("khaki", "#54593c"),
    "95A": ("old khaki", "#4f5e4f"),
    "96": ("olive", "#5b5c49"),
    "98": ("gold", "#bca558"),
    "99": ("pistachio", "#cdd877"),
}

# Regex to extract colour code(s) from itemNumber suffix
# AP12345-01 → ["01"], AP12345-01-02 → ["01","02"], AP12345-01T → ["01T"]
_COLOR_CODE_RE = re.compile(r"-(\d{2}[A-Z]?)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _text(el, tag: str, default: str = "") -> str:
    """Get text content of a child element."""
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return default


def _float(el, tag: str, default: float = 0.0) -> float:
    val = _text(el, tag)
    try:
        return float(val.replace(",", "."))
    except (ValueError, TypeError):
        return default


def _int(el, tag: str, default: int = 0) -> int:
    val = _text(el, tag)
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _extract_color_codes(item_number: str) -> list[str]:
    """Extract colour codes from ANDA item number suffix."""
    return _COLOR_CODE_RE.findall(item_number)


def _resolve_colors(item_number: str, primary_color: str, secondary_color: str) -> list[dict]:
    """Build color list from item number codes + names."""
    codes = _extract_color_codes(item_number)
    colors = []

    if codes:
        for code in codes:
            if code in ANDA_COLOR_HEX:
                name, hex_val = ANDA_COLOR_HEX[code]
                colors.append({"name": name, "hex": hex_val, "image": ""})
            elif primary_color:
                colors.append({"name": primary_color.lower(), "hex": "", "image": ""})
    else:
        if primary_color:
            # Try to find hex by matching name in the table
            hex_val = ""
            pc_lower = primary_color.lower()
            for _, (cname, chex) in ANDA_COLOR_HEX.items():
                if cname == pc_lower:
                    hex_val = chex
                    break
            colors.append({"name": primary_color, "hex": hex_val, "image": ""})

    if secondary_color and secondary_color.lower() not in {c["name"].lower() for c in colors}:
        hex_val = ""
        sc_lower = secondary_color.lower()
        for _, (cname, chex) in ANDA_COLOR_HEX.items():
            if cname == sc_lower:
                hex_val = chex
                break
        colors.append({"name": secondary_color, "hex": hex_val, "image": ""})

    return colors


# ---------------------------------------------------------------------------
# Products XML parser (ANDA v2.8)
# ---------------------------------------------------------------------------
def parse_products_xml(xml_content: bytes) -> list[dict]:
    """
    Parse ANDA products XML feed → list of product dicts.

    Real structure (v2.8):
    <products>
      <product>
        <itemNumber>AP741951-02</itemNumber>
        <designName>Martins</designName>
        <primaryColor>yellow</primaryColor>
        <secondaryColor>black</secondaryColor>
        <name>customisable thermo mug</name>
        <descriptions>Double wall plastic thermo mug...</descriptions>
        <primaryImage>https://data.cdn-andapresent.com/...</primaryImage>
        <images><image>url</image></images>
        <minimumOrderQuantity>50</minimumOrderQuantity>
        <individualProductWeightGram>240</individualProductWeightGram>
        <brandName>...</brandName>
        <rootItemNumber>AP741951</rootItemNumber>
        <countryOfOrigin>CN</countryOfOrigin>
        <categories>
          <category><name>Food &amp; Drinkware</name><level>1</level><externalId>14000</externalId></category>
          <category><name>Flasks and thermo mugs</name><level>2</level><externalId>14060</externalId></category>
          <category><name>Travel and Thermo mugs</name><level>3</level><externalId>14063</externalId></category>
        </categories>
        <specification>
          <property><type>Material 1</type><name>...</name><values><value>Plastic</value></values></property>
          <property><type>Size</type><name>...</name><values><value>85x155 mm</value></values></property>
        </specification>
      </product>
    </products>
    """
    try:
        root = etree.fromstring(xml_content)
    except etree.XMLSyntaxError as e:
        logger.error(f"Failed to parse products XML: {e}")
        return []

    products = []

    for prod_el in root.findall(".//product"):
        item_number = _text(prod_el, "itemNumber")
        if not item_number:
            continue

        # Name = designName, short_description = <name> tag
        design_name = _text(prod_el, "designName")
        short_desc = _text(prod_el, "name")
        name = design_name or short_desc or item_number

        # Description
        description = _text(prod_el, "descriptions") or _text(prod_el, "description")

        # Brand
        brand = _text(prod_el, "brandName")

        # Root item number (for variant grouping)
        root_item = _text(prod_el, "rootItemNumber") or item_number.split("-")[0].split("_")[0]

        # Images
        primary_image = _text(prod_el, "primaryImage")
        images = []
        images_el = prod_el.find("images")
        if images_el is not None:
            for img_el in images_el.findall("image"):
                if img_el.text:
                    images.append(img_el.text.strip())
        if primary_image and primary_image not in images:
            images.insert(0, primary_image)

        # Colors from item number + primaryColor/secondaryColor
        primary_color = _text(prod_el, "primaryColor")
        secondary_color = _text(prod_el, "secondaryColor")
        colors = _resolve_colors(item_number, primary_color, secondary_color)

        # Specifications
        specifications = {}
        spec_el = prod_el.find("specification")
        if spec_el is not None:
            for prop_el in spec_el.findall("property"):
                prop_type = _text(prop_el, "type")
                values_el = prop_el.find("values")
                if values_el is not None:
                    vals = [v.text.strip() for v in values_el.findall("value") if v.text]
                    if prop_type and vals:
                        specifications[prop_type] = ", ".join(vals)

        # Extract clothing size from item number suffix (e.g. AP721968-05_XL → XL)
        if "_" in item_number:
            size_from_id = item_number.rsplit("_", 1)[-1].strip()
            if size_from_id:
                specifications["size"] = size_from_id

        # Weight
        weight_gram = _int(prod_el, "individualProductWeightGram")
        if weight_gram > 0:
            specifications["weight"] = f"{weight_gram}g"

        # Country of origin
        country = _text(prod_el, "countryOfOrigin")
        if country:
            specifications["country_of_origin"] = country

        # Categories (level 1 = broad, level 2 = mid, level 3 = specific)
        category_l1 = ""
        category_l2 = ""
        category_l3 = ""
        cats_el = prod_el.find("categories")
        if cats_el is not None:
            for cat_el in cats_el.findall("category"):
                level = _text(cat_el, "level")
                cat_name = _text(cat_el, "name")
                if level == "1":
                    category_l1 = cat_name
                elif level == "2":
                    category_l2 = cat_name
                elif level == "3":
                    category_l3 = cat_name

        # Min order
        min_order = _int(prod_el, "minimumOrderQuantity") or 1

        # Temporarily unavailable
        temp_unavailable = _int(prod_el, "temporarilyUnavailable")

        products.append({
            "external_id": item_number,
            "name": name,
            "description": description,
            "short_description": short_desc or name,
            "category_l1": category_l1,
            "category_l2": category_l2,
            "category_l3": category_l3,
            "brand": brand,
            "primary_image": primary_image,
            "images": images,
            "colors": colors,
            "specifications": specifications,
            "min_order_qty": min_order,
            "supplier_code": root_item,
            "temp_unavailable": bool(temp_unavailable),
        })

    logger.info(f"Parsed {len(products)} products from ANDA XML")
    return products


# ---------------------------------------------------------------------------
# Prices XML parser (ANDA v2.8)
# ---------------------------------------------------------------------------
def parse_prices_xml(xml_content: bytes) -> dict[str, float]:
    """
    Parse ANDA prices XML → {item_number: discount_price}.

    Uses discountPrice (distributor purchase price), not listPrice.

    Structure:
    <prices>
      <price>
        <itemNumber>AP810803-10_XS</itemNumber>
        <currency>EUR</currency>
        <amount>2.5</amount>
        <type>discountPrice</type>
      </price>
    </prices>
    """
    try:
        root = etree.fromstring(xml_content)
    except etree.XMLSyntaxError as e:
        logger.error(f"Failed to parse prices XML: {e}")
        return {}

    prices: dict[str, float] = {}

    for price_el in root.findall(".//price"):
        item_number = _text(price_el, "itemNumber")
        if not item_number:
            continue

        price_type = _text(price_el, "type")
        # Only use discountPrice (distributor price)
        if price_type != "discountPrice":
            continue

        amount_str = _text(price_el, "amount")
        try:
            amount = float(amount_str.replace(",", "."))
            if amount > 0:
                prices[item_number] = amount
        except (ValueError, TypeError):
            pass

    logger.info(f"Parsed {len(prices)} discount prices from ANDA XML")
    return prices


# ---------------------------------------------------------------------------
# Inventory XML parser (ANDA v2.8)
# ---------------------------------------------------------------------------
def parse_inventory_xml(xml_content: bytes) -> dict[str, int]:
    """
    Parse ANDA inventories XML → {item_number: total_available_stock}.

    Aggregates central_stock + incoming_to_central_stock per item.

    Structure:
    <inventories>
      <record>
        <itemNumber>AP892006</itemNumber>
        <type>central_stock</type>
        <amount>0</amount>
        <moreThanAmount>0</moreThanAmount>
        <arrivalDate/>
      </record>
    </inventories>
    """
    try:
        root = etree.fromstring(xml_content)
    except etree.XMLSyntaxError as e:
        logger.error(f"Failed to parse inventory XML: {e}")
        return {}

    # Aggregate stock per item
    inventory: dict[str, int] = {}

    for record_el in root.findall(".//record"):
        item_number = _text(record_el, "itemNumber")
        if not item_number:
            continue

        stock_type = _text(record_el, "type")
        amount = _int(record_el, "amount")

        # Count central_stock as immediately available
        if stock_type == "central_stock":
            inventory[item_number] = inventory.get(item_number, 0) + amount

    logger.info(f"Parsed inventory for {len(inventory)} items from ANDA XML")
    return inventory


# ---------------------------------------------------------------------------
# Labeling XML parser (ANDA v2.8)
# ---------------------------------------------------------------------------
def parse_labeling_xml(xml_content: bytes) -> dict[str, list[dict]]:
    """
    Parse ANDA labeling XML → {item_number: printing_options}.

    Structure:
    <labelings>
      <labeling>
        <itemNumber>AP6155-06</itemNumber>
        <positions>
          <position>
            <serial>I</serial>
            <posName>Below clip - right handed</posName>
            <posImage>https://...</posImage>
            <technologies>
              <technology>
                <Code>P0</Code>
                <Name>Pad printing</Name>
                <maxColor>4</maxColor>
                <maxWmm>50</maxWmm>
                <maxHmm>7</maxHmm>
                <maxDmm/>
                <fixedSize>0</fixedSize>
              </technology>
            </technologies>
          </position>
        </positions>
      </labeling>
    </labelings>
    """
    try:
        root = etree.fromstring(xml_content)
    except etree.XMLSyntaxError as e:
        logger.error(f"Failed to parse labeling XML: {e}")
        return {}

    labeling: dict[str, list[dict]] = {}

    for lab_el in root.findall(".//labeling"):
        item_number = _text(lab_el, "itemNumber")
        if not item_number:
            continue

        options = []
        positions_el = lab_el.find("positions")
        if positions_el is None:
            continue

        for pos_el in positions_el.findall("position"):
            pos_name = _text(pos_el, "posName")
            pos_image = _text(pos_el, "posImage")
            max_w = _float(pos_el, "maxWmm")
            max_h = _float(pos_el, "maxHmm")
            max_d = _float(pos_el, "maxDmm")

            techniques = []
            techs_el = pos_el.find("technologies")
            if techs_el is not None:
                for tech_el in techs_el.findall("technology"):
                    tech_code = _text(tech_el, "Code")
                    tech_name = _text(tech_el, "Name")
                    max_color = _text(tech_el, "maxColor")
                    if tech_name:
                        techniques.append({
                            "name": tech_name,
                            "code": tech_code,
                            "max_colors": max_color,
                            "max_width_mm": _float(tech_el, "maxWmm"),
                            "max_height_mm": _float(tech_el, "maxHmm"),
                            "max_diameter_mm": _float(tech_el, "maxDmm"),
                        })

            options.append({
                "position": pos_name,
                "position_image": pos_image,
                "max_width_mm": max_w,
                "max_height_mm": max_h,
                "max_diameter_mm": max_d,
                "techniques": techniques,
            })

        if options:
            labeling[item_number] = options

    logger.info(f"Parsed labeling for {len(labeling)} products from ANDA XML")
    return labeling
