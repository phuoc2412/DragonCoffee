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


// --- Cập nhật phần Khởi tạo trong DOMContentLoaded ---
document.addEventListener('DOMContentLoaded', function() {
    console.log("DOM loaded. Initializing...");
    initializeBootstrapComponents();
    animateOnScroll();
    setupQuantityControls();
    setupContactForm();
    setupChatbot();
    setupAddToCartButtons();
    setupReviewFormSubmit(); // Giữ lại nếu trang detail dùng chung main.js
    setupQuickViewModal(); // <-- **GỌI HÀM SETUP MODAL**
    updateCartBadge();
    // ---- GỌI LẠI HÀM LỌC CHO MENU PAGE NẾU CÓ CÁC ELEMENT CỦA NÓ ----
     if (document.getElementById('menu-search-form')) {
         setupMenuFiltersAndSearch(); // Đóng gói code JS cho menu vào hàm này
    }
    console.log("Initializations complete.");
});

function setupMenuFiltersAndSearch() {
    // Logic AJAX filter menu giữ nguyên như cũ...
    console.log("Setting up Menu Filters and AJAX Search...");
    const categoryNav = document.querySelector('.category-nav .nav');
   const productGrid = document.getElementById('product-grid');
   const loadingSpinner = document.getElementById('product-grid-loading');
   const categoryDescriptionContainer = document.getElementById('category-description-container');
   const searchForm = document.getElementById('menu-search-form');
   const searchInput = document.getElementById('menu-search-input');
   const sortSelectContainer = document.getElementById('sort-select'); // Container <ul> cho dropdown
   const currentSortLabel = document.getElementById('current-sort-label');
   const suggestionsContainer = document.getElementById('menu-search-suggestions-container');
   const suggestionsList = document.getElementById('menu-search-suggestions-list');
   let suggestionDebounce;

   // Lấy state ban đầu
   let currentCategoryId = categoryNav ? categoryNav.querySelector('.nav-link.active')?.dataset.categoryId || '' : '';
   let currentSearchTerm = searchInput ? searchInput.value : '';
   let currentSortBy = sortSelectContainer ? sortSelectContainer.querySelector('.dropdown-item.active')?.dataset.sort || 'name' : 'name';

   function fetchProducts() {
       // Nội dung hàm fetch giữ nguyên
       console.log(`Fetching products: Cat=${currentCategoryId}, Q=${currentSearchTerm}, Sort=${currentSortBy}`);
       if (loadingSpinner) loadingSpinner.classList.add('active');
       if (productGrid) productGrid.innerHTML = '';
       if (categoryDescriptionContainer) categoryDescriptionContainer.classList.add('d-none');
       const params = new URLSearchParams({ q: currentSearchTerm, sort: currentSortBy });
       if (currentCategoryId) { params.set('category_id', currentCategoryId); }
       const apiUrl = `/api/menu-products?${params.toString()}`;
       fetch(apiUrl)
           .then(response => { if (!response.ok) { throw new Error(`Network error (${response.status})`); } return response.json(); })
           .then(data => { if (loadingSpinner) loadingSpinner.classList.remove('active'); if (data.success && productGrid) { productGrid.innerHTML = data.html; initializeAnimationsForGrid(); } else if (!data.success) { throw new Error(data.message || 'Lỗi tải sản phẩm'); } else { console.error("productGrid not found"); } })
           .catch(error => { console.error('Fetch Products Error:', error); if (loadingSpinner) loadingSpinner.classList.remove('active'); if (productGrid) productGrid.innerHTML = `<div class="col-12 text-center py-5"><p class="text-danger">Lỗi: ${error.message}</p></div>`; });
   }

   function updateBrowserUrl() {
       // Nội dung hàm update url giữ nguyên
        const params = new URLSearchParams(); if (currentSearchTerm) params.set('q', currentSearchTerm); if (currentCategoryId) params.set('category', currentCategoryId); if (currentSortBy !== 'name') params.set('sort', currentSortBy); const newUrl = `${window.location.pathname}?${params.toString()}`; history.pushState({ categoryId: currentCategoryId, q: currentSearchTerm, sort: currentSortBy }, '', newUrl);
    }

   if (categoryNav) { categoryNav.addEventListener('click', function(event) { if (event.target.matches('.category-filter-btn')) { /* ... logic cũ ... */ event.preventDefault(); const button = event.target; const newCategoryId = button.dataset.categoryId; if (newCategoryId !== currentCategoryId) { categoryNav.querySelectorAll('.nav-link').forEach(btn => btn.classList.remove('active')); button.classList.add('active'); currentCategoryId = newCategoryId; currentSearchTerm = ''; if(searchInput) searchInput.value = ''; fetchProducts(); updateBrowserUrl(); } } }); }
   if (sortSelectContainer) { sortSelectContainer.addEventListener('click', function(event){ if(event.target.matches('.dropdown-item')) { /* ... logic cũ ... */ event.preventDefault(); const selectedOption = event.target; const newSortBy = selectedOption.dataset.sort; if (newSortBy !== currentSortBy) { if(currentSortLabel) currentSortLabel.textContent = selectedOption.textContent; sortSelectContainer.querySelectorAll('.dropdown-item').forEach(item => item.classList.remove('active')); selectedOption.classList.add('active'); currentSortBy = newSortBy; fetchProducts(); updateBrowserUrl(); } }}); const initialActiveSort = sortSelectContainer.querySelector('.dropdown-item.active'); if (initialActiveSort && currentSortLabel) { currentSortLabel.textContent = initialActiveSort.textContent; } }
   if (searchForm) { searchForm.addEventListener('submit', function(event) { /* ... logic cũ ... */ event.preventDefault(); const newSearchTerm = searchInput ? searchInput.value.trim() : ''; if (newSearchTerm !== currentSearchTerm) { currentSearchTerm = newSearchTerm; fetchProducts(); updateBrowserUrl(); } if (suggestionsContainer) suggestionsContainer.style.display = 'none'; }); }
   if (searchInput && suggestionsContainer && suggestionsList) { searchInput.addEventListener('input', function() { /* ... logic gợi ý search cũ ... */ const term = this.value.trim(); suggestionsList.innerHTML = ''; if (term.length < 1) { suggestionsContainer.style.display = 'none'; return; } clearTimeout(suggestionDebounce); suggestionDebounce = setTimeout(() => { fetch(`/menu/search_suggestions?term=${term}`) .then(response => response.json()) .then(suggestions => { if (suggestions.length > 0) { suggestionsList.innerHTML = ''; suggestions.forEach(suggestion => { const li = document.createElement('li'); li.classList.add('list-group-item'); let imgHtml = `<div class="suggestion-no-img"><i class="fas fa-image"></i></div>`; if(suggestion.image_url) { imgHtml = `<img src="${suggestion.image_url}" alt="${suggestion.name}" class="suggestion-img">`; } li.innerHTML = `${imgHtml}<span class="suggestion-name">${suggestion.name}</span>`; li.addEventListener('click', function() { searchInput.value = suggestion.name; suggestionsContainer.style.display = 'none'; searchForm.dispatchEvent(new Event('submit')); }); suggestionsList.appendChild(li); }); suggestionsContainer.style.display = 'block'; } else { suggestionsContainer.style.display = 'none'; } }) .catch(error => { console.error("Error fetching suggestions:", error); suggestionsContainer.style.display = 'none'; }); }, 300); }); document.addEventListener('click', function(event) { if (searchInput && !searchInput.contains(event.target) && !suggestionsContainer.contains(event.target)) { suggestionsContainer.style.display = 'none'; } }); }

   fetchProducts(); // Load ban đầu

   function initializeAnimationsForGrid() { if (typeof animateOnScroll === 'function') animateOnScroll(); }

   console.log("Menu Filters and Search Setup complete.");
} // End of setupMenuFiltersAndSearch

// --- Gọi hàm setup trong DOMContentLoaded ---
document.addEventListener('DOMContentLoaded', function() {
   console.log("DOM loaded. Initializing...");
   initializeBootstrapComponents();
   animateOnScroll();
   setupQuantityControls();
   setupContactForm();
   setupChatbot();
   setupAddToCartButtons();
   setupReviewFormSubmit();
   setupQuickViewModal(); // Gọi setup modal
   updateCartBadge();

   // Chỉ gọi setup menu nếu đang ở trang menu
   if (document.getElementById('product-grid-container')) { // Kiểm tra element đặc trưng của trang menu
       setupMenuFiltersAndSearch();
   }

   console.log("Initializations complete.");
});

function setupReviewFormSubmit() {
    const reviewForm = document.getElementById('reviewSubmitForm');
    const reviewTextarea = document.getElementById('reviewContentInput');
    const reviewSubmitButton = reviewForm ? reviewForm.querySelector('button[type="submit"]') : null;
    const toxicityPlaceholder = "[AI ĐÃ LỌC]"; // Phải giống backend
    const warningPlaceholder = "Ngôn từ không phù hợp ("+ new Date().toLocaleTimeString() + ") " + toxicityPlaceholder; // Nội dung sẽ lưu DB


    if (!reviewForm || !reviewTextarea || !reviewSubmitButton) {
        // console.log("Review form elements not found, skipping setup.");
        return; // Thoát nếu không phải trang có form review
    }

    let isSubmitting = false; // Cờ chống submit liên tục

    reviewForm.addEventListener('submit', function(event) {
        event.preventDefault(); // Luôn chặn gửi form mặc định trước
        event.stopPropagation();

        if (isSubmitting) {
            console.warn("Review submission already in progress.");
            return;
        }

        const reviewContent = reviewTextarea.value.trim();
        const originalButtonHTML = reviewSubmitButton.innerHTML;

        if (reviewContent.length < 5) { // Kiểm tra độ dài tối thiểu (tùy chọn)
            showToast('Nội dung đánh giá cần ít nhất 5 ký tự.', 'warning');
            return;
        }
         if (reviewContent === warningPlaceholder) { // Nếu user cố submit lại placeholder
             showToast('Nội dung đã được lọc, vui lòng không gửi lại.', 'warning');
             return;
         }


        // === Gọi API Check Toxicity ===
        isSubmitting = true;
        reviewSubmitButton.disabled = true;
        reviewSubmitButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Đang kiểm tra...`;
        const csrfToken = reviewForm.querySelector('input[name="csrf_token"]')?.value || document.querySelector('meta[name="csrf-token"]')?.content;

        fetch('/review/check-toxicity', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                ...(csrfToken && { 'X-CSRFToken': csrfToken })
            },
            body: JSON.stringify({ content: reviewContent })
        })
        .then(response => response.json().then(data => ({ ok: response.ok, status: response.status, data })))
        .then(result => {
            if (!result.ok) { throw new Error(result.data.message || `Lỗi server (${result.status})`); }

            if (result.data.blocked) {
                showToast(result.data.message || 'Tài khoản của bạn bị chặn bình luận.', 'danger');
                // Không làm gì thêm, form bị chặn ở server side rồi
                isSubmitting = false; // Reset cờ
                reviewSubmitButton.disabled = true; // Disable hẳn nút nếu bị block
                reviewSubmitButton.innerHTML = "Đã bị chặn";
            } else if (result.data.is_toxic) {
                showToast('Phát hiện ngôn từ không phù hợp! Bình luận sẽ được lọc.', 'warning');
                // *** Thay đổi nội dung và Gửi Form Mới ***
                reviewTextarea.value = warningPlaceholder; // Thay nội dung
                // Cân nhắc: Reset nút về trạng thái submit bình thường để user thấy nút "Gửi" lại
                reviewSubmitButton.innerHTML = originalButtonHTML; // '<i class="fas fa-paper-plane"></i> Gửi';
                reviewSubmitButton.disabled = false; // Enable lại để user gửi lại nội dung đã lọc (hoặc form.submit() ngay)

                // === TÙY CHỌN: TỰ ĐỘNG GỬI FORM ĐÃ LỌC SAU 1S ===
                // setTimeout(() => {
                //     if (!isSubmitting) { // Kiểm tra lại nếu cần
                //        console.log("Submitting filtered review content...");
                //        reviewForm.submit(); // Gửi form gốc (nhưng textarea đã bị thay đổi)
                //     }
                // }, 1000);
                // Hoặc BỎ timeout và để người dùng tự nhấn gửi lại với nội dung đã thay thế.
                isSubmitting = false; // Reset cờ (quan trọng nếu không tự submit)

            } else {
                // *** Không Toxic - Gửi Form Gốc ***
                console.log("Content is not toxic, submitting original form...");
                reviewForm.submit(); // Gọi submit() mặc định của form HTML
                // Nút sẽ ở trạng thái loading cho đến khi trang chuyển đi
                // Hoặc nếu muốn có thể bật lại nút sau 1 thời gian:
                // setTimeout(() => {
                //      if (reviewSubmitButton) {
                //          reviewSubmitButton.disabled = false;
                //          reviewSubmitButton.innerHTML = originalButtonHTML;
                //      }
                //      isSubmitting = false;
                // }, 3000); // Reset sau 3 giây nếu submit lâu
            }

        })
        .catch(error => {
            console.error('Error checking review toxicity:', error);
            showToast(`Lỗi kiểm tra nội dung: ${error.message}. Vui lòng thử gửi lại.`, 'danger');
            isSubmitting = false; // Reset cờ
            reviewSubmitButton.disabled = false; // Enable lại nút
            reviewSubmitButton.innerHTML = originalButtonHTML;
        });
    });
    console.log("Review form submit interception is active.");
}

// Gọi hàm setup trong DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    // ... (các hàm setup khác như updateCartBadge, etc.) ...
    setupReviewFormSubmit(); // <<< GỌI HÀM SETUP
});

function setupQuickViewModal() {
    const quickViewModalElement = document.getElementById('quickViewModal');
    if (!quickViewModalElement) {
        console.warn("Quick View Modal element not found, skipping setup.");
        return;
    }

    // ===> **Lấy instance Modal bằng JavaScript** <===
    const modal = bootstrap.Modal.getOrCreateInstance(quickViewModalElement);
    // -------------------------------------------------

    const modalTitle = document.getElementById('quickViewModalLabel');
    const modalLoading = document.getElementById('quickViewLoading');
    const modalContent = document.getElementById('quickViewContent');
    const modalImage = document.getElementById('quickViewImage');
    const modalCategory = document.getElementById('quickViewCategory');
    const modalDescription = document.getElementById('quickViewDescription');
    const modalPrice = document.getElementById('quickViewPrice');
    const modalProductIdInput = document.getElementById('quickViewProductId');
    const modalQuantityInput = document.getElementById('quickViewQuantity');
    const modalNotesInput = document.getElementById('quickViewNotes');
    const modalAddToCartForm = document.getElementById('quickViewAddToCartForm');
    const modalFullDetailLink = document.getElementById('quickViewFullDetailLink');

    document.body.addEventListener('click', function(event) {
        const triggerButton = event.target.closest('.quick-view-trigger');
        if (triggerButton) {
            event.preventDefault();
            const productId = triggerButton.dataset.productId;

            if (!productId) {
                console.error("Quick view trigger missing data-product-id");
                showToast("Lỗi: Không tìm thấy ID sản phẩm.", "danger");
                return;
            }

            modalContent.classList.add('d-none');
            modalLoading.style.display = 'block';
            modalTitle.textContent = 'Đang tải...';
            modalImage.src = '#'; modalImage.alt = ''; modalCategory.textContent = '';
            modalDescription.textContent = ''; modalPrice.textContent = '';
            modalProductIdInput.value = ''; modalQuantityInput.value = '1';
            modalNotesInput.value = ''; modalFullDetailLink.href = '#';

            // ====> **HIỂN THỊ MODAL BẰNG JAVASCRIPT** <====
            modal.show();
            // --------------------------------------------

            fetch(`/api/product/${productId}`)
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(errData => { throw new Error(errData.message || `Lỗi ${response.status}`); })
                                           .catch(() => { throw new Error(`Không thể tải sản phẩm (Lỗi ${response.status})`); });
                    }
                    return response.json();
                })
                .then(data => {
                    modalLoading.style.display = 'none';
                    if (data.success) {
                        const product = data.product;
                        modalTitle.textContent = product.name;
                        modalImage.src = product.image_url;
                        modalImage.alt = product.name;
                        modalImage.style.display = 'block'; // Ensure image is visible
                        modalCategory.textContent = product.category_name;
                        modalDescription.innerHTML = product.description.replace(/\n/g, '<br>');
                        modalPrice.textContent = product.formatted_price;
                        modalProductIdInput.value = product.id;
                        modalFullDetailLink.href = `/product/${product.id}`;
                        modalAddToCartForm.style.display = 'block'; // Ensure form is visible
                        modalContent.classList.remove('d-none');
                    } else {
                        throw new Error(data.message || "Không thể tải thông tin sản phẩm.");
                    }
                })
                .catch(error => {
                    console.error('Quick View Fetch Error:', error);
                    modalLoading.style.display = 'none';
                    modalContent.classList.remove('d-none');
                    modalTitle.textContent = "Lỗi";
                    modalDescription.innerHTML = `<p class="text-danger">${error.message}</p>`;
                    modalImage.style.display = 'none';
                    modalCategory.textContent = '';
                    modalPrice.textContent = '';
                    modalAddToCartForm.style.display = 'none'; // Hide form on error
                });
        }

        const qtyButton = event.target.closest('.quick-qty-btn');
        if (qtyButton && qtyButton.closest('#quickViewModal')) {
            const action = qtyButton.dataset.action;
            const input = document.getElementById('quickViewQuantity');
            if (input) {
                let currentVal = parseInt(input.value) || 1; // Default to 1 if NaN
                const min = parseInt(input.min) || 1;
                const max = parseInt(input.max) || 99;
                if (action === 'inc' && currentVal < max) { input.value = currentVal + 1; }
                else if (action === 'dec' && currentVal > min) { input.value = currentVal - 1; }
            }
        }
    });

    if (modalAddToCartForm) {
        modalAddToCartForm.addEventListener('submit', function(event) {
            event.preventDefault();
            const productId = modalProductIdInput.value;
            const quantity = modalQuantityInput.value;
            const notes = modalNotesInput.value;

            if (!productId) {
                showToast("Lỗi: ID sản phẩm không xác định trong modal.", "danger");
                return;
            }

            // Gọi hàm addToCart đã có
            addToCart(productId, quantity, '', notes); // Size '' vì quick view không có chọn size

            modal.hide();
        });
    } else {
        console.error("Quick View Add to Cart Form not found.");
    }

    console.log("Quick View Modal setup complete.");
}
