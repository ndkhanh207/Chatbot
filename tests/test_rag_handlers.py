import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.catalog import ShopCatalog, ProductRecord, ProductQuery
from app.chat.models import DomainRequest
from app.core.intent.master_intent import MasterIntentSchema as ParsedIntent
from app.price.handler import PriceHandler
from app.rag.models import GroundedAnswer, GroundedAnswerRequest
from app.llm.result import LlmResult, LlmErrorKind

@pytest.fixture
def mock_catalog():
    catalog = MagicMock(spec=ShopCatalog)
    catalog.search_products.return_value = []
    return catalog

@pytest.fixture
def domain_request():
    return DomainRequest(
        user_message="Test message",
        user_uid="test_user",
        session_id="test_session"
    )


def test_price_handler_not_found(mock_catalog, domain_request):
    async def run_test():
        intent = ParsedIntent(intent="price_check", target_product="Unknown Product")
        handler = PriceHandler(mock_catalog)
        
        result = await handler.handle(domain_request, intent)
        
        assert "chưa tìm thấy" in result.reply
        assert result.metadata["intent"] == "price_check"
    asyncio.run(run_test())


@patch("app.price.handler.generate_grounded_answer")
def test_price_handler_calculation_success(mock_generate, mock_catalog, domain_request):
    async def run_test():
        intent = ParsedIntent(
            intent="price_calculation", 
            cpu="Intel i5", 
            mainboard="Asus B660"
        )
        
        # Mock search_products to return a product for each query
        def mock_search(query: ProductQuery):
            if query.text == "Intel i5":
                return [ProductRecord(product_id="cpu_1", name="Intel i5", price=5000000, category="CPU", brand="Intel", url="")]
            if query.text == "Asus B660":
                return [ProductRecord(product_id="main_1", name="Asus B660", price=3000000, category="MAINBOARD", brand="Asus", url="")]
            return []
            
        mock_catalog.search_products.side_effect = mock_search

        # Mock generator success
        mock_generate.return_value = LlmResult(
            value=GroundedAnswer(
                answer="Tổng giá là 8 triệu.",
                used_source_ids=["cpu_1", "main_1", "calculation_result"]
            )
        )

        handler = PriceHandler(mock_catalog)
        result = await handler.handle(domain_request, intent)

        assert result.reply == "Tổng giá là 8 triệu."
        assert set(result.metadata["source_ids"]) <= {"cpu_1", "main_1", "calculation_result"}
    asyncio.run(run_test())


@patch("app.price.handler.generate_grounded_answer")
def test_price_handler_fallback(mock_generate, mock_catalog, domain_request):
    async def run_test():
        intent = ParsedIntent(intent="price_check", target_product="Intel i5")
        
        mock_catalog.search_products.return_value = [
            ProductRecord(product_id="cpu_1", name="Intel i5", price=5000000, category="CPU", brand="Intel", url="")
        ]

        # Mock generator failure (timeout)
        mock_generate.return_value = LlmResult(error=LlmErrorKind.TIMEOUT)

        handler = PriceHandler(mock_catalog)
        result = await handler.handle(domain_request, intent)

        # Should fall back to deterministic response
        assert "5.000.000 VNĐ" in result.reply
        assert result.metadata["fallback"] is True
    asyncio.run(run_test())
