from app.catalog import InMemorySemanticIndex, ProductQuery, ProductRecord, ShopCatalog


def test_semantic_index_ranks_shared_domain_terms():
    products = [
        ProductRecord(
            product_id="gpu:gaming",
            category="GPU",
            name="GPU Gaming",
            brand="TEST",
            price=1,
            attributes={"workload": "gaming 2K game AAA"},
        ),
        ProductRecord(
            product_id="gpu:office",
            category="GPU",
            name="GPU Office",
            brand="TEST",
            price=1,
            attributes={"workload": "văn phòng hiển thị cơ bản"},
        ),
    ]
    catalog = ShopCatalog(products, [], InMemorySemanticIndex(), "test")

    results = catalog.search_products(ProductQuery(text="gaming AAA", category="GPU", limit=2))

    assert results[0].product_id == "gpu:gaming"
