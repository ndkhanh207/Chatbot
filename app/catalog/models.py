from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProductQuery(BaseModel):
    text: str = ""
    category: str | None = None
    brand: str | None = None
    model: str | None = None
    price_min: int | None = Field(default=None, ge=0)
    price_max: int | None = Field(default=None, ge=0)
    order: Literal["asc", "desc"] | None = None
    limit: int = Field(default=5, ge=1, le=1000)


class BuildConstraints(BaseModel):
    required_components: dict[str, str] = Field(default_factory=dict)
    preferred_components: dict[str, list[str]] = Field(default_factory=dict)
    excluded_brands: list[str] = Field(default_factory=list)


class BuildQuery(BaseModel):
    text: str = ""
    budget: int | None = Field(default=None, ge=0)
    constraints: BuildConstraints = Field(default_factory=BuildConstraints)
    excluded_ids: set[str] = Field(default_factory=set)
    priority: str | None = None
    price_order: Literal["asc", "desc"] | None = None
    limit: int = Field(default=5, ge=1, le=100)


class BuildEntityMatches(BaseModel):
    components: dict[str, str] = Field(default_factory=dict)
    brands: dict[str, set[str]] = Field(default_factory=dict)


class ComponentResolution(BaseModel):
    category: str
    raw_value: str
    canonical_model: str | None
    candidate_models: list[str]
    status: Literal["resolved", "ambiguous", "not_found"]


class ProductRecord(BaseModel):
    product_id: str
    category: str
    name: str
    brand: str | None
    price: int
    attributes: dict[str, object] = Field(default_factory=dict)

    def as_legacy_dict(self) -> dict:
        return {
            **self.attributes,
            "product_id": self.product_id,
            "category": self.category,
            "name": self.name,
            "tên": self.name,
            "brand": self.brand or "",
            "price": self.price,
            "giá": self.price,
        }


class BuildPart(BaseModel):
    category: str
    model: str
    brand: str | None = None
    price: int = 0
    tier: str | None = None
    attributes: dict[str, object] = Field(default_factory=dict)


class BuildRecord(BaseModel):
    build_id: str
    components: dict[str, BuildPart]
    assembly_fee: int
    total_price: int
    detailed_purpose: str = ""
    notes: str = ""
    source: Literal["catalog", "preset", "promotion"] = "catalog"
    attributes: dict[str, object] = Field(default_factory=dict)

    def as_legacy_dict(self) -> dict:
        values = {
            **self.attributes,
            "BuildID": self.build_id,
            "Assembly_Fee": self.assembly_fee,
            "Total_Price": self.total_price,
            "Detailed_Purpose": self.detailed_purpose,
            "Build_Notes": self.notes,
        }
        field_prefixes = {"cpu": "CPU", "gpu": "GPU", "mainboard": "Motherboard"}
        for key, part in self.components.items():
            prefix = field_prefixes.get(key, key.capitalize())
            values[f"{prefix}_Model"] = part.model
            values[f"{prefix}_Brand"] = part.brand or ""
            values[f"Component_Price_{prefix}"] = part.price
            if part.tier is not None:
                values[f"{prefix}_Tier"] = part.tier
        return values


class CatalogStatus(BaseModel):
    mode: Literal["semantic", "keyword-only"]
    product_count: int
    build_count: int
    product_fingerprint: str
    build_fingerprint: str
