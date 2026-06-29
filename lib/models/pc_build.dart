/// Model định nghĩa dữ liệu cho một cấu hình PC (đọc từ dữ liệu CSV hoặc API trả về)
class PcBuild {
  final String buildId;
  final String cpuModel;
  final int cpuPrice;
  final String motherboardModel;
  final int motherboardPrice;
  final String gpuModel;
  final int gpuPrice;
  final int assemblyFee;
  final String buildNotes;
  final int totalPrice;

  PcBuild({
    required this.buildId,
    required this.cpuModel,
    required this.cpuPrice,
    required this.motherboardModel,
    required this.motherboardPrice,
    required this.gpuModel,
    required this.gpuPrice,
    required this.assemblyFee,
    required this.buildNotes,
    required this.totalPrice,
  });

  // Chuyển đổi từ JSON nhận từ API backend FastAPI sang Object Flutter
  factory PcBuild.fromJson(Map<String, dynamic> json) {
    return PcBuild(
      buildId: json['BuildID'] ?? json['build_id'] ?? 'BUILD-TEMP',
      cpuModel: json['CPU_Model'] ?? json['cpu_model'] ?? 'Không rõ CPU',
      cpuPrice: json['Component_Price_CPU'] ?? json['cpu_price'] ?? 0,
      motherboardModel: json['Motherboard_Model'] ?? json['motherboard_model'] ?? 'Không rõ Mainboard',
      motherboardPrice: json['Component_Price_Motherboard'] ?? json['motherboard_price'] ?? 0,
      gpuModel: json['GPU_Model'] ?? json['gpu_model'] ?? 'Không rõ GPU',
      gpuPrice: json['Component_Price_GPU'] ?? json['gpu_price'] ?? 0,
      assemblyFee: json['Assembly_Fee'] ?? json['assembly_fee'] ?? 0,
      buildNotes: json['Build_Notes'] ?? json['build_notes'] ?? '',
      totalPrice: json['Total_Price'] ?? json['total_price'] ?? 0,
    );
  }

  // Chuyển đổi Object ngược lại thành bản đồ Map/JSON khi cần gửi dữ liệu đi
  Map<String, dynamic> toJson() {
    return {
      'BuildID': buildId,
      'CPU_Model': cpuModel,
      'Component_Price_CPU': cpuPrice,
      'Motherboard_Model': motherboardModel,
      'Component_Price_Motherboard': motherboardPrice,
      'GPU_Model': gpuModel,
      'Component_Price_GPU': gpuPrice,
      'Assembly_Fee': assemblyFee,
      'Build_Notes': buildNotes,
      'Total_Price': totalPrice,
    };
  }
}