import csv
import time
import sys
import urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def process_csv_with_playwright(input_file, output_file):
    print(f"Đang xử lý file: {input_file} ... (CHẾ ĐỘ PLAYWRIGHT: LẤY TRỰC TIẾP TỪ BUILDCORES)")
    
    with open(input_file, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames
        if 'image_url' not in fieldnames:
            fieldnames.append('image_url')
            
        rows = list(reader)
        
    with open(output_file, 'w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        
        with sync_playwright() as p:
            # Bật trình duyệt ẩn
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Vào thẳng trang chủ
            print("Đang mở trang web BuildCores...")
            try:
                page.goto("https://www.buildcores.com/", wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"Lỗi khi tải BuildCores: {e}")
                
            count = 0
            for row in rows:
                product_name = row['tên']
                print(f"[{count+1}] Đang lấy ảnh: {product_name}")
                
                if row.get('image_url') and "http" in row.get('image_url'):
                    writer.writerow(row)
                    continue
                
                try:
                    # Truy cập thẳng vào URL tìm kiếm của BuildCores
                    search_url = f"https://www.buildcores.com/products/Motherboard?search={urllib.parse.quote(product_name)}"
                    page.goto(search_url, wait_until="networkidle", timeout=30000)
                    
                    # Đợi một chút để danh sách sản phẩm load xong (thường load bằng React)
                    time.sleep(2)
                    
                    # Cào thẻ ảnh đầu tiên tìm thấy
                    images = page.locator("img").evaluate_all("imgs => imgs.map(img => img.src)")
                    
                    img_url = ""
                    for img in images:
                        # Ảnh sản phẩm của BuildCores luôn chứa chữ "part-images"
                        if "part-images" in img.lower():
                            # Nếu đây là link bọc qua Next.js, ta giải mã để lấy link gốc
                            if "_next/image" in img:
                                parsed = urllib.parse.urlparse(img)
                                query = urllib.parse.parse_qs(parsed.query)
                                if 'url' in query:
                                    img = query['url'][0]
                                    # Fix trường hợp link gốc bị thiếu https:
                                    if img.startswith("//"):
                                        img = "https:" + img
                            img_url = img
                            break
                    
                    if img_url:
                        print(f"  -> Thành công: {img_url[:60]}...")
                    else:
                        print(f"  -> Không tìm thấy trên BuildCores.")
                        
                    row['image_url'] = img_url
                except Exception as e:
                    print(f"  -> Lỗi: {e}")
                    row['image_url'] = ""
                
                writer.writerow(row)
                count += 1
                
            browser.close()
            
    print(f"\nHoàn thành! Đã lưu file tại: {output_file}")

if __name__ == "__main__":
    # Điền tên file CSV của bạn vào đây
    input_csv = 'motherboard.csv'
    output_csv = 'motherboard_with_images_buildcores_new.csv'
    
    if Path(input_csv).exists():
        process_csv_with_playwright(input_csv, output_csv)
    else:
        print(f"Không tìm thấy file {input_csv}.")
