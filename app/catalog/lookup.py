"""Catalog lookup helpers — resolve single products and lookup-with-rerank."""

from __future__ import annotations

from typing import Optional

from app.catalog.catalog import ShopCatalog
from app.catalog.models import ProductQuery


def resolve_component(name: str, category: str, catalog: ShopCatalog) -> Optional[dict]:
    """Look up one component by name and category. Returns None if name is
    empty/'none' or no match found in the catalog."""
    if not name or name.strip().lower() == "none":
        return None
    normalized_name = name.lower().replace("-", " ")
    results = catalog.search_products(ProductQuery(text=normalized_name, category=category, limit=1))
    return results[0].as_legacy_dict() if results else None


def lookup_and_rerank(
    catalog: ShopCatalog,
    lookup_term: str,
    search_query: str,
    category: str | None,
    top_k: int = 3,
    rerank_top_k: int = 2,
) -> list[dict]:
    """Search catalog, fallback to search_query if needed, then re-rank by
    name-token overlap.  Used by specification and price_check flows."""
    matched_items = [
        item.as_legacy_dict()
        for item in catalog.search_products(
            ProductQuery(text=lookup_term, category=category, limit=top_k)
        )
    ]

    if not matched_items and lookup_term != search_query:
        matched_items = [
            item.as_legacy_dict()
            for item in catalog.search_products(
                ProductQuery(text=search_query, category=category, limit=top_k)
            )
        ]

    if matched_items and len(matched_items) > 1:
        lookup_clean = lookup_term.replace("-", " ").lower()
        lookup_tokens = [w for w in lookup_clean.split() if len(w) > 1]

        def name_match_score(item: dict) -> int:
            name = (item.get("tên") or item.get("name") or "").replace("-", " ").lower()
            exact_bonus = 100 if lookup_clean in name or all(t in name for t in lookup_tokens) else 0
            return exact_bonus + sum(1 for t in lookup_tokens if t in name)

        matched_items.sort(key=name_match_score, reverse=True)
        matched_items = matched_items[:rerank_top_k]

    return matched_items
