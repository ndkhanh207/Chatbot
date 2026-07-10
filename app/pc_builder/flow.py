import re
from app.pc_builder.context import ConversationMemory

from .constants import (
    BEST_KEYWORDS, CHEAPEST_KEYWORDS, EXPENSIVE_KEYWORDS, PURPOSE_KEYWORD_MAP,
    ADJUSTMENT_LOCK_KEYWORDS, ADJUSTMENT_SWAP_KEYWORDS, ADJUSTMENT_BUDGET_KEYWORDS, BRAND_SWITCH_KEYWORDS
)
from .extractor import (
    extract_budget, extract_quantity, extract_brand_filter,
    extract_component_filter, extract_explicit_build_id, infer_purpose,
    is_reset_intent, extract_upgrade_component, extract_build_adjustment, extract_priority_bias
)
from .history import inherit_budget, inherit_quantity
from .formatter import format_approx_million, format_build_context, format_reply_body

from app.pc_builder.advisor import find_best_build
from app.pc_builder.presets import get_preset_by_id, get_preset_reply
from app.pc_builder.multi_turn import apply_build_adjustment
BUILD_REPLY_HEADER = '[GỢI Ý BỘ PC TỐI ƯU]'

class PcBuildEngine:
    def __init__(self, user_uid: str, session_id: str, user_message: str, user_message_fixed: str, msg_lower: str, search_query: str, chat_history: list, build_df, is_build_pc: bool, recognized_intent: str = "none"):
        self.user_uid = user_uid
        self.session_id = session_id
        self.user_message = user_message
        self.user_message_fixed = user_message_fixed
        self.msg_lower = msg_lower
        self.search_query = search_query
        self.chat_history = chat_history
        self.build_df = build_df
        self.is_build_pc = is_build_pc
        self.recognized_intent = recognized_intent
        
        self.memory = ConversationMemory(user_uid, session_id)
        self.ctx = self.memory.load_context()
        
        # State populated during execution
        self.budget = None
        self.quantity = 1
        self.brand_filter = {}
        self.component_filter = {}
        self.has_specific_component = False
        self.upgrade_info = {}
        self.is_upgrade_scenario = False
        self.is_adjustment = False
        self.combined_message_for_purpose = user_message
        self.has_final_purpose = False
        self.skip_presets = False

    def execute(self) -> dict | None:
        # 1. Explicit Build ID
        explicit_build_id = extract_explicit_build_id(self.user_message)
        if explicit_build_id:
            return self._handle_explicit_build(explicit_build_id)

        # 2. Context overrides
        override_reply = self._resolve_context_override()
        if override_reply:
            return override_reply

        if not self.is_build_pc:
            return None

        # 3. Cheapest/Expensive
        wants_cheapest = any(kw in self.msg_lower for kw in CHEAPEST_KEYWORDS)
        wants_expensive = any(kw in self.msg_lower for kw in EXPENSIVE_KEYWORDS)
        wants_best = any(kw in self.msg_lower for kw in BEST_KEYWORDS)

        if wants_cheapest or wants_expensive:
            return self._handle_extreme_price_build(wants_cheapest)

        # 4. Resolve budget and quantity
        budget_early_reply = self._resolve_budget_and_quantity(wants_best)
        if budget_early_reply:
            return budget_early_reply

        # 5. Extract purpose
        self._extract_purpose()

        # 6. Resolve filters
        self._resolve_filters()

        # 6.5. Multi-turn build adjustment
        self._handle_multi_turn_adjustment()

        # 7. Check missing info
        missing_info_reply = self._handle_missing_info()
        if missing_info_reply:
            return missing_info_reply

        # 8. Check presets
        if not self.skip_presets:
            preset = get_preset_reply(self.budget, self.combined_message_for_purpose, self.brand_filter, self.component_filter)
            if preset:
                print(f"⚠️ [PRESET MATCHED] Trả về bộ PC có sẵn cho ngân sách {self.budget}")
                self.ctx.build_id = preset["id"]
                self.ctx.preset_id = preset["id"]
                self.ctx.budget = self.budget
                self.ctx.last_suggested_cpu = preset.get("cpu")
                self.ctx.last_suggested_gpu = preset.get("gpu")
                self.ctx.last_suggested_mainboard = preset.get("mainboard")
                self.ctx.pending_question = None
                self.memory.commit_turn(self.user_message, preset["reply"], self.ctx)
                return {'chatbot_reply': preset["reply"]}

        # 9. Find best build
        return self._find_and_reply_best_build()

    def _apply_upgrade_to_filter(self) -> None:
        if self.upgrade_info.get('is_upgrade'):
            if self.upgrade_info.get('cpu_model') and not self.component_filter.get('cpu_model'):
                self.component_filter['cpu_model'] = self.upgrade_info['cpu_model']
            if self.upgrade_info.get('gpu_model') and not self.component_filter.get('gpu_model'):
                self.component_filter['gpu_model'] = self.upgrade_info['gpu_model']

    def _resolve_context_override(self) -> dict | None:
        if not self.chat_history:
            return None

        if self.recognized_intent in {"specification", "price_check", "compatibility"}:
            return None

        ai_asked_to_drop_filter = self.ctx.pending_question == "drop_filter"
        user_agrees = any(kw in self.msg_lower for kw in ['ok', 'đồng ý', 'được', 'triển', 'gợi ý', 'tìm đi'])
        if ai_asked_to_drop_filter and user_agrees:
            print("⚠️ [CONTEXT] Khách hàng đồng ý bỏ filter linh kiện/hãng không tìm thấy.")
            self.ctx.user_cpu = None
            self.ctx.user_gpu = None
            self.ctx.user_mainboard = None
            self.ctx.pending_question = None
            self.is_build_pc = True

        if self.is_build_pc:
            return None

        asked_budget = self.ctx.pending_question == "budget"
        asked_purpose = self.ctx.pending_question == "purpose"
        wants_cheapest = any(kw in self.msg_lower for kw in CHEAPEST_KEYWORDS)
        wants_best = any(kw in self.msg_lower for kw in BEST_KEYWORDS)
        has_purpose = any(kw in self.msg_lower for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list)
        
        if asked_budget and (extract_budget(self.user_message, context_aware=True) is not None or wants_cheapest):
            print(f"⚠️ [FALLBACK OVERRIDE] Context-Aware: Khách đang trả lời ngân sách, ép luồng BUILD_PC.")
            self.is_build_pc = True
        elif asked_purpose and has_purpose:
            print(f"⚠️ [FALLBACK OVERRIDE] Context-Aware: Khách đang trả lời mục đích, ép luồng BUILD_PC.")
            self.is_build_pc = True


        recent_build_context = bool(self.ctx.build_id and self.ctx.build_id != "BUILD-PENDING")

        is_question_about_current_build = False
        if recent_build_context:
            budget_current = extract_budget(self.user_message_fixed)
            is_component_query = re.search(r'\b(cpu|gpu|bo mạch chủ|mainboard|card|chip|vga)\b', self.msg_lower)
            wants_adjustment = bool(re.search(r'\b(cao hơn|đắt hơn|mạnh hơn|ngon hơn|thấp hơn|rẻ hơn|yếu hơn|bèo hơn)\b', self.msg_lower))
            
            is_question_about_current_build = bool(re.search(
                r'\b(bộ này|cái này|nó có|máy này|cấu hình này|bộ đó|cái đó|có thể.*không|chơi được không|có.*không)\b',
                self.msg_lower
            ))

            has_explicit_adj = any(kw in self.msg_lower for kw in ADJUSTMENT_LOCK_KEYWORDS + ADJUSTMENT_SWAP_KEYWORDS + ADJUSTMENT_BUDGET_KEYWORDS + BRAND_SWITCH_KEYWORDS)

            if has_explicit_adj:
                print(f"⚠️ [FALLBACK OVERRIDE] Context-Aware: Có từ khóa điều chỉnh linh kiện rõ ràng, ép luồng BUILD_PC.")
                self.is_build_pc = True
            elif (budget_current is not None or has_purpose or wants_cheapest or wants_best or wants_adjustment) \
                    and not is_component_query \
                    and not is_question_about_current_build:
                print(f"⚠️ [FALLBACK OVERRIDE] Context-Aware: Có keyword điều chỉnh PC đang build, ép luồng BUILD_PC.")
                self.is_build_pc = True

        if is_question_about_current_build and not has_explicit_adj and not wants_adjustment:
            return self._answer_about_current_build()
        return None

    def _resolve_budget_and_quantity(self, wants_best: bool) -> dict | None:
        _asked_budget = self.ctx.pending_question == "budget"
        self.budget = extract_budget(self.user_message, context_aware=_asked_budget)
        self.quantity = extract_quantity(self.user_message)
        
        if wants_best:
            inherited_budget = inherit_budget(self.msg_lower, self.ctx.budget)
            if inherited_budget is None:
                reply = (
                    "Dạ, để tìm bộ PC tốt nhất cho bạn, "
                    "em cần biết ngân sách bạn muốn đầu tư là bao nhiêu ạ? "
                    "(ví dụ: 30 triệu, 50 triệu...)"
                )
                return self._commit_early_reply(reply, pending_question="budget")
            self.budget = inherited_budget
        else:
            if self.budget is None:
                self.budget = inherit_budget(self.msg_lower, self.ctx.budget)

        if self.budget is not None and self.budget < 10_000_000:
            if self.budget <= 0:
                last_build_id = self.ctx.build_id
                if last_build_id and self.build_df is not None:
                    rows = self.build_df[self.build_df['BuildID'] == last_build_id]
                    if not rows.empty:
                        best_build = rows.iloc[0].to_dict()
                        reply = (
                            f"Ngân sách không hợp lệ ạ! Em hiển thị lại bộ PC trước đó cho bạn tham khảo:\n\n"
                            + format_reply_body(best_build, 0, 'sử dụng')
                        )
                        return self._commit_early_reply(reply, pending_question="budget")
                reply = "Dạ, ngân sách không hợp lệ ạ. Bạn vui lòng nhập lại tầm giá mong muốn nhé!"
            else:
                reply = (
                    f"Dạ ngân sách {format_approx_million(self.budget)} hơi thấp ạ. "
                    "Hiện tại các bộ PC bên em đang phân phối có giá từ 10 triệu trở lên. "
                    "Bạn cân nhắc nâng thêm chút ngân sách nhé!"
                )
            return self._commit_early_reply(reply, pending_question="budget")

        if self.quantity == 1 and self.chat_history:
            self.quantity = inherit_quantity(self.chat_history)
            
        if self.quantity > 1 and self.budget is not None and self.budget > 0:
            budget_per_unit = self.budget // self.quantity
            if budget_per_unit < 10_000_000:
                reply = (
                    f"Dạ, với tổng ngân sách {format_approx_million(self.budget)} cho {self.quantity} bộ, "
                    f"mỗi bộ chỉ có ~{format_approx_million(budget_per_unit)}. "
                    "Hiện tại cấu hình PC bên em phân phối có giá thấp nhất từ 10 triệu/bộ ạ. "
                    "Bạn có thể tăng ngân sách hoặc giảm số lượng không?"
                )
                return self._commit_early_reply(reply, pending_question="budget")
            self.budget = budget_per_unit
        return None

    def _extract_purpose(self):
        self.has_final_purpose = any(kw in self.msg_lower for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list)
        if not self.has_final_purpose and self.chat_history:
            for msg in reversed(self.chat_history):
                if getattr(msg, 'type', '') == 'human':
                    if any(kw in msg.content.lower() for kw_list in PURPOSE_KEYWORD_MAP.values() for kw in kw_list):
                        self.combined_message_for_purpose += ' ' + msg.content
                        self.has_final_purpose = True
                        break

    def _resolve_filters(self):
        self.brand_filter = extract_brand_filter(self.search_query)
        self.component_filter = extract_component_filter(self.search_query)
        print(f"DEBUG 1 component_filter: {self.component_filter}")

        self.upgrade_info = extract_upgrade_component(self.user_message)
        self.is_upgrade_scenario = self.upgrade_info.get('is_upgrade', False)
        
        self._apply_upgrade_to_filter()
        print(f"DEBUG 2 component_filter: {self.component_filter}")

        if not self.ctx.build_id or self.ctx.build_id == 'BUILD-PENDING':
            if not self.component_filter.get('cpu_model') and self.ctx.user_cpu:
                self.component_filter['cpu_model'] = self.ctx.user_cpu
            if not self.component_filter.get('gpu_model') and self.ctx.user_gpu:
                self.component_filter['gpu_model'] = self.ctx.user_gpu
            if not self.component_filter.get('mainboard') and self.ctx.user_mainboard:
                self.component_filter['mainboard'] = self.ctx.user_mainboard
        print(f"DEBUG 3 component_filter: {self.component_filter}")

        self.has_specific_component = bool(self.component_filter.get('cpu_model') or self.component_filter.get('gpu_model') or self.component_filter.get('mainboard'))

    def _commit_early_reply(self, reply: str, pending_question: str | None = None) -> dict:
        self.ctx.build_id = 'BUILD-PENDING'
        self.ctx.pending_question = pending_question
        if self.component_filter.get('cpu_model'): self.ctx.user_cpu = self.component_filter.get('cpu_model')
        if self.component_filter.get('gpu_model'): self.ctx.user_gpu = self.component_filter.get('gpu_model')
        if self.component_filter.get('mainboard'): self.ctx.user_mainboard = self.component_filter.get('mainboard')
        self.memory.commit_turn(self.user_message, reply, self.ctx)
        return {'chatbot_reply': reply}

    def _handle_multi_turn_adjustment(self):
        last_build = None
        if self.ctx.build_id:
            last_build = {
                'build_id': self.ctx.build_id,
                'cpu_model': self.ctx.last_suggested_cpu,
                'gpu_model': self.ctx.last_suggested_gpu,
                'mainboard_model': self.ctx.last_suggested_mainboard,
            }
        
        if last_build:
            adjustment = extract_build_adjustment(self.user_message, last_build)
            if adjustment:
                print("\n=== 🛠️ [DEBUG MULTI-TURN] PHÁT HIỆN ĐIỀU CHỈNH CẤU HÌNH ===")
                print(f"  - Loại điều chỉnh: {adjustment.get('type')}")
                print(f"  - LAST BUILD: {last_build}")
                print(f"  - Từ cấu hình cũ: {last_build.get('build_id')}")
                
                self.budget, self.component_filter, self.brand_filter = apply_build_adjustment(
                    adjustment, last_build, self.budget, self.component_filter, self.brand_filter
                )
                
                print(f"  - Ngân sách sau điều chỉnh: {self.budget}")
                print(f"  - Lọc linh kiện (Component Filter): {self.component_filter}")
                print(f"  - Lọc hãng (Brand Filter): {self.brand_filter}")
                print("========================================================\n")
                if self.component_filter.get('category') and not adjustment.get('new_budget') and extract_budget(self.user_message_fixed) is None:
                    self.budget = None
                
                self.skip_presets = True
                self.is_adjustment = True
                self.has_specific_component = bool(self.component_filter.get('cpu_model') or self.component_filter.get('gpu_model') or self.component_filter.get('mainboard'))

    def _handle_missing_info(self) -> dict | None:
        upgrade_cat = self.component_filter.get('category')
        if self.budget is None and upgrade_cat:
            reply = (
                f"Dạ để nâng cấp {upgrade_cat.upper()} lên dòng cao hơn, "
                "bạn dự định đầu tư tổng ngân sách mới cho bộ máy là khoảng bao nhiêu tiền ạ? "
                "(ví dụ: 30 triệu, 40 triệu...)"
            )
            return self._commit_early_reply(reply, pending_question="budget")

        if self.budget is None and not self.has_final_purpose and not self.has_specific_component:
            reply = (
                "Dạ, để em tư vấn bộ PC chuẩn nhất, bạn cho em biết bạn dùng máy chủ yếu "
                "để làm gì (chơi game, làm đồ họa...) và tầm giá khoảng bao nhiêu nhé!"
            )
            return self._commit_early_reply(reply, pending_question="budget")

        if self.budget is None and (self.has_final_purpose or self.has_specific_component):
            if self.has_specific_component and not self.has_final_purpose:
                comp_name = self.component_filter.get('cpu_model') or self.component_filter.get('gpu_model')
                reply = (
                    f"Dạ để build bộ máy có {comp_name.upper()}, "
                    "bạn dự định đầu tư khoảng bao nhiêu tiền ạ? (ví dụ: 20 triệu, 30 triệu...)"
                )
            else:
                purpose_str = infer_purpose(self.combined_message_for_purpose)
                reply = (
                    f"Dạ để build bộ máy tối ưu cho nhu cầu {purpose_str}, "
                    "bạn dự định đầu tư khoảng bao nhiêu tiền ạ? (ví dụ: 20 triệu, 30 triệu...)"
                )
            return self._commit_early_reply(reply, pending_question="budget")

        if self.budget is not None and not self.has_final_purpose and not self.has_specific_component:
            reply = (
                f"Dạ với ngân sách khoảng {format_approx_million(self.budget)}, em có thể ráp được nhiều cấu hình tối ưu "
                "cho các mục đích khác nhau. Bạn dự định dùng máy chủ yếu để làm gì ạ? "
                "(ví dụ: chơi game AAA, văn phòng, làm đồ họa 3D, hay lập trình...)"
            )
            return self._commit_early_reply(reply, pending_question="purpose")
        return None

    def _handle_extreme_price_build(self, wants_cheapest: bool) -> dict:
        self._resolve_filters()
        best_build = find_best_build(
            budget=0, user_message=self.user_message, build_df=self.build_df,
            exclude_builds=self.ctx.exclude_builds, brand_filter=self.brand_filter,
            component_filter=self.component_filter, priority_bias=None
        )
        if best_build is None:
            reply = "Dạ, em không tìm được bộ PC nào phù hợp trong kho ạ!"
            self.memory.commit_turn(self.user_message, reply, self.ctx)
            return {'chatbot_reply': reply}
            
        label = 'rẻ nhất' if wants_cheapest else 'mắc nhất'
        return self._build_reply(best_build, label)

    def _find_and_reply_best_build(self) -> dict:
        priority_bias = extract_priority_bias(self.user_message_fixed)
        
        best_build = find_best_build(
            budget=self.budget, user_message=self.combined_message_for_purpose, build_df=self.build_df,
            exclude_builds=self.ctx.exclude_builds, brand_filter=self.brand_filter, component_filter=self.component_filter,
            priority_bias=priority_bias
        )

        if best_build is None:
            return self._build_not_found_reply()

        if best_build.get("out_of_budget"):
            min_price = format_approx_million(best_build["min_price"])
            cur_budget = format_approx_million(self.budget)
            prefix = ""
            if self.is_upgrade_scenario and self.upgrade_info:
                comp_name = self.upgrade_info.get('cpu_model') or self.upgrade_info.get('gpu_model')
                if comp_name:
                    prefix = f"em ghi nhận bạn đã có sẵn {comp_name.upper()}, nhưng "
            reply = f"Dạ, {prefix}bộ PC rẻ nhất đáp ứng yêu cầu của bạn hiện có giá khoảng {min_price}, cao hơn ngân sách {cur_budget} hiện tại. Bạn có muốn tăng ngân sách lên mức này để em tiếp tục gợi ý không ạ?"
            return self._commit_early_reply(reply, pending_question="budget")
            
        purpose_str = infer_purpose(self.combined_message_for_purpose)
        return self._build_reply(best_build, purpose_str)

    def _build_not_found_reply(self) -> dict:
        comp = self.component_filter or {}
        gpu_req = comp.get('gpu_model')
        cpu_req = comp.get('cpu_model')
        brand   = self.brand_filter or {}

        if gpu_req:
            reply = (
                f"Dạ, hiện bên em chưa có bộ PC nào sử dụng GPU **{gpu_req.upper()}** trong kho ạ. "
                "Bạn có muốn em gợi ý bộ PC dùng GPU gần nhất không?"
            )
        elif cpu_req:
            reply = (
                f"Dạ, hiện bên em chưa có bộ PC nào sử dụng CPU **{cpu_req.upper()}** phù hợp với ngân sách này ạ. "
                "Bạn có muốn thử ngân sách cao hơn không?"
            )
        elif brand.get('cpu_brand') or brand.get('gpu_brand'):
            brand_name = brand.get('cpu_brand') or brand.get('gpu_brand')
            reply = (
                f"Dạ, em không tìm được bộ PC {brand_name} nào phù hợp với ngân sách của bạn ạ. "
                "Bạn thử điều chỉnh ngân sách hoặc bỏ yêu cầu hãng nhé!"
            )
        else:
            reply = (
                "Dạ, hiện tại bên em không tìm được bộ PC nào phù hợp với "
                "ngân sách và mục đích của bạn. "
                "Bạn có thể điều chỉnh ngân sách hoặc cho em biết thêm nhu cầu cụ thể nhé!"
            )
            
        return self._commit_early_reply(reply)

    def _invoke_llm_for_build(self, system_prompt: str, fallback_reply: str) -> str:
        from app.core.llm_chains import get_pc_build_qa_chain
        try:
            chain = get_pc_build_qa_chain()
            res = chain.invoke({"system_prompt": system_prompt, "user_message": self.user_message})
            return res.content.strip()
        except Exception:
            return fallback_reply

    def _build_reply(self, best_build: dict, purpose_str: str) -> dict:
        build_context = format_reply_body(best_build, self.budget or 0, purpose_str, self.quantity)

        print(f"🔍 [HỆ THỐNG DEBUG PC BUILDER] - Context saved")
        print(f"🔹 Nội dung [build_context] nạp vào:\n{build_context}")
        print("════════════════════════════════════════════════════════════\n")

        build_id = best_build.get('BuildID', 'N/A')
        final_reply = build_context
        
        if self.is_upgrade_scenario and self.upgrade_info:
            comp_name = self.upgrade_info.get('cpu_model') or self.upgrade_info.get('gpu_model') or "linh kiện của bạn"
            final_reply = f"Em ghi nhận bạn đã có sẵn {comp_name.upper()}. Bộ PC gợi ý dưới đây sẽ tận dụng linh kiện này để build phần còn lại cho bạn:\n\n{final_reply}"
            
        self.ctx.build_id = build_id
        self.ctx.budget = self.budget
        
        if best_build.get('CPU_Model'): self.ctx.last_suggested_cpu = best_build.get('CPU_Model')
        if best_build.get('GPU_Model'): self.ctx.last_suggested_gpu = best_build.get('GPU_Model')
        if best_build.get('Motherboard_Model'): self.ctx.last_suggested_mainboard = best_build.get('Motherboard_Model')
        
        if build_id not in self.ctx.exclude_builds and build_id != 'N/A':
            self.ctx.exclude_builds.append(build_id)
            
        self.memory.commit_turn(self.user_message, final_reply, self.ctx)
        return {'chatbot_reply': final_reply}

    def _answer_about_current_build(self) -> dict:
        if not self.ctx.build_id or self.ctx.build_id == 'BUILD-PENDING':
            reply = "Dạ, em không tìm thấy thông tin bộ PC nào gần đây cả. Bạn có thể nhắc lại yêu cầu hoặc cung cấp mã bộ PC giúp em được không ạ?"
            self.memory.commit_turn(self.user_message, reply, self.ctx)
            return {'chatbot_reply': reply}

        build_context = ""
        preset = get_preset_by_id(self.ctx.build_id)
        if preset:
            build_context = preset.get("reply", "")
        elif self.build_df is not None and not self.build_df.empty:
            rows = self.build_df[self.build_df['BuildID'].str.upper() == self.ctx.build_id.upper()]
            if not rows.empty:
                matched_build = rows.iloc[0].to_dict()
                build_context = format_build_context(matched_build)
                
        if not build_context:
            reply = "Dạ, em không tìm thấy thông tin chi tiết về bộ PC gần nhất. Bạn có thể nhắc lại yêu cầu được không ạ?"
            self.memory.commit_turn(self.user_message, reply, self.ctx)
            return {'chatbot_reply': reply}

        system_prompt = (
            "Bạn là chuyên gia tư vấn linh kiện máy tính tại cửa hàng. Dưới đây là thông số bộ PC mà bạn vừa gợi ý cho khách:\n\n"
            f"<build_context>\n{build_context}\n</build_context>\n\n"
            "Hãy trả lời câu hỏi của khách hàng về bộ PC này một cách thật ngắn gọn, chính xác, súc tích và thân thiện. Không được tự bịa ra thông số không có trong bộ PC.\n"
            "[QUY TẮC BẮT BUỘC]\n"
            "1. TUYỆT ĐỐI KHÔNG in lại 'Mã bộ' trong câu trả lời.\n"
            "2. Bắt đầu câu trả lời trực tiếp vào vấn đề.\n"
            "3. Bỏ qua các ký hiệu kỹ thuật nội bộ (như = 120 B). Chỉ dùng giá trị gốc (120W)."
        )
        fallback = "Dạ bộ PC này rất ngon trong tầm giá ạ! Bạn có muốn lấy bộ này luôn không?"
        
        reply = self._invoke_llm_for_build(system_prompt, fallback)
        self.memory.commit_turn(self.user_message, reply, self.ctx)
        return {'chatbot_reply': reply}

    def _handle_explicit_build(self, explicit_build_id: str) -> dict:
        if self.build_df is not None and not self.build_df.empty:
            rows = self.build_df[self.build_df['BuildID'].str.upper() == explicit_build_id.upper()]
        else:
            rows = None

        if rows is not None and not rows.empty:
            matched_build = rows.iloc[0].to_dict()
            return self._answer_about_specific_build(matched_build)
        
        reply = (
            f"Dạ, em không tìm thấy bộ PC nào có mã **{explicit_build_id}** "
            "trong hệ thống ạ. Bạn kiểm tra lại mã giúp em nhé!"
        )
        self.memory.commit_turn(self.user_message, reply, self.ctx)
        return {'chatbot_reply': reply}

    def _answer_about_specific_build(self, build: dict) -> dict:
        build_context = format_build_context(build)

        system_prompt = (
            "Bạn là chuyên gia tư vấn linh kiện máy tính tại cửa hàng. Dưới đây là thông số của bộ PC mà khách đang hỏi tới:\n\n"
            f"{build_context}\n\n"
            "Hãy trả lời câu hỏi của khách hàng về bộ PC này thật ngắn gọn, chính xác, súc tích và thân thiện, dựa hoàn toàn vào thông số trên. Không được tự bịa ra thông số không có trong bộ PC.\n"
            "[QUY TẮC BẮT BUỘC]\n"
            "1. TUYỆT ĐỐI KHÔNG in lại 'Mã bộ' trong câu trả lời.\n"
            "2. Bắt đầu câu trả lời trực tiếp vào vấn đề."
        )
        fallback = build_context + "\n\nBạn có muốn em tư vấn thêm về bộ PC này không ạ?"

        reply = self._invoke_llm_for_build(system_prompt, fallback)
        self.memory.commit_turn(self.user_message, reply, self.ctx)
        return {'chatbot_reply': reply}


def handle_pc_build_flow(
    user_uid: str,
    session_id: str,
    user_message: str,
    user_message_fixed: str,
    msg_lower: str,
    search_query: str,
    chat_history: list,
    build_df,
    is_build_pc: bool,
) -> dict | None:
    engine = PcBuildEngine(
        user_uid, session_id, user_message, user_message_fixed, msg_lower,
        search_query, chat_history, build_df, is_build_pc
    )
    return engine.execute()
