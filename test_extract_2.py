import sys
import asyncio
sys.path.append(r"d:\doan\Chatbot")
from app.pc_builder.extractor import extract_pc_build_command
from app.pc_builder.models import PcBuildContext
from app.routing.models import RouteDecision, TaskRelation

async def main():
    message = "chơi game valorant nhẹ"
    ctx = PcBuildContext(
        budget=30000000,
        purpose="chơi game",
        purpose_status="clarify"
    )
    decision = RouteDecision(
        handler_name="pc_builder",
        task_relation=TaskRelation.NEW_TASK,
        rewritten_query="chơi game valorant nhẹ"
    )
    result = await extract_pc_build_command(
        user_message=message,
        recent_history=[],
        current_context=ctx,
        route_decision=decision
    )
    print(result.value.model_dump() if result.ok and result.value else result.error)

if __name__ == "__main__":
    asyncio.run(main())
