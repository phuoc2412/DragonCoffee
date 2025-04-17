# /routes/ai_routes.py

"""
Dragon Coffee Shop - AI Routes
Routes for AI-powered features
"""

from flask import (Blueprint, render_template, redirect, url_for,
                   request, jsonify, session, flash, current_app) # Đã thêm current_app
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
# Import models trực tiếp nếu cấu trúc dự án của bạn như vậy
from models import db, Product, Review, User, Category, Order
from sqlalchemy import func
import os
from datetime import datetime, timedelta
import json
from app import db
from ai_services import get_response



# --- Import các hàm từ ai_services (THÔNG QUA __init__.py) ---
# Các hàm này đã được alias trong __init__.py để trỏ đến logic custom nếu cần
from ai_services import (
    get_recommendations,
    analyze_review_sentiment,
    predict_product_demand,
    get_inventory_recommendations,
    process_product_image,
    get_response,               # <-- Đã được alias trỏ đến get_custom_chatbot_response
    handle_order,               # <-- Đã được alias trỏ đến handle_custom_order
    generate_product_description,
    generate_promotion,
    generate_social_post
    # Import các hàm generate khác nếu bạn dùng trong file này
)
# Import các hàm xử lý ảnh cụ thể nếu cần dùng trực tiếp
from ai_services.image_similarity import extract_features, get_similar_products_by_feature_vector

# Import các hàm tiện ích khác
from utils import format_currency

# --- Khởi tạo Blueprint ---
ai_bp = Blueprint('ai', __name__, url_prefix='/ai') # Thêm prefix /ai

# === Routes ===

@ai_bp.route('/recommendations')
def recommendations():
    """Show personalized product recommendations"""
    # Log bắt đầu xử lý route
    logger = current_app.logger
    logger.info("Processing /ai/recommendations route...")

    personalized_recommendations = []
    popular_products = []
    similar_products = []
    last_viewed = None
    error_message = None

    try:
        # Get popular products for everyone
        logger.info("Fetching popular product recommendations...")
        popular_products = get_recommendations(limit=6)
        logger.info(f"Found {len(popular_products)} popular products.")

        # Get personalized recommendations for logged in users
        if current_user.is_authenticated:
            logger.info(f"Fetching personalized recommendations for user ID: {current_user.id}...")
            personalized_recommendations = get_recommendations(user_id=current_user.id, limit=6)
            logger.info(f"Found {len(personalized_recommendations)} personalized recommendations.")

        # Get similar products based on last viewed product
        if 'last_viewed_product' in session:
            last_viewed_id = session['last_viewed_product']
            logger.info(f"Fetching similar products based on last viewed ID: {last_viewed_id}...")
            last_viewed = Product.query.get(last_viewed_id)
            if last_viewed:
                similar_products = get_recommendations(product_id=last_viewed_id, limit=4)
                logger.info(f"Found {len(similar_products)} similar products to '{last_viewed.name}'.")
            else:
                 logger.warning(f"Last viewed product ID {last_viewed_id} not found in DB.")
                 session.pop('last_viewed_product', None) # Xóa khỏi session nếu không tìm thấy

    except Exception as e:
        logger.error(f"Error fetching recommendations: {e}", exc_info=True)
        error_message = "Lỗi khi tải gợi ý sản phẩm. Vui lòng thử lại sau."
        flash(error_message, 'danger') # Thông báo lỗi cho người dùng

    return render_template(
        'recommendations.html', # Đảm bảo bạn có template này
        personalized_recommendations=personalized_recommendations,
        popular_products=popular_products,
        similar_products=similar_products,
        last_viewed=last_viewed,
        format_currency=format_currency,
        error_message=error_message
    )

# Route này có thể xung đột với /product/<id> của main_routes.
# Đảm bảo URL prefix '/ai' hoạt động hoặc đổi tên route/endpoint
@ai_bp.route('/product-view/<int:product_id>') # Đổi tên route để tránh trùng
def ai_product_detail_view(product_id):
    """Show product details with AI-enhanced features (alternative view maybe?)"""
    logger = current_app.logger
    logger.info(f"Processing /ai/product-view/{product_id} route...")

    product = Product.query.get_or_404(product_id)

    # Ghi log đã xem (nếu bạn muốn tách biệt view này)
    session['last_viewed_product'] = product_id

    # Các logic khác tương tự main.product_detail nhưng có thể thêm tính năng AI khác
    similar_products = []
    ai_product_description = ""
    avg_rating = 0
    error_message = None

    try:
        # Get similar products
        logger.info(f"Fetching similar products for product ID: {product_id}")
        similar_products = get_recommendations(product_id=product_id, limit=4)
        logger.info(f"Found {len(similar_products)} similar products.")

        # Tính rating trung bình
        avg_rating_result = db.session.query(func.avg(Review.rating))\
            .filter(Review.product_id == product_id).scalar()
        avg_rating = round(avg_rating_result, 1) if avg_rating_result is not None else 0
        logger.info(f"Calculated average rating: {avg_rating}")

        # Generate AI description if needed
        if not product.description or len(product.description.strip()) < 10:
            logger.info(f"Generating AI description for product ID: {product_id}")
            try:
                product_data = {
                    'name': product.name,
                    'price': product.price,
                    'category': product.category.name if product.category else 'Đồ uống'
                }
                ai_product_description = generate_product_description(product_data)
                logger.info(f"AI description generated successfully.")
            except Exception as ai_desc_e:
                logger.error(f"Error generating AI description for {product.id}: {ai_desc_e}", exc_info=True)
                ai_product_description = "Mô tả đang được cập nhật..." # Mô tả fallback
        else:
            logger.info(f"Using existing description for product ID: {product_id}")


    except Exception as e:
        logger.error(f"Error fetching AI-related data for product detail: {e}", exc_info=True)
        error_message = "Lỗi khi tải thông tin bổ sung cho sản phẩm."
        flash(error_message, 'danger')

    # !!! QUAN TRỌNG: Đổi tên template render về product_detail.html nếu bạn chỉ có 1 template
    return render_template(
        'product_detail.html', # Sử dụng template gốc
        product=product,
        similar_products=similar_products,
        ai_product_description=ai_product_description,
        avg_rating=avg_rating,
        format_currency=format_currency,
        error_message=error_message,
        # **Phải truyền review_form nếu template product_detail cần**
        review_form=None # Hoặc tạo instance ReviewForm() nếu cần
    )

# --- Route này không cần thiết nếu logic đã ở trong main_routes.py/product_detail ---
# Bạn nên giữ logic submit review ở route product_detail của main_bp
# Nếu vẫn muốn giữ ở đây, phải đổi endpoint gọi từ form submit review
# @ai_bp.route('/product/<int:product_id>/review', methods=['POST'])
# @login_required
# def add_review(product_id):
#     # ... (Logic xử lý review như cũ) ...

@ai_bp.route('/chatbot', methods=['GET'])
def chatbot_page():
    """Renders the chatbot interface page."""
    logger = current_app.logger
    logger.info("Accessing Chatbot page (/ai/chatbot).")
    # Biến now cần thiết cho template gốc
    now = datetime.now()
    return render_template('chatbot.html', now=now)

@ai_bp.route('/chatbot/api', methods=['POST'])
def chatbot_api():
    """API endpoint for chatbot communication (uses the custom chatbot)."""
    logger = current_app.logger
    data = request.get_json()
    if not data:
        logger.warning("Chatbot API called with no JSON data.")
        return jsonify({'success': False, 'message': 'Yêu cầu không hợp lệ'}), 400

    user_message = data.get('message', '').strip()
    session_id = data.get('session_id', session.get('sid')) # Dùng session ID của Flask nếu có

    if not user_message:
        logger.warning("Chatbot API called with empty message.")
        return jsonify({'success': False, 'message': 'Vui lòng nhập tin nhắn.'}), 400

    logger.info(f"Chatbot API received message: '{user_message[:50]}...' from session: {session_id}")

    try:
        # ====> GỌI HÀM get_response (ĐÃ ALIAS) TỪ __init__.py <====
        # db.session được truyền ngầm vào get_custom_chatbot_response khi cần
        bot_response_data = get_response(user_message, db.session, session_id)
        logger.info(f"Chatbot API generated response. Intent: {bot_response_data.get('intent')}")

        # Trả về kết quả (giữ nguyên logic tạo payload)
        response_payload = {
            'success': bot_response_data.get('success', False), # Lấy trạng thái success từ kết quả
            'response': bot_response_data.get('response', 'Lỗi: Không có phản hồi.'),
            'intent': bot_response_data.get('intent', 'error'),
            'entities': bot_response_data.get('entities', {}),
            'image_results': bot_response_data.get('image_results', [])
        }
        # Dùng status code phù hợp nếu là lỗi
        status_code = 200 if response_payload['success'] else 500
        return jsonify(response_payload), status_code

    except Exception as e:
        logger.error(f"Error processing chatbot API request: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Lỗi xử lý từ chatbot.'}), 500

@ai_bp.route('/chatbot/upload-image', methods=['POST'])
def chatbot_upload_image():
    """Handles image uploads from the chatbot for visual search."""
    logger = current_app.logger
    logger.info("Processing chatbot image upload request...")

    if 'image_file' not in request.files:
        logger.warning("Chatbot image upload failed: 'image_file' not in request.files")
        return jsonify({'success': False, 'message': 'Không có file ảnh nào được gửi.'}), 400

    file = request.files['image_file']
    if file.filename == '':
        logger.warning("Chatbot image upload failed: No file selected.")
        return jsonify({'success': False, 'message': 'Bạn chưa chọn file ảnh.'}), 400

    # Kiểm tra đuôi file
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    filename = secure_filename(file.filename) # Làm sạch tên file
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
         logger.warning(f"Chatbot image upload failed: Invalid file type '{filename}'")
         return jsonify({'success': False, 'message': 'Định dạng ảnh không hợp lệ (png, jpg, jpeg, gif, webp).'}), 400

    try:
        image_bytes = file.read() # Đọc dữ liệu file vào bytes
        logger.info(f"Received image '{filename}', size: {len(image_bytes)} bytes for visual search.")

        # 1. Trích xuất đặc trưng từ ảnh được upload
        features = extract_features(image_bytes)
        if features is None:
            logger.error("Chatbot image upload: Feature extraction failed.")
            return jsonify({'success': False, 'message': 'Không thể xử lý ảnh của bạn.'}), 500
        logger.info("Image features extracted successfully.")

        # 2. Tìm kiếm sản phẩm tương đồng dựa trên vector đặc trưng
        # Hàm helper find_similar_products đã được định nghĩa bên dưới
        similar_products_data = find_similar_products(features) # Gọi hàm tìm kiếm
        logger.info(f"Found {len(similar_products_data)} visually similar products.")

        # 3. Trả kết quả về cho client (chatbot UI)
        return jsonify({
            'success': True,
            'message': 'Đã xử lý ảnh, đây là kết quả tương đồng:' if similar_products_data else 'Đã xử lý ảnh nhưng không tìm thấy sản phẩm tương đồng.',
            'image_results': similar_products_data # Trả về list kết quả (có thể rỗng)
        })

    except Exception as e:
        logger.error(f"Error processing uploaded image for chatbot: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Lỗi máy chủ khi xử lý ảnh.'}), 500

# --- Helper function: Tìm và định dạng sản phẩm tương đồng (GIỮ NGUYÊN hoặc chuyển vào module khác) ---
def find_similar_products(feature_vector, top_n=3):
    """Finds similar products based on feature vector and formats the results."""
    logger = current_app.logger
    try:
        # Gọi hàm cốt lõi từ module image_similarity
        similar_raw = get_similar_products_by_feature_vector(feature_vector, top_n * 2)
        formatted_results = []

        if not similar_raw:
            logger.info("No raw similar products found from vector search.")
            return []

        product_ids = [item['product_id'] for item in similar_raw]
        logger.debug(f"Product IDs from similarity search: {product_ids}")

        # Query thông tin các sản phẩm trong một lần
        products_dict = {p.id: p for p in Product.query.filter(Product.id.in_(product_ids), Product.is_available == True).all()}
        logger.debug(f"Found {len(products_dict)} available products in DB matching IDs.")

        # Tạo URL và định dạng kết quả (cần app context)
        # Bỏ qua with current_app.app_context() vì hàm này thường được gọi từ route đã có context
        for item in similar_raw:
            product = products_dict.get(item['product_id'])
            # Chỉ thêm nếu sản phẩm tồn tại, có sẵn và chưa đủ số lượng kết quả
            if product and len(formatted_results) < top_n:
                try:
                    image_url_val = product.image_url or url_for('static', filename='images/default_product.png')
                    product_url_val = url_for('main.product_detail', product_id=product.id) # Link đến trang chi tiết của main
                    formatted_results.append({
                         "id": product.id,
                         "name": product.name,
                         "image_url": image_url_val,
                         "product_url": product_url_val,
                         "similarity": round(item.get('similarity', 0.0), 3) # Làm tròn điểm tương đồng
                     })
                except Exception as url_e: # Bắt lỗi nếu url_for có vấn đề
                    logger.error(f"Error creating URL for product {product.id}: {url_e}", exc_info=False) # Không cần stack trace dài
                    # Vẫn có thể thêm sản phẩm mà không có URL nếu cần
                    formatted_results.append({
                         "id": product.id,
                         "name": product.name,
                         "image_url": product.image_url or "/static/images/default_product.png", # Fallback URL tĩnh
                         "product_url": "#",
                         "similarity": round(item.get('similarity', 0.0), 3)
                    })

        logger.info(f"Formatted {len(formatted_results)} similar products for response.")
        return formatted_results

    except Exception as e:
         logger.error(f"Error in find_similar_products helper: {e}", exc_info=True)
         return []
# --- End Helper function ---


# === Admin AI Routes (giữ nguyên logic, chỉ thêm logging và check quyền kỹ hơn) ===

@ai_bp.route('/admin/inventory/predictions')
@login_required
#@admin_required # Sử dụng decorator chuẩn của admin_routes nếu có
def inventory_predictions():
    """Show inventory predictions for admin"""
    logger = current_app.logger
    logger.info("Accessing admin inventory predictions page...")
    # Nên dùng decorator admin_required chuẩn ở đây
    if not current_user.is_authenticated or (not current_user.is_admin and not current_user.is_staff):
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        logger.warning(f"Unauthorized access attempt to admin inventory predictions by user: {current_user.email if current_user.is_authenticated else 'Anonymous'}")
        return redirect(url_for('main.index')) # Hoặc url_for('auth.login')

    recommendations = []
    error_message = None
    try:
        recommendations = get_inventory_recommendations(days=7)
        logger.info(f"Generated {len(recommendations)} inventory recommendations.")
    except Exception as e:
        logger.error(f"Error getting inventory recommendations: {e}", exc_info=True)
        error_message = "Lỗi khi tải dữ liệu dự đoán tồn kho."
        flash(error_message, 'danger')

    # --- Tên template có thể cần sửa lại cho phù hợp ---
    # return render_template('admin/inventory_predictions.html', ...)
    # Giả sử bạn render vào trang reports/inventory_report.html như code cũ:
    return render_template(
        'admin/reports/inventory_report.html', # Render template báo cáo tồn kho
        report_type='inventory', # Chỉ định type cho template
        recommendations=recommendations,
        error_message=error_message,
        days_predicted=7, # Truyền số ngày dự đoán
        # Các biến khác cần cho template reports (nếu có, ví dụ start/end date placeholder)
        start_date=(datetime.utcnow() - timedelta(days=6)).strftime('%Y-%m-%d'),
        end_date=datetime.utcnow().strftime('%Y-%m-%d'),
        period='week'
    )

@ai_bp.route('/admin/content/generate', methods=['GET', 'POST'])
@login_required
#@admin_required
def generate_content():
    """AI content generation for marketing"""
    logger = current_app.logger
    # Kiểm tra quyền
    if not current_user.is_authenticated or (not current_user.is_admin and not current_user.is_staff):
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        logger.warning(f"Unauthorized access attempt to admin content generator by user: {current_user.email if current_user.is_authenticated else 'Anonymous'}")
        # Nếu là request AJAX thì trả về JSON lỗi
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        return redirect(url_for('main.index')) # Hoặc trang login admin

    if request.method == 'POST':
        content_type = request.form.get('content_type')
        product_id = request.form.get('product_id')
        logger.info(f"Received request to generate content. Type: {content_type}, Product ID: {product_id}")

        product = None
        if product_id:
            product = Product.query.get(product_id)
            if not product:
                 logger.warning(f"Content generation request for non-existent product ID: {product_id}")
                 return jsonify({'success': False, 'message': f'Sản phẩm với ID {product_id} không tồn tại.'}), 404

        generated_content = None
        try:
            if content_type == 'product_description' and product:
                product_data = {'name': product.name, 'price': product.price, 'category': product.category.name if product.category else ''}
                generated_content = generate_product_description(product_data)
            elif content_type == 'promotion' and product:
                promo_data = {
                    'product_name': product.name,
                    'discount': request.form.get('discount', '15'), # Lấy discount từ form
                    'start_date': datetime.now(), # Dùng object datetime
                    'end_date': datetime.now() + timedelta(days=14)
                }
                generated_content = generate_promotion(promo_data)
            elif content_type == 'social_post' and product:
                post_data = {
                    'product_name': product.name,
                    'product_description': product.description or f'Trải nghiệm {product.name} tuyệt vời!'
                }
                generated_content = generate_social_post(post_data)
            else:
                 logger.warning(f"Invalid content type or missing product for generation: {content_type}")
                 return jsonify({'success': False, 'message': 'Loại nội dung không hợp lệ hoặc thiếu sản phẩm.'}), 400

            if generated_content:
                logger.info(f"Successfully generated content for type: {content_type}")
                return jsonify({'success': True, 'content': generated_content})
            else:
                 raise ValueError("Content generation returned empty result.")

        except Exception as e:
            logger.error(f"Error generating AI content (Type: {content_type}): {e}", exc_info=True)
            return jsonify({'success': False, 'message': f'Lỗi khi tạo nội dung: {str(e)}'}), 500

    # GET request
    try:
        products = Product.query.order_by(Product.name).all()
    except Exception as e:
        logger.error(f"Error fetching products for content generator form: {e}", exc_info=True)
        products = []
        flash("Lỗi khi tải danh sách sản phẩm.", "danger")

    # --- Cần template 'admin/content_generator.html' ---
    return render_template('admin/content_generator.html', products=products)

@ai_bp.route('/admin/product/image/process', methods=['POST'])
@login_required
#@admin_required
def process_image():
    """Process product image with AI"""
    logger = current_app.logger
    # Kiểm tra quyền
    if not current_user.is_authenticated or (not current_user.is_admin and not current_user.is_staff):
         logger.warning(f"Unauthorized access attempt to image processing by user: {current_user.email if current_user.is_authenticated else 'Anonymous'}")
         return jsonify({'success': False, 'message': 'Không có quyền truy cập'}), 403

    logger.info("Processing product image upload request...")

    if 'image' not in request.files:
        logger.warning("Image processing failed: 'image' not in request.files")
        return jsonify({'success': False, 'message': 'Không có file nào được tải lên'}), 400

    file = request.files['image']
    filename = secure_filename(file.filename) if file.filename else '' # Handle empty filename

    if not filename:
        logger.warning("Image processing failed: No file selected or invalid filename.")
        return jsonify({'success': False, 'message': 'Không có file nào được chọn'}), 400

    # Kiểm tra lại đuôi file
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        logger.warning(f"Image processing failed: Invalid file type '{filename}'")
        return jsonify({'success': False, 'message': 'Định dạng ảnh không hợp lệ (png, jpg, jpeg, gif, webp).'}), 400

    # --- Lưu file tạm thời để xử lý ---
    upload_folder = os.path.join(current_app.root_path, current_app.config.get('UPLOAD_FOLDER', 'static/uploads/temp'))
    os.makedirs(upload_folder, exist_ok=True)
    temp_filename = f"temp_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
    file_path = os.path.join(upload_folder, temp_filename)

    try:
        file.save(file_path)
        logger.info(f"Saved temporary image for processing: {file_path}")

        # Gọi hàm xử lý ảnh từ ai_services
        result = process_product_image(file_path)

        # Xóa file tạm sau khi xử lý xong
        try:
            os.remove(file_path)
            logger.info(f"Removed temporary image: {file_path}")
        except OSError as os_err:
            logger.error(f"Error removing temporary image {file_path}: {os_err}")

        # Kiểm tra kết quả từ process_product_image
        if isinstance(result, dict) and 'error' not in result:
            logger.info("Image processed successfully.")
            return jsonify({'success': True, 'result': result})
        else:
            logger.error(f"AI image processing failed. Result: {result}")
            return jsonify({'success': False, 'message': result.get('error', 'Lỗi không xác định khi xử lý ảnh.')}), 500

    except Exception as e:
        logger.error(f"Critical error during image processing: {e}", exc_info=True)
        # Cố gắng xóa file tạm nếu có lỗi
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except OSError: pass
        return jsonify({'success': False, 'message': f'Lỗi nghiêm trọng khi xử lý ảnh: {str(e)}'}), 500

# Hàm đăng ký blueprint này thường được gọi trong __init__.py của app hoặc file tạo app chính
# Để nó ở đây không gây hại nhưng không phải cách chuẩn
# def init_app(app):
#    app.register_blueprint(ai_bp, url_prefix='/ai')