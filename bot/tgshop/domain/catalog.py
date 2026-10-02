"""Catalog model loaded from ``shared/catalog.json`` (the single source of truth)."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from .base import CamelModel
from .enums import DeliverySlot
from .errors import ValidationFailed

Lang = Literal["ru", "en"]


class LocalizedText(CamelModel):
    ru: str
    en: str

    def get(self, lang: str | None) -> str:
        return self.en if lang == "en" else self.ru


class Category(CamelModel):
    id: str
    name: LocalizedText


class GrindOption(CamelModel):
    id: str
    name: LocalizedText


class PickupPoint(CamelModel):
    id: str
    name: LocalizedText
    hours: LocalizedText


class Variant(CamelModel):
    id: str
    label: LocalizedText
    price: int = Field(ge=0)


class ProductArt(CamelModel):
    kind: str
    colors: list[str]


class Product(CamelModel):
    id: str
    category_id: str
    name: LocalizedText
    subtitle: LocalizedText
    description: LocalizedText
    notes: list[LocalizedText] = Field(default_factory=list)
    roast: int | None = None
    grindable: bool = False
    badge: Literal["new"] | None = None
    in_stock: bool = True
    art: ProductArt
    variants: list[Variant] = Field(min_length=1)


class Catalog(CamelModel):
    categories: list[Category]
    grind_options: list[GrindOption]
    pickup_points: list[PickupPoint]
    # Courier delivery windows; the Mini App shows the very same ones.
    delivery_windows: dict[DeliverySlot, str]
    products: list[Product]

    @model_validator(mode="after")
    def _check_delivery_windows(self) -> Self:
        # Fail at startup, not with a KeyError when an order message is built.
        timed = {slot for slot in DeliverySlot if slot is not DeliverySlot.ASAP}
        if set(self.delivery_windows) != timed:
            raise ValueError(f"deliveryWindows must list exactly: {', '.join(sorted(timed))}")
        return self

    @classmethod
    def from_file(cls, path: Path) -> Catalog:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    @cached_property
    def _products(self) -> dict[str, Product]:
        return {p.id: p for p in self.products}

    @cached_property
    def _grinds(self) -> dict[str, GrindOption]:
        return {g.id: g for g in self.grind_options}

    @cached_property
    def _pickup_points(self) -> dict[str, PickupPoint]:
        return {p.id: p for p in self.pickup_points}

    def product(self, product_id: str) -> Product:
        try:
            return self._products[product_id]
        except KeyError:
            raise ValidationFailed(
                f"Unknown product '{product_id}'", code="unknown_product"
            ) from None

    def variant(self, product_id: str, variant_id: str) -> tuple[Product, Variant]:
        product = self.product(product_id)
        for variant in product.variants:
            if variant.id == variant_id:
                return product, variant
        raise ValidationFailed(
            f"Unknown variant '{variant_id}' of '{product_id}'", code="unknown_variant"
        )

    def grind(self, grind_id: str) -> GrindOption:
        try:
            return self._grinds[grind_id]
        except KeyError:
            raise ValidationFailed(f"Unknown grind '{grind_id}'", code="unknown_grind") from None

    def pickup_point(self, point_id: str) -> PickupPoint:
        try:
            return self._pickup_points[point_id]
        except KeyError:
            raise ValidationFailed(
                f"Unknown pickup point '{point_id}'", code="unknown_pickup_point"
            ) from None
