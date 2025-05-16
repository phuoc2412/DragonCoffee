// static/js/main.js

function showToast(message, type = 'info') {
    const toastBgClasses = {
        success: 'text-bg-success', danger: 'text-bg-danger', error: 'text-bg-danger',
        warning: 'text-bg-warning text-dark', 
        info: 'text-bg-info', primary: 'text-bg-primary',
        secondary: 'text-bg-secondary', light: 'text-bg-light text-dark', dark: 'text-bg-dark'
    };
    const textClass = (type === 'light' || type === 'warning') ? 'text-dark' : 'text-white';
    const btnCloseClass = (type === 'light' || type === 'warning') ? '' : 'btn-close-white';

    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        toastContainer.style.zIndex = "1150"; 
        document.body.appendChild(toastContainer);
    }

    const toastId = 'toast-' + Date.now();
    const iconClass = type === 'success' ? 'fa-check-circle' 
                    : (type === 'danger' || type === 'error' ? 'fa-exclamation-triangle' 
                    : (type === 'warning' ? 'fa-exclamation-circle' 
                    : 'fa-info-circle'));

    const toastHtml = `
        <div id="${toastId}" class="toast align-items-center ${toastBgClasses[type] || 'text-bg-secondary'} ${textClass} border-0" role="alert" aria-live="assertive" aria-atomic="true" data-bs-delay="4500">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas ${iconClass} me-2"></i> 
                    <span>${message}</span>
                </div>
                <button type="button" class="btn-close ${btnCloseClass} me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastElement = document.getElementById(toastId);

    if (toastElement && typeof bootstrap !== 'undefined' && bootstrap.Toast) {
         try {
             const bsToast = new bootstrap.Toast(toastElement);
             toastElement.addEventListener('hidden.bs.toast', () => toastElement.remove());
             bsToast.show();
         } catch (e) {
             console.error("Error showing Bootstrap toast:", e);
             alert(`${type.toUpperCase()}: ${message}`); 
             if(toastElement) toastElement.remove();
         }
     } else {
         console.warn('Bootstrap Toast component not available or toastElement not found. Fallback alert.');
         alert(`${type.toUpperCase()}: ${message}`); 
         if (toastElement) toastElement.remove(); 
     }
}

function updateCartBadge() {
    fetch('/order/cart-count')
        .then(response => response.ok ? response.json() : Promise.reject('Network error'))
        .then(data => {
            const badge = document.querySelector('.navbar .cart-badge');
            if (!badge) return;
            if (data && typeof data.count === 'number') {
                badge.textContent = data.count;
                badge.style.display = data.count > 0 ? 'inline-block' : 'none';
            } else { badge.textContent = '0'; badge.style.display = 'none'; }
        })
        .catch(error => { console.error('Error updating cart badge:', error); const badge = document.querySelector('.navbar .cart-badge'); if(badge) badge.style.display = 'none'; });
}

function addToCart(productId, quantity = 1, size = '', notes = '', isBuyNow = false) {
    const parsedProductId = parseInt(productId);
    if (isNaN(parsedProductId) || parsedProductId <= 0) {
        showToast('Lỗi: ID sản phẩm không hợp lệ.', 'danger');
        return;
    }

    const data = {
        product_id: parsedProductId,
        quantity: parseInt(quantity) || 1
    };
    if (notes && notes.trim()) { data.notes = notes.trim(); }

    const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfTokenMeta ? csrfTokenMeta.getAttribute('content') : null;

    fetch('/order/add-to-cart', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            ...(csrfToken && { 'X-CSRFToken': csrfToken })
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        // KIỂM TRA PHẢN HỒI 401 TẠI ĐÂY
        if (response.status === 401) {
            // Ném lỗi LOGIN_REQUIRED để catch bên dưới xử lý bằng custom notification
            throw new Error('LOGIN_REQUIRED');
        }
        // Tiếp tục xử lý JSON nếu không phải 401
        return response.json().then(jsonData => {
            return { ok: response.ok, status: response.status, data: jsonData };
        }).catch(jsonError => { // Thêm catch ở đây nếu response.json() lỗi
            console.error("Failed to parse JSON from /order/add-to-cart:", jsonError);
            console.error("Response that failed to parse as JSON might be HTML:", response);
            throw new Error(`Server returned non-JSON response (Status: ${response.status})`);
        });
    })
    .then(result => { // `result` sẽ là `{ ok, status, data }`
        if (!result.ok || !result.data.success) {
             throw new Error(result.data.message || `Lỗi từ máy chủ (${result.status})`);
        }
        showToast(result.data.message || 'Đã thêm vào giỏ!', 'success');
        updateCartBadge();
        if (isBuyNow) {
            window.location.href = '/order/checkout';
        }
    })
    .catch(error => {
        if (error.message === 'LOGIN_REQUIRED') {
            // HIỂN THỊ CUSTOM NOTIFICATION
            showCustomNotification(
                'Bạn cần đăng nhập để thêm vào giỏ.',
                'fa-user-lock', // Font Awesome icon class
                'warning',      // Type (ảnh hưởng màu icon/box nếu bạn style)
                3000            // Thời gian hiển thị (ms)
            );
            // KHÔNG mở login modal nữa
        } else {
            console.error('Add to Cart Error (Other):', error);
            showToast(`Lỗi khi thêm vào giỏ: ${error.message}`, 'danger');
        }
    });
}

function setupAddToCartButtons() {
    document.body.addEventListener('click', function(event) {
        const button = event.target.closest('.add-to-cart-btn');
        if (!button) return;
        event.preventDefault(); event.stopPropagation();
        const productId = button.dataset.productId;
        if (!productId) { showToast("Lỗi: Không thấy ID sản phẩm.", "danger"); return; }
        let quantity = 1; let notes = '';
        const form = button.closest('form#add-to-cart-form');
        if (form) { quantity = form.querySelector('input#quantity')?.value || 1; notes = form.querySelector('textarea#notes')?.value || ''; }
        const isBuyNow = button.dataset.action === 'buy-now';
        addToCart(productId, quantity, '', notes, isBuyNow);
    });
}

function initializeBootstrapComponents() {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    [...tooltipTriggerList].map(el => {
        const existing = bootstrap.Tooltip.getInstance(el); if(existing) existing.dispose(); return new bootstrap.Tooltip(el);
    });
    const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
    [...popoverTriggerList].map(el => {
        const existing = bootstrap.Popover.getInstance(el); if(existing) existing.dispose(); return new bootstrap.Popover(el);
    });
}

function animateOnScroll() {
    const animatedElements = document.querySelectorAll('.animate-on-scroll');
    if (typeof IntersectionObserver === 'undefined' || animatedElements.length === 0) { animatedElements.forEach(el => el.style.visibility = 'visible'); return; }
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.visibility = 'visible'; entry.target.classList.add('animate__animated');
                const animation = entry.target.dataset.animation || 'animate__fadeInUp';
                const delay = entry.target.dataset.animationDelay || entry.target.style.animationDelay || '0s';
                entry.target.style.animationDelay = delay; entry.target.classList.add(animation);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });
    animatedElements.forEach(el => { el.style.visibility = 'hidden'; observer.observe(el); });
}

function setupQuantityControls() {
    document.body.addEventListener('click', function(event) {
        const target = event.target;
        if (target.classList.contains('qty-btn') || target.closest('.qty-btn')) {
            const button = target.closest('.qty-btn');
            const inputGroup = button?.closest('.input-group');
            const input = inputGroup?.querySelector('input[type="number"]');
            if (!input || !button) return;
            let value = parseInt(input.value) || 1;
            const min = parseInt(input.min) || 1;
            const max = parseInt(input.max) || 99;
            const actionId = button.id; // Check id (incQty/decQty) or data-action if using data attributes
            const action = button.dataset.action; // Prefer data-action if exists
            if ((actionId === 'incQty' || action === 'inc') && value < max) value++;
            else if ((actionId === 'decQty' || action === 'dec') && value > min) value--;
            input.value = value; input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });
    document.querySelectorAll('input[type="number"].cart-quantity-input, input#quantity').forEach(input => {
        input.addEventListener('change', function() {
            const min = parseInt(this.min) || 1; const max = parseInt(this.max) || 99; let val = parseInt(this.value);
            if (isNaN(val) || val < min) this.value = min; else if (val > max) this.value = max;
        });
    });
}


function setupContactForm() {
    const contactForm = document.querySelector('form[action="/contact"]');
    if (!contactForm) return;
    contactForm.addEventListener('submit', function(event) {
        event.preventDefault(); const formData = new FormData(contactForm);
        const submitButton = contactForm.querySelector('button[type="submit"]');
        const originalBtnHtml = submitButton ? submitButton.innerHTML : 'Gửi';
        const csrfToken = contactForm.querySelector('input[name="csrf_token"]')?.value || document.querySelector('meta[name="csrf-token"]')?.content;
        if (submitButton) { submitButton.disabled = true; submitButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Gửi...`; }
        fetch(contactForm.action, { method: 'POST', body: formData, headers: {'Accept': 'application/json', ...(csrfToken && {'X-CSRFToken': csrfToken})} })
        .then(response => response.json().then(data => ({ ok: response.ok, data })))
        .then(result => { if (result.ok && result.data.success) { showToast(result.data.message || 'Đã gửi!', 'success'); contactForm.reset(); } else { throw new Error(result.data.message || 'Gửi thất bại'); } })
        .catch(error => { showToast(`Lỗi: ${error.message}`, 'danger'); })
        .finally(() => { if (submitButton) { submitButton.disabled = false; submitButton.innerHTML = originalBtnHtml; } });
    });
}


function setupReviewFormSubmit() {
    const reviewForm = document.getElementById('reviewSubmitForm');
    const reviewTextarea = document.getElementById('reviewContentInput');
    if (!reviewForm || !reviewTextarea) return;
    const reviewSubmitButton = reviewForm.querySelector('button[type="submit"]');
    let isSubmittingReview = false;
    const originalButtonHTML = reviewSubmitButton ? reviewSubmitButton.innerHTML : 'Gửi';
    const toxicityPlaceholder = "[AI ĐÃ LỌC]";

    reviewForm.addEventListener('submit', function(event) {
        event.preventDefault(); event.stopPropagation();
        if (isSubmittingReview) return;
        const reviewContent = reviewTextarea.value.trim();
        if (reviewContent.length < 5) { showToast('Nội dung đánh giá cần ít nhất 5 ký tự.', 'warning'); return; }
        if (reviewContent.startsWith(toxicityPlaceholder)) { showToast('Nội dung không hợp lệ.', 'warning'); return; }
        isSubmittingReview = true; reviewSubmitButton.disabled = true; reviewSubmitButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Đang kiểm tra...`;
        const csrfToken = reviewForm.querySelector('input[name="csrf_token"]')?.value || document.querySelector('meta[name="csrf-token"]')?.content;
        fetch('/review/check-toxicity', {
            method: 'POST', headers: {'Content-Type':'application/json','Accept':'application/json', ...(csrfToken && {'X-CSRFToken':csrfToken})},
            body: JSON.stringify({ content: reviewContent })
        })
        .then(response => response.json().then(data => ({ ok: response.ok, status: response.status, data })))
        .then(result => {
            if (!result.ok) throw new Error(result.data.message || `Lỗi server (${result.status})`);
            if (result.data.blocked) { throw new Error('Tài khoản của bạn bị chặn bình luận.'); }
            if (result.data.is_toxic) {
                 showToast('Phát hiện ngôn từ không phù hợp!', 'warning');
                 reviewTextarea.value = `${toxicityPlaceholder}\n(Nội dung gốc đã bị ẩn do vi phạm)`; // Chỉ hiện placeholder
                 isSubmittingReview = false; reviewSubmitButton.disabled = false; reviewSubmitButton.innerHTML = originalButtonHTML;
            } else { reviewSubmitButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Đang gửi...`; reviewForm.submit(); } // Gửi form gốc nếu sạch
        })
        .catch(error => { showToast(`Lỗi: ${error.message}`, 'danger'); isSubmittingReview = false; reviewSubmitButton.disabled = false; reviewSubmitButton.innerHTML = originalButtonHTML; });
    });
}

function setupQuickViewModal() {
    const quickViewModalElement = document.getElementById('quickViewModal');
    if (!quickViewModalElement) return;
    const modal = bootstrap.Modal.getOrCreateInstance(quickViewModalElement);
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
        if (!triggerButton) return;
        event.preventDefault(); const productId = triggerButton.dataset.productId;
        if (!productId) { showToast("Lỗi: Không thấy ID sản phẩm.", "danger"); return; }

        modalContent.classList.add('d-none'); modalLoading.style.display = 'block';
        modalTitle.textContent = 'Đang tải...'; modalImage.src = '#'; modalQuantityInput.value = '1'; modalNotesInput.value = '';
        modal.show();

        fetch(`/api/product/${productId}`)
            .then(response => response.json().then(data => ({ ok: response.ok, status: response.status, data })))
            .then(result => {
                modalLoading.style.display = 'none';
                if (result.ok && result.data.success) {
                    const p = result.data.product;
                    modalTitle.textContent = p.name; modalImage.src = p.image_url; modalImage.alt = p.name;
                    modalImage.style.display='block'; modalCategory.textContent = p.category_name;
                    modalDescription.innerHTML = p.description.replace(/\n/g,'<br>'); modalPrice.textContent = p.formatted_price;
                    modalProductIdInput.value = p.id; modalFullDetailLink.href = `/product/${p.id}`;
                    modalAddToCartForm.style.display='block'; modalContent.classList.remove('d-none');
                } else { throw new Error(result.data.message || `Lỗi tải SP (${result.status})`); }
            })
            .catch(error => {
                modalLoading.style.display='none'; modalContent.classList.remove('d-none');
                modalTitle.textContent = "Lỗi"; modalDescription.innerHTML=`<p class="text-danger">${error.message}</p>`;
                modalImage.style.display='none'; modalAddToCartForm.style.display='none';
            });
    });
    quickViewModalElement.addEventListener('click', function(event){
        const qtyBtn = event.target.closest('.quick-qty-btn');
        if(qtyBtn){
            const input = document.getElementById('quickViewQuantity'); if(!input) return;
            let val=parseInt(input.value)||1; let min=parseInt(input.min)||1; let max=parseInt(input.max)||99;
            if(qtyBtn.dataset.action==='inc' && val<max) input.value=val+1;
            else if(qtyBtn.dataset.action==='dec' && val>min) input.value=val-1;
        }
    });
    if (modalAddToCartForm) {
        modalAddToCartForm.addEventListener('submit', function(event) {
            event.preventDefault(); const productId = modalProductIdInput.value; const quantity = modalQuantityInput.value; const notes = modalNotesInput.value;
            if (productId) { addToCart(productId, quantity, '', notes); modal.hide(); }
            else { showToast("Lỗi: Không xác định được SP.", "danger"); }
        });
    }
}


function handleAuthFormSubmit(formElement, generalErrorDiv) {
    const submitButton = formElement.querySelector('button[type="submit"]');
    const spinner = submitButton?.querySelector('.spinner-border');
    const originalButtonHTML = submitButton?.innerHTML || 'Submit';

    submitButton.disabled = true; if (spinner) spinner.classList.remove('d-none');
    if (generalErrorDiv) generalErrorDiv.classList.add('d-none'); handleFormErrors(formElement, {});

    const formData = new FormData(formElement);
    const actionUrl = formElement.action;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || formElement.querySelector('input[name="csrf_token"]')?.value;

    fetch(actionUrl, {
        method: 'POST', body: new URLSearchParams(formData).toString(),
        headers: { 'Content-Type':'application/x-www-form-urlencoded', 'Accept':'application/json', ...(csrfToken && {'X-CSRFToken':csrfToken})}
    })
    .then(response => response.json().then(data => ({ ok: response.ok, status: response.status, data })))
    .then(result => {
        if (result.ok && result.data.success) {
            showToast(result.data.message || 'Thành công!', 'success');
            const modalEl = formElement.closest('.modal');
            if (modalEl) { const modalInstance = bootstrap.Modal.getInstance(modalEl); if (modalInstance) modalInstance.hide(); }
            if (result.data.redirect) setTimeout(() => { window.location.href = result.data.redirect; }, 300);
            else setTimeout(() => { window.location.reload(); }, 500);
        } else {
            if (result.data.errors) handleFormErrors(formElement, result.data.errors);
            else if (result.data.message) { if(generalErrorDiv) { generalErrorDiv.textContent = result.data.message; generalErrorDiv.classList.remove('d-none'); } else { showToast(result.data.message, 'danger'); }}
            else { const errMsg = `Lỗi ${result.status}.`; if(generalErrorDiv) { generalErrorDiv.textContent=errMsg; generalErrorDiv.classList.remove('d-none'); } else { showToast(errMsg, 'danger'); } }
        }
    })
    .catch(error => { const errMsg='Lỗi mạng/máy chủ.'; if(generalErrorDiv){ generalErrorDiv.textContent=errMsg; generalErrorDiv.classList.remove('d-none'); } else { showToast(errMsg, 'danger'); } })
    .finally(() => { if(submitButton) { submitButton.disabled = false; if(spinner) spinner.classList.add('d-none'); submitButton.innerHTML = originalButtonHTML; }});
}

function handleFormErrors(formElement, errors) {
    if (!formElement) return;
    formElement.querySelectorAll('.invalid-feedback').forEach(el => el.textContent = '');
    formElement.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
    for (const field in errors) {
        const errorList = errors[field];
        const feedbackDiv = formElement.querySelector(`.invalid-feedback[data-field="${field}"]`);
        const inputElement = formElement.querySelector(`[name="${field}"]`);
        if (inputElement) inputElement.classList.add('is-invalid');
        if (feedbackDiv && errorList.length > 0) feedbackDiv.textContent = errorList.join(' ');
    }
}

function setupAuthModals() {
    const loginForm = document.getElementById('loginModalForm');
    const registerForm = document.getElementById('registerModalForm');
    const loginModalEl = document.getElementById('loginModal');
    const registerModalEl = document.getElementById('registerModal');
    if (loginForm) loginForm.addEventListener('submit', (e) => { e.preventDefault(); handleAuthFormSubmit(loginForm, loginForm.querySelector('#login-modal-errors')); });
    if (registerForm) registerForm.addEventListener('submit', (e) => { e.preventDefault(); handleAuthFormSubmit(registerForm, registerForm.querySelector('#register-modal-errors')); });
    if (loginModalEl) loginModalEl.addEventListener('hidden.bs.modal', () => handleFormErrors(loginForm, {}));
    if (registerModalEl) registerModalEl.addEventListener('hidden.bs.modal', () => handleFormErrors(registerForm, {}));
}

function setupChatbot() {
    const chatbotContainer = document.getElementById('chatbot-container');
    const chatbotToggleBtn = document.getElementById('chatbot-toggle-btn');
    const chatbotMinimizeBtn = document.getElementById('chatbot-minimize-btn');
    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('chat-input');
    const chatForm = document.getElementById('chatForm');
    const chatUploadBtn = document.getElementById('chat-upload-btn');
    const chatImageInput = document.getElementById('chat-image-input');
    if (!chatbotContainer || !chatForm || !chatInput || !chatMessages || !chatbotToggleBtn || !chatbotMinimizeBtn || !chatUploadBtn || !chatImageInput) { console.warn("Chatbot elements missing."); return; }

    chatbotToggleBtn.addEventListener('click', (e) => { e.stopPropagation(); chatbotContainer.classList.toggle('collapsed'); const isClosed = chatbotContainer.classList.contains('collapsed'); if(!isClosed){ setTimeout(()=>{ try{chatMessages.scrollTop=chatMessages.scrollHeight; chatInput.focus();}catch(err){} }, 150);} });
    chatbotMinimizeBtn.addEventListener('click', (e) => { e.stopPropagation(); if(!chatbotContainer.classList.contains('collapsed')) chatbotContainer.classList.add('collapsed'); });

    chatForm.addEventListener('submit', function(event) {
        event.preventDefault(); event.stopPropagation();
        const userMessage = chatInput.value.trim();
        if (userMessage) { sendChatMessage(userMessage); }
    });

    chatUploadBtn.addEventListener('click', () => chatImageInput.click() );
    chatImageInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
             const reader = new FileReader(); reader.onload = e => appendChatMessage('user-message image-preview', `<img src="${e.target.result}" alt="Preview" style="max-width: 80px; border-radius: 4px;"> <small>Sending...</small>`); reader.readAsDataURL(file);
             uploadChatImage(file);
             chatImageInput.value = null;
        }
    });
}

function appendChatMessage(type, content) {
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) { console.error("Chat messages container not found!"); return; }
    const messageDiv = document.createElement('div'); messageDiv.classList.add('message', ...type.split(' '));

    if (type.includes('image-results') && Array.isArray(content)) {
        messageDiv.classList.add('bot-message');
        const title = document.createElement('p'); title.classList.add('image-results-title'); title.textContent = "Có phải bạn tìm món này?"; messageDiv.appendChild(title);
        const resultsWrapper = document.createElement('div'); resultsWrapper.classList.add('image-results-row', 'd-flex', 'flex-wrap', 'gap-2', 'mt-2', 'justify-content-center');
        if(content.length === 0) resultsWrapper.innerHTML = "<p class='small text-muted w-100'>Không tìm thấy ảnh phù hợp.</p>";
        else content.forEach(item => {
           const link = document.createElement('a'); link.href = item.product_url || '#'; link.classList.add('image-result-item','text-decoration-none','text-center'); link.target="_blank";
           const img = document.createElement('img'); img.src=item.image_url; img.alt=item.name; img.loading="lazy"; img.classList.add('img-thumbnail','mb-1'); img.style.cssText='width:70px; height:70px; object-fit:cover;';
           const nameSpan=document.createElement('span'); nameSpan.textContent=item.name; nameSpan.classList.add('d-block','small');
           link.appendChild(img); link.appendChild(nameSpan); resultsWrapper.appendChild(link); });
        messageDiv.appendChild(resultsWrapper);
    } else if (type.includes('image-preview')) {
         messageDiv.innerHTML = content;
    } else if (typeof content === 'string') {
        const p = document.createElement('p'); p.innerHTML = content.replace(/\n/g, '<br>'); messageDiv.appendChild(p);
    } else { console.warn("Invalid content for appendChatMessage:", content); return; }

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTo({ top: chatMessages.scrollHeight, behavior: 'smooth' });
}

function sendChatMessage(message) {
    const chatInput = document.getElementById('chat-input');
    const chatForm = document.getElementById('chatForm');
    const chatSendButton = chatForm?.querySelector('button[type="submit"]');
    const originalBtnHTML = chatSendButton?.innerHTML || '<i class="fas fa-paper-plane"></i>';

    appendChatMessage('user-message', message);
    if(chatInput) chatInput.value = '';
    if(chatSendButton) { chatSendButton.disabled = true; chatSendButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span>`; }

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    fetch('/ai/chatbot/api', {
        method: 'POST', headers: {'Content-Type':'application/json','Accept':'application/json',...(csrfToken && {'X-CSRFToken':csrfToken})},
        body: JSON.stringify({ message: message, session_id: getSessionId() })
    })
    .then(response => response.json().then(data => ({ ok: response.ok, data })))
    .then(result => {
        if (result.data.success) {
            if (result.data.response) { appendChatMessage('bot-message', result.data.response); }
            if (result.data.image_results?.length > 0) { appendChatMessage('image-results', result.data.image_results); } }
        else { appendChatMessage('bot-message', result.data.message || 'Lỗi!'); }
    })
    .catch(error => { appendChatMessage('bot-message', 'Lỗi kết nối.'); })
    .finally(() => { if(chatSendButton){ chatSendButton.disabled = false; chatSendButton.innerHTML = originalBtnHTML;} });
}

function uploadChatImage(file) {
    const formData = new FormData(); formData.append('image_file', file);
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const chatUploadBtn = document.getElementById('chat-upload-btn');
    const originalBtnHTML = chatUploadBtn?.innerHTML || '<i class="fas fa-image"></i>';
    if (chatUploadBtn) { chatUploadBtn.disabled = true; chatUploadBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span>`; }

    fetch('/ai/chatbot/upload-image', { method: 'POST', headers: {'Accept': 'application/json', ...(csrfToken && {'X-CSRFToken':csrfToken})}, body: formData })
    .then(response => response.json().then(data => ({ ok: response.ok, data })))
    .then(result => {
        if (result.ok && result.data.success) {
           if (result.data.message) appendChatMessage('bot-message', result.data.message);
           if (result.data.image_results?.length > 0) { appendChatMessage('image-results', result.data.image_results); }
           else if (!result.data.message) { appendChatMessage('bot-message', "Đã xử lý ảnh."); }
        } else { appendChatMessage('bot-message', result.data.message || 'Lỗi xử lý ảnh.'); }
    })
    .catch(error => { appendChatMessage('bot-message', `Lỗi upload: ${error.message}`); })
    .finally(() => { if (chatUploadBtn) { chatUploadBtn.disabled = false; chatUploadBtn.innerHTML = originalBtnHTML; } });
}

function getSessionId() {
    let sessionId = sessionStorage.getItem('chatbot_session_id');
    if (!sessionId) {
        sessionId = crypto.randomUUID ? crypto.randomUUID() : `session-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
        sessionStorage.setItem('chatbot_session_id', sessionId);
    }
    return sessionId;
}


function setupMenuFiltersAndSearch() {
    const productGridContainer = document.getElementById('product-grid-container');
    if (!productGridContainer) return;

    const categoryNav = document.querySelector('.category-nav .nav');
    const productGrid = document.getElementById('product-grid');
    const loadingSpinner = document.getElementById('product-grid-loading');
    const searchForm = document.getElementById('menu-search-form');
    const searchInput = document.getElementById('menu-search-input');
    const sortSelectContainer = document.getElementById('sort-select');
    const currentSortLabel = document.getElementById('current-sort-label');
    const suggestionsContainer = document.getElementById('menu-search-suggestions-container');
    const suggestionsList = document.getElementById('menu-search-suggestions-list');
    let suggestionDebounce;

    let currentCategoryId = categoryNav?.querySelector('.nav-link.active')?.dataset.categoryId || '';
    let currentSearchTerm = searchInput?.value || '';
    let currentSortBy = sortSelectContainer?.querySelector('.dropdown-item.active')?.dataset.sort || 'name';

    function fetchProducts() {
        if (loadingSpinner) loadingSpinner.classList.add('active');
        if (productGrid) productGrid.innerHTML = '';
        const params = new URLSearchParams({ q: currentSearchTerm, sort: currentSortBy });
        if (currentCategoryId) { params.set('category_id', currentCategoryId); }
        const apiUrl = `/api/menu-products?${params.toString()}`;

        fetch(apiUrl)
           .then(response => response.ok ? response.json() : Promise.reject('Network error'))
           .then(data => {
                if (loadingSpinner) loadingSpinner.classList.remove('active');
                if (data.success && productGrid) {
                    productGrid.innerHTML = data.html; initializeBootstrapComponents(); animateOnScroll(); // Re-init components/animations for new grid
                } else { throw new Error(data.message || 'Lỗi tải sản phẩm'); } })
           .catch(error => { if (loadingSpinner) loadingSpinner.classList.remove('active'); if (productGrid) productGrid.innerHTML = `<div class="col-12 text-danger p-5">Lỗi: ${error.message}</div>`; });
    }

    function updateBrowserUrl() {
        const params = new URLSearchParams();
        if (currentSearchTerm) params.set('q', currentSearchTerm);
        if (currentCategoryId) params.set('category', currentCategoryId);
        if (currentSortBy !== 'name') params.set('sort', currentSortBy);
        history.pushState({ }, '', `${window.location.pathname}?${params.toString()}`);
    }

    if(categoryNav) { categoryNav.addEventListener('click', e => { if(e.target.matches('.category-filter-btn')){ e.preventDefault(); const btn=e.target; const nId=btn.dataset.categoryId; if(nId !== currentCategoryId){ categoryNav.querySelectorAll('.nav-link').forEach(b => b.classList.remove('active')); btn.classList.add('active'); currentCategoryId = nId; currentSearchTerm = ''; if(searchInput) searchInput.value = ''; fetchProducts(); updateBrowserUrl(); }}}); }
    if(sortSelectContainer) { sortSelectContainer.addEventListener('click', e => { if(e.target.matches('.dropdown-item')){ e.preventDefault(); const opt=e.target; const nSort=opt.dataset.sort; if(nSort !== currentSortBy){ if(currentSortLabel) currentSortLabel.textContent = opt.textContent; sortSelectContainer.querySelectorAll('.dropdown-item').forEach(i => i.classList.remove('active')); opt.classList.add('active'); currentSortBy = nSort; fetchProducts(); updateBrowserUrl(); }}}); const iSort = sortSelectContainer.querySelector('.dropdown-item.active'); if(iSort && currentSortLabel) currentSortLabel.textContent = iSort.textContent; }
    if(searchForm) { searchForm.addEventListener('submit', e => { e.preventDefault(); const nTerm = searchInput?.value.trim() || ''; if(nTerm !== currentSearchTerm){ currentSearchTerm = nTerm; fetchProducts(); updateBrowserUrl(); } if(suggestionsContainer) suggestionsContainer.style.display = 'none'; }); }
    if(searchInput && suggestionsContainer && suggestionsList) { searchInput.addEventListener('input', function(){ const term = this.value.trim(); suggestionsList.innerHTML=''; if(term.length < 1){ suggestionsContainer.style.display = 'none'; return; } clearTimeout(suggestionDebounce); suggestionDebounce = setTimeout(()=>{ fetch(`/menu/search_suggestions?term=${term}`).then(r=>r.json()).then(suggs=>{if(suggs.length > 0){suggestionsList.innerHTML=''; suggs.forEach(s=>{const li = document.createElement('li');li.className='list-group-item'; let img = `<div class="suggestion-no-img"><i class="fas fa-image"></i></div>`; if(s.image_url) img = `<img src="${s.image_url}" alt="${s.name}" class="suggestion-img">`; li.innerHTML=`${img}<span class="suggestion-name">${s.name}</span>`; li.onclick=()=>{searchInput.value=s.name; suggestionsContainer.style.display = 'none'; searchForm.requestSubmit?searchForm.requestSubmit():searchForm.submit();}; suggestionsList.appendChild(li);}); suggestionsContainer.style.display = 'block';} else {suggestionsContainer.style.display='none';}}).catch(e=>suggestionsContainer.style.display='none');}, 300);}); document.addEventListener('click',e=>{if(searchInput && !searchInput.contains(e.target) && !suggestionsContainer.contains(e.target)) suggestionsContainer.style.display='none';});}

    // Initial fetch if on menu page
    if(document.getElementById('product-grid-container')) { fetchProducts(); }
}

// --- CART PAGE SPECIFIC ---
function updateCartItemUI(productId, newQuantity, newItemSubtotal) {
    const cartItemRow = document.querySelector(`.cart-item[data-product-id="${productId}"]`);
    if (!cartItemRow) return;
    const quantityInput = cartItemRow.querySelector('.cart-quantity-input');
    const subtotalElement = cartItemRow.querySelector('.cart-item-subtotal');
    if (quantityInput) quantityInput.value = newQuantity;
    if (subtotalElement && newItemSubtotal !== undefined) { subtotalElement.textContent = `$${parseFloat(newItemSubtotal).toFixed(2)}`; }
}

function updateCartSummaryUI(subtotal, tax, total) {
    const subtotalEl = document.querySelector('.cart-subtotal-value');
    const taxEl = document.querySelector('.cart-tax-value');
    const totalEl = document.querySelector('.cart-total-value');
    if (subtotalEl && subtotal !== undefined) subtotalEl.textContent = `$${parseFloat(subtotal).toFixed(2)}`;
    if (taxEl && tax !== undefined) taxEl.textContent = `$${parseFloat(tax).toFixed(2)}`;
    if (totalEl && total !== undefined) totalEl.textContent = `$${parseFloat(total).toFixed(2)}`;
}

function setupCartPageInteractions() {
    const cartContainer = document.querySelector('.cart-list'); // Target the list specifically
    if (!cartContainer) return;
    cartContainer.addEventListener('click', function(event) {
        const target = event.target;
        if (target.classList.contains('cart-quantity-btn') || target.closest('.cart-quantity-btn')) {
             const button = target.closest('.cart-quantity-btn');
             const cartItemRow = button.closest('.cart-item');
             const input = cartItemRow?.querySelector('.cart-quantity-input');
             const productId = cartItemRow?.dataset.productId;
             if (!input || !productId || !button) return;
             let currentQuantity = parseInt(input.value); let newQuantity = currentQuantity;
             if (button.classList.contains('increment') || button.dataset.action === 'increase') newQuantity++;
             else if (button.classList.contains('decrement') || button.dataset.action === 'decrease') newQuantity = Math.max(1, currentQuantity - 1);
             if (newQuantity !== currentQuantity) { updateCartItemAJAX(productId, newQuantity); button.disabled = true; setTimeout(() => {button.disabled = false;}, 700); }
        } else if (target.closest('.remove-from-cart-btn')) {
             const removeButton = target.closest('.remove-from-cart-btn');
             const cartItemRow = removeButton.closest('.cart-item');
             const productId = removeButton.dataset.productId || cartItemRow?.dataset.productId;
             if (productId && confirm('Bạn chắc chắn muốn xóa sản phẩm này?')) {
                  const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]'); const csrfToken = csrfTokenMeta?.content;
                  fetch(`/order/remove-from-cart/${productId}`, {method:'POST', headers:{'Accept':'application/json', ...(csrfToken&&{'X-CSRFToken':csrfToken})}})
                  .then(r => r.ok ? r.json() : Promise.reject(`Lỗi ${r.status}`))
                  .then(data => {
                      if (data.success) { if(cartItemRow) cartItemRow.remove(); updateCartSummaryUI(data.cart_subtotal, data.cart_tax, data.cart_total); updateCartBadge(); showToast('Đã xóa sản phẩm.', 'success');
                           if(data.cart_count === 0) {
                                cartContainer.innerHTML = `<div class="text-center py-4"><p>Giỏ hàng của bạn đang trống.</p><a href="/menu" class="btn btn-primary">Quay lại mua sắm</a></div>`;
                                document.querySelector('.col-lg-4 .cart-summary')?.remove();
                           }
                      } else { showToast(data.message || 'Lỗi khi xóa.', 'danger'); } })
                  .catch(e => { showToast(`Lỗi: ${e}.`, 'danger'); });
            }
        }
    });
}

function updateCartItemAJAX(productId, quantity) {
    const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfTokenMeta?.content;
    fetch('/order/update-cart', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', ...(csrfToken && { 'X-CSRFToken': csrfToken }) },
        body: JSON.stringify({ product_id: parseInt(productId), quantity: parseInt(quantity) })
    })
    .then(response => response.ok ? response.json() : response.json().then(e => Promise.reject(e.message || `Lỗi ${response.status}`)))
    .then(data => { if(data.success){ updateCartItemUI(productId, quantity, data.item_subtotal); updateCartSummaryUI(data.cart_subtotal, data.cart_tax, data.cart_total); updateCartBadge(); showToast(data.message || "Đã cập nhật.", 'success'); } else { showToast(data.message || 'Lỗi cập nhật.', 'danger'); /* Restore old value? */ } })
    .catch(error => { showToast(`Lỗi: ${error}.`, 'danger'); /* Restore old value? */ });
}
// --- End CART PAGE SPECIFIC ---


// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', function() {
    initializeBootstrapComponents();
    animateOnScroll();
    setupQuantityControls();
    setupContactForm();
    setupAddToCartButtons();
    setupReviewFormSubmit();
    setupQuickViewModal();
    setupAuthModals();
    setupChatbot(); 
    updateCartBadge(); 
    setupOrderHistoryOffcanvas(); 

    if (document.getElementById('product-grid-container')) { setupMenuFiltersAndSearch(); }
    const cartListPage = document.querySelector('.cart-list-page-identifier'); 
    if (cartListPage) {
       setupCartPageInteractions();
    }
    console.log("Dragon Coffee Main JS Fully Initialized.");
});


function showCustomNotification(message, iconClass = 'fa-info-circle', type = 'info', duration = 2000) {
    const overlay = document.getElementById('custom-notification-overlay');
    const box = document.getElementById('custom-notification-box');
    const iconEl = document.getElementById('custom-notification-icon');
    const messageEl = document.getElementById('custom-notification-message');

    if (!overlay || !box || !iconEl || !messageEl) {
        console.error("Custom notification elements not found in DOM!");
        showToast(message, type === 'danger' ? 'error' : type);
        return;
    }
    messageEl.textContent = message;
    iconEl.className = `fas ${iconClass}`; 
    box.classList.remove('success', 'warning', 'danger', 'info'); 
    if (type) {
        box.classList.add(type); 
        iconEl.classList.remove('text-primary','text-success', 'text-warning', 'text-danger');
        if (type === 'success') iconEl.classList.add('text-success');
        else if (type === 'warning') iconEl.classList.add('text-warning');
        else if (type === 'danger') iconEl.classList.add('text-danger');
        else iconEl.classList.add('text-primary');
    }
    overlay.style.display = 'flex'; 
    setTimeout(() => { 
        overlay.classList.add('show');
    }, 10);
    setTimeout(() => {
        overlay.classList.remove('show');
        setTimeout(() => {
            overlay.style.display = 'none';
        }, 300); 
    }, duration);
}


function setupOrderHistoryOffcanvas() {
    const historyIcon = document.querySelector('.order-history-icon');
    const offcanvasElement = document.getElementById('orderHistoryOffcanvas');
    const historyContentDiv = document.getElementById('orderHistoryContent');
    const historyLoadingDiv = document.getElementById('orderHistoryLoading');

    if (!historyIcon || !offcanvasElement || !historyContentDiv || !historyLoadingDiv) {
        return;
    }

    let offcanvasInstance = bootstrap.Offcanvas.getInstance(offcanvasElement);
    if (!offcanvasInstance) {
        offcanvasInstance = new bootstrap.Offcanvas(offcanvasElement);
    }

    historyIcon.addEventListener('click', function (event) {
        event.preventDefault();
        historyContentDiv.innerHTML = ''; 
        historyLoadingDiv.style.display = 'block'; 
        offcanvasInstance.show();

        fetch('/order/api/recent-orders') 
            .then(response => {
                if (!response.ok) {
                    // Đọc text lỗi để hiển thị chính xác hơn thay vì chỉ status code
                    return response.text().then(text => {
                        throw new Error(`Lỗi ${response.status}: ${text || 'Không tải được lịch sử.'}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                historyLoadingDiv.style.display = 'none';
                if (data.success && data.orders) {
                    renderOrderHistory(data.orders, historyContentDiv);
                } else {
                    historyContentDiv.innerHTML = `<p class="text-muted text-center p-3">${data.message || 'Không thể tải lịch sử.'}</p>`;
                }
            })
            .catch(error => {
                historyLoadingDiv.style.display = 'none';
                // Hiển thị lỗi rõ ràng hơn cho người dùng
                historyContentDiv.innerHTML = `<p class="text-danger text-center p-3">Lỗi khi tải lịch sử. <br><small>(${error.message})</small></p>`;
                console.error("Error fetching order history:", error);
            });
    });
}

function renderOrderHistory(orders, container) {
    if (!orders || orders.length === 0) {
        container.innerHTML = `<div class="no-history-message"><i class="fas fa-box-open fa-2x mb-2 text-muted"></i><p>Bạn chưa có món nào đã đặt gần đây.</p></div>`;
        return;
    }

    let html = '';
    orders.forEach(order => {
        // Chỉ hiển thị sản phẩm, không hiển thị thông tin chung của đơn hàng
        if (order.items && order.items.length > 0) {
             order.items.forEach(item => {
                html += `
                    <div class="history-order-item"> 
                        <div class="order-meta">
                            <span>Đặt lúc: <strong>${order.created_at}</strong></span>
                        </div>
                        <div class="history-product-item">
                            <img src="${item.image_url}" alt="${item.name}">
                            <div class="product-info">
                                <div class="product-name">${item.name}</div>
                                <div class="product-qty-price">
                                    Đã mua: ${item.quantity} x ${formatPriceJS(item.price_at_purchase)}
                                </div>
                            </div>
                            <button class="btn btn-sm btn-outline-primary btn-reorder add-to-cart-btn"
                                    data-product-id="${item.product_id}"
                                    data-quantity="1" {/* Mặc định đặt lại 1 cái */}
                                    title="Đặt lại ${item.name}">
                                <i class="fas fa-redo-alt"></i> Đặt lại
                            </button>
                        </div>
                    </div> 
                `;
            });
        }
    });
    if (html === '') { // Nếu không có sản phẩm nào trong các đơn hàng
        container.innerHTML = `<div class="no-history-message"><i class="fas fa-mug-hot fa-2x mb-2 text-muted"></i><p>Chưa có sản phẩm nào trong lịch sử đặt hàng.</p></div>`;
    } else {
        container.innerHTML = html;
    }
    initializeBootstrapComponents(container); 
}

function formatPriceJS(amount) {
    if (amount === null || typeof amount === 'undefined') return "0₫";
    try {
        return Math.round(Number(amount)).toLocaleString('vi-VN') + '₫';
    } catch (e) {
        return amount + '₫';
    }
}

