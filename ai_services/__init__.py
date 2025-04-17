# /ai_services/__init__.py

"""
Dragon Coffee Shop - AI Services
This package contains various AI modules for enhancing the coffee shop system.
"""

import os
from flask import current_app # Import current_app để dùng logger
import logging # Import logging dự phòng

# --- Directory Creation ---
ai_services_dir = os.path.dirname(__file__)
models_dir = os.path.join(ai_services_dir, 'models')
data_dir = os.path.join(ai_services_dir, 'data')
os.makedirs(models_dir, exist_ok=True)
os.makedirs(data_dir, exist_ok=True)

# --- Helper Function for Logging ---
def _ai_get_logger():
    """Gets the logger, handling cases outside Flask context."""
    if current_app:
        return current_app.logger
    else:
        logger = logging.getLogger('ai_services')
        if not logger.hasHandlers():
            logging.basicConfig(level=logging.INFO)
            logger.info("AI Services logger initialized outside Flask context.")
        return logger

# --- Import các modules AI ---
logger = _ai_get_logger() # Lấy logger để dùng trong block import

try:
    # 1. Recommendation Engine
    from .recommendation import init_recommendation_engine, get_recommendations
    logger.debug("Imported Recommendation Engine.")
except ImportError as e:
    logger.error(f"Failed to import Recommendation Engine: {e}. Feature disabled.")
    # Tạo hàm giả
    def init_recommendation_engine(*args, **kwargs): pass
    def get_recommendations(*args, **kwargs): return []

try:
    # 2. Sentiment Analysis
    from .sentiment_analysis import init_sentiment_analyzer, analyze_review_sentiment, get_sentiment_trends
    logger.debug("Imported Sentiment Analysis.")
except ImportError as e:
    logger.error(f"Failed to import Sentiment Analysis: {e}. Feature disabled.")
    # Tạo hàm giả
    def init_sentiment_analyzer(*args, **kwargs): pass
    def analyze_review_sentiment(*args, **kwargs): return {'sentiment_label': 'neutral', 'sentiment_score': 0.0}
    def get_sentiment_trends(*args, **kwargs): return []

try:
    # 3. Inventory Prediction
    from .inventory_prediction import init_inventory_predictor, predict_product_demand, get_inventory_recommendations
    logger.debug("Imported Inventory Prediction.")
except ImportError as e:
    logger.error(f"Failed to import Inventory Prediction: {e}. Feature disabled.")
    # Tạo hàm giả
    def init_inventory_predictor(*args, **kwargs): pass
    def predict_product_demand(*args, **kwargs): return []
    def get_inventory_recommendations(*args, **kwargs): return []

try:
    # 4. Image Similarity & Processing
    from .image_similarity import load_precomputed_features, extract_features, get_similar_products_by_feature_vector
    from .image_processing import init_image_processor, process_product_image, enhance_image
    logger.debug("Imported Image Similarity & Processing.")
except ImportError as e:
    logger.error(f"Failed to import Image Processing/Similarity: {e}. Feature disabled.")
    # Tạo hàm giả
    def load_precomputed_features(): return {}
    def extract_features(*args, **kwargs): return None
    def get_similar_products_by_feature_vector(*args, **kwargs): return []
    def init_image_processor(): pass
    def process_product_image(*args, **kwargs): return {'error': 'Image processing disabled'}
    def enhance_image(*args, **kwargs): return None

try:
    # 5. Custom Chatbot (Từ chatbot_custom.py)
    from .chatbot_custom import (
        get_custom_chatbot_response as get_response, # ALIAS hàm chính
        handle_custom_order as handle_order,         # ALIAS hàm xử lý đơn hàng (có thể dùng chung get_response)
        init_chatbot_custom as init_chatbot        # ALIAS hàm khởi tạo
    )
    logger.info("Imported Custom Chatbot (chatbot_custom.py).")
except ImportError as e:
    logger.critical(f"CRITICAL: Could not import Custom Chatbot from chatbot_custom.py: {e}. Chatbot functionality WILL NOT WORK.", exc_info=True)
    # Tạo hàm giả để tránh crash hoàn toàn
    def init_chatbot(*args, **kwargs): logger.error("!!! Custom Chatbot initialization SKIPPED due to import error !!!"); pass
    def get_response(*args, **kwargs): logger.error("!!! get_response called, but Custom Chatbot failed to import !!!"); return {"success": False, "response": "Lỗi hệ thống chatbot.", "intent": "error", "entities": {}, "image_results": []}
    def handle_order(*args, **kwargs): logger.error("!!! handle_order called, but Custom Chatbot failed to import !!!"); return get_response() # Gọi lại get_response lỗi

try:
    # 6. Content Generator
    from .content_generator import (
        init_content_generator,
        generate_product_description,
        generate_promotion,
        generate_social_post,
        generate_email,
        generate_blog_post,
        generate_about_us_intro,
        generate_interesting_story # Thêm hàm này nếu có
    )
    logger.debug("Imported Content Generator.")
except ImportError as e:
    logger.error(f"Failed to import Content Generator: {e}. Feature disabled.")
    # Tạo hàm giả
    def init_content_generator(): pass
    def generate_product_description(*args, **kwargs): return "Mô tả đang cập nhật..."
    def generate_promotion(*args, **kwargs): return "Ưu đãi sắp ra mắt!"
    def generate_social_post(*args, **kwargs): return "Bài viết sắp có..."
    def generate_email(*args, **kwargs): return "Nội dung email..."
    def generate_blog_post(*args, **kwargs): return "Bài blog..."
    def generate_about_us_intro(*args, **kwargs): return "Giới thiệu cửa hàng..."
    def generate_interesting_story(*args, **kwargs): return "Câu chuyện thú vị..."


# --- Hàm Khởi Tạo Tổng Hợp ---
def init_ai_services():
    """Initialize all available AI services. Should be called within app context."""
    logger = _ai_get_logger() # Lấy logger ở đầu hàm
    logger.info("--- Initializing All AI Services ---")

    # Chỉ import db ở đây để tránh import vòng tròn nếu ai_services được import sớm
    from app import db

    services_status = {}

    # Recommendation
    try:
        logger.info("Initializing Recommendation Engine...")
        init_recommendation_engine(db)
        services_status["Recommendation"] = "OK"
        logger.info("Recommendation Engine Initialized.")
    except NameError: services_status["Recommendation"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Recommendation"] = f"FAILED ({e})"; logger.error(f"Recommendation Engine Init FAILED: {e}", exc_info=True)

    # Sentiment Analysis
    try:
        logger.info("Initializing Sentiment Analyzer...")
        init_sentiment_analyzer(db) # Truyền db nếu cần
        services_status["Sentiment"] = "OK"
        logger.info("Sentiment Analyzer Initialized.")
    except NameError: services_status["Sentiment"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Sentiment"] = f"FAILED ({e})"; logger.error(f"Sentiment Analyzer Init FAILED: {e}", exc_info=True)

    # Inventory Prediction
    try:
        logger.info("Initializing Inventory Predictor...")
        init_inventory_predictor(db)
        services_status["Inventory Prediction"] = "OK"
        logger.info("Inventory Predictor Initialized.")
    except NameError: services_status["Inventory Prediction"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Inventory Prediction"] = f"FAILED ({e})"; logger.error(f"Inventory Predictor Init FAILED: {e}", exc_info=True)

    # Image Processing & Similarity
    try:
        logger.info("Initializing Image Processor & loading features...")
        init_image_processor()
        load_precomputed_features() # Load features đã tính toán
        services_status["Image Processing"] = "OK"
        logger.info("Image Processor & Features Initialized.")
    except NameError: services_status["Image Processing"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Image Processing"] = f"FAILED ({e})"; logger.error(f"Image Processing Init FAILED: {e}", exc_info=True)

    # Custom Chatbot
    try:
        logger.info("Initializing Custom Chatbot...")
        init_chatbot(db) # Gọi hàm init đã alias
        services_status["Chatbot (Custom)"] = "OK" # Tên rõ ràng hơn
        logger.info("Custom Chatbot Initialized.")
    except NameError: services_status["Chatbot (Custom)"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Chatbot (Custom)"] = f"FAILED ({e})"; logger.error(f"Custom Chatbot Init FAILED: {e}", exc_info=True)

    # Content Generator
    try:
        logger.info("Initializing Content Generator...")
        init_content_generator()
        services_status["Content Generator"] = "OK"
        logger.info("Content Generator Initialized.")
    except NameError: services_status["Content Generator"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Content Generator"] = f"FAILED ({e})"; logger.error(f"Content Generator Init FAILED: {e}", exc_info=True)

    logger.info("--- AI Services Initialization Complete ---")
    # Log trạng thái từng service
    for service, status in services_status.items():
        if "FAILED" in status: logger.error(f" - {service}: {status}")
        elif "SKIPPED" in status: logger.warning(f" - {service}: {status}")
        else: logger.info(f" - {service}: {status}")


# --- Helper kiểm tra OpenAI Key (nếu cần cho Content Gen phiên bản LLM) ---
def check_openai_available():
    """Check if OpenAI API key is configured."""
    # Tạm thời trả về False vì đang dùng bản template
    return False # bool(os.environ.get('OPENAI_API_KEY'))


# --- `__all__` để chỉ định các thành phần public ---
# Cập nhật __all__ để bao gồm các hàm/biến muốn export từ package này
__all__ = [
    'init_ai_services',
    'check_openai_available',

    # Recommendation
    'get_recommendations',

    # Sentiment Analysis
    'analyze_review_sentiment',
    'get_sentiment_trends',

    # Inventory Prediction
    'predict_product_demand',
    'get_inventory_recommendations',

    # Image Processing / Similarity
    'process_product_image',
    'enhance_image',
    'extract_features', # Có thể cần nếu muốn dùng từ bên ngoài
    'get_similar_products_by_feature_vector', # Nếu muốn dùng tìm kiếm ảnh nâng cao

    # Chatbot (Custom) - Dùng tên đã alias
    'get_response',
    'handle_order', # Vẫn export phòng trường hợp có logic riêng

    # Content Generation - Dùng hàm generate tương ứng
    'generate_product_description',
    'generate_promotion',
    'generate_social_post',
    'generate_email',
    'generate_blog_post',
    'generate_about_us_intro',
    'generate_interesting_story'
]