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
from flask import current_app
import logging

def get_logger():
    if current_app:
        return current_app.logger
    else:
        logger = logging.getLogger('sentiment_analyzer')
        if not logger.hasHandlers():
            log_format = '%(asctime)s - %(levelname)s - SENTIMENT - %(message)s'
            logging.basicConfig(level=logging.INFO, format=log_format)
        return logger

def download_nltk_data():
    logger = get_logger()
    data_to_download = ['punkt', 'stopwords', 'wordnet']
    for item in data_to_download:
        try:
            nltk.data.find(f'tokenizers/{item}' if item=='punkt' else f'corpora/{item}')
        except LookupError:
            logger.info(f"Downloading NLTK data: {item}")
            try:
                nltk.download(item, quiet=True)
            except Exception as e:
                logger.error(f"Failed to download NLTK data '{item}': {e}")

class SentimentAnalyzer:
    def __init__(self):
        self.logger = get_logger()

        try:
            download_nltk_data()
            self.lemmatizer = WordNetLemmatizer()
            self.stop_words = set(stopwords.words('english'))
        except Exception as e:
            self.logger.error(f"Failed to initialize NLTK components: {e}", exc_info=True)


        self.sentiment_lexicon = {
            'positive': [
                'good', 'great', 'excellent', 'amazing', 'awesome', 'delicious', 'tasty',
                'nice', 'love', 'like', 'enjoy', 'wonderful', 'perfect', 'fantastic',
                'fresh', 'pleasant', 'satisfied', 'happy', 'best', 'favorite',
                'recommended', 'affordable', 'friendly', 'attentive', 'quick', 'clean',
                'comfortable', 'convenient', 'impressed',
                'ngon', 'tuyệt', 'tốt', 'thích', 'yêu', 'thơm', 'đáng giá', 'hài lòng',
                'sạch sẽ', 'dễ chịu', 'nhiệt tình', 'nhanh', 'chất lượng', 'giá tốt',
                'tươi', 'hoàn hảo', 'ấm cúng', 'gần gũi', 'vui vẻ', 'khuyến khích',
                'nổi bật', 'độc đáo', 'đặc biệt', 'chuyên nghiệp', 'hấp dẫn'
            ],
            'negative': [
                'bad', 'terrible', 'awful', 'horrible', 'poor', 'worst', 'disappointing',
                'disappointed', 'slow', 'rude', 'cold', 'stale', 'expensive',
                'overpriced', 'dirty', 'unclean', 'uncomfortable', 'mediocre', 'bland',
                'bitter', 'burnt', 'tasteless', 'unfriendly', 'unhelpful', 'long wait',
                'crowded', 'noisy', 'unhygienic',
                'dở', 'tệ', 'không ngon', 'chán', 'đắt', 'lâu', 'chậm', 'bẩn',
                'không sạch', 'đông', 'ồn', 'khó chịu', 'thất vọng', 'lạnh',
                'cũ', 'khó ăn', 'không tươi', 'nhạt', 'không đáng giá', 'thiếu',
                'không hài lòng', 'không chuyên nghiệp', 'thiếu nhiệt tình', 'khó uống'
            ]
        }

        self.intensifiers = [
            'very', 'really', 'extremely', 'incredibly', 'absolutely', 'totally',
            'completely', 'highly', 'especially', 'particularly', 'most', 'rất',
            'cực kỳ', 'vô cùng', 'quá', 'siêu', 'cực', 'đặc biệt', 'vô cùng'
        ]

        self.negation_words = [
            'not', 'no', 'never', 'none', "don't", "doesn't", "didn't", "won't",
            "wouldn't", "couldn't", "shouldn't", "haven't", "hasn't", "hadn't",
            'cannot', "can't", 'nor', 'neither', 'không', 'chẳng', 'đừng',
            'không hề', 'không bao giờ', 'chẳng có gì'
        ]

        self.TOXIC_KEYWORDS = {
            'chửi thề': [
                'đm', 'dm', 'dcm', 'vcl', 'vl', 'lồn', 'loz', 'cak', 'cac', 'cặc',
                'địt', 'dit', 'địt mẹ', 'dit me', 'đit me', 'đờ mờ',
                'ngu', 'óc chó', 'đồ điên', 'thần kinh', 'điên à', 'chó', 'má mày', 'ml', 'cc',
                'fuck', 'fucking', 'shit', 'bitch', 'damn', 'asshole', 'đệt', 'ditme', 'dmm',
                'cứt'
                ],
            'đe dọa': ['giết', 'đánh', 'xử', 'bem', 'chặt', 'đập chết', 'coi chừng', 'biết tay', 'xử lý mày'],
            'xúc phạm nặng': [
                'kinh tởm', 'ghê tởm', 'rác rưởi', 'cặn bã', 'cút mẹ', 'biến mẹ', 'thú vật', 'súc vật',
                'nứng lồn', 'bú cặc', 'ngậm lồn', 'cave', 'đĩ', 'phò',
                'dơ vãi', 'bẩn vãi'
                ]
        }
        self.TOXIC_SENTIMENT_THRESHOLD = -0.1

        self.model_dir = os.path.join(os.path.dirname(__file__), 'models')
        os.makedirs(self.model_dir, exist_ok=True)
        self.model_path = os.path.join(self.model_dir, 'sentiment_model.joblib')
        self.vectorizer_path = os.path.join(self.model_dir, 'sentiment_vectorizer.joblib')

        self.ml_model = None
        self.vectorizer = None
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.vectorizer_path):
                self.ml_model = joblib.load(self.model_path)
                self.vectorizer = joblib.load(self.vectorizer_path)
                self.logger.info("Loaded sentiment analysis model from files.")
        except Exception as e:
            self.logger.error(f"Error loading sentiment model: {e}", exc_info=True)

    def preprocess_text(self, text):
        if not text: return []
        text = str(text).lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\d+', ' ', text)
        tokens = word_tokenize(text)
        tokens = [self.lemmatizer.lemmatize(token) for token in tokens
                 if token.isalpha() and token not in self.stop_words]
        return tokens

    def analyze_sentiment_lexicon(self, text):
        tokens = self.preprocess_text(text)
        if not tokens:
            return {'sentiment_score': 0, 'confidence': 0, 'method': 'lexicon', 'positive_words': 0, 'negative_words': 0}
        positive_count = 0
        negative_count = 0
        ngrams = []
        for i in range(len(tokens)):
            if i < len(tokens) - 1:
                ngrams.append(tokens[i] + ' ' + tokens[i+1])
        negation_active = False
        for i, token in enumerate(tokens):
            if token in self.negation_words:
                negation_active = True
                continue
            if negation_active and token not in self.sentiment_lexicon['positive'] and token not in self.sentiment_lexicon['negative']:
                if not (i > 0 and tokens[i-1] in self.negation_words) and not (i > 1 and tokens[i-2] in self.negation_words) and not (i > 2 and tokens[i-3] in self.negation_words):
                    negation_active = False
            intensifier = 1.5 if token in self.intensifiers else 1.0
            current_token_score = 0
            if token in self.sentiment_lexicon['positive']:
                current_token_score = 1 * intensifier
                if negation_active:
                    negative_count += abs(current_token_score)
                    negation_active = False
                else:
                    positive_count += current_token_score
            elif token in self.sentiment_lexicon['negative']:
                current_token_score = -1 * intensifier
                if negation_active:
                    positive_count += abs(current_token_score)
                    negation_active = False
                else:
                    negative_count += abs(current_token_score)
        for ngram in ngrams:
            if ngram in self.sentiment_lexicon['positive']:
                positive_count += 1.5
            elif ngram in self.sentiment_lexicon['negative']:
                negative_count += 1.5
        total_magnitude = positive_count + negative_count
        if total_magnitude == 0:
            sentiment_score = 0
            confidence = 0.1
        else:
            sentiment_score = (positive_count - negative_count) / total_magnitude
            confidence = min(0.9, (total_magnitude / max(1, len(tokens))) * 1.5)
        return {'sentiment_score': sentiment_score, 'confidence': round(confidence, 2), 'method': 'lexicon', 'positive_words': round(positive_count, 1), 'negative_words': round(negative_count, 1)}

    def train_from_existing_reviews(self):
        from models import Review
        if not hasattr(self, 'db') or not self.db:
             self.logger.error("Database instance 'self.db' not set for training.")
             return False
        self.logger.info("Attempting to train sentiment model from existing reviews...")
        try:
            reviews = self.db.session.query(Review).filter(Review.content != None, Review.content != '').all()
            if not reviews or len(reviews) < 20:
                self.logger.warning(f"Not enough reviews ({len(reviews)}) to train sentiment model. Minimum 20 required.")
                return False
            texts = [review.content for review in reviews]
            ratings = [review.rating for review in reviews]
            sentiments = []
            for rating in ratings:
                if rating <= 2: sentiments.append('negative')
                elif rating == 3: sentiments.append('neutral')
                else: sentiments.append('positive')
            return self.train_model(texts, sentiments)
        except Exception as e:
             self.logger.error(f"Error during training from existing reviews: {e}", exc_info=True)
             return False

    def train_model(self, texts=None, sentiments=None):
        if texts is None or sentiments is None:
             self.logger.info("No training data provided, using default sample data.")
             texts = ["Coffee excellent, service quick.", "Great atmosphere, delicious pastries.", "Staff friendly helpful.", "Best coffee shop town, highly recommended!", "Reasonable prices, great quality.", "Coffee cold, service slow.", "Overpriced mediocre quality.", "Staff rude unhelpful.", "Disappointed experience, won't return.", "Dirty tables, poor hygiene.", "Average coffee, nothing special.", "Place crowded noisy.", "OK experience better options.", "WiFi slow coffee good.", "Decent coffee expensive.", "Cà phê ngon nhân viên nhiệt tình.", "Không gian đẹp, đồ uống tuyệt vời.", "Quán sạch sẽ thoải mái.", "Giá hợp lý, chất lượng tốt.", "Cà phê ngon nhất khu vực!", "Cà phê nguội phục vụ chậm.", "Đắt chất lượng trung bình.", "Nhân viên không nhiệt tình.", "Thất vọng, không quay lại nữa.", "Bàn ghế bẩn vệ sinh kém."]
             sentiments = ['positive', 'positive', 'positive', 'positive', 'positive', 'negative', 'negative', 'negative', 'negative', 'negative', 'neutral', 'neutral', 'neutral', 'neutral', 'neutral', 'positive', 'positive', 'positive', 'positive', 'positive', 'negative', 'negative', 'negative', 'negative', 'negative']
        if len(texts) != len(sentiments):
             self.logger.error("Training data length mismatch.")
             return False
        self.logger.info(f"Starting ML model training with {len(texts)} samples...")
        try:
            self.vectorizer = TfidfVectorizer(max_features=1000, ngram_range=(1, 2), min_df=1)
            X = self.vectorizer.fit_transform(texts)
            self.ml_model = LogisticRegression(C=10, max_iter=1000, class_weight='balanced')
            self.ml_model.fit(X, sentiments)
            joblib.dump(self.ml_model, self.model_path)
            joblib.dump(self.vectorizer, self.vectorizer_path)
            self.logger.info(f"Sentiment analysis model and vectorizer saved to {self.model_dir}")
            return True
        except Exception as e:
            self.logger.error(f"Error during ML model training: {e}", exc_info=True)
            return False

    def analyze_sentiment_ml(self, text):
        if not self.ml_model or not self.vectorizer: return None
        try:
            X = self.vectorizer.transform([text])
            sentiment_label = self.ml_model.predict(X)[0]
            proba = self.ml_model.predict_proba(X)[0]
            confidence = max(proba)
            if sentiment_label == 'positive': score = confidence * 0.5 + 0.5
            elif sentiment_label == 'negative': score = -(confidence * 0.5 + 0.5)
            else: score = (proba[list(self.ml_model.classes_).index('positive')] - proba[list(self.ml_model.classes_).index('negative')]) * 0.3
            return {'sentiment_label': sentiment_label, 'sentiment_score': round(score, 2), 'confidence': round(confidence, 2), 'method': 'ml_model'}
        except Exception as e:
            self.logger.error(f"Error in ML sentiment analysis: {e}", exc_info=True)
            return None

    def _is_content_toxic(self, text_lower, sentiment_score):
        found_toxic_keyword = False
        found_category = None
        priority_categories = ['chửi thề', 'đe dọa', 'xúc phạm nặng']
        for category in priority_categories:
            keywords = self.TOXIC_KEYWORDS.get(category, [])
            for keyword in keywords:
                try:
                    pattern = r'\b' + re.escape(keyword) + r'\b'
                    if re.search(pattern, text_lower, re.IGNORECASE):
                        found_toxic_keyword = True
                        found_category = category
                        self.logger.warning(f"Toxic keyword match: '{keyword}' (Category: '{category}')")
                        break
                except Exception as regex_e:
                    self.logger.error(f"Regex error for keyword '{keyword}': {regex_e}")
            if found_toxic_keyword:
                break
        if found_toxic_keyword:
            self.logger.info(f"Content flagged toxic due to keyword category: '{found_category}' or other match.")
            return True
        return False

    def analyze_sentiment(self, text):
        ml_result = self.analyze_sentiment_ml(text)
        lexicon_result = self.analyze_sentiment_lexicon(text)
        final_result = {}
        ML_CONFIDENCE_THRESHOLD = 0.6
        if ml_result and ml_result['confidence'] >= ML_CONFIDENCE_THRESHOLD:
            final_result = ml_result
        else:
            final_result = lexicon_result
            score = final_result['sentiment_score']
            if score > 0.35: final_result['sentiment_label'] = 'positive'
            elif score < -0.35: final_result['sentiment_label'] = 'negative'
            else: final_result['sentiment_label'] = 'neutral'
        text_for_check = text.lower() if text else ""
        is_toxic_flag = self._is_content_toxic(text_for_check, final_result.get('sentiment_score', 0.0))
        final_result['is_toxic'] = is_toxic_flag
        if is_toxic_flag:
             if final_result.get('sentiment_label') != 'negative':
                 final_result['sentiment_label'] = 'negative'
                 final_result['sentiment_score'] = min(final_result.get('sentiment_score', 0.0), -0.75)
                 self.logger.info("Content flagged as toxic, sentiment adjusted to negative.")
        final_result.setdefault('sentiment_score', 0.0)
        final_result.setdefault('sentiment_label', 'neutral')
        final_result.setdefault('confidence', final_result.get('confidence', 0.0))
        final_result.setdefault('method', final_result.get('method', 'lexicon'))
        return final_result

    def get_recent_sentiment_trends(self, days=30, limit=100):
        from models import Review
        from sqlalchemy import func, case
        if not hasattr(self, 'db') or not self.db:
             self.logger.error("Database instance 'self.db' not set for getting trends.")
             return []
        self.logger.info(f"Fetching sentiment trends for the last {days} days...")
        try:
            threshold = datetime.utcnow() - timedelta(days=days)
            trends_query = self.db.session.query(
                func.date(Review.created_at).label('review_date'),
                func.count(Review.id).label('review_count'),
                func.avg(Review.rating).label('avg_rating'),
                func.avg(Review.sentiment_score).label('avg_sentiment_score'),
                func.sum(case((Review.sentiment_label == 'positive', 1), else_=0)).label('positive_count'),
                func.sum(case((Review.sentiment_label == 'negative', 1), else_=0)).label('negative_count'),
                func.sum(case((Review.sentiment_label == 'neutral', 1), else_=0)).label('neutral_count')
            ).filter(Review.created_at >= threshold, Review.sentiment_label != None)\
             .group_by(func.date(Review.created_at))\
             .order_by(func.date(Review.created_at).desc())\
             .limit(limit)
            results = trends_query.all()
            trends = []
            for row in results:
                trends.append({'date': row.review_date.strftime('%Y-%m-%d'), 'review_count': int(row.review_count), 'avg_rating': float(row.avg_rating) if row.avg_rating else 0, 'avg_sentiment_score': float(row.avg_sentiment_score) if row.avg_sentiment_score else 0, 'positive_count': int(row.positive_count), 'negative_count': int(row.negative_count), 'neutral_count': int(row.neutral_count)})
            self.logger.info(f"Successfully fetched {len(trends)} trend data points.")
            return trends
        except Exception as e:
            self.logger.error(f"Error getting sentiment trends: {e}", exc_info=True)
            return []

sentiment_analyzer = None

def init_sentiment_analyzer(db_instance=None):
    global sentiment_analyzer
    if sentiment_analyzer is None:
        sentiment_analyzer = SentimentAnalyzer()
        if db_instance:
             sentiment_analyzer.db = db_instance
    elif db_instance and not hasattr(sentiment_analyzer, 'db'):
         sentiment_analyzer.db = db_instance
    return sentiment_analyzer

def analyze_review_sentiment(review_text):
    logger = get_logger()
    if sentiment_analyzer is None:
        logger.error("Sentiment Analyzer not initialized before calling analyze_review_sentiment.")
        return {'sentiment_label': 'neutral', 'sentiment_score': 0.0, 'confidence': 0.0, 'method':'error', 'is_toxic': False}
    return sentiment_analyzer.analyze_sentiment(review_text)

def get_sentiment_trends(days=30):
    logger = get_logger()
    if sentiment_analyzer is None or not hasattr(sentiment_analyzer, 'db'):
        from app import db
        init_sentiment_analyzer(db)
    return sentiment_analyzer.get_recent_sentiment_trends(days)