"""ServiceRepository -- extra hotel services (pickup, laundry, tours)."""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.service import Service, ServiceRequest
from app.exceptions import NotFoundError

logger = structlog.get_logger(__name__)


class ServiceRepository:
    """Async DB operations for services and service requests."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_type(self, service_type: str) -> Service:
        """Fetch a service by its slug.

        Raises:
            NotFoundError: Unknown service type.
        """
        result = await self._session.execute(select(Service).where(Service.type == service_type))
        service = result.scalar_one_or_none()
        if service is None:
            raise NotFoundError(
                f"Service '{service_type}' is not offered",
                code="service_not_found",
                details={"service_type": service_type},
            )
        return service

    async def create_request(
        self,
        *,
        service: Service,
        booking_id: uuid.UUID | None,
        details: str | None,
    ) -> ServiceRequest:
        """Create a pending service request."""
        request = ServiceRequest(
            booking_id=booking_id, service_id=service.id, details=details, status="pending"
        )
        self._session.add(request)
        await self._session.flush()
        logger.info("service.requested", service=service.type, request_id=str(request.id))
        return request
