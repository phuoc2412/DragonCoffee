# /train_chatbot.py
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app import app, db # Import app và db instance

# === SỬA LỖI IMPORT ===
# Giờ đây get_logger và các hằng số (INTENT_MODEL_PATH, ...) được import từ chatbot_ml.py
try:
    from ai_services.chatbot_ml import (
        train_intent_model,
        load_training_data,        # Import hàm load training data
        create_default_training_data, # Import hàm tạo data mặc định
        get_logger,                # Import logger
        INTENT_MODEL_PATH,         # Import đường dẫn lưu model
        TFIDF_VECTORIZER_PATH,     # Import đường dẫn lưu vectorizer
        TRAINING_DATA_PATH         # Import đường dẫn file training data
    )
    # Không cần init_chatbot_ml ở đây vì train_intent_model sẽ xử lý việc tạo vectorizer/model
except ImportError as e:
    print(f"Lỗi nghiêm trọng khi import từ ai_services.chatbot_ml: {e}")
    print("Kiểm tra lại cấu trúc file và các định nghĩa trong chatbot_ml.py.")
    sys.exit(1)
# =======================

def run_training():
    """Chạy quá trình huấn luyện mô hình chatbot AI (NLU - Intent Classification)."""
    logger = get_logger() # Lấy logger chung của chatbot_ml
    print("-" * 40)
    logger.info(">>> BẮT ĐẦU QUÁ TRÌNH HUẤN LUYỆN CHATBOT ML <<<")

    # Cần app context để các hàm DB (nếu có) trong quá trình load_training_data hoạt động
    with app.app_context():
        logger.info("Chạy quá trình huấn luyện trong App Context...")

        # Bước 1: Tải hoặc tạo dữ liệu huấn luyện
        # Hàm load_training_data sẽ tự động tạo file default nếu chưa có
        current_training_data = load_training_data()
        if not current_training_data:
             logger.error("Không thể tải hoặc tạo dữ liệu huấn luyện. Dừng quá trình.")
             print("!!! LỖI: Không có dữ liệu huấn luyện. Quá trình dừng lại. !!!")
             sys.exit(1)

        logger.info(f"Sử dụng {len(current_training_data)} mẫu huấn luyện từ: {TRAINING_DATA_PATH}")
        if len(current_training_data) < 10: # Cảnh báo nếu quá ít dữ liệu
            logger.warning("Số lượng mẫu huấn luyện rất ít. Chất lượng model có thể không cao.")
            print("CẢNH BÁO: Dữ liệu huấn luyện quá ít, model có thể không chính xác.")


        # Bước 2: Huấn luyện mô hình
        # Hàm train_intent_model đã bao gồm cả việc tạo vectorizer và classifier
        try:
            logger.info("Bắt đầu huấn luyện mô hình phân loại ý định...")
            training_successful = train_intent_model() # Hàm này sẽ trả về True/False

            if training_successful:
                logger.info(">>> HUẤN LUYỆN MÔ HÌNH ML THÀNH CÔNG! <<<")
                print(">>> HUẤN LUYỆN MÔ HÌNH ML THÀNH CÔNG! <<<")
                print(f"   - Mô hình Intent Classifier đã được lưu tại: {INTENT_MODEL_PATH}")
                print(f"   - Bộ TF-IDF Vectorizer đã được lưu tại: {TFIDF_VECTORIZER_PATH}")
                print(f"   - Dữ liệu huấn luyện được sử dụng từ: {TRAINING_DATA_PATH}")
            else:
                logger.error("!!! HUẤN LUYỆN MÔ HÌNH ML THẤT BẠI. !!!")
                print("!!! HUẤN LUYỆN MÔ HÌNH ML THẤT BẠI. Vui lòng kiểm tra log lỗi chi tiết. !!!")
                sys.exit(1) # Dừng script nếu huấn luyện thất bại

        except Exception as e:
            logger.critical(f"Lỗi không mong muốn trong quá trình huấn luyện: {e}", exc_info=True)
            print(f"!!! LỖI NGHIÊM TRỌNG KHI HUẤN LUYỆN: {e} !!!")
            sys.exit(1)

    logger.info(">>> KẾT THÚC QUÁ TRÌNH HUẤN LUYỆN CHATBOT ML <<<")
    print("-" * 40)

if __name__ == "__main__":
    print("Khởi chạy script huấn luyện Chatbot ML...")
    run_training()
    print("Script huấn luyện đã hoàn tất.")