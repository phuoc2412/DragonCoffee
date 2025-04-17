/**
 * static/js/pos.js (hoặc thêm vào admin.js)
 * Xử lý giao diện và logic cho hệ thống POS
 */

document.addEventListener('DOMContentLoaded', function() {
    // Chỉ chạy nếu đang ở trang POS
    if (document.querySelector('.pos-container')) {
        console.log("POS Page detected. Initializing POS specific scripts...");
        setupPOS();
    }
});

function setupPOS() {
    // ----- DOM Elements -----
    const searchInput = document.getElementById('pos-search'); // Product search
    const categoryButtons = document.querySelectorAll('.pos-category-btn');
    const productsContainer = document.querySelector('.pos-product-grid');
    const cartItemsContainer = document.querySelector('.pos-cart-items');
    const cartTotalElement = document.querySelector('.pos-cart-total-amount');
    const orderTypeOptions = document.querySelectorAll('.pos-order-type-option');
    const paymentMethodOptions = document.querySelectorAll('.pos-payment-method');
    const checkoutButton = document.querySelector('.pos-checkout-btn');
    const clearCartButton = document.querySelector('.pos-clear-btn');
    const orderNotesInput = document.getElementById('pos-order-notes');
    // Customer elements
    const customerSearchInput = document.getElementById('pos-customer-search');
    const customerResultsContainer = document.getElementById('pos-customer-results');
    const selectedCustomerInfoDiv = document.getElementById('pos-selected-customer-info');
    const selectedCustomerNameSpan = document.getElementById('pos-selected-customer-name');
    const selectedCustomerDetailsSpan = document.getElementById('pos-selected-customer-details');
    const selectedCustomerIdInput = document.getElementById('pos-selected-customer-id');
    const clearCustomerButton = document.getElementById('pos-clear-customer-btn');
    const guestInputGroup = document.getElementById('pos-guest-input-group');
    const guestPhoneInput = document.getElementById('pos-guest-phone');

    // ----- State -----
    let cart = []; // Mảng chứa các sản phẩm trong giỏ hàng { product_id, name, price, quantity, notes }
    let selectedOrderType = 'dine-in';
    let selectedPaymentMethod = 'cash';
    let selectedCustomerId = null; // ID của khách hàng được chọn
    let customerSearchDebounceTimeout; // ID cho debounce tìm kiếm KH

    // ----- Initial Load -----
    loadProducts(); // Tải sản phẩm ban đầu
    updateCustomerSectionUI(); // Cập nhật UI phần KH ban đầu

    // ----- Event Listeners -----

    // 1. Tìm kiếm sản phẩm
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const query = this.value.trim();
            const activeCategory = document.querySelector('.pos-category-btn.active');
            const categoryId = activeCategory ? activeCategory.dataset.categoryId : '';
            loadProducts(categoryId, query);
        });
    }

    // 2. Chọn danh mục sản phẩm
    categoryButtons.forEach(button => {
        button.addEventListener('click', function() {
            categoryButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            const categoryId = this.dataset.categoryId;
            searchInput.value = ''; // Reset ô tìm kiếm khi đổi category
            loadProducts(categoryId);
        });
    });

    // 3. Tìm kiếm khách hàng (có debounce)
    if (customerSearchInput && customerResultsContainer) {
        customerSearchInput.addEventListener('input', function() {
            const query = this.value.trim();
            clearTimeout(customerSearchDebounceTimeout);

            if (query.length >= 2) {
                customerResultsContainer.innerHTML = `<span class="list-group-item disabled text-muted py-1">Đang tìm...</span>`;
                customerResultsContainer.style.display = 'block';

                customerSearchDebounceTimeout = setTimeout(() => {
                    searchCustomers(query);
                }, 350); // Delay 350ms
            } else {
                customerResultsContainer.style.display = 'none';
                customerResultsContainer.innerHTML = '';
            }
        });

        // Ẩn kết quả khi click ra ngoài
        document.addEventListener('click', function(event) {
            if (!customerSearchInput.contains(event.target) && !customerResultsContainer.contains(event.target)) {
                customerResultsContainer.style.display = 'none';
            }
        });
    }

    // 4. Chọn khách hàng từ kết quả tìm kiếm
    if (customerResultsContainer) {
        customerResultsContainer.addEventListener('click', function(event) {
            const targetItem = event.target.closest('.customer-result-item');
            if (targetItem) {
                event.preventDefault();
                selectedCustomerId = targetItem.dataset.customerId;
                const customerName = targetItem.dataset.customerName;
                const customerDetails = targetItem.dataset.customerDetails || ''; // Lấy SĐT/Email

                selectedCustomerIdInput.value = selectedCustomerId;
                selectedCustomerNameSpan.textContent = customerName;
                selectedCustomerDetailsSpan.textContent = `(${customerDetails})`;

                updateCustomerSectionUI(true); // Cập nhật UI (true = đã chọn KH)

                customerSearchInput.value = ''; // Xóa input search
                customerResultsContainer.style.display = 'none'; // Ẩn kết quả
                guestPhoneInput.value = ''; // Xóa SĐT khách vãng lai
            }
        });
    }

    // 5. Bỏ chọn khách hàng / Clear customer
    if (clearCustomerButton) {
        clearCustomerButton.addEventListener('click', function() {
            selectedCustomerId = null;
            selectedCustomerIdInput.value = '';
            selectedCustomerNameSpan.textContent = '';
            selectedCustomerDetailsSpan.textContent = '';
            updateCustomerSectionUI(false); // Cập nhật UI (false = không chọn KH)
        });
    }

    // 6. Chọn loại đơn hàng
    orderTypeOptions.forEach(option => {
        option.addEventListener('click', function() {
            orderTypeOptions.forEach(opt => opt.classList.remove('active'));
            this.classList.add('active');
            selectedOrderType = this.dataset.type;
        });
    });

    // 7. Chọn phương thức thanh toán
    paymentMethodOptions.forEach(option => {
        option.addEventListener('click', function() {
            paymentMethodOptions.forEach(opt => opt.classList.remove('active'));
            this.classList.add('active');
            selectedPaymentMethod = this.dataset.method;
        });
    });

    // 8. Nút xóa giỏ hàng
    if (clearCartButton) {
        clearCartButton.addEventListener('click', function() {
            if (confirm('Xóa tất cả sản phẩm khỏi đơn hàng này?')) {
                cart = [];
                renderCart();
                orderNotesInput.value = '';
                // Không reset khách hàng đã chọn ở đây, chỉ xóa sản phẩm
            }
        });
    }

    // 9. Nút hoàn thành đơn hàng
    if (checkoutButton) {
        checkoutButton.addEventListener('click', function() {
            handleCheckout();
        });
    }

    // 10. Sự kiện trong Cart Items (thêm/bớt/xóa SP) - Dùng Event Delegation
    if (cartItemsContainer) {
         cartItemsContainer.addEventListener('click', function(event) {
            const target = event.target;
            const cartItemDiv = target.closest('.pos-cart-item');
            if (!cartItemDiv) return;

            const index = parseInt(cartItemDiv.dataset.index); // Cần đặt data-index cho div item

             if (target.matches('.pos-cart-quantity-btn[data-action="decrease"]')) {
                updateCartQuantity(index, -1);
            } else if (target.matches('.pos-cart-quantity-btn[data-action="increase"]')) {
                updateCartQuantity(index, 1);
            } else if (target.matches('.pos-cart-remove')) {
                removeCartItem(index);
            }
        });

        // Lắng nghe sự kiện thay đổi input số lượng
         cartItemsContainer.addEventListener('change', function(event) {
             if (event.target.matches('.pos-cart-quantity-input')) {
                const cartItemDiv = event.target.closest('.pos-cart-item');
                 const index = parseInt(cartItemDiv.dataset.index);
                 const newQuantity = parseInt(event.target.value);
                setCartQuantity(index, newQuantity);
            }
         });
    }


    // ----- Functions -----

    // Load sản phẩm (Giống code cũ)
    function loadProducts(categoryId = '', query = '') {
        productsContainer.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"></div><p class="mt-2">Đang tải sản phẩm...</p></div>';
        let url = '/admin/api/products'; // Endpoint lấy SP
        const params = new URLSearchParams();
        if (categoryId) params.append('category_id', categoryId);
        if (query) params.append('q', query);
        if (params.toString()) url += '?' + params.toString();

        fetch(url)
            .then(response => response.ok ? response.json() : Promise.reject('Failed to load products'))
            .then(products => renderProducts(products))
            .catch(error => {
                console.error('Error loading products:', error);
                productsContainer.innerHTML = '<div class="text-center py-5 text-danger">Lỗi tải sản phẩm. Vui lòng thử lại.</div>';
            });
    }

    // Render sản phẩm (Giống code cũ)
    function renderProducts(products) {
        productsContainer.innerHTML = '';
        if (products.length === 0) {
            productsContainer.innerHTML = '<div class="text-center py-5 text-muted">Không tìm thấy sản phẩm nào.</div>';
            return;
        }
        products.forEach(product => {
            const productCard = document.createElement('div');
            productCard.className = 'pos-product-card';
            productCard.dataset.productId = product.id;
            // Giảm chiều cao ảnh, làm title rõ hơn
            productCard.innerHTML = `
                <img src="${product.image_url || '/static/images/default_product.png'}" alt="${product.name}" class="pos-product-image" style="height: 90px;">
                <div class="pos-product-info">
                    <div class="pos-product-title fw-semibold">${product.name}</div>
                    <div class="pos-product-price text-primary fw-bold mt-1">${formatCurrencyForPOS(product.price)}</div>
                </div>
            `;
            // Kiểm tra tồn kho (nếu API trả về stock)
            if (product.stock !== undefined && product.stock <= 0) {
                 productCard.classList.add('out-of-stock');
                 productCard.title = "Hết hàng";
                 // Thêm overlay báo hết hàng (tùy chọn)
                 // productCard.insertAdjacentHTML('beforeend', '<div class="out-of-stock-overlay">Hết</div>');
            } else {
                productCard.addEventListener('click', () => addToCart(product));
            }
            productsContainer.appendChild(productCard);
        });
    }

    // Định dạng tiền tệ đơn giản cho POS
     function formatCurrencyForPOS(amount) {
        return amount ? amount.toLocaleString('vi-VN') + '₫' : '0₫';
    }

    // Thêm SP vào giỏ hàng (Giống code cũ)
    function addToCart(product) {
        const existingItemIndex = cart.findIndex(item => item.product_id === product.id);
        if (existingItemIndex !== -1) {
            cart[existingItemIndex].quantity += 1;
        } else {
            cart.push({
                product_id: product.id,
                name: product.name,
                price: product.price,
                quantity: 1,
                notes: ''
            });
        }
        renderCart();
    }

    // Cập nhật số lượng (Kết hợp tăng/giảm)
    function updateCartQuantity(index, change) {
        if (cart[index]) {
             const newQuantity = cart[index].quantity + change;
             setCartQuantity(index, newQuantity); // Gọi hàm set để xử lý logic xóa
        }
    }

    // Set số lượng cụ thể (xử lý cả xóa khi <= 0)
    function setCartQuantity(index, newQuantity) {
         if (cart[index]) {
             if (newQuantity >= 1) {
                cart[index].quantity = newQuantity;
            } else {
                removeCartItem(index); // Xóa nếu số lượng <= 0
                return; // Dừng hàm vì đã xóa
            }
             renderCart(); // Render lại giỏ hàng
        }
    }


    // Xóa SP khỏi giỏ hàng
    function removeCartItem(index) {
        if (cart[index] && confirm(`Xóa "${cart[index].name}" khỏi đơn hàng?`)) {
            cart.splice(index, 1);
            renderCart();
        }
    }


    // Render giỏ hàng (Giống code cũ, thêm data-index)
    function renderCart() {
        if (!cartItemsContainer) return;
        cartItemsContainer.innerHTML = ''; // Xóa nội dung cũ
        let currentTotal = 0;

        if (cart.length === 0) {
            cartItemsContainer.innerHTML = '<div class="text-center py-4 text-muted">Giỏ hàng trống</div>';
        } else {
            cart.forEach((item, index) => {
                const itemTotal = item.price * item.quantity;
                currentTotal += itemTotal;
                const cartItemDiv = document.createElement('div');
                cartItemDiv.className = 'pos-cart-item';
                cartItemDiv.dataset.index = index; // <<< Thêm data-index

                cartItemDiv.innerHTML = `
                    <div class="pos-cart-product">
                        <div class="pos-cart-product-name">${item.name}</div>
                        <div class="pos-cart-product-price">${formatCurrencyForPOS(item.price)}</div>
                    </div>
                    <div class="pos-cart-quantity">
                        <button type="button" class="pos-cart-quantity-btn decrease-qty" data-action="decrease">-</button>
                        <input type="number" class="pos-cart-quantity-input" value="${item.quantity}" min="1" max="99">
                        <button type="button" class="pos-cart-quantity-btn increase-qty" data-action="increase">+</button>
                    </div>
                    <div class="pos-cart-subtotal">${formatCurrencyForPOS(itemTotal)}</div>
                    <button type="button" class="pos-cart-remove btn-close small p-1" aria-label="Remove item"></button>
                `;
                cartItemsContainer.appendChild(cartItemDiv);
            });
        }
        // Cập nhật tổng tiền
        cartTotalElement.textContent = formatCurrencyForPOS(currentTotal);
        // Bật/tắt nút checkout và clear
        checkoutButton.disabled = cart.length === 0;
        clearCartButton.disabled = cart.length === 0;
    }

     // ---- Tìm kiếm khách hàng bằng API ----
    function searchCustomers(query) {
        fetch(`/admin/api/search-customers?q=${encodeURIComponent(query)}`)
            .then(response => response.ok ? response.json() : Promise.reject('API Search Failed'))
            .then(customers => {
                renderCustomerSearchResults(customers);
            })
            .catch(error => {
                console.error("Error searching customers:", error);
                customerResultsContainer.innerHTML = `<span class="list-group-item text-danger py-1">Lỗi tìm kiếm KH.</span>`;
                customerResultsContainer.style.display = 'block'; // Vẫn hiển thị lỗi
            });
    }

    // ---- Render kết quả tìm kiếm khách hàng ----
    function renderCustomerSearchResults(customers) {
        customerResultsContainer.innerHTML = ''; // Xóa kết quả cũ
        if (customers.length === 0) {
            customerResultsContainer.innerHTML = `<span class="list-group-item disabled text-muted py-1">Không tìm thấy khách hàng.</span>`;
        } else {
            customers.forEach(customer => {
                const item = document.createElement('a');
                item.href = '#'; // Để có thể click
                item.className = 'list-group-item list-group-item-action customer-result-item py-1 px-2'; // class để JS nhận diện
                item.dataset.customerId = customer.id;
                item.dataset.customerName = customer.full_name || 'N/A';
                item.dataset.customerDetails = customer.phone || customer.email || ''; // Hiển thị SĐT hoặc Email
                item.innerHTML = `
                    <div class="d-flex justify-content-between">
                        <span class="fw-medium">${customer.full_name || customer.email || customer.phone}</span>
                        <small class="text-muted">${customer.phone || ''}</small>
                    </div>
                    <small class="text-muted d-block">${customer.email || ''}</small>
                `;
                customerResultsContainer.appendChild(item);
            });
        }
         customerResultsContainer.style.display = 'block'; // Luôn hiển thị container khi có kết quả hoặc thông báo
    }

    // ---- Cập nhật UI cho phần Khách hàng ----
    function updateCustomerSectionUI(customerSelected = false) {
         if (customerSelected) {
             selectedCustomerInfoDiv.style.display = 'block';
             guestInputGroup.style.display = 'none';
             customerSearchInput.style.display = 'none'; // Ẩn ô search khi đã chọn
             customerResultsContainer.style.display = 'none';// Ẩn kết quả search
        } else {
            selectedCustomerInfoDiv.style.display = 'none';
            guestInputGroup.style.display = 'block'; // Hiện ô nhập SĐT khách vãng lai
            customerSearchInput.style.display = 'block'; // Hiện lại ô search
            selectedCustomerIdInput.value = ''; // Clear ID đã lưu
            selectedCustomerId = null; // Reset state
        }
    }

     // ---- Xử lý Checkout ----
     function handleCheckout() {
        const cartTotalElement = document.querySelector('.pos-cart-total-amount'); // Cần lấy tổng tiền
        const guestPhoneInput = document.getElementById('pos-guest-phone'); // Input SĐT khách vãng lai
        const selectedCustomerIdInput = document.getElementById('pos-selected-customer-id'); // Input ẩn chứa ID KH
        const orderNotesInput = document.getElementById('pos-order-notes'); // Textarea ghi chú
        const checkoutButton = document.querySelector('.pos-checkout-btn'); // Nút checkout
        const orderTypeOptions = document.querySelectorAll('.pos-order-type-option'); // Các nút chọn loại đơn
        const paymentMethodOptions = document.querySelectorAll('.pos-payment-method'); // Các nút chọn phương thức TT
    
        // Lấy trạng thái từ các biến state đã quản lý
        // Ví dụ:
        // let cart = [...] // Mảng giỏ hàng hiện tại
        // let selectedOrderType = 'dine-in'; // Loại đơn đang chọn
        // let selectedPaymentMethod = 'cash'; // Phương thức TT đang chọn
        // let selectedCustomerId = selectedCustomerIdInput ? selectedCustomerIdInput.value : null; // Lấy ID khách từ input ẩn
    
    
        if (cart.length === 0) {
            showToast("Giỏ hàng trống!", "warning");
            return;
        }
    
        const guestPhone = guestPhoneInput ? guestPhoneInput.value.trim() : '';
        // Lấy ID khách hàng đã chọn từ input ẩn hoặc biến state
        const currentSelectedCustomerId = selectedCustomerIdInput ? selectedCustomerIdInput.value : selectedCustomerId;
    
        if (!currentSelectedCustomerId && !guestPhone) {
            showToast("Vui lòng chọn khách hàng hoặc nhập SĐT khách vãng lai.", "warning");
            if(guestPhoneInput) guestPhoneInput.focus();
            return;
         }
    
         // Tính tổng tiền hàng gốc từ state `cart`
        const totalBaseAmount = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    
        // Lấy các giá trị khác từ state
        const currentOrderType = selectedOrderType; // Sử dụng biến state
        const currentPaymentMethod = selectedPaymentMethod; // Sử dụng biến state
        const currentNotes = orderNotesInput ? orderNotesInput.value.trim() : '';
    
    
        const orderData = {
            items: cart.map(item => ({ product_id: item.product_id, quantity: item.quantity, notes: item.notes || ''})),
            total_amount: totalBaseAmount, // Gửi tiền hàng gốc
            // Gửi customer_id nếu có, nếu không gửi null
            customer_id: currentSelectedCustomerId ? parseInt(currentSelectedCustomerId) : null,
            // Gửi guest_phone nếu customer_id không có
            contact_phone: currentSelectedCustomerId ? null : guestPhone,
            order_type: currentOrderType,
            payment_method: currentPaymentMethod,
            notes: currentNotes
        };
    
        console.log("Submitting order data:", orderData);
    
        // Disable nút để tránh click nhiều lần
        if (checkoutButton) {
            checkoutButton.disabled = true;
            checkoutButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Đang xử lý...`;
        }
    
        // Lấy CSRF token từ thẻ meta
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        };
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
             console.log("CSRF Token Sent:", csrfToken);
        } else {
            console.warn("CSRF meta tag not found or empty! Request might fail.");
        }
    
        fetch('/admin/api/create-order', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(orderData)
        })
        .then(response => {
            // Xử lý response như cũ, trả về { ok: boolean, data: object }
            return response.json().then(data => ({ ok: response.ok, status: response.status, data }));
        })
        .then(result => {
            if (result.ok && result.data.success) {
                console.log("Order created successfully:", result.data);
                showToast(`Đã tạo đơn hàng #${result.data.order_number}!`, 'success');
    
                // Reset state và UI
                cart = []; // Reset cart state
                renderCart(); // Render lại giỏ hàng rỗng
                if (orderNotesInput) orderNotesInput.value = '';
                if (guestPhoneInput) guestPhoneInput.value = '';
                if (selectedCustomerIdInput) selectedCustomerIdInput.value = '';
                selectedCustomerId = null; // Reset biến state ID khách
                updateCustomerSectionUI(false); // Cập nhật lại UI phần khách hàng
    
                // Tùy chọn: Hiển thị modal success
                const successModalElement = document.getElementById('orderSuccessModal');
                if (successModalElement) {
                    const successModal = bootstrap.Modal.getOrCreateInstance(successModalElement);
                    const successOrderNumberSpan = document.getElementById('successOrderNumber');
                    if (successOrderNumberSpan) {
                         successOrderNumberSpan.textContent = result.data.order_number;
                    }
                    successModal.show();
                }
    
            } else {
                 // Ném lỗi để catch xử lý
                 console.error(`Failed to create order. Status: ${result.status}`, result.data);
                 throw new Error(result.data.error || `Lỗi từ server (${result.status})`);
             }
        })
        .catch(error => {
            console.error('Error creating order:', error);
            showToast(`Lỗi tạo đơn hàng: ${error.message || 'Lỗi không xác định'}`, 'danger');
        })
        .finally(() => {
            // Luôn bật lại nút checkout sau khi xử lý xong
            if (checkoutButton) {
                 checkoutButton.disabled = cart.length === 0; // Chỉ disable nếu giỏ hàng rỗng
                 checkoutButton.innerHTML = `<i class="fas fa-check me-1"></i> Hoàn thành`;
            }
        });
    }
}
// Helper để hiển thị Toast (Copy từ main.js hoặc base template JS nếu cần)
function showToast(message, type = 'info') {
    const toastBgClasses = { success: 'text-bg-success', danger: 'text-bg-danger', warning: 'text-bg-warning', info: 'text-bg-info' };
    const toastClass = toastBgClasses[type] || 'text-bg-secondary';
    let container = document.querySelector('.toast-container.position-fixed'); // Tìm container chuẩn
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        container.style.zIndex = "1150"; // Đảm bảo hiển thị trên modal
        document.body.appendChild(container);
    }
    const toastId = 'pos-toast-' + Date.now();
    const icon = type === 'success' ? 'fa-check-circle' : (type === 'danger' ? 'fa-exclamation-triangle' : 'fa-info-circle');
    const html = `<div id="${toastId}" class="toast align-items-center ${toastClass} border-0" role="alert" aria-live="assertive" aria-atomic="true" data-bs-delay="4000"><div class="d-flex"><div class="toast-body"><i class="fas ${icon} me-2"></i><span>${message}</span></div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div></div>`;
    container.insertAdjacentHTML('beforeend', html);
    const el = document.getElementById(toastId);
    if (el && typeof bootstrap !== 'undefined' && bootstrap.Toast) {
        const toast = bootstrap.Toast.getOrCreateInstance(el);
        el.addEventListener('hidden.bs.toast', () => el.remove());
        toast.show();
    } else { console.warn('Toast/Bootstrap not available'); alert(`${type}: ${message}`); if (el) el.remove(); }
}