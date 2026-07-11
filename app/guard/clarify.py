# ── Thêm vào đầu file, sau các import ──────────────────────
import threading
from app.core.llm_chains import get_emergency_chain
from app.core.health import reset_ollama_model
from app.memory.memory_store import get_trimmed_history
from langchain_core.runnables import RunnableSequence
from collections import OrderedDict
import asyncio
import re

class LRUCache(OrderedDict):
    """
    LRUCache caps memory limit. Keeps 100 newest items. Drops oldest item when full.
     Stops memory leak from infinite _session_context_cache growth.
    """
    def __init__(self, capacity=100):
        super().__init__()
        self.capacity = capacity

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        if len(self) > self.capacity:
            self.popitem(last=False)

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

_session_context_cache = LRUCache(100)

_REJECTION_PATTERNS = [
    "không cần", "cứ tìm", "cứ đưa", "thôi được",
    "đưa ra đi", "tìm luôn", "kệ đi", "cứ gợi ý",
    "không có gì thêm", "cứ liệt kê", "đưa luôn"
]

_ASKING_PATTERNS = [
    "bạn có thể cung cấp",
    "bạn có thể cho tôi biết",
    "bạn muốn tìm",
    "cho tôi biết thêm",
    "yêu cầu cụ thể",
    "sở thích của bạn",
    "ngân sách của bạn",
    "có thể cho em biết",
    "cho em biết rõ",
]

_POLITE_CLOSINGS = [
    "bạn có cần thêm thông tin gì khác không",
    "bạn có cần thông tin gì khác không",
    "bạn có cần hỗ trợ gì thêm không",
    "bạn có câu hỏi nào khác không",
    "bạn có muốn biết thêm",
    "bạn cần hỗ trợ gì thêm",
    "bạn cần thêm thông tin gì không",
    "cần thêm thông tin gì khác không",
    "bạn có muốn tham khảo thêm",   
]

_FALSE_COMPAT_PATTERNS = [
    "đều là các sản phẩm tương thích",
    "hai sản phẩm tương thích",
    "sản phẩm tương thích với nhau",
]

_INCOMPAT_VERDICTS = [
    "không tương thích",
    "không phù hợp",
]

_BOTTLENECK_VERDICTS = [
    "nghẽn",
    "cpu yếu",
    "gpu yếu",
]

_BANDWIDTH_VERDICTS = [
    "băng thông",
    "pcie",
]


def _is_context_valid(context: str) -> bool:
    """
    Context hợp lệ khi có data thật để LLM làm việc.
    Nếu data rác → không nên retry, LLM có retry cũng vô nghĩa.
    """
    if not context or len(context) < 30:
        return False
    # Tên sản phẩm là None → data rác từ DB
    if "] None |" in context:
        return False
    # Không có giá hợp lệ
    if "Giá: None" in context or "Giá: 0" in context:
        return False
    return True

def _is_clarification_rejection(text: str) -> bool:
    """Kiểm tra user có đang từ chối việc đưa thêm thông tin khi bot hỏi lại ."""
    t = text.lower().strip()
    return any(p in t for p in _REJECTION_PATTERNS)


def _is_asking_clarification(reply: str) -> bool:
    r = reply.lower().strip()
    
    # Nếu câu trả lời chứa thông tin giá trị (số tiền, cấu hình), hoặc kết luận tương thích, xem như đã trả lời
    valid_data_keywords = [
        "vnđ", "triệu", "giá là", "có giá", "gb ", "mhz", "ghz",
        "tương thích", "phù hợp", "không tương thích", "không phù hợp",
        "bottleneck", "nghẽn", "cảnh báo", "gợi ý", "đề xuất", "dạ đây là"
    ]
    has_data = any(x in r for x in valid_data_keywords)
    
    # Loại bỏ các câu hỏi lịch sự cuối câu trước khi đếm dấu hỏi
    for polite in _POLITE_CLOSINGS:
        if polite in r:
            r = r.replace(polite + "?", "").replace(polite, "").strip()
            
    is_asking = r.endswith("?") or r.count("?") >= 2 or any(p in r for p in _ASKING_PATTERNS)
    
    # Nếu có dấu hiệu hỏi vặn nhưng ĐÃ trả lời thông tin trước đó -> Hợp lệ, không chặn
    if is_asking and has_data:
        return False
        
    return is_asking


def _is_compatibility_hallucination(raw: str, context: str) -> bool:
    """
    Kiểm tra ảo giác của LLM trong luồng compatibility:
    - Báo tương thích khi dữ liệu ghi KHÔNG TƯƠNG THÍCH.
    - Bỏ quên cảnh báo BOTTLENECK hoặc CẢNH BÁO BĂNG THÔNG.
    """
    r_low = raw.lower().strip()
    if "KHÔNG TƯƠNG THÍCH" in context:
        has_false_claim = any(p in r_low for p in _FALSE_COMPAT_PATTERNS)
        has_incompat_verdict = any(v in r_low for v in _INCOMPAT_VERDICTS)
        if has_false_claim or not has_incompat_verdict:
            print("⚠️ [OUTPUT-GUARD] LLM trả lời sai KHÔNG TƯƠNG THÍCH → format trực tiếp")
            return True

    if "BOTTLENECK" in context:
        if not any(v in r_low for v in _BOTTLENECK_VERDICTS):
            print("⚠️ [OUTPUT-GUARD] LLM bỏ quên BOTTLENECK → format trực tiếp")
            return True

    if "CẢNH BÁO BĂNG THÔNG" in context:
        if not any(v in r_low for v in _BANDWIDTH_VERDICTS):
            print("⚠️ [OUTPUT-GUARD] LLM bỏ quên CẢNH BÁO BĂNG THÔNG → format trực tiếp")
            return True

    return False

def _format_context_directly(context: str, intent: str) -> str:
    """Bypass LLM — format context thành reply đọc được."""
    if not context:
        return "Dạ em chưa tìm thấy sản phẩm phù hợp ạ."
    
    header = {
        "suggestion":    "Dạ đây là các linh kiện em tìm được ạ:\n\n",
        "compatibility": "Dạ đây là kết quả kiểm tra tương thích:\n\n",
    }.get(intent, "Dạ đây là thông tin em tìm được:\n\n")
    
    return header + context

def _remove_repetitive_paragraphs(text: str) -> str:
    """Loại bỏ các câu văn bị LLM lặp lại vô tận (repetition collapse)."""
    # Tách văn bản thành các câu dựa trên dấu chấm, hỏi, chấm than
    sentences = re.split(r'(?<=[.?!])\s+', text)
    seen = set()
    result = []
    for s in sentences:
        cleaned = s.strip()
        if not cleaned:
            continue
        # Chỉ xét trùng với các câu có độ dài tương đối (tránh xóa nhầm các câu ngắn "Dạ.", "Vâng.")
        if len(cleaned) > 15:
            if cleaned not in seen:
                seen.add(cleaned)
                result.append(s)
        else:
            result.append(s)
    return " ".join(result).strip()

async def chain_invoke_async(chain, context, format_hint, user_message_fixed, chat_history, parsed_intent):
    """
    Gọi lại chain đã lưu trước đó khi user từ chối yêu cầu bổ sung thông tin.
    """
    MAX_RETRY = 1
    reply = None
    if parsed_intent.intent != "none" and not _is_context_valid(context):
            print("⚠️ [CONTEXT-GUARD] Context không hợp lệ → bypass LLM")
            reply = (
                "Dạ em chưa tìm thấy thông tin chính xác về sản phẩm này ạ. "
                "Bạn có thể cho em biết rõ hơn tên model không ạ?"
            )
    else:
        # Context hợp lệ → mới áp dụng output guard
        MAX_RETRY = 1
        for attempt in range(MAX_RETRY + 1):
            try:
                response = await asyncio.wait_for(
                    chain.ainvoke({
                        "context":      context,
                        "format_hint":  format_hint,
                        "user_message": user_message_fixed,
                        "chat_history": chat_history,
                    }),
                    timeout=45.0
                )
            except asyncio.TimeoutError:
                print(f"🚨 [OUTPUT-GUARD] Ollama server bị treo (Timeout) ở lần thử {attempt+1}!")
                await reset_ollama_model()
                reply = _format_context_directly(context, parsed_intent.intent)
                break
            except Exception as e:
                print(f"🚨 [OUTPUT-GUARD] Lỗi gọi LLM: {e}")
                reply = _format_context_directly(context, parsed_intent.intent)
                break

            raw = response.content
            raw = _remove_repetitive_paragraphs(raw)
            print(f"[RAW LLM OUTPUT - attempt {attempt}]: {raw}")

            # nếu là giao tiếp thông thường thì không chặn lại
            if parsed_intent.intent == "none":
                reply = raw
                break

            if not _is_asking_clarification(raw):
                # Kiểm tra ảo giác của LLM 1.5B trong luồng compatibility
                if parsed_intent.intent == "compatibility" and _is_compatibility_hallucination(raw, context):
                    reply = _format_context_directly(context, parsed_intent.intent)
                    break
                reply = raw     # ✅ hợp lệ
                break

            if attempt < MAX_RETRY:
                print(f"⚠️ [OUTPUT-GUARD] Phát hiện hỏi vặn, retry lần {attempt+1}...")
                if parsed_intent.intent == "compatibility":
                    print("🚨 [OUTPUT-GUARD] Luồng compatibility không dùng emergency list → format trực tiếp")
                    reply = _format_context_directly(context, parsed_intent.intent)
                    break
                else:
                    chain = get_emergency_chain()
            else:
                print("🚨 [OUTPUT-GUARD] Retry thất bại → format trực tiếp")
                reply = _format_context_directly(context, parsed_intent.intent)
    return reply

