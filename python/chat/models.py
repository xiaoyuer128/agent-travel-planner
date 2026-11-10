from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    departure_city: str | None = Field(None, min_length=1, max_length=30)
    destination: str | None = Field(None, min_length=1, max_length=30)
    budget: float | None = Field(None, gt=0, le=1_000_000)
    num_travelers: int | None = Field(None, ge=1, le=10, strict=True)
    start_date: date | None = None
    days: int | None = Field(None, ge=1, le=30, strict=True)
    interests: list[str] = Field(default_factory=list, max_length=10)
    pace: str | None = Field(None,max_length=20)
    transport: str | None = Field(None,max_length=20)
    walking: str | None = Field(None,max_length=20)
    needs: str | None = Field(None,max_length=300)
    selected_spots: list[str] = Field(default_factory=list,max_length=10)


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    revision: int = Field(ge=0)
    patch: Preferences | None = None
    action: Literal["auto", "hotel_cheaper", "hotel_better", "activity"] = "auto"
    generate: bool = True


REQUIRED = {
    "departure_city": "出发城市", "destination": "目的地", "budget": "总预算",
    "num_travelers": "出行人数", "start_date": "出发日期（YYYY-MM-DD）", "days": "旅行天数",
}
