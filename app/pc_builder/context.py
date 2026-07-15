from typing import Optional, List
from pydantic import BaseModel, Field
from app.memory.context_manager import ConversationContext

class PcBuildContext(BaseModel):
    """Deep module state for PC Builder multi-turn context."""
    build_id: Optional[str] = None
    preset_id: Optional[str] = None
    budget: Optional[int] = None
    exclude_builds: List[str] = Field(default_factory=list)
    
    # User explicit constraints
    user_cpu: Optional[str] = None
    user_gpu: Optional[str] = None
    user_mainboard: Optional[str] = None
    
    # AI suggested components (for reference in multi-turn lock/swap)
    last_suggested_cpu: Optional[str] = None
    last_suggested_gpu: Optional[str] = None
    last_suggested_mainboard: Optional[str] = None
    pending_question: Optional[str] = None


class ConversationMemory:
    """Deep Module adapter managing session state over the database."""
    def __init__(self, user_uid: str, session_id: str):
        self.context = ConversationContext(user_uid, session_id)

    def load_context(self) -> PcBuildContext:
        return self.context.load_snapshot(PcBuildContext)

    def commit_turn(self, user_msg: str, ai_msg: str, ctx: PcBuildContext) -> None:
        self.context.commit(
            user_msg, 
            ai_msg, 
            ctx.model_dump(exclude_none=True),
        )
