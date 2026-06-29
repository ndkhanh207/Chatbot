import urllib.request
import os

# Danh sách 15 link ảnh cào được
urls = [
    'https://static.buildcores.com/part-images/6731f670d63afd4f77f62e0a_main',
    'https://static.buildcores.com/part-images/642f6e938f1bfd41942d499f_main',
    'https://static.buildcores.com/part-images/633386ef113be9429703bb13_main',
    'https://static.buildcores.com/part-images/673e9273515e13731358d5ea_main',
    'https://static.buildcores.com/part-images/633386ef113be9429703bb10_main',
    'https://static.buildcores.com/part-images/67bd10ddcbe32482809741ff_main',
    'https://static.buildcores.com/part-images/671f9b7bcc0cc312120443b2_main',
    'https://static.buildcores.com/part-images/65483ef38c237e316b24e855_main',
    'https://static.buildcores.com/part-images/65483ef38c237e316b24e869_main',
    'https://static.buildcores.com/part-images/63cea26339c553ec68f751e0_main',
    'https://static.buildcores.com/part-images/633386ef113be9429703bb0d_main',
    'https://static.buildcores.com/part-images/671f9b7bcc0cc312120443af_main',
    'https://static.buildcores.com/part-images/65483ef38c237e316b24e85d_main',
    'https://static.buildcores.com/part-images/6732e0d0d63afd4f77fd1974_main',
    'https://static.buildcores.com/part-images/671f9b7bcc0cc312120443ac_main',
]

os.makedirs('../assets/images', exist_ok=True)

for i, url in enumerate(urls):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.buildcores.com/',
            # ÉP 서버 trả về JPEG/PNG thay vì AVIF/WebP
            'Accept': 'image/png, image/jpeg, image/*;q=0.8'
        })
        img_data = urllib.request.urlopen(req, timeout=10).read()
        
        with open(f'../assets/images/cpu_{i+1}.png', 'wb') as f:
            f.write(img_data)
        print(f"Downloaded CPU {i+1} - size: {len(img_data)} bytes")
    except Exception as e:
        print(f"Failed to download CPU {i+1}: {e}")
