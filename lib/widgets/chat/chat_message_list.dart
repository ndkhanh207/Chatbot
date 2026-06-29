import 'package:flutter/material.dart';
import '../../models/pc_build.dart';

class ChatMessageList extends StatelessWidget {
  final List<Map<String, dynamic>> messages;
  final bool isLoading;
  final Color primary;
  final ScrollController scrollController;

  const ChatMessageList({
    super.key,
    required this.messages,
    required this.isLoading,
    required this.primary,
    required this.scrollController,
  });

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      controller: scrollController,
      padding: const EdgeInsets.all(12),
      itemCount: messages.length + (isLoading ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == messages.length && isLoading) {
          return Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: const EdgeInsets.all(8.0),
              child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: primary)),
            ),
          );
        }
        final msg = messages[index];
        final isUser = msg['isUser'] == true;
        return Column(
          crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            Container(
              margin: const EdgeInsets.symmetric(vertical: 4),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.65),
              decoration: BoxDecoration(
                color: isUser ? primary : Colors.grey.shade100,
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(14),
                  topRight: const Radius.circular(14),
                  bottomLeft: Radius.circular(isUser ? 14 : 3),
                  bottomRight: Radius.circular(isUser ? 3 : 14),
                ),
              ),
              child: Text(msg['text'], style: TextStyle(color: isUser ? Colors.white : Colors.black87, fontSize: 13, height: 1.3)),
            ),
            if (msg['hasCard'] == true && msg['buildData'] != null)
              _ChatBuildCard(pcBuild: msg['buildData'] as PcBuild, primary: primary),
          ],
        );
      },
    );
  }
}

class _ChatBuildCard extends StatelessWidget {
  final PcBuild pcBuild;
  final Color primary;

  const _ChatBuildCard({required this.pcBuild, required this.primary});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(12),
      width: double.infinity,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: primary.withOpacity(0.4), width: 1.2),
        boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.08), blurRadius: 6, offset: const Offset(0, 3))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(pcBuild.buildId, style: TextStyle(color: primary, fontSize: 11, fontWeight: FontWeight.bold)),
              Icon(Icons.computer, color: primary, size: 16),
            ],
          ),
          Divider(color: Colors.grey.shade200, height: 12),
          _DetailRow(label: 'Vi xử lý', value: pcBuild.cpuModel),
          _DetailRow(label: 'Bo mạch chủ', value: pcBuild.motherboardModel),
          _DetailRow(label: 'Card đồ họa', value: pcBuild.gpuModel),
          _DetailRow(label: 'Lắp ráp & test', value: '${(pcBuild.assemblyFee / 1000).toStringAsFixed(0)}K đ'),
          Divider(color: Colors.grey.shade200, height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Tổng cộng:', style: TextStyle(color: Colors.black, fontWeight: FontWeight.bold, fontSize: 12)),
              Text(
                '${pcBuild.totalPrice.toString().replaceAllMapped(RegExp(r'(\d)(?=(\d{3})+(?!\d))'), (m) => '${m[1]}.')}đ',
                style: const TextStyle(color: Color(0xFF1B9E5A), fontWeight: FontWeight.bold, fontSize: 15),
              ),
            ],
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            height: 32,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF2B2B33),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                padding: EdgeInsets.zero,
              ),
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Đã thêm cấu hình ${pcBuild.buildId} vào giỏ hàng!')));
              },
              child: const Text('ÁP DỤNG CẤU HÌNH', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
            ),
          ),
        ],
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  final String label;
  final String value;

  const _DetailRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$label: ', style: const TextStyle(color: Colors.black54, fontSize: 11)),
          Expanded(child: Text(value, style: const TextStyle(color: Colors.black87, fontSize: 11, fontWeight: FontWeight.bold), maxLines: 1, overflow: TextOverflow.ellipsis)),
        ],
      ),
    );
  }
}
