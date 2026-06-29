import csv
import urllib.request
import os
import re
from PIL import Image
import pillow_avif  # Cần thiết để đọc AVIF
import time

def slugify(text):
    # Lọc bỏ các ký tự đặc biệt để làm tên file hợp lệ
    text = str(text).lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')

def download_and_convert_dataset(input_csv, output_csv, prefix="img"):
    print(f"Đang đọc dữ liệu từ: {input_csv}")
    
    # Tạo thư mục chứa ảnh nếu chưa có
    assets_dir = '../assets/images/mainboard'
    os.makedirs(assets_dir, exist_ok=True)
    
    with open(input_csv, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames
        rows = list(reader)
        
    print(f"Tìm thấy {len(rows)} sản phẩm. Bắt đầu tải và chuyển đổi ảnh...")
    
    with open(output_csv, 'w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        
        count = 0
        success_count = 0
        
        for row in rows:
            count += 1
            product_name = row.get('tên', f'product_{count}')
            url = row.get('image_url', '')
            
            # Tên file an toàn
            safe_name = f"{prefix}_{slugify(product_name)}.png"
            local_path = f"assets/images/{prefix}_{safe_name}"
            full_local_path = os.path.join(assets_dir, safe_name)
            
            print(f"[{count}/{len(rows)}] {product_name}")
            
            # Nếu chưa có URL hoặc đã là link local, bỏ qua tải
            if not url or not url.startswith('http'):
                print("   -> Bỏ qua (Không có link mạng)")
                writer.writerow(row)
                continue
                
            # Nếu file đã tồn tại, bỏ qua để tiết kiệm thời gian (hỗ trợ tải tiếp nếu bị đứt mạng)
            if os.path.exists(full_local_path):
                print("   -> Ảnh đã tồn tại, bỏ qua tải.")
                row['image_url'] = local_path
                writer.writerow(row)
                success_count += 1
                continue
                
            # Tải ảnh
            try:
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://www.buildcores.com/',
                    'Accept': 'image/png, image/jpeg, image/*;q=0.8'
                })
                img_data = urllib.request.urlopen(req, timeout=15).read()
                
                # Lưu tạm file gốc (thường là AVIF)
                temp_path = full_local_path + ".temp"
                with open(temp_path, 'wb') as f:
                    f.write(img_data)
                    
                # Dùng Pillow để đọc (tự nhận diện AVIF) và chuyển sang PNG
                img = Image.open(temp_path)
                img.save(full_local_path, 'PNG')
                
                # Xóa file tạm
                os.remove(temp_path)
                
                # Cập nhật CSV sang link local
                row['image_url'] = local_path
                print("   -> Tải & chuyển đổi thành công!")
                success_count += 1
                
            except Exception as e:
                print(f"   -> Lỗi: {e}")
                # Giữ nguyên url cũ nếu lỗi
                pass
                
            writer.writerow(row)
            
            # Ngủ 0.5s để tránh spam server quá nhanh
            time.sleep(0.5)
            
    print(f"\nHOÀN THÀNH! Đã xử lý thành công {success_count}/{len(rows)} ảnh.")
    print(f"Dữ liệu mới đã được lưu ra file: {output_csv}")
    print(f"Tất cả ảnh đã được lưu vào chuẩn PNG tại: {assets_dir}")

if __name__ == "__main__":
    # BẠN HÃY SỬA TÊN FILE Ở ĐÂY CHO PHÙ HỢP VỚI FILE CỦA BẠN NHÉ
    input_file = 'motherboard_with_images_buildcores_new.csv'
    output_file = 'motherboard_FINAL_READY.csv'
    prefix = "motherboard" # Tiền tố tên ảnh (ví dụ: cpu, gpu, main,...)
    
    if os.path.exists(input_file):
        download_and_convert_dataset(input_file, output_file, prefix)
    else:
        print(f"Không tìm thấy file: {input_file}")
