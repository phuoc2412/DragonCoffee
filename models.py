from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Association table for many-to-many relationship between orders and products
order_items = db.Table('order_items',
    db.Column('order_id', db.Integer, db.ForeignKey('order.id'), primary_key=True),
    db.Column('product_id', db.Integer, db.ForeignKey('product.id'), primary_key=True),
    db.Column('quantity', db.Integer, default=1),
    db.Column('notes', db.String(255), nullable=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(64), nullable=True)
    last_name = db.Column(db.String(64), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(256), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_staff = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    orders = db.relationship('Order', backref='customer', lazy='dynamic')
    reviews = db.relationship('Review', backref='author', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(256), nullable=True)
    
    # Relationships
    products = db.relationship('Product', backref='category', lazy='dynamic')
    
    def __repr__(self):
        return f'<Category {self.name}>'

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(256), nullable=True)
    is_available = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    reviews = db.relationship('Review', backref='product', lazy='dynamic')
    inventory_items = db.relationship('InventoryItem', backref='product', lazy='dynamic')
    
    def __repr__(self):
        return f'<Product {self.name}>'

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Guest orders can be null
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, processing, completed, cancelled
    total_amount = db.Column(db.Float, nullable=False)
    order_type = db.Column(db.String(20), nullable=False)  # dine-in, takeaway, delivery
    payment_method = db.Column(db.String(20), nullable=True)  # cash, credit, debit, online
    payment_status = db.Column(db.String(20), default='pending', nullable=False)  # pending, completed, failed
    notes = db.Column(db.Text, nullable=True)
    address = db.Column(db.String(256), nullable=True)  # Delivery address if needed
    contact_phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - many-to-many with products through order_items
    items = db.relationship('Product', secondary=order_items, lazy='dynamic',
                            backref=db.backref('orders', lazy='dynamic'))
    
    def __repr__(self):
        return f'<Order {self.order_number}>'

class OrderDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    notes = db.Column(db.String(256), nullable=True)
    
    # Relationships
    order = db.relationship('Order', backref='order_details')
    product = db.relationship('Product')
    
    def __repr__(self):
        return f'<OrderDetail {self.id} - Order {self.order_id}>'

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    content = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Review {self.id} - Rating {self.rating}>'

class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ContactMessage {self.id} - {self.subject}>'

class Promotion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text, nullable=True)
    discount_percent = db.Column(db.Float, nullable=True)
    discount_amount = db.Column(db.Float, nullable=True)
    code = db.Column(db.String(20), unique=True, nullable=True)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<Promotion {self.name}>'

class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    min_quantity = db.Column(db.Integer, nullable=False, default=10)  # Minimum stock level before alert
    unit = db.Column(db.String(20), nullable=True)  # e.g., kg, liters, pieces
    last_restocked = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<InventoryItem {self.id} - Product {self.product_id}>'

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    position = db.Column(db.String(64), nullable=False)
    hire_date = db.Column(db.DateTime, nullable=False)
    salary = db.Column(db.Float, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('employee_profile', uselist=False))
    
    def __repr__(self):
        return f'<Employee {self.id} - Position {self.position}>'
