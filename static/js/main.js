// static/js/main.js

function showToast(message, type = 'info') {
    const toastBgClasses = {
        success: 'text-bg-success',
        danger: 'text-bg-danger',
        error: 'text-bg-danger',
        warning: 'text-bg-warning',
        info: 'text-bg-info',
        primary: 'text-bg-primary',
        secondary: 'text-bg-secondary',
        light: 'text-bg-light',
        dark: 'text-bg-dark',
    };
    const toastClass = toastBgClasses[type] || 'text-bg-secondary';

    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        console.warn("Toast container not found, creating dynamically.");
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        toastContainer.style.zIndex = "1100";
        document.body.appendChild(toastContainer);
    }

    const toastId = 'toast-' + Date.now();
    const iconClass = type === 'success' ? 'fa-check-circle' : (type === 'danger' || type === 'error' ? 'fa-exclamation-triangle' : 'fa-info-circle');

    const toastHtml = `
        <div id="${toastId}" class="toast align-items-center ${toastClass} border-0" role="alert" aria-live="assertive" aria-atomic="true" data-bs-delay="4000">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas ${iconClass} me-2"></i>
                    <span>${message}</span>
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;

    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastElement = document.getElementById(toastId);

    if (toastElement && typeof bootstrap !== 'undefined' && bootstrap.Toast) {
         try {
             const bsToast = new bootstrap.Toast(toastElement);
             toastElement.addEventListener('hidden.bs.toast', function() {
                toastElement.remove();
            });
             bsToast.show();
         } catch (e) {
              console.error("Error showing Bootstrap toast:", e);
              alert(`${type.toUpperCase()}: ${message}`);
              toastElement.remove();
         }
     } else {
         console.warn('Bootstrap Toast JS not available or toast element missing. Using alert fallback.');
         alert(`${type.toUpperCase()}: ${message}`);
         if (toastElement) toastElement.remove();
     }
 }


function updateCartBadge() {
    fetch('/order/cart-count')
        .then(response => {
            if (!response.ok) {
                console.error(`Cart count request failed! Status: ${response.status}`);
                return null;
            }
            return response.json();
        })
        .then(data => {
            const badge = document.querySelector('.cart-badge');
            if (!badge) {
                console.warn("Cart badge element '.cart-badge' not found in DOM.");
                return;
            }
            if (data && typeof data.count === 'number') {
                badge.textContent = data.count;
                badge.style.display = data.count > 0 ? 'inline-block' : 'none';
            } else {
                console.warn("Received invalid data for cart count:", data);
                badge.textContent = '0';
                badge.style.display = 'none';
            }
        })
        .catch(error => {
            console.error('Error fetching/updating cart badge:', error);
            const badge = document.querySelector('.cart-badge');
            if (badge) { badge.style.display = 'none'; }
        });
}


function addToCart(productId, quantity = 1, size = '', notes = '', isBuyNow = false) { // Thêm tham số size và isBuyNow
    const parsedProductId = parseInt(productId);
    if (isNaN(parsedProductId) || parsedProductId <= 0) {
        console.error(`Invalid product ID: ${productId}`);
        showToast('Lỗi: ID sản phẩm không hợp lệ.', 'danger');
        return;
    }

    // ---- *** Tạo dữ liệu gửi đi *** ----
    const data = {
        product_id: parsedProductId,
        quantity: parseInt(quantity) || 1 // Đảm bảo quantity là số >= 1
    };
    // Chỉ gửi size/notes nếu chúng thực sự được cung cấp (khác rỗng)
    // Việc gửi size ở đây là tùy chọn, nếu backend không xử lý thì có thể bỏ qua
    // if (size) data.size = size;
    if (notes && notes.trim()) data.notes = notes.trim();
    // -----------------------------------

    const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfTokenMeta ? csrfTokenMeta.getAttribute('content') : null;

    console.log(`AJAX: Adding product ${parsedProductId}, Qty: ${data.quantity}, Notes: ${data.notes}, BuyNow: ${isBuyNow}`);

    fetch('/order/add-to-cart', { // Đảm bảo đúng endpoint
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            ...(csrfToken && { 'X-CSRFToken': csrfToken })
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        // Xử lý 401 và các lỗi khác giữ nguyên như cũ
        if (response.status === 401) {
            console.warn("Need login. Redirecting...");
            showToast('Bạn cần đăng nhập để thêm vào giỏ hàng.', 'warning');
            setTimeout(() => { /* redirect logic */ }, 1500);
            throw new Error('LOGIN_REQUIRED');
        }
        if (!response.ok) {
            // Cố gắng đọc lỗi JSON từ server nếu có
            return response.json().then(errData => {
                throw new Error(errData.message || `Lỗi server ${response.status}`);
            }).catch(() => { throw new Error(`Lỗi server ${response.status}`); });
        }
        return response.json(); // Nếu OK thì parse JSON
    })
    .then(jsonData => {
        console.log("Add to cart response:", jsonData);
        if (jsonData.success) {
            showToast(jsonData.message || 'Đã thêm vào giỏ!', 'success');
            updateCartBadge();
            // Nếu là Buy Now, chuyển hướng đến checkout
            if (isBuyNow) {
                console.log("Buy Now successful, redirecting to checkout...");
                window.location.href = '/order/checkout'; // Đảm bảo đúng URL checkout
            }
        } else {
            throw new Error(jsonData.message || 'Thêm vào giỏ thất bại.');
        }
    })
    .catch(error => {
        if (error.message !== 'LOGIN_REQUIRED') {
            console.error('Add to Cart Fetch Error:', error);
            showToast(`Lỗi: ${error.message}`, 'danger');
        }
    });
}


function setupAddToCartButtons() {
    console.log("Setting up Delegated Add to Cart listener...");
    document.body.addEventListener('click', function(event) {
        // Tìm nút .add-to-cart-btn gần nhất với vị trí click
        const button = event.target.closest('.add-to-cart-btn');
        if (button) {
            event.preventDefault();
            event.stopPropagation(); // Ngăn sự kiện nổi bọt thêm

            const productId = button.dataset.productId;
            if (!productId) {
                console.error("Missing data-product-id on button:", button);
                showToast("Lỗi: Không tìm thấy ID sản phẩm.", "danger");
                return;
            }

            // --- **Lấy quantity, size, notes nếu có từ trang product_detail** ---
            let quantity = 1;
            let size = ''; // Mặc định hoặc để trống nếu không áp dụng
            let notes = '';
            const form = button.closest('form#add-to-cart-form'); // Tìm form cha (chỉ tồn tại trên product_detail)

            if (form) { // Nếu tìm thấy form -> đang ở trang chi tiết
                const qtyInput = form.querySelector('input#quantity');
                const sizeSelect = form.querySelector('select#size');
                const notesTextarea = form.querySelector('textarea#notes');

                if (qtyInput) quantity = parseInt(qtyInput.value) || 1;
                if (sizeSelect) size = sizeSelect.value; // Lấy giá trị size đã chọn
                if (notesTextarea) notes = notesTextarea.value;
            }
            // --- Nếu không ở trang chi tiết, quantity mặc định là 1, notes/size rỗng ---

            // Xác định có phải là "Buy Now" không
            const isBuyNow = button.dataset.action === 'buy-now';

            // Gọi hàm addToCart với đủ tham số
            addToCart(productId, quantity, size, notes, isBuyNow);

        }
    });
    console.log("Delegated Add to Cart listener active.");
}


function initializeBootstrapComponents() {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
    const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
    [...popoverTriggerList].map(popoverTriggerEl => new bootstrap.Popover(popoverTriggerEl));
    console.log("Bootstrap components initialized.");
}


function animateOnScroll() {
    const animatedElements = document.querySelectorAll('.animate-on-scroll');
    if (typeof IntersectionObserver === 'undefined' || animatedElements.length === 0) {
        animatedElements.forEach(el => el.style.visibility = 'visible');
        return;
    }
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.visibility = 'visible';
                entry.target.classList.add('animate__animated');
                const animation = entry.target.dataset.animation || 'animate__fadeInUp';
                const delay = entry.target.dataset.animationDelay || entry.target.style.animationDelay || '0s';
                entry.target.style.animationDelay = delay;
                entry.target.classList.add(animation);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });
    animatedElements.forEach(element => {
        element.style.visibility = 'hidden';
        observer.observe(element);
    });
    console.log("Scroll animation setup complete.");
}


function setupQuantityControls() {
    document.body.addEventListener('click', function(event) {
        const target = event.target;
        if (target.classList.contains('qty-btn')) {
            const buttonId = target.id;
            const inputGroup = target.closest('.input-group');
            if (!inputGroup) return;
            const input = inputGroup.querySelector('input[type="number"]');
            if (!input) return;
            let value = parseInt(input.value) || 1;
            const min = parseInt(input.min) || 1;
            const max = parseInt(input.max) || 99;
            if (buttonId === 'incQty' && value < max) { value++; }
            else if (buttonId === 'decQty' && value > min) { value--; }
            input.value = value;
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });
    document.querySelectorAll('input#quantity').forEach(input => {
        input.addEventListener('change', function() {
            const min = parseInt(this.min) || 1;
            const max = parseInt(this.max) || 99;
            let val = parseInt(this.value);
            if (isNaN(val) || val < min) { this.value = min; }
            else if (val > max) { this.value = max; }
        });
    });
    console.log("Quantity controls setup complete (if applicable).");
}


function setupCategoryNav() {
     const categoryNav = document.querySelector('.category-nav');
     if (!categoryNav) return;
}


function setupContactForm() {
    const contactForm = document.querySelector('#contactForm');
     if (!contactForm) return;
    contactForm.addEventListener('submit', function(event) {
        event.preventDefault();
        const formData = new FormData(contactForm);
        const submitButton = contactForm.querySelector('button[type="submit"]');
        const originalButtonText = submitButton ? submitButton.innerHTML : 'Gửi';
        const csrfToken = contactForm.querySelector('input[name="csrf_token"]')?.value;
        if (submitButton) { submitButton.disabled = true; submitButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Đang gửi...`; }
        const headers = { 'Accept': 'application/json' };
        if (csrfToken) { headers['X-CSRFToken'] = csrfToken; }
        fetch(contactForm.action || window.location.href, { method: 'POST', body: formData, headers: headers })
        .then(response => response.json().then(data => ({ ok: response.ok, data })))
        .then(result => {
            if (result.ok && result.data.success) { showToast(result.data.message || 'Đã gửi!', 'success'); contactForm.reset(); }
            else { throw new Error(result.data.message || 'Gửi thất bại.'); } })
        .catch(error => { console.error('Contact form error:', error); showToast(`Lỗi: ${error.message || 'Không thể gửi.'}`, 'danger'); })
        .finally(() => { if (submitButton) { submitButton.disabled = false; submitButton.innerHTML = originalButtonText; } });
    });
}


function setupChatbot() {
    const chatbotContainer = document.getElementById('chatbot-container');
    const chatbotToggleBtn = document.getElementById('chatbot-toggle-btn');
    const chatbotMinimizeBtn = document.getElementById('chatbot-minimize-btn');
    const chatMessages = document.getElementById('chat-messages');
    const chatForm = document.getElementById('chatForm');
    const chatInput = document.getElementById('chat-input');
    const chatUploadBtn = document.getElementById('chat-upload-btn');
    const chatImageInput = document.getElementById('chat-image-input');

    if (!chatbotContainer || !chatbotToggleBtn || !chatbotMinimizeBtn || !chatMessages || !chatForm || !chatInput || !chatUploadBtn || !chatImageInput) {
        console.warn("Chatbot elements missing. UI disabled.");
        if(chatbotToggleBtn) chatbotToggleBtn.style.display = 'none'; return; }

    chatbotToggleBtn.addEventListener('click', () => {
        chatbotContainer.classList.toggle('collapsed');
        if (!chatbotContainer.classList.contains('collapsed')) { setTimeout(() => { chatMessages.scrollTop = chatMessages.scrollHeight; chatInput.focus(); }, 300); } });
    chatbotMinimizeBtn.addEventListener('click', () => { chatbotContainer.classList.add('collapsed'); });
    chatForm.addEventListener('submit', function(event) { event.preventDefault(); const userMessage = chatInput.value.trim(); if (userMessage) { sendChatMessage(userMessage); } });
    chatInput.addEventListener('keypress', function(event) { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); chatForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true })); } });
    chatUploadBtn.addEventListener('click', () => { chatImageInput.click(); });
    chatImageInput.addEventListener('change', function(event) { const file = event.target.files[0]; if (file && file.type.startsWith('image/')) { appendChatMessage('user-message', `[Ảnh: ${file.name.substring(0, 20)}...]`); uploadChatImage(file); } else if(file) { showToast('Chỉ chọn file ảnh.', 'warning'); } this.value = null; });
    console.log("Chatbot UI setup complete.");
}

function appendChatMessage(type, content) {
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) { console.error("Chat messages container not found!"); return; }
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', type);
    if (type === 'image-results' && Array.isArray(content)) {
        messageDiv.classList.add('image-results-container', 'bot-message');
        if (content.length === 0) { appendChatMessage('bot-message', 'Không tìm thấy ảnh phù hợp.'); return; }
        const title = document.createElement('p'); title.classList.add('image-results-title'); title.textContent = "Có phải bạn tìm món này?"; messageDiv.appendChild(title);
        const resultsWrapper = document.createElement('div'); resultsWrapper.classList.add('d-flex', 'flex-wrap', 'gap-2', 'mt-2');
        content.forEach(item => {
           const link = document.createElement('a'); link.href = item.product_url || '#'; link.classList.add('image-result-item', 'text-decoration-none', 'text-center'); link.target = "_blank"; link.rel = "noopener noreferrer";
           const img = document.createElement('img'); img.src = item.image_url; img.alt = item.name; img.loading = "lazy"; img.classList.add('img-thumbnail', 'mb-1'); img.style.cssText = 'width: 70px; height: 70px; object-fit: cover; border-color: #eee;';
           const nameSpan = document.createElement('span'); nameSpan.textContent = item.name; nameSpan.classList.add('d-block', 'small');
           link.appendChild(img); link.appendChild(nameSpan); resultsWrapper.appendChild(link); });
        messageDiv.appendChild(resultsWrapper); }
    else if (typeof content === 'string') { const p = document.createElement('p'); p.innerHTML = content.replace(/\n/g, '<br>'); messageDiv.appendChild(p); }
    else { console.warn("Invalid content for appendChatMessage:", content); return; }
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTo({ top: chatMessages.scrollHeight, behavior: 'smooth' });
}

function sendChatMessage(message) {
    const chatInput = document.getElementById('chat-input');
    const chatSendButton = document.querySelector('#chatForm button[type="submit"]');
    appendChatMessage('user-message', message);
    if (chatInput) chatInput.value = '';
    const originalButtonContent = chatSendButton ? chatSendButton.innerHTML : '<i class="fas fa-paper-plane"></i>';
    const csrfToken = document.querySelector('input[name="csrf_token"]')?.value || document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    if (chatSendButton) { chatSendButton.disabled = true; chatSendButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span>`; }
    fetch('/ai/chatbot/api', { method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json', ...(csrfToken && { 'X-CSRFToken': csrfToken })}, body: JSON.stringify({ message: message, session_id: getSessionId() }) })
    .then(response => response.json().then(data => ({ ok: response.ok, data })))
    .then(result => {
        if (result.data.success) {
            if (result.data.response) { appendChatMessage('bot-message', result.data.response); }
            if (result.data.image_results && result.data.image_results.length > 0) { appendChatMessage('image-results', result.data.image_results); } }
        else { appendChatMessage('bot-message', result.data.message || 'Lỗi từ server.'); } })
    .catch(error => { console.error('Chatbot API Error:', error); appendChatMessage('bot-message', 'Lỗi kết nối chatbot.'); })
    .finally(() => { if (chatSendButton) { chatSendButton.disabled = false; chatSendButton.innerHTML = originalButtonContent; } });
}

function uploadChatImage(file) {
    const formData = new FormData(); formData.append('image_file', file);
    const csrfToken = document.querySelector('input[name="csrf_token"]')?.value || document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const chatUploadBtn = document.getElementById('chat-upload-btn');
    const originalBtnContent = chatUploadBtn ? chatUploadBtn.innerHTML : '<i class="fas fa-image"></i>';
    if (chatUploadBtn) { chatUploadBtn.disabled = true; chatUploadBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span>`; }
    fetch('/ai/chatbot/upload-image', { method: 'POST', headers: { 'Accept': 'application/json', ...(csrfToken && { 'X-CSRFToken': csrfToken }) }, body: formData })
    .then(response => response.json().then(data => ({ ok: response.ok, data })))
    .then(result => {
        if (result.ok && result.data.success) {
           if (result.data.message) appendChatMessage('bot-message', result.data.message);
           if (result.data.image_results && result.data.image_results.length > 0) { appendChatMessage('image-results', result.data.image_results); }
           else if (!result.data.message) { appendChatMessage('bot-message', "Xử lý ảnh xong, không tìm thấy SP tương đồng."); } }
        else { appendChatMessage('bot-message', result.data.message || 'Lỗi xử lý ảnh.'); } })
    .catch(error => { console.error('Image Upload Error:', error); appendChatMessage('bot-message', `Lỗi upload ảnh: ${error.message}`); })
    .finally(() => { if (chatUploadBtn) { chatUploadBtn.disabled = false; chatUploadBtn.innerHTML = originalBtnContent; } });
}

function getSessionId() {
    let sessionId = sessionStorage.getItem('chatbot_session_id');
    if (!sessionId) { sessionId = crypto.randomUUID ? crypto.randomUUID() : `session-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`; sessionStorage.setItem('chatbot_session_id', sessionId); }
    return sessionId;
}


document.addEventListener('DOMContentLoaded', function() {
    console.log("DOM loaded. Initializing...");
    initializeBootstrapComponents();
    animateOnScroll();
    setupQuantityControls(); // Cần cho trang product_detail
    setupContactForm();
    setupChatbot();
    setupAddToCartButtons(); // *** GỌI HÀM NÀY ***
    updateCartBadge();
    console.log("Initializations complete.");
});