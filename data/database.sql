-- Script tạo cơ sở dữ liệu và các bảng cho Đồ án Chatbot PC Builder
-- Cấu trúc bao gồm bảng lưu trữ lịch sử chat (đã có trong source code) 
-- và các bảng linh kiện PC (được ánh xạ từ các file CSV hiện tại)

CREATE DATABASE IF NOT EXISTS `chat_history`
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE `chat_history`;

-- ==============================================================
-- 1. BẢNG LƯU TRỮ LỊCH SỬ HỘI THOẠI (Dùng bởi SQLAlchemy)
-- ==============================================================
CREATE TABLE IF NOT EXISTS `chat_history` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_uid` VARCHAR(255) NOT NULL COMMENT 'Firebase UID của người dùng',
    `session_id` VARCHAR(255) NOT NULL COMMENT 'ID của phiên chat',
    `role` VARCHAR(10) NOT NULL COMMENT 'Vai trò: human hoặc ai',
    `content` TEXT NOT NULL COMMENT 'Nội dung tin nhắn',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_user_uid` (`user_uid`),
    INDEX `idx_session_id` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -- ==============================================================
-- -- 2. CÁC BẢNG QUẢN LÝ LINH KIỆN PC (Dựa trên Headers của CSV)
-- -- Chú ý: Cấu trúc này dùng nếu bạn muốn migrate từ Pandas (CSV) sang MySQL
-- -- ==============================================================

-- -- Bảng lưu trữ dữ liệu CPU
-- CREATE TABLE IF NOT EXISTS `cpu` (
--     `id` INT AUTO_INCREMENT PRIMARY KEY,
--     `ten` VARCHAR(255) NOT NULL COMMENT 'Tên CPU',
--     `gia` DECIMAL(15, 2) DEFAULT 0.0 COMMENT 'Giá (VNĐ)',
--     `so_loi` INT DEFAULT 0 COMMENT 'Số lõi',
--     `xung_co_ban` FLOAT DEFAULT 0.0 COMMENT 'Xung cơ bản (GHz)',
--     `xung_boost` FLOAT DEFAULT 0.0 COMMENT 'Xung boost (GHz)',
--     `kien_truc` VARCHAR(100) COMMENT 'Kiến trúc (VD: Zen 4, Raptor Lake)',
--     `tdp` INT DEFAULT 0 COMMENT 'Công suất tiêu thụ (W)',
--     `do_hoa` VARCHAR(100) COMMENT 'Đồ họa tích hợp',
--     `socket` VARCHAR(50) COMMENT 'Loại Socket (VD: AM5, LGA1700)',
--     INDEX `idx_ten` (`ten`)
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -- Bảng lưu trữ dữ liệu Motherboard (Mainboard)
-- CREATE TABLE IF NOT EXISTS `motherboard` (
--     `id` INT AUTO_INCREMENT PRIMARY KEY,
--     `ten` VARCHAR(255) NOT NULL COMMENT 'Tên Mainboard',
--     `gia` DECIMAL(15, 2) DEFAULT 0.0 COMMENT 'Giá (VNĐ)',
--     `socket` VARCHAR(50) COMMENT 'Loại Socket hỗ trợ',
--     `kich_thuoc` VARCHAR(50) COMMENT 'Kích thước (VD: Micro ATX, ATX)',
--     `ram_toi_da` INT DEFAULT 0 COMMENT 'Dung lượng RAM tối đa (GB)',
--     `khe_ram` INT DEFAULT 0 COMMENT 'Số khe cắm RAM',
--     `mau` VARCHAR(50) COMMENT 'Màu sắc chủ đạo',
--     `ram_ho_tro` VARCHAR(50) COMMENT 'Loại RAM hỗ trợ (VD: DDR4, DDR5)',
--     `khe_m2` INT DEFAULT 0 COMMENT 'Số khe cắm ổ cứng M.2',
--     `luu_tru` VARCHAR(255) COMMENT 'Thông số lưu trữ khác (SATA, v.v.)',
--     `pcie` VARCHAR(100) COMMENT 'Chuẩn PCIe hỗ trợ',
--     INDEX `idx_ten` (`ten`)
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -- Bảng lưu trữ dữ liệu Card Đồ Họa (GPU)
-- CREATE TABLE IF NOT EXISTS `gpu` (
--     `id` INT AUTO_INCREMENT PRIMARY KEY,
--     `ten` VARCHAR(255) NOT NULL COMMENT 'Tên GPU',
--     `gia` DECIMAL(15, 2) DEFAULT 0.0 COMMENT 'Giá (VNĐ)',
--     `chipset` VARCHAR(100) COMMENT 'Chipset xử lý (VD: RTX 4060, RX 7900)',
--     `bo_nho` INT DEFAULT 0 COMMENT 'Dung lượng VRAM (GB)',
--     `xung_co_ban` FLOAT DEFAULT 0.0 COMMENT 'Xung cơ bản (MHz)',
--     `xung_boost` FLOAT DEFAULT 0.0 COMMENT 'Xung boost (MHz)',
--     `mau` VARCHAR(50) COMMENT 'Màu sắc',
--     `chieu_dai` FLOAT DEFAULT 0.0 COMMENT 'Chiều dài card (mm)',
--     `tdp` INT DEFAULT 0 COMMENT 'Công suất tiêu thụ (W)',
--     `interface` VARCHAR(100) COMMENT 'Chuẩn giao tiếp (VD: PCIe 4.0 x16)',
--     INDEX `idx_ten` (`ten`)
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
