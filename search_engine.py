import numpy as np
import re
from sklearn.metrics.pairwise import cosine_similarity
from utils import format_currency_vietnam, normalize_text
from functools import lru_cache


# ──────────────────────────────────────────────
# Price condition parser
# ──────────────────────────────────────────────

_HIGHEST_PRICE_KEYWORDS = [
    'cao nhất', 'đắt nhất', 'mắc nhất', 'giá cao',
    'cao cấp nhất', 'xịn nhất', 'tốt nhất',
]
_LOWEST_PRICE_KEYWORDS = [
    'thấp nhất', 'rẻ nhất', 'giá rẻ nhất',
    'tiết kiệm nhất', 'bình dân nhất', 'giá thấp nhất',
]


def _detect_price_extreme(query: str):
    """Return 'highest', 'lowest', or None."""
    q = query.lower()
    if any(kw in q for kw in _HIGHEST_PRICE_KEYWORDS):
        return 'highest'
    if any(kw in q for kw in _LOWEST_PRICE_KEYWORDS):
        return 'lowest'
    return None


def parse_price_condition(query: str):
    """Trích xuất điều kiện giá từ câu query.

    Trả về: (min_price, max_price, target_price, mode)
    - target_price: mức giá neo dùng để sort kết quả theo khoảng cách gần nhất
    - mode: 'exact_range' | 'greater' | 'less' | None
    """
    if not query:
        return None, None, None, None

    query_lower = query.lower()
    numbers = re.findall(r'\d+(?:\.\d+)?', query_lower)

    if not numbers:
        return None, None, None, None

    base_multiplier = 1
    if 'triệu' in query_lower or ' tr' in query_lower:
        base_multiplier = 1_000_000
    elif 'ngàn' in query_lower or ' k' in query_lower:
        base_multiplier = 1_000

    extracted_num = float(numbers[0]) * base_multiplier

    # "trên / hơn X" → target là X (lấy những cái vừa vượt ngưỡng, gần X nhất)
    if any(kw in query_lower for kw in ['trên', 'hơn', 'lớn hơn', 'cao hơn', '>=', '>']):
        return extracted_num, None, extracted_num, 'greater'

    # "dưới / thấp hơn X" → target là X (lấy những cái gần X nhất từ dưới lên)
    if any(kw in query_lower for kw in ['dưới', 'thấp hơn', 'nhỏ hơn', '<=', '<']):
        return None, extracted_num, extracted_num, 'less'

    # "tầm khoảng X" → band ±15%, target là chính X
    min_p = extracted_num * 0.75
    max_p = extracted_num * 1.15
    return min_p, max_p, extracted_num, 'exact_range'


# ──────────────────────────────────────────────
# Embedding helpers
# ──────────────────────────────────────────────

def build_corpus_embeddings(model, texts):
    """Encode a list of texts into a NumPy matrix (run once at startup)."""
    return model.encode(texts, show_progress_bar=True, convert_to_numpy=True)


@lru_cache(maxsize=128)
def _cached_encode_query(embedding_model, query: str):
    """Cache query embeddings to avoid redundant encode calls."""
    return embedding_model.encode([query], convert_to_numpy=True)


# ──────────────────────────────────────────────
# Main search function
# ──────────────────────────────────────────────

def hybrid_search(q, category, top_k, knowledge_base, embedding_model, corpus_embeddings):
    if knowledge_base is None or knowledge_base.empty:
        return []

    results = knowledge_base.copy()
    price_col = 'giá' if 'giá' in results.columns else 'price'

    if category:
        results = results[results['category'] == category.upper().strip()]
        if results.empty:
            return []

    # ── 1. Superlative intent: cao nhất / rẻ nhất (no numeric price) ──────
    price_extreme = _detect_price_extreme(q or '')
    if price_extreme is not None:
        ascending = (price_extreme == 'lowest')
        top_results = results.sort_values(by=price_col, ascending=ascending).head(1)
        records = top_results.to_dict(orient='records')
        for record in records:
            price_val = record.get('giá') if 'giá' in record else record.get('price', 0)
            record['price_formatted'] = format_currency_vietnam(price_val)
            record['is_fallback'] = False
            record.pop('hybrid_score', None)
            record.pop('search_text', None)
        return records

    # ── 2. Numeric price filtering ─────────────────────────────────────────
    min_price, max_price, target_price, price_mode = parse_price_condition(q)
    is_fallback_activated = False
    fallback_target = target_price  # giữ lại mức giá gốc user hỏi để báo lỗi

    if price_mode and price_col in results.columns:
        backup_results = results.copy()

        if price_mode == 'greater' and min_price is not None:
            results = results[results[price_col] >= min_price]
        elif price_mode == 'less' and max_price is not None:
            results = results[results[price_col] <= max_price]
        elif price_mode == 'exact_range' and min_price is not None and max_price is not None:
            results = results[
                (results[price_col] >= min_price) & (results[price_col] <= max_price)
            ]

        if results.empty:
            # Không có sản phẩm nào trong khoảng giá → báo fallback, KHÔNG gợi ý thay thế
            return [{
                'is_fallback': True,
                'fallback_target_price': fallback_target,
                'fallback_mode': price_mode,
                'category': category,
            }]

    # ── 3. Hybrid keyword + semantic scoring ───────────────────────────────
    score_length = len(results)
    keyword_scores = np.zeros(score_length)
    semantic_scores = np.zeros(score_length)

    if q:
        q_clean = normalize_text(q)

        if 'search_text' in results.columns:
            mask = results['search_text'].astype(str).str.contains(q_clean, case=False, na=False)
            keyword_scores[np.arange(score_length)[mask.values]] = 1.0
        else:
            for col in ('tên', 'name'):
                if col in results.columns:
                    m = results[col].astype(str).str.contains(q_clean, case=False, na=False)
                    keyword_scores[np.arange(score_length)[m.values]] = 1.0
                    break

        if embedding_model is not None and corpus_embeddings is not None and q_clean:
            query_vector = _cached_encode_query(embedding_model, q_clean)
            all_similarities = cosine_similarity(query_vector, corpus_embeddings[results.index])[0]
            semantic_scores = all_similarities

    results = results.copy()
    results['hybrid_score'] = 0.4 * keyword_scores + 0.6 * semantic_scores

    # ── 4. Final ranking ───────────────────────────────────────────────────
    if price_mode in ('less', 'greater') and target_price is not None:
        # Sort by proximity to target price (closest first), tie-break by hybrid score
        results['_price_dist'] = (results[price_col] - target_price).abs()
        top_results = (
            results
            .sort_values(by=['_price_dist', 'hybrid_score'], ascending=[True, False])
            .head(top_k)
        )
        results.drop(columns=['_price_dist'], inplace=True)
        top_results = top_results.drop(columns=['_price_dist'], errors='ignore')

    elif price_mode == 'exact_range' and len(results) >= 3:
        # Tầm khoảng: lấy 3 tầng giá (rẻ - trung - cao) trong band
        results_sorted = results.sort_values(by=price_col)
        chosen = list(set([0, len(results_sorted) // 2, len(results_sorted) - 1]))
        top_results = results_sorted.iloc[chosen].sort_values(by='hybrid_score', ascending=False)

    else:
        top_results = results.sort_values(by='hybrid_score', ascending=False).head(top_k)

    # ── 5. Serialise ───────────────────────────────────────────────────────
    records = top_results.to_dict(orient='records')
    for record in records:
        price_val = record.get('giá') if 'giá' in record else record.get('price', 0)
        record['price_formatted'] = format_currency_vietnam(price_val)
        record['is_fallback'] = False
        record.pop('hybrid_score', None)
        record.pop('search_text', None)
        record.pop('_price_dist', None)

    return records