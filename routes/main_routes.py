# /routes/main_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import current_user, login_required
from sqlalchemy import func
from datetime import datetime

# Đảm bảo import các thành phần cần thiết từ project của bạn
# Đường dẫn có thể thay đổi tùy cấu trúc thư mục
try:
    from models import Product, Category, ContactMessage, Review, User, InterestingStory, db
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

main_bp = Blueprint('main', __name__)

# === Routes ===

@main_bp.route('/')
def loading():
    """Trang loading ban đầu."""
    # Trang này thường không có logic phức tạp
    return render_template('loading.html') # Đảm bảo bạn có template loading.html

@main_bp.route('/home')
def index():
    """Trang chủ chính của website."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Accessing home page.")
    try:
        featured_products = Product.query.filter_by(
            is_featured=True,
            is_available=True # Chỉ lấy sản phẩm có sẵn
        ).order_by(func.random()).limit(6).all() # Lấy ngẫu nhiên hoặc theo tiêu chí khác

        categories = Category.query.order_by(Category.name).all()
    except Exception as e:
        logger.error(f"Error fetching data for home page: {e}", exc_info=True)
        featured_products = []
        categories = []
        flash("Lỗi khi tải dữ liệu trang chủ.", "danger")

    return render_template(
        'index.html',
        featured_products=featured_products,
        categories=categories,
        format_currency=format_currency # Truyền hàm format vào template
    )

@main_bp.route('/menu')
def menu():
    """Trang hiển thị thực đơn, có lọc và tìm kiếm."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    try:
        category_id = request.args.get('category', type=int)
        search_term = request.args.get('q', '')
        sort_by = request.args.get('sort', 'name') # Mặc định sort theo tên

        # Bắt đầu query sản phẩm có sẵn
        products_query = Product.query.filter_by(is_available=True)
        current_category = None

        # Lọc theo category
        if category_id:
            current_category = Category.query.get(category_id) # Dùng get thay get_or_404 để xử lý mềm dẻo hơn
            if current_category:
                products_query = products_query.filter_by(category_id=category_id)
                logger.info(f"Filtering menu by category: {current_category.name} (ID: {category_id})")
            else:
                 flash(f"Danh mục ID {category_id} không tồn tại.", "warning")
                 # Optionally redirect or just show all products

        # Lọc theo search term
        if search_term:
            logger.info(f"Searching menu for term: '{search_term}'")
            products_query = products_query.filter(Product.name.ilike(f"%{search_term}%"))

        # Sắp xếp kết quả
        if sort_by == 'price_asc':
            products_query = products_query.order_by(Product.price.asc(), Product.name.asc())
        elif sort_by == 'price_desc':
            products_query = products_query.order_by(Product.price.desc(), Product.name.asc())
        else: # Default sort by name
            products_query = products_query.order_by(Product.name.asc())

        products = products_query.all()
        categories = Category.query.order_by(Category.name).all()

    except Exception as e:
        logger.error(f"Error fetching data for menu page: {e}", exc_info=True)
        products = []
        categories = []
        current_category = None
        flash("Lỗi khi tải dữ liệu thực đơn.", "danger")

    return render_template('menu.html',
                           products=products,
                           categories=categories,
                           current_category=current_category,
                           format_currency=format_currency,
                           search_term=search_term,
                           sort_by=sort_by)


@main_bp.route('/menu/search_suggestions')
def menu_search_suggestions():
    """API trả về gợi ý tìm kiếm sản phẩm."""
    term = request.args.get('term', '').strip()
    suggestions = []
    if len(term) >= 1: # Bắt đầu tìm khi có ít nhất 1 ký tự
        try:
            query = Product.query.filter(
                Product.name.ilike(f"%{term}%"),
                Product.is_available == True
            ).order_by(func.length(Product.name)).limit(7).all() # Giới hạn và sắp xếp theo độ dài tên (ngắn hơn có thể ưu tiên)

            suggestions = [{"id": p.id, "name": p.name} for p in query]
        except Exception as e:
            logger = current_app.logger if current_app else logging.getLogger(__name__)
            logger.error(f"Error fetching search suggestions for term '{term}': {e}", exc_info=False) # Log lỗi ngắn gọn
            # Không cần trả lỗi về client, chỉ trả list rỗng

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
    """Trang liên hệ."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    form = ContactForm()
    if form.validate_on_submit():
        logger.info(f"Received contact form submission from: {form.email.data}")
        message = ContactMessage(
            name=form.name.data,
            email=form.email.data,
            subject=form.subject.data,
            message=form.message.data
        )
        try:
            db.session.add(message)
            db.session.commit()
            logger.info("Contact message saved successfully.")
            flash('Tin nhắn của bạn đã được gửi. Xin cảm ơn!', 'success') # Dùng tiếng Việt
            return redirect(url_for('main.contact')) # Redirect để tránh gửi lại form
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving contact message: {e}", exc_info=True)
            flash('Lỗi khi gửi tin nhắn. Vui lòng thử lại.', 'danger')
            # Render lại form với dữ liệu đã nhập

    elif request.method == 'POST':
         logger.warning(f"Contact form validation failed: {form.errors}")
         flash('Thông tin nhập không hợp lệ, vui lòng kiểm tra lại.', 'warning')


    return render_template('contact.html', form=form, format_currency=format_currency)

@main_bp.route('/locations')
def locations():
    """Trang hiển thị địa điểm."""
    # Hiện tại là trang tĩnh, có thể mở rộng để lấy từ DB
    return render_template('locations.html', format_currency=format_currency)


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

        existing_review = Review.query.filter_by(user_id=current_user.id, product_id=product_id).first()
        if existing_review:
            logger.info(f"User {current_user.id} already reviewed product {product_id}. Showing info message.")
            flash('Bạn đã đánh giá sản phẩm này rồi.', 'info')
            return redirect(url_for('main.product_detail', product_id=product_id))

        # Tạo review mới
        new_review = Review(
            product_id=product_id,
            rating=review_form.rating.data,
            content=review_form.content.data,
            user_id=current_user.id
        )
        sentiment_saved = False # Cờ đánh dấu lưu sentiment thành công
        try:
            db.session.add(new_review)
            db.session.flush() # Flush để lấy new_review.id (tạm thời chưa commit hẳn)
            logger.info(f"Review object created (ID placeholder: {new_review.id}), attempting sentiment analysis.")

            # Phân tích cảm xúc
            sentiment_result = None
            try:
                sentiment_result = analyze_review_sentiment(new_review.content)
            except Exception as ai_error:
                logger.error(f"Error calling analyze_review_sentiment for new review: {ai_error}", exc_info=True)

            if sentiment_result:
                new_review.sentiment_label = sentiment_result.get('sentiment_label')
                new_review.sentiment_score = sentiment_result.get('sentiment_score')
                logger.info(f"Sentiment result: Label={new_review.sentiment_label}, Score={new_review.sentiment_score}")

            # Commit tất cả thay đổi (review và sentiment nếu có)
            db.session.commit()
            logger.info(f"Successfully saved new review (ID: {new_review.id}) and sentiment data (if available).")
            sentiment_saved = True # Đánh dấu đã commit thành công

            flash('Cảm ơn bạn đã đánh giá!', 'success')
            return redirect(url_for('main.product_detail', product_id=product_id))

        except Exception as e:
            db.session.rollback() # Rollback nếu có lỗi ở bất kỳ đâu trong khối try
            logger.error(f"Error saving review or sentiment for product {product_id}: {e}", exc_info=True)
            flash('Lỗi khi gửi đánh giá. Vui lòng thử lại.', 'danger')
            # Không redirect, render lại trang với form lỗi

    elif request.method == 'POST':
        # Trường hợp POST nhưng form không hợp lệ
        logger.warning(f"Review form validation failed for product {product_id}: {review_form.errors}")
        flash("Nội dung đánh giá không hợp lệ. Vui lòng kiểm tra lại.", 'warning')

    # Render template cho GET hoặc POST thất bại
    return render_template('product_detail.html',
                           product=product,
                           reviews=reviews,
                           related_products=related_products,
                           avg_rating=avg_rating,
                           format_currency=format_currency,
                           review_form=review_form, # Truyền form để hiển thị (và lỗi validation nếu có)
                           ai_product_description=ai_product_description)


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