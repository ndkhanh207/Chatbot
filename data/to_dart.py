import csv
with open('cpu_with_images.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    print('const List<PcComponent> catalogSamples = [')
    for i, row in enumerate(reader):
        if i >= 15: break
        name = row['tên'].replace("'", "\\'")
        price = row['giá'] or "0"
        cores = row['số lõi'] or "0"
        boost = row.get('xung boost', '0') or "0"
        sock = row.get('socket', '')
        url = row.get('image_url', '')
        # Handle 'True'/'False' string in inStock if there is one
        print(f"  PcComponent(id: 'c{i}', name: '{name}', category: 'CPU', manufacturer: 'AMD' if 'AMD' in '{name}' else 'Intel', price: {price}, inStock: True, imageUrl: '{url}', socket: '{sock}', totalCores: {cores}, boostClockGhz: {boost}),")
    print('];')
