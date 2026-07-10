import asyncio

import pandas as pd

from app.combo_review.review_handler import handle_combo_review
from app.core.chat_handler import handle_chat
from app.core.intent.master_intent import MasterIntentSchema


def test_combo_review_uses_one_shot_handler(monkeypatch):
    knowledge_base = pd.DataFrame([
        {
            'category': 'CPU', 'name': 'AMD Ryzen 7 9800X3D',
            'search_text': 'amd ryzen 7 9800x3d', 'socket': 'AM5', 'price': 10_800_000,
        },
        {
            'category': 'MAINBOARD', 'name': 'MSI B850 PRO',
            'search_text': 'msi b850 pro', 'socket': 'AM5', 'pcie': 'PCIe 4.0', 'price': 5_000_000,
        },
        {
            'category': 'GPU', 'name': 'MSI GeForce RTX 4080',
            'search_text': 'msi geforce rtx 4080', 'interface': 'PCIe 4.0', 'price': 44_400_000,
        },
    ])
    parsed = MasterIntentSchema(
        reasoning='review', intent='combo_review', cpu='AMD Ryzen 7 9800X3D',
        mainboard='MSI B850 PRO', gpu='MSI GeForce RTX 4080',
    )
    monkeypatch.setattr('app.combo_review.review_handler.save_message', lambda *args: None)

    result = handle_combo_review(parsed, 'review this combo', knowledge_base, None, 'user', 'session')
    reply = result['chatbot_reply']

    assert 'Tương thích:' in reply
    assert 'Phù hợp:' in reply
    assert 'combo đang cân bằng tốt' in reply
    assert len([line for line in reply.splitlines() if line.strip()]) == 10


def test_compatibility_does_not_fall_through_to_general_search(monkeypatch):
    parsed = MasterIntentSchema(
        reasoning='compatibility', intent='compatibility', cpu='Intel Core i7-8700K',
        mainboard='ASUS H310M-R R2.0', gpu='MSI GeForce RTX 5070 Ti',
    )

    async def parse_intent(*_args):
        return parsed

    monkeypatch.setattr('app.core.chat_handler.parse_master_intent', parse_intent)
    monkeypatch.setattr('app.core.chat_handler.get_trimmed_history', lambda *_args: [])
    monkeypatch.setattr('app.core.chat_handler.handle_pc_build_flow', lambda **_kwargs: None)
    monkeypatch.setattr('app.core.chat_handler.build_compatibility_context', lambda *_args: 'compatibility context')
    monkeypatch.setattr('app.core.chat_handler.get_compat_check_chain', object)
    monkeypatch.setattr('app.core.chat_handler.format_compatibility_reply', lambda _context: 'compatibility result')
    monkeypatch.setattr(
        'app.core.chat_handler.build_general_search_context',
        lambda *_args: (_ for _ in ()).throw(AssertionError('compatibility fell through')),
    )
    monkeypatch.setattr('app.core.chat_handler.save_message', lambda *_args: None)

    result = asyncio.run(handle_chat('combo có tương thích không?', object(), None, 'user'))

    assert result['chatbot_reply'] == 'compatibility result'
