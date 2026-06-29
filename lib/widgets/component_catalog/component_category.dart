import 'package:flutter/material.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Danh mục hỗ trợ
// ─────────────────────────────────────────────────────────────────────────────
enum ComponentCategory { cpu, gpu, mainboard }

extension ComponentCategoryExt on ComponentCategory {
  String get label {
    switch (this) {
      case ComponentCategory.cpu:       return 'CPU';
      case ComponentCategory.gpu:       return 'GPU';
      case ComponentCategory.mainboard: return 'Mainboard';
    }
  }

  String get apiCategory {
    switch (this) {
      case ComponentCategory.cpu:       return 'CPU';
      case ComponentCategory.gpu:       return 'GPU';
      case ComponentCategory.mainboard: return 'MAINBOARD';
    }
  }

  IconData get icon {
    switch (this) {
      case ComponentCategory.cpu:       return Icons.memory;
      case ComponentCategory.gpu:       return Icons.videogame_asset;
      case ComponentCategory.mainboard: return Icons.developer_board;
    }
  }
}
