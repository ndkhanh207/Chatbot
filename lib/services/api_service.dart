import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/pc_build.dart';

class ApiService {
  // Thay thế bằng địa chỉ IP máy chủ FastAPI của bạn (Dùng 10.0.2.2 cho Android Emulator)
  static const String baseUrl = 'http://192.168.1.45:8000';

  /// Gửi câu hỏi của người dùng tới Backend FastAPI Chatbot và nhận phản hồi
  static Future<Map<String, dynamic>> sendMessageToChatbot(String message) async {
    final url = Uri.parse('$baseUrl/chat');
    
    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'message': message}),
      );

      if (response.statusCode == 200) {
        final Map<String, dynamic> responseData = jsonDecode(utf8.decode(response.bodyBytes));
        return responseData;
      } else {
        return {
          'text': 'Hệ thống đang bận phản hồi. Vui lòng thử lại sau giây lát!',
          'success': false
        };
      }
    } catch (e) {
      // Giả lập phản hồi thông minh trong trường hợp chưa bật Backend FastAPI
      return _generateMockResponse(message);
    }
  }

  /// Hàm giả lập phản hồi để bạn kiểm tra giao diện mượt mà ngay cả khi chưa kết nối Backend
  static Future<Map<String, dynamic>> _generateMockResponse(String userMessage) async {
    await Future.delayed(const Duration(milliseconds: 1200)); // Tạo độ trễ tự nhiên
    
    final lowerMsg = userMessage.toLowerCase();
    
    if (lowerMsg.contains('tư vấn') || lowerMsg.contains('build pc') || lowerMsg.contains('cấu hình')) {
      final mockBuild = PcBuild(
        buildId: 'BUILD-03909',
        cpuModel: 'AMD Ryzen 7 9800X3D',
        cpuPrice: 10836000,
        motherboardModel: 'MSI B850 PRO B850M-VC WIFI6E',
        motherboardPrice: 4992114,
        gpuModel: 'MSI GAMING TRIO RTX 4080 16GB',
        gpuPrice: 44399760,
        assemblyFee: 300000,
        buildNotes: 'Cấu hình tối ưu cao cấp cho Render 3D và Gaming siêu nặng!',
        totalPrice: 60527874,
      );

      return {
        'text': 'Tôi đã tìm thấy cấu hình tối ưu nhất cho bạn dựa trên kho dữ liệu sản phẩm!',
        'has_card': true,
        'build_data': mockBuild.toJson()
      };
    }

    return {
      'text': 'Chào bạn! Tôi là trợ lý tư vấn cấu hình PC tự động. Bạn cần tôi build cấu hình trong tầm giá bao nhiêu hoặc có yêu cầu linh kiện gì đặc biệt không?',
      'has_card': false
    };
  }
}