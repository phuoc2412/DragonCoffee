from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from models import Product, Order, OrderDetail
from app import db
from datetime import datetime
import uuid

order_bp = Blueprint('order', __name__)

@order_bp.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    total = 0
    products = []
    
    for item in cart_items:
        product = Product.query.get(item['product_id'])
        if product:
            quantity = item['quantity']
            subtotal = product.price * quantity
            total += subtotal
            products.append({
                'id': product.id,
                'name': product.name,
                'price': product.price,
                'quantity': quantity,
                'subtotal': subtotal,
                'image_url': product.image_url,
                'notes': item.get('notes', '')
            })
    
    return render_template('cart.html', cart_items=products, total=total)

@order_bp.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', 1, type=int)
    notes = request.form.get('notes', '')
    
    if not product_id or quantity <= 0:
        flash('Invalid product or quantity', 'danger')
        return redirect(request.referrer or url_for('main.menu'))
    
    product = Product.query.get_or_404(product_id)
    
    if not product.is_available:
        flash('This product is currently unavailable', 'danger')
        return redirect(request.referrer or url_for('main.menu'))
    
    # Initialize cart if it doesn't exist
    if 'cart' not in session:
        session['cart'] = []
    
    # Check if product already in cart, update quantity if it is
    updated = False
    for item in session['cart']:
        if item['product_id'] == product_id:
            item['quantity'] += quantity
            item['notes'] = notes
            updated = True
            break
    
    # Otherwise add new product to cart
    if not updated:
        session['cart'].append({
            'product_id': product_id,
            'quantity': quantity,
            'notes': notes
        })
    
    # Update session
    session.modified = True
    
    flash(f'Added {product.name} to cart', 'success')
    return redirect(request.referrer or url_for('main.menu'))

@order_bp.route('/update-cart', methods=['POST'])
def update_cart():
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', 0, type=int)
    
    if not product_id:
        flash('Invalid product', 'danger')
        return redirect(url_for('order.cart'))
    
    if 'cart' not in session:
        return redirect(url_for('order.cart'))
    
    # Remove product if quantity is 0, otherwise update quantity
    if quantity <= 0:
        session['cart'] = [item for item in session['cart'] if item['product_id'] != product_id]
    else:
        for item in session['cart']:
            if item['product_id'] == product_id:
                item['quantity'] = quantity
                break
    
    # Update session
    session.modified = True
    
    flash('Cart updated', 'success')
    return redirect(url_for('order.cart'))

@order_bp.route('/remove-from-cart/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    if 'cart' not in session:
        return redirect(url_for('order.cart'))
    
    session['cart'] = [item for item in session['cart'] if item['product_id'] != product_id]
    session.modified = True
    
    flash('Item removed from cart', 'success')
    return redirect(url_for('order.cart'))

@order_bp.route('/clear-cart', methods=['POST'])
def clear_cart():
    session.pop('cart', None)
    flash('Cart cleared', 'success')
    return redirect(url_for('order.cart'))

@order_bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'cart' not in session or not session['cart']:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('main.menu'))
    
    cart_items = session.get('cart', [])
    total = 0
    products = []
    
    for item in cart_items:
        product = Product.query.get(item['product_id'])
        if product:
            quantity = item['quantity']
            subtotal = product.price * quantity
            total += subtotal
            products.append({
                'id': product.id,
                'name': product.name,
                'price': product.price,
                'quantity': quantity,
                'subtotal': subtotal,
                'image_url': product.image_url,
                'notes': item.get('notes', '')
            })
    
    if request.method == 'POST':
        order_type = request.form.get('order_type', 'takeaway')
        payment_method = request.form.get('payment_method', 'cash')
        notes = request.form.get('notes', '')
        
        # Create order
        order = Order(
            user_id=current_user.id if current_user.is_authenticated else None,
            order_number=f"WEB-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:8]}",
            status='pending',
            total_amount=total,
            order_type=order_type,
            payment_method=payment_method,
            payment_status='pending',
            notes=notes,
            address=request.form.get('address', '') if order_type == 'delivery' else None,
            contact_phone=request.form.get('phone', '')
        )
        
        db.session.add(order)
        db.session.flush()  # Get order ID without committing
        
        # Add order details
        for item in products:
            detail = OrderDetail(
                order_id=order.id,
                product_id=item['id'],
                quantity=item['quantity'],
                unit_price=item['price'],
                subtotal=item['subtotal'],
                notes=item['notes']
            )
            db.session.add(detail)
        
        db.session.commit()
        
        # Clear cart
        session.pop('cart', None)
        
        flash('Your order has been placed successfully!', 'success')
        return render_template('order_confirmation.html', order=order, products=products, total=total)
    
    return render_template('checkout.html', cart_items=products, total=total)

@order_bp.route('/orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('my_orders.html', orders=orders)

@order_bp.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Ensure user can only see their own orders (except for admin/staff)
    if order.user_id != current_user.id and not (current_user.is_admin or current_user.is_staff):
        flash('You do not have permission to view this order', 'danger')
        return redirect(url_for('order.my_orders'))
    
    order_details = OrderDetail.query.filter_by(order_id=order_id).all()
    return render_template('order_detail.html', order=order, order_details=order_details)

@order_bp.route('/api/order-status/<order_number>')
def api_order_status(order_number):
    order = Order.query.filter_by(order_number=order_number).first()
    
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    return jsonify({
        'status': order.status,
        'updated_at': order.updated_at.strftime('%Y-%m-%d %H:%M:%S')
    })
