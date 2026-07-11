import asyncio
import os
import sys

# Đảm bảo đường dẫn đúng
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.intent.master_intent import analyze_intent

async def main():
    q = 'Khe cắm SSD M.2 trên con main Asus B760M-AYW này chạy ở băng thông chuẩn nào'
    res = await analyze_intent(q, 'test_user', 'test_main_asus_b760m')
    print('Category:', res.category)
    print('Target:', res.target_product)
    print('Mainboard:', res.mainboard)
    print('Intent:', res.intent)

if __name__ == "__main__":
    asyncio.run(main())
