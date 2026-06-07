from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from config import Config
import pandas as pd
import torch
import os
from data_loader import load_knowledge_base, convert_to_documents

# Tắt thông báo nhắc nhở ẩn danh của Chroma
os.environ["ANONYMIZED_TELEMETRY"] = "False"

def test_cosine_similarity():
    print("==================================================")
    print("📊 KIỂM TRA ĐỘ TƯƠNG ĐỒNG COSINE TRONG DATABASE")
    print("==================================================")
    
    # 1. Lấy cấu hình thiết bị và mô hình từ config
    device = Config.EMBEDDING_DEVICE or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"🚀 Thiết bị đang sử dụng để xử lý Vector: {device.upper()}")
    
    # 2. Khởi tạo mô hình Embedding tiếng Việt
    print("⏳ Đang nạp mô hình Embedding...")
    embeddings = HuggingFaceEmbeddings(
        model_name=Config.EMBEDDING_MODEL,
        model_kwargs={'device': device}
    )
    
    # 3. Kết nối vào thư mục ChromaDB hiện tại
    # Nếu DB chưa tồn tại, tự động tạo từ dữ liệu CSV
    if not os.path.exists(Config.VECTOR_DB_DIR) or not os.listdir(Config.VECTOR_DB_DIR):
        print(f"⚠️ Vector DB không tồn tại tại '{Config.VECTOR_DB_DIR}'. Đang tạo mới...")
        try:
            # Load dữ liệu gốc và chuyển thành Document
            knowledge_base = load_knowledge_base()
            docs = convert_to_documents(knowledge_base)
            # Khởi tạo embedding cho Chroma
            embeddings = HuggingFaceEmbeddings(
                model_name=Config.EMBEDDING_MODEL,
                model_kwargs={'device': device}
            )
            vector_store = Chroma(persist_directory=Config.VECTOR_DB_DIR, embedding_function=embeddings)
            vector_store.add_documents(docs)
            # Chroma automatically persists when a persist_directory is provided; no explicit persist() needed.
            print("✅ Đã tạo Vector DB thành công.")
        except Exception as e:
            print(f"❌ Lỗi khi tạo Vector DB: {e}")
            return

    vector_store = Chroma(
        persist_directory=Config.VECTOR_DB_DIR, 
        embedding_function=embeddings
    )
    
    # 4. Nhập câu hỏi bạn muốn test độ tương đồng ở đây
    query = "Tìm cho tôi một mainboard phù hơp với CPU Intel Core i5 12400F"
    # lấy top 10
    top_k = 10
    print(f"\n🔍 Câu hỏi test: '{query}'")
    print("⏳ Đang quét cơ sở dữ liệu và tính toán khoảng cách vector...\n")
    
    # 5. Thực hiện hàm tìm kiếm kèm tính Score (Khoảng cách Cosine)
    # k=5 nghĩa là xuất ra top 5 sản phẩm có độ tương đồng cao nhất
    results = vector_store.similarity_search_with_score(query, k=top_k)
    
    # 6. Đổ dữ liệu thô vào mảng để xử lý thành bảng Pandas
    table_rows = []
    for index, (doc, score) in enumerate(results, 1):
        content = doc.page_content.replace("\n", " | ").strip() # Làm sạch chuỗi hiển thị
        csv_row = doc.metadata.get('row', 'N/A') # Lấy vị trí dòng trong file CSV gốc
        
        table_rows.append({
            "Thứ hạng": f"Top {index}",
            "Dòng CSV": csv_row,
            "Nội dung chi tiết linh kiện": content,
            "Khoảng cách (Raw Score)": round(float(score), 4)
        })
        
    # 7. Khởi tạo bảng bằng Pandas
    df = pd.DataFrame(table_rows)
    
    # Cấu hình định dạng hiển thị cho bảng trên màn hình không bị cắt chữ
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_colwidth', None)
    pd.set_option('display.width', 1000)
    
    # 8. Xuất kết quả ra file markdown (đây là cách hiển thị mặc định)
    try:
        md_content = df.to_markdown(index=False)
        md_path = os.path.join(os.getcwd(), "cosine_results.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# Kết quả tìm kiếm độ tương đồng cosine\n\n")
            f.write(md_content)
        print(f"✅ Đã lưu kết quả vào file markdown: {md_path}")
    except Exception as e:
        print(f"⚠️ Không thể lưu file markdown: {e}")

    # 9. (Tùy chọn) Hiển thị bảng trên terminal nếu muốn xem nhanh
    try:
        from tabulate import tabulate
        print("\n🎯 BẢNG KẾT QUẢ TRA CỨU ĐỘ TƯƠNG ĐỒNG (hiển thị nhanh):")
        print(tabulate(df, headers="keys", tablefmt="psql", showindex=False))
    except Exception:
        # Nếu không có tabulate, hiển thị dạng pandas mặc định
        print("\n🎯 BẢNG KẾT QUẢ TRA CỨU ĐỘ TƯƠNG ĐỒNG (hiển thị nhanh):")
        print(df.to_string(index=False))
    print("==================================================")
    print("💡 MẸO ĐỌC BẢNG:")
    print("- Khoảng cách (Raw Score) CÀNG BÉ (gần về 0) = Độ tương đồng CÀNG CAO.")
    print("- Sản phẩm ở dòng Top 1 là linh kiện sát với nhu cầu của khách hàng nhất.")
    print("==================================================")

if __name__ == "__main__":
    test_cosine_similarity()