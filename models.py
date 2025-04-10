# /DragonCoffee/models.py

from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.dialects.postgresql import NUMERIC # Có thể xóa nếu không dùng PostgreSQL NUMERIC

# ==================== User Model ====================
class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_staff = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    orders = db.relationship('Order', backref='customer', lazy='dynamic', foreign_keys='Order.user_id')
    reviews = db.relationship('Review', backref='author', lazy='dynamic', foreign_keys='Review.user_id')
    employee_profile = db.relationship('Employee', backref='user', uselist=False, foreign_keys='Employee.user_id', cascade="all, delete-orphan")

    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name or self.username

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password) if self.password_hash else False

    def __repr__(self):
        return f'<User {self.username}>'

# ==================== Category Model ====================
class Category(db.Model):
    __tablename__ = 'category'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(256))
    products = db.relationship('Product', backref='category', lazy='dynamic', foreign_keys='Product.category_id')

    def __repr__(self):
        return f'<Category {self.name}>'

# ==================== Product Model ====================
class Product(db.Model):
    __tablename__ = 'product'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, index=True) # Thêm index cho tên
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(256))
    is_available = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    reviews = db.relationship('Review', backref='product', lazy='dynamic', foreign_keys='Review.product_id', cascade="all, delete-orphan")
    inventory = db.relationship('InventoryItem', backref='product_inventory', uselist=False, foreign_keys='InventoryItem.product_id', cascade="all, delete-orphan")

    # SỬA backref TRÁNH XUNG ĐỘT - Đây là Lựa chọn 1 (Đổi tên backref ở đây)
    order_details = db.relationship(
        'OrderDetail',
        backref='product_details_link', # Đổi tên backref thành cái gì đó không trùng với thuộc tính trong OrderDetail
        lazy='dynamic',
        foreign_keys='OrderDetail.product_id',
        cascade="all, delete-orphan" # Cascade xóa OrderDetail khi Product bị xóa (cẩn thận khi dùng)
    )
    # KHÔNG cần OrderItemsAssociation nếu bạn đã dùng OrderDetail hiệu quả
    # orders_assoc = db.relationship('OrderItemsAssociation', back_populates='product', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Product {self.name}>'

# ==================== Order Model ====================
class Order(db.Model):
    __tablename__ = 'order'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False, index=True) # Thêm index
    status = db.Column(db.String(30), default='pending', nullable=False, index=True) # Tăng độ dài phòng các status mới
    total_amount = db.Column(db.Float, nullable=False) # Tổng tiền hàng trước thuế/ship/discount
    # tax_amount = db.Column(db.Float, nullable=True, default=0.0)
    # shipping_fee = db.Column(db.Float, nullable=True, default=0.0)
    # discount_amount = db.Column(db.Float, nullable=True, default=0.0)
    final_amount = db.Column(db.Float, nullable=False) # Tổng tiền cuối cùng khách trả
    order_type = db.Column(db.String(20), nullable=False, index=True) # Thêm index
    payment_method = db.Column(db.String(30)) # Tăng độ dài
    payment_status = db.Column(db.String(20), default='pending', nullable=False, index=True)
    notes = db.Column(db.Text)
    address = db.Column(db.String(256))
    contact_phone = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    # backref='customer' đã định nghĩa ở User.orders
    # backref cho OrderItemsAssociation nếu bạn dùng:
    # items_assoc = db.relationship('OrderItemsAssociation', back_populates='order', cascade='all, delete-orphan')

    # Quan hệ với OrderDetail
    details = db.relationship('OrderDetail', backref='parent_order', lazy='dynamic', foreign_keys='OrderDetail.order_id', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Order {self.order_number}>'

    def get_status_display(self):
        status_mapping = {
            'pending': 'Chờ xử lý',
            'processing': 'Đang xử lý',
            'ready_for_pickup': 'Sẵn sàng lấy',
            'out_for_delivery': 'Đang giao',
            'completed': 'Hoàn thành',
            'delivered': 'Đã giao', # Thêm trạng thái
            'cancelled': 'Đã hủy',
            'failed': 'Thất bại'   # Thêm trạng thái
        }
        return status_mapping.get(self.status, self.status.replace('_', ' ').capitalize())

# === BỎ OrderItemsAssociation nếu bạn không dùng mô hình Many-to-Many qua Association Object này ===
# Nếu bạn chỉ cần OrderDetail là đủ thì không cần class này
# class OrderItemsAssociation(db.Model):
#     __tablename__ = 'order_items'
#     # ... (columns)
#     # ... (relationships)

# ==================== OrderDetail Model ====================
class OrderDetail(db.Model):
    __tablename__ = 'order_detail'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id', ondelete='RESTRICT'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    notes = db.Column(db.String(256))

    # Relationship đến Product (VẪN giữ nguyên tên này trong code Python)
    # Backref đã được định nghĩa trong Product với tên là 'product_details_link' (theo Lựa chọn 1)
    # Nên khi truy cập từ Product sẽ là product.product_details_link
    # Khi truy cập từ OrderDetail sẽ là detail.ordered_product (NHƯNG CẦN KẾT HỢP VỚI backref từ Product)
    # Để đơn giản, chỉ cần định nghĩa ở 1 bên với backref
    # BỎ định nghĩa này nếu đã có backref 'product_details_link' trong Product
    # ordered_product = db.relationship('Product')

    # Relationship đến Order (đã có backref='details' từ Order)

    def __repr__(self):
        return f'<OrderDetail {self.id} for Order {self.order_id}>'


# ==================== Review Model ====================
class Review(db.Model):
    __tablename__ = 'review'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sentiment_label = db.Column(db.String(20), nullable=True, index=True)
    sentiment_score = db.Column(db.Float, nullable=True)

    # author backref từ User.reviews
    # product backref từ Product.reviews

    def __repr__(self):
        return f'<Review {self.id} for Product {self.product_id}>'

# ==================== ContactMessage Model ====================
class ContactMessage(db.Model):
    __tablename__ = 'contact_message'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(120))
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<ContactMessage {self.id}>'

# ==================== Promotion Model ====================
class Promotion(db.Model):
    __tablename__ = 'promotion'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text)
    discount_percent = db.Column(db.Float, nullable=True)
    discount_amount = db.Column(db.Float, nullable=True)
    code = db.Column(db.String(20), unique=True, index=True)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    def __repr__(self):
        return f'<Promotion {self.name}>'

# ==================== InventoryItem Model ====================
class InventoryItem(db.Model):
    __tablename__ = 'inventory_item'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id', ondelete='CASCADE'), unique=True, nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    min_quantity = db.Column(db.Integer, nullable=False, default=10)
    unit = db.Column(db.String(20), nullable=True)
    last_restocked = db.Column(db.DateTime, nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # product_inventory backref từ Product.inventory

    def __repr__(self):
        return f'<InventoryItem for Product ID {self.product_id}>'

# ==================== Employee Model ====================
class Employee(db.Model):
    __tablename__ = 'employee'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), unique=True, nullable=False, index=True)
    position = db.Column(db.String(64), nullable=False)
    hire_date = db.Column(db.Date, nullable=False)
    salary = db.Column(db.Float, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    # user backref từ User.employee_profile

    def __repr__(self):
        return f'<Employee Record {self.id} for User ID {self.user_id}>'

# ==================== InterestingStory Model ====================
class InterestingStory(db.Model):
    __tablename__ = 'interesting_story'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, default="Câu chuyện thú vị về Dragon Coffee")
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(256), nullable=True)
    status = db.Column(db.String(20), default='draft', nullable=False, index=True)
    generated_by_ai = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    # author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # ForeignKey đến User
    # author = db.relationship('User') # Quan hệ đến User (tùy chọn)

    def __repr__(self):
        return f'<InterestingStory {self.id}: {self.title[:30]}...>'