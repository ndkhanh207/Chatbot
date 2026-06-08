import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from utils import format_currency_vietnam, normalize_text
from functools import lru_cache

def build_corpus_embeddings(model, texts):
    """Encode a list of texts into a NumPy matrix.

    The function is kept simple because the corpus is static and is computed only
    once during server startup.  No caching is required here.
    """
    return model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

@lru_cache(maxsize=128)
def _cached_encode_query(embedding_model, query: str):
    """Cache the embedding of a query string.

    ``SentenceTransformer.encode`` is relatively cheap for short queries but can
    become a bottleneck when the same query is issued repeatedly (e.g., during
    testing or when users repeat common questions).  Using ``functools.lru_cache``
    stores the most recent 128 query embeddings in memory, dramatically reducing
    latency for repeated queries.
    """
    # ``embedding_model.encode`` returns a NumPy array when ``convert_to_numpy``
    # is True.  We keep that behaviour for compatibility with the rest of the
    # code.
    return embedding_model.encode([query], convert_to_numpy=True)

def hybrid_search(q, category, top_k, knowledge_base, embedding_model, corpus_embeddings):
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
                mask = results['search_text'].astype(str).str.contains(q_clean, case=False, na=False)
                keyword_scores[np.arange(score_length)[mask.values]] = 1.0
            else:
                # Fallback to previous name‑only logic for backward
                # compatibility if the column is missing.
                if 'tên' in results.columns:
                    name_mask = results['tên'].astype(str).str.contains(q_clean, case=False, na=False)
                    keyword_scores[np.arange(score_length)[name_mask.values]] = 1.0
                elif 'name' in results.columns:
                    name_mask = results['name'].astype(str).str.contains(q_clean, case=False, na=False)
                    keyword_scores[np.arange(score_length)[name_mask.values]] = 1.0

            # ---------------------------------------------------------------
            # Semantic similarity – unchanged, still uses cached query embedding.
            # ---------------------------------------------------------------
            if embedding_model is not None and corpus_embeddings is not None and q_clean:
                query_vector = _cached_encode_query(embedding_model, q_clean)
                all_similarities = cosine_similarity(query_vector, corpus_embeddings[results.index])[0]
                semantic_scores = all_similarities

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