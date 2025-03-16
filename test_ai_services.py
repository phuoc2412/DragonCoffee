"""
Test AI services functionality
"""

from app import app, db
from ai_services import (
    init_ai_services,
    generate_social_post,
    analyze_review_sentiment,
    predict_product_demand,
    get_recommendations
)

def test_content_generation():
    """Test content generation with OpenAI"""
    post_data = {
        'product_name': 'Cà phê Dragon Đặc biệt',
        'product_description': 'Hỗn hợp độc đáo của hạt Arabica và Robusta, rang vừa tạo nên hương vị đậm đà đặc trưng'
    }
    
    result = generate_social_post(post_data)
    print("\nGenerated social media post:")
    print(result)

def test_sentiment_analysis():
    """Test sentiment analysis"""
    review_text = "Cà phê rất ngon, nhân viên phục vụ nhiệt tình và không gian quán rất đẹp!"
    
    result = analyze_review_sentiment(review_text)
    print("\nSentiment analysis result:")
    print(result)

def test_demand_prediction():
    """Test inventory demand prediction"""
    # Assuming product_id 1 exists
    result = predict_product_demand(1, days=7)
    print("\nDemand prediction result:")
    print(result)

def test_recommendations():
    """Test product recommendations"""
    # Get popular products (no user_id)
    result = get_recommendations(limit=3)
    print("\nPopular product recommendations:")
    print(result)

if __name__ == "__main__":
    with app.app_context():
        # Initialize AI services
        init_ai_services()
        
        # Run tests
        test_content_generation()
        test_sentiment_analysis()
        test_demand_prediction()
        test_recommendations()