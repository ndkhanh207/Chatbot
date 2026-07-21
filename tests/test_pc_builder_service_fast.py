import pytest
import asyncio
from app.pc_builder.models import (
    PcBuildContext,
    PcBuildCommand,
    PcBuildAction,
    PcBuildStatus,
    PendingQuestion
)
from app.pc_builder.service import _merge_command, PcBuildIssueCode, _evaluate_completeness
from app.catalog import ShopCatalog

# A mock catalog for testing
class MockCatalog:
    def __init__(self, items=None):
        self.items = items or []
        
    def search_builds(self, query):
        if not self.items:
            return []
        return self.items

    def get_build(self, build_id):
        return None

# Override resolve_component to mock catalog lookup
import app.pc_builder.service as service_module

@pytest.fixture
def mock_resolver(monkeypatch):
    def fake_resolve(name, cat, catalog):
        if name.lower() == "not_found_cpu":
            return None
        return {"name": f"Resolved {name}", "brand": "BrandX", "tier": "mid"}
    monkeypatch.setattr(service_module, "resolve_component", fake_resolve)

@pytest.mark.anyio
async def test_merge_command_basic(mock_resolver):
    ctx = PcBuildContext()
    cmd = PcBuildCommand(
        action=PcBuildAction.UPDATE,
        budget=20_000_000,
        purpose="gaming",
        required_components={"CPU": "Intel i5"}
    )
    
    catalog = MockCatalog(items=[{"build_id": "BUILD-1"}])
    result = await _merge_command(current=ctx, command=cmd, catalog=catalog)
    
    assert not result.has_errors
    state = result.next_state
    assert state.budget == 20_000_000
    assert state.purpose == "gaming"
    assert state.required_components["CPU"] == "Resolved Intel i5"

@pytest.mark.anyio
async def test_merge_command_component_not_found(mock_resolver):
    ctx = PcBuildContext()
    cmd = PcBuildCommand(
        action=PcBuildAction.UPDATE,
        required_components={"CPU": "not_found_cpu"}
    )
    
    catalog = MockCatalog()
    result = await _merge_command(current=ctx, command=cmd, catalog=catalog)
    
    assert result.has_errors
    assert result.issues[0].code == PcBuildIssueCode.COMPONENT_NOT_FOUND

@pytest.mark.anyio
async def test_merge_command_reset(mock_resolver):
    ctx = PcBuildContext(budget=10_000_000, purpose="office")
    cmd = PcBuildCommand(action=PcBuildAction.RESET)
    
    catalog = MockCatalog()
    result = await _merge_command(current=ctx, command=cmd, catalog=catalog)
    
    assert not result.has_errors
    assert result.next_state.budget is None
    assert result.next_state.purpose is None

def test_evaluate_completeness():
    ctx = PcBuildContext()
    assert _evaluate_completeness(ctx) == PendingQuestion.GENERAL
    
    ctx.budget = 15_000_000
    assert _evaluate_completeness(ctx) == PendingQuestion.PURPOSE
    
    ctx.purpose = "gaming"
    assert _evaluate_completeness(ctx) is None
