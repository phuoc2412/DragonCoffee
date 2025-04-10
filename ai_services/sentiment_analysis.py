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
from flask import current_app # Để ghi log an toàn trong môi trường Flask

# Ensure NLTK resources are downloaded (chỉ chạy 1 lần khi cần)
def download_nltk_data():
    data_to_download = ['punkt', 'stopwords', 'wordnet']
    for item in data_to_download:
        try:
            nltk.data.find(f'tokenizers/{item}' if item=='punkt' else f'corpora/{item}')
        except LookupError:
            print(f"Downloading NLTK data: {item}")
            nltk.download(item)

# download_nltk_data() # Gọi hàm này nếu bạn chạy script độc lập lần đầu

class SentimentAnalyzer:
    def __init__(self):
        """Initialize sentiment analyzer with basic lexicon-based approach"""
        self.logger = current_app.logger if current_app else print # Sử dụng logger

        try:
            download_nltk_data() # Đảm bảo dữ liệu nltk có sẵn
            self.lemmatizer = WordNetLemmatizer()
            self.stop_words = set(stopwords.words('english')) # Thêm tiếng Việt nếu cần xử lý TV tốt hơn
        except Exception as e:
            self.logger.error(f"Failed to initialize NLTK components: {e}", exc_info=True)
            # Handle error appropriately, maybe raise or disable the analyzer

        # Sentiment lexicon
        self.sentiment_lexicon = {
            'positive': [
                'good', 'great', 'excellent', 'amazing', 'awesome', 'delicious', 'tasty',
                'nice', 'love', 'like', 'enjoy', 'wonderful', 'perfect', 'fantastic',
                'fresh', 'pleasant', 'satisfied', 'happy', 'best', 'favorite',
                'recommended', 'affordable', 'friendly', 'attentive', 'quick', 'clean',
                'comfortable', 'convenient', 'impressed',
                # Tiếng Việt
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
                # Tiếng Việt
                'dở', 'tệ', 'không ngon', 'chán', 'đắt', 'lâu', 'chậm', 'bẩn',
                'không sạch', 'đông', 'ồn', 'khó chịu', 'thất vọng', 'lạnh',
                'cũ', 'khó ăn', 'không tươi', 'nhạt', 'không đáng giá', 'thiếu',
                'không hài lòng', 'không chuyên nghiệp', 'thiếu nhiệt tình', 'khó uống'
            ]
        }

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
        self.model_dir = os.path.join(os.path.dirname(__file__), 'models')
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
                self.logger.info("Loaded sentiment analysis model from files.") # Sửa logger
        except Exception as e:
            self.logger.error(f"Error loading sentiment model: {e}", exc_info=True) # Sửa logger

    # --- CÁC PHƯƠNG THỨC ĐỊNH NGHĨA Ở CẤP ĐỘ CLASS ---

    def preprocess_text(self, text):
        """Clean and tokenize text"""
        if not text: return [] # Trả về list rỗng nếu text đầu vào rỗng
        text = str(text).lower() # Đảm bảo là string và lowercase
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\d+', ' ', text)
        tokens = word_tokenize(text)
        tokens = [self.lemmatizer.lemmatize(token) for token in tokens
                 if token.isalpha() and token not in self.stop_words] # Chỉ giữ lại chữ và không phải stopword
        return tokens

    def analyze_sentiment_lexicon(self, text):
        """Analyze sentiment using lexicon-based approach"""
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
            # Chỉ reset negation nếu token hiện tại không phải là từ sentiment
            # (cho phép cụm "not good not bad")
            if negation_active and token not in self.sentiment_lexicon['positive'] and token not in self.sentiment_lexicon['negative']:
                # Có thể giới hạn số từ reset, ví dụ: sau 2-3 từ
                if i > 0 and tokens[i-1] in self.negation_words: pass # Không reset ngay sau từ phủ định
                elif (i > 1 and tokens[i-2] in self.negation_words) or (i > 2 and tokens[i-3] in self.negation_words): pass # Reset sau 2 hoặc 3 từ
                else: negation_active = False


            intensifier = 1.0
            if token in self.intensifiers:
                intensifier = 1.5 # Tăng trọng số hơn một chút
                # Không 'continue' ở đây, từ 'very good' thì 'good' vẫn cần được tính
                # Cần xử lý logic xem intensifier áp dụng cho từ nào tiếp theo, ở đây làm đơn giản

            current_token_score = 0
            if token in self.sentiment_lexicon['positive']:
                current_token_score = 1 * intensifier
                if negation_active:
                    negative_count += abs(current_token_score) # Phủ định -> thành tiêu cực
                    negation_active = False # Reset sau khi áp dụng
                else:
                    positive_count += current_token_score
            elif token in self.sentiment_lexicon['negative']:
                current_token_score = -1 * intensifier
                if negation_active:
                    positive_count += abs(current_token_score) # Phủ định -> thành tích cực
                    negation_active = False # Reset sau khi áp dụng
                else:
                    negative_count += abs(current_token_score) # Tính điểm tuyệt đối âm

            # Reset intensifier sau khi dùng (hoặc logic phức tạp hơn)
            if token in self.intensifiers: intensifier = 1.0

        # Check ngrams
        for ngram in ngrams:
            if ngram in self.sentiment_lexicon['positive']:
                positive_count += 1.5
            elif ngram in self.sentiment_lexicon['negative']:
                negative_count += 1.5

        total_magnitude = positive_count + negative_count
        if total_magnitude == 0:
            sentiment_score = 0
            confidence = 0.1 # Độ tin cậy thấp nếu không có từ cảm xúc
        else:
            # Điểm từ -1 đến 1
            sentiment_score = (positive_count - negative_count) / total_magnitude
            # Độ tin cậy dựa trên số lượng từ cảm xúc / tổng số từ (đã qua xử lý)
            confidence = min(0.9, (total_magnitude / max(1, len(tokens))) * 1.5) # Tăng nhẹ hệ số

        return {
            'sentiment_score': sentiment_score,
            'confidence': round(confidence, 2), # Làm tròn
            'method': 'lexicon',
            'positive_words': round(positive_count, 1),
            'negative_words': round(negative_count, 1)
        }

    def train_from_existing_reviews(self):
        """Train model from existing reviews in database"""
        from models import Review # Import model ở đây
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
        """Train a machine learning model for sentiment analysis. Uses default data if none provided."""
        if texts is None or sentiments is None:
             # Sử dụng dữ liệu mẫu nếu không có dữ liệu nào được cung cấp
             self.logger.info("No training data provided, using default sample data.")
             texts = [
                "Coffee excellent, service quick.", "Great atmosphere, delicious pastries.",
                "Staff friendly helpful.", "Best coffee shop town, highly recommended!",
                "Reasonable prices, great quality.", "Coffee cold, service slow.",
                "Overpriced mediocre quality.", "Staff rude unhelpful.",
                "Disappointed experience, won't return.", "Dirty tables, poor hygiene.",
                "Average coffee, nothing special.", "Place crowded noisy.",
                "OK experience better options.", "WiFi slow coffee good.",
                "Decent coffee expensive.", "Cà phê ngon nhân viên nhiệt tình.",
                "Không gian đẹp, đồ uống tuyệt vời.", "Quán sạch sẽ thoải mái.",
                "Giá hợp lý, chất lượng tốt.", "Cà phê ngon nhất khu vực!",
                "Cà phê nguội phục vụ chậm.", "Đắt chất lượng trung bình.",
                "Nhân viên không nhiệt tình.", "Thất vọng, không quay lại nữa.",
                "Bàn ghế bẩn vệ sinh kém."
            ]
             sentiments = [
                'positive', 'positive', 'positive', 'positive', 'positive', 'negative',
                'negative', 'negative', 'negative', 'negative', 'neutral', 'neutral',
                'neutral', 'neutral', 'neutral', 'positive', 'positive', 'positive',
                'positive', 'positive', 'negative', 'negative', 'negative', 'negative', 'negative'
            ]

        if len(texts) != len(sentiments):
             self.logger.error("Training data length mismatch: texts and sentiments must have the same number of items.")
             return False

        self.logger.info(f"Starting ML model training with {len(texts)} samples...")
        try:
            self.vectorizer = TfidfVectorizer(
                max_features=1000, ngram_range=(1, 2), min_df=1 # Giảm min_df nếu dữ liệu ít
            )
            X = self.vectorizer.fit_transform(texts)
            self.ml_model = LogisticRegression(C=10, max_iter=1000, class_weight='balanced') # Thêm class_weight
            self.ml_model.fit(X, sentiments)

            joblib.dump(self.ml_model, self.model_path)
            joblib.dump(self.vectorizer, self.vectorizer_path)
            self.logger.info(f"Sentiment analysis model and vectorizer saved to {self.model_dir}") # Sửa logger
            return True
        except Exception as e:
            self.logger.error(f"Error during ML model training: {e}", exc_info=True) # Sửa logger
            return False

    def analyze_sentiment_ml(self, text):
        """Analyze sentiment using machine learning model if available"""
        if not self.ml_model or not self.vectorizer:
            return None # Trả về None nếu model chưa sẵn sàng

        try:
            X = self.vectorizer.transform([text])
            sentiment_label = self.ml_model.predict(X)[0]
            proba = self.ml_model.predict_proba(X)[0]
            confidence = max(proba)
            class_index = list(self.ml_model.classes_).index(sentiment_label)

            # Ước lượng điểm số dựa trên nhãn và xác suất (ví dụ đơn giản)
            if sentiment_label == 'positive':
                 score = confidence * 0.5 + 0.5 # Map confidence (0.33-1) to score (0.66-1) approx.
            elif sentiment_label == 'negative':
                 score = -(confidence * 0.5 + 0.5) # Map confidence (0.33-1) to score (-0.66 to -1) approx.
            else: # neutral
                 score = (proba[list(self.ml_model.classes_).index('positive')] - \
                          proba[list(self.ml_model.classes_).index('negative')]) * 0.3 # Điểm gần 0 hơn

            return {
                'sentiment_label': sentiment_label,
                'sentiment_score': round(score, 2), # Điểm số ước lượng
                'confidence': round(confidence, 2),
                'method': 'ml_model'
                # 'rating' key sẽ được thêm trong hàm analyze_sentiment nếu cần
            }
        except Exception as e:
            self.logger.error(f"Error in ML sentiment analysis: {e}", exc_info=True) # Sửa logger
            return None

    # --- **ĐÂY LÀ HÀM analyze_sentiment ĐÃ SỬA LỖI THỤT LỀ** ---
    def analyze_sentiment(self, text):
        """Analyze sentiment using both methods (ML preferred) and return score + label."""
        ml_result = self.analyze_sentiment_ml(text)
        lexicon_result = self.analyze_sentiment_lexicon(text)

        final_result = {}

        # Ngưỡng tin cậy để dùng ML model
        ML_CONFIDENCE_THRESHOLD = 0.6

        if ml_result and ml_result['confidence'] >= ML_CONFIDENCE_THRESHOLD:
            final_result = ml_result # Ưu tiên kết quả ML
            # self.logger.info(f"Using ML result for sentiment (conf: {ml_result['confidence']:.2f})") # Optional log
        else:
            # Dùng lexicon nếu ML không tự tin hoặc không có
            final_result = lexicon_result # Lấy score và method từ lexicon
             # Xác định label từ score của lexicon
            score = final_result['sentiment_score']
            if score > 0.35: # Tăng ngưỡng positive
                final_result['sentiment_label'] = 'positive'
            elif score < -0.35: # Tăng ngưỡng negative (âm hơn)
                final_result['sentiment_label'] = 'negative'
            else:
                final_result['sentiment_label'] = 'neutral'
            # self.logger.info(f"Using Lexicon result for sentiment (ML conf: {ml_result['confidence'] if ml_result else 'N/A'})") # Optional log


        # Đảm bảo các key cần thiết luôn tồn tại trong kết quả trả về
        final_result.setdefault('sentiment_score', 0.0)
        final_result.setdefault('sentiment_label', 'neutral')
        final_result.setdefault('confidence', 0.0)
        final_result.setdefault('method', 'unknown')

        return final_result
    # --- KẾT THÚC HÀM analyze_sentiment ---

    # Bỏ hàm track_sentiment vì lưu trực tiếp vào Review
    # def track_sentiment(self, review_id, sentiment_data): ...

    def get_recent_sentiment_trends(self, days=30, limit=100):
        """Get sentiment trends for recent reviews using sentiment saved in Review table."""
        from models import Review # Import model
        from sqlalchemy import func, case

        if not hasattr(self, 'db') or not self.db:
             self.logger.error("Database instance 'self.db' not set for getting trends.")
             return []

        self.logger.info(f"Fetching sentiment trends for the last {days} days...")
        try:
            threshold = datetime.utcnow() - timedelta(days=days)
            # Query trực tiếp từ bảng Review
            trends_query = self.db.session.query(
                func.date(Review.created_at).label('review_date'),
                func.count(Review.id).label('review_count'),
                func.avg(Review.rating).label('avg_rating'),
                # Tính avg_sentiment_score dựa trên sentiment_score đã lưu
                func.avg(Review.sentiment_score).label('avg_sentiment_score'),
                # Đếm số lượng positive/negative/neutral
                func.sum(case((Review.sentiment_label == 'positive', 1), else_=0)).label('positive_count'),
                func.sum(case((Review.sentiment_label == 'negative', 1), else_=0)).label('negative_count'),
                func.sum(case((Review.sentiment_label == 'neutral', 1), else_=0)).label('neutral_count')
            ).filter(
                Review.created_at >= threshold,
                Review.sentiment_label != None # Chỉ tính các review đã được phân tích
            ).group_by(
                func.date(Review.created_at)
            ).order_by(
                func.date(Review.created_at).desc()
            ).limit(limit)

            results = trends_query.all()

            # Format results
            trends = []
            for row in results:
                trends.append({
                    'date': row.review_date.strftime('%Y-%m-%d'),
                    'review_count': int(row.review_count),
                    'avg_rating': float(row.avg_rating) if row.avg_rating else 0,
                    'avg_sentiment_score': float(row.avg_sentiment_score) if row.avg_sentiment_score else 0,
                    'positive_count': int(row.positive_count),
                    'negative_count': int(row.negative_count),
                    'neutral_count': int(row.neutral_count)
                })

            self.logger.info(f"Successfully fetched {len(trends)} trend data points.")
            return trends
        except Exception as e:
            self.logger.error(f"Error getting sentiment trends: {e}", exc_info=True)
            return []


# --- Singleton instance (giữ nguyên) ---
sentiment_analyzer = None

def init_sentiment_analyzer(db_instance=None): # Thêm tham số db (tùy chọn)
    """Initialize the sentiment analyzer"""
    global sentiment_analyzer
    if sentiment_analyzer is None:
        sentiment_analyzer = SentimentAnalyzer()
        # Gán db instance nếu được cung cấp (cần cho train_from_existing/get_trends)
        if db_instance:
             sentiment_analyzer.db = db_instance

        # Cân nhắc train model ở đây nếu chưa có, hoặc tách ra script riêng
        if not sentiment_analyzer.ml_model:
            # sentiment_analyzer.train_model() # Train với dữ liệu mẫu
            # HOẶC gọi train từ DB nếu muốn:
            # if db_instance: sentiment_analyzer.train_from_existing_reviews()
             pass # Nên train bằng script riêng hoặc khi có dữ liệu đủ lớn

    # Nếu đã khởi tạo và có db_instance mới, gán lại db
    elif db_instance and not hasattr(sentiment_analyzer, 'db'):
         sentiment_analyzer.db = db_instance

    return sentiment_analyzer

def analyze_review_sentiment(review_text):
    """Analyze sentiment of review text"""
    if sentiment_analyzer is None:
        # Không nên init ở đây nếu cần db context cho việc train
        # Nên đảm bảo init_sentiment_analyzer() được gọi trước ở global scope hoặc app context
        # init_sentiment_analyzer() # Tạm thời vẫn gọi ở đây
        raise Exception("Sentiment Analyzer not initialized. Call init_sentiment_analyzer() first.")

    # Hàm này chỉ trả về kết quả phân tích, không ghi DB
    return sentiment_analyzer.analyze_sentiment(review_text)

def get_sentiment_trends(days=30):
    """Get sentiment trends for the specified time period"""
    if sentiment_analyzer is None or not hasattr(sentiment_analyzer, 'db'):
         # Nếu chưa init hoặc chưa có db, cần init lại với db
        from app import db # Import db ở đây
        init_sentiment_analyzer(db) # Truyền db vào

    return sentiment_analyzer.get_recent_sentiment_trends(days)