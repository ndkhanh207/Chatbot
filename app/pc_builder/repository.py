import json
from pydantic import ValidationError
from app.pc_builder.models import PcContextRepository, VersionedPcContext
from app.pc_builder.context import PcBuildContext
from app.memory.memory_store import _get_session, ChatMessage

def migrate_pc_context(raw: dict) -> dict | None:
    """Migrate old state schemas to the current one."""
    state = raw.get("state")
    if state is None:
        return None
    if not isinstance(state, dict):
        return None
        
    nested = state.get("intent_state")
    if isinstance(nested, dict):
        state = {**{k: v for k, v in state.items() if k != "intent_state"}, **nested}
        
    return state

class PcContextRepositoryImpl(PcContextRepository):
    async def load(self, user_uid: str, session_id: str) -> VersionedPcContext:
        session = _get_session()
        if session is None:
            return VersionedPcContext(context=PcBuildContext(), version=0)
            
        try:
            # Look for the most recent message with a state in metadata
            messages = session.query(ChatMessage).filter(
                ChatMessage.user_uid == user_uid,
                ChatMessage.session_id == session_id
            ).order_by(ChatMessage.id.desc()).limit(20).all()
            
            for msg in messages:
                metadata = msg.metadata_json
                if not isinstance(metadata, dict):
                    continue
                    
                migrated = migrate_pc_context(metadata)
                if migrated is None:
                    continue
                    
                # We found the latest state
                # In the old system, version wasn't stored, so we default to msg.id as the version
                version = metadata.get("version", msg.id)
                
                try:
                    context = PcBuildContext.model_validate(migrated)
                    return VersionedPcContext(context=context, version=version)
                except ValidationError as exc:
                    print(f"⚠️ [REPO] Bỏ qua state không hợp lệ: {exc}")
                    
            return VersionedPcContext(context=PcBuildContext(), version=0)
        finally:
            session.close()

    async def save(
        self,
        user_uid: str,
        session_id: str,
        context: PcBuildContext,
        *,
        expected_version: int,
    ) -> int:
        session = _get_session()
        if session is None:
            return expected_version + 1
            
        try:
            # We are using optimistic versioning.
            # In existing storage (ChatMessage), we can just append a system message representing the state.
            # To check version, we see if the latest state's version matches expected_version.
            latest = await self.load(user_uid, session_id)
            if latest.version != expected_version and expected_version != 0:
                raise ValueError(f"Version conflict: expected {expected_version}, got {latest.version}")
                
            new_version = expected_version + 1
            metadata = {
                "state": context.model_dump(mode="json"),
                "version": new_version,
                "type": "pc_state_commit"
            }
            
            # Save as a system message so it doesn't pollute chat history visually
            msg = ChatMessage(
                user_uid=user_uid,
                session_id=session_id,
                role="system",
                content="[PC State Save]",
                metadata_json=metadata
            )
            session.add(msg)
            session.commit()
            return new_version
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
