"""
Dragon Coffee Shop - Sentiment Analysis System
This module analyzes customer reviews and feedback to determine sentiment.
"""

import re
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from collections import Counter
import os
import joblib
from datetime import datetime, timedelta

# Ensure NLTK resources are downloaded
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')
    
try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet')

class SentimentAnalyzer:
    def __init__(self):
        """Initialize sentiment analyzer with basic lexicon-based approach"""
        self.lemmatizer = WordNetLemmatizer()
        self.stop_words = set(stopwords.words('english'))
        
        # Sentiment lexicon
        self.sentiment_lexicon = {
            'positive': [
                'good', 'great', 'excellent', 'amazing', 'awesome', 'delicious',
                'tasty', 'nice', 'love', 'like', 'enjoy', 'wonderful', 'perfect',
                'fantastic', 'fresh', 'pleasant', 'satisfied', 'happy', 'best',
                'favorite', 'recommended', 'affordable', 'friendly', 'attentive',
                'quick', 'clean', 'comfortable', 'convenient', 'impressed'
            ],
            'negative': [
                'bad', 'terrible', 'awful', 'horrible', 'poor', 'worst',
                'disappointing', 'disappointed', 'slow', 'rude', 'cold', 'stale',
                'expensive', 'overpriced', 'dirty', 'unclean', 'uncomfortable',
                'mediocre', 'bland', 'bitter', 'burnt', 'tasteless', 'unfriendly',
                'unhelpful', 'long wait', 'crowded', 'noisy', 'unhygienic'
            ]
        }
        
        # Add some Vietnamese sentiment words
        self.sentiment_lexicon['positive'].extend([
            'ngon', 'tuyệt', 'tốt', 'thích', 'yêu', 'thơm', 'đáng giá', 'hài lòng',
            'sạch sẽ', 'dễ chịu', 'nhiệt tình', 'nhanh', 'chất lượng', 'giá tốt',
            'tươi', 'hoàn hảo', 'ấm cúng', 'gần gũi', 'vui vẻ', 'khuyến khích',
            'nổi bật', 'độc đáo', 'đặc biệt', 'chuyên nghiệp', 'hấp dẫn'
        ])
        
        self.sentiment_lexicon['negative'].extend([
            'dở', 'tệ', 'không ngon', 'chán', 'đắt', 'lâu', 'chậm', 'bẩn',
            'không sạch', 'đông', 'ồn', 'khó chịu', 'thất vọng', 'lạnh',
            'cũ', 'khó ăn', 'không tươi', 'nhạt', 'không đáng giá', 'thiếu',
            'không hài lòng', 'không chuyên nghiệp', 'thiếu nhiệt tình', 'khó uống'
        ])
        
        # Intensity modifiers
        self.intensifiers = [
            'very', 'really', 'extremely', 'incredibly', 'absolutely', 'totally',
            'completely', 'highly', 'especially', 'particularly', 'most', 'rất',
            'cực kỳ', 'vô cùng', 'quá', 'siêu', 'cực', 'đặc biệt', 'vô cùng'
        ]
        
        # Negation words
        self.negation_words = [
            'not', 'no', 'never', 'none', "don't", "doesn't", "didn't", "won't",
            "wouldn't", "couldn't", "shouldn't", "haven't", "hasn't", "hadn't",
            'cannot', "can't", 'nor', 'neither', 'không', 'chẳng', 'đừng',
            'không hề', 'không bao giờ', 'chẳng có gì'
        ]
        
        # ML model directory
        self.model_dir = 'ai_services/models'
        os.makedirs(self.model_dir, exist_ok=True)
        
        # ML model path
        self.model_path = os.path.join(self.model_dir, 'sentiment_model.joblib')
        self.vectorizer_path = os.path.join(self.model_dir, 'sentiment_vectorizer.joblib')
        
        # Try to load ML model
        self.ml_model = None
        self.vectorizer = None
        
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.vectorizer_path):
                self.ml_model = joblib.load(self.model_path)
                self.vectorizer = joblib.load(self.vectorizer_path)
                print("Loaded sentiment analysis model")
        except Exception as e:
            print(f"Error loading sentiment model: {e}")
    
    def preprocess_text(self, text):
        """Clean and tokenize text"""
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters and digits
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\d+', ' ', text)
        
        # Tokenize
        tokens = word_tokenize(text)
        
        # Remove stopwords and lemmatize
        tokens = [self.lemmatizer.lemmatize(token) for token in tokens 
                 if token not in self.stop_words]
        
        return tokens
    
    def analyze_sentiment_lexicon(self, text):
        """Analyze sentiment using lexicon-based approach"""
        # Preprocess text
        tokens = self.preprocess_text(text)
        
        # Check for sentiment words
        positive_count = 0
        negative_count = 0
        
        # Extract ngrams to catch phrases like "long wait"
        ngrams = []
        for i in range(len(tokens)):
            if i < len(tokens) - 1:
                ngrams.append(tokens[i] + ' ' + tokens[i+1])
        
        # Check negation context
        negation_active = False
        
        for i, token in enumerate(tokens):
            # Check for negation words
            if token in self.negation_words:
                negation_active = True
                continue
            
            # Reset negation after 3 words
            if negation_active and i > 0 and i % 3 == 0:
                negation_active = False
            
            # Check for intensifiers
            intensifier = 1.0
            if token in self.intensifiers:
                intensifier = 2.0
                continue
            
            # Check sentiment
            if token in self.sentiment_lexicon['positive']:
                if negation_active:
                    negative_count += intensifier
                else:
                    positive_count += intensifier
            
            elif token in self.sentiment_lexicon['negative']:
                if negation_active:
                    positive_count += intensifier
                else:
                    negative_count += intensifier
        
        # Also check ngrams
        for ngram in ngrams:
            if ngram in self.sentiment_lexicon['positive']:
                positive_count += 1.5  # Give extra weight to phrases
            elif ngram in self.sentiment_lexicon['negative']:
                negative_count += 1.5
        
        # Calculate sentiment score (-1 to 1)
        total = positive_count + negative_count
        if total == 0:
            sentiment_score = 0
        else:
            sentiment_score = (positive_count - negative_count) / total
        
        # Map to 1-5 star rating
        rating = round(2.5 + sentiment_score * 2.5)
        rating = max(1, min(5, rating))
        
        # Calculate confidence based on number of sentiment words found
        confidence = min(0.9, (total / max(5, len(tokens))) + 0.3)
        
        return {
            'rating': rating,
            'sentiment_score': sentiment_score,
            'confidence': confidence,
            'method': 'lexicon',
            'positive_words': positive_count,
            'negative_words': negative_count
        }
    
    def train_from_existing_reviews(self):
        """Train model from existing reviews in database"""
        from models import Review
        
        # Get all reviews with ratings
        reviews = self.db.session.query(Review).all()
        
        if not reviews or len(reviews) < 20:  # Need minimum data
            print("Not enough reviews to train sentiment model")
            return False
        
        # Prepare data
        texts = [review.content for review in reviews if review.content]
        ratings = [review.rating for review in reviews if review.content]
        
        # Convert ratings to sentiment classes
        # 1-2 stars = negative, 3 = neutral, 4-5 = positive
        sentiments = []
        for rating in ratings:
            if rating <= 2:
                sentiments.append('negative')
            elif rating == 3:
                sentiments.append('neutral')
            else:
                sentiments.append('positive')
        
        # Train the model
        return self.train_model(texts, sentiments)
    
    def train_model(self):
        """Train a machine learning model for sentiment analysis"""
        # This is a simplified implementation
        # In production, you would use a more sophisticated approach
        
        # Sample training data
        texts = [
            "The coffee was excellent and the service was quick.",
            "Great atmosphere and delicious pastries.",
            "The staff was very friendly and helpful.",
            "The best coffee shop in town, highly recommended!",
            "Reasonable prices and great quality.",
            "The coffee was cold and the service was slow.",
            "Overpriced and mediocre quality.",
            "The staff was rude and unhelpful.",
            "Very disappointed with my experience, won't return.",
            "Dirty tables and poor hygiene.",
            "Average coffee, nothing special.",
            "The place was too crowded and noisy.",
            "OK experience but there are better options.",
            "The WiFi was slow but the coffee was good.",
            "Decent coffee but expensive.",
            "Cà phê rất ngon và nhân viên nhiệt tình.",
            "Không gian đẹp, đồ uống tuyệt vời.",
            "Quán sạch sẽ và thoải mái.",
            "Giá cả hợp lý, chất lượng tốt.",
            "Cà phê ngon nhất trong khu vực!",
            "Cà phê nguội và phục vụ chậm.",
            "Đắt và chất lượng trung bình.",
            "Nhân viên không nhiệt tình.",
            "Rất thất vọng, không quay lại nữa.",
            "Bàn ghế bẩn, vệ sinh kém."
        ]
        
        sentiments = [
            'positive', 'positive', 'positive', 'positive', 'positive',
            'negative', 'negative', 'negative', 'negative', 'negative',
            'neutral', 'neutral', 'neutral', 'neutral', 'neutral',
            'positive', 'positive', 'positive', 'positive', 'positive',
            'negative', 'negative', 'negative', 'negative', 'negative'
        ]
        
        # Create TF-IDF vectorizer
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            ngram_range=(1, 2),
            min_df=2
        )
        
        # Transform text data
        X = self.vectorizer.fit_transform(texts)
        
        # Train logistic regression model
        self.ml_model = LogisticRegression(C=10, max_iter=1000)
        self.ml_model.fit(X, sentiments)
        
        # Save model and vectorizer
        try:
            joblib.dump(self.ml_model, self.model_path)
            joblib.dump(self.vectorizer, self.vectorizer_path)
            print("Saved sentiment analysis model")
            return True
        except Exception as e:
            print(f"Error saving sentiment model: {e}")
            return False
    
    def analyze_sentiment_ml(self, text):
        """Analyze sentiment using machine learning model if available"""
        if not self.ml_model or not self.vectorizer:
            return None
        
        try:
            # Transform text
            X = self.vectorizer.transform([text])
            
            # Predict sentiment
            sentiment = self.ml_model.predict(X)[0]
            
            # Get probabilities
            proba = self.ml_model.predict_proba(X)[0]
            confidence = max(proba)
            
            # Map sentiment to rating
            if sentiment == 'negative':
                rating = 1 if confidence > 0.7 else 2
            elif sentiment == 'neutral':
                rating = 3
            else:  # positive
                rating = 5 if confidence > 0.7 else 4
            
            return {
                'rating': rating,
                'sentiment': sentiment,
                'confidence': confidence,
                'method': 'ml_model'
            }
        except Exception as e:
            print(f"Error in ML sentiment analysis: {e}")
            return None
    
    def analyze_sentiment(self, text):
        """Analyze sentiment using both methods (ML preferred if available)"""
        # Try ML model first
        ml_result = self.analyze_sentiment_ml(text)
        
        # Always run lexicon analysis
        lexicon_result = self.analyze_sentiment_lexicon(text)
        
        # If ML model is available and confident, use it
        if ml_result and ml_result['confidence'] > 0.6:
            result = ml_result
            # Add lexicon metrics for debugging
            result['lexicon_rating'] = lexicon_result['rating']
            result['lexicon_confidence'] = lexicon_result['confidence']
        else:
            # Otherwise use lexicon result
            result = lexicon_result
        
        return result
    
    def track_sentiment(self, review_id, sentiment_data):
        """Store sentiment analysis result in database"""
        from models import Review
        from sqlalchemy import text
        
        try:
            # Store sentiment data in a custom SQL table if needed
            # For this implementation, we'll just update the review
            
            # Create metadata table if it doesn't exist
            self.db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS review_sentiment (
                    id SERIAL PRIMARY KEY,
                    review_id INTEGER REFERENCES review(id),
                    sentiment_score FLOAT,
                    confidence FLOAT,
                    method VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            self.db.session.commit()
            
            # Insert sentiment data
            self.db.session.execute(text("""
                INSERT INTO review_sentiment (review_id, sentiment_score, confidence, method)
                VALUES (:review_id, :sentiment_score, :confidence, :method)
            """), {
                'review_id': review_id,
                'sentiment_score': sentiment_data.get('sentiment_score', 0),
                'confidence': sentiment_data.get('confidence', 0),
                'method': sentiment_data.get('method', 'unknown')
            })
            self.db.session.commit()
            
            return True
        except Exception as e:
            print(f"Error tracking sentiment: {e}")
            return False
    
    def get_recent_sentiment_trends(self, days=30, limit=100):
        """Get sentiment trends for recent reviews"""
        from sqlalchemy import text
        
        try:
            # Calculate date threshold
            threshold = datetime.utcnow() - timedelta(days=days)
            
            # Query for sentiment trends
            result = self.db.session.execute(text("""
                SELECT 
                    DATE(r.created_at) as review_date,
                    AVG(r.rating) as avg_rating,
                    COUNT(r.id) as review_count,
                    AVG(rs.sentiment_score) as avg_sentiment_score
                FROM 
                    review r
                LEFT JOIN 
                    review_sentiment rs ON r.id = rs.review_id
                WHERE 
                    r.created_at >= :threshold
                GROUP BY 
                    DATE(r.created_at)
                ORDER BY 
                    review_date DESC
                LIMIT :limit
            """), {
                'threshold': threshold,
                'limit': limit
            })
            
            # Format results
            trends = []
            for row in result:
                trends.append({
                    'date': row.review_date.strftime('%Y-%m-%d'),
                    'avg_rating': float(row.avg_rating),
                    'review_count': int(row.review_count),
                    'avg_sentiment_score': float(row.avg_sentiment_score) if row.avg_sentiment_score else 0
                })
            
            return trends
        except Exception as e:
            print(f"Error getting sentiment trends: {e}")
            return []


# Singleton instance
sentiment_analyzer = None

def init_sentiment_analyzer():
    """Initialize the sentiment analyzer"""
    global sentiment_analyzer
    sentiment_analyzer = SentimentAnalyzer()
    
    # Train model if not already trained
    if not sentiment_analyzer.ml_model:
        sentiment_analyzer.train_model()
    
    return sentiment_analyzer

def analyze_review_sentiment(review_text, review_id=None):
    """Analyze sentiment of review text and optionally store result"""
    if sentiment_analyzer is None:
        init_sentiment_analyzer()
    
    sentiment_result = sentiment_analyzer.analyze_sentiment(review_text)
    
    # Store result if review_id is provided
    if review_id is not None and sentiment_result:
        from app import db
        sentiment_analyzer.db = db
        sentiment_analyzer.track_sentiment(review_id, sentiment_result)
    
    return sentiment_result

def get_sentiment_trends(days=30):
    """Get sentiment trends for the specified time period"""
    if sentiment_analyzer is None:
        from app import db
        init_sentiment_analyzer()
        sentiment_analyzer.db = db
    
    return sentiment_analyzer.get_recent_sentiment_trends(days)