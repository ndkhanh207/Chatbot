import json
import os
import random
import sys
import pandas as pd

random.seed(3407)

# Thêm đường dẫn để import được templates từ app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from app.templates.prompt_templates import (
    BASIC_SEARCH_TEMPLATE,
    COMPAT_CHECK_TEMPLATE,
    PC_BUILD_TEMPLATE,
    SUGGESTION_TEMPLATE,
)
from app.core.intent.prompts import _SYSTEM_CLASSIFY, _SYSTEM_EXTRACT

# --- 1. DỮ LIỆU TỪ CSV ---
def load_csv(path):
    if os.path.exists(path):
        df = pd.read_csv(path).fillna("Không có")
        return df.to_dict('records')
    return []

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dataset"))
CPUS = load_csv(os.path.join(base_dir, "cpu.csv"))
GPUS = load_csv(os.path.join(base_dir, "gpu.csv"))
MAINS = load_csv(os.path.join(base_dir, "motherboard.csv"))
PC_BUILDS = load_csv(os.path.join(base_dir, "Pc_build_data.csv"))

if not all((CPUS, GPUS, MAINS, PC_BUILDS)):
    raise RuntimeError("Thiếu CSV CPU, GPU, motherboard hoặc Pc_build_data")

CPU_BY_NAME = {row["tên"]: row for row in CPUS}
GPU_BY_NAME = {row["tên"]: row for row in GPUS}
MAIN_BY_NAME = {row["tên"]: row for row in MAINS}

BUDGETS = [
    ("10 triệu", 10_000_000), ("15 củ", 15_000_000),
    ("20 triệu", 20_000_000), ("tầm 25m", 25_000_000),
    ("khoảng 30 củ", 30_000_000), ("dưới 40 củ", 40_000_000),
    ("50tr", 50_000_000), ("12tr", 12_000_000), ("tầm 8 củ", 8_000_000),
]
def extract_price(value):
    try:
        if isinstance(value, dict):
            value = value.get("giá", 0)
        return float(str(value).replace(',', '').replace('.', ''))
    except (TypeError, ValueError):
        return 0.0


def is_compatible(cpu, main):
    cpu_socket = str(cpu.get("socket", "")).strip()
    main_socket = str(main.get("socket", "")).strip()
    return bool(cpu_socket and cpu_socket != "Không có" and cpu_socket == main_socket)


VALID_PC_BUILDS = [
    (build, CPU_BY_NAME.get(build["CPU_Model"]), GPU_BY_NAME.get(build["GPU_Model"]), MAIN_BY_NAME.get(build["Motherboard_Model"]))
    for build in PC_BUILDS
]
VALID_PC_BUILDS = [row for row in VALID_PC_BUILDS if all(row[1:]) and is_compatible(row[1], row[3])]

compatible_pair_names = {
    (cpu["tên"], main["tên"])
    for _, cpu, _, main in VALID_PC_BUILDS
}
COMPATIBLE_PAIRS = [(CPU_BY_NAME[cpu], MAIN_BY_NAME[main]) for cpu, main in sorted(compatible_pair_names)]
INCOMPATIBLE_PAIRS = [(cpu, main) for cpu in CPUS for main in MAINS if not is_compatible(cpu, main)]

if not COMPATIBLE_PAIRS or not INCOMPATIBLE_PAIRS or not VALID_PC_BUILDS:
    raise RuntimeError("Không có đủ cặp tương thích hoặc bộ PC hợp lệ")


def choose_build_components(budget):
    candidates = [row for row in VALID_PC_BUILDS if extract_price(row[0].get("Total_Price")) <= budget]
    if not candidates:
        return None
    preferred = [row for row in candidates if extract_price(row[0].get("Total_Price")) >= budget * 0.7]
    build, cpu, gpu, main = random.choice(preferred or candidates)
    return (cpu, gpu, main), extract_price(build.get("Total_Price")), extract_price(build.get("Assembly_Fee"))


def compatibility_context(cpu, main):
    compatible = is_compatible(cpu, main)
    cpu_socket = cpu.get("socket", "không rõ")
    main_socket = main.get("socket", "không rõ")
    conclusion = "TƯƠNG THÍCH (PHÙ HỢP)" if compatible else "KHÔNG TƯƠNG THÍCH (KHÔNG PHÙ HỢP)"
    detail = f"Cùng socket {cpu_socket}" if compatible else f"Khác chuẩn socket ({cpu_socket} so với {main_socket})"
    return (
        f"- CPU: '{cpu['tên']}' | Socket: {cpu_socket}\n"
        f"- Mainboard: '{main['tên']}' | Socket: {main_socket}\n"
        f"- KẾT LUẬN TƯƠNG THÍCH: {conclusion}\n"
        f"- CHI TIẾT: {detail}"
    )


def compatibility_answer(cpu, main):
    if is_compatible(cpu, main):
        return random.choice(COMPAT_ANSWERS).format(cpu=cpu["tên"], main=main["tên"], socket=cpu.get("socket"))
    return random.choice(COMPAT_ANSWERS_NOT).format(
        cpu=cpu["tên"], main=main["tên"], cpu_socket=cpu.get("socket"), main_socket=main.get("socket")
    )

# Syntactic Variety Arrays
BUILD_PHRASES = [
    "build pc {price}", "lắp ráp máy {price}", "tư vấn dàn máy {price}",
    "cần một cấu hình {price}", "lên cho mình dàn pc {price}",
    "có cấu hình nào {price} không", "mình cần ráp máy khoảng {price}"
]
BUILD_WITHOUT_BUDGET_PHRASES = [
    "tư vấn pc", "build pc", "ráp máy", "tư vấn PC chơi game", "build máy làm đồ họa",
    "ráp máy văn phòng", "lên cấu hình học tập", "tư vấn dàn máy render", "mình muốn mua bộ PC",
    "giúp mình chọn cấu hình máy",
]
BUILD_WITHOUT_BUDGET_ANSWERS = [
    "Dạ, bạn dự định đầu tư khoảng bao nhiêu cho bộ PC ạ?",
    "Dạ, bạn cho em xin mức ngân sách dự kiến để em chọn cấu hình phù hợp nhé.",
    "Dạ, để tư vấn đúng cấu hình, em cần biết khoảng ngân sách của bạn ạ.",
]
COMPAT_PHRASES = [
    "{cpu} lắp với {main} được không?",
    "{cpu} cắm vô main {main} có bị lỗi không", "main {main} cân được con {cpu} không shop",
    "cho hỏi {cpu} và {main} có gắn được không", "{main} có đi chung với {cpu} được ko"
]
GENERAL_QUERY_TEMPLATES = {
    "CPU": ["tư vấn CPU {brand}", "shop có CPU {brand} nào không", "mình cần tìm CPU {brand}"],
    "VGA": ["tìm card đồ họa {brand}", "tư vấn VGA {brand}", "shop có GPU {brand} nào không"],
    "Mainboard": ["tìm mainboard {brand}", "shop có bo mạch chủ {brand} nào không", "tư vấn main {brand}"],
}
PRICE_CHECK_PHRASES = [
    "giá {comp} là bao nhiêu", "{comp} nhiêu tiền", "hỏi giá {comp}",
    "cho xin giá con {comp}", "{comp} rổ giá sao shop", "báo giá mình {comp}"
]
SPEC_QUERY_TEMPLATES = [
    "{spec} của {comp} là bao nhiêu?",
    "cho mình hỏi {comp} có {spec} thế nào?",
    "thông số {spec} trên {comp} là gì?",
]

IMPOSSIBLE_BUDGETS = ["1 triệu", "2 triệu", "500k", "1tr5", "800 cành", "2 củ"]

# --- VARIETY ANSWER TEMPLATES ---
PRICE_ANSWERS = [
    "Dạ, sản phẩm {name} hiện đang có mức giá là {price} VNĐ ạ.",
    "Dạ, giá của {name} là {price} VNĐ ạ.",
    "Dạ, sản phẩm {name} hiện có giá {price} VNĐ.",
    "Dạ, {name} đang được bán với giá {price} VNĐ ạ."
]
PRICE_ANSWERS_NOT_FOUND = [
    "Dạ, hiện tại em chưa tìm thấy thông tin giá của sản phẩm này trong kho ạ.",
    "Dạ, em không tìm thấy thông tin giá cho sản phẩm bạn vừa nêu. Bạn có thể kiểm tra lại tên giúp em được không ạ?",
    "Dạ, hiện tại cửa hàng chưa có thông tin giá cả cụ thể cho sản phẩm này ạ."
]

GENERAL_ANSWERS = [
    "Dạ, với nhu cầu tìm {comp} của bạn, cửa hàng đang có các sản phẩm tiêu biểu như:\n{list}",
    "Dạ, cửa hàng hiện có một số sản phẩm {comp} như:\n{list}",
    "Dạ, đây là danh sách một vài sản phẩm {comp} hiện có:\n{list}"
]
GENERAL_ANSWERS_NOT_FOUND = [
    "Dạ, hiện tại em chưa tìm thấy mã sản phẩm này trong kho ạ.",
    "Dạ, sản phẩm bạn tìm hiện chưa có thông tin trong cơ sở dữ liệu ạ.",
    "Dạ, rất tiếc em không tìm thấy sản phẩm nào khớp với yêu cầu của bạn."
]

SPEC_ANSWERS = [
    "Dạ, {name} có {spec_name} là {spec_val}.",
    "Dạ, thông số {spec_name} của {name} là {spec_val} ạ.",
    "Dạ, {spec_name} của {name} là {spec_val} ạ."
]
SPEC_ANSWERS_NOT_FOUND = [
    "Dạ, hiện chưa có thông tin về {spec_name} của {name} ạ.",
    "Dạ, em chưa tra được {spec_name} của {name} ạ.",
    "Dạ, {name} hiện chưa có thông số {spec_name} ạ."
]

COMPAT_ANSWERS = [
    "Dạ, {cpu} lắp được với {main}. Lý do: Cùng sử dụng socket {socket}.",
    "Dạ, {cpu} có thể lắp được với {main} ạ. Lý do: Cả hai đều hỗ trợ socket {socket}.",
    "Dạ, {cpu} và {main} tương thích về socket. Lý do: Cùng chuẩn socket {socket}."
]
COMPAT_ANSWERS_NOT = [
    "Dạ, hai linh kiện này không tương thích với nhau. Lý do: CPU {cpu} dùng socket {cpu_socket} trong khi Mainboard {main} lại dùng socket {main_socket} ạ.",
    "Dạ, {cpu} và {main} không lắp được với nhau. Lý do: Khác chuẩn socket ({cpu_socket} so với {main_socket}).",
    "Dạ không tương thích ạ. Lý do: Mainboard {main} yêu cầu socket {main_socket}, nhưng CPU {cpu} lại là {cpu_socket}."
]

# --- 3. HÀM TẠO DATA ---
dataset = []

def lc_to_dict(lc_msgs, ans):
    out = []
    sys_content = ""
    for m in lc_msgs:
        if m.type == "system":
            sys_content += m.content + "\n"
    
    if sys_content:
        out.append({"role": "system", "content": sys_content.strip()})
        
    for m in lc_msgs:
        if m.type == "human":
            out.append({"role": "user", "content": m.content})
            
    out.append({"role": "assistant", "content": ans})
    return {"messages": out}

def lc_to_dict_multi(lc_msgs, ans1, user_q2, ans2, system_context2=""):
    base = lc_to_dict(lc_msgs, ans1)
    if system_context2:
        base["messages"].append({"role": "system", "content": system_context2})
    base["messages"].append({"role": "user", "content": f"<user_input>{user_q2}</user_input>"})
    base["messages"].append({"role": "assistant", "content": ans2})
    return base


def lc_to_dict_three_turns(lc_msgs, ans1, system_context2, user_q2, ans2, user_q3, ans3):
    base = lc_to_dict_multi(lc_msgs, ans1, user_q2, ans2, system_context2)
    base["messages"].append({"role": "user", "content": f"<user_input>{user_q3}</user_input>"})
    base["messages"].append({"role": "assistant", "content": ans3})
    return base


def extraction_result(intent, reasoning, **values):
    result = {
        "reasoning": reasoning,
        "intent": intent,
        "target_product": "none",
        "spec_detail": "none",
        "cpu": "none",
        "mainboard": "none",
        "gpu": "none",
        "budget_amount": 0,
        "category": "none",
    }
    result.update(values)
    return result


def make_intent_case(intent, index):
    cpu = random.choice(CPUS)["tên"]
    gpu = random.choice(GPUS)["tên"]
    main = random.choice(MAINS)["tên"]
    follow_up = index % 4 == 0
    history = ""

    if intent == "compatibility":
        question = random.choice([
            f"{cpu} lắp với {main} được không?",
            f"main {main} có đi cùng CPU {cpu} không shop?",
            f"kiểm tra giúp mình {cpu} và {main} có tương thích không",
        ])
        if follow_up:
            old_main = random.choice(MAINS)["tên"]
            history = f"[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU={cpu}, MAINBOARD={old_main}, LAST_INTENT=compatibility\n\n"
            question = f"thế còn main {main} thì sao?"
        result = extraction_result(intent, "Kiểm tra tương thích CPU và mainboard.", cpu=cpu.lower(), mainboard=main.lower())
    elif intent == "suggestion":
        wanted = "gpu" if index % 2 else "mainboard"
        question = random.choice([
            f"mình có {cpu}, tìm {wanted} phù hợp giúp mình",
            f"đã có CPU {cpu} rồi, tư vấn {wanted} để ghép cùng",
            f"chọn giúp mình một {wanted} đi với {cpu}",
        ])
        if follow_up:
            history = f"[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU={cpu}, LAST_INTENT=suggestion\n\n"
            question = f"giờ tìm {wanted} cho nó nhé"
        result = extraction_result(intent, "Tìm linh kiện mới để ghép với CPU đã có.", cpu=cpu.lower(), category=wanted)
    elif intent == "price_calculation":
        calculation_type = index % 3
        if calculation_type == 0:
            question = f"tổng giá {cpu} với {main} là bao nhiêu?"
            values = {"cpu": cpu.lower(), "mainboard": main.lower()}
        elif calculation_type == 1:
            question = f"cộng tiền CPU {cpu} và GPU {gpu} giúp mình"
            values = {"cpu": cpu.lower(), "gpu": gpu.lower()}
        else:
            question = f"mua {cpu}, {main} và {gpu} thì tổng bao nhiêu tiền?"
            values = {"cpu": cpu.lower(), "mainboard": main.lower(), "gpu": gpu.lower()}
        result = extraction_result(intent, "Tính tổng giá nhiều linh kiện.", **values)
    elif intent == "specification":
        component_type, component, spec = random.choice([
            ("cpu", cpu, random.choice(["số lõi", "xung boost", "socket", "tdp"])),
            ("gpu", gpu, random.choice(["bộ nhớ", "xung boost", "chiều dài", "tdp"])),
            ("mainboard", main, random.choice(["socket", "kích thước", "ram tối đa", "pcie"])),
        ])
        question = random.choice([
            f"{spec} của {component} là bao nhiêu?",
            f"cho mình hỏi {component} có {spec} thế nào",
            f"thông số {spec} trên {component} là gì?",
        ])
        if follow_up:
            history = f"[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nTARGET_PRODUCT={component}, {component_type.upper()}={component}, LAST_INTENT=specification\n\n"
            question = f"thế {spec} của nó thì sao?"
        result = extraction_result(
            intent,
            "Hỏi thông số của một linh kiện.",
            target_product=component.lower(),
            spec_detail=spec,
            category=component_type,
            **{component_type: component.lower()},
        )
    elif intent == "price_check":
        component_type, component = random.choice([("cpu", cpu), ("gpu", gpu), ("mainboard", main)])
        question = random.choice([
            f"giá {component} là bao nhiêu?",
            f"{component} nhiêu tiền vậy shop",
            f"báo giá giúp mình {component}",
        ])
        if follow_up:
            old_component = random.choice({"cpu": CPUS, "gpu": GPUS, "mainboard": MAINS}[component_type])["tên"]
            history = f"[TRẠNG THÁI ĐÃ XÁC NHẬN]:\n{component_type.upper()}={old_component}, LAST_INTENT=price_check\n\n"
            question = f"thế còn {component} thì sao?"
        result = extraction_result(
            intent,
            "Hỏi giá một linh kiện cụ thể.",
            target_product=component.lower(),
            category=component_type,
            **{component_type: component.lower()},
        )
    elif intent == "budget_search":
        category, category_word = random.choice([("cpu", "CPU"), ("gpu", "GPU"), ("mainboard", "mainboard")])
        _, budget = random.choice(BUDGETS)
        question = random.choice([
            f"tìm {category_word} dưới {budget // 1_000_000} triệu",
            f"có {category_word} nào tầm {budget // 1_000_000}tr không?",
            f"tư vấn {category_word} không vượt quá {budget // 1_000_000} triệu",
        ])
        if follow_up:
            history = f"[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCATEGORY={category}, LAST_INTENT=general_search\n\n"
            question = f"tầm {budget // 1_000_000} triệu có mẫu nào?"
        result = extraction_result(intent, "Tìm một linh kiện theo ngân sách.", budget_amount=budget, category=category)
    elif intent == "combo_review":
        _, build_cpu, build_gpu, build_main = random.choice(VALID_PC_BUILDS)
        cpu, gpu, main = build_cpu["tên"], build_gpu["tên"], build_main["tên"]
        question = random.choice([
            f"đánh giá combo {cpu} + {main} + {gpu}",
            f"bộ {cpu}, {main}, {gpu} có đáng mua không?",
            f"review hiệu năng dàn {cpu} / {main} / {gpu} giúp mình",
        ])
        if follow_up:
            history = f"[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCPU={cpu}, MAINBOARD={main}, GPU={gpu}, LAST_INTENT=compatibility\n\n"
            question = "đánh giá tổng thể bộ này giúp mình"
        result = extraction_result(intent, "Đánh giá bộ ba linh kiện có sẵn.", cpu=cpu.lower(), mainboard=main.lower(), gpu=gpu.lower())
    elif intent == "build_pc":
        _, budget = random.choice(BUDGETS)
        question = random.choice([
            f"build cho mình bộ PC khoảng {budget // 1_000_000} triệu",
            f"lên cấu hình máy tầm {budget // 1_000_000}tr",
            f"tư vấn một dàn PC ngân sách {budget // 1_000_000} triệu",
            f"ráp giúp mình bộ máy khoảng {budget // 1_000_000} triệu",
            f"mình cần một cấu hình PC giá {budget // 1_000_000}tr",
        ])
        if follow_up:
            history = "LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ:\nKhách: tư vấn bộ pc\nAI: Bạn dự định đầu tư khoảng bao nhiêu?\n\n"
            question = random.choice([
                f"{budget // 1_000_000} triệu",
                f"khoảng {budget // 1_000_000}tr",
                f"ngân sách của mình là {budget // 1_000_000} triệu",
            ])
        result = extraction_result(intent, "Tư vấn một bộ PC mới.", budget_amount=budget)
    elif intent == "general_search":
        category, category_word, pool = random.choice([
            ("cpu", "CPU", CPUS), ("gpu", "GPU", GPUS), ("mainboard", "mainboard", MAINS),
        ])
        brand = str(random.choice(pool)["tên"]).split()[0]
        question = random.choice([
            f"tìm giúp mình {category_word} hãng {brand}",
            f"shop có {category_word} {brand} nào không?",
            f"cho xem các mẫu {category_word} của {brand}",
        ])
        if follow_up:
            history = f"[TRẠNG THÁI ĐÃ XÁC NHẬN]:\nCATEGORY={category}, LAST_INTENT=general_search\n\n"
            question = f"thế còn của hãng {brand} thì sao?"
        result = extraction_result(intent, "Tìm sản phẩm chung theo loại hoặc hãng.", target_product=brand.lower(), category=category)
    else:
        question = random.choice([
            "chào shop", "cảm ơn nhé", "ok mình hiểu rồi", "shop còn online không?",
            "ừ để mình xem thêm", "mình chưa biết chọn gì", "xin chào", "được rồi ạ",
        ]) + random.choice(["", "!", " shop", " nhé", " ạ"])
        result = extraction_result("none", "Giao tiếp thông thường, không có yêu cầu linh kiện.")

    return history, question, result

# 3.1 PC Build (1000 rows)
for i in range(1000):
    is_negative = (i % 10 == 0) # 10% negative
    price_str, budget = random.choice(BUDGETS)
    
    if is_negative:
        case_id = i // 10
        user_q = BUILD_WITHOUT_BUDGET_PHRASES[case_id % len(BUILD_WITHOUT_BUDGET_PHRASES)]
        build_context = "KHÔNG CÓ DỮ LIỆU DO KHÁCH CHƯA CUNG CẤP NGÂN SÁCH."
        ans = BUILD_WITHOUT_BUDGET_ANSWERS[(case_id // len(BUILD_WITHOUT_BUDGET_PHRASES)) % len(BUILD_WITHOUT_BUDGET_ANSWERS)]
    else:
        user_q = random.choice(BUILD_PHRASES).format(price=price_str)
        selection = choose_build_components(budget)
        if selection is None:
            build_context = "KHÔNG TÌM THẤY CẤU HÌNH PHÙ HỢP NGÂN SÁCH."
            ans = "Dạ, em chưa tìm thấy cấu hình phù hợp trong dữ liệu hiện có ạ."
            lc_msgs = PC_BUILD_TEMPLATE.format_messages(user_message=user_q, build_context=build_context)
            dataset.append(lc_to_dict(lc_msgs, ans))
            continue
        (cpu, gpu, main), total_price, assembly_fee = selection
        c_price, g_price, m_price = map(extract_price, (cpu, gpu, main))
        
        build_context = f"[THÔNG TIN BỘ PC]\nCPU: {cpu['tên']} ({c_price:,.0f})\nGPU: {gpu['tên']} ({g_price:,.0f})\nMainboard: {main['tên']} ({m_price:,.0f})\nPhí lắp ráp: {assembly_fee:,.0f}\nTổng: ~{total_price/1000000:.1f} triệu"
        ans = f"Dạ, với ngân sách của bạn, em xin gợi ý cấu hình sau:\n1. CPU: {cpu['tên']} - ~{c_price/1000000:.1f} triệu\n2. GPU: {gpu['tên']} - ~{g_price/1000000:.1f} triệu\n3. Mainboard: {main['tên']} - ~{m_price/1000000:.1f} triệu\n4. Phí lắp ráp: ~{assembly_fee/1000000:.1f} triệu\n* Tổng cộng: ~{total_price/1000000:.1f} triệu"
        
    lc_msgs = PC_BUILD_TEMPLATE.format_messages(user_message=user_q, build_context=build_context)
    dataset.append(lc_to_dict(lc_msgs, ans))

# 3.2 Compat (1500 rows)
for i in range(1500):
    is_negative = (i % 10 == 0) # 10% negative
    
    if is_negative:
        case_id = i // 10
        if case_id % 2:
            user_q = f"CPU Mẫu Không Tồn Tại {case_id} lắp với {random.choice(MAINS)['tên']} được không?"
        else:
            user_q = f"{random.choice(CPUS)['tên']} lắp với Mainboard Mẫu Không Tồn Tại {case_id} được không?"
        compat_context = "[KHÔNG TÌM THẤY CPU HOẶC MAINBOARD TRONG DỮ LIỆU]"
        ans = "Dạ, em chưa tìm thấy thông tin về khả năng tương thích của linh kiện này trong cơ sở dữ liệu. Bạn vui lòng cung cấp thêm thông tin hoặc kiểm tra lại thông số kỹ thuật nhé."
    else:
        cpu, main = random.choice(COMPATIBLE_PAIRS if i % 2 else INCOMPATIBLE_PAIRS)
        user_q = random.choice(COMPAT_PHRASES).format(cpu=cpu['tên'], main=main['tên'])
        compat_context = compatibility_context(cpu, main)
        ans = compatibility_answer(cpu, main)
            
    lc_msgs = COMPAT_CHECK_TEMPLATE.format_messages(user_message=user_q, context=compat_context, format_hint=f"Câu hỏi gốc: '{user_q}'")
    dataset.append(lc_to_dict(lc_msgs, ans))

# 3.3 General / Price / Spec (1500 rows)
for i in range(1500):
    is_negative = (i % 10 == 0) # 10% negative
    
    comp_pool = random.choice(["CPU", "GPU", "MAIN"])
    if comp_pool == "CPU":
        comp = random.choice(CPUS)
        category = "CPU"
    elif comp_pool == "GPU":
        comp = random.choice(GPUS)
        category = "VGA"
    else:
        comp = random.choice(MAINS)
        category = "Mainboard"
        
    mode = random.choice(["price", "spec", "general"])
    
    if is_negative:
        if mode == "price":
            user_q = random.choice(PRICE_CHECK_PHRASES).format(comp=f"{category} Sản phẩm ảo {i}")
            context = "Dạ, danh sách linh kiện thực tế đang có sẵn tại cửa hàng:\n"
            ans = random.choice(PRICE_ANSWERS_NOT_FOUND)
        elif mode == "spec":
            spec_keys = [k for k in comp if k not in ["tên", "giá"] and str(comp[k]) != "Không có"]
            given_key, asked_key = random.sample(spec_keys, 2)
            user_q = random.choice(SPEC_QUERY_TEMPLATES).format(spec=asked_key, comp=comp["tên"])
            context = f"- **[{category}]** {comp['tên']} | {given_key}: {comp[given_key]}"
            ans = random.choice(SPEC_ANSWERS_NOT_FOUND).format(name=comp["tên"], spec_name=asked_key)
        else:
            user_q = f"tìm {category} Không Tồn Tại {i}"
            context = ""
            ans = random.choice(GENERAL_ANSWERS_NOT_FOUND)
        
        format_hint = (
            f"Thông số khách hỏi không có trong dữ liệu. Hãy nói ngắn gọn là chưa có thông tin; "
            f"không thay bằng thông số khác.\nCâu hỏi gốc: '{user_q}'"
            if mode == "spec"
            else f"Câu hỏi gốc: '{user_q}'"
        )
        lc_msgs = BASIC_SEARCH_TEMPLATE.format_messages(user_message=user_q, context=context, format_hint=format_hint)
        dataset.append(lc_to_dict(lc_msgs, ans))
        continue
        
    if mode == "price":
        user_q = random.choice(PRICE_CHECK_PHRASES).format(comp=comp['tên'])
        context = f"Dạ, danh sách linh kiện thực tế đang có sẵn tại cửa hàng:\n- **[{category}]** {comp['tên']} | **Giá:** {comp.get('giá', '0')} VNĐ"
        ans = random.choice(PRICE_ANSWERS).format(name=comp['tên'], price=comp.get('giá', '0'))
        
        format_hint = (
            f"\n[CHỈ THỊ CỦA HỆ THỐNG]: Khách hàng muốn hỏi giá. BẮT BUỘC chỉ trả lời đúng 1 câu ngắn gọn, không giải thích dài dòng: "
            f"\"Dạ, giá của **{comp['tên']}** hiện tại là **{comp.get('giá', '0')} VNĐ** ạ.\""
        ) + f"\nCâu hỏi gốc: '{user_q}'"
        
        lc_msgs = BASIC_SEARCH_TEMPLATE.format_messages(user_message=user_q, context=context, format_hint=format_hint)
        dataset.append(lc_to_dict(lc_msgs, ans))
    elif mode == "spec":
        spec_keys = [k for k in comp.keys() if k not in ['tên', 'giá'] and str(comp[k]) != "Không có"]
        if not spec_keys:
            spec_key = "socket" if category != "VGA" else "bộ nhớ"
            spec_val = "AM4" if category != "VGA" else "8GB"
        else:
            spec_key = random.choice(spec_keys)
            spec_val = comp[spec_key]
        user_q = random.choice(SPEC_QUERY_TEMPLATES).format(spec=spec_key, comp=comp['tên'])
        context = f"Dạ, danh sách linh kiện thực tế đang có sẵn tại cửa hàng:\n- **[{category}]** {comp['tên']} | {spec_key}: {spec_val}"
        
        format_hint = f"THÔNG TIN HỆ THỐNG: Khách đang hỏi thông số '{spec_key}' của '{comp['tên']}'."
        format_hint += f"\nDỮ LIỆU THỰC TẾ: Thông số '{spec_key}' = '{spec_val}'. Hãy trả lời DỰA TRÊN GIÁ TRỊ NÀY, giữ nguyên số và đơn vị."
        format_hint += "\nQUAN TRỌNG: Chỉ trả lời thẳng vào thông tin số liệu. Giữ nguyên đơn vị. KHÔNG giải thích thêm."
        format_hint += "\n[TUYỆT ĐỐI TUÂN THỦ]: TRẢ LỜI NGẮN GỌN TỐI ĐA. KHÔNG yapping, KHÔNG chào hỏi dài dòng, KHÔNG phân tích, KHÔNG kết luận thừa thãi."
        format_hint += f"\nCâu hỏi gốc: '{user_q}'"
        
        ans = random.choice(SPEC_ANSWERS).format(name=comp['tên'], spec_name=spec_key, spec_val=spec_val)
        lc_msgs = BASIC_SEARCH_TEMPLATE.format_messages(user_message=user_q, context=context, format_hint=format_hint)
        dataset.append(lc_to_dict(lc_msgs, ans))
    else: # general
        brand = str(comp['tên']).split()[0]
        user_q = random.choice(GENERAL_QUERY_TEMPLATES[category]).format(brand=brand)
        list_str = f"1. **{comp['tên']}** | Giá: {comp.get('giá', '0')} VNĐ"
        context = f"Dạ, danh sách linh kiện thực tế đang có sẵn tại cửa hàng:\n- **[{category}]** {comp['tên']} | **Giá:** {comp.get('giá', '0')} VNĐ"
        
        format_hint = f"Câu hỏi gốc: '{user_q}'"
        
        ans = random.choice(GENERAL_ANSWERS).format(comp=category, list=list_str)
        lc_msgs = BASIC_SEARCH_TEMPLATE.format_messages(user_message=user_q, context=context, format_hint=format_hint)
        dataset.append(lc_to_dict(lc_msgs, ans))

# 3.4 Multi-turn Memory (500 rows)
# Price -> Spec, Price -> Price, Compat -> Compat, General -> Budget
for i in range(500):
    scenario = random.choice(["price_price", "price_spec", "compat_compat"])
    
    if scenario == "price_price":
        comp1 = random.choice(GPUS)
        comp2 = random.choice([gpu for gpu in GPUS if gpu["tên"] != comp1["tên"]])
        
        user_q1 = random.choice(PRICE_CHECK_PHRASES).format(comp=comp1['tên'])
        context1 = f"Tên: {comp1['tên']}\nGiá: {comp1.get('giá', '0')} VNĐ"
        ans1 = random.choice(PRICE_ANSWERS).format(name=comp1['tên'], price=comp1.get('giá', '0'))
        lc_msgs = BASIC_SEARCH_TEMPLATE.format_messages(user_message=user_q1, context=context1, format_hint="")
        
        user_q2 = random.choice(["còn {comp} thì sao", "thế {comp} giá sao"]).format(comp=comp2['tên'])
        ans2 = random.choice(PRICE_ANSWERS).format(name=comp2['tên'], price=comp2.get('giá', '0'))
        context2 = f"DỮ LIỆU THỰC TẾ CHO LƯỢT HIỆN TẠI:\nTên: {comp2['tên']}\nGiá: {comp2.get('giá', '0')} VNĐ"
        dataset.append(lc_to_dict_multi(lc_msgs, ans1, user_q2, ans2, context2))
        
    elif scenario == "price_spec":
        comp1 = random.choice(GPUS)
        spec_keys = [k for k in comp1.keys() if k not in ['tên', 'giá'] and str(comp1[k]) != "Không có"]
        spec_key = random.choice(spec_keys) if spec_keys else "bộ nhớ"
        spec_val = comp1.get(spec_key, "8GB")
        
        user_q1 = random.choice(PRICE_CHECK_PHRASES).format(comp=comp1['tên'])
        context1 = (
            f"Tên: {comp1['tên']}\nGiá: {comp1.get('giá', '0')} VNĐ\n"
            f"{spec_key}: {spec_val}"
        )
        ans1 = random.choice(PRICE_ANSWERS).format(name=comp1['tên'], price=comp1.get('giá', '0'))
        lc_msgs = BASIC_SEARCH_TEMPLATE.format_messages(user_message=user_q1, context=context1, format_hint="")
        
        user_q2 = f"thế còn {spec_key} thì sao?"
        ans2 = random.choice(SPEC_ANSWERS).format(name=comp1['tên'], spec_name=spec_key, spec_val=spec_val)
        dataset.append(lc_to_dict_multi(lc_msgs, ans1, user_q2, ans2))
        
    elif scenario == "compat_compat":
        cpu1, compatible_main = random.choice(COMPATIBLE_PAIRS)
        incompatible_main = random.choice([main for main in MAINS if not is_compatible(cpu1, main)])
        main1, main2 = (compatible_main, incompatible_main) if i % 2 else (incompatible_main, compatible_main)
        
        user_q1 = random.choice(COMPAT_PHRASES).format(cpu=cpu1['tên'], main=main1['tên'])
        compat_context1 = compatibility_context(cpu1, main1)
        ans1 = compatibility_answer(cpu1, main1)
        
        lc_msgs = COMPAT_CHECK_TEMPLATE.format_messages(user_message=user_q1, context=compat_context1, format_hint=f"Câu hỏi gốc: '{user_q1}'")
        
        user_q2 = f"thế còn main {main2['tên']} thì sao?"
        ans2 = compatibility_answer(cpu1, main2)
        context2 = f"THÔNG TIN KỸ THUẬT CHO LƯỢT HIỆN TẠI:\n{compatibility_context(cpu1, main2)}"
        dataset.append(lc_to_dict_multi(lc_msgs, ans1, user_q2, ans2, context2))

# 3.5 Recent Product Tracking (150 rows)
for _ in range(150):
    category, pool = random.choice([("CPU", CPUS), ("GPU", GPUS), ("Mainboard", MAINS)])
    comp1, comp2 = random.sample(pool, 2)

    user_q1 = random.choice(PRICE_CHECK_PHRASES).format(comp=comp1["tên"])
    context1 = f"Tên: {comp1['tên']}\nGiá: {comp1.get('giá', '0')} VNĐ"
    ans1 = random.choice(PRICE_ANSWERS).format(name=comp1["tên"], price=comp1.get("giá", "0"))
    lc_msgs = BASIC_SEARCH_TEMPLATE.format_messages(user_message=user_q1, context=context1, format_hint="")

    user_q2 = random.choice(["còn {name} thì sao", "thế {name} giá sao"]).format(name=comp2["tên"])
    context2 = f"DỮ LIỆU THỰC TẾ CHO LƯỢT HIỆN TẠI:\nTên: {comp2['tên']}\nGiá: {comp2.get('giá', '0')} VNĐ"
    ans2 = random.choice(PRICE_ANSWERS).format(name=comp2["tên"], price=comp2.get("giá", "0"))

    user_q3 = random.choice([
        f"Tên {category} tôi vừa hỏi sau cùng là gì?",
        "Sản phẩm tôi vừa hỏi tên đầy đủ là gì?",
        "Mình vừa hỏi mẫu nào?",
    ])
    ans3 = f"Dạ, sản phẩm bạn vừa hỏi là {comp2['tên']} ạ."
    dataset.append(lc_to_dict_three_turns(lc_msgs, ans1, context2, user_q2, ans2, user_q3, ans3))

# 3.6 Single-component Budget Search (250 rows)
for _ in range(250):
    category, category_word, pool = random.choice([
        ("CPU", "CPU", CPUS),
        ("GPU", "GPU", GPUS),
        ("Mainboard", "mainboard", MAINS),
    ])
    _, budget = random.choice(BUDGETS)
    matched = sorted(
        (component for component in pool if 0 < extract_price(component) <= budget),
        key=extract_price,
        reverse=True,
    )[:5]
    if not matched:
        continue

    budget_text = f"{budget // 1_000_000} triệu"
    user_q = random.choice([
        f"tìm {category_word} dưới {budget_text}",
        f"liệt kê {category_word} không vượt quá {budget_text}",
        f"có {category_word} nào trong ngân sách {budget_text} không?",
    ])
    context = "\n".join(
        f"- **[{category}]** {component['tên']} | **Giá:** {component.get('giá', '0')} VNĐ"
        for component in matched
    )
    format_hint = (
        f"Đã lọc các sản phẩm {category} có giá không vượt quá {budget:,} VNĐ. "
        "Hãy liệt kê đúng tên và giá của từng sản phẩm trong dữ liệu."
    )
    answer_list = "\n".join(
        f"{index}. {component['tên']} - {component.get('giá', '0')} VNĐ"
        for index, component in enumerate(matched, 1)
    )
    answer = f"Dạ, các sản phẩm {category} trong ngân sách của bạn gồm:\n{answer_list}"
    lc_msgs = SUGGESTION_TEMPLATE.format_messages(user_message=user_q, context=context, format_hint=format_hint)
    dataset.append(lc_to_dict(lc_msgs, answer))

# 3.7 Impossible Budget Trap (50 rows)
for _ in range(50):
    price_str = random.choice(IMPOSSIBLE_BUDGETS)
    user_q = random.choice(BUILD_PHRASES).format(price=price_str)
    build_context = "[NGÂN SÁCH QUÁ THẤP] Không tìm thấy bộ CPU + GPU + Mainboard phù hợp trong dữ liệu."
    ans = f"Dạ, em chưa tìm thấy bộ CPU, GPU và Mainboard nào phù hợp với mức ngân sách {price_str} trong dữ liệu hiện có ạ."
    lc_msgs = PC_BUILD_TEMPLATE.format_messages(user_message=user_q, build_context=build_context)
    dataset.append(lc_to_dict(lc_msgs, ans))

# 3.8 Raw grounding contrast (120 rows)
component_sources = [("CPU", CPUS), ("GPU", GPUS), ("Mainboard", MAINS)]
for i in range(120):
    category, pool = component_sources[i % len(component_sources)]
    comp = pool[(i // len(component_sources)) % len(pool)]
    name = comp["tên"] if i < 60 else f"{category} Atlas-{i:03d}"
    spec_keys = [k for k in comp if k not in ["tên", "giá"] and str(comp[k]) != "Không có"]
    shown_key, other_key = random.sample(spec_keys, 2)
    asked_key = shown_key if i % 2 == 0 else other_key
    user_q = random.choice(SPEC_QUERY_TEMPLATES).format(spec=asked_key, comp=name)
    user_content = (
        f"DỮ LIỆU:\n- {name} có {shown_key} {comp[shown_key]}.\n\n"
        f"CÂU HỎI:\n{user_q}"
    )
    answer = (
        random.choice(SPEC_ANSWERS).format(
            name=name, spec_name=shown_key, spec_val=comp[shown_key]
        )
        if asked_key == shown_key
        else random.choice(SPEC_ANSWERS_NOT_FOUND).format(name=name, spec_name=asked_key)
    )
    dataset.append({"messages": [
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": answer},
    ]})

# 3.9 Suggestion failures (75 rows)
for i in range(75):
    component_type, label, pool = random.choice([
        ("cpu", "CPU", CPUS),
        ("mainboard", "Mainboard", MAINS),
        ("gpu", "GPU", GPUS),
    ])
    item = random.choice(pool)

    if i % 3 == 0:
        user_q = f"tìm thêm {label} để lắp chung với {item['tên']}"
        context = (
            "[LỖI LOGIC TỪ NGƯỜI DÙNG]\n"
            f"Khách đang yêu cầu tìm {label} để lắp với '{item['tên']}' (cũng là {label}).\n"
            f"Một bộ PC thông thường chỉ sử dụng 1 {label}."
        )
        answer = f"Dạ, một bộ PC thông thường chỉ dùng một {label}, nên không thể lắp thêm {label} cùng loại với {item['tên']} ạ."
    elif i % 3 == 1:
        unknown_name = f"{label} Mẫu Không Tồn Tại {i}"
        user_q = f"tìm linh kiện phù hợp với {unknown_name}"
        context = (
            "[CẢNH BÁO TỪ HỆ THỐNG]\n"
            f"Cửa hàng không có sản phẩm '{unknown_name}' nên chưa thể kiểm tra thông số để gợi ý linh kiện tương thích."
        )
        answer = f"Dạ, cửa hàng chưa có {unknown_name}, nên em chưa thể gợi ý linh kiện tương thích chính xác ạ."
    else:
        user_q = f"tìm linh kiện phù hợp với {item['tên']}"
        context = (
            "[KẾT QUẢ TÌM KIẾM]\n"
            f"Đã xác định '{item['tên']}' nhưng hiện không có linh kiện tương thích trong kho."
        )
        answer = f"Dạ, cửa hàng hiện chưa có linh kiện tương thích để ghép với {item['tên']} ạ."

    lc_msgs = SUGGESTION_TEMPLATE.format_messages(user_message=user_q, context=context, format_hint="")
    dataset.append(lc_to_dict(lc_msgs, answer))

# 3.10 Pass-1 Classification + Pass-2 Extraction
INTENTS = (
    "compatibility",
    "suggestion",
    "price_calculation",
    "specification",
    "price_check",
    "budget_search",
    "combo_review",
    "build_pc",
    "general_search",
    "none",
)

for intent in INTENTS:
    cases = []
    seen_inputs = set()
    attempts = 0
    while len(cases) < 40 and attempts < 2000:
        history, question, extracted = make_intent_case(intent, len(cases))
        user_content = f"{history}<user_input>{question}</user_input>"
        attempts += 1
        if user_content in seen_inputs:
            continue
        seen_inputs.add(user_content)
        cases.append((history, question, extracted))

    if len(cases) != 40:
        raise RuntimeError(f"Không tạo đủ dữ liệu intent đa dạng cho {intent}")

    for index, (history, question, extracted) in enumerate(cases):
        dataset.append({
            "messages": [
                {"role": "system", "content": _SYSTEM_CLASSIFY},
                {"role": "user", "content": f"{history}<user_input>{question}</user_input>"},
                {"role": "assistant", "content": json.dumps({"intent": intent}, ensure_ascii=False)},
            ]
        })

        if index < 20:
            dataset.append({
                "messages": [
                    {"role": "system", "content": _SYSTEM_EXTRACT},
                    {
                        "role": "user",
                        "content": f"{history}<system_hint>Intent = {intent}</system_hint>\n<user_input>{question}</user_input>",
                    },
                    {"role": "assistant", "content": json.dumps(extracted, ensure_ascii=False)},
                ]
            })

# --- 4. DEDUPLICATE, SHUFFLE & GHI FILE ---
unique_dataset = []
seen = set()
for row in dataset:
    row_str = json.dumps(row, ensure_ascii=False)
    if row_str not in seen:
        seen.add(row_str)
        unique_dataset.append(row)

dataset = unique_dataset

positive_compat = []
negative_compat = []
for row in dataset:
    if len(row["messages"]) != 3:
        continue
    system_text = row["messages"][0]["content"]
    if "KẾT LUẬN TƯƠNG THÍCH: KHÔNG TƯƠNG THÍCH" in system_text:
        negative_compat.append(row)
    elif "KẾT LUẬN TƯƠNG THÍCH: TƯƠNG THÍCH" in system_text:
        positive_compat.append(row)

if not positive_compat or not negative_compat:
    raise RuntimeError("Thiếu dữ liệu tương thích CPU/Mainboard hai chiều")

negative_ids = {id(row) for row in negative_compat}
kept_negative_ids = {id(row) for row in random.sample(negative_compat, min(len(negative_compat), len(positive_compat)))}
dataset = [row for row in dataset if id(row) not in negative_ids or id(row) in kept_negative_ids]
random.shuffle(dataset)

assert all(
    row.get("messages")
    and all(message.get("role") in {"system", "user", "assistant"} and message.get("content") for message in row["messages"])
    for row in dataset
)
assert not any(
    marker in message["content"].lower()
    for row in dataset
    for message in row["messages"]
    for marker in ("cách nấu cơm", "thời tiết hôm nay", "làm thơ", "giá vàng", "ram ddr6", "tản nhiệt abc")
)
assert sum(
    len(row["messages"]) == 3
    and "KẾT LUẬN TƯƠNG THÍCH: KHÔNG TƯƠNG THÍCH" in row["messages"][0]["content"]
    for row in dataset
) == len(positive_compat)
assert sum(row["messages"][0]["content"] == _SYSTEM_CLASSIFY for row in dataset) == 400
assert sum(row["messages"][0]["content"] == _SYSTEM_EXTRACT for row in dataset) == 200
assert sum(
    "Thông số khách hỏi không có trong dữ liệu" in row["messages"][0]["content"]
    for row in dataset
) >= 40
for marker in ("[LỖI LOGIC TỪ NGƯỜI DÙNG]", "[CẢNH BÁO TỪ HỆ THỐNG]", "[KẾT QUẢ TÌM KIẾM]"):
    assert sum(marker in row["messages"][0]["content"] for row in dataset) >= 20
assert sum(
    any(
        "KHÔNG CÓ DỮ LIỆU DO KHÁCH CHƯA CUNG CẤP NGÂN SÁCH" in message["content"]
        for message in row["messages"]
    )
    for row in dataset
) >= 20
assert sum(
    "[KHÔNG TÌM THẤY CPU HOẶC MAINBOARD TRONG DỮ LIỆU]" in row["messages"][0]["content"]
    for row in dataset
) >= 100
assert sum("Sản phẩm ảo" in row["messages"][1]["content"] for row in dataset) >= 40
assert sum("Không Tồn Tại" in row["messages"][1]["content"] for row in dataset) >= 40
raw_grounding_rows = [
    row for row in dataset
    if len(row["messages"]) == 2
    and row["messages"][0]["role"] == "user"
    and row["messages"][0]["content"].startswith("DỮ LIỆU:")
]
assert len(raw_grounding_rows) == 120
assert sum("chưa" in row["messages"][1]["content"].lower() for row in raw_grounding_rows) == 60
assert not any(
    phrase in message["content"].lower()
    for row in dataset
    for message in row["messages"]
    if message["role"] == "assistant"
    for phrase in ("không chính xác", "dựa trên thông tin được cung cấp")
)

out_file = os.path.abspath(os.path.join(base_dir, "finetune_data_clean.jsonl"))
os.makedirs(os.path.dirname(out_file), exist_ok=True)

temp_file = f"{out_file}.tmp"
with open(temp_file, "w", encoding="utf-8") as f:
    for row in dataset:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
os.replace(temp_file, out_file)

print(f"Generated {len(dataset)} validated rows into {out_file}")
