# /routes/ai_routes.py

from flask import (Blueprint, render_template, redirect, url_for,
                   request, jsonify, session, flash, current_app, make_response)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from app import db
from models import Product, Review, User, Category, Order, Promotion, InventoryItem, Location
from sqlalchemy import func, or_, desc, cast, String
import os
from datetime import datetime, timedelta
import json
import uuid
import logging
from sqlalchemy.orm import joinedload
from ai_services import (
    get_response,
    handle_order,
    get_recommendations,
    analyze_review_sentiment,
    predict_product_demand,
    get_inventory_recommendations,
    process_product_image,
    extract_features,
    get_similar_products_by_feature_vector,
    generate_image_from_text_hf,
    save_generated_image,
    generate_product_description,
    generate_promotion,
    generate_social_post,
)
from utils import format_currency

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')

@ai_bp.route('/recommendations')
def recommendations():
    logger = current_app.logger
    logger.info("Processing /ai/recommendations...")
    personalized_recommendations = []
    popular_products = []
    similar_products = []
    last_viewed = None
    error_message = None
    try:
        popular_products = get_recommendations(limit=6)
        logger.info(f"Found {len(popular_products)} popular products for /ai/recommendations.")
        if current_user.is_authenticated:
            personalized_recommendations = get_recommendations(user_id=current_user.id, limit=6)
            logger.info(f"Found {len(personalized_recommendations)} personalized recommendations for user {current_user.id} at /ai/recommendations.")
        if 'last_viewed_product' in session:
            last_viewed_id = session['last_viewed_product']
            last_viewed = Product.query.get(last_viewed_id)
            if last_viewed:
                similar_products = get_recommendations(product_id=last_viewed_id, limit=4)
                logger.info(f"Found {len(similar_products)} similar products to {last_viewed.name} for /ai/recommendations.")
            else:
                logger.warning(f"Last viewed product ID {last_viewed_id} not found in database. Clearing from session.")
                session.pop('last_viewed_product', None)
    except Exception as e:
        logger.error(f"Error fetching recommendations for /ai/recommendations: {e}", exc_info=True)
        error_message="Lỗi tải gợi ý sản phẩm."
        flash(error_message,'danger')
    return render_template('recommendations.html',
                           personalized_recommendations=personalized_recommendations,
                           popular_products=popular_products,
                           similar_products=similar_products,
                           last_viewed=last_viewed,
                           format_currency=format_currency,
                           error_message=error_message)

@ai_bp.route('/chatbot')
def chatbot_page():
    logger = current_app.logger
    logger.info("Accessing Chatbot page (/ai/chatbot).")
    return render_template('chatbot.html')

@ai_bp.route('/chatbot/api', methods=['POST'])
def chatbot_api():
    logger = current_app.logger
    data = request.get_json()
    if not data or 'message' not in data:
        logger.warning("/ai/chatbot/api received invalid data.")
        return jsonify({'success': False, 'message': 'Yêu cầu không hợp lệ.'}), 400

    user_message = data.get('message', '').strip()
    session_id_frontend = data.get('session_id')
    current_flask_session_id = session.get('chatbot_sid')
    session_id = None

    if session_id_frontend and len(session_id_frontend) > 10:
        if current_flask_session_id != session_id_frontend:
            logger.warning(f"Flask session ID ({current_flask_session_id}) does not match frontend ID ({session_id_frontend[:8]}...). Trusting frontend.")
            session['chatbot_sid'] = session_id_frontend
        session_id = session_id_frontend
    elif current_flask_session_id:
         session_id = current_flask_session_id
         logger.debug(f"Using existing Flask session ID: {session_id[:8]}")
    else:
        session_id = str(uuid.uuid4())
        session['chatbot_sid'] = session_id
        session.permanent = True
        logger.info(f"Generated and stored new session ID: {session_id[:8]}")

    if not user_message:
        logger.warning(f"Empty message received for SID {session_id[:8]}.")
        return jsonify({'success': False, 'message': 'Vui lòng nhập tin nhắn.'}), 400

    logger.info(f"Processing message for SID {session_id[:8]}: '{user_message[:100]}...'")

    try:
        bot_response_data = get_response(user_message, db.session, session_id=session_id)
        response_payload = bot_response_data
        status_code = 200 if response_payload.get('success', True) else 500
        return jsonify(response_payload), status_code
    except Exception as e:
        logger.critical(f"Unexpected error processing chatbot API request for SID {session_id[:8]}: {e}", exc_info=True)
        try:
             db.session.rollback()
             logger.warning("Database session rolled back after unhandled chatbot error.")
        except Exception as rb_e:
             logger.error(f"Failed to rollback DB session after chatbot error: {rb_e}", exc_info=True)
        return jsonify({'success': False, 'response': 'Đã xảy ra lỗi hệ thống chatbot. Vui lòng thử lại.', 'intent': 'internal_error', 'entities': {}, 'image_results': []}), 500

@ai_bp.route('/admin/chatbot_test')
@login_required
def admin_chatbot_test():
    logger = current_app.logger
    logger.info(f"Admin user {current_user.id} accessing chatbot test page.")
    test_message = "Quán có bán cà phê sữa không?"
    test_session_id = f"admin-test-{current_user.id}"
    test_response = {}
    try:
         test_response = get_response(test_message, db.session, session_id=test_session_id)
         logger.info(f"Admin test response: {test_response}")
    except Exception as e:
         logger.error(f"Error running admin chatbot test: {e}", exc_info=True)
         test_response['response'] = f"Lỗi test: {e}"
    return render_template('admin/chatbot_test.html',
                           test_message=test_message,
                           test_response=test_response,
                           format_currency=format_currency
                           )

@ai_bp.route('/chatbot/upload-image', methods=['POST'])
def chatbot_upload_image():
    logger = current_app.logger; logger.info("Processing chatbot image upload...")
    if 'image_file' not in request.files: return jsonify({'success':False,'message':'Không có file.'}), 400
    file = request.files['image_file']
    if not file or file.filename == '': return jsonify({'success':False,'message':'File rỗng.'}), 400
    allowed_exts = current_app.config.get('ALLOWED_EXTENSIONS', {'png','jpg','jpeg','gif','webp'})
    filename = secure_filename(file.filename)
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_exts: return jsonify({'success':False,'message':'Định dạng không hỗ trợ.'}), 400
    max_bytes = current_app.config.get('MAX_CONTENT_LENGTH', 16*1024*1024); file.seek(0,os.SEEK_END); file_size=file.tell(); file.seek(0,os.SEEK_SET);
    if file_size > max_bytes: return jsonify({'success':False,'message':f'Ảnh quá lớn (max {max_bytes//1024//1024} MB).'}), 413
    try:
        image_bytes = file.read(); features = extract_features(image_bytes);
        if features is None: logger.error("Feature extraction failed."); return jsonify({'success':False,'message':'Không xử lý được ảnh.'}), 500
        similar_prods_raw = get_similar_products_by_feature_vector(features, top_n=4); logger.info(f"Found {len(similar_prods_raw)} similar visuals (raw).")
        
        similar_prods_display = []
        with current_app.app_context(): # Needed for url_for
            for item in similar_prods_raw:
                product = Product.query.get(item['product_id'])
                if product and product.is_available:
                     img_url = product.image_url or url_for('static', filename='images/default_product.png')
                     prod_url = url_for('main.product_detail', product_id=product.id)
                     similar_prods_display.append({"id": product.id, "name": product.name, "image_url": img_url, "product_url": prod_url, "similarity": item.get('similarity',0.0)})
                if len(similar_prods_display) >= 4: break

        logger.info(f"Formatted {len(similar_prods_display)} similar products for display.")
        resp_text = "Đây là vài món tương tự dựa trên ảnh bạn gửi:" if similar_prods_display else "Rất tiếc, tôi chưa tìm thấy món nào trong menu giống với ảnh này.";
        return jsonify({'success':True,'message':resp_text,'image_results':similar_prods_display})
    except Exception as e: logger.error(f"Visual search error: {e}", exc_info=True); return jsonify({'success':False,'message':'Lỗi tìm kiếm bằng ảnh.'}), 500

@ai_bp.route('/admin/inventory/predictions')
@login_required
def inventory_predictions():
    logger=current_app.logger; logger.info("Admin viewing inventory predictions page...")
    if not (current_user.is_admin or current_user.is_staff):
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('main.index'))
    
    recommendations_data=[]; error_msg=None; days_predicted_config=7
    try:
        recommendations_data = get_inventory_recommendations(days=days_predicted_config)
    except Exception as e:
        logger.error(f"Error getting inventory predictions: {e}", exc_info=True)
        error_msg = "Lỗi khi tải dữ liệu dự đoán tồn kho."
        flash(error_msg,'danger')

    start_date_default=(datetime.utcnow()-timedelta(days=days_predicted_config-1)).strftime('%Y-%m-%d')
    end_date_default=datetime.utcnow().strftime('%Y-%m-%d')
    
    return render_template('admin/reports/inventory_report.html',
                           report_type='inventory_ai', # Unique type for this page
                           recommendations=recommendations_data,
                           error_message=error_msg,
                           days_predicted=days_predicted_config,
                           start_date=start_date_default, # Or pass from request args if used
                           end_date=end_date_default,   # Or pass from request args if used
                           period='custom_range'      # Or pass from request args if used
                           )