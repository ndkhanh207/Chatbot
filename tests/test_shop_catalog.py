from app.catalog import (
    BuildPart,
    BuildQuery,
    BuildRecord,
    ProductQuery,
    ProductRecord,
    ShopCatalog,
)
from app.catalog.semantic import SemanticHit
from app.catalog import ChromaSemanticIndex
from app.compatibility.compat_logic import check_cpu_main_compat


class MappingIndex:
    available = True

    def __init__(self, rankings=None, fail_search=False):
        self.rankings = rankings or {}
        self.fail_search = fail_search
        self.collections = {}

    def ensure_collection(self, name, fingerprint, documents):
        self.collections[name] = (fingerprint, list(documents))

    def search(self, collection, text, limit, allowed_ids=None):
        if self.fail_search:
            raise RuntimeError("Chroma offline")
        allowed = set(allowed_ids or [])
        return [
            SemanticHit(document_id, score)
            for document_id, score in self.rankings.get(text, [])
            if allowed_ids is None or document_id in allowed
        ][:limit]

    def embed_documents(self, texts):
        return [[float(len(text))] for text in texts]


def product(product_id, category, name, price, **attributes):
    return ProductRecord(
        product_id=product_id,
        category=category,
        name=name,
        brand=name.split()[0],
        price=price,
        attributes={"tên": name, "giá": price, **attributes},
    )


def build(build_id, price, cpu, mainboard, gpu, notes="", purpose=None):
    components = {
        "cpu": BuildPart(category="CPU", model=cpu, brand=cpu.split()[0], tier=3),
        "mainboard": BuildPart(category="MAINBOARD", model=mainboard, brand=mainboard.split()[0], tier=2),
        "gpu": BuildPart(category="GPU", model=gpu, brand=gpu.split()[0], tier=4),
    }
    return BuildRecord(
        build_id=build_id,
        components=components,
        assembly_fee=500_000,
        total_price=price,
        detailed_purpose=purpose or notes,
        notes=notes,
        attributes={
            "BuildID": build_id,
            "CPU_Model": cpu,
            "Motherboard_Model": mainboard,
            "GPU_Model": gpu,
            "Total_Price": price,
            "Detailed_Purpose": purpose or notes,
            "Build_Notes": notes,
        },
    )


def fixtures(index=None):
    products = [
        product("cpu:12400f", "CPU", "Intel Core i5-12400F", 3_000_000, socket="LGA 1700", tdp=65),
        product("cpu:12400", "CPU", "Intel Core i5-12400", 2_900_000, socket="LGA 1700", tdp=65),
        product("cpu:7600x", "CPU", "AMD Ryzen 5 7600X", 4_100_000, socket="AM5", tdp=105),
        product("main:b760", "MAINBOARD", "ASUS B760M D4", 2_500_000, socket="LGA 1700", pcie="PCIe 4.0 x16"),
        product("gpu:4070", "GPU", "MSI GeForce RTX 4070", 14_000_000, interface="PCIe 4.0 x16", **{"bộ nhớ": 12}),
    ]
    builds = [
        build("BUILD-1", 20_000_000, "Intel Core i5-12400F", "ASUS B760M D4", "MSI RTX 4070", "gaming 2K cân bằng"),
        build("BUILD-2", 30_000_000, "AMD Ryzen 5 7600X", "ASUS B650M", "MSI RTX 4070 Ti", "render và đồ họa"),
    ]
    return ShopCatalog(products, builds, index or MappingIndex(), "test-model")


def test_semantic_paraphrase_resolves_product():
    index = MappingIndex({"máy mát tiết kiệm điện": [("cpu:12400f", 0.95)]})
    catalog = fixtures(index)

    results = catalog.search_products(ProductQuery(text="máy mát tiết kiệm điện", category="CPU"))

    assert results[0].product_id == "cpu:12400f"
    assert results[0].attributes["tdp"] == 65


def test_exact_model_always_outranks_semantic_match():
    index = MappingIndex({"Intel Core i5 12400F": [("cpu:12400", 1.0), ("cpu:12400f", 0.01)]})
    catalog = fixtures(index)

    results = catalog.search_products(ProductQuery(text="Intel Core i5 12400F", category="CPU"))

    assert results[0].product_id == "cpu:12400f"


def test_build_entities_are_matched_from_catalog_models():
    catalog = fixtures()

    constraints = catalog.match_build_entities(
        "build i5-12400F với RTX4070 và main B760M"
    )

    assert constraints.components == {
        "cpu": "i5 12400f",
        "gpu": "rtx4070",
        "mainboard": "b760m",
    }
    assert catalog.search_builds(BuildQuery(
        required_components=constraints.components,
        limit=1,
    ))[0].build_id == "BUILD-1"
    assert catalog.match_build_entities("gaming 2K 60 FPS").components == {}


def test_catalog_exposes_brand_facts_without_interpreting_user_policy():
    matches = fixtures().match_build_entities("Ryzen 5 7600X rồi quay lại Intel")

    assert matches.components == {"cpu": "ryzen 5 7600x"}
    assert matches.brands["Intel"] == {"cpu"}


def test_product_hard_constraints_are_never_violated():
    catalog = fixtures()

    results = catalog.search_products(ProductQuery(
        text="mạnh", category="CPU", brand="Intel", model="12400",
        price_min=2_950_000, price_max=3_100_000, limit=10,
    ))

    assert [record.product_id for record in results] == ["cpu:12400f"]


def test_compatibility_uses_exact_catalog_fields():
    catalog = fixtures()
    cpu = catalog.search_products(ProductQuery(text="i5 12400f", category="CPU", limit=1))[0]
    mainboard = catalog.search_products(ProductQuery(text="B760M D4", category="MAINBOARD", limit=1))[0]

    result = check_cpu_main_compat(cpu.as_legacy_dict(), mainboard.as_legacy_dict())

    assert result["is_compatible"] is True
    assert result["socket_match"] is True


def test_build_semantic_search_stays_inside_hard_filters():
    index = MappingIndex({"render chuyên nghiệp": [("BUILD-2", 1.0), ("BUILD-1", 0.9)]})
    catalog = fixtures(index)

    results = catalog.search_builds(BuildQuery(
        text="render chuyên nghiệp",
        budget=22_000_000,
        required_components={"cpu": "12400F"},
        brands={"gpu": "MSI"},
        limit=5,
    ))

    assert [record.build_id for record in results] == ["BUILD-1"]


def test_build_top_five_preserves_rank_order():
    builds = [
        build(f"BUILD-{index}", 20_000_000 + index, "Intel CPU", "ASUS Main", "MSI GPU")
        for index in range(6)
    ]
    ranking = [(f"BUILD-{index}", 1.0 - index / 10) for index in range(6)]
    catalog = ShopCatalog([], builds, MappingIndex({"gaming": ranking}), "test")

    results = catalog.search_builds(BuildQuery(text="gaming", limit=5))

    assert [record.build_id for record in results] == [f"BUILD-{index}" for index in range(5)]


def test_build_price_order_is_exact():
    catalog = fixtures()

    cheapest = catalog.search_builds(BuildQuery(price_order="asc", limit=1))[0]
    expensive = catalog.search_builds(BuildQuery(price_order="desc", limit=1))[0]

    assert cheapest.total_price == 20_000_000
    assert expensive.total_price == 30_000_000


def test_build_budget_is_a_strict_maximum():
    catalog = fixtures()

    results = catalog.search_builds(BuildQuery(text="gaming", budget=25_000_000, limit=5))
    none = catalog.search_builds(BuildQuery(text="gaming", budget=19_000_000, limit=5))

    assert [record.build_id for record in results] == ["BUILD-1"]
    assert none == []


def test_build_without_budget_prefers_capability_price_on_relevance_tie():
    cheaper = build("BUILD-CHEAP", 20_000_000, "CPU A", "Main A", "GPU A", "gaming")
    stronger = build("BUILD-STRONG", 30_000_000, "CPU B", "Main B", "GPU B", "gaming")
    catalog = ShopCatalog([], [cheaper, stronger])

    results = catalog.search_builds(BuildQuery(text="gaming", limit=2))

    assert [result.build_id for result in results] == ["BUILD-STRONG", "BUILD-CHEAP"]


def test_build_tiers_are_not_indexed_or_ranked():
    low = build("BUILD-LOW", 20_000_000, "Intel CPU", "ASUS Main", "MSI GPU")
    high = build("BUILD-HIGH", 20_000_000, "Intel CPU", "ASUS Main", "MSI GPU")
    low.components["cpu"].tier = 1
    high.components["cpu"].tier = 99
    index = MappingIndex()
    catalog = ShopCatalog([], [low, high], index, "test")

    results = catalog.search_builds(BuildQuery(text="", priority="cpu", limit=2))
    documents = index.collections["builds_v4"][1]

    assert [record.build_id for record in results] == ["BUILD-LOW"]
    assert all("tier" not in document.text.casefold() for document in documents)


def test_build_search_uses_v3_metadata_but_not_supporting_notes_or_tiers():
    record = build(
        "BUILD-PURPOSE", 20_000_000, "Intel CPU", "ASUS Main", "MSI GPU",
        notes="Cảnh báo giá cần xác minh",
        purpose="Dựng video 4K và render 3D",
    )
    record.attributes.update({
        "Primary_Workload": "Dựng phim nhiều góc quay",
        "Purpose_Category": "Sáng tạo nội dung",
        "Purpose_Code": "CRE-02",
        "RAG_Keywords": "Premiere; After Effects; dựng phim",
        "Price_Confidence": "low",
    })
    index = MappingIndex()

    catalog = ShopCatalog([], [record], index, "test")

    document = index.collections["builds_v4"][1][0].text
    assert "Dựng video 4K và render 3D" in document
    assert "Dựng phim nhiều góc quay" in document
    assert "Sáng tạo nội dung" in document
    assert "Premiere; After Effects; dựng phim" in document
    assert "Cảnh báo giá cần xác minh" not in document
    assert "Price_Confidence" not in document
    assert "tier" not in document.casefold()
    assert document == catalog._build_search_text(record)
    assert index.collections["builds_v4"][1][0].metadata["purpose_code"] == "CRE-02"


def test_build_keyword_fallback_reuses_v3_search_text():
    target = build("BUILD-TARGET", 20_000_000, "CPU A", "Main A", "GPU A", purpose="workstation")
    other = build("BUILD-OTHER", 20_000_000, "CPU B", "Main B", "GPU B", purpose="workstation")
    target.attributes["RAG_Keywords"] = "MATLAB mô phỏng kỹ thuật"
    catalog = ShopCatalog([], [other, target], MappingIndex(fail_search=True), "test")

    results = catalog.search_builds(BuildQuery(text="MATLAB", limit=2))

    assert results[0].build_id == "BUILD-TARGET"


def test_semantic_failure_falls_back_to_exact_keyword_search():
    catalog = fixtures(MappingIndex(fail_search=True))

    result = catalog.search_products(ProductQuery(text="Intel Core i5 12400F", category="CPU", limit=1))[0]

    assert result.product_id == "cpu:12400f"
    assert catalog.status().mode == "keyword-only"


def test_build_failure_falls_back_to_domain_keyword_ranking():
    catalog = fixtures(MappingIndex(fail_search=True))

    results = catalog.search_builds(BuildQuery(text="render đồ họa", limit=2))

    assert results[0].build_id == "BUILD-2"


def test_fingerprint_changes_with_records_or_embedding_config():
    first_index = MappingIndex()
    first = ShopCatalog([product("cpu:a", "CPU", "CPU A", 1)], [], first_index, "model-a")
    second = ShopCatalog([product("cpu:a", "CPU", "CPU A", 2)], [], MappingIndex(), "model-a")
    third = ShopCatalog([product("cpu:a", "CPU", "CPU A", 1)], [], MappingIndex(), "model-b")

    assert first.status().product_fingerprint != second.status().product_fingerprint
    assert first.status().product_fingerprint != third.status().product_fingerprint
    assert len(first_index.collections["products_v1"][1]) == 1


def test_future_ram_category_needs_no_catalog_interface_change():
    ram = product("ram:vengeance-32", "RAM", "Corsair Vengeance 32GB", 2_000_000, speed="6000 MHz")
    catalog = ShopCatalog([ram], [], MappingIndex(), "test-model")

    results = catalog.search_products(ProductQuery(text="Vengeance 32GB", category="RAM"))

    assert results[0].product_id == "ram:vengeance-32"
    assert results[0].attributes["speed"] == "6000 MHz"


def test_future_ram_csv_is_discovered_without_loader_change(tmp_path):
    import pandas as pd

    for filename, name in (
        ("cpu.csv", "CPU Fixture"),
        ("gpu.csv", "GPU Fixture"),
        ("motherboard.csv", "Mainboard Fixture"),
        ("ram.csv", "Corsair Vengeance 32GB"),
    ):
        pd.DataFrame([{"tên": name, "giá": 1_000_000}]).to_csv(
            tmp_path / filename, index=False
        )

    catalog = ShopCatalog.load(tmp_path)

    assert catalog.search_products(ProductQuery(text="Vengeance", category="RAM"))[0].name == "Corsair Vengeance 32GB"


def test_v3_is_the_only_authoritative_build_source(tmp_path):
    import pandas as pd

    for filename, name in (("cpu.csv", "CPU"), ("gpu.csv", "GPU"), ("motherboard.csv", "Main")):
        pd.DataFrame([{"tên": name, "giá": 1_000_000}]).to_csv(tmp_path / filename, index=False)
    canonical = {
        "BuildID": "BUILD-1", "CPU_Model": "CPU Canon", "CPU_Brand": "Intel",
        "Motherboard_Model": "Main Canon", "Motherboard_Brand": "ASUS",
        "GPU_Model": "GPU Canon", "GPU_Brand": "MSI", "Total_Price": 10_000_000,
        "Assembly_Fee": 200_000, "Build_Notes": "canonical note",
    }
    pd.DataFrame([canonical]).to_csv(tmp_path / "Pc_build_data.csv", index=False)
    changed = canonical | {
        "CPU_Model": "CPU CHEAT", "Total_Price": 1,
        "Detailed_Purpose": "heavy data workload", "Build_Notes": "audited warning",
        "Purpose_Code": "OFF-03",
    }
    pd.DataFrame([changed, changed | {"BuildID": "BUILD-V3-ONLY"}]).to_csv(
        tmp_path / "Pc_build_data_v3.csv", index=False
    )

    catalog = ShopCatalog.load(tmp_path)
    record = catalog.get_build("BUILD-1")

    assert catalog.status().build_count == 2
    assert record.components["cpu"].model == "CPU CHEAT"
    assert record.total_price == 1
    assert record.detailed_purpose == "heavy data workload"
    assert record.notes == "audited warning"
    assert record.attributes["Purpose_Code"] == "OFF-03"
    assert catalog.get_build("BUILD-V3-ONLY") is not None


class TinyEmbeddings:
    @staticmethod
    def _vector(text):
        lowered = text.casefold()
        return [
            float(lowered.count("gaming")),
            float(lowered.count("render")),
            float(lowered.count("intel")),
            1.0,
        ]

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)


def test_chroma_collections_are_versioned_filtered_and_reusable(tmp_path):
    index = ChromaSemanticIndex(tmp_path, TinyEmbeddings())
    catalog = fixtures(index)

    products = catalog.search_products(ProductQuery(text="gaming", category="CPU", brand="Intel", limit=5))
    builds = catalog.search_builds(BuildQuery(text="render", required_components={"cpu": "7600X"}, limit=5))
    reloaded = fixtures(ChromaSemanticIndex(tmp_path, TinyEmbeddings()))

    assert products and all(record.category == "CPU" and record.brand == "Intel" for record in products)
    assert [record.build_id for record in builds] == ["BUILD-2"]
    assert reloaded.status().product_fingerprint == catalog.status().product_fingerprint


def test_real_csv_catalog_loads_all_authoritative_records():
    from config.config import Config

    catalog = ShopCatalog.load(Config.PC_STORE_DATA)
    status = catalog.status()

    assert status.product_count == 1075
    assert status.build_count == 1036
    assert catalog.search_products(ProductQuery(text="Ryzen 7 9800X3D", category="CPU", limit=1))[0].price > 0
    assert catalog.search_builds(BuildQuery(text="AAA 4K ray tracing", limit=1))[0].detailed_purpose
