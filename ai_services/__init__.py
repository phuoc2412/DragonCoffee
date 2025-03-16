"""
Dragon Coffee Shop - AI Services
This package contains various AI modules for enhancing the coffee shop system.
"""

from app import db

# Import all AI service modules
from .recommendation import init_recommendation_engine, get_recommendations
from .sentiment_analysis import init_sentiment_analyzer, analyze_review_sentiment, get_sentiment_trends
from .inventory_prediction import init_inventory_predictor, predict_product_demand, get_inventory_recommendations
from .image_processing import init_image_processor, process_product_image, enhance_image
from .chatbot import init_chatbot, get_response, handle_order
from .content_generator import (
    init_content_generator, 
    generate_product_description, 
    generate_promotion, 
    generate_social_post, 
    generate_email, 
    generate_blog_post
)

# Create directory for models
import os
os.makedirs('ai_services/models', exist_ok=True)
os.makedirs('ai_services/data', exist_ok=True)

# Initialize all services
def init_ai_services():
    """Initialize all AI services"""
    try:
        init_recommendation_engine(db)
        init_sentiment_analyzer()
        init_inventory_predictor(db)
        init_image_processor()
        init_chatbot(db)
        init_content_generator()
        print("AI services initialized successfully")
    except Exception as e:
        print(f"Error initializing AI services: {e}")

# Check for OpenAI API key
def check_openai_available():
    """Check if OpenAI API key is available"""
    import os
    return bool(os.environ.get('OPENAI_API_KEY'))