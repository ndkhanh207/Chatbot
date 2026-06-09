import os
from pathlib import Path
import pandas as pd
from langchain_core.documents import Document 
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import Config
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from tqdm import tqdm
from multiprocessing import Pool
import warnings
warnings.filterwarnings('ignore')

# Đã đổi sang tiếng Việt theo đúng Header trong file CSV của bạn
DEFAULT_INT_COLS = ['số lõi', 'khe RAM', 'khe M.2', 'bộ nhớ', 'RAM tối đa', 'tdp']
DEFAULT_FLOAT_COLS = ['giá', 'xung cơ bản', 'xung boost', 'chiều dài']

# Bảng giá trị mặc định để chống lỗi Null
DEFAULT_FILL_VALUES = {col: 0.0 for col in DEFAULT_FLOAT_COLS + DEFAULT_INT_COLS}

FIELD_ALIAS_MAP = {
    'tdp': ['tdp', 'điện năng', 'điện năng tiêu thụ', 'công suất tiêu thụ'],
    'xung cơ bản': ['xung cơ bản', 'base clock'],
    'xung boost': ['xung boost', 'boost clock'],
}

DATA_DIR = Path(os.getenv('PC_STORE_DATA_DIR', Path(__file__).resolve().parent / 'data'))

def resolve_data_path(filename):
    return DATA_DIR / filename

def load_csv(filename, category):
    path = resolve_data_path(filename)
    if not path.exists():
        raise FileNotFoundError(f'Không tìm thấy file dữ liệu: {path}')
    
    df = pd.read_csv(path, keep_default_na=True)

    
    df['category'] = category
    return df

def normalize_dataframe(df):
    for column in DEFAULT_INT_COLS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors='coerce').fillna(0).astype('Int64')

    for column in DEFAULT_FLOAT_COLS:
        if column in df.columns and column not in DEFAULT_INT_COLS:
            df[column] = pd.to_numeric(df[column], errors='coerce')

    df = df.fillna(value=DEFAULT_FILL_VALUES)
    df = df.fillna("")
    return df

def load_knowledge_base():
    df_cpu = load_csv('cpu.csv', 'CPU')
    df_mainboard = load_csv('motherboard.csv', 'MAINBOARD')
    df_gpu = load_csv('gpu.csv', 'GPU')

    knowledge_base = pd.concat([df_cpu, df_mainboard, df_gpu], ignore_index=True)
    # Normalize numeric columns and fill missing values
    knowledge_base = normalize_dataframe(knowledge_base)

    # ---------------------------------------------------------------------
    # Create a unified searchable text field.
    # ---------------------------------------------------------------------
    # Many queries refer to specifications (e.g., "xung cơ bản", "độ nhớ")
    # that are stored in separate columns. To avoid having to manually
    # enumerate every possible column in the search logic, we concatenate all
    # non‑price, non‑empty values into a single string column ``search_text``.
    # This column is then used for simple keyword matching in ``search_engine``.

    def _make_search_text(row):
        parts = []
        for col, val in row.items():
            # Skip price fields – they are already handled separately
            if col.lower() in ('giá', 'price'):
                continue
            if pd.isna(val) or val == "" or (isinstance(val, (int, float)) and val == 0):
                continue
            parts.append(f"{col} {val}")
            alias_list = FIELD_ALIAS_MAP.get(col.lower())
            if alias_list:
                parts.extend(alias_list)
        return " ".join(parts)

    knowledge_base['search_text'] = knowledge_base.apply(_make_search_text, axis=1)

    return knowledge_base

# ==============================================================
# BỔ SUNG QUAN TRỌNG: Hàm chuyển DataFrame sang LangChain Document
# ==============================================================
def _process_row_for_docs(args):
    """Helper function for parallel document processing."""
    index, row, cols_to_use = args
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    
    content_parts = []
    for col in cols_to_use:
        val = row.get(col)
        if val != "" and pd.notna(val) and (not isinstance(val, (int, float)) or val != 0):
            content_parts.append(f"{str(col).capitalize()}: {val}")
    
    page_content = " | ".join(content_parts)
    chunks = splitter.split_text(page_content)
    
    docs = []
    category = row.get("category", "UNKNOWN")
    for chunk in chunks:
        docs.append(Document(page_content=chunk, metadata={"row": index, "category": category}))
    return docs

def convert_to_documents(df, num_workers=4):
    """Convert each DataFrame row into one or more LangChain ``Document`` objects.

    Uses parallel processing for faster document generation. Documents are split
    into chunks for better embedding performance.
    """
    # Skip search_text column during document conversion
    cols_to_use = [col for col in df.columns if col != 'search_text']
    
    # Prepare arguments for parallel processing
    rows_data = [(idx, row.to_dict(), cols_to_use) for idx, row in df.iterrows()]
    
    docs = []
    with Pool(num_workers) as pool:
        for doc_batch in tqdm(
            pool.imap_unordered(_process_row_for_docs, rows_data, chunksize=32),
            total=len(rows_data),
            desc="📄 Converting documents",
            unit="row"
        ):
            docs.extend(doc_batch)
    
    return docs

def load_compatibility_rules():
    path = resolve_data_path('compatibility.csv')
    if not path.exists():
        return pd.DataFrame()

    rules = pd.read_csv(path, skipinitialspace=True, keep_default_na=True)
    rules.columns = rules.columns.str.strip()

    for column in ['component_1', 'component_2']:
        if column in rules.columns:
            rules[column] = rules[column].astype(str).str.lower().str.strip()

    return rules.fillna("")

# ------------------------------------------------------------
# Vector DB (Chroma) initialization helper
# ------------------------------------------------------------
def initialize_vector_db():
    """Create the Chroma vector store if it does not exist, otherwise load it.

    This function is used by ``main.py`` during startup and can also be called
    directly from scripts (e.g., ``test_cosine.py``) to ensure the DB is ready.
    """
    # Prepare embedding function using the same model/device as the rest of the app
    embeddings = HuggingFaceEmbeddings(
        model_name=Config.EMBEDDING_MODEL,
        model_kwargs={"device": Config.EMBEDDING_DEVICE}
    )

    # Ensure the persistence directory exists
    if not os.path.exists(Config.VECTOR_DB_DIR):
        os.makedirs(Config.VECTOR_DB_DIR, exist_ok=True)

    # If the directory is empty, build the DB from the knowledge base
    if not os.listdir(Config.VECTOR_DB_DIR):
        try:
            print("=== [HỆ THỐNG] Vector DB chưa tồn tại, đang tạo mới... ===\n")
            kb = load_knowledge_base()
            docs = convert_to_documents(kb, num_workers=4)
            
            print(f"\n🔄 Adding {len(docs)} documents to vector store...")
            vector_store = Chroma(persist_directory=Config.VECTOR_DB_DIR, embedding_function=embeddings)
            
            # Add documents in larger batches for faster indexing
            batch_size = 500
            for i in tqdm(range(0, len(docs), batch_size), desc="💾 Indexing documents", unit="batch"):
                batch = docs[i:i + batch_size]
                vector_store.add_documents(batch)

            print("\n=== [HỆ THỐNG] Đã tạo và lưu Vector DB thành công. ===\n")
        except Exception as e:
            print(f"❌ LỖI TẠO VECTOR DB trong data_loader: {e}")
            raise
    else:
        print("=== [HỆ THỐNG] Vector DB đã tồn tại, không tạo lại. ===")
