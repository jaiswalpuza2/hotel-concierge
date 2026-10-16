"""ORM model registry.

Import all models here so that:
1. Alembic's ``env.py`` can import this single module and have all models
   registered on ``Base.metadata`` for autogenerate.
2. SQLAlchemy's relationship resolution works correctly (all models must be
   imported before relationships are resolved).
"""
from __future__ import annotations

from app.db.models.booking import Booking
from app.db.models.conversation import Conversation, Message
from app.db.models.document import Document, DocumentChunk
from app.db.models.guest import Guest
from app.db.models.handoff import HandoffTicket
from app.db.models.notification import NotificationLog
from app.db.models.restaurant import RestaurantTable, TableReservation
from app.db.models.room import Room, RoomType
from app.db.models.seasonal_pricing import SeasonalPricing
from app.db.models.service import Service, ServiceRequest
from app.db.models.user import User

__all__ = [
    "Booking",
    "Conversation",
    "Document",
    "DocumentChunk",
    "Guest",
    "HandoffTicket",
    "Message",
    "NotificationLog",
    "RestaurantTable",
    "Room",
    "RoomType",
    "SeasonalPricing",
    "Service",
    "ServiceRequest",
    "TableReservation",
    "User",
]
