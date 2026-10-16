#!/usr/bin/env python
"""Seed the database with realistic demo data for Himalayan Heritage Hotel.

Idempotent: safe to run multiple times. Clears and re-seeds each table in the
correct FK order so the result is always deterministic.

Usage:
    python scripts/seed_db.py

Environment:
    DB_URL — asyncpg connection string (default: localhost:5433/hoteldb)
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

# Ensure the app package is importable when run from the scripts/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth.password import hash_password
from app.db.models import (
    Booking,
    Conversation,
    Document,
    Guest,
    HandoffTicket,
    Message,
    NotificationLog,
    RestaurantTable,
    Room,
    RoomType,
    SeasonalPricing,
    Service,
    ServiceRequest,
    TableReservation,
    User,
)
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_URL = os.environ.get(
    "DB_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/hoteldb",
)

# Fixed UUIDs for deterministic seeding (same IDs every run)
import uuid  # noqa: E402

ROOM_TYPE_IDS = {
    "standard": "standard",
    "deluxe": "deluxe",
    "family_suite": "family_suite",
    "conference_hall": "conference_hall",
}

ADMIN_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

TODAY = date.today()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _d(offset_days: int) -> date:
    """Return a date relative to today."""
    return TODAY + timedelta(days=offset_days)


def _past(offset_days: int) -> date:
    """Return a past date."""
    return TODAY - timedelta(days=offset_days)


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------


async def seed_room_types(session: AsyncSession) -> None:
    await session.execute(delete(RoomType))
    room_types = [
        RoomType(
            id="standard",
            name="Standard Room",
            capacity=2,
            bed_type="Queen Bed",
            base_price_npr=3500,
            amenities='["AC","WiFi","Hot Water","TV","Room Service"]',
            floor_count=4,
        ),
        RoomType(
            id="deluxe",
            name="Deluxe Room",
            capacity=2,
            bed_type="King Bed",
            base_price_npr=5500,
            amenities='["AC","WiFi","Hot Water","TV","Minibar","Room Service","Mountain View","Bathtub"]',
            floor_count=4,
        ),
        RoomType(
            id="family_suite",
            name="Family Suite",
            capacity=4,
            bed_type="1 King + 2 Single Beds",
            base_price_npr=9500,
            amenities='["AC","WiFi","Hot Water","2 TVs","Kitchenette","Living Room","Room Service","Mountain View","Bathtub"]',
            floor_count=2,
        ),
        RoomType(
            id="conference_hall",
            name="Conference Hall",
            capacity=60,
            bed_type="N/A",
            base_price_npr=25000,
            amenities='["Projector","Sound System","AC","WiFi","Whiteboard","Podium","Catering Available"]',
            floor_count=1,
        ),
    ]
    session.add_all(room_types)
    await session.flush()
    print(f"  OK {len(room_types)} room types")


async def seed_rooms(session: AsyncSession) -> None:
    await session.execute(delete(Room))
    rooms: list[Room] = []

    # Standard rooms: 101-120 (floors 1-4, 5 per floor)
    for i in range(1, 21):
        floor = ((i - 1) // 5) + 1
        rooms.append(Room(number=f"1{i:02d}", floor=floor, room_type_id="standard"))

    # Deluxe rooms: 201-214 (floors 2-4)
    for i in range(1, 15):
        floor = ((i - 1) // 5) + 2
        rooms.append(Room(number=f"2{i:02d}", floor=floor, room_type_id="deluxe"))

    # Family suites: 301-304 (floors 3-4, 2 per floor)
    for i in range(1, 5):
        floor = 3 + ((i - 1) // 2)
        rooms.append(Room(number=f"3{i:02d}", floor=floor, room_type_id="family_suite"))

    # Conference hall: C-01 (floor 1)
    rooms.append(Room(number="C-01", floor=1, room_type_id="conference_hall"))

    # Mark a few rooms under maintenance for realism
    rooms[3].status = "maintenance"   # Room 104
    rooms[10].status = "maintenance"  # Room 111

    session.add_all(rooms)
    await session.flush()
    print(f"  OK {len(rooms)} rooms (20 standard, 14 deluxe, 4 family suites, 1 conference hall)")


async def seed_seasonal_pricing(session: AsyncSession) -> None:
    await session.execute(delete(SeasonalPricing))
    # Dashain 2081 BS ~ Oct 2024
    # Tihar 2081 BS ~ Nov 2024
    # Chhath 2081 BS ~ Nov 2024
    # Dashain 2082 BS ~ Oct 2025
    # New Year (Naya Barsa) 2082 BS ~ Apr 2025
    seasonal = [
        SeasonalPricing(
            name="Dashain 2081",
            start_date=date(2024, 10, 13),
            end_date=date(2024, 10, 27),
            multiplier=Decimal("1.50"),
            room_type_id=None,  # applies to all rooms
        ),
        SeasonalPricing(
            name="Tihar 2081",
            start_date=date(2024, 11, 1),
            end_date=date(2024, 11, 5),
            multiplier=Decimal("1.40"),
            room_type_id=None,
        ),
        SeasonalPricing(
            name="Chhath 2081",
            start_date=date(2024, 11, 7),
            end_date=date(2024, 11, 9),
            multiplier=Decimal("1.30"),
            room_type_id=None,
        ),
        SeasonalPricing(
            name="Naya Barsa 2082",
            start_date=date(2025, 4, 14),
            end_date=date(2025, 4, 16),
            multiplier=Decimal("1.25"),
            room_type_id=None,
        ),
        SeasonalPricing(
            name="Dashain 2082",
            start_date=date(2025, 10, 2),
            end_date=date(2025, 10, 16),
            multiplier=Decimal("1.50"),
            room_type_id=None,
        ),
        SeasonalPricing(
            name="Tihar 2082",
            start_date=date(2025, 10, 20),
            end_date=date(2025, 10, 25),
            multiplier=Decimal("1.40"),
            room_type_id=None,
        ),
        SeasonalPricing(
            name="Chhath 2082",
            start_date=date(2025, 10, 27),
            end_date=date(2025, 10, 29),
            multiplier=Decimal("1.30"),
            room_type_id=None,
        ),
        # 2083 BS (current season). Festival dates move with the lunar calendar:
        # verify against the official panchang each year before relying on them.
        SeasonalPricing(
            name="Dashain 2083",
            start_date=date(2026, 10, 11),
            end_date=date(2026, 10, 26),
            multiplier=Decimal("1.50"),
            room_type_id=None,
        ),
        SeasonalPricing(
            name="Tihar 2083",
            start_date=date(2026, 11, 6),
            end_date=date(2026, 11, 10),
            multiplier=Decimal("1.40"),
            room_type_id=None,
        ),
        SeasonalPricing(
            name="Chhath 2083",
            start_date=date(2026, 11, 13),
            end_date=date(2026, 11, 15),
            multiplier=Decimal("1.30"),
            room_type_id=None,
        ),
        SeasonalPricing(
            name="Dashain 2083 - Family Suite Premium",
            start_date=date(2026, 10, 11),
            end_date=date(2026, 10, 26),
            multiplier=Decimal("1.75"),
            room_type_id="family_suite",
        ),
        SeasonalPricing(
            name="Naya Barsa 2084",
            start_date=date(2027, 4, 14),
            end_date=date(2027, 4, 16),
            multiplier=Decimal("1.25"),
            room_type_id=None,
        ),
        # Family suite premium for upcoming Dashain/Tihar
        SeasonalPricing(
            name="Dashain 2082 - Family Suite Premium",
            start_date=date(2025, 10, 2),
            end_date=date(2025, 10, 16),
            multiplier=Decimal("1.75"),
            room_type_id="family_suite",
        ),
        # Conference hall discount in off-season
        SeasonalPricing(
            name="Off-Season Conference Discount",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
            multiplier=Decimal("0.80"),
            room_type_id="conference_hall",
        ),
    ]
    session.add_all(seasonal)
    await session.flush()
    print(f"  OK {len(seasonal)} seasonal pricing rules")


async def seed_services(session: AsyncSession) -> None:
    await session.execute(delete(Service))
    services = [
        Service(
            type="airport_pickup",
            name="Biratnagar Airport Pickup",
            price_npr=800,
            description="Pick-up from Biratnagar Airport (BIR) to hotel. Available 24/7. Book at least 2 hours in advance.",
        ),
        Service(
            type="bus_park_pickup",
            name="Itahari Bus Park Pickup",
            price_npr=300,
            description="Pick-up from Itahari Bus Park to hotel. Available 6 AM - 10 PM.",
        ),
        Service(
            type="laundry",
            name="Laundry Service",
            price_npr=400,
            description="Same-day laundry service. Items handed in before 9 AM returned by 6 PM.",
        ),
        Service(
            type="koshi_tappu_tour",
            name="Koshi Tappu Wildlife Reserve Day Tour",
            price_npr=4500,
            description="Full-day guided tour to Koshi Tappu Wildlife Reserve. Includes transport, guide, entry fee. Departs 6 AM.",
        ),
        Service(
            type="dharan_tour",
            name="Dharan Bindabasi Temple Visit",
            price_npr=1200,
            description="Half-day guided tour to Dharan with Bindabasi temple, Pahadi bazaar, and Bijayapur Danda viewpoint. Departs 8 AM.",
        ),
    ]
    session.add_all(services)
    await session.flush()
    print(f"  OK {len(services)} services")


async def seed_restaurant_tables(session: AsyncSession) -> None:
    await session.execute(delete(RestaurantTable))
    tables = [
        RestaurantTable(name="Table 1 (Window)", capacity=2),
        RestaurantTable(name="Table 2 (Window)", capacity=2),
        RestaurantTable(name="Table 3 (Center)", capacity=4),
        RestaurantTable(name="Table 4 (Center)", capacity=4),
        RestaurantTable(name="Table 5 (Center)", capacity=6),
        RestaurantTable(name="Table 6 (Private)", capacity=8),
        RestaurantTable(name="Garden Table A", capacity=4),
        RestaurantTable(name="Garden Table B", capacity=4),
    ]
    session.add_all(tables)
    await session.flush()
    print(f"  OK {len(tables)} restaurant tables")


async def seed_guests(session: AsyncSession) -> None:
    await session.execute(delete(Guest))
    guests = [
        Guest(name="Ram Bahadur Thapa", phone="9841234567", email="ram.thapa@gmail.com", preferred_language="ne"),
        Guest(name="Sita Devi Shrestha", phone="9852345678", email="sita.shrestha@gmail.com", preferred_language="ne"),
        Guest(name="Hari Prasad Rai", phone="9863456789", email="hari.rai@yahoo.com", preferred_language="en"),
        Guest(name="Gita Kumari Tamang", phone="9874567890", email=None, preferred_language="ne"),
        Guest(name="Bikram Sharma", phone="9885678901", email="bikram.sharma@hotmail.com", preferred_language="en"),
        Guest(name="Kamala Adhikari", phone="9896789012", email=None, preferred_language="ne"),
        Guest(name="Deepak Gurung", phone="9807890123", email="deepak.gurung@gmail.com", preferred_language="en"),
        Guest(name="Anita Basnet", phone="9818901234", email="anita.basnet@gmail.com", preferred_language="ne"),
        Guest(name="Suresh Kafle", phone="9829012345", email=None, preferred_language="ne"),
        Guest(name="Manita Lama", phone="9840123456", email="manita.lama@gmail.com", preferred_language="en"),
        Guest(name="Rajesh Kumar Singh", phone="9751234567", email="rajesh.singh@gmail.com", preferred_language="en"),
        Guest(name="Sunita Yadav", phone="9762345678", email=None, preferred_language="ne"),
        Guest(name="Prakash Bhandari", phone="9773456789", email="prakash.bhandari@gmail.com", preferred_language="en"),
        Guest(name="Meena Poudel", phone="9784567890", email=None, preferred_language="ne"),
        Guest(name="Nabin Khadka", phone="9795678901", email="nabin.khadka@gmail.com", preferred_language="en"),
    ]
    session.add_all(guests)
    await session.flush()
    print(f"  OK {len(guests)} guests")
    return guests


async def seed_bookings(
    session: AsyncSession, guests: list[Guest], rooms: list[Room]
) -> list[Booking]:
    await session.execute(delete(Booking))

    # Helper: get rooms by type
    def rooms_of_type(rt: str) -> list[Room]:
        return [r for r in rooms if r.room_type_id == rt and r.status == "available"]

    std = rooms_of_type("standard")
    dlx = rooms_of_type("deluxe")
    fam = rooms_of_type("family_suite")

    bookings: list[Booking] = []

    # ---- Past bookings (confirmed / completed) ----
    past_data = [
        # (guest_idx, room, check_in_offset, nights, status, price)
        (0, std[0], -120, 3, "completed", 10500),
        (1, dlx[0], -110, 2, "completed", 11000),
        (2, fam[0], -100, 4, "completed", 38000),
        (3, std[1], -90, 1, "completed", 3500),
        (4, dlx[1], -85, 3, "completed", 16500),
        (5, std[2], -80, 2, "completed", 7000),
        (6, dlx[2], -75, 5, "completed", 27500),
        (7, fam[1], -70, 3, "completed", 28500),
        (8, std[3], -65, 2, "completed", 7000),
        (9, dlx[3], -60, 4, "completed", 22000),
        (10, std[4], -55, 1, "completed", 3500),
        (11, dlx[4], -50, 2, "completed", 11000),
        (12, std[5], -45, 3, "completed", 10500),
        (13, dlx[5], -40, 2, "completed", 11000),
        (14, fam[2], -35, 5, "completed", 47500),
        # Dashain 2081 bookings (Oct 2024) — at 1.5x multiplier
        (0, dlx[6], -370, 5, "completed", 41250),   # 5500 * 5 * 1.5
        (1, fam[3], -368, 4, "completed", 57000),   # 9500 * 4 * 1.5
        (2, std[6], -369, 3, "completed", 15750),   # 3500 * 3 * 1.5
        (3, dlx[7], -367, 6, "completed", 49500),   # 5500 * 6 * 1.5
        # Tihar 2081 (Nov 2024) — at 1.4x
        (4, std[7], -340, 3, "completed", 14700),   # 3500 * 3 * 1.4
        (5, dlx[8], -339, 4, "completed", 30800),   # 5500 * 4 * 1.4
        # Recent past (last 30 days)
        (6, std[8], -28, 2, "completed", 7000),
        (7, dlx[9], -25, 3, "completed", 16500),
        (8, std[9], -20, 1, "completed", 3500),
        (9, fam[0], -18, 2, "completed", 19000),
        (10, dlx[10], -15, 4, "completed", 22000),
        (11, std[10], -12, 2, "completed", 7000),
        (12, dlx[11], -10, 3, "completed", 16500),
        (13, std[11], -7, 1, "completed", 3500),
        (14, dlx[12], -5, 2, "completed", 11000),
    ]

    for g_idx, room, offset, nights, status, price in past_data:
        ci = _past(-offset)  # offset is already negative
        co = ci + timedelta(days=nights)
        bookings.append(Booking(
            guest_id=guests[g_idx].id,
            room_id=room.id,
            check_in=ci,
            check_out=co,
            guests_count=2,
            status=status,
            total_price_npr=price,
        ))

    # ---- Current / upcoming confirmed bookings ----
    upcoming_data = [
        (0, std[12], 2, 3, "confirmed", 10500),
        (1, dlx[0], 5, 4, "confirmed", 22000),
        (2, fam[1], 7, 5, "confirmed", 47500),
        (3, std[13], 3, 2, "confirmed", 7000),
        (4, dlx[1], 10, 3, "confirmed", 16500),
        (5, std[14], 14, 4, "confirmed", 14000),
        (6, dlx[2], 20, 2, "confirmed", 11000),
        (7, fam[2], 25, 7, "confirmed", 66500),
        (8, std[0], 30, 3, "confirmed", 10500),
        (9, dlx[3], 35, 5, "confirmed", 27500),
        (10, std[1], 45, 2, "confirmed", 7000),
        (11, dlx[4], 60, 4, "confirmed", 22000),
        (12, fam[3], 90, 3, "confirmed", 28500),
    ]

    for g_idx, room, offset, nights, status, price in upcoming_data:
        ci = _d(offset)
        co = ci + timedelta(days=nights)
        bookings.append(Booking(
            guest_id=guests[g_idx].id,
            room_id=room.id,
            check_in=ci,
            check_out=co,
            guests_count=2,
            status=status,
            total_price_npr=price,
        ))

    # ---- Pending bookings (awaiting confirmation) ----
    pending_data = [
        (13, std[2], 8, 2, "pending", 7000),
        (14, dlx[5], 15, 3, "pending", 16500),
    ]
    for g_idx, room, offset, nights, status, price in pending_data:
        ci = _d(offset)
        co = ci + timedelta(days=nights)
        bookings.append(Booking(
            guest_id=guests[g_idx].id,
            room_id=room.id,
            check_in=ci,
            check_out=co,
            guests_count=2,
            status=status,
            total_price_npr=price,
        ))

    # ---- Cancelled bookings ----
    cancelled_data = [
        (0, std[3], -50, 3, "cancelled", 0),
        (1, dlx[6], -30, 2, "cancelled", 0),
        (2, fam[0], 40, 5, "cancelled", 0),
    ]
    for g_idx, room, offset, nights, status, price in cancelled_data:
        ci = _past(-offset) if offset < 0 else _d(offset)
        co = ci + timedelta(days=nights)
        bookings.append(Booking(
            guest_id=guests[g_idx].id,
            room_id=room.id,
            check_in=ci,
            check_out=co,
            guests_count=2,
            status=status,
            total_price_npr=price,
        ))

    session.add_all(bookings)
    await session.flush()
    confirmed = len([b for b in bookings if b.status == "confirmed"])
    completed = len([b for b in bookings if b.status == "completed"])
    pending = len([b for b in bookings if b.status == "pending"])
    cancelled = len([b for b in bookings if b.status == "cancelled"])
    print(
        f"  OK {len(bookings)} bookings "
        f"({completed} completed, {confirmed} confirmed, "
        f"{pending} pending, {cancelled} cancelled)"
    )
    return bookings


async def seed_table_reservations(
    session: AsyncSession,
    guests: list[Guest],
    tables: list[RestaurantTable],
) -> None:
    await session.execute(delete(TableReservation))
    from datetime import time as dtime

    reservations = [
        TableReservation(table_id=tables[0].id, guest_id=guests[0].id, reservation_date=_d(2), reservation_time=dtime(19, 0), party_size=2, status="confirmed"),
        TableReservation(table_id=tables[2].id, guest_id=guests[1].id, reservation_date=_d(3), reservation_time=dtime(20, 0), party_size=4, status="confirmed"),
        TableReservation(table_id=tables[5].id, guest_id=guests[2].id, reservation_date=_d(5), reservation_time=dtime(12, 30), party_size=8, status="confirmed"),
        TableReservation(table_id=tables[1].id, guest_id=guests[3].id, reservation_date=_d(7), reservation_time=dtime(19, 30), party_size=2, status="confirmed"),
        TableReservation(table_id=tables[3].id, guest_id=guests[4].id, reservation_date=_d(10), reservation_time=dtime(13, 0), party_size=3, status="confirmed"),
        TableReservation(table_id=tables[6].id, guest_id=guests[5].id, reservation_date=_d(12), reservation_time=dtime(18, 0), party_size=4, status="confirmed"),
        TableReservation(table_id=tables[0].id, guest_id=guests[6].id, reservation_date=_past(3), reservation_time=dtime(20, 0), party_size=2, status="completed"),
        TableReservation(table_id=tables[4].id, guest_id=guests[7].id, reservation_date=_past(7), reservation_time=dtime(19, 0), party_size=6, status="completed"),
        TableReservation(table_id=tables[7].id, guest_id=guests[8].id, reservation_date=_past(1), reservation_time=dtime(12, 0), party_size=4, status="completed"),
        TableReservation(table_id=tables[2].id, guest_id=guests[9].id, reservation_date=_d(1), reservation_time=dtime(19, 0), party_size=2, status="confirmed"),
        TableReservation(table_id=tables[3].id, guest_id=None, reservation_date=_d(4), reservation_time=dtime(20, 30), party_size=4, status="confirmed"),
        TableReservation(table_id=tables[1].id, guest_id=guests[10].id, reservation_date=_past(2), reservation_time=dtime(13, 30), party_size=2, status="completed"),
        TableReservation(table_id=tables[5].id, guest_id=guests[11].id, reservation_date=_past(5), reservation_time=dtime(19, 0), party_size=7, status="cancelled"),
        TableReservation(table_id=tables[0].id, guest_id=guests[12].id, reservation_date=_d(15), reservation_time=dtime(19, 30), party_size=2, status="confirmed"),
        TableReservation(table_id=tables[4].id, guest_id=guests[13].id, reservation_date=_d(20), reservation_time=dtime(12, 0), party_size=5, status="confirmed"),
    ]
    session.add_all(reservations)
    await session.flush()
    print(f"  OK {len(reservations)} restaurant table reservations")


async def seed_admin_user(session: AsyncSession) -> None:
    await session.execute(delete(User))
    admin = User(
        id=ADMIN_USER_ID,
        email="admin@hotel.local",
        hashed_password=hash_password("Admin@2081"),
        role="admin",
        is_active=True,
    )
    staff = User(
        email="staff@hotel.local",
        hashed_password=hash_password("Staff@2081"),
        role="staff",
        is_active=True,
    )
    session.add_all([admin, staff])
    await session.flush()
    print("  OK 2 users (admin@hotel.local / Admin@2081, staff@hotel.local / Staff@2081)")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def seed() -> None:
    """Run all seed functions in FK-dependency order."""
    engine = create_async_engine(DB_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        async with session.begin():
            # Clear in reverse FK order first (safety net; delete cascades handle most)
            for model in [
                NotificationLog, ServiceRequest, HandoffTicket, Message,
                Booking, TableReservation, Conversation, Document,
                Guest, User, Service, RestaurantTable, SeasonalPricing,
                Room, RoomType,
            ]:
                await session.execute(delete(model))

            print("\nSeeding Himalayan Heritage Hotel demo data...")
            print("-" * 50)

            await seed_room_types(session)
            await seed_rooms(session)
            await seed_seasonal_pricing(session)
            await seed_services(session)
            await seed_restaurant_tables(session)
            await seed_admin_user(session)

            guests = await seed_guests(session)

            # Fetch rooms from session (they have IDs now after flush)
            from sqlalchemy import select
            result = await session.execute(select(Room))
            rooms = list(result.scalars().all())
            result2 = await session.execute(select(RestaurantTable))
            tables = list(result2.scalars().all())

            await seed_bookings(session, guests, rooms)
            await seed_table_reservations(session, guests, tables)

        print("-" * 50)
        print("âœ… Seed complete!\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())

