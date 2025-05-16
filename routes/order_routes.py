# /routes/order_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from flask_login import login_required, current_user
from models import Product, Order, OrderDetail, db, InventoryItem, Promotion # Đảm bảo db được import
from datetime import datetime
import uuid # << --- THÊM IMPORT UUID ---
from utils import generate_order_number, format_currency, send_order_status_email
import logging
from sqlalchemy import func
import logging # Thêm logging
from sqlalchemy.orm import joinedload

order_bp = Blueprint('order', __name__, url_prefix='/order') # <-- Thêm prefix

@order_bp.route('/cart')
def cart():
    cart_items_data = session.get('cart', [])
    total = 0
    products = []
    product_ids = [item['product_id'] for item in cart_items_data if 'product_id' in item] # An toàn hơn
    logger = current_app.logger if current_app else logging.getLogger(__name__)

    if product_ids:
        products_in_db = Product.query.filter(Product.id.in_(product_ids)).all()
        products_map = {p.id: p for p in products_in_db}

        valid_cart_items_session = []
        for item_data in cart_items_data:
            product_id_from_session = item_data.get('product_id')
            if not product_id_from_session: continue # Bỏ qua item thiếu product_id

            product = products_map.get(product_id_from_session)
            if product:
                quantity = item_data.get('quantity', 1)
                if not isinstance(quantity, int) or quantity <= 0: quantity = 1 # Đảm bảo số lượng hợp lệ
                
                price = item_data.get('price') # Lấy giá đã lưu trong session khi add to cart
                if price is None: # Nếu vì lý do nào đó giá không có trong session, query lại
                    price = product.price
                if price is None: # Nếu vẫn không có giá (ví dụ sp chưa set giá), bỏ qua
                    logger.warning(f"Product ID {product_id_from_session} has no price. Skipping from cart display.")
                    continue

                try:
                    price_float = float(price)
                    subtotal = price_float * quantity
                    total += subtotal
                    products.append({
                        'id': product.id,
                        'name': product.name,
                        'price': price_float, # Đảm bảo là float
                        'quantity': quantity,
                        'subtotal': subtotal,
                        'image_url': product.image_url or url_for('static',filename='images/default_product_thumb.png'), # Thêm fallback
                        'notes': item_data.get('notes', '')
                    })
                    valid_cart_items_session.append(item_data)
                except ValueError:
                    logger.warning(f"Could not convert price to float for product {product_id_from_session}. Price in session: {price}")
                    continue # Bỏ qua sản phẩm có giá không hợp lệ
            else:
                 logger.warning(f"Product ID {product_id_from_session} found in cart session but not in DB or unavailable. Removing from cart.")
        
        if len(valid_cart_items_session) < len(cart_items_data):
            session['cart'] = valid_cart_items_session
            session.modified = True
            if any(item_data not in valid_cart_items_session for item_data in cart_items_data):
                 flash("Một vài sản phẩm không hợp lệ đã được tự động xóa khỏi giỏ hàng.", "info")


    return render_template('cart.html', cart_items=products, total=total, format_price=format_currency)


@order_bp.route('/add-to-cart', methods=['POST'])
@login_required  # << --- THÊM LẠI DECORATOR NÀY
def add_to_cart():
    logger = current_app.logger
    try:
        if not request.is_json:
            logger.warning("'/add-to-cart' received non-JSON request.")
            return jsonify({'success': False, 'message': 'Yêu cầu không hợp lệ (Invalid Request)'}), 400

        data = request.get_json()
        product_id = data.get('product_id')
        try:
            quantity = int(data.get('quantity', 1))
            if quantity <= 0: quantity = 1
        except (ValueError, TypeError):
            quantity = 1
        notes = data.get('notes', '').strip()

        # user_log_id không cần thay đổi vì @login_required sẽ đảm bảo current_user tồn tại
        user_log_id = current_user.id
        logger.info(f"Add to cart request: ProductID={product_id}, Quantity={quantity}, User={user_log_id}")

        if not isinstance(product_id, int):
            logger.warning(f"Invalid product_id type received: {product_id}")
            return jsonify({'success': False, 'message': 'ID Sản phẩm không hợp lệ.'}), 400

        product = Product.query.get(product_id)
        if not product:
            logger.warning(f"Product ID {product_id} not found.")
            return jsonify({'success': False, 'message': 'Sản phẩm không tồn tại.'}), 404

        if not product.is_available:
            logger.warning(f"Attempted to add unavailable product ID {product_id} to cart.")
            return jsonify({'success': False, 'message': f"'{product.name}' hiện đang tạm hết hàng."}), 400

        cart = session.get('cart', [])
        updated = False
        for item in cart:
            if item.get('product_id') == product_id:
                item['quantity'] = item.get('quantity', 0) + quantity
                if notes: item['notes'] = notes
                updated = True
                logger.info(f"Updated quantity for product {product_id} in cart. New quantity: {item['quantity']}")
                break
        
        if not updated:
            cart.append({
                'product_id': product_id,
                'name': product.name,
                'price': float(product.price),
                'image_url': product.image_url or url_for('static', filename='images/default_product_thumb.png'),
                'quantity': quantity,
                'notes': notes
            })
            logger.info(f"Added new product {product_id} to cart.")

        session['cart'] = cart
        session.modified = True
        
        logger.info(f"Product '{product.name}' successfully added/updated in cart for User={user_log_id}")
        return jsonify({'success': True, 'message': f"Đã thêm '{product.name}' vào giỏ hàng!", 'cart_count': len(cart)})

    except Exception as e:
        logger.error(f"Error in add_to_cart: {e}", exc_info=True)
        if db and hasattr(db.session, 'is_active') and db.session.is_active:
            try: db.session.rollback()
            except Exception as dbe: logger.error(f"Error rolling back session: {dbe}")
        return jsonify({'success': False, 'message': 'Đã có lỗi xảy ra. Vui lòng thử lại.'}), 500


@order_bp.route('/update-cart', methods=['POST'])
def update_cart():
    if not request.is_json: return jsonify({'success': False, 'message': 'Yêu cầu không hợp lệ'}), 400
    data = request.get_json(); logger = current_app.logger
    product_id = data.get('product_id'); quantity = data.get('quantity')

    if not isinstance(product_id, int) and (isinstance(product_id, str) and not product_id.isdigit()):
        logger.warning(f"Update cart: Invalid product_id type or value '{product_id}'")
        return jsonify({'success': False, 'message': 'ID Sản phẩm không hợp lệ.'}), 400
    if isinstance(product_id, str): product_id = int(product_id) # Chuyển thành int nếu là chuỗi số

    try: quantity = int(quantity)
    except (ValueError, TypeError): logger.warning(f"Update cart: Invalid quantity '{quantity}'"); return jsonify({'success': False, 'message': 'Số lượng không hợp lệ'}), 400
    if quantity < 0: logger.warning(f"Update cart: Negative quantity '{quantity}'"); return jsonify({'success': False, 'message': 'Số lượng không hợp lệ'}), 400

    cart = session.get('cart', [])
    item_subtotal = 0.0; item_updated = False; new_cart = []
    
    for item in cart:
        if item.get('product_id') == product_id:
            if quantity > 0:
                 item['quantity'] = quantity
                 current_price = float(item.get('price', 0)) # Lấy giá đã lưu trong item
                 item_subtotal = current_price * quantity
                 # Không cần cập nhật 'subtotal' vào item session, vì calculate_cart_totals sẽ tính lại
                 new_cart.append(item); item_updated = True
            else: item_updated = True # Item bị xóa (quantity = 0)
        else: new_cart.append(item)

    if not item_updated and quantity > 0:
        logger.warning(f"Update cart: Product ID {product_id} not found in cart to update.")
        return jsonify({'success': False, 'message': 'Sản phẩm không có trong giỏ.'}), 404

    session['cart'] = new_cart; session.modified = True
    
    totals = calculate_cart_totals_for_session_display() # Sử dụng hàm mới này
    resp_data = { 'success': True, 'item_subtotal': f"{item_subtotal:.2f}" if quantity > 0 else "0.00", 'message': "Cập nhật giỏ hàng thành công."}
    resp_data.update(totals) # Gộp dicts
    if quantity == 0 : resp_data['item_removed'] = True; resp_data['message']="Đã xóa sản phẩm."
    
    return jsonify(resp_data)

def calculate_cart_totals_for_session_display():
    """
    Tính toán tổng giỏ hàng dựa trên dữ liệu đã có trong session.
    Hàm này sẽ đọc 'applied_promotion' từ session và tính toán discount.
    Cũng sẽ đọc 'current_order_type_for_total_calc' từ session để tính phí ship nếu có.
    """
    cart_session_list = session.get('cart', [])
    logger = current_app.logger
    cart_subtotal_float = 0.0
        
    for item in cart_session_list:
        price_item = float(item.get('price', 0)) # Giá đã được lưu dạng float khi thêm vào giỏ
        try:
            cart_subtotal_float += price_item * int(item.get('quantity', 1))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid item data in cart session: {item}, error: {e}")

    promo_in_session = session.get('applied_promotion')
    discount_amount_float = 0.0
    if promo_in_session:
        code_in_session = promo_in_session.get('code')
        if code_in_session:
            now = datetime.utcnow()
            valid_promo = Promotion.query.filter(
                func.upper(Promotion.code) == func.upper(code_in_session), # Case-insensitive search
                Promotion.is_active == True, Promotion.start_date <= now, Promotion.end_date >= now
            ).first()
            if valid_promo:
                if valid_promo.discount_percent:
                    discount_amount_float = cart_subtotal_float * (valid_promo.discount_percent / 100.0)
                elif valid_promo.discount_amount:
                    discount_amount_float = min(float(valid_promo.discount_amount), cart_subtotal_float)
                session['applied_promotion']['calculated_discount'] = round(discount_amount_float, 2)
                session.modified = True
                logger.debug(f"calculate_cart_totals: Recalculated discount for '{code_in_session}': {discount_amount_float}")
            else: # Mã trong session không còn hợp lệ
                logger.warning(f"calculate_cart_totals: Promo code '{code_in_session}' from session is no longer valid. Removing it.")
                session.pop('applied_promotion', None)
                session.modified = True
    
    subtotal_after_discount_float = cart_subtotal_float - discount_amount_float
    if subtotal_after_discount_float < 0: subtotal_after_discount_float = 0.0

    tax_rate_from_config = current_app.config.get('TAX_RATE', 0.1) # Mặc định 10%
    cart_tax_float = subtotal_after_discount_float * tax_rate_from_config
    
    shipping_fee_float = 0.0
    # Sử dụng 'current_order_type_for_total_calc' từ session mà JS đã set
    if session.get('current_order_type_for_total_calc') == 'delivery':
         shipping_fee_float = float(current_app.config.get('DEFAULT_SHIPPING_FEE', 20000.0))

    cart_total_float = subtotal_after_discount_float + cart_tax_float + shipping_fee_float
    
    logger.debug(f"Calculated totals for display: Sub={cart_subtotal_float}, Disc={discount_amount_float}, SubAfterDisc={subtotal_after_discount_float}, Tax={cart_tax_float}, Ship={shipping_fee_float}, Total={cart_total_float}")

    return {
        "cart_subtotal": f"{cart_subtotal_float:.2f}", 
        "discount_amount": f"{discount_amount_float:.2f}",
        # "subtotal_after_discount": f"{subtotal_after_discount_float:.2f}", # Thường không cần hiển thị trực tiếp
        "cart_tax": f"{cart_tax_float:.2f}", 
        "shipping_fee": f"{shipping_fee_float:.2f}", # Thêm phí ship vào response
        "cart_total": f"{cart_total_float:.2f}",
        "cart_count": len(cart_session_list)
    }


# Hàm helper để tính tổng giỏ hàng (tránh lặp code)
def calculate_cart_totals(cart_list):
    subtotal = 0.0
    product_ids = [item.get('product_id') for item in cart_list if item.get('product_id')]
    if product_ids:
        products_map = {p.id: p.price for p in Product.query.filter(Product.id.in_(product_ids)).all()}
        for item in cart_list:
            price = products_map.get(item['product_id'])
            if price:
                 try:
                     subtotal += float(price) * int(item.get('quantity', 1))
                 except (ValueError, TypeError):
                     pass # Ignore items with invalid data silently for calculation
    tax = subtotal * 0.1
    total = subtotal + tax
    return subtotal, tax, total


@order_bp.route('/remove-from-cart/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    cart = session.get('cart', [])
    original_length = len(cart)
    new_cart = [item for item in cart if item.get('product_id') != product_id]
    if len(new_cart) < original_length:
        session['cart'] = new_cart
        session.modified = True
        totals = calculate_cart_totals_for_session_display()
        return jsonify({**{'success': True, 'message': 'Đã xóa sản phẩm.'}, **totals})
    else:
        totals = calculate_cart_totals_for_session_display() 
        return jsonify({**{'success': False, 'message': 'Sản phẩm không có trong giỏ.'}, **totals}), 404


@order_bp.route('/clear-cart', methods=['POST'])
def clear_cart():
    session.pop('cart', None)
    session.pop('applied_promotion', None)
    session.modified = True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
         return jsonify({
             'success': True, 'message': 'Giỏ hàng đã được xóa.', 
             'cart_count': 0, 'cart_subtotal': "0.00", 'discount_amount': "0.00",
             'cart_tax': "0.00", 'shipping_fee': "0.00", 'cart_total': "0.00"
             })
    else:
        flash('Đã xóa toàn bộ giỏ hàng.', 'success')
        return redirect(url_for('order.cart'))


@order_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    logger = current_app.logger
    cart_list = session.get('cart', [])
    if not cart_list:
        flash('Giỏ hàng trống, không thể thanh toán.', 'warning')
        return redirect(url_for('main.menu'))

    # === Lấy giá trị config để truyền vào template ===
    tax_rate_config = current_app.config.get('TAX_RATE', 0.1)
    default_shipping_fee_config = float(current_app.config.get('DEFAULT_SHIPPING_FEE', 20000.0)) # Đảm bảo là float
    shop_hotline_config = current_app.config.get('SHOP_HOTLINE', '1900-DRAGON')
    shop_feedback_email_config = current_app.config.get('SHOP_FEEDBACK_EMAIL', 'feedback@dragoncoffee.com')
    # === Kết thúc lấy config ===

    products_in_cart_display = []
    valid_cart_items_for_order = []
    total_base_amount_float = 0.0

    product_ids = [item.get('product_id') for item in cart_list if item.get('product_id')]
    if product_ids:
        # Lấy thông tin product mới nhất từ DB
        products_map = {p.id: p for p in Product.query.filter(Product.id.in_(product_ids)).all()}
        updated_session_cart = []
        for item_data_from_session in cart_list:
            product_id_from_session = item_data_from_session.get('product_id')
            if not isinstance(product_id_from_session, int): continue
            
            product_from_db = products_map.get(product_id_from_session)
            if product_from_db and product_from_db.is_available:
                try:
                     qty = int(item_data_from_session.get('quantity', 1))
                     if qty <= 0: continue
                     
                     # QUAN TRỌNG: Luôn dùng giá từ DB cho đơn hàng
                     current_product_price_float = float(product_from_db.price)
                     sub_float = current_product_price_float * qty
                     total_base_amount_float += sub_float
                     
                     # Item để hiển thị và lưu vào OrderDetail
                     item_info_for_order = {
                        'product_id': product_from_db.id, 'name': product_from_db.name, 
                        'price': current_product_price_float, # Giá đơn vị thực tế từ DB
                        'quantity': qty, 'subtotal': sub_float,
                        'image_url': product_from_db.image_url, 'notes': item_data_from_session.get('notes', '')
                     }
                     products_in_cart_display.append(item_info_for_order)
                     valid_cart_items_for_order.append({**item_info_for_order, 'unit_price': current_product_price_float})
                     
                     # Item để cập nhật lại session (giá từ DB, các thông tin khác giữ nguyên từ session nếu có)
                     updated_session_cart.append({
                        'product_id': product_from_db.id, 'quantity': qty, 
                        'notes': item_data_from_session.get('notes',''),
                        'name': product_from_db.name, 
                        'price': current_product_price_float, # Cập nhật giá từ DB vào session
                        'image_url': product_from_db.image_url or url_for('static', filename='images/default_product_thumb.png')
                     })
                except (ValueError, TypeError) as e:
                     logger.warning(f"Invalid quantity or price for product ID {product_id_from_session} in cart during checkout prep: {e}")
                     continue
            else: # Sản phẩm không tồn tại hoặc không available nữa
                logger.warning(f"Checkout: Product ID {product_id_from_session} from cart session is invalid/unavailable. Removing from current checkout process.")
        
        # Cập nhật lại session nếu có thay đổi giá hoặc sản phẩm bị loại bỏ
        if len(updated_session_cart) != len(cart_list) or \
           any(sc_item['price'] != dict((i['product_id'],i['price']) for i in cart_list).get(sc_item['product_id']) for sc_item in updated_session_cart):
            session['cart'] = updated_session_cart
            session.modified = True
            if len(updated_session_cart) < len(cart_list):
                 flash("Một vài sản phẩm trong giỏ không còn hợp lệ và đã được tự động cập nhật/xóa.", "info")
            elif any(sc_item['price'] != dict((i['product_id'],i['price']) for i in cart_list).get(sc_item['product_id']) for sc_item in updated_session_cart):
                 flash("Giá của một số sản phẩm trong giỏ đã được cập nhật theo giá hiện tại.", "info")


    if not valid_cart_items_for_order:
        flash('Các sản phẩm trong giỏ không hợp lệ hoặc đã hết hàng. Vui lòng chọn lại.', 'danger')
        session.pop('cart', None); session.pop('applied_promotion', None); session.modified = True
        return redirect(url_for('main.menu'))

    form_data_on_error = None
    available_promotions = []
    now_utc = datetime.utcnow()
    try:
        available_promotions = Promotion.query.filter(
            Promotion.is_active == True, Promotion.start_date <= now_utc, Promotion.end_date >= now_utc
        ).order_by(Promotion.name).all()
    except Exception as e:
        logger.error(f"Error fetching promotions: {e}", exc_info=True)

    render_context_base = {
        'cart_items': products_in_cart_display,
        'total': total_base_amount_float, # Tổng tiền hàng gốc (chưa KM, chưa thuế, chưa ship)
        'available_promotions': available_promotions,
        'format_price': format_currency,
        'CONFIG_TAX_RATE': tax_rate_config,
        'CONFIG_DEFAULT_SHIPPING_FEE': default_shipping_fee_config,
        'CONFIG_SHOP_HOTLINE': shop_hotline_config,
        'CONFIG_SHOP_FEEDBACK_EMAIL': shop_feedback_email_config
    }

    if request.method == 'POST':
        form_data_on_error = request.form.to_dict()
        logger.info("Processing checkout POST request...")
        # ... (logic validation form như cũ) ...
        order_type = request.form.get('order_type', 'takeaway')
        payment_method = request.form.get('payment_method', 'cash')
        notes = request.form.get('notes', '').strip()
        address = request.form.get('address', '').strip() if order_type == 'delivery' else None
        contact_phone = request.form.get('phone', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        errors = {}
        if not name: errors['name'] = 'Vui lòng nhập tên.'
        if not email: errors['email'] = 'Vui lòng nhập địa chỉ email.'
        if order_type == 'delivery' and not address: errors['address'] = 'Vui lòng nhập địa chỉ giao hàng.'
        if not contact_phone: errors['phone'] = 'Vui lòng nhập số điện thoại liên hệ.'
        
        # Recalculate totals before saving order, always trust server-side calculation
        # total_base_amount_float is already the sum of latest prices * quantities from cart

        calculated_discount_float = 0.0
        promotion_id_to_save = None
        promotion_code_to_save = None
        
        promo_in_session = session.get('applied_promotion')
        if promo_in_session:
            code_in_session = promo_in_session.get('code')
            if code_in_session:
                valid_promo = Promotion.query.filter(
                    func.upper(Promotion.code) == func.upper(code_in_session),
                    Promotion.is_active == True, Promotion.start_date <= now_utc, Promotion.end_date >= now_utc
                ).first()
                if valid_promo:
                    if valid_promo.discount_percent:
                        calculated_discount_float = total_base_amount_float * (valid_promo.discount_percent / 100.0)
                    elif valid_promo.discount_amount:
                        calculated_discount_float = min(float(valid_promo.discount_amount), total_base_amount_float)
                    
                    calculated_discount_float = round(calculated_discount_float, 2)
                    promotion_id_to_save = valid_promo.id
                    promotion_code_to_save = valid_promo.code
                    logger.info(f"Checkout POST: Promo '{code_in_session}' still valid. Discount: {calculated_discount_float}")
                else: # Mã trong session không còn hợp lệ
                    logger.warning(f"Checkout POST: Promo code '{code_in_session}' from session no longer valid. Discarding.")
                    session.pop('applied_promotion', None); session.modified = True
        
        if errors:
            for field, msg in errors.items(): flash(msg, 'danger')
            render_context_error = {**render_context_base, 'promo_applied': promo_in_session, 'form_data': form_data_on_error}
            return render_template('checkout.html', **render_context_error)


        subtotal_after_discount_float = total_base_amount_float - calculated_discount_float
        if subtotal_after_discount_float < 0 : subtotal_after_discount_float = 0.0
        
        tax_amount_float = subtotal_after_discount_float * tax_rate_config
        shipping_fee_float = default_shipping_fee_config if order_type == 'delivery' else 0.0
        final_amount_calculated_float = subtotal_after_discount_float + tax_amount_float + shipping_fee_float

        logger.info(f"Checkout Final Save Calculation: Base={total_base_amount_float}, Disc={calculated_discount_float}, SubAfterDisc={subtotal_after_discount_float}, Tax={tax_amount_float}, Ship={shipping_fee_float}, Final={final_amount_calculated_float}")

        try:
            # db.session.begin_nested() không cần thiết nếu không có try...except bên trong,
            # Flask-SQLAlchemy tự quản lý transaction cho mỗi request.
            # Nếu có lỗi, db.session.rollback() ở cuối là đủ.
            
            new_order = Order(
                user_id=current_user.id, order_number=generate_order_number(), status='pending',
                total_amount=round(total_base_amount_float,2), 
                final_amount=round(final_amount_calculated_float,2),
                order_type=order_type, payment_method=payment_method, payment_status='pending',
                notes=notes or None, address=address, contact_phone=contact_phone,
                promotion_id=promotion_id_to_save, promotion_code_used=promotion_code_to_save,
                discount_applied=calculated_discount_float if calculated_discount_float > 0 else None,
                shipping_fee=round(shipping_fee_float,2) if shipping_fee_float > 0 else None,
                tax_amount=round(tax_amount_float,2) if tax_amount_float > 0 else None
            )
            db.session.add(new_order); db.session.flush()
            
            for item_data in valid_cart_items_for_order: # Dùng valid_cart_items_for_order chứa giá đúng
                detail = OrderDetail(order_id=new_order.id, product_id=item_data['product_id'],
                                     quantity=item_data['quantity'], unit_price=item_data['unit_price'], # unit_price từ valid_cart_items...
                                     subtotal=item_data['subtotal'], notes=item_data['notes'] or None)
                db.session.add(detail)
                inv_item = db.session.query(InventoryItem).filter_by(product_id=item_data['product_id']).with_for_update().first()
                if inv_item:
                    if inv_item.quantity >= item_data['quantity']: 
                        inv_item.quantity -= item_data['quantity']; inv_item.last_updated = datetime.utcnow()
                    else: 
                        # Lỗi này KHÔNG nên xảy ra nếu đã check is_available và tồn kho khi add to cart
                        # và check lại khi chuẩn bị valid_cart_items_for_order
                        logger.error(f"CRITICAL STOCK INCONSISTENCY at order commit. Product ID {item_data['product_id']}, Order {new_order.order_number}. Req: {item_data['quantity']}, Avail: {inv_item.quantity}")
                        raise Exception(f"Hết hàng đột ngột cho '{item_data['name']}'.") # Ném lỗi để rollback
                else: logger.warning(f"No InventoryItem found for product {item_data['product_id']} at stock decrement for order {new_order.order_number}.")
            
            db.session.commit()
            logger.info(f"Order {new_order.order_number} (UID: {current_user.id}) CREATED. Promo: {promotion_code_to_save}, Disc: {calculated_discount_float}")
            session.pop('cart', None); session.pop('applied_promotion', None); session.pop('current_order_type_for_total_calc',None); session.modified = True
            flash('Đặt hàng thành công!', 'success'); 
            # send_order_status_email(new_order) # Có thể gửi email ở đây
            return redirect(url_for('order.order_confirmation', order_id=new_order.id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Checkout final commit failed for user {current_user.id}: {e}", exc_info=True)
            flash(f'Lỗi nghiêm trọng khi xử lý đơn hàng: {str(e)}. Vui lòng thử lại sau.', 'danger')
            render_context_exception = {**render_context_base, 'promo_applied': session.get('applied_promotion'), 'form_data': form_data_on_error}
            return render_template('checkout.html', **render_context_exception)

    # GET Request Logic
    logger.info(f"User {current_user.id} accessing checkout page (GET).")
    
    # Xử lý promo_applied cho GET request (phải tính lại discount dựa trên total_base_amount_float)
    promo_applied_for_get = None
    if session.get('applied_promotion'):
        code_in_session_get = session['applied_promotion'].get('code')
        valid_promo_get = Promotion.query.filter(func.upper(Promotion.code)==func.upper(code_in_session_get),Promotion.is_active==True,Promotion.start_date<=now_utc,Promotion.end_date>=now_utc).first()
        if valid_promo_get:
            promo_applied_for_get = {'id':valid_promo_get.id, 'code':valid_promo_get.code, 'name': valid_promo_get.name, 'calculated_discount': 0}
            discount_for_get = 0.0
            if valid_promo_get.discount_percent: discount_for_get = total_base_amount_float * (valid_promo_get.discount_percent / 100.0)
            elif valid_promo_get.discount_amount: discount_for_get = min(float(valid_promo_get.discount_amount), total_base_amount_float)
            promo_applied_for_get['calculated_discount'] = round(discount_for_get,2)
            session['applied_promotion'] = promo_applied_for_get # Cập nhật lại session với discount đúng
            session.modified = True
        else: # Mã không còn hợp lệ
            session.pop('applied_promotion', None); session.modified = True

    # Lưu trữ order_type đã chọn từ trước vào session storage để JS đọc khi tải lại trang
    session['current_order_type_for_total_calc'] = request.form.get('order_type', session.get('current_order_type_for_total_calc', 'takeaway'))
    
    render_context_get = {**render_context_base, 'promo_applied': session.get('applied_promotion')} # Lấy lại từ session sau khi có thể đã update
    return render_template('checkout.html', **render_context_get)



# Route này nên được tạo để chuyển hướng sau khi checkout thành công
@order_bp.route('/confirmation/<int:order_id>')
@login_required
def order_confirmation(order_id):
    logger = current_app.logger
    order = db.session.get(Order, order_id) 
    if not order: logger.warning(f"Confirmation: Order ID {order_id} not found."); flash('Không tìm thấy đơn hàng.', 'danger'); return redirect(url_for('order.my_orders'))
    is_admin_or_staff = (hasattr(current_user, 'is_admin') and current_user.is_admin) or (hasattr(current_user, 'is_staff') and current_user.is_staff)
    if order.user_id != current_user.id and not is_admin_or_staff:
        logger.warning(f"Confirmation: User {current_user.id} unauthorized for order {order_id}."); flash('Bạn không có quyền xem xác nhận đơn hàng này.', 'danger'); return redirect(url_for('order.my_orders'))
    
    order_details_list = OrderDetail.query.options(joinedload(OrderDetail.ordered_product)).filter(OrderDetail.order_id == order_id).all()
    products_for_display = []
    for detail in order_details_list:
        if detail.ordered_product:
            subtotal = float(detail.unit_price or 0) * int(detail.quantity or 0)
            products_for_display.append({'name': detail.ordered_product.name,'quantity': detail.quantity,'price': detail.unit_price,'subtotal': subtotal,'notes': detail.notes})
        else: logger.warning(f"Confirmation Order {order_id}: Product ID {detail.product_id} on detail {detail.id} missing.")
            
    return render_template('order_confirmation.html', order=order, products=products_for_display, format_price=format_currency)

@order_bp.route('/orders') # <-- Đường dẫn URL
@login_required
def my_orders(): # <-- Tên hàm này sẽ tạo ra endpoint 'order.my_orders'
    logger = current_app.logger
    logger.info(f"User {current_user.id} accessing their orders page.")
    page = request.args.get('page', 1, type=int)
    per_page = 10 
    
    orders_pagination = None # Khởi tạo trước khi try
    try:
        orders_pagination = Order.query.filter_by(user_id=current_user.id)\
                                     .order_by(Order.created_at.desc())\
                                     .paginate(page=page, per_page=per_page, error_out=False)
        
    except Exception as e:
        logger.error(f"Error fetching orders for user {current_user.id}: {e}", exc_info=True)
        # orders_pagination vẫn là None nếu lỗi
        flash("Lỗi khi tải danh sách đơn hàng. Vui lòng thử lại.", "danger")

    return render_template('my_orders.html', 
                           orders=orders_pagination.items if orders_pagination else [], 
                           pagination=orders_pagination, # Truyền đối tượng pagination
                           format_price=format_currency)

@order_bp.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    # ... (logic hiện tại của bạn)
    # Đảm bảo `order_details_list` và `order` được truyền đúng
    logger = current_app.logger
    order = db.session.get(Order, order_id)
    if not order:
        logger.warning(f"Order detail: Order ID {order_id} not found.")
        flash('Không tìm thấy đơn hàng.', 'danger')
        return redirect(url_for('order.my_orders'))
    is_admin_or_staff = (hasattr(current_user, 'is_admin') and current_user.is_admin) or \
                        (hasattr(current_user, 'is_staff') and current_user.is_staff)
    if order.user_id != current_user.id and not is_admin_or_staff:
        logger.warning(f"Order detail: User {current_user.id} unauthorized access to order {order_id}.")
        flash('Bạn không có quyền xem đơn hàng này.', 'danger')
        return redirect(url_for('order.my_orders'))
    order_details_list = OrderDetail.query.options(joinedload(OrderDetail.ordered_product))\
                              .filter_by(order_id=order_id).all()
    return render_template('order_detail.html', order=order, order_details=order_details_list, format_price=format_currency)

@order_bp.route('/api/order-status/<string:order_number>')
def api_order_status(order_number):
    # ... (logic hiện tại của bạn) ...
    # Không cần thay đổi
    logger = current_app.logger
    try:
        order = Order.query.filter(func.upper(Order.order_number) == func.upper(order_number)).first()
        if order:
            return jsonify({
                'success': True, 'order_number': order.order_number,
                'status': order.status, 'status_display': order.get_status_display(),
                'payment_status': order.payment_status,
                'order_date': order.created_at.strftime('%d/%m/%Y %H:%M') if order.created_at else None,
                'total_amount': order.final_amount if order.final_amount is not None else order.total_amount
            })
        else:
            return jsonify({'success': False, 'message': 'Không tìm thấy đơn hàng.'}), 404
    except Exception as e:
        logger.error(f"Error fetching order status for {order_number}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Lỗi hệ thống khi kiểm tra đơn hàng.'}), 500

@order_bp.route('/cart-count')
def cart_count():
    # Sử dụng hàm helper tính totals để lấy count (an toàn hơn là chỉ len)
    totals = calculate_cart_totals_for_session_display()
    return jsonify({'count': totals.get('cart_count', 0)})


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    # ... (logic hiện tại của bạn)
    logger = current_app.logger
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and not (hasattr(current_user, 'is_admin') and current_user.is_admin):
        flash("Bạn không có quyền hủy đơn hàng này.", "danger")
        return redirect(url_for('order.my_orders'))
    if order.status not in ['pending', 'processing']:
        flash(f"Đơn hàng #{order.order_number} không thể hủy.", "warning")
        return redirect(url_for('order.order_detail', order_id=order_id))
    try:
        with db.session.begin_nested(): # Đảm bảo transaction an toàn cho stock
            order.status = 'cancelled'
            order.updated_at = datetime.utcnow()
            for detail in order.details:
                if detail.product_id: 
                    inventory_item = db.session.query(InventoryItem).filter_by(product_id=detail.product_id).with_for_update().first()
                    if inventory_item:
                        inventory_item.quantity += detail.quantity
                        inventory_item.last_updated = datetime.utcnow()
                    else: logger.warning(f"Inv item not found for product {detail.product_id} (Order {order_id} cancel).")
            if order.payment_status == 'completed' or order.payment_status == 'paid':
                 order.payment_status = 'refunded'
        db.session.commit()
        flash(f"Đã hủy đơn hàng #{order.order_number}.", "success")
        send_order_status_email(order) 
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error cancelling order {order_id}: {e}", exc_info=True)
        flash("Lỗi hủy đơn hàng.", "danger")
    return redirect(url_for('order.order_detail', order_id=order_id))


@order_bp.route('/apply-promo', methods=['POST'])
def apply_promo_code(): # Bỏ @login_required để khách có thể thử KM, chỉ check login khi checkout
    logger = current_app.logger; data = request.get_json(); cart_list = session.get('cart', [])
    if not data or 'promo_code' not in data: return jsonify({'success': False, 'message': 'Thiếu mã KM.'}), 400
    code_input = data['promo_code'].strip().upper()
    user_log = current_user.id if current_user.is_authenticated else session.get('guest_session_id', 'Guest')
    logger.info(f"User/Session {user_log} applying promo: {code_input}")
    if not cart_list: return jsonify({'success': False, 'message': 'Giỏ hàng trống.'}), 400

    now = datetime.utcnow()
    promo = Promotion.query.filter(Promotion.code == code_input, Promotion.is_active == True, 
                                  Promotion.start_date <= now, Promotion.end_date >= now).first()
    
    # Luôn tính totals mới nhất, bất kể KM có hợp lệ hay không để trả về UI
    # Gọi hàm này sau khi đã POP KM cũ (nếu có và không hợp lệ) ra khỏi session
    if not promo: # Mã không hợp lệ hoặc hết hạn
        if 'applied_promotion' in session: # Nếu có KM cũ đang áp dụng thì bỏ nó đi
             old_promo_code = session.pop('applied_promotion', {}).get('code')
             session.modified = True
             logger.info(f"Invalid promo '{code_input}' applied, removed old promo '{old_promo_code}' from session.")
        else:
             logger.warning(f"Invalid promo code '{code_input}' applied.")
        
        totals_no_promo = calculate_cart_totals_for_session_display() # Tính lại total khi không có KM
        return jsonify({**{'success': False, 'message': 'Mã khuyến mãi không hợp lệ hoặc đã hết hạn.'}, **totals_no_promo}), 400

    # Mã hợp lệ, lấy tổng tiền hàng gốc để tính discount
    subtotal_base_float = 0.0
    for item_in_cart_session in cart_list:
        try: subtotal_base_float += float(item_in_cart_session.get('price',0)) * int(item_in_cart_session.get('quantity',1))
        except: pass # Bỏ qua lỗi nếu item trong session không đúng format
    
    discount_amount_calculated = 0.0
    if promo.discount_percent: discount_amount_calculated = subtotal_base_float * (promo.discount_percent / 100.0)
    elif promo.discount_amount: discount_amount_calculated = min(float(promo.discount_amount), subtotal_base_float)
    
    session['applied_promotion'] = { 'id': promo.id, 'code': promo.code, 'name': promo.name, 
                                     'calculated_discount': round(discount_amount_calculated, 2) }
    session.modified = True
    totals_with_promo = calculate_cart_totals_for_session_display() # Hàm này sẽ đọc session KM
    
    logger.info(f"Promo '{promo.code}' applied. Discount: {discount_amount_calculated}. New Cart Total: {totals_with_promo.get('cart_total')}")
    return jsonify({**{'success': True, 'message': f'Đã áp dụng "{promo.name}"!', 
                      'promo_code': promo.code, 'promo_name': promo.name }, **totals_with_promo})


@order_bp.route('/remove-promo', methods=['POST'])
def remove_promo_code(): # Bỏ @login_required
    logger = current_app.logger; removed = False
    if 'applied_promotion' in session:
        removed_code = session.pop('applied_promotion', {}).get('code','N/A')
        session.modified = True
        user_log = current_user.id if current_user.is_authenticated else session.get('guest_session_id', 'Guest')
        logger.info(f"User/Session {user_log} removed promo: {removed_code}"); removed = True
    
    totals_after_remove = calculate_cart_totals_for_session_display() # Tính lại khi không còn KM
    message = 'Đã gỡ bỏ mã giảm giá.' if removed else 'Không có mã giảm giá nào đang được áp dụng.'
    return jsonify({**{'success': True, 'message': message}, **totals_after_remove})

@order_bp.route('/api/recent-orders') # URL prefix /order sẽ được tự động thêm vào đây
@login_required
def api_recent_orders():
    logger = current_app.logger
    logger.info(f"API: User {current_user.id} requesting recent orders.")
    try:
        recent_orders = Order.query.filter_by(user_id=current_user.id)\
                                 .order_by(Order.created_at.desc())\
                                 .limit(5).all() # Giới hạn 5 đơn hàng gần nhất

        orders_data = []
        if recent_orders:
            for order in recent_orders:
                details_data = []
                order_details = OrderDetail.query.options(joinedload(OrderDetail.ordered_product))\
                                            .filter_by(order_id=order.id).all()
                for detail in order_details:
                    if detail.ordered_product:
                        details_data.append({
                            'product_id': detail.product_id,
                            'name': detail.ordered_product.name,
                            'quantity': detail.quantity, # Số lượng đã mua lần đó
                            'price_at_purchase': detail.unit_price,
                            'image_url': detail.ordered_product.image_url or url_for('static', filename='images/default_product_thumb.png')
                        })

                orders_data.append({
                    'id': order.id, # Vẫn giữ id đơn hàng cho mục đích khác nếu cần
                    'order_number': order.order_number,
                    'created_at': order.created_at.strftime('%H:%M %d/%m/%Y') if order.created_at else 'N/A', # Định dạng giờ:phút ngày/tháng/năm
                    # 'total_amount_formatted': format_currency(order.final_amount or order.total_amount), # Bỏ vì không hiển thị
                    # 'status_display': order.get_status_display(), # Bỏ vì không hiển thị
                    'items': details_data
                })
        return jsonify({'success': True, 'orders': orders_data})
    except Exception as e:
        logger.error(f"API: Error fetching recent orders for user {current_user.id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Không thể tải lịch sử đơn hàng.'}), 500