from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import (User, Product, Category, Order, OrderDetail, 
                   Review, ContactMessage, Promotion, InventoryItem, Employee)
from forms import ProductForm, CategoryForm, PromotionForm, EmployeeForm
from app import db
from functools import wraps
from sqlalchemy import func, desc
from datetime import datetime, timedelta

admin_bp = Blueprint('admin', __name__)

# Custom decorator to check admin rights
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    # Get quick statistics for dashboard
    total_orders = Order.query.count()
    total_products = Product.query.count()
    total_users = User.query.count()
    total_revenue = db.session.query(func.sum(Order.total_amount)).filter(Order.status == 'completed').scalar() or 0
    
    # Get recent orders
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    
    # Get top selling products
    top_products = db.session.query(
        Product, func.sum(OrderDetail.quantity).label('total_sold')
    ).join(OrderDetail).group_by(Product).order_by(desc('total_sold')).limit(5).all()
    
    # Get sales data for chart (last 7 days)
    today = datetime.utcnow().date()
    sales_data = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        next_date = date + timedelta(days=1)
        daily_sales = db.session.query(func.sum(Order.total_amount)).filter(
            Order.created_at >= date,
            Order.created_at < next_date,
            Order.status == 'completed'
        ).scalar() or 0
        sales_data.append({
            'date': date.strftime('%a'),
            'amount': float(daily_sales)
        })
    
    return render_template('admin/dashboard.html', 
                          total_orders=total_orders,
                          total_products=total_products,
                          total_users=total_users,
                          total_revenue=total_revenue,
                          recent_orders=recent_orders,
                          top_products=top_products,
                          sales_data=sales_data)

@admin_bp.route('/menu-management')
@login_required
@admin_required
def menu_management():
    products = Product.query.all()
    categories = Category.query.all()
    return render_template('admin/menu_management.html', products=products, categories=categories)

@admin_bp.route('/product/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    form = ProductForm()
    form.category_id.choices = [(c.id, c.name) for c in Category.query.all()]
    
    if form.validate_on_submit():
        product = Product(
            name=form.name.data,
            description=form.description.data,
            price=form.price.data,
            image_url=form.image_url.data,
            is_available=form.is_available.data,
            is_featured=form.is_featured.data,
            category_id=form.category_id.data
        )
        db.session.add(product)
        db.session.commit()
        
        # Add inventory item for the product
        inventory = InventoryItem(
            product_id=product.id,
            quantity=form.stock_quantity.data,
            min_quantity=10
        )
        db.session.add(inventory)
        db.session.commit()
        
        flash('Product added successfully!', 'success')
        return redirect(url_for('admin.menu_management'))
        
    return render_template('admin/product_form.html', form=form, title='Add Product')

@admin_bp.route('/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    inventory = InventoryItem.query.filter_by(product_id=product_id).first()
    
    form = ProductForm(obj=product)
    form.category_id.choices = [(c.id, c.name) for c in Category.query.all()]
    
    if form.validate_on_submit():
        product.name = form.name.data
        product.description = form.description.data
        product.price = form.price.data
        product.image_url = form.image_url.data
        product.is_available = form.is_available.data
        product.is_featured = form.is_featured.data
        product.category_id = form.category_id.data
        
        if inventory:
            inventory.quantity = form.stock_quantity.data
        else:
            inventory = InventoryItem(
                product_id=product.id,
                quantity=form.stock_quantity.data,
                min_quantity=10
            )
            db.session.add(inventory)
            
        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('admin.menu_management'))
    
    # Pre-populate stock quantity if inventory exists
    if inventory:
        form.stock_quantity.data = inventory.quantity
        
    return render_template('admin/product_form.html', form=form, title='Edit Product', product=product)

@admin_bp.route('/product/delete/<int:product_id>', methods=['POST'])
@login_required
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Delete associated inventory items
    InventoryItem.query.filter_by(product_id=product_id).delete()
    
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully!', 'success')
    return redirect(url_for('admin.menu_management'))

@admin_bp.route('/category/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_category():
    form = CategoryForm()
    
    if form.validate_on_submit():
        category = Category(
            name=form.name.data,
            description=form.description.data
        )
        db.session.add(category)
        db.session.commit()
        flash('Category added successfully!', 'success')
        return redirect(url_for('admin.menu_management'))
        
    return render_template('admin/category_form.html', form=form, title='Add Category')

@admin_bp.route('/category/edit/<int:category_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    form = CategoryForm(obj=category)
    
    if form.validate_on_submit():
        category.name = form.name.data
        category.description = form.description.data
        db.session.commit()
        flash('Category updated successfully!', 'success')
        return redirect(url_for('admin.menu_management'))
        
    return render_template('admin/category_form.html', form=form, title='Edit Category', category=category)

@admin_bp.route('/category/delete/<int:category_id>', methods=['POST'])
@login_required
@admin_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    
    # Check if category has products
    if Product.query.filter_by(category_id=category_id).first():
        flash('Cannot delete category with products. Please delete or reassign products first.', 'danger')
        return redirect(url_for('admin.menu_management'))
    
    db.session.delete(category)
    db.session.commit()
    flash('Category deleted successfully!', 'success')
    return redirect(url_for('admin.menu_management'))

@admin_bp.route('/orders')
@login_required
@admin_required
def orders():
    status_filter = request.args.get('status', '')
    if status_filter and status_filter != 'all':
        orders = Order.query.filter_by(status=status_filter).order_by(Order.created_at.desc()).all()
    else:
        orders = Order.query.order_by(Order.created_at.desc()).all()
    
    return render_template('admin/orders.html', orders=orders, current_filter=status_filter)

@admin_bp.route('/orders/<int:order_id>')
@login_required
@admin_required
def order_details(order_id):
    order = Order.query.get_or_404(order_id)
    order_details = OrderDetail.query.filter_by(order_id=order_id).all()
    
    return render_template('admin/order_details.html', order=order, order_details=order_details)

@admin_bp.route('/orders/update-status/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    
    if new_status in ['pending', 'processing', 'completed', 'cancelled']:
        order.status = new_status
        db.session.commit()
        flash(f'Order #{order.order_number} status updated to {new_status}', 'success')
    else:
        flash('Invalid status', 'danger')
        
    return redirect(url_for('admin.order_details', order_id=order_id))

@admin_bp.route('/pos')
@login_required
@admin_required
def pos():
    categories = Category.query.all()
    products = Product.query.filter_by(is_available=True).all()
    
    return render_template('admin/pos.html', categories=categories, products=products)

@admin_bp.route('/api/products')
@login_required
@admin_required
def api_products():
    category_id = request.args.get('category_id', type=int)
    query = request.args.get('q', '')
    
    products_query = Product.query.filter_by(is_available=True)
    
    if category_id:
        products_query = products_query.filter_by(category_id=category_id)
        
    if query:
        products_query = products_query.filter(Product.name.ilike(f'%{query}%'))
    
    products = products_query.all()
    
    result = []
    for product in products:
        result.append({
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'category_id': product.category_id,
            'image_url': product.image_url
        })
    
    return jsonify(result)

@admin_bp.route('/api/create-order', methods=['POST'])
@login_required
@admin_required
def api_create_order():
    data = request.json
    
    if not data or 'items' not in data:
        return jsonify({'error': 'Invalid data'}), 400
    
    # Create new order
    order = Order(
        user_id=data.get('user_id'),
        order_number=f"POS-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        status='completed',
        total_amount=data.get('total_amount', 0),
        order_type=data.get('order_type', 'dine-in'),
        payment_method=data.get('payment_method', 'cash'),
        payment_status='completed',
        notes=data.get('notes', ''),
        contact_phone=data.get('contact_phone', '')
    )
    
    db.session.add(order)
    db.session.flush()  # Get the order ID without committing
    
    # Add order details
    for item in data['items']:
        product = Product.query.get(item['product_id'])
        if not product:
            continue
            
        order_detail = OrderDetail(
            order_id=order.id,
            product_id=product.id,
            quantity=item['quantity'],
            unit_price=product.price,
            subtotal=product.price * item['quantity'],
            notes=item.get('notes', '')
        )
        db.session.add(order_detail)
        
        # Update inventory
        inventory = InventoryItem.query.filter_by(product_id=product.id).first()
        if inventory:
            inventory.quantity = max(0, inventory.quantity - item['quantity'])
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'order_id': order.id,
        'order_number': order.order_number
    })

@admin_bp.route('/inventory')
@login_required
@admin_required
def inventory():
    inventory_items = InventoryItem.query.join(Product).order_by(Product.name).all()
    return render_template('admin/inventory.html', inventory_items=inventory_items)

@admin_bp.route('/inventory/update/<int:inventory_id>', methods=['POST'])
@login_required
@admin_required
def update_inventory(inventory_id):
    inventory = InventoryItem.query.get_or_404(inventory_id)
    new_quantity = request.form.get('quantity', type=int)
    
    if new_quantity is not None and new_quantity >= 0:
        inventory.quantity = new_quantity
        inventory.last_restocked = datetime.utcnow()
        db.session.commit()
        flash('Inventory updated successfully!', 'success')
    else:
        flash('Invalid quantity value', 'danger')
        
    return redirect(url_for('admin.inventory'))

@admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    report_type = request.args.get('type', 'sales')
    period = request.args.get('period', 'week')
    
    today = datetime.utcnow().date()
    
    if period == 'day':
        start_date = today
    elif period == 'week':
        start_date = today - timedelta(days=7)
    elif period == 'month':
        start_date = today.replace(day=1)
    elif period == 'year':
        start_date = today.replace(month=1, day=1)
    else:
        start_date = today - timedelta(days=7)
    
    # Sales report data
    if report_type == 'sales':
        orders = Order.query.filter(
            Order.created_at >= start_date,
            Order.status == 'completed'
        ).order_by(Order.created_at).all()
        
        # Calculate daily sales for chart
        daily_sales = {}
        for order in orders:
            order_date = order.created_at.date().strftime('%Y-%m-%d')
            if order_date in daily_sales:
                daily_sales[order_date] += order.total_amount
            else:
                daily_sales[order_date] = order.total_amount
        
        chart_data = {
            'labels': list(daily_sales.keys()),
            'values': list(daily_sales.values())
        }
        
        # Get total sales
        total_sales = sum(daily_sales.values())
        
        return render_template('admin/reports.html', 
                              report_type=report_type,
                              period=period,
                              orders=orders,
                              chart_data=chart_data,
                              total_sales=total_sales)
    
    # Product popularity report
    elif report_type == 'products':
        product_sales = db.session.query(
            Product.name,
            func.sum(OrderDetail.quantity).label('total_sold'),
            func.sum(OrderDetail.subtotal).label('total_revenue')
        ).join(OrderDetail).join(Order).filter(
            Order.created_at >= start_date,
            Order.status == 'completed'
        ).group_by(Product.name).order_by(desc('total_sold')).all()
        
        chart_data = {
            'labels': [p[0] for p in product_sales],
            'values': [p[1] for p in product_sales]
        }
        
        return render_template('admin/reports.html', 
                              report_type=report_type,
                              period=period,
                              product_sales=product_sales,
                              chart_data=chart_data)
    
    # Default to sales report
    return redirect(url_for('admin.reports', type='sales', period='week'))

@admin_bp.route('/employees')
@login_required
@admin_required
def employees():
    employees = Employee.query.join(User).all()
    return render_template('admin/employees.html', employees=employees)

@admin_bp.route('/employees/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_employee():
    form = EmployeeForm()
    
    if form.validate_on_submit():
        # Check if user exists, if not create one
        user = User.query.filter_by(email=form.email.data).first()
        if not user:
            user = User(
                username=form.email.data.split('@')[0],
                email=form.email.data,
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                phone=form.phone.data,
                is_staff=True
            )
            user.set_password('dragonstaff123')  # Default password
            db.session.add(user)
            db.session.flush()
        
        # Create employee record
        employee = Employee(
            user_id=user.id,
            position=form.position.data,
            hire_date=form.hire_date.data,
            salary=form.salary.data,
            is_active=True
        )
        
        db.session.add(employee)
        db.session.commit()
        
        flash('Employee added successfully!', 'success')
        return redirect(url_for('admin.employees'))
    
    return render_template('admin/employee_form.html', form=form, title='Add Employee')

@admin_bp.route('/employees/edit/<int:employee_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    user = User.query.get(employee.user_id)
    
    form = EmployeeForm(obj=employee)
    form.first_name.data = user.first_name
    form.last_name.data = user.last_name
    form.email.data = user.email
    form.phone.data = user.phone
    
    if form.validate_on_submit():
        # Update user information
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.email = form.email.data
        user.phone = form.phone.data
        
        # Update employee information
        employee.position = form.position.data
        employee.hire_date = form.hire_date.data
        employee.salary = form.salary.data
        
        db.session.commit()
        
        flash('Employee updated successfully!', 'success')
        return redirect(url_for('admin.employees'))
    
    return render_template('admin/employee_form.html', form=form, title='Edit Employee', employee=employee)

@admin_bp.route('/employees/toggle/<int:employee_id>', methods=['POST'])
@login_required
@admin_required
def toggle_employee_status(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    employee.is_active = not employee.is_active
    
    # Also update user staff status
    user = User.query.get(employee.user_id)
    user.is_staff = employee.is_active
    
    db.session.commit()
    
    status = "activated" if employee.is_active else "deactivated"
    flash(f'Employee {status} successfully!', 'success')
    
    return redirect(url_for('admin.employees'))
