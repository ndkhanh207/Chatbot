from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, cast

import pandas as pd

from app.catalog.models import (
    BuildEntityMatches,
    BuildPart,
    BuildQuery,
    BuildRecord,
    CatalogStatus,
    ProductQuery,
    ProductRecord,
    ComponentResolution,
)
from app.catalog.semantic import SemanticDocument, SemanticIndex
from app.pc_builder.presets import PRESET_CONFIGS

PRODUCT_COLLECTION = "products_v1"
BUILD_COLLECTION = "builds_v4"

logger = logging.getLogger(__name__)

CATEGORY_ALIASES = {
    "CPU": "bộ vi xử lý vi xử lý processor chip",
    "GPU": "card đồ họa card màn hình vga graphics",
    "MAINBOARD": "mainboard bo mạch chủ main motherboard",
    "RAM": "bộ nhớ ram memory",
    "SSD": "ổ cứng ssd lưu trữ storage",
    "PSU": "nguồn máy tính psu power supply",
}


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold().replace("đ", "d"))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _number(value: Any) -> int:
    try:
        if value is None or pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _optional_text(value: object) -> str | None:
    cleaned = str(_clean_value(value)).strip()
    return cleaned or None


def _clean_value(value: object) -> object:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return ""
    if hasattr(value, "item"):
        return getattr(value, "item")()
    return value


def _brand(name: str) -> str | None:
    normalized = normalize(name)
    if not normalized:
        return None
    known = (
        "amd", "intel", "asus", "msi", "gigabyte", "asrock", "zotac",
        "palit", "galax", "sapphire", "powercolor", "biostar", "evga",
    )
    for brand in known:
        if normalized == brand or normalized.startswith(f"{brand} "):
            return brand.upper()
    return normalized.split()[0].upper()


def _fingerprint(records: list[dict], config: str) -> str:
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{config}\n{payload}".encode("utf-8")).hexdigest()


def _model_ngrams(models: set[str]) -> set[tuple[str, ...]]:
    ngrams = set()
    for model in models:
        tokens = model.split()
        for start in range(len(tokens)):
            for end in range(start + 1, min(len(tokens), start + 8) + 1):
                phrase = tuple(tokens[start:end])
                has_digit = any(char.isdigit() for token in phrase for char in token)
                if has_digit and phrase and (len(phrase) > 1 or len(phrase[0]) >= 3):
                    ngrams.add(phrase)
                    if len(phrase) > 1:
                        ngrams.add(("".join(phrase),))
    return ngrams


def _model_matches(model: object, wanted: object) -> bool:
    model_text = normalize(model)
    wanted_text = normalize(wanted)
    return (
        wanted_text in model_text
        or wanted_text.replace(" ", "") in model_text.replace(" ", "")
    )


class ShopCatalog:
    """Single authority for shop data loading, filtering, and semantic ranking."""

    def __init__(
        self,
        products: list[ProductRecord],
        builds: list[BuildRecord],
        semantic_index: SemanticIndex | None = None,
        embedding_config: str = "keyword-only",
    ) -> None:
        self._products = {record.product_id: record for record in products}
        self._builds = {record.build_id.casefold(): record for record in builds}
        if len(self._products) != len(products) or len(self._builds) != len(builds):
            logger.warning("Duplicate canonical catalog IDs detected. They will be merged by keeping the last occurrence.")

        self._semantic_index = semantic_index
        self._build_brand_categories: dict[str, tuple[str, set[str]]] = {}
        component_models: dict[str, set[str]] = {
            "cpu": set(), "gpu": set(), "mainboard": set(),
        }
        for record in builds:
            for category, part in record.components.items():
                component_models.setdefault(category, set()).add(normalize(part.model))
                if not part.brand:
                    continue
                _, categories = self._build_brand_categories.setdefault(
                    normalize(part.brand), (part.brand, set())
                )
                categories.add(category)
        for record in products:
            category = record.category.casefold()
            if category in component_models:
                component_models[category].add(normalize(record.name))
        self._build_model_ngrams = {
            category: _model_ngrams(models)
            for category, models in component_models.items()
        }
        self._product_fingerprint = _fingerprint(
            [record.model_dump() for record in products], embedding_config
        )
        self._build_fingerprint = _fingerprint(
            [record.model_dump() for record in builds], embedding_config
        )
        self._semantic_mode = semantic_index is not None
        self._initialize_index()

    @classmethod
    def load(
        cls,
        data_directory: str | Path,
        semantic_index: SemanticIndex | None = None,
        embedding_config: str = "keyword-only",
    ) -> "ShopCatalog":
        data_directory = Path(data_directory)
        category_names = {
            "cpu": "CPU",
            "gpu": "GPU",
            "motherboard": "MAINBOARD",
            "mainboard": "MAINBOARD",
        }
        csv_files = {
            path.stem.casefold(): path
            for path in data_directory.glob("*.csv")
            if not path.stem.casefold().startswith("pc_build_data")
        }
        missing = {"cpu", "gpu", "motherboard"} - csv_files.keys()
        if missing:
            raise FileNotFoundError(f"Missing catalog CSV files: {', '.join(sorted(missing))}")
        products = []
        for stem, path in sorted(csv_files.items()):
            category = category_names.get(stem, normalize(stem).replace(" ", "_").upper())
            products.extend(cls._read_products(path, category))
        build_path = data_directory / "Pc_build_data_v3.csv"
        builds = cls._read_builds(build_path) if build_path.exists() else []
        builds.extend(cls._read_presets())
        if not products:
            raise ValueError("Catalog contains no products")
        if build_path.exists() and not builds:
            raise ValueError("Catalog contains no builds")
        return cls(products, builds, semantic_index, embedding_config)

    @staticmethod
    def _read_products(path: Path, category: str) -> list[ProductRecord]:
        records = []
        for row in pd.read_csv(path).to_dict(orient="records"):
            attributes: dict[str, Any] = {str(key): _clean_value(value) for key, value in row.items()}
            name = str(attributes.get("tên") or attributes.get("name") or "").strip()
            if not name:
                raise ValueError(f"Product without name in {path.name}")
            price = _number(attributes.get("giá", attributes.get("price", 0)))
            if price <= 0:
                raise ValueError(f"Invalid price for product '{name}' in {path.name}")
            attributes["giá"] = price
            product_id = f"product:{category.casefold()}:{normalize(name).replace(' ', '-')}"
            records.append(ProductRecord(
                product_id=product_id,
                category=category,
                name=name,
                brand=_brand(name),
                price=price,
                attributes=attributes,
            ))
        return records

    @staticmethod
    def _read_builds(path: Path) -> list[BuildRecord]:
        records = []
        for row in pd.read_csv(path).to_dict(orient="records"):
            attributes: dict[str, Any] = {str(key): _clean_value(value) for key, value in row.items()}
            build_id = str(attributes.get("BuildID") or "").strip()
            if not build_id:
                raise ValueError(f"Build without BuildID in {path.name}")
            components = {
                "cpu": BuildPart(
                    category="CPU", model=str(attributes.get("CPU_Model", "")),
                    brand=str(attributes.get("CPU_Brand", "")) or None,
                    price=_number(attributes.get("Component_Price_CPU")),
                    tier=_optional_text(attributes.get("CPU_Tier")),
                ),
                "mainboard": BuildPart(
                    category="MAINBOARD", model=str(attributes.get("Motherboard_Model", "")),
                    brand=str(attributes.get("Motherboard_Brand", "")) or None,
                    price=_number(attributes.get("Component_Price_Motherboard")),
                    tier=_optional_text(attributes.get("Motherboard_Tier")),
                    attributes={"chipset": attributes.get("Motherboard_Chipset", "")},
                ),
                "gpu": BuildPart(
                    category="GPU", model=str(attributes.get("GPU_Model", "")),
                    brand=str(attributes.get("GPU_Brand", "")) or None,
                    price=_number(attributes.get("Component_Price_GPU")),
                    tier=_optional_text(attributes.get("GPU_Tier")),
                ),
            }
            if any(not part.model for part in components.values()):
                raise ValueError(f"Build '{build_id}' has a missing component model")
            total_price = _number(attributes.get("Total_Price"))
            if total_price <= 0:
                raise ValueError(f"Build '{build_id}' has an invalid total price")
            records.append(BuildRecord(
                build_id=build_id,
                components=components,
                assembly_fee=_number(attributes.get("Assembly_Fee")),
                total_price=total_price,
                detailed_purpose=str(attributes.get("Detailed_Purpose", "")),
                notes=str(attributes.get("Build_Notes", "")),
                source="catalog",
                attributes=attributes,
            ))
        return records

    @staticmethod
    def _read_presets() -> list[BuildRecord]:
        records = []
        for preset in PRESET_CONFIGS:
            components = {}
            if preset.get("cpu"):
                components["cpu"] = BuildPart(category="CPU", model=str(preset["cpu"]), brand=_brand(str(preset["cpu"])))
            if preset.get("gpu"):
                components["gpu"] = BuildPart(category="GPU", model=str(preset["gpu"]), brand=_brand(str(preset["gpu"])))
            if preset.get("mainboard"):
                components["mainboard"] = BuildPart(category="MAINBOARD", model=str(preset["mainboard"]), brand=_brand(str(preset["mainboard"])))
            
            records.append(BuildRecord(
                build_id=str(preset["id"]),
                components=components,
                assembly_fee=0,
                total_price=_number(preset["budget"]),
                detailed_purpose=" ".join(cast(list[str], preset.get("purposes", []))),
                source="preset",
                attributes=dict(preset),
            ))
        return records

    def _initialize_index(self) -> None:
        if self._semantic_index is None:
            return
        try:
            self._semantic_index.ensure_collection(
                PRODUCT_COLLECTION,
                self._product_fingerprint,
                [self._product_document(record) for record in self._products.values()],
            )
            self._semantic_index.ensure_collection(
                BUILD_COLLECTION,
                self._build_fingerprint,
                [self._build_document(record) for record in self._builds.values()],
            )
        except Exception as error:
            print(f"[CATALOG] semantic index unavailable: {error}")
            self._semantic_mode = False

    @staticmethod
    def _product_document(record: ProductRecord) -> SemanticDocument:
        specs = " | ".join(
            f"{key}: {value}" for key, value in record.attributes.items()
            if normalize(key) not in {"gia", "price"} and value not in ("", 0)
        )
        text = (
            f"Tên {record.name}. Danh mục {record.category}: {CATEGORY_ALIASES.get(record.category, '')}. "
            f"Hãng {record.brand or ''}. "
            f"Thông số và đặc điểm: {specs}. Phù hợp nhu cầu theo các thông số trên."
        )
        return SemanticDocument(
            record.product_id, text,
            {"record_id": record.product_id, "category": record.category, "brand": record.brand or ""},
        )

    @staticmethod
    def _build_search_text(record: BuildRecord) -> str:
        parts = ", ".join(
            f"{key}: {part.model}; brand: {part.brand or ''}"
            for key, part in record.components.items()
        )
        return (
            f"Mã bộ {record.build_id}. Linh kiện {parts}. "
            f"Mục đích: {record.detailed_purpose}. "
            f"Công việc chính: {record.attributes.get('Primary_Workload', '')}. "
            f"Thể loại: {record.attributes.get('Purpose_Category', '')}. "
            f"Từ khóa: {record.attributes.get('RAG_Keywords', '')}."
        )

    @classmethod
    def _build_document(cls, record: BuildRecord) -> SemanticDocument:
        return SemanticDocument(record.build_id, cls._build_search_text(record), {
            "record_id": record.build_id,
            "total_price": record.total_price,
            "purpose_category": str(record.attributes.get("Purpose_Category", "")),
            "purpose_code": str(record.attributes.get("Purpose_Code", "")),
        })

    def search_products(self, query: ProductQuery) -> list[ProductRecord]:
        candidates = list(self._products.values())
        if query.category:
            category = query.category.upper().strip()
            candidates = [record for record in candidates if record.category == category]
        if query.brand:
            brand = normalize(query.brand)
            candidates = [record for record in candidates if brand in normalize(record.brand)]
        if query.model:
            model = normalize(query.model)
            candidates = [record for record in candidates if model in normalize(record.name)]
        if query.price_min is not None:
            candidates = [record for record in candidates if record.price >= query.price_min]
        if query.price_max is not None:
            candidates = [record for record in candidates if record.price <= query.price_max]
        if not candidates:
            return []
        if query.order:
            return sorted(candidates, key=lambda record: record.price, reverse=query.order == "desc")[:query.limit]

        text = normalize(query.text)
        semantic_scores = self._semantic_scores(
            PRODUCT_COLLECTION, query.text, [record.product_id for record in candidates]
        )
        tokens = set(text.split())

        def score(record: ProductRecord) -> tuple[int, float, int, str]:
            name = normalize(record.name)
            name_tokens = set(name.split())
            exact_rank = 0
            if text and text == name:
                exact_rank = 2
            elif text and (text in name or tokens <= name_tokens):
                exact_rank = 1
            token_score = len(tokens & name_tokens) / max(len(tokens), 1)
            domain_text = normalize(" ".join(map(str, record.attributes.values())))
            domain_score = len(tokens & set(domain_text.split())) / max(len(tokens), 1)
            total = token_score + 0.25 * domain_score + semantic_scores.get(record.product_id, 0.0)
            return exact_rank, total, -record.price, record.name

        return sorted(candidates, key=score, reverse=True)[:query.limit]

    def search_builds(self, query: BuildQuery) -> list[BuildRecord]:
        excluded = {build_id.casefold() for build_id in query.excluded_ids}
        candidates = [
            record for record in self._builds.values()
            if record.build_id.casefold() not in excluded
        ]
        for category, model in query.constraints.required_components.items():
            key = "mainboard" if category.casefold() in {"main", "motherboard"} else category.casefold()
            wanted = normalize(model)
            candidates = [
                record for record in candidates
                if key in record.components and _model_matches(record.components[key].model, wanted)
            ]
            
        if query.constraints.excluded_brands:
            excluded_b = {normalize(b) for b in query.constraints.excluded_brands}
            candidates = [
                record for record in candidates
                if not any(normalize(part.brand) in excluded_b for part in record.components.values())
            ]
            
        if not candidates:
            return []
        if query.price_order:
            return self._unique_builds(
                sorted(candidates, key=lambda record: record.total_price, reverse=query.price_order == "desc"),
                query.limit,
            )

        if query.budget is not None:
            candidates = [record for record in candidates if record.total_price <= query.budget]
            if not candidates:
                return []

        semantic_scores = self._semantic_scores(
            BUILD_COLLECTION, query.text, [record.build_id for record in candidates]
        )
        query_tokens = set(normalize(query.text).split())

        def score(record: BuildRecord) -> tuple[float, int]:
            budget_score = 0.0
            if query.budget:
                budget_score = max(0.0, 1.0 - abs(record.total_price - query.budget) / query.budget)
                
            preference_score = 0.0
            for category, preferred_list in query.constraints.preferred_components.items():
                key = "mainboard" if category.casefold() in {"main", "motherboard"} else category.casefold()
                if key in record.components and any(_model_matches(record.components[key].model, normalize(m)) for m in preferred_list):
                    preference_score += 1.0
                    

            domain = normalize(self._build_search_text(record))
            keyword_score = len(query_tokens & set(domain.split())) / max(len(query_tokens), 1)
            return (
                semantic_scores.get(record.build_id, 0.0) * 2
                + keyword_score * 2
                + budget_score * 1.5
                + preference_score * 2.0,
                -record.total_price if query.budget is not None else record.total_price,
            )

        return self._unique_builds(sorted(candidates, key=score, reverse=True), query.limit)

    @staticmethod
    def _unique_builds(records: list[BuildRecord], limit: int) -> list[BuildRecord]:
        unique = []
        seen = set()
        for record in records:
            signature = (
                tuple(sorted(
                    (category, part.model, part.brand, part.price)
                    for category, part in record.components.items()
                )),
                record.assembly_fee,
                record.total_price,
                record.detailed_purpose,
                str(record.attributes.get("Primary_Workload", "")),
                str(record.attributes.get("Purpose_Category", "")),
                record.notes,
            )
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(record)
            if len(unique) == limit:
                break
        return unique

    def match_build_entities(self, text: str) -> BuildEntityMatches:
        """Match component models and brands that exist in the catalog."""
        tokens = normalize(text).split()
        components = {}
        for category, ngrams in self._build_model_ngrams.items():
            matches = [
                (end, end - start, " ".join(tokens[start:end]))
                for start in range(len(tokens))
                for end in range(start + 1, min(len(tokens), start + 8) + 1)
                if tuple(tokens[start:end]) in ngrams
            ]
            if matches:
                components[category] = max(matches)[2]
        normalized = normalize(text)
        brands = {
            canonical: set(categories)
            for brand, (canonical, categories) in self._build_brand_categories.items()
            if re.search(rf"\b{re.escape(brand)}\b", normalized)
        }
        return BuildEntityMatches(components=components, brands=brands)

    def component_matches_brand(self, category: str, model: str, brand: str) -> bool:
        """Return whether a known component model belongs to a canonical brand."""
        matching_brands = {
            normalize(record.components[category].brand)
            for record in self._builds.values()
            if category in record.components
            and _model_matches(record.components[category].model, model)
        }
        return not matching_brands or normalize(brand) in matching_brands

    def resolve_component_mention(self, category: str, raw_value: str) -> ComponentResolution:
        key = "mainboard" if category.casefold() in {"main", "motherboard"} else category.casefold()
        matches = {
            record.components[key].model
            for record in self._builds.values()
            if key in record.components and _model_matches(record.components[key].model, raw_value)
        }
        candidate_models = sorted(list(matches))
        if len(candidate_models) == 1:
            return ComponentResolution(category=category, raw_value=raw_value, canonical_model=candidate_models[0], candidate_models=candidate_models, status="resolved")
        elif len(candidate_models) > 1:
            return ComponentResolution(category=category, raw_value=raw_value, canonical_model=None, candidate_models=candidate_models, status="ambiguous")
        return ComponentResolution(category=category, raw_value=raw_value, canonical_model=None, candidate_models=[], status="not_found")

    def resolve_brand(self, raw_brand: str) -> str | None:
        return _brand(raw_brand)

    def _semantic_scores(self, collection: str, text: str, allowed_ids: list[str]) -> dict[str, float]:
        if not self._semantic_mode or not text.strip() or self._semantic_index is None:
            return {}
        try:
            hits = self._semantic_index.search(collection, text, min(max(len(allowed_ids), 20), 100), allowed_ids)
            return {hit.document_id: hit.score for hit in hits}
        except Exception as error:
            print(f"[CATALOG] semantic search fallback: {error}")
            self._semantic_mode = False
            return {}

    def get_product(self, product_id: str) -> ProductRecord | None:
        return self._products.get(product_id)

    def get_build(self, build_id: str) -> BuildRecord | None:
        return self._builds.get(build_id.casefold())

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self._semantic_index is None:
            raise RuntimeError("Embedding model is not initialized")
        return self._semantic_index.embed_documents(texts)

    def status(self) -> CatalogStatus:
        return CatalogStatus(
            mode="semantic" if self._semantic_mode else "keyword-only",
            product_count=len(self._products),
            build_count=len(self._builds),
            product_fingerprint=self._product_fingerprint,
            build_fingerprint=self._build_fingerprint,
        )
