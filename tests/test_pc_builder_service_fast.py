import pytest
import asyncio
from app.llm.result import LlmResult
from app.rag.models import GroundedAnswer
from app.pc_builder.models import (
    PcBuildContext,
    PcBuildCommand,
    PcBuildAction,
    PendingQuestion
)
from app.pc_builder.service import (
    PcBuildIssueCode,
    PcBuildService,
    _evaluate_completeness,
    _merge_command,
)
from app.pc_builder.extractor import (
    extract_pc_build_command,
)
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
    assert _evaluate_completeness(ctx) is None

    ctx.purpose_status = "clarify"
    assert _evaluate_completeness(ctx) == PendingQuestion.PURPOSE

    ctx.pending_question = PendingQuestion.BUDGET_SCOPE
    assert _evaluate_completeness(ctx) == PendingQuestion.BUDGET_SCOPE


@pytest.mark.anyio
async def test_known_budget_does_not_suppress_missing_purpose(monkeypatch):
    async def fake_generate(request):
        assert request.intent == "build_pc_clarification"
        assert request.evidence.insufficient is True
        assert request.evidence.missing_information
        return LlmResult(value=GroundedAnswer(
            answer="Dạ, bạn thường chơi game nào và muốn độ phân giải, FPS bao nhiêu?"
        ))

    monkeypatch.setattr(service_module, "generate_grounded_answer", fake_generate)
    service = PcBuildService(catalog=MockCatalog())

    outcome = await service.execute(
        command=PcBuildCommand(
            action=PcBuildAction.CREATE,
            budget=30_000_000,
            budget_scope="total",
            purpose="chơi game",
            purpose_status="clarify",
        ),
        current_context=PcBuildContext(),
        user_message="build pc 30 triệu chơi game",
    )

    assert outcome.next_context.purpose == "chơi game"
    assert outcome.next_context.purpose_status == "clarify"
    assert outcome.next_context.pending_question == PendingQuestion.PURPOSE
    assert outcome.result.reply == "Dạ, bạn thường chơi game nào và muốn độ phân giải, FPS bao nhiêu?"


@pytest.mark.anyio
async def test_negative_budget_is_rejected_before_retrieval(monkeypatch):
    async def fake_generate(request):
        facts = request.evidence.items[0].facts
        assert facts["issue"] == "invalid_budget"
        assert facts["budget"] == -30_000_000
        return LlmResult(value=GroundedAnswer(
            answer="Dạ, ngân sách này không hợp lệ; bạn muốn nhập lại bao nhiêu?"
        ))

    monkeypatch.setattr(service_module, "generate_grounded_answer", fake_generate)
    service = PcBuildService(catalog=MockCatalog())

    outcome = await service.execute(
        command=PcBuildCommand(
            action=PcBuildAction.CREATE,
            budget=-30_000_000,
            budget_scope="total",
            purpose="chơi Valorant 1080p 240 FPS",
            purpose_status="ready",
        ),
        current_context=PcBuildContext(),
        user_message="build PC âm 30 triệu để chơi Valorant 1080p 240 FPS",
    )

    assert outcome.next_context.pending_question == PendingQuestion.BUDGET
    assert "hợp lệ" in outcome.result.reply

def test_pc_build_extraction_examples_are_valid_training_data():
    examples = load_extraction_examples()

    assert len(examples) >= 10
    commands = {
        example["input"]: PcBuildCommand.model_validate(example["output"])
        for example in examples
    }

    assert commands["build pc 30 triệu chơi game"].budget == 30_000_000
    assert commands["build pc 30 triệu chơi game"].purpose == "chơi game"
    assert commands["build pc 30 triệu chơi game"].purpose_status == "clarify"
    assert commands["bộ pc deep learning huấn luyện AI 80 triệu"].purpose == "deep learning huấn luyện AI"
    assert commands["build pc 30 triệu"].purpose is None
    assert commands["build pc 30 triệu"].purpose_status == "clarify"
    assert commands["đổi sang rtx 4080"].required_components == {"gpu": "rtx 4080"}
    assert commands["đổi main sang msi b850"].required_components == {"mainboard": "msi b850"}


def test_pc_build_extraction_examples_prompt_block_is_compact():
    examples = load_extraction_examples()
    block = format_extraction_examples(examples, limit=2)

    assert "Input:" in block
    assert "Output:" in block
    assert "build pc 30 triệu chơi game" in block


def test_pc_build_extraction_examples_select_nearest_cases():
    examples = load_extraction_examples()
    selected = select_extraction_examples(examples, "đổi sang rtx 4080", limit=1)
    clarification = select_extraction_examples(examples, "chơi game valorant nhẹ", limit=1)
    exact = find_exact_extraction_example(examples, "giữ nguyên cpu nhưng đổi gpu mạnh hơn")

    assert selected[0]["input"] == "đổi sang rtx 4080"
    assert clarification[0]["input"] == "chơi Valorant nhẹ"
    assert exact is not None
    assert exact.keep_components == ["cpu"]
