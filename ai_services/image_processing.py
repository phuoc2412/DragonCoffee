"""
Dragon Coffee Shop - Image Processing Module
This module provides image recognition and processing capabilities.
"""

import os
import base64
import numpy as np
from PIL import Image, ImageOps, ImageFilter, ImageEnhance
import io
from sklearn.cluster import KMeans
from collections import Counter
import re
import joblib
from datetime import datetime
import base64
from werkzeug.utils import secure_filename
import logging
from flask import current_app, url_for
import uuid
import requests

HF_API_TOKEN = os.environ.get("HUGGINGFACE_API_TOKEN")
# Lấy model ID từ env hoặc dùng default (chọn model phù hợp, kiểm tra trên Hugging Face)
DEFAULT_MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0" # Ví dụ, cần test
# Hoặc model khác nhẹ hơn nếu có "runwayml/stable-diffusion-v1-5"
IMAGE_MODEL_ID = os.environ.get("HUGGINGFACE_IMAGE_MODEL", DEFAULT_MODEL_ID)
API_URL = f"https://api-inference.huggingface.co/models/{IMAGE_MODEL_ID}"

def get_logger_img_gen():
    # Ưu tiên logger của Flask app nếu có context
    if current_app:
        return current_app.logger
    else:
        # Fallback logging cơ bản nếu không có app context
        logger = logging.getLogger("ai_image_processing")
        if not logger.hasHandlers(): # Chỉ cấu hình nếu chưa có handler
            log_format = '%(asctime)s - %(levelname)s - IMG_PROC - %(message)s'
            logging.basicConfig(level=logging.INFO, format=log_format)
            logger.info("Logger for Image Processing initialized outside Flask context.")
        return logger

def generate_image_from_text_hf(prompt: str):
    """
    Generates an image using Hugging Face Inference API.
    Returns image bytes if successful, None otherwise.
    """
    logger = get_logger_img_gen()
    if not HF_API_TOKEN:
        logger.error("Hugging Face API Token (HUGGINGFACE_API_TOKEN) not set.")
        return None

    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    payload = {"inputs": prompt}
    logger.info(f"Sending image generation request to HF API ({IMAGE_MODEL_ID}) with prompt: '{prompt[:100]}...'")

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=90) # Tăng timeout
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        # HF API trả về image bytes trực tiếp hoặc lỗi JSON
        content_type = response.headers.get('content-type')
        if 'image' in content_type.lower():
             logger.info("Image generation successful, received image bytes.")
             return response.content # Trả về dạng bytes
        elif 'json' in content_type.lower():
            error_data = response.json()
            error_msg = error_data.get("error", "Unknown JSON error from HF")
            estimated_time = error_data.get("estimated_time")
            if estimated_time:
                 logger.warning(f"HF Model is loading (estimated time: {estimated_time}s). Prompt: '{prompt}'. Try again later.")
                 # Trả về lỗi đặc biệt để frontend biết model đang load
                 raise TimeoutError(f"Model đang tải, vui lòng thử lại sau khoảng {int(estimated_time)+5} giây.")
            else:
                 logger.error(f"Hugging Face API JSON error: {error_msg}. Prompt: '{prompt}'")
                 raise ValueError(f"Lỗi từ API tạo ảnh: {error_msg}")
        else:
             logger.error(f"Unexpected content type from HF API: {content_type}")
             raise ValueError("API tạo ảnh trả về định dạng không mong đợi.")

    except requests.exceptions.Timeout:
         logger.error(f"Timeout error during Hugging Face image generation request for prompt: '{prompt}'")
         raise TimeoutError("Yêu cầu tạo ảnh quá hạn. Vui lòng thử lại.") # Ném lỗi rõ ràng
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during Hugging Face image generation request: {e}", exc_info=True)
        raise ConnectionError(f"Lỗi kết nối đến API tạo ảnh: {e}")
    except Exception as e:
        # Bắt các lỗi khác (ValueError, TimeoutError từ trên)
        logger.error(f"General error in generate_image_from_text_hf: {e}", exc_info=True)
        raise e # Ném lại lỗi để route xử lý


def save_generated_image(image_bytes, subfolder='stories'):
    """Lưu ảnh vào thư mục uploads và trả về URL web có thể truy cập."""
    logger = get_logger_img_gen()
    if not current_app:
        logger.error("Critical: Cannot save image or generate URL without Flask app context.")
        return None

    try:
        upload_folder_config_key = 'UPLOAD_FOLDER'
        configured_path = current_app.config.get(upload_folder_config_key, 'static/uploads')
        base_upload_dir_abs = os.path.abspath(os.path.join(current_app.root_path, configured_path))
        target_folder_abs = os.path.join(base_upload_dir_abs, subfolder)
        os.makedirs(target_folder_abs, exist_ok=True)
        logger.debug(f"Absolute save directory: {target_folder_abs}")

        img = Image.open(io.BytesIO(image_bytes))
        img_format = img.format if img.format else 'JPEG'
        img_extension = img_format.lower()
        if img_extension == 'jpeg': img_extension = 'jpg'
        filename = f"ai_story_{uuid.uuid4().hex[:12]}.{img_extension}" # Thêm tiền tố story
        save_path_abs = os.path.join(target_folder_abs, filename)

        # === SỬA LẠI: Ghi trực tiếp bytes ===
        # img.save(save_path_abs, format=img_format.upper(), quality=90) # Không cần thiết nếu đã có bytes
        with open(save_path_abs, 'wb') as f:
            f.write(image_bytes)
        # ====================================

        logger.info(f"Generated image successfully saved to: {save_path_abs}")

        # --- Tạo URL ---
        static_folder_name = os.path.basename(current_app.static_folder)
        if configured_path.strip(os.path.sep).startswith(static_folder_name):
             # Đường dẫn tương đối trong thư mục static
            path_parts = configured_path.strip(os.path.sep).split(os.path.sep, 1)
            base_static_path = path_parts[1] if len(path_parts) > 1 else ''
            static_relative_path = os.path.join(base_static_path, subfolder, filename).replace(os.path.sep, '/')
            try:
                # Dùng url_for để tạo URL đúng
                web_url = url_for('static', filename=static_relative_path, _external=False)
                logger.info(f"Generated static web URL: {web_url}")
                return web_url # <-- Phải trả về URL này
            except Exception as url_error:
                 logger.error(f"Could not generate static URL using url_for for '{static_relative_path}': {url_error}", exc_info=True)
                 web_url_fallback = f"/{static_folder_name}/{static_relative_path}"
                 logger.warning(f"Falling back to manually constructed URL: {web_url_fallback}")
                 return web_url_fallback
        else:
            logger.error(f"UPLOAD_FOLDER ('{configured_path}') not inside static folder ('{static_folder_name}'). Cannot generate static URL.")
            return None

    except Exception as e:
        logger.error(f"Error saving generated image or creating URL: {e}", exc_info=True)
        return None

class ImageProcessor:
    def __init__(self):
        """Initialize image processor"""
        self.model_dir = 'ai_services/models'
        self.image_classifier = None
        self.load_image_classifier()
        
        # Coffee-related image categories
        self.coffee_categories = [
            'coffee cup', 'coffee mug', 'espresso', 'cappuccino', 'latte',
            'coffee beans', 'coffee maker', 'coffee shop', 'cafe', 'tea',
            'drinking glass', 'bakery', 'pastry', 'croissant', 'cake'
        ]
        
        # Color names mapping
        self.color_names = {
            (0, 0, 0): 'black',
            (255, 255, 255): 'white',
            (255, 0, 0): 'red',
            (0, 255, 0): 'green',
            (0, 0, 255): 'blue',
            (255, 255, 0): 'yellow',
            (255, 0, 255): 'magenta',
            (0, 255, 255): 'cyan',
            (128, 0, 0): 'maroon',
            (128, 128, 0): 'olive',
            (0, 128, 0): 'dark green',
            (128, 0, 128): 'purple',
            (0, 128, 128): 'teal',
            (0, 0, 128): 'navy',
            (165, 42, 42): 'brown',
            (210, 180, 140): 'tan',
            (250, 128, 114): 'salmon',
            (255, 215, 0): 'gold',
            (192, 192, 192): 'silver'
        }
    
    def load_image_classifier(self):
        """Load the image classifier model (fallback to simple rules if not available)"""
        # In a real implementation, this would load a proper image classifier
        model_path = os.path.join(self.model_dir, 'image_classifier.joblib')
        
        if os.path.exists(model_path):
            try:
                self.image_classifier = joblib.load(model_path)
                return True
            except Exception as e:
                print(f"Error loading image classifier: {e}")
        
        return False
    
    def preprocess_image(self, image):
        """Preprocess an image for analysis"""
        # Resize for consistency
        image = ImageOps.contain(image, (299, 299))
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        return image
    
    def extract_image_features(self, image):
        """Extract basic image features for analysis"""
        # Get image dimensions
        width, height = image.size
        
        # Convert to numpy array
        img_array = np.array(image)
        
        # Extract dominant colors
        dominant_colors = self.extract_dominant_colors(img_array)
        
        # Calculate brightness
        brightness = self.calculate_brightness(img_array)
        
        # Calculate sharpness
        sharpness = self.calculate_sharpness(image)
        
        # Build feature dictionary
        features = {
            'width': width,
            'height': height,
            'aspect_ratio': width / height,
            'dominant_colors': dominant_colors,
            'brightness': brightness,
            'sharpness': sharpness
        }
        
        return features
    
    def extract_dominant_colors(self, img_array, n_colors=3):
        """Extract dominant colors from an image"""
        # Reshape the image data for KMeans
        pixels = img_array.reshape(-1, 3)
        
        # Sample pixels for efficiency
        sample_size = min(10000, pixels.shape[0])
        sampled_pixels = pixels[np.random.choice(pixels.shape[0], sample_size, replace=False)]
        
        # Perform KMeans clustering
        kmeans = KMeans(n_clusters=n_colors, n_init=10, random_state=0)
        kmeans.fit(sampled_pixels)
        
        # Get dominant colors
        colors = kmeans.cluster_centers_.astype(int)
        
        # Calculate color proportions
        labels = kmeans.predict(sampled_pixels)
        counts = Counter(labels)
        
        # Sort colors by frequency
        sorted_colors = []
        for i in range(n_colors):
            color = tuple(colors[i])
            proportion = counts[i] / sample_size
            sorted_colors.append((color, proportion))
        
        sorted_colors.sort(key=lambda x: x[1], reverse=True)
        
        # Map to named colors
        named_colors = []
        for color, proportion in sorted_colors:
            closest_color = self.find_closest_color(color)
            named_colors.append({
                'color': [int(c) for c in color],
                'name': closest_color,
                'proportion': float(proportion)
            })
        
        return named_colors
    
    def find_closest_color(self, color):
        """Find the closest named color"""
        min_distance = float('inf')
        closest_name = 'unknown'
        
        for ref_color, name in self.color_names.items():
            distance = sum((c1 - c2) ** 2 for c1, c2 in zip(color, ref_color))
            if distance < min_distance:
                min_distance = distance
                closest_name = name
        
        return closest_name
    
    def calculate_brightness(self, img_array):
        """Calculate the brightness of an image"""
        # Convert to grayscale weights and normalize
        return float(np.mean(img_array) / 255)
    
    def calculate_sharpness(self, image):
        """Calculate the sharpness of an image"""
        # Convert to grayscale
        gray_img = image.convert('L')
        
        # Apply Laplacian filter to detect edges
        laplacian_img = gray_img.filter(ImageFilter.FIND_EDGES)
        
        # Calculate variance (higher variance means sharper image)
        return float(np.var(np.array(laplacian_img)) / 255)
    
    def identify_image_content(self, image):
        """Identify the content of an image"""
        # Preprocess image
        processed_img = self.preprocess_image(image)
        
        # Extract features
        features = self.extract_image_features(processed_img)
        
        # If we have a trained classifier, use it
        if self.image_classifier:
            # Prepare feature vector for the model
            # This is a simplified placeholder - actual implementation would depend on the model
            # feature_vector = self.prepare_feature_vector(features)
            # prediction = self.image_classifier.predict([feature_vector])[0]
            # confidence = max(self.image_classifier.predict_proba([feature_vector])[0])
            pass
        else:
            # Fallback: Simple rule-based classification
            # This is just a simplified example - real implementation would be more sophisticated
            brightness = features['brightness']
            dominant_color = features['dominant_colors'][0]['name']
            
            # Simple rules for coffee-related items
            if dominant_color in ['brown', 'black', 'maroon']:
                if brightness < 0.4:
                    prediction = 'coffee cup'
                    confidence = 0.7
                else:
                    prediction = 'latte'
                    confidence = 0.6
            elif dominant_color in ['white', 'cream', 'tan']:
                prediction = 'cappuccino'
                confidence = 0.65
            else:
                prediction = 'cafe scene'
                confidence = 0.5
        
        # Create result
        result = {
            'prediction': prediction if 'prediction' in locals() else 'cafe scene',
            'confidence': confidence if 'confidence' in locals() else 0.5,
            'features': features,
            'analysis_type': 'rule-based' if not self.image_classifier else 'model-based'
        }
        
        return result
    
    def generate_image_description(self, image_content):
        """Generate a human-readable description of an image"""
        # Start with basic description
        prediction = image_content['prediction']
        features = image_content['features']
        
        # Describe dominant colors
        color_desc = []
        for color in features['dominant_colors']:
            if color['proportion'] > 0.2:  # Only mention significant colors
                color_desc.append(f"{color['name']} ({int(color['proportion']*100)}%)")
        
        color_text = ", ".join(color_desc)
        
        # Describe brightness
        if features['brightness'] < 0.3:
            brightness_desc = "dark"
        elif features['brightness'] < 0.6:
            brightness_desc = "moderately bright"
        else:
            brightness_desc = "bright"
        
        # Describe sharpness
        if features['sharpness'] < 0.05:
            sharpness_desc = "soft-focus"
        elif features['sharpness'] < 0.2:
            sharpness_desc = "clear"
        else:
            sharpness_desc = "very sharp"
        
        # Build the description
        description = f"A {brightness_desc}, {sharpness_desc} image of a {prediction} "
        if color_text:
            description += f"with {color_text} tones"
        
        # Add extra details for coffee products
        if prediction in ['coffee cup', 'latte', 'cappuccino', 'espresso']:
            if features['brightness'] > 0.6:
                description += ". The coffee appears to have creamy foam or milk."
            else:
                description += ". The coffee appears to be dark and rich."
        
        return description
    
    def suggest_product_tags(self, image_content):
        """Suggest tags for a product based on image analysis"""
        prediction = image_content['prediction']
        features = image_content['features']
        
        # Initial tags based on prediction
        tags = [prediction]
        
        # Add coffee category
        if prediction in ['coffee cup', 'espresso', 'latte', 'cappuccino']:
            tags.append('coffee')
            
            # Add specifics
            if prediction == 'latte':
                tags.extend(['milk', 'creamy'])
            elif prediction == 'cappuccino':
                tags.extend(['foam', 'creamy'])
            elif prediction == 'espresso':
                tags.extend(['strong', 'concentrated'])
        
        # Add tags based on colors
        for color in image_content['features']['dominant_colors']:
            if color['name'] in ['black', 'brown', 'maroon'] and color['proportion'] > 0.3:
                tags.append('dark roast')
            elif color['name'] in ['tan', 'gold'] and color['proportion'] > 0.3:
                tags.append('medium roast')
        
        # Add atmospheric tags
        if features['brightness'] < 0.4:
            tags.append('rich')
        else:
            tags.append('light')
        
        # Remove duplicates and return
        return list(set(tags))
    
    def enhance_product_image(self, image, enhancement_type='auto'):
        """Enhance a product image for better presentation"""
        # Preprocess image
        processed_img = self.preprocess_image(image)
        
        if enhancement_type == 'auto':
            # Determine best enhancement based on image analysis
            features = self.extract_image_features(processed_img)
            
            if features['brightness'] < 0.4:
                enhancement_type = 'brighten'
            elif features['sharpness'] < 0.1:
                enhancement_type = 'sharpen'
            else:
                enhancement_type = 'vibrance'
        
        # Apply selected enhancement
        if enhancement_type == 'brighten':
            # Increase brightness
            enhancer = ImageEnhance.Brightness(processed_img)
            enhanced_img = enhancer.enhance(1.3)
            
            # Also increase contrast slightly
            enhancer = ImageEnhance.Contrast(enhanced_img)
            enhanced_img = enhancer.enhance(1.2)
            
        elif enhancement_type == 'sharpen':
            # Apply sharpening filter
            enhanced_img = processed_img.filter(ImageFilter.SHARPEN)
            
        elif enhancement_type == 'vibrance':
            # Increase color saturation
            enhancer = ImageEnhance.Color(processed_img)
            enhanced_img = enhancer.enhance(1.4)
            
        elif enhancement_type == 'product_focus':
            # Apply a subtle vignette and sharpen
            # First, sharpen the image
            enhanced_img = processed_img.filter(ImageFilter.SHARPEN)
            
            # Then, apply a vignette effect
            # Convert to numpy array
            img_array = np.array(enhanced_img)
            
            # Create a vignette mask
            h, w = img_array.shape[:2]
            y, x = np.ogrid[0:h, 0:w]
            center_y, center_x = h/2, w/2
            mask = ((x - center_x)**2 + (y - center_y)**2) / (max(center_x, center_y)**2)
            mask = np.clip(mask, 0, 1)
            mask = 1 - mask * 0.5  # Adjust vignette strength
            
            # Apply vignette
            for i in range(3):  # Apply to each color channel
                img_array[:,:,i] = img_array[:,:,i] * mask
            
            # Convert back to PIL Image
            enhanced_img = Image.fromarray(img_array.astype('uint8'))
        
        else:
            # Default: no enhancement
            enhanced_img = processed_img
        
        # Save the enhanced image to a buffer
        buffer = io.BytesIO()
        enhanced_img.save(buffer, format="JPEG", quality=90)
        buffer.seek(0)
        
        # Return the enhanced image data
        return {
            'image_data': buffer.getvalue(),
            'enhancement_type': enhancement_type,
            'format': 'JPEG'
        }
    
    def image_to_base64(self, image_data):
        """Convert image data to base64 string"""
        return base64.b64encode(image_data).decode('utf-8')
    
    def process_uploaded_image(self, file_path):
        """Process an uploaded image file"""
        try:
            # Load image
            with Image.open(file_path) as img:
                # Identify content
                content = self.identify_image_content(img)
                
                # Generate description
                description = self.generate_image_description(content)
                
                # Suggest tags
                tags = self.suggest_product_tags(content)
                
                # Enhance image
                enhanced = self.enhance_product_image(img)
                
                # Convert to base64 for convenience
                base64_img = self.image_to_base64(enhanced['image_data'])
                
                # Create result
                result = {
                    'original_filename': os.path.basename(file_path),
                    'content_prediction': content['prediction'],
                    'confidence': content['confidence'],
                    'description': description,
                    'suggested_tags': tags,
                    'enhanced_image_base64': base64_img,
                    'enhancement_type': enhanced['enhancement_type']
                }
                
                return result
        except Exception as e:
            print(f"Error processing image: {e}")
            return {
                'error': str(e),
                'original_filename': os.path.basename(file_path)
            }


# Singleton instance
image_processor = None

def init_image_processor():
    """Initialize the image processor"""
    global image_processor
    image_processor = ImageProcessor()
    return image_processor

def process_product_image(file_path):
    """Process a product image and return analysis"""
    if image_processor is None:
        init_image_processor()
    
    return image_processor.process_uploaded_image(file_path)

def enhance_image(file_path, enhancement_type='auto'):
    """Enhance an image for better presentation"""
    if image_processor is None:
        init_image_processor()
    
    try:
        with Image.open(file_path) as img:
            enhanced = image_processor.enhance_product_image(img, enhancement_type)
            return enhanced['image_data']
    except Exception as e:
        print(f"Error enhancing image: {e}")
        return None