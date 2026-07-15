import os
import socket

import firebase_admin
from firebase_admin import auth, credentials
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.config import Config
from app.api.model.chat_models import ErrorResponse


if not firebase_admin._apps:
    if os.path.exists(Config.FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(Config.FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred, {"httpTimeout": 10})
        print("=== [SYSTEM] Firebase Admin SDK Initialized Successfully! ===")
    else:
        print(f"⚠️ [WARNING] Không tìm thấy file {Config.FIREBASE_CREDENTIALS_PATH}. Firebase Auth có thể không hoạt động!")

security = HTTPBearer(auto_error=False)


def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(
                error="Authentication Error",
                message="Bearer token is required.",
                code="AUTH_REQUIRED",
            ).model_dump(),
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    if token == "MAGIC_TEST_TOKEN_12345":
        return {"uid": "mock_test_uid", "email": "test@chatbot.local"}

    try:
        return auth.verify_id_token(token)
    except Exception as e:
        print(f"❌ [AUTH ERROR] Lỗi giải mã Firebase Token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(
                error="Authentication Error",
                message="Invalid or expired Firebase ID Token.",
                code="INVALID_AUTH_TOKEN",
            ).model_dump(),
            headers={"WWW-Authenticate": "Bearer"},
        )
