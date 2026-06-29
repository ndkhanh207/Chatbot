import csv
import glob
import os

def clean_price(price_str):
    try:
        # Nếu có dấu phẩy hoặc chấm, bỏ đi (nếu format là 10,000,000)
        p = price_str.replace(',', '').replace('.', '')
        if not p: return 0
        return float(p)
    except:
        return 0

def clean_float(val):
    try:
        return float(val)
    except:
        return 0.0

def clean_int(val):
    try:
        return int(float(val))
    except:
        return 0

def generate():
    dart_code = []
    dart_code.append("import '../../models/component.dart';\n")
    dart_code.append("// TỆP NÀY ĐƯỢC TẠO TỰ ĐỘNG TỪ PYTHON\n")
    dart_code.append("const List<PcComponent> generatedCatalog = [")
    
    # --- CPU ---
    if os.path.exists('cpu_FINAL_READY.csv'):
        with open('cpu_FINAL_READY.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                name = row.get('tên', '').replace("'", "\\'")
                price = clean_price(row.get('giá', '0'))
                cores = clean_int(row.get('số lõi', '0'))
                boost = clean_float(row.get('xung boost', '0'))
                socket = row.get('socket', '').replace("'", "\\'")
                image = row.get('image_url', '').replace("'", "\\'")
                
                manufacturer = 'AMD' if 'AMD' in name else 'Intel'
                
                dart_code.append(f"  PcComponent(id: 'cpu_{i}', name: '{name}', category: 'CPU', manufacturer: '{manufacturer}', price: {price}, inStock: true, imageUrl: '{image}', socket: '{socket}', totalCores: {cores}, boostClockGhz: {boost}),")
                
    # --- GPU ---
    if os.path.exists('gpu_FINAL_READY.csv'):
        with open('gpu_FINAL_READY.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                name = row.get('tên', '').replace("'", "\\'")
                price = clean_price(row.get('giá', '0'))
                vram = row.get('bộ nhớ', '0')
                boost = clean_float(row.get('xung boost', '0')) / 1000.0  # Convert MHz to GHz
                tdp = clean_int(row.get('tdp', '0'))
                image = row.get('image_url', '').replace("'", "\\'")
                
                # Cố gắng tìm manufacturer từ tên
                manu = 'Unknown'
                if 'MSI' in name.upper(): manu = 'MSI'
                elif 'ASUS' in name.upper(): manu = 'ASUS'
                elif 'GIGABYTE' in name.upper(): manu = 'Gigabyte'
                elif 'ASROCK' in name.upper(): manu = 'ASRock'
                elif 'SAPPHIRE' in name.upper(): manu = 'Sapphire'
                elif 'ZOTAC' in name.upper(): manu = 'Zotac'
                elif 'EVGA' in name.upper(): manu = 'EVGA'
                
                dart_code.append(f"  PcComponent(id: 'gpu_{i}', name: '{name}', category: 'GPU', manufacturer: '{manu}', price: {price}, inStock: true, imageUrl: '{image}', boostClockGhz: {boost}, tdpWatt: {tdp}, vramLabel: '{vram} GB'),")
                
    # --- MOTHERBOARD ---
    if os.path.exists('motherboard_FINAL_READY.csv'):
        with open('motherboard_FINAL_READY.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                name = row.get('tên', '').replace("'", "\\'")
                price = clean_price(row.get('giá', '0'))
                socket = row.get('socket', '').replace("'", "\\'")
                form = row.get('kích thước', '').replace("'", "\\'")
                image = row.get('image_url', '').replace("'", "\\'")
                
                manu = 'Unknown'
                if 'MSI' in name.upper(): manu = 'MSI'
                elif 'ASUS' in name.upper(): manu = 'ASUS'
                elif 'GIGABYTE' in name.upper(): manu = 'Gigabyte'
                elif 'ASROCK' in name.upper(): manu = 'ASRock'
                
                dart_code.append(f"  PcComponent(id: 'mb_{i}', name: '{name}', category: 'MAINBOARD', manufacturer: '{manu}', price: {price}, inStock: true, imageUrl: '{image}', socket: '{socket}', formFactor: '{form}'),")

    dart_code.append("];\n")
    
    with open('../lib/widgets/component_catalog/catalog_data_generated.dart', 'w', encoding='utf-8') as out:
        out.write('\n'.join(dart_code))
        
    print("Đã tạo file catalog_data_generated.dart thành công!")

if __name__ == '__main__':
    generate()
