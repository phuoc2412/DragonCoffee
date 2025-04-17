# /ai_services/image_similarity.py
import os
import numpy as np
from tensorflow.keras.applications import ResNet50
# from tensorflow.keras.applications.resnet50 import preprocess_input
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input # MobileNetV2 nhẹ hơn ResNet50
from tensorflow.keras.preprocessing import image as keras_image
from tensorflow.keras.models import Model
from sklearn.metrics.pairwise import cosine_similarity
import pickle # Để lưu/đọc file đặc trưng
from flask import current_app
import requests # Để tải ảnh từ URL
from io import BytesIO # Để xử lý ảnh từ URL
from PIL import Image # Để xử lý ảnh

# --- Chọn Model (ví dụ: ResNet50 hoặc MobileNetV2) ---
# BASE_MODEL = ResNet50
# TARGET_SIZE = (224, 224)
# FEATURE_LAYER_NAME = 'avg_pool' # Lớp để lấy đặc trưng của ResNet50

# Hoặc dùng MobileNetV2 nhẹ hơn
from tensorflow.keras.applications import MobileNetV2
BASE_MODEL = MobileNetV2
TARGET_SIZE = (224, 224)
FEATURE_LAYER_NAME = 'out_relu' # Lớp của MobileNetV2

# --- Đường dẫn lưu file đặc trưng ---
FEATURE_FILE_DIR = os.path.join(os.path.dirname(__file__), 'data', 'image_features')
FEATURE_FILE_PATH = os.path.join(FEATURE_FILE_DIR, 'product_features.pkl')
os.makedirs(FEATURE_FILE_DIR, exist_ok=True)

# --- Biến toàn cục cho model và features (tránh load lại nhiều lần) ---
feature_extractor_model = None
product_features = {} # Dict: {product_id: feature_vector (numpy array)}

def _get_logger():
    """Lấy logger an toàn."""
    return current_app.logger if current_app else logging.getLogger(__name__)

def _load_feature_extractor():
    """Khởi tạo hoặc lấy model trích xuất đặc trưng."""
    global feature_extractor_model
    if feature_extractor_model is None:
        try:
            logger = _get_logger()
            logger.info(f"Loading pre-trained model: {BASE_MODEL.__name__}")
            base_model = BASE_MODEL(weights='imagenet', include_top=False, input_shape=TARGET_SIZE + (3,))

            # --- Sử dụng FEATURE_LAYER_NAME đã sửa ---
            feature_layer = base_model.get_layer(FEATURE_LAYER_NAME)
            if feature_layer is None:
                 # Fallback nếu tên layer vẫn sai (nên kiểm tra lại log lỗi)
                 # Có thể lấy layer cuối cùng theo index âm: base_model.layers[-1]
                 feature_layer = base_model.layers[-1] # Thử lấy lớp cuối cùng
                 logger.warning(f"Layer '{FEATURE_LAYER_NAME}' not found, falling back to last layer: '{feature_layer.name}'")

            feature_extractor_model = Model(inputs=base_model.input, outputs=feature_layer.output)
            # ----------------------------------------

            feature_extractor_model.trainable = False
            logger.info("Feature extractor model loaded.")
        except ValueError as ve: # Bắt lỗi ValueError cụ thể nếu get_layer sai
             logger.error(f"Error getting layer '{FEATURE_LAYER_NAME}' from {BASE_MODEL.__name__}: {ve}. Please check layer names.", exc_info=True)
             feature_extractor_model = None
        except Exception as e:
            logger.error(f"Error loading pre-trained model: {e}", exc_info=True)
            feature_extractor_model = None
    return feature_extractor_model

def load_precomputed_features():
    """Load các vector đặc trưng đã được tính toán trước."""
    global product_features
    logger = _get_logger()
    if not product_features: # Chỉ load nếu chưa có trong memory
        if os.path.exists(FEATURE_FILE_PATH):
            try:
                with open(FEATURE_FILE_PATH, 'rb') as f:
                    product_features = pickle.load(f)
                logger.info(f"Loaded {len(product_features)} precomputed image features from {FEATURE_FILE_PATH}")
            except Exception as e:
                logger.error(f"Error loading precomputed features: {e}", exc_info=True)
                product_features = {}
        else:
            logger.warning(f"Precomputed feature file not found: {FEATURE_FILE_PATH}. Please run the precomputation script.")
            product_features = {}
    return product_features

def preprocess_image(img_input):
    """Tiền xử lý ảnh cho phù hợp với model CNN."""
    try:
        if isinstance(img_input, str): # Nếu là đường dẫn file
            img = keras_image.load_img(img_input, target_size=TARGET_SIZE)
        elif isinstance(img_input, bytes): # Nếu là dữ liệu bytes (từ upload/url)
            img = Image.open(BytesIO(img_input))
            # Resize nếu cần
            if img.size != TARGET_SIZE:
                 # Dùng thumbnail để giữ aspect ratio, sau đó pad nếu cần, hoặc resize trực tiếp
                 # img.thumbnail(TARGET_SIZE, Image.Resampling.LANCZOS)
                 img = img.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
            if img.mode != 'RGB': # Đảm bảo là ảnh màu RGB
                 img = img.convert('RGB')
        elif isinstance(img_input, Image.Image): # Nếu đã là đối tượng PIL Image
            img = img_input
            if img.size != TARGET_SIZE: img = img.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
            if img.mode != 'RGB': img = img.convert('RGB')
        else:
            raise ValueError("Invalid image input type")

        img_array = keras_image.img_to_array(img)
        img_array_expanded = np.expand_dims(img_array, axis=0)
        return preprocess_input(img_array_expanded) # Sử dụng hàm tiền xử lý của model đã chọn
    except Exception as e:
         _get_logger().error(f"Error preprocessing image: {e}", exc_info=True)
         return None


def extract_features(img_input):
    """Trích xuất vector đặc trưng từ ảnh."""
    logger = _get_logger()
    model = _load_feature_extractor()
    if model is None:
        logger.error("Feature extractor model is not available.")
        return None

    preprocessed_img = preprocess_image(img_input)
    if preprocessed_img is None:
        logger.error("Image preprocessing failed.")
        return None

    try:
        features = model.predict(preprocessed_img, verbose=0) # verbose=0 để tắt log của predict
        return features.flatten() # Trả về vector 1D
    except Exception as e:
        logger.error(f"Error extracting features: {e}", exc_info=True)
        return None

def find_similar_images(input_features, top_n=5):
    """Tìm các ảnh sản phẩm tương đồng nhất."""
    logger = _get_logger()
    # Load các features đã tính toán trước của sản phẩm
    product_features_dict = load_precomputed_features()

    if not product_features_dict:
        logger.warning("No precomputed product features found.")
        return []
    if input_features is None:
        logger.warning("Input features are None, cannot find similar images.")
        return []

    product_ids = list(product_features_dict.keys())
    # Đảm bảo feature vectors là numpy array 2D
    all_features = np.array(list(product_features_dict.values()))
    input_features_reshaped = input_features.reshape(1, -1) # Reshape input thành 2D array

    if all_features.shape[1] != input_features_reshaped.shape[1]:
         logger.error(f"Feature dimension mismatch: Input {input_features_reshaped.shape}, Stored {all_features.shape}")
         return []


    try:
        # Tính cosine similarity
        similarities = cosine_similarity(input_features_reshaped, all_features)[0]

        # Lấy index của top_n sản phẩm tương đồng nhất (bỏ qua chính nó nếu có)
        # Sử dụng argsort để lấy index, sau đó đảo ngược và lấy top N
        # Bỏ qua score = 1.0 (ảnh giống hệt) nếu cần
        sorted_indices = np.argsort(similarities)[::-1]

        results = []
        for i in sorted_indices:
            product_id = product_ids[i]
            similarity_score = similarities[i]

            # Có thể bỏ qua nếu score quá thấp hoặc là chính ảnh đó (nếu input là ảnh sp)
            if similarity_score < 0.5: # Ngưỡng tương đồng tối thiểu
                continue

            results.append({'product_id': product_id, 'similarity': float(similarity_score)})
            if len(results) >= top_n:
                break

        logger.info(f"Found {len(results)} similar images.")
        return results

    except Exception as e:
        logger.error(f"Error finding similar images: {e}", exc_info=True)
        return []

# --- Hàm tiện ích để sử dụng từ bên ngoài ---
def get_similar_products_by_feature_vector(feature_vector, top_n=3):
     if feature_vector is None:
         return []
     return find_similar_images(feature_vector, top_n)

# Đảm bảo logger hoạt động cả khi không có current_app (ví dụ khi chạy script)
import logging
if not current_app:
    logging.basicConfig(level=logging.INFO)