/**
 * Dragon Coffee Shop - Cart Page JavaScript
 * Handles quantity updates and removals specifically for the cart page using AJAX.
 */

// Function to show toast messages (Copy từ main.js nếu cần)
function showToast(message, type = 'info') {
    // (Copy nội dung hàm showToast từ main.js vào đây nếu cart.js đứng độc lập)
    const toastBgClasses = { success: 'text-bg-success', danger: 'text-bg-danger', error: 'text-bg-danger', warning: 'text-bg-warning', info: 'text-bg-info' };
    const toastClass = toastBgClasses[type] || 'text-bg-secondary';
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div'); container.className = 'toast-container position-fixed bottom-0 end-0 p-3'; container.style.zIndex = "1100"; document.body.appendChild(container);
    }
    const toastId = 'toast-cart-' + Date.now();
    const icon = type === 'success' ? 'fa-check-circle' : (type === 'danger' || type === 'error' ? 'fa-exclamation-triangle' : 'fa-info-circle');
    const html = `<div id="${toastId}" class="toast align-items-center ${toastClass} border-0" role="alert" aria-live="assertive" aria-atomic="true" data-bs-delay="3000"><div class="d-flex"><div class="toast-body"><i class="fas ${icon} me-2"></i><span>${message}</span></div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div></div>`;
    container.insertAdjacentHTML('beforeend', html);
    const el = document.getElementById(toastId);
    if (el && typeof bootstrap !== 'undefined' && bootstrap.Toast) {
        const toast = bootstrap.Toast.getOrCreateInstance(el);
        el.addEventListener('hidden.bs.toast', () => el.remove());
        toast.show();
    } else { console.warn('Toast/Bootstrap not available'); alert(`${type}: ${message}`); if (el) el.remove(); }
}

/** Update cart badge count */
function updateCartBadge() {
    fetch('/order/cart-count')
        .then(response => response.ok ? response.json() : null)
        .then(data => {
            const badge = document.querySelector('.cart-badge'); // Tìm badge ở header chung
            if (badge && data && typeof data.count === 'number') {
                badge.textContent = data.count;
                badge.style.display = data.count > 0 ? 'inline-block' : 'none';
            } else if (badge) {
                badge.textContent = '0'; badge.style.display = 'none';
            }
        })
        .catch(error => console.error('Error updating cart badge:', error));
}


/**
 * Send AJAX request to update item quantity in the cart.
 * @param {string} productId - The ID of the product to update.
 * @param {number} quantity - The new quantity for the product.
 */
function updateCartItemAJAX(productId, quantity) {
    console.log(`AJAX: Updating cart for product ID: ${productId}, New Quantity: ${quantity}`);
    const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfTokenMeta ? csrfTokenMeta.getAttribute('content') : null;
    const endpoint = '/order/update-cart'; // Đảm bảo endpoint này đúng

    fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json', // <-- GỬI JSON
            'Accept': 'application/json',
            ...(csrfToken && { 'X-CSRFToken': csrfToken }) // Gửi token nếu có
        },
        body: JSON.stringify({ // <-- GỬI BODY JSON
            product_id: parseInt(productId), // Đảm bảo là số
            quantity: parseInt(quantity)     // Đảm bảo là số
        })
    })
    .then(response => {
        // Xử lý lỗi HTTP trước khi parse JSON
        if (!response.ok) {
            // Cố gắng đọc lỗi từ server, nếu không thì dùng status text
            return response.json().then(errData => {
                throw new Error(errData.message || `Lỗi ${response.status}: ${response.statusText}`);
            }).catch(() => { throw new Error(`Lỗi máy chủ: ${response.status}`); });
        }
        return response.json(); // Parse JSON nếu response OK
    })
    .then(data => {
        console.log('Update cart response:', data);
        if (data.success) {
            // --- **CẬP NHẬT GIAO DIỆN TRANG GIỎ HÀNG** ---
            updateCartItemUI(productId, quantity, data.item_subtotal);
            updateCartSummaryUI(data.cart_subtotal, data.cart_tax, data.cart_total);
            updateCartBadge(); // Cập nhật badge ở header
            showToast(data.message || "Đã cập nhật số lượng.", 'success');
        } else {
            // Lỗi từ backend (vd: validation, không tìm thấy sản phẩm)
            showToast(data.message || 'Lỗi cập nhật giỏ hàng từ máy chủ.', 'danger');
            // Có thể cần khôi phục lại giá trị input cũ nếu muốn
        }
    })
    .catch(error => {
        console.error('AJAX Update Cart Item Error:', error);
        showToast(`Lỗi cập nhật giỏ hàng: ${error.message}`, 'danger');
        // Có thể cần khôi phục lại giá trị input cũ ở đây
        // const input = document.querySelector(`.cart-item[data-product-id="${productId}"] .cart-quantity-input`);
        // if(input) input.value = // giá trị cũ lưu ở đâu đó
    });
}

/**
 * Updates the specific cart item's quantity input and subtotal display.
 */
function updateCartItemUI(productId, newQuantity, newItemSubtotal) {
    const cartItemRow = document.querySelector(`.cart-item[data-product-id="${productId}"]`);
    if (!cartItemRow) {
        console.error(`Cannot find cart item UI row for product ID: ${productId}`);
        return;
    }

    const quantityInput = cartItemRow.querySelector('.cart-quantity-input');
    const subtotalElement = cartItemRow.querySelector('.cart-item-subtotal');

    if (quantityInput) {
        quantityInput.value = newQuantity; // Cập nhật số lượng hiển thị
    }
    if (subtotalElement && newItemSubtotal !== undefined) {
        // Cần format tiền tệ giống backend (hoặc đơn giản là $)
        subtotalElement.textContent = `$${parseFloat(newItemSubtotal).toFixed(2)}`;
    }
}

/**
 * Updates the cart summary section (subtotal, tax, total).
 */
function updateCartSummaryUI(subtotal, tax, total) {
    const subtotalEl = document.querySelector('.cart-subtotal-value');
    const taxEl = document.querySelector('.cart-tax-value');
    const totalEl = document.querySelector('.cart-total-value');

    if (subtotalEl && subtotal !== undefined) subtotalEl.textContent = `$${parseFloat(subtotal).toFixed(2)}`;
    if (taxEl && tax !== undefined) taxEl.textContent = `$${parseFloat(tax).toFixed(2)}`;
    if (totalEl && total !== undefined) totalEl.textContent = `$${parseFloat(total).toFixed(2)}`;
}


/**
 * Set up event listeners for quantity buttons and remove buttons on the cart page.
 */
function setupCartPageInteractions() {
    console.log("Setting up Cart Page Interactions...");
    const cartContainer = document.querySelector('.col-lg-8 .card-body'); // Tìm container chứa các cart-item

    if (!cartContainer) {
        console.warn("Cart items container not found. Cart interactions disabled.");
        return;
    }

    cartContainer.addEventListener('click', function(event) {
        const target = event.target;

        // --- Handling Quantity Buttons (+ / -) ---
        if (target.classList.contains('cart-quantity-btn')) {
            event.preventDefault();
            const cartItemRow = target.closest('.cart-item');
            const input = cartItemRow ? cartItemRow.querySelector('.cart-quantity-input') : null;
            const productId = cartItemRow ? cartItemRow.dataset.productId : null;

            if (!input || !productId) {
                console.error("Could not find quantity input or product ID for button:", target);
                return;
            }

            let currentQuantity = parseInt(input.value);
            let newQuantity = currentQuantity;

            if (target.classList.contains('increment')) {
                newQuantity++; // Tăng số lượng
            } else if (target.classList.contains('decrement')) {
                newQuantity = Math.max(1, currentQuantity - 1); // Giảm, tối thiểu là 1
            }

            if (newQuantity !== currentQuantity) {
                // Chỉ gọi AJAX nếu số lượng thực sự thay đổi
                updateCartItemAJAX(productId, newQuantity);
                // Cập nhật UI tạm thời (có thể bị ghi đè bởi AJAX response)
                 input.value = newQuantity;
                 // Tạm thời ẩn/disable nút để tránh click liên tục trong khi chờ AJAX
                 target.disabled = true;
                 setTimeout(() => { if(target) target.disabled = false; }, 700); // Enable lại sau 0.7s
            }
        }

        // --- Handling Remove Button ---
        else if (target.closest('.remove-from-cart-btn')) {
             event.preventDefault();
             const removeButton = target.closest('.remove-from-cart-btn');
             const cartItemRow = removeButton.closest('.cart-item');
             const productId = removeButton.dataset.productId || (cartItemRow ? cartItemRow.dataset.productId : null);

            if (productId && confirm('Bạn chắc chắn muốn xóa sản phẩm này khỏi giỏ hàng?')) {
                console.log(`AJAX: Removing product ID: ${productId}`);
                const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
                const csrfToken = csrfTokenMeta ? csrfTokenMeta.getAttribute('content') : null;
                const endpoint = `/order/remove-from-cart/${productId}`; // Đảm bảo endpoint đúng

                fetch(endpoint, {
                    method: 'POST', // Backend route phải chấp nhận POST
                    headers: {
                         'Accept': 'application/json',
                        ...(csrfToken && { 'X-CSRFToken': csrfToken })
                    }
                })
                .then(response => {
                     if (!response.ok) { throw new Error(`Lỗi ${response.status}`); }
                     return response.json();
                 })
                 .then(data => {
                      if (data.success) {
                           // Xóa hẳn row khỏi giao diện
                           if(cartItemRow) cartItemRow.remove();
                           // Cập nhật lại summary và badge
                           updateCartSummaryUI(data.cart_subtotal, data.cart_tax, data.cart_total);
                           updateCartBadge();
                           showToast(data.message || 'Đã xóa sản phẩm.', 'success');
                           // Kiểm tra nếu giỏ hàng rỗng thì hiển thị thông báo
                           if(data.cart_count === 0) {
                               cartContainer.innerHTML = '<div class="text-center py-4"><p>Giỏ hàng của bạn đang trống.</p><a href="/menu" class="btn btn-primary">Quay lại mua sắm</a></div>'; // Cập nhật lại nội dung báo rỗng
                               // Ẩn luôn phần summary nếu muốn
                               document.querySelector('.cart-summary')?.remove();
                           }
                      } else {
                           showToast(data.message || 'Lỗi khi xóa sản phẩm.', 'danger');
                      }
                  })
                 .catch(error => {
                      console.error("Error removing item via AJAX:", error);
                      showToast(`Lỗi: ${error.message}.`, 'danger');
                  });
            } else if (!productId) {
                console.error("Remove button clicked, but 'data-product-id' attribute is missing!", removeButton);
            }
        }
    });
    console.log("Cart Page Interaction listeners are active.");
}


// --- MAIN INITIALIZATION FOR CART PAGE ---
document.addEventListener('DOMContentLoaded', function() {
    // Chỉ gọi các hàm cần thiết cho trang giỏ hàng
    if (document.querySelector('.cart-item')) { // Chỉ chạy nếu có element cart-item -> chắc là trang cart
        console.log("Cart page detected. Initializing cart interactions.");
        initializeBootstrapComponents(); // Vẫn cần cho tooltip/popover (nếu có)
        setupCartPageInteractions();    // <<< QUAN TRỌNG: Hàm xử lý riêng cho trang cart
        updateCartBadge();              // Cập nhật badge ban đầu
        // Không cần gọi setupAddToCartButtons từ main.js ở đây nữa
        // Không cần gọi setupChatbot nếu không muốn chatbot trên trang cart
    } else {
         // Nếu không phải trang cart, vẫn có thể chạy các setup chung khác từ main.js (nếu gộp file)
         // initializeBootstrapComponents();
         // animateOnScroll();
         // setupChatbot();
         // updateCartBadge();
         // setupAddToCartButtons(); // Gắn listener chung cho các trang khác
         // console.log("Non-cart page detected. Skipping cart-specific setup.");
    }
});