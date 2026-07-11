from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.core.health import check_ollama_status, check_mysql_status

router = APIRouter()

class HealthResponse(BaseModel):
    status: str

from app.guard.security import limiter

@router.get("/health", response_model=HealthResponse, tags=["System"])
@limiter.exempt
async def health_check(request: Request):
    """Kiểm tra tình trạng của các dịch vụ cốt lõi."""
    ollama_ok = await check_ollama_status()
    mysql_ok = await check_mysql_status()
    vector_db_ok = getattr(request.app.state, "vector_store", None) is not None
    
    overall = "ok" if (ollama_ok and mysql_ok and vector_db_ok) else "degraded"
    
    return HealthResponse(status=overall)
