import 'package:flutter/material.dart';

class ChatHeader extends StatelessWidget {
  final Color primary;
  final bool isDesktop;
  final bool isModal;
  final VoidCallback? onClose;

  const ChatHeader({
    super.key,
    required this.primary,
    required this.isDesktop,
    this.isModal = false,
    this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: Colors.grey.shade200,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(color: primary, shape: BoxShape.circle),
                child: const Icon(Icons.bolt, color: Colors.white, size: 18),
              ),
              const SizedBox(width: 12),
              const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('AI PC Assistant', style: TextStyle(color: Colors.black, fontWeight: FontWeight.bold, fontSize: 14)),
                  Row(
                    children: [
                      Icon(Icons.circle, color: Colors.green, size: 10),
                      SizedBox(width: 4),
                      Text('Trực tuyến', style: TextStyle(color: Colors.green, fontSize: 12)),
                    ],
                  ),
                ],
              ),
            ],
          ),
          if (!isDesktop && onClose != null)
            IconButton(
              icon: const Icon(Icons.close, color: Colors.redAccent, size: 30),
              onPressed: onClose,
              tooltip: 'Đóng',
            ),
        ],
      ),
    );
  }
}
