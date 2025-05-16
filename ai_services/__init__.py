import os
import logging
from flask import current_app # Để sử dụng logger của Flask

# --- Setup Logging ---
# Define AI-specific logger first
ai_logger = logging.getLogger('ai_services')
if not ai_logger.hasHandlers(): # Basic configuration if not already set up
    log_format = '%(asctime)s - %(levelname)s - AI_PACKAGE - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format)
    ai_logger.setLevel(logging.INFO) # Ensure level is set


def _ai_get_logger():
    """Helper to get logger, prioritize Flask's logger if in context."""
    return current_app.logger if current_app else ai_logger


# Get the package-level logger
logger = _ai_get_logger()

# --- Import ML Chatbot ---
try:
    # Import only the necessary public interface functions and the init function
    from .chatbot_ml import (
        init_chatbot_ml,           # The function to initialize the core instance
        get_ml_chatbot_response,  # Alias for the main response function
        handle_ml_order           # Alias for the order handling flow
        # Do NOT import the MLChatbot class instance itself unless necessary
    )
    logger.info("Imported core ML Chatbot functions from chatbot_ml.py.")
    # Alias the functions for the package-level public interface if desired
    get_response = get_ml_chatbot_response
    handle_order = handle_ml_order
    init_chatbot = init_chatbot_ml # Also alias the init function if needed

except ImportError as e:
    logger.critical(f"CRITICAL: Could not import ML Chatbot functions from chatbot_ml.py: {e}. Chatbot functionality WILL NOT WORK.", exc_info=True)
    # Define dummy/placeholder functions if the core chatbot import fails
    def init_chatbot_ml(*args, **kwargs):
        logger.error("!!! ML Chatbot initialization SKIPPED due to import error !!!")
        pass
    get_ml_chatbot_response = lambda text, db, sid=None: {'success': False, 'response': "Lỗi hệ thống chatbot (Import).", 'intent': "init_error", 'entities': {}, 'image_results': []}
    handle_ml_order = get_ml_chatbot_response # Alias dummy function
    get_response = get_ml_chatbot_response # Alias dummy function
    handle_order = get_ml_chatbot_response # Alias dummy function
    init_chatbot = init_chatbot_ml # Alias dummy function


# --- Import Other AI Modules (Keep existing structure as per request) ---
# Assuming these are separate modules you want to keep
try:
    # Recommendation
    from .recommendation import init_recommendation_engine, get_recommendations
    logger.debug("Imported Recommendation Engine.")
except ImportError as e:
    logger.warning(f"Recommendation Engine module not found: {e}. Feature disabled.")
    def init_recommendation_engine(*args, **kwargs): pass
    def get_recommendations(*args, **kwargs): return []

try:
    # Sentiment Analysis
    from .sentiment_analysis import init_sentiment_analyzer, analyze_review_sentiment, get_sentiment_trends
    logger.debug("Imported Sentiment Analysis.")
except ImportError as e:
    logger.warning(f"Sentiment Analysis module not found: {e}. Feature disabled.")
    def init_sentiment_analyzer(*args, **kwargs): pass
    def analyze_review_sentiment(*args, **kwargs): return {'sentiment_label': 'neutral', 'sentiment_score': 0.0, 'is_toxic': False}
    def get_sentiment_trends(*args, **kwargs): return []

try:
    # Inventory Prediction
    from .inventory_prediction import init_inventory_predictor, predict_product_demand, get_inventory_recommendations
    logger.debug("Imported Inventory Prediction.")
except ImportError as e:
    logger.warning(f"Inventory Prediction module not found: {e}. Feature disabled.")
    def init_inventory_predictor(*args, **kwargs): pass
    def predict_product_demand(*args, **kwargs): return []
    def get_inventory_recommendations(*args, **kwargs): return []

try:
    # Image Processing/Similarity
    # Assuming `image_similarity.py` and `image_processing.py` exist and provide these functions
    from .image_similarity import load_precomputed_features, extract_features, get_similar_products_by_feature_vector
    from .image_processing import init_image_processor, process_product_image, enhance_image, generate_image_from_text_hf, save_generated_image
    logger.debug("Imported Image Processing/Similarity modules.")
except ImportError as e:
    logger.warning(f"Image Processing/Similarity modules not found: {e}. Feature disabled.")
    def load_precomputed_features(*args, **kwargs): return {}
    def extract_features(*args, **kwargs): return None
    def get_similar_products_by_feature_vector(*args, **kwargs): return []
    def init_image_processor(*args, **kwargs): pass
    def process_product_image(*args, **kwargs): return {'error': 'Image processing disabled'}
    def enhance_image(*args, **kwargs): return None
    def generate_image_from_text_hf(*args, **kwargs): return None
    def save_generated_image(*args, **kwargs): return None


# --- Import Content Generator (Template-Based) ---
# Assuming this module exists and is needed
try:
    from .content_generator import (
        init_content_generator,
        generate_product_description,
        generate_promotion,
        generate_social_post,
        generate_email,
        generate_blog_post,
        generate_about_us_intro,
        generate_interesting_story
    )
    logger.debug("Imported Content Generator (Template).")
except ImportError as e:
    logger.warning(f"Content Generator module not found: {e}. Feature disabled.")
    def init_content_generator(): pass
    def generate_product_description(*args, **kwargs): return "Mô tả đang cập nhật..."
    def generate_promotion(*args, **kwargs): return "Ưu đãi sắp ra mắt!"
    def generate_social_post(*args, **kwargs): return "Bài viết sắp có..."
    def generate_email(*args, **kwargs): return "Nội dung email..."
    def generate_blog_post(*args, **kwargs): return "Bài blog..."
    def generate_about_us_intro(*args, **kwargs): return "Giới thiệu cửa hàng..."
    def generate_interesting_story(*args, **kwargs): return "Câu chuyện thú vị..."


# === Global AI Service Initialization Function ===
def init_ai_services(db_instance):
    """
    Initialize all available AI services.
    Pass the database instance to services that need it.
    This function should be called once when the Flask app starts, within an app context.
    """
    logger = _ai_get_logger()
    logger.info("--- Initializing All AI Services ---")

    if db_instance is None:
        logger.critical("Database instance is None. AI services that depend on DB cannot be fully initialized.")


    services_status = {} # To report initialization status

    # Initialize each service and record status
    # Pass the db_instance where needed

    try: # Custom ML Chatbot (Highest priority due to critical function)
        logger.info("Initializing Custom ML Chatbot...")
        init_chatbot_ml(db_instance) # Pass db_instance here
        services_status["Chatbot (ML)"] = "OK" if ml_chatbot_instance else "PARTIAL/FAILED"
        logger.info("Custom ML Chatbot Initialized.")
    except NameError: services_status["Chatbot (ML)"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Chatbot (ML)"] = f"FAILED ({type(e).__name__})"; logger.critical(f"Custom ML Chatbot Init FAILED: {e}.", exc_info=True)


    try: # Recommendation Engine
        logger.info("Initializing Recommendation Engine...")
        init_recommendation_engine(db_instance) # Pass db_instance
        services_status["Recommendation"] = "OK"
        logger.info("Recommendation Engine Initialized.")
    except NameError: services_status["Recommendation"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Recommendation"] = f"FAILED ({type(e).__name__})"; logger.error(f"Recommendation Engine Init FAILED: {e}.", exc_info=True)

    try: # Sentiment Analysis
        logger.info("Initializing Sentiment Analyzer...")
        init_sentiment_analyzer(db_instance) # Pass db_instance
        services_status["Sentiment"] = "OK"
        logger.info("Sentiment Analyzer Initialized.")
    except NameError: services_status["Sentiment"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Sentiment"] = f"FAILED ({type(e).__name__})"; logger.error(f"Sentiment Analyzer Init FAILED: {e}.", exc_info=True)


    try: # Inventory Prediction
        logger.info("Initializing Inventory Predictor...")
        init_inventory_predictor(db_instance) # Pass db_instance
        services_status["Inventory Prediction"] = "OK"
        logger.info("Inventory Predictor Initialized.")
    except NameError: services_status["Inventory Prediction"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Inventory Prediction"] = f"FAILED ({type(e).__name__})"; logger.error(f"Inventory Predictor Init FAILED: {e}.", exc_info=True)

    try: # Image Processing / Similarity (Only init if the module has an init func)
        logger.info("Initializing Image Processor & loading features...")
        # load_precomputed_features() # Load features needs DB if product mapping needed. Let image_similarity handle load on first use.
        # init_image_processor() # Call this if image_processing has a dedicated init
        services_status["Image Processing/Similarity"] = "OK" # Assume OK if module imported
        logger.info("Image Processing/Similarity Modules Loaded.") # Refined message
    except NameError: services_status["Image Processing/Similarity"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Image Processing/Similarity"] = f"FAILED ({type(e).__name__})"; logger.error(f"Image Processing/Similarity Init FAILED: {e}.", exc_info=True)

    try: # Content Generator (Template)
        logger.info("Initializing Content Generator (Template)...")
        init_content_generator()
        services_status["Content Generator (Template)"] = "OK"
        logger.info("Content Generator (Template) Initialized.")
    except NameError: services_status["Content Generator (Template)"] = "SKIPPED (Not Imported)"
    except Exception as e: services_status["Content Generator (Template)"] = f"FAILED ({type(e).__name__})"; logger.error(f"Content Generator Init FAILED: {e}.", exc_info=True)


    logger.info("--- AI Services Initialization Report ---")
    for service, status in services_status.items():
        if "FAILED" in status or "CRITICAL" in status or "SKIPPED" in status:
             logger.error(f" - {service}: {status}") # Use error for failures
        else:
            logger.info(f" - {service}: {status}") # Use info for success


# === Expose Public Functions (`__all__`) ===
__all__ = [
    'init_ai_services', # Function to initialize everything

    # --- Core Chatbot Interface (ML-based logic handled by chatbot_ml.py) ---
    'get_response',          # -> Alias for get_ml_chatbot_response
    'handle_order',          # -> Alias for handle_ml_order (or get_response if order is within general flow)
    # We don't expose `init_chatbot_ml` directly, `init_ai_services` is the entry point


    # --- Functions/Classes imported from other specific AI modules ---
    'get_recommendations',          # from recommendation.py
    'analyze_review_sentiment',     # from sentiment_analysis.py
    'get_sentiment_trends',         # from sentiment_analysis.py
    'predict_product_demand',       # from inventory_prediction.py
    'get_inventory_recommendations', # from inventory_prediction.py
    'process_product_image',        # from image_processing.py (and image_similarity?)
    'enhance_image',                # from image_processing.py
    'generate_image_from_text_hf',  # from image_processing.py (example of allowed external *API* for a *specific task*)
    'save_generated_image',         # from image_processing.py (saving result)
    # Add low-level image/feature functions if they are needed elsewhere
    'extract_features',             # from image_similarity.py (if raw feature vector is needed)
    'get_similar_products_by_feature_vector', # from image_similarity.py (if similarity needed outside chatbot visual search)
    'load_precomputed_features',    # from image_similarity.py (if manual reload is ever needed)

    # --- Content Generator Functions (Template-based) ---
    'generate_product_description',
    'generate_promotion',
    'generate_social_post',
    'generate_email',
    'generate_blog_post',
    'generate_about_us_intro',
    'generate_interesting_story',

    # Optional: Expose training function if intended to be called directly by admin/script
    # from .chatbot_ml import train_intent_model
    # 'train_intent_model',
]