# /DragonCoffee/models.py

from datetime import datetime, timedelta, timezone
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.dialects.postgresql import NUMERIC # Có thể xóa nếu không dùng PostgreSQL NUMERIC
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask import current_app
from sqlalchemy import Text

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
    address = db.Column(db.Text, nullable=True)
    avatar_url = db.Column(db.String(256), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_staff = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    review_warning_count = db.Column(db.Integer, default=0, nullable=False)
    is_comment_banned = db.Column(db.Boolean, default=False, nullable=False, index=True)

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

    def get_reset_token(self, expires_sec=1800):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id, 'ts': datetime.now(timezone.utc).timestamp()}, salt='password-reset-salt')

    @staticmethod
    def verify_reset_token(token, expires_sec=1800, salt='password-reset-salt'):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, salt=salt, max_age=expires_sec)
            user_id = data.get('user_id')
        except Exception as e:
            current_app.logger.warning(f"Password reset token verification failed: {e}")
            return None
        return User.query.get(user_id)

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
    name = db.Column(db.String(64), nullable=False, index=True)
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

    order_details = db.relationship(
        'OrderDetail',
        backref='ordered_product',
        lazy='dynamic',
        foreign_keys='OrderDetail.product_id',
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f'<Product {self.name}>'

# ==================== Order Model ====================
class Order(db.Model):
    __tablename__ = 'order'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    status = db.Column(db.String(30), default='pending', nullable=False, index=True)
    total_amount = db.Column(db.Float, nullable=False)
    final_amount = db.Column(db.Float, nullable=False)
    order_type = db.Column(db.String(20), nullable=False, index=True)
    payment_method = db.Column(db.String(30))
    payment_status = db.Column(db.String(20), default='pending', nullable=False, index=True)
    notes = db.Column(db.Text)
    address = db.Column(db.String(256))
    contact_phone = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    promotion_id = db.Column(db.Integer, db.ForeignKey('promotion.id', ondelete='SET NULL'), nullable=True, index=True)
    promotion_code_used = db.Column(db.String(30), nullable=True)
    discount_applied = db.Column(db.Float, nullable=True, default=0.0)
    tax_amount = db.Column(db.Float, nullable=True, default=0.0)      # Added based on later discussion
    shipping_fee = db.Column(db.Float, nullable=True, default=0.0)   # Added based on later discussion

    promotion = db.relationship('Promotion')
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
            'delivered': 'Đã giao',
            'cancelled': 'Đã hủy',
            'failed': 'Thất bại'
        }
        return status_mapping.get(self.status, self.status.replace('_', ' ').capitalize())

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
    original_content = db.Column(db.Text, nullable=True)
    is_toxic_guess = db.Column(db.Boolean, nullable=True, index=True)
    sentiment_label = db.Column(db.String(20), nullable=True, index=True)
    sentiment_score = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=False, index=True)

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

    receipts = db.relationship('StockReceipt', backref='inventory_item', lazy='dynamic', cascade="all, delete-orphan")

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

    def __repr__(self):
        return f'<InterestingStory {self.id}: {self.title[:30]}...>'

# ==================== StockReceipt Model ====================
class StockReceipt(db.Model):
    __tablename__ = 'stock_receipt'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id', ondelete='CASCADE'), nullable=False, index=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id', ondelete='CASCADE'), nullable=True, index=True)
    quantity_added = db.Column(db.Integer, nullable=False)
    supplier = db.Column(db.String(128), nullable=True)
    unit_cost = db.Column(db.Float, nullable=True)
    received_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    received_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    product = db.relationship('Product')
    received_by = db.relationship('User')

    def __repr__(self):
        return f'<StockReceipt ID {self.id} for Product {self.product_id}>'

# ==================== Location Model ====================
class Location(db.Model):
    __tablename__ = 'location'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    address = db.Column(Text, nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    hours = db.Column(Text, nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    map_embed_url = db.Column(Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<Location {self.name}>'