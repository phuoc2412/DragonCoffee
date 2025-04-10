# /ai_services/__init__.py

"""
Dragon Coffee Shop - AI Services
This package contains various AI modules for enhancing the coffee shop system.
"""

import os
from flask import current_app # Import current_app để dùng logger

# --- Directory Creation (Đảm bảo thư mục models và data tồn tại) ---
# Chạy một lần khi module này được load
ai_services_dir = os.path.dirname(__file__)
models_dir = os.path.join(ai_services_dir, 'models')
data_dir = os.path.join(ai_services_dir, 'data')
os.makedirs(models_dir, exist_ok=True)
os.makedirs(data_dir, exist_ok=True)
# print(f"Ensured directories exist: {models_dir}, {data_dir}") # Optional debug print


# --- Import các modules AI và hàm khởi tạo/tiện ích của chúng ---

# 1. Recommendation Engine
from .recommendation import init_recommendation_engine, get_recommendations

# 2. Sentiment Analysis
# Giả sử db được truyền vào init_sentiment_analyzer nếu cần
from .sentiment_analysis import init_sentiment_analyzer, analyze_review_sentiment, get_sentiment_trends

# 3. Inventory Prediction
from .inventory_prediction import init_inventory_predictor, predict_product_demand, get_inventory_recommendations

# 4. Image Processing / Similarity
# Sửa đổi import nếu bạn tách file image_similarity
from .image_similarity import load_precomputed_features # Nếu cần load trước
from .image_processing import init_image_processor, process_product_image, enhance_image

# 5. Custom Chatbot (Thay thế chatbot cũ)
# GIẢ SỬ bạn đã tạo file chatbot_custom.py theo hướng dẫn trước
try:
    from .chatbot_custom import (
        get_custom_chatbot_response as get_response, # Alias để tên hàm dùng chung
        handle_custom_order as handle_order,         # Alias để tên hàm dùng chung
        init_chatbot_custom as init_chatbot        # Alias để tên hàm dùng chung
    )
    # print("Successfully imported from chatbot_custom") # Optional debug print
except ImportError as e:
    # Fallback hoặc báo lỗi nghiêm trọng nếu file chatbot_custom không tồn tại
    print(f"ERROR: Could not import custom chatbot from chatbot_custom.py: {e}. AI Chatbot will NOT work.")
    # Tạo các hàm giả để tránh lỗi runtime nếu cần thiết
    def init_chatbot(db): print("ERROR: Custom Chatbot init failed.")
    def get_response(*args, **kwargs): return {"response": "Chatbot đang bảo trì.", "intent": "error"}
    def handle_order(*args, **kwargs): return {"response": "Chức năng đặt hàng qua Chatbot đang bảo trì."}

# 6. Content Generator
from .content_generator import (
    init_content_generator,
    generate_product_description,
    generate_promotion,
    generate_social_post,
    generate_email,
    generate_blog_post,
    generate_about_us_intro,
    generate_interesting_story # <-- ĐÃ CÓ Ở ĐÂY
)

# --- Initialize all services ---
def init_ai_services():
    """Initialize all AI services. Should be called within app context."""
    # Chỉ import db ở đây nếu nó chưa được truyền vào các hàm init
    from app import db

    # Luôn kiểm tra xem current_app có tồn tại không trước khi dùng logger
    logger = None
    if current_app:
        logger = current_app.logger
        logger.info("Initializing AI services within app context...")
    else:
        # Fallback logging nếu không có app context (ví dụ khi chạy script riêng)
        import logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        logger.warning("Initializing AI services outside of Flask app context.")

    all_initialized = True
    services_initialized = []
    services_failed = []

    try:
        logger.info("Initializing Recommendation Engine...")
        init_recommendation_engine(db)
        services_initialized.append("Recommendation")

        logger.info("Initializing Sentiment Analyzer...")
        init_sentiment_analyzer(db) # Truyền db nếu hàm init cần
        services_initialized.append("Sentiment")

        logger.info("Initializing Inventory Predictor...")
        init_inventory_predictor(db)
        services_initialized.append("Inventory")

        logger.info("Initializing Image Processor...")
        init_image_processor()
        services_initialized.append("Image Processing")

        # Khởi tạo Custom Chatbot
        logger.info("Initializing Custom Chatbot...")
        init_chatbot(db) # Gọi hàm init_chatbot đã được alias
        services_initialized.append("Chatbot (Custom)")

        logger.info("Initializing Content Generator...")
        init_content_generator()
        services_initialized.append("Content Generator")

    except Exception as e:
        all_initialized = False
        # Xác định service nào lỗi nếu có thể, hoặc log lỗi chung
        failed_service = next((s for s in ["Recommendation", "Sentiment", "Inventory", "Image Processing", "Chatbot (Custom)", "Content Generator"] if s not in services_initialized), "Unknown")
        services_failed.append(f"{failed_service}: {e}")
        logger.error(f"Error initializing AI service '{failed_service}': {e}", exc_info=True)
        # Cân nhắc có nên raise lỗi để dừng app không, hay chỉ log và tiếp tục
        # raise e

    if all_initialized:
        logger.info("All AI services initialized successfully.")
    else:
        logger.error(f"AI service initialization completed with errors. Failed: {', '.join(services_failed)}")


# --- Helper Functions (Ví dụ: Kiểm tra OpenAI key) ---
def check_openai_available():
    """Check if OpenAI API key is available"""
    # Function này không cần logger vì nó đơn giản
    return bool(os.environ.get('OPENAI_API_KEY'))


# --- `__all__` for exporting functions ---
# Đảm bảo tất cả các hàm bạn muốn dùng bên ngoài package `ai_services` đều có ở đây.
__all__ = [
    'init_ai_services',              # Hàm khởi tạo chung
    'check_openai_available',        # Kiểm tra OpenAI key

    # Recommendation
    'get_recommendations',

    # Sentiment Analysis
    'analyze_review_sentiment',
    'get_sentiment_trends',

    # Inventory Prediction
    'predict_product_demand',
    'get_inventory_recommendations',

    # Image Processing / Similarity
    'process_product_image',        # Xử lý ảnh tổng quát
    'enhance_image',                # Nâng cấp ảnh
    # Nếu cần dùng hàm tìm ảnh từ bên ngoài (thường chỉ dùng trong chatbot):
    # 'get_similar_products_by_feature_vector',
    # 'extract_features',

    # Chatbot (Custom)
    'get_response',                 # Hàm lấy phản hồi chính
    'handle_order',                 # Hàm xử lý đặt hàng (nếu có logic riêng)

    # Content Generation
    'generate_product_description',
    'generate_promotion',
    'generate_social_post',
    'generate_email',
    'generate_blog_post',
    'generate_about_us_intro',
    'generate_interesting_story'    # <-- Hàm tạo câu chuyện
]