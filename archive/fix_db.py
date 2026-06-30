from sqlalchemy import create_engine, text

MYSQL_CONNECTION_STRING = "mysql+pymysql://root:@127.0.0.1:3306/chat_history"
engine = create_engine(MYSQL_CONNECTION_STRING)

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE chat_history ADD COLUMN user_uid VARCHAR(255) DEFAULT 'default_uid';"))
        conn.commit()
        print("Success")
    except Exception as e:
        print(f"Error: {e}")