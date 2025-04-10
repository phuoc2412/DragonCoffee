
import os
import uuid
from datetime import datetime, timedelta, time  # Đảm bảo timedelta được import
from functools import wraps
from collections import defaultdict
from app import db # Đảm bảo đã import db
from models import InventoryItem, Product, InterestingStory,  Order, User # Import các model cần thiết
from forms import InterestingStoryForm
from ai_services import generate_interesting_story, get_inventory_recommendations
from flask import current_app, jsonify
import csv # Import module csv
import io # Import module io (hoặc StringIO từ io)
import logging

from flask import (Blueprint, flash, jsonify, make_response, redirect,
                   render_template, request, url_for, Response, current_app) # Thêm current_app import
from flask_login import current_user, login_required, login_user
# Xóa dòng này nếu không dùng fontTools trực tiếp ở đây: from fontTools.ttLib import TTFont
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration
from sqlalchemy.orm import joinedload, contains_eager, selectinload

from app import app, db
from forms import (CategoryForm, ContactForm, EmployeeForm, LoginForm,
                   ProductForm, PromotionForm, ReviewForm)
from models import (Category, ContactMessage, Employee, InventoryItem, Order,
                   OrderDetail, Product, Promotion, Review, User)
from sqlalchemy import desc, func

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = User.query.filter(func.lower(User.email) == func.lower(form.email.data)).first() # Tìm không phân biệt hoa thường
            if user is None or not user.check_password(form.password.data) or not user.is_admin:
                flash('Email, mật khẩu không hợp lệ hoặc bạn không có quyền quản trị.', 'danger')
                return redirect(url_for('admin.login'))

            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            flash('Đăng nhập quản trị thành công!', 'success')
            return redirect(next_page or url_for('admin.dashboard'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Lỗi đăng nhập Admin: {e}", exc_info=True)
            flash('Lỗi hệ thống khi đăng nhập. Vui lòng thử lại.', 'danger')
            return redirect(url_for('admin.login'))

    return render_template('admin/login.html', form=form, title="Đăng nhập Quản trị")

def admin_required(f):
    """Decorator để yêu cầu quyền admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Bạn không có quyền truy cập trang này.', 'danger')
            return redirect(url_for('admin.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/logout')
@login_required
def logout():
    """Đăng xuất người dùng."""
    logout_user()
    flash('Bạn đã đăng xuất khỏi trang quản trị.', 'info')
    return redirect(url_for('admin.login')) # Chuyển về trang login admin

@admin_bp.route('/')
@admin_bp.route('/dashboard') # Thêm alias
@login_required
@admin_required
def dashboard():
    """Hiển thị trang dashboard chính của admin."""
    try:
        total_orders = db.session.query(func.count(Order.id)).scalar()
        total_products = db.session.query(func.count(Product.id)).scalar()
        total_users = db.session.query(func.count(User.id)).filter(User.is_admin == False, User.is_staff == False).scalar() # Chỉ khách hàng
        total_revenue = db.session.query(func.sum(Order.total_amount)).filter(Order.status == 'completed').scalar() or 0.0

        recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()

        top_products = db.session.query(
            Product, func.sum(OrderDetail.quantity).label('total_sold')
        ).join(OrderDetail, OrderDetail.product_id == Product.id)\
         .join(Order, Order.id == OrderDetail.order_id)\
         .filter(Order.status == 'completed')\
         .group_by(Product.id)\
         .order_by(desc('total_sold'))\
         .limit(5).all()

        # Dữ liệu biểu đồ doanh thu 7 ngày gần nhất
        today = datetime.utcnow().date()
        date_labels = []
        sales_amounts = []
        for i in range(6, -1, -1):
            start_dt = datetime.combine(today - timedelta(days=i), datetime.min.time())
            end_dt = datetime.combine(today - timedelta(days=i), datetime.max.time())
            daily_sales = db.session.query(func.sum(Order.total_amount)).filter(
                Order.created_at >= start_dt,
                Order.created_at <= end_dt,
                Order.status == 'completed'
            ).scalar() or 0.0
            date_labels.append((today - timedelta(days=i)).strftime('%d/%m')) # dd/mm
            sales_amounts.append(float(daily_sales))

        chart_data = {'labels': date_labels, 'values': sales_amounts}

        # Dữ liệu cảnh báo tồn kho (số lượng)
        low_inventory_items = InventoryItem.query.filter(
            InventoryItem.quantity <= InventoryItem.min_quantity, InventoryItem.quantity > 0 # Sắp hết
        ).count()
        out_of_stock_items = InventoryItem.query.filter(InventoryItem.quantity <= 0).count() # Hết hàng

    except Exception as e:
        current_app.logger.error(f"Lỗi khi tải dữ liệu dashboard: {e}", exc_info=True)
        flash("Không thể tải dữ liệu dashboard. Vui lòng thử lại.", "danger")
        # Khởi tạo giá trị mặc định để tránh lỗi template
        total_orders, total_products, total_users, total_revenue = 0, 0, 0, 0.0
        recent_orders, top_products, chart_data = [], [], {'labels': [], 'values': []}
        low_inventory_items, out_of_stock_items = 0, 0


    return render_template('admin/dashboard.html',
                           total_orders=total_orders,
                           total_products=total_products,
                           total_users=total_users,
                           total_revenue=total_revenue,
                           recent_orders=recent_orders,
                           top_products=top_products,
                           chart_data=chart_data,
                           low_inventory_count=low_inventory_items, # Đổi tên biến
                           out_of_stock_count=out_of_stock_items)  # Đổi tên biến

@admin_bp.route('/menu-management')
@login_required
@admin_required
def menu_management():
    # Load tất cả sản phẩm và danh mục để hiển thị
    products = Product.query.join(Category).order_by(Category.name, Product.name).all()
    categories = Category.query.order_by(Category.name).all()
    return render_template('admin/menu_management.html', products=products, categories=categories)

@admin_bp.route('/product/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    form = ProductForm()
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by('name').all()]

    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                product = Product(
                    name=form.name.data,
                    description=form.description.data,
                    price=form.price.data,
                    image_url=form.image_url.data if form.image_url.data else None,
                    is_available=form.is_available.data,
                    is_featured=form.is_featured.data,
                    category_id=form.category_id.data
                )
                db.session.add(product)
                db.session.flush()

                inventory = InventoryItem(
                    product_id=product.id,
                    quantity=form.stock_quantity.data if form.stock_quantity.data is not None else 0,
                    min_quantity=form.min_quantity.data if form.min_quantity.data is not None else 10 # Lấy giá trị hoặc default
                )
                db.session.add(inventory)

                db.session.commit()
                flash('Thêm sản phẩm thành công!', 'success')
                return redirect(url_for('admin.menu_management'))

            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Lỗi thêm sản phẩm: {e}", exc_info=True)
                flash(f'Lỗi khi thêm sản phẩm: {str(e)}', 'danger')
                # Không redirect, để render lại form với lỗi

        else: # Form không valid khi POST
             flash('Có lỗi trong form, vui lòng kiểm tra lại các trường được đánh dấu.', 'warning')
             # current_app.logger.warning(f"Product form validation failed: {form.errors}") # Ghi log lỗi validation nếu cần

    # Render template cho GET request hoặc POST không valid
    return render_template('admin/product_form.html', form=form, title='Thêm sản phẩm', legend='Thêm sản phẩm mới')

@admin_bp.route('/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    # Query inventory, đảm bảo nó tồn tại
    inventory = InventoryItem.query.filter_by(product_id=product_id).first()
    if not inventory and request.method == 'GET':
        # Nếu inventory chưa có, tạo tạm để form hiển thị (nhưng chưa lưu)
        inventory = InventoryItem(product_id=product_id, quantity=0, min_quantity=10)
        flash("Lưu ý: Sản phẩm này chưa có bản ghi tồn kho. Số lượng mặc định là 0.", "info")


    form = ProductForm(obj=product) # Populate form với data sản phẩm
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by('name').all()]

    if request.method == 'GET':
        # Điền dữ liệu tồn kho vào form khi GET
        if inventory:
             form.stock_quantity.data = inventory.quantity
             form.min_quantity.data = inventory.min_quantity

    if form.validate_on_submit():
        try:
            product.name = form.name.data
            product.description = form.description.data
            product.price = form.price.data
            product.image_url = form.image_url.data if form.image_url.data else None
            product.is_available = form.is_available.data
            product.is_featured = form.is_featured.data
            product.category_id = form.category_id.data
            product.updated_at = datetime.utcnow() # Cập nhật thời gian

            # Cập nhật inventory (hoặc tạo mới nếu chưa có)
            if inventory:
                inventory.quantity = form.stock_quantity.data if form.stock_quantity.data is not None else inventory.quantity
                inventory.min_quantity = form.min_quantity.data if form.min_quantity.data is not None else inventory.min_quantity
                inventory.last_updated = datetime.utcnow()
                if not inventory.id: # Nếu inventory vừa được tạo tạm ở GET request
                     db.session.add(inventory)
            else: # Trường hợp hiếm gặp, nếu không query được inventory lúc đầu
                 new_inventory = InventoryItem(
                     product_id=product.id,
                     quantity=form.stock_quantity.data if form.stock_quantity.data is not None else 0,
                     min_quantity=form.min_quantity.data if form.min_quantity.data is not None else 10
                 )
                 db.session.add(new_inventory)


            db.session.commit()
            flash('Cập nhật sản phẩm thành công!', 'success')
            return redirect(url_for('admin.menu_management'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Lỗi cập nhật sản phẩm ID {product_id}: {e}", exc_info=True)
            flash(f'Lỗi khi cập nhật sản phẩm: {str(e)}', 'danger')

    elif request.method == 'POST':
        flash('Có lỗi trong form, vui lòng kiểm tra lại các trường.', 'warning')

    return render_template('admin/product_form.html', form=form, title='Chỉnh sửa sản phẩm', product=product, legend=f'Chỉnh sửa: {product.name}')

@admin_bp.route('/product/delete/<int:product_id>', methods=['POST'])
@login_required
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    try:
        # Kiểm tra ràng buộc đơn hàng
        if OrderDetail.query.filter_by(product_id=product_id).first():
            flash(f'Không thể xóa "{product.name}" vì đã tồn tại trong đơn hàng.', 'danger')
            return redirect(url_for('admin.menu_management'))

        # Xóa InventoryItem liên quan trước (nếu tồn tại)
        inventory = InventoryItem.query.filter_by(product_id=product_id).first()
        if inventory:
            db.session.delete(inventory)

        db.session.delete(product) # Sau đó xóa Product
        db.session.commit()
        flash(f'Đã xóa sản phẩm "{product.name}" và dữ liệu tồn kho liên quan!', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Lỗi xóa sản phẩm ID {product_id}: {e}", exc_info=True)
        flash(f'Lỗi khi xóa sản phẩm: {str(e)}', 'danger')
    return redirect(url_for('admin.menu_management'))

@admin_bp.route('/category/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_category():
    form = CategoryForm()
    if form.validate_on_submit():
        # Kiểm tra tên danh mục đã tồn tại chưa (không phân biệt hoa thường)
        existing_category = Category.query.filter(func.lower(Category.name) == func.lower(form.name.data)).first()
        if existing_category:
            flash(f'Tên danh mục "{form.name.data}" đã tồn tại.', 'warning')
        else:
            try:
                category = Category(
                    name=form.name.data,
                    description=form.description.data
                )
                db.session.add(category)
                db.session.commit()
                flash('Thêm danh mục thành công!', 'success')
                return redirect(url_for('admin.menu_management'))
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Lỗi thêm danh mục: {e}", exc_info=True)
                flash(f'Lỗi khi thêm danh mục: {str(e)}', 'danger')
    elif request.method == 'POST':
        flash('Có lỗi trong form, vui lòng kiểm tra lại.', 'warning')
    return render_template('admin/category_form.html', form=form, title='Thêm danh mục', legend='Thêm danh mục mới')

@admin_bp.route('/category/edit/<int:category_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    form = CategoryForm(obj=category)
    if form.validate_on_submit():
         # Kiểm tra nếu tên mới khác tên cũ và đã tồn tại
         new_name_lower = form.name.data.lower()
         if new_name_lower != category.name.lower():
             existing_category = Category.query.filter(func.lower(Category.name) == new_name_lower, Category.id != category_id).first()
             if existing_category:
                 flash(f'Tên danh mục "{form.name.data}" đã được sử dụng bởi danh mục khác.', 'warning')
                 return render_template('admin/category_form.html', form=form, title='Chỉnh sửa danh mục', category=category, legend=f'Chỉnh sửa: {category.name}')

         try:
            category.name = form.name.data
            category.description = form.description.data
            db.session.commit()
            flash('Cập nhật danh mục thành công!', 'success')
            return redirect(url_for('admin.menu_management'))
         except Exception as e:
             db.session.rollback()
             current_app.logger.error(f"Lỗi cập nhật danh mục ID {category_id}: {e}", exc_info=True)
             flash(f'Lỗi khi cập nhật danh mục: {str(e)}', 'danger')
    elif request.method == 'POST':
        flash('Có lỗi trong form, vui lòng kiểm tra lại.', 'warning')
    return render_template('admin/category_form.html', form=form, title='Chỉnh sửa danh mục', category=category, legend=f'Chỉnh sửa: {category.name}')

@admin_bp.route('/category/delete/<int:category_id>', methods=['POST'])
@login_required
@admin_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    if category.products.first(): # Kiểm tra hiệu quả hơn
        flash(f'Không thể xóa danh mục "{category.name}" vì còn chứa sản phẩm.', 'danger')
        return redirect(url_for('admin.menu_management'))
    try:
        db.session.delete(category)
        db.session.commit()
        flash(f'Đã xóa danh mục "{category.name}"!', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Lỗi xóa danh mục ID {category_id}: {e}", exc_info=True)
        flash(f'Lỗi khi xóa danh mục: {str(e)}', 'danger')
    return redirect(url_for('admin.menu_management'))

@admin_bp.route('/orders')
@login_required
@admin_required
def orders():
    page = request.args.get('page', 1, type=int)
    per_page = 15
    status_filter = request.args.get('status') # Lấy cả None
    search_term = request.args.get('q', '') # Thêm tìm kiếm

    query = Order.query

    if status_filter:
        query = query.filter(Order.status == status_filter)

    # Logic tìm kiếm theo mã đơn, tên KH, sđt, email
    if search_term:
        search_like = f"%{search_term}%"
        # Sử dụng func.lower cho tìm kiếm không phân biệt hoa thường
        query = query.outerjoin(User, Order.user_id == User.id).filter(
            db.or_(
                Order.order_number.ilike(search_like),
                # Nối tên KH lại nếu có
                func.lower(User.first_name + ' ' + User.last_name).contains(func.lower(search_term)),
                User.email.ilike(search_like),
                User.phone.ilike(search_like),
                Order.contact_phone.ilike(search_like) # Thêm tìm kiếm SĐT trên đơn hàng
                # Bỏ Order.customer_name vì nó không tồn tại trong model Order
            )
        )


    orders_pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    orders = orders_pagination.items # orders là danh sách các object Order

    return render_template('admin/orders.html',
                           orders=orders, # Truyền danh sách orders
                           pagination=orders_pagination,
                           status=status_filter, # Đổi tên biến cho rõ
                           q=search_term)        # Truyền lại term tìm kiếm

# --- HÀM QUAN TRỌNG ĐÃ SỬA ---
@admin_bp.route('/orders/<int:order_id>')
@login_required
@admin_required
def order_details(order_id):
     # Giữ nguyên logic lấy dữ liệu và tính toán thời gian như trước
    order = Order.query.get_or_404(order_id)
    order_details = order.details.all() # Lấy qua relationship
    payment_confirmation_time, processing_time_display, completed_time_display, cancelled_time_display = None, None, None, None

    if order.created_at:
        try:
            if order.payment_status == 'completed':
                 # Nên có timestamp thanh toán thực tế, đây là giả định
                 payment_confirmation_time = order.updated_at if order.payment_method != 'cash' else order.created_at + timedelta(minutes=5)
            if order.status in ['processing', 'completed', 'delivered', 'shipped']: # Thêm các trạng thái liên quan
                 processing_time_display = order.updated_at if order.updated_at > order.created_at else order.created_at + timedelta(minutes=10)
            if order.status == 'completed' or order.status == 'delivered': # Hoàn thành hoặc đã giao
                 completed_time_display = order.updated_at if order.updated_at > order.created_at else order.created_at + timedelta(minutes=30)
            if order.status == 'cancelled':
                 cancelled_time_display = order.updated_at
        except TypeError: flash('Lỗi định dạng thời gian.', 'warning')
        except Exception as e: flash(f'Lỗi tính toán thời gian: {e}', 'warning')

    return render_template('admin/order_details.html',
                           order=order, order_details=order_details,
                           payment_confirmation_time=payment_confirmation_time,
                           processing_time_display=processing_time_display,
                           completed_time_display=completed_time_display,
                           cancelled_time_display=cancelled_time_display)
# --- KẾT THÚC PHẦN SỬA QUAN TRỌNG ---

@admin_bp.route('/orders/update-status/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    logger = current_app.logger if current_app else logging.getLogger()
    updated_fields = [] # List để theo dõi các trường đã cập nhật

    # Lấy dữ liệu từ form, get trả về None nếu key không tồn tại
    new_order_status = request.form.get('status')
    new_payment_status = request.form.get('payment_status')

    # --- Cập nhật Trạng thái Đơn hàng ---
    if new_order_status is not None: # Chỉ xử lý nếu 'status' được gửi lên
        valid_order_statuses = ['pending', 'processing', 'ready_for_pickup', 'out_for_delivery', 'completed', 'delivered', 'cancelled', 'failed']
        if new_order_status in valid_order_statuses:
            if order.status != new_order_status:
                order.status = new_order_status
                updated_fields.append(f"Trạng thái ĐH thành '{order.get_status_display()}'") # Dùng hàm get_status_display
                logger.info(f"Updating Order {order_id} status to '{new_order_status}'")
                # Logic liên quan: nếu hủy thì TT cũng hủy, nếu xong thì TT cũng xong?
                if new_order_status == 'cancelled' and order.payment_status not in ['cancelled', 'refunded']:
                     order.payment_status = 'cancelled'
                     updated_fields.append("Trạng thái TT thành 'Đã hủy TT'")
                elif new_order_status == 'completed' and order.payment_status not in ['completed', 'paid']:
                      order.payment_status = 'completed' # Hoặc 'paid' tùy logic
                      updated_fields.append("Trạng thái TT thành 'Đã thanh toán'")
            else:
                 flash(f'Đơn hàng #{order.order_number} đã ở trạng thái "{order.get_status_display()}".', 'info')
        else:
            flash(f'Trạng thái đơn hàng "{new_order_status}" không hợp lệ.', 'danger')
            return redirect(request.referrer or url_for('admin.order_details', order_id=order_id))

    # --- Cập nhật Trạng thái Thanh toán ---
    if new_payment_status is not None: # Chỉ xử lý nếu 'payment_status' được gửi lên
        valid_payment_statuses = ['pending', 'completed', 'paid', 'failed', 'cancelled', 'refunded']
        if new_payment_status in valid_payment_statuses:
            if order.payment_status != new_payment_status:
                order.payment_status = new_payment_status
                updated_fields.append(f"Trạng thái TT thành '{new_payment_status.replace('_', ' ').title()}'")
                logger.info(f"Updating Order {order_id} payment status to '{new_payment_status}'")
                 # Logic liên quan: Nếu TT xong thì ĐH đang xử lý? (Tùy quy trình)
                # if new_payment_status == 'completed' and order.status == 'pending':
                #     order.status = 'processing'
                #     updated_fields.append("Trạng thái ĐH thành 'Đang xử lý'")
            else:
                flash(f'Đơn hàng #{order.order_number} đã ở trạng thái thanh toán "{order.payment_status}".', 'info')
        else:
            flash(f'Trạng thái thanh toán "{new_payment_status}" không hợp lệ.', 'danger')
            return redirect(request.referrer or url_for('admin.order_details', order_id=order_id))

    # --- Lưu thay đổi nếu có ---
    if updated_fields:
        order.updated_at = datetime.utcnow()
        try:
            db.session.commit()
            flash(f'Đã cập nhật cho đơn hàng #{order.order_number}: {", ".join(updated_fields)}.', 'success')
            logger.info(f"Successfully updated order {order_id}. Fields: {', '.join(updated_fields)}")
             # Gửi email thông báo cho khách hàng tại đây nếu cần
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB error updating order {order_id}: {e}", exc_info=True)
            flash(f'Lỗi khi cập nhật đơn hàng: {str(e)}', 'danger')
    # else: Không có gì để cập nhật (có thể không cần thông báo gì)
    #    flash('Không có thay đổi trạng thái nào được thực hiện.', 'info')


    return redirect(request.referrer or url_for('admin.order_details', order_id=order_id))


@admin_bp.route('/pos')
@login_required
@admin_required
def pos():
    categories = Category.query.order_by(Category.name).all()
    # Lấy tất cả sản phẩm có sẵn để JS xử lý filter tồn kho nếu cần hiệu năng tốt hơn
    products = Product.query.filter_by(is_available=True)\
                            .order_by(Product.category_id, Product.name).all()
    # Nếu quá nhiều SP, có thể giới hạn ban đầu hoặc chỉ load category đầu tiên
    return render_template('admin/pos.html', categories=categories, products=products) # Truyền products vào

@admin_bp.route('/api/products')
@login_required
@admin_required
def api_products():
     # Logic giữ nguyên
     # Lưu ý: Nếu products truyền vào pos.html đã đủ, API này có thể không cần thiết nữa
    # Trừ khi bạn muốn lọc động bằng AJAX trên POS page
    category_id = request.args.get('category_id', type=int)
    query_term = request.args.get('q', '')

    products_query = Product.query.filter(Product.is_available==True)\
                                  .join(InventoryItem, isouter=True) # OUTER JOIN để lấy cả SP chưa có inventory
                                  #.filter(InventoryItem.quantity > 0) # Tạm bỏ filter này, để JS xử lý

    if category_id:
        products_query = products_query.filter(Product.category_id == category_id)
    if query_term:
        products_query = products_query.filter(Product.name.ilike(f'%{query_term}%'))

    products = products_query.order_by(Product.name).all()
    result = [{
            'id': p.id, 'name': p.name, 'price': float(p.price), 'category_id': p.category_id,
            'image_url': p.image_url or url_for('static', filename='images/default-product.png'),
            'stock': p.inventory.quantity if p.inventory else 0 # Kiểm tra nếu inventory tồn tại
        } for p in products]
    return jsonify(result)

@admin_bp.route('/api/create-order', methods=['POST'])
@login_required
@admin_required
def api_create_order():
     logger = current_app.logger
     data = request.json
     if not data or 'items' not in data or not data['items']:
        logger.warning("POS create order: Invalid data received.")
        return jsonify({'success': False, 'error': 'Dữ liệu đơn hàng không hợp lệ.'}), 400

     items_data = data.get('items', [])
     # ĐÂY LÀ TỔNG TIỀN HÀNG GỐC
     total_base_amount_calculated = 0 # Đổi tên biến
     product_inventory_updates = {}

     try:
        with db.session.begin_nested():
            # --- Kiểm tra tồn kho và tính tổng tiền hàng gốc ---
            for item in items_data:
                # ... (logic kiểm tra product_id, quantity như cũ) ...
                product_id = item.get('product_id')
                quantity = item.get('quantity')
                if not product_id or not isinstance(quantity, int) or quantity <= 0:
                     raise ValueError(f"Sản phẩm ID {product_id} có số lượng không hợp lệ: {quantity}")

                # Nên lấy luôn cả giá ở đây để tính toán
                product = db.session.query(Product.id, Product.name, Product.price, Product.is_available)\
                                    .filter(Product.id == product_id).first()

                if not product or not product.is_available:
                     raise ValueError(f"Sản phẩm '{item.get('name', product_id)}' không tồn tại hoặc đã hết hàng.")

                inventory = db.session.query(InventoryItem).filter_by(product_id=product_id).with_for_update().first()
                current_stock = inventory.quantity if inventory else 0
                planned_usage = product_inventory_updates.get(product_id, 0)
                if current_stock < quantity + planned_usage:
                      raise ValueError(f"Không đủ '{product.name}'. Chỉ còn {current_stock - planned_usage} (cần {quantity}).")

                total_base_amount_calculated += product.price * quantity
                product_inventory_updates[product_id] = planned_usage + quantity
            # -----------------------------------------------

            # --- *** TÍNH TOÁN final_amount CHO POS *** ---
            # Đơn POS thường không có ship, chỉ có thuế (và có thể discount)
            tax_rate_pos = 0.10 # Ví dụ VAT 10%
            discount_amount_pos = 0 # Lấy từ data nếu POS có hỗ trợ nhập mã giảm giá

            tax_amount_pos = total_base_amount_calculated * tax_rate_pos
            final_amount_calculated = total_base_amount_calculated + tax_amount_pos - discount_amount_pos
            # --------------------------------------------

            # --- Tạo Order object VỚI final_amount ---
            new_order = Order(
                # User ID nên là ID của nhân viên đang thao tác POS, hoặc 1 user mặc định cho POS?
                # user_id=current_user.id, # <= LÀ USER ĐANG LOGIN ADMIN
                user_id= data.get('customer_id') or current_user.id, # Có thể truyền customer_id từ POS hoặc mặc định là NV
                order_number=f"POS-{uuid.uuid4().hex[:8].upper()}",
                status='completed', # POS thường là completed
                total_amount=total_base_amount_calculated, # Tiền hàng gốc
                final_amount=final_amount_calculated, # << GÁN GIÁ TRỊ ĐÃ TÍNH
                order_type=data.get('order_type', 'dine-in'),
                payment_method=data.get('payment_method', 'cash'),
                payment_status='completed', # POS thường là đã TT
                notes=data.get('notes', ''),
                address=None, # Đơn POS tại quán thường không cần địa chỉ
                contact_phone=data.get('contact_phone', '') # SĐT khách (nếu có nhập)
                # created_at, updated_at sẽ tự động
            )
            # ------------------------------------------
            db.session.add(new_order)
            db.session.flush() # Lấy new_order.id

            # --- Tạo OrderDetail và Cập nhật Inventory ---
            for item in items_data:
                # ... (logic tạo OrderDetail như cũ) ...
                 product_info = db.session.query(Product.price).filter(Product.id == item['product_id']).scalar() # Lấy giá tại thời điểm tạo
                 order_detail = OrderDetail(
                     order_id=new_order.id,
                     product_id=item['product_id'],
                     quantity=item['quantity'],
                     unit_price=product_info if product_info is not None else 0, # Lưu giá đơn vị
                     subtotal=(product_info if product_info is not None else 0) * item['quantity'],
                     notes=item.get('notes', '')
                 )
                 db.session.add(order_detail)

                # ... (logic cập nhật inventory như cũ) ...
                 inventory = db.session.query(InventoryItem).filter_by(product_id=item['product_id']).with_for_update().one_or_none() # Dùng one_or_none
                 if inventory:
                     if inventory.quantity >= item['quantity']:
                         inventory.quantity -= item['quantity']
                         inventory.last_updated = datetime.utcnow()
                     else:
                          # Lỗi này không nên xảy ra nếu check ở trên đúng
                          raise ValueError(f"Lỗi tồn kho không nhất quán cho SP ID {item['product_id']} khi commit POS.")
                 else:
                     logger.warning(f"Không tìm thấy inventory item cho product {item['product_id']} khi trừ kho POS.")

        db.session.commit() # Commit transaction
        logger.info(f"POS Order {new_order.order_number} created successfully by staff {current_user.id}.")
        return jsonify({
            'success': True,
            'order_id': new_order.id,
            'order_number': new_order.order_number,
            'message': f'Đã tạo đơn hàng POS {new_order.order_number}.'
        })

     except ValueError as ve:
        db.session.rollback()
        logger.warning(f"POS order validation failed: {ve}")
        return jsonify({'success': False, 'error': str(ve)}), 400
     except Exception as e:
        db.session.rollback()
        logger.error(f"Lỗi khi tạo đơn POS: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Lỗi máy chủ nội bộ khi xử lý đơn hàng.'}), 500


@admin_bp.route('/inventory')
@login_required
@admin_required
def inventory():
     # Logic lấy inventory và tính toán low/out stock giữ nguyên
    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '')
    status_filter = request.args.get('status_filter', 'all') # Thêm status_filter

    query = InventoryItem.query.join(Product) # Join để search và sort

    if search_term:
        query = query.filter(Product.name.ilike(f'%{search_term}%'))

    # Áp dụng filter trạng thái
    if status_filter == 'low':
        query = query.filter(InventoryItem.quantity <= InventoryItem.min_quantity, InventoryItem.quantity > 0)
    elif status_filter == 'out':
        query = query.filter(InventoryItem.quantity <= 0)
    elif status_filter == 'adequate':
        query = query.filter(InventoryItem.quantity > InventoryItem.min_quantity)
    # Mặc định 'all' không cần filter

    pagination = query.order_by(Product.name).paginate(page=page, per_page=20, error_out=False) # Tăng per_page
    items = pagination.items
    total_items = pagination.total # Tổng item khớp với filter hiện tại

    # Đếm tổng quát không theo filter trang hiện tại (để hiển thị trên thẻ thống kê)
    base_query = db.session.query(InventoryItem.id) # Query ID cho nhẹ
    total_all_items_count = base_query.count()
    low_stock_count = base_query.filter(InventoryItem.quantity <= InventoryItem.min_quantity, InventoryItem.quantity > 0).count()
    out_of_stock_count = base_query.filter(InventoryItem.quantity <= 0).count()
    adequate_stock_count = total_all_items_count - low_stock_count - out_of_stock_count


    return render_template('admin/inventory.html',
                           inventory_items=items,
                           pagination=pagination,
                           total_items=total_items, # Số item trên trang/khớp filter
                           total_all_items_count=total_all_items_count, # Tổng số item trong kho
                           low_stock_count=low_stock_count,
                           out_of_stock_count=out_of_stock_count,
                           adequate_stock_count=adequate_stock_count,
                           search_term=search_term,
                           status_filter=status_filter) # Truyền filter vào template


# === THÊM ROUTE XUẤT INVENTORY ===
@admin_bp.route('/inventory/export')
@login_required
@admin_required
def export_inventory():
    logger = current_app.logger if current_app else logging.getLogger() # Get logger
    # Lấy tham số
    file_format = request.args.get('format', 'csv').lower()
    status_filter = request.args.get('status', 'all')
    search_term = request.args.get('search', '')
    logger.info(f"Exporting inventory. Format: {file_format}, Status: {status_filter}, Search: '{search_term}'")

    # --- Query dữ liệu với Eager Loading ---
    query = db.session.query(InventoryItem).options(
        # Eager load Product và Category để tránh N+1 queries trong loop
        joinedload(InventoryItem.product_inventory).joinedload(Product.category)
    )

    # -- Tham gia bảng Product để tìm kiếm và sắp xếp --
    query = query.join(InventoryItem.product_inventory) # Join sử dụng tên relationship

    # --- Áp dụng bộ lọc trạng thái ---
    if status_filter == 'low':
        query = query.filter(InventoryItem.quantity > 0, InventoryItem.quantity <= InventoryItem.min_quantity) # <= min_quantity mới đúng
        filename_status = "low_stock"
    elif status_filter == 'out':
        query = query.filter(InventoryItem.quantity <= 0)
        filename_status = "out_of_stock"
    else: # 'all' hoặc không xác định
        filename_status = "all"

    # --- Áp dụng tìm kiếm ---
    if search_term:
        query = query.filter(Product.name.ilike(f'%{search_term}%'))
        filename_search = f"search_{search_term.replace(' ','_').lower()}_"
    else:
        filename_search = ""

    filename = f"dragon_coffee_inventory_{filename_search}{filename_status}.{file_format}"

    # Sắp xếp theo tên sản phẩm
    items_to_export = query.order_by(Product.name).all()
    # -----------------------------------------

    if not items_to_export:
        flash(f"Không có dữ liệu tồn kho{' với bộ lọc hiện tại' if status_filter != 'all' or search_term else ''} để xuất.", "warning")
        return redirect(url_for('admin.inventory', status_filter=status_filter, search=search_term))

    if file_format == 'csv':
        try:
            si = io.StringIO()
            cw = csv.writer(si)
            # ... (Viết header và các dòng dữ liệu như cũ) ...
            header = ['Product ID', 'Product Name', 'Category', 'Current Quantity', 'Min Quantity', 'Unit', 'Last Restocked', 'Last Updated']
            cw.writerow(header)
            for item in items_to_export:
                last_restocked_str = item.last_restocked.strftime('%Y-%m-%d %H:%M:%S') if item.last_restocked else ''
                last_updated_str = item.last_updated.strftime('%Y-%m-%d %H:%M:%S') if item.last_updated else ''
                product_name = item.product_inventory.name if item.product_inventory else 'N/A'
                category_name = item.product_inventory.category.name if item.product_inventory and item.product_inventory.category else 'N/A'
                row = [ # Dữ liệu vẫn giữ nguyên kiểu Python
                    item.product_id, product_name, category_name,
                    item.quantity, item.min_quantity, item.unit or '',
                    last_restocked_str, last_updated_str
                ]
                cw.writerow(row)

            # ----- **SỬA PHẦN TẠO OUTPUT VÀ RESPONSE** -----
            output_string = si.getvalue()
            # Encode chuỗi thành bytes UTF-8 with BOM (Byte Order Mark)
            # BOM giúp Excel nhận diện đúng UTF-8 khi mở trực tiếp
            output_bytes = output_string.encode('utf-8-sig')

            return Response(
                output_bytes, # Trả về bytes đã encode
                mimetype="text/csv; charset=utf-8-sig", # Chỉ định charset trong mimetype
                headers={"Content-Disposition": f"attachment;filename=\"{filename}\""} # Đặt tên file trong dấu ngoặc kép
            )
            # ----------------------------------------------
        except Exception as e:
             logger.error(f"Error generating CSV export: {e}", exc_info=True)
             flash(f"Lỗi khi tạo file CSV: {e}", "danger")
             return redirect(url_for('admin.inventory'))

    # elif file_format == 'xlsx': ... (Logic cho Excel nếu cần) ...
    else:
        flash(f"Định dạng file '{file_format}' không được hỗ trợ.", "danger")
        return redirect(url_for('admin.inventory'))

# === KẾT THÚC ROUTE XUẤT INVENTORY ===


@admin_bp.route('/inventory/add-item', methods=['POST'])
@login_required
@admin_required
def add_inventory_item():
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', 0, type=int)
    min_quantity = request.form.get('min_quantity', 10, type=int)

    if not product_id:
        flash('Vui lòng chọn sản phẩm.', 'danger')
        return redirect(url_for('admin.inventory'))

    # Kiểm tra xem inventory item đã tồn tại chưa
    existing_item = InventoryItem.query.filter_by(product_id=product_id).first()
    if existing_item:
        flash('Sản phẩm này đã có trong kho. Vui lòng cập nhật số lượng.', 'warning')
        return redirect(url_for('admin.inventory'))

    product = Product.query.get(product_id)
    if not product:
        flash('Sản phẩm không tồn tại.', 'danger')
        return redirect(url_for('admin.inventory'))

    try:
        inventory = InventoryItem(
            product_id=product_id,
            quantity=quantity,
            min_quantity=min_quantity,
            last_restocked=datetime.utcnow() if quantity > 0 else None
        )
        db.session.add(inventory)
        db.session.commit()
        flash(f'Đã thêm "{product.name}" vào kho.', 'success')
    except Exception as e: ### FIXED: Thêm try-except commit + rollback + logging
        db.session.rollback()
        flash(f'Lỗi khi thêm sản phẩm vào kho: {str(e)}', 'danger')
        current_app.logger.error(f"Lỗi thêm item vào inventory cho product ID {product_id}: {e}", exc_info=True)

    return redirect(url_for('admin.inventory'))


@admin_bp.route('/inventory/update/<int:inventory_id>', methods=['POST'])
@login_required
@admin_required
def update_inventory(inventory_id):
    inventory = InventoryItem.query.get_or_404(inventory_id)
    new_quantity = request.form.get('quantity', type=int)
    new_min_quantity = request.form.get('min_quantity', type=int) # Lấy cả min_quantity

    updated = False
    try:
        if new_quantity is not None and new_quantity >= 0 and inventory.quantity != new_quantity:
            # Chỉ cập nhật last_restocked nếu số lượng tăng lên hoặc từ 0 thành > 0
            if new_quantity > inventory.quantity :
                 inventory.last_restocked = datetime.utcnow()
            inventory.quantity = new_quantity
            updated = True

        if new_min_quantity is not None and new_min_quantity >= 0 and inventory.min_quantity != new_min_quantity:
            inventory.min_quantity = new_min_quantity
            updated = True

        if updated:
            try: ### FIXED: Thêm try-except commit
                db.session.commit()
                flash('Cập nhật kho thành công!', 'success')
            except Exception as e: ### FIXED: Rollback và logging trong nested try-except
                db.session.rollback()
                flash(f'Lỗi khi cập nhật kho: {str(e)}', 'danger')
                current_app.logger.error(f"Lỗi cập nhật inventory item ID {inventory_id}: {e}", exc_info=True)
                return redirect(url_for('admin.inventory', page=request.args.get('page', 1))) # Giữ lại trang hiện tại
        else:
            flash('Không có thay đổi nào được thực hiện.', 'info')

    except Exception as e: ### FIXED: Catch ngoại lệ ở outer try
        db.session.rollback()
        flash(f'Lỗi khi cập nhật kho: {str(e)}', 'danger')
        current_app.logger.error(f"Lỗi chung khi update inventory: {e}", exc_info=True)


    return redirect(url_for('admin.inventory', page=request.args.get('page', 1))) # Giữ lại trang hiện tại

# === THÊM ROUTE ĐỂ TẢI FILE MẪU BATCH UPDATE ===
@admin_bp.route('/inventory/batch-template') # Bạn có thể chọn URL path khác nếu muốn
@login_required
@admin_required # Hoặc quyền hạn phù hợp khác
def download_inventory_template():
    """Cung cấp file CSV mẫu để người dùng tải về cho việc cập nhật hàng loạt."""
    # Tạo nội dung CSV trong bộ nhớ
    si = io.StringIO()
    cw = csv.writer(si)

    # Xác định các cột header CẦN THIẾT cho logic xử lý batch update của bạn
    # Quan trọng: Các header này phải khớp với cách bạn đọc file trong route batch_update_inventory
    # Ví dụ 1: Nếu bạn xử lý dựa trên product_id
    # header = ['product_id', 'quantity']

    # Ví dụ 2: Nếu bạn xử lý dựa trên tên sản phẩm (cần tìm kiếm ID sau)
    header = ['product_name', 'quantity'] # Hoặc có thể là ['product_sku', 'quantity'] nếu bạn dùng SKU

    # --- Chọn ĐÚNG header mà route batch_update_inventory của bạn mong đợi ---
    cw.writerow(header)

    # (Tùy chọn) Thêm một vài dòng ví dụ hoặc để trống
    # cw.writerow(['Ví dụ Tên Sản Phẩm A', 50])
    # cw.writerow(['Ví dụ Tên Sản Phẩm B', 100])

    output = si.getvalue()

    # Tạo Response để trình duyệt tải về
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=inventory_batch_template.csv"} # Tên file tải về
    )
# === KẾT THÚC ROUTE TẢI FILE MẪU ===

# === ROUTE XỬ LÝ BATCH UPDATE (Bạn cần có route này) ===
@admin_bp.route('/inventory/batch-update', methods=['POST'])
@login_required
@admin_required
def batch_update_inventory():
    # --- Logic xử lý file CSV tải lên ở đây ---
    # 1. Kiểm tra xem file có được tải lên không ('batch_file' trong form)
    # 2. Đọc file CSV (dùng csv.reader, pandas, ...)
    # 3. Lặp qua từng dòng trong CSV:
    #    a. Lấy product_id/product_name/sku và quantity
    #    b. Nếu dùng product_name/sku, tìm Product tương ứng để lấy product_id
    #    c. Tìm InventoryItem dựa trên product_id
    #    d. Cập nhật quantity cho InventoryItem đó
    #    e. Lưu thay đổi vào DB (có thể commit một lần sau vòng lặp hoặc theo lô nhỏ)
    # 4. Flash message thông báo thành công/thất bại
    # 5. Redirect về trang inventory

    uploaded_file = request.files.get('batch_file')
    if not uploaded_file or uploaded_file.filename == '':
        flash('Vui lòng chọn file CSV để cập nhật.', 'warning')
        return redirect(url_for('admin.inventory'))

    if not uploaded_file.filename.lower().endswith('.csv'):
        flash('Chỉ chấp nhận file định dạng CSV.', 'danger')
        return redirect(url_for('admin.inventory'))

    updated_count = 0
    error_count = 0
    errors_list = []

    try: ### FIXED: Bọc TOÀN BỘ logic batch update trong try-except
        # Đọc file CSV từ stream
        stream = io.StringIO(uploaded_file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.reader(stream)
        header = next(csv_reader) # Đọc dòng header

        # --- Đảm bảo header này khớp với file template và logic xử lý ---
        # Ví dụ nếu dùng product_name:
        try:
             name_idx = header.index('product_name')
             qty_idx = header.index('quantity')
        except ValueError:
             flash("File CSV không đúng định dạng. Thiếu cột 'product_name' hoặc 'quantity'.", "danger")
             return redirect(url_for('admin.inventory'))


        # Ví dụ nếu dùng product_id:
        # try:
        #    id_idx = header.index('product_id')
        #    qty_idx = header.index('quantity')
        # except ValueError:
        #     flash("File CSV không đúng định dạng. Thiếu cột 'product_id' hoặc 'quantity'.", "danger")
        #     return redirect(url_for('admin.inventory'))


        items_to_update = []
        for i, row in enumerate(csv_reader):
            if not row: # Bỏ qua dòng trống
                 continue
            try:
                # --- Xử lý dựa trên header đã chọn ---

                # Ví dụ nếu dùng product_name:
                product_name = row[name_idx].strip()
                quantity_str = row[qty_idx].strip()

                if not product_name or not quantity_str:
                    errors_list.append(f"Dòng {i+2}: Dữ liệu không hợp lệ (tên hoặc số lượng trống).")
                    error_count += 1
                    continue

                product = Product.query.filter(func.lower(Product.name) == func.lower(product_name)).first()
                if not product:
                     errors_list.append(f"Dòng {i+2}: Không tìm thấy sản phẩm '{product_name}'.")
                     error_count += 1
                     continue
                product_id = product.id

                # Ví dụ nếu dùng product_id:
                # product_id_str = row[id_idx].strip()
                # quantity_str = row[qty_idx].strip()
                # if not product_id_str or not quantity_str:
                #     errors_list.append(f"Dòng {i+2}: Dữ liệu không hợp lệ (ID hoặc số lượng trống).")
                #     error_count += 1
                #     continue
                # product_id = int(product_id_str) # Cần try-except nếu ID không phải số

                # --- Phần chung ---
                try:
                    quantity = int(quantity_str)
                    if quantity < 0:
                         raise ValueError("Số lượng không được âm.")
                except ValueError:
                     errors_list.append(f"Dòng {i+2}: Số lượng '{quantity_str}' không hợp lệ cho sản phẩm ID {product_id}.")
                     error_count += 1
                     continue

                items_to_update.append({'product_id': product_id, 'quantity': quantity, 'line': i+2})

            except IndexError:
                errors_list.append(f"Dòng {i+2}: Thiếu cột dữ liệu.")
                error_count += 1
            except Exception as e:
                errors_list.append(f"Dòng {i+2}: Lỗi không xác định - {e}.")
                error_count += 1


        # Thực hiện cập nhật vào DB
        for item_data in items_to_update:
            inventory_item = InventoryItem.query.filter_by(product_id=item_data['product_id']).first()
            if inventory_item:
                inventory_item.quantity = item_data['quantity']
                # Có thể cập nhật last_restocked ở đây nếu muốn
                # inventory_item.last_restocked = datetime.utcnow()
                db.session.add(inventory_item)
                updated_count += 1
            else:
                # Có thể bạn muốn tạo mới inventory item nếu chưa tồn tại?
                 errors_list.append(f"Dòng {item_data['line']}: Không tìm thấy bản ghi tồn kho cho Product ID {item_data['product_id']} (Sản phẩm này có thể chưa được thêm vào kho?).")
                 error_count += 1

        if updated_count > 0 or error_count > 0:
            try: ### FIXED: Thêm try-except commit
                 db.session.commit()
            except Exception as commit_e: ### FIXED: Bắt lỗi commit trong batch update, logging cụ thể
                db.session.rollback()
                current_app.logger.error(f"Lỗi commit batch update: {commit_e}", exc_info=True)
                flash(f"Lỗi commit database khi cập nhật hàng loạt: {commit_e}", "danger")
                return redirect(url_for('admin.inventory')) # RETURN NGAY nếu commit lỗi

        if error_count > 0:
             flash(f"Cập nhật hoàn tất với {updated_count} thành công và {error_count} lỗi.", 'warning')
             # Có thể hiển thị chi tiết lỗi nếu cần
             for err in errors_list[:10]: # Hiển thị tối đa 10 lỗi
                 flash(err, 'danger')
        elif updated_count > 0:
             flash(f"Đã cập nhật thành công tồn kho cho {updated_count} sản phẩm.", 'success')
        else:
             flash("Không có sản phẩm nào được cập nhật từ file.", "info")


    except Exception as e: ### FIXED: Catch all ngoại lệ outer try, rollback và logging tổng quát
         db.session.rollback() # Rollback nếu có lỗi nghiêm trọng trong quá trình xử lý file
         current_app.logger.error(f"Lỗi khi cập nhật hàng loạt tồn kho: {e}", exc_info=True)
         flash(f"Đã xảy ra lỗi trong quá trình xử lý file: {e}", "danger")


    return redirect(url_for('admin.inventory'))

# API lấy inventory history (CẦN BẢNG LOG)
@admin_bp.route('/inventory/<int:inventory_id>/history')
@login_required
@admin_required
def inventory_history(inventory_id):
    logger = current_app.logger
    logger.info(f"Fetching inventory history for item ID: {inventory_id}")
    limit = 50 # Giới hạn số lượng giao dịch gần nhất

    try:
        inventory_item = db.session.query(InventoryItem).options(
            joinedload(InventoryItem.product_inventory) # Load sẵn tên sản phẩm
        ).get(inventory_id)

        if not inventory_item:
            return "<div class='alert alert-warning'>Không tìm thấy mục tồn kho.</div>"

        product_name = inventory_item.product_inventory.name if inventory_item.product_inventory else f"ID {inventory_item.product_id}"

        # --- Query Lịch Sử Bán Hàng ---
        # Lấy các chi tiết đơn hàng đã hoàn thành cho sản phẩm này
        sales_history = db.session.query(
                Order.order_number,
                Order.created_at,
                OrderDetail.quantity,
                OrderDetail.unit_price # Có thể thêm thông tin khác nếu cần
            ).join(OrderDetail, Order.id == OrderDetail.order_id)\
             .filter(
                 OrderDetail.product_id == inventory_item.product_id,
                 Order.status.in_(['completed', 'delivered']) # Chỉ tính đơn hoàn thành/đã giao
             )\
             .order_by(desc(Order.created_at))\
             .limit(limit)\
             .all()

        # --- TODO (Optional): Query Lịch Sử Nhập Kho ---
        # Nếu bạn có bảng riêng để log việc nhập kho (ví dụ: StockReceipt)
        # receipt_history = db.session.query(StockReceipt) \
        #                           .filter(StockReceipt.product_id == inventory_item.product_id) \
        #                           .order_by(desc(StockReceipt.received_at)) \
        #                           .limit(limit).all()
        receipt_history = [] # Placeholder nếu chưa có

        # Render một template partial (HTML nhỏ chỉ chứa phần nội dung của modal)
        # Tạo file /templates/admin/_inventory_history_content.html
        return render_template('admin/_inventory_history_content.html',
                               item=inventory_item,
                               product_name=product_name,
                               sales_history=sales_history,
                               receipt_history=receipt_history, # Truyền lịch sử nhập kho nếu có
                               limit=limit)

    except Exception as e:
        logger.error(f"Error fetching inventory history for item {inventory_id}: {e}", exc_info=True)
        return "<div class='alert alert-danger'>Lỗi khi tải dữ liệu lịch sử.</div>"
     # ----------------------------------


# API lấy item inventory (có thể không cần thiết nếu đã có batch update)
@admin_bp.route('/api/inventory-items')
@login_required
@admin_required
def api_inventory_items():
    skip = request.args.get('skip', 0, type=int)
    limit = request.args.get('limit', 10, type=int) # Tăng giới hạn mặc định
    search_term = request.args.get('q', '')

    query = InventoryItem.query.join(Product)

    if search_term:
         query = query.filter(Product.name.ilike(f'%{search_term}%'))


    total_items = query.count()
    inventory_items = query.order_by(Product.name).offset(skip).limit(limit).all()


    items = []
    for item in inventory_items:
        items.append({
            'id': item.id,
            'product_id': item.product_id,
            'product_name': item.product.name,
            'quantity': item.quantity,
            'min_quantity': item.min_quantity,
            'unit': item.unit or 'Cái', # Đơn vị mặc định
            'image_url': item.product.image_url or url_for('static', filename='images/default-coffee.jpg')
        })

    return jsonify({
        'items': items,
        'total_items': total_items,
        'has_more': (skip + len(items)) < total_items,
        'skip': skip,
        'limit': limit
    })

@admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    logger = current_app.logger if current_app else logging.getLogger(__name__)

    # ----- **LẤY report_type và period Ở ĐÂY (TRƯỚC KHI DÙNG)** -----
    report_type = request.args.get('type', 'sales')
    period = request.args.get('period', 'week')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    # -------------------------------------------------------------

    # --- Xác định Ngày bắt đầu và kết thúc (logic giữ nguyên) ---
    end_date = datetime.utcnow().date()
    if end_date_str:
        try: end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError: flash("Ngày kết thúc không hợp lệ.", "warning")
    start_date = None
    if start_date_str:
        try: start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError: flash("Ngày bắt đầu không hợp lệ.", "warning")
    if not start_date:
        if period == 'day': start_date = end_date
        elif period == 'week': start_date = end_date - timedelta(days=6)
        elif period == 'month': start_date = end_date.replace(day=1)
        elif period == 'year': start_date = end_date.replace(month=1, day=1)
        else: period = 'week'; start_date = end_date - timedelta(days=6)
    if start_date and end_date and start_date > end_date: start_date, end_date = end_date, start_date
    # ----------------------------------------------------------

    start_datetime = datetime.combine(start_date, time.min)
    end_datetime = datetime.combine(end_date, time.max)

    logger.info(f"Generating report: type={report_type}, period={period}, start={start_date}, end={end_date}")

    # --- Logic cho từng loại báo cáo (BÂY GIỜ report_type ĐÃ CÓ GIÁ TRỊ) ---
    if report_type == 'sales':
        try:
            # ... (logic query và tính toán cho sales report như đã sửa ở bước trước) ...
            # Query:
            orders_query = Order.query.filter(
                Order.created_at >= start_datetime,
                Order.created_at <= end_datetime,
                func.lower(Order.status).in_(['completed', 'delivered'])
            ).options(db.selectinload(Order.customer)).order_by(Order.created_at.asc())
            orders_in_period = orders_query.all()
            logger.info(f"Found {len(orders_in_period)} completed/delivered orders for sales report.")

            # Calculate chart data and totals:
            daily_sales = defaultdict(float)
            current_scan_date = start_date
            while current_scan_date <= end_date: daily_sales[current_scan_date.strftime('%Y-%m-%d')]=0.0; current_scan_date += timedelta(days=1)
            total_sales_in_period = 0.0
            for order in orders_in_period:
                order_date_str = order.created_at.date().strftime('%Y-%m-%d')
                amount_to_sum = order.final_amount if order.final_amount is not None else order.total_amount
                if isinstance(amount_to_sum, (int, float)):
                     daily_sales[order_date_str] += amount_to_sum; total_sales_in_period += amount_to_sum
            logger.debug(f"Calculated daily_sales: {dict(daily_sales)}") # Log giá trị daily_sales
            sorted_daily_sales = dict(sorted(daily_sales.items()))
            chart_labels = [datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m') for d in sorted_daily_sales.keys()]
            chart_values = list(sorted_daily_sales.values())
            sales_chart_data = {'labels': chart_labels, 'values': chart_values}
            logger.debug(f"Final chart_data for template: {sales_chart_data}")
            total_orders_count_in_period = len(orders_in_period)

            # Render template
            return render_template('admin/reports/sales_report.html',
                                   report_type=report_type, period=period,
                                   start_date=start_date.strftime('%Y-%m-%d'),
                                   end_date=end_date.strftime('%Y-%m-%d'),
                                   orders=orders_in_period,
                                   chart_data=sales_chart_data,
                                   total_sales=total_sales_in_period,
                                   total_orders=total_orders_count_in_period)
        except Exception as e:
            logger.error(f"Error generating sales report: {e}", exc_info=True)
            flash("Lỗi khi tạo báo cáo doanh thu.", "danger")
            return redirect(url_for('admin.dashboard'))

    elif report_type == 'products':
         # ... (logic cho products report) ...
         return "Product Report Placeholder" # Placeholder

    elif report_type == 'inventory':
        # ... (logic cho inventory report) ...
         return "Inventory Report Placeholder" # Placeholder

    else:
        flash(f"Loại báo cáo '{report_type}' không hợp lệ.", "warning")
        return redirect(url_for('admin.reports', type='sales')) # Mặc định về sales report



# Các route quản lý Employee (nhân viên)
@admin_bp.route('/employees')
@login_required
@admin_required
def employees():
    # --- SỬA DÒNG QUERY Ở ĐÂY ---
    employees = Employee.query.join(User).order_by(
        Employee.is_active.desc(), # Sắp xếp theo Employee.is_active giảm dần (True trước)
        User.last_name.asc(),      # Sau đó theo họ tăng dần
        User.first_name.asc()      # Cuối cùng theo tên tăng dần
    ).all()
    # ---------------------------
    return render_template('admin/employees.html', employees=employees)

@admin_bp.route('/employees/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_employee():
    form = EmployeeForm()
    # Loại bỏ các trường user khỏi form này vì user được tạo/tìm tự động
    del form.first_name
    del form.last_name
    del form.email
    del form.phone
    del form.is_staff # is_staff sẽ được set tự động


    if form.validate_on_submit():
        user_email = request.form.get('email') # Lấy email từ input riêng (cần thêm vào template)
        user_first_name = request.form.get('first_name')
        user_last_name = request.form.get('last_name')
        user_phone = request.form.get('phone')

        if not user_email or not user_first_name or not user_last_name:
             flash('Vui lòng nhập đủ thông tin Email, Họ, Tên.', 'danger')
             # Cần render lại template với dữ liệu đã nhập và lỗi
             return render_template('admin/employee_form.html', form=form, title='Thêm nhân viên', legend='Thêm nhân viên mới')


        # Kiểm tra email đã tồn tại chưa
        user = User.query.filter_by(email=user_email).first()
        if user:
             # Nếu user đã tồn tại nhưng chưa phải staff, có thể nâng quyền? (Tùy nghiệp vụ)
             if not user.is_staff:
                 user.is_staff = True
                 # Cập nhật thông tin user nếu cần
                 user.first_name = user_first_name
                 user.last_name = user_last_name
                 user.phone = user_phone
                 flash(f'Tài khoản {user.email} đã tồn tại và được cấp quyền nhân viên.', 'info')
             else:
                  # Nếu đã là staff, kiểm tra xem đã có record Employee chưa
                  existing_employee = Employee.query.filter_by(user_id=user.id).first()
                  if existing_employee:
                       flash(f'Nhân viên với email {user.email} đã tồn tại.', 'warning')
                       return redirect(url_for('admin.employees'))
        else:
            # Nếu user chưa tồn tại, tạo mới
            default_password = 'dragonstaff123' # Mật khẩu mặc định yếu, nên yêu cầu đổi hoặc gửi mail
            user = User(
                username=user_email.split('@')[0] + str(uuid.uuid4())[:4], # Tạo username duy nhất
                email=user_email,
                first_name=user_first_name,
                last_name=user_last_name,
                phone=user_phone,
                is_staff=True,
                is_admin=False # Mặc định không phải admin
            )
            user.set_password(default_password)
            db.session.add(user)
            db.session.flush() # Lấy user_id
            flash(f'Đã tạo tài khoản nhân viên mới cho {user.email} với mật khẩu mặc định.', 'success')


        # Tạo bản ghi Employee
        try:
            employee = Employee(
                user_id=user.id,
                position=form.position.data,
                hire_date=form.hire_date.data or datetime.utcnow().date(), # Ngày thuê mặc định
                salary=form.salary.data,
                is_active=True # Mặc định là active
            )
            db.session.add(employee)
            db.session.commit()
            flash('Thêm thông tin nhân viên thành công!', 'success')
            return redirect(url_for('admin.employees'))

        except Exception as e: ### FIXED: Thêm try-except commit + rollback + logging cho khối employee
             db.session.rollback()
             # Nếu tạo user thành công nhưng employee lỗi, cần xử lý rollback user hoặc thông báo rõ ràng
             if 'user' in locals() and not User.query.get(user.id).employee: # Nếu user vừa được tạo mới
                  # Có thể cân nhắc xóa user vừa tạo
                  # db.session.delete(user)
                  # db.session.commit()
                  flash(f'Lỗi khi thêm thông tin nhân viên cho {user.email}: {str(e)}. Tài khoản đã tạo.', 'danger')
             else:
                  flash(f'Lỗi khi thêm thông tin nhân viên: {str(e)}', 'danger')
             current_app.logger.error(f"Lỗi thêm Employee cho user {user_email}: {e}", exc_info=True) # Log lỗi chi tiết
             return render_template('admin/employee_form.html', form=form, title='Thêm nhân viên', legend='Thêm nhân viên mới',
                                    # Truyền lại giá trị user đã nhập vào template
                                    user_email=user_email, user_first_name=user_first_name,
                                    user_last_name=user_last_name, user_phone=user_phone)

    # Cần render template với cả form và các input cho user info
    return render_template('admin/employee_form.html', form=form, title='Thêm nhân viên', legend='Thêm nhân viên mới')

@admin_bp.route('/employees/edit/<int:employee_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    user = User.query.get_or_404(employee.user_id)

    # EmployeeForm bây giờ chỉ chứa thông tin của Employee model
    form = EmployeeForm(obj=employee)

    # Lấy thông tin user để hiển thị và cập nhật riêng
    user_data = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'phone': user.phone,
        'is_staff': user.is_staff, # Để hiển thị/cập nhật quyền staff
        'is_admin': user.is_admin # Để hiển thị/cập nhật quyền admin
    }

    if form.validate_on_submit():
        # Lấy dữ liệu user từ request.form (cần input tương ứng trong template)
        user.first_name = request.form.get('first_name', user.first_name)
        user.last_name = request.form.get('last_name', user.last_name)
        user.email = request.form.get('email', user.email) # Cẩn thận khi cho sửa email (unique)
        user.phone = request.form.get('phone', user.phone)
        user.is_staff = request.form.get('is_staff') == 'on' # Checkbox trả về 'on'
        user.is_admin = request.form.get('is_admin') == 'on' # Checkbox cho admin

        # Cập nhật thông tin employee từ form
        employee.position = form.position.data
        employee.hire_date = form.hire_date.data
        employee.salary = form.salary.data
        employee.is_active = request.form.get('is_active') == 'on' # Trạng thái hoạt động của employee

        # Nếu employee bị deactivate, is_staff cũng nên là False (trừ khi là admin?)
        if not employee.is_active:
            user.is_staff = False

        try: ### FIXED: Thêm try-except commit
            db.session.commit()
            flash('Cập nhật thông tin nhân viên thành công!', 'success')
            return redirect(url_for('admin.employees'))
        except Exception as e: ### FIXED: Rollback và logging
            db.session.rollback()
            flash(f'Lỗi khi cập nhật nhân viên: {str(e)}', 'danger')
            current_app.logger.error(f"Lỗi cập nhật employee ID {employee_id}: {e}", exc_info=True)

    # Truyền cả form Employee và dữ liệu user vào template khi GET
    if request.method == 'GET':
         user_data = { # Cập nhật lại user_data để truyền vào template
             'first_name': user.first_name,
             'last_name': user.last_name,
             'email': user.email,
             'phone': user.phone,
             'is_staff': user.is_staff,
             'is_admin': user.is_admin,
             'is_active': employee.is_active # Trạng thái của employee record
        }

    return render_template('admin/employee_form.html', form=form, user_data=user_data, title='Chỉnh sửa nhân viên', employee=employee, legend=f'Chỉnh sửa: {user.full_name}')

# Toggle Employee Status (Active/Inactive) - có thể gộp vào trang edit hoặc để riêng
@admin_bp.route('/employees/toggle-active/<int:employee_id>', methods=['POST'])
@login_required
@admin_required
def toggle_employee_active_status(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    user = User.query.get_or_404(employee.user_id)

    try:
        employee.is_active = not employee.is_active
        # Đồng bộ is_staff với is_active (trừ khi là admin)
        if not user.is_admin: # Chỉ thay đổi is_staff nếu không phải admin
            user.is_staff = employee.is_active

        try: ### FIXED: Thêm try-except commit
            db.session.commit()
            status_text = "kích hoạt" if employee.is_active else "vô hiệu hóa"
            flash(f'Đã {status_text} nhân viên {user.full_name()}.', 'success')
        except Exception as e: ### FIXED: Rollback và logging trong nested try-except
            db.session.rollback()
            flash(f'Lỗi khi thay đổi trạng thái nhân viên: {str(e)}', 'danger')
            current_app.logger.error(f"Lỗi toggle active status employee ID {employee_id}: {e}", exc_info=True)
            return redirect(url_for('admin.employees')) # Return redirect trong nested try

    except Exception as e: ### FIXED: Catch ngoại lệ ở outer try và rollback+logging
        db.session.rollback()
        flash(f'Lỗi khi thay đổi trạng thái nhân viên: {str(e)}', 'danger')
        current_app.logger.error(f"Lỗi chung khi toggle active status employee ID {employee_id}: {e}", exc_info=True)

    return redirect(url_for('admin.employees'))

# --- INVOICE AND PDF ROUTES ---

@admin_bp.route('/orders/invoice/<int:order_id>')
@login_required
@admin_required
def view_invoice(order_id): # Đổi tên hàm thành view_invoice
    order = Order.query.get_or_404(order_id)
    order_details = OrderDetail.query.filter_by(order_id=order_id).all()
    # Lấy thông tin cửa hàng/công ty từ cấu hình hoặc DB để hiển thị trên invoice
    shop_info = {
        'name': 'Dragon Coffee Shop',
        'address': '123 Đường ABC, Quận XYZ, Thành phố HCM',
        'phone': '090 xxx yyyy',
        'email': 'info@dragoncoffee.com',
        'logo': url_for('static', filename='images/logo_dragon_web.png') # Đường dẫn logo
    }
    return render_template('admin/invoice.html', # Đổi tên template cho rõ ràng
                           order=order,
                           order_details=order_details,
                           shop_info=shop_info)


@admin_bp.route('/orders/invoice/<int:order_id>/pdf')
@login_required
@admin_required
def print_invoice_pdf(order_id):
    # ... (lấy order, details, shop_info như cũ) ...
    order = Order.query.get_or_404(order_id)
    order_details = OrderDetail.query.filter_by(order_id=order_id).all()
    shop_info = {
        'name': 'Dragon Coffee Shop',
        'address': '123 Đường ABC, Quận XYZ, Thành phố HCM',
        'phone': '090 xxx yyyy',
        'email': 'info@dragoncoffee.com',
        'logo': url_for('static', filename='images/logo_dragon_web.png', _external=True)
    }

    try:
        # Render template HTML thành chuỗi
        # ----- SỬA TÊN TEMPLATE Ở ĐÂY -----
        html_string = render_template('admin/invoice.html', # <<< Sửa thành invoice.html
                                    order=order,
                                    order_details=order_details,
                                    shop_info=shop_info,
                                    # Truyền biến để ẩn nút nếu template có dùng
                                    show_buttons=False, # Giả sử bạn muốn ẩn nút trong PDF
                                    is_pdf=True)
        # ------------------------------------

        # --- Phần tạo PDF với WeasyPrint (giữ nguyên) ---
        font_config = FontConfiguration()
        css_path = os.path.join(current_app.static_folder, 'css/invoice_pdf.css') # Sửa tên biến app nếu khác
        if os.path.exists(css_path):
             base_url = request.url_root
             pdf_css = CSS(filename=css_path, font_config=font_config, base_url=base_url)
             stylesheets = [pdf_css]
        else:
             # CSS mặc định
             default_css_string = '''
                 @import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@300;400;500;700&display=swap');
                 body { font-family: 'Be Vietnam Pro', sans-serif; font-size: 9pt; line-height: 1.4; }
                 .invoice { padding: 10mm; } /* Giảm padding cho PDF */
                 .invoice-actions, .no-print { display: none; } /* Ẩn các phần không in */
                 table { width: 100%; border-collapse: collapse; margin-bottom: 15px; }
                 th, td { border: 1px solid #ddd; padding: 6px; text-align: left; }
                 th { background-color: #f8f9fa; font-weight: 500;}
                 .text-end { text-align: right; }
                 .fw-medium { font-weight: 500; }
                 .fw-bold { font-weight: 700; }
                 /* Thêm các style PDF khác nếu cần */
                 @page { margin: 15mm; size: A4; }
             '''
             default_css = CSS(string=default_css_string, font_config=font_config)
             stylesheets = [default_css]
             # flash("Không tìm thấy file css/invoice_pdf.css, sử dụng style mặc định.", "info") # Không nên flash ở route tạo PDF

        html = HTML(string=html_string, base_url=request.url_root)
        pdf_file = html.write_pdf(stylesheets=stylesheets, font_config=font_config)

        response = make_response(pdf_file)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=HoaDon_{order.order_number}.pdf'
        return response
        # --- Kết thúc phần tạo PDF ---

    except Exception as e:
        # Log lỗi chi tiết
        current_app.logger.error(f"Lỗi khi tạo PDF hóa đơn {order_id}: {str(e)}", exc_info=True)
        flash(f"Không thể tạo PDF hóa đơn. Lỗi: {str(e)}", "danger")
        # Quay về trang xem hóa đơn web nếu tạo PDF lỗi
        return redirect(url_for('admin.view_invoice', order_id=order_id))


# ------ CONTACT MESSAGES -----
@admin_bp.route('/messages')
@login_required
@admin_required
def contact_messages():
    page = request.args.get('page', 1, type=int)
    per_page = 15
    messages_pagination = ContactMessage.query.order_by(ContactMessage.created_at.desc())\
                                            .paginate(page=page, per_page=per_page, error_out=False)
    messages = messages_pagination.items
    return render_template('admin/messages.html', messages=messages, pagination=messages_pagination)


@admin_bp.route('/messages/<int:message_id>')
@login_required
@admin_required
def view_message(message_id):
    message = ContactMessage.query.get_or_404(message_id)
    if not message.is_read:
        message.is_read = True
        try: ### FIXED: Thêm try-except commit
            db.session.commit()
        except Exception as e: ### FIXED: Rollback và logging (lỗi rất ít khi xảy ra ở đây nhưng vẫn nên có)
            db.session.rollback()
            current_app.logger.error(f"Lỗi cập nhật trạng thái đọc message ID {message_id}: {e}", exc_info=True)
            flash("Lỗi khi cập nhật trạng thái tin nhắn.", "danger") # Flash lỗi nếu cần, tùy UX
    return render_template('admin/message_detail.html', message=message)


@admin_bp.route('/messages/delete/<int:message_id>', methods=['POST'])
@login_required
@admin_required
def delete_message(message_id):
    message = ContactMessage.query.get_or_404(message_id)
    try:
        db.session.delete(message)
        db.session.commit()
        flash("Đã xóa tin nhắn.", "success")
    except Exception as e: ### FIXED: Thêm try-except commit + rollback + logging
        db.session.rollback()
        flash(f"Lỗi khi xóa tin nhắn: {str(e)}", "danger")
        current_app.logger.error(f"Lỗi xóa contact message ID {message_id}: {e}", exc_info=True)
    return redirect(url_for('admin.contact_messages'))

# @admin_bp.route('/logout')
# @login_required
# def logout():
#    from flask_login import logout_user # Import ở đây để tránh circular import nếu login_manager ở app chính
#    logout_user()
#    flash('Bạn đã đăng xuất.', 'info')
#    return redirect(url_for('admin.login'))

# --- CÁC HÀM TIỆN ÍCH KHÁC (NẾU CẦN) ---
# Ví dụ: Cập nhật ghi chú nội bộ cho đơn hàng
@admin_bp.route('/orders/add-note/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def add_order_note(order_id):
    order = Order.query.get_or_404(order_id)
    note_content = request.form.get('internal_note')

    if not note_content:
        flash("Nội dung ghi chú không được để trống.", "warning")
        return redirect(url_for('admin.order_details', order_id=order_id))

    # Lưu ghi chú vào một bảng riêng hoặc một trường JSON trong Order?
    # Ví dụ đơn giản: Lưu vào trường notes (cần phân biệt với note của khách)
    new_note = f"\n[NV {current_user.username} - {datetime.now().strftime('%d/%m/%y %H:%M')}]: {note_content}"
    order.notes = (order.notes or "") + new_note # Nối vào notes hiện có

    # Tốt hơn là tạo bảng OrderNote riêng:
    # new_order_note = OrderNote(order_id=order_id, user_id=current_user.id, content=note_content, created_at=datetime.utcnow())
    # db.session.add(new_order_note)

    try: ### FIXED: Thêm try-except commit
        db.session.commit()
        flash("Đã thêm ghi chú nội bộ.", "success")
    except Exception as e: ### FIXED: Rollback và logging
        db.session.rollback()
        flash(f"Lỗi khi thêm ghi chú: {str(e)}", "danger")
        current_app.logger.error(f"Lỗi thêm order note cho order ID {order_id}: {e}", exc_info=True)

    return redirect(url_for('admin.order_details', order_id=order_id))

# Thêm hàm này vào admin_routes.py nếu bạn muốn xử lý từ trang danh sách
@admin_bp.route('/orders/process/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def process_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status == 'pending':
        order.status = 'processing'
        order.updated_at = datetime.utcnow()
        try: ### FIXED: Thêm try-except commit
            db.session.commit()
            flash(f'Đã chuyển đơn hàng #{order.order_number} sang trạng thái xử lý.', 'success')
        except Exception as e: ### FIXED: Rollback và logging
            db.session.rollback()
            flash(f'Lỗi khi xử lý đơn hàng: {str(e)}', 'danger')
            current_app.logger.error(f"Lỗi process order ID {order_id}: {e}", exc_info=True)
    else:
        flash(f'Đơn hàng #{order.order_number} không ở trạng thái chờ xử lý.', 'warning')
    return redirect(url_for('admin.orders')) # Quay lại trang danh sách

# === QUẢN LÝ CÂU CHUYỆN THÚ VỊ ===

@admin_bp.route('/interesting-stories')
@login_required
@admin_required
def interesting_stories():
    stories = InterestingStory.query.order_by(InterestingStory.status, InterestingStory.created_at.desc()).all()
    return render_template('admin/interesting_stories.html', stories=stories)

@admin_bp.route('/interesting-stories/generate', methods=['POST'])
@login_required
@admin_required
def generate_story():
    try:
        ai_content = generate_interesting_story()
        if not ai_content:
            flash("AI không thể tạo nội dung. Thử lại?", "danger")
            return redirect(url_for('admin.interesting_stories'))
        words = ai_content.split()
        default_title = " ".join(words[:6]) + "..." if len(words) > 6 else ai_content[:50]+"..."
        new_story = InterestingStory(title=default_title, content=ai_content, status='draft', generated_by_ai=True)
        db.session.add(new_story)
        db.session.commit()
        flash("Đã tạo câu chuyện nháp bằng AI.", "success")
        return redirect(url_for('admin.edit_story', story_id=new_story.id))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Lỗi tạo story: {e}", exc_info=True)
        flash(f"Lỗi tạo câu chuyện: {e}", "danger")
        return redirect(url_for('admin.interesting_stories'))

@admin_bp.route('/interesting-stories/edit/<int:story_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_story(story_id):
    """Chỉnh sửa câu chuyện thú vị."""
    story = InterestingStory.query.get_or_404(story_id)
    form = InterestingStoryForm(obj=story) # Load dữ liệu vào form

    if form.validate_on_submit():
        try:
            story.title = form.title.data
            story.content = form.content.data
            story.image_url = form.image_url.data if form.image_url.data else None
            # Admin có thể chỉnh sửa, đánh dấu không phải do AI tạo nữa? Tùy bạn
            # story.generated_by_ai = False
            story.updated_at = datetime.utcnow()
            db.session.commit()
            flash("Đã cập nhật câu chuyện thành công.", "success")
            return redirect(url_for('admin.interesting_stories'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error editing story {story_id}: {e}", exc_info=True)
            flash(f"Lỗi khi cập nhật câu chuyện: {e}", "danger")
            # Render lại form với lỗi nếu có

    elif request.method == 'POST': # Trường hợp POST nhưng form không valid
        flash("Thông tin nhập không hợp lệ, vui lòng kiểm tra lại.", "warning")

    return render_template('admin/interesting_story_form.html', form=form, story=story, title="Chỉnh sửa câu chuyện")

@admin_bp.route('/interesting-stories/toggle-status/<int:story_id>', methods=['POST'])
@login_required
@admin_required
def toggle_story_status(story_id):
    """Publish hoặc Unpublish một câu chuyện."""
    story = InterestingStory.query.get_or_404(story_id)
    try:
        if story.status == 'draft':
            story.status = 'published'
            flash(f'Đã đăng câu chuyện "{story.title[:30]}...".', 'success')
        elif story.status == 'published':
            story.status = 'draft'
            flash(f'Đã gỡ câu chuyện "{story.title[:30]}..." về bản nháp.', 'info')
        else:
            flash(f'Không thể thay đổi trạng thái của câu chuyện "{story.title[:30]}..." (hiện tại: {story.status}).', 'warning')
            return redirect(url_for('admin.interesting_stories'))

        story.updated_at = datetime.utcnow()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error toggling status for story {story_id}: {e}", exc_info=True)
        flash(f"Lỗi khi thay đổi trạng thái: {e}", "danger")

    return redirect(url_for('admin.interesting_stories'))

@admin_bp.route('/interesting-stories/delete/<int:story_id>', methods=['POST'])
@login_required
@admin_required
def delete_story(story_id):
    """Xóa một câu chuyện."""
    story = InterestingStory.query.get_or_404(story_id)
    try:
        title = story.title # Lưu lại tiêu đề trước khi xóa
        db.session.delete(story)
        db.session.commit()
        flash(f'Đã xóa câu chuyện "{title[:30]}...".', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting story {story_id}: {e}", exc_info=True)
        flash(f"Lỗi khi xóa câu chuyện: {e}", "danger")

    return redirect(url_for('admin.interesting_stories'))

# === KẾT THÚC QUẢN LÝ CÂU CHUYỆN ===

# === ROUTE ĐỂ VIẾT LẠI CÂU CHUYỆN BẰNG AI ===
@admin_bp.route('/interesting-stories/rewrite/<int:story_id>', methods=['POST'])
@login_required
@admin_required
def rewrite_story_ai(story_id):
    """Gọi AI để tạo lại nội dung cho một câu chuyện cụ thể và trả về JSON."""
    # Bạn có thể load story để lấy context nếu muốn, nhưng hiện tại hàm AI không cần
    # story = InterestingStory.query.get_or_404(story_id)

    current_app.logger.info(f"Received AI rewrite request for story ID: {story_id}")
    try:
        # Gọi hàm tạo story như bình thường (có thể thêm context nếu muốn)
        # ví dụ: ai_content = generate_interesting_story({'theme': 'bí ẩn'})
        ai_content = generate_interesting_story() # Giữ nguyên logic tạo hiện tại

        if not ai_content:
            current_app.logger.error(f"AI failed to generate rewrite for story ID: {story_id}")
            return jsonify({'success': False, 'message': 'AI không thể tạo nội dung mới vào lúc này.'}), 500

        current_app.logger.info(f"AI successfully generated rewrite for story ID: {story_id}")
        # Trả về nội dung mới dạng JSON
        return jsonify({'success': True, 'new_content': ai_content})

    except Exception as e:
        current_app.logger.error(f"Error during AI rewrite for story {story_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Lỗi máy chủ khi yêu cầu viết lại: {str(e)}'}), 500
# === KẾT THÚC ROUTE VIẾT LẠI ===