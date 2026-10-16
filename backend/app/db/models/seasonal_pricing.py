"""SeasonalPricing ORM model — festival/peak price multipliers."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SeasonalPricing(Base):
    """A price multiplier applied during a specific date range.

    If ``room_type_id`` is NULL, the multiplier applies to all room types.
    If set, it applies only to that room type.

    Example rows:
        Dashain 2081  2024-10-13  2024-10-27  1.5   NULL        (all rooms)
        Tihar 2081    2024-11-01  2024-11-05  1.4   NULL
        Chhath 2081   2024-11-07  2024-11-09  1.3   NULL
        New Year 2082 2025-04-14  2025-04-16  1.2   deluxe      (deluxe only)
    """

    __tablename__ = "seasonal_pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[Date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Date] = mapped_column(Date, nullable=False)
    # Multiplier: 1.0 = no change, 1.5 = 50% premium, 0.8 = 20% discount
    multiplier: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False
    )
    # NULL means applies to all room types
    room_type_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("room_types.id"), nullable=True, index=True
    )

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_seasonal_end_after_start"),
        CheckConstraint("multiplier > 0", name="ck_seasonal_multiplier_positive"),
    )

    # Relationships
    room_type_rel: Mapped[RoomType | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "RoomType", back_populates="seasonal_pricing"
    )

    def __repr__(self) -> str:
        return (
            f"<SeasonalPricing {self.name!r} "
            f"{self.start_date}-{self.end_date} x{self.multiplier}>"
        )
