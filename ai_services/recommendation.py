"""
Dragon Coffee Shop - Recommendation System
This module provides product recommendation functionality based on:
1. User purchase history
2. Product popularity
3. Item-based collaborative filtering
"""

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from collections import Counter, defaultdict
import pandas as pd
import os
import joblib
from datetime import datetime, timedelta

class RecommendationEngine:
    def __init__(self, db):
        """Initialize recommendation engine with database connection"""
        self.db = db
        self.similarity_matrix = None
        self.product_features = {}
        self.product_vectors = {}
        self.model_dir = 'ai_services/models'
        
        # Ensure model directory exists
        os.makedirs(self.model_dir, exist_ok=True)
        
        # Load or initialize data
        self.similarity_matrix_path = os.path.join(self.model_dir, 'product_similarity.joblib')
        self.product_vectors_path = os.path.join(self.model_dir, 'product_vectors.joblib')
        
        # Try to load existing data
        try:
            if os.path.exists(self.similarity_matrix_path):
                self.similarity_matrix = joblib.load(self.similarity_matrix_path)
            
            if os.path.exists(self.product_vectors_path):
                self.product_vectors = joblib.load(self.product_vectors_path)
        except Exception as e:
            print(f"Error loading recommendation data: {e}")
        
        # Initialize product data if not loaded
        if not self.similarity_matrix or not self.product_vectors:
            self.initialize_product_data()
            self.calculate_similarity_matrix()
    
    def initialize_product_data(self):
        """Load product data and build initial feature vectors"""
        from models import Product, Category, OrderDetail, Review
        from sqlalchemy import func
        
        print("Initializing product data for recommendations...")
        
        # Get all products
        products = self.db.session.query(Product).filter(Product.is_available == True).all()
        
        # Create feature vectors for each product
        for product in products:
            # Basic product features
            self.product_features[product.id] = {
                'name': product.name,
                'price': product.price,
                'category_id': product.category_id,
                'is_featured': product.is_featured,
                'avg_rating': 0,  # Default, will be updated if reviews exist
                'order_count': 0  # Default, will be updated later
            }
            
            # Get category name
            category = self.db.session.query(Category).get(product.category_id)
            if category:
                self.product_features[product.id]['category_name'] = category.name
            
            # Get average rating if reviews exist
            avg_rating = self.db.session.query(func.avg(Review.rating)).filter(
                Review.product_id == product.id
            ).scalar()
            
            if avg_rating:
                self.product_features[product.id]['avg_rating'] = float(avg_rating)
            
            # Get order count
            order_count = self.db.session.query(func.sum(OrderDetail.quantity)).filter(
                OrderDetail.product_id == product.id
            ).scalar()
            
            if order_count:
                self.product_features[product.id]['order_count'] = int(order_count)
        
        # Create numerical feature vectors for similarity computation
        for product_id, features in self.product_features.items():
            # Create vector with normalized numerical features
            # [price, is_featured, avg_rating, order_count, category_one_hot]
            
            # Get all categories for one-hot encoding
            categories = self.db.session.query(Category).all()
            category_ids = [cat.id for cat in categories]
            
            # One-hot encode category
            category_vector = [1 if features['category_id'] == cat_id else 0 
                              for cat_id in category_ids]
            
            # Create the full vector
            vector = [
                features['price'] / 100,  # Normalize price
                1 if features['is_featured'] else 0,
                features['avg_rating'] / 5.0,  # Normalize rating to 0-1
                min(1.0, features['order_count'] / 100)  # Cap at 1.0 for very popular items
            ]
            
            # Combine with category vector
            vector.extend(category_vector)
            
            # Store the vector
            self.product_vectors[product_id] = np.array(vector)
        
        # Save product vectors
        try:
            joblib.dump(self.product_vectors, self.product_vectors_path)
            print(f"Saved product vectors for {len(self.product_vectors)} products")
        except Exception as e:
            print(f"Error saving product vectors: {e}")
    
    def calculate_similarity_matrix(self):
        """Calculate cosine similarity between all products"""
        if not self.product_vectors:
            print("No product vectors available for similarity calculation")
            return
        
        # Get all product IDs
        product_ids = list(self.product_vectors.keys())
        
        # Create matrix from vectors
        vectors = np.array([self.product_vectors[pid] for pid in product_ids])
        
        # Calculate similarity
        try:
            similarity = cosine_similarity(vectors)
            
            # Create a dictionary mapping product IDs to similarities
            similarity_dict = {}
            for i, pid in enumerate(product_ids):
                similarity_dict[pid] = {
                    product_ids[j]: float(similarity[i, j]) 
                    for j in range(len(product_ids)) if i != j
                }
            
            self.similarity_matrix = similarity_dict
            
            # Save similarity matrix
            joblib.dump(self.similarity_matrix, self.similarity_matrix_path)
            print(f"Calculated and saved similarity matrix for {len(product_ids)} products")
        except Exception as e:
            print(f"Error calculating similarity matrix: {e}")
    
    def get_product_order_count(self, product_id):
        """Get number of times a product has been ordered"""
        if product_id in self.product_features:
            return self.product_features[product_id]['order_count']
        return 0
    
    def get_user_purchase_history(self, user_id):
        """Get products purchased by user"""
        from models import Order, OrderDetail
        
        # Query for user's order history
        orders = self.db.session.query(Order).filter(
            Order.user_id == user_id,
            Order.status == 'completed'  # Only consider completed orders
        ).all()
        
        # Collect product IDs and quantities from order details
        product_counts = Counter()
        
        for order in orders:
            order_details = self.db.session.query(OrderDetail).filter(
                OrderDetail.order_id == order.id
            ).all()
            
            for detail in order_details:
                product_counts[detail.product_id] += detail.quantity
        
        return product_counts
    
    def recommend_for_user(self, user_id, limit=5):
        """Generate product recommendations for a user"""
        # Get user's purchase history
        purchase_history = self.get_user_purchase_history(user_id)
        
        if not purchase_history:
            # No purchase history, return popular products
            return self.most_popular_products(limit)
        
        # Calculate recommendation scores
        # Start with some popular products as candidates
        candidates = set(product.id for product in self.most_popular_products(limit=20))
        
        # Add similar products to items in purchase history
        for product_id in purchase_history:
            if product_id in self.similarity_matrix:
                # Get top 5 similar products
                similar_products = sorted(
                    self.similarity_matrix[product_id].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:5]
                
                # Add to candidates
                candidates.update([p[0] for p in similar_products])
        
        # Remove products the user has already purchased
        candidates = candidates - set(purchase_history.keys())
        
        if not candidates:
            # If no candidates, return popular products
            return self.most_popular_products(limit)
        
        # Score candidates
        scores = {}
        for candidate in candidates:
            # Base score
            scores[candidate] = 0
            
            # Boost from similarity to purchased products
            for product_id, quantity in purchase_history.items():
                if product_id in self.similarity_matrix and candidate in self.similarity_matrix[product_id]:
                    similarity = self.similarity_matrix[product_id][candidate]
                    scores[candidate] += similarity * min(5, quantity)  # Cap the quantity factor
            
            # Boost for popular products (small factor to prioritize personal preference)
            if candidate in self.product_features:
                popularity = min(1.0, self.product_features[candidate]['order_count'] / 100)
                scores[candidate] += popularity * 0.2
        
        # Sort by score and return top recommendations
        recommendations = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        
        # Get product details
        from models import Product
        
        result = []
        for product_id, score in recommendations:
            product = self.db.session.query(Product).get(product_id)
            if product and product.is_available:
                result.append({
                    'id': product.id,
                    'name': product.name,
                    'price': product.price,
                    'image_url': product.image_url,
                    'recommendation_score': score,
                    'recommendation_type': 'personalized'
                })
        
        # If not enough recommendations, pad with popular products
        if len(result) < limit:
            popular = self.most_popular_products(limit - len(result))
            # Add only products not already in results
            existing_ids = set(item['id'] for item in result)
            for item in popular:
                if item['id'] not in existing_ids:
                    item['recommendation_type'] = 'popular'
                    result.append(item)
        
        return result
    
    def most_popular_products(self, limit=5):
        """Return most popular products based on order count"""
        from models import Product
        
        # Sort products by order count
        popular_product_ids = sorted(
            self.product_features.keys(),
            key=lambda pid: self.product_features[pid]['order_count'],
            reverse=True
        )[:limit*2]  # Get more than needed in case some are unavailable
        
        # Get product details
        result = []
        for product_id in popular_product_ids:
            if len(result) >= limit:
                break
                
            product = self.db.session.query(Product).get(product_id)
            if product and product.is_available:
                result.append({
                    'id': product.id,
                    'name': product.name,
                    'price': product.price,
                    'image_url': product.image_url,
                    'order_count': self.product_features[product_id]['order_count'],
                    'recommendation_type': 'popular'
                })
        
        return result
    
    def get_similar_products(self, product_id, limit=5):
        """Get products similar to given product_id"""
        if product_id not in self.similarity_matrix:
            # Product not found or no similarity data
            return self.most_popular_products(limit)
        
        # Get similar products sorted by similarity
        similar_products = sorted(
            self.similarity_matrix[product_id].items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit*2]  # Get more than needed in case some are unavailable
        
        # Get product details
        from models import Product
        
        result = []
        for similar_id, similarity in similar_products:
            if len(result) >= limit:
                break
                
            product = self.db.session.query(Product).get(similar_id)
            if product and product.is_available:
                result.append({
                    'id': product.id,
                    'name': product.name,
                    'price': product.price,
                    'image_url': product.image_url,
                    'similarity': similarity,
                    'recommendation_type': 'similar'
                })
        
        # If not enough recommendations, pad with popular products
        if len(result) < limit:
            popular = self.most_popular_products(limit - len(result))
            # Add only products not already in results
            existing_ids = set(item['id'] for item in result)
            for item in popular:
                if item['id'] not in existing_ids:
                    item['recommendation_type'] = 'popular'
                    result.append(item)
        
        return result


# Singleton instance
recommendation_engine = None

def init_recommendation_engine(db):
    """Initialize the recommendation engine"""
    global recommendation_engine
    recommendation_engine = RecommendationEngine(db)
    return recommendation_engine

def get_recommendations(user_id=None, product_id=None, limit=5):
    """Get recommendations based on user_id or product_id"""
    if recommendation_engine is None:
        from app import db
        init_recommendation_engine(db)
    
    # If product_id is provided, return similar products
    if product_id:
        return recommendation_engine.get_similar_products(product_id, limit)
    
    # If user_id is provided, return personalized recommendations
    if user_id:
        return recommendation_engine.recommend_for_user(user_id, limit)
    
    # Otherwise, return popular products
    return recommendation_engine.most_popular_products(limit)