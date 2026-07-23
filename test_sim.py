import sys
import asyncio
sys.path.append(r"d:\doan\Chatbot")
from config.config import Config
from app.catalog import ShopCatalog
from app.pc_builder.service import PcBuildService
from tests.test_pc_builder_service_fast import MockCatalog
from app.pc_builder.extractor import extract_pc_build_command
from app.pc_builder.models import PcBuildContext
from app.routing.models import RouteDecision, TaskRelation

from app.catalog.models import BuildRecord

async def main():
    catalog = ShopCatalog.load(Config.PC_STORE_DATA)
    service = PcBuildService(catalog=catalog)

    # First turn
    message1 = "build pc 30 triệu làm văn phòng"
    ctx = PcBuildContext()
    decision1 = RouteDecision(handler_name="pc_builder", task_relation=TaskRelation.NEW_REQUEST, rewritten_query=message1)
    
    cmd1 = await extract_pc_build_command(user_message=message1, recent_history=[], current_context=ctx, route_decision=decision1)
    print("--- Turn 1 Command ---")
    print(cmd1.value.model_dump() if cmd1.ok else cmd1.error)

    if not cmd1.ok or not cmd1.value: return

    out1 = await service.execute(cmd1.value, ctx, message1)
    print("--- Turn 1 Reply ---")
    print(out1.result.reply)
    print("Build ID:", out1.next_context.build_id)
    
    # Second turn
    message2 = "chơi game valorant nhẹ"
    ctx2 = out1.next_context.model_copy(deep=True)
    decision2 = RouteDecision(handler_name="pc_builder", task_relation=TaskRelation.CONTINUE_TASK, rewritten_query=message2)

    cmd2 = await extract_pc_build_command(user_message=message2, recent_history=[], current_context=ctx2, route_decision=decision2)
    print("--- Turn 2 Command ---")
    print(cmd2.value.model_dump() if cmd2.ok else cmd2.error)

    if not cmd2.ok or not cmd2.value: return

    out2 = await service.execute(cmd2.value, ctx2, message2)
    print("--- Turn 2 Reply ---")
    print(out2.result.reply)
    print("Build ID:", out2.next_context.build_id)

if __name__ == "__main__":
    asyncio.run(main())
