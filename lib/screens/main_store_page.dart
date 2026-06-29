import 'package:flutter/material.dart';
import '../models/pc_build.dart';
import '../widgets/chat/chat_bot_widget.dart';
import '../widgets/component_catalog.dart';
import '../widgets/store/build_list.dart';
import '../widgets/store/build_filters.dart';
import '../data/mock_data.dart';

enum StoreTab { builds, components }

class MainStorePage extends StatefulWidget {
  const MainStorePage({super.key});

  @override
  State<MainStorePage> createState() => _MainStorePageState();
}

class _MainStorePageState extends State<MainStorePage> {
  StoreTab _tab = StoreTab.builds;

  String _selectedBrand = 'All';
  double _maxBuildPrice = 100000000.0;
  final TextEditingController _buildSearchController = TextEditingController();

  StateSetter? _modalSetState;

  void _updateState(VoidCallback fn) {
    setState(fn);
    _modalSetState?.call(() {});
  }

  String _brandOf(PcBuild build) => build.cpuModel.toLowerCase().contains('intel') ? 'Intel' : 'AMD';

  List<PcBuild> get _filteredBuilds {
    final keyword = _buildSearchController.text.toLowerCase();
    return mockPcBuilds.where((b) {
      if (keyword.isNotEmpty &&
          !('${b.buildId} ${b.cpuModel} ${b.motherboardModel} ${b.gpuModel}').toLowerCase().contains(keyword)) {
        return false;
      }
      if (_selectedBrand != 'All' && _brandOf(b) != _selectedBrand) return false;
      if (b.totalPrice > _maxBuildPrice) return false;
      return true;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final isDesktop = screenWidth > 900;
    final primary = Theme.of(context).colorScheme.primary;
    final secondary = Theme.of(context).colorScheme.secondary;

    return DefaultTabController(
      length: 3, // For CPU, GPU, Mainboard
      child: Scaffold(
        backgroundColor: const Color(0xFF0D0D12),
        body: SafeArea(
          bottom: false,
          child: Stack(
            children: [
              NestedScrollView(
                floatHeaderSlivers: true,
                headerSliverBuilder: (context, innerBoxIsScrolled) {
                  return [
                    SliverAppBar(
                      primary: false,
                      floating: true,
                      snap: true,
                  backgroundColor: const Color(0xFF0D0D12),
                  automaticallyImplyLeading: false,
                  title: Row(
                    children: [
                      Icon(Icons.memory_rounded, color: primary),
                      const SizedBox(width: 8),
                      const Text('TECH-GEAR', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1.2, fontSize: 16, color: Colors.white)),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Container(
                          height: 38,
                          constraints: const BoxConstraints(maxWidth: 480),
                          decoration: BoxDecoration(color: const Color(0xFF1A1A22), borderRadius: BorderRadius.circular(8)),
                          padding: const EdgeInsets.symmetric(horizontal: 12),
                          child: const Row(
                            crossAxisAlignment: CrossAxisAlignment.center,
                            children: [
                              Icon(Icons.search, color: Colors.white38, size: 18),
                              SizedBox(width: 8),
                              Expanded(
                                child: TextField(
                                  style: TextStyle(color: Colors.white, fontSize: 13),
                                  decoration: InputDecoration(
                                    hintText: 'Tìm linh kiện, cấu hình...',
                                    hintStyle: TextStyle(color: Colors.white30, fontSize: 13),
                                    border: InputBorder.none,
                                    isDense: true,
                                    contentPadding: EdgeInsets.zero,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                  actions: [
                    Container(
                      margin: const EdgeInsets.only(right: 16),
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                      decoration: BoxDecoration(color: secondary, borderRadius: BorderRadius.circular(6)),
                      child: const Text('PCSTORE PRO', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 11)),
                    ),
                  ],
                    bottom: PreferredSize(
                      preferredSize: const Size.fromHeight(56),
                      child: _buildTabBar(),
                    ),
                  ),
                  if (_tab == StoreTab.components)
                    SliverAppBar(
                      primary: false,
                      pinned: true,
                      automaticallyImplyLeading: false,
                      backgroundColor: const Color(0xFF0D0D12),
                      toolbarHeight: 0,
                      bottom: TabBar(
                        indicatorColor: primary,
                        indicatorWeight: 3,
                        labelColor: primary,
                        unselectedLabelColor: Colors.white38,
                        labelStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                        tabs: const [
                          Tab(child: Row(mainAxisSize: MainAxisSize.min, children: [Icon(Icons.memory, size: 16), SizedBox(width: 6), Text('CPU')])),
                          Tab(child: Row(mainAxisSize: MainAxisSize.min, children: [Icon(Icons.videogame_asset, size: 16), SizedBox(width: 6), Text('GPU')])),
                          Tab(child: Row(mainAxisSize: MainAxisSize.min, children: [Icon(Icons.developer_board, size: 16), SizedBox(width: 6), Text('Mainboard')])),
                        ],
                      ),
                    ),
                ];
              },
              body: _tab == StoreTab.builds
                  ? Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (isDesktop) 
                        BuildFilters(
                          isDesktop: isDesktop,
                          selectedBrand: _selectedBrand,
                          maxBuildPrice: _maxBuildPrice,
                          onBrandChanged: (val) => _updateState(() => _selectedBrand = val),
                          onPriceChanged: (val) => _updateState(() => _maxBuildPrice = val),
                          onClear: () => _updateState(() {
                            _selectedBrand = 'All';
                            _maxBuildPrice = 100000000.0;
                            _buildSearchController.clear();
                          }),
                        ),
                      Expanded(child: _buildBuildContentArea(isDesktop)),
                    ],
                  )
                : const ComponentCatalogPage(),
            ),
            const ChatBotWidget(),
          ],
        ),
      ),
    ),
  );
}

  void _showMobileBuildFilters() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF0D0D12),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.only(top: 16.0),
            child: StatefulBuilder(
              builder: (ctx, setModalState) {
                _modalSetState = setModalState;
                return Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(color: Colors.white24, borderRadius: BorderRadius.circular(2)),
                    ),
                    const SizedBox(height: 16),
                    Flexible(
                      child: SingleChildScrollView(
                        child: BuildFilters(
                          isDesktop: false,
                          selectedBrand: _selectedBrand,
                          maxBuildPrice: _maxBuildPrice,
                          onBrandChanged: (val) => _updateState(() => _selectedBrand = val),
                          onPriceChanged: (val) => _updateState(() => _maxBuildPrice = val),
                          onClear: () => _updateState(() {
                            _selectedBrand = 'All';
                            _maxBuildPrice = 100000000.0;
                            _buildSearchController.clear();
                          }),
                        ),
                      ),
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

  // _buildHeader has been integrated into SliverAppBar

  Widget _buildTabBar() {
    final primary = Theme.of(context).colorScheme.primary;
    return Container(
      color: const Color(0xFF0D0D12),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          _buildTabButton('Cấu hình PC', StoreTab.builds, primary),
          const SizedBox(width: 8),
          _buildTabButton('Linh kiện rời', StoreTab.components, primary),
        ],
      ),
    );
  }

  Widget _buildTabButton(String label, StoreTab tab, Color primary) {
    final isActive = _tab == tab;
    return InkWell(
      onTap: () => setState(() => _tab = tab),
      borderRadius: BorderRadius.circular(6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: isActive ? primary.withOpacity(0.15) : Colors.transparent,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: isActive ? primary : Colors.transparent),
        ),
        child: Text(label, style: TextStyle(color: isActive ? primary : Colors.white60, fontWeight: isActive ? FontWeight.bold : FontWeight.normal, fontSize: 13)),
      ),
    );
  }

  Widget _buildBuildContentArea(bool isDesktop) {
    final builds = _filteredBuilds;
    final primary = Theme.of(context).colorScheme.primary;
    return CustomScrollView(
      slivers: [
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16.0, 16.0, 16.0, 0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  height: 48,
                  decoration: BoxDecoration(color: const Color(0xFF1A1A22), borderRadius: BorderRadius.circular(10)),
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: TextField(
                    controller: _buildSearchController,
                    onChanged: (value) => setState(() {}),
                    style: const TextStyle(color: Colors.white, fontSize: 13),
                    decoration: const InputDecoration(
                      icon: Icon(Icons.search, color: Colors.white54, size: 20),
                      hintText: 'Tìm theo CPU, GPU, mã cấu hình...',
                      hintStyle: TextStyle(color: Colors.white30, fontSize: 13),
                      border: InputBorder.none,
                      contentPadding: EdgeInsets.symmetric(vertical: 12),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Tìm thấy ${builds.length} cấu hình phù hợp', style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.bold)),
                    if (!isDesktop)
                      InkWell(
                        onTap: _showMobileBuildFilters,
                        borderRadius: BorderRadius.circular(8),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          decoration: BoxDecoration(
                            color: primary.withOpacity(0.15),
                            border: Border.all(color: primary),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.filter_list, size: 16, color: primary),
                              const SizedBox(width: 6),
                              Text('Lọc', style: TextStyle(color: primary, fontSize: 13, fontWeight: FontWeight.bold)),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
        BuildList(builds: builds),
      ],
    );
  }
}
