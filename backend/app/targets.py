"""Customer target properties: the input to a campaign (loop step 1, a person's decision).

The default values are ILLUSTRATIVE, not real customer data. A real customer sets their own.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CustomerTargets(BaseModel):
    service_temp_c: int = Field(1200, ge=500, le=2500, description="High temperature performance: minimum service temperature, degrees C")
    min_yield_strength_mpa: int = Field(600, ge=50, le=3000, description="Strength: minimum yield strength at room temperature, MPa")
    max_hafnium_at_pct: float = Field(0.0, ge=0.0, le=10.0, description="Reduced hafnium: maximum Hf, atomic percent (0 means none)")


DEFAULT_TARGETS: dict = CustomerTargets().model_dump()


def describe(targets: dict | None) -> str:
    """One line for the planner prompt."""
    if not targets:
        return ""
    return (
        f"Customer targets: service temperature at least {targets['service_temp_c']} C, "
        f"yield strength at least {targets['min_yield_strength_mpa']} MPa, "
        f"hafnium at most {targets['max_hafnium_at_pct']} at%."
    )
