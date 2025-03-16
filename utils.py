import os
import uuid
from datetime import datetime
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (not current_user.is_admin and not current_user.is_staff):
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def generate_order_number():
    """Generate a unique order number"""
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    random_str = str(uuid.uuid4())[:8]
    return f"ORD-{timestamp}-{random_str}"

def calculate_order_total(items):
    """Calculate the total amount for an order"""
    total = 0
    for item in items:
        total += item['price'] * item['quantity']
    return total

def get_order_status_label(status):
    """Get bootstrap label class for order status"""
    status_labels = {
        'pending': 'badge bg-warning',
        'processing': 'badge bg-info',
        'completed': 'badge bg-success',
        'cancelled': 'badge bg-danger'
    }
    return status_labels.get(status, 'badge bg-secondary')

def format_currency(amount):
    """Format amount as currency"""
    return f"${amount:.2f}"
