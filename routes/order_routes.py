# /routes/order_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from flask_login import login_required, current_user
from models import Product, Order, OrderDetail, db, InventoryItem # Đảm bảo db được import
from datetime import datetime
import uuid
from utils import generate_order_number

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
    """Tính tổng tiền hàng, thuế (ví dụ 10%), tổng cuối cùng từ list cart."""
    subtotal = 0
    product_ids = [item['product_id'] for item in cart_list]
    if product_ids:
        products_map = {p.id: p.price for p in Product.query.filter(Product.id.in_(product_ids)).all()}
        for item in cart_list:
            price = products_map.get(item['product_id'])
            if price:
                 subtotal += price * item.get('quantity', 1)
    tax = subtotal * 0.1 # Ví dụ thuế 10%
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
    logger = current_app.logger
    cart = session.get('cart', [])
    if not cart:
        flash('Giỏ hàng trống, không thể thanh toán.', 'warning')
        return redirect(url_for('main.menu'))

    # ----- Tính toán chi tiết và tổng tiền hàng ban đầu -----
    products_in_cart = []
    product_ids = [item['product_id'] for item in cart]
    # Biến này là TỔNG TIỀN HÀNG (chưa thuế, ship, discount)
    total_base_amount = 0 # Đổi tên biến cho rõ ràng
    valid_cart_items_for_order = []
    if product_ids:
        products_map = {p.id: p for p in Product.query.filter(Product.id.in_(product_ids)).all()}
        for item_data in cart:
            product = products_map.get(item_data['product_id'])
            if product and product.is_available:
                qty = item_data.get('quantity', 1)
                sub = product.price * qty
                total_base_amount += sub # Cộng dồn tiền hàng
                details = { # Dữ liệu để hiển thị trên trang checkout
                    'id': product.id, 'name': product.name, 'price': product.price,
                    'quantity': qty, 'subtotal': sub,
                    'image_url': product.image_url, 'notes': item_data.get('notes', '')
                }
                products_in_cart.append(details)
                valid_cart_items_for_order.append({ # Dữ liệu để tạo OrderDetail
                    'product_id': product.id, 'quantity': qty,
                    'unit_price': product.price, 'subtotal': sub,
                    'notes': item_data.get('notes', '')
                })
            else: logger.warning(f"Checkout: Skipping invalid/unavailable product ID {item_data.get('product_id')} from cart.")
    if not valid_cart_items_for_order:
         flash('Các sản phẩm trong giỏ không hợp lệ.', 'danger'); session.pop('cart', None); return redirect(url_for('main.menu'))
    # --------------------------------------------------------

    # ----- XỬ LÝ POST REQUEST -----
    if request.method == 'POST':
        logger.info("Processing checkout POST request...")
        try:
            order_type = request.form.get('order_type', 'takeaway')
            payment_method = request.form.get('payment_method', 'cash')
            notes = request.form.get('notes', '').strip()
            address = request.form.get('address', '').strip() if order_type == 'delivery' else None
            contact_phone = request.form.get('phone', '').strip()

            # --- Server-side validation ---
            errors = {}
            if order_type == 'delivery' and not address: errors['address'] = 'Vui lòng nhập địa chỉ giao hàng.'
            if not contact_phone: errors['phone'] = 'Vui lòng nhập số điện thoại liên hệ.'
            # ... validate khác ...
            if errors:
                # ... (flash lỗi và render lại template như cũ) ...
                return render_template('checkout.html', ...)


            # ----- *** TÍNH TOÁN final_amount Ở ĐÂY *** -----
            tax_rate = 0.10  # Ví dụ thuế 10%
            shipping_fee = 0
            discount_amount = 0 # Tạm thời chưa có giảm giá

            if order_type == 'delivery':
                # Thêm logic tính phí ship dựa trên địa chỉ hoặc quy tắc cố định
                shipping_fee = 20000 # Ví dụ phí ship cố định

            tax_amount = total_base_amount * tax_rate
            # Tổng cuối cùng khách trả
            final_amount_calculated = total_base_amount + tax_amount + shipping_fee - discount_amount
            # ---------------------------------------------


            # ----- Tạo đối tượng Order VỚI final_amount -----
            new_order = Order(
                user_id=current_user.id,
                order_number=generate_order_number(),
                status='pending',
                total_amount=total_base_amount, # Tiền hàng gốc
                order_type=order_type,
                payment_method=payment_method,
                payment_status='pending',
                notes=notes,
                address=address,
                contact_phone=contact_phone,
                # Các trường khác nếu có trong model (như tax_amount, shipping_fee, discount_amount)
                # tax_amount = tax_amount,
                # shipping_fee = shipping_fee,
                # discount_amount = discount_amount,
                # *** GÁN final_amount ĐÃ TÍNH ***
                final_amount = final_amount_calculated
            )
            # ------------------------------------------------

            db.session.add(new_order)
            db.session.flush()

            # --- Tạo OrderDetail và trừ tồn kho (giữ nguyên logic đã có) ---
            for item_detail_data in valid_cart_items_for_order:
                # ... (tạo OrderDetail) ...
                detail = OrderDetail( # Copy từ code trước
                     order_id=new_order.id,
                     product_id=item_detail_data['product_id'],
                     quantity=item_detail_data['quantity'],
                     unit_price=item_detail_data['unit_price'],
                     subtotal=item_detail_data['subtotal'],
                     notes=item_detail_data['notes']
                )
                db.session.add(detail)
                # ... (trừ tồn kho) ...
                try: # Copy từ code trước
                    inventory_item = db.session.query(InventoryItem)\
                                              .filter_by(product_id=item_detail_data['product_id'])\
                                              .with_for_update().first()
                    if inventory_item and inventory_item.quantity >= item_detail_data['quantity']:
                        inventory_item.quantity -= item_detail_data['quantity']
                    elif inventory_item:
                        raise Exception(f"Lỗi tồn kho không nhất quán cho SP ID {item_detail_data['product_id']}.")
                    else:
                        logger.warning(f"Inv item not found for product {item_detail_data['product_id']} during stock decrement.")
                except Exception as stock_err:
                    db.session.rollback()
                    logger.error(f"Stock decrement failed: {stock_err}", exc_info=True)
                    flash("Lỗi hệ thống khi cập nhật kho. Đơn hàng chưa được tạo.", "danger")
                    return redirect(url_for('order.cart'))
             # ----------------------------------------------------------

            db.session.commit()
            logger.info(f"Order {new_order.order_number} created successfully.")
            session.pop('cart', None)
            flash('Đặt hàng thành công!', 'success')
            return redirect(url_for('order.order_detail', order_id=new_order.id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Checkout failed: {e}", exc_info=True)
            flash('Lỗi khi xử lý đơn hàng. Vui lòng thử lại.', 'danger')
            return render_template('checkout.html',
                                   cart_items=products_in_cart,
                                   total=total_base_amount, # Vẫn dùng total_base_amount cho hiển thị Tóm tắt đơn hàng ban đầu
                                   error_message="Lỗi hệ thống, vui lòng thử lại.",
                                   form_data=request.form)

    # ----- GET REQUEST -----
    logger.info("Displaying checkout page.")
    return render_template('checkout.html',
                           cart_items=products_in_cart,
                           total=total_base_amount) # Truyền tổng tiền hàng vào template

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
    # Check permissions
    if order.user_id != current_user.id and not (hasattr(current_user, 'is_admin') and current_user.is_admin) and not (hasattr(current_user, 'is_staff') and current_user.is_staff):
        logger.warning(f"User {current_user.id} attempting to access unauthorized order {order_id}")
        flash('Bạn không có quyền xem đơn hàng này.', 'danger')
        return redirect(url_for('order.my_orders'))
    try:
        order_details = OrderDetail.query.filter_by(order_id=order_id).all()
    except Exception as e:
        logger.error(f"Error fetching order details for order {order_id}: {e}", exc_info=True)
        order_details = []
        flash("Lỗi khi tải chi tiết đơn hàng.", "danger")
    return render_template('order_detail.html', order=order, order_details=order_details)

@order_bp.route('/api/order-status/<order_number>')
def api_order_status(order_number):
    # ... (Giữ nguyên logic) ...
    pass

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

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error cancelling order {order_id}: {e}", exc_info=True)
        flash("Có lỗi xảy ra khi hủy đơn hàng.", "danger")

    return redirect(url_for('order.order_detail', order_id=order_id))