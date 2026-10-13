from datetime import datetime
from typing import Literal

from ninja import Field, Schema
from pydantic import field_validator


class PlaceIn(Schema):
    label: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class TripIn(Schema):
    origin: PlaceIn
    destination: PlaceIn
    departure: datetime
    load_lb: int = Field(gt=0, le=150_000)
    interval_mi: Literal[10, 25, 50] = 25

    @field_validator("departure")
    @classmethod
    def departure_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Departure must include a time zone offset.")
        return value
