import os
from pathlib import Path
import pandas as pd
from langchain_core.documents import Document 
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import Config
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Đã đổi sang tiếng Việt theo đúng Header trong file CSV của bạn
DEFAULT_INT_COLS = ['số lõi', 'khe RAM', 'khe M.2', 'bộ nhớ', 'RAM tối đa', 'tdp']
DEFAULT_FLOAT_COLS = ['giá', 'xung cơ bản', 'xung boost', 'chiều dài']

# Bảng giá trị mặc định để chống lỗi Null
DEFAULT_FILL_VALUES = {col: 0.0 for col in DEFAULT_FLOAT_COLS + DEFAULT_INT_COLS}

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
            parts.append(str(val))
        return " ".join(parts)

    knowledge_base['search_text'] = knowledge_base.apply(_make_search_text, axis=1)

    return knowledge_base

# ==============================================================
# BỔ SUNG QUAN TRỌNG: Hàm chuyển DataFrame sang LangChain Document
# ==============================================================
def convert_to_documents(df):
    """Convert each DataFrame row into one or more LangChain ``Document`` objects.

    The original implementation created a single document per row.  For long
    textual rows (e.g., detailed product descriptions) it is beneficial to
    split the content into smaller chunks before embedding.  This function now
    uses :class:`RecursiveCharacterTextSplitter` to break the concatenated
    ``page_content`` into manageable pieces (default 500 characters with a 50
    character overlap).  Each chunk is stored as an individual ``Document``
    while preserving the original row index and category in the metadata.
    """

    # Configure a generic text splitter – can be tuned via parameters if needed
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    docs = []
    for index, row in df.iterrows():
        # Build a single string representation of the row (same as before)
        content_parts = []
        for col in df.columns:
            val = row[col]
            if val != "" and pd.notna(val) and val != 0 and val != 0.0:
                content_parts.append(f"{str(col).capitalize()}: {val}")
        page_content = " | ".join(content_parts)

        # Split the content into chunks; if the text is short, ``split_text``
        # will simply return a list containing the original string.
        chunks = splitter.split_text(page_content)
        for chunk in chunks:
            metadata = {"row": index, "category": row.get("category", "UNKNOWN")}
            docs.append(Document(page_content=chunk, metadata=metadata))

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
            print("=== [HỆ THỐNG] Vector DB chưa tồn tại, đang tạo mới... ===")
            kb = load_knowledge_base()
            docs = convert_to_documents(kb)
            vector_store = Chroma(persist_directory=Config.VECTOR_DB_DIR, embedding_function=embeddings)
            vector_store.add_documents(docs)

            print("=== [HỆ THỐNG] Đã tạo và lưu Vector DB thành công. ===")
        except Exception as e:
            print(f"❌ LỖI TẠO VECTOR DB trong data_loader: {e}")
            raise
    else:
        print("=== [HỆ THỐNG] Vector DB đã tồn tại, không tạo lại. ===")