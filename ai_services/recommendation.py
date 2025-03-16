"""
Dragon Coffee Shop - Recommendation System
This module provides product recommendation functionality based on:
1. User purchase history
2. Product popularity
3. Item-based collaborative filtering
"""

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from collections import Counter

class RecommendationEngine:
    def __init__(self, db):
        """Initialize recommendation engine with database connection"""
        self.db = db
        self.product_vectors = {}
        self.product_features = {}
        self.similarity_matrix = None
        self.initialize_product_data()
    
    def initialize_product_data(self):
        """Load product data and build initial feature vectors"""
        # Get all products from database
        products = self.db.session.query(self.db.Product).all()
        
        # Extract features for content-based filtering
        for product in products:
            # Create feature vector from product attributes
            feature_vector = []
            
            # Category as one-hot encoded feature
            feature_vector.append(product.category_id)
            
            # Price-based feature (normalized)
            feature_vector.append(product.price / 100)  # Simple normalization
            
            # Popularity-based feature
            order_count = self.get_product_order_count(product.id)
            feature_vector.append(order_count / 10)  # Simple normalization
            
            # Store feature vectors
            self.product_features[product.id] = {
                'id': product.id,
                'name': product.name,
                'category_id': product.category_id,
                'price': product.price,
                'is_featured': product.is_featured,
                'image_url': product.image_url,
                'order_count': order_count
            }
            
            self.product_vectors[product.id] = np.array(feature_vector)
        
        # Calculate similarity matrix
        if len(self.product_vectors) > 1:
            self.calculate_similarity_matrix()
    
    def calculate_similarity_matrix(self):
        """Calculate cosine similarity between all products"""
        product_ids = list(self.product_vectors.keys())
        vectors = np.array([self.product_vectors[pid] for pid in product_ids])
        
        self.similarity_matrix = cosine_similarity(vectors)
        self.product_ids = product_ids
    
    def get_product_order_count(self, product_id):
        """Get number of times a product has been ordered"""
        from models import OrderDetail
        
        count = self.db.session.query(OrderDetail).filter(
            OrderDetail.product_id == product_id
        ).count()
        
        return count or 0
    
    def get_user_purchase_history(self, user_id):
        """Get products purchased by user"""
        from models import Order, OrderDetail
        
        # Get all orders by user
        orders = self.db.session.query(Order).filter(
            Order.user_id == user_id
        ).all()
        
        order_ids = [order.id for order in orders]
        
        if not order_ids:
            return []
        
        # Get all product IDs from those orders
        order_details = self.db.session.query(OrderDetail).filter(
            OrderDetail.order_id.in_(order_ids)
        ).all()
        
        product_ids = [od.product_id for od in order_details]
        return product_ids
    
    def recommend_for_user(self, user_id, limit=5):
        """Generate product recommendations for a user"""
        if not self.similarity_matrix:
            # Fall back to popularity-based recommendations
            return self.most_popular_products(limit)
        
        # Get user's purchase history
        purchased_products = self.get_user_purchase_history(user_id)
        
        if not purchased_products:
            # Fall back to popular and featured products
            return self.most_popular_products(limit)
        
        # Calculate recommendation scores for each product
        recommendation_scores = {}
        
        for product_id in self.product_vectors.keys():
            # Don't recommend products they've already purchased
            if product_id in purchased_products:
                continue
            
            score = 0
            
            for purchased_id in purchased_products:
                if purchased_id not in self.product_vectors:
                    continue
                
                # Find indices in similarity matrix
                idx1 = self.product_ids.index(product_id)
                idx2 = self.product_ids.index(purchased_id)
                
                # Add similarity score
                score += self.similarity_matrix[idx1, idx2]
            
            recommendation_scores[product_id] = score
        
        # Sort by score
        recommended_ids = sorted(recommendation_scores, 
                                 key=recommendation_scores.get, 
                                 reverse=True)[:limit]
        
        # Get product details
        from models import Product
        products = self.db.session.query(Product).filter(
            Product.id.in_(recommended_ids)
        ).all()
        
        return products
    
    def most_popular_products(self, limit=5):
        """Return most popular products based on order count"""
        sorted_products = sorted(
            self.product_features.values(), 
            key=lambda p: p['order_count'],
            reverse=True
        )
        
        product_ids = [p['id'] for p in sorted_products[:limit]]
        
        # Get product details
        from models import Product
        products = self.db.session.query(Product).filter(
            Product.id.in_(product_ids)
        ).all()
        
        return products
    
    def get_similar_products(self, product_id, limit=5):
        """Get products similar to given product_id"""
        if not self.similarity_matrix or product_id not in self.product_ids:
            return self.most_popular_products(limit)
        
        # Get index of product
        idx = self.product_ids.index(product_id)
        
        # Get similarity scores for all products
        similarity_scores = self.similarity_matrix[idx]
        
        # Sort by similarity and get top products (excluding itself)
        product_indices = np.argsort(similarity_scores)[::-1][1:limit+1]
        recommended_ids = [self.product_ids[i] for i in product_indices]
        
        # Get product details
        from models import Product
        products = self.db.session.query(Product).filter(
            Product.id.in_(recommended_ids)
        ).all()
        
        return products


# Initialize global recommendation engine
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
    
    if user_id:
        return recommendation_engine.recommend_for_user(user_id, limit)
    elif product_id:
        return recommendation_engine.get_similar_products(product_id, limit)
    else:
        return recommendation_engine.most_popular_products(limit)