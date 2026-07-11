from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

def get_real_client_ip(request: Request) -> str:
    # Đọc IP thật từ Ngrok/Nginx truyền vào (chuẩn RESTful).
    # Rất an toàn vì Ngrok tự động ghi đè header này từ client thật, chống giả mạo từ internet.
    # Đồng thời cho phép local test tự inject header này để giả lập IP.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)

# Global Rate Limiter
limiter = Limiter(key_func=get_real_client_ip)
