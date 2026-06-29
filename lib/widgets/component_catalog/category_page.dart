import 'package:flutter/material.dart';
import '/models/component.dart';
import 'component_category.dart';
import 'product_card.dart';

// ─────────────────────────────────────────────────────────────────────────────
// CategoryPage — màn hình lọc + grid cho 1 category
// ─────────────────────────────────────────────────────────────────────────────
class CategoryPage extends StatefulWidget {
  final ComponentCategory category;
  final List<PcComponent> components;

  const CategoryPage({super.key, required this.category, required this.components});

  @override
  State<CategoryPage> createState() => _CategoryPageState();
}

class _CategoryPageState extends State<CategoryPage> {
  bool _inStockOnly = false;
  RangeValues _priceRange = const RangeValues(0, 100000000);
  final Set<String> _selectedManufacturers = {};
  final Set<String> _selectedSockets       = {};   // CPU / Mainboard
  final Set<String> _selectedVram          = {};   // GPU
  final Set<String> _selectedChipsets      = {};   // Mainboard
  final TextEditingController _searchCtrl  = TextEditingController();
  String _sortOption = 'Mặc định';

  static const double _minPrice = 0;
  static const double _maxPrice = 100000000;

  // ── Filter options per category ─────────────────────────────────────────
  static const _cpuSockets    = ['AM5', 'AM4', 'LGA 1700', 'LGA 1851', 'LGA 1200', 'LGA 1151', 'LGA 1150', 'sTR5'];
  static const _mainSockets   = ['AM5', 'AM4', 'LGA 1700', 'LGA 1851', 'LGA 1200', 'LGA 1151'];
  static const _mainChipsets  = ['B850', 'X870', 'Z890', 'B760', 'Z790', 'X670', 'B650', 'A520', 'B550'];
  static const _gpuVram       = ['4 GB', '6 GB', '8 GB', '10 GB', '12 GB', '16 GB', '24 GB', '32 GB'];
  static const _gpuManufacturers = ['NVIDIA', 'AMD', 'Intel'];

  String _formatVnd(num value) {
    final str = value.round().toString();
    final buf = StringBuffer();
    for (int i = 0; i < str.length; i++) {
      if (i != 0 && (str.length - i) % 3 == 0) buf.write('.');
      buf.write(str[i]);
    }
    return '${buf.toString()}đ';
  }

  List<PcComponent> get _filtered {
    var list = widget.components;
    final kw = _searchCtrl.text.toLowerCase();

    list = list.where((c) {
      if (_inStockOnly && !c.inStock)                           return false;
      if (c.price < _priceRange.start || c.price > _priceRange.end) return false;
      if (_selectedManufacturers.isNotEmpty &&
          !_selectedManufacturers.contains(c.manufacturer))    return false;

      // CPU / Mainboard — socket filter
      if (_selectedSockets.isNotEmpty) {
        if (c.socket == null || !_selectedSockets.contains(c.socket)) return false;
      }

      // Mainboard — chipset filter
      if (_selectedChipsets.isNotEmpty) {
        final chipset = c.chipset ?? '';
        if (!_selectedChipsets.any((ch) => chipset.contains(ch)))     return false;
      }

      // GPU — VRAM filter
      if (_selectedVram.isNotEmpty) {
        final vram = c.vramLabel ?? '';
        if (!_selectedVram.contains(vram))                            return false;
      }

      if (kw.isNotEmpty && !c.name.toLowerCase().contains(kw))       return false;
      return true;
    }).toList();

    switch (_sortOption) {
      case 'Giá tăng dần': list.sort((a, b) => a.price.compareTo(b.price));  break;
      case 'Giá giảm dần': list.sort((a, b) => b.price.compareTo(a.price));  break;
      case 'Tên A-Z':      list.sort((a, b) => a.name.compareTo(b.name));    break;
    }
    return list;
  }

  StateSetter? _modalSetState;

  void _updateState(VoidCallback fn) {
    setState(fn);
    _modalSetState?.call(() {});
  }

  void _resetFilters() => _updateState(() {
    _inStockOnly = false;
    _priceRange  = const RangeValues(_minPrice, _maxPrice);
    _selectedManufacturers.clear();
    _selectedSockets.clear();
    _selectedVram.clear();
    _selectedChipsets.clear();
  });

  void _showMobileFilters() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) {
        return SafeArea(
          child: Container(
            height: MediaQuery.of(context).size.height * 0.9,
            decoration: const BoxDecoration(
              color: Color(0xFF0D0D12),
              borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
            ),
            child: StatefulBuilder(
              builder: (ctx, setModalState) {
                _modalSetState = setModalState;
                return Column(
                  children: [
                    Container(
                      margin: const EdgeInsets.only(top: 16),
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(color: Colors.white24, borderRadius: BorderRadius.circular(2)),
                    ),
                    Expanded(
                      child: _buildSidebar(false),
                    ),
                    Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: SizedBox(
                        width: double.infinity,
                        height: 48,
                        child: ElevatedButton(
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Theme.of(context).colorScheme.primary,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                          ),
                          onPressed: () => Navigator.pop(context),
                          child: const Text('Xem kết quả', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        );
      },
    ).whenComplete(() {
      _modalSetState = null;
    });
  }

  // ── Build ────────────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    final sw        = MediaQuery.of(context).size.width;
    final isDesktop = sw > 900;
    final filtered  = _filtered;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (isDesktop) _buildSidebar(true),
        Expanded(child: _buildContent(filtered, isDesktop)),
      ],
    );
  }

  // ── Sidebar ──────────────────────────────────────────────────────────────
  Widget _buildSidebar(bool isDesktop) {
    final primary = Theme.of(context).colorScheme.primary;
    final cat     = widget.category;

    return Container(
      width: isDesktop ? 260 : double.infinity,
      color: const Color(0xFF0D0D12),
      padding: const EdgeInsets.all(16),
      child: ListView(
        primary: false,
        children: [
          // Header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Filters', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16)),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextButton(
                    onPressed: _resetFilters,
                    child: const Text('Reset', style: TextStyle(color: Colors.white54, fontSize: 12)),
                  ),
                  if (!isDesktop)
                    IconButton(
                      icon: const Icon(Icons.close, color: Colors.white54),
                      onPressed: () => Navigator.pop(context),
                    ),
                ],
              ),
            ],
          ),
          const Divider(color: Colors.white12),
          const SizedBox(height: 8),

          // In Stock toggle
          InkWell(
            onTap: () => _updateState(() => _inStockOnly = !_inStockOnly),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: _inStockOnly ? primary.withOpacity(0.15) : Colors.transparent,
                border: Border.all(color: _inStockOnly ? primary : Colors.white24),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.check, size: 14, color: _inStockOnly ? primary : Colors.white38),
                  const SizedBox(width: 6),
                  Text('In Stock', style: TextStyle(color: _inStockOnly ? primary : Colors.white70, fontSize: 12)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),

          // Price slider
          const Text('Giá', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          RangeSlider(
            values: _priceRange,
            min: _minPrice, max: _maxPrice,
            activeColor: primary, inactiveColor: Colors.white12,
            onChanged: (v) => _updateState(() => _priceRange = v),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(_formatVnd(_priceRange.start), style: const TextStyle(color: Colors.white70, fontSize: 11)),
              Text(_formatVnd(_priceRange.end),   style: const TextStyle(color: Colors.white70, fontSize: 11)),
            ],
          ),
          const SizedBox(height: 20),

          // Manufacturer
          const Text('Hãng sản xuất', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          const SizedBox(height: 10),
          if (cat == ComponentCategory.gpu)
            Wrap(
              spacing: 8, runSpacing: 8,
              children: _gpuManufacturers.map(_buildManufacturerChip).toList(),
            )
          else
            Row(children: [
              _buildManufacturerChip('AMD'),
              const SizedBox(width: 8),
              _buildManufacturerChip('Intel'),
            ]),
          const SizedBox(height: 20),

          // CPU / Mainboard → Socket
          if (cat == ComponentCategory.cpu || cat == ComponentCategory.mainboard) ...[
            const Text('Socket', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            ...(cat == ComponentCategory.cpu ? _cpuSockets : _mainSockets)
                .map(_buildSocketCheckbox),
            const SizedBox(height: 20),
          ],

          // Mainboard → Chipset
          if (cat == ComponentCategory.mainboard) ...[
            const Text('Chipset', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            ..._mainChipsets.map(_buildChipsetCheckbox),
            const SizedBox(height: 20),
          ],

          // GPU → VRAM
          if (cat == ComponentCategory.gpu) ...[
            const Text('VRAM', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            ..._gpuVram.map(_buildVramCheckbox),
          ],
        ],
      ),
    );
  }

  Widget _buildManufacturerChip(String brand) {
    final isSelected = _selectedManufacturers.contains(brand);
    final primary    = Theme.of(context).colorScheme.primary;
    return Expanded(
      child: InkWell(
        onTap: () => _updateState(() => isSelected
            ? _selectedManufacturers.remove(brand)
            : _selectedManufacturers.add(brand)),
        child: Container(
          height: 44,
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: isSelected ? primary : Colors.transparent, width: 2),
          ),
          child: Center(
            child: Text(brand, style: const TextStyle(color: Colors.black, fontWeight: FontWeight.bold, fontSize: 12)),
          ),
        ),
      ),
    );
  }

  Widget _buildSocketCheckbox(String socket) {
    final isChecked = _selectedSockets.contains(socket);
    return CheckboxListTile(
      value: isChecked,
      onChanged: (v) => _updateState(() => v == true
          ? _selectedSockets.add(socket)
          : _selectedSockets.remove(socket)),
      title: Text(socket, style: const TextStyle(color: Colors.white70, fontSize: 13)),
      controlAffinity: ListTileControlAffinity.leading,
      activeColor: Theme.of(context).colorScheme.primary,
      checkColor: Colors.white,
      contentPadding: EdgeInsets.zero,
      dense: true,
    );
  }

  Widget _buildChipsetCheckbox(String chipset) {
    final isChecked = _selectedChipsets.contains(chipset);
    return CheckboxListTile(
      value: isChecked,
      onChanged: (v) => _updateState(() => v == true
          ? _selectedChipsets.add(chipset)
          : _selectedChipsets.remove(chipset)),
      title: Text(chipset, style: const TextStyle(color: Colors.white70, fontSize: 13)),
      controlAffinity: ListTileControlAffinity.leading,
      activeColor: Theme.of(context).colorScheme.primary,
      checkColor: Colors.white,
      contentPadding: EdgeInsets.zero,
      dense: true,
    );
  }

  Widget _buildVramCheckbox(String vram) {
    final isChecked = _selectedVram.contains(vram);
    return CheckboxListTile(
      value: isChecked,
      onChanged: (v) => _updateState(() => v == true
          ? _selectedVram.add(vram)
          : _selectedVram.remove(vram)),
      title: Text(vram, style: const TextStyle(color: Colors.white70, fontSize: 13)),
      controlAffinity: ListTileControlAffinity.leading,
      activeColor: Theme.of(context).colorScheme.primary,
      checkColor: Colors.white,
      contentPadding: EdgeInsets.zero,
      dense: true,
    );
  }

  // ── Content area ─────────────────────────────────────────────────────────
  Widget _buildContent(List<PcComponent> items, bool isDesktop) {
    final total = widget.components.length;
    return CustomScrollView(
      slivers: [
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!isDesktop) ...[
                  _buildSearchField(isDesktop),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(child: _buildSortDropdown(isDesktop)),
                      const SizedBox(width: 8),
                      _buildFilterButton(),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('Tìm thấy ${items.length} sản phẩm phù hợp',
                          style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.bold)),
                    ],
                  ),
                ] else ...[
                  Wrap(
                    spacing: 16, runSpacing: 12,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Hiển thị ${items.length} sản phẩm phù hợp',
                              style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
                          Text('trên tổng $total sản phẩm',
                              style: const TextStyle(color: Colors.white38, fontSize: 12)),
                        ],
                      ),
                      _buildSortDropdown(isDesktop),
                      _buildSearchField(isDesktop),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),
        SliverPadding(
          padding: const EdgeInsets.all(16),
          sliver: items.isEmpty
              ? const SliverToBoxAdapter(
                  child: Center(
                    child: Padding(
                      padding: EdgeInsets.all(32.0),
                      child: Text('Không tìm thấy linh kiện phù hợp.', style: TextStyle(color: Colors.white38)),
                    ),
                  ),
                )
              : SliverGrid.builder(
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: isDesktop ? 5 : 2,
                    crossAxisSpacing: 12,
                    mainAxisSpacing: 16,
                    childAspectRatio: isDesktop ? 0.65 : 0.52,
                  ),
                  itemCount: items.length,
                  itemBuilder: (_, i) => ProductCard(
                    component: items[i],
                    category: widget.category,
                    formatVnd: _formatVnd,
                  ),
                ),
        ),
      ],
    );
  }

  Widget _buildFilterButton() {
    return SizedBox(
      height: 40,
      child: ElevatedButton.icon(
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF1A1A22),
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
        icon: const Icon(Icons.filter_list, size: 18),
        label: const Text('Filters'),
        onPressed: _showMobileFilters,
      ),
    );
  }

  Widget _buildSortDropdown(bool isDesktop) {
    return Container(
      height: 44,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(color: const Color(0xFF1A1A22), borderRadius: BorderRadius.circular(10)),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: _sortOption,
          isExpanded: !isDesktop,
          dropdownColor: const Color(0xFF1A1A22),
          icon: const Icon(Icons.swap_vert, color: Colors.white54, size: 18),
          style: const TextStyle(color: Colors.white, fontSize: 13),
          items: ['Mặc định', 'Giá tăng dần', 'Giá giảm dần', 'Tên A-Z']
              .map((e) => DropdownMenuItem(value: e, child: Text(e)))
              .toList(),
          onChanged: (v) => setState(() => _sortOption = v!),
        ),
      ),
    );
  }

  Widget _buildSearchField(bool isDesktop) {
    return Container(
      width: isDesktop ? 220 : double.infinity,
      height: 48,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(color: const Color(0xFF1A1A22), borderRadius: BorderRadius.circular(10)),
      child: TextField(
        controller: _searchCtrl,
        onChanged: (_) => setState(() {}),
        style: const TextStyle(color: Colors.white, fontSize: 13),
        decoration: const InputDecoration(
          icon: Icon(Icons.search, color: Colors.white54, size: 20),
          hintText: 'Tìm linh kiện...',
          hintStyle: TextStyle(color: Colors.white30, fontSize: 13),
          border: InputBorder.none,
          contentPadding: EdgeInsets.symmetric(vertical: 14),
        ),
      ),
    );
  }
}
