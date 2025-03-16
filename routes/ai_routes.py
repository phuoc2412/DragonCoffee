"""
Dragon Coffee Shop - AI Routes
Routes for AI-powered features
"""

from flask import Blueprint, render_template, redirect, url_for, request, jsonify, session, flash, current_app
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from models import db, Product, Review, User, Category, Order
from sqlalchemy import func
import os
from datetime import datetime, timedelta
import json

# Import AI services
from ai_services import (
    get_recommendations,
    analyze_review_sentiment,
    predict_product_demand,
    get_inventory_recommendations,
    process_product_image,
    get_response,
    handle_order,
    generate_product_description,
    generate_promotion,
    generate_social_post
)

ai_bp = Blueprint('ai', __name__)

@ai_bp.route('/recommendations')
def recommendations():
    """Show personalized product recommendations"""
    personalized_recommendations = []
    popular_products = []
    similar_products = []
    last_viewed = None
    
    # Get popular products for everyone
    popular_products = get_recommendations(limit=6)
    
    # Get personalized recommendations for logged in users
    if current_user.is_authenticated:
        personalized_recommendations = get_recommendations(user_id=current_user.id, limit=6)
    
    # Get similar products based on last viewed product
    if 'last_viewed_product' in session:
        last_viewed_id = session['last_viewed_product']
        last_viewed = Product.query.get(last_viewed_id)
        if last_viewed:
            similar_products = get_recommendations(product_id=last_viewed_id, limit=4)
    
    return render_template(
        'recommendations.html',
        personalized_recommendations=personalized_recommendations,
        popular_products=popular_products,
        similar_products=similar_products,
        last_viewed=last_viewed
    )

@ai_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    """Show product details with AI-enhanced features"""
    product = Product.query.get_or_404(product_id)
    
    # Record this as the last viewed product
    session['last_viewed_product'] = product_id
    
    # Get similar products
    similar_products = get_recommendations(product_id=product_id, limit=4)
    
    # Generate AI product description if not available
    ai_product_description = ""
    if not product.description or len(product.description.strip()) < 10:
        product_data = {
            'name': product.name,
            'price': product.price,
            'category': product.category.name if product.category else 'Đồ uống'
        }
        ai_product_description = generate_product_description(product_data)
    
    # Add sentiment analysis to reviews
    reviews_with_sentiment = []
    for review in product.reviews:
        if not hasattr(review, 'sentiment_score'):
            # Analyze sentiment if not already done
            sentiment = analyze_review_sentiment(review.content)
            if sentiment:
                review.sentiment_score = sentiment.get('sentiment_score', 0)
                review.sentiment_label = 'Tích cực' if sentiment.get('rating', 3) >= 4 else (
                    'Tiêu cực' if sentiment.get('rating', 3) <= 2 else 'Trung tính'
                )
    
    return render_template(
        'product_detail.html',
        product=product,
        similar_products=similar_products,
        ai_product_description=ai_product_description,
        func=func  # Pass SQLAlchemy func for aggregations
    )

@ai_bp.route('/product/<int:product_id>/review', methods=['POST'])
@login_required
def add_review(product_id):
    """Add a review to a product with sentiment analysis"""
    product = Product.query.get_or_404(product_id)
    
    # Get data from request
    data = request.get_json()
    rating = int(data.get('rating', 0))
    content = data.get('content', '').strip()
    
    if rating < 1 or rating > 5:
        return jsonify({'success': False, 'message': 'Điểm đánh giá không hợp lệ (1-5)'})
    
    if not content:
        return jsonify({'success': False, 'message': 'Vui lòng nhập nội dung đánh giá'})
    
    # Check if user already reviewed this product
    existing_review = Review.query.filter_by(
        user_id=current_user.id,
        product_id=product_id
    ).first()
    
    if existing_review:
        # Update existing review
        existing_review.rating = rating
        existing_review.content = content
        existing_review.created_at = datetime.utcnow()
        db.session.commit()
        
        # Analyze sentiment
        sentiment = analyze_review_sentiment(content, review_id=existing_review.id)
        
        return jsonify({'success': True, 'message': 'Đánh giá đã được cập nhật'})
    else:
        # Create new review
        review = Review(
            user_id=current_user.id,
            product_id=product_id,
            rating=rating,
            content=content
        )
        db.session.add(review)
        db.session.commit()
        
        # Analyze sentiment
        sentiment = analyze_review_sentiment(content, review_id=review.id)
        
        return jsonify({'success': True, 'message': 'Cảm ơn bạn đã đánh giá!'})

@ai_bp.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    """Chatbot interface"""
    if request.method == 'POST':
        data = request.get_json()
        user_message = data.get('message', '').strip()
        session_id = session.get('id', None)
        
        if not user_message:
            return jsonify({'success': False, 'message': 'Vui lòng nhập tin nhắn'})
        
        # Check if this is an order intent
        if 'đặt' in user_message.lower() or 'mua' in user_message.lower() or 'order' in user_message.lower():
            response = handle_order(user_message, session_id)
        else:
            # General conversation
            response = get_response(user_message, session_id)
        
        return jsonify({
            'success': True,
            'response': response.get('response', 'Xin lỗi, tôi không hiểu. Bạn có thể nói rõ hơn không?'),
            'intent': response.get('intent', 'unknown')
        })
    
    # GET request - render chatbot page
    return render_template('chatbot.html')

@ai_bp.route('/chatbot/api', methods=['POST'])
def chatbot_api():
    """API endpoint for chatbot"""
    data = request.get_json()
    user_message = data.get('message', '').strip()
    session_id = data.get('session_id', None)
    
    if not user_message:
        return jsonify({'success': False, 'message': 'Message is required'})
    
    # Process message with chatbot
    response = get_response(user_message, session_id)
    
    return jsonify({
        'success': True,
        'response': response.get('response', 'Sorry, I didn\'t understand that.'),
        'intent': response.get('intent', 'unknown')
    })

@ai_bp.route('/admin/inventory/predictions')
@login_required
def inventory_predictions():
    """Show inventory predictions for admin"""
    if not current_user.is_admin and not current_user.is_staff:
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('index'))
    
    # Get inventory recommendations
    recommendations = get_inventory_recommendations(days=7)
    
    return render_template(
        'admin/inventory_predictions.html',
        recommendations=recommendations
    )

@ai_bp.route('/admin/content/generate', methods=['GET', 'POST'])
@login_required
def generate_content():
    """AI content generation for marketing"""
    if not current_user.is_admin and not current_user.is_staff:
        flash('Bạn không có quyền truy cập trang này.', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        content_type = request.form.get('content_type')
        product_id = request.form.get('product_id')
        
        if content_type == 'product_description':
            product = Product.query.get(product_id)
            if product:
                product_data = {
                    'name': product.name,
                    'price': product.price,
                    'category': product.category.name if product.category else 'Đồ uống'
                }
                content = generate_product_description(product_data)
                return jsonify({'success': True, 'content': content})
        
        elif content_type == 'promotion':
            product = Product.query.get(product_id)
            if product:
                promo_data = {
                    'product_name': product.name,
                    'discount_percent': request.form.get('discount', '15'),
                    'start_date': datetime.now().strftime('%d/%m/%Y'),
                    'end_date': (datetime.now() + timedelta(days=14)).strftime('%d/%m/%Y')
                }
                content = generate_promotion(promo_data)
                return jsonify({'success': True, 'content': content})
        
        elif content_type == 'social_post':
            product = Product.query.get(product_id)
            if product:
                post_data = {
                    'product_name': product.name,
                    'product_description': product.description or f'Đồ uống tuyệt vời tại Dragon Coffee'
                }
                content = generate_social_post(post_data)
                return jsonify({'success': True, 'content': content})
        
        return jsonify({'success': False, 'message': 'Không thể tạo nội dung'})
    
    # GET request - show content generation form
    products = Product.query.all()
    return render_template('admin/content_generator.html', products=products)

@ai_bp.route('/admin/product/image/process', methods=['POST'])
@login_required
def process_image():
    """Process product image with AI"""
    if not current_user.is_admin and not current_user.is_staff:
        return jsonify({'success': False, 'message': 'Không có quyền truy cập'})
    
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'Không có file nào được tải lên'})
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Không có file nào được chọn'})
    
    if file:
        filename = secure_filename(file.filename)
        upload_folder = os.path.join(current_app.static_folder, 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        # Process the image with AI
        result = process_product_image(file_path)
        
        return jsonify({
            'success': True,
            'result': result
        })
    
    return jsonify({'success': False, 'message': 'Lỗi khi xử lý ảnh'})

# Register this blueprint in app.py
def init_app(app):
    app.register_blueprint(ai_bp, url_prefix='/ai')