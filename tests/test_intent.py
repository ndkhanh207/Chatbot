import asyncio
import sys
import os

# Ensure app is in path
sys.path.insert(0, os.path.abspath("."))

from app.core.intent.master_intent import parse_master_intent, _extract_verified_state

class DummyMsg:
    def __init__(self, t, c): self.type = t; self.content = c

chat_history = [
    DummyMsg('human', 'rx 6600 giá bao nhiêu?'),
    DummyMsg('ai', 'Dạ, Giá của GPU ASRock AMD Radeon RX 6600 Challenger 8GB GDDR6 là 5.279.760 VNĐ.'),
    DummyMsg('human', 'vậy rx 7600 thì sao?'),
]
print('EXTRACTED STATE:', _extract_verified_state(chat_history))

intent = parse_master_intent('vậy rx 7600 thì sao?', chat_history)
print('MASTER INTENT DUMP:', intent.model_dump_json(indent=2))
