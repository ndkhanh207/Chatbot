import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from util.utils import normalize_text
from app.price.pricing import format_currency_vietnam

def hybrid_search(q, category, top_k, knowledge_base, vector_store):
    if knowledge_base is None or knowledge_base.empty:
        return []

    results = knowledge_base.copy()
    if category:
        results = results[results['category'] == category.upper().strip()]
        if results.empty:
            return []

    score_length = len(results) # Dùng len(results) sau khi đã lọc để khớp với index
    keyword_scores = np.zeros(score_length)
    semantic_scores = np.zeros(score_length)

    if q:
            q_clean = normalize_text(q)
            # ---------------------------------------------------------------
            # Unified keyword matching using the pre‑computed ``search_text``
            # column (created in ``data_loader.load_knowledge_base``). This
            # column concatenates all relevant textual fields, so a single
            # ``contains`` check is sufficient to capture any spec‑related
            # query without manually enumerating each possible column.
            # ---------------------------------------------------------------
            if 'search_text' in results.columns:
                mask = results['search_text'].astype(str).str.contains(q_clean, case=False, na=False, regex=False)
                keyword_scores[np.arange(score_length)[mask.values]] = 1.0
            else:
                # Fallback to previous name‑only logic for backward
                # compatibility if the column is missing.
                if 'tên' in results.columns:
                    name_mask = results['tên'].astype(str).str.contains(q_clean, case=False, na=False, regex=False)
                    keyword_scores[np.arange(score_length)[name_mask.values]] = 1.0
                elif 'name' in results.columns:
                    name_mask = results['name'].astype(str).str.contains(q_clean, case=False, na=False, regex=False)
                    keyword_scores[np.arange(score_length)[name_mask.values]] = 1.0

            # ---------------------------------------------------------------
            # Semantic similarity using Chroma DB
            # ---------------------------------------------------------------
            if vector_store is not None and q_clean:
                try:
                    search_filter = {"category": category.upper().strip()} if category else None
                    docs_and_scores = vector_store.similarity_search_with_score(
                        q_clean, 
                        k=top_k * 4, 
                        filter=search_filter
                    )
                    
                    for doc, distance in docs_and_scores:
                        row_idx = doc.metadata.get("row")
                        # Chroma returns distance (smaller is better). Convert to similarity score [0, 1].
                        # Usually L2 distance can range higher, but 1 / (1 + dist) maps it nicely.
                        # Alternatively, simple clamping: max(0, 1 - distance) if cosine.
                        # We use a robust normalization 1 / (1 + distance)
                        similarity = 1.0 / (1.0 + float(distance))
                        
                        if row_idx is not None and row_idx in results.index:
                            # Map the original row_idx to the filtered results positional index
                            pos_indices = np.where(results.index == row_idx)[0]
                            if len(pos_indices) > 0:
                                semantic_scores[pos_indices[0]] = max(semantic_scores[pos_indices[0]], similarity)
                except Exception as e:
                    print(f"Lỗi khi tìm kiếm qua Chroma: {e}")

    # Kết hợp điểm số
    results['hybrid_score'] = 0.4 * keyword_scores + 0.6 * semantic_scores

    top_results = results.sort_values(by='hybrid_score', ascending=False).head(top_k)
    records = top_results.to_dict(orient='records')

    for record in records:
        # format giá sang tiếng việt có dấu và đơn vị VND
        price_val = record.get('giá') if 'giá' in record else record.get('price', 0)
        record['price_formatted'] = format_currency_vietnam(price_val)
        # Remove internal fields before returning to the user
        record.pop('hybrid_score', None)
        record.pop('search_text', None)

    return records