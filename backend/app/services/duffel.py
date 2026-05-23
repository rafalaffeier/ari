from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


class FlightSearchRequest(BaseModel):
    origin: str = Field(..., min_length=3, max_length=3)
    destination: str = Field(..., min_length=3, max_length=3)
    departure_date: date
    return_date: date | None = None
    passengers: int = Field(1, ge=1, le=9)
    cabin_class: str = Field("economy")
    max_results: int = Field(5, ge=1, le=20)

    @field_validator("origin", "destination")
    @classmethod
    def normalize_iata_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("must be a 3-letter IATA airport or city code")
        return normalized

    @field_validator("cabin_class")
    @classmethod
    def validate_cabin_class(cls, value: str) -> str:
        normalized = value.strip().lower()
        valid = {"economy", "premium_economy", "business", "first"}
        if normalized not in valid:
            raise ValueError(f"must be one of: {', '.join(sorted(valid))}")
        return normalized


class FlightSegment(BaseModel):
    origin: str
    destination: str
    departing_at: str | None = None
    arriving_at: str | None = None
    marketing_carrier: str | None = None
    operating_carrier: str | None = None
    flight_number: str | None = None


class FlightOffer(BaseModel):
    id: str
    total_amount: str
    total_currency: str
    owner: str | None = None
    live_mode: bool
    expires_at: str | None = None
    slices: list[list[FlightSegment]]
    booking_available: bool


class FlightSearchResponse(BaseModel):
    provider: str = "duffel"
    live_mode: bool
    offer_request_id: str
    results: list[FlightOffer]
    raw_result_count: int


async def search_flights(body: FlightSearchRequest) -> FlightSearchResponse:
    if not settings.DUFFEL_ACCESS_TOKEN.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUFFEL_ACCESS_TOKEN is not configured.",
        )

    payload = _build_offer_request_payload(body)
    timeout = max(5.0, settings.DUFFEL_SUPPLIER_TIMEOUT_MS / 1000 + 5)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{settings.DUFFEL_API_BASE_URL.rstrip('/')}/air/offer_requests",
                headers={
                    "Authorization": f"Bearer {settings.DUFFEL_ACCESS_TOKEN}",
                    "Duffel-Version": settings.DUFFEL_API_VERSION,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json={"data": payload},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Duffel request failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Duffel returned {response.status_code}: {_safe_error_detail(response)}",
        )

    data = response.json().get("data", {})
    return normalize_offer_request(data, max_results=body.max_results)


def _build_offer_request_payload(body: FlightSearchRequest) -> dict[str, Any]:
    slices = [
        {
            "origin": body.origin,
            "destination": body.destination,
            "departure_date": body.departure_date.isoformat(),
        }
    ]
    if body.return_date:
        slices.append(
            {
                "origin": body.destination,
                "destination": body.origin,
                "departure_date": body.return_date.isoformat(),
            }
        )

    return {
        "slices": slices,
        "passengers": [{"type": "adult"} for _ in range(body.passengers)],
        "cabin_class": body.cabin_class,
        "supplier_timeout": settings.DUFFEL_SUPPLIER_TIMEOUT_MS,
    }


def normalize_offer_request(data: dict[str, Any], max_results: int = 5) -> FlightSearchResponse:
    offers = data.get("offers") or []
    normalized = [_normalize_offer(offer) for offer in offers]
    normalized.sort(key=lambda offer: _decimal_or_high(offer.total_amount))
    limited = normalized[:max(1, max_results)]
    return FlightSearchResponse(
        live_mode=bool(data.get("live_mode", settings.DUFFEL_TEST_MODE is False)),
        offer_request_id=str(data.get("id") or ""),
        results=limited,
        raw_result_count=len(offers),
    )


def _normalize_offer(offer: dict[str, Any]) -> FlightOffer:
    slices = []
    for slice_item in offer.get("slices") or []:
        segments = []
        for segment in slice_item.get("segments") or []:
            marketing_carrier = segment.get("marketing_carrier") or {}
            operating_carrier = segment.get("operating_carrier") or {}
            origin = segment.get("origin") or {}
            destination = segment.get("destination") or {}
            segments.append(
                FlightSegment(
                    origin=str(origin.get("iata_code") or origin.get("name") or ""),
                    destination=str(destination.get("iata_code") or destination.get("name") or ""),
                    departing_at=segment.get("departing_at"),
                    arriving_at=segment.get("arriving_at"),
                    marketing_carrier=marketing_carrier.get("name"),
                    operating_carrier=operating_carrier.get("name"),
                    flight_number=segment.get("marketing_carrier_flight_number"),
                )
            )
        slices.append(segments)

    owner = offer.get("owner") or {}
    return FlightOffer(
        id=str(offer.get("id") or ""),
        total_amount=str(offer.get("total_amount") or "0"),
        total_currency=str(offer.get("total_currency") or ""),
        owner=owner.get("name"),
        live_mode=bool(offer.get("live_mode", settings.DUFFEL_TEST_MODE is False)),
        expires_at=offer.get("expires_at"),
        slices=slices,
        booking_available=bool(offer.get("available_services") is not None or offer.get("id")),
    )


def _decimal_or_high(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return Decimal("999999999")


def _safe_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]
    return str(payload.get("errors") or payload)[:800]
