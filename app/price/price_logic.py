

def filter_knowledge_base_by_price(knowledge_base, category, lo, hi, brand=None, model_query=None, top_k=10):
    """
    Lọc TRỰC TIẾP trên toàn bộ knowledge_base (DataFrame) theo khoảng giá,
    hãng (brand), và/hoặc model cụ thể (model_query) — không phụ thuộc
    vào kết quả semantic search top_k.
    Trả về (list[dict], total_count).
    """
    df = knowledge_base
    price_col = "giá" if "giá" in df.columns else "price"

    mask = (df[price_col] >= lo) & (df[price_col] <= hi)
    if category and "category" in df.columns:
        mask &= (df["category"] == category)

    search_col = "chipset" if "chipset" in df.columns else (
        "tên" if "tên" in df.columns else "name"
    )

    if brand:
        mask &= df[search_col].str.contains(brand, case=False, na=False)

    # ⭐ Lọc theo model cụ thể (vd "4070") — đặt SAU brand để cộng dồn điều
    # kiện, tránh việc câu hỏi có model cụ thể bị brand-wide filter nuốt mất
    # (bug cũ: "RTX 4070" từng bị trộn lẫn với toàn bộ GPU geforce trong kho).
    if model_query:
        col_lower = df[search_col].str.lower()
        mask &= col_lower.str.contains(model_query["digits"], na=False)
        if model_query["suffix"]:
            mask &= col_lower.str.contains(model_query["suffix"], na=False)

    full_match = df[mask]
    if full_match.empty:
        return [], 0

    total_count = len(full_match)
    sorted_df = full_match.sort_values(by=price_col)

    if total_count <= top_k:
        sample = sorted_df
    else:
        step = max(1, total_count // top_k)
        sample = sorted_df.iloc[::step].head(top_k)

    return sample.to_dict(orient="records"), total_count