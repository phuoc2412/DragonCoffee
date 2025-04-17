# /routes/order_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from flask_login import login_required, current_user
from models import Product, Order, OrderDetail, db, InventoryItem, Promotion # Đảm bảo db được import
from datetime import datetime
import uuid
from utils import generate_order_number, format_currency, send_order_status_email
import logging
from sqlalchemy import func
import logging # Thêm logging
from sqlalchemy.orm import joinedload

order_bp = Blueprint('order', __name__, url_prefix='/order') # <-- Thêm prefix

@order_bp.route('/cart')
def cart():
    # ... (logic hiển thị giỏ hàng giữ nguyên) ...
    cart_items_data = session.get('cart', [])
    total = 0
    products = []
    product_ids = [item['product_id'] for item in cart_items_data]

    if product_ids:
        # Query tất cả sản phẩm một lần
        products_in_db = Product.query.filter(Product.id.in_(product_ids)).all()
        products_map = {p.id: p for p in products_in_db}

        for item_data in cart_items_data:
            product = products_map.get(item_data['product_id'])
            if product:
                quantity = item_data.get('quantity', 1) # Lấy số lượng từ session
                subtotal = product.price * quantity
                total += subtotal
                products.append({
                    'id': product.id,
                    'name': product.name,
                    'price': product.price,
                    'quantity': quantity,
                    'subtotal': subtotal,
                    'image_url': product.image_url,
                    'notes': item_data.get('notes', '')
                })
            else:
                 # Nếu sản phẩm không còn tồn tại, nên có cơ chế xóa khỏi giỏ hàng session
                 logger = current_app.logger if current_app else logging.getLogger()
                 logger.warning(f"Product ID {item_data['product_id']} found in cart session but not in DB. Skipping.")
                 # Nên thêm logic xóa item lỗi khỏi session['cart'] ở đây

    return render_template('cart.html', cart_items=products, total=total)


@order_bp.route('/add-to-cart', methods=['POST'])
@login_required # <-- ĐẢM BẢO DECORATOR NÀY ĐANG HOẠT ĐỘNG
def add_to_cart():
    logger = current_app.logger
    # --- **SỬA Ở ĐÂY: Nhận dữ liệu từ JSON thay vì Form** ---
    if not request.is_json:
        logger.warning("'/add-to-cart' received non-JSON request.")
        return jsonify({'success': False, 'message': 'Yêu cầu không hợp lệ (Invalid Request)'}), 400

    data = request.get_json()
    product_id = data.get('product_id')
    # Ép kiểu an toàn, mặc định là 1
    try:
        quantity = int(data.get('quantity', 1))
        if quantity <= 0: quantity = 1 # Số lượng tối thiểu là 1
    except (ValueError, TypeError):
        quantity = 1
    notes = data.get('notes', '').strip() # Lấy notes và xóa khoảng trắng thừa

    logger.info(f"Add to cart request: ProductID={product_id}, Quantity={quantity}, User={current_user.id}")

    if not isinstance(product_id, int):
        logger.warning(f"Invalid product_id type received: {product_id}")
        return jsonify({'success': False, 'message': 'ID Sản phẩm không hợp lệ.'}), 400

    # --- Logic xử lý sản phẩm và giỏ hàng giữ nguyên ---
    product = Product.query.get(product_id) # Dùng get() để trả None nếu không tìm thấy
    if not product:
        logger.warning(f"Product ID {product_id} not found.")
        return jsonify({'success': False, 'message': 'Sản phẩm không tồn tại.'}), 404

    if not product.is_available:
        logger.warning(f"Attempted to add unavailable product ID {product_id} to cart.")
        return jsonify({'success': False, 'message': f"'{product.name}' hiện đang tạm hết hàng."}), 400

    cart = session.get('cart', [])

    updated = False
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] = item.get('quantity', 0) + quantity # Cộng dồn số lượng
            if notes: item['notes'] = notes # Cập nhật ghi chú mới nhất (hoặc nối?)
            updated = True
            logger.info(f"Updated quantity for product {product_id} in cart. New quantity: {item['quantity']}")
            break

    if not updated:
        cart.append({
            'product_id': product_id,
            'quantity': quantity,
            'notes': notes
        })
        logger.info(f"Added new product {product_id} to cart.")

    session['cart'] = cart
    session.modified = True # Quan trọng!

    # --- **SỬA Ở ĐÂY: Trả về JSON thay vì Flash/Redirect** ---
    logger.info(f"Product '{product.name}' successfully added/updated in cart for user {current_user.id}")
    return jsonify({'success': True, 'message': f"Đã thêm '{product.name}' vào giỏ hàng!"})
    # -------------------------------------------------------


@order_bp.route('/update-cart', methods=['POST'])
def update_cart():
    # --- **SỬA: Nhận JSON** ---
    if not request.is_json:
         return jsonify({'success': False, 'message': 'Yêu cầu không hợp lệ'}), 400
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity')
    # --- Kết thúc sửa ---

    if not isinstance(product_id, int): return jsonify({'success': False, 'message': 'ID Sản phẩm không hợp lệ'}), 400
    try: quantity = int(quantity)
    except (ValueError, TypeError): return jsonify({'success': False, 'message': 'Số lượng không hợp lệ'}), 400

    if quantity < 0: return jsonify({'success': False, 'message': 'Số lượng không hợp lệ'}), 400

    cart = session.get('cart', [])
    item_subtotal = 0.0
    item_found_and_updated = False

    # Dùng list comprehension để cập nhật/xóa hiệu quả hơn
    new_cart = []
    for item in cart:
        if item['product_id'] == product_id:
            if quantity > 0: # Update quantity
                 item['quantity'] = quantity
                 product = Product.query.get(product_id)
                 if product: item_subtotal = product.price * quantity
                 new_cart.append(item) # Giữ lại item đã update
                 item_found_and_updated = True
            # else: quantity == 0 -> Xóa item (không cần làm gì, chỉ cần không append vào new_cart)
            else:
                 item_found_and_updated = True # Đánh dấu là đã xử lý (xóa)
        else:
            new_cart.append(item) # Giữ lại các item khác

    # Nếu không tìm thấy item để update và quantity > 0 -> đây là lỗi?
    if not item_found_and_updated and quantity > 0:
         # Nên báo lỗi hay thêm mới? Tùy logic mong muốn. Hiện tại báo lỗi.
         return jsonify({'success': False, 'message': 'Sản phẩm không tìm thấy trong giỏ để cập nhật.'}), 404


    session['cart'] = new_cart
    session.modified = True

    # Tính toán lại tổng giỏ hàng SAU KHI cập nhật session
    cart_subtotal_calc, cart_tax_calc, cart_total_calc = calculate_cart_totals(new_cart)

    response_data = {
        'success': True,
        'item_subtotal': "{:.2f}".format(item_subtotal) if quantity > 0 else "0.00",
        'cart_subtotal': "{:.2f}".format(cart_subtotal_calc),
        'cart_tax': "{:.2f}".format(cart_tax_calc),
        'cart_total': "{:.2f}".format(cart_total_calc),
        'cart_count': len(session['cart'])
    }
    if quantity == 0:
         response_data['item_removed'] = True
         response_data['message'] = "Đã xóa sản phẩm khỏi giỏ."
    else:
         response_data['message'] = "Đã cập nhật giỏ hàng."

    return jsonify(response_data)

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
@login_required # Giữ lại nếu cần đăng nhập để xóa
def remove_from_cart(product_id):
    cart = session.get('cart', [])
    original_length = len(cart)
    new_cart = [item for item in cart if item.get('product_id') != product_id]

    if len(new_cart) < original_length:
        session['cart'] = new_cart
        session.modified = True
        subtotal, tax, total = calculate_cart_totals(new_cart)
        # *** LUÔN TRẢ VỀ JSON THÀNH CÔNG ***
        return jsonify({
            'success': True,
            'message': 'Đã xóa sản phẩm.',
            'cart_count': len(new_cart),
            'cart_subtotal': "{:.2f}".format(subtotal),
            'cart_tax': "{:.2f}".format(tax),
            'cart_total': "{:.2f}".format(total)
        })
    else:
        # Sản phẩm không có trong giỏ để xóa
        subtotal, tax, total = calculate_cart_totals(new_cart)
        # *** LUÔN TRẢ VỀ JSON LỖI ***
        return jsonify({
            'success': False,
            'message': 'Sản phẩm không có trong giỏ.',
            'cart_count': len(new_cart),
            'cart_subtotal': "{:.2f}".format(subtotal),
            'cart_tax': "{:.2f}".format(tax),
            'cart_total': "{:.2f}".format(total)
            }), 404 # Trả về status code 404 Not Found hợp lý

@order_bp.route('/clear-cart', methods=['POST'])
def clear_cart():
    session.pop('cart', None)
    # Trả về JSON nếu là AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
         return jsonify({'success': True, 'message': 'Giỏ hàng đã được xóa.', 'cart_count': 0})
    else:
        flash('Đã xóa toàn bộ giỏ hàng.', 'success')
        return redirect(url_for('order.cart'))


@order_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    # ... (toàn bộ code của hàm checkout giữ nguyên như bạn đã cung cấp ở lần trước)
    # Chỗ sử dụng format_currency trong render_template bây giờ sẽ hợp lệ
    # Ví dụ ở phần xử lý lỗi và render lại form:
    # return render_template('checkout.html',
    #                        cart_items=products_in_cart_display,
    #                        total=total_base_amount,
    #                        promo_applied=promo_applied_data,
    #                        form_data=form_data_on_error,
    #                        format_price=format_currency, # <<< OKAY
    #                        error_message="Lỗi hệ thống, vui lòng thử lại.")

    # Và ở phần render cho GET request
    # return render_template('checkout.html',
    #                        cart_items=products_in_cart_display,
    #                        total=total_base_amount,
    #                        promo_applied=promo_applied_data,
    #                        format_price=format_currency) # <<< OKAY

    # === Bắt đầu logic hàm checkout ===
    logger = current_app.logger
    cart_list = session.get('cart', [])
    if not cart_list:
        flash('Giỏ hàng trống, không thể thanh toán.', 'warning')
        return redirect(url_for('main.menu'))

    products_in_cart_display = []
    valid_cart_items_for_order = []
    total_base_amount = 0.0
    product_ids = [item.get('product_id') for item in cart_list if item.get('product_id')]

    if product_ids:
        products_map = {p.id: p for p in Product.query.filter(Product.id.in_(product_ids)).all()}
        for item_data in cart_list:
            product_id = item_data.get('product_id')
            if not isinstance(product_id, int): continue
            product = products_map.get(product_id)
            if product and product.is_available:
                try:
                     qty = int(item_data.get('quantity', 1))
                     if qty <= 0: continue
                     sub = float(product.price) * qty
                     total_base_amount += sub
                     display_details = {
                        'id': product.id, 'name': product.name, 'price': float(product.price),
                        'quantity': qty, 'subtotal': sub,
                        'image_url': product.image_url, 'notes': item_data.get('notes', '')
                     }
                     products_in_cart_display.append(display_details)
                     valid_cart_items_for_order.append({
                        'product_id': product.id, 'quantity': qty,
                        'unit_price': float(product.price), 'subtotal': sub,
                        'notes': item_data.get('notes', '')
                     })
                except (ValueError, TypeError):
                     logger.warning(f"Invalid quantity or price for product ID {product_id} in cart.")
                     continue
            else:
                logger.warning(f"Checkout: Skipping invalid/unavailable product ID {product_id} from cart.")

    if not valid_cart_items_for_order:
        flash('Các sản phẩm trong giỏ không hợp lệ hoặc đã hết hàng.', 'danger')
        session.pop('cart', None)
        return redirect(url_for('main.menu'))

    form_data_on_error = None

    if request.method == 'POST':
        form_data_on_error = request.form.to_dict()
        logger.info("Processing checkout POST request...")

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

        if errors:
            for field, msg in errors.items(): flash(msg, 'danger')
            promo_applied_data = session.get('applied_promotion')
            if promo_applied_data:
                 current_discount = promo_applied_data.get('calculated_discount', 0)
                 subtotal_after_discount = total_base_amount - current_discount
                 current_tax = subtotal_after_discount * 0.1
                 is_delivery_on_error = request.form.get('order_type') == 'delivery'
                 shipping_fee_on_error = 20000 if is_delivery_on_error else 0
                 current_total = subtotal_after_discount + current_tax + shipping_fee_on_error
                 promo_applied_data['current_total'] = round(current_total,2)
                 promo_applied_data['current_tax'] = round(current_tax,2)
            return render_template('checkout.html',
                                   cart_items=products_in_cart_display,
                                   total=total_base_amount,
                                   promo_applied=promo_applied_data,
                                   form_data=form_data_on_error,
                                   format_price=format_currency)

        applied_promo_details = None
        calculated_discount = 0.0
        promotion_id_to_save = None
        promotion_code_to_save = None

        if 'applied_promotion' in session:
            promo_in_session = session['applied_promotion']
            code_in_session = promo_in_session.get('code')
            if code_in_session:
                now = datetime.utcnow()
                valid_promo = Promotion.query.filter(
                    func.upper(Promotion.code) == code_in_session,
                    Promotion.is_active == True,
                    Promotion.start_date <= now,
                    Promotion.end_date >= now
                ).first()
                if valid_promo:
                    calculated_discount = promo_in_session.get('calculated_discount', 0)
                    promotion_id_to_save = valid_promo.id
                    promotion_code_to_save = valid_promo.code
                    logger.info(f"Checkout: Applying valid promo code '{code_in_session}'.")
                else:
                    logger.warning(f"Checkout: Promo code '{code_in_session}' from session was invalid/expired. Removing.")
                    session.pop('applied_promotion', None)
                    session.modified = True
                    flash('Mã giảm giá bạn áp dụng đã hết hạn hoặc không còn hợp lệ. Đơn hàng được tính theo giá gốc.', 'warning')


        tax_rate = 0.10
        shipping_fee = 20000.0 if order_type == 'delivery' else 0.0 # Ensure float
        subtotal_after_discount = total_base_amount - calculated_discount
        tax_amount = subtotal_after_discount * tax_rate
        final_amount_calculated = subtotal_after_discount + tax_amount + shipping_fee
        logger.info(f"Checkout totals: Base={total_base_amount}, Discount={calculated_discount}, SubtotalAfter={subtotal_after_discount}, Tax={tax_amount}, Ship={shipping_fee}, Final={final_amount_calculated}")


        try:
            with db.session.begin_nested():
                new_order = Order(
                    user_id=current_user.id,
                    order_number=generate_order_number(),
                    status='pending',
                    total_amount=round(total_base_amount, 2),
                    final_amount=round(final_amount_calculated, 2),
                    order_type=order_type,
                    payment_method=payment_method,
                    payment_status='pending',
                    notes=notes if notes else None,
                    address=address,
                    contact_phone=contact_phone,
                    promotion_id=promotion_id_to_save,
                    promotion_code_used=promotion_code_to_save,
                    discount_applied=round(calculated_discount, 2) if calculated_discount > 0 else None,
                    # Assign explicit float value to shipping_fee and tax_amount if they are in the model
                    # shipping_fee = shipping_fee,
                    # tax_amount = round(tax_amount, 2)
                )
                db.session.add(new_order)
                db.session.flush()


                for item_detail_data in valid_cart_items_for_order:
                    detail = OrderDetail(
                         order_id=new_order.id,
                         product_id=item_detail_data['product_id'],
                         quantity=item_detail_data['quantity'],
                         unit_price=item_detail_data['unit_price'],
                         subtotal=item_detail_data['subtotal'],
                         notes=item_detail_data['notes'] if item_detail_data['notes'] else None
                    )
                    db.session.add(detail)

                    try:
                        inventory_item = db.session.query(InventoryItem)\
                                                  .filter_by(product_id=item_detail_data['product_id'])\
                                                  .with_for_update().first()
                        if inventory_item:
                            if inventory_item.quantity >= item_detail_data['quantity']:
                                inventory_item.quantity -= item_detail_data['quantity']
                                inventory_item.last_updated = datetime.utcnow()
                            else:
                                logger.error(f"CRITICAL STOCK INCONSISTENCY during checkout commit for product {item_detail_data['product_id']} in order {new_order.id}. Required: {item_detail_data['quantity']}, Available: {inventory_item.quantity}")
                                raise Exception(f"Không đủ hàng tồn kho cho sản phẩm ID {item_detail_data['product_id']} khi xác nhận đơn hàng.")
                        else:
                             logger.warning(f"No InventoryItem found for product {item_detail_data['product_id']} during checkout stock decrement.")
                    except Exception as stock_err:
                        logger.error(f"Stock decrement failed during checkout transaction: {stock_err}", exc_info=True)
                        raise stock_err

            db.session.commit()
            logger.info(f"Order {new_order.order_number} (Promo: {promotion_code_to_save}, Discount: {calculated_discount}) created successfully for user {current_user.id}.")
            session.pop('cart', None)
            session.pop('applied_promotion', None)
            flash('Đặt hàng thành công!', 'success')
            return redirect(url_for('order.order_confirmation', order_id=new_order.id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Checkout failed: {e}", exc_info=True)
            flash(f'Lỗi khi xử lý đơn hàng: {str(e)}. Vui lòng thử lại.', 'danger')
            promo_applied_data = session.get('applied_promotion')
            if promo_applied_data:
                current_discount = promo_applied_data.get('calculated_discount', 0)
                subtotal_after_discount = total_base_amount - current_discount
                current_tax = subtotal_after_discount * 0.1
                is_delivery_on_error = request.form.get('order_type') == 'delivery'
                shipping_fee_on_error = 20000.0 if is_delivery_on_error else 0.0
                current_total = subtotal_after_discount + current_tax + shipping_fee_on_error
                promo_applied_data['current_total'] = round(current_total,2)
                promo_applied_data['current_tax'] = round(current_tax,2)
            return render_template('checkout.html',
                                   cart_items=products_in_cart_display,
                                   total=total_base_amount,
                                   promo_applied=promo_applied_data,
                                   form_data=form_data_on_error,
                                   format_price=format_currency,
                                   error_message="Lỗi hệ thống, vui lòng thử lại.")

    # GET Request Handling
    logger.info("Displaying checkout page.")
    promo_applied_data = session.get('applied_promotion')
    current_tax = total_base_amount * 0.1
    current_discount = 0.0
    current_shipping = 0.0

    if promo_applied_data:
         current_discount = promo_applied_data.get('calculated_discount', 0)
         subtotal_after_discount = total_base_amount - current_discount
         current_tax = subtotal_after_discount * 0.1

    default_order_type = 'takeaway'
    if request.args.get('order_type') == 'delivery' or (form_data_on_error and form_data_on_error.get('order_type') == 'delivery'):
         current_shipping = 20000.0

    current_total = total_base_amount - current_discount + current_tax + current_shipping
    if promo_applied_data:
        promo_applied_data['current_total'] = round(current_total, 2)
        promo_applied_data['current_tax'] = round(current_tax, 2)

    return render_template('checkout.html',
                           cart_items=products_in_cart_display,
                           total=total_base_amount,
                           promo_applied=promo_applied_data,
                           format_price=format_currency)


# Route này nên được tạo để chuyển hướng sau khi checkout thành công
@order_bp.route('/confirmation/<int:order_id>')
@login_required
def order_confirmation(order_id):
     logger = current_app.logger if current_app else logging.getLogger(__name__)
     order = db.session.get(Order, order_id)

     if not order:
         logger.warning(f"Order confirmation requested for non-existent order ID: {order_id}")
         flash('Không tìm thấy đơn hàng.', 'danger')
         return redirect(url_for('order.my_orders'))

     # Check if the order belongs to the current user (or if user is admin/staff)
     if order.user_id != current_user.id and not (current_user.is_admin or current_user.is_staff):
          logger.warning(f"Unauthorized access attempt for order confirmation ID {order_id} by user {current_user.id}")
          flash('Bạn không có quyền xem xác nhận đơn hàng này.', 'danger')
          return redirect(url_for('order.my_orders'))

     try:
        # Eager load details and product info in one go
        order_details_with_product = db.session.query(OrderDetail).options(
            joinedload(OrderDetail.ordered_product)
        ).filter(OrderDetail.order_id == order_id).all()

        # Prepare display list
        products_for_display = []
        calculated_subtotal = 0.0
        for detail in order_details_with_product:
             if detail.ordered_product: # Check if product exists
                 subtotal = detail.unit_price * detail.quantity if detail.unit_price is not None and detail.quantity is not None else 0.0
                 calculated_subtotal += subtotal
                 products_for_display.append({
                    'name': detail.ordered_product.name,
                    'quantity': detail.quantity,
                    'price': detail.unit_price,
                    'subtotal': subtotal,
                    'notes': detail.notes
                })
             else: logger.warning(f"Order Confirmation {order_id}: Product ID {detail.product_id} associated with detail ID {detail.id} no longer exists.")

        # Tính toán lại giá trị để hiển thị trên confirmation
        tax_amount = (order.final_amount if order.final_amount is not None else order.total_amount) - \
                      (order.total_amount if order.total_amount is not None else 0.0) + \
                      (order.discount_applied if order.discount_applied is not None else 0.0) - \
                      (order.shipping_fee if hasattr(order,'shipping_fee') and order.shipping_fee is not None else 0.0)


        return render_template('order_confirmation.html',
                           order=order,
                           products=products_for_display,
                           # Tính lại total tiền hàng gốc từ OrderDetails (an toàn hơn)
                           total=calculated_subtotal,
                           # Pass các giá trị đã tính/lưu trong order
                           discount_amount=order.discount_applied,
                           tax_amount=tax_amount,
                           shipping_fee=getattr(order, 'shipping_fee', 0), # Lấy an toàn
                           final_total=order.final_amount if order.final_amount is not None else order.total_amount,
                           format_price=format_currency)
     except Exception as e:
          logger.error(f"Error fetching data for order confirmation {order_id}: {e}", exc_info=True)
          flash('Lỗi khi hiển thị xác nhận đơn hàng.', 'danger')
          return redirect(url_for('order.order_detail', order_id=order_id))

@order_bp.route('/orders')
@login_required
def my_orders():
    logger = current_app.logger if current_app else logging.getLogger()
    logger.info(f"Fetching orders for user {current_user.id}")
    try:
        orders = Order.query.filter_by(user_id=current_user.id)\
                            .order_by(Order.created_at.desc())\
                            .all()
    except Exception as e:
         logger.error(f"Error fetching orders for user {current_user.id}: {e}", exc_info=True)
         orders = []
         flash("Lỗi khi tải danh sách đơn hàng.", "danger")
    return render_template('my_orders.html', orders=orders)

@order_bp.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    logger = current_app.logger if current_app else logging.getLogger()
    logger.info(f"Fetching detail for order {order_id}")
    order = Order.query.get_or_404(order_id)
    # Check permissions (cho người dùng)
    if order.user_id != current_user.id and not (hasattr(current_user, 'is_admin') and current_user.is_admin) and not (hasattr(current_user, 'is_staff') and current_user.is_staff):
        logger.warning(f"User {current_user.id} attempting to access unauthorized order {order_id}")
        flash('Bạn không có quyền xem đơn hàng này.', 'danger')
        return redirect(url_for('order.my_orders'))
    try:
        # Eager load Product cùng OrderDetail
        order_details = OrderDetail.query.options(joinedload(OrderDetail.ordered_product)).filter_by(order_id=order_id).all()
    except Exception as e:
        logger.error(f"Error fetching order details for order {order_id}: {e}", exc_info=True)
        order_details = []
        flash("Lỗi khi tải chi tiết đơn hàng.", "danger")

    # Render template của NGƯỜI DÙNG
    return render_template('order_detail.html', # <<< Đảm bảo render file này
                           order=order,
                           order_details=order_details,
                           format_currency=format_currency # <-- Cần truyền format_currency
                           )

@order_bp.route('/api/order-status/<string:order_number>') # Đảm bảo type là string
def api_order_status(order_number):
    """
    API Endpoint để kiểm tra trạng thái đơn hàng dựa trên mã đơn hàng.
    Trả về JSON với trạng thái và thông tin cơ bản.
    """
    logger = current_app.logger if current_app else logging.getLogger()
    logger.info(f"API request for order status: {order_number}")
    try:
        # Tìm đơn hàng theo order_number (không phân biệt hoa thường nếu cần)
        # Sử dụng func.upper() để đảm bảo khớp nếu order_number trong DB là uppercase
        order = Order.query.filter(func.upper(Order.order_number) == func.upper(order_number)).first()

        if order:
            logger.info(f"Order {order_number} found. Status: {order.status}")
            # Trả về thông tin cần thiết
            return jsonify({
                'success': True,
                'order_number': order.order_number,
                'status': order.status, # Trạng thái mã hóa (pending, processing,...)
                'status_display': order.get_status_display(), # Trạng thái dạng text tiếng Việt
                'payment_status': order.payment_status,
                'order_date': order.created_at.strftime('%d/%m/%Y %H:%M') if order.created_at else None,
                'total_amount': order.final_amount if order.final_amount else order.total_amount # Nên trả về final_amount
            })
        else:
            logger.warning(f"Order {order_number} not found via API.")
            # Không tìm thấy đơn hàng
            return jsonify({'success': False, 'message': 'Không tìm thấy đơn hàng.'}), 404

    except Exception as e:
        logger.error(f"Error fetching order status for {order_number}: {e}", exc_info=True)
        # Lỗi server
        return jsonify({'success': False, 'message': 'Lỗi hệ thống khi kiểm tra đơn hàng.'}), 500

@order_bp.route('/cart-count')
def cart_count():
    # ... (Giữ nguyên logic) ...
    count = len(session.get('cart', []))
    return jsonify({'count': count})


@order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    # ... (Giữ nguyên logic hủy đơn, nhưng nên thêm rollback và logging tốt hơn) ...
    logger = current_app.logger if current_app else logging.getLogger()
    order = Order.query.get_or_404(order_id)

    if order.user_id != current_user.id and not (hasattr(current_user, 'is_admin') and current_user.is_admin): # Cho phép admin hủy
        logger.warning(f"User {current_user.id} unauthorized cancel attempt on order {order_id}")
        flash("Bạn không có quyền hủy đơn hàng này.", "danger")
        return redirect(url_for('order.my_orders'))

    allowed_statuses = ['pending', 'processing'] # Trạng thái cho phép hủy
    if order.status not in allowed_statuses:
        flash(f"Đơn hàng #{order.order_number} không thể hủy (trạng thái: {order.get_status_display()}).", "warning")
        return redirect(url_for('order.order_detail', order_id=order_id))

    try:
        order.status = 'cancelled'
        order.updated_at = datetime.utcnow()
        # --- Logic Hoàn trả Tồn kho (QUAN TRỌNG) ---
        details_to_refund = OrderDetail.query.filter_by(order_id=order.id).all()
        for detail in details_to_refund:
             inventory_item = db.session.query(InventoryItem)\
                                        .filter_by(product_id=detail.product_id)\
                                        .with_for_update().first()
             if inventory_item:
                 inventory_item.quantity += detail.quantity
                 logger.info(f"Restored stock for product {detail.product_id} by {detail.quantity} due to cancellation.")
             else:
                 logger.warning(f"Could not find inventory item for product {detail.product_id} to restore stock on cancellation.")
        # --- Kết thúc hoàn trả tồn kho ---
        # Logic hoàn tiền nếu cần
        # if order.payment_status == 'completed': ...

        db.session.commit()
        flash(f"Đã hủy thành công đơn hàng #{order.order_number}.", "success")
        logger.info(f"Order {order_id} cancelled successfully by user {current_user.id}")
        send_order_status_email(order)

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error cancelling order {order_id}: {e}", exc_info=True)
        flash("Có lỗi xảy ra khi hủy đơn hàng.", "danger")

    return redirect(url_for('order.order_detail', order_id=order_id))

@order_bp.route('/apply-promo', methods=['POST'])
@login_required
def apply_promo_code():
    """API Endpoint để áp dụng mã khuyến mãi vào giỏ hàng."""
    logger = current_app.logger
    cart_list = session.get('cart', [])
    data = request.get_json()

    if not data or 'promo_code' not in data:
        return jsonify({'success': False, 'message': 'Thiếu mã khuyến mãi.'}), 400

    code = data['promo_code'].strip().upper()
    logger.info(f"User {current_user.id} attempting to apply promo code: {code}")

    if not cart_list:
        return jsonify({'success': False, 'message': 'Giỏ hàng trống.'}), 400

    # === Logic kiểm tra mã hợp lệ ===
    now = datetime.utcnow()
    promo = Promotion.query.filter(
        func.upper(Promotion.code) == code, # Không phân biệt hoa thường
        Promotion.is_active == True,
        Promotion.start_date <= now,
        Promotion.end_date >= now
    ).first()

    if not promo:
        logger.warning(f"Promo code '{code}' is invalid or expired.")
        # Xóa KM khỏi session nếu có và trả về lỗi
        session.pop('applied_promotion', None); session.modified = True
        subtotal, tax, total_no_promo = calculate_cart_totals(cart_list)
        return jsonify({
            'success': False,
            'message': 'Mã khuyến mãi không hợp lệ hoặc đã hết hạn.',
            'new_total': total_no_promo, # Trả về giá không KM
            'new_tax': tax # Thuế chưa giảm
        }), 400

    # === Mã hợp lệ, tính toán giảm giá ===
    subtotal, tax_original, _ = calculate_cart_totals(cart_list) # Lấy tiền hàng gốc và thuế gốc
    discount_amount = 0
    if promo.discount_percent:
        discount_amount = subtotal * (promo.discount_percent / 100.0)
        discount_type = 'percent'
    elif promo.discount_amount:
        discount_amount = min(promo.discount_amount, subtotal) # Không giảm nhiều hơn tiền hàng
        discount_type = 'amount'
    else: # Trường hợp hiếm gặp: promo hợp lệ nhưng không có % hay số tiền
        logger.error(f"Valid promotion {promo.id} has no discount value!")
        return jsonify({'success': False, 'message': 'Lỗi cấu hình khuyến mãi.'}), 500

    # Cập nhật session với KM đã áp dụng
    session['applied_promotion'] = {
        'id': promo.id,
        'code': promo.code,
        'name': promo.name,
        'discount_type': discount_type,
        'discount_value': promo.discount_percent if discount_type == 'percent' else promo.discount_amount,
        'calculated_discount': round(discount_amount, 2) # Lưu số tiền đã tính
    }
    session.modified = True

    # Tính lại tổng cuối cùng (thuế tính trên giá gốc hay sau giảm?)
    # Giả sử thuế tính trên giá *sau khi* giảm giá (phổ biến hơn)
    subtotal_after_discount = subtotal - discount_amount
    new_tax = subtotal_after_discount * 0.1 # Tính thuế trên giá mới
    new_total = subtotal_after_discount + new_tax # Giả sử chưa có phí ship

    logger.info(f"Promo code '{code}' applied. Discount: {discount_amount}, New Total: {new_total}")
    return jsonify({
        'success': True,
        'message': f'Đã áp dụng mã "{promo.name}"!',
        'promo_code': promo.code,
        'promo_name': promo.name,
        'discount_amount': round(discount_amount, 2),
        'new_total': round(new_total, 2),
        'new_tax': round(new_tax, 2), # Trả về thuế mới
        'cart_subtotal': round(subtotal, 2) # Vẫn trả về subtotal gốc
    })

@order_bp.route('/remove-promo', methods=['POST'])
@login_required
def remove_promo_code():
    """API Endpoint để gỡ bỏ mã khuyến mãi khỏi giỏ hàng."""
    logger = current_app.logger
    if 'applied_promotion' in session:
        removed_code = session['applied_promotion'].get('code', 'N/A')
        session.pop('applied_promotion', None)
        session.modified = True
        logger.info(f"User {current_user.id} removed promo code '{removed_code}'.")

        # Tính lại tổng khi không có KM
        cart_list = session.get('cart', [])
        subtotal, tax, total = calculate_cart_totals(cart_list)

        return jsonify({
            'success': True,
            'message': 'Đã gỡ bỏ mã giảm giá.',
            'new_total': round(total, 2),
            'new_tax': round(tax, 2) # Trả về thuế gốc
        })
    else:
        logger.warning(f"User {current_user.id} attempted to remove promo, but none was applied.")
        # Vẫn trả về success và giá hiện tại (không có KM)
        cart_list = session.get('cart', [])
        subtotal, tax, total = calculate_cart_totals(cart_list)
        return jsonify({'success': True, 'new_total': round(total, 2), 'new_tax': round(tax, 2) })
