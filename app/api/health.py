from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Literal
from app.catalog import CatalogStatus
from app.core.health import check_ollama_status, check_mysql_status

router = APIRouter()

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    catalog: CatalogStatus | None = None

from app.guard.security import limiter

@router.get("/health", response_model=HealthResponse, tags=["System"])
@limiter.exempt
async def health_check(request: Request):
    """Kiểm tra tình trạng của các dịch vụ cốt lõi."""
    ollama_ok = await check_ollama_status()
    mysql_ok = await check_mysql_status()
    catalog = getattr(request.app.state, "catalog", None)
    catalog_status = catalog.status() if catalog is not None else None
    vector_db_ok = (
        catalog_status is not None
        and catalog_status.product_count > 0
        and catalog_status.mode == "semantic"
    )
    
    overall = "ok" if (ollama_ok and mysql_ok and vector_db_ok) else "degraded"
    
    return HealthResponse(status=overall, catalog=catalog_status)
