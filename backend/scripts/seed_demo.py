"""Seed a fresh DB with a demo admin, a default company, and ~30 sample products.

Idempotent — running it twice does not duplicate rows. Run after `init_db()`
has created the tables (i.e. after the backend has started at least once).

    python backend/scripts/seed_demo.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from sqlalchemy import select  # noqa: E402

from app.database import async_session, init_db  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.integration import Integration  # noqa: E402
from app.services.auth_service import hash_password  # noqa: E402


SAMPLE_PRODUCTS = [
    # Textile
    ("Classic T-Shirt Unisex", "DEMO-T001", "Tricou bumbac 180 g/m², unisex, mai multe culori.", "Textile", "Tricouri", 2.45, "Negru", "#000000", "S-XXL", "200g"),
    ("Polo Tricot Premium", "DEMO-T002", "Polo cu nasturi, 200 g/m², bumbac piqué.", "Textile", "Polo", 5.90, "Bleumarin", "#1E3A8A", "S-XXL", "220g"),
    ("Hoodie Comfort Fit", "DEMO-T003", "Hanorac bumbac fleece, 280 g/m², cu glugă și buzunar canguru.", "Textile", "Hanorace", 12.30, "Gri închis", "#374151", "S-XXL", "450g"),
    ("Polar Fleece Jacket", "DEMO-T004", "Jachetă polar fleece 300 g/m², 2 buzunare cu fermoar.", "Textile", "Jachete", 11.80, "Negru", "#111827", "S-XXL", "480g"),
    ("Softshell Pro", "DEMO-T005", "Jachetă softshell impermeabilă cu membrană respirabilă.", "Textile", "Jachete", 24.50, "Negru", "#000000", "S-XXL", "560g"),
    ("Cap Sandwich Visor", "DEMO-T006", "Șapcă bumbac cu cozoroc rigid, închidere reglabilă.", "Textile", "Șepci", 1.85, "Roșu", "#DC2626", "ONE", "85g"),
    # Bags
    ("City Backpack 18L", "DEMO-B001", "Rucsac urban cu compartiment laptop 15.6\".", "Bagaje", "Rucsacuri", 8.40, "Gri", "#6B7280", "30×42×15 cm", "520g"),
    ("Sport Duffel Bag 40L", "DEMO-B002", "Geantă sport cu compartimente separate.", "Bagaje", "Genți sport", 7.20, "Negru", "#000000", "50×30×26 cm", "640g"),
    ("Cotton Shopper Tote", "DEMO-B003", "Sacoșă bumbac 140 g/m², mânere lungi.", "Bagaje", "Sacoșe", 0.95, "Natur", "#F5F5DC", "38×42 cm", "120g"),
    ("Drawstring Backpack", "DEMO-B004", "Rucsac cu șnur, poliester, ușor.", "Bagaje", "Saci", 0.75, "Albastru", "#3B82F6", "35×45 cm", "80g"),
    # Drinkware
    ("Stainless Steel Bottle 500ml", "DEMO-D001", "Sticlă inox dublu strat, păstrează rece 24h / cald 12h.", "Drinkware", "Sticle", 6.10, "Argintiu", "#C0C0C0", "Ø7×24 cm", "300g"),
    ("Bamboo Coffee Mug 350ml", "DEMO-D002", "Cană bambus reutilizabilă cu capac silicon.", "Drinkware", "Căni", 3.20, "Maro", "#92400E", "Ø8×14 cm", "180g"),
    ("Ceramic Mug Classic", "DEMO-D003", "Cană ceramică 330 ml, ideală pentru personalizare.", "Drinkware", "Căni", 1.10, "Alb", "#FFFFFF", "Ø8×9.5 cm", "320g"),
    ("Glass Water Bottle 600ml", "DEMO-D004", "Sticlă borosilicat, husă silicon protectoare.", "Drinkware", "Sticle", 4.80, "Verde", "#10B981", "Ø7×25 cm", "420g"),
    # Tech
    ("Powerbank 10000 mAh", "DEMO-E001", "Powerbank cu 2 USB-A + USB-C, intrare 5V/2A.", "Electronice", "Powerbank", 9.95, "Alb", "#FFFFFF", "14×6.5×1.5 cm", "210g"),
    ("Wireless Earbuds BT 5.3", "DEMO-E002", "Căști true wireless cu carcasă de încărcare.", "Electronice", "Audio", 12.40, "Negru", "#000000", "5×4×2 cm", "45g"),
    ("USB-C Hub 4-in-1", "DEMO-E003", "Hub USB-C cu HDMI 4K, 2× USB-A, USB-C PD.", "Electronice", "Adaptoare", 7.80, "Gri spațial", "#4B5563", "10×3×1.2 cm", "65g"),
    ("Wireless Charger Pad 15W", "DEMO-E004", "Încărcător wireless Qi cu LED indicator.", "Electronice", "Încărcătoare", 5.20, "Negru", "#000000", "Ø10×0.8 cm", "120g"),
    # Writing
    ("Metal Pen Click Action", "DEMO-W001", "Pix metalic cu mecanism click, scriere fluentă.", "Pixuri", "Metalice", 0.65, "Argintiu", "#C0C0C0", "14×1 cm", "20g"),
    ("Eco Bamboo Pen", "DEMO-W002", "Pix din bambus + plastic reciclat.", "Pixuri", "Eco", 0.42, "Maro", "#92400E", "14×1 cm", "10g"),
    ("Premium Roller Ball Pen", "DEMO-W003", "Pix roller premium în cutie cadou.", "Pixuri", "Premium", 2.10, "Negru", "#000000", "14×1.2 cm", "30g"),
    # Office
    ("A5 Hardcover Notebook", "DEMO-O001", "Caiet copertă rigidă, 192 pagini dictando.", "Birou", "Caiete", 2.85, "Negru", "#000000", "15×21 cm", "320g"),
    ("Desk Calendar 2026", "DEMO-O002", "Calendar de birou, suport carton.", "Birou", "Calendare", 1.65, "Multicolor", "#FFFFFF", "20×14 cm", "180g"),
    ("Foldable Reading Glasses", "DEMO-O003", "Ochelari de citit pliabili în etui propriu.", "Birou", "Accesorii", 1.95, "Negru", "#000000", "12×3×2 cm", "30g"),
    # Wellness
    ("Yoga Mat 6mm", "DEMO-W004", "Saltea yoga NBR, antiderapantă, cu curea transport.", "Wellness", "Sport", 6.40, "Mov", "#A855F7", "183×61×0.6 cm", "1100g"),
    ("Bamboo Toothbrush Set 4 pcs", "DEMO-W005", "Set 4 periuțe bambus cu peri moi.", "Wellness", "Igienă", 1.75, "Bambus", "#D6BD8E", "19 cm", "40g"),
    # Eco / outdoor
    ("Reusable Straw Set", "DEMO-G001", "Set 4 paie inox + perie + săculeț.", "Eco", "Accesorii", 1.10, "Argintiu", "#C0C0C0", "21 cm", "55g"),
    ("Foldable Shopping Bag", "DEMO-G002", "Sacoșă pliabilă în pungă proprie, poliester.", "Eco", "Sacoșe", 0.85, "Verde", "#10B981", "40×38 cm", "45g"),
    ("Umbrella Compact Auto", "DEMO-G003", "Umbrelă pliabilă cu deschidere automată.", "Outdoor", "Umbrele", 4.20, "Negru", "#000000", "28 cm pliată", "320g"),
    ("Reflective Safety Vest", "DEMO-G004", "Vestă reflectorizantă, taglie unică.", "Outdoor", "Siguranță", 1.25, "Galben", "#FACC15", "M-XL", "120g"),
]


async def seed():
    await init_db()

    async with async_session() as db:
        # ── Admin user ───────────────────────────────────────────────
        existing = await db.execute(select(User).where(User.email == "admin@demo.local"))
        if existing.scalar_one_or_none() is None:
            db.add(User(
                email="admin@demo.local",
                name="Admin Demo",
                password_hash=hash_password("admin123"),
                is_admin=True,
            ))
            print("  + Created admin user (admin@demo.local / admin123)")
        else:
            print("  · Admin user already exists, skipped")

        # ── Default company ──────────────────────────────────────────
        existing = await db.execute(select(Company).where(Company.is_default == True))
        if existing.scalar_one_or_none() is None:
            db.add(Company(
                id=str(uuid.uuid4()),
                name="Demo Company SRL",
                cui="RO00000000",
                address="Str. Demo nr. 1, București",
                phone="+40 700 000 000",
                email="demo@example.com",
                website="https://example.com",
                bank="Banca Demo",
                iban="RO00DEMO0000000000000000",
                is_default=True,
            ))
            print("  + Created default company")
        else:
            print("  · Default company already exists, skipped")

        # ── Generic XML integration ──────────────────────────────────
        existing = await db.execute(select(Integration).where(Integration.name == "demo"))
        integ = existing.scalar_one_or_none()
        if integ is None:
            integ = Integration(
                name="demo",
                display_name="Demo Catalog",
                integration_type="generic_xml",
                api_url="",
                api_key="",
                extra_config={},
                is_active=True,
                products_count=len(SAMPLE_PRODUCTS),
                last_sync_at=datetime.now(timezone.utc),
                last_sync_status="success",
            )
            db.add(integ)
            await db.flush()
            print("  + Created demo integration")
        else:
            integ.products_count = len(SAMPLE_PRODUCTS)
            print("  · Demo integration exists, will refresh products")

        # ── Sample products ──────────────────────────────────────────
        added = 0
        for name, sku, desc, cat, sub, price, color_name, hex_, size, weight in SAMPLE_PRODUCTS:
            external_id = sku  # already prefixed "DEMO-" in SAMPLE_PRODUCTS
            existing = await db.execute(select(Product).where(Product.external_id == external_id))
            if existing.scalar_one_or_none() is not None:
                continue
            db.add(Product(
                external_id=external_id,
                integration_id=integ.id,
                supplier_code=sku,
                name=name,
                description=desc,
                category=cat,
                subcategory=sub,
                brand="Demo",
                base_price=price,
                currency="EUR",
                primary_image="",
                images=[],
                colors=[{"name": color_name, "hex": hex_}],
                specifications={"size": size, "weight": weight},
                printing_options=[],
                stock=500,
                min_order_qty=25,
                is_active=True,
                last_synced_at=datetime.now(timezone.utc),
            ))
            added += 1

        await db.commit()
        print(f"  + Added {added} sample products (total in catalog: {len(SAMPLE_PRODUCTS)})")
        print("\nSeed complete. Log in at http://localhost:3000 with:")
        print("    email:    admin@demo.local")
        print("    password: admin123\n")


if __name__ == "__main__":
    asyncio.run(seed())
