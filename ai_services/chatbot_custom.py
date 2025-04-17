# /ai_services/chatbot_custom.py
import re
import random
import nltk
from nltk.tokenize import word_tokenize
from flask import current_app, url_for
from sqlalchemy import or_, func, desc, case, cast, String
from models import Product, Category, Promotion, Order, OrderDetail, InventoryItem # Đảm bảo import đủ model
import json
import os
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.orm import joinedload

# ====> ĐẢM BẢO HÀM NÀY ĐƯỢC ĐỊNH NGHĨA Ở ĐÂY <====
def create_default_templates():
    """Creates default templates dictionary."""
    logger = get_logger()
    logger.info("Creating default chatbot response templates structure.")
    # Sử dụng lại file chatbot_responses.json đã cung cấp làm nội dung mặc định
    try:
        # Đường dẫn tương đối đến file JSON trong cùng thư mục data
        default_path = os.path.join(os.path.dirname(__file__), 'data', 'chatbot_responses.json')
        if os.path.exists(default_path):
            with open(default_path, 'r', encoding='utf-8') as f:
                # logger.debug(f"Loading default templates from: {default_path}")
                return json.load(f)
        else:
            logger.error("Default chatbot_responses.json not found in data directory! Using hardcoded basic defaults.")
            # Fallback cứng nếu file JSON cũng không có
            return {
                "greeting": ["Xin chào!", "Chào bạn, Dragon Coffee nghe!"],
                "goodbye": ["Tạm biệt!", "Hẹn gặp lại!"],
                "thanks": ["Không có gì ạ!", "Rất vui được giúp bạn."],
                "fallback": ["Xin lỗi, tôi chưa hiểu lắm.", "Bạn hỏi lại câu khác được không?"]
                # Thêm các intent cơ bản khác ở đây làm fallback
            }
    except Exception as e:
        logger.error(f"Error loading default templates from JSON file: {e}", exc_info=True)
        return {"fallback": ["Lỗi chatbot."], "greeting": ["Xin chào!"]}
# ====> KẾT THÚC ĐỊNH NGHĨA HÀM create_default_templates <====


def load_or_create_templates():
    """Loads templates from file or creates/loads defaults."""
    global RESPONSE_TEMPLATES
    logger = get_logger()
    # ===> Đảm bảo gọi đúng hàm đã định nghĩa ở trên <====
    default_templates_data = create_default_templates() # Gọi hàm đã định nghĩa
    # ===================================================
    try:
        if os.path.exists(TEMPLATES_FILE_PATH):
            with open(TEMPLATES_FILE_PATH, 'r', encoding='utf-8') as f:
                loaded_templates = json.load(f)
                merged_templates = {**default_templates_data, **loaded_templates} # Merge, ưu tiên file đã load
                # Check for missing keys explicitly might be too verbose, assume default is fallback
                RESPONSE_TEMPLATES = merged_templates
                logger.info(f"Successfully loaded/merged response templates from {TEMPLATES_FILE_PATH}")
        else:
            logger.warning(f"Template file not found: {TEMPLATES_FILE_PATH}. Using defaults.")
            RESPONSE_TEMPLATES = default_templates_data
            try:
                with open(TEMPLATES_FILE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(RESPONSE_TEMPLATES, f, ensure_ascii=False, indent=4)
                logger.info(f"Saved default templates to {TEMPLATES_FILE_PATH}")
            except Exception as save_e:
                logger.error(f"Could not save default templates: {save_e}")
    except Exception as e:
        logger.error(f"Error loading/creating templates: {e}. Using defaults.", exc_info=True)
        RESPONSE_TEMPLATES = default_templates_data # Fallback an toàn nhất là dùng default

# --- NLTK Data Check/Download (Run only once if needed) ---
def download_nltk_data():
    logger = get_logger()
    try: nltk.data.find('tokenizers/punkt')
    except LookupError:
        logger.info("Downloading NLTK 'punkt' data...")
        try: nltk.download('punkt', quiet=True); logger.info("NLTK 'punkt' downloaded.")
        except Exception as e: logger.error(f"Failed to download NLTK 'punkt': {e}")

# --- Logger ---
def get_logger():
    if current_app: return current_app.logger
    else:
        logger = logging.getLogger('chatbot_custom')
        if not logger.hasHandlers():
            log_format = '%(asctime)s - %(levelname)s - CHATBOT - %(message)s'
            logging.basicConfig(level=logging.INFO, format=log_format)
        return logger

# ===========================================
# === GLOBAL CONSTANTS & DEFINITIONS    ===
# ===========================================
# (Copy toàn bộ INTENTS_DATA và ENTITY_PATTERNS từ trên vào đây)
INTENTS_DATA = {
    "greeting": ["xin chào", "chào", "hello", "hi", "hey", "alo", "chào buổi sáng", "chào buổi tối", "quán ơi"],
    "goodbye": ["tạm biệt", "bye", "goodbye", "hẹn gặp lại", "bai bai", "chào nha", "thoát", "kết thúc"],
    "thanks": ["cảm ơn", "cám ơn", "thank", "tks", "thanks you", "cảm ơn bạn", "ok cảm ơn", "cảm ơn shop", "hay quá", "tuyệt vời"],
    "menu_inquiry": ["menu", "thực đơn", "có món gì", "bán gì", "giá cả", "xem menu", "cho xem đồ", "quán có gì"],
    "category_inquiry": ["cà phê", "cafe", "trà", "tea", "bánh ngọt", "cake", "sinh tố", "smoothie", "nước ép", "juice", "đồ ăn", "ăn vặt", "snack", "đá xay", "ice blended", "frappe", "đặc biệt", "signature", "combo", "món đặc biệt"],
    "hours_inquiry": ["giờ", "mấy giờ", "thời gian", "mở cửa", "đóng cửa", "khi nào mở", "làm việc", "hoạt động", "opening hours", "giờ hoạt động", "thời gian bán"],
    "location_inquiry": ["ở đâu", "địa chỉ", "chi nhánh", "chỗ nào", "tìm quán", "đến quán", "đường nào", "store address", "location", "quán nằm ở", "chỉ đường"],
    "order_intent": ["đặt", "order", "mua", "lấy", "gọi món", "cho tôi", "cho mình", "một ly", "1 ly", "một cái", "1 cái", "một phần", "take", "buy", "get", "đặt hàng"],
    "product_info": ["thông tin", "về món", "là gì", "như thế nào", "thành phần", "chi tiết", "details", "ingredient", "mô tả", "giới thiệu", "cụ thể về"],
    "product_price_inquiry": ["giá bao nhiêu", "bao nhiêu tiền", "giá", "tiền", "cost", "price", "nhiêu tiền"],
    "check_availability": ["còn hàng", "hết hàng", "có bán", "có sẵn", "available", "còn ko", "bán chưa"],
    "promotion_inquiry": ["khuyến mãi", "giảm giá", "ưu đãi", "discount", "deal", "voucher", "coupon", "km", "chương trình", "có sale"],
    "suggest_combo": ["gợi ý combo", "tư vấn combo", "nên uống gì ăn gì", "suggest combo", "recommend combo", "chọn giúp", "nên chọn", "kết hợp"],
    "wifi_inquiry": ["wifi", "internet", "mạng", "pass wifi", "mật khẩu wifi", "pass mạng", "vào mạng"],
    "payment_inquiry": ["thanh toán", "trả tiền", "cà thẻ", "chuyển khoản", "momo", "qr", "payment method", "hình thức", "tính tiền", "trả bill"],
    "visual_product_search": ["ảnh", "hình", "picture", "image", "photo", "nhìn", "trông", "giống", "giống như", "show image", "có hình", "ảnh món"],
    "order_status_inquiry": ["đơn hàng của tôi", "kiểm tra đơn", "trạng thái đơn", "order status", "tình trạng đơn", "đơn đâu rồi", "check order", "xem đơn", "đơn hàng"],
    "generic_question": ["hôm nay thế nào", "bạn khỏe không", "bạn là ai", "sao vậy", "tại sao", "who are you", "how are you", "?", "bạn làm được gì"],
    "affirmation": ["đúng", "vâng", "ok", "oke", "đồng ý", "yes", "ukm", "uh", "phải rồi", "chốt"],
    "negation": ["không", "hủy", "bỏ", "đừng", "no", "cancel", "sai rồi"],
    "quality_inquiry": ["ngon không", "chất lượng", "ổn không", "tươi không", "có tốt không"],
    "ambiance_inquiry": ["không gian", "chỗ ngồi", "thoải mái không", "yên tĩnh không", "checkin", "decor"],
    "reservation_inquiry": ["đặt bàn", "giữ chỗ", "book table"],
    "feedback_complaint": ["góp ý", "phản hồi", "khiếu nại", "chất lượng kém", "phục vụ tệ"],
    "help_inquiry": ["giúp", "cần hỗ trợ", "help"]
}
ENTITY_PATTERNS = {
    "product_name_pattern": r"(?i)\b(cà phê(?: sữa| đen| trứng| muối| cốt dừa| phin)?(?: nóng| đá)?|bạc xỉu(?: đá)?|latte|espresso|cappuccino|mocha|americano|cold brew(?: truyền thống| sữa tươi)?|trà(?: đào(?: cam sả)?| tắc| vải| sen| hoa cúc| ô long| gừng mật ong| sữa(?: trân châu)?| xanh matcha| đen| dâu tây| nhài| atiso)?|sinh tố(?: bơ| dâu| xoài| chanh tuyết| việt quất| mãng cầu| sapoche)?|nước ép(?: cam| táo| dưa hấu| cà rốt| dứa| ổi| cần tây| lựu| bưởi)?|khoai tây(?: chiên)?|bánh phô mai(?: trà xanh| chanh dây)?|bánh tiramisu|bánh sừng bò|croissant|cookie(?: socola| yến mạch)?|pudding trứng|matcha(?: đá xay)?|chocolate(?: đá xay(?: cookie)?| nóng)?|yogurt(?: đá xay| trân châu)?|đá xay(?: việt quất| oreo| phúc bồn tử)?|ca cao(?: sữa| nóng| đá)?|sữa tươi trân châu đường đen|trà sữa kem trứng)\b",
    "category_name_pattern": r"(?i)\b(cà phê|cafe|trà|tea|sinh tố|smoothie|nước ép|juice|bánh|pastry|bánh ngọt|đồ ăn|ăn vặt|snack|đá xay|ice blended|frappe|đặc biệt|signature|combo|yogurt)\b",
    "size": r"(?i)\b(size s|size m|size l|nhỏ|vừa|lớn|bé|to|bự|small|medium|large|big)\b",
    "quantity": r"\b(một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|[0-9]+)\s*(ly|cốc|cái|phần|suất|chai|tách|cup|cups?|shot|gói|hũ|bịch|hộp)\b",
    "price_query_kw": r"(?i)\b(giá|bao nhiêu tiền|tiền|cost|price|rate|giá tiền)\b",
    "availability_query_kw": r"(?i)\b(còn hàng|hết hàng|có bán|có sẵn|available|còn ko)\b",
    "notes": r"(?i)\b(ít đường|nhiều đá|không đá|ít ngọt|nóng|lạnh|không sữa|thêm kem|ít kem|thêm trân châu|add boba|thêm topping|add topping|không topping|không đường|no sugar|less ice|no ice|more ice|less sweet|hot|cold|warm|no milk|add cream|less cream|add whip|no whip|extra shot|double shot)\b",
    "visual_keyword": r"(?i)\b(trắng|đen|nâu|vàng|đỏ|xanh lá|xanh dương|hồng|cam|tím|kem|be|bọt|foam|nhiều lớp|layer|có tầng|trong suốt|clear|trong veo|sánh đặc|thick|loãng|thin|giòn|crisp|mềm|soft|mịn|smooth|sần|sần sùi|grainy|lấp lánh|shiny|sparkling)\b",
    "order_number": r"(?i)(?:đơn|mã|số|dh|hd|order|bill)\s*[:#\-]?\s*([OoRrDd]{3}[-\s]?\w{6,}[-\s]?\w{4})\b",
    "order_number_simple": r"(?i)(?:đơn|mã|số|dh|hd|order|bill)\s+#?([\w\d]{5,15})\b",
    "combo_keyword": r"(?i)\b(combo|gói|set|kết hợp)\b",
    "confirm_yes": r"(?i)^(?:yes|yep|ok|oke|uh|ukm|đúng|vâng|đồng ý|chốt|đặt đi|đặt luôn|confirm|ừ|ừa|đặt)$",
    "confirm_no": r"(?i)^(?:no|nope|cancel|hủy|bỏ|không|đừng|thôi|stop)$",
    "quality_kw": r"(?i)\b(ngon|dở|chất lượng|ổn|tươi|tốt|tệ|hay|hợp|hạp)\b",
    "ambiance_kw": r"(?i)\b(không gian|chỗ ngồi|thoải mái|yên tĩnh|checkin|decor|đẹp|view|trang trí|nhạc)\b",
    "reservation_kw": r"(?i)\b(đặt bàn|giữ chỗ|book table|reservation)\b",
    "feedback_kw": r"(?i)\b(góp ý|phản hồi|khiếu nại|phàn nàn|tệ|chê)\b",
    "help_kw": r"(?i)\b(giúp|cần hỗ trợ|help)\b",
    "bot_kw": r"(?i)\b(bạn là ai|mày là ai|bot|chatbot|who are you|làm được gì|chức năng)\b"
}

RESPONSE_TEMPLATES = {}
TEMPLATES_FILE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'chatbot_responses.json')

def load_or_create_templates():
    global RESPONSE_TEMPLATES
    logger = get_logger()
    try:
        if os.path.exists(TEMPLATES_FILE_PATH):
            with open(TEMPLATES_FILE_PATH, 'r', encoding='utf-8') as f:
                loaded_templates = json.load(f)
                default_templates = create_default_templates()
                merged_templates = {**default_templates, **loaded_templates}
                # Check if any default template uses placeholders missing in merged
                for key, val_list in default_templates.items():
                    if key not in merged_templates or not merged_templates[key]:
                         logger.warning(f"Template key '{key}' missing or empty in loaded file, using default.")
                         merged_templates[key] = val_list # Ensure key exists with default if empty in loaded file
                RESPONSE_TEMPLATES = merged_templates
                logger.info(f"Successfully loaded/merged response templates from {TEMPLATES_FILE_PATH}")
        else:
            logger.warning(f"Template file not found: {TEMPLATES_FILE_PATH}. Creating defaults.")
            RESPONSE_TEMPLATES = create_default_templates()
            try:
                with open(TEMPLATES_FILE_PATH, 'w', encoding='utf-8') as f: json.dump(RESPONSE_TEMPLATES, f, ensure_ascii=False, indent=4)
                logger.info(f"Saved default templates to {TEMPLATES_FILE_PATH}")
            except Exception as save_e: logger.error(f"Could not save default templates: {save_e}")
    except Exception as e:
        logger.error(f"Error loading/creating templates: {e}. Using basic defaults.", exc_info=True)
        RESPONSE_TEMPLATES = create_default_templates()

# (Tải dữ liệu NLTK và Templates khi khởi động)
# download_nltk_data()
load_or_create_templates()

# ===========================================
# === NLP & ENTITY EXTRACTION           ===
# ===========================================
def preprocess_text(text):
    # Giữ nguyên hàm này
    logger = get_logger()
    try:
        if not text or not isinstance(text, str): return []
        text_lower = text.lower()
        text_cleaned = re.sub(r'[^\w\sàáãạảăắằẳẵặâấầẩẫậèéẹẻẽêềếểễệđìíỉĩịòóõọỏôốồổỗộơớờởỡợùúũụủưứừửữựỳýỷỹỵ]', '', text_lower)
        tokens = text_cleaned.split()
        tokens = [word for word in tokens if len(word) > 1 or word.isdigit()]
        return tokens
    except Exception as e: logger.error(f"Error preprocessing text '{text[:50]}...': {e}", exc_info=False); return text.lower().split()

def extract_entities_custom(text):
    # Giữ nguyên hàm này
    logger = get_logger()
    entities = {}
    if not text or not isinstance(text, str): return entities
    processed_indices = set()
    patterns_ordered = sorted(ENTITY_PATTERNS.items(), key=lambda item: len(item[1]), reverse=True)
    for entity_type, pattern in patterns_ordered:
        try:
            if entity_type.endswith('_kw'):
                 if re.search(pattern, text, re.IGNORECASE): entities[entity_type.replace('_kw', '')] = True
                 continue
            for match in re.finditer(pattern, text, re.IGNORECASE):
                start, end = match.span()
                is_overlapped = any(max(start, p_start) < min(end, p_end) for p_start, p_end in processed_indices)
                if is_overlapped: continue
                entity_value = match.group(0).strip(); raw_group1 = match.group(1).strip() if len(match.groups()) > 0 else None
                if entity_type == 'product_name_pattern': entities.setdefault("product", []).append(entity_value.lower())
                elif entity_type == 'category_name_pattern':
                    is_subspan = False;
                    if "product" in entities: is_subspan = any(entity_value.lower() in p for p in entities["product"])
                    if not is_subspan: entities.setdefault("category", []).append(entity_value.lower())
                elif entity_type == 'quantity':
                    qmap = {'một': 1, 'hai': 2, 'ba': 3, 'bốn': 4, 'năm': 5, 'sáu': 6, 'bảy': 7, 'tám': 8, 'chín': 9, 'mười': 10}
                    if raw_group1: entities['quantity'] = qmap.get(raw_group1.lower(), int(raw_group1) if raw_group1.isdigit() else 1)
                elif entity_type in ['notes', 'visual_keyword']: entities.setdefault(entity_type+"s", []).append(entity_value.lower()) # Note: visual_keywords
                elif entity_type in ['order_number', 'order_number_simple']:
                     if raw_group1 and 'order_number' not in entities: entities['order_number'] = raw_group1.upper().replace("-", "").replace(" ","")
                elif entity_type == 'combo_keyword': entities['combo_keyword'] = True
                elif entity_type not in entities: entities[entity_type] = entity_value.lower()
                processed_indices.add((start, end))
        except Exception as regex_e: logger.error(f"Regex error for {entity_type} pattern '{pattern}': {regex_e}", exc_info=False)
    for key in ["product", "category", "notes", "visual_keywords"]:
        if key in entities: entities[key] = sorted(list(set(entities[key])), key=len, reverse=True)
    return entities

# ===========================================
# === INTENT DETECTION                    ===
# ===========================================
def detect_intent_custom(text, db_session):
    logger = get_logger()
    if not text or not isinstance(text, str): return 'fallback'
    entities = extract_entities_custom(text); text_lower = text.lower(); tokens = preprocess_text(text_lower); text_len = len(tokens)

    # --- Highest Priority: Confirmation (Yes/No) - Needs context ---
    # Note: Context needs to be passed or accessed globally/via session_id
    # if is_confirming_order(session_id) and re.match(ENTITY_PATTERNS['confirm_yes'], text_lower): return "order_confirmation_yes"
    # if is_confirming_order(session_id) and re.match(ENTITY_PATTERNS['confirm_no'], text_lower): return "order_confirmation_no"
    if re.match(ENTITY_PATTERNS['confirm_yes'], text_lower) and text_len <=2: return "affirmation" # Simple Yes
    if re.match(ENTITY_PATTERNS['confirm_no'], text_lower) and text_len <=2: return "negation" # Simple No

    # --- Rule-Based based on Entities and Keywords ---
    rules_map = {
        "order_status_inquiry": (entities.get("order_number") and not any(kw in text_lower for kw in INTENTS_DATA.get('order_intent',[]))),
        "order_intent": ("product" in entities and (any(kw in tokens for kw in INTENTS_DATA.get('order_intent', [])) or "quantity" in entities)),
        "check_availability": ("product" in entities and entities.get("availability")),
        "product_price_inquiry": ("product" in entities and entities.get("price_query")),
        "product_info": ("product" in entities and any(kw in text_lower for kw in INTENTS_DATA.get('product_info', [])) and not entities.get("price_query") and not entities.get("availability")),
        "suggest_combo": any(kw in text_lower for kw in INTENTS_DATA.get('suggest_combo', [])),
        "combo_inquiry": (entities.get('combo_keyword') and not entities.get('product') and 'suggest_combo' not in rules_map and not any(kw in text_lower for kw in INTENTS_DATA.get('suggest_combo', []))), # If asking about combo generally
        "category_inquiry": ("category" in entities and "product" not in entities and not any(kw in text_lower for kw in ['menu','thực đơn'])),
        "visual_product_search": (any(kw in text_lower for kw in INTENTS_DATA.get('visual_product_search',[])) and not any(ex in text_lower for ex in ["menu","giá","địa chỉ","giờ","đơn hàng"]) and (entities.get("visual_keywords") or text_len >=3)),
        "feedback_complaint": any(kw in text_lower for kw in INTENTS_DATA.get('feedback_complaint', [])),
        "reservation_inquiry": any(kw in text_lower for kw in INTENTS_DATA.get('reservation_inquiry', [])),
        "ambiance_inquiry": any(kw in text_lower for kw in INTENTS_DATA.get('ambiance_inquiry', [])),
        "quality_inquiry": any(kw in text_lower for kw in INTENTS_DATA.get('quality_inquiry', [])),
        "help_inquiry": any(kw in text_lower for kw in INTENTS_DATA.get('help_inquiry', [])),
        "bot_identity": any(kw in text_lower for kw in INTENTS_DATA.get('bot_identity',[])) or any(kw in text_lower for kw in INTENTS_DATA.get('bot_capability',[])) # Gộp chung hỏi về bot
    }
    for intent, condition in rules_map.items():
        if condition: logger.debug(f"Intent[Rule]: {intent}"); return intent

    # Handle single-word intents missed by rules
    if text_len == 1:
        word = tokens[0]
        for intent, keywords in INTENTS_DATA.items():
             if word in keywords and intent in ['menu_inquiry','hours_inquiry','location_inquiry','promotion_inquiry','wifi_inquiry','payment_inquiry','greeting','thanks','goodbye', 'help_inquiry']:
                logger.debug(f"Intent[SingleWord]: {intent}"); return intent

    # === Keyword Scoring (Fallback) ===
    scores = defaultdict(float)
    exclude_from_scoring = set(rules_map.keys()) # Don't score intents already matched by rules
    for intent, keywords in INTENTS_DATA.items():
        if intent in exclude_from_scoring: continue
        weight = 1.0
        if intent == "greeting": weight = 1.8
        if intent == "thanks": weight = 1.5
        if intent == "goodbye": weight = 1.8
        if intent in ["wifi_inquiry", "payment_inquiry", "hours_inquiry", "location_inquiry", "promotion_inquiry"]: weight = 1.2
        if intent == "generic_question": weight = 0.8

        for phrase in keywords:
             if phrase in text_lower:
                 score_add = (1.8 * len(phrase.split()) if len(phrase.split()) > 1 else 1.0) * weight
                 scores[intent] += score_add

    if scores:
        matched_intent = max(scores, key=scores.get)
        max_score = scores[matched_intent]
        threshold = 1.6 if text_len <= 2 else 1.9 # Lower threshold for shorter inputs
        if max_score >= threshold:
             logger.info(f"Intent[Score]: '{matched_intent}' (Score: {max_score:.2f})")
             # Refinements
             if matched_intent == 'generic_question': # Don't easily fallback to generic if another intent is plausible
                 non_generic_scores = {k:v for k,v in scores.items() if k != 'generic_question'}
                 if non_generic_scores:
                     second_best = max(non_generic_scores, key=non_generic_scores.get)
                     if scores[second_best] > threshold * 0.7: logger.info(f"Refining Generic->'{second_best}'"); return second_best
             return matched_intent
        else: logger.info(f"Scores below threshold ({threshold}). Highest: {max_score:.2f} for '{matched_intent}' -> Fallback.")
    else: logger.info("No keywords matched -> Fallback.")
    return "fallback"

# ===========================================
# === DB & Formatting Helpers             ===
# ===========================================
def format_currency_vn(amount):
    if amount is None: return "[Chưa có giá]"
    try: return f"{int(round(amount)):,}₫".replace(",", ".")
    except (ValueError, TypeError): return "[Lỗi giá]"

def format_product_list(products, max_items=3):
    if not products: return "đang cập nhật"
    names = [p.name for p in products]
    if len(names) > max_items: return ", ".join(names[:max_items]) + f",..."
    else: return ", ".join(names)

def get_db_link_html(link_type, db_session, **kwargs):
    logger = get_logger(); url, text = "#", ""
    try: # Try/except block for url_for
        with current_app.app_context(): # Ensure context for url_for
            endpoint_map={'menu':('main.menu',"trang Menu"),'locations':('main.locations',"trang Địa điểm"), 'promotions':('main.promotions_page',"trang Khuyến mãi"), 'product':('main.product_detail',"xem chi tiết"),'order_detail':('order.order_detail',"xem đơn hàng")}
            if link_type not in endpoint_map: return ""
            endpoint, default_text = endpoint_map[link_type]
            text = kwargs.get('text', default_text)
            url_kwargs = {k: v for k, v in kwargs.items() if k not in ['text','db_session']} # Filter kwargs
            if link_type == 'category_menu' and 'category_id' in kwargs: url_kwargs['category'] = kwargs['category_id']; endpoint = 'main.menu' # Adjust endpoint/param
            if link_type == 'product' and 'product_id' in kwargs: url_kwargs['product_id'] = kwargs['product_id']
            if link_type == 'order_detail' and 'order_id' in kwargs: url_kwargs['order_id'] = kwargs['order_id']
            url = url_for(endpoint, _external=False, **url_kwargs) # _external=False is usually fine for links in app
            if url: return f"<a href='{url}' target='_blank'>{text}</a>"
    except Exception as e: logger.warning(f"Could not generate URL for '{link_type}': {e}")
    return "" # Return empty string on failure

def get_product_info_from_db(product_name, db_session):
    logger = get_logger(); logger.debug(f"DB Search: '{product_name}'")
    try: # Try/Except block for DB query
        # 1. Exact match (case-insensitive)
        exact_match = db_session.query(Product).options(joinedload(Product.inventory), joinedload(Product.category)).filter(func.lower(Product.name) == func.lower(product_name)).first()
        if exact_match: logger.debug(f"DB: Exact match ID {exact_match.id}"); return exact_match
        # 2. Partial match (case-insensitive), prefer shorter results
        partial_matches = db_session.query(Product).options(joinedload(Product.inventory), joinedload(Product.category)).filter(Product.name.ilike(f"%{product_name}%")).order_by(func.length(Product.name)).limit(5).all()
        if partial_matches: logger.debug(f"DB: Found {len(partial_matches)} partial matches."); return partial_matches[0] # Return the shortest partial match
        logger.debug(f"DB: No product found for '{product_name}'")
        return None
    except Exception as e: logger.error(f"DB Error get_product_info: {e}", exc_info=True); return None

# ===========================================
# === ACTION HANDLERS (Using DB)        ===
# ===========================================
conversation_context = {} # Basic context storage (replace with better solution if needed)

def handle_greeting(entities, db_session): return random.choice(RESPONSE_TEMPLATES['greeting'])
def handle_goodbye(entities, db_session): return random.choice(RESPONSE_TEMPLATES['goodbye'])
def handle_thanks(entities, db_session): return random.choice(RESPONSE_TEMPLATES['thanks'])
def handle_hours_inquiry(entities, db_session): return random.choice(RESPONSE_TEMPLATES['hours_inquiry'])
def handle_wifi_inquiry(entities, db_session): return random.choice(RESPONSE_TEMPLATES['wifi_inquiry'])
def handle_payment_inquiry(entities, db_session): return random.choice(RESPONSE_TEMPLATES['payment_inquiry'])

def handle_location_inquiry(entities, db_session):
    # Lấy địa chỉ cố định hoặc từ DB/config
    address_list = ["- 123 Đường ABC, Quận XYZ, TP. HCM", "- 456 Đại lộ Rồng, Thành phố Rồng"]
    locations_link = get_db_link_html('locations', db_session, text="Xem bản đồ và chi nhánh khác")
    response = random.choice(RESPONSE_TEMPLATES['location_inquiry']).format(locations_url=locations_link)
    response += "\n" + "\n".join(address_list)
    return response

def handle_menu_inquiry(entities, db_session):
    logger = get_logger()
    try:
        featured = db_session.query(Product).filter(Product.is_available == True, Product.is_featured == True).order_by(func.random()).limit(3).all()
        others = db_session.query(Product).filter(Product.is_available == True, Product.is_featured == False).order_by(func.random()).limit(2).all()
        suggestions_str = f" Gợi ý thử: {format_product_list(featured + others)}." if featured or others else ""
        menu_link = get_db_link_html('menu', db_session)
        tmpl = random.choice(RESPONSE_TEMPLATES.get('menu_inquiry'))
        return tmpl.format(menu_url=menu_link, suggestions=suggestions_str)
    except Exception as e: logger.error(f"Error handle_menu_inquiry: {e}"); return random.choice(RESPONSE_TEMPLATES['error'])

def handle_category_inquiry(entities, db_session):
    logger = get_logger(); cat_names = entities.get("category", []);
    if not cat_names: return "Bạn hỏi nhóm món nào ạ (cà phê, trà, bánh...)?"
    target_cat = cat_names[0].lower(); logger.info(f"Category inquiry: '{target_cat}'")
    if target_cat == "combo": return handle_suggest_combo(entities, db_session) # Delegate
    try:
        category = db_session.query(Category)\
    .filter(func.lower(Category.name) == target_cat.lower()).first() # Tìm chính xác trước
        if not category:
            # Nếu không tìm thấy, thử tìm LIKE VÀ đảm bảo đó là category phổ biến
            plausible_cats = ['cà phê', 'cafe', 'trà', 'tea', 'bánh', 'bánh ngọt', 'sinh tố', 'smoothie', 'nước ép', 'juice', 'đá xay', 'ice blended', 'frappe', 'combo', 'snack', 'đồ ăn', 'ăn vặt']
            if target_cat in plausible_cats: # Chỉ tìm LIKE nếu keyword có vẻ là category hợp lệ
                category = db_session.query(Category)\
                    .filter(Category.name.ilike(f"%{target_cat}%")).first()
        if category:
            prods = db_session.query(Product).filter(Product.category_id == category.id, Product.is_available == True).order_by(Product.is_featured.desc(), func.random()).limit(5).all()
            p_list = format_product_list(prods, 3)
            cat_menu_link = get_db_link_html('category_menu', db_session, category_id=category.id, text="Xem thêm")
            tmpl = random.choice(RESPONSE_TEMPLATES.get('category_inquiry_result'))
            return tmpl.format(category_name=category.name, product_list=p_list, menu_url=cat_menu_link)
        else:
            tmpl = random.choice(RESPONSE_TEMPLATES.get('category_not_found'))
            return tmpl.format(category_name=cat_names[0])
    except Exception as e: logger.error(f"Error category inquiry '{target_cat}': {e}", exc_info=True); return random.choice(RESPONSE_TEMPLATES['error'])

def handle_product_info(entities, db_session):
    logger = get_logger(); product_names = entities.get("product", []);
    if not product_names: return "Bạn muốn biết thông tin món nào?"
    target_name = product_names[0]; logger.info(f"Product info request: '{target_name}'")
    try:
        product = get_product_info_from_db(target_name, db_session)
        if product:
            is_avail = product.is_available and (product.inventory is None or product.inventory.quantity > 0)
            avail_text = "còn hàng" if is_avail else "đang tạm hết"
            desc = product.description or "Món signature thơm ngon khó cưỡng."
            cat_name = product.category.name if product.category else "Đặc biệt"
            price_str_value = format_currency_vn(product.price)
            prod_link = get_db_link_html('product', db_session, product_id=product.id, text="[Xem chi tiết]")
            tmpl = random.choice(RESPONSE_TEMPLATES.get('product_info')) # Template này có price
            return tmpl.format(product_name=product.name, category=cat_name, price=price_str_value, description=desc, availability=avail_text, product_link=prod_link)
        else: menu_link = get_db_link_html('menu', db_session); tmpl = random.choice(RESPONSE_TEMPLATES["product_not_found"]); return tmpl.format(product_name=target_name, menu_url=menu_link)
    except Exception as e: logger.error(f"Error product info '{target_name}': {e}", exc_info=True); return random.choice(RESPONSE_TEMPLATES['error'])

def handle_product_price_inquiry(entities, db_session):
    logger = get_logger(); product_names = entities.get("product", []);
    if not product_names: menu_link = get_db_link_html('menu', db_session); return f"Bạn muốn hỏi giá món nào? Xem {menu_link} nhé."
    target_name = product_names[0]; logger.info(f"Price inquiry: '{target_name}'")
    try:
        product = get_product_info_from_db(target_name, db_session)
        if product:
             if product.price is not None: p_str = format_currency_vn(product.price); tmpl = random.choice(RESPONSE_TEMPLATES['product_price_inquiry_result']); return tmpl.format(product_name=product.name, price_str=p_str) + " Bạn đặt món này không?"
             else: return f"Món '{product.name}' chưa có giá công bố."
        else: return random.choice(RESPONSE_TEMPLATES["product_not_found"]).format(product_name=target_name)
    except Exception as e: logger.error(f"Error price inquiry '{target_name}': {e}", exc_info=True); return random.choice(RESPONSE_TEMPLATES['error'])

# Code xử lý khi không tìm thấy sản phẩm (else của khối try-except hoặc trong khối try sau khi check product is None)
    if not product:
        menu_link_html = get_db_link_html('menu', db_session) # <--- Lấy link menu
        tmpl = random.choice(RESPONSE_TEMPLATES["product_not_found"])
        try:
            # Thử format với cả 2 key, key nào template không có sẽ bị bỏ qua
            return tmpl.format(product_name=target_name, menu_url=menu_link_html)
        except KeyError as ke:
            # Fallback nếu template vẫn bị lỗi key lạ (dù đã cố gắng cung cấp)
            logger.warning(f"KeyError formatting product_not_found template ({ke}). Template: {tmpl}")
            return f"Xin lỗi, tôi không tìm thấy món '{target_name}'. Bạn thử tìm món khác nhé."

def handle_check_availability(entities, db_session):
    logger = get_logger(); product_names = entities.get("product", []);
    if not product_names: return "Bạn muốn kiểm tra món nào còn không?"
    target_name = product_names[0]; logger.info(f"Availability check: '{target_name}'")
    try:
        product = get_product_info_from_db(target_name, db_session)
        if product:
            is_avail = product.is_available and (product.inventory is None or product.inventory.quantity > 0)
            stat = "còn hàng" if is_avail else "đang tạm hết"
            tmpl = random.choice(RESPONSE_TEMPLATES["check_availability_result"])
            suggestion = " Bạn muốn đặt món này chứ?" if is_avail else " Bạn chọn món khác nhé?"
            return tmpl.format(product_name=product.name, status=stat) + suggestion
        else: return random.choice(RESPONSE_TEMPLATES['check_availability_not_found']).format(product_name=target_name)
    except Exception as e: logger.error(f"Error availability check '{target_name}': {e}", exc_info=True); return random.choice(RESPONSE_TEMPLATES['error'])

def handle_promotion_inquiry(entities, db_session):
    logger = get_logger(); logger.info("Handling promotion inquiry")
    try:
        now = datetime.utcnow()
        promos = db_session.query(Promotion).filter(Promotion.is_active == True, Promotion.start_date <= now, Promotion.end_date >= now).order_by(Promotion.end_date.asc()).limit(4).all()
        if not promos: return random.choice(RESPONSE_TEMPLATES['promotion_inquiry_none'])
        p_texts = []; idx=1
        for p in promos:
            t=f"{idx}. **{p.name}**: "; desc = p.description or ""
            if p.discount_percent: desc += f" (Giảm {p.discount_percent}%)"
            if p.discount_amount: desc += f" (Giảm {format_currency_vn(p.discount_amount)})"
            if p.code: desc += f" [Mã: `{p.code}`]"
            t += f"{desc[:60]}{'...' if len(desc)>60 else ''}. (HSD: {p.end_date.strftime('%d/%m')})"; p_texts.append(t); idx+=1
        promo_list = "\n".join(p_texts); promo_link = get_db_link_html('promotions', db_session, text="Chi tiết")
        tmpl = random.choice(RESPONSE_TEMPLATES['promotion_inquiry'])
        return tmpl.format(promotion_list=promo_list, promotions_url=promo_link).strip()
    except Exception as e: logger.error(f"DB Err promos: {e}", exc_info=True); return random.choice(RESPONSE_TEMPLATES['error'])

def handle_suggest_combo(entities, db_session):
    logger = get_logger(); prefs = entities.get("product", []) + entities.get("category", []); pref_text = prefs[0] if prefs else None
    logger.info(f"Handling combo suggestion. Preferences: {pref_text}")
    try:
        drink, food = None, None
        # Find suitable drink
        drink_q = db_session.query(Product).join(Category).filter(Product.is_available == True, Category.name.in_(['Cà phê', 'Trà', 'Nước ép', 'Sinh tố', 'Đá xay']))
        if pref_text: drink_q = drink_q.filter(or_(Product.name.ilike(f'%{pref_text}%'), Category.name.ilike(f'%{pref_text}%')))
        drink = drink_q.order_by(func.random()).first()
        # Find suitable food
        food_q = db_session.query(Product).join(Category).filter(Product.is_available == True, Category.name.in_(['Bánh ngọt', 'Đồ ăn nhẹ', 'Snack']))
        # Avoid suggesting the same category if drink is also a 'food' category somehow
        if drink and drink.category and drink.category.name in ['Bánh ngọt', 'Đồ ăn nhẹ', 'Snack']:
            food_q = food_q.filter(Category.id != drink.category_id)
        food = food_q.order_by(func.random()).first()

        if drink and food and drink.price is not None and food.price is not None:
            c_name=f"{drink.name} & {food.name}"; c_items=f"{drink.name} và {food.name}"
            c_price=format_currency_vn((drink.price + food.price) * 0.9) # 10% off combo
            tmpl=random.choice(RESPONSE_TEMPLATES['suggest_combo_result'])
            return tmpl.format(combo_name=c_name, combo_items=c_items, combo_price=c_price, preference=f"cho bạn thích '{pref_text}'" if pref_text else "cho bạn")
        elif drink: return f"Bạn thử '{drink.name}' nhé? Có muốn ăn thêm bánh hay gì không?"
        else: return random.choice(RESPONSE_TEMPLATES['suggest_combo_no_pref'])
    except Exception as e: logger.error(f"Error suggest combo: {e}", exc_info=True); return random.choice(RESPONSE_TEMPLATES['suggest_combo_no_pref'])

def handle_order_status_inquiry(entities, db_session):
    logger = get_logger(); order_num = entities.get("order_number")
    if not order_num: return random.choice(RESPONSE_TEMPLATES['order_status_ask_number'])
    logger.info(f"Handling order status: '{order_num}'")
    try:
        order = db_session.query(Order).filter(or_(Order.order_number == order_num, cast(Order.id, String) == order_num)).first() # Allow search by ID too
        if order:
            stat = order.get_status_display(); date = order.created_at.strftime('%d/%m/%Y') if order.created_at else 'N/A'; det=""
            if order.status == 'processing': det = "Quán đang chuẩn bị món nha."
            elif order.status == 'ready_for_pickup': det = "Đồ đã sẵn sàng mời bạn ghé lấy."
            elif order.status == 'out_for_delivery': det = "Shipper đang trên đường giao ạ."
            elif order.status in ['completed', 'delivered']: det = "Cảm ơn bạn nhiều!"
            elif order.status == 'cancelled': det = "Đơn này đã bị hủy rồi ạ."
            tmpl = random.choice(RESPONSE_TEMPLATES['order_status_found'])
            link = get_db_link_html('order_detail', db_session, order_id=order.id, text="[Chi tiết]")
            return tmpl.format(order_number=order.order_number, order_date=date, status_display=stat, details=det, order_link=link)
        else: tmpl = random.choice(RESPONSE_TEMPLATES['order_status_not_found']); return tmpl.format(order_number=order_num)
    except Exception as e: logger.error(f"Error order status '{order_num}': {e}", exc_info=True); return random.choice(RESPONSE_TEMPLATES['error'])

def handle_visual_product_search(entities, db_session):
    logger = get_logger()
    visual_kws=list(set(entities.get("visual_keywords",[])+entities.get("product",[])+entities.get("category",[])))
    stop_words={"ảnh","hình","picture","image","photo","cho","tôi","xem","tìm","với","có","một","rất","khá","như","giống","là","của","nhìn","trông","thì","mà","ly","cốc", "cái", "phần", "đồ uống"}
    final_kws=[kw for kw in visual_kws if kw and kw not in stop_words and len(kw)>1]; # Lọc lại keywords
    if not final_kws: return {'response':random.choice(RESPONSE_TEMPLATES["visual_product_search_nokeywords"]),'image_results':[]}
    logger.info(f"Handling visual search: {final_kws}")
    try:
        img_res=search_products_by_visual_keywords(final_kws,db_session,limit=4); kw_str=", ".join(final_kws)
        if img_res: tmpl=random.choice(RESPONSE_TEMPLATES["visual_product_search_result"]); resp=tmpl.format(keywords=kw_str)
        else: tmpl=random.choice(RESPONSE_TEMPLATES["visual_product_search_notfound"]); resp=tmpl.format(keywords=kw_str)
        return {'response':resp,'image_results':img_res}
    except Exception as e: logger.error(f"Error visual search handler: {e}",exc_info=True); return {'response':random.choice(RESPONSE_TEMPLATES['error']),'image_results':[]}

def handle_order_intent(entities, db_session, session_id=None):
    global conversation_context # Access global context store
    logger = get_logger()
    p_names = entities.get("product"); qty = entities.get("quantity", 1)
    size = entities.get("size", "vừa"); notes = entities.get("notes", [])
    notes_str = f" (ghi chú: {', '.join(notes)})" if notes else ""

    if not p_names: return random.choice(RESPONSE_TEMPLATES['order_intent_noproduct']).format(menu_url=get_db_link_html('menu', db_session))
    target_name = p_names[0].title()
    logger.info(f"Order Intent: Confirming {qty} x '{target_name}', Size: {size}, Notes: {notes_str}")

    try:
        product = get_product_info_from_db(target_name, db_session)
        if not product: return random.choice(RESPONSE_TEMPLATES['product_not_found']).format(product_name=target_name)

        is_avail = product.is_available and (product.inventory is None or product.inventory.quantity >= qty)
        if not is_avail: avail_qty = product.inventory.quantity if product.inventory else 0; return f"Xin lỗi, '{product.name}' không đủ số lượng (còn {avail_qty}). Bạn chọn lại nhé?"

        price_str = format_currency_vn(product.price * qty) if product.price else "..."
        tmpl = random.choice(RESPONSE_TEMPLATES['order_confirmation_request'])
        confirm_text = tmpl.format(quantity=qty, product_name=product.name, size=size, notes=notes_str, price_str=price_str)

        # === Store pending order in context ===
        if session_id:
             conversation_context[session_id] = {
                 'state': 'awaiting_order_confirmation',
                 'pending_order': {
                     'product_id': product.id,
                     'product_name': product.name,
                     'quantity': qty,
                     'size': size,
                     'notes': notes,
                     'estimated_price': product.price * qty if product.price else 0
                 },
                 'timestamp': datetime.utcnow()
             }
             logger.info(f"Stored pending order for SID {session_id}: {conversation_context[session_id]['pending_order']}")
        else: logger.warning("No session ID provided, cannot store pending order context.")
        # =====================================

        return confirm_text

    except Exception as e: logger.error(f"Error order intent '{target_name}': {e}", exc_info=True); return random.choice(RESPONSE_TEMPLATES['error'])

# === New Handlers ===
def handle_affirmation(entities, db_session, session_id=None):
    global conversation_context
    logger = get_logger(); context = conversation_context.get(session_id)
    if context and context.get('state') == 'awaiting_order_confirmation' and context.get('pending_order'):
         # === Execute Order Placement ===
         pending_order = context['pending_order']
         logger.info(f"Affirmation received for pending order: {pending_order}")
         error_reason = None
         try:
              # 1. Double-check inventory (critical section - use with_for_update)
              inv_item = db_session.query(InventoryItem).filter_by(product_id=pending_order['product_id']).with_for_update().first()
              if not inv_item or inv_item.quantity < pending_order['quantity']:
                  raise ValueError(f"Hết hàng hoặc không đủ số lượng cho '{pending_order['product_name']}' khi xác nhận.")
              # 2. Create Order and OrderDetail
              new_order = Order(
                  # user_id=context.get('user_id'), # Need user ID from session/context
                  order_number=f"BOT-{uuid.uuid4().hex[:8].upper()}", status='pending', # Bot orders start pending
                  total_amount=pending_order['estimated_price'], final_amount=pending_order['estimated_price']*1.1, # Simple total+tax
                  order_type='chatbot', payment_method='pending', payment_status='pending',
                  notes=", ".join(pending_order['notes']) if pending_order['notes'] else ''
              )
              db_session.add(new_order); db_session.flush()
              new_detail = OrderDetail(
                  order_id=new_order.id, product_id=pending_order['product_id'],
                  quantity=pending_order['quantity'], unit_price=pending_order['estimated_price']/pending_order['quantity'],
                  subtotal=pending_order['estimated_price'], notes=", ".join(pending_order['notes']))
              db_session.add(new_detail)
              # 3. Decrement Inventory
              inv_item.quantity -= pending_order['quantity']
              inv_item.last_updated = datetime.utcnow()
              db_session.commit()
              logger.info(f"Successfully created order {new_order.order_number} via chatbot.")
              # Clear context
              conversation_context.pop(session_id, None)
              tmpl=random.choice(RESPONSE_TEMPLATES['order_success'])
              return tmpl.format(order_number=new_order.order_number)
         except Exception as order_e:
              db_session.rollback()
              logger.error(f"Failed to create order from context: {order_e}", exc_info=True)
              error_reason = str(order_e)
              conversation_context.pop(session_id, None) # Clear context on error too
              tmpl=random.choice(RESPONSE_TEMPLATES['order_failed'])
              return tmpl.format(error_reason=error_reason or "Lỗi hệ thống.")
    else: # Affirmation outside order confirmation
         return random.choice(RESPONSE_TEMPLATES.get('affirmation', ["Ok ạ."]))

def handle_negation(entities, db_session, session_id=None):
    global conversation_context
    logger = get_logger(); context = conversation_context.get(session_id)
    if context and context.get('state') == 'awaiting_order_confirmation':
        logger.info("Negation received for pending order. Cancelling.")
        conversation_context.pop(session_id, None) # Clear context
        return random.choice(RESPONSE_TEMPLATES.get('order_confirmation_no', ["Ok, đã hủy. Bạn muốn đặt món khác không?"]))
    else: return random.choice(RESPONSE_TEMPLATES.get('negation', ["Dạ vâng ạ."]))

def handle_quality_inquiry(entities, db_session):
    logger = get_logger(); product_names = entities.get("product", [])
    if product_names:
        target_name = product_names[0]; logger.info(f"Quality inquiry for: {target_name}")
        product = get_product_info_from_db(target_name, db_session)
        if product:
            # Simple quality statements based on type or rating (if implemented)
            adj = random.choice(["đậm đà", "thơm ngon", "tươi mới", "đặc biệt"])
            tmpl = random.choice(RESPONSE_TEMPLATES.get('quality_inquiry_product'))
            return tmpl.format(product_name=product.name, quality_adj=adj, ingredient_highlight=product.category.name.lower() if product.category else "đặc biệt")
        else: return random.choice(RESPONSE_TEMPLATES.get('product_not_found')).format(product_name=target_name)
    else: logger.info("General quality inquiry"); return random.choice(RESPONSE_TEMPLATES.get('quality_inquiry_general'))

def handle_ambiance_inquiry(entities, db_session):
    logger = get_logger(); logger.info("Handling ambiance inquiry.")
    # Cần mô tả cố định hoặc lấy từ DB/config nếu có
    theme="Á Đông huyền bí"; zone1="sofa"; zone2="bàn cao"; feature="tượng rồng";
    tmpl=random.choice(RESPONSE_TEMPLATES.get('ambiance_inquiry'))
    return tmpl.format(theme_description=theme, zone_type1=zone1, zone_type2=zone2, decor_feature=feature)

def handle_reservation_inquiry(entities, db_session):
    logger = get_logger(); logger.info("Handling reservation inquiry.")
    # Lấy hotline từ config hoặc cứng
    hotline = "[Số Hotline Chính]"; locations_link = get_db_link_html('locations', db_session)
    tmpl=random.choice(RESPONSE_TEMPLATES.get('reservation_inquiry'))
    return tmpl.format(hotline=hotline, locations_url=locations_link)

def handle_feedback_complaint(entities, db_session):
    logger = get_logger(); logger.info("Handling feedback/complaint.")
    hotline="[Số Hotline CSKH]"; email="[Email CSKH]"
    tmpl=random.choice(RESPONSE_TEMPLATES.get('feedback_complaint'))
    return tmpl.format(hotline=hotline, feedback_email=email)

def handle_help_inquiry(entities, db_session):
    logger = get_logger(); logger.info("Handling help inquiry.")
    return random.choice(RESPONSE_TEMPLATES.get('help_inquiry', ["Tôi có thể giúp bạn về menu, giá, địa chỉ, khuyến mãi..."]))

def handle_bot_identity(entities, db_session):
    logger = get_logger(); logger.info("Handling bot identity/capability inquiry.")
    return random.choice(RESPONSE_TEMPLATES.get('bot_identity') + RESPONSE_TEMPLATES.get('bot_capability'))

def handle_generic_question(entities, db_session):
    logger = get_logger(); logger.info("Handling generic question.")
    return random.choice(RESPONSE_TEMPLATES.get('generic_question_response'))

def handle_fallback(entities, db_session):
    logger = get_logger(); logger.info("Handling fallback intent.")
    return random.choice(RESPONSE_TEMPLATES.get('fallback'))

# --- Mapping (Thêm các intent mới) ---
INTENT_HANDLERS = {
    "greeting": handle_greeting, "goodbye": handle_goodbye, "thanks": handle_thanks,
    "hours_inquiry": handle_hours_inquiry, "location_inquiry": handle_location_inquiry,
    "menu_inquiry": handle_menu_inquiry, "category_inquiry": handle_category_inquiry,
    "product_info": handle_product_info, "product_price_inquiry": handle_product_price_inquiry,
    "check_availability": handle_check_availability, "promotion_inquiry": handle_promotion_inquiry,
    "combo_inquiry": handle_suggest_combo, # Trỏ combo inquiry đến suggest luôn
    "suggest_combo": handle_suggest_combo, "wifi_inquiry": handle_wifi_inquiry,
    "payment_inquiry": handle_payment_inquiry, "order_status_inquiry": handle_order_status_inquiry,
    "order_intent": handle_order_intent, "visual_product_search": handle_visual_product_search,
    "generic_question": handle_generic_question,
    "affirmation": handle_affirmation, # <- Thêm xử lý Yes
    "negation": handle_negation,     # <- Thêm xử lý No
    "quality_inquiry": handle_quality_inquiry,
    "ambiance_inquiry": handle_ambiance_inquiry,
    "reservation_inquiry": handle_reservation_inquiry,
    "feedback_complaint": handle_feedback_complaint,
    "help_inquiry": handle_help_inquiry,
    "bot_identity": handle_bot_identity,
    "fallback": handle_fallback
}


# ===========================================
# === MAIN CHATBOT PROCESSING FUNCTION ====
# ===========================================
def generate_chatbot_response_custom(text, db_session, session_id=None):
    global conversation_context
    logger = get_logger(); start_time = datetime.now(); log_prefix=f"[SID:{session_id or 'NoSID'}]"
    logger.info(f"{log_prefix} Input: '{text[:150]}...'")
    intent=detect_intent_custom(text, db_session); entities=extract_entities_custom(text)
    entities['__original_text__'] = text
    logger.info(f"{log_prefix} Intent='{intent}', Entities={entities}")
    handler=INTENT_HANDLERS.get(intent, handle_fallback); logger.info(f"{log_prefix} Handler='{handler.__name__}'")
    response_text, image_results, success = "", [], False

    # Check and cleanup old context before handling
    if session_id and session_id in conversation_context:
        ctx_time = conversation_context[session_id].get('timestamp')
        if ctx_time and (datetime.utcnow() - ctx_time) > timedelta(minutes=5): # Context timeout: 5 mins
             logger.info(f"{log_prefix} Clearing expired conversation context.")
             conversation_context.pop(session_id, None)

    try:
        # Pass session_id to handlers that need context
        if handler in [handle_affirmation, handle_negation, handle_order_intent]:
            result = handler(entities, db_session, session_id=session_id)
        else:
            result = handler(entities, db_session)

        if isinstance(result, dict): response_text=result.get('response',''); image_results=result.get('image_results',[])
        elif isinstance(result, str): response_text = result
        else: logger.warning(f"Handler {handler.__name__} returned invalid type {type(result)}"); response_text=random.choice(RESPONSE_TEMPLATES.get('fallback')); intent='fallback'
        success = True
        # Clear context if it was just handled (affirm/negation) successfully
        if intent in ['affirmation', 'negation'] and session_id in conversation_context:
            conversation_context.pop(session_id, None)
    except Exception as e:
        logger.error(f"{log_prefix} Handler '{handler.__name__}' Execution ERROR: {e}", exc_info=True)
        response_text = random.choice(RESPONSE_TEMPLATES.get('error')); intent='error'
        if session_id: conversation_context.pop(session_id, None) # Clear context on error too

    if success and image_results and not response_text.strip():
        kws=", ".join(entities.get("visual_keywords",["bạn mô tả"]))
        response_text=random.choice(RESPONSE_TEMPLATES.get('visual_product_search_result')).format(keywords=kws)

    final_entities={k:v for k,v in entities.items() if k != '__original_text__'}
    payload = { 'success': success and intent!='error', 'response': response_text.strip(), 'intent': intent, 'entities': final_entities, 'image_results': image_results }
    proc_time=(datetime.now()-start_time).total_seconds()
    logger.info(f"{log_prefix} Resp -> Intent='{intent}', Time={proc_time:.3f}s, Text='{payload['response'][:70]}...', Images={len(payload['image_results'])}")
    return payload

# ===========================================
# === PUBLIC INTERFACE                  ===
# ===========================================
def get_custom_chatbot_response(text, db_session, session_id=None):
    logger = get_logger()
    try:
        if not RESPONSE_TEMPLATES: load_or_create_templates()
        if not RESPONSE_TEMPLATES: raise ValueError("Templates failed to load.")
        return generate_chatbot_response_custom(text, db_session, session_id)
    except Exception as e:
        logger.critical(f"CRITICAL ERROR in get_custom_chatbot_response: {e}", exc_info=True)
        return {'success': False, 'response': "Chatbot đang tạm nghỉ. Vui lòng thử lại sau.", 'intent': "error", 'entities': {}, 'image_results': []}

def handle_custom_order(text, db_session, session_id=None):
    # For now, this just triggers the normal response flow which includes confirmation
    # More complex logic could start here if needed
    return get_custom_chatbot_response(text, db_session, session_id)

def init_chatbot_custom(database_session):
    logger = get_logger(); logger.info("----- Initializing Custom Chatbot -----")
    # download_nltk_data() # Ensure NLTK data is present
    load_or_create_templates()
    logger.info("----- Custom Chatbot Ready -----")
    return True

