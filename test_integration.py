import asyncio
import os
from app.core.chat_handler import handle_chat
from app.catalog import ShopCatalog

async def main():
    catalog = ShopCatalog([], [])
    print("Testing PC Builder Route:")
    result = await handle_chat("build pc choi game", catalog, "user1", "session1")
    print(result)
    
    print("\nTesting Intent Route:")
    result = await handle_chat("rtx 3060 giá bao nhiêu", catalog, "user1", "session1")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
