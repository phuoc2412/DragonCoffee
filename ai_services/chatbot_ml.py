# /ai_services/chatbot_ml.py
import re
import random
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from collections import Counter, defaultdict
import os
import joblib
from datetime import datetime, timedelta
from flask import current_app, url_for, session
from sqlalchemy import or_, func, desc, case, cast, String
import uuid
import logging
from sqlalchemy.orm import joinedload

try:
    from models import db, Product, Category, Promotion, Order, OrderDetail, InventoryItem, User, Location
except ImportError:
    db = None
    Product = Category = Promotion = Order = OrderDetail = InventoryItem = User = Location = type("DummyModel", (object,), {})

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, 'data')
MODELS_DIR = os.path.join(DATA_DIR, 'models')
os.makedirs(MODELS_DIR, exist_ok=True)

INTENT_MODEL_PATH = os.path.join(MODELS_DIR, 'intent_model.joblib')
TFIDF_VECTORIZER_PATH = os.path.join(MODELS_DIR, 'tfidf_vectorizer.joblib')
TEMPLATES_FILE_PATH = os.path.join(DATA_DIR, 'chatbot_responses.json')
TRAINING_DATA_PATH = os.path.join(DATA_DIR, 'training_data.json')

def get_logger():
    if current_app: return current_app.logger
    logger = logging.getLogger("chatbot_ml_service")
    if not logger.hasHandlers():
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

_nltk_data_initialized = False
def initialize_nltk_data():
    global _nltk_data_initialized
    if _nltk_data_initialized: return
    logger = get_logger()
    logger.info("Checking and initializing NLTK data...")
    resources = {'tokenizers/punkt':'punkt','corpora/stopwords':'stopwords','corpora/wordnet':'wordnet','corpora/omw-1.4':'omw-1.4'}
    for path, name in resources.items():
        try: nltk.data.find(path)
        except LookupError:
            logger.warning(f"NLTK resource '{name}' not found. Downloading...")
            try: nltk.download(name, quiet=True); logger.info(f"'{name}' downloaded.")
            except Exception as e: logger.error(f"Failed to download '{name}': {e}")
    _nltk_data_initialized = True

try:
    initialize_nltk_data()
    lemmatizer = WordNetLemmatizer()
    stop_words_english = set(stopwords.words('english')) if 'corpora/stopwords' in nltk.data.path else set()
    vietnamese_stopwords_list = ['là','và','của','các','được','để','với','có','cho','không','trên','này','đó','những','thì','mà','rất','cũng','vẫn','tôi','bạn','mình','chúng','anh','chị','em','người','khi','như','ở','vào','hay','ạ','ơi','quán','shop','ad','vậy','nhé','nha','đi','đây','ấy','gì','thế','nào','còn','rồi','nhỉ','à','ừ','dạ','vâng']
    ALL_STOP_WORDS = stop_words_english.union(set(vietnamese_stopwords_list))
except Exception as e:
    get_logger().critical(f"NLTK init error: {e}. Fallback.", exc_info=True)
    lemmatizer = type('DummyLemmatizer',(object,),{'lemmatize': lambda self,x:x})()
    ALL_STOP_WORDS = set(vietnamese_stopwords_list)

INTENTS_DATA_KEYWORDS = {
    "greeting": ["xin chào", "chào", "hello", "hi", "hey", "alo"],
    "goodbye": ["tạm biệt", "bye", "hẹn gặp lại"],
    "thanks": ["cảm ơn", "cám ơn", "thank"],
    "hours_inquiry": ["giờ mở cửa", "mấy giờ mở", "thời gian bán", "khi nào đóng cửa"],
    "menu_inquiry": ["menu", "thực đơn", "có món gì", "bán gì", "xem menu", "món hôm nay"],
    "category_inquiry": ["cà phê", "cafe", "trà", "tea", "bánh", "sinh tố", "nước ép", "đá xay", "combo"],
    "location_inquiry": ["địa chỉ", "chi nhánh", "ở đâu", "tìm quán", "quán ở chỗ nào"],
    "order_intent": ["đặt hàng", "order", "mua", "lấy món", "gọi món", "cho tôi đặt", "muốn đặt"],
    "product_info": [
        "thông tin món", "chi tiết sản phẩm", "món này là gì", "mô tả sản phẩm", "thành phần món",
        "giới thiệu món", "nói về món", "sản phẩm này thế nào", "đặc điểm của", "vị ra sao",
        "gồm những gì", "làm từ gì", "giải thích món",
        "dinh dưỡng", "calo", "caffeine", "cách pha", "nguồn gốc"
    ],
    "product_price_inquiry": ["giá bao nhiêu", "bao nhiêu tiền", "giá của", "tiền món", "cost", "price"],
    "check_availability": ["còn hàng không", "còn bán không", "có sẵn không", "available"],
    "promotion_inquiry": ["khuyến mãi", "giảm giá", "ưu đãi", "discount", "deal", "voucher", "coupon", "km"],
    "suggest_combo": ["gợi ý combo", "tư vấn combo", "chọn giúp combo"],
    "wifi_inquiry": ["wifi", "pass wifi", "mật khẩu mạng"],
    "payment_inquiry": ["thanh toán", "trả tiền", "payment method"],
    "visual_product_search": ["ảnh của", "hình món", "trông như thế nào", "picture of", "giống món nào"],
    "order_status_inquiry": ["đơn hàng của tôi", "kiểm tra đơn", "trạng thái đơn", "tình trạng đơn hàng"],
    "generic_question": ["bạn là ai", "bạn làm được gì"],
    "affirmation": ["đúng", "vâng", "ok", "oke", "đồng ý", "yes", "chốt", "xác nhận", "đặt đi"],
    "negation": ["không", "hủy", "bỏ", "đừng", "no", "cancel", "thôi"],
    "provide_order_details": ["một ly", "2 phần", "size lớn", "ít đường", "không đá"],
    "quality_inquiry": ["ngon không", "chất lượng", "ổn không", "tươi không"],
    "ambiance_inquiry": ["không gian", "chỗ ngồi", "thoải mái không", "yên tĩnh không", "checkin", "decor"],
    "reservation_inquiry": ["đặt bàn", "giữ chỗ", "book table"],
    "feedback_complaint": ["góp ý", "phản hồi", "khiếu nại", "chất lượng kém"],
    "help_inquiry": ["giúp", "cần hỗ trợ", "help"],
    "bot_identity": ["bạn là ai", "who are you", "tên bot"],
    "bot_capability": ["bạn làm được gì", "what can you do", "chức năng bot"],
    "best_seller_inquiry": ["bán chạy", "món hot", "ưa thích", "best seller"]
}

ENTITY_PATTERNS = {
   "product": r"(?i)\b(" + "|".join(sorted([
        "cà phê chồn", # <-- Ưu tiên cụm dài
        "cà phê sữa đá", "cà phê đen đá", "cà phê trứng", "cà phê muối", "cà phê cốt dừa",
        "trà đào cam sả", "trà sữa trân châu đường đen", "cold brew truyền thống",
        # ... (Thêm tất cả các sản phẩm của bạn, những cụm dài lên trước) ...
        "cà phê sữa", "cà phê đen", "bạc xỉu", "latte", "espresso", "cappuccino", "mocha", "americano", "cold brew",
        "trà đào", "trà tắc", "trà vải", "trà sen", "trà hoa cúc", "trà ô long", "trà gừng", "trà sữa", "trà xanh", "trà đen", "hồng trà",
        "sinh tố bơ", "sinh tố dâu", "sinh tố xoài", "chanh tuyết", "sinh tố việt quất", "mãng cầu", "sapoche",
        "nước ép cam", "nước ép táo", "nước ép dưa hấu", "nước ép cà rốt", "nước ép dứa", "nước ép ổi", "nước ép cần tây",
        "khoai tây chiên", "bánh phô mai", "bánh tiramisu", "bánh sừng bò", "croissant", "cookie",
        "matcha đá xay", "chocolate đá xay", "oreo đá xay",
        "cà phê", "cafe", "coffee", "trà", "tea", "sinh tố", "smoothie", "nước ép", "juice",
        "bánh", "pastry", "snack", "đá xay", "ice blended", "frappe", "yogurt"
    ], key=len, reverse=True)) + r")\b", # Sắp xếp theo độ dài giảm dần để ưu tiên match dài hơn
    "category": r"(?i)\b(cà phê|cafe|coffee|trà|tea|sinh tố|smoothie|nước ép|juice|bánh|pastry|bánh ngọt|đồ ăn(?: sáng| trưa| tối| nhẹ| chính| vặt| thêm)?|món chính|snack|đá xay|ice blended|frappe|yogurt|sữa chua|kem|ice cream|đặc biệt|signature|combo|gói|set|mì|pasta|cơm|rice|phở|noodles|bún|xôi|bánh mì)\b",
    "size": r"(?i)\b(size s|size m|size l|nhỏ|vừa|lớn|bé|to|bự|trung bình|regular|small|medium|large|big)\b",
    "quantity_pattern": r"\b((?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|[0-9]+))\s*(ly|cốc|cái|phần|suất|chai|tách|cup|cups?|shot|gói|hũ|bịch|hộp|phần ăn|đĩa|tô|ổ)\b",
    "notes": r"(?i)\b(ít đường|nhiều đá|không đá|ít ngọt|thêm ngọt|ngọt vừa|nóng|lạnh|ấm|không sữa|sữa tươi|sữa đặc|sữa yến mạch|sữa hạnh nhân|thêm kem|ít kem|kem cheese|macchiato|không kem|thêm trân châu(?: đen| trắng| hoàng kim| sợi)?|boba|full topping|topping|thêm topping|không topping|không đường|no sugar|less ice|no ice|more ice|less sweet|hot|cold|warm|no milk|add cream|less cream|add whip|no whip|extra shot|double shot|decaf|không caffeine|nguyên chất|đặc|loãng|không hành|không tỏi|không ớt|ít cay|cay nhiều|thêm trứng(?: ốp la| lòng đào| chín)?|chín kỹ|tái|vừa chín tới|thêm phô mai|không rau|nhiều rau|không giá)\b",
    "visual_keywords": r"(?i)\b(trắng|đen|nâu(?: đậm| nhạt| sữa| sô cô la| socola)?|vàng(?: nhạt| tươi| đậm| nghệ)?|đỏ(?: tươi| đậm| cam| rượu vang| gạch)?|xanh lá(?: cây| non| đậm| bạc hà| matcha| rêu)?|xanh dương(?: nước biển| da trời| navy| coban)?|hồng(?: phấn| sen| cánh sen| đậm| cam)?|cam(?: tươi| đất)?|tím(?: than| đậm| nhạt| cà)?|kem|be|nude|xám|ghi|bọt|foam|nhiều lớp|phân tầng|layer|có tầng|trong suốt|clear|trong veo|trong vắt|sánh đặc|sánh mịn|thick|đặc quánh|đông đặc|loãng|thin|lỏng|sệt|sệt sệt|giòn|crisp|mềm|soft|dẻo|mịn|smooth|sần|sần sùi|grainy|hạt|lợn cợn|lấp lánh|shiny|sparkling|óng ánh|phủ kem|có kem|kem mịn|có sốt|nhiều nước sốt|trang trí|decor đẹp|cắt lát|thái sợi|viên|hình tròn|vuông|dài|xoắn|có đá|nhiều đá|ít đá|đá viên|đá xay)\b",
    "order_number": r"(?i)(?:đơn|mã|số|dh|hd|order|bill)\s*[:#\-]?\s*([A-Za-z0-9]{3}[-\s]?\w{4,}[-\s]?\w{3,}|[A-Za-z0_9]{5,20})\b",
    "price_query_kw": r"(?i)\b(giá|bao nhiêu|tiền|cost|price|rate|giá tiền|giá cả)\b",
    "availability_query_kw": r"(?i)\b(còn hàng|hết hàng|có bán|có sẵn|available|còn ko|còn không)\b",
    "combo_keyword_kw": r"(?i)\b(combo|gói|set|kết hợp|suất ăn)\b",
    "quality_kw": r"(?i)\b(ngon|dở|chất lượng|ổn|tươi|tốt|tệ|hay|hợp|hạp|đảm bảo|vệ sinh)\b",
    "ambiance_kw": r"(?i)\b(không gian|chỗ ngồi|thoải mái|yên tĩnh|checkin|decor|đẹp|view|trang trí|nhạc|bài trí|phong cách)\b",
    "reservation_kw": r"(?i)\b(đặt bàn|giữ chỗ|book table|reservation|đặt trước)\b",
    "feedback_kw": r"(?i)\b(góp ý|phản hồi|khiếu nại|phàn nàn|tệ|chê|đánh giá)\b",
    "help_kw": r"(?i)\b(giúp|cần hỗ trợ|help|hướng dẫn|làm sao)\b",
    "bot_kw": r"(?i)\b(bạn là ai|mày là ai|bot|chatbot|who are you|làm được gì|chức năng|tên gì|trợ lý ảo)\b",
    "best_seller_kw": r"(?i)\b(bán chạy|ưa thích|món hot|best seller|popular|phổ biến|chuộng|best selling|signature drink)\b",
    "confirm_yes_strict": r"^(?:yes|yep|ừ|ukm|đồng ý|chốt|được|ok|oke|okê|okie|đặt đi|đặtเลย|xác nhận|confirm|đúng rồi|chắc chắn|mua)$",
    "confirm_no_strict": r"^(?:no|nope|không|thôi|hủy|bỏ|đừng|cancel|ngừng|dừng|stop|ko|hong|hok|đếu|déll)$"
}

tfidf_vectorizer = None
intent_classifier_model = None
RESPONSE_TEMPLATES = {}
conversation_context = {}

def create_default_templates():
    logger = get_logger()
    try:
        default_path = os.path.join(DATA_DIR, 'chatbot_responses.json')
        if os.path.exists(default_path):
            with open(default_path, 'rb') as f_handle:
                content_bytes = f_handle.read()
                content_string = content_bytes.decode('utf-8-sig')
                return json.loads(content_string)
        else:
            logger.error(f"Default chatbot_responses.json not found at: {default_path}! Using hardcoded basic defaults.")
            return {"greeting": ["Xin chào!", "Chào bạn, Dragon Coffee nghe!"], "goodbye": ["Tạm biệt!", "Hẹn gặp lại!"], "thanks": ["Không có gì ạ!", "Rất vui được giúp bạn."], "fallback": ["Xin lỗi, tôi chưa hiểu lắm.", "Bạn hỏi lại câu khác được không?"]}
    except Exception as e:
        logger.error(f"Critical error creating/loading default response templates: {e}", exc_info=True)
        return {"fallback": ["Lỗi tải mẫu chatbot."], "greeting": ["Xin chào!"]}

def load_or_create_templates():
    global RESPONSE_TEMPLATES
    logger = get_logger()
    default_templates_data = create_default_templates()
    try:
        if os.path.exists(TEMPLATES_FILE_PATH):
            with open(TEMPLATES_FILE_PATH, 'rb') as f:
                loaded_templates = json.loads(f.read().decode('utf-8-sig'))
                merged_templates = {**default_templates_data, **loaded_templates}
                all_expected_intents = set(INTENTS_DATA_KEYWORDS.keys()).union({
                    'category_inquiry_result', 'category_not_found', 'category_inquiry_noproduct',
                    'product_info_no_price', 'product_not_found', 'product_not_found_suggestion',
                    'check_availability_result','check_availability_not_found', 'promotion_inquiry_none',
                    'suggest_combo_result', 'suggest_combo_no_pref',
                    'order_status_found', 'order_status_not_found', 'order_status_ask_number', 'order_status_no_order_history',
                    'order_intent_noproduct','order_confirmation_request', 'order_confirmation_yes', 'order_confirmation_no',
                    'order_intent_ask_qty_notes',
                    'order_success', 'order_failed', 'order_confirmation_missing_info',
                    'quality_inquiry_product', 'quality_inquiry_general',
                    'ambiance_inquiry', 'reservation_inquiry', 'feedback_complaint',
                    'help_inquiry', 'bot_identity', 'bot_capability', 'best_seller_inquiry', 'best_seller_inquiry_none',
                    'visual_product_search_result', 'visual_product_search_notfound', 'visual_product_search_nokeywords',
                    'fallback', 'error'
                })
                missing_templates = [intent for intent in all_expected_intents if intent not in merged_templates or not merged_templates[intent] or not isinstance(merged_templates[intent], list)]
                if missing_templates:
                     logger.warning(f"Templates missing or invalid for intents: {', '.join(missing_templates)}. Using fallback/default templates for these.")
                     for intent in missing_templates:
                         if intent in default_templates_data: merged_templates[intent] = default_templates_data[intent]
                         else: merged_templates[intent] = [f"Tôi chưa có mẫu phản hồi cho ý định '{intent}'."]
                RESPONSE_TEMPLATES = merged_templates
                logger.info(f"Successfully loaded/merged {len(RESPONSE_TEMPLATES)} response templates.")
        else:
            logger.warning(f"Template file not found: {TEMPLATES_FILE_PATH}. Creating defaults and saving.")
            RESPONSE_TEMPLATES = default_templates_data
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(TEMPLATES_FILE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(RESPONSE_TEMPLATES, f, ensure_ascii=False, indent=4)
                logger.info(f"Saved default templates to {TEMPLATES_FILE_PATH}")
            except Exception as save_e: logger.error(f"Could not save default templates: {save_e}")
    except Exception as e:
        logger.error(f"Error during loading/creating templates: {e}. Using basic defaults.", exc_info=True)
        RESPONSE_TEMPLATES = {"fallback": ["Chatbot bị lỗi mẫu phản hồi."], "greeting": ["Xin chào! Chatbot gặp lỗi."]}

def preprocess_text(text):
    logger = get_logger()
    try:
        if not text or not isinstance(text, str): return []
        text_lower = text.lower()
        text_cleaned = re.sub(r'[^\w\s.,!?' + re.escape('àáãạảăắằẳẵặâấầẩẫậèéẹẻẽêềếểễệđìíỉĩịòóõọỏôốồổỗộơớờởỡợùúũụủưứừửữựỳýỷỹỵ') + r']', ' ', text_lower)
        text_cleaned = re.sub(r'\s+', ' ', text_cleaned).strip()
        tokens = text_cleaned.split()
        filtered_tokens = [
            lemmatizer.lemmatize(token) if lemmatizer else token
            for token in tokens
            if token not in ALL_STOP_WORDS
            and (token.isalpha() or token.isdigit() or token in ['.', ',', '!', '?'])
            and len(token) > 0
        ]
        return filtered_tokens
    except Exception as e:
        logger.error(f"Error preprocessing text '{text[:50]}...': {e}", exc_info=False)
        text_cleaned = re.sub(r'[^\w\s]+', ' ', text.lower()).strip()
        return text_cleaned.split()

def extract_entities_ml(text):
    logger = get_logger()
    entities = {}; text_lower = text.lower(); processed_spans = []
    def add_if_not_overlapped(entity_key, value, start, end, is_list=False):
        for p_start, p_end in processed_spans:
            if max(start, p_start) < min(end, p_end):
                if entity_key not in ["notes", "visual_keywords"]: return False
        if is_list: entities.setdefault(entity_key, []).append(value)
        elif entity_key not in entities: entities[entity_key] = value
        processed_spans.append((start, end))
        return True
    priority_order = [
         "order_number", "product", "quantity_pattern", "category", "notes", "best_seller_kw",
         "price_query_kw", "availability_query_kw", "visual_keywords", "combo_keyword_kw",
         "quality_kw", "ambiance_kw", "reservation_kw", "feedback_kw", "help_kw", "bot_kw", "size"
     ]
    for entity_key in priority_order:
         pattern = ENTITY_PATTERNS.get(entity_key)
         if not pattern: continue
         try:
             for match in re.finditer(pattern, text_lower):
                 start, end = match.span()
                 value = match.group(0).strip()
                 raw_group1 = match.group(1).strip() if len(match.groups()) > 0 and match.group(1) else None
                 raw_group2 = match.group(2).strip() if len(match.groups()) > 1 and match.group(2) else None

                 if entity_key == "order_number": add_if_not_overlapped('order_number', raw_group1 if raw_group1 else value, start, end)
                 elif entity_key == "quantity_pattern":
                     if raw_group1: add_if_not_overlapped('quantity_value', raw_group1, start, end)
                     if raw_group2: add_if_not_overlapped('quantity_unit', raw_group2, start, end)
                 elif entity_key in ["product", "category", "notes", "visual_keywords"]:
                     add_if_not_overlapped(entity_key, value, start, end, is_list=True)
                 elif entity_key == "size": add_if_not_overlapped('size', value, start, end)
                 elif entity_key.endswith('_kw'):
                     entity_name = entity_key.replace('_kw', '')
                     if entity_name not in entities: entities[entity_name] = True
                     processed_spans.append((start,end))
         except Exception as regex_e: logger.error(f"Regex error for {entity_key}: {regex_e}", exc_info=False)

    for key in ["product", "category", "notes", "visual_keywords"]:
        if key in entities: entities[key] = sorted(list(set(e.lower() for e in entities[key] if e)), key=len, reverse=True)
    qty_str = entities.get('quantity_value')
    if qty_str:
        num_map = {'một': 1,'hai': 2,'ba': 3,'bốn': 4,'năm': 5,'sáu': 6,'bảy': 7,'tám': 8,'chín': 9,'mười': 10}
        try: entities['quantity'] = max(1, num_map.get(qty_str.lower(), int(qty_str)))
        except ValueError: logger.warning(f"Invalid qty: {qty_str}"); entities['quantity'] = 1 # Mặc định là 1 nếu không parse được
        if 'quantity_value' in entities: del entities['quantity_value']
    else:
        entities['quantity'] = None # Sửa: Để None nếu không có số lượng rõ ràng, để handler xử lý
        
    expected_keys_list = ['product', 'category', 'notes', 'visual_keywords']
    expected_keys_bool = ['price_query', 'availability_query', 'combo_keyword', 'quality', 'ambiance', 'reservation', 'feedback', 'help', 'bot', 'best_seller']
    expected_keys_single_val = ['size', 'order_number', 'quantity_unit']
    for k in expected_keys_list: entities.setdefault(k, [])
    for k in expected_keys_bool: entities.setdefault(k, False)
    for k in expected_keys_single_val: entities.setdefault(k, None)
    if 'quantity' not in entities: entities['quantity'] = None # Đảm bảo 'quantity' luôn có key, có thể là None
    return entities

def create_default_training_data():
    logger = get_logger(); logger.info("Creating default training data...")
    td = []
    for intent, phrases in INTENTS_DATA_KEYWORDS.items():
        for p in phrases: td.append({"text": p.strip(), "intent": intent})
    custom_examples = [
        {"text": "Quán còn mở cửa không ad ơi?", "intent": "greeting"},
        {"text": "Có ai hỗ trợ mình không?", "intent": "greeting"},
        {"text": "Cho tôi xem thực đơn đồ uống.", "intent": "menu_inquiry"},
        {"text": "Menu bánh ngọt có những loại nào vậy shop?", "intent": "category_inquiry"},
        {"text": "Quán có bán món gì ăn sáng không?", "intent": "category_inquiry"},
        {"text": "Cà phê trứng của quán có đặc biệt không?", "intent": "product_info"},
        {"text": "Giá món Latte Hạnh Nhân size M là bao nhiêu ạ?", "intent": "product_price_inquiry"},
        {"text": "Hôm nay quán còn Trà Đào Cam Sả không?", "intent": "check_availability"},
        {"text": "Bánh Tiramisu có dùng rượu rum không shop?", "intent": "product_info"},
        {"text": "Đặt cho mình 1 ly cà phê sữa đá, size vừa, ít ngọt.", "intent": "order_intent"},
        {"text": "Tôi muốn mua 2 bánh sừng bò hạnh nhân mang về.", "intent": "order_intent"},
        {"text": "Lấy cho em 3 phần khoai tây chiên phô mai.", "intent": "order_intent"},
        {"text": "Tháng này quán có ưu đãi gì đặc biệt cho thành viên không?", "intent": "promotion_inquiry"},
        {"text": "Mã giảm giá DRAGONNEW còn dùng được không?", "intent": "promotion_inquiry"},
        {"text": "Gợi ý cho tôi một combo đồ uống thanh mát và bánh ngọt nhẹ nhàng.", "intent": "suggest_combo"},
        {"text": "Đi 2 người thì nên chọn combo nào cho bữa trưa?", "intent": "suggest_combo"},
        {"text": "Tìm giúp tôi ảnh món nước màu xanh lá cây, có nhiều bọt kem trắng ở trên.", "intent": "visual_product_search"},
        {"text": "Cho xem hình món bánh có lớp socola chảy, nhìn hấp dẫn.", "intent": "visual_product_search"},
        {"text": "Kiểm tra đơn hàng ORD-ABC123 giúp tôi với.", "intent": "order_status_inquiry"},
        {"text": "Đơn hàng tôi đặt sáng nay mã #555XYZ đã tới đâu rồi?", "intent": "order_status_inquiry"},
        {"text": "Đúng rồi, xác nhận đơn đó đi.", "intent": "affirmation"},
        {"text": "Không, tôi muốn hủy món đó.", "intent": "negation"},
        {"text": "cho tôi 2 ly trà sữa và 1 bánh mì chảo, ghi chú trà sữa ít ngọt", "intent": "order_intent"},
        {"text": "lấy 1 cà phê đen, không đường không đá", "intent": "order_intent"},
        {"text": "tôi muốn 1 phần cơm sườn và 1 ly trà tắc", "intent": "order_intent"},
        {"text": "ok", "intent": "affirmation"},
        {"text": "yes", "intent": "affirmation"},
        {"text": "ừ", "intent": "affirmation"},
        {"text": "đồng ý", "intent": "affirmation"},
        {"text": "no", "intent": "negation"},
        {"text": "ko", "intent": "negation"},
        {"text": "thôi", "intent": "negation"},
        {"text": "hủy", "intent": "negation"},
        {"text": "một ly thôi", "intent": "provide_order_details"},
        {"text": "hai phần nha", "intent": "provide_order_details"},
        {"text": "cho mình size lớn", "intent": "provide_order_details"},
        {"text": "ghi chú là ít đường", "intent": "provide_order_details"},
        {"text": "thêm trân châu", "intent": "provide_order_details"},
        {"text": "số lượng là 3", "intent": "provide_order_details"},
        {"text": "Cà phê sữa đá ở đây có ngon bằng chỗ X không?", "intent": "quality_inquiry"},
        {"text": "Không gian quán có phù hợp để làm việc nhóm không?", "intent": "ambiance_inquiry"},
        {"text": "Tôi muốn đặt bàn cho 4 người tối thứ 7 này.", "intent": "reservation_inquiry"},
        {"text": "Phục vụ hôm qua hơi chậm, tôi muốn góp ý.", "intent": "feedback_complaint"},
        {"text": "Bot có thể đặt hàng giúp tôi không?", "intent": "bot_capability"},
        {"text": "Chào bot, bạn là ai vậy?", "intent": "bot_identity"},
        {"text": "Món nào là best seller của quán vậy shop?", "intent": "best_seller_inquiry"},
        {"text": "Thời tiết hôm nay đẹp quá nhỉ.", "intent": "fallback"},
        {"text": "Con rồng có thật không?", "intent": "fallback"}
    ]
    td.extend(custom_examples)
    unique_td = []; texts_seen = set()
    for item in td:
        text_key = item['text'].lower().strip()
        if text_key not in texts_seen: unique_td.append(item); texts_seen.add(text_key)
    logger.info(f"Generated {len(unique_td)} unique default training samples.")
    if not os.path.exists(TRAINING_DATA_PATH):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(TRAINING_DATA_PATH, 'w', encoding='utf-8') as f:
                json.dump(unique_td, f, ensure_ascii=False, indent=4)
            logger.info(f"Saved default training data to {TRAINING_DATA_PATH}")
        except Exception as e: logger.error(f"Could not save default training data: {e}")
    return unique_td

def load_training_data():
     logger = get_logger()
     if not os.path.exists(TRAINING_DATA_PATH):
         logger.info(f"{TRAINING_DATA_PATH} not found. Generating default training data...")
         default_data = create_default_training_data()
         return default_data
     try:
         with open(TRAINING_DATA_PATH, 'rb') as f_handle:
             content_bytes = f_handle.read()
             content_string = content_bytes.decode('utf-8-sig')
             data = json.loads(content_string)
         logger.info(f"Loaded training data from {TRAINING_DATA_PATH}: {len(data)} samples.")
         return data
     except Exception as e:
         logger.error(f"Failed to load training data: {e}. Using default.", exc_info=True)
         return create_default_training_data()

def train_intent_model():
    global tfidf_vectorizer, intent_classifier_model
    logger = get_logger()
    training_data = load_training_data()
    if not training_data: logger.warning("No training data. Cannot train."); tfidf_vectorizer=None; intent_classifier_model=None; return False
    texts = [d.get("text","") for d in training_data if d.get("text")]; intents = [d.get("intent","") for d in training_data if d.get("intent")]
    if len(texts)!=len(intents) or not texts or len(set(intents))<2: logger.error(f"Invalid data ({len(texts)} texts, {len(set(intents))} intents)."); tfidf_vectorizer=None; intent_classifier_model=None; return False
    logger.info(f"Training with {len(texts)} samples, {len(set(intents))} intents...")
    try:
        tfidf_vectorizer = TfidfVectorizer(analyzer='word', ngram_range=(1,3), max_features=2500, stop_words=list(ALL_STOP_WORDS), min_df=1, sublinear_tf=True, norm='l2')
        X_tfidf = tfidf_vectorizer.fit_transform(texts)
        intent_classifier_model = LogisticRegression(solver='liblinear', random_state=42, C=1.8, class_weight='balanced', max_iter=1500, tol=1e-6, multi_class='ovr')
        intent_classifier_model.fit(X_tfidf, intents)
        score = intent_classifier_model.score(X_tfidf, intents); logger.info(f"Model training score: {score:.4f}")
        os.makedirs(MODELS_DIR, exist_ok=True); joblib.dump(intent_classifier_model, INTENT_MODEL_PATH); joblib.dump(tfidf_vectorizer, TFIDF_VECTORIZER_PATH)
        logger.info(f"Model & Vectorizer saved to {MODELS_DIR}"); return True
    except Exception as train_err: logger.error(f"ML training error: {train_err}", exc_info=True); tfidf_vectorizer=None; intent_classifier_model=None; return False

def load_trained_model():
    global tfidf_vectorizer, intent_classifier_model; logger = get_logger()
    if all([tfidf_vectorizer, intent_classifier_model]): logger.debug("Model/Vectorizer already loaded."); return True
    success = True
    if not os.path.exists(TFIDF_VECTORIZER_PATH): logger.warning(f"Vectorizer missing: {TFIDF_VECTORIZER_PATH}"); success=False
    if not os.path.exists(INTENT_MODEL_PATH): logger.warning(f"Model missing: {INTENT_MODEL_PATH}"); success=False
    if not success:
        logger.error("Model/vectorizer files missing. Retraining attempt...")
        if not train_intent_model(): logger.critical("Auto-retrain FAILED. NLU limited."); return False
        return True
    try:
        tfidf_vectorizer = joblib.load(TFIDF_VECTORIZER_PATH); intent_classifier_model = joblib.load(INTENT_MODEL_PATH)
        logger.info("Loaded model and vectorizer."); return True
    except Exception as e: logger.error(f"Error loading model: {e}", exc_info=True); tfidf_vectorizer=None; intent_classifier_model=None; return False

def predict_intent_ml(text):
    logger = get_logger()
    if not all([tfidf_vectorizer, intent_classifier_model]):
        logger.error("ML Model/Vectorizer not loaded for prediction. Attempting to load...")
        if not load_trained_model(): logger.error("Failed to load model for ML prediction."); return None, 0.0
    try:
        cleaned_text = text.lower(); X = tfidf_vectorizer.transform([cleaned_text])
        intent = intent_classifier_model.predict(X)[0]; proba = intent_classifier_model.predict_proba(X)[0]
        confidence = proba[intent_classifier_model.classes_.tolist().index(intent)]
        return intent, float(confidence)
    except Exception as e: logger.error(f"ML intent prediction error for '{text[:50]}...': {e}", exc_info=True); return None, 0.0

def detect_intent_combined(text, db_session, session_id=None):
    logger = get_logger()
    entities = extract_entities_ml(text)
    logger.debug(f"Entities extracted for intent detection: {entities}")
    context = conversation_context.get(session_id)
    text_lower_for_intent = text.lower().strip()
    
    # Khởi tạo rule_based_intents_handled ngay từ đầu
    rule_based_intents_handled = set()

    if context:
        current_state = context.get('state')
        if current_state == 'awaiting_order_confirmation':
            if ENTITY_PATTERNS.get('confirm_yes_strict') and re.fullmatch(ENTITY_PATTERNS['confirm_yes_strict'], text_lower_for_intent):
                logger.debug("Intent [Strict Context]: order_confirmation_yes")
                return "order_confirmation_yes", 1.0, entities
            if ENTITY_PATTERNS.get('confirm_no_strict') and re.fullmatch(ENTITY_PATTERNS['confirm_no_strict'], text_lower_for_intent):
                logger.debug("Intent [Strict Context]: order_confirmation_no")
                return "order_confirmation_no", 1.0, entities
        elif current_state == 'awaiting_quantity_and_notes':
             if entities.get('quantity') is not None or entities.get('notes'):
                logger.debug("Intent [Context]: provide_order_details (qty/notes for pending order)")
                rule_based_intents_handled.add("provide_order_details") # Thêm vào đây nếu nó là rule-based
                return "provide_order_details", 0.99, entities
    
    if entities.get("order_number") and not (entities.get("product") or any(kw in text_lower_for_intent for kw in INTENTS_DATA_KEYWORDS.get('order_intent', ["đặt","mua","lấy","order"]))):
        logger.debug("Intent [Rule High: Order Number Dominant]: order_status_inquiry")
        rule_based_intents_handled.add("order_status_inquiry")
        return "order_status_inquiry", 0.98, entities
        
    order_intent_keywords = INTENTS_DATA_KEYWORDS.get('order_intent', [])
    if entities.get("product") and any(kw in text_lower_for_intent for kw in order_intent_keywords):
        logger.debug("Intent [Rule High: Product + Order Trigger]: order_intent")
        rule_based_intents_handled.add("order_intent")
        return "order_intent", 0.97, entities
        
    availability_keywords = INTENTS_DATA_KEYWORDS.get('check_availability', [])
    if entities.get("product") and (entities.get("availability_query") or any(kw in text_lower_for_intent for kw in availability_keywords)):
        logger.debug("Intent [Rule High: Product + Avail Query]: check_availability")
        rule_based_intents_handled.add("check_availability")
        return "check_availability", 0.96, entities
        
    price_keywords = INTENTS_DATA_KEYWORDS.get('product_price_inquiry', [])
    if entities.get("product") and (entities.get("price_query") or any(kw in text_lower_for_intent for kw in price_keywords)):
        logger.debug("Intent [Rule High: Product + Price Query]: product_price_inquiry")
        rule_based_intents_handled.add("product_price_inquiry")
        return "product_price_inquiry", 0.96, entities

    product_info_keywords = INTENTS_DATA_KEYWORDS.get("product_info", [])
    if entities.get("product"):
        is_very_short_product_query = False
        if entities["product"]:
            num_product_words = len(entities["product"][0].split())
            if len(text.split()) <= num_product_words + 2:
                is_very_short_product_query = True
        
        if any(kw in text_lower_for_intent for kw in product_info_keywords) or is_very_short_product_query:
            if not (len(entities["product"]) == 1 and entities["product"][0] in ["cà phê", "trà", "bánh", "cafe", "tea", "cake"] and not is_very_short_product_query):
                logger.info(f"Intent [Rule High: Product Info Trigger]: product_info for '{entities['product'][0]}'")
                rule_based_intents_handled.add("product_info")
                return "product_info", 0.95, entities

    visual_search_keywords = INTENTS_DATA_KEYWORDS.get("visual_product_search", ["ảnh", "hình"])
    if (entities.get("visual_keywords") or \
       (entities.get("product") and any(kw in text_lower_for_intent for kw in visual_search_keywords))) and \
       not any(kw in text_lower_for_intent for kw in ["mô tả", "thông tin", "chi tiết"]):
        logger.debug("Intent [Rule: Visual Dominant]: visual_product_search")
        rule_based_intents_handled.add("visual_product_search")
        return "visual_product_search", 0.93, entities
        
    if entities.get("category") and not entities.get("product") and not any(kw in text_lower_for_intent for kw in ["menu","thực đơn"]):
        logger.debug("Intent [Rule: Category no Product/Menu]: category_inquiry")
        rule_based_intents_handled.add("category_inquiry")
        return "category_inquiry", 0.92, entities
        
    if entities.get("combo_keyword") and not any(kw in text_lower_for_intent for kw in INTENTS_DATA_KEYWORDS.get('suggest_combo', ["gợi ý", "tư vấn"])):
         if "thực đơn" in text_lower_for_intent or "menu" in text_lower_for_intent:
             logger.debug("Intent [Rule: Combo keyword with menu]: menu_inquiry")
             rule_based_intents_handled.add("menu_inquiry")
             return "menu_inquiry", 0.90, entities
         else:
             logger.debug("Intent [Rule: Combo General Inquiry]: combo_inquiry")
             rule_based_intents_handled.add("combo_inquiry") # Thêm vào set
             return "combo_inquiry", 0.91, entities

    ml_intent, ml_conf = predict_intent_ml(text)
    ML_CONF_THRESHOLD = float(current_app.config.get('CHATBOT_ML_MODEL_CONFIDENCE_THRESHOLD', 0.60))

    if ml_intent and ml_conf >= ML_CONF_THRESHOLD:
        logger.info(f"Intent [ML]: '{ml_intent}' (Conf: {ml_conf:.2f})")
        if ml_intent == 'product_info' and not entities.get('product') and ml_conf < 0.75 :
             logger.debug(f"ML '{ml_intent}' ({ml_conf:.2f}) without product entity and conf < 0.75. Checking keyword fallback.")
        elif ml_intent in ["greeting", "goodbye", "thanks"] and entities.get("product") and len(text.split()) > 3:
             logger.debug(f"ML detected '{ml_intent}' for a long query with product. Re-evaluating with keywords for product_info possibility.")
        else:
            return ml_intent, ml_conf, entities
    elif ml_intent:
        logger.info(f"ML Intent '{ml_intent}' with low confidence ({ml_conf:.2f}). Proceeding to keyword fallback.")

    keyword_scores = defaultdict(float)
    ML_CONSIDERED_THRESHOLD = 0.35
    
    # Khởi tạo lại already_considered_intents ở đây, bao gồm các rule đã thực sự khớp
    # (không phải tất cả các rule có thể có)
    already_considered_intents_for_keyword_fallback = set(rule_based_intents_handled) 
    if ml_intent and ml_conf >= ML_CONSIDERED_THRESHOLD:
        already_considered_intents_for_keyword_fallback.add(ml_intent)

    for intent, keywords_list in INTENTS_DATA_KEYWORDS.items():
        if intent in already_considered_intents_for_keyword_fallback:
            if not (intent == 'product_info' and ml_intent == 'product_info'):
                continue
            
        weight = 1.0
        if intent == 'product_info': weight = 2.5 
        elif intent in ["greeting", "goodbye", "thanks", "affirmation", "negation"]: weight = 2.2
        elif intent in ["hours_inquiry", "location_inquiry", "wifi_inquiry", "payment_inquiry","promotion_inquiry"]: weight = 1.8
        elif intent in ["suggest_combo", "best_seller_inquiry","help_inquiry","bot_identity", "bot_capability",
                       "quality_inquiry", "ambiance_inquiry", "reservation_inquiry", "feedback_complaint"]: weight = 1.7
        elif intent == "generic_question": weight = 0.5
        
        for phrase in keywords_list:
            if phrase in text_lower_for_intent:
                keyword_scores[intent] += len(phrase.split()) * weight * (1.5 if len(phrase.split()) > 1 else 1.0)
    
    best_keyword_intent = None
    best_keyword_score = 0.0
    if keyword_scores:
        best_keyword_intent = max(keyword_scores, key=keyword_scores.get)
        best_keyword_score = keyword_scores[best_keyword_intent]
    
    KEYWORD_FALLBACK_THR = float(current_app.config.get('CHATBOT_ML_KEYWORD_FALLBACK_THRESHOLD', 2.8))

    if best_keyword_score >= KEYWORD_FALLBACK_THR:
        if ml_intent and ml_conf >= ML_CONSIDERED_THRESHOLD and ml_intent != best_keyword_intent:
            if best_keyword_intent == 'product_info' and ml_intent in ['greeting','thanks','goodbye']:
                logger.info(f"Intent [Keyword Priority]: Keyword '{best_keyword_intent}' (Score: {best_keyword_score:.2f}) chosen over weak generic ML '{ml_intent}' ({ml_conf:.2f}).")
                return best_keyword_intent, min(best_keyword_score / (KEYWORD_FALLBACK_THR * 1.5), 0.90), entities
            
            if best_keyword_score > (ml_conf * 3.5) and best_keyword_score > KEYWORD_FALLBACK_THR + 0.5 :
                 logger.info(f"Intent [Keyword Override]: ML was '{ml_intent}' ({ml_conf:.2f}), but keyword '{best_keyword_intent}' (Score: {best_keyword_score:.2f}) is significantly stronger and different.")
                 return best_keyword_intent, min(best_keyword_score / (KEYWORD_FALLBACK_THR * 1.5), 0.88), entities
            else: 
                if ml_intent not in rule_based_intents_handled:
                    logger.info(f"Intent [ML Low Confidence Retained]: '{ml_intent}' (Conf: {ml_conf:.2f}) retained over weaker/similar keyword '{best_keyword_intent}' ({best_keyword_score:.2f}).")
                    return ml_intent, ml_conf, entities
        logger.info(f"Intent [Keyword Fallback]: '{best_keyword_intent}' (Score: {best_keyword_score:.2f})")
        return best_keyword_intent, min(best_keyword_score / (KEYWORD_FALLBACK_THR * 1.5), 0.88), entities
    
    elif ml_intent and ml_conf >= ML_CONSIDERED_THRESHOLD and ml_intent not in rule_based_intents_handled:
         logger.info(f"Intent [ML Low Confidence Accepted as Fallback]: '{ml_intent}' (Conf: {ml_conf:.2f}) because no keyword score met threshold ({KEYWORD_FALLBACK_THR}).")
         return ml_intent, ml_conf, entities

    final_fallback_info = f"(ML: {ml_intent}@{ml_conf:.2f} if any, Best Keyword: {best_keyword_intent if keyword_scores else 'N/A'}@{best_keyword_score if keyword_scores else 'N/A'})"
    logger.info(f"Intent [Final Fallback] for text: '{text[:70]}...' {final_fallback_info}")
    return "fallback", 0.0, entities

INTENT_HANDLER_METHODS = {
    "greeting": "handle_greeting", "goodbye": "handle_goodbye", "thanks": "handle_thanks",
    "hours_inquiry": "handle_hours_inquiry", "location_inquiry": "handle_location_inquiry",
    "menu_inquiry": "handle_menu_inquiry", "category_inquiry": "handle_category_inquiry",
    "product_info": "handle_product_info", "product_price_inquiry": "handle_product_price_inquiry",
    "check_availability": "handle_check_availability", "promotion_inquiry": "handle_promotion_inquiry",
    "combo_inquiry": "handle_suggest_combo", "suggest_combo": "handle_suggest_combo",
    "wifi_inquiry": "handle_wifi_inquiry", "payment_inquiry": "handle_payment_inquiry",
    "order_status_inquiry": "handle_order_status_inquiry", "order_intent": "handle_order_intent",
    "visual_product_search": "handle_visual_product_search", "generic_question": "handle_generic_question",
    "affirmation": "handle_affirmation", "negation": "handle_negation",
    "provide_order_details": "handle_provide_order_details",
    "quality_inquiry": "handle_quality_inquiry", "ambiance_inquiry": "handle_ambiance_inquiry",
    "reservation_inquiry": "handle_reservation_inquiry", "feedback_complaint": "handle_feedback_complaint",
    "help_inquiry": "handle_help_inquiry", "bot_identity": "handle_bot_identity",
    "bot_capability": "handle_bot_identity", "best_seller_inquiry": "handle_best_seller_inquiry",
    "fallback": "handle_fallback", "order_confirmation_yes": "handle_affirmation",
    "order_confirmation_no": "handle_negation"
}

class MLChatbot:
    def __init__(self, database_instance):
        self.db = database_instance
        self.logger = get_logger()
        self.load_resources()
        self.CONTEXT_TIMEOUT_MINUTES = current_app.config.get('CHATBOT_CONTEXT_TIMEOUT_MINUTES', 5) if current_app else 5
        self.intent_handlers_map = INTENT_HANDLER_METHODS

    def load_resources(self):
        self.logger.info("MLChatbot: Loading resources (models, templates)...")
        load_trained_model(); load_or_create_templates()
        if not all([tfidf_vectorizer, intent_classifier_model]): self.logger.warning("ML models not fully loaded.")
        if not RESPONSE_TEMPLATES: self.logger.critical("Response templates not loaded.")

    def get_product_info_from_db(self, product_name, db_session_override=None):
        db_to_use = db_session_override if db_session_override else self.db.session
        logger = self.logger

        if not product_name or not isinstance(product_name, str):
            logger.debug("Invalid product name provided to get_product_info_from_db.")
            return None
        
        product_name_lower = product_name.strip().lower()
        if not product_name_lower:
            return None

        try:
            logger.debug(f"DB Search: Attempting to find product matching '{product_name_lower}'")
            
            query = db_to_use.query(Product).options(
                joinedload(Product.inventory), 
                joinedload(Product.category)
            )

            exact_match = query.filter(func.lower(Product.name) == product_name_lower).first()
            if exact_match:
                logger.info(f"DB: Exact match found for '{product_name_lower}': ID {exact_match.id}")
                return exact_match

            search_keywords_raw = product_name_lower.split()
            # Lọc bỏ stop words và từ quá ngắn, giữ lại những từ có ý nghĩa để tìm kiếm
            search_keywords = [kw for kw in search_keywords_raw if kw not in ALL_STOP_WORDS and len(kw) > 1]
            
            # Nếu sau khi lọc không còn keyword nào (ví dụ: chỉ toàn stop words), thì dùng lại cụm từ gốc
            if not search_keywords and product_name_lower:
                search_keywords = [product_name_lower] # Tìm theo cả cụm
            # Hoặc nếu cụm từ gốc chưa có trong list keyword đã xử lý (và nó đủ dài)
            elif product_name_lower and product_name_lower not in search_keywords and len(product_name_lower) >= 2:
                 search_keywords.insert(0, product_name_lower) # Ưu tiên tìm cả cụm gốc

            logger.debug(f"DB Search: Using keywords for partial match: {search_keywords}")

            partial_conditions = []
            added_full_phrase_condition = False
            for kw in search_keywords:
                if len(kw) >= 2: # Chỉ tìm từ có độ dài nhất định
                    condition = Product.name.ilike(f"%{kw}%")
                    partial_conditions.append(condition)
                    if kw == product_name_lower: # Đánh dấu là đã thêm điều kiện cho cả cụm
                        added_full_phrase_condition = True
            
            # Đảm bảo điều kiện tìm theo cả cụm product_name_lower được thêm vào nếu chưa có
            if product_name_lower and not added_full_phrase_condition and len(product_name_lower) >=2 :
                partial_conditions.append(Product.name.ilike(f"%{product_name_lower}%"))

            if partial_conditions:
                partial_matches_query = query.filter(or_(*partial_conditions)).order_by(
                    case(
                        (func.lower(Product.name) == product_name_lower, 0), 
                        else_=1
                    ),
                    case(
                        (Product.name.ilike(f"%{product_name_lower}%"), 1),
                        else_=2
                    ),
                    func.length(Product.name).asc(),
                    Product.is_featured.desc()
                )
                
                best_match = partial_matches_query.first()
                
                if best_match:
                    logger.info(f"DB: Partial match found for '{product_name_lower}'. Best candidate: '{best_match.name}' (ID: {best_match.id})")
                    return best_match
            
            logger.info(f"DB: No suitable product found for '{product_name_lower}' after exact and partial search.")
            return None
            
        except Exception as e:
            logger.error(f"DB Error during get_product_info_from_db for '{product_name_lower}': {e}", exc_info=True)
            return None

    def format_currency_vn(self, amount):
        if amount is None: return "[Chưa có giá]";
        try: return f"{int(round(amount)):,}₫".replace(",", ".");
        except: return "[Lỗi giá]"

    def format_product_list(self, products, max_items=3):
        if not products: return "đang cập nhật";
        names = [p.name for p in products if hasattr(p,'name') and p.name];
        if not names: return "Không có sản phẩm.";
        return ", ".join(names[:max_items]) + (f", và {len(names)-max_items} món khác" if len(names)>max_items else "")

    def get_db_link_html(self, link_type, db_session, **kwargs):
        logger=self.logger; url,text="#","";
        try:
            if current_app:
                with current_app.app_context():
                    map={'menu':('main.menu',"trang Menu"),'locations':('main.locations',"trang Địa điểm"),'promotions':('main.promotions_page',"trang Khuyến mãi"),'product':('main.product_detail',"xem chi tiết"),'order_detail':('order.order_detail',"xem đơn hàng")}
                    if link_type not in map: logger.warning(f"Invalid link_type '{link_type}'"); return ""
                    ep,d_text = map[link_type]; text = kwargs.pop('text',d_text); url_p={k:v for k,v in kwargs.items() if k!='db_session'}
                    if link_type=='category_menu' and 'category_id' in kwargs: url_p['category']=kwargs['category_id']; ep='main.menu'
                    url=url_for(ep,_external=False,**url_p);
                    if url: return f"<a href='{url}' target='_blank'>{text}</a>"
                    else: logger.warning(f"url_for None for {ep} with {url_p}."); return ""
            else: logger.warning("No Flask app context for get_db_link_html."); return f"{text} (link error)"
        except Exception as e: logger.error(f"Error get_db_link_html '{link_type}': {e}",exc_info=True); return f"{text} (link error)"

    def handle_greeting(self, entities, db_session, session_id=None): return random.choice(RESPONSE_TEMPLATES.get('greeting',["Chào bạn."]))
    def handle_goodbye(self, entities, db_session, session_id=None): return random.choice(RESPONSE_TEMPLATES.get('goodbye',["Tạm biệt."]))
    def handle_thanks(self, entities, db_session, session_id=None): return random.choice(RESPONSE_TEMPLATES.get('thanks',["Không có gì."]))
    def handle_hours_inquiry(self, entities, db_session, session_id=None): return random.choice(RESPONSE_TEMPLATES.get('hours_inquiry',["Giờ làm việc của quán..."]))
    def handle_wifi_inquiry(self, entities, db_session, session_id=None): return random.choice(RESPONSE_TEMPLATES.get('wifi_inquiry',["Pass wifi là..."]))
    def handle_payment_inquiry(self, entities, db_session, session_id=None): return random.choice(RESPONSE_TEMPLATES.get('payment_inquiry',["Quán chấp nhận..."]))

    def handle_location_inquiry(self, entities, db_session, session_id=None):
        locations_data = []; response=""
        try: locations_data = db_session.query(Location).filter_by(is_active=True).order_by(Location.name).limit(3).all()
        except Exception as e: self.logger.error(f"DB Err loc: {e}"); return random.choice(RESPONSE_TEMPLATES.get('error',["Lỗi DB."]))
        if locations_data:
            details = [f"{i+1}. **{l.name}**: {l.address}{f' (ĐT: {l.phone})' if l.phone else ''}" for i,l in enumerate(locations_data)]
            list_str = "\n".join(details); link = self.get_db_link_html('locations', db_session, text="Xem bản đồ và tất cả chi nhánh")
            tmpl = random.choice(RESPONSE_TEMPLATES.get('location_inquiry')); response = tmpl.format(location_list=list_str, locations_url=link)
        else: response = "Hiện Dragon Coffee chưa cập nhật chi nhánh. Mong bạn quay lại sau!"
        return response

    def handle_menu_inquiry(self, entities, db_session, session_id=None):
        prods = []; sugg_str = "Có nhiều món ngon đang chờ bạn!"
        try:
            prods_q = db_session.query(Product).filter(Product.is_available==True)
            featured = prods_q.filter(Product.is_featured==True).order_by(func.random()).limit(2).all()
            if len(featured) < 2:
                more = prods_q.filter(~Product.id.in_([p.id for p in featured])).order_by(func.random()).limit(2-len(featured)).all(); featured.extend(more)
            if featured: sugg_str = f"Bạn có thể thử: **{self.format_product_list(featured, 2)}**."
        except Exception as e: self.logger.error(f"DB Err menu sugg: {e}")
        link = self.get_db_link_html('menu',db_session,text="xem toàn bộ menu tại đây"); tmpl = random.choice(RESPONSE_TEMPLATES.get('menu_inquiry'))
        try: return tmpl.format(menu_url=link, suggestions=sugg_str)
        except KeyError as ke: self.logger.error(f"KeyErr fmt menu_inquiry: {ke}. Tmpl: '{tmpl}'"); return f"Mời bạn xem menu tại {link}. {sugg_str}"

    def handle_category_inquiry(self, entities, db_session, session_id=None):
        logger = self.logger
        cat_names = entities.get("category", []); menu_link = self.get_db_link_html('menu',db_session)
        if not cat_names: tmpl=random.choice(RESPONSE_TEMPLATES.get('category_inquiry_noproduct')); return tmpl.format(menu_url=menu_link)
        target_name_input = cat_names[0].lower().strip()
        if entities.get('combo_keyword') or "combo" in target_name_input: return self.handle_suggest_combo(entities, db_session, session_id, preferred_category=target_name_input)
        category=None
        try:
            category = db_session.query(Category).filter(func.lower(Category.name)==target_name_input).first()
            if not category and len(target_name_input)>=3: category = db_session.query(Category).filter(func.lower(Category.name).contains(target_name_input)).order_by(func.length(Category.name).asc()).first()
        except Exception as e: logger.error(f"DB Err cat '{target_name_input}': {e}", exc_info=True); return random.choice(RESPONSE_TEMPLATES.get('error'))
        if category:
            prods = [];
            try: prods = db_session.query(Product).filter(Product.category_id==category.id, Product.is_available==True).order_by(Product.is_featured.desc(), func.random()).limit(5).all()
            except Exception as e: logger.error(f"DB Err prods for cat {category.id}: {e}", exc_info=True)
            list_str = self.format_product_list(prods,3) if prods else "chưa có món nào nổi bật hoặc đang được cập nhật";
            cat_link = self.get_db_link_html('menu',db_session, category=category.id, text=f"Xem tất cả món trong '{category.name}'")
            tmpl = random.choice(RESPONSE_TEMPLATES.get('category_inquiry_result'))
            data = {'category_name': category.name, 'product_list': list_str, 'category_menu_link': cat_link, 'menu_url': menu_link, 'product_count': len(prods)}
            try: return tmpl.format(**data)
            except KeyError as ke: logger.error(f"KeyErr fmt cat_result: {ke}. Tmpl: '{tmpl}'"); return f"Lỗi {ke} DM '{category.name}'."
        else:
            tmpl=random.choice(RESPONSE_TEMPLATES.get('category_not_found')); data={'category_name':target_name_input, 'menu_url':menu_link}
            try: return tmpl.format(**data)
            except KeyError as ke: logger.error(f"KeyErr fmt cat_notfound: {ke}. Tmpl: '{tmpl}'"); return f"Ko có DM '{target_name_input}'. ({ke})"

    def handle_product_info(self, entities, db_session, session_id=None):
        logger = self.logger
        product_names_from_entities = entities.get("product", [])
        
        if not product_names_from_entities:
            # Nếu không có tên sản phẩm nào được trích xuất từ câu hỏi
            menu_link = self.get_db_link_html('menu', db_session, text="tham khảo menu đầy đủ")
            tmpl = random.choice(RESPONSE_TEMPLATES.get('product_info_no_product_entity', ["Bạn muốn biết thông tin về món nào cụ thể ạ? Bạn có thể {menu_url} của quán nhé."]))
            try:
                return tmpl.format(menu_url=menu_link)
            except KeyError as ke: # Fallback an toàn
                logger.error(f"KeyError formatting product_info_no_product_entity template ({ke}). Tmpl: '{tmpl}'")
                return f"Bạn hỏi thông tin về sản phẩm nào vậy? (Xem {menu_link} nếu cần)"

        # Lấy tên sản phẩm đầu tiên được trích xuất (thường là chính xác nhất)
        target_product_name_query = product_names_from_entities[0] 
        logger.info(f"Handling product_info request for: '{target_product_name_query}'")

        # Sử dụng hàm tìm kiếm sản phẩm đã cải thiện
        product = self.get_product_info_from_db(target_product_name_query, db_session)

        if product:
            availability = "còn hàng"
            # Kiểm tra InventoryItem (nếu có)
            if product.inventory: # Giả sử relationship tên là 'inventory'
                if product.inventory.quantity <= 0:
                    availability = "đang tạm hết hàng"
                elif product.inventory.quantity <= product.inventory.min_quantity:
                    availability = f"còn hàng (nhưng sắp hết, chỉ còn {product.inventory.quantity} thôi!)"
            elif not product.is_available: # Kiểm tra flag is_available nếu không có InventoryItem
                availability = "hiện không có sẵn"
            
            description_to_use = product.description
            # Tạo mô tả bằng AI nếu mô tả gốc quá ngắn hoặc không có
            if not description_to_use or len(description_to_use.strip()) < 20: # Ngưỡng 20 ký tự
                try:
                    if 'generate_product_description' in globals() and callable(generate_product_description):
                        # Đảm bảo hàm AI có tồn tại và gọi được
                        product_data_for_ai = {'name': product.name, 'price': product.price, 'category': product.category.name if product.category else 'Nước uống'}
                        ai_desc = generate_product_description(product_data_for_ai)
                        if ai_desc and "Lỗi" not in ai_desc and "cập nhật" not in ai_desc and len(ai_desc.strip()) > 10:
                            description_to_use = f"{ai_desc} (Mô tả này được tạo bởi AI để bạn tham khảo)"
                            logger.info(f"Used AI-generated description for product '{product.name}'.")
                        else:
                             description_to_use = description_to_use or "Một sản phẩm đặc trưng của Dragon Coffee, mang đến trải nghiệm hương vị tuyệt vời." # Fallback cuối
                    else:
                        description_to_use = description_to_use or "Hương vị tuyệt vời, đáng để thử!" # Fallback đơn giản nếu hàm AI không có
                except Exception as ai_e:
                    logger.error(f"Error generating AI description for '{product.name}': {ai_e}", exc_info=True)
                    description_to_use = description_to_use or "Mô tả đang được cập nhật." # Fallback an toàn
            
            category_name = product.category.name if product.category else "Đặc biệt"
            price_string = self.format_currency_vn(product.price)
            product_link_html = self.get_db_link_html('product', db_session, product_id=product.id, text="xem chi tiết trên website")

            # Chuẩn bị context cho template
            template_context = {
                'product_name': product.name,
                'category': category_name,
                'price': product.price, # Giá gốc dạng số (nếu template cần)
                'price_str': price_string, # Giá đã format
                'description': description_to_use,
                'availability': availability,
                'product_link': product_link_html,
                # Xử lý câu hỏi ngầm định về giá và tình trạng còn hàng
                'explicit_price_query': f" Giá của món này là {price_string} ạ." if entities.get('price_query') else "",
                'explicit_availability_query': f" Hiện tại món này {availability} bạn nhé." if entities.get('availability_query') else ""
            }
            
            # Chọn template
            # Ưu tiên template có thông tin giá nếu người dùng không hỏi giá tường minh
            if product.price is not None and not entities.get('price_query'):
                 # Dùng template mặc định có giá nếu không hỏi giá, để cung cấp luôn
                template_name = 'product_info' 
            else: 
                # Dùng template không có giá (hoặc có giá nhưng chỉ hiện khi có price_str) nếu giá None hoặc người dùng hỏi giá rồi
                template_name = 'product_info' # Vẫn có thể là template chung, nhưng explicit_price_query sẽ có giá trị

            tmpl = random.choice(RESPONSE_TEMPLATES.get(template_name, ["Mô tả về {product_name}: {description} Giá: {price_str}. Tình trạng: {availability}."]))
            
            try:
                return tmpl.format(**template_context)
            except KeyError as ke:
                logger.error(f"KeyError formatting product_info template ('{template_name}'): {ke}. Product: '{product.name}'. Template: '{tmpl[:70]}...' Context: {template_context}")
                # Fallback an toàn nếu template bị lỗi key
                return f"Món **'{product.name}'** ({category_name}) giá {price_string}. Mô tả: {description_to_use}. Tình trạng: {availability}. ({product_link_html})"
        
        else: # Không tìm thấy sản phẩm
            menu_link_html = self.get_db_link_html('menu', db_session)
            not_found_tmpl = random.choice(RESPONSE_TEMPLATES.get("product_not_found", ["Xin lỗi, tôi không tìm thấy món '{product_name}'. Mời bạn {menu_url}."]))
            try:
                return not_found_tmpl.format(product_name=target_product_name_query, menu_url=menu_link_html)
            except KeyError:
                return f"Xin lỗi, không tìm thấy món '{target_product_name_query}'. Mời bạn xem menu ({menu_link_html})."

    def handle_product_price_inquiry(self, entities, db_session, session_id=None):
        logger=self.logger; p_names=entities.get("product",[]); menu_link=self.get_db_link_html('menu',db_session)
        if not p_names: return f"Bạn hỏi giá món nào? Xem {menu_link}."
        target_name=p_names[0]; logger.info(f"Price inquiry: '{target_name}'"); product=self.get_product_info_from_db(target_name, db_session)
        if product:
            if product.price is not None: price_str=self.format_currency_vn(product.price); tmpl=random.choice(RESPONSE_TEMPLATES.get('product_price_inquiry_result')); sugg=" Bạn đặt món này không?"; return tmpl.format(product_name=product.name, price_str=price_str) + sugg
            else: return f"'{product.name}' chưa có giá."
        else: tmpl=random.choice(RESPONSE_TEMPLATES.get("product_not_found")); return tmpl.format(product_name=target_name, menu_url=menu_link)

    def handle_check_availability(self, entities, db_session, session_id=None):
        logger=self.logger; p_names=entities.get("product",[]); menu_link=self.get_db_link_html('menu',db_session)
        if not p_names: return f"Bạn kiểm tra món nào? Xem {menu_link}."
        target_name=p_names[0]; logger.info(f"Avail check: '{target_name}'"); product=self.get_product_info_from_db(target_name, db_session)
        if product:
            is_avail = product.is_available and (not product.inventory or product.inventory.quantity>0); stat_txt="**còn hàng**" if is_avail else "**đang tạm hết**";
            resp_tmpl = random.choice(RESPONSE_TEMPLATES.get('check_availability_result')); resp_txt=resp_tmpl.format(product_name=product.name,status=stat_txt)
            if is_avail and product.inventory and product.inventory.quantity <= product.inventory.min_quantity: resp_txt += f" (Sắp hết, còn {product.inventory.quantity} thôi ạ!)"
            sugg = " Bạn đặt món này nhé?" if is_avail else " Bạn chọn món khác nha."; resp_txt += sugg
            return resp_txt
        else: tmpl=random.choice(RESPONSE_TEMPLATES.get('check_availability_not_found')); sugg=random.choice(RESPONSE_TEMPLATES.get('product_not_found_suggestion')); return tmpl.format(product_name=target_name) + " " + sugg.format(menu_url=menu_link)

    def handle_promotion_inquiry(self, entities, db_session, session_id=None):
        logger=self.logger; logger.info("Handling promotion inquiry."); promos=[]; now=datetime.utcnow()
        try: promos=db_session.query(Promotion).filter(Promotion.is_active==True,Promotion.start_date<=now,Promotion.end_date>=now).order_by(Promotion.end_date.asc()).limit(3).all()
        except Exception as e: logger.error(f"DB Err promos: {e}",exc_info=True); return random.choice(RESPONSE_TEMPLATES.get('error'))
        if not promos: return random.choice(RESPONSE_TEMPLATES.get('promotion_inquiry_none'))
        texts=[]
        for i,p in enumerate(promos):
            txt=f"{i+1}. **{p.name}**: "; desc_part=p.description or "";
            if p.discount_percent: desc_part += f" (Giảm {p.discount_percent:.0f}%)"
            elif p.discount_amount: desc_part += f" (Giảm {self.format_currency_vn(p.discount_amount)})"
            if p.code: desc_part += f" - Mã: `{p.code}`"
            desc_sum = desc_part.strip(); desc_sum = desc_sum[:65]+"..." if len(desc_sum)>68 else desc_sum;
            txt+= f" {desc_sum} (Đến: {p.end_date.strftime('%d/%m/%Y')})."; texts.append(txt)
        list_fmt = "\n".join(texts); link = self.get_db_link_html('promotions',db_session,text="xem tất cả ưu đãi")
        tmpl=random.choice(RESPONSE_TEMPLATES.get('promotion_inquiry'))
        try: return tmpl.format(promotion_list=list_fmt, promotions_url=link)
        except KeyError as ke: logger.error(f"KeyErr fmt promo_inq: {ke}. Tmpl: '{tmpl}'"); return f"Lỗi placeholder KM ({ke})."

    def handle_suggest_combo(self, entities, db_session, session_id=None, preferred_category=None):
        logger=self.logger; prefs=entities.get("product",[])+entities.get("category",[]); pref_kw = prefs[0] if prefs else preferred_category; logger.info(f"Combo sugg. Pref: '{pref_kw}'")
        drink, food = None, None
        try:
            drink_cats=['Cà phê','Trà','Nước ép','Sinh tố','Đá xay']; drink_q = db_session.query(Product).join(Category).filter(Product.is_available==True)
            if pref_kw: drink_q=drink_q.filter(or_(func.lower(Product.name).contains(pref_kw.lower()), func.lower(Category.name).contains(pref_kw.lower()),Category.name.in_(drink_cats)))
            else: drink_q=drink_q.filter(Category.name.in_(drink_cats))
            drink=drink_q.order_by(func.random()).first()
            food_cats=['Bánh ngọt','Đồ ăn nhẹ','Snack','Mì','Cơm','Phở','Bún','Xôi','Bánh mì']; food_q=db_session.query(Product).join(Category).filter(Product.is_available==True,Category.name.in_(food_cats))
            if pref_kw and pref_kw.lower() in [c.lower() for c in food_cats]: food_q = food_q.filter(or_(func.lower(Product.name).contains(pref_kw.lower()),func.lower(Category.name).contains(pref_kw.lower())))
            elif drink and drink.category and drink.category.name in food_cats: food_q = food_q.filter(Category.id != drink.category_id)
            food = food_q.order_by(func.random()).first()
            if drink and food and hasattr(drink,'price') and drink.price and hasattr(food,'price') and food.price:
                combo_name=f"'{drink.name}' & '{food.name}'"; items=f"một **{drink.name}** và một **{food.name}**"; orig_price=drink.price+food.price; combo_p_val=orig_price*0.9; combo_p_str=self.format_currency_vn(combo_p_val); saved_str=self.format_currency_vn(orig_price-combo_p_val)
                tmpl=random.choice(RESPONSE_TEMPLATES.get('suggest_combo_result')); pref_disp = f" dành cho bạn thích '{pref_kw}'" if pref_kw else "";
                data = {'combo_name':combo_name,'combo_items_desc':items,'combo_price_str':combo_p_str,'saved_amount_str':saved_str,'preference':pref_disp}
                return tmpl.format(**data)
            elif drink: return f"Thử món **{drink.name}** nhé. Bạn muốn dùng kèm bánh hay đồ ăn nhẹ gì không?"
            elif food: return f"Nếu ăn nhẹ, thử **{food.name}**. Bạn muốn uống gì kèm theo không?"
            else: tmpl=random.choice(RESPONSE_TEMPLATES.get('suggest_combo_no_pref')); return tmpl
        except Exception as e: logger.error(f"Error sugg combo (Pref '{pref_kw}'): {e}",exc_info=True); return random.choice(RESPONSE_TEMPLATES.get('suggest_combo_no_pref'))

    def handle_visual_product_search(self, entities, db_session, session_id=None):
        logger=self.logger; keywords = list(set(entities.get("product",[]) + entities.get("category",[]) + entities.get("visual_keywords",[])))
        stop_w={"ảnh","hình","cho","tôi","xem","tìm","với","có","một","rất","khá","như","giống","là","của","nhìn","trông","thì","mà","ly","cốc","phần","tách"}
        final_kws = [kw.strip() for kw in keywords if kw.strip() and kw.strip() not in stop_w and len(kw.strip())>1]; kw_str = ", ".join(final_kws)
        if not final_kws: logger.debug("No valid visual keywords."); return {'response':random.choice(RESPONSE_TEMPLATES.get("visual_product_search_nokeywords")),'image_results':[]}
        logger.info(f"Visual search with keywords: {final_kws}")
        try:
            image_search_results = search_products_by_visual_keywords(final_kws, db_session, limit=4)
            response_text=""
            if image_search_results: tmpl=random.choice(RESPONSE_TEMPLATES.get("visual_product_search_result")); response_text=tmpl.format(keywords=kw_str)
            else: tmpl=random.choice(RESPONSE_TEMPLATES.get("visual_product_search_notfound")); response_text=tmpl.format(keywords=kw_str)+" Bạn thử mô tả rõ hơn (màu sắc, hình dáng...) xem."
            return {'response':response_text,'image_results':image_search_results}
        except Exception as e: logger.error(f"Err visual search: {e}",exc_info=True); return {'response':random.choice(RESPONSE_TEMPLATES.get('error')),'image_results':[]}

    def handle_order_status_inquiry(self, entities, db_session, session_id=None):
        logger=self.logger; order_num=entities.get("order_number");
        user_id_for_query = None
        if session_id and session_id in conversation_context: user_id_for_query = conversation_context[session_id].get('user_id')

        if not order_num:
            if user_id_for_query:
                logger.info(f"No order num, finding latest for user {user_id_for_query}.")
                try:
                    latest_order = db_session.query(Order).filter(Order.user_id == user_id_for_query)\
                                   .order_by(Order.created_at.desc()).first()
                    if latest_order: order_num = latest_order.order_number; logger.info(f"Found latest order {order_num}.")
                    else: return random.choice(RESPONSE_TEMPLATES.get('order_status_no_order_history',["Bạn chưa có đơn hàng nào."]))
                except Exception as e: logger.error(f"DB Err latest order UID {user_id_for_query}: {e}"); return random.choice(RESPONSE_TEMPLATES.get('error'))
            else: return random.choice(RESPONSE_TEMPLATES.get('order_status_ask_number'))

        logger.info(f"Order status for: '{order_num}' (UserCtxID: {user_id_for_query})")
        order=None
        try:
            query = db_session.query(Order).filter(or_(func.upper(Order.order_number)==func.upper(order_num), cast(Order.id,String)==order_num))
            if user_id_for_query: query = query.filter(Order.user_id == user_id_for_query)
            order = query.first()
        except Exception as e: logger.error(f"DB Err order status '{order_num}': {e}",exc_info=True); return random.choice(RESPONSE_TEMPLATES.get('error'))

        if order:
            stat_disp = order.get_status_display(); date_str = order.created_at.strftime('%d/%m/%Y %H:%M') if order.created_at else "N/A";
            details_map = {'pending':"Đang chờ xử lý.",'processing':"Đang chuẩn bị.",'ready_for_pickup':"Sẵn sàng tại quầy!",'out_for_delivery':"Đang giao đến bạn...",'completed':"Đã hoàn thành!",'delivered':"Đã giao xong!",'cancelled':"Đã bị hủy."}
            stat_detail = details_map.get(order.status, "Trạng thái đang cập nhật.");
            link=self.get_db_link_html('order_detail', db_session,order_id=order.id, text="[Xem chi tiết đơn hàng]")
            tmpl = random.choice(RESPONSE_TEMPLATES.get('order_status_found'));
            data = {'order_number':order.order_number,'order_date_str':date_str,'status_display_text':stat_disp,'status_specific_details':stat_detail,'order_detail_link_html':link}
            try: return tmpl.format(**data)
            except KeyError as ke: logger.error(f"KeyErr fmt order_status_found: {ke}. Tmpl: '{tmpl}'"); return f"Đơn #{order.order_number}: {stat_disp}. {stat_detail} (Lỗi:{ke})"
        else:
            msg_not_found = f"Không tìm thấy đơn **{order_num}**"
            if user_id_for_query: msg_not_found += " của bạn."
            else: msg_not_found += "."
            msg_not_found += " Kiểm tra lại mã nhé."
            return msg_not_found

    def handle_order_intent(self, entities, db_session, session_id=None):
        global conversation_context; logger=self.logger;
        p_names=entities.get("product"); menu_url=self.get_db_link_html('menu', db_session)
        if not p_names: tmpl=random.choice(RESPONSE_TEMPLATES.get('order_intent_noproduct')); return tmpl.format(menu_url=menu_url)
        target_name = p_names[0].title(); logger.info(f"Order Intent: User wants to order '{target_name}'")
        product = self.get_product_info_from_db(target_name, db_session)
        if not product: tmpl=random.choice(RESPONSE_TEMPLATES.get('product_not_found')); return tmpl.format(product_name=target_name, menu_url=menu_url)
        if not product.is_available or (product.inventory and product.inventory.quantity <=0 ): return f"Xin lỗi, món '{product.name}' hiện đang tạm hết. Bạn chọn món khác nhé."
        if product.price is None: return f"Món '{product.name}' chưa có giá, không thể đặt."
        
        initial_qty = entities.get("quantity") # Có thể là None
        initial_notes = entities.get("notes", [])
        initial_size = entities.get("size") or "Vừa"

        if session_id:
            conversation_context[session_id] = {
                'state': 'awaiting_quantity_and_notes',
                'pending_order': { 
                    'product_id': product.id, 
                    'product_name': product.name, 
                    'price_per_unit': product.price,
                    'quantity': initial_qty, # Có thể None
                    'notes': initial_notes,  # Có thể list rỗng
                    'size': initial_size
                },
                'timestamp': datetime.utcnow()
            }
            logger.info(f"Context for SID {session_id[:8]}: Initial pending order for '{product.name}' - Details provided: Qty={initial_qty}, Size={initial_size}, Notes={initial_notes}")
            
            # Nếu chưa có số lượng, hỏi số lượng trước
            if initial_qty is None:
                tmpl_ask_qty = random.choice(RESPONSE_TEMPLATES.get('order_intent_ask_qty_only', ["Bạn muốn đặt bao nhiêu phần/ly và có ghi chú gì thêm không? '{product_name}' ạ?"]))
                return tmpl_ask_qty.format(product_name=product.name)
            else: # Nếu có số lượng rồi, có thể hỏi note hoặc xác nhận luôn
                return self.handle_provide_order_details(entities, db_session, session_id) # Đi thẳng tới bước tiếp theo nếu đã có SL
        else: logger.error("Critical: No session_id for order_intent."); return random.choice(RESPONSE_TEMPLATES.get('error'))

    def handle_provide_order_details(self, entities, db_session, session_id=None):
        global conversation_context; logger=self.logger;
        if not session_id or session_id not in conversation_context or conversation_context[session_id].get('state') != 'awaiting_quantity_and_notes':
            logger.warning(f"Provide_order_details no/wrong context for SID {session_id[:8] if session_id else 'None'}.")
            return self.handle_fallback(entities, db_session, session_id)
        
        context_data = conversation_context[session_id]; pending_order = context_data['pending_order']
        
        new_qty = entities.get("quantity"); new_notes = entities.get("notes", []); new_size = entities.get("size")

        if new_qty is not None : pending_order['quantity'] = new_qty
        if new_notes : pending_order['notes'] = sorted(list(set(pending_order.get('notes', []) + new_notes)))
        if new_size : pending_order['size'] = new_size.title()
        
        if pending_order.get('quantity') is None: # Nếu vẫn chưa có SL, hỏi lại
            tmpl_ask_qty_again = random.choice(RESPONSE_TEMPLATES.get('order_intent_ask_qty_only', ["Bạn muốn đặt bao nhiêu phần/ly và có ghi chú gì thêm không? '{product_name}' ạ?"]))
            return tmpl_ask_qty_again.format(product_name=pending_order['product_name'])

        if not isinstance(pending_order['quantity'], int) or pending_order['quantity'] <= 0: pending_order['quantity'] = 1
            
        estimated_price = pending_order['price_per_unit'] * pending_order['quantity']
        pending_order['estimated_price'] = estimated_price
        price_str = self.format_currency_vn(estimated_price)
        # Sửa lỗi KeyError 'notes' ở đây
        notes_current_list = pending_order.get('notes', []) # Lấy list notes, mặc định là list rỗng
        notes_str = f" (Ghi chú: {', '.join(notes_current_list)})" if notes_current_list else ""
        size_str = pending_order.get('size',"Vừa")

        context_data['state'] = 'awaiting_order_confirmation'; context_data['timestamp'] = datetime.utcnow()
        logger.info(f"Ctx SID {session_id[:8]}: Updated order {pending_order}, awaiting final confirm.")
        tmpl_confirm = random.choice(RESPONSE_TEMPLATES.get('order_confirmation_request'))
        return tmpl_confirm.format(quantity=pending_order['quantity'], product_name=pending_order['product_name'], size=size_str, notes=notes_str, price_str=price_str)

    def handle_affirmation(self, entities, db_session, session_id=None):
        global conversation_context; logger=self.logger;
        if not session_id: logger.error("Affirmation: No session_id."); return random.choice(RESPONSE_TEMPLATES.get('error'))
        context = conversation_context.get(session_id)
        if context and context.get('state') == 'awaiting_order_confirmation' and context.get('pending_order'):
            pending = context['pending_order']; logger.info(f"Affirmation for order: {pending}"); err_reason = "Lỗi không xác định."
            try:
                with db_session.begin_nested():
                    inv_item = db_session.query(InventoryItem).filter_by(product_id=pending['product_id']).with_for_update().first()
                    if not inv_item or inv_item.quantity < pending['quantity']:
                         err_reason = f"'{pending['product_name']}' đã hết hoặc không đủ SL (còn {inv_item.quantity if inv_item else 0})."
                         raise ValueError(err_reason)
                    price_item = pending.get('estimated_price',0.0); tax = round(price_item*0.1, 2); final = round(price_item + tax, 2)
                    user_id_order = context.get('user_id')
                    if user_id_order and not isinstance(user_id_order, int): user_id_order = None
                    order_notes_list = pending.get('notes',[])
                    order_notes_str = ", ".join(order_notes_list) if order_notes_list else None
                    full_notes = f"[Chatbot SID {session_id[:8]}]"
                    size_str = pending.get('size',"Vừa") # Lấy size
                    if size_str.lower() != "vừa": full_notes += f" Size: {size_str}." # Chỉ thêm nếu khác Vừa
                    if order_notes_str: full_notes += f" Khách ghi chú: {order_notes_str}."
                    new_order = Order(user_id=user_id_order, order_number=f"BOT-{uuid.uuid4().hex[:7].upper()}", status='pending',
                                      total_amount=round(price_item,2), final_amount=final, tax_amount=tax,
                                      order_type='chatbot', payment_method='cash', payment_status='pending', notes=full_notes.strip())
                    db_session.add(new_order); db_session.flush()
                    unit_price = round(price_item/pending['quantity'],2) if pending['quantity']>0 else 0.0
                    new_detail = OrderDetail(order_id=new_order.id, product_id=pending['product_id'], quantity=pending['quantity'],
                                             unit_price=unit_price, subtotal=round(price_item,2), notes=order_notes_str)
                    db_session.add(new_detail)
                    inv_item.quantity -= pending['quantity']; inv_item.last_updated=datetime.utcnow()
                db_session.commit(); logger.info(f"Order {new_order.order_number} created by chatbot SID {session_id[:8]} (UID: {user_id_order}).")
                conversation_context.pop(session_id, None); tmpl=random.choice(RESPONSE_TEMPLATES.get('order_success'))
                link_detail=self.get_db_link_html('order_detail',db_session,order_id=new_order.id,text="Xem chi tiết đơn hàng của bạn")
                return tmpl.format(order_number=new_order.order_number, order_link=link_detail)
            except Exception as ord_exc:
                db_session.rollback(); logger.error(f"Failed order from context SID {session_id[:8]}: {ord_exc}",exc_info=True);
                conversation_context.pop(session_id,None); tmpl=random.choice(RESPONSE_TEMPLATES.get('order_failed'))
                hotline = current_app.config.get('SHOP_HOTLINE','[Hotline]') if current_app else '[Hotline]'
                return tmpl.format(error_reason=err_reason or str(ord_exc) or "Lỗi hệ thống.", hotline=hotline)
        else: return random.choice(RESPONSE_TEMPLATES.get('affirmation',["Vâng ạ."]))

    def handle_negation(self, entities, db_session, session_id=None):
        global conversation_context; logger=self.logger;
        if not session_id: logger.error("Negation: No session_id."); return random.choice(RESPONSE_TEMPLATES.get('error'))
        context = conversation_context.get(session_id)
        if context and context.get('state') in ['awaiting_order_confirmation', 'awaiting_quantity_and_notes']:
            logger.info(f"Negation for pending order (State: {context.get('state')}, SID {session_id[:8]}). Clearing context."); conversation_context.pop(session_id,None)
            return random.choice(RESPONSE_TEMPLATES.get('order_confirmation_no',["Đã hủy yêu cầu. Bạn muốn đặt món khác không?"]))
        else: return random.choice(RESPONSE_TEMPLATES.get('negation',["Dạ vâng ạ."]))

    def handle_quality_inquiry(self, entities, db_session, session_id=None):
        p_names = entities.get("product",[]);
        if p_names:
            target_name = p_names[0]; product = self.get_product_info_from_db(target_name, db_session)
            if product:
                adj = random.choice(["đậm đà","thơm ngon","tuyệt hảo","tươi mới","đặc trưng"]); ingr = product.category.name.lower() if product.category else "nguyên liệu chọn lọc"
                tmpl = random.choice(RESPONSE_TEMPLATES.get('quality_inquiry_product')); return tmpl.format(product_name=product.name,quality_adj=adj,ingredient_highlight=ingr)
            else: tmpl=random.choice(RESPONSE_TEMPLATES.get('product_not_found')); return tmpl.format(product_name=target_name,menu_url=self.get_db_link_html('menu',db_session))
        else: return random.choice(RESPONSE_TEMPLATES.get('quality_inquiry_general'))

    def handle_ambiance_inquiry(self, entities, db_session, session_id=None):
        tmpl=random.choice(RESPONSE_TEMPLATES.get('ambiance_inquiry'))
        data={'theme_description':"phong cách Á Đông ấm cúng",'zone_type1':"sofa êm ái",'zone_type2':"bàn cao cho nhóm bạn",'decor_feature':"những bức tranh rồng độc đáo",'music_style':"nhạc nhẹ nhàng"}
        try: return tmpl.format(**data)
        except KeyError as ke: self.logger.warning(f"KeyErr fmt ambiance: {ke}. Tmpl: '{tmpl}'"); return f"Lỗi {ke} ambiance."

    def handle_reservation_inquiry(self, entities, db_session, session_id=None):
        link=self.get_db_link_html('locations',db_session); tmpl=random.choice(RESPONSE_TEMPLATES.get('reservation_inquiry'))
        hotline = current_app.config.get('SHOP_HOTLINE', '[Vui lòng xem SĐT chi nhánh]') if current_app else '[Hotline]'
        try: return tmpl.format(hotline=hotline, locations_url=link)
        except KeyError as ke: self.logger.warning(f"KeyErr fmt reserv: {ke}. Tmpl: '{tmpl}'"); return f"Lỗi {ke} reserv."

    def handle_feedback_complaint(self, entities, db_session, session_id=None):
        tmpl=random.choice(RESPONSE_TEMPLATES.get('feedback_complaint'))
        hotline = current_app.config.get('SHOP_HOTLINE','[Hotline CSKH]') if current_app else '[Hotline]'
        email = current_app.config.get('SHOP_FEEDBACK_EMAIL','[Email CSKH]') if current_app else '[Email]'
        try: return tmpl.format(hotline=hotline, feedback_email=email)
        except KeyError as ke: self.logger.warning(f"KeyErr fmt feedback: {ke}. Tmpl: '{tmpl}'"); return f"Lỗi {ke} feedback."

    def handle_help_inquiry(self, entities, db_session, session_id=None): return random.choice(RESPONSE_TEMPLATES.get('help_inquiry'))
    def handle_bot_identity(self, entities, db_session, session_id=None): return random.choice(RESPONSE_TEMPLATES.get('bot_identity') + RESPONSE_TEMPLATES.get('bot_capability'))

    def handle_best_seller_inquiry(self, entities, db_session, session_id=None):
        logger=self.logger; best_sellers = []
        try:
            date_limit = datetime.utcnow() - timedelta(days=45)
            best_sellers_q = db_session.query(Product.name, func.sum(OrderDetail.quantity).label('total_qty'))\
                .join(OrderDetail, Product.id == OrderDetail.product_id)\
                .join(Order, OrderDetail.order_id == Order.id)\
                .filter(Order.created_at >= date_limit, Product.is_available == True, Order.status.in_(['completed','delivered']))\
                .group_by(Product.name).order_by(desc('total_qty')).limit(5).all()
            best_sellers = [{"name": name, "quantity_sold": qty} for name, qty in best_sellers_q]
        except Exception as e: logger.error(f"DB Err best sellers: {e}", exc_info=True)
        if not best_sellers: return random.choice(RESPONSE_TEMPLATES.get('best_seller_inquiry_none', ["Hiện quán chưa có thống kê món bán chạy."]))
        list_str = "\n".join([f"- **{item['name']}** (đã bán {item['quantity_sold']} phần)" for item in best_sellers])
        tmpl = random.choice(RESPONSE_TEMPLATES.get('best_seller_inquiry')); menu_url = self.get_db_link_html('menu',db_session)
        try: return tmpl.format(best_seller_list=list_str, menu_url=menu_url)
        except KeyError as ke: logger.warning(f"KeyErr fmt best_seller: {ke}. Tmpl: '{tmpl}'"); return f"Lỗi {ke} best seller."

    def handle_generic_question(self, entities, db_session, session_id=None): return random.choice(RESPONSE_TEMPLATES.get('generic_question_response'))
    def handle_fallback(self, entities, db_session, session_id=None):
        original_text=entities.get('__original_text__',''); menu_url=self.get_db_link_html('menu',db_session);loc_url=self.get_db_link_html('locations',db_session)
        self.logger.warning(f"Fallback for: '{original_text[:100]}'. Entities: { {k:v for k,v in entities.items() if k!='__original_text__'} }")
        sugg_list=[f"tìm hiểu về {menu_url}", f"xem {loc_url} của quán", "hỏi về chương trình khuyến mãi", "cần tôi trợ giúp về đơn hàng đã đặt"]
        tmpl=random.choice(RESPONSE_TEMPLATES.get('fallback')); suggestions_fallback_str = "; ".join(random.sample(sugg_list, min(len(sugg_list),2)))
        try: return tmpl.format(suggestions=suggestions_fallback_str)
        except KeyError as ke: self.logger.warning(f"KeyErr fmt fallback: {ke}. Tmpl: '{tmpl}'"); return f"Xin lỗi, tôi chưa hiểu. Thử hỏi: {suggestions_fallback_str}?"

    def generate_ml_chatbot_response(self, text, db_session, session_id=None):
        logger = get_logger(); start_time = datetime.now();
        log_prefix=f"[SID:{session_id[:8] if session_id else 'NoSID'}]"; logger.info(f"{log_prefix} <- User: '{text[:150]}...'")
        if not all([tfidf_vectorizer, intent_classifier_model, RESPONSE_TEMPLATES]): self.load_resources();
        if not all([tfidf_vectorizer, intent_classifier_model, RESPONSE_TEMPLATES]):
             logger.critical(f"{log_prefix} Chatbot components NOT READY! Critical error.");
             return {'success': False,'response': "Lỗi nghiêm trọng: Chatbot chưa sẵn sàng.",'intent': "critical_init_error", 'entities': {}, 'image_results':[]}
        if session_id and session_id in conversation_context:
            ctx_data = conversation_context[session_id]; last_activity_ts = ctx_data.get('timestamp')
            if isinstance(last_activity_ts, datetime) and (datetime.utcnow() - last_activity_ts) > timedelta(minutes=self.CONTEXT_TIMEOUT_MINUTES):
                logger.info(f"{log_prefix} Context expired. Clearing SID context."); conversation_context.pop(session_id, None)
            elif session_id in conversation_context : conversation_context[session_id]['timestamp'] = datetime.utcnow()

        intent, confidence, entities = detect_intent_combined(text, db_session, session_id=session_id)
        entities['__original_text__'] = text
        logger.info(f"{log_prefix} Intent='{intent}' (Conf: {confidence:.3f}), Entities: { {k:v for k,v in entities.items() if k!='__original_text__'} }")

        handler_method_name = self.intent_handlers_map.get(intent)
        handler_func = getattr(self, handler_method_name, self.handle_fallback) if handler_method_name else self.handle_fallback
        logger.debug(f"{log_prefix} Using Handler: '{handler_func.__name__ if hasattr(handler_func, '__name__') else str(handler_func)}'")

        response_payload = {'success': False, 'response': 'Lỗi xử lý chatbot.', 'intent': 'processing_error', 'entities': {}, 'image_results': [] }
        try:
            if session_id and current_app and current_app.config.get('SESSION_TYPE') != 'null' and session:
                user_for_chatbot = None
                try:
                    if hasattr(session, 'get') and session.get('_user_id'):
                         user_for_chatbot = User.query.get(session['_user_id'])
                    elif hasattr(current_app, 'login_manager') and current_app.login_manager._load_user:
                         user_for_chatbot = current_app.login_manager._load_user()
                except Exception as user_load_e: logger.warning(f"{log_prefix} Error getting user from session: {user_load_e}", exc_info=False)
                if user_for_chatbot and user_for_chatbot.is_authenticated:
                    conversation_context.setdefault(session_id,{})['user_id'] = user_for_chatbot.id
                    logger.debug(f"{log_prefix} User ID {user_for_chatbot.id} added to chatbot context.")

            handler_args = [entities, db_session]
            if handler_func in [self.handle_affirmation, self.handle_negation, self.handle_order_intent, self.handle_provide_order_details]: handler_args.append(session_id)
            result_from_handler = handler_func(*handler_args)

            if isinstance(result_from_handler, dict): response_payload.update(result_from_handler); response_payload['success'] = result_from_handler.get('success', True)
            elif isinstance(result_from_handler, str): response_payload['response'] = result_from_handler.strip(); response_payload['success'] = True
            else: logger.error(f"{log_prefix} Invalid handler return: {type(result_from_handler)}"); response_payload.update({'response': random.choice(RESPONSE_TEMPLATES.get('fallback')), 'intent': 'fallback_handler_error'})
            response_payload['intent'] = intent

            if intent in ['order_confirmation_yes', 'order_confirmation_no','goodbye'] and response_payload['success']:
                if session_id in conversation_context: logger.info(f"{log_prefix} Clearing context after {intent}."); conversation_context.pop(session_id, None)
        except Exception as e:
            logger.critical(f"{log_prefix} CRITICAL ERROR in handler '{handler_func.__name__ if hasattr(handler_func,'__name__') else 'N/A'}': {e}", exc_info=True)
            response_payload = {'success': False, 'response': random.choice(RESPONSE_TEMPLATES.get('error')), 'intent': 'handler_exception', 'entities': entities, 'image_results': []}
            if session_id: conversation_context.pop(session_id, None)
            try:
                if db_session.is_active: db_session.rollback(); logger.info(f"{log_prefix} DB session rolled back.")
            except Exception as rb_e: logger.error(f"{log_prefix} Rollback fail: {rb_e}")

        final_entities_for_log = {k:v for k,v in entities.items() if k != '__original_text__'}
        response_payload['entities'] = final_entities_for_log
        proc_time=(datetime.now()-start_time).total_seconds()
        resp_log = response_payload.get('response', '?')[:100].replace('\n',' '); img_len = len(response_payload.get('image_results',[]))
        log_int = response_payload.get('intent','n/a'); log_ok = response_payload.get('success',False)
        logger.info(f"{log_prefix} -> Resp (Int:'{log_int}', OK:{log_ok}, Time:{proc_time:.3f}s): '{resp_log}' (Imgs:{img_len})")
        return response_payload

ml_chatbot_instance = None

def init_chatbot_ml(database_instance):
    global ml_chatbot_instance
    logger = get_logger()
    initialize_nltk_data()
    load_or_create_templates()
    if not load_trained_model():
        logger.warning("ML model load fail. Retraining...")
        if not train_intent_model(): logger.critical("CRITICAL: ML Model train FAIL. NLU limited.")
        else: logger.info("ML Model trained & saved.")
    else: logger.info("ML model loaded.")
    if ml_chatbot_instance is None:
        logger.info("Creating MLChatbot instance...")
        if database_instance is None: logger.error("DB instance None for MLChatbot. Handlers need DB will fail.")
        try: ml_chatbot_instance = MLChatbot(database_instance); logger.info("MLChatbot instance created.")
        except Exception as e: logger.critical(f"CRIT ERROR MLChatbot instance: {e}", exc_info=True); ml_chatbot_instance=None
    elif ml_chatbot_instance.db is None and database_instance:
         ml_chatbot_instance.db = database_instance; logger.info("Updated DB for existing MLChatbot instance.")
    return ml_chatbot_instance

def get_ml_chatbot_response(text: str, db_session, session_id: str | None = None) -> dict:
    logger = get_logger()
    if ml_chatbot_instance is None:
        logger.error("MLChatbot NOT INITIALIZED when calling get_ml_chatbot_response.")
        return {'success': False, 'response': "Lỗi: Chatbot chưa sẵn sàng (init fail).", 'intent': "init_error_call", 'entities': {}, 'image_results': []}
    try: return ml_chatbot_instance.generate_ml_chatbot_response(text, db_session, session_id=session_id)
    except Exception as e:
        logger.critical(f"UNEXPECTED CRITICAL error in get_ml_chatbot_response: {e}", exc_info=True)
        try:
            if db_session and db_session.is_active : db_session.rollback()
        except Exception as rb_e: logger.error(f"Rollback fail post-critical: {rb_e}")
        return {'success': False, 'response': "Lỗi hệ thống nghiêm trọng, vui lòng thử lại sau.", 'intent': "critical_internal_error_call", 'entities': {}, 'image_results': []}

def handle_ml_order(text: str, db_session, session_id: str | None = None) -> dict:
    return get_ml_chatbot_response(text, db_session, session_id)

def search_products_by_visual_keywords(keywords, db_session, limit=3):
    logger = get_logger()
    if not keywords or not isinstance(keywords, list):
        logger.debug("No valid keywords for visual search.")
        return []
    if not db_session:
        logger.error("DB session not provided for visual product search.")
        return []

    logger.info(f"Visual Search: Keywords: {keywords}")
    search_conditions = []
    for kw_phrase in keywords:
        # Tìm kiếm cả trong tên và mô tả
        search_conditions.append(Product.name.ilike(f"%{kw_phrase}%"))
        search_conditions.append(Product.description.ilike(f"%{kw_phrase}%"))

    if not search_conditions:
        logger.debug("No valid search conditions generated from keywords.")
        return []

    try:
        # Bỏ .distinct(Product.id) ở đây
        # Lấy dư một chút để có thêm lựa chọn ngẫu nhiên
        potential_results = db_session.query(Product).options(joinedload(Product.category))\
                           .filter(Product.is_available == True)\
                           .filter(or_(*search_conditions))\
                           .order_by(func.random()) \
                           .limit(limit * 3).all() # Lấy dư hơn một chút (x3)

        # Lọc các sản phẩm trùng lặp và giới hạn số lượng kết quả trong Python
        final_results_map = {}
        for product in potential_results:
            if product.id not in final_results_map:
                final_results_map[product.id] = product
            if len(final_results_map) >= limit: # Dừng sớm khi đủ số lượng
                break
        
        # Chuyển lại thành list
        results_to_format = list(final_results_map.values())

        formatted_results = []
        if current_app:
            with current_app.app_context():
                for product in results_to_format: # Sử dụng results_to_format
                     img_url_final = product.image_url or url_for('static', filename='images/default_product_thumb.png', _external=False)
                     product_page_url = url_for('main.product_detail', product_id=product.id, _external=False)
                     formatted_results.append({
                         "id": product.id, "name": product.name, "image_url": img_url_final,
                         "product_url": product_page_url, "category_name": product.category.name if product.category else "Khác"
                     })
        else: # Fallback nếu không có app context (ví dụ: chạy script)
             for product in results_to_format: # Sử dụng results_to_format
                img_url_final = product.image_url or "/static/images/default_product_thumb.png"
                product_page_url = f"/product/{product.id}"
                formatted_results.append({
                    "id":product.id, "name":product.name, "image_url":img_url_final, 
                    "product_url":product_page_url, "category_name": product.category.name if product.category else "Khác"
                })

        logger.info(f"Visual Search: Found {len(formatted_results)} unique results for keywords: {keywords}")
        return formatted_results

    except Exception as e:
        logger.error(f"DB Error during visual product search for keywords '{keywords}': {e}", exc_info=True)
        return []

__all__ = ['init_chatbot_ml','get_ml_chatbot_response','handle_ml_order','train_intent_model','load_training_data','create_default_training_data','get_logger','INTENT_MODEL_PATH','TFIDF_VECTORIZER_PATH','TRAINING_DATA_PATH','TEMPLATES_FILE_PATH']