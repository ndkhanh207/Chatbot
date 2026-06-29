/// Model cho một linh kiện PC đơn lẻ (CPU, GPU, Mainboard).
/// Mỗi category dùng một tập field khác nhau — field không dùng để null.
class PcComponent {
  final String id;
  final String name;
  final String category;       // 'CPU' | 'GPU' | 'MAINBOARD'
  final String manufacturer;   // AMD | Intel | NVIDIA | ASUS | MSI | Gigabyte...
  final double price;
  final bool inStock;
  final String imageUrl;

  // ── CPU / Mainboard ───────────────────────────────────────────────────────
  final String? socket;        // AM5 | LGA 1700 | LGA 1851 ...

  // ── CPU ───────────────────────────────────────────────────────────────────
  final int?    totalCores;
  final double? boostClockGhz;

  // ── GPU ───────────────────────────────────────────────────────────────────
  final String? vramLabel;     // '8 GB' | '16 GB' ...  (dạng hiển thị)
  final int?    tdpWatt;       // TDP (W)

  // ── Mainboard ─────────────────────────────────────────────────────────────
  final String? chipset;       // B850 | Z890 | B760 ...
  final String? formFactor;    // ATX | Micro ATX | Mini-ITX | EATX

  const PcComponent({
    required this.id,
    required this.name,
    required this.category,
    required this.manufacturer,
    required this.price,
    required this.inStock,
    this.imageUrl    = '',
    this.socket,
    this.totalCores,
    this.boostClockGhz,
    this.vramLabel,
    this.tdpWatt,
    this.chipset,
    this.formFactor,
  });

  // ── JSON → Object ─────────────────────────────────────────────────────────
  // Backend (FastAPI hybrid_search) trả về các field tiếng Việt:
  // 'tên', 'giá', 'category', 'socket', 'chipset', 'bộ nhớ', 'tdp', ...
  factory PcComponent.fromJson(Map<String, dynamic> json) {
    final cat = (json['category'] ?? '').toString().toUpperCase();

    // Giá — backend lưu là 'giá' (int VNĐ)
    final rawPrice = json['giá'] ?? json['price'] ?? json['Price'] ?? 0;
    final price    = double.tryParse(rawPrice.toString()) ?? 0.0;

    // VRAM — backend lưu là 'bộ nhớ' (số GB)
    final rawVram  = json['bộ nhớ'] ?? json['vram_gb'] ?? json['memory'];
    final vramGb   = rawVram != null
        ? double.tryParse(rawVram.toString())
        : null;
    final vramLabel = vramGb != null ? '${vramGb.toInt()} GB' : null;

    // TDP — backend lưu là 'tdp' (số W)
    final rawTdp = json['tdp'] ?? json['TDP'];
    final tdp    = rawTdp != null ? int.tryParse(rawTdp.toString()) : null;

    // Boost clock — backend lưu là 'xung boost' (MHz cho GPU, GHz cho CPU)
    final rawBoost = json['xung boost'] ?? json['boost_clock'];
    double? boostGhz;
    if (rawBoost != null) {
      final v = double.tryParse(rawBoost.toString()) ?? 0;
      // GPU: giá trị > 100 → đơn vị MHz → đổi sang GHz
      boostGhz = (cat == 'GPU' && v > 100) ? v / 1000 : v;
    }

    // Chipset — lấy từ tên mainboard nếu không có field riêng
    String? chipset = json['chipset']?.toString();
    if (chipset == null && cat == 'MAINBOARD') {
      final name = (json['tên'] ?? json['name'] ?? '').toString();
      for (final ch in ['B850', 'X870', 'Z890', 'B760', 'Z790', 'X670', 'B650', 'A520', 'B550', 'X570']) {
        if (name.toUpperCase().contains(ch)) { chipset = ch; break; }
      }
    }

    // Form factor — từ field 'kích thước'
    final rawSize  = json['kích thước'] ?? json['form_factor'];
    final formFact = rawSize?.toString();

    return PcComponent(
      id           : json['id']?.toString() ?? '',
      name         : json['tên'] ?? json['name'] ?? 'Không rõ tên',
      category     : cat,
      manufacturer  : _extractManufacturer(json['tên'] ?? json['name'] ?? ''),
      price        : price,
      inStock      : json['in_stock'] ?? true,
      imageUrl     : json['image_url'] ?? '',
      socket       : json['socket']?.toString(),
      totalCores   : int.tryParse((json['số lõi'] ?? json['total_cores'] ?? '').toString()),
      boostClockGhz: boostGhz,
      vramLabel    : vramLabel,
      tdpWatt      : tdp,
      chipset      : chipset,
      formFactor   : formFact,
    );
  }

  // ── Object → JSON ─────────────────────────────────────────────────────────
  Map<String, dynamic> toJson() => {
    'id'          : id,
    'name'        : name,
    'category'    : category,
    'manufacturer': manufacturer,
    'price'       : price,
    'in_stock'    : inStock,
    'image_url'   : imageUrl,
    'socket'      : socket,
    'total_cores' : totalCores,
    'boost_clock' : boostClockGhz,
    'vram_label'  : vramLabel,
    'tdp'         : tdpWatt,
    'chipset'     : chipset,
    'form_factor' : formFactor,
  };

  // ── Helper: đoán hãng từ tên sản phẩm ─────────────────────────────────────
  static String _extractManufacturer(String name) {
    final n = name.toUpperCase();
    if (n.contains('AMD') || n.contains('RYZEN') || n.contains('RADEON') ||
        n.contains('EPYC') || n.contains('THREADRIPPER'))          return 'AMD';
    if (n.contains('INTEL') || n.contains('CORE I') ||
        n.contains('XEON') || n.contains('PENTIUM') ||
        n.contains('CELERON') || n.contains('ARC'))               return 'Intel';
    if (n.contains('NVIDIA') || n.contains('GEFORCE') ||
        n.contains('RTX') || n.contains('GTX') || n.contains('GT ')) return 'NVIDIA';
    if (n.startsWith('ASUS') || n.startsWith('ROG') || n.startsWith('TUF')) return 'ASUS';
    if (n.startsWith('MSI'))                                       return 'MSI';
    if (n.startsWith('GIGABYTE') || n.startsWith('AORUS'))        return 'Gigabyte';
    if (n.startsWith('ASROCK'))                                    return 'ASRock';
    if (n.startsWith('SAPPHIRE'))                                  return 'Sapphire';
    if (n.startsWith('POWERCOLOR'))                                return 'PowerColor';
    if (n.startsWith('XFX'))                                       return 'XFX';
    return 'Other';
  }
}