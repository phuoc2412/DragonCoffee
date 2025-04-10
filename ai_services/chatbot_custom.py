# /ai_services/chatbot_custom.py
import re
import random
import nltk
from nltk.tokenize import word_tokenize
from flask import current_app, url_for
from sqlalchemy import or_, func, desc, case
from models import Product, Category, Promotion, Order, OrderDetail, InventoryItem
import json
import os
import logging
from datetime import datetime, timedelta

# --- NLTK Setup ---
def download_nltk_data():
    logger = get_logger()
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        logger.info("Downloading NLTK 'punkt' data for tokenization...")
        try:
            nltk.download('punkt', quiet=True)
            logger.info("NLTK 'punkt' downloaded successfully.")
        except Exception as e:
            logger.error(f"Failed to download NLTK 'punkt' data: {e}")

# --- Logger Helper ---
def get_logger():
    if current_app:
        return current_app.logger
    else:
        logger = logging.getLogger('chatbot_custom')
        if not logger.hasHandlers():
             log_format = '%(asctime)s - %(levelname)s - CHATBOT - %(message)s'
             logging.basicConfig(level=logging.INFO, format=log_format)
             logger.info("Chatbot logger initialized outside Flask context.")
        return logger

# ===========================================
# === GLOBAL CONSTANTS & DEFINITIONS    ===
# ===========================================
INTENTS_DATA = {
    "greeting": ["xin chào", "chào", "hello", "hi", "hey", "alo"],
    "goodbye": ["tạm biệt", "bye", "goodbye", "hẹn gặp lại", "bai bai"],
    "thanks": ["cảm ơn", "cám ơn", "thank", "tks", "thanks you"],
    "menu_inquiry": ["menu", "thực đơn", "có món gì", "đồ uống", "bán gì", "món ăn", "giá cả", "xem menu", "giá", "price", "cost"],
    "category_inquiry": ["món cà phê", "món trà", "đồ ăn nhẹ", "bánh ngọt", "sinh tố", "nước ép", "đá xay", "cafe", "tea", "cake", "smoothie", "juice", "snack", "frappe"], # Intent hỏi về category cụ thể
    "hours_inquiry": ["giờ", "mấy giờ", "thời gian", "mở cửa", "đóng cửa", "khi nào mở", "làm việc"],
    "location_inquiry": ["ở đâu", "địa chỉ", "chi nhánh", "chỗ nào", "tìm quán", "đến", "store address"],
    "order_intent": ["đặt", "order", "mua", "lấy", "gọi món", "cho tôi", "cho mình", "1 ly", "2 cái", "một phần", "take", "buy"], # Bỏ số lượng cụ thể
    "product_info": ["thông tin", "về món", "như thế nào", "thành phần", "chi tiết", "details", "ingredient"], # Bỏ "giá", "ngon không"
    "product_price_inquiry": ["giá bao nhiêu", "bao nhiêu tiền", "giá", "tiền", "cost", "price"], # Intent hỏi giá riêng
    "check_availability": ["còn hàng không", "hết hàng chưa", "có bán", "có sẵn", "available"], # Intent hỏi còn hàng
    "promotion_inquiry": ["khuyến mãi", "giảm giá", "ưu đãi", "discount", "deal", "voucher", "coupon", "km"],
    "combo_inquiry": ["combo", "gói", "set", "ưu đãi cặp đôi", "đi nhóm", "ăn gì uống gì"], # Rõ ràng hơn
    "suggest_combo": ["gợi ý combo", "tư vấn combo", "nên uống gì ăn gì", "suggest combo", "recommend combo"], # Intent YÊU CẦU gợi ý
    "wifi_inquiry": ["wifi", "internet", "mạng", "pass wifi", "mật khẩu"],
    "payment_inquiry": ["thanh toán", "trả tiền", "cà thẻ", "chuyển khoản", "momo", "qr", "payment method"],
    "visual_product_search": ["ảnh", "hình", "picture", "image", "photo", "nhìn", "trông", "giống", "giống như", "show image"],
    "order_status_inquiry": ["đơn hàng của tôi", "kiểm tra đơn", "trạng thái đơn", "order status", "tình trạng đơn", "đơn đâu"],
}

ENTITY_PATTERNS = {
    "product_name_pattern": r"(?i)\b(cà phê(?: sữa| đen| trứng| muối| cốt dừa)?(?: đá)?|cafe(?: sữa| đen)?(?: đá)?|bạc xỉu|latte|espresso|cappuccino|mocha|americano|cold brew|trà(?: đào(?: cam sả)?| tắc| vải| sen| hoa cúc| ô long| sữa| xanh| đen)?|sinh tố(?: bơ| dâu| xoài)?|nước ép(?: cam| táo| dưa hấu| cà rốt| dứa| ổi)?|khoai tây chiên|bánh phô mai|bánh tiramisu|croissant|cookie|pudding|matcha(?: đá xay)?|chocolate(?: đá xay)?)\b",
    "category_name_pattern": r"(?i)\b(cà phê|cafe|trà|tea|sinh tố|smoothie|nước ép|juice|bánh|pastry|đồ ăn|snack|đá xay|frappe|đặc biệt|special)\b",
    "size": r"(?i)\b(nhỏ|vừa|lớn|size s|size m|size l|small|medium|large)\b",
    "quantity": r"(\d+)\s*(ly|cốc|cái|phần|suất|chai|cup|cups?)?",
    "price_query_kw": r"(?i)\b(giá|bao nhiêu tiền|tiền|cost|price|rate)\b",
    "availability_query_kw": r"(?i)\b(còn hàng|hết hàng|có bán|có sẵn|available)\b",
    "notes": r"(?i)\b(ít đường|nhiều đá|không đá|ít ngọt|nóng|lạnh|không sữa|thêm kem|ít kem|thêm trân châu|add boba|thêm topping|add topping|không topping|no sugar|less ice|no ice|less sweet|hot|cold|extra cream|less cream)\b",
    "visual_keyword": r"(?i)\b(trắng|đen|nâu|vàng|đỏ|xanh|hồng|cam|kem|bọt|nhiều lớp|trong suốt|sánh đặc|loãng|white|black|brown|yellow|red|green|pink|orange|cream|foam|layer|layered|clear|thick|thin)\b",
    "order_number": r"(?i)(?:order|đơn hàng|mã đơn|số đơn)\s*[:#\-]?\s*([OoRrDd]{3}[-\s]?\d{10,14}[-\s]?\w{4})\b",
    "order_number_simple": r"(?i)(?:đơn|mã|order)\s+#?(\d{5,})\b",
    "combo_keyword": r"(?i)\b(combo|gói|set)\b"
}

RESPONSE_TEMPLATES = {}
TEMPLATES_FILE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'chatbot_responses.json')

def create_default_templates():
    """Creates default templates dictionary with all necessary keys."""
    logger = get_logger()
    logger.info("Creating default chatbot response templates structure.")
    return {
        "greeting": ["Xin chào! Tôi là Dragon Bot, tôi có thể giúp gì?", "Chào bạn! Bạn cần hỗ trợ về vấn đề gì hôm nay?"],
        "goodbye": ["Cảm ơn bạn đã liên hệ. Chúc bạn một ngày tốt lành!", "Tạm biệt, hẹn gặp lại bạn!"],
        "thanks": ["Rất vui được giúp đỡ bạn!", "Không có gì đâu ạ!"],
        "hours_inquiry": ["Quán mở cửa từ 7:00 sáng đến 10:00 tối các ngày trong tuần và 8:00 sáng đến 11:00 tối cuối tuần."],
        "menu_inquiry": ["Bạn có thể xem menu đầy đủ trên <a href='{menu_url}' target='_blank'>trang Thực Đơn</a> nhé. Bạn quan tâm món cụ thể nào không ạ?", "Menu có nhiều loại cà phê, trà, bánh và đồ ăn nhẹ. Xem chi tiết tại <a href='{menu_url}' target='_blank'>đây</a> nha."],
        "category_inquiry_result": ["Trong danh mục '{category_name}' có các món nổi bật như: {product_list}. Bạn xem thêm tại {menu_url} nhé.", "Một vài món ngon trong nhóm '{category_name}': {product_list}. Bạn thích món nào?"],
        "category_not_found": ["Xin lỗi, tôi không tìm thấy danh mục '{category_name}'."],
        "location_inquiry": ["Bạn xem địa chỉ các chi nhánh tại {locations_url} ạ.", "Tìm chi nhánh gần bạn nhất tại {locations_url} nha."],
        "order_intent": ["Bạn muốn đặt món '{product}' phải không ạ? Bạn chọn size và số lượng giúp tôi nhé.", "Ok bạn. Cho tôi biết size và số lượng của '{product}' bạn muốn đặt?"],
        # Có thể dùng key chung hoặc tách bạch như cũ
        "product_info": ["Món '{product}' ({category}) có giá {price}. {description}. Hiện tại món này {availability}.", "'{product}' giá {price}, là món {category}. {description} Hiện món này {availability}."],
        "product_info_no_price": ["Thông tin món '{product}' ({category}): {description} Hiện tại món này {availability}. Bạn muốn biết giá không?", "'{product}' là món {category}, mô tả: {description}. Hiện tại {availability}."],
        "product_not_found": ["Xin lỗi, tôi chưa tìm thấy thông tin món '{product}'.", "Hmm, tên món '{product}' có vẻ chưa đúng."],
        "product_price_inquiry_result": ["Dạ, món '{product_name}' có giá {price_str} ạ.", "Giá của '{product_name}' là {price_str} nhé."],
        "check_availability_result": ["Món '{product_name}' hiện đang {status} ạ.", "Dạ, '{product_name}' {status}."],
        "check_availability_not_found": ["Tôi chưa tìm thấy món '{product_name}' để kiểm tra ạ."],
        "promotion_inquiry": ["Các khuyến mãi hiện có:\n{promotion_list}Xem chi tiết tại {promotions_url}", "Hiện đang có ưu đãi:\n{promotion_list}Bạn xem thêm tại {promotions_url}"],
        "promotion_inquiry_none": ["Hiện tại quán chưa có chương trình khuyến mãi đặc biệt nào. Bạn theo dõi page nhé!", "Xin lỗi, hôm nay chưa có ưu đãi nào."],
        "combo_inquiry": ["Quán có các combo [Combo 1], [Combo 2], bạn tham khảo nhé.", "Hiện có các combo tiết kiệm: [Combo 1], [Combo 2]."],
        "suggest_combo_result": ["Bạn thử combo '{combo_name}' xem sao? Gồm có: {combo_items}. Giá khoảng {combo_price}.", "Nếu bạn thích {preference}, combo '{combo_name}' ({combo_items}) giá {combo_price} khá hợp lý đó."],
        "suggest_combo_no_pref": ["Bạn thích uống/ăn kèm món gì hoặc thể loại nào không để tôi gợi ý?", "Quán có nhiều combo. Bạn cho tôi biết sở thích (cà phê/trà/bánh...) để tôi tư vấn nha?"],
        "wifi_inquiry": ["Dạ, quán có wifi miễn phí, pass là `dragoncoffee` hoặc hỏi nhân viên nhé."],
        "payment_inquiry": ["Bạn có thể thanh toán bằng tiền mặt, thẻ, Momo, ZaloPay, VNPay, hoặc chuyển khoản."],
        # ----- CÁC KEY CẦN THÊM / KIỂM TRA LẠI -----
        "visual_product_search_result": [
            "Dựa vào mô tả '{keywords}', tôi thấy có mấy món này:",
            "Đây là một vài hình ảnh món '{keywords}' bạn có thể thích:",
            "Tìm thấy kết quả cho '{keywords}':"
        ],
        "visual_product_search_notfound": [
            "Xin lỗi, tôi chưa tìm được món nào trông giống '{keywords}' cả. Bạn thử mô tả khác xem sao?",
            "Hmm, tôi không thấy món nào khớp với '{keywords}'. Bạn tìm món khác nhé?"
        ],
        "visual_product_search_nokeywords": [
            "Bạn muốn tôi tìm ảnh món trông như thế nào vậy?",
            "Hãy mô tả món bạn muốn xem ảnh nhé (màu sắc, hình dáng...)."],
        "order_confirmation_request": [
            "Xác nhận đặt: {quantity} ly '{product}' (size {size}){notes}. Tạm tính: {price}. Đúng chưa ạ?",
            "Ok, {quantity} '{product}' size {size}{notes}. Giá khoảng {price}. Bạn đồng ý đặt hàng chứ?"
        ],
        "order_success": ["Đặt hàng thành công! Mã đơn hàng của bạn là #{order_number}.", "Okie, đơn hàng #{order_number} đã được tạo."],
        "order_failed": ["Xin lỗi, không thể tạo đơn. Có thể do thiếu thông tin hoặc lỗi hệ thống.", "Tạo đơn hàng thất bại. Vui lòng kiểm tra lại thông tin hoặc thử lại sau."],
        "order_status_found": ["Đơn hàng #{order_number} (ngày {order_date}) có trạng thái: **{status_display}**. {details}"],
        "order_status_not_found": ["Không tìm thấy đơn hàng với mã: {order_number}. Bạn kiểm tra lại mã nhé.", "Mã đơn {order_number} không đúng hoặc không tồn tại."],
        "order_status_ask_number": ["Bạn vui lòng cung cấp mã đơn hàng (VD: ORD-...) để tôi kiểm tra nhé.", "Cho tôi xin mã đơn hàng ạ?"],
        "error": [  # <-- KEY BỊ THIẾU
            "Xin lỗi, tôi đang gặp lỗi kỹ thuật. Bạn vui lòng thử lại sau giây lát nhé.",
            "Hệ thống chatbot đang có chút vấn đề, mong bạn thông cảm và thử lại sau.",
            "Rất tiếc, tôi không thể xử lý yêu cầu của bạn lúc này."
        ],
        "fallback": ["Xin lỗi, tôi chưa hiểu rõ lắm. Bạn có thể hỏi về menu, địa chỉ, giờ mở cửa, khuyến mãi?", "Tôi đang học hỏi. Bạn có thể nói rõ hơn yêu cầu được không ạ?"]
        # ---------------------------------------------
    }

def load_or_create_templates():
    global RESPONSE_TEMPLATES
    logger = get_logger()
    # ... (Giữ nguyên logic load/create file JSON) ...
    try:
        if os.path.exists(TEMPLATES_FILE_PATH):
            with open(TEMPLATES_FILE_PATH, 'r', encoding='utf-8') as f:
                RESPONSE_TEMPLATES = json.load(f)
                logger.info(f"Successfully loaded response templates from {TEMPLATES_FILE_PATH}")
        else:
            logger.warning(f"Response templates file not found: {TEMPLATES_FILE_PATH}. Creating defaults.")
            RESPONSE_TEMPLATES = create_default_templates()
            try:
                with open(TEMPLATES_FILE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(RESPONSE_TEMPLATES, f, ensure_ascii=False, indent=4)
                logger.info(f"Saved default templates to {TEMPLATES_FILE_PATH}")
            except Exception as save_e: logger.error(f"Could not save default templates: {save_e}")
    except Exception as e:
        logger.error(f"Critical error loading/creating templates: {e}. Using basic defaults.", exc_info=True)
        RESPONSE_TEMPLATES = {"fallback": ["Lỗi chatbot."], "greeting": ["Xin chào!"]} # Ít nhất phải có fallback và greeting


# Load templates on module import
load_or_create_templates()


# ===========================================
# === CORE NLP/PROCESSING FUNCTIONS     ===
# ===========================================
def preprocess_text(text):
    # ... (Giữ nguyên) ...
    logger = get_logger()
    try:
        if not text or not isinstance(text, str): return []
        text_lower = text.lower()
        tokens = text_lower.split()
        tokens = [word for word in tokens if re.match("^[a-z0-9àáãạảăắằẳẵặâấầẩẫậèéẹẻẽêềếểễệđìíỉĩịòóõọỏôốồổỗộơớờởỡợùúũụủưứừửữựỳýỷỹỵ]+$", word)]
        return tokens
    except Exception as e:
        logger.error(f"Error preprocessing text: '{text[:50]}...': {e}", exc_info=False)
        return []

def extract_entities_custom(text):
    # ... (Giữ nguyên logic extract entities) ...
    logger = get_logger()
    entities = {}
    if not text or not isinstance(text, str): return entities
    text_lower = text.lower()
    processed_indices = set()
    patterns_ordered = sorted(ENTITY_PATTERNS.items(), key=lambda item: len(item[1]), reverse=True)

    for entity_type, pattern in patterns_ordered:
        try:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                start, end = match.span()
                is_overlapped = any(max(start, p_start) < min(end, p_end) for p_start, p_end in processed_indices)
                if is_overlapped: continue
                entity_value = match.group(0)
                # --- Specific Entity Handling ---
                if entity_type == 'product_name_pattern': entities.setdefault("product", []).append(entity_value.lower())
                elif entity_type == 'category_name_pattern':
                    is_product_subspan = any(start >= p_start and end <= p_end for p_start, p_end in processed_indices if p_start!=start or p_end!=end )
                    if "product" not in entities and not is_product_subspan : entities.setdefault("category", []).append(entity_value.lower())
                elif entity_type == 'quantity':
                    num_match = re.search(r'\d+', entity_value);
                    if num_match: entities[entity_type] = int(num_match.group(0))
                elif entity_type == 'notes': entities.setdefault(entity_type, []).append(entity_value.lower())
                elif entity_type == 'order_number': entities[entity_type] = match.group(1).upper().replace("-", "").replace(" ","")
                elif entity_type == 'order_number_simple':
                     if any(kw in text_lower for kw in ["đơn", "mã", "số", "order"]): entities[entity_type] = match.group(1)
                elif entity_type.endswith('_kw'): entities[entity_type.replace('_kw', '')] = True
                elif entity_type not in entities: entities[entity_type] = entity_value.lower()
                processed_indices.add((start, end))
        except Exception as regex_e: logger.error(f"Regex error for {entity_type} pattern '{pattern}': {regex_e}")

    if "product" in entities: entities["product"] = list(set(entities["product"]))
    if "category" in entities: entities["category"] = list(set(entities["category"]))
    if "notes" in entities: entities["notes"] = list(set(entities["notes"]))
    logger.info(f"Final Extracted Entities: {entities}")
    return entities


def detect_intent_custom(text, db_session):
    # ... (Giữ nguyên logic detect_intent đã sửa) ...
    logger = get_logger()
    if not text or not isinstance(text, str): return 'fallback'
    entities = extract_entities_custom(text)
    text_lower = text.lower()
    processed_tokens = preprocess_text(text_lower)

    # --- Rule-based ---
    if entities.get("order_number") or entities.get("order_number_simple") or any(kw in processed_tokens for kw in INTENTS_DATA.get('order_status_inquiry',[])):
        if not any(kw in processed_tokens for kw in INTENTS_DATA.get('order_intent',[])): return "order_status_inquiry"
    if "product" in entities and (any(kw in processed_tokens for kw in INTENTS_DATA.get('order_intent',[])) or "quantity" in entities): return "order_intent"
    if "product" in entities and entities.get("availability"): return "check_availability"
    if "product" in entities and (any(kw in text_lower for kw in INTENTS_DATA.get('product_info',[])) or entities.get('price_query')):
        if entities.get('price_query') or any(kw in text_lower for kw in ['giá', 'tiền', 'price', 'cost']): return "product_price_inquiry"
        else: return "product_info"
    if "category" in entities and "product" not in entities:
        if not any(kw in text_lower for kw in ['menu', 'thực đơn']): return "category_inquiry"
    if any(kw in text_lower for kw in INTENTS_DATA.get('suggest_combo',[])): return "suggest_combo"
    if any(kw in text_lower for kw in INTENTS_DATA.get('visual_product_search',[])):
         exclude_kws = INTENTS_DATA.get('menu_inquiry',[]) + INTENTS_DATA.get('location_inquiry',[]) + \
                       INTENTS_DATA.get('hours_inquiry',[]) + INTENTS_DATA.get('order_status_inquiry',[]) + \
                       INTENTS_DATA.get('promotion_inquiry',[]) + INTENTS_DATA.get('order_intent', []) + ['giá', 'tiền']
         if not any(kw in text_lower for kw in exclude_kws): return 'visual_product_search'

    # --- Keyword Scoring ---
    scores = {intent: 0.0 for intent in INTENTS_DATA}
    max_score = 0.0; matched_intent = 'fallback'
    for intent, keywords in INTENTS_DATA.items():
        score = 0.0; weight = 1.0
        if intent in ["wifi_inquiry", "payment_inquiry", "combo_inquiry"]: weight = 1.2
        for phrase in keywords:
            if len(phrase.split()) > 1 and phrase in text_lower: score += 1.5 * len(phrase.split()) * weight
            elif phrase in processed_tokens: score += 1.0 * weight
        scores[intent] = score
        if score > max_score: max_score = score; matched_intent = intent

    keyword_threshold = 1.5
    if max_score >= keyword_threshold:
        logger.info(f"Intent detected (Keyword Score): '{matched_intent}' (Score: {max_score:.2f})")
        if matched_intent == 'product_info' and 'product' not in entities:
             logger.info("Refining 'product_info' to 'menu_inquiry' (no product entity).")
             return 'menu_inquiry'
        # NEW: Refine menu_inquiry to product_price_inquiry if price keyword is present
        if matched_intent == 'menu_inquiry' and entities.get('price_query'):
            logger.info("Refining 'menu_inquiry' to 'product_price_inquiry' due to price keyword.")
            return 'product_price_inquiry'
        return matched_intent
    else:
        logger.info(f"Keyword scores below threshold. Intent: fallback. Max score: {max_score:.2f} for '{matched_intent}'")
        return "fallback"


# --- Search Products Helper ---
def search_products_by_visual_keywords(keywords, db_session, limit=3):
    # ... (Giữ nguyên) ...
    logger = get_logger()
    if not keywords: return []
    logger.info(f"DB Searching visual keywords: {keywords}")
    search_conditions = [Product.name.ilike(f"%{kw}%") for kw in keywords] + \
                        [Product.description.ilike(f"%{kw}%") for kw in keywords]
    try:
        query = db_session.query(Product)\
                        .filter(Product.is_available == True)\
                        .filter(or_(*search_conditions))
        results = query.limit(limit * 5).all()
        def relevance_score(p, kws): # noqa: E731
            s = 0; n = p.name.lower(); d = (p.description or "").lower()
            for kw in kws: s += 2 if kw in n else (1 if kw in d else 0)
            return s
        results.sort(key=lambda p: relevance_score(p, keywords), reverse=True)
        results = results[:limit]
        formatted = []
        url_context = current_app.app_context() if current_app else None
        if url_context: url_context.push() # Push context if available
        for p in results:
            try:
                img = p.image_url or (url_for('static', filename='images/default_product.png') if current_app else None)
                url = url_for('main.product_detail', product_id=p.id) if current_app else f"/product/{p.id}"
                formatted.append({"id": p.id, "name": p.name, "image_url": img, "product_url": url})
            except Exception as e_url: logger.error(f"Error gen URL for product {p.id}: {e_url}")
        if url_context: url_context.pop() # Pop context
        logger.info(f"DB Found {len(formatted)} visual results.")
        return formatted
    except Exception as e: logger.error(f"DB Error visual keywords search: {e}", exc_info=True); return []

# ===========================================
# === ACTION HANDLERS DEFINITIONS =======
# ===========================================
# *** Định nghĩa TẤT CẢ các hàm handle_...() Ở ĐÂY ***

def handle_greeting(entities, db_session): return random.choice(RESPONSE_TEMPLATES.get('greeting', ["Xin chào!"]))
def handle_goodbye(entities, db_session): return random.choice(RESPONSE_TEMPLATES.get('goodbye', ["Tạm biệt!"]))
def handle_thanks(entities, db_session): return random.choice(RESPONSE_TEMPLATES.get('thanks', ["Không có gì."]))
def handle_hours_inquiry(entities, db_session): return random.choice(RESPONSE_TEMPLATES.get('hours_inquiry', ["Mở 7h-22h T2-6, 8h-23h T7-CN."]))
def handle_wifi_inquiry(entities, db_session): return random.choice(RESPONSE_TEMPLATES.get('wifi_inquiry', ["Có Wifi ạ, pass hỏi nhân viên nhé."]))
def handle_payment_inquiry(entities, db_session): return random.choice(RESPONSE_TEMPLATES.get('payment_inquiry', ["Nhận tiền mặt, thẻ, ví điện tử."]))

def handle_location_inquiry(entities, db_session):
    logger = get_logger()
    templates = RESPONSE_TEMPLATES.get('location_inquiry', ["Xem địa chỉ tại {locations_url}."])
    resp = random.choice(templates); url = "#"
    if current_app:
        try:
            with current_app.app_context(): url = url_for('main.locations', _external=True)
        except: pass
    return resp.format(locations_url=f"<a href='{url}' target='_blank'>trang Địa điểm</a>")

def handle_menu_inquiry(entities, db_session):
    logger = get_logger(); logger.info("Handling menu_inquiry (general)")
    try:
        cats = db_session.query(Category.name).order_by(Category.name).limit(5).all()
        pros = db_session.query(Product.name).filter(Product.is_available == True).order_by(Product.is_featured.desc(), func.random()).limit(3).all()
        resp = "Menu gồm: " + ", ".join([c.name for c in cats]) + ",..."
        if pros: resp += f" Món ngon: {', '.join([p.name for p in pros])}. "
        url, link = "#", "trang Menu"
        if current_app:
            try:
                with current_app.app_context(): url = url_for('main.menu', _external=True); link=f"<a href='{url}' target='_blank'>{link}</a>"
            except: pass
        return resp + f"Xem đầy đủ tại {link}!"
    except Exception as e: logger.error(f"Err menu sum: {e}"); url, link = "#", "trang Menu"; # Fallback logic
    if current_app:
        try:
            with current_app.app_context(): url = url_for('main.menu', _external=True); link=f"<a href='{url}' target='_blank'>{link}</a>"
        except: pass
    return random.choice(RESPONSE_TEMPLATES['menu_inquiry']).format(menu_url=link)

def handle_category_inquiry(entities, db_session):
    logger = get_logger()
    cat_names = entities.get("category", []);
    if not cat_names: return "Hỏi về nhóm món nào ạ?"
    target_cat = cat_names[0]
    logger.info(f"Handling cat inquiry: '{target_cat}'")
    try:
        cat = db_session.query(Category).filter(func.lower(Category.name) == func.lower(target_cat)).first() \
               or db_session.query(Category).filter(Category.name.ilike(f"%{target_cat}%")).first()
        if cat:
            pros = db_session.query(Product.name).filter(Product.category_id == cat.id, Product.is_available == True).order_by(Product.is_featured.desc(), func.random()).limit(5).all()
            if pros:
                p_list = ", ".join([p.name for p in pros]); url, link = "#", ""
                if current_app:
                     try:
                         with current_app.app_context(): url=url_for('main.menu', category=cat.id, _external=True); link=f"<a href='{url}'> Xem thêm</a>"
                     except: pass
                tmpl = random.choice(RESPONSE_TEMPLATES.get('category_inquiry_result'))
                return tmpl.format(category_name=cat.name, product_list=p_list) + link
            else: return f"Nhóm '{cat.name}' đang cập nhật."
        else: return random.choice(RESPONSE_TEMPLATES['category_not_found']).format(category_name=target_cat)
    except Exception as e: logger.error(f"Err cat inquiry '{target_cat}': {e}"); return "Lỗi xem nhóm món."

def handle_product_info(entities, db_session):
    logger = get_logger(); p_names = entities.get("product", []);
    if not p_names: return "Bạn hỏi thông tin món nào?"
    t_name = p_names[0]
    try:
        prod = db_session.query(Product).options(db.joinedload(Product.inventory)).filter(func.lower(Product.name) == func.lower(t_name)).first() \
               or db_session.query(Product).options(db.joinedload(Product.inventory)).filter(Product.name.ilike(f"%{t_name}%")).first()
        if prod:
            avail = prod.is_available and (not prod.inventory or prod.inventory.quantity > 0)
            a_text = "còn hàng" if avail else "tạm hết"
            desc = prod.description or "Món signature của quán."
            cat_name = prod.category.name if prod.category else "Đặc biệt"
            # Không trả giá ở đây
            tmpl = random.choice(RESPONSE_TEMPLATES.get('product_info_no_price', ["'{product}' ({category}): {description} Hiện tại {availability}.", "Đây là thông tin món '{product}': {description} ({availability})"])) # Cần thêm key này vào templates
            return tmpl.format(product=prod.name, category=cat_name, description=desc, availability=a_text) + " Bạn muốn biết giá hay đặt luôn không?"
        else: return random.choice(RESPONSE_TEMPLATES["product_not_found"]).format(product=t_name)
    except Exception as e: logger.error(f"Err info '{t_name}': {e}"); return "Lỗi tra cứu SP."

def handle_product_price_inquiry(entities, db_session):
    logger = get_logger(); p_names = entities.get("product", []);
    if not p_names: return "Bạn hỏi giá món nào?"
    t_name = p_names[0]
    try:
        prod = db_session.query(Product.name, Product.price).filter(func.lower(Product.name) == func.lower(t_name)).first() \
               or db_session.query(Product.name, Product.price).filter(Product.name.ilike(f"%{t_name}%")).first()
        if prod and prod.price is not None:
             p_str = f"{int(prod.price):,}đ"; tmpl = random.choice(RESPONSE_TEMPLATES['product_price_inquiry_result'])
             return tmpl.format(product_name=prod.name, price_str=p_str)
        elif prod: return f"Món '{prod.name}' giá liên hệ ạ."
        else: return random.choice(RESPONSE_TEMPLATES["product_not_found"]).format(product=t_name)
    except Exception as e: logger.error(f"Err price '{t_name}': {e}"); return "Lỗi tra giá."

def handle_check_availability(entities, db_session):
    # ... (Giữ nguyên logic) ...
    logger = get_logger(); p_names = entities.get("product", []);
    if not p_names: return "Bạn kiểm tra món nào còn hàng?"
    t_name = p_names[0]; logger.info(f"Checking avail for: '{t_name}'")
    try:
        prod = db_session.query(Product.id, Product.name, Product.is_available).filter(func.lower(Product.name) == func.lower(t_name)).first() \
               or db_session.query(Product.id, Product.name, Product.is_available).filter(Product.name.ilike(f"%{t_name}%")).first()
        if prod:
            inv_qty = db_session.query(InventoryItem.quantity).filter(InventoryItem.product_id == prod.id).scalar()
            is_avail = prod.is_available and (inv_qty is None or inv_qty > 0)
            stat = "còn hàng" if is_avail else "đang tạm hết"
            tmpl = random.choice(RESPONSE_TEMPLATES["check_availability_result"])
            return tmpl.format(product_name=prod.name, status=stat)
        else: return random.choice(RESPONSE_TEMPLATES['check_availability_not_found']).format(product_name=t_name) # Thêm template này
    except Exception as e: logger.error(f"Err avail '{t_name}': {e}"); return "Lỗi kiểm tra món."


def handle_promotion_inquiry(entities, db_session):
    # ... (Giữ nguyên logic) ...
    logger = get_logger(); logger.info("Handling promotion inquiry")
    try:
        now = datetime.utcnow()
        promos = db_session.query(Promotion).filter(
            Promotion.is_active == True, Promotion.start_date <= now, Promotion.end_date >= now
        ).order_by(Promotion.end_date.asc()).limit(3).all()
        if not promos: return random.choice(RESPONSE_TEMPLATES['promotion_inquiry_none'])
        else:
            p_texts = [];
            for p in promos:
                t = f"**{p.name}**";
                if p.discount_percent: t += f" (Giảm {p.discount_percent}%)"
                elif p.discount_amount: t += f" (Giảm {int(p.discount_amount):,}đ)"
                t += f" - {p.description or ''}. Đến {p.end_date.strftime('%d/%m')}"; p_texts.append(t)
            p_list_str = "\n- ".join(p_texts); tmpl = random.choice(RESPONSE_TEMPLATES['promotion_inquiry'])
            url, link = "#", ""
            if current_app:
                try:
                     with current_app.app_context(): url = url_for('main.promotions', _external=True); link = f"<a href='{url}'>trang KM</a>"
                except: pass
            return tmpl.format(promotion_list=p_list_str, promotions_url=link).strip()
    except Exception as e: logger.error(f"DB Err promos: {e}"); return "Lỗi xem KM."


def handle_suggest_combo(entities, db_session):
    # ... (Giữ nguyên logic) ...
    logger = get_logger(); logger.info("Handling suggest combo"); pref = entities.get("product", [None])[0]
    try:
        # Đơn giản: gợi ý combo ảo
        drinks = db_session.query(Product.name, Product.price).join(Category).filter(Category.name.in_(['Cà phê', 'Trà']), Product.is_available==True).order_by(func.random()).limit(1).all()
        foods = db_session.query(Product.name, Product.price).join(Category).filter(Category.name.in_(['Bánh ngọt']), Product.is_available==True).order_by(func.random()).limit(1).all()
        if drinks and foods:
            name=f"Combo Ngày Mới"; items=f"{drinks[0].name} và {foods[0].name}"
            price_v = sum(p.price for p in drinks+foods if p.price)*0.9; price_s=f"~{int(price_v):,}đ"
            tmpl = random.choice(RESPONSE_TEMPLATES['suggest_combo_result'])
            return tmpl.format(combo_name=name, combo_items=items, combo_price=price_s, preference="")
        else: return random.choice(RESPONSE_TEMPLATES['suggest_combo_no_pref'])
    except Exception as e: logger.error(f"Err suggest combo: {e}"); return random.choice(RESPONSE_TEMPLATES['suggest_combo_no_pref'])

def handle_order_status_inquiry(entities, db_session):
    # ... (Giữ nguyên logic) ...
    logger = get_logger(); num_full=entities.get("order_number"); num_simp=entities.get("order_number_simple"); uid=None
    lookup = num_full
    if not lookup and num_simp:
        try:
            q = db_session.query(Order).filter(or_(Order.id==int(num_simp), Order.order_number.like(f"%{num_simp}%")))
            if uid: q=q.filter(Order.user_id==uid)
            poss = q.order_by(desc(Order.created_at)).limit(2).all()
            if len(poss)==1: lookup=poss[0].order_number
            elif len(poss)>1: return "Tìm thấy nhiều đơn. Vui lòng nhập mã đầy đủ."
        except: pass

    if not lookup:
        if uid: last=db_session.query(Order).filter(Order.user_id==uid).order_by(desc(Order.created_at)).first();
        if last: return f"Đơn gần nhất #{last.order_number}. Bạn hỏi đơn này?"
        return random.choice(RESPONSE_TEMPLATES['order_status_ask_number'])

    logger.info(f"Querying status for: '{lookup}'");
    try:
        order = db_session.query(Order).filter(Order.order_number==lookup).first()
        if order:
            if uid and order.user_id!=uid: return "Không thể xem đơn này."
            stat = order.get_status_display(); tmpl=random.choice(RESPONSE_TEMPLATES['order_status_found']); det=""
            # Add details logic
            resp = tmpl.format(order_number=order.order_number, order_date=order.created_at.strftime('%d/%m'), status_display=stat, details=det)
            # Add link logic
            return resp
        else: return random.choice(RESPONSE_TEMPLATES['order_status_not_found']).format(order_number=lookup)
    except Exception as e: logger.error(f"Err query order '{lookup}': {e}"); return "Lỗi kiểm tra đơn."


def handle_visual_product_search(entities, db_session):
    # ... (Giữ nguyên logic) ...
    logger=get_logger(); orig_text=entities.get('__original_text__',''); tokens=preprocess_text(orig_text)
    vt=INTENTS_DATA['visual_product_search']; gs=['cho','tôi','xem','tìm','hình','ảnh','với','có','là','của']
    kws=[w for w in tokens if w not in vt and w not in gs and len(w)>2][:5]
    if not kws: return {'response': random.choice(RESPONSE_TEMPLATES["visual_product_search_nokeywords"]), 'image_results': []}
    logger.info(f"Handling visual search for: {kws}"); prods=search_products_by_visual_keywords(kws,db_session)
    kw_str=" ".join(kws)
    if prods: tmpl=random.choice(RESPONSE_TEMPLATES["visual_product_search_result"]); return {'response':tmpl.format(keywords=kw_str), 'image_results':prods}
    else: tmpl=random.choice(RESPONSE_TEMPLATES["visual_product_search_notfound"]); return {'response':tmpl.format(keywords=kw_str), 'image_results':[]}

def handle_order_intent(entities, db_session):
    logger=get_logger(); p_names=entities.get("product")
    if p_names: logger.info(f"Handling order_intent for {p_names[0]}"); return handle_order_confirmation_request(entities,db_session)
    else: return "Bạn muốn đặt món nào ạ?"

def handle_order_confirmation_request(entities, db_session):
    logger = get_logger(); p_names = entities.get("product", ["món bạn chọn"]); name = p_names[0].title()
    qty=entities.get("quantity",1); size=entities.get("size","vừa"); notes=f" ({', '.join(entities.get('notes',[]))})" if entities.get('notes') else ""
    price="?";
    try: # Get price estimate
        p_price=db_session.query(Product.price).filter(func.lower(Product.name)==func.lower(p_names[0])).scalar() or db_session.query(Product.price).filter(Product.name.ilike(f"%{p_names[0]}%")).scalar()
        if p_price: price=f"~{int(p_price*qty):,}đ"
    except Exception as e: logger.error(f"Err price confirm: {e}")
    tmpl=random.choice(RESPONSE_TEMPLATES['order_confirmation_request'])
    return tmpl.format(quantity=qty,product=name,size=size,notes=notes,price=price)

def handle_combo_inquiry(entities, db_session):
    logger=get_logger(); logger.info("Handling combo inquiry");
    return handle_suggest_combo(entities,db_session) # Delegate

def handle_fallback(entities, db_session):
    return random.choice(RESPONSE_TEMPLATES.get('fallback', ["Xin lỗi, tôi chưa rõ lắm."]))

# === Intent to Handler Mapping ===
INTENT_HANDLERS = {
    "greeting": handle_greeting,
    "goodbye": handle_goodbye,
    "thanks": handle_thanks,
    "hours_inquiry": handle_hours_inquiry,
    "location_inquiry": handle_location_inquiry,
    "menu_inquiry": handle_menu_inquiry,
    "category_inquiry": handle_category_inquiry,
    "product_info": handle_product_info,
    "product_price_inquiry": handle_product_price_inquiry,
    "check_availability": handle_check_availability,
    "promotion_inquiry": handle_promotion_inquiry,
    "combo_inquiry": handle_combo_inquiry,
    "suggest_combo": handle_suggest_combo,
    "wifi_inquiry": handle_wifi_inquiry,
    "payment_inquiry": handle_payment_inquiry,
    "order_status_inquiry": handle_order_status_inquiry,
    "order_intent": handle_order_intent,
    "visual_product_search": handle_visual_product_search,
    "fallback": handle_fallback
}

# ===========================================
# === MAIN CHATBOT PROCESSING FUNCTION ====
# ===========================================
def generate_chatbot_response_custom(text, db_session, session_id=None):
    # ... (Giữ nguyên logic gọi handler và xử lý kết quả như phiên bản trước) ...
    logger = get_logger(); start_time = datetime.now()
    logger.info(f"[Chatbot Req ID:{session_id or 'N/A'}] Input: '{text[:150]}...'")
    intent = detect_intent_custom(text, db_session); entities = extract_entities_custom(text)
    entities['__original_text__'] = text; handler = INTENT_HANDLERS.get(intent, handle_fallback)
    logger.info(f"[Chatbot Processing ID:{session_id or 'N/A'}] Intent: {intent}, Handler: {handler.__name__}")
    resp_txt, img_res, ok = "", [], False
    try:
        res = handler(entities, db_session)
        if isinstance(res, dict): resp_txt=res.get('response',''); img_res=res.get('image_results',[])
        elif isinstance(res, str): resp_txt = res
        else: logger.warning(f"Handler {handler.__name__} ret invalid type {type(res)}"); resp_txt=random.choice(RESPONSE_TEMPLATES['fallback']); intent='fallback'
        ok = True
    except Exception as e: logger.error(f"Err exec handler '{handler.__name__}' for '{intent}': {e}", exc_info=True); resp_txt=random.choice(RESPONSE_TEMPLATES['error']); intent='error'
    if ok and img_res and not resp_txt: # Default text for image results
        kws="bạn mô tả"; resp_txt = random.choice(RESPONSE_TEMPLATES['visual_product_search_result']).format(keywords=kws)
    final_entities = {k:v for k,v in entities.items() if k != '__original_text__'}
    payload = {'response': resp_txt, 'intent': intent, 'entities': final_entities, 'image_results': img_res}
    proc_time = (datetime.now()-start_time).total_seconds()
    logger.info(f"[Chatbot Resp ID:{session_id or 'N/A'}] Intent='{intent}', Time={proc_time:.3f}s, Resp='{resp_txt[:50]}...', Images={len(img_res)}")
    return payload


# ===========================================
# === PUBLIC INTERFACE FUNCTIONS ========
# ===========================================
def get_custom_chatbot_response(text, db_session, session_id=None):
    # ... (Giữ nguyên logic, đảm bảo gọi generate_chatbot_response_custom) ...
    logger = get_logger()
    try:
         if not RESPONSE_TEMPLATES: load_or_create_templates()
         if not RESPONSE_TEMPLATES: raise ValueError("Templates failed to load.")
         return generate_chatbot_response_custom(text, db_session, session_id)
    except Exception as e:
        logger.critical(f"CRITICAL error get_custom_chatbot_response: {e}", exc_info=True)
        return {'response': "Chatbot đang tạm nghỉ.", 'intent': "error", 'entities': {}, 'image_results': []}

def handle_custom_order(text, db_session, session_id=None):
    # ... (Giữ nguyên) ...
    logger = get_logger(); logger.info(f"Handling order (basic): '{text[:50]}...'")
    return get_custom_chatbot_response(text, db_session, session_id)

def init_chatbot_custom(database):
    # ... (Giữ nguyên) ...
    logger = get_logger(); logger.info("----- Init Custom Chatbot -----")
    # download_nltk_data()
    load_or_create_templates()
    logger.info("----- Custom Chatbot Ready -----")
    return True