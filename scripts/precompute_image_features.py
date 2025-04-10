# /scripts/precompute_image_features.py
import sys
import os
import pickle
import requests
from io import BytesIO
import logging # Import logging cơ bản

# Thêm đường dẫn gốc của dự án vào sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- SỬA PHẦN IMPORT APP VÀ DB ---
# Thay vì import create_app, import trực tiếp instance app và db đã tạo
from app import app, db
# ----------------------------------
from models import Product
from ai_services.image_similarity import extract_features, FEATURE_FILE_PATH, _get_logger # Giữ nguyên import này

def precompute_features():
    """Tính toán và lưu feature vectors cho tất cả ảnh sản phẩm."""
    # Không cần gọi create_app() nữa
    logger = _get_logger() # Lấy logger (có thể hoạt động nhờ app context bên dưới)

    # --- QUAN TRỌNG: Sử dụng app.app_context() ---
    # Cần tạo app context để có thể query DB và sử dụng logger của Flask
    with app.app_context():
        logger.info("Starting image feature precomputation within app context...")
        try:
            # Query sản phẩm trong context
            products = Product.query.filter(Product.image_url != None, Product.image_url != '').all()
            logger.info(f"Found {len(products)} products with image URLs.")
        except Exception as db_err:
             logger.error(f"Error querying products from database: {db_err}", exc_info=True)
             return # Dừng lại nếu không query được DB

        product_features = {}
        processed_count = 0
        error_count = 0

        for product in products:
            logger.info(f"Processing product ID: {product.id}, Name: {product.name}")
            if not product.image_url: # Kiểm tra lại lần nữa
                 logger.warning(f"-> Skipping product {product.id} due to missing image_url.")
                 continue

            try:
                # Tải ảnh từ URL
                response = requests.get(product.image_url, timeout=15, stream=True) # Tăng timeout
                response.raise_for_status()
                content_type = response.headers.get('content-type')
                if content_type and not content_type.lower().startswith('image'):
                     logger.warning(f"-> Skipping non-image content type '{content_type}' for product {product.id}")
                     error_count += 1
                     continue

                image_bytes = response.content
                if not image_bytes:
                     logger.warning(f"-> Empty image content for product {product.id}")
                     error_count += 1
                     continue

                # Trích xuất đặc trưng
                features = extract_features(image_bytes) # Hàm này có logger riêng

                if features is not None and len(features) > 0: # Kiểm tra feature có rỗng không
                    product_features[product.id] = features
                    processed_count += 1
                    # logger.info(f"-> Features extracted successfully (vector shape: {features.shape}).") # Ghi log shape nếu muốn
                else:
                    logger.warning(f"-> Failed to extract features for product {product.id}. Skipping.")
                    error_count += 1

            except requests.exceptions.Timeout:
                 logger.error(f"-> Timeout fetching image for product {product.id} from {product.image_url}")
                 error_count += 1
            except requests.exceptions.RequestException as req_err:
                 logger.error(f"-> Network error fetching image for product {product.id}: {req_err}")
                 error_count += 1
            except IOError as io_err: # Bắt lỗi PIL/IO
                 logger.error(f"-> IO/Image format error processing image for product {product.id}: {io_err}")
                 error_count += 1
            except Exception as e: # Bắt lỗi chung
                logger.error(f"-> Unexpected error processing product {product.id}: {e}", exc_info=True)
                error_count += 1

        # Lưu kết quả vào file (vẫn trong app_context)
        if product_features:
            try:
                os.makedirs(os.path.dirname(FEATURE_FILE_PATH), exist_ok=True)
                with open(FEATURE_FILE_PATH, 'wb') as f:
                    pickle.dump(product_features, f)
                logger.info(f"Successfully saved {len(product_features)} feature vectors to {FEATURE_FILE_PATH}")
            except Exception as e:
                logger.error(f"Error saving feature file: {e}", exc_info=True)
        else:
             logger.warning("No features were extracted or all encountered errors. Feature file not saved/updated.")

        logger.info(f"Precomputation finished. Successfully processed: {processed_count}, Errors/Skipped: {error_count}")
    # --- KẾT THÚC APP CONTEXT ---

if __name__ == "__main__":
    print("Starting image feature precomputation script...")
    # --- Cấu hình logging cơ bản cho script nếu chạy độc lập ---
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    # ---------------------------------------------------------
    precompute_features()
    print("Script finished.")