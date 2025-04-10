"""
Dragon Coffee Shop - Chatbot and Natural Language Processing
This module provides chatbot functionality for customer support and order taking,
including basic visual search based on text description.
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
from flask import current_app, url_for
from sqlalchemy import or_

# Ensure NLTK data is available (Run once if needed)
def download_nltk_data():
    data_to_download = ['punkt', 'stopwords', 'wordnet']
    for item in data_to_download:
        try:
            nltk.data.find(f'tokenizers/{item}' if item == 'punkt' else f'corpora/{item}')
        except LookupError:
            print(f"Downloading NLTK data: {item}")
            nltk.download(item, quiet=True)

# Call this explicitly when needed, e.g., during app setup or first run
# download_nltk_data()

class Chatbot:
    def __init__(self, db):
        """Initialize chatbot with database connection"""
        self.db = db
        # Use Flask logger if available, otherwise fallback to print
        self.logger = current_app.logger if current_app else logging.getLogger(__name__)
        if not current_app: # Setup basic logging if outside Flask
             import logging
             logging.basicConfig(level=logging.INFO)

        try:
            # Initialize NLTK components
            download_nltk_data()
            self.lemmatizer = WordNetLemmatizer()
            vietnamese_stopwords = set() # Add custom Vietnamese stopwords here if needed
            # stopword_file = os.path.join(os.path.dirname(__file__), 'data', 'vietnamese_stopwords.txt')
            # if os.path.exists(stopword_file):
            #     with open(stopword_file, 'r', encoding='utf-8') as f:
            #         vietnamese_stopwords = set(line.strip() for line in f)
            self.stop_words = set(stopwords.words('english')).union(vietnamese_stopwords)
        except Exception as e:
            self.logger.error(f"Failed to initialize NLTK components: {e}", exc_info=True)
            # Depending on severity, you might want to raise the exception or handle it

        # Setup paths and load data
        self.data_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        self.response_templates_path = os.path.join(self.data_dir, 'chatbot_responses.json')
        self.response_templates = {}
        self.load_response_templates()

        # Initialize NLP components
        self.vectorizer = TfidfVectorizer()
        self.faq_data = []
        self.faq_questions = []
        self.tfidf_matrix = None
        self.preprocess_faq()

        self.conversation_history = {}

        # Define entity patterns (add more as needed)
        self.entity_patterns = {
            'product': r'(?i)(cà phê|coffee|latte|espresso|cappuccino|trà|tea|mocha|americano|brew|sinh tố|nước ép|bánh|pastry|snack|phô mai|cookie|bạc xỉu|cốt dừa|đen đá|sữa đá|trứng|muối)',
            'size': r'(?i)(nhỏ|vừa|lớn|small|medium|large|regular|grande|venti|tall)',
            'quantity': r'(?i)(\d+)(\s+ly|\s+cái|\s+phần|\s+cups?|\s+shots?)?',
            'topping': r'(?i)(đường|kem|sữa|whipped cream|caramel|sô cô la|chocolate|vanilla|vani|syrup|trân châu|thạch|đá)',
            'color': r'(?i)(đỏ|xanh|vàng|nâu|đen|trắng|hồng|cam|tím|kem|red|green|yellow|brown|black|white|pink|orange|purple|cream)',
            'texture': r'(?i)(bọt|mịn|kem|creamy|sánh|đặc|trong|sệt|giòn|mềm|foam|smooth|thick|clear|crispy|soft)',
            'flavor': r'(?i)(ngọt|chua|đắng|cay|mặn|đậm đà|thanh mát|béo|thơm|ít ngọt|sweet|sour|bitter|spicy|salty|rich|fresh|creamy|aromatic)',
            'time': r'(?i)((vào|lúc|khoảng|trước|sau)\s+\d{1,2}([:.]\d{2})?\s*(sáng|trưa|chiều|tối|giờ|am|pm)?)',
            'date': r'(?i)(hôm nay|ngày mai|thứ hai|thứ ba|thứ tư|thứ năm|thứ sáu|thứ bảy|chủ nhật|today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
            'location': r'(?i)(cửa hàng|quán|chi nhánh|địa điểm|chỗ nào|ở đâu|store|location|branch|shop|cafe|downtown|uptown)'
        }

    def load_response_templates(self):
        """Loads response templates from a JSON file, creates defaults if necessary."""
        if os.path.exists(self.response_templates_path):
            try:
                with open(self.response_templates_path, 'r', encoding='utf-8') as f:
                    self.response_templates = json.load(f)
                    self.logger.info(f"Loaded response templates from {self.response_templates_path}")
            except json.JSONDecodeError as e:
                 self.logger.error(f"Error decoding JSON from {self.response_templates_path}: {e}. Creating defaults.")
                 self.create_default_templates()
            except Exception as e:
                 self.logger.error(f"Error loading response templates: {e}. Creating defaults.")
                 self.create_default_templates()
        else:
            self.logger.info("Response templates file not found. Creating defaults.")
            self.create_default_templates()

    def create_default_templates(self):
        """Creates a default set of response templates."""
        self.response_templates = {
            'greeting': ["Xin chào! Tôi là Dragon Bot, tôi có thể giúp gì?", "Chào bạn! Bạn cần hỗ trợ về vấn đề gì hôm nay?"],
            'goodbye': ["Cảm ơn bạn đã liên hệ. Chúc bạn một ngày tốt lành!", "Tạm biệt, hẹn gặp lại bạn!"],
            'thanks': ["Rất vui được giúp đỡ bạn!", "Không có gì đâu ạ!"],
            'hours': ["Quán mở cửa từ 7:00 sáng đến 10:00 tối các ngày trong tuần và 8:00 sáng đến 11:00 tối cuối tuần."],
            'menu': ["Bạn có thể xem menu đầy đủ trên trang web nhé. Bạn quan tâm món cụ thể nào không?", "Menu có nhiều loại cà phê, trà, bánh và đồ ăn nhẹ."],
            'location': ["Chúng tôi có nhiều chi nhánh. Bạn đang ở gần khu vực nào?", "Bạn có thể tìm địa chỉ chi nhánh gần nhất trên website của Dragon Coffee."],
            'order': ["Bạn muốn đặt món gì ạ? Tôi có thể ghi nhận đơn hàng giúp bạn.", "Để đặt hàng, bạn muốn chọn món nào?"],
            'price': ["Giá món tùy thuộc vào sản phẩm và size. Bạn muốn biết giá món nào?", "Bạn vui lòng tham khảo giá trên menu hoặc cho tôi biết món bạn quan tâm nhé."],
            'wifi': ["Vâng, quán có wifi miễn phí cho khách hàng ạ.", "Bạn có thể hỏi mật khẩu wifi tại quầy nhé."],
            'promotion': ["Hiện quán đang có [Tên khuyến mãi]. Bạn xem chi tiết trên trang Khuyến Mãi hoặc Fanpage nhé!", "Các chương trình ưu đãi được cập nhật thường xuyên trên website."],
            'visual_product_search_result': ["Tìm được vài hình ảnh giống mô tả '{keywords}' của bạn nè:", "Đây là các sản phẩm trông giống '{keywords}':"],
            'visual_product_search_notfound': ["Rất tiếc, tôi không tìm thấy sản phẩm nào khớp với mô tả '{keywords}'. Bạn thử mô tả khác xem?", "Hmm, tôi chưa tìm được món nào giống '{keywords}'."],
            'visual_product_search_nokeywords': ["Bạn muốn tôi tìm ảnh món ăn/đồ uống trông như thế nào?", "Hãy mô tả thêm về món bạn muốn xem ảnh nhé."],
            'faq': [
                { "question": "Quán mở cửa mấy giờ?", "answer": "Dragon Coffee mở cửa từ 7:00 sáng đến 10:00 tối các ngày trong tuần và 8:00 sáng đến 11:00 tối cuối tuần.", "intent": "hours" },
                { "question": "Menu có gì?", "answer": "Menu có nhiều loại cà phê, trà, bánh và đồ ăn nhẹ. Bạn có thể xem menu đầy đủ trên trang web nhé.", "intent": "menu" },
                { "question": "Có đặt online không?", "answer": "Có ạ, bạn đặt qua web hoặc app nhé.", "intent": "order"},
                { "question": "Wifi free không?", "answer": "Vâng, quán có wifi miễn phí.", "intent": "wifi" },
                { "question": "Có khuyến mãi gì?", "answer": "Quán thường có ưu đãi theo mùa, bạn theo dõi website/fanpage nhé!", "intent": "promotion" }
            ],
            'fallback': ["Xin lỗi, tôi chưa hiểu ý bạn lắm. Bạn có thể nói cách khác được không?", "Tôi có thể chưa hiểu rõ, bạn giải thích thêm giúp tôi nhé."]
        }
        try:
            with open(self.response_templates_path, 'w', encoding='utf-8') as f:
                json.dump(self.response_templates, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.logger.error(f"Error saving default response templates: {e}")

    def preprocess_faq(self):
        """Preprocesses FAQ data for similarity matching."""
        if not self.response_templates: self.load_response_templates()
        try:
            self.faq_data = self.response_templates.get('faq', [])
            if self.faq_data:
                self.faq_questions = [faq.get("question","").lower() for faq in self.faq_data if faq.get("question")] # Lowercase questions
                if self.faq_questions:
                    self.tfidf_matrix = self.vectorizer.fit_transform(self.faq_questions)
                    self.logger.info(f"Processed {len(self.faq_questions)} FAQ questions.")
                else:
                     self.logger.warning("No valid questions found in FAQ data.")
                     self.tfidf_matrix = None
            else:
                self.logger.warning("No FAQ data found in response templates.")
                self.tfidf_matrix = None
        except Exception as e:
            self.logger.error(f"Error preprocessing FAQ: {e}", exc_info=True)
            self.faq_data = []
            self.faq_questions = []
            self.tfidf_matrix = None

    def preprocess_text(self, text):
        """Cleans and tokenizes text."""
        if not text: return []
        try:
            text = str(text).lower()
            tokens = word_tokenize(text)
            tokens = [self.lemmatizer.lemmatize(word) for word in tokens
                      if word.isalpha() and word not in self.stop_words and len(word) > 1]
            return tokens
        except Exception as e:
            self.logger.error(f"Error in preprocess_text: {e}")
            return []

    def detect_intent(self, text):
        """Detects the intent of the user message."""
        text_lower = text.lower()
        visual_keywords = ['ảnh', 'hình', 'picture', 'image', 'photo', 'nhìn', 'trông', 'giống']
        if any(kw in text_lower for kw in visual_keywords) and len(text_lower.split()) >= 3: # Cần ít nhất 3 từ
             if not any(kw in text_lower for kw in ['giá', 'bao nhiêu', 'menu', 'địa chỉ', 'mấy giờ', 'giờ mở cửa']):
                 return 'visual_product_search'

        if re.search(r'(?i)\b(gợi ý|tư vấn|recommend|suggest)\b', text_lower):
             if re.search(r'(?i)\b(combo|set|bộ)\b', text_lower): return 'menu_recommendation'
             if re.search(r'(?i)\b(món|ăn kèm|food)\b', text_lower): return 'food_pairing'
             if re.search(r'(?i)\b(ăn kiêng|diet|healthy)\b', text_lower): return 'diet_suggestion'

        greeting_patterns = ['xin chào', 'chào bạn', 'chào shop', 'hello', 'hi', 'hey', 'alo']
        if any(text_lower.startswith(p) for p in greeting_patterns): return 'greeting'

        goodbye_patterns = ['tạm biệt', 'goodbye', 'bye', 'see you', 'hẹn gặp lại']
        if any(p in text_lower for p in goodbye_patterns): return 'goodbye'

        thanks_patterns = ['cảm ơn', 'cám ơn', 'thank', 'thanks', 'appreciate']
        if any(p in text_lower for p in thanks_patterns): return 'thanks'

        if re.search(r'(?i)\b(giờ|mấy giờ|thời gian|mở cửa|đóng cửa)\b', text_lower): return 'hours'
        if re.search(r'(?i)\b(menu|thực đơn|có món gì|đồ uống|đồ ăn)\b', text_lower): return 'menu'
        if re.search(r'(?i)\b(ở đâu|địa chỉ|chi nhánh|địa điểm|đến quán)\b', text_lower): return 'location'
        if re.search(r'(?i)\b(đặt|order|mua|lấy|gọi món)\b.*\b(cà phê|trà|bánh|espresso|latte)\b', text_lower): return 'order' # Pattern chặt hơn cho order
        if re.search(r'(?i)\b(giá|bao nhiêu tiền|tiền|cost|price)\b', text_lower): return 'price'
        if re.search(r'(?i)\b(wifi|internet|mạng)\b', text_lower): return 'wifi'
        if re.search(r'(?i)\b(khuyến mãi|giảm giá|ưu đãi|promotion|discount|deal)\b', text_lower): return 'promotion'

        if self.tfidf_matrix is not None and self.faq_data:
            try:
                user_vector = self.vectorizer.transform([text])
                similarities = cosine_similarity(user_vector, self.tfidf_matrix)[0]
                max_sim_idx = np.argmax(similarities)
                if similarities[max_sim_idx] > 0.55: # Điều chỉnh ngưỡng nếu cần
                    faq_intent = self.faq_data[max_sim_idx].get("intent")
                    if faq_intent:
                         self.logger.info(f"Intent detected via FAQ matching (Similarity: {similarities[max_sim_idx]:.2f}): {faq_intent}")
                         return faq_intent
            except Exception as e:
                self.logger.error(f"Error in FAQ matching: {e}", exc_info=True)

        self.logger.info(f"No specific intent or FAQ match found for: '{text[:50]}...'. Using fallback.")
        return 'fallback'

    def extract_entities(self, text):
        """Extracts entities from the user message."""
        entities = {}
        # Sắp xếp entity_patterns theo độ dài pattern giảm dần để khớp đúng hơn
        # Ví dụ: 'cà phê sữa đá' trước 'cà phê'
        sorted_patterns = sorted(self.entity_patterns.items(), key=lambda item: len(item[1]), reverse=True)

        processed_text = text # Giữ lại text gốc để tránh xóa nhầm

        for entity_type, pattern in sorted_patterns:
            # Dùng finditer để tìm tất cả vị trí khớp
            for match in re.finditer(pattern, processed_text, re.IGNORECASE):
                entity_value = match.group(0).lower()
                # Xử lý quantity
                if entity_type == 'quantity':
                     num_match = re.search(r'\d+', entity_value)
                     entities[entity_type] = int(num_match.group(0)) if num_match else entities.get(entity_type, 1)
                # Xử lý product (list)
                elif entity_type == 'product':
                    # Lemmatize hoặc chuẩn hóa tên SP ở đây nếu cần
                    entities.setdefault(entity_type, []).append(entity_value)
                # Các entity khác lấy giá trị đầu tiên tìm được
                elif entity_type not in entities:
                     entities[entity_type] = entity_value

                 # Đánh dấu phần đã xử lý để tránh khớp lại (thô sơ)
                 # processed_text = processed_text[:match.start()] + '*' * len(entity_value) + processed_text[match.end():]

        if 'product' in entities:
            entities['product'] = list(set(entities['product']))
        return entities

    def extract_visual_keywords(self, text):
        """Extracts descriptive keywords for visual search."""
        text_lower = text.lower()
        stop_words_visual = set(self.stop_words).union({
            'tìm', 'hình', 'ảnh', 'cho', 'xem', 'show', 'picture', 'image', 'photo',
            'of', 'for', 'search', 'với', 'có', 'lớp', 'phía', 'một', 'vài', 'ít',
            'nhiều', 'giống', 'trông', 'nhìn', 'thấy', 'that', 'looks', 'like', 'with',
            'hơi', 'khá', 'rất', 'cực', 'siêu', 'là', 'thì', 'mà', 'của', 'ở', 'tại'
        })
        tokens = word_tokenize(text_lower)
        tagged_tokens = nltk.pos_tag(tokens)
        keywords = []
        for word, tag in tagged_tokens:
            if (tag.startswith('JJ') or tag.startswith('NN')) and \
               word.isalpha() and word not in stop_words_visual and len(word) > 2:
                keywords.append(self.lemmatizer.lemmatize(word))
        entities = self.extract_entities(text)
        if 'color' in entities: keywords.append(entities['color'])
        if 'texture' in entities: keywords.append(entities['texture'])
        return list(set(keywords))

    def search_products_by_visual_keywords(self, keywords, limit=3):
        """Searches products by visual keywords in name and description."""
        from models import Product
        if not keywords: return []
        self.logger.info(f"Searching products with visual keywords: {keywords}")
        # Tạo điều kiện tìm kiếm (ưu tiên tên)
        search_conditions = []
        for keyword in keywords: search_conditions.append(Product.name.ilike(f"%{keyword}%"))
        for keyword in keywords: search_conditions.append(Product.description.ilike(f"%{keyword}%"))

        try:
            # Sắp xếp theo mức độ khớp tên trước? (Hơi phức tạp với OR)
            results = Product.query.filter(Product.is_available == True)\
                                   .filter(or_(*search_conditions))\
                                   .limit(limit * 2).all() # Lấy dư để xử lý sau

            formatted_results = []
            # Cần app context để chạy url_for
            if current_app:
                with current_app.app_context():
                    for product in results[:limit]: # Giới hạn lại kết quả cuối
                        img_url = product.image_url or url_for('static', filename='images/default_product.png', _external=True) # Cần _external nếu chạy độc lập
                        prod_url = url_for('main.product_detail', product_id=product.id, _external=True)
                        formatted_results.append({"id": product.id, "name": product.name, "image_url": img_url, "product_url": prod_url})
            else: # Fallback nếu không có app context
                 for product in results[:limit]:
                      formatted_results.append({"id": product.id, "name": product.name, "image_url": product.image_url or "/static/images/default_product.png", "product_url": f"/product/{product.id}"})

            self.logger.info(f"Found {len(formatted_results)} visual search results for keywords: {keywords}.")
            return formatted_results
        except Exception as e:
            self.logger.error(f"Error searching products by visual keywords: {e}", exc_info=True)
            return []

    def generate_response(self, text, session_id=None):
        """Generates a response based on user input, intent, and entities."""
        if session_id:
            if session_id not in self.conversation_history: self.conversation_history[session_id] = []
            self.conversation_history[session_id].append({'role': 'user', 'message': text, 'timestamp': datetime.utcnow().isoformat()})

        intent = self.detect_intent(text)
        entities = self.extract_entities(text)
        response_text = random.choice(self.response_templates.get('fallback', ["Xin lỗi, tôi chưa hiểu."]))
        image_results = [] # Reset kết quả ảnh cho mỗi tin nhắn mới

        # --- *** XỬ LÝ INTENT TÌM ẢNH BẰNG VĂN BẢN (visual_product_search) *** ---
        if intent == 'visual_product_search':
            keywords = self.extract_visual_keywords(text)
            if keywords:
                found_products = self.search_products_by_visual_keywords(keywords) # Dùng hàm tìm theo keyword
                if found_products:
                    response_key = 'visual_product_search_result'
                    # Lấy 1 câu ngẫu nhiên từ template và format
                    response_text = random.choice(self.response_templates.get(response_key, ["Kết quả tìm kiếm cho '{keywords}':"])).format(keywords=" ".join(keywords))
                    image_results = found_products # Gán kết quả ảnh tìm được
                else:
                    response_key = 'visual_product_search_notfound'
                    response_text = random.choice(self.response_templates.get(response_key, ["Không tìm thấy ảnh khớp '{keywords}'."])).format(keywords=" ".join(keywords))
            else:
                 response_key = 'visual_product_search_nokeywords'
                 response_text = random.choice(self.response_templates.get(response_key, ["Bạn muốn tìm ảnh món gì?"]))
        # --- *** KẾT THÚC XỬ LÝ VISUAL SEARCH *** ---

        # --- Xử lý các intent khác (như cũ) ---
        elif intent in self.response_templates:
             response_text = random.choice(self.response_templates[intent])
             # Customize if needed, e.g., for 'order'
             if intent == 'order' and 'product' in entities:
                  products = entities.get('product', [])
                  response_text = f"Bạn muốn đặt {', '.join(products)} phải không? Vui lòng cho biết thêm chi tiết (size, số lượng)."
             # ... (các tùy chỉnh intent khác nếu có) ...
        else: # Fallback hoặc FAQ Match
            matched_faq = False
            if self.tfidf_matrix is not None and self.faq_data:
                try:
                    user_vector = self.vectorizer.transform([text])
                    similarities = cosine_similarity(user_vector, self.tfidf_matrix)[0]
                    max_sim_idx = np.argmax(similarities)
                    if similarities[max_sim_idx] > 0.55: # Ngưỡng FAQ
                         response_text = self.faq_data[max_sim_idx].get("answer", response_text)
                         intent = self.faq_data[max_sim_idx].get("intent", "faq_match")
                         matched_faq = True
                except Exception as e: self.logger.error(f"Error during FAQ lookup: {e}", exc_info=True)
            # Nếu không khớp FAQ, intent vẫn là fallback (đã set mặc định ban đầu)
            if not matched_faq: intent = 'fallback'


        # --- Lưu vào history và trả về ---
        if session_id:
            self.conversation_history[session_id].append({
                'role': 'bot', 'message': response_text, 'timestamp': datetime.utcnow().isoformat(),
                'intent': intent, 'entities': entities, 'image_results': image_results # Luôn trả về image_results (có thể rỗng)
            })
        return {'response': response_text, 'intent': intent, 'entities': entities, 'image_results': image_results}

    # --- Các phương thức helper giữ nguyên hoặc cần hoàn thiện logic ---
    def get_conversation_history(self, session_id): return self.conversation_history.get(session_id, [])
    def clear_conversation_history(self, session_id): self.conversation_history.pop(session_id, None)
    def recommend_combo(self, preferences): return None # Placeholder
    def handle_order_intent(self, text, session_id): return {'response': 'Tính năng đặt hàng đang được phát triển.'} # Placeholder
    def validate_product(self, product_name): return {'id': 1, 'name': 'Cà phê Dragon', 'price': 30000} # Placeholder
    def calculate_order_price(self, product, size, quantity): return product.get('price',0) * quantity # Placeholder
    def is_user_authenticated(self, session_id): return False # Placeholder
    def create_order(self, session_id, product_info, size, quantity): return None # Placeholder

# --- Singleton instance ---
chatbot = None

def init_chatbot(db):
    global chatbot
    if chatbot is None:
        print("Initializing Chatbot...")
        try:
             chatbot = Chatbot(db)
             print("Chatbot initialized.")
        except Exception as e:
             print(f"FATAL: Chatbot initialization failed: {e}")
             chatbot = None # Đảm bảo chatbot là None nếu init lỗi
    return chatbot

def get_response(text, session_id=None):
    if chatbot is None:
        # raise Exception("Chatbot not initialized. Call init_chatbot() during app setup.")
        # Hoặc cố gắng init lại một cách an toàn (ít được khuyến khích trong production)
         print("ERROR: Chatbot called before initialization!")
         return {"response": "Xin lỗi, hệ thống chatbot đang gặp sự cố. Vui lòng thử lại sau.", "intent": "error", "entities": {}, "image_results": []}
    try:
         return chatbot.generate_response(text, session_id)
    except Exception as e:
        chatbot.logger.error(f"Error generating chatbot response: {e}", exc_info=True)
        return {"response": "Tôi gặp chút trục trặc, bạn thử lại sau nhé.", "intent": "error", "entities": {}, "image_results": []}

def handle_order(text, session_id=None):
     if chatbot is None: raise Exception("Chatbot not initialized.")
     # Tạm thời gọi get_response, cần logic riêng phức tạp hơn cho đặt hàng
     return chatbot.handle_order_intent(text, session_id)