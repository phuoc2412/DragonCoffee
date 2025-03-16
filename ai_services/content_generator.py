"""
Dragon Coffee Shop - Content Generator
This module generates marketing content, product descriptions, and promotional materials.
"""

import random
import re
import numpy as np
from datetime import datetime, timedelta
import os
import json

# Try to use OpenAI if available, or fall back to rule-based generation
try:
    from openai import OpenAI
    openai_available = True
except ImportError:
    openai_available = False

class ContentGenerator:
    def __init__(self):
        """Initialize content generator"""
        # Templates directory
        self.templates_dir = 'ai_services/data'
        os.makedirs(self.templates_dir, exist_ok=True)
        
        # Load templates
        self.templates = self.load_templates()
        
        # Initialize OpenAI client if available
        self.openai_client = None
        if openai_available:
            try:
                api_key = os.environ.get('OPENAI_API_KEY')
                if api_key:
                    self.openai_client = OpenAI(api_key=api_key)
            except Exception as e:
                print(f"Error initializing OpenAI client: {e}")
    
    def load_templates(self):
        """Load content templates from file or create defaults"""
        templates_path = os.path.join(self.templates_dir, 'content_templates.json')
        
        if os.path.exists(templates_path):
            try:
                with open(templates_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return self.create_default_templates()
        else:
            return self.create_default_templates()
    
    def create_default_templates(self):
        """Create default content templates"""
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
                "Thân gửi {customer_first_name},\n\nBạn đã sẵn sàng cho {season} cùng Dragon Coffee chưa? Chúng tôi vừa ra mắt {product_name} - {product_description}\n\nĐặc biệt, khách hàng thân thiết như bạn sẽ được {discount}% khi sử dụng mã: {promo_code} từ {start_date}.\n\n{promotion_details}\n\nCảm ơn vì đã luôn đồng hành cùng chúng tôi,\nDragon Coffee",
                "Chào {customer_first_name},\n\nChúng tôi nhớ rằng bạn yêu thích {previous_order}. Vì vậy, chúng tôi muốn giới thiệu với bạn {product_name} mới của chúng tôi!\n\n{product_description}\n\nHôm nay, bạn có thể dùng mã: {promo_code} để được giảm {discount}% cho đơn hàng tiếp theo.\n\n{promotion_details}\n\nCảm ơn vì đã chọn Dragon Coffee,\nĐội ngũ Dragon Coffee"
            ],
            'blog_post': [
                "# {blog_title}\n\n*{publication_date}*\n\n## Giới thiệu\n\n{intro_paragraph}\n\n## {product_name} - Sự kết hợp hoàn hảo\n\n{product_description}\n\n## Cách thưởng thức tốt nhất\n\n{serving_suggestion}\n\n## Kết luận\n\n{conclusion_paragraph}",
                "# {blog_title}\n\n*{publication_date}*\n\n![{product_name}](image_url)\n\n{intro_paragraph}\n\n## Nguồn gốc của {product_name}\n\n{origin_story}\n\n## Hương vị đặc trưng\n\n{flavor_profile}\n\n## Lợi ích sức khỏe\n\n{health_benefits}\n\n## Tại sao khách hàng yêu thích {product_name}\n\n{testimonial}\n\n## Kết luận\n\n{conclusion_paragraph}"
            ]
        }
        
        # Save templates
        templates_path = os.path.join(self.templates_dir, 'content_templates.json')
        try:
            with open(templates_path, 'w', encoding='utf-8') as f:
                json.dump(templates, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving templates: {e}")
        
        return templates
    
    def generate_product_description(self, product_data):
        """Generate a product description"""
        # Try OpenAI first if available
        if self.openai_client:
            try:
                openai_result = self.generate_with_openai(
                    "product_description", product_data
                )
                if openai_result:
                    return openai_result
            except Exception as e:
                print(f"Error using OpenAI for product description: {e}")
        
        # Fall back to template-based generation
        try:
            # Select a random template
            template = random.choice(self.templates['product_description'])
            
            # Add default values for missing fields
            defaults = {
                'product_name': product_data.get('name', 'Đồ uống đặc biệt'),
                'adjective': random.choice(['thơm ngon', 'tuyệt vời', 'đặc biệt', 'độc đáo', 'hấp dẫn']),
                'unique_quality': random.choice(['độc đáo', 'đặc trưng', 'khó cưỡng', 'đậm đà']),
                'flavor_profile': random.choice(['Hương vị đậm đà', 'Vị ngọt tinh tế', 'Hương thơm quyến rũ']),
                'texture': random.choice(['độ mịn', 'bọt kem', 'sự hòa quyện', 'lớp topping']),
                'occasion': random.choice(['buổi sáng tràn đầy năng lượng', 'giây phút thư giãn', 'cuộc họp đầu ngày']),
                'ingredient': random.choice(['hạt cà phê Arabica', 'trà xanh thượng hạng', 'sô-cô-la Bỉ']),
                'ingredient2': random.choice(['sữa tươi', 'kem tươi', 'caramel', 'bạc hà']),
                'serving_suggestion': random.choice(['nóng', 'đá', 'với bánh ngọt', 'vào buổi sáng']),
                'origin': random.choice(['Việt Nam', 'Á Đông', 'truyền thống', 'hiện đại']),
                'sensation': random.choice(['thư giãn', 'sảng khoái', 'hài lòng', 'khó quên'])
            }
            
            # Merge provided data with defaults
            context = {**defaults, **product_data}
            
            # Fill template with context
            description = template
            for key, value in context.items():
                pattern = '{' + key + '}'
                description = description.replace(pattern, str(value))
            
            return description
        except Exception as e:
            print(f"Error generating product description: {e}")
            return f"Thưởng thức {product_data.get('name', 'đồ uống đặc biệt')} tại Dragon Coffee."
    
    def generate_promotion(self, promotion_data):
        """Generate a promotion announcement"""
        # Try OpenAI first if available
        if self.openai_client:
            try:
                openai_result = self.generate_with_openai(
                    "promotion_announcement", promotion_data
                )
                if openai_result:
                    return openai_result
            except Exception as e:
                print(f"Error using OpenAI for promotion: {e}")
        
        # Fall back to template-based generation
        try:
            # Select a random template
            template = random.choice(self.templates['promotion_announcement'])
            
            # Format dates
            start_date = promotion_data.get('start_date')
            if isinstance(start_date, str):
                try:
                    start_date = datetime.strptime(start_date, '%Y-%m-%d').strftime('%d/%m/%Y')
                except:
                    start_date = start_date
            elif isinstance(start_date, datetime):
                start_date = start_date.strftime('%d/%m/%Y')
            
            end_date = promotion_data.get('end_date')
            if isinstance(end_date, str):
                try:
                    end_date = datetime.strptime(end_date, '%Y-%m-%d').strftime('%d/%m/%Y')
                except:
                    end_date = end_date
            elif isinstance(end_date, datetime):
                end_date = end_date.strftime('%d/%m/%Y')
            
            # Add default values for missing fields
            defaults = {
                'promotion_name': promotion_data.get('name', 'Khuyến mãi đặc biệt'),
                'discount': promotion_data.get('discount_percent', '20'),
                'product_name': random.choice(['Cà phê Dragon', 'Trà sữa Phượng Hoàng', 'Cappuccino Rồng Vàng']),
                'product_category': random.choice(['tất cả đồ uống', 'cà phê', 'trà', 'đồ uống đặc biệt']),
                'promotion_details': random.choice(['Áp dụng cho mọi chi nhánh', 'Chỉ áp dụng khi đặt hàng online', 'Giới hạn 1 ly/khách hàng']),
                'start_date': start_date or 'hôm nay',
                'end_date': end_date or 'cuối tháng',
                'free_item': random.choice(['bánh quy', 'bánh ngọt', 'upsize miễn phí', 'topping thêm'])
            }
            
            # Merge provided data with defaults
            context = {**defaults, **promotion_data}
            
            # Fill template with context
            announcement = template
            for key, value in context.items():
                pattern = '{' + key + '}'
                announcement = announcement.replace(pattern, str(value))
            
            return announcement
        except Exception as e:
            print(f"Error generating promotion: {e}")
            return f"KHUYẾN MÃI! {promotion_data.get('discount_percent', '20')}% cho {promotion_data.get('name', 'đồ uống')}. Chỉ tại Dragon Coffee!"
    
    def generate_social_post(self, post_data):
        """Generate a social media post"""
        # Try OpenAI first if available
        if self.openai_client:
            try:
                openai_result = self.generate_with_openai(
                    "social_media_post", post_data
                )
                if openai_result:
                    return openai_result
            except Exception as e:
                print(f"Error using OpenAI for social post: {e}")
        
        # Fall back to template-based generation
        try:
            # Select a random template
            template = random.choice(self.templates['social_media_post'])
            
            # Add default values for missing fields
            defaults = {
                'product_name': post_data.get('product_name', 'Đồ uống Dragon'),
                'adjective': random.choice(['Tuyệt vời', 'Tràn đầy năng lượng', 'Mới mẻ', 'Thư giãn']),
                'benefit': random.choice(['đánh thức vị giác', 'tiếp thêm năng lượng', 'làm dịu tâm hồn']),
                'benefit2': random.choice(['mang đến cảm giác sảng khoái', 'tạo cảm hứng cho ngày mới', 'làm cuộc sống thêm thú vị']),
                'discount': random.choice(['10', '15', '20']),
                'product_description': post_data.get('product_description', 'Đồ uống độc đáo với hương vị khó cưỡng.'),
                'promotion_details': random.choice(['mua 1 tặng 1', 'giảm giá đặc biệt', 'quà tặng bất ngờ']),
                'unique_quality': random.choice(['hương vị mới', 'công thức cải tiến', 'nguyên liệu cao cấp'])
            }
            
            # Merge provided data with defaults
            context = {**defaults, **post_data}
            
            # Fill template with context
            post = template
            for key, value in context.items():
                pattern = '{' + key + '}'
                post = post.replace(pattern, str(value))
            
            return post
        except Exception as e:
            print(f"Error generating social post: {e}")
            return f"☕ Thưởng thức {post_data.get('product_name', 'đồ uống Dragon')} tại Dragon Coffee! #DragonCoffee"
    
    def generate_email(self, email_data):
        """Generate an email newsletter"""
        # Try OpenAI first if available
        if self.openai_client:
            try:
                openai_result = self.generate_with_openai(
                    "email_newsletter", email_data
                )
                if openai_result:
                    return openai_result
            except Exception as e:
                print(f"Error using OpenAI for email: {e}")
        
        # Fall back to template-based generation
        try:
            # Select a random template
            template = random.choice(self.templates['email_newsletter'])
            
            # Format dates
            start_date = email_data.get('start_date')
            if isinstance(start_date, str):
                try:
                    start_date = datetime.strptime(start_date, '%Y-%m-%d').strftime('%d/%m/%Y')
                except:
                    start_date = start_date
            elif isinstance(start_date, datetime):
                start_date = start_date.strftime('%d/%m/%Y')
            
            end_date = email_data.get('end_date')
            if isinstance(end_date, str):
                try:
                    end_date = datetime.strptime(end_date, '%Y-%m-%d').strftime('%d/%m/%Y')
                except:
                    end_date = end_date
            elif isinstance(end_date, datetime):
                end_date = end_date.strftime('%d/%m/%Y')
            
            # Generate promo code if not provided
            promo_code = email_data.get('promo_code')
            if not promo_code:
                promo_code = f"DRAGON{random.randint(1000, 9999)}"
            
            # Add default values for missing fields
            defaults = {
                'customer_first_name': email_data.get('customer_name', 'Quý khách'),
                'product_name': email_data.get('product_name', 'Đồ uống Dragon đặc biệt'),
                'product_description': email_data.get('product_description', 'Đồ uống độc đáo với hương vị khó cưỡng.'),
                'discount': email_data.get('discount', '15'),
                'promo_code': promo_code,
                'start_date': start_date or 'hôm nay',
                'end_date': end_date or 'cuối tháng',
                'promotion_details': email_data.get('promotion_details', 'Chương trình áp dụng cho mọi chi nhánh Dragon Coffee.'),
                'season': random.choice(['mùa hè', 'mùa thu', 'mùa đông', 'mùa xuân']),
                'previous_order': random.choice(['Cà phê Dragon', 'Trà sữa Phượng Hoàng', 'Cappuccino Rồng Vàng'])
            }
            
            # Merge provided data with defaults
            context = {**defaults, **email_data}
            
            # Fill template with context
            email = template
            for key, value in context.items():
                pattern = '{' + key + '}'
                email = email.replace(pattern, str(value))
            
            return email
        except Exception as e:
            print(f"Error generating email: {e}")
            return f"Chào {email_data.get('customer_name', 'Quý khách')},\n\nChúng tôi xin giới thiệu {email_data.get('product_name', 'đồ uống mới')} tại Dragon Coffee.\n\nTrân trọng,\nĐội ngũ Dragon Coffee"
    
    def generate_blog_post(self, blog_data):
        """Generate a blog post about a product"""
        # Try OpenAI first if available
        if self.openai_client:
            try:
                openai_result = self.generate_with_openai(
                    "blog_post", blog_data
                )
                if openai_result:
                    return openai_result
            except Exception as e:
                print(f"Error using OpenAI for blog post: {e}")
        
        # Fall back to template-based generation
        try:
            # Select a random template
            template = random.choice(self.templates['blog_post'])
            
            # Format publication date
            publication_date = blog_data.get('publication_date')
            if not publication_date:
                publication_date = datetime.now().strftime('%d/%m/%Y')
            elif isinstance(publication_date, datetime):
                publication_date = publication_date.strftime('%d/%m/%Y')
            
            # Generate blog title if not provided
            blog_title = blog_data.get('blog_title')
            if not blog_title:
                product_name = blog_data.get('product_name', 'Đồ uống Dragon')
                blog_title = f"Khám phá {product_name}: Hành trình hương vị đặc biệt"
            
            # Add default values for missing fields
            defaults = {
                'blog_title': blog_title,
                'publication_date': publication_date,
                'product_name': blog_data.get('product_name', 'Đồ uống Dragon'),
                'intro_paragraph': blog_data.get('intro_paragraph', 
                    f"Dragon Coffee tự hào giới thiệu {blog_data.get('product_name', 'đồ uống đặc biệt')} - một trải nghiệm hương vị độc đáo mà chúng tôi muốn chia sẻ với bạn. Trong bài viết này, chúng tôi sẽ khám phá những điều đặc biệt về sản phẩm này."),
                'product_description': blog_data.get('product_description', 
                    f"{blog_data.get('product_name', 'Đồ uống này')} được chế biến từ những nguyên liệu tươi ngon nhất, tạo nên hương vị đậm đà và khó quên. Sự kết hợp tinh tế giữa các thành phần tạo nên một đồ uống hoàn hảo cho mọi thời điểm trong ngày."),
                'serving_suggestion': blog_data.get('serving_suggestion',
                    f"Để thưởng thức {blog_data.get('product_name', 'đồ uống')} một cách trọn vẹn nhất, chúng tôi khuyên bạn nên uống khi còn nóng/lạnh. Bạn có thể kết hợp với bánh ngọt hoặc bánh mặn để có trải nghiệm ẩm thực trọn vẹn."),
                'conclusion_paragraph': blog_data.get('conclusion_paragraph',
                    f"Hãy ghé thăm Dragon Coffee để thưởng thức {blog_data.get('product_name', 'đồ uống đặc biệt')} và nhiều lựa chọn tuyệt vời khác. Chúng tôi luôn cam kết mang đến cho khách hàng những trải nghiệm ẩm thực tuyệt vời nhất."),
                'origin_story': blog_data.get('origin_story',
                    f"{blog_data.get('product_name', 'Đồ uống này')} có nguồn gốc từ những công thức truyền thống, được cải tiến bởi các barista tài năng của Dragon Coffee. Chúng tôi đã nghiên cứu và phát triển công thức này trong nhiều tháng để đạt được hương vị hoàn hảo."),
                'flavor_profile': blog_data.get('flavor_profile',
                    f"{blog_data.get('product_name', 'Đồ uống này')} có hương vị đậm đà, với notes của chocolate và caramel. Vị ngọt vừa phải kết hợp với độ đắng tinh tế tạo nên sự cân bằng hoàn hảo."),
                'health_benefits': blog_data.get('health_benefits',
                    "Bên cạnh hương vị tuyệt vời, đồ uống này còn cung cấp nhiều lợi ích cho sức khỏe. Các thành phần tự nhiên giúp tăng cường năng lượng, cải thiện tâm trạng và hỗ trợ hệ tiêu hóa."),
                'testimonial': blog_data.get('testimonial',
                    '"Tôi hoàn toàn bị chinh phục bởi hương vị đặc biệt này. Mỗi ngày tôi đều ghé Dragon Coffee để thưởng thức." - Một khách hàng thân thiết')
            }
            
            # Merge provided data with defaults
            context = {**defaults, **blog_data}
            
            # Fill template with context
            blog_post = template
            for key, value in context.items():
                pattern = '{' + key + '}'
                blog_post = blog_post.replace(pattern, str(value))
            
            return blog_post
        except Exception as e:
            print(f"Error generating blog post: {e}")
            return f"# {blog_data.get('blog_title', 'Đồ uống Dragon')}\n\nGiới thiệu về {blog_data.get('product_name', 'đồ uống đặc biệt')} tại Dragon Coffee."
    
    def generate_with_openai(self, content_type, data):
        """Generate content using OpenAI"""
        if not self.openai_client:
            return None
        
        try:
            # Map content types to prompts
            prompts = {
                "product_description": f"Hãy viết một mô tả hấp dẫn cho sản phẩm {data.get('name', 'đồ uống')} tại quán cà phê Dragon Coffee. Sản phẩm có giá {data.get('price', '')}. Đây là một quán cà phê với chủ đề rồng châu Á. Viết bằng tiếng Việt, độ dài khoảng 2-3 câu.",
                
                "promotion_announcement": f"Hãy viết một thông báo khuyến mãi hấp dẫn cho {data.get('name', 'chương trình khuyến mãi')} tại quán cà phê Dragon Coffee. Khuyến mãi giảm {data.get('discount_percent', '20')}% và diễn ra từ {data.get('start_date', 'hôm nay')} đến {data.get('end_date', 'cuối tháng')}. Viết bằng tiếng Việt, ngắn gọn và thu hút, phù hợp đăng trên mạng xã hội.",
                
                "social_media_post": f"Hãy viết một bài đăng mạng xã hội ngắn gọn, hấp dẫn về {data.get('product_name', 'sản phẩm')} tại quán cà phê Dragon Coffee. Sản phẩm có đặc điểm: {data.get('product_description', 'đồ uống độc đáo')}. Viết bằng tiếng Việt, thêm emoji phù hợp và hashtag.",
                
                "email_newsletter": f"Hãy viết một email ngắn gửi đến khách hàng {data.get('customer_name', 'quý khách')} để giới thiệu về {data.get('product_name', 'sản phẩm mới')} tại quán cà phê Dragon Coffee. Email có mã giảm giá {data.get('promo_code', 'DRAGON2023')} giảm {data.get('discount', '15')}%. Viết bằng tiếng Việt, lịch sự và chuyên nghiệp.",
                
                "blog_post": f"Hãy viết một bài blog chi tiết về {data.get('product_name', 'sản phẩm')} tại quán cà phê Dragon Coffee. Bài viết nên bao gồm giới thiệu, mô tả sản phẩm, nguồn gốc, hương vị, và kết luận. Hãy viết bằng tiếng Việt, với định dạng Markdown, độ dài khoảng 300-500 từ."
            }
            
            prompt = prompts.get(content_type)
            if not prompt:
                return None
            
            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",  # the newest OpenAI model is "gpt-4o" which was released May 13, 2024
                messages=[
                    {"role": "system", "content": "Bạn là một chuyên gia marketing cho quán cà phê Dragon Coffee, một quán cà phê với phong cách châu Á và hình ảnh rồng. Hãy viết nội dung marketing hấp dẫn bằng tiếng Việt."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating content with OpenAI: {e}")
            return None


# Singleton instance
content_generator = None

def init_content_generator():
    """Initialize the content generator"""
    global content_generator
    content_generator = ContentGenerator()
    return content_generator

def generate_product_description(product_data):
    """Generate a product description"""
    if content_generator is None:
        init_content_generator()
    
    return content_generator.generate_product_description(product_data)

def generate_promotion(promotion_data):
    """Generate a promotion announcement"""
    if content_generator is None:
        init_content_generator()
    
    return content_generator.generate_promotion(promotion_data)

def generate_social_post(post_data):
    """Generate a social media post"""
    if content_generator is None:
        init_content_generator()
    
    return content_generator.generate_social_post(post_data)

def generate_email(email_data):
    """Generate an email newsletter"""
    if content_generator is None:
        init_content_generator()
    
    return content_generator.generate_email(email_data)

def generate_blog_post(blog_data):
    """Generate a blog post about a product"""
    if content_generator is None:
        init_content_generator()
    
    return content_generator.generate_blog_post(blog_data)