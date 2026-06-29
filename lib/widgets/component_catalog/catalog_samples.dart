import '/models/component.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Sample data (xem trước UI khi chưa nối API)
// ─────────────────────────────────────────────────────────────────────────────
const List<PcComponent> catalogSamples = [
  // ── CPU ──────────────────────────────────────────────────────────────────
  PcComponent(id: 'c1', name: 'AMD Ryzen 7 9800X3D', category: 'CPU', manufacturer: 'AMD', price: 10836000, inStock: true, imageUrl: 'assets/images/cpu_1.png', socket: 'AM5', totalCores: 8, boostClockGhz: 5.2),
  PcComponent(id: 'c2', name: 'AMD Ryzen 7 7800X3D', category: 'CPU', manufacturer: 'AMD', price: 8161200, inStock: true, imageUrl: 'assets/images/cpu_2.png', socket: 'AM5', totalCores: 8, boostClockGhz: 5.0),
  PcComponent(id: 'c3', name: 'AMD Ryzen 5 7600X', category: 'CPU', manufacturer: 'AMD', price: 4091760, inStock: true, imageUrl: 'assets/images/cpu_3.png', socket: 'AM5', totalCores: 6, boostClockGhz: 5.3),
  PcComponent(id: 'c4', name: 'AMD Ryzen 5 9600X', category: 'CPU', manufacturer: 'AMD', price: 4919760, inStock: true, imageUrl: 'assets/images/cpu_4.png', socket: 'AM5', totalCores: 6, boostClockGhz: 5.4),
  PcComponent(id: 'c5', name: 'AMD Ryzen 7 7700X', category: 'CPU', manufacturer: 'AMD', price: 5831520, inStock: true, imageUrl: 'assets/images/cpu_5.png', socket: 'AM5', totalCores: 8, boostClockGhz: 5.4),
  PcComponent(id: 'c6', name: 'AMD Ryzen 9 9950X3D', category: 'CPU', manufacturer: 'AMD', price: 15599760, inStock: true, imageUrl: 'assets/images/cpu_6.png', socket: 'AM5', totalCores: 16, boostClockGhz: 5.7),
  PcComponent(id: 'c7', name: 'AMD Ryzen 7 9700X', category: 'CPU', manufacturer: 'AMD', price: 7341360, inStock: true, imageUrl: 'assets/images/cpu_7.png', socket: 'AM5', totalCores: 8, boostClockGhz: 5.5),
  PcComponent(id: 'c8', name: 'Intel Core i7-14700K', category: 'CPU', manufacturer: 'Intel', price: 7132080, inStock: true, imageUrl: 'assets/images/cpu_8.png', socket: 'LGA 1700', totalCores: 20, boostClockGhz: 5.6),
  PcComponent(id: 'c9', name: 'Intel Core i9-14900K', category: 'CPU', manufacturer: 'Intel', price: 10536000, inStock: true, imageUrl: 'assets/images/cpu_9.png', socket: 'LGA 1700', totalCores: 24, boostClockGhz: 6.0),
  PcComponent(id: 'c10', name: 'AMD Ryzen 5 7600', category: 'CPU', manufacturer: 'AMD', price: 4727280, inStock: true, imageUrl: 'assets/images/cpu_10.png', socket: 'AM5', totalCores: 6, boostClockGhz: 5.1),
  PcComponent(id: 'c11', name: 'AMD Ryzen 9 7900X', category: 'CPU', manufacturer: 'AMD', price: 7538640, inStock: true, imageUrl: 'assets/images/cpu_11.png', socket: 'AM5', totalCores: 12, boostClockGhz: 5.6),
  PcComponent(id: 'c12', name: 'AMD Ryzen 9 9900X', category: 'CPU', manufacturer: 'AMD', price: 8616000, inStock: true, imageUrl: 'assets/images/cpu_12.png', socket: 'AM5', totalCores: 12, boostClockGhz: 5.6),
  PcComponent(id: 'c13', name: 'Intel Core i5-14600K', category: 'CPU', manufacturer: 'Intel', price: 4559760, inStock: true, imageUrl: 'assets/images/cpu_13.png', socket: 'LGA 1700', totalCores: 14, boostClockGhz: 5.3),
  PcComponent(id: 'c14', name: 'Intel Core Ultra 7 265K', category: 'CPU', manufacturer: 'Intel', price: 6479760, inStock: true, imageUrl: 'assets/images/cpu_14.png', socket: 'LGA 1851', totalCores: 20, boostClockGhz: 5.5),
  PcComponent(id: 'c15', name: 'AMD Ryzen 9 9950X', category: 'CPU', manufacturer: 'AMD', price: 12811920, inStock: true, imageUrl: 'assets/images/cpu_15.png', socket: 'AM5', totalCores: 16, boostClockGhz: 5.7),

  // ── GPU ──────────────────────────────────────────────────────────────────
  PcComponent(id: 'g1', name: 'MSI GeForce RTX 4080 GAMING TRIO 16GB', category: 'GPU', manufacturer: 'NVIDIA', price: 44399760, inStock: true,  imageUrl: 'assets/images/placeholder_gpu.png', boostClockGhz: 2.51, tdpWatt: 320, vramLabel: '16 GB'),
  PcComponent(id: 'g2', name: 'ASUS ROG Strix RTX 4070 Ti 12GB',       category: 'GPU', manufacturer: 'NVIDIA', price: 26399760, inStock: true,  imageUrl: 'assets/images/placeholder_gpu.png', boostClockGhz: 2.61, tdpWatt: 285, vramLabel: '12 GB'),
  PcComponent(id: 'g3', name: 'Sapphire NITRO+ RX 9070 XT 16GB',       category: 'GPU', manufacturer: 'AMD',   price: 17999760, inStock: true,  imageUrl: 'assets/images/placeholder_gpu.png', boostClockGhz: 3.06, tdpWatt: 330, vramLabel: '16 GB'),
  PcComponent(id: 'g4', name: 'MSI GeForce RTX 5060 Ti 16GB GAMING',   category: 'GPU', manufacturer: 'NVIDIA', price: 11519760, inStock: true,  imageUrl: 'assets/images/placeholder_gpu.png', boostClockGhz: 2.57, tdpWatt: 180, vramLabel: '16 GB'),
  PcComponent(id: 'g5', name: 'Gigabyte RTX 4060 WINDFORCE OC 8GB',    category: 'GPU', manufacturer: 'NVIDIA', price: 10799760, inStock: false, imageUrl: 'assets/images/placeholder_gpu.png', boostClockGhz: 2.49, tdpWatt: 115, vramLabel: '8 GB'),

  // ── MAINBOARD ─────────────────────────────────────────────────────────────
  PcComponent(id: 'm1', name: 'MSI B850 PRO B850M-VC WIFI6E AM5 DDR5', category: 'MAINBOARD', manufacturer: 'MSI',     price: 4992114,  inStock: true,  imageUrl: 'assets/images/placeholder_mainboard.png', socket: 'AM5',      chipset: 'B850', formFactor: 'Micro ATX'),
  PcComponent(id: 'm2', name: 'Gigabyte Z890 AORUS ELITE WIFI7 DDR5',  category: 'MAINBOARD', manufacturer: 'Gigabyte', price: 5928942,  inStock: true,  imageUrl: 'assets/images/placeholder_mainboard.png', socket: 'LGA 1851', chipset: 'Z890', formFactor: 'ATX'),
  PcComponent(id: 'm3', name: 'ASUS TUF GAMING B760M-PLUS WIFI II',    category: 'MAINBOARD', manufacturer: 'ASUS',     price: 6949021,  inStock: true,  imageUrl: 'assets/images/placeholder_mainboard.png', socket: 'LGA 1700', chipset: 'B760', formFactor: 'Micro ATX'),
  PcComponent(id: 'm4', name: 'ASRock X670E Taichi Carrara AM5 DDR5',  category: 'MAINBOARD', manufacturer: 'ASRock',   price: 21075737, inStock: false, imageUrl: 'assets/images/placeholder_mainboard.png', socket: 'AM5',      chipset: 'X670', formFactor: 'EATX'),
  PcComponent(id: 'm5', name: 'MSI MAG Z790 TOMAHAWK WIFI DDR5',       category: 'MAINBOARD', manufacturer: 'MSI',      price: 6322537,  inStock: true,  imageUrl: 'assets/images/placeholder_mainboard.png', socket: 'LGA 1851', chipset: 'Z790', formFactor: 'ATX'),
];
