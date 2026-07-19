"""
generate_compat_training_data.py

Uses the actual catalog + compat_logic ground-truth functions to produce
fine-tuning examples in Alpaca JSONL format.

Each example:
  - instruction: system prompt (what the model should know)
  - input:       user question with real product names
  - output:      the ideal assistant response derived from logic verdicts

Run from project root:
    python scripts/generate_compat_training_data.py

Output: data/training/compat_training_data.jsonl
"""

import json
import itertools
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.catalog import ShopCatalog, ProductQuery
from app.compatibility.compat_logic import (
    check_cpu_main_compat,
    check_gpu_main_compat,
    check_cpu_gpu_compat,
)
from app.utils.format import format_currency_vietnam, get_field

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
DATA_DIR   = "data/dataset"
OUTPUT = os.path.join(os.path.dirname(__file__), "compat_training_data.jsonl")
MAX_PAIRS  = 80   # cap per pairing type to avoid bloat

SYSTEM_PROMPT = """\
Bạn là chuyên gia tư vấn build PC chuyên nghiệp. Khách hàng hỏi về độ tương thích linh kiện.
Hệ thống cung cấp thông số kỹ thuật thực tế từ kho hàng. Dựa vào thông số đó, trả lời ngắn gọn,
chính xác, tự nhiên. Bắt đầu bằng "Dạ, "."""

QUESTION_TEMPLATES = {
    "cpu_main": [
        "{cpu} lắp được với {main} không?",
        "{cpu} có tương thích với main {main} không ạ?",
        "Main {main} có dùng được với CPU {cpu} không?",
        "Cho em hỏi {cpu} với {main} có phù hợp không?",
    ],
    "gpu_main": [
        "Card {gpu} lắp được với main {main} không?",
        "GPU {gpu} cắm vào {main} có ổn không ạ?",
        "{gpu} có chạy được trên main {main} không?",
    ],
    "cpu_gpu": [
        "{cpu} đi với {gpu} có bị nghẽn cổ chai không?",
        "{gpu} ghép với {cpu} có ổn không?",
        "{cpu} với {gpu} cân nhau không ạ?",
    ],
    "combo": [
        "{cpu} + {main} + {gpu} có tương thích với nhau không?",
        "Combo {cpu} - {main} - {gpu} có ổn không ạ?",
        "Em muốn build với {cpu}, {main}, {gpu} — có ổn không?",
    ],
}


def fmt_price(p) -> str:
    try:
        return f"{format_currency_vietnam(p)} VNĐ" if p else "Liên hệ"
    except Exception:
        return str(p)


def cpu_context(cpu: dict) -> str:
    name  = get_field(cpu, "tên", "name", default="?")
    sock  = cpu.get("socket", "?")
    tdp   = cpu.get("tdp", "?")
    price = fmt_price(get_field(cpu, "giá", "price", default=None))
    return f"- CPU: '{name}' (Socket: {sock}, TDP: {tdp}W) | Giá: {price}"


def main_context(main: dict) -> str:
    name  = get_field(main, "tên", "name", default="?")
    sock  = main.get("socket", "?")
    pcie  = main.get("pcie", "?")
    price = fmt_price(get_field(main, "giá", "price", default=None))
    return f"- Mainboard: '{name}' (Socket: {sock}, PCIe: {pcie}) | Giá: {price}"


def gpu_context(gpu: dict) -> str:
    name  = get_field(gpu, "tên", "name", default="?")
    iface = gpu.get("interface", "?")
    vram  = get_field(gpu, "bộ nhớ", "vram", default="?")
    price = fmt_price(get_field(gpu, "giá", "price", default=None))
    return f"- GPU: '{name}' (PCIe: {iface}, VRAM: {vram}) | Giá: {price}"


def build_cpu_main_answer(cpu: dict, main: dict) -> str:
    check   = check_cpu_main_compat(cpu, main)
    cpu_name  = get_field(cpu, "tên", "name", default="?")
    main_name = get_field(main, "tên", "name", default="?")

    if check["is_compatible"]:
        reason = check["reasons"][0] if check["reasons"] else ""
        return (
            f"Dạ, {cpu_name} và {main_name} hoàn toàn tương thích với nhau ạ. "
            f"Cả hai đều dùng {cpu.get('socket','?')}, mainboard đủ khả năng cấp điện cho CPU."
        )
    else:
        detail = check["reasons"][0] if check["reasons"] else "không phù hợp"
        return f"Dạ, {cpu_name} và {main_name} KHÔNG tương thích. {detail}"


def build_gpu_main_answer(gpu: dict, main: dict) -> str:
    check    = check_gpu_main_compat(gpu, main)
    gpu_name = get_field(gpu, "tên", "name", default="?")
    main_name = get_field(main, "tên", "name", default="?")

    if check.get("warning"):
        return (
            f"Dạ, {gpu_name} và {main_name} tương thích với nhau, card vẫn chạy được. "
            f"Tuy nhiên cần lưu ý: {check['warning']}"
        )
    return (
        f"Dạ, {gpu_name} lắp vào {main_name} hoàn toàn ổn ạ. "
        f"Cả hai cùng hỗ trợ PCIe nên không bị hạn chế băng thông."
    )


def build_cpu_gpu_answer(cpu: dict, gpu: dict) -> str:
    check    = check_cpu_gpu_compat(cpu, gpu)
    cpu_name = get_field(cpu, "tên", "name", default="?")
    gpu_name = get_field(gpu, "tên", "name", default="?")

    if check.get("warning"):
        return (
            f"Dạ, {cpu_name} và {gpu_name} cắm vào nhau được, nhưng cần cảnh báo: {check['warning']} "
            f"Bạn có thể cân nhắc nâng cấp để tận dụng tối đa hiệu suất."
        )
    return (
        f"Dạ, {cpu_name} kết hợp với {gpu_name} rất ổn ạ. "
        f"Hai linh kiện cân bằng về hiệu năng, không xảy ra nghẽn cổ chai đáng kể."
    )


def build_combo_answer(cpu: dict, main: dict, gpu: dict) -> str:
    cm = check_cpu_main_compat(cpu, main)
    gm = check_gpu_main_compat(gpu, main)
    cg = check_cpu_gpu_compat(cpu, gpu)

    cpu_name  = get_field(cpu,  "tên", "name", default="?")
    main_name = get_field(main, "tên", "name", default="?")
    gpu_name  = get_field(gpu,  "tên", "name", default="?")

    overall_ok = cm["is_compatible"] and gm["is_compatible"]
    verdict    = "tương thích với nhau" if overall_ok else "KHÔNG tương thích hoàn toàn"

    parts = [f"Dạ, combo {cpu_name} + {main_name} + {gpu_name} {verdict} ạ."]

    if not cm["is_compatible"]:
        parts.append(f"CPU và Mainboard: {cm['reasons'][0]}")
    else:
        parts.append(f"CPU + Mainboard: Tương thích (cùng socket {cpu.get('socket','?')}).")

    if gm.get("warning"):
        parts.append(f"GPU + Mainboard: Tương thích nhưng cảnh báo băng thông PCIe.")
    else:
        parts.append("GPU + Mainboard: Tương thích tốt.")

    if cg.get("warning"):
        parts.append(f"CPU + GPU: {cg['warning']}")
    else:
        parts.append("CPU + GPU: Cân bằng, không nghẽn cổ chai.")

    return " ".join(parts)


def make_record(question: str, context_block: str, answer: str) -> dict:
    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": f"Khách hỏi: {question}\n\nDỮ LIỆU TỪ HỆ THỐNG:\n{context_block}"},
            {"role": "assistant", "content": answer},
        ]
    }


def main():
    print("Loading catalog...")
    catalog = ShopCatalog.load(DATA_DIR)

    cpus  = [p.as_legacy_dict() for p in catalog.search_products(ProductQuery(text="", category="CPU",       limit=500))]
    mains = [p.as_legacy_dict() for p in catalog.search_products(ProductQuery(text="", category="MAINBOARD", limit=500))]
    gpus  = [p.as_legacy_dict() for p in catalog.search_products(ProductQuery(text="", category="GPU",       limit=500))]

    print(f"Loaded: {len(cpus)} CPUs, {len(mains)} mainboards, {len(gpus)} GPUs")

    records = []

    # ── CPU × Mainboard ────────────────────────────────────────────────────────
    pairs = list(itertools.product(cpus, mains))
    random.shuffle(pairs)
    for cpu, main in pairs[:MAX_PAIRS]:
        q_tmpl = random.choice(QUESTION_TEMPLATES["cpu_main"])
        q      = q_tmpl.format(cpu=get_field(cpu,"tên","name",default="?"), main=get_field(main,"tên","name",default="?"))
        ctx    = cpu_context(cpu) + "\n" + main_context(main)
        ans    = build_cpu_main_answer(cpu, main)
        records.append(make_record(q, ctx, ans))

    # ── GPU × Mainboard ────────────────────────────────────────────────────────
    pairs = list(itertools.product(gpus, mains))
    random.shuffle(pairs)
    for gpu, main in pairs[:MAX_PAIRS]:
        q_tmpl = random.choice(QUESTION_TEMPLATES["gpu_main"])
        q      = q_tmpl.format(gpu=get_field(gpu,"tên","name",default="?"), main=get_field(main,"tên","name",default="?"))
        ctx    = gpu_context(gpu) + "\n" + main_context(main)
        ans    = build_gpu_main_answer(gpu, main)
        records.append(make_record(q, ctx, ans))

    # ── CPU × GPU ──────────────────────────────────────────────────────────────
    pairs = list(itertools.product(cpus, gpus))
    random.shuffle(pairs)
    for cpu, gpu in pairs[:MAX_PAIRS]:
        q_tmpl = random.choice(QUESTION_TEMPLATES["cpu_gpu"])
        q      = q_tmpl.format(cpu=get_field(cpu,"tên","name",default="?"), gpu=get_field(gpu,"tên","name",default="?"))
        ctx    = cpu_context(cpu) + "\n" + gpu_context(gpu)
        ans    = build_cpu_gpu_answer(cpu, gpu)
        records.append(make_record(q, ctx, ans))

    # ── Full Combo ─────────────────────────────────────────────────────────────
    combos = list(itertools.product(cpus, mains, gpus))
    random.shuffle(combos)
    for cpu, main, gpu in combos[:MAX_PAIRS]:
        q_tmpl = random.choice(QUESTION_TEMPLATES["combo"])
        q = q_tmpl.format(
            cpu=get_field(cpu,"tên","name",default="?"),
            main=get_field(main,"tên","name",default="?"),
            gpu=get_field(gpu,"tên","name",default="?"),
        )
        ctx = cpu_context(cpu) + "\n" + main_context(main) + "\n" + gpu_context(gpu)
        ans = build_combo_answer(cpu, main, gpu)
        records.append(make_record(q, ctx, ans))

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n✅ Generated {len(records)} training examples → {OUTPUT}")
    print(f"   CPU×Main: {MAX_PAIRS}, GPU×Main: {MAX_PAIRS}, CPU×GPU: {MAX_PAIRS}, Combo: {MAX_PAIRS}")


if __name__ == "__main__":
    random.seed(42)
    main()
