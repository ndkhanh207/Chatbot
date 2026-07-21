import re
with open('tests/test_shop_catalog.py', 'r', encoding='utf-8') as f:
    text = f.read()
text = re.sub(r'tier=(\d+)', r'tier=\1', text)
text = text.replace('tier=1', 'tier="1"').replace('tier=99', 'tier="99"')
with open('tests/test_shop_catalog.py', 'w', encoding='utf-8') as f:
    f.write(text)
