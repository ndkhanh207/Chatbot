from typing import Optional, List
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from app.memory.memory_store import save_message, get_latest_metadata, get_trimmed_history

class PcBuildContext(BaseModel):
    """Deep module state for PC Builder multi-turn context."""
    build_id: Optional[str] = None
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


class ConversationMemory:
    """Deep Module adapter managing session state over the database."""
    def __init__(self, user_uid: str, session_id: str):
        self.user_uid = user_uid
        self.session_id = session_id

    def load_context(self) -> PcBuildContext:
        metadata = get_latest_metadata(self.user_uid, self.session_id)
        if metadata:
            # Chỉ nạp những trường hợp lệ
            try:
                return PcBuildContext.model_validate(metadata)
            except Exception as e:
                print(f"⚠️ [CONTEXT ERROR] Metadata không hợp lệ: {e}. Tạo context trống.")
        return PcBuildContext()

    def commit_turn(self, user_msg: str, ai_msg: str, ctx: PcBuildContext) -> None:
        save_message(
            self.user_uid, 
            self.session_id, 
            user_msg, 
            ai_msg, 
            metadata=ctx.model_dump(exclude_none=True)
        )

    def get_trimmed_history(self) -> List[BaseMessage]:
        return get_trimmed_history(self.user_uid, self.session_id)
