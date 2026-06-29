import 'package:flutter/material.dart';
import '../../models/pc_build.dart';
import '../../data/mock_data.dart';

class BuildList extends StatelessWidget {
  final List<PcBuild>? builds;

  const BuildList({super.key, this.builds});

  String _formatVnd(int value) {
    final str = value.toString();
    final buffer = StringBuffer();
    for (int i = 0; i < str.length; i++) {
      if (i != 0 && (str.length - i) % 3 == 0) buffer.write('.');
      buffer.write(str[i]);
    }
    return '${buffer.toString()}đ';
  }

  @override
  Widget build(BuildContext context) {
    final data = builds ?? mockPcBuilds;
    final primary = Theme.of(context).colorScheme.primary;
    final surface = Theme.of(context).colorScheme.surface;

    if (data.isEmpty) {
      return const SliverToBoxAdapter(
        child: Padding(
          padding: EdgeInsets.all(32.0),
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.search_off_rounded, color: Colors.white24, size: 48),
                SizedBox(height: 12),
                Text('Không tìm thấy cấu hình nào phù hợp.', style: TextStyle(color: Colors.white38, fontSize: 14)),
              ],
            ),
          ),
        ),
      );
    }

    return SliverPadding(
      padding: const EdgeInsets.all(16),
      sliver: SliverList.builder(
        itemCount: data.length,
        itemBuilder: (context, index) {
          final build = data[index];
          return Container(
            margin: const EdgeInsets.only(bottom: 16),
            decoration: BoxDecoration(
              color: surface,
              borderRadius: BorderRadius.circular(16),
              boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.18), blurRadius: 10, offset: const Offset(0, 4))],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
                  child: Row(
                    children: [
                      Icon(Icons.bolt, color: primary, size: 18),
                      const SizedBox(width: 8),
                      Text(build.buildId, style: const TextStyle(color: Colors.black, fontSize: 14, fontWeight: FontWeight.bold)),
                      const Spacer(),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(color: primary.withOpacity(0.12), borderRadius: BorderRadius.circular(8)),
                        child: Text('CẤU HÌNH SẴN', style: TextStyle(color: primary, fontSize: 9, fontWeight: FontWeight.bold)),
                      ),
                    ],
                  ),
                ),
                Divider(color: Colors.grey.shade200, height: 1),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  child: Column(
                    children: [
                      _ComponentRow(icon: Icons.memory, label: 'CPU', model: build.cpuModel, price: _formatVnd(build.cpuPrice), accent: primary),
                      const SizedBox(height: 10),
                      _ComponentRow(icon: Icons.developer_board, label: 'Mainboard', model: build.motherboardModel, price: _formatVnd(build.motherboardPrice), accent: primary),
                      const SizedBox(height: 10),
                      _ComponentRow(icon: Icons.videogame_asset, label: 'VGA', model: build.gpuModel, price: _formatVnd(build.gpuPrice), accent: primary),
                      const SizedBox(height: 10),
                      _ComponentRow(icon: Icons.build_outlined, label: 'Lắp ráp', model: 'Phí lắp ráp & test', price: _formatVnd(build.assemblyFee), accent: primary),
                    ],
                  ),
                ),
                if (build.buildNotes.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                    child: Text(build.buildNotes, style: TextStyle(color: Colors.black.withOpacity(0.55), fontSize: 12, fontStyle: FontStyle.italic)),
                  ),
                Divider(color: Colors.grey.shade200, height: 1),
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Tổng giá', style: TextStyle(color: Colors.black54, fontSize: 11)),
                          Text(_formatVnd(build.totalPrice), style: const TextStyle(color: Color(0xFF1B9E5A), fontSize: 17, fontWeight: FontWeight.bold)),
                        ],
                      ),
                      ElevatedButton.icon(
                        onPressed: () {},
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF2B2B33),
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                        ),
                        icon: const Icon(Icons.shopping_cart_outlined, size: 18),
                        label: const Text('Chọn cấu hình'),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _ComponentRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String model;
  final String price;
  final Color accent;

  const _ComponentRow({required this.icon, required this.label, required this.model, required this.price, required this.accent});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 16, color: Colors.black38),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: TextStyle(color: accent, fontSize: 10, fontWeight: FontWeight.bold)),
              Text(model, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Colors.black87, fontSize: 12)),
            ],
          ),
        ),
        Text(price, style: const TextStyle(color: Colors.black54, fontSize: 12)),
      ],
    );
  }
}
