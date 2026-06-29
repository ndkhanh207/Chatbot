import 'package:flutter/material.dart';

class BuildFilters extends StatelessWidget {
  final bool isDesktop;
  final String selectedBrand;
  final double maxBuildPrice;
  final ValueChanged<String> onBrandChanged;
  final ValueChanged<double> onPriceChanged;
  final VoidCallback onClear;

  const BuildFilters({
    super.key,
    required this.isDesktop,
    required this.selectedBrand,
    required this.maxBuildPrice,
    required this.onBrandChanged,
    required this.onPriceChanged,
    required this.onClear,
  });

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    return Container(
      width: isDesktop ? 260 : double.infinity,
      color: const Color(0xFF0D0D12),
      padding: const EdgeInsets.all(16.0),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Bộ lọc', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16)),
                TextButton(
                  onPressed: onClear,
                  child: const Text('Xóa hết', style: TextStyle(fontSize: 12, color: Colors.white54)),
                ),
              ],
            ),
            const Divider(color: Colors.white12),
            const SizedBox(height: 10),
            const Text('Hãng CPU', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white70)),
            const SizedBox(height: 10),
            Row(
              children: [
                _buildBrandFilterButton('AMD', primary),
                const SizedBox(width: 8),
                _buildBrandFilterButton('Intel', primary),
              ],
            ),
            const SizedBox(height: 24),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Ngân sách tối đa', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white70)),
                Text('${(maxBuildPrice / 1000000).toStringAsFixed(0)} Tr', style: TextStyle(color: primary, fontWeight: FontWeight.bold)),
              ],
            ),
            Slider(
              value: maxBuildPrice,
              min: 10000000.0,
              max: 100000000.0,
              activeColor: primary,
              inactiveColor: Colors.white12,
              onChanged: onPriceChanged,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBrandFilterButton(String brand, Color primary) {
    final isSelected = selectedBrand == brand;
    return Expanded(
      child: InkWell(
        onTap: () => onBrandChanged(isSelected ? 'All' : brand),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: isSelected ? primary.withOpacity(0.1) : const Color(0xFF1A1A22),
            border: Border.all(color: isSelected ? primary : Colors.white12, width: 1.5),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Center(
            child: Text(brand, style: TextStyle(fontWeight: FontWeight.bold, color: isSelected ? primary : Colors.white70)),
          ),
        ),
      ),
    );
  }
}
