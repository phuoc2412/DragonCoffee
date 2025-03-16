"""
Dragon Coffee Shop - Chatbot and Natural Language Processing
This module provides chatbot functionality for customer support and order taking.
"""

import re
import random
import nltk
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import os
import json
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

class Chatbot:
    def __init__(self, db):
        """Initialize chatbot with database connection"""
        self.db = db
        self.lemmatizer = WordNetLemmatizer()
        self.stop_words = set(stopwords.words('english'))
        
        # Load response templates
        self.response_templates_path = 'ai_services/data/chatbot_responses.json'
        self.load_response_templates()
        
        # Initialize TF-IDF vectorizer
        self.vectorizer = TfidfVectorizer()
        self.preprocess_faq()
        
        # Track conversation history for context
        self.conversation_history = {}
        
        # Entity recognition patterns
        self.entity_patterns = {
            'product': r'(?i)(coffee|latte|espresso|cappuccino|tea|mocha|americano|brew)',
            'size': r'(?i)(small|medium|large|regular|grande|venti|tall)',
            'quantity': r'(?i)(\d+)(\s+cups?|\s+shots?)?',
            'topping': r'(?i)(sugar|cream|milk|whipped cream|caramel|chocolate|vanilla|syrup)',
            'time': r'(?i)((at|around|before|after)\s+\d{1,2}(\:\d{2})?\s*(am|pm)?)',
            'date': r'(?i)(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
            'location': r'(?i)(store|location|branch|shop|cafe|downtown|uptown)'
        }
    
    def load_response_templates(self):
        """Load response templates from file or create default ones"""
        # Create data directory if it doesn't exist
        os.makedirs('ai_services/data', exist_ok=True)
        
        if os.path.exists(self.response_templates_path):
            try:
                with open(self.response_templates_path, 'r', encoding='utf-8') as f:
                    self.response_templates = json.load(f)
            except:
                # Create default templates
                self.create_default_templates()
        else:
            # Create default templates
            self.create_default_templates()
    
    def create_default_templates(self):
        """Create default response templates"""
        self.response_templates = {
            'menu_recommendation': [
                "Dựa trên sở thích của bạn về {}, tôi gợi ý combo {} sẽ phù hợp với bạn.",
                "Bạn có vẻ thích {}. Hãy thử combo {} của chúng tôi nhé!",
                "Tôi nghĩ bạn sẽ thích combo {} với {} đấy."
            ],
            'food_pairing': [
                "Món {} sẽ rất ngon khi dùng cùng với {}.",
                "Bạn có thể kết hợp {} với {} để tạo nên bữa ăn hoàn hảo.",
                "Gợi ý nhỏ: {} và {} là một cặp đôi hoàn hảo đấy!"
            ],
            'diet_suggestion': [
                "Với chế độ ăn {}, tôi gợi ý bạn nên thử món {} và {}.",
                "Đối với người {}, chúng tôi có các món phù hợp như {} và {}.",
                "Menu của chúng tôi có nhiều lựa chọn cho {}. Bạn có thể thử {} hoặc {}."
            ],
            'greeting': [
                "Xin chào! Tôi là trợ lý ảo Dragon Coffee. Tôi có thể giúp gì cho bạn?",
                "Chào bạn! Cảm ơn bạn đã liên hệ với Dragon Coffee. Bạn cần giúp đỡ gì?",
                "Xin chào, rất vui được gặp bạn. Tôi có thể giúp gì cho bạn hôm nay?"
            ],
            'goodbye': [
                "Cảm ơn bạn đã liên hệ. Chúc bạn một ngày tốt lành!",
                "Rất vui được hỗ trợ bạn. Hẹn gặp lại!",
                "Cảm ơn bạn đã ghé thăm Dragon Coffee. Hẹn gặp lại bạn sớm!"
            ],
            'thanks': [
                "Không có gì đâu! Rất vui được giúp đỡ bạn.",
                "Không có chi. Bạn có cần hỗ trợ gì thêm không?",
                "Rất hân hạnh được phục vụ bạn!"
            ],
            'hours': [
                "Dragon Coffee mở cửa từ 7:00 sáng đến 10:00 tối từ thứ Hai đến thứ Sáu, và từ 8:00 sáng đến 11:00 tối vào cuối tuần.",
                "Chúng tôi mở cửa hàng ngày! Từ thứ Hai đến thứ Sáu: 7:00 - 22:00, cuối tuần: 8:00 - 23:00."
            ],
            'menu': [
                "Menu của chúng tôi bao gồm nhiều loại cà phê đặc trưng của châu Á, đồ uống và đồ ăn nhẹ. Bạn có thể xem menu đầy đủ tại trang web của chúng tôi.",
                "Dragon Coffee có nhiều loại cà phê, trà và đồ ăn nhẹ. Bạn quan tâm đến loại đồ uống nào?"
            ],
            'location': [
                "Dragon Coffee có nhiều chi nhánh trên toàn thành phố. Bạn đang tìm kiếm chi nhánh gần khu vực nào?",
                "Chúng tôi có nhiều địa điểm. Bạn có thể tìm thấy chi nhánh gần nhất bằng cách sử dụng tính năng 'Tìm cửa hàng' trên trang web của chúng tôi."
            ],
            'order': [
                "Tôi có thể giúp bạn đặt đồ uống. Bạn muốn gọi gì?",
                "Rất vui được tiếp nhận đơn hàng của bạn. Bạn muốn đặt đồ uống nào?"
            ],
            'price': [
                "Giá cả phụ thuộc vào đồ uống và kích cỡ bạn chọn. Bạn quan tâm đến loại đồ uống cụ thể nào?",
                "Chúng tôi có nhiều lựa chọn với các mức giá khác nhau. Bạn đang tìm hiểu về sản phẩm nào?"
            ],
            'wifi': [
                "Có, tất cả các chi nhánh Dragon Coffee đều cung cấp Wi-Fi miễn phí cho khách hàng.",
                "Chúng tôi có Wi-Fi miễn phí tại tất cả các cửa hàng. Bạn chỉ cần yêu cầu mật khẩu từ nhân viên."
            ],
            'fallback': [
                "Xin lỗi, tôi không hiểu rõ. Bạn có thể diễn đạt lại được không?",
                "Tôi chưa chắc mình hiểu đúng ý bạn. Bạn có thể nói rõ hơn không?",
                "Xin lỗi, tôi không thể trả lời câu hỏi đó. Bạn có thể giúp tôi hiểu rõ hơn không?"
            ]
        }
        
        # Save default templates
        try:
            with open(self.response_templates_path, 'w', encoding='utf-8') as f:
                json.dump(self.response_templates, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving response templates: {e}")
    
    def preprocess_faq(self):
        """Preprocess FAQ data for similarity matching"""
        # Load FAQ data from database or default data
        try:
            # Try to get FAQ from database
            # For now, use default data
            self.faq_data = [
                {
                    "question": "Quán mở cửa từ mấy giờ?",
                    "answer": "Dragon Coffee mở cửa từ 7:00 sáng đến 10:00 tối từ thứ Hai đến thứ Sáu, và từ 8:00 sáng đến 11:00 tối vào cuối tuần.",
                    "intent": "hours"
                },
                {
                    "question": "Giờ hoạt động của quán?",
                    "answer": "Chúng tôi mở cửa hàng ngày! Từ thứ Hai đến thứ Sáu: 7:00 - 22:00, cuối tuần: 8:00 - 23:00.",
                    "intent": "hours"
                },
                {
                    "question": "Menu của quán có những gì?",
                    "answer": "Menu của chúng tôi bao gồm nhiều loại cà phê đặc trưng của châu Á, đồ uống và đồ ăn nhẹ. Bạn có thể xem menu đầy đủ tại trang web của chúng tôi.",
                    "intent": "menu"
                },
                {
                    "question": "Tôi có thể đặt đồ uống trực tuyến không?",
                    "answer": "Có, bạn có thể đặt đồ uống trực tuyến thông qua trang web hoặc ứng dụng di động của chúng tôi. Chúng tôi cung cấp cả dịch vụ giao hàng và nhận tại cửa hàng.",
                    "intent": "order"
                },
                {
                    "question": "Quán có khuyến mãi gì không?",
                    "answer": "Chúng tôi thường xuyên có các chương trình khuyến mãi. Bạn có thể theo dõi trang mạng xã hội của chúng tôi hoặc đăng ký nhận thông báo để biết thông tin mới nhất về các ưu đãi.",
                    "intent": "promotion"
                }
            ]
            
            # Extract questions for vectorization
            self.faq_questions = [faq["question"] for faq in self.faq_data]
            
            # Create TF-IDF matrix
            self.tfidf_matrix = self.vectorizer.fit_transform(self.faq_questions)
            
        except Exception as e:
            print(f"Error preprocessing FAQ: {e}")
            self.faq_data = []
            self.faq_questions = []
            self.tfidf_matrix = None
    
    def preprocess_text(self, text):
        """Clean and tokenize text"""
        # Convert to lowercase
        text = text.lower()
        
        # Tokenize
        tokens = word_tokenize(text)
        
        # Remove stopwords and lemmatize
        tokens = [self.lemmatizer.lemmatize(token) for token in tokens 
                 if token not in self.stop_words]
        
        return tokens
    
    def detect_intent(self, text):
        """Detect the intent of the user message"""
        # Preprocess text
        tokens = self.preprocess_text(text)
        text_lower = text.lower()

        # Check for recommendation patterns
        if re.search(r'(?i)(gợi ý|tư vấn|recommend|suggest)', text_lower):
            if re.search(r'(?i)(combo|set|bộ)', text_lower):
                return 'menu_recommendation'
            elif re.search(r'(?i)(món|ăn kèm|food)', text_lower):
                return 'food_pairing'
            elif re.search(r'(?i)(ăn kiêng|diet|healthy)', text_lower):
                return 'diet_suggestion'
        
        # Check for greeting patterns
        greeting_patterns = ['xin chào', 'chào', 'hello', 'hi', 'hey', 'alo']
        if any(pattern in text_lower for pattern in greeting_patterns):
            return 'greeting'
        
        # Check for goodbye patterns
        goodbye_patterns = ['tạm biệt', 'goodbye', 'bye', 'see you', 'hẹn gặp lại']
        if any(pattern in text_lower for pattern in goodbye_patterns):
            return 'goodbye'
        
        # Check for thanks patterns
        thanks_patterns = ['cảm ơn', 'thank', 'thanks', 'appreciate']
        if any(pattern in text_lower for pattern in thanks_patterns):
            return 'thanks'
        
        # Check for other specific patterns
        if re.search(r'(?i)(giờ|thời gian|mở cửa|đóng cửa)', text_lower):
            return 'hours'
        
        if re.search(r'(?i)(menu|đồ uống|món gì|đồ ăn)', text_lower):
            return 'menu'
        
        if re.search(r'(?i)(ở đâu|địa chỉ|chi nhánh|địa điểm)', text_lower):
            return 'location'
        
        if re.search(r'(?i)(order|đặt hàng|giao hàng|mua)', text_lower):
            return 'order'
        
        if re.search(r'(?i)(giá|bao nhiêu tiền|chi phí)', text_lower):
            return 'price'
        
        if re.search(r'(?i)(wifi|internet|mạng)', text_lower):
            return 'wifi'
        
        # If no specific intent is detected, try FAQ matching
        if self.tfidf_matrix is not None and self.faq_questions:
            try:
                # Transform the user query
                user_vector = self.vectorizer.transform([text])
                
                # Calculate similarity with FAQ questions
                similarities = cosine_similarity(user_vector, self.tfidf_matrix)[0]
                
                # Get the most similar question
                max_sim_idx = np.argmax(similarities)
                
                # If similarity is above threshold, use the corresponding intent
                if similarities[max_sim_idx] > 0.5:
                    return self.faq_data[max_sim_idx]["intent"]
            except Exception as e:
                print(f"Error in FAQ matching: {e}")
        
        # Default fallback intent
        return 'fallback'
    
    def extract_entities(self, text):
        """Extract entities from user message"""
        entities = {}
        
        # Apply entity recognition patterns
        for entity_type, pattern in self.entity_patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                if entity_type == 'quantity':
                    # Extract numeric value from quantity match
                    for match in matches:
                        if match[0].isdigit():
                            entities[entity_type] = int(match[0])
                            break
                else:
                    # Store first match for other entity types
                    entities[entity_type] = matches[0]
        
        return entities
    
    def generate_response(self, text, session_id=None):
        """Generate a response to the user message"""
        # Track conversation
        if session_id:
            if session_id not in self.conversation_history:
                self.conversation_history[session_id] = []
            
            # Add user message to history
            self.conversation_history[session_id].append({
                'role': 'user',
                'message': text,
                'timestamp': datetime.utcnow().isoformat()
            })
        
        # Detect intent
        intent = self.detect_intent(text)
        
        # Handle recommendation intents
        if intent == 'menu_recommendation':
            combo = self.recommend_combo(text)
            if combo:
                response = random.choice(self.response_templates['menu_recommendation']).format(
                    text.lower(), combo[0], combo[1]
                )
            else:
                response = "Bạn có thể cho tôi biết bạn thích đồ uống gì không? (cà phê, trà,...)"
        elif intent == 'food_pairing':
            # Get food pairing suggestion
            pairs = {
                'cà phê': 'bánh mì',
                'trà': 'bánh ngọt',
                'espresso': 'cookies',
                'cappuccino': 'tiramisu'
            }
            for food, pair in pairs.items():
                if food in text.lower():
                    response = random.choice(self.response_templates['food_pairing']).format(
                        food, pair
                    )
                    break
            else:
                response = "Bạn muốn tìm món ăn kèm cho đồ uống nào?"
        else:
            if session_id not in self.conversation_history:
                self.conversation_history[session_id] = []
            
            # Add user message to history
            self.conversation_history[session_id].append({
                'role': 'user',
                'message': text,
                'timestamp': datetime.utcnow().isoformat()
            })
        
        # Detect intent
        intent = self.detect_intent(text)
        
        # Extract entities
        entities = self.extract_entities(text)
        
        # Get appropriate response based on intent
        if intent in self.response_templates:
            response = random.choice(self.response_templates[intent])
        else:
            response = random.choice(self.response_templates['fallback'])
        
        # Customize response based on extracted entities
        if intent == 'order' and 'product' in entities:
            product = entities['product']
            size = entities.get('size', 'regular')
            quantity = entities.get('quantity', 1)
            
            response = f"Tôi đã ghi nhận đơn hàng của bạn: {quantity} {size} {product}. Bạn có muốn thêm gì không?"
        
        # For FAQ matching, use the stored answer
        if self.tfidf_matrix is not None and intent not in self.response_templates:
            try:
                user_vector = self.vectorizer.transform([text])
                similarities = cosine_similarity(user_vector, self.tfidf_matrix)[0]
                max_sim_idx = np.argmax(similarities)
                
                if similarities[max_sim_idx] > 0.5:
                    response = self.faq_data[max_sim_idx]["answer"]
            except Exception as e:
                print(f"Error retrieving FAQ answer: {e}")
        
        # Track bot response
        if session_id:
            self.conversation_history[session_id].append({
                'role': 'bot',
                'message': response,
                'timestamp': datetime.utcnow().isoformat(),
                'intent': intent,
                'entities': entities
            })
        
        return {
            'response': response,
            'intent': intent,
            'entities': entities
        }
    
    def get_conversation_history(self, session_id):
        """Get conversation history for a session"""
        if session_id in self.conversation_history:
            return self.conversation_history[session_id]
        return []
    
    def clear_conversation_history(self, session_id):
        """Clear conversation history for a session"""
        if session_id in self.conversation_history:
            del self.conversation_history[session_id]
    
    def recommend_combo(self, preferences):
        """Generate combo recommendations based on user preferences"""
        combos = {
            'coffee': {
                'morning': ['Combo Sáng Tỉnh Táo', 'Cà phê sữa đá + Bánh mì'],
                'afternoon': ['Combo Chiều Năng Động', 'Americano + Cookies'],
                'sweet': ['Combo Ngọt Ngào', 'Mocha + Bánh flan'],
                'strong': ['Combo Mạnh Mẽ', 'Espresso đúp + Brownies']
            },
            'tea': {
                'morning': ['Combo Thanh Mát', 'Trà sen + Bánh bông lan'],
                'afternoon': ['Combo Thư Giãn', 'Trà đào + Macaron'],
                'sweet': ['Combo Trà Ngọt', 'Trà sữa trân châu + Bánh pudding'],
                'light': ['Combo Nhẹ Nhàng', 'Trà xanh + Bánh cuộn']
            }
        }
        
        # Match preferences with combos
        if 'coffee' in preferences.lower():
            if 'sáng' in preferences.lower():
                return combos['coffee']['morning']
            elif 'chiều' in preferences.lower():
                return combos['coffee']['afternoon']
            elif 'ngọt' in preferences.lower():
                return combos['coffee']['sweet']
            else:
                return combos['coffee']['strong']
        elif 'trà' in preferences.lower() or 'tea' in preferences.lower():
            if 'sáng' in preferences.lower():
                return combos['tea']['morning']
            elif 'chiều' in preferences.lower():
                return combos['tea']['afternoon']
            elif 'ngọt' in preferences.lower():
                return combos['tea']['sweet']
            else:
                return combos['tea']['light']
        return None

    def handle_order_intent(self, text, session_id):
        """Handle order intent specifically"""
        entities = self.extract_entities(text)
        
        if 'product' not in entities:
            return {
                'response': "Bạn muốn đặt đồ uống gì? Chúng tôi có nhiều loại cà phê, trà và nước giải khát.",
                'intent': 'order',
                'entities': entities,
                'requires_followup': True
            }
        
        product = entities['product']
        size = entities.get('size', 'regular')
        quantity = entities.get('quantity', 1)
        
        # Validate product against menu items
        valid_product = self.validate_product(product)
        
        if not valid_product:
            return {
                'response': f"Xin lỗi, chúng tôi không có {product} trong menu. Bạn có thể chọn loại đồ uống khác không?",
                'intent': 'order',
                'entities': entities,
                'requires_followup': True
            }
        
        # Calculate price
        price = self.calculate_order_price(valid_product, size, quantity)
        
        # Create order in database if user is logged in
        order_id = None
        if session_id and self.is_user_authenticated(session_id):
            try:
                order_id = self.create_order(session_id, valid_product, size, quantity)
            except Exception as e:
                print(f"Error creating order: {e}")
        
        response = f"Tôi đã ghi nhận đơn hàng của bạn: {quantity} {size} {valid_product['name']}."
        
        if price:
            response += f" Giá tạm tính là {price:,.0f}đ."
        
        if order_id:
            response += f" Mã đơn hàng của bạn là #{order_id}."
        else:
            response += " Bạn có thể hoàn tất đơn hàng bằng cách đăng nhập và thanh toán trên trang web của chúng tôi."
        
        return {
            'response': response,
            'intent': 'order',
            'entities': entities,
            'order': {
                'product': valid_product['name'],
                'size': size,
                'quantity': quantity,
                'price': price,
                'order_id': order_id
            }
        }
    
    def validate_product(self, product_name):
        """Validate product against menu items"""
        try:
            from models import Product
            
            # Try to find product by name or similar name
            products = self.db.session.query(Product).filter(
                Product.name.ilike(f"%{product_name}%")
            ).all()
            
            if products:
                # Return first matching product
                return {
                    'id': products[0].id,
                    'name': products[0].name,
                    'price': products[0].price
                }
            
            return None
        except Exception as e:
            print(f"Error validating product: {e}")
            # Fallback: Return a default product for demo purposes
            return {
                'id': 1,
                'name': 'Cà phê Dragon',
                'price': 30000
            }
    
    def calculate_order_price(self, product, size, quantity):
        """Calculate price for an order"""
        base_price = product['price']
        
        # Apply size multiplier
        size_multipliers = {
            'small': 0.8,
            'regular': 1.0,
            'medium': 1.0,
            'large': 1.2,
            'grande': 1.3,
            'venti': 1.5
        }
        
        size_multiplier = size_multipliers.get(size.lower(), 1.0)
        
        # Calculate total price
        total_price = base_price * size_multiplier * quantity
        
        return total_price
    
    def is_user_authenticated(self, session_id):
        """Check if user is authenticated"""
        # This would check session data in a real implementation
        return False
    
    def create_order(self, session_id, product, size, quantity):
        """Create an order in the database"""
        # This would create an actual order in a real implementation
        return f"ORD{random.randint(10000, 99999)}"


# Singleton instance
chatbot = None

def init_chatbot(db):
    """Initialize the chatbot"""
    global chatbot
    chatbot = Chatbot(db)
    return chatbot

def get_response(text, session_id=None):
    """Get chatbot response for a message"""
    if chatbot is None:
        from app import db
        init_chatbot(db)
    
    return chatbot.generate_response(text, session_id)

def handle_order(text, session_id=None):
    """Handle order intent specifically"""
    if chatbot is None:
        from app import db
        init_chatbot(db)
    
    return chatbot.handle_order_intent(text, session_id)