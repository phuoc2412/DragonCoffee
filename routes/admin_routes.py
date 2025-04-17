
import os
import uuid
from datetime import datetime, timedelta, time  # Đảm bảo timedelta được import
from functools import wraps
from collections import defaultdict
from app import db, app, babel # Đảm bảo đã import db
from models import InventoryItem, Product, InterestingStory,  Order, User, OrderDetail, Employee, StockReceipt, db, ContactMessage, Promotion, Location, Review # Import các model cần thiết
from forms import InterestingStoryForm, StockReceiptForm, PromotionForm, LocationForm, ForgotPasswordForm, ResetPasswordForm
from ai_services import generate_interesting_story, get_inventory_recommendations, analyze_review_sentiment
from flask import current_app, jsonify, Blueprint, request, url_for, Response, render_template_string
import csv # Import module csv
import io # Import module io (hoặc StringIO từ io)
import json
import requests
from werkzeug.utils import secure_filename
from utils import admin_required, staff_required, save_story_image, delete_file, format_currency

# Import hàm tạo ảnh từ ai_services
try:
    # Giả sử hàm nằm trong image_processing.py
    from ai_services.image_processing import generate_image_from_text_hf, save_generated_image
except ImportError:
    # Fallback hoặc báo lỗi nếu hàm không tồn tại
    def generate_image_from_text_hf(prompt):
        logger = current_app.logger if current_app else logging.getLogger()
        logger.error("!!! generate_image_from_text_hf function not available !!!")
        return None
    def save_generated_image(img_bytes, subfolder):
        logger = current_app.logger if current_app else logging.getLogger()
        logger.error("!!! save_generated_image function not available !!!")
        return None


try:
    from utils import (admin_required, staff_required,
                       send_reset_email, send_order_status_email) # <-- THÊM VÀO ĐÂY
except ImportError:
     # Xử lý lỗi import nếu cần
     # Ví dụ: Định nghĩa một hàm placeholder
     def send_reset_email(user):
         logger = current_app.logger if current_app else logging.getLogger()
         logger.error("send_reset_email function is not available!")
         return False
     # Hoặc raise lỗi
     # raise ImportError("Could not import send_reset_email function from utils.")
import logging

from utils import (admin_required, staff_required, generate_order_number,
                   send_reset_email, send_order_status_email, send_contact_notification_email,
                   format_currency, # <<<======== THÊM IMPORT Ở ĐÂY ========>>>
                   get_order_status_label) # Bổ sung nếu template macro _ui_helpers dùng
from flask import (Blueprint, flash, jsonify, make_response, redirect,
                   render_template, request, url_for, Response, current_app) # Thêm current_app import
from flask_login import current_user, login_required, login_user, logout_user
# Xóa dòng này nếu không dùng fontTools trực tiếp ở đây: from fontTools.ttLib import TTFont
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration
from sqlalchemy.orm import joinedload, contains_eager, selectinload, aliased

from app import app, db
from forms import (CategoryForm, ContactForm, EmployeeForm, LoginForm,
                   ProductForm, PromotionForm, ReviewForm)
from models import (Category, ContactMessage, Employee, InventoryItem, Order,
                   OrderDetail, Product, Promotion, Review, User,)
from sqlalchemy import desc, func, or_, cast, String, case


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# --- API ROUTE TÌM KIẾM KHÁCH HÀNG ---
@admin_bp.route('/api/search-customers')
@login_required
@admin_required # Hoặc @staff_required
def api_search_customers():
    search_query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 10, type=int) # Giới hạn số lượng kết quả
    results = []

    if len(search_query) >= 2: # Chỉ tìm khi có ít nhất 2 ký tự
        try:
            search_term = f"%{search_query}%"
            customers = User.query.filter(
                User.is_admin == False, # Không tìm admin/staff
                User.is_staff == False,
                or_(
                    # Tìm gần đúng không phân biệt hoa thường
                    (User.first_name + ' ' + User.last_name).ilike(search_term),
                    User.email.ilike(search_term),
                    User.phone.ilike(search_term)
                )
            ).order_by(User.last_name, User.first_name).limit(limit).all()

            results = [
                {
                    'id': customer.id,
                    'full_name': customer.full_name, # Dùng @property nếu có
                    'email': customer.email,
                    'phone': customer.phone
                }
                for customer in customers
            ]
        except Exception as e:
            current_app.logger.error(f"API Customer Search Error: {e}", exc_info=True)
            # Không trả lỗi chi tiết về client, chỉ trả list rỗng
            return jsonify([]) # Trả list rỗng nếu có lỗi DB

    return jsonify(results) # Trả về list (có thể rỗng)
# ----------------------------------

# --- Route mới để xử lý nhập kho ---
@admin_bp.route('/inventory/add-stock', methods=['GET', 'POST'])
@login_required
@admin_required
def add_stock():
    form = StockReceiptForm() # Form vẫn có coerce=int

    try:
        # Chỉ lấy các lựa chọn hợp lệ từ DB
        inventory_choices = [
            (item.id, item.product_inventory.name)
            for item in InventoryItem.query.join(Product).order_by(Product.name).all()
            if hasattr(item, 'product_inventory') and item.product_inventory
        ]
        # *** CHỈ GÁN LỰA CHỌN HỢP LỆ ***
        form.inventory_item_id.choices = inventory_choices
    except Exception as e:
         current_app.logger.error(f"Lỗi khi lấy danh sách sản phẩm tồn kho: {e}", exc_info=True)
         flash("Lỗi khi tải danh sách sản phẩm. Không thể nhập kho.", "danger")
         form.inventory_item_id.choices = [] # Vẫn gán list rỗng nếu lỗi DB

    # *** BỎ DÒNG INSERT PLACEHOLDER Ở ĐÂY ***
    # form.inventory_item_id.choices.insert(0, ('', '-- Chọn sản phẩm --')) # <--- BỎ DÒNG NÀY

    if form.validate_on_submit():
        inventory_item_id = form.inventory_item_id.data # Sẽ là int hợp lệ vì DataRequired + coerce=int
        quantity_added = form.quantity_added.data
        # Dùng get để tránh lỗi nếu ID không hợp lệ sau validation (dù hiếm)
        inventory_item = db.session.get(InventoryItem, inventory_item_id)

        if not inventory_item:
            flash(f'Lỗi: Không tìm thấy item tồn kho ID {inventory_item_id}.', 'danger')
            return redirect(url_for('admin.inventory'))

        related_product = getattr(inventory_item, 'product_inventory', None)
        if not related_product:
            flash(f'Lỗi: Item tồn kho ID {inventory_item_id} không có sản phẩm liên kết.', 'danger')
            return redirect(url_for('admin.inventory'))

        try:
            # ... (Logic tạo receipt và cập nhật inventory giữ nguyên) ...
            receipt = StockReceipt(
                product_id=inventory_item.product_id,
                inventory_item_id=inventory_item_id,
                quantity_added=quantity_added,
                supplier=form.supplier.data,
                unit_cost=form.unit_cost.data if form.unit_cost.data is not None else None,
                notes=form.notes.data,
                received_by_user_id=current_user.id,
                received_at = datetime.utcnow()
            )
            db.session.add(receipt)
            inventory_item.quantity += quantity_added
            inventory_item.last_restocked = datetime.utcnow()
            inventory_item.last_updated = datetime.utcnow()
            db.session.commit()
            flash(f"Đã nhập thêm {quantity_added} cho sản phẩm '{related_product.name}'.", "success")
            return redirect(url_for('admin.inventory'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Lỗi khi nhập kho cho item ID {inventory_item_id}: {e}", exc_info=True)
            flash(f"Lỗi hệ thống khi nhập kho: {str(e)}", "danger")
            # Render lại form khi lỗi commit, cần gán lại choices
            # form.inventory_item_id.choices = inventory_choices # Gán lại list hợp lệ

    # Render cho GET hoặc POST không hợp lệ
    # Phải gán lại choices ở đây nếu POST bị lỗi validation VÀ bạn *không* thêm placeholder trong HTML
    # Nếu bạn thêm placeholder trong HTML (Bước 2) thì không cần gán lại ở đây
    # form.inventory_item_id.choices = [('', '-- Chọn sản phẩm --')] + inventory_choices

    return render_template('admin/add_stock_form.html', form=form, title="Nhập kho Sản phẩm")

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

    if form.validate_on_submit():
        image_url = None
        image_file = request.files.get('image_file') # Lấy file từ request

        if image_file and image_file.filename: # Nếu có file được upload
            image_path_relative = save_product_image(image_file)
            if image_path_relative:
                 # Dùng url_for để tạo URL web hoàn chỉnh
                 image_url = url_for('static', filename=image_path_relative, _external=False)
                 # Không cần external=True vì đang dùng trong cùng app
            else:
                 # Nếu lưu file lỗi, dừng lại hoặc dùng ảnh mặc định
                 flash('Lưu ảnh sản phẩm thất bại.', 'danger')
                 # Không redirect, để người dùng sửa form
                 return render_template('admin/product_form.html', form=form, title='Thêm sản phẩm', legend='Thêm sản phẩm mới')
        elif form.image_url.data: # Nếu không upload file thì dùng URL nhập vào
             image_url = form.image_url.data
        else:
             image_url = None # Không có ảnh

        # === Tạo sản phẩm và inventory ===
        try:
            product = Product(
                name=form.name.data, description=form.description.data,
                price=form.price.data, image_url=image_url, # Lưu URL hoặc None
                is_available=form.is_available.data, is_featured=form.is_featured.data,
                category_id=form.category_id.data
            )
            db.session.add(product)
            db.session.flush()
            inventory = InventoryItem(
                product_id=product.id,
                quantity=form.stock_quantity.data if form.stock_quantity.data is not None else 0,
                min_quantity=form.min_quantity.data if form.min_quantity.data is not None else 10
            )
            db.session.add(inventory)
            db.session.commit()
            flash('Thêm sản phẩm thành công!', 'success')
            return redirect(url_for('admin.menu_management'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Lỗi thêm sản phẩm (DB): {e}", exc_info=True)
            flash(f'Lỗi khi thêm sản phẩm: {str(e)}', 'danger')
            # Xóa ảnh đã upload nếu DB bị lỗi
            if image_file and 'image_path_relative' in locals() and image_path_relative:
                delete_old_image(image_path_relative) # Thực chất là xóa file vừa upload
                flash("Đã xóa file ảnh vừa upload do lỗi database.", "warning")

    elif request.method == 'POST':
         flash('Có lỗi trong form, vui lòng kiểm tra lại.', 'warning')

    return render_template('admin/product_form.html', form=form, title='Thêm sản phẩm', legend='Thêm sản phẩm mới')

@admin_bp.route('/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    product = Product.query.options(joinedload(Product.inventory)).get_or_404(product_id)
    inventory = product.inventory # Truy cập inventory đã eager load
    if not inventory:
        inventory = InventoryItem(product_id=product_id, quantity=0, min_quantity=10)
        current_app.logger.info(f"Creating temporary inventory object for product {product_id}")

    form = ProductForm(obj=product)
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by('name').all()]
    current_image_url = product.image_url # Lưu URL ảnh hiện tại

    if request.method == 'GET':
        if inventory:
            form.stock_quantity.data = inventory.quantity
            form.min_quantity.data = inventory.min_quantity
        # Giữ lại image_url trong ô nhập URL nếu nó là URL web, ko phải link static
        if current_image_url and not current_image_url.startswith(url_for('static', filename='')):
             form.image_url.data = current_image_url

    if form.validate_on_submit():
        old_image_relative_path = None
        # Xác định URL ảnh tương đối cũ nếu nó là file upload
        if current_image_url and current_image_url.startswith(url_for('static', filename='uploads/')):
             # Tách phần '/static/' khỏi đầu URL để lấy path tương đối trong static
             prefix = url_for('static', filename='')
             if current_image_url.startswith(prefix):
                 old_image_relative_path = current_image_url[len(prefix):]
                 current_app.logger.debug(f"Old image relative path identified: {old_image_relative_path}")


        new_image_url = current_image_url # Mặc định giữ ảnh cũ
        image_file = request.files.get('image_file')

        # Ưu tiên file upload mới
        if image_file and image_file.filename:
            new_relative_path = save_product_image(image_file)
            if new_relative_path:
                new_image_url = url_for('static', filename=new_relative_path, _external=False)
                current_app.logger.info(f"New image uploaded, URL set to: {new_image_url}")
                # Sẽ xóa ảnh cũ *sau khi* commit DB thành công
            else:
                 flash('Lưu ảnh mới thất bại, giữ nguyên ảnh cũ (nếu có).', 'danger')
                 new_image_url = current_image_url # Đảm bảo giữ lại ảnh cũ nếu upload lỗi
        # Nếu không có upload, kiểm tra URL nhập vào
        elif form.image_url.data and form.image_url.data != current_image_url:
            # User đã nhập URL mới hoặc xóa URL cũ
             new_image_url = form.image_url.data if form.image_url.data.strip() else None
             current_app.logger.info(f"Image URL field changed, new URL: {new_image_url}")
             # Nếu URL mới được nhập, có thể ảnh cũ cần bị xóa nếu nó là file upload
        elif not form.image_url.data and current_image_url and image_file.filename == '':
             # Nếu ô URL bị xóa trống VÀ không có file upload -> Người dùng muốn xóa ảnh
             new_image_url = None
             current_app.logger.info("Image URL field cleared, removing image association.")
             # Ảnh cũ (nếu là file upload) sẽ bị xóa sau commit

        # --- Cập nhật sản phẩm và inventory ---
        product.name = form.name.data
        product.description = form.description.data
        product.price = form.price.data
        product.image_url = new_image_url # Lưu URL mới hoặc None
        product.is_available = form.is_available.data
        product.is_featured = form.is_featured.data
        product.category_id = form.category_id.data
        product.updated_at = datetime.utcnow()

        if inventory:
             inventory.quantity = form.stock_quantity.data if form.stock_quantity.data is not None else inventory.quantity
             inventory.min_quantity = form.min_quantity.data if form.min_quantity.data is not None else inventory.min_quantity
             inventory.last_updated = datetime.utcnow()
             if not inventory.id: db.session.add(inventory) # Add nếu nó được tạo tạm lúc GET
        # (else case: inventory lỗi load ban đầu -> log/flash?)

        try:
            db.session.commit()
            flash('Cập nhật sản phẩm thành công!', 'success')
            # Xóa ảnh cũ nếu có ảnh mới được upload HOẶC URL bị xóa
            if old_image_relative_path and new_image_url != current_image_url:
                delete_old_image(old_image_relative_path)
            return redirect(url_for('admin.menu_management'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Lỗi cập nhật sản phẩm (DB) ID {product_id}: {e}", exc_info=True)
            flash(f'Lỗi khi cập nhật sản phẩm: {str(e)}', 'danger')
            # Xóa file mới upload nếu commit DB lỗi
            if image_file and 'new_relative_path' in locals() and new_relative_path:
                 delete_old_image(new_relative_path)
                 flash("Đã xóa file ảnh vừa upload do lỗi database.", "warning")

    elif request.method == 'POST':
        flash('Có lỗi trong form, vui lòng kiểm tra lại.', 'warning')

    return render_template('admin/product_form.html', form=form, title='Chỉnh sửa sản phẩm', product=product, legend=f'Chỉnh sửa: {product.name}', current_image_url=current_image_url)

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

@admin_bp.route('/orders/<int:order_id>')
@login_required
@admin_required
def order_details(order_id):
    # --- LOGIC LẤY DỮ LIỆU GIỮ NGUYÊN ---
    order = Order.query.options(
                joinedload(Order.customer)
            ).get_or_404(order_id)
    order_details = db.session.query(OrderDetail).options(
                        joinedload(OrderDetail.ordered_product)
                    ).filter(OrderDetail.order_id == order_id).all()

    # --- Logic tính toán thời gian giữ nguyên ---
    payment_confirmation_time, processing_time_display, completed_time_display, cancelled_time_display = None, None, None, None
    # ... (code tính thời gian như cũ) ...
    if order.created_at:
        try:
            if order.payment_status == 'completed':
                payment_confirmation_time = order.updated_at if order.payment_method != 'cash' else order.created_at + timedelta(minutes=5)
            if order.status in ['processing', 'completed', 'delivered', 'shipped']:
                processing_time_display = order.updated_at if order.updated_at > order.created_at else order.created_at + timedelta(minutes=10)
            if order.status == 'completed' or order.status == 'delivered':
                completed_time_display = order.updated_at if order.updated_at > order.created_at else order.created_at + timedelta(minutes=30)
            if order.status == 'cancelled':
                cancelled_time_display = order.updated_at
        except TypeError: pass # Bỏ qua lỗi type error
        except Exception as e: pass # Bỏ qua các lỗi khác


    # ===> **ĐÃ XÓA `, format_price=format_currency` KHỎI ĐÂY** <===
    return render_template('admin/order_details.html',
                           order=order,
                           order_details=order_details,
                           payment_confirmation_time=payment_confirmation_time,
                           processing_time_display=processing_time_display,
                           completed_time_display=completed_time_display,
                           cancelled_time_display=cancelled_time_display
                          )

@admin_bp.route('/orders/update-status/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    logger = current_app.logger if current_app else logging.getLogger()
    updated_fields = [] # List để theo dõi các trường đã cập nhật

    # Lấy dữ liệu từ form
    new_order_status = request.form.get('status')
    new_payment_status = request.form.get('payment_status')
    valid_order_statuses = ['pending', 'processing', 'ready_for_pickup', 'out_for_delivery', 'completed', 'delivered', 'cancelled', 'failed']
    valid_payment_statuses = ['pending', 'completed', 'paid', 'failed', 'cancelled', 'refunded']

    # --- Cập nhật Trạng thái Đơn hàng ---
    if new_order_status is not None:
        if new_order_status in valid_order_statuses:
            if order.status != new_order_status:
                order.status = new_order_status
                updated_fields.append(f"Trạng thái ĐH thành '{order.get_status_display()}'")
                logger.info(f"Updating Order {order_id} status to '{new_order_status}'")
                if new_order_status == 'cancelled' and order.payment_status not in ['cancelled', 'refunded']:
                     order.payment_status = 'cancelled'
                     updated_fields.append("Trạng thái TT thành 'Đã hủy TT'")
                elif new_order_status == 'completed' and order.payment_status not in ['completed', 'paid']:
                      order.payment_status = 'completed'
                      updated_fields.append("Trạng thái TT thành 'Đã thanh toán'")
            # else: flash(...) # Có thể flash info nếu không thay đổi
        else:
            flash(f'Trạng thái đơn hàng "{new_order_status}" không hợp lệ.', 'danger')
            return redirect(request.referrer or url_for('admin.order_details', order_id=order_id))

    # --- Cập nhật Trạng thái Thanh toán ---
    if new_payment_status is not None:
        if new_payment_status in valid_payment_statuses:
            if order.payment_status != new_payment_status:
                order.payment_status = new_payment_status
                updated_fields.append(f"Trạng thái TT thành '{new_payment_status.replace('_', ' ').title()}'")
                logger.info(f"Updating Order {order_id} payment status to '{new_payment_status}'")
            # else: flash(...) # Có thể flash info nếu không thay đổi
        else:
            flash(f'Trạng thái thanh toán "{new_payment_status}" không hợp lệ.', 'danger')
            return redirect(request.referrer or url_for('admin.order_details', order_id=order_id))

    # --- Lưu thay đổi nếu có ---
    # Dòng 686 bạn đề cập
    if updated_fields:
        # ===> ĐẢM BẢO CÁC DÒNG SAU ĐƯỢC THỤT LỀ ĐÚNG CÁCH <===
        # Lấy trạng thái cũ trước khi commit (dùng get_history có thể phức tạp, cách đơn giản hơn là query lại trước khi sửa)
        # Thay vì get_history, query trạng thái cũ lưu vào biến tạm trước khi sửa đổi `order.status`
        # -> Nên thực hiện query trạng thái cũ ở đầu hàm nếu cần dùng.
        # Giả sử bạn đã có biến `original_status_value` lưu trạng thái cũ trước khi sửa `order.status`
        # Hoặc bạn chỉ cần gửi email dựa trên trạng thái mới `new_order_status`

        order.updated_at = datetime.utcnow()
        try:
            db.session.commit() # Commit thay đổi vào DB trước khi gửi mail
            flash(f'Đã cập nhật cho đơn hàng #{order.order_number}: {", ".join(updated_fields)}.', 'success')
            logger.info(f"Successfully updated order {order_id}. Fields: {', '.join(updated_fields)}")

            # *** GỌI HÀM GỬI EMAIL SAU KHI COMMIT THÀNH CÔNG ***
            # Sử dụng trạng thái MỚI NHẤT của order sau khi commit để gửi email
            if new_order_status and new_order_status in ['processing', 'ready_for_pickup', 'out_for_delivery', 'completed', 'delivered', 'cancelled']:
                 # Query lại order để đảm bảo lấy đúng trạng thái mới nhất nếu cần, nhưng order object thường được update sau commit
                 send_order_status_email(order) # Gửi email với trạng thái mới

        except Exception as e:
            db.session.rollback()
            logger.error(f"DB error updating order {order_id}: {e}", exc_info=True)
            flash(f'Lỗi khi cập nhật đơn hàng: {str(e)}', 'danger')
        # ====> KẾT THÚC KHỐI THỤT LỀ <====
    # else: Không có gì để cập nhật


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
     total_base_amount_calculated = 0
     product_inventory_updates = {}

     # ==== LẤY THÔNG TIN KHÁCH HÀNG TỪ REQUEST ====
     customer_id = data.get('customer_id') # ID của KH đã chọn (có thể là None)
     guest_phone = (data.get('contact_phone') or '').strip() # SĐT khách vãng lai
     order_user_id = None # User ID sẽ gán cho đơn hàng
     contact_phone_for_order = guest_phone # Mặc định là SĐT khách vãng lai
     customer_name_display = None # Để log (tùy chọn)
     # ===========================================

     try:
        with db.session.begin_nested(): # Bắt đầu transaction

            # === XÁC ĐỊNH USER_ID CHO ĐƠN HÀNG ===
            if customer_id:
                 customer = User.query.get(customer_id)
                 if customer and not customer.is_admin and not customer.is_staff: # Đảm bảo là khách hàng hợp lệ
                      order_user_id = customer.id
                      # Ưu tiên SĐT đã lưu trong profile KH nếu SĐT khách vãng lai trống
                      contact_phone_for_order = guest_phone or customer.phone or ''
                      customer_name_display = customer.full_name
                      logger.info(f"POS order associated with customer ID: {customer_id} ({customer_name_display})")
                 else:
                      logger.warning(f"Invalid or non-customer ID received: {customer_id}. Proceeding as guest or staff.")
                      # Nếu ID không hợp lệ, xem như không có customer_id
                      customer_id = None
                      # Dùng guest_phone nếu có, nếu không đơn hàng sẽ là của staff
                      if not guest_phone:
                          order_user_id = current_user.id # Gán cho staff nếu cả KH và SĐT khách đều không có
                          logger.info(f"POS order (no valid customer/guest info) assigned to staff ID: {current_user.id}")
            elif guest_phone:
                 order_user_id = None # Đơn của khách vãng lai không link user_id
                 contact_phone_for_order = guest_phone
                 customer_name_display = f"Guest ({guest_phone})"
                 logger.info(f"POS order for guest with phone: {guest_phone}")
            else: # Không có ID khách, không có SĐT khách -> Gán cho nhân viên
                 order_user_id = current_user.id
                 contact_phone_for_order = current_user.phone or ''
                 customer_name_display = f"Staff ({current_user.username})"
                 logger.info(f"POS order with no customer/guest info assigned to staff ID: {current_user.id}")
            # =====================================

            # --- Kiểm tra tồn kho và tính tổng (giữ nguyên) ---
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
            # ----------------------------------------------------

            # --- Tính final_amount (giữ nguyên) ---
            tax_rate_pos = 0.10
            discount_amount_pos = 0
            tax_amount_pos = total_base_amount_calculated * tax_rate_pos
            final_amount_calculated = total_base_amount_calculated + tax_amount_pos - discount_amount_pos
            # -----------------------------------

            # --- Tạo Order VỚI user_id và contact_phone ĐÃ XÁC ĐỊNH ---
            new_order = Order(
                user_id=order_user_id, # Có thể là ID KH, None (khách vãng lai), hoặc ID staff
                order_number=f"POS-{uuid.uuid4().hex[:8].upper()}",
                status='completed',
                total_amount=total_base_amount_calculated,
                final_amount=final_amount_calculated,
                order_type=data.get('order_type', 'dine-in'),
                payment_method=data.get('payment_method', 'cash'),
                payment_status='completed',
                notes=data.get('notes', ''),
                address=None,
                contact_phone=contact_phone_for_order # Gán SĐT đã xác định
            )
            db.session.add(new_order)
            db.session.flush()
            # ----------------------------------------------------------

            # --- Tạo OrderDetail và Cập nhật Inventory (giữ nguyên) ---
            for item_data in items_data:
                # Lấy giá sản phẩm tại thời điểm tạo chi tiết đơn hàng
                product_price = db.session.query(Product.price).filter(Product.id == item_data['product_id']).scalar()
                if product_price is None:
                    # Xử lý trường hợp giá sản phẩm không tìm thấy (có thể bỏ qua hoặc gán giá mặc định)
                    logger.warning(f"Không tìm thấy giá cho Product ID {item_data['product_id']} khi tạo OrderDetail.")
                    calculated_unit_price = 0
                else:
                    calculated_unit_price = float(product_price) # Ép kiểu sang float cho chắc

                calculated_subtotal = calculated_unit_price * item_data['quantity']
                order_notes = item_data.get('notes', '') or None # Gán None nếu chuỗi rỗng

                # ----- **KHỞI TẠO OrderDetail DÙNG KEYWORD ARGUMENTS** -----
                order_detail = OrderDetail(
                    order_id=new_order.id,                  # Keyword argument
                    product_id=item_data['product_id'],     # Keyword argument
                    quantity=item_data['quantity'],         # Keyword argument
                    unit_price=calculated_unit_price,       # Keyword argument
                    subtotal=calculated_subtotal,           # Keyword argument
                    notes=order_notes                       # Keyword argument
                )
                # -------------------------------------------------------
                db.session.add(order_detail)

                # --- Phần trừ tồn kho (Giữ nguyên) ---
                inventory = db.session.query(InventoryItem).filter_by(product_id=item_data['product_id']).with_for_update().one_or_none()
                if inventory:
                    if inventory.quantity >= item_data['quantity']:
                        inventory.quantity -= item_data['quantity']
                        inventory.last_updated = datetime.utcnow()
                    else:
                        # Lỗi này không nên xảy ra nếu kiểm tra ban đầu đúng
                        raise ValueError(f"Lỗi tồn kho không nhất quán cho SP ID {item_data['product_id']} khi commit POS.")
                else:
                    logger.warning(f"Inv item not found for product {item_data['product_id']} when decrementing stock.")
                # --- Kết thúc phần trừ tồn kho ---

        # db.session.commit() # Commit transaction (đã có trong begin_nested)
        logger.info(f"POS Order {new_order.order_number} (Customer: {customer_name_display}, Contact: {contact_phone_for_order}) created successfully by staff {current_user.id}.")
        return jsonify({ 'success': True, 'order_id': new_order.id, 'order_number': new_order.order_number, 'message': f'Đã tạo đơn hàng POS {new_order.order_number}.'})

     except ValueError as ve:
        # db.session.rollback() # Tự rollback khi thoát with hoặc có lỗi
        logger.warning(f"POS order validation failed: {ve}")
        return jsonify({'success': False, 'error': str(ve)}), 400
     except Exception as e:
        # db.session.rollback() # Tự rollback
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
    limit = 30

    try:
        # Lấy InventoryItem và Product liên quan
        inventory_item = db.session.query(InventoryItem).options(
            # joinedload(InventoryItem.product_inventory) # Bỏ đi nếu không dùng/gây lỗi
             joinedload('product_inventory', innerjoin=False) # Thay thế bằng tên relationship nếu có
        ).get(inventory_id)

        if not inventory_item:
            return "<div class='alert alert-warning'>Không tìm thấy mục tồn kho.</div>", 404

        # ===== **LẤY THÔNG TIN PRODUCT THEO CÁCH KHÁC** =====
        # product_id_for_query = inventory_item.product_id
        # product_info = db.session.query(Product).get(product_id_for_query) # Query riêng Product
        # product_name = product_info.name if product_info else f"ID {product_id_for_query}"
        # -----------------------------------------------

        # ---- Truy cập product qua relationship một cách an toàn ----
        product_id_for_query = inventory_item.product_id
        related_product = getattr(inventory_item, 'product_inventory', None) # Lấy an toàn
        product_name = related_product.name if related_product else f"SP ID {product_id_for_query}"
        # --------------------------------------------------------

        # --- Query Lịch Sử Bán Hàng (Xuất kho) ---
        sales_history = db.session.query(
                Order.order_number,
                Order.created_at,
                OrderDetail.quantity,
                OrderDetail.unit_price,
                Order.id.label('order_id')
            ).join(OrderDetail, Order.id == OrderDetail.order_id)\
             .filter(
                 OrderDetail.product_id == product_id_for_query,
                 Order.status.in_(['completed', 'delivered'])
             )\
             .order_by(desc(Order.created_at))\
             .limit(limit)\
             .all()
        logger.debug(f"Found {len(sales_history)} sales history records.")

        # --- Query Lịch Sử Nhập Kho (Bảng mới) ---
        receipt_history = db.session.query(StockReceipt).options(joinedload(StockReceipt.received_by))\
             .filter(StockReceipt.inventory_item_id == inventory_id)\
             .order_by(desc(StockReceipt.received_at))\
             .limit(limit)\
             .all()
        logger.debug(f"Found {len(receipt_history)} stock receipt records.")

        # --- Render template partial ---
        return render_template('admin/_inventory_history_content.html',
                               item=inventory_item,
                               product_name=product_name, # Dùng tên đã lấy
                               sales_history=sales_history,
                               receipt_history=receipt_history,
                               limit=limit)

    except Exception as e:
        logger.error(f"Error fetching inventory history for item {inventory_id}: {e}", exc_info=True)
        return "<div class='alert alert-danger'>Lỗi máy chủ khi tải dữ liệu lịch sử.</div>", 500
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
    logger = current_app.logger
    report_type = request.args.get('type', 'sales')
    period = request.args.get('period')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # --- Xác định Ngày bắt đầu và kết thúc (Giữ nguyên logic) ---
    end_date = datetime.utcnow().date()
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date(); period = None
        except ValueError: flash("Ngày kết thúc không hợp lệ.", "warning")
    start_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date(); period = None
        except ValueError: flash("Ngày bắt đầu không hợp lệ.", "warning")

    if not start_date: # Chỉ set start_date dựa trên period nếu start_date chưa được set bởi form
        if period == 'day': start_date = end_date
        elif period == 'month': start_date = end_date.replace(day=1)
        elif period == 'year': start_date = end_date.replace(month=1, day=1)
        else: # Mặc định là tuần nếu không có period và không có ngày cụ thể
              if not period and not start_date_str and not end_date_str: period = 'week' # Đặt period mặc định
              start_date = end_date - timedelta(days=6) # Logic default week vẫn giữ nguyên

    if start_date and end_date and start_date > end_date:
        flash("Ngày bắt đầu không thể lớn hơn ngày kết thúc.", "warning")
        start_date = end_date - timedelta(days=6); end_date = datetime.utcnow().date(); period='week'
    # --------------------------------------------------------------------

    start_datetime = datetime.combine(start_date, time.min)
    end_datetime = datetime.combine(end_date, time.max)
    logger.info(f"Generating report: type={report_type}, period={period}, start={start_date}, end={end_date}")

    # Tạo context chung cho tất cả các template
    render_context = {
        'report_type': report_type,
        'period': period,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d')
    }
    # *** Inject Các Filter Jinja Cần Thiết ***
    render_context['format_price'] = format_currency # Giả sử format_currency là hàm cần thiết
    # Thêm các filter khác nếu cần, ví dụ format_datetime
    from app import format_datetime_filter # Hoặc từ utils
    render_context['format_datetime'] = format_datetime_filter


    try:
        base_order_query = Order.query.filter(
            Order.created_at >= start_datetime,
            Order.created_at <= end_datetime,
            Order.status.in_(['completed', 'delivered'])
        )

        if report_type == 'sales':
            orders_in_period = base_order_query.options(
                db.selectinload(Order.customer)
            ).order_by(Order.created_at.asc()).all()
            total_sales_in_period = sum(o.final_amount if o.final_amount is not None else o.total_amount or 0.0 for o in orders_in_period)
            total_orders_count_in_period = len(orders_in_period)
            daily_sales = defaultdict(float)
            current_scan_date = start_date
            while current_scan_date <= end_date:
                daily_sales[current_scan_date.strftime('%Y-%m-%d')] = 0.0
                current_scan_date += timedelta(days=1)
            for order in orders_in_period:
                order_date_str = order.created_at.date().strftime('%Y-%m-%d')
                amount_to_sum = order.final_amount if order.final_amount is not None else order.total_amount or 0.0
                daily_sales[order_date_str] += float(amount_to_sum)
            sorted_daily_sales = dict(sorted(daily_sales.items()))
            chart_labels = [datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m') for d in sorted_daily_sales.keys()]
            chart_values = [v for v in sorted_daily_sales.values()]
            sales_chart_data = {'labels': chart_labels, 'values': chart_values}

            render_context.update({
                'orders': orders_in_period,
                'chart_data': sales_chart_data,
                'total_sales': total_sales_in_period,
                'total_orders': total_orders_count_in_period
            })
            return render_template('admin/reports/sales_report.html', **render_context)

        elif report_type == 'products':
            logger.info("Generating Product Report...")
            product_sales_data = db.session.query(
                Product.id,
                Product.name,
                Category.name.label('category_name'),
                func.sum(OrderDetail.quantity).label('total_quantity'),
                func.sum(OrderDetail.subtotal).label('total_revenue'),
                func.avg(OrderDetail.unit_price).label('avg_price')
            ).select_from(OrderDetail)\
             .join(Order, OrderDetail.order_id == Order.id)\
             .join(Product, OrderDetail.product_id == Product.id)\
             .join(Category, Product.category_id == Category.id)\
             .filter(
                 Order.created_at >= start_datetime,
                 Order.created_at <= end_datetime,
                 Order.status.in_(['completed', 'delivered'])
             ).group_by(Product.id, Product.name, Category.name)\
             .order_by(desc('total_revenue'))\
             .all()
            logger.info(f"Found {len(product_sales_data)} products with sales in period.")

            # --- **LỌC VÀ TÍNH TOÁN AN TOÀN** ---
            safe_product_sales_list = []
            safe_total_revenue_values_for_sum = [] # Chỉ chứa số để tính tổng
            for p in product_sales_data:
                revenue = p.total_revenue
                # Kiểm tra chặt chẽ hơn: phải là số và không phải None
                if isinstance(revenue, (int, float, db.Numeric)) and revenue is not None:
                    safe_product_sales_list.append(p)
                    safe_total_revenue_values_for_sum.append(float(revenue)) # Ép kiểu float cho sum
                else:
                    logger.warning(f"Invalid type/value for total_revenue of product '{p.name}': {revenue} ({type(revenue)}). Skipping in calculations.")

            total_revenue_for_products = sum(safe_total_revenue_values_for_sum)
            # -------------------------------------

            # Tạo dữ liệu chart từ list AN TOÀN
            top_products_chart = safe_product_sales_list[:10] # Lấy top từ list an toàn
            product_chart_values = [float(p.total_revenue or 0.0) for p in top_products_chart] # Lấy value an toàn
            product_chart_data = {
                'labels': [p.name for p in top_products_chart],
                'values': product_chart_values # <-- Dùng list values đã tạo
            }
            # ***** Tính tổng các giá trị trong biểu đồ để kiểm tra trong template *****
            chart_values_sum = sum(product_chart_values)
            # ***********************************************************************
            logger.debug(f"Product Chart Data (Revenue): labels={len(product_chart_data['labels'])}, values_sum={chart_values_sum}")

            render_context.update({
                'product_sales': safe_product_sales_list,
                'chart_data': product_chart_data,
                'total_revenue': total_revenue_for_products,
                'chart_values_sum': chart_values_sum # ***** TRUYỀN SUM NÀY VÀO *****
            })
            # Inject filter không cần nữa nếu đã làm ở đầu hàm reports
            # render_context['format_price'] = format_currency
            return render_template('admin/reports/product_report.html', **render_context)

        elif report_type == 'customers':
            logger.info("Generating Customer Report...")
            customer_stats = db.session.query(
               User.id, User.first_name, User.last_name, User.username,
               User.email, User.phone,
               User.created_at.label('registered_date'),
               func.count(Order.id).label('order_count'),
               func.sum(Order.final_amount if Order.final_amount is not None else Order.total_amount).label('total_spent')
            ).join(Order, User.id == Order.user_id)\
             .filter(
                Order.created_at >= start_datetime,
                Order.created_at <= end_datetime,
                Order.status.in_(['completed', 'delivered']),
                User.is_admin == False,
                User.is_staff == False
            ).group_by(User.id)\
             .order_by(desc('total_spent'), desc('order_count'))\
             .all()
            logger.info(f"Found {len(customer_stats)} active customers in period.")
            # Inject filter không cần nữa nếu đã làm ở đầu hàm reports
            # render_context['format_price'] = format_currency
            render_context.update({'customer_stats': customer_stats})
            return render_template('admin/reports/customer_report.html', **render_context)

        elif report_type == 'inventory':
            logger.info("Generating General Inventory Report (Current Status)...")
            search_inventory = request.args.get('search_inventory', '')
            inventory_query = db.session.query(InventoryItem).options(
                joinedload(InventoryItem.product_inventory).joinedload(Product.category)
            )
            inventory_query = inventory_query.join(Product, InventoryItem.product_id == Product.id)
            if search_inventory:
                inventory_query = inventory_query.filter(Product.name.ilike(f'%{search_inventory}%'))

            inventory_items = inventory_query.order_by(
                case(
                    (InventoryItem.quantity <= 0, 0),
                    (InventoryItem.quantity <= InventoryItem.min_quantity, 1),
                    else_=2
                ),
                Product.name.asc()
            ).all()
            logger.info(f"Found {len(inventory_items)} inventory items for snapshot report.")

            total_items_count = len(inventory_items)
            calculated_low_count = sum(1 for item in inventory_items if 0 < item.quantity <= item.min_quantity)
            calculated_out_count = sum(1 for item in inventory_items if item.quantity <= 0)
            calculated_adequate_count = total_items_count - calculated_low_count - calculated_out_count

            # Inject filter không cần nữa nếu đã làm ở đầu hàm reports
            # render_context['format_price'] = format_currency
            # render_context['format_datetime'] = format_datetime_filter

            render_context.update({
                'inventory_items': inventory_items,
                'search_inventory': search_inventory,
                'total_items_count': total_items_count,
                'low_stock_count': calculated_low_count,
                'out_of_stock_count': calculated_out_count,
                'adequate_stock_count': calculated_adequate_count
            })
            return render_template('admin/reports/general_inventory_report.html', **render_context)

    except Exception as e:
        logger.error(f"Error generating report (type={report_type}): {e}", exc_info=True)
        flash(f"Lỗi khi tạo báo cáo '{report_type}'. Chi tiết: {e}", "danger")
        return redirect(url_for('admin.dashboard'))

    logger.warning(f"Invalid report type requested: {report_type}")
    flash("Loại báo cáo không hợp lệ.", "warning")
    return redirect(url_for('admin.reports', type='sales'))



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
    per_page = 20 # Số lượng tin nhắn mỗi trang
    show_filter = request.args.get('filter', 'all') # Lọc theo trạng thái đọc

    query = ContactMessage.query
    if show_filter == 'unread':
        query = query.filter_by(is_read=False)
    elif show_filter == 'read':
        query = query.filter_by(is_read=True)

    messages_pagination = query.order_by(ContactMessage.created_at.desc())\
                                            .paginate(page=page, per_page=per_page, error_out=False)
    messages = messages_pagination.items
    return render_template('admin/messages.html',
                           messages=messages,
                           pagination=messages_pagination,
                           current_filter=show_filter,
                           title="Hộp thư Liên hệ")


@admin_bp.route('/messages/<int:message_id>')
@login_required
@admin_required
def view_message(message_id):
    message = ContactMessage.query.get_or_404(message_id)
    if not message.is_read:
        message.is_read = True
        try:
            db.session.commit()
            # Không cần flash khi chỉ xem và đánh dấu đã đọc
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Lỗi cập nhật trạng thái đọc message ID {message_id}: {e}", exc_info=True)
            flash("Lỗi khi đánh dấu tin nhắn đã đọc.", "danger")
    return render_template('admin/message_detail.html', message=message, title="Chi tiết Tin nhắn")


@admin_bp.route('/messages/delete/<int:message_id>', methods=['POST'])
@login_required
@admin_required
def delete_message(message_id):
    message = ContactMessage.query.get_or_404(message_id)
    try:
        db.session.delete(message)
        db.session.commit()
        flash("Đã xóa tin nhắn.", "success")
    except Exception as e:
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
        # Tạo nội dung TEXT bằng AI (giữ nguyên)
        ai_content = generate_interesting_story() # Đảm bảo hàm này vẫn tồn tại và hoạt động
        if not ai_content:
            flash("AI không thể tạo nội dung. Thử lại?", "danger")
            return redirect(url_for('admin.interesting_stories'))
        # ... (phần tạo title và lưu story như cũ) ...
        words = ai_content.split()
        default_title = " ".join(words[:6]) + "..." if len(words) > 6 else ai_content[:50]+"..."
        new_story = InterestingStory(title=default_title, content=ai_content, status='draft', generated_by_ai=True)
        db.session.add(new_story)
        db.session.commit()
        flash("Đã tạo câu chuyện nháp bằng AI.", "success")
        # Chuyển đến trang edit để người dùng xem lại và **TẢI ẢNH LÊN**
        return redirect(url_for('admin.edit_story', story_id=new_story.id))
    except Exception as e:
        # ... (xử lý lỗi như cũ) ...
        db.session.rollback()
        current_app.logger.error(f"Lỗi tạo story: {e}", exc_info=True)
        flash(f"Lỗi tạo câu chuyện: {e}", "danger")
        return redirect(url_for('admin.interesting_stories'))

@admin_bp.route('/interesting-stories/edit/<int:story_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_story(story_id):
    """Chỉnh sửa câu chuyện thú vị và xử lý upload ảnh."""
    story = InterestingStory.query.get_or_404(story_id)
    form = InterestingStoryForm(obj=story) # Load dữ liệu vào form

    # -- KHÔNG load image_url vào form nữa vì dùng FileField --

    if form.validate_on_submit():
        old_image_relative_path = story.image_url # Lưu lại URL cũ
        image_file = form.image_file.data # Lấy file từ form
        new_image_relative_path = old_image_relative_path # Mặc định giữ ảnh cũ

        if image_file: # Nếu có file mới được upload
            saved_path = save_story_image(image_file) # Lưu ảnh mới
            if saved_path:
                new_image_relative_path = saved_path # Cập nhật đường dẫn mới
                # Xóa ảnh cũ (nếu có và nếu khác ảnh mới) sau khi commit thành công
            else:
                # Nếu lưu file lỗi, flash message và không thay đổi ảnh
                flash("Lưu ảnh mới thất bại. Ảnh minh họa không được thay đổi.", "warning")
                new_image_relative_path = old_image_relative_path

        try:
            story.title = form.title.data
            story.content = form.content.data
            story.image_url = new_image_relative_path # Cập nhật URL mới (hoặc cũ/None)
            story.updated_at = datetime.utcnow()
            # Không cần đánh dấu lại generated_by_ai vì có thể admin chỉ sửa text
            db.session.commit()

            # ---- XÓA ẢNH CŨ (NẾU CẦN) SAU KHI COMMIT THÀNH CÔNG ----
            if image_file and new_image_relative_path != old_image_relative_path and old_image_relative_path:
                delete_file(old_image_relative_path) # Gọi hàm xóa file từ utils
            # --------------------------------------------------------

            flash("Đã cập nhật câu chuyện thành công.", "success")
            return redirect(url_for('admin.interesting_stories'))
        except Exception as e:
            db.session.rollback()
            # Xóa ảnh vừa upload nếu lưu DB bị lỗi
            if image_file and new_image_relative_path != old_image_relative_path:
                 delete_file(new_image_relative_path) # Xóa file vừa upload lỗi
                 flash("Ảnh vừa tải lên đã bị xóa do lỗi cập nhật câu chuyện.", "warning")

            current_app.logger.error(f"Error editing story {story_id}: {e}", exc_info=True)
            flash(f"Lỗi khi cập nhật câu chuyện: {e}", "danger")
            # Render lại form với lỗi nếu có

    elif request.method == 'POST': # Trường hợp POST nhưng form không valid
        flash("Thông tin nhập không hợp lệ, vui lòng kiểm tra lại.", "warning")

    # Lấy URL đầy đủ để hiển thị ảnh hiện tại trong template
    current_image_full_url = None
    if story.image_url:
        try:
            # Sử dụng url_for để tạo URL từ thư mục static
            current_image_full_url = url_for('static', filename=story.image_url, _external=False)
        except RuntimeError: # Nếu chạy ngoài app context
            current_image_full_url = f"/static/{story.image_url}" # Tạo thủ công
        except Exception as e_url:
            current_app.logger.error(f"Error generating URL for image '{story.image_url}': {e_url}")


    return render_template(
        'admin/interesting_story_form.html',
        form=form,
        story=story,
        title="Chỉnh sửa câu chuyện",
        current_image_url=current_image_full_url # Truyền URL đầy đủ vào template
    )

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
    # ... (logic gọi AI tạo text giữ nguyên, trả về JSON new_content) ...
    current_app.logger.info(f"Received AI rewrite request for story ID: {story_id}")
    try:
        ai_content = generate_interesting_story()
        if not ai_content:
            current_app.logger.error(f"AI failed to generate rewrite for story ID: {story_id}")
            return jsonify({'success': False, 'message': 'AI không thể tạo nội dung mới vào lúc này.'}), 500
        current_app.logger.info(f"AI successfully generated rewrite for story ID: {story_id}")
        return jsonify({'success': True, 'new_content': ai_content})
    except Exception as e:
        current_app.logger.error(f"Error during AI rewrite for story {story_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Lỗi máy chủ khi yêu cầu viết lại: {str(e)}'}), 500

    except Exception as e:
        current_app.logger.error(f"Error during AI rewrite for story {story_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Lỗi máy chủ khi yêu cầu viết lại: {str(e)}'}), 500
# === KẾT THÚC ROUTE VIẾT LẠI ===

@admin_bp.route('/employees/send-reset-link/<int:employee_id>', methods=['POST'])
@login_required
@admin_required # Đảm bảo chỉ admin mới gửi được
def send_employee_reset_link(employee_id):
    """Gửi email chứa link reset mật khẩu cho một nhân viên cụ thể."""
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info(f"Admin {current_user.id} requested password reset link for employee ID {employee_id}")

    # Lấy thông tin employee và user liên quan
    employee = Employee.query.get_or_404(employee_id)
    user = User.query.get(employee.user_id)

    if not user:
        logger.error(f"User not found for Employee ID {employee_id} (User ID: {employee.user_id})")
        flash(f"Lỗi: Không tìm thấy tài khoản người dùng liên kết với nhân viên này.", "danger")
        # Redirect về trang edit hoặc danh sách
        referrer = request.referrer or url_for('admin.edit_employee', employee_id=employee_id)
        return redirect(referrer)

    # Kiểm tra xem user có email hợp lệ không
    if not user.email:
        logger.warning(f"Employee {employee_id} (User: {user.username}) does not have an email address.")
        flash(f"Nhân viên '{user.full_name}' không có địa chỉ email được lưu. Không thể gửi link reset.", "warning")
        referrer = request.referrer or url_for('admin.edit_employee', employee_id=employee_id)
        return redirect(referrer)

    # Gọi hàm gửi email (tái sử dụng hàm đã tạo)
    if send_reset_email(user, endpoint_name='admin.reset_password'):
        flash(f"Đã gửi link đặt lại mật khẩu đến email: {user.email}", "success")
    else:
        flash("Gửi email thất bại. Vui lòng kiểm tra cấu hình mail hoặc thử lại sau.", "danger")

    referrer = request.referrer or url_for('admin.edit_employee', employee_id=employee_id)
    return redirect(referrer)


@admin_bp.route('/promotions')
@login_required
@admin_required
def promotions():
    """Hiển thị danh sách các chương trình khuyến mãi."""
    logger = current_app.logger
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 15 # Hoặc lấy từ config
        # Thêm tìm kiếm nếu muốn
        search_term = request.args.get('q', '')
        query = Promotion.query

        if search_term:
            search_like = f"%{search_term}%"
            query = query.filter(
                db.or_(
                    Promotion.name.ilike(search_like),
                    Promotion.code.ilike(search_like),
                    Promotion.description.ilike(search_like)
                )
            )

        promotions_pagination = query.order_by(Promotion.end_date.desc(), Promotion.start_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        promotions = promotions_pagination.items
        logger.info(f"Displaying promotions page {page}. Found {promotions_pagination.total} total matching promotions.")
    except Exception as e:
        logger.error(f"Error fetching promotions: {e}", exc_info=True)
        promotions = []
        promotions_pagination = None
        flash("Lỗi khi tải danh sách khuyến mãi.", "danger")

    return render_template('admin/promotions.html', # <-- Tên template mới
                           promotions=promotions,
                           pagination=promotions_pagination,
                           q=search_term,
                           title="Quản lý Khuyến mãi")

@admin_bp.route('/promotions/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_promotion():
    """Thêm chương trình khuyến mãi mới."""
    logger = current_app.logger
    form = PromotionForm()
    if form.validate_on_submit():
        logger.info(f"Attempting to add new promotion: {form.name.data}")
        # Kiểm tra mã code đã tồn tại chưa (không phân biệt hoa thường)
        if form.code.data:
            existing_promo = Promotion.query.filter(func.lower(Promotion.code) == func.lower(form.code.data)).first()
            if existing_promo:
                flash(f'Mã khuyến mãi "{form.code.data}" đã tồn tại. Vui lòng chọn mã khác.', 'warning')
                # Render lại form với lỗi
                return render_template('admin/promotion_form.html', form=form, title="Thêm Khuyến mãi")

        # Kiểm tra logic discount (chỉ nên có 1 loại)
        if form.discount_percent.data and form.discount_amount.data:
            flash('Chỉ nên nhập Giảm giá theo % HOẶC số tiền cố định, không nhập cả hai.', 'warning')
            return render_template('admin/promotion_form.html', form=form, title="Thêm Khuyến mãi")
        if not form.discount_percent.data and not form.discount_amount.data:
            flash('Cần nhập Giảm giá theo % hoặc số tiền cố định.', 'warning')
            return render_template('admin/promotion_form.html', form=form, title="Thêm Khuyến mãi")
        # Kiểm tra ngày bắt đầu < ngày kết thúc
        if form.start_date.data and form.end_date.data and form.start_date.data > form.end_date.data:
            flash('Ngày bắt đầu không thể sau ngày kết thúc.', 'warning')
            return render_template('admin/promotion_form.html', form=form, title="Thêm Khuyến mãi")

        try:
            new_promo = Promotion(
                name=form.name.data,
                description=form.description.data,
                discount_percent=form.discount_percent.data,
                discount_amount=form.discount_amount.data,
                code=form.code.data.upper() if form.code.data else None, # Lưu code uppercase
                start_date=form.start_date.data,
                end_date=form.end_date.data,
                is_active=form.is_active.data
            )
            db.session.add(new_promo)
            db.session.commit()
            logger.info(f"Promotion '{new_promo.name}' (ID: {new_promo.id}) added successfully.")
            flash(f'Đã thêm khuyến mãi "{new_promo.name}" thành công!', 'success')
            return redirect(url_for('admin.promotions'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding promotion: {e}", exc_info=True)
            flash(f'Lỗi khi thêm khuyến mãi: {str(e)}', 'danger')

    elif request.method == 'POST':
        logger.warning(f"Add promotion form validation failed: {form.errors}")
        flash('Vui lòng kiểm tra lại các lỗi trong form.', 'danger')

    return render_template('admin/promotion_form.html', form=form, title="Thêm Khuyến mãi") # <-- Tên template mới

@admin_bp.route('/promotions/edit/<int:promotion_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_promotion(promotion_id):
    """Chỉnh sửa chương trình khuyến mãi."""
    logger = current_app.logger
    promo = Promotion.query.get_or_404(promotion_id)
    form = PromotionForm(obj=promo) # Load data vào form cho GET

    if form.validate_on_submit():
        logger.info(f"Attempting to edit promotion ID: {promotion_id}")
        new_code = form.code.data.upper().strip() if form.code.data else None

        # Kiểm tra code mới (nếu có thay đổi và không rỗng) có trùng với code khác không
        if new_code and new_code != promo.code: # Chỉ kiểm tra nếu code thay đổi
            existing_promo = Promotion.query.filter(
                func.lower(Promotion.code) == func.lower(new_code),
                Promotion.id != promotion_id # Loại trừ chính nó
            ).first()
            if existing_promo:
                flash(f'Mã khuyến mãi "{form.code.data}" đã được sử dụng bởi một chương trình khác.', 'warning')
                # Render lại form với lỗi
                return render_template('admin/promotion_form.html', form=form, title="Chỉnh sửa Khuyến mãi", promotion=promo)

        # Kiểm tra logic discount
        if form.discount_percent.data and form.discount_amount.data:
            flash('Chỉ nên nhập Giảm giá theo % HOẶC số tiền cố định, không nhập cả hai.', 'warning')
            return render_template('admin/promotion_form.html', form=form, title="Chỉnh sửa Khuyến mãi", promotion=promo)
        if not form.discount_percent.data and not form.discount_amount.data:
             flash('Cần nhập Giảm giá theo % hoặc số tiền cố định.', 'warning')
             return render_template('admin/promotion_form.html', form=form, title="Chỉnh sửa Khuyến mãi", promotion=promo)
        # Kiểm tra ngày
        if form.start_date.data and form.end_date.data and form.start_date.data > form.end_date.data:
             flash('Ngày bắt đầu không thể sau ngày kết thúc.', 'warning')
             return render_template('admin/promotion_form.html', form=form, title="Chỉnh sửa Khuyến mãi", promotion=promo)

        try:
            # Cập nhật các trường
            promo.name = form.name.data
            promo.description = form.description.data
            promo.discount_percent = form.discount_percent.data
            promo.discount_amount = form.discount_amount.data
            promo.code = new_code
            promo.start_date = form.start_date.data
            promo.end_date = form.end_date.data
            promo.is_active = form.is_active.data

            db.session.commit()
            logger.info(f"Promotion ID {promotion_id} edited successfully.")
            flash(f'Đã cập nhật khuyến mãi "{promo.name}" thành công!', 'success')
            return redirect(url_for('admin.promotions'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error editing promotion {promotion_id}: {e}", exc_info=True)
            flash(f'Lỗi khi cập nhật khuyến mãi: {str(e)}', 'danger')

    elif request.method == 'POST':
         logger.warning(f"Edit promotion form validation failed: {form.errors}")
         flash('Vui lòng kiểm tra lại các lỗi trong form.', 'danger')

    return render_template('admin/promotion_form.html', form=form, title="Chỉnh sửa Khuyến mãi", promotion=promo) # <-- Tên template mới

@admin_bp.route('/promotions/delete/<int:promotion_id>', methods=['POST'])
@login_required
@admin_required
def delete_promotion(promotion_id):
    """Xóa chương trình khuyến mãi."""
    logger = current_app.logger
    promo = Promotion.query.get_or_404(promotion_id)
    promo_name = promo.name # Lưu lại tên để hiển thị message

    # Cân nhắc: Kiểm tra xem KM có đang được áp dụng cho đơn hàng nào không?
    # if Order.query.filter_by(promotion_id=promotion_id).first():
    #    flash(f'Không thể xóa khuyến mãi "{promo_name}" vì đang được áp dụng.', 'danger')
    #    return redirect(url_for('admin.promotions'))

    try:
        db.session.delete(promo)
        db.session.commit()
        logger.info(f"Promotion '{promo_name}' (ID: {promotion_id}) deleted successfully.")
        flash(f'Đã xóa khuyến mãi "{promo_name}".', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting promotion {promotion_id}: {e}", exc_info=True)
        flash(f'Lỗi khi xóa khuyến mãi: {str(e)}', 'danger')

    return redirect(url_for('admin.promotions'))

@admin_bp.route('/promotions/toggle/<int:promotion_id>', methods=['POST'])
@login_required
@admin_required
def toggle_promotion_active(promotion_id):
    """Bật/Tắt trạng thái active của khuyến mãi."""
    logger = current_app.logger
    promo = Promotion.query.get_or_404(promotion_id)
    try:
        promo.is_active = not promo.is_active
        status_text = "kích hoạt" if promo.is_active else "vô hiệu hóa"
        db.session.commit()
        logger.info(f"Promotion '{promo.name}' (ID: {promotion_id}) status toggled to {promo.is_active}.")
        flash(f'Đã {status_text} khuyến mãi "{promo.name}".', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling promotion status {promotion_id}: {e}", exc_info=True)
        flash(f'Lỗi khi thay đổi trạng thái: {str(e)}', 'danger')
    return redirect(url_for('admin.promotions'))


# ===== KẾT THÚC QUẢN LÝ KHUYẾN MÃI =====

@admin_bp.route('/locations')
@login_required
@admin_required
def locations():
    """Hiển thị danh sách địa điểm."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '')
    per_page = 15 # Hoặc lấy từ config

    query = Location.query

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Location.name.ilike(search_term),
                Location.address.ilike(search_term),
                Location.phone.ilike(search_term)
            )
        )

    locations_pagination = query.order_by(Location.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
    locations = locations_pagination.items

    return render_template('admin/locations.html',
                           locations=locations,
                           pagination=locations_pagination,
                           search_term=search,
                           title="Quản lý Địa điểm")

@admin_bp.route('/locations/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_location():
    """Thêm địa điểm mới."""
    form = LocationForm()
    if form.validate_on_submit():
        try:
            new_location = Location(
                name=form.name.data,
                address=form.address.data,
                phone=form.phone.data if form.phone.data else None,
                hours=form.hours.data if form.hours.data else None,
                latitude=form.latitude.data if form.latitude.data is not None else None,
                longitude=form.longitude.data if form.longitude.data is not None else None,
                map_embed_url=form.map_embed_url.data if form.map_embed_url.data else None,
                is_active=form.is_active.data
            )
            db.session.add(new_location)
            db.session.commit()
            flash(f'Đã thêm địa điểm "{new_location.name}" thành công!', 'success')
            return redirect(url_for('admin.locations'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Lỗi khi thêm địa điểm: {e}", exc_info=True)
            flash(f'Lỗi khi thêm địa điểm: {str(e)}', 'danger')
    elif request.method == 'POST':
        flash('Thông tin nhập không hợp lệ, vui lòng kiểm tra lại.', 'warning')
    return render_template('admin/location_form.html', form=form, title="Thêm Địa điểm", legend="Thêm Địa điểm Mới")

@admin_bp.route('/locations/edit/<int:location_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_location(location_id):
    """Chỉnh sửa địa điểm."""
    location = Location.query.get_or_404(location_id)
    form = LocationForm(obj=location) # Load data cho GET
    if form.validate_on_submit():
        try:
            location.name = form.name.data
            location.address = form.address.data
            location.phone = form.phone.data if form.phone.data else None
            location.hours = form.hours.data if form.hours.data else None
            location.latitude = form.latitude.data if form.latitude.data is not None else None
            location.longitude = form.longitude.data if form.longitude.data is not None else None
            location.map_embed_url = form.map_embed_url.data if form.map_embed_url.data else None
            location.is_active = form.is_active.data
            # updated_at sẽ tự cập nhật nếu có trigger hoặc cần set thủ công:
            location.updated_at = datetime.utcnow()
            db.session.commit()
            flash(f'Đã cập nhật địa điểm "{location.name}" thành công!', 'success')
            return redirect(url_for('admin.locations'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Lỗi khi cập nhật địa điểm {location_id}: {e}", exc_info=True)
            flash(f'Lỗi khi cập nhật địa điểm: {str(e)}', 'danger')
    elif request.method == 'POST':
        flash('Thông tin nhập không hợp lệ, vui lòng kiểm tra lại.', 'warning')
    return render_template('admin/location_form.html', form=form, title="Chỉnh sửa Địa điểm", legend=f"Chỉnh sửa: {location.name}", location=location)

@admin_bp.route('/locations/delete/<int:location_id>', methods=['POST'])
@login_required
@admin_required
def delete_location(location_id):
    """Xóa địa điểm."""
    location = Location.query.get_or_404(location_id)
    location_name = location.name # Lưu tên trước khi xóa
    try:
        db.session.delete(location)
        db.session.commit()
        flash(f'Đã xóa địa điểm "{location_name}"!', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Lỗi khi xóa địa điểm {location_id}: {e}", exc_info=True)
        flash(f'Lỗi khi xóa địa điểm: {str(e)}', 'danger')
    return redirect(url_for('admin.locations'))

@admin_bp.route('/reviews')
@login_required
@admin_required
def manage_reviews():
    """Hiển thị danh sách đánh giá để quản lý."""
    logger = current_app.logger
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '').strip()
    filter_toxic_param = request.args.get('filter_toxic', '') # toxic, clean, or empty ''
    per_page = 20

    base_query = Review.query.options(
        joinedload(Review.product), # Tải thông tin sản phẩm
        joinedload(Review.author)   # Tải thông tin người đánh giá
    )

    # Lọc theo nội dung/tên SP/tên user
    if search_query:
        search_term = f"%{search_query}%"
        base_query = base_query.filter(
            db.or_(
                Review.content.ilike(search_term),
                Review.original_content.ilike(search_term),
                Product.name.ilike(search_term), # Cần join với Product
                User.username.ilike(search_term), # Cần join với User
                User.email.ilike(search_term)
            )
        )
        # Join các bảng cần thiết cho search
        base_query = base_query.outerjoin(Product, Review.product_id == Product.id)\
                               .outerjoin(User, Review.user_id == User.id)


    # Lọc theo trạng thái AI đã lọc
    if filter_toxic_param == 'toxic':
         base_query = base_query.filter(Review.is_toxic_guess == True)
    elif filter_toxic_param == 'clean':
        base_query = base_query.filter(Review.is_toxic_guess != True) # != True bao gồm False và NULL

    # Sắp xếp: Ưu tiên review bị lọc lên đầu, sau đó đến mới nhất
    reviews_pagination = base_query.order_by(
        Review.is_toxic_guess.desc().nullslast(), # True (toxic) trước
        Review.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/reviews.html',
                           reviews_page=reviews_pagination, # Truyền cả object pagination
                           filter_toxic=filter_toxic_param, # Truyền bộ lọc hiện tại
                           title="Quản lý Đánh giá")

@admin_bp.route('/reviews/delete/<int:review_id>', methods=['POST'])
@login_required
@admin_required
def delete_review(review_id):
    """Xóa một đánh giá."""
    review = Review.query.get_or_404(review_id)
    try:
        db.session.delete(review)
        db.session.commit()
        flash("Đã xóa đánh giá thành công.", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting review ID {review_id}: {e}", exc_info=True)
        flash(f"Lỗi khi xóa đánh giá: {str(e)}", "danger")
    return redirect(request.referrer or url_for('admin.manage_reviews'))


@admin_bp.route('/users/toggle-comment-ban/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_comment_ban(user_id):
    """Chặn hoặc bỏ chặn quyền bình luận của người dùng."""
    user = User.query.get_or_404(user_id)
    if user.is_admin: # Không cho chặn admin khác
         flash('Không thể chặn tài khoản quản trị viên.', 'danger')
         return redirect(request.referrer or url_for('admin.manage_reviews'))

    try:
        action_text = "Bỏ chặn" if user.is_comment_banned else "Chặn"
        user.is_comment_banned = not user.is_comment_banned
        # Tùy chọn: Reset warning count khi bỏ chặn?
        # if not user.is_comment_banned:
        #     user.review_warning_count = 0
        db.session.commit()
        flash(f"Đã {action_text} quyền bình luận của người dùng {user.username}.", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error toggling comment ban for user {user_id}: {e}", exc_info=True)
        flash(f"Lỗi khi {action_text.lower()} người dùng: {str(e)}", "danger")
    return redirect(request.referrer or url_for('admin.manage_reviews'))

@admin_bp.route('/reviews/analyze-old')
@login_required
@admin_required
def analyze_old_reviews():
    logger = current_app.logger
    logger.info("Starting bulk analysis of old reviews...")
    try:
        # Tìm các review chưa có sentiment_label
        reviews_to_analyze = Review.query.filter(Review.sentiment_label == None).limit(200).all() # Phân tích từng lô nhỏ
        if not reviews_to_analyze:
            flash("Tất cả các đánh giá đã được phân tích sentiment.", "info")
            return redirect(url_for('admin.manage_reviews'))

        count = 0
        for review in reviews_to_analyze:
            if review.content and review.content.strip(): # Chỉ phân tích nếu có nội dung
                analysis = analyze_review_sentiment(review.content)
                review.sentiment_label = analysis.get('sentiment_label')
                review.sentiment_score = analysis.get('sentiment_score')
                review.is_toxic_guess = analysis.get('is_toxic') # Cũng lưu lại kết quả toxic
                db.session.add(review)
                count += 1

        db.session.commit()
        logger.info(f"Analyzed and updated sentiment for {count} reviews.")
        flash(f"Đã cập nhật sentiment cho {count} đánh giá.", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error during bulk sentiment analysis: {e}", exc_info=True)
        flash(f"Lỗi khi phân tích sentiment hàng loạt: {e}", "danger")

    return redirect(url_for('admin.manage_reviews'))

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """Hiển thị danh sách khách hàng."""
    logger = current_app.logger
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    # Thêm bộ lọc theo trạng thái cấm bình luận
    ban_filter = request.args.get('banned', type=int) # 0: not banned, 1: banned, None: all
    per_page = 20

    query = User.query.filter(
        User.is_admin == False,
        User.is_staff == False # Chỉ lấy khách hàng
    )

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(search_term),
                User.email.ilike(search_term),
                User.phone.ilike(search_term),
                (User.first_name + ' ' + User.last_name).ilike(search_term)
            )
        )

    # Áp dụng bộ lọc cấm
    if ban_filter == 1:
        query = query.filter(User.is_comment_banned == True)
    elif ban_filter == 0:
        query = query.filter(User.is_comment_banned == False)

    users_pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    users = users_pagination.items

    return render_template('admin/users.html',
                           users=users,
                           pagination=users_pagination,
                           search_term=search,
                           ban_filter=ban_filter, # Truyền trạng thái lọc vào template
                           title="Quản lý Khách hàng")


@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    """Hiển thị chi tiết một khách hàng."""
    user = User.query.filter(
        User.id == user_id,
        User.is_admin == False,
        User.is_staff == False # Chỉ xem chi tiết khách hàng
    ).first_or_404()

    # Lấy thêm thông tin liên quan (ví dụ: 5 đơn hàng gần nhất)
    recent_orders = Order.query.filter_by(user_id=user_id)\
                                .order_by(Order.created_at.desc())\
                                .limit(5).all()
    # Lấy 5 đánh giá gần nhất (nếu cần)
    recent_reviews = Review.query.filter_by(user_id=user_id)\
                                .order_by(Review.created_at.desc())\
                                .limit(5).all()

    return render_template('admin/user_detail.html',
                           user=user,
                           recent_orders=recent_orders,
                           recent_reviews=recent_reviews,
                           title=f"Chi tiết: {user.username}")

@admin_bp.route('/users/toggle-ban/<int:user_id>', methods=['POST'])
@login_required
@admin_required
# ===> ĐỔI TÊN HÀM TỪ toggle_comment_ban THÀNH toggle_user_comment_ban <====
def toggle_user_comment_ban(user_id):
    """Chặn hoặc bỏ chặn quyền bình luận của người dùng."""
    logger = current_app.logger
    user = User.query.get_or_404(user_id)

    # Kiểm tra không cho thao tác trên admin/staff
    if user.is_admin or user.is_staff:
        flash("Không thể thay đổi trạng thái cấm cho quản trị viên hoặc nhân viên.", 'danger')
        return redirect(request.referrer or url_for('admin.users'))

    try:
        action_text = "Bỏ chặn" if user.is_comment_banned else "Chặn"
        user.is_comment_banned = not user.is_comment_banned
        # Tùy chọn: Reset warning count khi bỏ chặn
        if not user.is_comment_banned:
             user.review_warning_count = 0
             action_text += " và reset cảnh báo"
        db.session.commit()
        flash(f"Đã {action_text} quyền bình luận của người dùng '{user.username}'.", 'success')
        logger.info(f"Admin {current_user.id} {action_text} comment ban for user {user.id} ('{user.username}')")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling comment ban for user {user_id}: {e}", exc_info=True)
        flash(f"Lỗi khi {action_text.lower()} người dùng: {str(e)}", "danger")
    # Nên redirect về trang chi tiết user nếu đến từ đó, hoặc về trang list
    if request.referrer and f'/users/{user_id}' in request.referrer:
        return redirect(url_for('admin.user_detail', user_id=user_id))
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/send-reset/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def send_user_reset_link(user_id):
    """Gửi email reset mật khẩu cho khách hàng từ admin."""
    logger = current_app.logger
    user = User.query.get_or_404(user_id)

    # Kiểm tra không gửi cho admin/staff (trừ khi có yêu cầu đặc biệt)
    if user.is_admin or user.is_staff:
         flash("Chức năng này chỉ dành cho tài khoản khách hàng.", 'warning')
         return redirect(request.referrer or url_for('admin.users'))

    if not user.email:
        flash(f"Người dùng '{user.username}' không có địa chỉ email để gửi link.", "warning")
        return redirect(request.referrer or url_for('admin.user_detail', user_id=user_id))

    if send_reset_email(user):
        flash(f"Đã gửi link đặt lại mật khẩu đến email: {user.email}", "success")
        logger.info(f"Admin {current_user.id} sent password reset link to user {user.id} ('{user.username}')")
    else:
        flash("Gửi email thất bại. Vui lòng kiểm tra cấu hình mail hoặc thử lại sau.", "danger")

    return redirect(request.referrer or url_for('admin.user_detail', user_id=user_id))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def save_product_image(file_storage):
    """Lưu ảnh sản phẩm và trả về URL tương đối."""
    if not file_storage or file_storage.filename == '':
        return None
    if allowed_file(file_storage.filename):
        filename = secure_filename(file_storage.filename)
        # Tạo tên file duy nhất để tránh trùng lặp
        ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"product_{uuid.uuid4().hex[:10]}.{ext}"

        # Xác định đường dẫn lưu file tuyệt đối
        products_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'products')
        save_path = os.path.join(products_folder, unique_filename)

        # Đảm bảo thư mục tồn tại (dù đã tạo trong app.py)
        os.makedirs(products_folder, exist_ok=True)

        try:
            file_storage.save(save_path)
            # Tạo URL tương đối để lưu vào DB (ví dụ: 'uploads/products/product_xyz.jpg')
            # Giả sử UPLOAD_FOLDER là 'static/uploads'
            relative_url = os.path.join('uploads/products', unique_filename).replace(os.path.sep, '/')
            current_app.logger.info(f"Saved product image to: {save_path}, Relative URL: {relative_url}")
            # Trả về đường dẫn tương đối từ thư mục static
            return relative_url
        except Exception as e:
            current_app.logger.error(f"Error saving uploaded file '{unique_filename}': {e}", exc_info=True)
            return None
    else:
        current_app.logger.warning(f"Upload attempt with disallowed file type: {file_storage.filename}")
        flash('Loại file ảnh không hợp lệ!', 'danger')
        return None
    return None

def delete_old_image(image_url_relative):
    """Xóa file ảnh cũ nếu tồn tại."""
    if not image_url_relative:
        return False
    try:
        # Xây dựng đường dẫn file tuyệt đối từ URL tương đối
        file_path = os.path.join(current_app.static_folder, image_url_relative)
        if os.path.exists(file_path):
            os.remove(file_path)
            current_app.logger.info(f"Deleted old image: {file_path}")
            return True
    except Exception as e:
        current_app.logger.error(f"Error deleting old image '{image_url_relative}': {e}", exc_info=True)
    return False

@admin_bp.route('/products/export/csv')
@login_required
@admin_required
def export_products_csv():
    """Xuất danh sách sản phẩm ra file CSV."""
    logger = current_app.logger
    logger.info("Initiating CSV export for products...")
    try:
        # Query dữ liệu - KHÔNG PHÂN TRANG, LẤY TẤT CẢ
        # Sử dụng joinedload để tải category cùng lúc, tránh N+1 query
        products_to_export = Product.query.options(
            joinedload(Product.category), # Tải thông tin Category
            joinedload(Product.inventory) # Tải thông tin InventoryItem
        ).order_by(Product.category_id, Product.name).all()

        if not products_to_export:
            flash("Không có sản phẩm nào để xuất.", "warning")
            return redirect(url_for('admin.menu_management'))

        # Tạo file CSV trong bộ nhớ
        output = io.StringIO()
        writer = csv.writer(output)

        # Viết header
        header = [
            'ID', 'Tên Sản Phẩm', 'Mô Tả', 'Giá', 'Danh Mục', 'Có Sẵn',
            'Nổi Bật', 'URL Ảnh', 'Tồn Kho', 'Tồn Kho Tối Thiểu',
            'Ngày Tạo', 'Ngày Cập Nhật'
        ]
        writer.writerow(header)

        # Viết dữ liệu
        for p in products_to_export:
            writer.writerow([
                p.id,
                p.name,
                p.description or '',
                p.price,
                p.category.name if p.category else 'N/A',
                'Yes' if p.is_available else 'No',
                'Yes' if p.is_featured else 'No',
                p.image_url or '',
                p.inventory.quantity if p.inventory else 0,
                p.inventory.min_quantity if p.inventory else 'N/A',
                p.created_at.strftime('%Y-%m-%d %H:%M:%S') if p.created_at else '',
                p.updated_at.strftime('%Y-%m-%d %H:%M:%S') if p.updated_at else ''
            ])

        # Chuẩn bị Response để tải file
        csv_data = output.getvalue().encode('utf-8-sig') # Encode UTF-8 with BOM
        output.close()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dragoncoffee_products_{timestamp}.csv"

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=\"{filename}\""}
        )

    except Exception as e:
        logger.error(f"Error exporting products to CSV: {e}", exc_info=True)
        flash("Đã xảy ra lỗi khi xuất file sản phẩm.", "danger")
        return redirect(url_for('admin.menu_management'))
    
@admin_bp.route('/orders/export/csv')
@login_required
@admin_required
def export_orders_csv():
    """Xuất danh sách đơn hàng ra file CSV."""
    logger = current_app.logger
    logger.info("Initiating CSV export for orders...")
    # Lấy filters từ request args (giống trang list orders)
    status_filter = request.args.get('status') # Giữ lại filter này
    search_term = request.args.get('q', '')   # Đổi tên arg thành 'q' cho khớp

    try:
        query = Order.query.options(
            joinedload(Order.customer) # Tải user để lấy tên KH
        )
        # Apply filters tương tự như route admin.orders
        if status_filter:
            query = query.filter(Order.status == status_filter)
        if search_term:
            search_like = f"%{search_term}%"
            # ===> **SỬA KHỐI or_() Ở ĐÂY** <===
            query = query.outerjoin(User, Order.user_id == User.id).filter(
                or_( # Sử dụng or_ (hoặc db.or_)
                    Order.order_number.ilike(search_like),
                    func.lower(User.first_name + ' ' + User.last_name).contains(func.lower(search_term)),
                    User.email.ilike(search_like),
                    User.phone.ilike(search_like),
                    Order.contact_phone.ilike(search_like)
                    # BỎ comment và dấu ngoặc đóng thừa ở đây
                )
            )
            # ====> **KẾT THÚC SỬA** <====

        orders_to_export = query.order_by(Order.created_at.desc()).all()

        if not orders_to_export:
            flash("Không có đơn hàng nào để xuất (theo bộ lọc hiện tại).", "warning")
            return redirect(url_for('admin.orders', status=status_filter, q=search_term))

        output = io.StringIO()
        writer = csv.writer(output)
        header = [ # ... (header giữ nguyên) ...
            'Order ID', 'Order Number', 'User ID', 'Customer Name', 'Contact Phone', 'Email',
            'Order Date', 'Order Type', 'Status', 'Payment Method', 'Payment Status',
            'Total Amount (Base)', 'Discount', 'Final Amount', 'Notes', 'Address'
        ]
        writer.writerow(header)

        for o in orders_to_export:
            # ... (phần ghi dữ liệu giữ nguyên) ...
            customer_name = o.customer.full_name if o.customer else ''
            customer_email = o.customer.email if o.customer else ''
            writer.writerow([
                o.id, o.order_number, o.user_id or '', customer_name, o.contact_phone or '', customer_email,
                o.created_at.strftime('%Y-%m-%d %H:%M:%S') if o.created_at else '',
                o.order_type, o.status, o.payment_method or '', o.payment_status or '',
                o.total_amount or 0.0, o.discount_applied or 0.0, o.final_amount or 0.0,
                o.notes or '', o.address or ''
            ])

        csv_data = output.getvalue().encode('utf-8-sig')
        output.close()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dragoncoffee_orders_{timestamp}.csv"
        return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename=\"{filename}\""})

    except Exception as e:
        logger.error(f"Error exporting orders to CSV: {e}", exc_info=True)
        flash("Đã xảy ra lỗi khi xuất file đơn hàng.", "danger")
        return redirect(url_for('admin.orders', status=status_filter, q=search_term))
    
@admin_bp.context_processor
def inject_admin_notifications():
    """Injects notification counts into admin templates."""
    if current_user.is_authenticated and (current_user.is_admin or current_user.is_staff):
        try:
            # Đếm đơn hàng chờ xử lý
            new_order_count = Order.query.filter(Order.status == 'pending').count()

            # Hoặc nếu dùng admin_viewed:
            # new_order_count = Order.query.filter_by(admin_viewed=False).count()

            # Đếm tin nhắn chưa đọc
            unread_message_count = ContactMessage.query.filter_by(is_read=False).count()

            # Đếm tồn kho thấp + hết hàng
            low_stock_count = InventoryItem.query.filter(
                InventoryItem.quantity > 0, InventoryItem.quantity <= InventoryItem.min_quantity
            ).count()
            out_of_stock_count = InventoryItem.query.filter(InventoryItem.quantity <= 0).count()
            inventory_alert_count = low_stock_count + out_of_stock_count

            # Đếm review chờ duyệt
            pending_review_count = Review.query.filter_by(status='pending').count()

            return dict(
                new_order_count=new_order_count,
                unread_message_count=unread_message_count,
                inventory_alert_count=inventory_alert_count,
                pending_review_count=pending_review_count
                # Bạn có thể trả về low_stock_count, out_of_stock_count riêng nếu muốn hiển thị chi tiết
            )
        except Exception as e:
            # Ghi log nhưng không làm crash app
            if current_app: current_app.logger.error(f"Error injecting admin notifications: {e}", exc_info=False)
            return {} # Trả về dict rỗng
    return {} # Không có gì cho người dùng chưa đăng nhập hoặc không phải admin/staff

@admin_bp.route('/reviews/update-status/<int:review_id>', methods=['POST'])
@login_required
@admin_required
def update_review_status(review_id):
    """Duyệt hoặc Từ chối một đánh giá."""
    review = Review.query.get_or_404(review_id)
    new_status = request.form.get('status') # Lấy trạng thái mới từ form ('approved', 'rejected')
    logger = current_app.logger

    if new_status not in ['approved', 'rejected']:
        flash("Trạng thái cập nhật không hợp lệ.", 'danger')
        return redirect(request.referrer or url_for('admin.manage_reviews'))

    try:
        original_status = review.status
        review.status = new_status
        # (Tùy chọn) Có thể thêm ghi chú lý do từ chối vào review nếu cần
        # if new_status == 'rejected': review.admin_notes = "Lý do..."
        db.session.commit()
        action_text = "Duyệt" if new_status == 'approved' else "Từ chối"
        flash(f"Đã {action_text.lower()} đánh giá ID {review.id}.", 'success')
        logger.info(f"Admin {current_user.id} updated review {review.id} status from '{original_status}' to '{new_status}'")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating review status for ID {review_id}: {e}", exc_info=True)
        flash(f"Lỗi khi cập nhật trạng thái đánh giá: {str(e)}", 'danger')

    return redirect(request.referrer or url_for('admin.manage_reviews'))

@admin_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard')) # Chuyển về dashboard admin nếu đã đăng nhập
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        logger = current_app.logger
        user = User.query.filter(func.lower(User.email) == func.lower(form.email.data)).first()
        # *** QUAN TRỌNG: Kiểm tra là Admin hoặc Staff ***
        if user and (user.is_admin or user.is_staff):
             logger.info(f"Admin/Staff forgot password request for user {user.id} ({user.email})")
             # Gọi hàm gửi email với endpoint admin
             if send_reset_email(user, endpoint_name='admin.reset_password'):
                 flash('Một email hướng dẫn đặt lại mật khẩu đã được gửi.', 'info')
             else:
                flash('Lỗi khi gửi email. Vui lòng thử lại hoặc liên hệ hỗ trợ kỹ thuật.', 'danger')
             # Luôn redirect về login admin
             return redirect(url_for('admin.login'))
        else:
            # Nếu không tìm thấy user hoặc không phải admin/staff -> KHÔNG GỬI EMAIL
            # Vẫn hiển thị thông báo chung chung để tránh dò quét email
             logger.warning(f"Forgot password attempt for non-staff/admin or non-existent email: {form.email.data}")
             flash('Nếu địa chỉ email của bạn hợp lệ và thuộc tài khoản nhân viên/admin, bạn sẽ nhận được email.', 'info')
             return redirect(url_for('admin.login'))

    return render_template('admin/forgot_password.html', title='Quên Mật khẩu', form=form)

@admin_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
    logger = current_app.logger

    # Xác thực token VÀ kiểm tra quyền admin/staff
    user = User.verify_reset_token(token) # Dùng lại hàm verify token cũ

    # *** QUAN TRỌNG: Kiểm tra quyền sau khi xác thực token ***
    if user is None or not (user.is_admin or user.is_staff):
        flash('Link đặt lại mật khẩu không hợp lệ, đã hết hạn hoặc không dành cho tài khoản này.', 'warning')
        logger.warning(f"Invalid/Expired token or non-staff/admin access attempt for reset token: {token[:10]}...")
        return redirect(url_for('admin.forgot_password')) # Quay về form yêu cầu reset của admin

    # Nếu token và quyền hợp lệ, hiển thị form
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        try:
            db.session.commit()
            flash('Mật khẩu của bạn đã được cập nhật! Bây giờ bạn có thể đăng nhập bằng mật khẩu mới.', 'success')
            logger.info(f"Password reset successfully for user {user.id} via admin reset flow.")
            return redirect(url_for('admin.login')) # Chuyển về trang login admin
        except Exception as e:
            db.session.rollback()
            flash(f'Lỗi khi cập nhật mật khẩu: {e}', 'danger')
            logger.error(f"Error resetting password via admin flow for user ID {user.id}: {e}", exc_info=True)

    return render_template('admin/reset_password.html', title='Đặt Lại Mật khẩu', form=form, token=token)

@admin_bp.route('/api/search-orders')
@login_required
@admin_required # Hoặc @staff_required tùy quyền
def api_search_orders():
    """API endpoint để tìm kiếm và lọc đơn hàng cho Admin (trả về HTML)."""
    logger = current_app.logger
    try:
        query = request.args.get('q', '')
        status = request.args.get('status', '')
        # page = request.args.get('page', 1, type=int) # BỎ PHÂN TRANG Ở ĐÂY VÌ JS CHƯA XỬ LÝ
        # per_page = 100 # Lấy nhiều KQ một lúc cho tìm kiếm động

        order_query = Order.query.options(
            joinedload(Order.customer) # Tải sẵn thông tin khách hàng
        )

        # Áp dụng bộ lọc trạng thái
        if status:
            order_query = order_query.filter(Order.status == status)

        # Áp dụng tìm kiếm
        if query:
            search_like = f"%{query}%"
            order_query = order_query.outerjoin(User, Order.user_id == User.id).filter(
                db.or_(
                    Order.order_number.ilike(search_like),
                    func.lower(User.first_name + ' ' + User.last_name).contains(func.lower(query)),
                    User.email.ilike(search_like),
                    User.phone.ilike(search_like),
                    Order.contact_phone.ilike(search_like)
                )
            )
        orders = order_query.order_by(Order.created_at.desc()).limit(100).all() # Ví dụ giới hạn 100
        count = len(orders) # Số lượng KQ thực tế trả về

        table_rows_html = render_template(
            'admin/_order_table_rows.html',
            orders=orders,
            pagination=None # Truyền None vì không dùng phân trang ở đây
        )

        return jsonify({
            'success': True,
            'html': table_rows_html,
            'count': count # Số lượng kết quả trả về
        })

    except Exception as e:
        logger.error(f"API Error searching orders (q='{query}', status='{status}'): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'Lỗi máy chủ khi tìm kiếm đơn hàng.'
        }), 500
    
@admin_bp.route('/api/search-inventory')
@login_required
@admin_required # Hoặc quyền hạn phù hợp
def api_search_inventory():
    """API tìm kiếm tồn kho động cho trang Admin."""
    logger = current_app.logger
    try:
        query = request.args.get('q', '')
        status_filter = request.args.get('status', 'all')

        base_query = db.session.query(InventoryItem).options(
            joinedload(InventoryItem.product_inventory).joinedload(Product.category)
        ).join(Product, InventoryItem.product_id == Product.id)

        if query:
            base_query = base_query.filter(Product.name.ilike(f'%{query}%'))

        if status_filter == 'low':
            base_query = base_query.filter(InventoryItem.quantity > 0, InventoryItem.quantity <= InventoryItem.min_quantity)
        elif status_filter == 'out':
            base_query = base_query.filter(InventoryItem.quantity <= 0)
        elif status_filter == 'adequate':
            base_query = base_query.filter(InventoryItem.quantity > InventoryItem.min_quantity)

        inventory_items = base_query.order_by(
            case(
                (InventoryItem.quantity <= 0, 0),
                (InventoryItem.quantity <= InventoryItem.min_quantity, 1),
                else_=2
            ),
            Product.name.asc()
        ).limit(150).all() # Giới hạn số lượng trả về
        count = len(inventory_items)

        # --- Render template partial ---
        # Cần import format_datetime nếu dùng trong partial
        from utils import format_currency, get_order_status_label # Bổ sung format_datetime nếu utils có
        from app import format_datetime_filter # Hoặc import trực tiếp filter nếu định nghĩa ở app.py

        table_rows_html = render_template(
            'admin/_inventory_table_rows.html',
            inventory_items=inventory_items,
            format_datetime=format_datetime_filter # Truyền filter vào template
        )
        # --- Kết thúc render partial ---

        return jsonify({'success': True, 'html': table_rows_html, 'count': count})

    except Exception as e:
        logger.error(f"API Error searching inventory (q='{query}', status='{status_filter}'): {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Lỗi khi tìm kiếm tồn kho.'}), 500