"""
Dragon Coffee Shop - Inventory Demand Prediction
This module provides AI-powered inventory demand forecasting to optimize stock levels
and reduce wastage.
"""

import numpy as np
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
import joblib
import os
import pandas as pd
from collections import defaultdict

class InventoryPredictor:
    def __init__(self, db):
        """Initialize inventory predictor with database connection"""
        self.db = db
        self.models = {}  # Product ID -> trained model
        self.features = {}  # Product ID -> feature engineering function
        self.model_dir = 'ai_services/models'
        
        # Ensure model directory exists
        os.makedirs(self.model_dir, exist_ok=True)
        
        # Load or train models
        self.initialize_models()
    
    def initialize_models(self):
        """Load existing models or train new ones"""
        # Get all inventory items
        from models import InventoryItem
        items = self.db.session.query(InventoryItem).all()
        
        for item in items:
            model_path = os.path.join(self.model_dir, f'inventory_model_{item.product_id}.joblib')
            
            if os.path.exists(model_path):
                # Load existing model
                try:
                    self.models[item.product_id] = joblib.load(model_path)
                    print(f"Loaded model for product {item.product_id}")
                except Exception as e:
                    print(f"Error loading model for product {item.product_id}: {e}")
            else:
                # Train new model
                self.train_model_for_product(item.product_id)
    
    def get_product_usage_data(self, product_id, days=90):
        """Get historical usage data for a product"""
        from models import OrderDetail, Order
        from sqlalchemy import func
        
        # Calculate date threshold
        threshold = datetime.utcnow() - timedelta(days=days)
        
        # Query for daily product usage
        query = self.db.session.query(
            func.date(Order.created_at).label('date'),
            func.sum(OrderDetail.quantity).label('quantity')
        ).join(
            OrderDetail, Order.id == OrderDetail.order_id
        ).filter(
            OrderDetail.product_id == product_id,
            Order.created_at >= threshold
        ).group_by(
            func.date(Order.created_at)
        ).order_by(
            func.date(Order.created_at)
        )
        
        results = query.all()
        
        # Convert to list of (date, quantity) tuples
        return [(date, int(quantity)) for date, quantity in results]
    
    def engineer_features(self, product_id, usage_data):
        """Create features for prediction model"""
        if not usage_data:
            return None, None
        
        df = pd.DataFrame(usage_data, columns=['date', 'quantity'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # Add day of week feature
        df['day_of_week'] = df['date'].dt.dayofweek
        
        # Add month feature
        df['month'] = df['date'].dt.month
        
        # Add lag features
        for lag in [1, 2, 3, 7]:
            df[f'lag_{lag}'] = df['quantity'].shift(lag)
        
        # Add rolling mean features
        for window in [3, 7, 14]:
            df[f'rolling_mean_{window}'] = df['quantity'].rolling(window=window).mean()
        
        # Drop rows with NAs (due to lag/rolling features)
        df = df.dropna()
        
        if df.empty:
            return None, None
        
        # Split into X and y
        X = df.drop(['date', 'quantity'], axis=1)
        y = df['quantity']
        
        # Save feature function
        self.features[product_id] = lambda date: self.create_prediction_features(product_id, date)
        
        return X, y
    
    def train_model_for_product(self, product_id):
        """Train a prediction model for a specific product"""
        # Get usage data
        usage_data = self.get_product_usage_data(product_id)
        
        if not usage_data or len(usage_data) < 14:  # Need minimum data
            print(f"Not enough data to train model for product {product_id}")
            return False
        
        # Prepare features
        X, y = self.engineer_features(product_id, usage_data)
        
        if X is None or X.empty:
            print(f"Could not create features for product {product_id}")
            return False
        
        # Train model
        try:
            # Try Random Forest first
            model = RandomForestRegressor(n_estimators=50)
            model.fit(X, y)
            
            # Save model
            self.models[product_id] = model
            model_path = os.path.join(self.model_dir, f'inventory_model_{product_id}.joblib')
            joblib.dump(model, model_path)
            
            print(f"Trained model for product {product_id}")
            return True
        except Exception as e:
            print(f"Error training model for product {product_id}: {e}")
            # Fallback to linear model
            try:
                model = LinearRegression()
                model.fit(X, y)
                
                # Save model
                self.models[product_id] = model
                model_path = os.path.join(self.model_dir, f'inventory_model_{product_id}.joblib')
                joblib.dump(model, model_path)
                
                print(f"Trained fallback linear model for product {product_id}")
                return True
            except Exception as e2:
                print(f"Error training fallback model for product {product_id}: {e2}")
                return False
    
    def create_prediction_features(self, product_id, target_date):
        """Create features for a specific prediction date"""
        from models import OrderDetail, Order
        from sqlalchemy import func
        
        # Get usage data for past periods to create lag features
        past_data = self.get_product_usage_data(product_id, days=30)
        
        if not past_data:
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(past_data, columns=['date', 'quantity'])
        df['date'] = pd.to_datetime(df['date'])
        
        # Ensure data is sorted
        df = df.sort_values('date')
        
        # Create a one-row dataframe for the target date
        target_df = pd.DataFrame([{'date': target_date}])
        target_df['date'] = pd.to_datetime(target_df['date'])
        
        # Add day of week
        target_df['day_of_week'] = target_df['date'].dt.dayofweek
        
        # Add month
        target_df['month'] = target_df['date'].dt.month
        
        # Add lag features
        # For simplicity assuming daily prediction, adjust for different frequencies
        lag_values = {}
        for lag in [1, 2, 3, 7]:
            lag_idx = -lag
            if -lag < -len(df):
                lag_values[f'lag_{lag}'] = 0  # Default if not enough history
            else:
                lag_values[f'lag_{lag}'] = df.iloc[lag_idx]['quantity']
        
        for col, val in lag_values.items():
            target_df[col] = val
        
        # Add rolling mean features
        for window in [3, 7, 14]:
            if len(df) >= window:
                target_df[f'rolling_mean_{window}'] = df['quantity'].tail(window).mean()
            else:
                target_df[f'rolling_mean_{window}'] = df['quantity'].mean() if not df.empty else 0
        
        # Return feature vector
        X = target_df.drop('date', axis=1)
        return X
    
    def predict_demand(self, product_id, days=7):
        """Predict demand for a product for the next N days"""
        if product_id not in self.models:
            # Try to train a model first
            success = self.train_model_for_product(product_id)
            if not success:
                # Fall back to simple average-based prediction
                return self.simple_demand_prediction(product_id, days)
        
        # Generate dates to predict
        prediction_dates = [datetime.utcnow().date() + timedelta(days=i) for i in range(1, days+1)]
        
        predictions = []
        for date in prediction_dates:
            # Create features for this date
            X = self.create_prediction_features(product_id, date)
            
            if X is None or X.empty:
                # Fall back to simple prediction for this date
                avg_demand = self.simple_demand_prediction(product_id, 1)[0]['predicted_quantity']
                predictions.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'predicted_quantity': avg_demand,
                    'confidence': 0.5,
                    'method': 'average'
                })
                continue
            
            # Make prediction
            try:
                predicted = max(0, round(self.models[product_id].predict(X)[0]))
                
                # Add prediction details
                predictions.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'predicted_quantity': predicted,
                    'confidence': 0.8,  # Simplified confidence measure
                    'method': 'model'
                })
            except Exception as e:
                print(f"Error predicting for product {product_id} on {date}: {e}")
                # Fall back to simple prediction
                avg_demand = self.simple_demand_prediction(product_id, 1)[0]['predicted_quantity']
                predictions.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'predicted_quantity': avg_demand,
                    'confidence': 0.5,
                    'method': 'average'
                })
        
        return predictions
    
    def simple_demand_prediction(self, product_id, days=7):
        """Simple prediction based on historical averages"""
        # Get usage data
        usage_data = self.get_product_usage_data(product_id, days=30)
        
        # Calculate average daily demand
        if not usage_data:
            avg_demand = 0
        else:
            total_quantity = sum(quantity for _, quantity in usage_data)
            avg_demand = total_quantity / len(usage_data)
        
        # Generate predictions for each day
        prediction_dates = [datetime.utcnow().date() + timedelta(days=i) for i in range(1, days+1)]
        
        predictions = []
        for date in prediction_dates:
            # Simple day-of-week adjustment
            day_of_week = date.weekday()
            
            # Apply simple rules (weekends might have higher demand)
            adjustment = 1.0
            if day_of_week >= 5:  # Weekend
                adjustment = 1.3
            
            predictions.append({
                'date': date.strftime('%Y-%m-%d'),
                'predicted_quantity': round(avg_demand * adjustment),
                'confidence': 0.5,
                'method': 'average'
            })
        
        return predictions
    
    def get_restock_recommendations(self, days_ahead=7, threshold=0.3):
        """Generate restock recommendations based on predicted demand"""
        from models import InventoryItem, Product
        
        # Get all inventory items
        items = self.db.session.query(InventoryItem).join(
            Product, InventoryItem.product_id == Product.id
        ).filter(
            Product.is_available == True
        ).all()
        
        recommendations = []
        
        for item in items:
            # Current stock level
            current_stock = item.quantity
            
            # Predict demand
            predicted_demand = self.predict_demand(item.product_id, days=days_ahead)
            
            # Total predicted demand
            total_predicted = sum(p['predicted_quantity'] for p in predicted_demand)
            
            # Calculate if restock needed
            if item.min_quantity > 0:
                # Use minimum stock level from inventory item
                stock_threshold = item.min_quantity
            else:
                # Default minimum (30% of predicted weekly demand)
                stock_threshold = max(1, round(total_predicted * threshold))
            
            # Check if restock needed
            if current_stock <= stock_threshold:
                # Get product details
                product = self.db.session.query(Product).get(item.product_id)
                
                # Calculate recommended restock amount
                restock_amount = max(
                    stock_threshold - current_stock + total_predicted,
                    item.min_quantity * 2 if item.min_quantity > 0 else total_predicted * 2
                )
                
                recommendations.append({
                    'product_id': item.product_id,
                    'product_name': product.name,
                    'current_stock': current_stock,
                    'predicted_demand': total_predicted,
                    'minimum_threshold': stock_threshold,
                    'restock_amount': round(restock_amount),
                    'urgency': 'high' if current_stock < total_predicted else 'medium',
                    'prediction_details': predicted_demand
                })
        
        # Sort by urgency and stock ratio
        recommendations.sort(key=lambda x: (
            0 if x['urgency'] == 'high' else 1,
            x['current_stock'] / max(1, x['predicted_demand'])
        ))
        
        return recommendations


# Singleton instance
inventory_predictor = None

def init_inventory_predictor(db):
    """Initialize the inventory predictor"""
    global inventory_predictor
    inventory_predictor = InventoryPredictor(db)
    return inventory_predictor

def predict_product_demand(product_id, days=7):
    """Predict demand for a specific product"""
    if inventory_predictor is None:
        from app import db
        init_inventory_predictor(db)
    
    return inventory_predictor.predict_demand(product_id, days)

def get_inventory_recommendations(days=7):
    """Get inventory restock recommendations"""
    if inventory_predictor is None:
        from app import db
        init_inventory_predictor(db)
    
    return inventory_predictor.get_restock_recommendations(days_ahead=days)