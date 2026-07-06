# app/pc_builder/multi_turn.py

def apply_build_adjustment(adjustment: dict, last_build: dict, budget: int | None, component_filter: dict, brand_filter: dict) -> tuple[int | None, dict, dict]:
    """
    Áp dụng các điều chỉnh từ multi-turn vào filter và budget.
    Returns: (new_budget, new_component_filter, new_brand_filter)
    """
    adj_type = adjustment.get('type')
    new_budget = budget
    skip_inherit = set()

    # 1. Budget Processing
    if adj_type == 'budget_change':
        skip_inherit.update(['cpu', 'gpu', 'mainboard'])
        
    if adjustment.get('new_budget'):
        if last_build.get('total_price') and abs(adjustment['new_budget']) < 50_000_000:
            val = adjustment['new_budget']
            if abs(val) < 10_000_000 and last_build.get('total_price'): 
                new_budget = last_build['total_price'] + val
            else:
                new_budget = abs(val)
        else:
            new_budget = adjustment['new_budget']

    # 2. Swap Component Processing
    if adjustment.get('swap'):
        swap = adjustment['swap']
        if swap.get('target_cpu'):
            component_filter['cpu_model'] = swap.get('cpu_model')
            component_filter['category'] = 'cpu'
            skip_inherit.add('cpu')
            # Swapping CPU means old mainboard is likely incompatible (different socket/platform)
            skip_inherit.add('mainboard')
        if swap.get('target_gpu'):
            component_filter['gpu_model'] = swap.get('gpu_model')
            component_filter['category'] = 'gpu'
            skip_inherit.add('gpu')
        if swap.get('target_main'):
            component_filter['mainboard'] = swap.get('mainboard_model')
            component_filter['category'] = 'mainboard'
            skip_inherit.add('mainboard')

    # 3. Lock Component Processing
    if adjustment.get('lock'):
        lock = adjustment['lock']
        if lock.get('cpu') and last_build.get('cpu_model'):
            component_filter['cpu_model'] = last_build['cpu_model']
            skip_inherit.add('cpu')
        if lock.get('gpu') and last_build.get('gpu_model'):
            component_filter['gpu_model'] = last_build['gpu_model']
            skip_inherit.add('gpu')
        if lock.get('mainboard') and last_build.get('mainboard_model'):
            component_filter['mainboard'] = last_build['mainboard_model']
            skip_inherit.add('mainboard')

    # 4. Brand Switch Processing
    if adj_type == 'brand_switch' and adjustment.get('brand'):
        brand = adjustment['brand']
        if brand in ['Intel', 'AMD']:
            brand_filter['cpu_brand'] = brand
            skip_inherit.add('cpu')
            skip_inherit.add('mainboard')  # Đổi hãng CPU thì mainboard cũ không còn phù hợp
        elif brand == 'NVIDIA':
            brand_filter['gpu_brand'] = brand
            skip_inherit.add('gpu')

    # 5. Priority Change
    if adj_type == 'priority_change':
        component_filter['category'] = None

    # No implicit inheritance unless explicitly locked by user

    return new_budget, component_filter, brand_filter
