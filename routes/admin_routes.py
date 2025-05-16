# /routes/admin_routes.py

import os
import uuid
from models import WebVisit
from forms import UpdateProfileForm
from datetime import datetime, timedelta, time
from functools import wraps
from flask import send_file
from collections import defaultdict
from app import db, app # Đã xóa babel vì không dùng ở đây
from models import (InventoryItem, Product, InterestingStory, Order, User, OrderDetail,
                    Employee, StockReceipt, ContactMessage, Promotion, Location, Review,
                    Category, WebVisit)
from forms import (InterestingStoryForm, StockReceiptForm, PromotionForm, LocationForm,
                   ForgotPasswordForm, ResetPasswordForm, LoginForm, ProductForm, CategoryForm,
                   EmployeeForm, UpdateProfileForm)

import qrcode # <--- THÊM IMPORT NÀY
from io import BytesIO # <--- THÊM IMPORT NÀY
 # <--- THÊM IMPORT NÀY (quan trọng)
# Import AI functions - Ensure these exist and work 
try:
    from ai_services import (generate_interesting_story, get_inventory_recommendations,
                           analyze_review_sentiment, generate_image_from_text_hf,
                           save_generated_image)
except ImportError as ai_err:
     # Ghi log lỗi nếu có logger
     import logging
     logger = logging.getLogger(__name__)
     logger.error(f"AI Service Import Error in admin_routes: {ai_err}", exc_info=True)
     # Define placeholder functions if import fails to prevent runtime crashes elsewhere
     def generate_interesting_story(): return None
     def get_inventory_recommendations(): return []
     def analyze_review_sentiment(text): return {}
     def generate_image_from_text_hf(prompt): return None
     def save_generated_image(bytes, sub): return None

from flask import current_app, jsonify, Blueprint, request, url_for, Response, make_response, redirect, render_template, flash, session
import csv
import io
import json
import requests
from werkzeug.utils import secure_filename

# Đảm bảo import decorators và hàm utils
from utils import (admin_required, staff_required, save_story_image, delete_file, format_currency,
                   generate_order_number, send_reset_email, send_order_status_email, send_contact_notification_email,
                   delete_old_image, save_product_image, save_avatar_file, delete_avatar_file) # Bổ sung các hàm utils cần thiết
import logging
from flask_login import current_user, login_required, login_user, logout_user
# from weasyprint import CSS, HTML
# from weasyprint.text.fonts import FontConfiguration
from sqlalchemy.orm import joinedload, selectinload, contains_eager
from sqlalchemy import desc, func, or_, cast, String, case

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# --- API Routes ---
@admin_bp.route('/api/search-customers')
@login_required
@staff_required # CHO PHÉP Staff và Admin
def api_search_customers():
    search_query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 10, type=int)
    results = []
    if len(search_query) >= 2:
        try:
            search_term = f"%{search_query}%"
            customers = User.query.filter(
                User.is_admin == False,
                User.is_staff == False,
                or_(
                    (User.first_name + ' ' + User.last_name).ilike(search_term),
                    User.email.ilike(search_term),
                    User.phone.ilike(search_term)
                )
            ).order_by(User.last_name, User.first_name).limit(limit).all()
            results = [
                {'id': customer.id, 'full_name': customer.full_name, 'email': customer.email, 'phone': customer.phone}
                for customer in customers
            ]
        except Exception as e:
            current_app.logger.error(f"API Customer Search Error: {e}", exc_info=True)
            return jsonify([])
    return jsonify(results)

@admin_bp.route('/api/products')
@login_required
@staff_required # CHO PHÉP Staff và Admin (cần cho POS)
def api_products():
    category_id = request.args.get('category_id', type=int)
    query_term = request.args.get('q', '')
    products_query = Product.query.filter(Product.is_available==True)\
                                  .join(InventoryItem, isouter=True)
    if category_id:
        products_query = products_query.filter(Product.category_id == category_id)
    if query_term:
        products_query = products_query.filter(Product.name.ilike(f'%{query_term}%'))

    products = products_query.order_by(Product.name).all()
    result = [{
            'id': p.id, 'name': p.name, 'price': float(p.price), 'category_id': p.category_id,
            'image_url': p.image_url or url_for('static', filename='images/default_product.png'),
            'stock': p.inventory.quantity if p.inventory else 0
        } for p in products]
    return jsonify(result)

@admin_bp.route('/api/create-order', methods=['POST'])
@login_required
@staff_required # CHO PHÉP Staff và Admin (cần cho POS)
def api_create_order():
    logger = current_app.logger
    data = request.json
    if not data or 'items' not in data or not data['items']:
        logger.warning("POS create order: Invalid data received.")
        return jsonify({'success': False, 'error': 'Dữ liệu đơn hàng không hợp lệ.'}), 400

    items_data = data.get('items', [])
    total_base_amount_calculated = 0
    product_inventory_updates = {}
    customer_id = data.get('customer_id')
    guest_phone = (data.get('contact_phone') or '').strip()
    order_user_id = None
    contact_phone_for_order = guest_phone
    customer_name_display = None

    try:
        with db.session.begin_nested():
            if customer_id:
                 customer = User.query.get(customer_id)
                 if customer and not customer.is_admin and not customer.is_staff:
                      order_user_id = customer.id
                      contact_phone_for_order = guest_phone or customer.phone or ''
                      customer_name_display = customer.full_name
                      logger.info(f"POS order associated with customer ID: {customer_id} ({customer_name_display})")
                 else:
                      logger.warning(f"Invalid or non-customer ID received: {customer_id}. Proceeding as guest or staff.")
                      customer_id = None
                      if not guest_phone:
                          order_user_id = current_user.id
                          logger.info(f"POS order (no valid customer/guest info) assigned to staff ID: {current_user.id}")
            elif guest_phone:
                 order_user_id = None
                 contact_phone_for_order = guest_phone
                 customer_name_display = f"Khách ({guest_phone})"
                 logger.info(f"POS order for guest with phone: {guest_phone}")
            else:
                 order_user_id = current_user.id
                 contact_phone_for_order = current_user.phone or ''
                 customer_name_display = f"NV ({current_user.username})"
                 logger.info(f"POS order with no customer/guest info assigned to staff ID: {current_user.id}")

            for item in items_data:
                product_id = item.get('product_id')
                quantity = item.get('quantity')
                if not product_id or not isinstance(quantity, int) or quantity <= 0: raise ValueError(f"SP ID {product_id} có số lượng không hợp lệ: {quantity}")
                product = db.session.query(Product.id, Product.name, Product.price, Product.is_available).filter(Product.id == product_id).first()
                if not product or not product.is_available: raise ValueError(f"SP '{item.get('name', product_id)}' không tồn tại hoặc đã hết hàng.")
                inventory = db.session.query(InventoryItem).filter_by(product_id=product_id).with_for_update().first()
                current_stock = inventory.quantity if inventory else 0
                planned_usage = product_inventory_updates.get(product_id, 0)
                if current_stock < quantity + planned_usage: raise ValueError(f"Không đủ '{product.name}'. Còn {current_stock - planned_usage} (cần {quantity}).")
                total_base_amount_calculated += product.price * quantity
                product_inventory_updates[product_id] = planned_usage + quantity

            tax_rate_pos = 0.10
            discount_amount_pos = 0
            tax_amount_pos = total_base_amount_calculated * tax_rate_pos
            final_amount_calculated = total_base_amount_calculated + tax_amount_pos - discount_amount_pos

            new_order = Order(
                user_id=order_user_id,
                order_number=f"POS-{uuid.uuid4().hex[:8].upper()}",
                status='completed', # POS orders are completed immediately
                total_amount=round(total_base_amount_calculated,2),
                final_amount=round(final_amount_calculated,2),
                order_type=data.get('order_type', 'dine-in'),
                payment_method=data.get('payment_method', 'cash'),
                payment_status='completed', # POS orders are paid immediately
                notes=data.get('notes', '') or None,
                address=None,
                contact_phone=contact_phone_for_order,
                tax_amount=round(tax_amount_pos, 2),
                discount_applied=discount_amount_pos
            )
            db.session.add(new_order)
            db.session.flush()

            for item_data in items_data:
                product_price = db.session.query(Product.price).filter(Product.id == item_data['product_id']).scalar()
                calculated_unit_price = float(product_price) if product_price is not None else 0
                calculated_subtotal = calculated_unit_price * item_data['quantity']
                order_notes = item_data.get('notes', '') or None
                order_detail = OrderDetail(
                    order_id=new_order.id,
                    product_id=item_data['product_id'],
                    quantity=item_data['quantity'],
                    unit_price=calculated_unit_price,
                    subtotal=calculated_subtotal,
                    notes=order_notes
                )
                db.session.add(order_detail)
                inventory = db.session.query(InventoryItem).filter_by(product_id=item_data['product_id']).with_for_update().one_or_none()
                if inventory:
                    if inventory.quantity >= item_data['quantity']:
                        inventory.quantity -= item_data['quantity']
                        inventory.last_updated = datetime.utcnow()
                    else:
                        raise ValueError(f"Lỗi tồn kho cho SP ID {item_data['product_id']} khi tạo đơn POS.")
                else:
                    logger.warning(f"Inv item not found for product {item_data['product_id']} when decrementing stock.")
        # End of with db.session.begin_nested(): - auto commit/rollback happens here
        logger.info(f"POS Order {new_order.order_number} (Customer: {customer_name_display}, Contact: {contact_phone_for_order}) created successfully by staff {current_user.id}.")
        return jsonify({'success': True, 'order_id': new_order.id, 'order_number': new_order.order_number, 'message': f'Đã tạo đơn hàng POS {new_order.order_number}.'})

    except ValueError as ve:
        logger.warning(f"POS order validation failed: {ve}")
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Lỗi khi tạo đơn POS: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Lỗi máy chủ khi xử lý đơn hàng.'}), 500


@admin_bp.route('/api/search-orders')
@login_required
@staff_required # CHO PHÉP Staff và Admin
def api_search_orders():
    logger = current_app.logger
    try:
        query = request.args.get('q', '')
        status = request.args.get('status', '')
        order_query = Order.query.options(joinedload(Order.customer))
        if status: order_query = order_query.filter(Order.status == status)
        if query:
            search_like = f"%{query}%"
            order_query = order_query.outerjoin(User, Order.user_id == User.id).filter(
                or_(
                    Order.order_number.ilike(search_like),
                    func.lower(User.first_name + ' ' + User.last_name).contains(func.lower(query)),
                    User.email.ilike(search_like), User.phone.ilike(search_like), Order.contact_phone.ilike(search_like)
                ))
        orders = order_query.order_by(Order.created_at.desc()).limit(100).all()
        count = len(orders)
        table_rows_html = render_template('admin/_order_table_rows.html', orders=orders, pagination=None)
        return jsonify({'success': True, 'html': table_rows_html, 'count': count})
    except Exception as e:
        logger.error(f"API Error searching orders (q='{query}', status='{status}'): {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Lỗi máy chủ khi tìm kiếm đơn hàng.'}), 500

@admin_bp.route('/api/search-inventory')
@login_required
@staff_required # CHO PHÉP Staff và Admin
def api_search_inventory():
    logger = current_app.logger
    try:
        query = request.args.get('q', '')
        status_filter = request.args.get('status', 'all')
        base_query = db.session.query(InventoryItem).options(
            joinedload(InventoryItem.product_inventory).joinedload(Product.category)
        ).join(Product, InventoryItem.product_id == Product.id)
        if query: base_query = base_query.filter(Product.name.ilike(f'%{query}%'))
        if status_filter == 'low': base_query = base_query.filter(InventoryItem.quantity > 0, InventoryItem.quantity <= InventoryItem.min_quantity)
        elif status_filter == 'out': base_query = base_query.filter(InventoryItem.quantity <= 0)
        elif status_filter == 'adequate': base_query = base_query.filter(InventoryItem.quantity > InventoryItem.min_quantity)
        inventory_items = base_query.order_by(
            case( (InventoryItem.quantity <= 0, 0), (InventoryItem.quantity <= InventoryItem.min_quantity, 1), else_=2), Product.name.asc()
        ).limit(150).all()
        count = len(inventory_items)
        from app import format_datetime_filter # Tạm import ở đây
        table_rows_html = render_template('admin/_inventory_table_rows.html', inventory_items=inventory_items, format_datetime=format_datetime_filter)
        return jsonify({'success': True, 'html': table_rows_html, 'count': count})
    except Exception as e:
        logger.error(f"API Error searching inventory (q='{query}', status='{status_filter}'): {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Lỗi khi tìm kiếm tồn kho.'}), 500


# --- Admin Login/Logout/Password Reset Routes ---
@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and (current_user.is_admin or current_user.is_staff):
        return redirect(url_for('admin.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = User.query.filter(func.lower(User.email) == func.lower(form.email.data)).first()
            if user is None or not user.check_password(form.password.data) or not (user.is_admin or user.is_staff):
                flash('Email, mật khẩu không hợp lệ hoặc bạn không có quyền truy cập.', 'danger')
                return redirect(url_for('admin.login'))
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            flash('Đăng nhập thành công!', 'success')
            return redirect(next_page or url_for('admin.dashboard'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Lỗi đăng nhập Admin/Staff: {e}", exc_info=True)
            flash('Lỗi hệ thống khi đăng nhập. Vui lòng thử lại.', 'danger')
            return redirect(url_for('admin.login'))
    return render_template('admin/login.html', form=form, title="Đăng nhập Quản trị/Nhân viên")


@admin_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('admin.login'))


@admin_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        logger = current_app.logger
        user = User.query.filter(func.lower(User.email) == func.lower(form.email.data)).first()
        if user and (user.is_admin or user.is_staff):
            logger.info(f"Admin/Staff forgot password request for user {user.id} ({user.email})")
            if send_reset_email(user, endpoint_name='admin.reset_password'):
                 flash('Một email hướng dẫn đặt lại mật khẩu đã được gửi.', 'info')
            else:
                flash('Lỗi khi gửi email. Vui lòng thử lại hoặc liên hệ hỗ trợ.', 'danger')
            return redirect(url_for('admin.login'))
        else:
             logger.warning(f"Forgot password attempt for non-staff/admin or non-existent email: {form.email.data}")
             flash('Nếu email của bạn tồn tại và thuộc tài khoản NV/Admin, bạn sẽ nhận được thư.', 'info')
             return redirect(url_for('admin.login'))
    return render_template('admin/forgot_password.html', title='Quên Mật khẩu', form=form)

@admin_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
    logger = current_app.logger
    user = User.verify_reset_token(token)
    if user is None or not (user.is_admin or user.is_staff):
        flash('Link đặt lại mật khẩu không hợp lệ, đã hết hạn hoặc không dành cho tài khoản này.', 'warning')
        logger.warning(f"Invalid/Expired token or non-staff/admin access attempt for reset token: {token[:10]}...")
        return redirect(url_for('admin.forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        try:
            db.session.commit()
            flash('Mật khẩu đã được cập nhật! Bây giờ bạn có thể đăng nhập.', 'success')
            logger.info(f"Password reset successfully for user {user.id} via admin reset flow.")
            return redirect(url_for('admin.login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Lỗi khi cập nhật mật khẩu: {e}', 'danger')
            logger.error(f"Error resetting password via admin flow for user ID {user.id}: {e}", exc_info=True)
    return render_template('admin/reset_password.html', title='Đặt Lại Mật khẩu', form=form, token=token)


# --- Main Dashboard ---
@admin_bp.route('/')
@admin_bp.route('/dashboard')
@login_required
@staff_required 
def dashboard():
    logger = current_app.logger
    period = request.args.get('period')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    end_date = datetime.utcnow().date()
    start_date = None

    try:
        if end_date_str: end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date(); period = None 
        if start_date_str: start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date(); period = None 
        if not start_date: 
            if period == 'day': start_date = end_date
            elif period == 'month': start_date = end_date.replace(day=1)
            elif period == 'year': start_date = end_date.replace(month=1, day=1)
            elif period == 'week': start_date = end_date - timedelta(days=end_date.weekday())
            else: 
                  if not period and not start_date_str and not end_date_str: period = 'last7days' 
                  start_date = end_date - timedelta(days=6)
        if start_date and end_date and start_date > end_date:
             flash("Ngày bắt đầu không thể sau ngày kết thúc. Hiển thị 7 ngày gần nhất.", "warning")
             end_date = datetime.utcnow().date(); start_date = end_date - timedelta(days=6); period = 'last7days'
    except ValueError:
         flash("Ngày tháng không hợp lệ. Hiển thị 7 ngày gần nhất.", "warning")
         end_date = datetime.utcnow().date(); start_date = end_date - timedelta(days=6); period = 'last7days'

    start_datetime = datetime.combine(start_date, time.min)
    end_datetime = datetime.combine(end_date, time.max)
    logger.info(f"Dashboard Request: period={period}, start={start_date}, end={end_date}")

    total_revenue=0.0; total_orders=0; total_users=0; total_products=0
    recent_orders, top_products = [], []
    chart_data = {'labels': [], 'values': []} # Doanh thu theo ngày
    pie_chart_data = {'labels': [], 'values': []} # Doanh thu theo danh mục
    low_inventory_items, low_inventory_count, out_of_stock_count = [], 0, 0

    try:
        base_completed_order_query = Order.query.filter(
            Order.created_at.between(start_datetime, end_datetime),
            Order.status.in_(['completed', 'delivered'])
        )
        total_revenue = db.session.query(func.sum(func.coalesce(Order.final_amount, Order.total_amount, 0.0))).select_from(base_completed_order_query.subquery()).scalar() or 0.0
        total_orders = Order.query.filter(Order.created_at.between(start_datetime, end_datetime)).count()
        total_products = db.session.query(func.count(Product.id)).scalar()
        total_users = db.session.query(func.count(User.id)).filter(User.is_admin == False, User.is_staff == False).scalar()
        recent_orders = Order.query.options(joinedload(Order.customer)).filter(Order.created_at.between(start_datetime, end_datetime)).order_by(Order.created_at.desc()).limit(5).all()
        
        top_products_data = db.session.query( Product, func.sum(OrderDetail.quantity).label('total_sold'))\
         .join(OrderDetail, OrderDetail.product_id == Product.id)\
         .join(Order, Order.id == OrderDetail.order_id)\
         .filter(Order.created_at.between(start_datetime, end_datetime), Order.status.in_(['completed', 'delivered']))\
         .group_by(Product.id).order_by(desc('total_sold')).limit(5).all()
        # Chuyển thành list dictionaries để dễ dùng trong template nếu cần (hoặc dùng tuple trực tiếp)
        top_products = [{'product': tp[0], 'total_sold': tp[1]} for tp in top_products_data]


        daily_sales_data = db.session.query( func.date(Order.created_at).label('sale_date'), func.sum(func.coalesce(Order.final_amount, Order.total_amount, 0.0)).label('daily_total'))\
             .select_from(base_completed_order_query.subquery()).group_by('sale_date').order_by('sale_date').all()
        daily_sales_dict = {row.sale_date: float(row.daily_total) for row in daily_sales_data}
        date_labels, sales_amounts = [], []; current_date_iter = start_date
        while current_date_iter <= end_date:
            sales_amounts.append(daily_sales_dict.get(current_date_iter, 0.0))
            date_labels.append(current_date_iter.strftime('%d/%m'))
            current_date_iter += timedelta(days=1)
        chart_data = {'labels': date_labels, 'values': sales_amounts}
        logger.debug(f"Sales by Time Chart Data: {chart_data}")
        
        # Query doanh thu theo danh mục
        sales_by_category_data = db.session.query(
            Category.name,
            func.sum(func.coalesce(Order.final_amount, Order.total_amount, 0.0)).label('category_revenue')
        ).select_from(OrderDetail)\
         .join(Order, Order.id == OrderDetail.order_id)\
         .join(Product, Product.id == OrderDetail.product_id)\
         .join(Category, Category.id == Product.category_id)\
         .filter(
             Order.created_at.between(start_datetime, end_datetime),
             Order.status.in_(['completed', 'delivered'])
         ).group_by(Category.name)\
         .order_by(desc('category_revenue'))\
         .limit(7).all() # Lấy top 7 danh mục

        pie_chart_data = {
            'labels': [cat.name for cat in sales_by_category_data],
            'values': [float(cat.category_revenue or 0.0) for cat in sales_by_category_data]
        }
        logger.debug(f"Sales by Category Pie Chart Data: {pie_chart_data}")

        low_inventory_items_q = InventoryItem.query.filter(InventoryItem.quantity > 0, InventoryItem.quantity <= InventoryItem.min_quantity).options(joinedload(InventoryItem.product_inventory))
        out_of_stock_items_q = InventoryItem.query.filter(InventoryItem.quantity <= 0)
        low_inventory_count = low_inventory_items_q.count(); out_of_stock_count = out_of_stock_items_q.count()
        low_inventory_items = low_inventory_items_q.limit(5).all()

    except Exception as e:
        logger.error(f"Lỗi tải dữ liệu dashboard: {e}", exc_info=True)
        flash("Không thể tải dữ liệu dashboard. Vui lòng thử lại.", "danger")
        # Reset giá trị về mặc định nếu có lỗi để tránh lỗi render
        total_revenue=0.0; total_orders=0; total_users=0; total_products=0
        recent_orders, top_products, chart_data, pie_chart_data = [], [], {'labels':[],'values':[]}, {'labels':[],'values':[]}
        low_inventory_items, low_inventory_count, out_of_stock_count = [],0,0


    return render_template('admin/dashboard.html',
                           total_revenue=total_revenue, total_orders=total_orders,
                           total_users=total_users, total_products=total_products,
                           recent_orders=recent_orders, top_products=top_products,
                           chart_data=chart_data, pie_chart_data=pie_chart_data, # Thêm pie_chart_data
                           low_inventory_items=low_inventory_items, low_inventory_count=low_inventory_count,
                           out_of_stock_count=out_of_stock_count,
                           start_date=start_date.strftime('%Y-%m-%d'),
                           end_date=end_date.strftime('%Y-%m-%d'),
                           period=period)
# --- Menu Management (ADMIN ONLY) ---
@admin_bp.route('/menu-management')
@login_required
@admin_required 
def menu_management():
    products = Product.query.join(Product.category).options(contains_eager(Product.category)).order_by(Category.name, Product.name).all() 
    categories = Category.query.order_by(Category.name).all()
    return render_template('admin/menu_management.html', products=products, categories=categories)

@admin_bp.route('/product/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    form = ProductForm()
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by('name').all()]
    if form.validate_on_submit():
        image_url = None; image_file = request.files.get('image_file'); image_path_relative = None
        try:
            if image_file and image_file.filename:
                image_path_relative = save_product_image(image_file)
                if image_path_relative: image_url = url_for('static', filename=image_path_relative, _external=False)
                else: raise ValueError('Lưu ảnh thất bại.')
            elif form.image_url.data: image_url = form.image_url.data

            product = Product( name=form.name.data, description=form.description.data, price=form.price.data,
                              image_url=image_url, is_available=form.is_available.data, is_featured=form.is_featured.data,
                              category_id=form.category_id.data )
            db.session.add(product); db.session.flush()
            inventory = InventoryItem( product_id=product.id, quantity=form.stock_quantity.data or 0,
                                      min_quantity=form.min_quantity.data or 10 )
            db.session.add(inventory); db.session.commit()
            flash('Thêm sản phẩm thành công!', 'success')
            return redirect(url_for('admin.menu_management'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Lỗi thêm sản phẩm (DB): {e}", exc_info=True)
            flash(f'Lỗi khi thêm sản phẩm: {str(e)}', 'danger')
            if image_path_relative: delete_old_image(image_path_relative)
    elif request.method == 'POST': flash('Có lỗi trong form, vui lòng kiểm tra lại.', 'warning')
    return render_template('admin/product_form.html', form=form, title='Thêm sản phẩm', legend='Thêm sản phẩm mới')

@admin_bp.route('/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    product = Product.query.options(joinedload(Product.inventory)).get_or_404(product_id)
    inventory = product.inventory
    if not inventory: inventory = InventoryItem(product_id=product_id, quantity=0, min_quantity=10)

    form = ProductForm(obj=product)
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by('name').all()]
    current_image_url = product.image_url
    old_image_relative_path = None
    if current_image_url and current_image_url.startswith(url_for('static', filename='uploads/')):
        prefix = url_for('static', filename='')
        if current_image_url.startswith(prefix): old_image_relative_path = current_image_url[len(prefix):]

    if request.method == 'GET':
        if inventory: form.stock_quantity.data = inventory.quantity; form.min_quantity.data = inventory.min_quantity
        if current_image_url and not current_image_url.startswith(url_for('static', filename='')): form.image_url.data = current_image_url

    if form.validate_on_submit():
        new_image_url = current_image_url; image_file = request.files.get('image_file'); new_relative_path = None
        try:
            if image_file and image_file.filename:
                new_relative_path = save_product_image(image_file)
                if new_relative_path: new_image_url = url_for('static', filename=new_relative_path, _external=False)
                else: flash('Lưu ảnh mới thất bại, giữ nguyên ảnh cũ.', 'danger')
            elif form.image_url.data != current_image_url:
                 new_image_url = form.image_url.data if form.image_url.data and form.image_url.data.strip() else None
            elif request.form.get('remove_image') == '1': # Check field ẩn để xóa ảnh
                new_image_url = None
                current_app.logger.info(f"User requested image removal for product {product_id}")


            product.name = form.name.data; product.description = form.description.data; product.price = form.price.data
            product.image_url = new_image_url; product.is_available = form.is_available.data; product.is_featured = form.is_featured.data
            product.category_id = form.category_id.data; product.updated_at = datetime.utcnow()

            if inventory:
                 inventory.quantity = form.stock_quantity.data if form.stock_quantity.data is not None else inventory.quantity
                 inventory.min_quantity = form.min_quantity.data if form.min_quantity.data is not None else inventory.min_quantity
                 inventory.last_updated = datetime.utcnow()
                 if not inventory.id: db.session.add(inventory)

            db.session.commit()
            flash('Cập nhật sản phẩm thành công!', 'success')
            if old_image_relative_path and new_image_url != current_image_url: delete_old_image(old_image_relative_path)
            return redirect(url_for('admin.menu_management'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Lỗi cập nhật sản phẩm (DB) ID {product_id}: {e}", exc_info=True)
            flash(f'Lỗi khi cập nhật sản phẩm: {str(e)}', 'danger')
            if new_relative_path and new_relative_path != old_image_relative_path: delete_old_image(new_relative_path)

    elif request.method == 'POST': flash('Có lỗi trong form, vui lòng kiểm tra lại.', 'warning')
    return render_template('admin/product_form.html', form=form, title='Chỉnh sửa sản phẩm', product=product, legend=f'Chỉnh sửa: {product.name}', current_image_url=current_image_url)


@admin_bp.route('/product/delete/<int:product_id>', methods=['POST'])
@login_required
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if OrderDetail.query.filter_by(product_id=product_id).first():
        flash(f'Không thể xóa "{product.name}" vì đã tồn tại trong đơn hàng.', 'danger')
        return redirect(url_for('admin.menu_management'))
    try:
        inventory = InventoryItem.query.filter_by(product_id=product_id).first()
        if inventory: db.session.delete(inventory)
        db.session.delete(product); db.session.commit()
        flash(f'Đã xóa sản phẩm "{product.name}".', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Lỗi xóa sản phẩm ID {product_id}: {e}", exc_info=True)
        flash(f'Lỗi khi xóa sản phẩm: {str(e)}', 'danger')
    return redirect(url_for('admin.menu_management'))

@admin_bp.route('/products/export/csv')
@login_required
@admin_required
def export_products_csv():
    logger = current_app.logger; logger.info("Initiating CSV export for products...")
    try:
        products_to_export = Product.query.options(joinedload(Product.category), joinedload(Product.inventory)).order_by(Product.category_id, Product.name).all()
        if not products_to_export:
            flash("Không có sản phẩm nào để xuất.", "warning")
            return redirect(url_for('admin.menu_management'))
        output = io.StringIO(); writer = csv.writer(output)
        header = ['ID', 'Tên Sản Phẩm', 'Mô Tả', 'Giá', 'Danh Mục', 'Có Sẵn', 'Nổi Bật', 'URL Ảnh', 'Tồn Kho', 'Tồn Kho Tối Thiểu', 'Ngày Tạo', 'Ngày Cập Nhật']
        writer.writerow(header)
        for p in products_to_export:
            writer.writerow([ p.id, p.name, p.description or '', p.price, p.category.name if p.category else 'N/A',
                             'Yes' if p.is_available else 'No', 'Yes' if p.is_featured else 'No', p.image_url or '',
                             p.inventory.quantity if p.inventory else 0, p.inventory.min_quantity if p.inventory else 'N/A',
                             p.created_at.strftime('%Y-%m-%d %H:%M:%S') if p.created_at else '',
                             p.updated_at.strftime('%Y-%m-%d %H:%M:%S') if p.updated_at else '' ])
        csv_data = output.getvalue().encode('utf-8-sig'); output.close()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dragoncoffee_products_{timestamp}.csv"
        return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename=\"{filename}\""})
    except Exception as e:
        logger.error(f"Error exporting products to CSV: {e}", exc_info=True)
        flash("Lỗi khi xuất file sản phẩm.", "danger")
        return redirect(url_for('admin.menu_management'))

@admin_bp.route('/category/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_category():
    form = CategoryForm()
    if form.validate_on_submit():
        existing_category = Category.query.filter(func.lower(Category.name) == func.lower(form.name.data)).first()
        if existing_category: flash(f'Tên danh mục "{form.name.data}" đã tồn tại.', 'warning')
        else:
            try:
                category = Category(name=form.name.data, description=form.description.data)
                db.session.add(category); db.session.commit()
                flash('Thêm danh mục thành công!', 'success')
                return redirect(url_for('admin.menu_management'))
            except Exception as e: db.session.rollback(); current_app.logger.error(f"Lỗi thêm danh mục: {e}", exc_info=True); flash(f'Lỗi khi thêm danh mục: {str(e)}', 'danger')
    elif request.method == 'POST': flash('Có lỗi trong form, vui lòng kiểm tra lại.', 'warning')
    return render_template('admin/category_form.html', form=form, title='Thêm danh mục', legend='Thêm danh mục mới')

@admin_bp.route('/category/edit/<int:category_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_category(category_id):
    category = Category.query.get_or_404(category_id); form = CategoryForm(obj=category)
    if form.validate_on_submit():
         new_name_lower = form.name.data.lower()
         if new_name_lower != category.name.lower():
             existing_category = Category.query.filter(func.lower(Category.name) == new_name_lower, Category.id != category_id).first()
             if existing_category: flash(f'Tên danh mục "{form.name.data}" đã được sử dụng.', 'warning'); return render_template(...)
         try:
            category.name = form.name.data; category.description = form.description.data
            db.session.commit(); flash('Cập nhật danh mục thành công!', 'success'); return redirect(url_for('admin.menu_management'))
         except Exception as e: db.session.rollback(); current_app.logger.error(f"Lỗi cập nhật danh mục ID {category_id}: {e}", exc_info=True); flash(f'Lỗi khi cập nhật danh mục: {str(e)}', 'danger')
    elif request.method == 'POST': flash('Có lỗi trong form, vui lòng kiểm tra lại.', 'warning')
    return render_template('admin/category_form.html', form=form, title='Chỉnh sửa danh mục', category=category, legend=f'Chỉnh sửa: {category.name}')

@admin_bp.route('/category/delete/<int:category_id>', methods=['POST'])
@login_required
@admin_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    if category.products.first():
        flash(f'Không thể xóa "{category.name}" vì còn chứa sản phẩm.', 'danger')
        return redirect(url_for('admin.menu_management'))
    try:
        db.session.delete(category)
        db.session.commit()
        flash(f'Đã xóa danh mục "{category.name}".', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Lỗi xóa danh mục ID {category_id}: {e}", exc_info=True)
        # SỬA Ở ĐÂY: Thay flash(...) bằng tin nhắn thực tế
        flash(f'Lỗi khi xóa danh mục: {str(e)}', 'danger')
    return redirect(url_for('admin.menu_management'))


# --- Order Management (Staff & Admin) ---
@admin_bp.route('/orders')
@login_required
@staff_required
def orders():
    page = request.args.get('page', 1, type=int); per_page = 15
    status_filter = request.args.get('status'); search_term = request.args.get('q', '')
    query = Order.query
    if status_filter: query = query.filter(Order.status == status_filter)
    if search_term:
        search_like = f"%{search_term}%"
        query = query.outerjoin(User, Order.user_id == User.id).filter(
            or_( Order.order_number.ilike(search_like), func.lower(User.first_name + ' ' + User.last_name).contains(func.lower(search_term)),
                 User.email.ilike(search_like), User.phone.ilike(search_like), Order.contact_phone.ilike(search_like)))
    if not current_user.is_admin: # Lọc cho Staff
        allowed_statuses_for_staff = ['pending', 'processing', 'ready_for_pickup', 'out_for_delivery']
        query = query.filter(Order.status.in_(allowed_statuses_for_staff))
    orders_pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/orders.html', orders=orders_pagination.items, pagination=orders_pagination, status=status_filter, q=search_term)

@admin_bp.route('/orders/<int:order_id>')
@login_required
@staff_required
def order_details(order_id):
    order = Order.query.options(joinedload(Order.customer)).get_or_404(order_id)
    order_details_list = OrderDetail.query.options(joinedload(OrderDetail.ordered_product)).filter(OrderDetail.order_id == order_id).all()
    # Bỏ phần tính time ở đây cho gọn, có thể thêm lại nếu cần
    return render_template('admin/order_details.html', order=order, order_details=order_details_list)


@admin_bp.route('/orders/update-status/<int:order_id>', methods=['POST'])
@login_required
@staff_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id); logger = current_app.logger
    new_order_status = request.form.get('status'); new_payment_status = request.form.get('payment_status')
    valid_order_statuses = ['pending', 'processing', 'ready_for_pickup', 'out_for_delivery', 'completed', 'delivered', 'cancelled', 'failed']
    valid_payment_statuses = ['pending', 'completed', 'paid', 'failed', 'cancelled', 'refunded']
    allowed_updates_for_staff = {'pending': ['processing'], 'processing': ['ready_for_pickup', 'out_for_delivery']}
    can_update_order = True; can_update_payment = True; updated_fields = []

    if not current_user.is_admin:
        if new_order_status and new_order_status != order.status and new_order_status not in allowed_updates_for_staff.get(order.status, []):
            can_update_order = False; flash(f'Nhân viên không được phép chuyển từ "{order.get_status_display()}" sang "{new_order_status.replace("_"," ").title()}".', 'danger')
        if new_payment_status and new_payment_status != order.payment_status:
             can_update_payment = False; flash('Nhân viên không được thay đổi trạng thái thanh toán.', 'danger')

    if can_update_order and new_order_status and new_order_status in valid_order_statuses and order.status != new_order_status:
        order.status = new_order_status; updated_fields.append(f"Trạng thái ĐH thành '{order.get_status_display()}'")
        if new_order_status == 'cancelled' and order.payment_status not in ['cancelled', 'refunded']: order.payment_status = 'cancelled'; updated_fields.append("TT TT thành 'Đã hủy'")
        elif new_order_status == 'completed' and order.payment_status not in ['completed', 'paid']: order.payment_status = 'completed'; updated_fields.append("TT TT thành 'Đã thanh toán'")
    if can_update_payment and new_payment_status and new_payment_status in valid_payment_statuses and order.payment_status != new_payment_status:
        order.payment_status = new_payment_status; updated_fields.append(f"TT TT thành '{new_payment_status.replace('_', ' ').title()}'")

    if updated_fields:
        order.updated_at = datetime.utcnow()
        try:
            db.session.commit(); flash(f'Đã cập nhật đơn #{order.order_number}: {", ".join(updated_fields)}.', 'success'); logger.info(...)
            if new_order_status and new_order_status in ['processing', 'ready_for_pickup', 'out_for_delivery', 'completed', 'delivered', 'cancelled']:
                send_order_status_email(order)
        except Exception as e: db.session.rollback(); logger.error(...); flash(...)
    elif not can_update_order or not can_update_payment: pass
    else: flash('Không có thay đổi trạng thái.', 'info')
    return redirect(request.referrer or url_for('admin.order_details', order_id=order_id))

@admin_bp.route('/orders/add-note/<int:order_id>', methods=['POST'])
@login_required
@staff_required
def add_order_note(order_id):
    order = Order.query.get_or_404(order_id); note_content = request.form.get('internal_note')
    if not note_content: flash("Nội dung ghi chú không được trống.", "warning"); return redirect(...)
    new_note = f"\n[NV {current_user.username} - {datetime.now().strftime('%d/%m/%y %H:%M')}]: {note_content}"
    order.notes = (order.notes or "") + new_note
    try: db.session.commit(); flash("Đã thêm ghi chú.", "success")
    except Exception as e: db.session.rollback(); flash(f"Lỗi thêm ghi chú: {str(e)}", "danger"); current_app.logger.error(...)
    return redirect(url_for('admin.order_details', order_id=order_id))

@admin_bp.route('/orders/process/<int:order_id>', methods=['POST'])
@login_required
@staff_required # Cho phép Staff nhấn xử lý
def process_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status == 'pending':
        order.status = 'processing'; order.updated_at = datetime.utcnow()
        try: db.session.commit(); flash(f'Đã xử lý đơn #{order.order_number}.', 'success')
        except Exception as e: db.session.rollback(); flash(f'Lỗi xử lý đơn: {str(e)}', 'danger'); current_app.logger.error(...)
    else: flash(f'Đơn #{order.order_number} không ở trạng thái chờ xử lý.', 'warning')
    return redirect(url_for('admin.orders'))


# --- POS System (Staff & Admin) ---
@admin_bp.route('/pos')
@login_required
@staff_required
def pos():
    categories = Category.query.order_by(Category.name).all()
    products = Product.query.filter_by(is_available=True).options(joinedload(Product.inventory)).order_by(Product.category_id, Product.name).all()
    return render_template('admin/pos.html', categories=categories, products=products)


# --- Inventory Management (Staff & Admin, limited Staff actions) ---
@admin_bp.route('/inventory')
@login_required
@staff_required
def inventory():
    page = request.args.get('page', 1, type=int); search_term = request.args.get('search', '')
    status_filter = request.args.get('status_filter', 'all'); per_page=20
    query = InventoryItem.query.join(Product)
    if search_term: query = query.filter(Product.name.ilike(f'%{search_term}%'))
    if status_filter == 'low': query = query.filter(InventoryItem.quantity <= InventoryItem.min_quantity, InventoryItem.quantity > 0)
    elif status_filter == 'out': query = query.filter(InventoryItem.quantity <= 0)
    elif status_filter == 'adequate': query = query.filter(InventoryItem.quantity > InventoryItem.min_quantity)
    pagination = query.order_by(Product.name).paginate(page=page, per_page=per_page, error_out=False)
    base_query = db.session.query(InventoryItem.id)
    total_all_items_count = base_query.count()
    low_stock_count = base_query.filter(InventoryItem.quantity <= InventoryItem.min_quantity, InventoryItem.quantity > 0).count()
    out_of_stock_count = base_query.filter(InventoryItem.quantity <= 0).count()
    adequate_stock_count = total_all_items_count - low_stock_count - out_of_stock_count
    return render_template('admin/inventory.html', inventory_items=pagination.items, pagination=pagination,
                           total_items=pagination.total, total_all_items_count=total_all_items_count,
                           low_stock_count=low_stock_count, out_of_stock_count=out_of_stock_count,
                           adequate_stock_count=adequate_stock_count, search_term=search_term, status_filter=status_filter)


@admin_bp.route('/inventory/add-stock', methods=['GET', 'POST'])
@login_required
@staff_required # Cho phép Staff thêm phiếu nhập kho
def add_stock():
    form = StockReceiptForm()
    try:
        inventory_choices = [(item.id, item.product_inventory.name) for item in InventoryItem.query.join(Product).order_by(Product.name).all() if hasattr(item, 'product_inventory') and item.product_inventory]
        form.inventory_item_id.choices = inventory_choices
    except Exception as e: current_app.logger.error(...); flash("Lỗi tải danh sách sản phẩm.", "danger"); form.inventory_item_id.choices = []

    if form.validate_on_submit():
        inventory_item_id = form.inventory_item_id.data; quantity_added = form.quantity_added.data
        inventory_item = db.session.get(InventoryItem, inventory_item_id)
        if not inventory_item: flash(...); return redirect(url_for('admin.inventory'))
        related_product = getattr(inventory_item, 'product_inventory', None)
        if not related_product: flash(...); return redirect(url_for('admin.inventory'))
        try:
            receipt = StockReceipt( product_id=inventory_item.product_id, inventory_item_id=inventory_item_id, quantity_added=quantity_added,
                                   supplier=form.supplier.data, unit_cost=form.unit_cost.data if form.unit_cost.data is not None else None, notes=form.notes.data,
                                   received_by_user_id=current_user.id, received_at = datetime.utcnow())
            db.session.add(receipt); inventory_item.quantity += quantity_added; inventory_item.last_restocked = datetime.utcnow(); inventory_item.last_updated = datetime.utcnow()
            db.session.commit(); flash(f"Đã nhập {quantity_added} cho '{related_product.name}'.", "success"); return redirect(url_for('admin.inventory'))
        except Exception as e: db.session.rollback(); current_app.logger.error(...); flash(...)
    return render_template('admin/add_stock_form.html', form=form, title="Nhập kho Sản phẩm")


@admin_bp.route('/inventory/update/<int:inventory_id>', methods=['POST'])
@login_required
@admin_required # CHỈ ADMIN sửa trực tiếp
def update_inventory(inventory_id):
    inventory = InventoryItem.query.get_or_404(inventory_id); new_quantity = request.form.get('quantity', type=int); new_min_quantity = request.form.get('min_quantity', type=int)
    updated = False; original_qty = inventory.quantity
    try:
        if new_quantity is not None and new_quantity >= 0 and inventory.quantity != new_quantity: inventory.quantity = new_quantity; updated = True
        if new_min_quantity is not None and new_min_quantity >= 0 and inventory.min_quantity != new_min_quantity: inventory.min_quantity = new_min_quantity; updated = True
        if updated:
            # Chỉ cập nhật last_restocked nếu SL tăng từ 0 lên > 0 hoặc tăng nói chung
            if inventory.quantity > original_qty or (original_qty <= 0 and inventory.quantity > 0):
                 inventory.last_restocked = datetime.utcnow()
            inventory.last_updated = datetime.utcnow()
            try: db.session.commit(); flash('Cập nhật kho thành công!', 'success')
            except Exception as e: db.session.rollback(); flash(f'Lỗi cập nhật kho: {str(e)}', 'danger'); current_app.logger.error(...)
        else: flash('Không có thay đổi.', 'info')
    except Exception as e: db.session.rollback(); flash(f'Lỗi cập nhật kho: {str(e)}', 'danger'); current_app.logger.error(...)
    return redirect(url_for('admin.inventory', page=request.args.get('page', 1)))

@admin_bp.route('/inventory/batch-update', methods=['POST'])
@login_required
@admin_required # CHỈ ADMIN
def batch_update_inventory():
    uploaded_file = request.files.get('batch_file'); updated_count = 0; error_count = 0; errors_list = []
    if not uploaded_file or not uploaded_file.filename.lower().endswith('.csv'):
        flash('Vui lòng chọn file CSV.', 'danger' if uploaded_file else 'warning')
        return redirect(url_for('admin.inventory'))
    try:
        stream = io.StringIO(uploaded_file.stream.read().decode("UTF8"), newline=None); csv_reader = csv.reader(stream)
        header = next(csv_reader); name_idx = header.index('product_name'); qty_idx = header.index('quantity')
        items_to_update = []
        for i, row in enumerate(csv_reader):
            if not row: continue
            try:
                product_name = row[name_idx].strip(); quantity_str = row[qty_idx].strip()
                if not product_name or not quantity_str: raise ValueError("Tên hoặc SL trống")
                product = Product.query.filter(func.lower(Product.name) == func.lower(product_name)).first()
                if not product: raise ValueError(f"Không tìm thấy SP '{product_name}'")
                quantity = int(quantity_str);
                if quantity < 0: raise ValueError("Số lượng không âm")
                items_to_update.append({'product_id': product.id, 'quantity': quantity, 'line': i+2})
            except (ValueError, IndexError) as row_e: errors_list.append(f"Dòng {i+2}: Lỗi - {row_e}."); error_count += 1
        for item_data in items_to_update:
            inventory_item = InventoryItem.query.filter_by(product_id=item_data['product_id']).first()
            if inventory_item: inventory_item.quantity = item_data['quantity']; db.session.add(inventory_item); updated_count += 1
            else: errors_list.append(f"Dòng {item_data['line']}: Không có bản ghi tồn kho cho SP ID {item_data['product_id']}."); error_count += 1
        if updated_count > 0 or error_count > 0: db.session.commit()
        if error_count > 0: flash(f"Hoàn tất: {updated_count} thành công, {error_count} lỗi.", 'warning'); [flash(e,'danger') for e in errors_list[:10]]
        elif updated_count > 0: flash(f"Cập nhật thành công tồn kho cho {updated_count} sản phẩm.", 'success')
        else: flash("Không có sản phẩm nào được cập nhật từ file.", "info")
    except Exception as e:
        db.session.rollback(); current_app.logger.error(...); flash(f"Lỗi xử lý file: {e}", "danger")
    return redirect(url_for('admin.inventory'))

@admin_bp.route('/inventory/batch-template')
@login_required
@admin_required # CHỈ ADMIN (hoặc Staff nếu cần)
def download_inventory_template():
    si = io.StringIO(); cw = csv.writer(si); header = ['product_name', 'quantity']; cw.writerow(header)
    output = si.getvalue(); si.close()
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=inventory_batch_template.csv"})

@admin_bp.route('/inventory/<int:inventory_id>/history')
@login_required
@staff_required # CHO PHÉP Staff xem history
def inventory_history(inventory_id):
    logger = current_app.logger; limit = 30
    try:
        inventory_item = db.session.query(InventoryItem).options(joinedload(InventoryItem.product_inventory, innerjoin=False)).get(inventory_id)
        if not inventory_item: return "<div class='alert alert-warning'>Không tìm thấy mục tồn kho.</div>", 404
        product_id = inventory_item.product_id
        product = getattr(inventory_item, 'product_inventory', None)
        product_name = product.name if product else f"SP ID {product_id}"
        sales_history = db.session.query( Order.order_number, Order.created_at, OrderDetail.quantity, OrderDetail.unit_price, Order.id.label('order_id') )\
                           .join(OrderDetail, Order.id == OrderDetail.order_id)\
                           .filter( OrderDetail.product_id == product_id, Order.status.in_(['completed', 'delivered']) )\
                           .order_by(desc(Order.created_at)).limit(limit).all()
        receipt_history = db.session.query(StockReceipt).options(joinedload(StockReceipt.received_by))\
                           .filter(StockReceipt.inventory_item_id == inventory_id)\
                           .order_by(desc(StockReceipt.received_at)).limit(limit).all()
        return render_template('admin/_inventory_history_content.html', item=inventory_item, product_name=product_name,
                               sales_history=sales_history, receipt_history=receipt_history, limit=limit)
    except Exception as e:
        logger.error(f"Error fetching inventory history for item {inventory_id}: {e}", exc_info=True)
        return "<div class='alert alert-danger'>Lỗi tải lịch sử.</div>", 500


# --- Reports (ADMIN ONLY) ---
@admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    # --- Logic xử lý và render báo cáo tương ứng (đã có phân quyền ở route này) ---
    logger = current_app.logger; report_type = request.args.get('type', 'sales')
    period = request.args.get('period'); start_date_str = request.args.get('start_date'); end_date_str = request.args.get('end_date')
    end_date = datetime.utcnow().date(); start_date = end_date - timedelta(days=6); # Defaults
    try:
        if end_date_str: end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date(); period=None
        if start_date_str: start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date(); period=None
        elif period=='day': start_date = end_date
        elif period=='month': start_date = end_date.replace(day=1)
        elif period=='year': start_date = end_date.replace(month=1, day=1)
        if start_date > end_date: raise ValueError("Ngày bắt đầu sau ngày kết thúc.")
    except ValueError as date_err: flash(f"Lỗi ngày tháng: {date_err}. Dùng khoảng mặc định.", "warning")

    start_datetime = datetime.combine(start_date, time.min); end_datetime = datetime.combine(end_date, time.max)
    logger.info(f"Report request: type={report_type}, start={start_date}, end={end_date}")
    render_context = { 'report_type': report_type, 'period': period, 'start_date': start_date.strftime('%Y-%m-%d'), 'end_date': end_date.strftime('%Y-%m-%d') }
    try:
        base_order_query = Order.query.filter(Order.created_at.between(start_datetime, end_datetime), Order.status.in_(['completed', 'delivered']))
        if report_type == 'sales':
            orders_in_period = base_order_query.options(selectinload(Order.customer)).order_by(Order.created_at.asc()).all()
            total_sales = sum(o.final_amount if o.final_amount is not None else o.total_amount or 0.0 for o in orders_in_period)
            total_orders = len(orders_in_period); daily_sales = defaultdict(float); d = start_date
            while d <= end_date: daily_sales[d.strftime('%Y-%m-%d')] = 0.0; d += timedelta(days=1)
            for o in orders_in_period: amount = o.final_amount if o.final_amount is not None else o.total_amount or 0.0; daily_sales[o.created_at.strftime('%Y-%m-%d')] += float(amount)
            sorted_daily = dict(sorted(daily_sales.items()))
            chart_data = {'labels': [datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m') for d in sorted_daily.keys()], 'values': list(sorted_daily.values())}
            render_context.update({'orders': orders_in_period, 'chart_data': chart_data, 'total_sales': total_sales, 'total_orders': total_orders})
            return render_template('admin/reports/sales_report.html', **render_context)
        elif report_type == 'products':
            product_sales_data = db.session.query( Product.id, Product.name, Category.name.label('category_name'), func.sum(OrderDetail.quantity).label('total_quantity'),
                                                   func.sum(OrderDetail.subtotal).label('total_revenue'), func.avg(OrderDetail.unit_price).label('avg_price') )\
                .select_from(OrderDetail).join(Order).join(Product).join(Category)\
                .filter( Order.created_at.between(start_datetime, end_datetime), Order.status.in_(['completed', 'delivered']) )\
                .group_by(Product.id, Product.name, Category.name).order_by(desc('total_revenue')).all()
            safe_list, safe_revs = [], [];
            for p in product_sales_data:
                if isinstance(p.total_revenue, (int, float, db.Numeric)) and p.total_revenue is not None: safe_list.append(p); safe_revs.append(float(p.total_revenue))
                else: logger.warning(...)
            total_rev_prod = sum(safe_revs); top_prods_chart = safe_list[:10]
            chart_vals = [float(p.total_revenue or 0.0) for p in top_prods_chart]
            chart_data = {'labels': [p.name for p in top_prods_chart], 'values': chart_vals}; chart_vals_sum = sum(chart_vals)
            render_context.update({'product_sales': safe_list, 'chart_data': chart_data, 'total_revenue': total_rev_prod, 'chart_values_sum': chart_vals_sum})
            return render_template('admin/reports/product_report.html', **render_context)
        elif report_type == 'customers':
            customer_stats = db.session.query( User.id, User.first_name, User.last_name, User.username, User.email, User.phone, User.created_at.label('registered_date'),
                                              func.count(Order.id).label('order_count'), func.sum(case((Order.final_amount != None, Order.final_amount), else_=Order.total_amount)).label('total_spent'))\
                .join(Order, User.id == Order.user_id)\
                .filter( Order.created_at.between(start_datetime, end_datetime), Order.status.in_(['completed', 'delivered']), User.is_admin == False, User.is_staff == False )\
                .group_by(User.id).order_by(desc('total_spent'), desc('order_count')).all()
            render_context.update({'customer_stats': customer_stats})
            return render_template('admin/reports/customer_report.html', **render_context)
        elif report_type == 'inventory':
            search_inv = request.args.get('search_inventory', '')
            inv_query = db.session.query(InventoryItem).options(joinedload(InventoryItem.product_inventory).joinedload(Product.category)).join(Product, InventoryItem.product_id == Product.id)
            if search_inv: inv_query = inv_query.filter(Product.name.ilike(f'%{search_inv}%'))
            inv_items = inv_query.order_by(case((InventoryItem.quantity <= 0, 0),(InventoryItem.quantity <= InventoryItem.min_quantity, 1),else_=2), Product.name.asc()).all()
            total_items_c = len(inv_items); low_c = sum(1 for i in inv_items if 0 < i.quantity <= i.min_quantity)
            out_c = sum(1 for i in inv_items if i.quantity <= 0); adequate_c = total_items_c - low_c - out_c
            render_context.update({'inventory_items': inv_items, 'search_inventory': search_inv, 'total_items_count': total_items_c, 'low_stock_count': low_c, 'out_of_stock_count': out_c, 'adequate_stock_count': adequate_c})
            return render_template('admin/reports/general_inventory_report.html', **render_context)
    except Exception as e: logger.error(...); flash(...); return redirect(url_for('admin.dashboard'))
    logger.warning(f"Invalid report type: {report_type}"); flash("Loại báo cáo không hợp lệ.", "warning"); return redirect(url_for('admin.reports', type='sales'))


# --- Employee Management (ADMIN ONLY) ---
@admin_bp.route('/employees')
@login_required
@admin_required
def employees():
    employees = Employee.query.join(User).order_by(Employee.is_active.desc(), User.last_name.asc(), User.first_name.asc()).all()
    return render_template('admin/employees.html', employees=employees)

@admin_bp.route('/employees/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_employee():
    form = EmployeeForm()
    logger = current_app.logger # Lấy logger để sử dụng

    if request.method == 'POST':
        # Lấy dữ liệu User từ form POST
        user_email = request.form.get('email').strip().lower() if request.form.get('email') else None
        user_fname = request.form.get('first_name', '').strip()
        user_lname = request.form.get('last_name', '').strip()
        user_phone = request.form.get('phone', '').strip() or None

        # Kiểm tra các trường bắt buộc của User
        if not form.position.data or not user_email or not user_fname or not user_lname:
            flash('Vui lòng nhập đủ thông tin: Chức vụ, Email, Họ, và Tên.', 'danger')
        # Validate form Employee (Position, Hire Date, Salary, is_staff)
        elif form.validate():
            user = User.query.filter(User.email.ilike(user_email)).first()
            new_user_created = False

            # Xử lý logic tạo hoặc cập nhật User
            if user and not user.is_staff: # User tồn tại nhưng chưa phải staff -> nâng cấp
                user.is_staff = True
                user.first_name = user_fname
                user.last_name = user_lname
                user.phone = user_phone
                flash(f"Tài khoản '{user_email}' đã tồn tại, cập nhật thành Nhân viên.", 'info')
                logger.info(f"Existing user {user.id} promoted to Staff.")
            elif user and user.is_staff: # User tồn tại và đã là staff -> Báo lỗi
                flash(f'Nhân viên với email "{user_email}" đã tồn tại.', 'warning')
                # Không return render_template ở đây nữa, để nó chạy xuống dưới render cuối hàm
            else: # User chưa tồn tại -> Tạo mới
                default_pass = 'dragonstaff123'
                # Tạo username duy nhất phòng trường hợp trùng lặp tiềm ẩn
                base_uname = user_email.split('@')[0]
                unique_suffix = str(uuid.uuid4())[:4]
                uname = f"{base_uname}_{unique_suffix}"
                # Đảm bảo username không quá dài (ví dụ: 64 ký tự)
                max_len = 64
                if len(uname) > max_len:
                    uname = uname[:max_len - len(unique_suffix) - 1] + "_" + unique_suffix

                user = User(username=uname, email=user_email, first_name=user_fname, last_name=user_lname, phone=user_phone, is_staff=True, is_admin=False)
                user.set_password(default_pass)
                db.session.add(user)
                db.session.flush() # Lấy ID của user mới
                new_user_created = True
                flash(f"Đã tạo tài khoản mới cho '{user_email}'. Mật khẩu mặc định: dragonstaff123", 'info')
                logger.info(f"Created new User ({user.id}) for Staff email: {user_email}")

            # Nếu đã có user (từ query hoặc mới tạo) thì tạo Employee record
            if user:
                try:
                    emp = Employee(user_id=user.id,
                                   position=form.position.data,
                                   # Dùng ngày hiện tại nếu không chọn hire_date
                                   hire_date=form.hire_date.data or datetime.utcnow().date(),
                                   salary=form.salary.data, # Salary có thể là None
                                   is_active=True, # Mặc định là active
                                   # is_staff của Employee model không còn nữa?
                                   )
                    # Cập nhật is_staff trong User model dựa vào form
                    user.is_staff = form.is_staff.data # <--- CẬP NHẬT is_staff user dựa vào form

                    db.session.add(emp)
                    # Nếu User mới được tạo, cần add lại vào session để update is_staff (nếu cần)
                    if not db.session.is_modified(user):
                        db.session.add(user)
                    db.session.commit()
                    flash('Thêm thông tin nhân viên thành công!', 'success')
                    logger.info(f"Successfully created Employee record for user {user.id}")
                    return redirect(url_for('admin.employees'))
                except Exception as e_emp:
                    db.session.rollback()
                    err_msg = f'Lỗi khi lưu thông tin công việc: {str(e_emp)}'
                    if new_user_created:
                        flash(f"{err_msg}. Tài khoản người dùng cho '{user_email}' có thể đã được tạo nhưng thông tin nhân viên thì chưa.", 'danger')
                    else:
                        flash(err_msg, 'danger')
                    logger.error(f"Error adding Employee record for user {user.id if user else 'unknown'}: {e_emp}", exc_info=True)
        else: # form.validate() trả về False
             flash('Dữ liệu nhập cho Thông tin Công việc không hợp lệ.', 'danger')
             logger.warning(f"EmployeeForm validation failed: {form.errors}")
    # Render template cho cả GET và khi POST bị lỗi validation/exception
    return render_template('admin/employee_form.html', form=form, title='Thêm nhân viên', legend='Thêm nhân viên mới')


@admin_bp.route('/employees/edit/<int:employee_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    user = User.query.get_or_404(employee.user_id)
    form = EmployeeForm(obj=employee) # Chỉ chứa trường của Employee model

    # Dùng user object trực tiếp thay vì user_data dict cho rõ ràng hơn
    # user_data = {...} # Có thể bỏ dòng này

    if request.method == 'POST':
        # Validate phần EmployeeForm trước
        if form.validate():
            logger = current_app.logger
            original_email = user.email # Lưu lại email cũ để kiểm tra thay đổi

            # --- Lấy giá trị User từ request.form ---
            user.first_name = request.form.get('first_name', user.first_name).strip()
            user.last_name = request.form.get('last_name', user.last_name).strip()
            user.phone = request.form.get('phone', user.phone).strip() or None # Để phone có thể là None
            new_email = request.form.get('email', user.email).strip().lower()

            # --- Lấy giá trị quyền và trạng thái từ request.form ---
            # Chỉ cho phép current admin thay đổi is_admin
            can_change_admin = hasattr(current_user, 'is_admin') and current_user.is_admin
            new_is_admin = request.form.get('is_admin') == 'on' if can_change_admin else user.is_admin
            new_is_staff = request.form.get('is_staff') == 'on' # Checkbox Is Staff từ form EmployeeForm WTForms? Không, lấy từ HTML input
            new_is_active = request.form.get('is_active') == 'on' # Checkbox Is Active từ HTML input

            logger.debug(f"Updating Employee {employee_id} (User {user.id}): Submitted -> is_admin={new_is_admin}, is_staff={new_is_staff}, is_active={new_is_active}")

            # --- Xử lý cập nhật Email ---
            if new_email != original_email:
                existing_user = User.query.filter(User.email.ilike(new_email), User.id != user.id).first()
                if existing_user:
                    flash(f"Email '{new_email}' đã được người khác sử dụng.", 'warning')
                    # Render lại form với lỗi, giữ lại dữ liệu user đã nhập
                    return render_template('admin/employee_form.html', form=form, user=user, title='Chỉnh sửa nhân viên', employee=employee, legend=f'Chỉnh sửa: {user.full_name}')
                user.email = new_email

            # --- Xử lý cập nhật quyền logic User ---
            # Ưu tiên quyền Admin: Nếu check Admin, thì user phải là staff
            if new_is_admin:
                user.is_admin = True
                user.is_staff = True # Admin luôn là Staff
                logger.debug(f"Set roles for user {user.id}: Admin=True, Staff=True")
            elif new_is_staff:
                # Nếu check Staff nhưng không check Admin
                user.is_admin = False
                user.is_staff = True
                logger.debug(f"Set roles for user {user.id}: Admin=False, Staff=True")
            else:
                # Nếu cả Admin và Staff đều không được check
                user.is_admin = False
                user.is_staff = False
                logger.debug(f"Set roles for user {user.id}: Admin=False, Staff=False")

            # --- Xử lý cập nhật thông tin Employee ---
            employee.position = form.position.data
            employee.hire_date = form.hire_date.data
            # Gán salary là None nếu không nhập hoặc là 0
            salary_input = form.salary.data
            employee.salary = float(salary_input) if salary_input is not None else None
            employee.is_active = new_is_active

            # Lưu thay đổi vào DB
            try:
                # Lưu cả User và Employee object
                db.session.add(user)
                db.session.add(employee)
                db.session.commit()
                flash('Cập nhật thông tin nhân viên thành công!', 'success')
                logger.info(f"Successfully updated Employee {employee.id} and User {user.id}.")
                return redirect(url_for('admin.employees'))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error updating employee ID {employee_id} or user ID {user.id}: {e}", exc_info=True)
                flash(f'Lỗi khi cập nhật: {str(e)}', 'danger')

        else: # EmployeeForm không hợp lệ
            flash('Dữ liệu công việc không hợp lệ. Vui lòng kiểm tra lại.', 'danger')

    # GET request hoặc khi form POST không validate
    return render_template('admin/employee_form.html', form=form, user=user, title='Chỉnh sửa nhân viên', employee=employee, legend=f'Chỉnh sửa: {user.full_name}')


@admin_bp.route('/employees/toggle-active/<int:employee_id>', methods=['POST'])
@login_required
@admin_required
def toggle_employee_active_status(employee_id):
    employee = Employee.query.get_or_404(employee_id); user = User.query.get_or_404(employee.user_id)
    try:
        employee.is_active = not employee.is_active
        if not user.is_admin: user.is_staff = employee.is_active
        try: db.session.commit(); status_text = "kích hoạt" if employee.is_active else "vô hiệu hóa"; flash(f'Đã {status_text} NV {user.full_name}.', 'success')
        except Exception as e_db: db.session.rollback(); flash(...); current_app.logger.error(...)
    except Exception as e: flash(f'Lỗi: {str(e)}', 'danger'); current_app.logger.error(...)
    return redirect(url_for('admin.employees'))


@admin_bp.route('/employees/send-reset-link/<int:employee_id>', methods=['POST'])
@login_required
@admin_required
def send_employee_reset_link(employee_id):
    employee = Employee.query.get_or_404(employee_id); user = User.query.get(employee.user_id)
    if not user: flash("Lỗi: Không tìm thấy tài khoản người dùng.", "danger"); return redirect(...)
    if not user.email: flash(f"NV '{user.full_name}' không có email.", "warning"); return redirect(...)
    if send_reset_email(user, endpoint_name='admin.reset_password'): flash(f"Đã gửi link đến: {user.email}", "success")
    else: flash("Gửi email thất bại.", "danger")
    return redirect(request.referrer or url_for('admin.edit_employee', employee_id=employee_id))

# --- Customer Management (ADMIN ONLY) ---
@admin_bp.route('/users')
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int); search = request.args.get('q', ''); ban_filter = request.args.get('banned', type=int); per_page = 20
    query = User.query.filter(User.is_admin == False, User.is_staff == False)
    if search: search_term = f"%{search}%"; query = query.filter(or_(User.username.ilike(search_term), User.email.ilike(search_term), User.phone.ilike(search_term), (User.first_name + ' ' + User.last_name).ilike(search_term)))
    if ban_filter == 1: query = query.filter(User.is_comment_banned == True)
    elif ban_filter == 0: query = query.filter(User.is_comment_banned == False)
    users_pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/users.html', users=users_pagination.items, pagination=users_pagination, search_term=search, ban_filter=ban_filter, title="Quản lý Khách hàng")

@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    user = User.query.filter(User.id == user_id, User.is_admin == False, User.is_staff == False).first_or_404()
    recent_orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).limit(5).all()
    recent_reviews = Review.query.options(joinedload(Review.product)).filter_by(user_id=user_id).order_by(Review.created_at.desc()).limit(5).all()
    return render_template('admin/user_detail.html', user=user, recent_orders=recent_orders, recent_reviews=recent_reviews, title=f"Chi tiết: {user.username}")

@admin_bp.route('/users/toggle-ban/<int:user_id>', methods=['POST']) # Note: Route name fixed from previous example
@login_required
@admin_required
def toggle_user_comment_ban(user_id):
    user = User.query.get_or_404(user_id); logger = current_app.logger
    if user.is_admin or user.is_staff: flash("Không thể cấm NV/Admin.", 'danger'); return redirect(...)
    try:
        action_text = "Bỏ cấm" if user.is_comment_banned else "Cấm"; user.is_comment_banned = not user.is_comment_banned
        if not user.is_comment_banned: user.review_warning_count = 0; action_text += " & reset cảnh báo"
        db.session.commit(); flash(f"Đã {action_text} quyền bình luận của '{user.username}'.", 'success'); logger.info(...)
    except Exception as e: db.session.rollback(); logger.error(...); flash(...)
    redirect_url = url_for('admin.user_detail', user_id=user_id) if request.referrer and f'/users/{user_id}' in request.referrer else url_for('admin.users')
    return redirect(redirect_url)

@admin_bp.route('/users/send-reset/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def send_user_reset_link(user_id):
    user = User.query.get_or_404(user_id); logger = current_app.logger
    if user.is_admin or user.is_staff: flash("Chỉ gửi link cho khách hàng.", 'warning'); return redirect(...)
    if not user.email: flash(f"Người dùng '{user.username}' không có email.", "warning"); return redirect(...)
    if send_reset_email(user): flash(f"Đã gửi link đến: {user.email}", "success"); logger.info(...)
    else: flash("Gửi email thất bại.", "danger")
    return redirect(request.referrer or url_for('admin.user_detail', user_id=user_id))

# --- Content Management (Stories - ADMIN ONLY) ---
@admin_bp.route('/interesting-stories')
@login_required
@admin_required
def interesting_stories():
    stories = InterestingStory.query.order_by(InterestingStory.status, InterestingStory.created_at.desc()).all()
    return render_template('admin/interesting_stories.html', stories=stories, title="Câu chuyện Thú vị")

@admin_bp.route('/interesting-stories/generate', methods=['POST'])
@login_required
@admin_required
def generate_story():
    try:
        ai_content = generate_interesting_story()
        if not ai_content: flash("AI không thể tạo nội dung.", "danger"); return redirect(...)
        words = ai_content.split(); default_title = " ".join(words[:6])+"..." if len(words)>6 else ai_content[:50]+"..."
        new_story = InterestingStory(title=default_title, content=ai_content, status='draft', generated_by_ai=True)
        db.session.add(new_story); db.session.commit()
        flash("Đã tạo truyện nháp bằng AI.", "success"); return redirect(url_for('admin.edit_story', story_id=new_story.id))
    except Exception as e: db.session.rollback(); current_app.logger.error(...); flash(...); return redirect(...)

@admin_bp.route('/interesting-stories/edit/<int:story_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_story(story_id):
    story = InterestingStory.query.get_or_404(story_id); form = InterestingStoryForm(obj=story)
    current_image_full_url = url_for('static', filename=story.image_url) if story.image_url else None
    if form.validate_on_submit():
        old_image_rel = story.image_url; image_file = form.image_file.data; new_image_rel = old_image_rel; removed = request.form.get('remove_image') == '1'
        try:
            if removed: new_image_rel = None
            elif image_file:
                saved_path = save_story_image(image_file)
                if saved_path: new_image_rel = saved_path
                else: flash("Lưu ảnh mới thất bại.", "warning") # Giữ ảnh cũ

            story.title = form.title.data; story.content = form.content.data; story.image_url = new_image_rel; story.updated_at = datetime.utcnow()
            db.session.commit()
            if old_image_rel and new_image_rel != old_image_rel: delete_file(old_image_rel)
            flash("Cập nhật truyện thành công.", "success"); return redirect(url_for('admin.interesting_stories'))
        except Exception as e:
            db.session.rollback();
            if new_image_rel and new_image_rel != old_image_rel: delete_file(new_image_rel) # Xóa ảnh mới nếu lỗi DB
            flash(f"Lỗi cập nhật truyện: {e}", "danger"); current_app.logger.error(...)
    elif request.method == 'POST': flash("Lỗi nhập liệu.", "warning")
    return render_template('admin/interesting_story_form.html', form=form, story=story, title="Chỉnh sửa truyện", current_image_url=current_image_full_url)

@admin_bp.route('/interesting-stories/toggle-status/<int:story_id>', methods=['POST'])
@login_required
@admin_required
def toggle_story_status(story_id):
    story = InterestingStory.query.get_or_404(story_id)
    try:
        new_status = 'published' if story.status == 'draft' else 'draft'
        story.status = new_status; story.updated_at = datetime.utcnow(); db.session.commit()
        action = "Đăng" if new_status=='published' else "Gỡ"
        flash(f'Đã {action} câu chuyện "{story.title[:30]}...".', 'success')
    except Exception as e: db.session.rollback(); flash(f"Lỗi đổi trạng thái: {e}", "danger"); current_app.logger.error(...)
    return redirect(url_for('admin.interesting_stories'))

@admin_bp.route('/interesting-stories/delete/<int:story_id>', methods=['POST'])
@login_required
@admin_required
def delete_story(story_id):
    story = InterestingStory.query.get_or_404(story_id); title = story.title; old_image = story.image_url
    try:
        db.session.delete(story); db.session.commit()
        if old_image: delete_file(old_image)
        flash(f'Đã xóa "{title[:30]}...".', 'success')
    except Exception as e: db.session.rollback(); flash(f"Lỗi xóa truyện: {e}", "danger"); current_app.logger.error(...)
    return redirect(url_for('admin.interesting_stories'))

@admin_bp.route('/interesting-stories/rewrite/<int:story_id>', methods=['POST'])
@login_required
@admin_required
def rewrite_story_ai(story_id):
    logger=current_app.logger; logger.info(f"AI rewrite request: Story {story_id}")
    try:
        ai_content = generate_interesting_story()
        if ai_content: return jsonify({'success': True, 'new_content': ai_content})
        else: raise ValueError("AI generation failed.")
    except Exception as e: logger.error(...); return jsonify({'success': False, 'message': f'Lỗi AI: {str(e)}'}), 500

# --- Promotions (ADMIN ONLY) ---
@admin_bp.route('/promotions')
@login_required
@admin_required
def promotions():
    page = request.args.get('page', 1, type=int); per_page = 15; search_term = request.args.get('q', ''); query = Promotion.query
    if search_term: query = query.filter(or_(Promotion.name.ilike(f"%{search_term}%"), Promotion.code.ilike(f"%{search_term}%")))
    pagination = query.order_by(Promotion.end_date.desc(), Promotion.start_date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/promotions.html', promotions=pagination.items, pagination=pagination, q=search_term, title="Quản lý Khuyến mãi")

@admin_bp.route('/promotions/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_promotion():
    form = PromotionForm(); logger = current_app.logger
    if form.validate_on_submit():
        code = form.code.data.upper().strip() if form.code.data else None
        if code and Promotion.query.filter(func.lower(Promotion.code) == func.lower(code)).first(): flash(...); return render_template(...)
        if form.discount_percent.data and form.discount_amount.data: flash(...); return render_template(...)
        if not form.discount_percent.data and not form.discount_amount.data: flash(...); return render_template(...)
        if form.start_date.data > form.end_date.data: flash(...); return render_template(...)
        try:
            new_promo = Promotion( name=form.name.data, description=form.description.data, discount_percent=form.discount_percent.data,
                                  discount_amount=form.discount_amount.data, code=code, start_date=form.start_date.data, end_date=form.end_date.data, is_active=form.is_active.data )
            db.session.add(new_promo); db.session.commit(); flash('Thêm KM thành công!', 'success'); logger.info(...)
            return redirect(url_for('admin.promotions'))
        except Exception as e: db.session.rollback(); logger.error(...); flash(...)
    elif request.method == 'POST': logger.warning(...); flash('Lỗi form.', 'danger')
    return render_template('admin/promotion_form.html', form=form, title="Thêm Khuyến mãi")

@admin_bp.route('/promotions/edit/<int:promotion_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_promotion(promotion_id):
    promo = Promotion.query.get_or_404(promotion_id); form = PromotionForm(obj=promo); logger = current_app.logger
    if form.validate_on_submit():
        new_code = form.code.data.upper().strip() if form.code.data else None
        if new_code and new_code != promo.code:
            if Promotion.query.filter(func.lower(Promotion.code)==func.lower(new_code), Promotion.id != promotion_id).first(): flash(...); return render_template(...)
        if form.discount_percent.data and form.discount_amount.data: flash(...); return render_template(...)
        if not form.discount_percent.data and not form.discount_amount.data: flash(...); return render_template(...)
        if form.start_date.data > form.end_date.data: flash(...); return render_template(...)
        try:
            promo.name = form.name.data; promo.description = form.description.data; promo.discount_percent = form.discount_percent.data;
            promo.discount_amount = form.discount_amount.data; promo.code = new_code; promo.start_date = form.start_date.data;
            promo.end_date = form.end_date.data; promo.is_active = form.is_active.data
            db.session.commit(); flash('Cập nhật KM thành công!', 'success'); logger.info(...); return redirect(url_for('admin.promotions'))
        except Exception as e: db.session.rollback(); logger.error(...); flash(...)
    elif request.method == 'POST': logger.warning(...); flash('Lỗi form.', 'danger')
    return render_template('admin/promotion_form.html', form=form, title="Chỉnh sửa Khuyến mãi", promotion=promo)

@admin_bp.route('/promotions/delete/<int:promotion_id>', methods=['POST'])
@login_required
@admin_required
def delete_promotion(promotion_id):
    promo = Promotion.query.get_or_404(promotion_id); name = promo.name; logger = current_app.logger
    try: db.session.delete(promo); db.session.commit(); logger.info(...); flash(f'Đã xóa KM "{name}".', 'success')
    except Exception as e: db.session.rollback(); logger.error(...); flash(...)
    return redirect(url_for('admin.promotions'))

@admin_bp.route('/promotions/toggle/<int:promotion_id>', methods=['POST'])
@login_required
@admin_required
def toggle_promotion_active(promotion_id):
    promo = Promotion.query.get_or_404(promotion_id); logger = current_app.logger
    try:
        promo.is_active = not promo.is_active; status = "kích hoạt" if promo.is_active else "vô hiệu hóa"; db.session.commit()
        logger.info(...); flash(f'Đã {status} KM "{promo.name}".', 'success')
    except Exception as e: db.session.rollback(); logger.error(...); flash(...)
    return redirect(url_for('admin.promotions'))

# --- Reviews (ADMIN ONLY) ---
@admin_bp.route('/reviews')
@login_required
@admin_required
def manage_reviews():
    page = request.args.get('page', 1, type=int); query = request.args.get('q', ''); toxic = request.args.get('filter_toxic', ''); per_page=20
    base_query = Review.query.options(joinedload(Review.product), joinedload(Review.author))
    if query: base_query = base_query.join(Product, Review.product_id==Product.id, isouter=True).join(User, Review.user_id==User.id, isouter=True).filter(or_(Review.content.ilike(f'%{query}%'), Review.original_content.ilike(f'%{query}%'), Product.name.ilike(f'%{query}%'), User.username.ilike(f'%{query}%')))
    if toxic == 'toxic': base_query = base_query.filter(Review.is_toxic_guess == True)
    elif toxic == 'clean': base_query = base_query.filter(Review.is_toxic_guess != True)
    reviews_pagination = base_query.order_by(Review.is_toxic_guess.desc().nullslast(), Review.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/reviews.html', reviews_page=reviews_pagination, filter_toxic=toxic, q=query, title="Quản lý Đánh giá")

@admin_bp.route('/reviews/delete/<int:review_id>', methods=['POST'])
@login_required
@admin_required
def delete_review(review_id):
    review = Review.query.get_or_404(review_id)
    try: db.session.delete(review); db.session.commit(); flash("Xóa đánh giá thành công.", "success")
    except Exception as e: db.session.rollback(); current_app.logger.error(...); flash(...)
    return redirect(request.referrer or url_for('admin.manage_reviews'))

@admin_bp.route('/reviews/update-status/<int:review_id>', methods=['POST'])
@login_required
@admin_required
def update_review_status(review_id):
    review = Review.query.get_or_404(review_id); new_status = request.form.get('status')
    if new_status not in ['approved', 'rejected']: flash("Trạng thái không hợp lệ.", 'danger'); return redirect(...)
    try:
        original = review.status; review.status = new_status; db.session.commit(); action = "Duyệt" if new_status=='approved' else "Từ chối"
        flash(f"Đã {action.lower()} đánh giá ID {review.id}.", 'success'); current_app.logger.info(...)
    except Exception as e: db.session.rollback(); current_app.logger.error(...); flash(...)
    return redirect(request.referrer or url_for('admin.manage_reviews'))

@admin_bp.route('/reviews/analyze-old')
@login_required
@admin_required
def analyze_old_reviews():
    logger = current_app.logger; logger.info("Starting bulk sentiment analysis...")
    try:
        reviews = Review.query.filter(Review.sentiment_label == None).limit(200).all()
        if not reviews: flash("Tất cả đã được phân tích.", "info"); return redirect(...)
        count = 0
        for r in reviews:
            if r.content and r.content.strip():
                 analysis = analyze_review_sentiment(r.content); r.sentiment_label = analysis.get('sentiment_label')
                 r.sentiment_score = analysis.get('sentiment_score'); r.is_toxic_guess = analysis.get('is_toxic'); db.session.add(r); count += 1
        db.session.commit(); logger.info(f"Analyzed {count} reviews."); flash(f"Cập nhật sentiment cho {count} đánh giá.", "success")
    except Exception as e: db.session.rollback(); logger.error(...); flash(...)
    return redirect(url_for('admin.manage_reviews'))

# --- Contact Messages (ADMIN ONLY) ---
@admin_bp.route('/messages')
@login_required
@admin_required
def contact_messages():
    page = request.args.get('page', 1, type=int); per_page = 20; filter_ = request.args.get('filter', 'all')
    query = ContactMessage.query
    if filter_ == 'unread': query = query.filter_by(is_read=False)
    elif filter_ == 'read': query = query.filter_by(is_read=True)
    pagination = query.order_by(ContactMessage.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/messages.html', messages=pagination.items, pagination=pagination, current_filter=filter_, title="Hộp thư Liên hệ")

@admin_bp.route('/messages/<int:message_id>')
@login_required
@admin_required
def view_message(message_id):
    message = ContactMessage.query.get_or_404(message_id)
    if not message.is_read:
        message.is_read = True
        try: db.session.commit()
        except Exception as e: db.session.rollback(); current_app.logger.error(...); flash(...)
    return render_template('admin/message_detail.html', message=message, title="Chi tiết Tin nhắn")

@admin_bp.route('/messages/delete/<int:message_id>', methods=['POST'])
@login_required
@admin_required
def delete_message(message_id):
    message = ContactMessage.query.get_or_404(message_id)
    try: db.session.delete(message); db.session.commit(); flash("Đã xóa tin nhắn.", "success")
    except Exception as e: db.session.rollback(); flash(...); current_app.logger.error(...)
    return redirect(url_for('admin.contact_messages'))

# --- Location Management (ADMIN ONLY) ---
@admin_bp.route('/locations')
@login_required
@admin_required
def locations():
    page = request.args.get('page', 1, type=int); search = request.args.get('q', ''); per_page = 15; query = Location.query
    if search: query = query.filter(or_(Location.name.ilike(f"%{search}%"), Location.address.ilike(f"%{search}%"), Location.phone.ilike(f"%{search}%")))
    pagination = query.order_by(Location.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/locations.html', locations=pagination.items, pagination=pagination, search_term=search, title="Quản lý Địa điểm")

@admin_bp.route('/locations/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_location():
    form = LocationForm()
    if form.validate_on_submit():
        try:
            loc = Location( name=form.name.data, address=form.address.data, phone=form.phone.data or None, hours=form.hours.data or None,
                           latitude=form.latitude.data if form.latitude.data is not None else None, longitude=form.longitude.data if form.longitude.data is not None else None,
                           map_embed_url=form.map_embed_url.data or None, is_active=form.is_active.data )
            db.session.add(loc); db.session.commit(); flash(f'Thêm địa điểm "{loc.name}" thành công!', 'success')
            return redirect(url_for('admin.locations'))
        except Exception as e: db.session.rollback(); current_app.logger.error(...); flash(...)
    elif request.method == 'POST': flash('Lỗi nhập liệu.', 'warning')
    return render_template('admin/location_form.html', form=form, title="Thêm Địa điểm", legend="Thêm Địa điểm Mới")

@admin_bp.route('/locations/edit/<int:location_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_location(location_id):
    location = Location.query.get_or_404(location_id); form = LocationForm(obj=location)
    if form.validate_on_submit():
        try:
            location.name = form.name.data; location.address = form.address.data; location.phone = form.phone.data or None;
            location.hours = form.hours.data or None; location.latitude = form.latitude.data if form.latitude.data is not None else None;
            location.longitude = form.longitude.data if form.longitude.data is not None else None; location.map_embed_url = form.map_embed_url.data or None;
            location.is_active = form.is_active.data; location.updated_at = datetime.utcnow()
            db.session.commit(); flash(f'Cập nhật địa điểm "{location.name}" thành công!', 'success')
            return redirect(url_for('admin.locations'))
        except Exception as e: db.session.rollback(); current_app.logger.error(...); flash(...)
    elif request.method == 'POST': flash('Lỗi nhập liệu.', 'warning')
    return render_template('admin/location_form.html', form=form, title="Chỉnh sửa Địa điểm", legend=f"Chỉnh sửa: {location.name}", location=location)

@admin_bp.route('/locations/delete/<int:location_id>', methods=['POST'])
@login_required
@admin_required
def delete_location(location_id):
    location = Location.query.get_or_404(location_id); name = location.name
    try: db.session.delete(location); db.session.commit(); flash(f'Đã xóa địa điểm "{name}"!', 'success')
    except Exception as e: db.session.rollback(); current_app.logger.error(...); flash(...)
    return redirect(url_for('admin.locations'))

# --- Invoice Routes (Staff & Admin) ---
@admin_bp.route('/orders/invoice/<int:order_id>')
@login_required
@staff_required # Staff có thể xem
def view_invoice(order_id):
    order = Order.query.get_or_404(order_id)
    order_details = OrderDetail.query.filter_by(order_id=order_id).all()
    shop_info = { 'name': 'Dragon Coffee Shop', 'address': '123 Đường ABC...', 'phone': '...', 'email': '...', 'logo': url_for('static', filename='images/logo_dragon_web.png') }
    return render_template('admin/invoice.html', order=order, order_details=order_details, shop_info=shop_info)


@admin_bp.route('/orders/invoice/<int:order_id>/pdf')
@login_required
@staff_required # Staff có thể in PDF
def print_invoice_pdf(order_id):
    # BỎ from weasyprint... và import os vì đã có ở đầu file
    order = Order.query.get_or_404(order_id)
    order_details = OrderDetail.query.filter_by(order_id=order_id).all()
    shop_info = { 'name': 'Dragon Coffee Shop', 'address': '...', 'phone': '...', 'email': '...', 'logo': url_for('static', filename='images/logo_dragon_web.png', _external=True) } # External True cho PDF
    try:
        html_string = render_template('admin/invoice.html', order=order, order_details=order_details, shop_info=shop_info, show_buttons=False, is_pdf=True)
        # Phần CSS và tạo PDF (không thay đổi nhiều, bỏ logging/flash nếu chạy mượt)
        # Đảm bảo các đường dẫn font/css đúng
        css_string = """ @import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@300;400;500;700&display=swap');
                     body { font-family: 'Be Vietnam Pro', sans-serif; font-size: 9pt; }
                     .invoice-actions, .no-print { display: none; }
                     table { width: 100%; border-collapse: collapse; margin-bottom: 10px;}
                     th, td { border: 1px solid #eee; padding: 5px; }
                     .text-end { text-align: right;} /* etc. */
                     @page { margin: 1cm; size: A4; } """
        # Sử dụng weasyprint để tạo PDF (bạn có thể dùng thư viện khác nếu muốn)
        html_obj = HTML(string=html_string, base_url=request.url_root)
        pdf_file = html_obj.write_pdf(stylesheets=[CSS(string=css_string)])

        response = make_response(pdf_file)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=HoaDon_{order.order_number}.pdf'
        return response
    except Exception as e:
        current_app.logger.error(f"Lỗi tạo PDF hóa đơn {order_id}: {e}", exc_info=True)
        flash("Không thể tạo PDF.", "danger")
        return redirect(url_for('admin.view_invoice', order_id=order_id))


@admin_bp.context_processor
def inject_admin_vars():
    """Injects common variables and filters into admin templates."""
    notifications = {}
    total_web_visits_count = 0 # Khởi tạo
    if current_user.is_authenticated and (current_user.is_admin or current_user.is_staff):
        try:
            notifications = {
                'new_order_count': Order.query.filter(Order.status == 'pending').count(),
                'unread_message_count': ContactMessage.query.filter_by(is_read=False).count(),
                'inventory_alert_count': InventoryItem.query.filter(InventoryItem.quantity <= InventoryItem.min_quantity).count(),
                'pending_review_count': Review.query.filter_by(status='pending').count()
            }
            # Query tổng số lượt truy cập
            total_web_visits_count = db.session.query(func.count(WebVisit.id)).scalar() # Sửa lại scalar()
        except Exception as e:
            current_app.logger.error(f"Error injecting notifications/visits: {e}", exc_info=False)

    return dict(
        format_currency=format_currency,
        total_web_visits=total_web_visits_count, # <-- TRUYỀN BIẾN NÀY
        **notifications 
    )


@admin_bp.route('/orders/export/csv')
@login_required
@admin_required # Chỉ Admin mới được xuất file
def export_orders_csv():
    """Xuất danh sách đơn hàng (theo bộ lọc hiện tại) ra file CSV."""
    logger = current_app.logger
    logger.info("Initiating CSV export for orders...")
    # Lấy các tham số lọc từ URL (giống trang danh sách đơn hàng)
    status_filter = request.args.get('status')
    search_term = request.args.get('q', '')

    try:
        # Bắt đầu query với Eager Loading Customer
        query = Order.query.options(
            joinedload(Order.customer) # Tải thông tin khách hàng liên quan
        )

        # --- Áp dụng bộ lọc (giống hệt route /admin/orders) ---
        if status_filter:
            query = query.filter(Order.status == status_filter)

        if search_term:
            search_like = f"%{search_term}%"
            # outerjoin để có thể tìm kiếm user ngay cả khi user_id là NULL (ít xảy ra)
            query = query.outerjoin(User, Order.user_id == User.id).filter(
                or_(
                    Order.order_number.ilike(search_like),
                    # Sử dụng func.lower() và contains() cho tìm kiếm tên không phân biệt hoa thường
                    func.lower(User.first_name + ' ' + User.last_name).contains(func.lower(search_term)),
                    User.email.ilike(search_like),
                    User.phone.ilike(search_like), # Tìm trong SĐT của User model
                    Order.contact_phone.ilike(search_like) # Tìm trong SĐT liên hệ trên đơn hàng
                )
            )
        # --- Kết thúc áp dụng bộ lọc ---

        # Lấy TẤT CẢ đơn hàng khớp bộ lọc, không phân trang
        orders_to_export = query.order_by(Order.created_at.desc()).all()

        if not orders_to_export:
            flash("Không có đơn hàng nào khớp với bộ lọc hiện tại để xuất file.", "warning")
            # Quay về trang đơn hàng với bộ lọc cũ
            return redirect(url_for('admin.orders', status=status_filter, q=search_term))

        # --- Tạo file CSV trong bộ nhớ ---
        output = io.StringIO()
        writer = csv.writer(output)

        # Định nghĩa Header cho file CSV
        header = [
            'ID Đơn hàng', 'Mã Đơn hàng', 'ID Khách hàng', 'Tên Khách hàng', 'SĐT Liên hệ',
            'Email Khách hàng', 'Ngày đặt', 'Loại Đơn', 'Trạng thái ĐH', 'PT Thanh toán',
            'TT Thanh toán', 'Tổng tiền hàng', 'Giảm giá', 'Phí Ship (Nếu có)', 'Thuế (Nếu có)',
            'Tổng Thanh toán', 'Ghi chú', 'Địa chỉ Giao hàng'
        ]
        writer.writerow(header)

        # Viết dữ liệu từng đơn hàng
        for order in orders_to_export:
            customer_name = order.customer.full_name if order.customer else '(Khách vãng lai)'
            customer_email = order.customer.email if order.customer else ''
            user_id = order.user_id or ''
            writer.writerow([
                order.id,
                order.order_number,
                user_id,
                customer_name,
                order.contact_phone or '',
                customer_email,
                order.created_at.strftime('%Y-%m-%d %H:%M:%S') if order.created_at else '',
                order.order_type or '',
                order.status or '',
                order.payment_method or '',
                order.payment_status or '',
                order.total_amount or 0.0,
                order.discount_applied or 0.0,
                getattr(order, 'shipping_fee', 0.0), # Lấy an toàn nếu field chưa có
                getattr(order, 'tax_amount', 0.0),    # Lấy an toàn nếu field chưa có
                order.final_amount if order.final_amount is not None else order.total_amount or 0.0,
                order.notes or '',
                order.address or ''
            ])

        # Chuẩn bị nội dung file CSV để trả về
        csv_data = output.getvalue().encode('utf-8-sig') # Encode UTF-8 with BOM cho Excel
        output.close()

        # Tạo tên file động
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filter_suffix = f"_{status_filter}" if status_filter else ""
        search_suffix = f"_q_{search_term.replace(' ','_')[:15]}" if search_term else ""
        filename = f"dragoncoffee_orders_{timestamp}{filter_suffix}{search_suffix}.csv"

        # Tạo và trả về Response
        return Response(
            csv_data,
            mimetype="text/csv; charset=utf-8-sig", # Quan trọng: Chỉ định charset
            headers={"Content-Disposition": f"attachment;filename=\"{filename}\""} # Dùng dấu nháy kép
        )

    except Exception as e:
        logger.error(f"Error exporting orders to CSV: {e}", exc_info=True)
        flash("Đã xảy ra lỗi trong quá trình xuất file đơn hàng.", "danger")
        return redirect(url_for('admin.orders', status=status_filter, q=search_term)) # Quay về trang đơn hàng

@admin_bp.route('/inventory/export')
@login_required
@admin_required # Đảm bảo chỉ Admin có quyền xuất file này
def export_inventory():
    """Xuất danh sách tồn kho (theo bộ lọc hiện tại) ra file CSV."""
    logger = current_app.logger
    logger.info("Initiating CSV export for inventory...")

    # Lấy các tham số lọc từ URL
    file_format = request.args.get('format', 'csv').lower()
    status_filter = request.args.get('status', 'all')
    search_term = request.args.get('search', '') # Lấy tham số 'search'

    logger.info(f"Export Filters - Format: {file_format}, Status: {status_filter}, Search: '{search_term}'")

    if file_format != 'csv':
        flash(f"Định dạng file '{file_format}' không được hỗ trợ cho xuất tồn kho.", "danger")
        return redirect(url_for('admin.inventory'))

    try:
        # Query dữ liệu tồn kho với thông tin Product và Category
        query = db.session.query(InventoryItem).options(
            joinedload(InventoryItem.product_inventory).joinedload(Product.category)
        )

        # Luôn join với Product để có thể lọc và sắp xếp
        query = query.join(InventoryItem.product_inventory) # Sử dụng tên relationship

        # Áp dụng bộ lọc trạng thái
        if status_filter == 'low':
            query = query.filter(InventoryItem.quantity > 0, InventoryItem.quantity <= InventoryItem.min_quantity)
            filename_status = "low_stock"
        elif status_filter == 'out':
            query = query.filter(InventoryItem.quantity <= 0)
            filename_status = "out_of_stock"
        elif status_filter == 'adequate':
             query = query.filter(InventoryItem.quantity > InventoryItem.min_quantity)
             filename_status = "adequate_stock"
        else: # 'all' hoặc không xác định
            filename_status = "all"

        # Áp dụng bộ lọc tìm kiếm (theo tên sản phẩm)
        if search_term:
            query = query.filter(Product.name.ilike(f'%{search_term}%'))
            filename_search = f"search_{search_term.replace(' ','_').lower()[:20]}_" # Giới hạn độ dài tên file
        else:
            filename_search = ""

        # Sắp xếp kết quả: theo trạng thái ưu tiên (hết -> sắp hết -> đủ), sau đó theo tên SP
        inventory_items_to_export = query.order_by(
             case(
                 (InventoryItem.quantity <= 0, 0),              # Hết hàng lên đầu
                 (InventoryItem.quantity <= InventoryItem.min_quantity, 1), # Sắp hết tiếp theo
                 else_=2                                          # Đủ hàng cuối cùng
             ),
            Product.name.asc() # Sau đó sắp xếp theo tên A-Z
        ).all()

        if not inventory_items_to_export:
            flash("Không có dữ liệu tồn kho nào khớp với bộ lọc để xuất.", "warning")
            # Quay về trang inventory với bộ lọc hiện tại
            return redirect(url_for('admin.inventory', status_filter=status_filter, search=search_term))

        # --- Tạo file CSV ---
        output = io.StringIO()
        writer = csv.writer(output)

        # Viết dòng Header
        header = [
            'ID Sản phẩm', 'Tên Sản phẩm', 'Danh mục', 'Số lượng hiện tại',
            'Số lượng tối thiểu', 'Đơn vị', 'Lần nhập cuối', 'Lần cập nhật cuối'
        ]
        writer.writerow(header)

        # Viết dữ liệu cho từng item
        for item in inventory_items_to_export:
            # Lấy thông tin an toàn, phòng trường hợp product_inventory bị None
            product_name = item.product_inventory.name if item.product_inventory else 'Lỗi SP'
            category_name = item.product_inventory.category.name if item.product_inventory and item.product_inventory.category else 'N/A'
            last_restocked_str = item.last_restocked.strftime('%Y-%m-%d %H:%M:%S') if item.last_restocked else ''
            last_updated_str = item.last_updated.strftime('%Y-%m-%d %H:%M:%S') if item.last_updated else ''

            writer.writerow([
                item.product_id,
                product_name,
                category_name,
                item.quantity,
                item.min_quantity,
                item.unit or '',
                last_restocked_str,
                last_updated_str
            ])

        # Chuẩn bị Response
        csv_data = output.getvalue().encode('utf-8-sig') # Encode UTF-8 with BOM for Excel
        output.close()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Đặt tên file phản ánh bộ lọc (nếu có)
        filename = f"dragoncoffee_inventory_{filename_search}{filename_status}_{timestamp}.csv"

        logger.info(f"Successfully generated CSV export for inventory. Filename: {filename}")

        # Trả về file CSV cho người dùng tải
        return Response(
            csv_data,
            mimetype="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition": f"attachment;filename=\"{filename}\""}
        )

    except Exception as e:
        logger.error(f"Error exporting inventory to CSV: {e}", exc_info=True)
        flash("Đã xảy ra lỗi trong quá trình xuất file tồn kho.", "danger")
        return redirect(url_for('admin.inventory', status_filter=status_filter, search=search_term))
    

@admin_bp.route('/visits')
@login_required
@admin_required
def web_visits_history():
    page = request.args.get('page', 1, type=int)
    per_page = 30 # Số lượt truy cập mỗi trang
    search_ip = request.args.get('ip', '')
    search_path = request.args.get('path', '')
    search_email = request.args.get('email', '')

    query = WebVisit.query
    if search_ip:
        query = query.filter(WebVisit.ip_address.ilike(f"%{search_ip}%"))
    if search_path:
        query = query.filter(WebVisit.path.ilike(f"%{search_path}%"))
    if search_email:
        query = query.filter(WebVisit.user_email.ilike(f"%{search_email}%"))

    visits_pagination = query.order_by(WebVisit.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    # Lấy các giá trị duy nhất cho bộ lọc (tùy chọn, có thể nặng nếu nhiều dữ liệu)
    # distinct_ips = [ip[0] for ip in db.session.query(WebVisit.ip_address).distinct().order_by(WebVisit.ip_address).all() if ip[0]]
    # distinct_paths = [p[0] for p in db.session.query(WebVisit.path).distinct().order_by(WebVisit.path).all() if p[0]]
    
    return render_template(
        'admin/web_visits_history.html',
        visits=visits_pagination.items,
        pagination=visits_pagination,
        title="Lịch sử Truy cập Web",
        search_ip=search_ip,
        search_path=search_path,
        search_email=search_email
        # distinct_ips=distinct_ips, # Bỏ comment nếu dùng
        # distinct_paths=distinct_paths  # Bỏ comment nếu dùng
    )


@admin_bp.route('/profile')
@login_required
@staff_required 
def profile():
    return render_template('admin/admin_profile.html', 
                           user=current_user, 
                           title="Hồ sơ Tài khoản")

@admin_bp.route('/profile/confirm-pin', methods=['GET', 'POST'])
@login_required
@staff_required
def confirm_pin_for_edit():
    from flask_wtf import FlaskForm 
    from wtforms import PasswordField, SubmitField
    from wtforms.validators import DataRequired, Length

    class ConfirmPinForm(FlaskForm):
        pin = PasswordField('Mã PIN xác thực', 
                            validators=[DataRequired("Vui lòng nhập mã PIN."),
                                        Length(min=8, max=8, message="Mã PIN phải có 8 ký tự.")])
        submit = SubmitField('Xác nhận')

    confirm_form = ConfirmPinForm()
    ADMIN_EDIT_UNLOCK_PIN = "24122003" 

    if confirm_form.validate_on_submit():
        entered_pin = confirm_form.pin.data
        if entered_pin == ADMIN_EDIT_UNLOCK_PIN:
            session['admin_profile_edit_authorized'] = True
            session['admin_profile_edit_auth_time'] = datetime.utcnow().timestamp()
            flash('Xác thực thành công. Bạn có thể chỉnh sửa hồ sơ.', 'success')
            return redirect(url_for('admin.edit_profile'))
        else:
            flash('Mã PIN xác thực không đúng.', 'danger')
    
    return render_template('admin/admin_confirm_pin.html', 
                           title="Xác thực Mã PIN", 
                           confirm_form=confirm_form)


@admin_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
@staff_required
def edit_profile():
    auth_time = session.get('admin_profile_edit_auth_time')
    authorized = session.get('admin_profile_edit_authorized', False)
    AUTH_TIMEOUT_SECONDS = 10 * 60 

    if not authorized or not auth_time or (datetime.utcnow().timestamp() - auth_time > AUTH_TIMEOUT_SECONDS):
        session.pop('admin_profile_edit_authorized', None)
        session.pop('admin_profile_edit_auth_time', None)
        flash('Vui lòng xác thực mã PIN để chỉnh sửa hồ sơ.', 'warning')
        return redirect(url_for('admin.confirm_pin_for_edit'))

    form = UpdateProfileForm(
        original_username=current_user.username,
        original_email=current_user.email,
        obj=current_user
    )

    if form.validate_on_submit():
        logger = current_app.logger
        old_avatar_relative_path = current_user.avatar_url
        new_avatar_relative_path = None
        avatar_updated = False
        try:
            avatar_file = form.avatar.data
            if avatar_file:
                # Giờ hàm save_avatar_file đã được import và có thể sử dụng
                saved_path = save_avatar_file(avatar_file) 
                if saved_path:
                    new_avatar_relative_path = saved_path
                    avatar_updated = True
                else:
                    flash("Lưu ảnh đại diện mới thất bại.", "warning")

            current_user.username = form.username.data
            current_user.email = form.email.data.lower()
            current_user.first_name = form.first_name.data
            current_user.last_name = form.last_name.data
            current_user.phone = form.phone.data
            
            if form.password.data: 
                current_user.set_password(form.password.data)
            
            if avatar_updated: 
                current_user.avatar_url = new_avatar_relative_path

            db.session.commit()
            
            session.pop('admin_profile_edit_authorized', None)
            session.pop('admin_profile_edit_auth_time', None)
            flash('Hồ sơ của bạn đã được cập nhật!', 'success')

            if avatar_updated and old_avatar_relative_path and 'default_' not in old_avatar_relative_path:
                delete_avatar_file(old_avatar_relative_path)
                
            return redirect(url_for('admin.profile'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating admin/staff profile (User ID: {current_user.id}): {e}", exc_info=True)
            flash(f'Lỗi khi cập nhật hồ sơ: {str(e)}.', 'danger')
            if new_avatar_relative_path:
                delete_avatar_file(new_avatar_relative_path)
    elif request.method == 'POST':
        current_app.logger.warning(f"Admin Profile edit validation failed for user {current_user.id}: {form.errors}")
        flash('Thông tin cập nhật không hợp lệ. Vui lòng kiểm tra lại các trường.', 'warning')

    return render_template('admin/admin_edit_profile.html', 
                           title='Chỉnh sửa Hồ sơ', 
                           form=form,
                           user=current_user)

@admin_bp.route('/profile/confirm-password', methods=['GET', 'POST'])
@login_required
@staff_required
def confirm_password_for_edit():
    from wtforms import PasswordField, SubmitField
    from wtforms.validators import DataRequired, EqualTo, Length
    from flask_wtf import FlaskForm

    class ConfirmPasswordForm(FlaskForm):
        current_password = PasswordField('Mật khẩu hiện tại', validators=[DataRequired("Vui lòng nhập mật khẩu hiện tại.")])
        submit = SubmitField('Xác nhận')

    confirm_form = ConfirmPasswordForm()

    if confirm_form.validate_on_submit():
        if current_user.check_password(confirm_form.current_password.data):
            session['admin_profile_edit_authorized'] = True # Đánh dấu đã xác thực
            session['admin_profile_edit_auth_time'] = datetime.utcnow().timestamp() # Lưu thời gian
            flash('Xác thực thành công. Bạn có thể chỉnh sửa hồ sơ.', 'success')
            return redirect(url_for('admin.edit_profile'))
        else:
            flash('Mật khẩu hiện tại không đúng.', 'danger')
    return render_template('admin/admin_confirm_password.html', 
                           title="Xác thực mật khẩu", 
                           confirm_form=confirm_form)

@admin_bp.route('/inventory/qr-code/<int:product_id>')
@login_required
@staff_required # Cho phép cả staff và admin xem/in QR
def generate_product_qr_code_image(product_id):
    """
    Sinh ra hình ảnh mã QR cho một product_id cụ thể.
    Ảnh này sẽ chứa URL đến trang chỉnh sửa sản phẩm.
    """
    logger = current_app.logger
    product = Product.query.get_or_404(product_id)

    # URL đích mà mã QR sẽ trỏ tới.
    # Chúng ta sẽ trỏ đến trang edit_product của admin.
    try:
        # QUAN TRỌNG: Dùng _external=True nếu mã QR sẽ được quét
        # từ một thiết bị không cùng mạng/domain với server.
        # Nếu chỉ dùng nội bộ và biết chắc domain, _external=False vẫn OK.
        # Vì mục đích quét bằng điện thoại, _external=True an toàn hơn.
        target_url = url_for('admin.edit_product', product_id=product.id, _external=True)
    except Exception as url_e:
        logger.error(f"Không thể tạo URL cho QR sản phẩm {product_id}: {url_e}", exc_info=True)
        return "Lỗi tạo URL cho QR", 500

    logger.info(f"Generating QR for Product ID: {product.id}, Name: '{product.name}', Target URL: {target_url}")

    try:
        qr_img = qrcode.make(target_url, border=2) # border=2 để QR nhỏ gọn hơn một chút
        img_io = BytesIO() # Tạo một đối tượng BytesIO để lưu ảnh trong bộ nhớ
        qr_img.save(img_io, 'PNG', scale=6) # Lưu ảnh dưới dạng PNG, scale để QR nét hơn
        img_io.seek(0) # Đưa con trỏ về đầu stream

        # Trả về ảnh cho trình duyệt
        return send_file(
            img_io,
            mimetype='image/png',
            as_attachment=False, # Hiển thị trực tiếp, không tải xuống
            download_name=f'qr_product_{product.id}.png' # Tên file nếu người dùng muốn lưu
        )
    except Exception as e:
        logger.error(f"Lỗi khi tạo hoặc gửi ảnh QR cho sản phẩm {product_id}: {e}", exc_info=True)
        # Có thể trả về một ảnh placeholder báo lỗi hoặc lỗi 500
        # For simplicity, returning a text error now.
        # In production, you might want a default error image.
        return "Lỗi tạo ảnh QR", 500