# /ai_services/content_generator.py

"""
Dragon Coffee Shop - Content Generator (Template-Based Only)
This module generates marketing content, product descriptions, etc., using ONLY predefined templates.
"""

import random
import re
import os
import json
from flask import current_app # Để ghi log
import logging # Dùng logging cơ bản nếu không có app context
from datetime import datetime, timedelta

class ContentGenerator:
    def __init__(self):
        """Initialize template-based content generator"""
        self.logger = self._get_logger() # Lấy logger
        self.templates_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(self.templates_dir, exist_ok=True)
        self.templates_path = os.path.join(self.templates_dir, 'content_templates.json')
        self.templates = self.load_templates()
        self.logger.info("Template-based ContentGenerator initialized.")

    def _get_logger(self):
        """Helper to get logger safely."""
        if current_app:
            return current_app.logger
        else:
            logger = logging.getLogger('content_generator')
            if not logger.hasHandlers():
                 logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - CONTENT_GEN - %(message)s')
            # logger.info("ContentGenerator logger initialized outside Flask context.")
            return logger

    def load_templates(self):
        """Load content templates from file or create defaults."""
        if os.path.exists(self.templates_path):
            try:
                with open(self.templates_path, 'r', encoding='utf-8') as f:
                    templates = json.load(f)
                    self.logger.info(f"Loaded templates from {self.templates_path}")
                    return templates
            except Exception as e:
                self.logger.error(f"Error loading templates file: {e}. Using defaults.", exc_info=True)
                # Fall through to create defaults
        else:
            self.logger.warning(f"Templates file not found at {self.templates_path}. Creating defaults.")

        return self.create_default_templates() # Create defaults if load fails or file not found


    def create_default_templates(self):
        """Create default content templates (nội dung template giữ nguyên như cũ)."""
        self.logger.info("Creating default content templates structure.")
        templates = {
             'product_description': [
                "Thưởng thức {product_name}, một {adjective} đồ uống {unique_quality} của Dragon Coffee. {flavor_profile} với {texture} tuyệt vời, đây là sự lựa chọn hoàn hảo cho {occasion}.",
                "{product_name} của chúng tôi là sự kết hợp {adjective} giữa {ingredient} và {ingredient2}, tạo nên hương vị {flavor_profile} không thể quên. Thưởng thức {serving_suggestion} để có trải nghiệm tốt nhất.",
                "Khám phá {product_name} - {adjective} đồ uống {origin} với {unique_quality}. {product_name} được phục vụ {serving_suggestion}, mang đến trải nghiệm {sensation} cho giác quan của bạn."
            ],
            'promotion_announcement': [
                "🔥 KHUYẾN MÃI ĐẶC BIỆT! 🔥\nTừ {start_date} đến {end_date}, tận hưởng {discount}% cho {product_name}. {promotion_details}. Chỉ có tại Dragon Coffee! #DragonSpecial",
                "⚡️ ƯU ĐÃI SHOCK! ⚡️\n{promotion_name} đã trở lại! {discount}% cho {product_category} từ {start_date}. {promotion_details}. Đừng bỏ lỡ!",
                "🎉 DEAL HOT! 🎉\nMua {product_name}, tặng {free_item}! Chương trình {promotion_details} chỉ diễn ra từ {start_date} đến {end_date}. Ghé ngay Dragon Coffee!"
            ],
            'social_media_post': [
                "☕ Bạn đã thử {product_name} chưa? {adjective} đồ uống này sẽ {benefit} và {benefit2}! Ghé Dragon Coffee ngay hôm nay và được giảm {discount}% khi check-in! #DragonCoffee #CoffeeLovers",
                "🌟 {adjective} buổi sáng bắt đầu với {product_name}! {product_description} Hôm nay chúng tôi có chương trình {promotion_details}. Đừng bỏ lỡ! #MorningBoost #DragonCoffee",
                "✨ Trải nghiệm mới tại Dragon Coffee! {product_name} đã trở lại với {unique_quality}. {product_description} Ghé thăm chúng tôi và chia sẻ cảm nhận của bạn! #NewExperience #DragonTaste"
            ],
            'email_newsletter': [
                "Chào {customer_first_name},\n\nChúng tôi rất vui được chia sẻ về {product_name} mới của Dragon Coffee! {product_description}\n\nTừ {start_date} đến {end_date}, bạn sẽ nhận được {discount}% khi đặt hàng online. Chỉ cần sử dụng mã: {promo_code}.\n\n{promotion_details}\n\nChúc bạn một ngày tuyệt vời,\nĐội ngũ Dragon Coffee",
                # ... (Thêm các template email khác nếu cần) ...
            ],
             "about_us_intro": [
                "Chào mừng bạn đến với {shop_name}! Chúng tôi tự hào là điểm đến cà phê độc đáo, nơi {theme} huyền bí hòa quyện cùng hương vị {key_feature} tinh tế. Hãy bước vào không gian {adjective} của chúng tôi để có một {experience} khó quên.",
                "Khám phá thế giới đầy mê hoặc tại {shop_name}, quán cà phê lấy cảm hứng từ {theme}. Chúng tôi không chỉ phục vụ những ly cà phê thơm ngon nhất mà còn mang đến {key_feature} và một bầu không khí {adjective}, hứa hẹn một {experience} tuyệt vời.",
            ],
             "interesting_story": [
                "Người ta kể rằng, vào những đêm trăng tròn, {artifact} của Dragon Coffee lại phát ra ánh sáng huyền ảo.",
                "Đã từng có {event} tại quán, và kể từ đó, không khí nơi đây trở nên ấm áp hơn hẳn.",
                "Một {customer_type} từng nói nhỏ với chúng tôi rằng, {secret}.",
                "Ít ai biết, ly {drink_name} bạn đang thưởng thức không chỉ đơn thuần là cà phê..."
            ]
             # ... (Thêm các key template khác bạn cần) ...
        }
        # Cố gắng lưu file default
        try:
            os.makedirs(os.path.dirname(self.templates_path), exist_ok=True)
            with open(self.templates_path, 'w', encoding='utf-8') as f:
                json.dump(templates, f, ensure_ascii=False, indent=4)
            self.logger.info(f"Saved default templates to {self.templates_path}")
        except Exception as e:
            self.logger.error(f"Could not save default templates: {e}")
        return templates

    def fill_template(self, template_key, data, default_data):
        """Fills a template using provided data and defaults."""
        self.logger.debug(f"Filling template '{template_key}' with data: {data}")
        templates_list = self.templates.get(template_key)
        if not templates_list:
            self.logger.error(f"Template key '{template_key}' not found in loaded templates.")
            return f"Lỗi: Không tìm thấy mẫu nội dung cho '{template_key}'." # Trả về lỗi rõ ràng

        if not isinstance(templates_list, list) or not templates_list:
             self.logger.error(f"Template for '{template_key}' is not a valid list or is empty.")
             return f"Lỗi: Mẫu nội dung cho '{template_key}' không hợp lệ."

        template = random.choice(templates_list)
        context = {**default_data, **data} # Ưu tiên data được truyền vào

        try:
            # Tìm placeholders dạng {key}
            placeholders = re.findall(r'{(\w+)}', template)
            # Tạo context cuối cùng, chỉ giữ lại các key có trong placeholder
            final_context = {k: context.get(k, f"[{k.upper()}]") for k in placeholders} # Hiển thị placeholder nếu thiếu data

            filled_template = template.format(**final_context)
            # self.logger.debug(f"Filled template for '{template_key}': '{filled_template[:100]}...'")
            return filled_template
        except KeyError as ke:
            self.logger.error(f"Missing key '{ke}' while formatting template '{template_key}'. Context: {context}")
            return f"Lỗi tạo nội dung (thiếu: {ke})"
        except Exception as format_e:
            self.logger.error(f"Error formatting template '{template_key}': {format_e}", exc_info=True)
            return f"Lỗi xử lý mẫu nội dung '{template_key}'."


    # --- Các hàm generate_* giờ chỉ gọi fill_template ---

    def generate_product_description(self, product_data):
        self.logger.info(f"Generating product description for '{product_data.get('name')}' using TEMPLATE ONLY.")
        defaults = {
            'product_name': 'Sản phẩm', 'adjective': 'đặc biệt', 'unique_quality': ' độc đáo',
            'flavor_profile': 'hương vị khó quên', 'texture': 'kết cấu mịn màng',
            'occasion': 'mọi dịp', 'ingredient': 'nguyên liệu chọn lọc',
            'ingredient2': 'công thức bí truyền', 'serving_suggestion': 'khi dùng lạnh',
            'origin': 'từ Dragon Coffee', 'sensation': 'tuyệt vời'
        }
        return self.fill_template('product_description', product_data, defaults)

    def generate_promotion(self, promotion_data):
        self.logger.info(f"Generating promotion announcement for '{promotion_data.get('name')}' using TEMPLATE ONLY.")
        defaults = {
             'promotion_name': 'KM Đặc Biệt', 'discount': '10', 'product_name': 'Đồ uống bất kỳ',
             'product_category': 'sản phẩm', 'promotion_details': 'Áp dụng tại quán.',
             'start_date': 'Hôm nay', 'end_date': 'Sớm thôi',
             'free_item': 'quà tặng nhỏ'
        }
        # Format date nếu cần
        if isinstance(promotion_data.get('start_date'), datetime):
             promotion_data['start_date'] = promotion_data['start_date'].strftime('%d/%m')
        if isinstance(promotion_data.get('end_date'), datetime):
             promotion_data['end_date'] = promotion_data['end_date'].strftime('%d/%m/%Y')

        return self.fill_template('promotion_announcement', promotion_data, defaults)

    def generate_social_post(self, post_data):
        self.logger.info(f"Generating social post for '{post_data.get('product_name')}' using TEMPLATE ONLY.")
        defaults = {
             'product_name': 'Món Mới', 'adjective': 'Tuyệt hảo', 'benefit': 'thêm năng lượng',
             'benefit2': 'cho ngày mới', 'discount': '5',
             'product_description': 'Hãy thử ngay!', 'promotion_details': 'ưu đãi hấp dẫn.',
             'unique_quality': 'vị ngon khó cưỡng'
        }
        return self.fill_template('social_media_post', post_data, defaults)

    def generate_email(self, email_data):
        self.logger.info(f"Generating email for '{email_data.get('customer_first_name')}' using TEMPLATE ONLY.")
        defaults = {
            'customer_first_name': 'Bạn', 'product_name': 'Ưu đãi mới',
            'product_description': 'Nhiều món ngon đang chờ.', 'discount': '10',
            'promo_code': f"DRAGON{random.randint(100,999)}", 'start_date': 'Hiện tại',
            'end_date': 'Sắp hết hạn', 'promotion_details': 'Đặt hàng ngay!',
            'season': 'mùa này', 'previous_order': 'món bạn thích'
        }
        # Format date
        if isinstance(email_data.get('start_date'), datetime): email_data['start_date'] = email_data['start_date'].strftime('%d/%m/%Y')
        if isinstance(email_data.get('end_date'), datetime): email_data['end_date'] = email_data['end_date'].strftime('%d/%m/%Y')

        return self.fill_template('email_newsletter', email_data, defaults)

    # Blog post generator có thể phức tạp, template có thể chưa đủ, nhưng vẫn tạo fallback
    def generate_blog_post(self, blog_data):
         self.logger.info(f"Generating blog post titled '{blog_data.get('blog_title')}' using TEMPLATE ONLY.")
         defaults = {
             'blog_title': blog_data.get('product_name', 'Bài viết mới'),
             'publication_date': datetime.now().strftime('%d/%m/%Y'),
             'product_name': 'Sản phẩm Đặc Biệt',
             'intro_paragraph': 'Giới thiệu về chủ đề...',
             'product_description': 'Mô tả chi tiết...',
             'serving_suggestion': 'Cách thưởng thức...',
             'conclusion_paragraph': 'Kết luận.',
             'origin_story': 'Câu chuyện nguồn gốc...',
             'flavor_profile': 'Hương vị ra sao...',
             'health_benefits': 'Lợi ích...',
             'testimonial': '"Khách hàng nói..."',
             'image_url': '#'
         }
         # Format date nếu cần
         pub_date = blog_data.get('publication_date')
         if isinstance(pub_date, datetime): blog_data['publication_date'] = pub_date.strftime('%d/%m/%Y')

         return self.fill_template('blog_post', blog_data, defaults)


    def generate_about_us_intro(self, shop_data):
        self.logger.info(f"Generating 'About Us' intro for '{shop_data.get('shop_name')}' using TEMPLATE ONLY.")
        defaults = {
             'shop_name': 'Dragon Coffee', 'theme': 'độc đáo', 'key_feature': 'chất lượng tuyệt hảo',
             'adjective': 'ấm cúng', 'experience': 'thú vị'
        }
        return self.fill_template('about_us_intro', shop_data, defaults)


    def generate_interesting_story(self, story_data=None):
        """Generates an interesting story using templates."""
        self.logger.info("Generating interesting story using TEMPLATE ONLY.")
        if story_data is None: story_data = {}
        defaults = {
            'artifact': 'chiếc ấm cổ', 'event': 'một buổi chiều mưa',
            'drink_name': 'Cà Phê Rồng', 'customer_type': 'vị khách quen',
            'secret': 'có một công thức bí mật.'
        }
        # Logic format drink_name trong secret nếu cần
        if '{drink_name}' in defaults.get('secret',''):
             drink = story_data.get('drink_name', defaults['drink_name'])
             defaults['secret'] = defaults['secret'].format(drink_name=drink)

        return self.fill_template('interesting_story', story_data, defaults)

# --- Singleton instance ---
content_generator = None

def init_content_generator():
    """Initialize the template-based content generator."""
    global content_generator
    if content_generator is None:
        content_generator = ContentGenerator()
    return content_generator

# --- Helper functions ---
# Đảm bảo các hàm này gọi đúng phiên bản content_generator chỉ dùng template

def generate_product_description(product_data):
    if content_generator is None: init_content_generator()
    return content_generator.generate_product_description(product_data)

def generate_promotion(promotion_data):
    if content_generator is None: init_content_generator()
    return content_generator.generate_promotion(promotion_data)

def generate_social_post(post_data):
    if content_generator is None: init_content_generator()
    return content_generator.generate_social_post(post_data)

def generate_email(email_data):
    if content_generator is None: init_content_generator()
    return content_generator.generate_email(email_data)

def generate_blog_post(blog_data):
     if content_generator is None: init_content_generator()
     return content_generator.generate_blog_post(blog_data)

def generate_about_us_intro(shop_data):
    if content_generator is None: init_content_generator()
    if not isinstance(shop_data, dict): shop_data = {}
    if 'shop_name' not in shop_data: shop_data['shop_name'] = 'Dragon Coffee' # Thêm default
    return content_generator.generate_about_us_intro(shop_data)

def generate_interesting_story(story_data=None):
    if content_generator is None: init_content_generator()
    return content_generator.generate_interesting_story(story_data)

# Không cần hàm check_openai_available nữa vì không dùng