from sklearn.feature_extraction import DictVectorizer
from sklearn.svm import SVC
import nltk
from nltk.classify import NaiveBayesClassifier
from nltk.corpus import stopwords
import random

# --- Dữ liệu Huấn luyện (Training Data) Mẫu Mở Rộng ---
# (Đây chỉ là dữ liệu MẪU, để chatbot hoạt động. Dữ liệu thực tế cần phong phú và chính xác hơn)
training_data = [
    # Intent: greeting
    ({"words": "chào bạn"}, "greeting"),
    ({"words": "xin chào"}, "greeting"),
    ({"words": "hello"}, "greeting"),
    ({"words": "hi"}, "greeting"),
    ({"words": "hey"}, "greeting"),
    ({"words": "chào quán"}, "greeting"),
    ({"words": "khỏe không"}, "greeting"),

    # Intent: menu_inquiry
    ({"words": "menu của quán đâu"}, "menu_inquiry"),
    ({"words": "cho xem thực đơn"}, "menu_inquiry"),
    ({"words": "quán có món gì"}, "menu_inquiry"),
    ({"words": "đồ uống của quán"}, "menu_inquiry"),
    ({"words": "xem menu"}, "menu_inquiry"),
    ({"words": "thực đơn"}, "menu_inquiry"),
    ({"words": "menu"}, "menu_inquiry"),
    ({"words": "bảng giá"}, "menu_inquiry"),

    # Intent: product_info (ví dụ: cà phê đen đá)
    ({"words": "cà phê đen đá là gì"}, "product_info_capheden_da"),
    ({"words": "thành phần cà phê đen đá"}, "product_info_capheden_da"),
    ({"words": "cách làm cà phê đen đá"}, "product_info_capheden_da"),
    ({"words": "giới thiệu cà phê đen đá"}, "product_info_capheden_da"),
    ({"words": "mô tả cà phê đen đá"}, "product_info_capheden_da"),

    # Intent: product_info (ví dụ: trà đào)
    ({"words": "trà đào là gì"}, "product_info_tradao"),
    ({"words": "trà đào có ngon không"}, "product_info_tradao"),
    ({"words": "thành phần trà đào"}, "product_info_tradao"),
    ({"words": "về trà đào"}, "product_info_tradao"),
    ({"words": "tư vấn trà đào"}, "product_info_tradao"),

    # Intent: combo_inquiry
    ({"words": "quán có combo gì"}, "combo_inquiry"),
    ({"words": "gợi ý combo"}, "combo_inquiry"),
    ({"words": "combo nào ngon"}, "combo_inquiry"),
    ({"words": "các loại combo"}, "combo_inquiry"),
    ({"words": "xem combo"}, "combo_inquiry"),
    ({"words": "combo khuyến mãi"}, "combo_inquiry"),
    ({"words": "combo đặc biệt"}, "combo_inquiry"),
    ({"words": "tư vấn combo"}, "combo_inquiry"),

    # Intent: promotion_inquiry
    ({"words": "khuyến mãi hôm nay"}, "promotion_inquiry"),
    ({"words": "có giảm giá không"}, "promotion_inquiry"),
    ({"words": "ưu đãi gì"}, "promotion_inquiry"),
    ({"words": "khuyến mại"}, "promotion_inquiry"),
    ({"words": "giảm giá"}, "promotion_inquiry"),
    ({"words": "hôm nay có gì đặc biệt"}, "promotion_inquiry"),
    ({"words": "CTKM"}, "promotion_inquiry"),

    # Intent: order_coffee (ví dụ: cà phê đen đá)
    ({"words": "order cà phê đen đá"}, "order_capheden_da"),
    ({"words": "gọi cà phê đen đá"}, "order_capheden_da"),
    ({"words": "đặt cà phê đen đá"}, "order_capheden_da"),
    ({"words": "mua cà phê đen đá"}, "order_capheden_da"),
    ({"words": "cho tôi cà phê đen đá"}, "order_capheden_da"),
    ({"words": "lấy cà phê đen đá"}, "order_capheden_da"),
    ({"words": "một cà phê đen đá"}, "order_capheden_da"),

    # Intent: order_coffee (ví dụ: trà đào)
    ({"words": "order trà đào"}, "order_tradao"),
    ({"words": "gọi trà đào"}, "order_tradao"),
    ({"words": "đặt trà đào"}, "order_tradao"),
    ({"words": "mua trà đào"}, "order_tradao"),
    ({"words": "cho tôi trà đào"}, "order_tradao"),
    ({"words": "lấy trà đào"}, "order_tradao"),
    ({"words": "một trà đào"}, "order_tradao"),

    # Intent: location_hours_inquiry
    ({"words": "địa chỉ quán ở đâu"}, "location_hours_inquiry"),
    ({"words": "quán ở chỗ nào"}, "location_hours_inquiry"),
    ({"words": "vị trí quán"}, "location_hours_inquiry"),
    ({"words": "mấy giờ mở cửa"}, "location_hours_inquiry"),
    ({"words": "giờ làm việc"}, "location_hours_inquiry"),
    ({"words": "khi nào mở cửa"}, "location_hours_inquiry"),
    ({"words": "giờ mở cửa"}, "location_hours_inquiry"),
    ({"words": "hôm nay mở cửa không"}, "location_hours_inquiry"),

    # Intent: thank_you
    ({"words": "cảm ơn bạn"}, "thank_you"),
    ({"words": "cám ơn"}, "thank_you"),
    ({"words": "thanks"}, "thank_you"),
    ({"words": "tks"}, "thank_you"),
    ({"words": "ok cảm ơn"}, "thank_you"),
    ({"words": "vậy cảm ơn nhé"}, "thank_you"),
    ({"words": "thanks nhiều"}, "thank_you"),

    # Intent: farewell
    ({"words": "tạm biệt"}, "farewell"),
    ({"words": "bye"}, "farewell"),
    ({"words": "goodbye"}, "farewell"),
    ({"words": "hẹn gặp lại"}, "farewell"),
    ({"words": "see you later"}, "farewell"),
    ({"words": "thoát"}, "farewell"), # Thêm "thoát" để người dùng có thể thoát chat

    # Intent: wifi_inquiry
    ({"words": "mật khẩu wifi"}, "wifi_inquiry"),
    ({"words": "pass wifi là gì"}, "wifi password"),
    ({"words": "wifi password"}, "wifi password"),
    ({"words": "wifi pass"}, "wifi password"),
    ({"words": "xin mật khẩu wifi"}, "wifi password"),

    # Intent: payment_methods
    ({"words": "thanh toán bằng gì"}, "payment_methods"),
    ({"words": "cách thanh toán"}, "payment_methods"),
    ({"words": "hình thức thanh toán"}, "payment_methods"),
    ({"words": "chấp nhận thanh toán"}, "payment_methods"),
    ({"words": "phương thức thanh toán"}, "payment_methods"),
    ({"words": "thanh toán thẻ được không"}, "payment_methods"),
    ({"words": "có thanh toán online không"}, "payment_methods"),

    # Intent: feedback_complaint
    ({"words": "góp ý cho quán"}, "feedback_complaint"),
    ({"words": "phản hồi dịch vụ"}, "feedback_complaint"),
    ({"words": "feedback quán"}, "feedback_complaint"),
    ({"words": "khiếu nại"}, "feedback_complaint"),
    ({"words": "đóng góp ý kiến"}, "feedback_complaint"),
    ({"words": "nhận xét về quán"}, "feedback_complaint"),
    ({"words": "có điều muốn nói"}, "feedback_complaint"),

    # ... Bạn có thể THÊM DỮ LIỆU HUẤN LUYỆN cho các intent và sản phẩm khác ...
]


# --- Dữ liệu Mẫu MENU và THÔNG TIN QUÁN (giữ nguyên từ phiên bản trước) ---
MENU_DATA = {
    "coffee": [
        {"name": "Cà phê đen đá", "price": 25000, "description": "Cà phê đen truyền thống, đá mát lạnh, đậm đà."},
        {"name": "Cà phê sữa đá", "price": 30000, "description": "Cà phê đen kết hợp sữa đặc, đá, ngọt ngào."},
        {"name": "Cappuccino", "price": 35000, "description": "Cà phê espresso với sữa nóng và bọt sữa mịn, thơm."},
        {"name": "Latte", "price": 35000, "description": "Cà phê espresso với sữa nóng, nhẹ nhàng."},
        {"name": "Espresso", "price": 30000, "description": "Cà phê espresso nguyên chất, đậm đà, mạnh mẽ."},
    ],
    "tea": [
        {"name": "Trà đào", "price": 35000, "description": "Trà đào thanh mát, thơm ngon, giải nhiệt."},
        {"name": "Trà tắc", "price": 20000, "description": "Trà tắc chua ngọt, giải khát, sảng khoái."},
    ],
    "snack": [
        {"name": "Bánh croissant", "price": 25000, "description": "Bánh sừng bò Pháp, thơm bơ, giòn tan."},
        {"name": "Bánh mì nướng muối ớt", "price": 20000, "description": "Bánh mì giòn tan, đậm đà, cay nồng."},
    ],
    "combo": [
        {"name": "Combo Sáng", "price": 50000, "items": ["Cà phê sữa đá", "Bánh mì nướng muối ớt"], "description": "Combo bữa sáng đầy đủ, tiện lợi."},
        {"name": "Combo Trà Chiều", "price": 60000, "items": ["Trà đào", "Bánh croissant"], "description": "Combo trà chiều thư giãn, ngọt ngào."},
    ]
}

QUAN_INFO = {
    "address": "123 Đường ABC, Quận XYZ, Thành phố Hà Nội",
    "hours": "8:00 AM - 10:00 PM hàng ngày",
    "wifi": "dragoncoffee123",
    "payment_methods": ["Tiền mặt", "Thẻ ngân hàng", "Ví điện tử Momo, VNPay"]
}


# --- Tiền xử lý dữ liệu (trích xuất features) ---
def extract_features(sentence):
    words = nltk.word_tokenize(sentence.lower())
    features = {}
    for word in words:
        features['contains(%s)' % word] = True
    return features

# Chuẩn bị dữ liệu huấn luyện cho NLTK
# stopwords_vietnamese = set(stopwords.words('vietnamese')) # Tải stopwords tiếng Việt (nếu cần) # Tải stopwords tiếng Việt (nếu cần)
processed_training_data = []
for data, intent in training_data:
    # Loại bỏ stopwords (ví dụ): Có thể thêm bước này nếu muốn, nhưng có thể không cần thiết với chatbot đơn giản
    # words_filtered = [w for w in nltk.word_tokenize(data['words'].lower()) if not w in stopwords_vietnamese]
    # featureset = extract_features(" ".join(words_filtered))
    featureset = extract_features(data['words']) # Dùng features từ toàn bộ câu, không lọc stopwords
    processed_training_data.append((featureset, intent))

# --- Vectorize features dùng DictVectorizer ---
vectorizer = DictVectorizer(sparse=False) # Khởi tạo DictVectorizer, sparse=False để output NumPy array
feature_list = [extract_features(data['words']) for data, intent in training_data] # Lấy list features dictionary
vectorizer.fit(feature_list) # Huấn luyện vectorizer trên list features

    # --- XỬ LÝ training_data GỐC ĐỂ TẠO processed_training_data (ĐÚNG LOGIC) ---
processed_training_data = [] # KHỞI TẠO list processed_training_data (QUAN TRỌNG)
for data, intent in training_data: # Lặp QUA training_data GỐC
    featureset = extract_features(data['words']) # Trích xuất features cho TỪNG DATA GỐC
    processed_training_data.append((featureset, intent)) # Append vào processed_training_data (ĐÚNG)

    # --- CODE DEBUG (in processed_training_data sau khi TẠO RA) ---
    print("--- DEBUG: Nội dung của processed_training_data (sau khi tạo) ---")
    for item in processed_training_data:
        print(item) # In nội dung của processed_training_data
    print("--- DEBUG: Kết thúc in processed_training_data ---")
    # --- KẾT THÚC CODE DEBUG ---

        # --- Huấn luyện mô hình SVM (dùng processed_training_data ĐÃ TẠO RA) ---
    classifier = SVC(kernel='linear', probability=True)
    features_dict = [featureset for featureset, intent in processed_training_data] # Lấy list features dictionary từ processed_training_data (ĐÚNG)
    features_vectorized = vectorizer.transform(features_dict)
    import pdb; pdb.set_trace() # <---- CHÈN ĐIỂM DỪNG DEBUGGER (BREAKPOINT) - VỊ TRÍ MỚI (TRƯỚC KHI TẠO labels)
    labels = [intent for featureset, intent in processed_training_data] # <---- DÒNG CODE TẠO labels
    classifier.fit(features_vectorized, labels) # <---- DÒNG CODE HUẤN LUYỆN SVM




# --- Hàm Nhận diện Intent (dùng mô hình Naive Bayes) ---
# --- Hàm Nhận diện Intent (dùng mô hình SVM, đã chỉnh sửa để dùng DictVectorizer) ---
def detect_intent_ai(user_input):
    feats_dict = extract_features(user_input.lower()) # Tạo features dictionary cho user input
    feats_vectorized = vectorizer.transform(feats_dict) # Vectorize features dictionary -> vector số (1 dòng)
    predicted_intent = classifier.predict(feats_vectorized)[0] # Dự đoán intent, classifier.predict() trả về array, lấy phần tử đầu [0]
    return predicted_intent


# --- Hàm Tạo Phản hồi (mở rộng và chi tiết hơn) ---
def generate_response(intent, user_input):
    if intent == "greeting":
        return "Chào bạn! Dragon Coffee rất vui được chào đón bạn. Hôm nay bạn muốn thưởng thức gì ạ?"

    elif intent == "menu_inquiry":
        menu_text = "Chào bạn! Đây là menu của Dragon Coffee:\n"
        menu_text += "Bạn muốn xem menu theo loại nào không? (ví dụ: 'menu cà phê', 'menu trà', 'menu combo')\n" # Gợi ý xem menu theo loại
        menu_text += "Hoặc bạn có thể xem toàn bộ menu dưới đây:\n"
        for category, items in MENU_DATA.items():
            menu_text += f"\n--- {category.upper()} ---\n"
            for item in items:
                menu_text += f"- {item['name']}: {item['price']} VNĐ\n"
        menu_text += "\nBạn cần tư vấn gì thêm không?"
        return menu_text

    elif intent.startswith("product_info_"):
        product_name_key = intent.split("product_info_")[1] # Lấy key tên món (ví dụ: capheden_da)
        product_name_display = product_name_key.replace("_", " ").title() # Format tên món để hiển thị (ví dụ: Cà Phê Đen Đá)
        found_product = None
        for category_items in MENU_DATA.values():
            for item in category_items:
                if item["name"].lower() == product_name_display.lower(): # Tìm món (so khớp không phân biệt hoa thường)
                    found_product = item
                    break
            if found_product:
                break # Thoát khỏi vòng lặp category sau khi tìm thấy sản phẩm

        if found_product:
            response_text = f"Thông tin về {found_product['name']}:\n"
            response_text += f"- Giá: {found_product['price']} VNĐ\n"
            response_text += f"- Mô tả: {found_product['description']}\n"
            # Gợi ý thêm món tương tự (ví dụ):
            similar_category = [item["name"] for item in MENU_DATA.get(list(MENU_DATA.keys())[list(MENU_DATA.values()).index(category_items)], []) if item != found_product] # Lấy danh sách món cùng loại trừ món hiện tại
            if similar_category:
                response_text += f"\nBạn có muốn thử các món khác cùng loại như: {', '.join(similar_category[:3])} không?" # Gợi ý tối đa 3 món
            return response_text
        else:
            return f"Xin lỗi, Dragon Coffee hiện tại không có thông tin chi tiết về món '{product_name_display}'. Bạn có muốn hỏi món khác không?"

    elif intent == "combo_inquiry":
        combo_text = "Dragon Coffee gợi ý một số combo hấp dẫn:\n"
        for combo_item in MENU_DATA.get("combo", []): # Lấy danh sách combo từ MENU_DATA
            combo_text += f"\n- {combo_item['name']} - Giá: {combo_item['price']} VNĐ\n"
            combo_text += f"   Bao gồm: {', '.join(combo_item['items'])}\n"
            combo_text += f"   Mô tả: {combo_item['description']}\n"
        combo_text += "\nBạn thấy combo nào thú vị không ạ?"
        return combo_text

    elif intent == "promotion_inquiry":
        return "Hiện tại Dragon Coffee đang có chương trình khuyến mãi giảm 20% cho tất cả đồ uống vào thứ 2 hàng tuần.  Ngoài ra còn có combo giảm giá đặc biệt vào mỗi tháng. Bạn muốn biết thêm về combo tháng này không?"

    elif intent.startswith("order_"): # Intent order_... (ví dụ: order_capheden_da, order_tradao)
        ordered_item_key = intent.split("order_")[1] # Lấy key tên món đã order (ví dụ: capheden_da)
        ordered_item_name = ordered_item_key.replace("_", " ").title() # Format tên món
        return f"Bạn đã order món '{ordered_item_name}'. Quý khách vui lòng chờ trong giây lát nhé! \n(Chức năng order hoàn chỉnh sẽ sớm được tích hợp, hiện tại đây chỉ là demo)." # Xác nhận order

    elif intent == "location_hours_inquiry":
        return f"Dragon Coffee rất hân hạnh đón tiếp bạn tại địa chỉ: {QUAN_INFO['address']}. \nChúng tôi mở cửa từ {QUAN_INFO['hours']} hàng ngày."

    elif intent == "wifi_inquiry":
        return f"Mật khẩu Wi-Fi của Dragon Coffee là: {QUAN_INFO['wifi']}. Mời bạn kết nối và trải nghiệm internet tốc độ cao!"

    elif intent == "payment_methods":
        payment_methods_str = ", ".join(QUAN_INFO['payment_methods'])
        return f"Dragon Coffee chấp nhận thanh toán bằng: {payment_methods_str}. Bạn muốn thanh toán bằng hình thức nào ạ?"

    elif intent == "feedback_complaint":
        return "Cảm ơn bạn đã muốn đóng góp ý kiến cho Dragon Coffee!  Mời bạn cho biết phản hồi/góp ý của mình để chúng tôi ngày càng hoàn thiện hơn." # Hỏi xin feedback

    elif intent == "thank_you":
        return "Dragon Coffee rất vui được phục vụ bạn! Nếu cần gì thêm, đừng ngần ngại hỏi nhé."

    elif intent == "farewell":
        return "Cảm ơn bạn đã ghé thăm Dragon Coffee! Hẹn gặp lại bạn lần sau!"

    elif intent == "unknown":
        return "Xin lỗi, tôi chưa hiểu rõ yêu cầu của bạn. Bạn có thể diễn đạt lại câu hỏi hoặc thử hỏi theo cách khác được không ạ?  Tôi có thể giúp bạn về menu, thông tin sản phẩm, combo, khuyến mãi, địa chỉ, giờ mở cửa, wifi, thanh toán..." # Gợi ý các intent chatbot có thể xử lý

    return "Xin lỗi, có lỗi xảy ra trong quá trình xử lý yêu cầu của bạn. Vui lòng thử lại sau." # Fallback response


# --- Hàm chính chatbot ---
def chatbot_response(user_input):
    intent = detect_intent_ai(user_input) # Nhận diện intent bằng AI
    response = generate_response(intent, user_input) # Tạo phản hồi dựa trên intent
    return response


if __name__ == '__main__':
    print("--- Chatbot Demo - Phiên bản AI (Naive Bayes) Đầy Đủ ---")
    nltk.download('punkt') # Tải punkt tokenizer (nếu chưa có) - cần cho nltk.word_tokenize
    while True:
        user_message = input("Bạn: ")
        if user_message.lower() == "thoát":
            print("Chatbot: Tạm biệt! Hẹn gặp lại.")
            break
        response = chatbot_response(user_message)
        print("Chatbot:", response)