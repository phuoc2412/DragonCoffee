"""
Dragon Coffee Shop - Sentiment Analysis System
This module analyzes customer reviews and feedback to determine sentiment.
"""

import re
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from collections import Counter
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from datetime import datetime

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
        self.model = None
        self.tfidf_vectorizer = None
        self.lemmatizer = WordNetLemmatizer()
        self.stop_words = set(stopwords.words('english'))
        
        # Simple sentiment lexicon (could be expanded with a proper lexicon file)
        self.positive_words = {
            'good', 'great', 'excellent', 'delicious', 'awesome', 'amazing',
            'wonderful', 'fantastic', 'tasty', 'friendly', 'fresh', 'love',
            'best', 'perfect', 'enjoyed', 'pleasant', 'recommend', 'quality',
            'clean', 'fast', 'efficient', 'helpful', 'nice', 'comfortable',
            'favorite', 'reasonable', 'worth', 'satisfaction', 'satisfied',
            'happy', 'joy', 'convenient', 'polite', 'professional', 'exceptional'
        }
        
        self.negative_words = {
            'bad', 'poor', 'terrible', 'awful', 'disappointing', 'worst',
            'horrible', 'rude', 'slow', 'dirty', 'expensive', 'overpriced',
            'cold', 'bland', 'tasteless', 'mediocre', 'waste', 'stale',
            'unfriendly', 'unpleasant', 'unhelpful', 'unprofessional', 'amateur',
            'wrong', 'mistake', 'error', 'complaint', 'noisy', 'uncomfortable',
            'wait', 'delay', 'crowded', 'bitter', 'annoying', 'disappointed'
        }
        
        # Training data for model (if available)
        self.training_data = []
        self.training_labels = []
        
        # Try to train initial model from DB data
        self.train_from_existing_reviews()
    
    def preprocess_text(self, text):
        """Clean and tokenize text"""
        # Convert to lowercase
        text = text.lower()
        
        # Remove punctuation and numbers
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\d+', '', text)
        
        # Tokenize
        tokens = word_tokenize(text)
        
        # Remove stopwords and lemmatize
        tokens = [self.lemmatizer.lemmatize(token) for token in tokens 
                 if token not in self.stop_words]
        
        return tokens
    
    def analyze_sentiment_lexicon(self, text):
        """Analyze sentiment using lexicon-based approach"""
        tokens = self.preprocess_text(text)
        
        # Count positive and negative words
        positive_count = sum(1 for token in tokens if token in self.positive_words)
        negative_count = sum(1 for token in tokens if token in self.negative_words)
        
        # Calculate sentiment score
        total_words = len(tokens)
        if total_words == 0:
            return {'score': 0, 'label': 'neutral'}
        
        score = (positive_count - negative_count) / total_words
        
        # Determine sentiment label
        if score > 0.1:
            label = 'positive'
        elif score < -0.1:
            label = 'negative'
        else:
            label = 'neutral'
        
        return {
            'score': score,
            'label': label,
            'positive_words': positive_count,
            'negative_words': negative_count,
            'total_words': total_words
        }
    
    def train_from_existing_reviews(self):
        """Train model from existing reviews in database"""
        try:
            from models import Review
            from app import db
            
            # Get reviews with ratings
            reviews = db.session.query(Review).all()
            
            if len(reviews) < 10:  # Not enough data to train a model
                return False
            
            for review in reviews:
                if not review.content:
                    continue
                
                # Use rating as a proxy for sentiment
                label = 1 if review.rating >= 4 else 0  # Binary for simplicity
                
                self.training_data.append(review.content)
                self.training_labels.append(label)
            
            # Train a model if we have enough data
            if len(self.training_data) >= 10:
                self.train_model()
                return True
            
            return False
            
        except Exception as e:
            print(f"Error training from existing reviews: {e}")
            return False
    
    def train_model(self):
        """Train a machine learning model for sentiment analysis"""
        if len(self.training_data) < 10:
            return False
        
        try:
            # Create TF-IDF vectors
            self.tfidf_vectorizer = TfidfVectorizer(max_features=1000)
            X = self.tfidf_vectorizer.fit_transform(self.training_data)
            y = np.array(self.training_labels)
            
            # Train logistic regression model
            self.model = LogisticRegression(max_iter=1000)
            self.model.fit(X, y)
            
            return True
        except Exception as e:
            print(f"Error training model: {e}")
            return False
    
    def analyze_sentiment_ml(self, text):
        """Analyze sentiment using machine learning model if available"""
        if self.model is None or self.tfidf_vectorizer is None:
            return None
        
        try:
            # Transform text using TF-IDF
            X = self.tfidf_vectorizer.transform([text])
            
            # Predict sentiment
            prediction = self.model.predict(X)[0]
            probability = self.model.predict_proba(X)[0]
            
            # Convert to sentiment label
            label = 'positive' if prediction == 1 else 'negative'
            confidence = probability[1] if prediction == 1 else probability[0]
            
            return {
                'label': label,
                'confidence': float(confidence),
                'method': 'machine_learning'
            }
        except Exception as e:
            print(f"Error using ML model: {e}")
            return None
    
    def analyze_sentiment(self, text):
        """Analyze sentiment using both methods (ML preferred if available)"""
        # Try ML-based approach first
        ml_result = self.analyze_sentiment_ml(text)
        
        if ml_result:
            return ml_result
        
        # Fall back to lexicon-based approach
        lexicon_result = self.analyze_sentiment_lexicon(text)
        lexicon_result['method'] = 'lexicon'
        
        return lexicon_result
    
    def track_sentiment(self, review_id, sentiment_data):
        """Store sentiment analysis result in database"""
        try:
            from models import SentimentAnalysis
            from app import db
            
            # Check if analysis exists
            existing = db.session.query(SentimentAnalysis).filter_by(
                review_id=review_id).first()
            
            if existing:
                # Update existing record
                existing.sentiment_score = sentiment_data.get('score', 0)
                existing.sentiment_label = sentiment_data.get('label', 'neutral')
                existing.analyzed_at = datetime.utcnow()
            else:
                # Create new record
                analysis = SentimentAnalysis(
                    review_id=review_id,
                    sentiment_score=sentiment_data.get('score', 0),
                    sentiment_label=sentiment_data.get('label', 'neutral'),
                    analyzed_at=datetime.utcnow()
                )
                db.session.add(analysis)
            
            db.session.commit()
            return True
        except Exception as e:
            print(f"Error tracking sentiment: {e}")
            return False
    
    def get_recent_sentiment_trends(self, days=30, limit=100):
        """Get sentiment trends for recent reviews"""
        try:
            from models import Review, SentimentAnalysis
            from app import db
            from sqlalchemy import func
            from datetime import datetime, timedelta
            
            # Calculate date threshold
            threshold = datetime.utcnow() - timedelta(days=days)
            
            # Get sentiment counts by day
            query = db.session.query(
                func.date(Review.created_at).label('date'),
                SentimentAnalysis.sentiment_label,
                func.count().label('count')
            ).join(
                SentimentAnalysis, 
                Review.id == SentimentAnalysis.review_id
            ).filter(
                Review.created_at >= threshold
            ).group_by(
                func.date(Review.created_at),
                SentimentAnalysis.sentiment_label
            ).order_by(
                func.date(Review.created_at).desc()
            ).limit(limit)
            
            results = query.all()
            
            # Format results
            trends = {}
            for date, label, count in results:
                if date not in trends:
                    trends[date] = {'positive': 0, 'negative': 0, 'neutral': 0}
                trends[date][label] = count
            
            return trends
        except Exception as e:
            print(f"Error getting sentiment trends: {e}")
            return {}


# Singleton instance
sentiment_analyzer = None

def init_sentiment_analyzer():
    """Initialize the sentiment analyzer"""
    global sentiment_analyzer
    sentiment_analyzer = SentimentAnalyzer()
    return sentiment_analyzer

def analyze_review_sentiment(review_text, review_id=None):
    """Analyze sentiment of review text and optionally store result"""
    if sentiment_analyzer is None:
        init_sentiment_analyzer()
    
    sentiment_data = sentiment_analyzer.analyze_sentiment(review_text)
    
    if review_id is not None:
        sentiment_analyzer.track_sentiment(review_id, sentiment_data)
    
    return sentiment_data

def get_sentiment_trends(days=30):
    """Get sentiment trends for the specified time period"""
    if sentiment_analyzer is None:
        init_sentiment_analyzer()
    
    return sentiment_analyzer.get_recent_sentiment_trends(days)