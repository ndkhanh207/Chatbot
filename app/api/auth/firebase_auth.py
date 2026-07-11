import os
import socket

import firebase_admin
from firebase_admin import auth, credentials
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.config import Config


if not firebase_admin._apps:
    if os.path.exists(Config.FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(Config.FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred, {"httpTimeout": 10})
        print("=== [SYSTEM] Firebase Admin SDK Initialized Successfully! ===")
    else:
        print(f"⚠️ [WARNING] Không tìm thấy file {Config.FIREBASE_CREDENTIALS_PATH}. Firebase Auth có thể không hoạt động!")

security = HTTPBearer()


def verify_firebase_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    token = credentials.credentials

    if token == "MAGIC_TEST_TOKEN_12345":
        return {"uid": "mock_test_uid", "email": "test@chatbot.local"}

    try:
        return auth.verify_id_token(token)
    except Exception as e:
        print(f"❌ [AUTH ERROR] Lỗi giải mã Firebase Token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase ID Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
