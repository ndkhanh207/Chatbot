import 'package:flutter/material.dart';
import '/models/component.dart';
import 'component_category.dart';

// ─────────────────────────────────────────────────────────────────────────────
// ProductCard — card sản phẩm, hiển thị spec theo category
// ─────────────────────────────────────────────────────────────────────────────
class ProductCard extends StatelessWidget {
  final PcComponent component;
  final ComponentCategory category;
  final String Function(num) formatVnd;

  const ProductCard({
    super.key,
    required this.component,
    required this.category,
    required this.formatVnd,
  });

  Color get _accentColor {
    switch (component.manufacturer.toUpperCase()) {
      case 'AMD':    return Colors.deepOrange;
      case 'NVIDIA': return Colors.green;
      case 'INTEL':  return Colors.blueAccent;
      default:       return Colors.grey;
    }
  }

  IconData get _categoryIcon {
    switch (category) {
      case ComponentCategory.cpu:       return Icons.memory;
      case ComponentCategory.gpu:       return Icons.videogame_asset;
      case ComponentCategory.mainboard: return Icons.developer_board;
    }
  }

  @override
  Widget build(BuildContext context) {
    final c       = component;
    final primary = Theme.of(context).colorScheme.primary;

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: primary.withOpacity(0.08), width: 1),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.15), blurRadius: 8, offset: const Offset(0, 4))],
      ),
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Ảnh / placeholder
          AspectRatio(
            aspectRatio: 1.3,
            child: Container(
              decoration: BoxDecoration(
                  color: const Color(0xFFF2F2F5), borderRadius: BorderRadius.circular(8)),
              child: c.imageUrl.isNotEmpty
                  ? ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: c.imageUrl.startsWith('assets/')
                          ? Image.asset(c.imageUrl, fit: BoxFit.contain,
                              errorBuilder: (_, __, ___) =>
                                  Icon(_categoryIcon, size: 40, color: _accentColor))
                          : Image.network(c.imageUrl, fit: BoxFit.contain,
                              errorBuilder: (_, __, ___) =>
                                  Icon(_categoryIcon, size: 40, color: _accentColor)),
                    )
                  : Center(child: Icon(_categoryIcon, size: 40, color: _accentColor)),
            ),
          ),
          const SizedBox(height: 8),

          // Tên
          Text(c.name, maxLines: 2, overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.black, fontWeight: FontWeight.bold, fontSize: 12)),
          const SizedBox(height: 4),

          // Giá
          Text(formatVnd(c.price),
              style: const TextStyle(color: Color(0xFF1B9E5A), fontWeight: FontWeight.bold, fontSize: 13)),
          const SizedBox(height: 6),

          // Spec lines theo category
          ..._buildSpecs(c),

          const Spacer(),

          // Button
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: c.inStock ? () {} : null,
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF2B2B33),
                foregroundColor: Colors.white,
                disabledBackgroundColor: Colors.grey.shade300,
                padding: const EdgeInsets.symmetric(vertical: 8),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              icon: Icon(c.inStock ? Icons.add : Icons.remove_shopping_cart, size: 14),
              label: Text(c.inStock ? 'Add to build' : 'Hết hàng',
                  style: const TextStyle(fontSize: 11)),
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _buildSpecs(PcComponent c) {
    final specs = <MapEntry<String, String>>[];

    switch (category) {
      case ComponentCategory.cpu:
        if (c.socket        != null) specs.add(MapEntry('Socket',      c.socket!));
        if (c.totalCores    != null) specs.add(MapEntry('Cores',       '${c.totalCores}'));
        if (c.boostClockGhz != null) specs.add(MapEntry('Boost',       '${c.boostClockGhz} GHz'));
        break;

      case ComponentCategory.gpu:
        if (c.vramLabel     != null) specs.add(MapEntry('VRAM',        c.vramLabel!));
        if (c.boostClockGhz != null) specs.add(MapEntry('Boost',       '${c.boostClockGhz} GHz'));
        if (c.tdpWatt       != null) specs.add(MapEntry('TDP',         '${c.tdpWatt} W'));
        break;

      case ComponentCategory.mainboard:
        if (c.socket        != null) specs.add(MapEntry('Socket',      c.socket!));
        if (c.chipset       != null) specs.add(MapEntry('Chipset',     c.chipset!));
        if (c.formFactor    != null) specs.add(MapEntry('Form factor', c.formFactor!));
        break;
    }

    return specs
        .map((e) => SpecLine(label: e.key, value: e.value))
        .toList();
  }
}

class SpecLine extends StatelessWidget {
  final String label;
  final String value;
  const SpecLine({super.key, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: Colors.black54, fontSize: 10)),
          Text(value, style: const TextStyle(color: Colors.black87, fontSize: 10, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
