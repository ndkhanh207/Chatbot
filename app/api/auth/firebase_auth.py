import os
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config.config import Config

# Chỉ khởi tạo Firebase Admin SDK 1 lần duy nhất trong suốt vòng đời ứng dụng
if not firebase_admin._apps:
    if os.path.exists(Config.FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(Config.FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        print(f"=== [SYSTEM] Firebase Admin SDK Initialized Successfully! ===")
    else:
        print(f"⚠️ [WARNING] Không tìm thấy file {Config.FIREBASE_CREDENTIALS_PATH}. Tính năng Firebase Auth có thể không hoạt động!")

security = HTTPBearer()

def verify_firebase_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    Dependency bắt buộc cho mọi API cần bảo mật.
    Tự động bóc tách token JWT (Bearer Token) và giải mã qua Firebase Admin.
    """
    token = credentials.credentials
    try:
        # Giải mã và xác thực token đồng bộ (nhưng chạy trong thread pool do khai báo là def)
        decoded_token = auth.verify_id_token(token)
        return decoded_token  # Dict chứa 'uid', 'email', 'name', 'picture'
    except Exception as e:
        print(f"❌ [AUTH ERROR] Lỗi giải mã Firebase Token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase ID Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
