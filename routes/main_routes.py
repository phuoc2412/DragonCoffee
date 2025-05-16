# /routes/main_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import current_user, login_required
from sqlalchemy import func, text, or_, asc, desc
from datetime import datetime, time, timedelta
from utils import format_currency
from sqlalchemy.orm import joinedload
import json

# Đảm bảo import các thành phần cần thiết từ project của bạn
# Đường dẫn có thể thay đổi tùy cấu trúc thư mục
try:
    from models import Product, Category, ContactMessage, Review, User, InterestingStory, db,  ContactMessage, Location, Promotion
    from forms import ContactForm, ReviewForm
    from utils import format_currency
    # Import các hàm AI bạn sử dụng trong file này
    from ai_services import (
        generate_product_description,
        generate_about_us_intro,
        analyze_review_sentiment
        # Chỉ import những hàm AI thực sự dùng trong main_routes
    )
except ImportError as e:
    # Log lỗi nghiêm trọng nếu không import được
    # (Bạn cần thiết lập logger cơ bản nếu current_app chưa sẵn sàng)
    try:
        if current_app:
            current_app.logger.critical(f"CRITICAL IMPORT ERROR in main_routes: {e}", exc_info=True)
        else:
            import logging
            logging.critical(f"CRITICAL IMPORT ERROR in main_routes: {e}", exc_info=True)
    except: pass # Bỏ qua nếu logger cũng lỗi
    # Có thể raise lỗi ở đây để dừng app nếu import lỗi là nghiêm trọng
    # raise ImportError(f"Could not import required modules in main_routes: {e}")

import logging
# Import hàm gửi email từ utils (đảm bảo đường dẫn đúng)
try:
    from utils import send_contact_notification_email, format_currency
except ImportError:
    def send_contact_notification_email(message): # Hàm placeholder nếu import lỗi
        logger = current_app.logger if current_app else logging.getLogger(__name__)
        logger.error("!!! send_contact_notification_email function not found !!!")
        return False

main_bp = Blueprint('main', __name__)

# === Routes ===

@main_bp.route('/')
@main_bp.route('/home')
def index():
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Accessing home page.")
    featured_products = []
    categories = []
    active_promotions = [] # <-- Vẫn cần lấy biến này
    item_of_the_week = None
    random_reviews = []

    category_icons = { # Giữ nguyên định nghĩa icons
        "Cà phê": "fa-coffee", "Trà": "fa-leaf", "Sinh tố": "fa-blender-phone",
        "Nước ép": "fa-glass-citrus", "Bánh ngọt": "fa-birthday-cake",
        "Đồ ăn nhẹ": "fa-hamburger", "Đá xay": "fa-snowflake",
        "Đồ uống đặc biệt": "fa-star",
    }

    try:
        # === Logic query dữ liệu (GIỮ NGUYÊN NHƯ CŨ) ===
        # Lấy sản phẩm nổi bật
        featured_products = Product.query.filter_by(
            is_featured=True, is_available=True
        ).order_by(func.random()).limit(6).all()

        # Lấy món của tuần
        item_of_the_week = Product.query.filter(
            Product.is_available == True, Product.is_featured == True
        ).order_by(func.random()).first()
        if not item_of_the_week:
            item_of_the_week = Product.query.filter(
                Product.is_available == True
            ).order_by(func.random()).first()
        logger.info(f"Selected item of the week: {item_of_the_week.name if item_of_the_week else 'None'}")

        # Lấy danh mục
        categories = Category.query.order_by(Category.name).all()

        # Lấy khuyến mãi (Vẫn lấy vì dùng trong Hero Section mới)
        now = datetime.utcnow()
        active_promotions = Promotion.query.filter(
            Promotion.is_active == True,
            Promotion.start_date <= now,
            Promotion.end_date >= now
        ).order_by(Promotion.end_date.asc()).limit(3).all()
        logger.info(f"Found {len(active_promotions)} active promotions for hero section.")

        # Lấy review ngẫu nhiên
        random_reviews = Review.query.join(Product, Review.product_id == Product.id)\
                                      .filter(Review.rating >= 4, Product.is_available == True)\
                                      .order_by(func.random())\
                                      .limit(3).all()
        logger.info(f"Found {len(random_reviews)} random positive reviews.")

    except Exception as e:
        logger.error(f"Error fetching data for home page: {e}", exc_info=True)
        # Đặt giá trị mặc định nếu lỗi
        featured_products, categories, active_promotions, item_of_the_week, random_reviews = [], [], [], None, []
        flash("Lỗi khi tải dữ liệu trang chủ.", "danger")

    return render_template(
        'index.html',
        featured_products=featured_products,
        item_of_the_week=item_of_the_week,
        categories=categories,
        active_promotions=active_promotions, # <-- Truyền KM vào template
        random_reviews=random_reviews,
        format_currency=format_currency,
        category_icons=category_icons
    )


@main_bp.route('/menu')
def menu():
    """Trang hiển thị thực đơn ban đầu, gọi AJAX để load sản phẩm."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    try:
        # Vẫn lấy categories để hiển thị nav
        categories = Category.query.order_by(Category.name).all()

        # Lấy tham số từ URL để thiết lập trạng thái ban đầu cho JS
        initial_category_id = request.args.get('category', default=None, type=int)
        initial_search_term = request.args.get('q', default='', type=str)
        initial_sort_by = request.args.get('sort', default='name', type=str)

        # Xác định current_category ban đầu nếu có category_id
        current_category = None
        if initial_category_id:
            current_category = Category.query.get(initial_category_id)

    except Exception as e:
        logger.error(f"Error preparing initial menu page: {e}", exc_info=True)
        categories = []
        initial_category_id = None
        initial_search_term = ''
        initial_sort_by = 'name'
        current_category = None
        flash("Lỗi khi tải cấu trúc trang thực đơn.", "danger")

    return render_template('menu.html',
                           categories=categories,
                           current_category=current_category, # Chỉ để hiển thị description ban đầu nếu có
                           initial_category_id=initial_category_id, # Truyền ID để JS biết
                           initial_search_term=initial_search_term, # Truyền search để JS biết
                           initial_sort_by=initial_sort_by,       # Truyền sort để JS biết
                           format_currency=format_currency # Vẫn truyền format nếu template chính dùng
                           ) # Không cần truyền 'products' ở đây nữa

@main_bp.route('/menu/search_suggestions')
def menu_search_suggestions():
    term = request.args.get('term', '').strip()
    suggestions = []
    limit = 7 # Số gợi ý tối đa
    if len(term) >= 1:
        try:
            # --- SỬA QUERY Ở ĐÂY ---
            query = Product.query.filter(
                Product.name.ilike(f"%{term}%"),
                Product.is_available == True
            ).with_entities( # Chỉ lấy các cột cần thiết
                Product.id,
                Product.name,
                Product.image_url # <-- Lấy thêm image_url
            ).order_by(func.length(Product.name)).limit(limit).all()

            # --- SỬA CÁCH TẠO RESULT ---
            suggestions = [
                {"id": p.id, "name": p.name, "image_url": p.image_url or url_for('static', filename='images/default_product_thumb.png')} # <-- Thêm image_url (có fallback)
                for p in query
            ]
            # -------------------------
        except Exception as e:
            logger = current_app.logger if current_app else logging.getLogger(__name__)
            logger.error(f"Error fetching search suggestions for term '{term}': {e}", exc_info=False)
            suggestions = [] # Trả rỗng nếu lỗi

    return jsonify(suggestions)

@main_bp.route('/about')
def about():
    """Trang giới thiệu."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    ai_about_intro = None
    published_stories = []
    ai_generated_successfully = False

    try:
        # Lấy nội dung giới thiệu từ AI
        shop_info_for_ai = {
           'shop_name': 'Dragon Coffee',
           'theme': 'phong cách rồng châu Á huyền bí',
           'key_feature': 'hương vị cà phê đặc sản đậm đà và không gian check-in độc đáo'
        }
        logger.info("Attempting to generate AI 'About Us' intro...")
        # Phần gọi AI có thể bị lỗi (ví dụ: API key), nên cần try-except riêng hoặc hàm generate đã có xử lý lỗi
        try:
             ai_about_intro = generate_about_us_intro(shop_info_for_ai)
             # Chỉ log thành công NẾU có kết quả thực sự từ AI (không phải fallback)
             if ai_about_intro and "Lỗi" not in ai_about_intro and "đang được cập nhật" not in ai_about_intro:
                  logger.info("Successfully generated AI 'About Us' intro.")
                  ai_generated_successfully = True
             # Hàm generate_about_us_intro NÊN tự log lỗi/fallback bên trong nó rồi
        except Exception as ai_error:
             logger.error(f"Error calling generate_about_us_intro: {ai_error}", exc_info=True)
             # ai_about_intro sẽ là None hoặc fallback từ hàm generate

        # Lấy các câu chuyện đã published
        logger.info("Fetching published interesting stories...")
        published_stories = InterestingStory.query.filter_by(status='published')\
                                                .order_by(InterestingStory.created_at.desc())\
                                                .limit(3).all()
        logger.info(f"Found {len(published_stories)} published stories.")

    except Exception as e:
        logger.error(f"Error fetching data for about page: {e}", exc_info=True)
        flash("Lỗi khi tải dữ liệu trang giới thiệu.", "danger")
        # Giá trị mặc định đã được set là None/[]

    # Nếu bạn muốn log riêng biệt việc AI có thành công hay không sau khối try chính
    # logger.info(f"AI Intro Generation Status: {'Success' if ai_generated_successfully else 'Fallback/Error'}")

    return render_template('about.html',
                           ai_about_intro=ai_about_intro, # Sẽ là None hoặc fallback nếu AI lỗi
                           published_stories=published_stories,
                           format_currency=format_currency)


@main_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    """Trang liên hệ: Xử lý form, lưu DB và gửi email."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    form = ContactForm()
    if form.validate_on_submit():
        logger.info(f"Processing contact form submission from: {form.email.data}")
        # 1. Tạo đối tượng ContactMessage
        message = ContactMessage(
            name=form.name.data,
            email=form.email.data,
            subject=form.subject.data,
            message=form.message.data,
            is_read=False # Mặc định là chưa đọc
            # created_at tự động gán
        )
        try:
            # 2. Lưu vào Database
            db.session.add(message)
            db.session.commit()
            logger.info(f"Contact message (ID: {message.id}) saved successfully.")

            # 3. Gửi Email Thông Báo cho Admin
            email_sent = send_contact_notification_email(message)
            if not email_sent:
                # Chỉ cảnh báo, không nên báo lỗi cho người dùng nếu chỉ email thất bại
                flash('Tin nhắn của bạn đã được gửi tới quản trị viên. Cảm ơn!', 'success')
                logger.warning(f"Contact message saved (ID: {message.id}) but failed to send email notification.")
            else:
                flash('Tin nhắn của bạn đã được gửi. Xin cảm ơn!', 'success')

            return redirect(url_for('main.contact')) # Redirect để tránh gửi lại form

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving contact message or sending email: {e}", exc_info=True)
            flash('Rất tiếc, đã có lỗi xảy ra khi gửi tin nhắn của bạn. Vui lòng thử lại.', 'danger')
            # Render lại form với dữ liệu đã nhập khi có lỗi DB

    elif request.method == 'POST':
         logger.warning(f"Contact form validation failed: {form.errors}")
         flash('Thông tin nhập không hợp lệ, vui lòng kiểm tra lại các trường.', 'warning')

    return render_template('contact.html', form=form) # format_currency không cần thiết ở đây

@main_bp.route('/locations')
def locations():
    """Trang hiển thị địa điểm."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Accessing locations page.")
    try:
        active_locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    except Exception as e:
        logger.error(f"Error fetching locations: {e}", exc_info=True)
        active_locations = []
        flash("Lỗi khi tải danh sách địa điểm.", "danger")

    # --- CHỌN MAP CHÍNH ĐỂ HIỂN THỊ ---
    # Ưu tiên hiển thị map của địa điểm đầu tiên có URL nhúng
    # Hoặc dùng một map cố định nếu không có địa điểm nào có URL
    main_map_url = None
    if active_locations and active_locations[0].map_embed_url:
         main_map_url = active_locations[0].map_embed_url
    else:
         # Thay bằng URL map mặc định của khu vực bạn
         main_map_url = "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3919.447169714984!2d106.69543627504645!3d10.777044589371742!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x31752f38f9ed887b%3A0x14aded5703d96ae7!2zRGluaCDEkOG7mWMgTOG6rXA!5e0!3m2!1sen!2s!4v1682421296098!5m2!1sen!2s" # Thay URL mẫu này

    return render_template('locations.html',
                           locations=active_locations,
                           main_map_url=main_map_url) # Truyền URL map chính


@main_bp.route('/product/<int:product_id>', methods=['GET', 'POST'])
def product_detail(product_id):
    """Trang chi tiết sản phẩm và xử lý gửi review."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info(f"Accessing product detail page for ID: {product_id}")

    product = Product.query.get_or_404(product_id) # 404 nếu không tìm thấy SP

    # Lấy thông tin liên quan và tính toán (bao trong try-except tổng)
    reviews = []
    related_products = []
    avg_rating = 0
    ai_product_description = product.description # Dùng mô tả gốc trước

    try:
        # Lấy reviews (có thể thêm filter is_approved nếu có)
        reviews = Review.query.filter_by(product_id=product_id)\
                              .order_by(Review.created_at.desc())\
                              .all()
        logger.debug(f"Found {len(reviews)} reviews for product {product_id}.")

        # Lấy sản phẩm liên quan
        related_products = Product.query.filter(
            Product.category_id == product.category_id,
            Product.id != product_id,
            Product.is_available == True
        ).order_by(func.random()).limit(4).all() # Lấy ngẫu nhiên 4 SP cùng loại
        logger.debug(f"Found {len(related_products)} related products.")

        # Tính rating trung bình
        avg_rating_result = db.session.query(func.avg(Review.rating))\
            .filter(Review.product_id == product_id).scalar()
        avg_rating = round(avg_rating_result, 1) if avg_rating_result is not None else 0.0
        logger.debug(f"Average rating calculated: {avg_rating}")

        # Tạo mô tả bằng AI nếu cần
        if not product.description or len(product.description.strip()) < 10:
            logger.info(f"Generating AI description for product {product_id} (existing description short or empty).")
            try:
                product_data = {
                    'name': product.name,
                    'price': product.price,
                    'category': product.category.name if product.category else 'Đồ uống'
                }
                ai_description_result = generate_product_description(product_data)
                if ai_description_result and "Lỗi" not in ai_description_result and "cập nhật" not in ai_description_result:
                    ai_product_description = ai_description_result # Chỉ gán nếu AI thành công
                    logger.info("AI description generated.")
                else:
                    logger.warning("AI description generation failed or returned fallback. Using original description.")
            except Exception as ai_e:
                logger.error(f"Error calling generate_product_description for product {product.id}: {ai_e}", exc_info=True)
                # Giữ mô tả gốc nếu AI lỗi
    except Exception as e:
        logger.error(f"Error fetching related data for product detail {product_id}: {e}", exc_info=True)
        flash("Lỗi khi tải chi tiết sản phẩm.", "danger")


    # Xử lý form Review
    review_form = ReviewForm()
    if review_form.validate_on_submit():
        logger.info(f"Processing review submission for product {product_id}")
        if not current_user.is_authenticated:
            flash('Bạn cần đăng nhập để viết đánh giá.', 'warning')
            return redirect(url_for('auth.login', next=request.url))

        if current_user.is_comment_banned:
            logger.warning(f"Review submission blocked for banned user: {current_user.id}")
            flash('Tài khoản của bạn đã bị hạn chế quyền bình luận.', 'danger')
            return redirect(url_for('main.product_detail', product_id=product_id))

        existing_review = Review.query.filter_by(user_id=current_user.id, product_id=product_id).first()
        if existing_review:
            logger.info(f"User {current_user.id} already reviewed product {product_id}. Showing info message.")
            flash('Bạn đã đánh giá sản phẩm này rồi.', 'info')
            return redirect(url_for('main.product_detail', product_id=product_id))

        # ====> THÊM DÒNG KHỞI TẠO NÀY <====
        submitted_content = None
        # ====> VÀ CÓ THỂ BỌC TRONG TRY-EXCEPT CHO AN TOÀN HƠN <====
        try:
            submitted_content = review_form.content.data
            logger.debug(f"Submitted review content received: '{submitted_content[:50]}...'")
        except AttributeError as attr_err:
             logger.error(f"AttributeError accessing review_form.content.data: {attr_err}", exc_info=True)
             flash('Lỗi xử lý form bình luận.', 'danger')
             # Return hoặc render lại template ngay tại đây
             return redirect(url_for('main.product_detail', product_id=product_id)) # Redirect cho đơn giản

        # Check lại xem submitted_content có giá trị không sau khi thử gán
        if submitted_content is None:
            logger.error("Failed to assign submitted_content, maybe form error.")
            flash("Không thể lấy nội dung bình luận từ form.", "danger")
            return redirect(url_for('main.product_detail', product_id=product_id)) # Redirect


        is_placeholder = "[AI ĐÃ LỌC]" # Placeholder cũ, không cần đổi

        # *** KIỂM TRA NỘI DUNG VÀ XỬ LÝ CẢNH BÁO/CẤM ***
        user_warning_count = current_user.review_warning_count or 0
        user_ban_status_changed = False
        # Nội dung placeholder mới để lưu DB, tránh trùng với check is_placeholder
        warning_placeholder_db = f"Ngôn từ không phù hợp ({datetime.utcnow().strftime('%d/%m %H:%M')}) [AI Đã Lọc]"

        if submitted_content == is_placeholder: # Chỗ này kiểm tra nội dung *trong form*
            logger.warning(f"Toxic review content placeholder received from user {current_user.id} for product {product_id}.")
            user_warning_count += 1
            current_user.review_warning_count = user_warning_count
            flash(f'Ngôn từ trong bình luận của bạn không phù hợp. Đây là cảnh báo lần {user_warning_count}.', 'warning')
            warning_limit = current_app.config.get('REVIEW_WARNING_LIMIT', 4)
            if user_warning_count >= warning_limit:
                current_user.is_comment_banned = True
                user_ban_status_changed = True
                logger.error(f"User {current_user.id} reached warning limit ({user_warning_count}/{warning_limit}) and is now BANNED from commenting.")
                flash('Bạn đã vượt quá số lần cảnh báo về ngôn từ. Tài khoản của bạn sẽ bị hạn chế quyền bình luận.', 'danger')
            else:
                logger.info(f"User {current_user.id} warning count updated to {user_warning_count}/{warning_limit}.")

            content_to_save = warning_placeholder_db # <<< LƯU placeholder này vào DB
            is_toxic_save = True
            original_content_to_save = request.form.get('original_content_hidden') # Giả sử bạn có field ẩn này

        else: # Bình luận bình thường (hoặc AI lọc phía server)
            content_to_save = submitted_content
            is_toxic_save = False # Mặc định là không toxic ban đầu
            original_content_to_save = None
            sentiment_label, sentiment_score = None, None
            try:
                analysis_result = analyze_review_sentiment(content_to_save)
                sentiment_label = analysis_result.get('sentiment_label')
                sentiment_score = analysis_result.get('sentiment_score')
                is_toxic_save = analysis_result.get('is_toxic', False)
                if is_toxic_save: # Nếu check phía server vẫn thấy toxic
                    content_to_save = f"Ngôn từ không phù hợp ({datetime.utcnow().strftime('%d/%m %H:%M')}) [AI Lọc Server]"
                    original_content_to_save = submitted_content # Lưu nội dung gốc nếu server lọc
                    logger.warning(f"Review content by user {current_user.id} flagged toxic by server-side check.")
            except Exception as ai_analyze_err:
                logger.error(f"Error analyzing sentiment for review (Prod {product_id}, User {current_user.id}): {ai_analyze_err}", exc_info=True)

        # Tạo review mới với nội dung đã xử lý
        new_review = Review(
            product_id=product_id,
            rating=review_form.rating.data,
            content=content_to_save,
            original_content=original_content_to_save, # Lưu nội dung gốc nếu có
            is_toxic_guess=is_toxic_save,
            user_id=current_user.id,
            sentiment_label=sentiment_label, # Lưu label
            sentiment_score=sentiment_score # Lưu score      
        )
        # ... (phần commit và flash/redirect như cũ) ...
        try:
            db.session.add(new_review)
            # Nếu có thay đổi trạng thái cấm hoặc warning count, user cũng cần được add vào session để commit
            # Cần lấy lại count MỚI NHẤT của user để so sánh
            user_db_warnings = db.session.get(User, current_user.id).review_warning_count or 0
            if user_warning_count > user_db_warnings or user_ban_status_changed:
                 # Query lại user từ DB để đảm bảo lấy bản mới nhất trước khi sửa
                 user_to_update = db.session.get(User, current_user.id)
                 user_to_update.review_warning_count = user_warning_count
                 user_to_update.is_comment_banned = user_to_update.is_comment_banned or user_ban_status_changed
                 db.session.add(user_to_update)

            db.session.commit()
            logger.info(f"Successfully saved new review (Toxic: {is_toxic_save}) and updated user status (if any) for user {current_user.id}.")

            # Điều chỉnh flash success dựa trên kết quả cuối cùng
            if not is_toxic_save:
                 flash('Cảm ơn bạn đã đánh giá!', 'success')
            # Không cần flash success nếu là toxic vì đã flash warning trước đó

            return redirect(url_for('main.product_detail', product_id=product_id))

        except Exception as e:
            db.session.rollback() # Rollback tất cả nếu có lỗi DB
            logger.error(f"Error saving review or updating user status for product {product_id}: {e}", exc_info=True)
            flash('Lỗi khi gửi đánh giá hoặc cập nhật tài khoản. Vui lòng thử lại.', 'danger')


    elif request.method == 'POST':
        logger.warning(f"Review form validation failed for product {product_id}: {review_form.errors}")
        flash("Nội dung đánh giá không hợp lệ. Vui lòng kiểm tra lại.", 'warning')

    # ===> ĐẢM BẢO TRUYỀN ĐỦ BIẾN VÀO ĐÂY <====
    return render_template('product_detail.html',
                           product=product,
                           reviews=reviews,
                           related_products=related_products,
                           avg_rating=avg_rating,
                           format_currency=format_currency,
                           review_form=review_form,
                           ai_product_description=ai_product_description,
                           max=max) # Biến max đã thêm từ lần sửa trước


# === Error Handlers ===

@main_bp.app_errorhandler(404)
def page_not_found(e):
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.warning(f"Page not found (404): {request.path}")
    # Không cần format_currency nếu template 404 không dùng
    return render_template('errors/404.html'), 404

@main_bp.app_errorhandler(500)
def internal_server_error(e):
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.error(f"Internal Server Error (500): {e}", exc_info=True)
    try:
        # Luôn rollback để tránh session bị lỗi
        db.session.rollback()
        logger.info("Database session rolled back due to 500 error.")
    except Exception as db_err:
        logger.error(f"Error during rollback after 500 error: {db_err}", exc_info=True)
    # Không cần format_currency nếu template 500 không dùng
    return render_template('errors/500.html'), 500

@main_bp.route('/promotions')
def promotions_page():
    """Trang hiển thị tất cả khuyến mãi (active, upcoming, expired)."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Accessing ALL promotions page.")
    now = datetime.utcnow() # Sử dụng UTC để so sánh nhất quán với DB (nếu DB dùng UTC)
                            # Hoặc timezone của server/quán bạn nếu DB lưu local time.
    active_promotions_list = []
    upcoming_promotions_list = []
    expired_or_inactive_promotions_list = []

    try:
        # Query tất cả khuyến mãi, sắp xếp để dễ phân loại và hiển thị
        # Ưu tiên sắp xếp theo trạng thái, rồi đến ngày kết thúc/bắt đầu
        all_promotions = Promotion.query.order_by(
            Promotion.is_active.desc(), # Active lên đầu
            Promotion.start_date.asc(), # Sắp tới gần nhất lên đầu (cho upcoming)
            Promotion.end_date.desc()   # Sắp hết hạn gần nhất lên đầu (cho active)
        ).all()

        for promo in all_promotions:
            if promo.is_active and promo.start_date <= now <= promo.end_date:
                active_promotions_list.append(promo)
            elif promo.is_active and promo.start_date > now:
                upcoming_promotions_list.append(promo)
            else: # Bao gồm is_active == False HOẶC đã hết hạn (promo.end_date < now)
                expired_or_inactive_promotions_list.append(promo)
        
        # Sắp xếp lại các list con nếu cần (ví dụ: active thì sắp hết hạn lên đầu)
        active_promotions_list.sort(key=lambda p: p.end_date) 
        upcoming_promotions_list.sort(key=lambda p: p.start_date)
        # expired_or_inactive_promotions_list.sort(key=lambda p: p.end_date, reverse=True) # Mới hết hạn lên đầu

    except Exception as e:
        logger.error(f"Error fetching all promotions for display: {e}", exc_info=True)
        flash("Lỗi khi tải danh sách khuyến mãi.", "danger")

    return render_template('promotions.html',
                           active_promotions=active_promotions_list,
                           upcoming_promotions=upcoming_promotions_list,
                           expired_or_inactive_promotions=expired_or_inactive_promotions_list,
                           format_currency=format_currency, # Vẫn truyền format_currency
                           title="Tất cả Ưu đãi",
                           now_utc=now # Truyền now_utc vào template để so sánh
                           )

@main_bp.route('/api/menu-products')
def api_menu_products():
    """API trả về HTML cho lưới sản phẩm dựa trên filter/sort/search."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    try:
        category_id = request.args.get('category_id', type=int)
        search_term = request.args.get('q', '').strip()
        sort_by = request.args.get('sort', 'name')

        logger.info(f"API Request: Category={category_id}, Search='{search_term}', Sort='{sort_by}'")

        products_query = Product.query.filter(Product.is_available == True)

        if category_id:
            # Tối ưu: Có thể chỉ cần join nếu search theo category name, ở đây filter ID là đủ
            products_query = products_query.filter(Product.category_id == category_id)

        if search_term:
            products_query = products_query.join(Category).filter( # Join để search cả tên Category
                or_(
                    Product.name.ilike(f"%{search_term}%"),
                    Category.name.ilike(f"%{search_term}%"),
                    Product.description.ilike(f"%{search_term}%") # Thêm search description
                )
            )

        # Sắp xếp
        if sort_by == 'price_asc':
            products_query = products_query.order_by(Product.price.asc(), Product.name.asc())
        elif sort_by == 'price_desc':
            products_query = products_query.order_by(Product.price.desc(), Product.name.asc())
        elif sort_by == 'rating': # Thêm sort theo rating nếu muốn (cần join hoặc subquery)
             # Placeholder: Sắp xếp theo rating cần phức tạp hơn (tính avg rating)
            products_query = products_query.order_by(Product.name.asc()) # Tạm sort theo tên
        else: # Default sort by name
            products_query = products_query.order_by(Product.name.asc())

        products = products_query.all() # Lấy hết kết quả phù hợp
        count = len(products)
        logger.info(f"API Found {count} products matching criteria.")

        # === Render TEMPLATE PARTIAL ===
        # Tạo template mới chỉ chứa lưới sản phẩm
        # Truyền các hàm cần thiết vào context của render_template_string hoặc partial template
        html_content = render_template(
            '_product_grid.html', # Tên file partial mới
            products=products,
            format_currency=format_currency # Cần truyền lại filter/function
        )

        return jsonify({'success': True, 'html': html_content, 'count': count})

    except Exception as e:
        logger.error(f"API Error fetching menu products: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Lỗi tải sản phẩm.'}), 500

@main_bp.route('/api/product/<int:product_id>')
def api_product_detail(product_id):
    """API trả về dữ liệu JSON cho một sản phẩm để xem nhanh."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    try:
        # Sử dụng joinedload để lấy Category cùng lúc, tránh query riêng
        # Cũng có thể thêm joinedload(Product.inventory) nếu modal cần hiển thị tồn kho
        product = Product.query.options(
                      joinedload(Product.category)
                  ).get(product_id) # Dùng get() để trả None nếu không thấy

        if product and product.is_available: # Chỉ trả về nếu SP tồn tại và CÓ SẴN
            product_data = {
                'id': product.id,
                'name': product.name,
                'description': product.description or "Chưa có mô tả chi tiết.", # Mô tả fallback
                'price': product.price,
                'formatted_price': format_currency(product.price), # Gửi giá đã format
                'image_url': product.image_url or url_for('static', filename='images/default_product_large.png'), # Ảnh lớn hơn
                'category_name': product.category.name if product.category else 'Khác',
                'is_featured': product.is_featured
                # Thêm các trường khác nếu modal cần: avg_rating, stock,...
                # 'stock_quantity': product.inventory.quantity if product.inventory else 0,
            }
            logger.info(f"API: Successfully fetched product details for ID {product_id}")
            return jsonify({'success': True, 'product': product_data})
        elif product: # SP tồn tại nhưng không có sẵn
             logger.warning(f"API: Product ID {product_id} found but is unavailable.")
             return jsonify({'success': False, 'message': 'Sản phẩm này hiện đang tạm hết hàng.'}), 404
        else: # Không tìm thấy SP
            logger.warning(f"API: Product ID {product_id} not found.")
            return jsonify({'success': False, 'message': 'Không tìm thấy sản phẩm.'}), 404

    except Exception as e:
        logger.error(f"API Error fetching product detail for ID {product_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Lỗi máy chủ khi lấy thông tin sản phẩm.'}), 500