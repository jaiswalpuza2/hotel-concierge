"""Repository layer -- all async database operations.

Import repositories from this module in route handlers and tool functions::

    from app.db.repositories import BookingRepository, GuestRepository
"""
from __future__ import annotations

from app.db.repositories.booking_repo import BookingRepository
from app.db.repositories.conversation_repo import ConversationRepository
from app.db.repositories.document_repo import DocumentRepository
from app.db.repositories.guest_repo import GuestRepository
from app.db.repositories.handoff_repo import HandoffRepository
from app.db.repositories.notification_repo import NotificationRepository
from app.db.repositories.restaurant_repo import RestaurantRepository
from app.db.repositories.room_repo import RoomRepository
from app.db.repositories.service_repo import ServiceRepository

__all__ = [
    "BookingRepository",
    "ConversationRepository",
    "DocumentRepository",
    "GuestRepository",
    "HandoffRepository",
    "NotificationRepository",
    "RestaurantRepository",
    "RoomRepository",
    "ServiceRepository",
]
