import enum

from sqlalchemy import Column, String, Float, Text, DateTime, Integer, Boolean, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base, generate_uuid


class QuoteStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        # Quote number must be unique per company, not globally
        UniqueConstraint("company_id", "number", name="uq_quotes_company_number"),
        Index("ix_quotes_number", "number"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    number = Column(String(50))

    # Company (who issues the quote)
    company_id = Column(String(36), nullable=True)

    # Client
    client_name = Column(String(300), default="")
    client_email = Column(String(300), default="")
    client_company = Column(String(300), default="")
    client_phone = Column(String(50), default="")

    # Status
    status = Column(String(20), default=QuoteStatus.DRAFT, index=True)

    # Financials
    subtotal = Column(Float, default=0.0)
    margin_percent = Column(Float, default=30.0)
    total = Column(Float, default=0.0)
    currency = Column(String(10), default="EUR")

    # Pricing snapshot — frozen at creation so PDF regenerations
    # stay stable even if global settings (EUR/RON rate, qty tiers,
    # discount step) change afterwards.
    exchange_rate = Column(Float, nullable=True)
    quantity_tiers = Column(String(200), nullable=True)  # e.g. "100,200,300,500,1000"
    discount_step = Column(Float, nullable=True)
    # When True, the per-unit RON price and item.total bake in the tier
    # discount based on item.quantity. False on legacy quotes — they keep
    # their original totals untouched so historical PDFs stay identical.
    apply_tier_discount = Column(Boolean, default=False)

    # Extra
    notes = Column(Text, default="")
    valid_until = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    items = relationship("QuoteItem", back_populates="quote", cascade="all, delete-orphan", lazy="selectin")

    def _parse_tiers(self) -> list[int]:
        """Parse quantity_tiers string into a sorted list of ints."""
        raw = self.quantity_tiers or ""
        out: list[int] = []
        for t in raw.split(","):
            t = t.strip()
            if t.isdigit():
                out.append(int(t))
        return out

    def recalculate(self):
        """Recalculate each item then subtotal/total from items.

        When `apply_tier_discount` is True, items get their tier % discount
        baked into their stored `total` so DB, API and UI all see the final
        figure. Legacy quotes (flag False) keep the pre-existing behaviour.
        """
        tiers = self._parse_tiers()
        step = self.discount_step if self.discount_step is not None else 2.0
        apply_disc = bool(self.apply_tier_discount)
        for item in self.items:
            item.calculate(
                quantity_tiers=tiers if apply_disc else None,
                discount_step=step if apply_disc else 0.0,
            )
        self.subtotal = round(sum(item.total for item in self.items), 2)
        self.total = self.subtotal


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    quote_id = Column(String(36), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(String(36), nullable=True)

    # Product snapshot
    product_name = Column(String(500), default="")
    product_description = Column(Text, default="")
    product_sku = Column(String(100), default="")
    product_image = Column(String(1000), default="")
    product_color = Column(String(200), default="")
    product_colors = Column(JSON, default=list)   # [{"name": "Roșu", "hex": "#FF0000"}, ...]
    product_size = Column(String(200), default="")
    size_prices = Column(JSON, default=list)       # [{"size": "S", "price": 2.28}, {"size": "3XL", "price": 3.22}, ...]
    size_quantities = Column(JSON, default=list)    # [{"size": "S", "qty": 50}, {"size": "M", "qty": 100}, ...] — optional per-size breakdown

    # Pricing
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, default=0.0)       # Base cost price
    margin_percent = Column(Float, default=30.0)
    sell_price = Column(Float, default=0.0)        # unit_price * (1 + margin/100)
    total = Column(Float, default=0.0)             # sell_price * quantity

    # Customization
    printing_method = Column(String(200), default="")
    printing_cost = Column(Float, default=0.0)     # Per unit printing cost
    printing_setup = Column(Float, default=0.0)    # One-time setup cost
    customization_notes = Column(Text, default="")

    notes = Column(Text, default="")

    # Order confirmation
    is_confirmed = Column(Boolean, default=False)   # True when client confirmed this item

    quote = relationship("Quote", back_populates="items")

    def calculate(
        self,
        quantity_tiers: list[int] | None = None,
        discount_step: float = 0.0,
    ):
        """Calculate sell_price and total from base values.

        sell_price = product EUR price with margin (no printing) — BASE per unit.
        total = sell_price * quantity * (1 - tier_discount) (EUR).
        Tier discount is only applied when `quantity_tiers` is provided
        (caller's flag); otherwise total stays at the pre-discount value.
        Printing costs are in RON and handled separately in PDF/display.
        """
        self.sell_price = round(
            self.unit_price * (1 + self.margin_percent / 100), 2
        )
        # Tier discount on item total (only when caller passes tiers)
        pct = 0.0
        if quantity_tiers and self.quantity > 0:
            for tier_idx, tier_qty in enumerate(quantity_tiers):
                if self.quantity >= tier_qty:
                    pct = tier_idx * discount_step
        base_total = self.sell_price * self.quantity
        self.total = round(base_total * (1 - pct / 100), 2) if pct > 0 else round(base_total, 2)
