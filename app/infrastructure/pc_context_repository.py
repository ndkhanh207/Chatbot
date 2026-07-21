import logging
from typing import Optional
from pydantic import ValidationError

from app.pc_builder.models import PcContextRepository, VersionedPcContext, PcBuildContext
from app.memory.memory_store import _get_session, ChatMessage

logger = logging.getLogger(__name__)


class PcContextVersionConflict(Exception):
    def __init__(self, expected: int, actual: int):
        super().__init__(f"Version conflict: expected {expected}, got {actual}")
        self.expected = expected
        self.actual = actual


def migrate_pc_context(raw: dict) -> dict | None:
    """Migrate old state schemas to the current one."""
    state = raw.get("state")
    if state is None or not isinstance(state, dict):
        return None
        
    nested = state.get("intent_state")
    if isinstance(nested, dict):
        state = {**{k: v for k, v in state.items() if k != "intent_state"}, **nested}
        
    return state


class SqlPcContextRepository(PcContextRepository):
    
    def _load_latest(self, session, user_uid: str, session_id: str) -> VersionedPcContext:
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
                
            version = metadata.get("version", msg.id)
            if version is None:
                version = msg.id if msg.id is not None else 0

            try:
                context = PcBuildContext.model_validate(migrated)
                return VersionedPcContext(context=context, version=int(version))
            except ValidationError as exc:
                logger.warning(f"[REPO] Skipped invalid state: {exc}")
                
        return VersionedPcContext(context=PcBuildContext(), version=0)
        
    async def load(self, user_uid: str, session_id: str) -> VersionedPcContext:
        session = _get_session()
        if session is None:
            return VersionedPcContext(context=PcBuildContext(), version=0)
            
        try:
            return self._load_latest(session, user_uid, session_id)
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
            latest = self._load_latest(session, user_uid, session_id)
            
            if latest.version != expected_version and expected_version != 0:
                raise PcContextVersionConflict(expected=expected_version, actual=latest.version)
                
            new_version = expected_version + 1
            metadata = {
                "state": context.model_dump(mode="json"),
                "version": new_version,
                "type": "pc_state_commit"
            }
            
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
