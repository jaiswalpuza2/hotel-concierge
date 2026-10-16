"""Integration tests for all repository classes.

These tests run against a real PostgreSQL database. The session fixture
wraps each test in a savepoint (SAVEPOINT / ROLLBACK TO SAVEPOINT) so
tests never pollute each other and the seed data is always intact.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta

import pytest
from app.db.repositories import (
    BookingRepository,
    DocumentRepository,
    GuestRepository,
    HandoffRepository,
    RoomRepository,
)
from app.exceptions import NotFoundError, ValidationError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/hoteldb"


# ---------------------------------------------------------------------------
# Fixtures — all function-scoped to avoid event_loop scope mismatch
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn() -> AsyncGenerator[AsyncConnection, None]:
    """Yield a connection wrapped in a transaction, rolled back after the test."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.connect() as connection:
        await connection.begin()
        try:
            yield connection
        finally:
            await connection.rollback()
    await engine.dispose()


@pytest.fixture
async def session(conn: AsyncConnection) -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession bound to the rolled-back connection."""
    sess = AsyncSession(bind=conn, expire_on_commit=False)
    try:
        yield sess
    finally:
        await sess.close()


@pytest.fixture
def guest_repo(session: AsyncSession) -> GuestRepository:
    return GuestRepository(session)


@pytest.fixture
def room_repo(session: AsyncSession) -> RoomRepository:
    return RoomRepository(session)


@pytest.fixture
def booking_repo(session: AsyncSession) -> BookingRepository:
    return BookingRepository(session)


@pytest.fixture
def document_repo(session: AsyncSession) -> DocumentRepository:
    return DocumentRepository(session)


@pytest.fixture
def handoff_repo(session: AsyncSession) -> HandoffRepository:
    return HandoffRepository(session)


# ---------------------------------------------------------------------------
# GuestRepository
# ---------------------------------------------------------------------------


class TestGuestRepository:
    async def test_get_or_create_creates_new_guest(
        self, guest_repo: GuestRepository
    ) -> None:
        # Unique phone per run so committed data outside these tests
        # (e.g. smoke-test runs against the same dev database) can't collide.
        phone = "98" + uuid.uuid4().hex[:8]
        guest, created = await guest_repo.get_or_create_by_phone(
            phone=phone, name="Test Guest", preferred_language="en"
        )
        assert created is True
        assert guest.phone == phone
        assert guest.id is not None

    async def test_get_or_create_returns_existing_guest(
        self, guest_repo: GuestRepository
    ) -> None:
        # Seeded guest: Ram Bahadur Thapa / 9841234567
        guest, created = await guest_repo.get_or_create_by_phone(
            phone="9841234567", name="Different Name"
        )
        assert created is False
        assert guest.name == "Ram Bahadur Thapa"

    async def test_get_by_phone_not_found_returns_none(
        self, guest_repo: GuestRepository
    ) -> None:
        result = await guest_repo.get_by_phone("9999999999")
        assert result is None

    async def test_get_by_id_not_found_raises(
        self, guest_repo: GuestRepository
    ) -> None:
        with pytest.raises(NotFoundError) as exc:
            await guest_repo.get_by_id(uuid.uuid4())
        assert exc.value.code == "guest_not_found"


# ---------------------------------------------------------------------------
# RoomRepository
# ---------------------------------------------------------------------------


class TestRoomRepository:
    async def test_find_available_returns_results(
        self, room_repo: RoomRepository
    ) -> None:
        ci = date.today() + timedelta(days=200)
        co = ci + timedelta(days=3)
        rooms = await room_repo.find_available_rooms(ci, co, guests=2)
        assert len(rooms) > 0
        for r in rooms:
            assert r.status == "available"
            assert r.room_type_rel.capacity >= 2

    async def test_find_available_filters_by_type(
        self, room_repo: RoomRepository
    ) -> None:
        ci = date.today() + timedelta(days=200)
        co = ci + timedelta(days=2)
        rooms = await room_repo.find_available_rooms(ci, co, guests=2, room_type_id="deluxe")
        assert len(rooms) > 0
        assert all(r.room_type_id == "deluxe" for r in rooms)

    async def test_find_available_respects_capacity(
        self, room_repo: RoomRepository
    ) -> None:
        ci = date.today() + timedelta(days=200)
        co = ci + timedelta(days=2)
        rooms = await room_repo.find_available_rooms(ci, co, guests=4)
        for r in rooms:
            assert r.room_type_rel.capacity >= 4

    async def test_get_price_no_seasonal(self, room_repo: RoomRepository) -> None:
        # June 2025 has no seasonal rules
        ci = date(2025, 6, 1)
        co = date(2025, 6, 4)  # 3 nights
        result = await room_repo.get_price_with_seasonal("standard", ci, co)
        assert result["nights"] == 3
        assert result["base_price_npr"] == 3500
        assert result["multiplier"] == "1.00"
        assert result["total_npr"] == 10500
        assert result["seasonal_name"] is None

    async def test_get_price_dashain_multiplier(self, room_repo: RoomRepository) -> None:
        # Dashain 2082: Oct 2-16 2025, multiplier 1.5
        ci = date(2025, 10, 5)
        co = date(2025, 10, 8)  # 3 nights
        result = await room_repo.get_price_with_seasonal("standard", ci, co)
        assert result["multiplier"] == "1.50"
        assert result["seasonal_name"] is not None
        assert "Dashain" in result["seasonal_name"]
        assert result["total_npr"] == int(3500 * 3 * 1.5)

    async def test_get_room_type_not_found_raises(
        self, room_repo: RoomRepository
    ) -> None:
        with pytest.raises(NotFoundError) as exc:
            await room_repo.get_room_type("nonexistent")
        assert exc.value.code == "room_type_not_found"


# ---------------------------------------------------------------------------
# BookingRepository
# ---------------------------------------------------------------------------


class TestBookingRepository:
    async def test_create_booking_success(
        self,
        booking_repo: BookingRepository,
        guest_repo: GuestRepository,
        room_repo: RoomRepository,
    ) -> None:
        guest, _ = await guest_repo.get_or_create_by_phone(
            phone="9800000099", name="Integration Test Guest"
        )
        ci = date.today() + timedelta(days=300)
        co = ci + timedelta(days=2)
        rooms = await room_repo.find_available_rooms(ci, co, guests=2, room_type_id="standard")
        assert len(rooms) > 0

        booking = await booking_repo.create_booking(
            guest_id=guest.id,
            room_id=rooms[0].id,
            check_in=ci,
            check_out=co,
            guests_count=2,
            total_price_npr=7000,
        )
        assert booking.status == "confirmed"
        assert booking.id is not None

    async def test_create_booking_invalid_dates_raises(
        self,
        booking_repo: BookingRepository,
        guest_repo: GuestRepository,
    ) -> None:
        guest, _ = await guest_repo.get_or_create_by_phone(
            phone="9800000098", name="Test Guest 2"
        )
        today = date.today()
        with pytest.raises(ValidationError) as exc:
            await booking_repo.create_booking(
                guest_id=guest.id,
                room_id=1,
                check_in=today + timedelta(days=5),
                check_out=today + timedelta(days=3),  # before check_in
                guests_count=2,
                total_price_npr=7000,
            )
        assert exc.value.code == "invalid_dates"

    async def test_get_by_id_not_found_raises(
        self, booking_repo: BookingRepository
    ) -> None:
        with pytest.raises(NotFoundError) as exc:
            await booking_repo.get_by_id(uuid.uuid4())
        assert exc.value.code == "booking_not_found"

    async def test_get_by_id_and_wrong_phone_raises(
        self, booking_repo: BookingRepository
    ) -> None:
        with pytest.raises(NotFoundError):
            await booking_repo.get_by_id_and_phone(uuid.uuid4(), "9999999999")

    async def test_cancel_full_refund_over_48h(
        self,
        booking_repo: BookingRepository,
        guest_repo: GuestRepository,
        room_repo: RoomRepository,
    ) -> None:
        guest, _ = await guest_repo.get_or_create_by_phone(
            phone="9800000097", name="Cancel Test Guest"
        )
        ci = date.today() + timedelta(days=10)  # >48h away -- full refund
        co = ci + timedelta(days=2)
        rooms = await room_repo.find_available_rooms(ci, co, guests=2, room_type_id="standard")
        assert len(rooms) > 0

        booking = await booking_repo.create_booking(
            guest_id=guest.id,
            room_id=rooms[0].id,
            check_in=ci,
            check_out=co,
            guests_count=2,
            total_price_npr=7000,
        )
        result = await booking_repo.cancel_booking(booking)
        assert result["status"] == "cancelled"
        assert result["refund_percentage"] == 100
        assert result["refund_amount_npr"] == 7000

    async def test_cancel_already_cancelled_raises(
        self,
        booking_repo: BookingRepository,
        guest_repo: GuestRepository,
        room_repo: RoomRepository,
    ) -> None:
        guest, _ = await guest_repo.get_or_create_by_phone(
            phone="9800000096", name="Double Cancel Guest"
        )
        ci = date.today() + timedelta(days=20)
        co = ci + timedelta(days=2)
        rooms = await room_repo.find_available_rooms(ci, co, guests=2, room_type_id="standard")
        booking = await booking_repo.create_booking(
            guest_id=guest.id,
            room_id=rooms[0].id,
            check_in=ci,
            check_out=co,
            guests_count=2,
            total_price_npr=7000,
        )
        await booking_repo.cancel_booking(booking)
        with pytest.raises(ValidationError) as exc:
            await booking_repo.cancel_booking(booking)
        assert exc.value.code == "invalid_booking_status"


# ---------------------------------------------------------------------------
# DocumentRepository
# ---------------------------------------------------------------------------


class TestDocumentRepository:
    async def test_create_document(self, document_repo: DocumentRepository) -> None:
        doc = await document_repo.create(
            filename="test_doc_123.md",
            original_name="Hotel Policies.md",
            mime_type="text/markdown",
            size_bytes=4096,
        )
        assert doc.id is not None
        assert doc.status == "queued"
        assert doc.chunk_count == 0

    async def test_update_status_indexed(self, document_repo: DocumentRepository) -> None:
        doc = await document_repo.create(
            filename="test_doc_456.pdf",
            original_name="FAQ.pdf",
            mime_type="application/pdf",
            size_bytes=102400,
        )
        await document_repo.update_status(doc.id, "indexed", chunk_count=42)
        updated = await document_repo.get_by_id(doc.id)
        assert updated.status == "indexed"
        assert updated.chunk_count == 42
        assert updated.indexed_at is not None

    async def test_update_status_failed(self, document_repo: DocumentRepository) -> None:
        doc = await document_repo.create(
            filename="bad_doc.pdf",
            original_name="Corrupted.pdf",
            mime_type="application/pdf",
            size_bytes=512,
        )
        await document_repo.update_status(doc.id, "failed", error_message="PDF parse error")
        updated = await document_repo.get_by_id(doc.id)
        assert updated.status == "failed"
        assert updated.error_message == "PDF parse error"

    async def test_get_by_id_not_found_raises(
        self, document_repo: DocumentRepository
    ) -> None:
        with pytest.raises(NotFoundError) as exc:
            await document_repo.get_by_id(uuid.uuid4())
        assert exc.value.code == "document_not_found"

    async def test_delete_removes_document(
        self, document_repo: DocumentRepository
    ) -> None:
        doc = await document_repo.create(
            filename="delete_me.md",
            original_name="ToDelete.md",
            mime_type="text/markdown",
            size_bytes=100,
        )
        doc_id = doc.id
        await document_repo.delete_with_chunks(doc_id)
        with pytest.raises(NotFoundError):
            await document_repo.get_by_id(doc_id)


# ---------------------------------------------------------------------------
# HandoffRepository
# ---------------------------------------------------------------------------


async def _make_conversation(session: AsyncSession) -> uuid.UUID:
    """Insert a minimal Conversation row for FK references in handoff tests."""
    from app.db.models.conversation import Conversation
    conv = Conversation(
        session_id=uuid.uuid4(),
        detected_language="en",
        status="active",
    )
    session.add(conv)
    await session.flush()
    return conv.id


class TestHandoffRepository:
    async def test_create_ticket(
        self, handoff_repo: HandoffRepository, session: AsyncSession
    ) -> None:
        conv_id = await _make_conversation(session)
        ticket = await handoff_repo.create_ticket(
            conversation_id=conv_id,
            trigger_reason="complaint_detected",
            conversation_summary="Guest complained about noise.",
            guest_language="en",
        )
        assert ticket.id is not None
        assert ticket.status == "open"
        assert ticket.trigger_reason == "complaint_detected"

    async def test_reply_advances_to_in_progress(
        self, handoff_repo: HandoffRepository, session: AsyncSession
    ) -> None:
        conv_id = await _make_conversation(session)
        ticket = await handoff_repo.create_ticket(
            conversation_id=conv_id,
            trigger_reason="user_requested_human",
            conversation_summary="User asked to speak to staff.",
            guest_language="ne",
        )
        staff_id = uuid.UUID("00000000-0000-0000-0000-000000000001")  # seeded admin
        updated = await handoff_repo.reply_and_set_in_progress(
            ticket.id, "We will help you shortly.", staff_id
        )
        assert updated.status == "in_progress"
        assert updated.manager_reply == "We will help you shortly."

    async def test_resolve_ticket(
        self, handoff_repo: HandoffRepository, session: AsyncSession
    ) -> None:
        conv_id = await _make_conversation(session)
        ticket = await handoff_repo.create_ticket(
            conversation_id=conv_id,
            trigger_reason="two_tool_failures",
            conversation_summary="DB errors occurred.",
            guest_language="en",
        )
        staff_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        resolved = await handoff_repo.resolve(ticket.id, staff_id)
        assert resolved.status == "resolved"
        assert resolved.resolved_at is not None

    async def test_get_by_id_not_found_raises(
        self, handoff_repo: HandoffRepository
    ) -> None:
        with pytest.raises(NotFoundError) as exc:
            await handoff_repo.get_by_id(uuid.uuid4())
        assert exc.value.code == "ticket_not_found"
