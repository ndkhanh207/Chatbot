"""build_advisor.py – Tìm combo CPU + Mainboard + GPU tối ưu trong ngân sách,
hoặc combo 2 linh kiện (CPU+Main / GPU+Main) có kiểm tra tương thích.

Logic build 3 món:
- Ngân sách thực tế = 55% × số tiền user đề cập
- Brute-force top-K (6 mỗi loại → 216 combo) chọn tổng giá cao nhất ≤ budget

Logic combo 2 món:
- Phát hiện user hỏi đúng 2 loại linh kiện (cpu+main hoặc gpu+main)
- Tự parse ngân sách từ câu tiếng Việt (không dùng parse_price_condition)
- Kiểm tra tương thích trước khi trả kết quả
"""

import re
from itertools import product as iterproduct
from utils import format_currency_vietnam
from search_engine import hybrid_search, _detect_price_extreme, parse_price_condition
from compatibility import build_compatibility_context, is_compatibility_query

# Tỷ lệ ngân sách dành cho 3 linh kiện chính
BUDGET_RATIO = 0.55

# Số lượng ứng viên mỗi danh mục khi tìm combo
_CANDIDATE_K = 6


# ──────────────────────────────────────────────
# Budget parser riêng – không dùng parse_price_condition
# ──────────────────────────────────────────────

def _parse_budget_vn(text: str) -> float | None:
    """
    Parse ngân sách từ câu tiếng Việt. Hỗ trợ:
      - "30 triệu", "30tr", "30 tr"
      - "500k", "500 nghìn", "500 ngàn"
      - "1.5 triệu", "1,5 triệu"
      - "30000000", "30.000.000", "30,000,000"

    Trả về số thực (VNĐ) hoặc None nếu không parse được.
    """
    t = text.lower().strip()

    # Chuẩn hoá dấu phẩy thập phân kiểu "1,5" → "1.5"
    # (chỉ khi sau dấu phẩy là 1-2 chữ số)
    t_norm = re.sub(r',(\d{1,2})(?!\d)', r'.\1', t)
    # Xoá dấu chấm ngăn cách hàng nghìn: "30.000.000" → "30000000"
    t_norm = re.sub(r'\.(\d{3})(?!\d)', r'\1', t_norm)

    # 1) X triệu / X tr
    m = re.search(r'([\d]+(?:\.\d+)?)\s*tri[eệ]u', t_norm)
    if not m:
        m = re.search(r'([\d]+(?:\.\d+)?)\s*tr\b', t_norm)
    if m:
        return float(m.group(1)) * 1_000_000

    # 2) X nghìn / X ngàn / Xk
    m = re.search(r'([\d]+(?:\.\d+)?)\s*(?:ngh[iì]n|ng[àa]n)', t_norm)
    if not m:
        m = re.search(r'([\d]+(?:\.\d+)?)\s*k\b', t_norm)
    if m:
        return float(m.group(1)) * 1_000

    # 3) Số thuần >= 6 chữ số → đã là VNĐ
    digits_only = t_norm.replace('.', '').replace(',', '')
    m = re.search(r'\b(\d{6,})\b', digits_only)
    if m:
        return float(m.group(1))

    return None


# ──────────────────────────────────────────────
# Intent detection
# ──────────────────────────────────────────────

_BUILD_TRIGGERS = [
    'build pc', 'build máy', 'lắp máy', 'cấu hình máy', 'cấu hình pc',
    'bộ máy', 'máy tính tầm', 'pc tầm', 'pc dưới', 'pc trên',
    'máy dưới', 'máy trên', 'tổng giá', 'cộng giá', 'combo',
]

_CPU_HINTS  = ['cpu', 'vi xử lý', 'i3', 'i5', 'i7', 'i9', 'ryzen']
_GPU_HINTS  = ['gpu', 'vga', 'card', 'đồ họa', 'rtx', 'gtx', 'rx']
_MAIN_HINTS = ['main', 'mainboard', 'bo mạch', 'motherboard', 'h610', 'b760', 'z790', 'x670', 'a520']


def is_build_query(msg_lower: str) -> bool:
    return any(trigger in msg_lower for trigger in _BUILD_TRIGGERS)


def _detect_2component_intent(msg_lower: str) -> tuple[str, str] | None:
    """
    Phát hiện user hỏi đúng 2 loại linh kiện.
    Trả về ('CPU','MAINBOARD') hoặc ('GPU','MAINBOARD'), hoặc None.
    """
    has_cpu  = any(h in msg_lower for h in _CPU_HINTS)
    has_gpu  = any(h in msg_lower for h in _GPU_HINTS)
    has_main = any(h in msg_lower for h in _MAIN_HINTS)

    if has_cpu and has_main and not has_gpu:
        return ('CPU', 'MAINBOARD')
    if has_gpu and has_main and not has_cpu:
        return ('GPU', 'MAINBOARD')
    return None


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

def _fetch_candidates(q_neutral: str, category: str,
                      knowledge_base, embedding_model, corpus_embeddings) -> list:
    return hybrid_search(
        q=q_neutral,
        category=category,
        top_k=_CANDIDATE_K,
        knowledge_base=knowledge_base,
        embedding_model=embedding_model,
        corpus_embeddings=corpus_embeddings,
    )


def _fetch_candidates_for_combo(category: str, knowledge_base,
                                budget: float) -> list:
    """
    Lấy ứng viên cho combo search: KHÔNG dùng hybrid_search để tránh bị
    superlative filter. Lọc thẳng từ knowledge_base, chỉ lấy sản phẩm
    có giá <= budget (hoặc tất cả nếu budget = inf), trả về top _CANDIDATE_K
    sắp xếp theo giá giảm dần (đắt nhất trong budget lên trước).
    """
    if knowledge_base is None or knowledge_base.empty:
        return []

    price_col = 'giá' if 'giá' in knowledge_base.columns else 'price'

    # ── FIX: so sánh không phân biệt hoa/thường để tránh miss do data lưu
    # khác case (e.g. 'gpu' vs 'GPU', 'Mainboard' vs 'MAINBOARD')
    cat_upper = category.upper().strip()
    df = knowledge_base[knowledge_base['category'].str.upper().str.strip() == cat_upper].copy()

    if df.empty:

        if budget != float('inf'):
         df = df[df[price_col] <= budget]

    if df.empty:
        return []

    df = df.sort_values(by=price_col, ascending=False).head(_CANDIDATE_K)
    records = df.to_dict(orient='records')

    for r in records:
        price_val = r.get('giá') if 'giá' in r else r.get('price', 0)
        from utils import format_currency_vietnam as _fmt
        r['price_formatted'] = _fmt(price_val)
        r['is_fallback'] = False
        r.pop('hybrid_score', None)
        r.pop('search_text', None)

    return records


def _item_price(record: dict) -> float:
    val = record.get('giá') if 'giá' in record else record.get('price', 0)
    return float(val or 0)


def _find_best_combo(cpus: list, mains: list, gpus: list,
                     budget: float) -> dict | None:
    """Brute-force 3 linh kiện, chọn tổng giá cao nhất ≤ budget."""
    best = None
    best_total = float('inf')

    for cpu, main, gpu in iterproduct(cpus, mains, gpus):
        if cpu.get('is_fallback') or main.get('is_fallback') or gpu.get('is_fallback'):
            continue
        total = _item_price(cpu) + _item_price(main) + _item_price(gpu)
        if total > budget:
            continue
        if best is None or total > best_total:
            best = (cpu, main, gpu)
            best_total = total

    if best is None:
        return None

    cpu, main, gpu = best
    total_price = _item_price(cpu) + _item_price(main) + _item_price(gpu)
    return {
        'cpu': cpu, 'mainboard': main, 'gpu': gpu,
        'total_price': total_price,
        'total_price_formatted': format_currency_vietnam(total_price),
        'budget': budget,
        'budget_formatted': format_currency_vietnam(budget),
    }


# ──────────────────────────────────────────────
# Combo 2 linh kiện có tương thích
# ──────────────────────────────────────────────

def _check_socket_compatible(item_a: dict, item_b: dict) -> bool:
    socket_a = str(item_a.get('socket', item_a.get('socket_type', ''))).strip().upper()
    socket_b = str(item_b.get('socket', item_b.get('socket_type', ''))).strip().upper()
    if not socket_a or not socket_b:
        return True
    # ── FIX: loại bỏ trường hợp socket là 'NAN' do pandas đọc NaN thành chuỗi
    if socket_a in ('NAN', 'NONE', '') or socket_b in ('NAN', 'NONE', ''):
        return True
    return socket_a == socket_b


def _find_best_2combo(items_a: list, items_b: list,
                      cat_a: str, cat_b: str,
                      budget: float, mode: str) -> dict | None:
    need_socket_check = {cat_a, cat_b} == {'CPU', 'MAINBOARD'}
    candidates = []

    for a, b in iterproduct(items_a, items_b):
        if a.get('is_fallback') or b.get('is_fallback'):
            continue

        compatible = _check_socket_compatible(a, b) if need_socket_check else True
        total = _item_price(a) + _item_price(b)

        if mode not in ('lowest', 'highest') and total > budget:
            continue

        candidates.append({
            'item_a': a, 'item_b': b,
            'cat_a': cat_a, 'cat_b': cat_b,
            'total_price': total,
            'compatible': compatible,
        })

    if not candidates:
        return None

    compatible_ones = [c for c in candidates if c['compatible']]

    if mode == 'lowest':
        pool = compatible_ones or candidates
        best = min(pool, key=lambda x: x['total_price'])
    elif mode == 'highest':
        pool = compatible_ones or candidates
        best = max(pool, key=lambda x: x['total_price'])
    else:
        if not compatible_ones:
            return {'no_compatible': True, 'budget': budget}
        best = max(compatible_ones, key=lambda x: x['total_price'])

    total_price = best['total_price']
    return {
        'item_a': best['item_a'],
        'item_b': best['item_b'],
        'cat_a': best['cat_a'],
        'cat_b': best['cat_b'],
        'compatible': best['compatible'],
        'total_price': total_price,
        'total_price_formatted': format_currency_vietnam(total_price),
        'budget': budget if budget != float('inf') else None,
        'budget_formatted': format_currency_vietnam(budget) if budget != float('inf') else None,
    }


def find_2component_combo(user_message: str,
                          knowledge_base,
                          embedding_model,
                          corpus_embeddings,
                          compatibility_rules=None) -> dict | None:
    """
    Tìm combo 2 linh kiện có kiểm tra tương thích.
    Dùng _parse_budget_vn() thay vì parse_price_condition để tránh lỗi parse sai đơn vị.
    """
    msg = user_message.lower()

    pair = _detect_2component_intent(msg)
    if pair is None:
        return None

    cat_a, cat_b = pair

    # ── Xác định ngân sách bằng parser riêng ─────────────────────────────
    extreme = _detect_price_extreme(msg)
    if extreme == 'lowest':
        budget = float('inf')
        mode = 'lowest'
    elif extreme == 'highest':
        budget = float('inf')
        mode = 'highest'
    else:
        budget = _parse_budget_vn(user_message)
        if budget is None:
            # Không có giá cụ thể → tư vấn sản phẩm tốt nhất không giới hạn
            budget = float('inf')
            mode = 'highest'
        else:
            # Xác định mode: "dưới/tầm" → less, "trên" → greater
            if any(w in msg for w in ['dưới', 'không quá', 'tối đa', 'tầm', 'khoảng']):
                mode = 'less'
            elif any(w in msg for w in ['trên', 'hơn', 'tối thiểu']):
                mode = 'greater'
            else:
                mode = 'less'  # mặc định: tổng giá ≤ budget

    # ── Lấy ứng viên ────────────────────────────────────────────────────
    per_item_budget = (budget / 2) if (mode == 'less' and budget != float('inf')) else float('inf')
    items_a = _fetch_candidates_for_combo(cat_a, knowledge_base, per_item_budget)
    items_b = _fetch_candidates_for_combo(cat_b, knowledge_base, per_item_budget)

    items_a = [r for r in items_a if not r.get('is_fallback')]
    items_b = [r for r in items_b if not r.get('is_fallback')]

    if not items_a or not items_b:
        return {'no_result': True, 'budget': budget, 'mode': mode, 'pair': pair}

    result = _find_best_2combo(items_a, items_b, cat_a, cat_b, budget, mode)

    if result is None:
        return {'no_result': True, 'budget': budget, 'mode': mode, 'pair': pair}

    return result


# ──────────────────────────────────────────────
# Public API – 3 linh kiện (giữ nguyên)
# ──────────────────────────────────────────────

def find_build_combo(user_message: str, knowledge_base,
                     embedding_model, corpus_embeddings) -> dict | None:
    msg = user_message.lower()

    extreme = _detect_price_extreme(msg)
    if extreme == 'lowest':
        budget = float('inf')
        mode = 'lowest'
    elif extreme == 'highest':
        budget = float('inf')
        mode = 'highest'
    else:
        _, _, target_price, price_mode = parse_price_condition(user_message)
        if target_price is None:
            return None
        budget = target_price * BUDGET_RATIO
        mode = price_mode

    neutral_q = ''
    cpus  = _fetch_candidates(neutral_q, 'CPU',       knowledge_base, embedding_model, corpus_embeddings)
    mains = _fetch_candidates(neutral_q, 'MAINBOARD', knowledge_base, embedding_model, corpus_embeddings)
    gpus  = _fetch_candidates(neutral_q, 'GPU',       knowledge_base, embedding_model, corpus_embeddings)

    cpus  = [r for r in cpus  if not r.get('is_fallback')]
    mains = [r for r in mains if not r.get('is_fallback')]
    gpus  = [r for r in gpus  if not r.get('is_fallback')]

    if not cpus or not mains or not gpus:
        return {'no_result': True, 'budget': budget, 'mode': mode}

    if mode == 'lowest':
        for lst in (cpus, mains, gpus):
            lst.sort(key=_item_price)
        combo = {'cpu': cpus[0], 'mainboard': mains[0], 'gpu': gpus[0]}
    elif mode == 'highest':
        for lst in (cpus, mains, gpus):
            lst.sort(key=_item_price, reverse=True)
        combo = {'cpu': cpus[0], 'mainboard': mains[0], 'gpu': gpus[0]}
    else:
        combo = _find_best_combo(cpus, mains, gpus, budget)
        if combo is None:
            return {'no_result': True, 'budget': budget, 'mode': mode}
        return combo

    total = sum(_item_price(combo[k]) for k in combo)
    combo['total_price'] = total
    combo['total_price_formatted'] = format_currency_vietnam(total)
    combo['budget'] = None
    combo['budget_formatted'] = None
    return combo


# ──────────────────────────────────────────────
# Context builders
# ──────────────────────────────────────────────

def build_2combo_context(combo: dict) -> str:
    """Chuyển kết quả combo 2 linh kiện thành context cho LLM."""
    if combo.get('no_result') or combo.get('no_compatible'):
        return ''  # Caller sẽ xử lý trực tiếp, không qua LLM

    def _fmt(label, record):
        name  = record.get('tên') or record.get('name', '?')
        price = record.get('price_formatted') or format_currency_vietnam(
            record.get('giá') or record.get('price', 0)
        )
        sock  = record.get('socket') or record.get('socket_type', '')
        sock_info = f' | Socket: {str(sock).upper()}' if sock and str(sock).upper() not in ('NAN', 'NONE', '') else ''
        return f"- [{label}] {name} | Giá: {price} VNĐ{sock_info}"

    cat_a = combo.get('cat_a', 'LINH KIỆN A')
    cat_b = combo.get('cat_b', 'LINH KIỆN B')
    compat = '✅ TƯƠNG THÍCH' if combo.get('compatible', True) else '⚠️ CÓ THỂ KHÔNG TƯƠNG THÍCH'

    lines = [f"GỢI Ý COMBO 2 LINH KIỆN ({cat_a} + {cat_b}) – {compat}:"]
    lines.append(_fmt(cat_a, combo['item_a']))
    lines.append(_fmt(cat_b, combo['item_b']))
    lines.append(f"→ Tổng giá 2 linh kiện: {combo['total_price_formatted']} VNĐ")
    if combo.get('budget_formatted'):
        lines.append(f"(Ngân sách yêu cầu: {combo['budget_formatted']} VNĐ)")
    lines.append(
        "\nHướng dẫn trả lời: Liệt kê đúng 2 sản phẩm trên + tổng giá + trạng thái tương thích. "
        "Không thêm, không bớt, không so sánh."
    )
    return "\n".join(lines)


def build_2combo_no_result_reply(combo: dict) -> str:
    """
    Tạo câu trả lời thẳng (KHÔNG qua LLM) khi không tìm được combo.
    Dùng khi model quá nhỏ không thể tuân thủ instruction.
    """
    pair = combo.get('pair', ('linh kiện', 'linh kiện'))
    cat_a, cat_b = pair

    budget = combo.get('budget')
    budget_str = format_currency_vietnam(budget) + ' VNĐ' if budget and budget != float('inf') else 'yêu cầu'

    if combo.get('no_compatible'):
        return (
            f"Dạ, em đã tìm trong kho nhưng hiện không có cặp {cat_a} + {cat_b} nào "
            f"tương thích với nhau trong tầm giá {budget_str} ạ. "
            f"Bạn có thể cho em biết thêm yêu cầu cụ thể hơn không?"
        )
    return (
        f"Dạ, hiện tại trong kho không có combo {cat_a} + {cat_b} nào "
        f"phù hợp trong tầm giá {budget_str} ạ. "
        f"Bạn thử tăng ngân sách lên một chút hoặc cho em biết ưu tiên linh kiện nào nhé!"
    )


def build_combo_context(combo: dict) -> str:
    """Chuyển kết quả combo 3 linh kiện thành context cho LLM."""
    if combo.get('no_result'):
        budget_fmt = (
            format_currency_vietnam(combo['budget'])
            if combo.get('budget') and combo['budget'] != float('inf') else '?'
        )
        return (
            f"THÔNG BÁO HỆ THỐNG: Không tìm được bộ 3 linh kiện (CPU + Mainboard + GPU) "
            f"phù hợp trong ngân sách {budget_fmt} VNĐ (55% tổng ngân sách).\n"
            f"Hãy thông báo thành thật, không gợi ý thay thế."
        )

    def _fmt(label, record):
        name  = record.get('tên') or record.get('name', '?')
        price = record.get('price_formatted') or format_currency_vietnam(
            record.get('giá') or record.get('price', 0)
        )
        return f"- [{label}] {name} | Giá: {price} VNĐ"

    lines = ["GỢI Ý BUILD PC (CPU + Mainboard + GPU):"]
    lines.append(_fmt('CPU',       combo['cpu']))
    lines.append(_fmt('MAINBOARD', combo['mainboard']))
    lines.append(_fmt('GPU',       combo['gpu']))
    lines.append(f"→ Tổng giá 3 linh kiện: {combo['total_price_formatted']} VNĐ")
    if combo.get('budget_formatted'):
        lines.append(f"(Ngân sách 3 linh kiện = 55% × yêu cầu = {combo['budget_formatted']} VNĐ)")
    lines.append(
        "\nHướng dẫn trả lời: Liệt kê đúng 3 sản phẩm trên + tổng giá. "
        "Không thêm, không bớt, không so sánh."
    )
    return "\n".join(lines)