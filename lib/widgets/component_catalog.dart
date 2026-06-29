import 'package:flutter/material.dart';
import '/models/component.dart';
import 'component_catalog/component_category.dart';
import 'component_catalog/category_page.dart';
import 'component_catalog/catalog_data_generated.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Entry point — wrapper giữ TabBar
// ─────────────────────────────────────────────────────────────────────────────
class ComponentCatalogPage extends StatelessWidget {
  /// Truyền null → dùng sample data xem trước UI
  final List<PcComponent>? components;

  const ComponentCatalogPage({super.key, this.components});

  List<PcComponent> _forCategory(ComponentCategory cat) {
    final all = components ?? generatedCatalog;
    return all.where((c) => c.category == cat.apiCategory).toList();
  }

  @override
  Widget build(BuildContext context) {
    return TabBarView(
      children: ComponentCategory.values.map((cat) {
        return CategoryPage(
          category: cat,
          components: _forCategory(cat),
        );
      }).toList(),
    );
  }
}