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