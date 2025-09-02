"""
E-commerce database models for Wednesday WhatsApp Assistant
"""
import json
import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages SQLite database for e-commerce functionality"""
    
    def __init__(self, db_path: str = "ecommerce.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
                category TEXT,
                stock_quantity INTEGER DEFAULT 0,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Customers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                whatsapp_number TEXT,
                address TEXT,
                city TEXT,
                postal_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                order_number TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'pending',
                total_amount REAL NOT NULL,
                delivery_address TEXT,
                delivery_city TEXT,
                delivery_postal_code TEXT,
                paxi_tracking_number TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )
        """)
        
        # Order items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                product_id INTEGER,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                total_price REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders (id),
                FOREIGN KEY (product_id) REFERENCES products (id)
            )
        """)
        
        # Reviews table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                customer_id INTEGER,
                rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products (id),
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )
        """)
        
        # Newsletter subscribers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                phone TEXT,
                whatsapp_number TEXT,
                subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT 1
            )
        """)
        
        # Newsletter campaigns table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                recipients_count INTEGER DEFAULT 0
            )
        """)
        
        # Admin users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

# Global database instance
db_manager = DatabaseManager()

class Product:
    """Product model"""
    
    @staticmethod
    def create(name: str, price: float, description: str = "", category: str = "", 
               stock_quantity: int = 0, image_url: str = "") -> int:
        """Create a new product"""
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO products (name, description, price, category, stock_quantity, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, description, price, category, stock_quantity, image_url))
        
        product_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Created product: {name} (ID: {product_id})")
        return product_id
    
    @staticmethod
    def get_all() -> List[Dict]:
        """Get all products"""
        conn = sqlite3.connect(db_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM products ORDER BY created_at DESC")
        products = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return products
    
    @staticmethod
    def get_by_id(product_id: int) -> Optional[Dict]:
        """Get product by ID"""
        conn = sqlite3.connect(db_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        
        conn.close()
        return dict(row) if row else None
    
    @staticmethod
    def update_stock(product_id: int, quantity: int) -> bool:
        """Update product stock"""
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE products SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (quantity, product_id))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success

class Customer:
    """Customer model"""
    
    @staticmethod
    def create(name: str, email: str = "", phone: str = "", whatsapp_number: str = "",
               address: str = "", city: str = "", postal_code: str = "") -> int:
        """Create a new customer"""
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO customers (name, email, phone, whatsapp_number, address, city, postal_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, email, phone, whatsapp_number, address, city, postal_code))
        
        customer_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Created customer: {name} (ID: {customer_id})")
        return customer_id
    
    @staticmethod
    def get_by_phone(phone: str) -> Optional[Dict]:
        """Get customer by phone number"""
        conn = sqlite3.connect(db_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM customers 
            WHERE phone = ? OR whatsapp_number = ?
        """, (phone, phone))
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    @staticmethod
    def get_all() -> List[Dict]:
        """Get all customers"""
        conn = sqlite3.connect(db_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM customers ORDER BY created_at DESC")
        customers = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return customers

class Order:
    """Order model"""
    
    @staticmethod
    def create(customer_id: int, total_amount: float, delivery_address: str = "",
               delivery_city: str = "", delivery_postal_code: str = "", notes: str = "") -> str:
        """Create a new order"""
        import uuid
        order_number = f"ORD{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:8].upper()}"
        
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO orders (customer_id, order_number, total_amount, delivery_address,
                              delivery_city, delivery_postal_code, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (customer_id, order_number, total_amount, delivery_address, 
              delivery_city, delivery_postal_code, notes))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created order: {order_number}")
        return order_number
    
    @staticmethod
    def add_item(order_number: str, product_id: int, quantity: int, unit_price: float):
        """Add item to order"""
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        
        # Get order ID
        cursor.execute("SELECT id FROM orders WHERE order_number = ?", (order_number,))
        order_id = cursor.fetchone()[0]
        
        total_price = quantity * unit_price
        
        cursor.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, unit_price, total_price)
            VALUES (?, ?, ?, ?, ?)
        """, (order_id, product_id, quantity, unit_price, total_price))
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_all() -> List[Dict]:
        """Get all orders with customer details"""
        conn = sqlite3.connect(db_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT o.*, c.name as customer_name, c.email as customer_email, c.phone as customer_phone
            FROM orders o
            LEFT JOIN customers c ON o.customer_id = c.id
            ORDER BY o.created_at DESC
        """)
        
        orders = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return orders
    
    @staticmethod
    def update_status(order_number: str, status: str, paxi_tracking: str = ""):
        """Update order status"""
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        
        if paxi_tracking:
            cursor.execute("""
                UPDATE orders 
                SET status = ?, paxi_tracking_number = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_number = ?
            """, (status, paxi_tracking, order_number))
        else:
            cursor.execute("""
                UPDATE orders 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_number = ?
            """, (status, order_number))
        
        conn.commit()
        conn.close()

class Review:
    """Review model"""
    
    @staticmethod
    def create(product_id: int, customer_id: int, rating: int, comment: str = "") -> int:
        """Create a new review"""
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO reviews (product_id, customer_id, rating, comment)
            VALUES (?, ?, ?, ?)
        """, (product_id, customer_id, rating, comment))
        
        review_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Created review for product {product_id} (ID: {review_id})")
        return review_id
    
    @staticmethod
    def get_by_product(product_id: int) -> List[Dict]:
        """Get reviews for a product"""
        conn = sqlite3.connect(db_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT r.*, c.name as customer_name
            FROM reviews r
            LEFT JOIN customers c ON r.customer_id = c.id
            WHERE r.product_id = ?
            ORDER BY r.created_at DESC
        """, (product_id,))
        
        reviews = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return reviews

class NewsletterSubscriber:
    """Newsletter subscriber model"""
    
    @staticmethod
    def subscribe(email: str, name: str = "", phone: str = "", whatsapp_number: str = "") -> int:
        """Subscribe to newsletter"""
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO newsletter_subscribers (email, name, phone, whatsapp_number)
                VALUES (?, ?, ?, ?)
            """, (email, name, phone, whatsapp_number))
            
            subscriber_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            logger.info(f"Newsletter subscription: {email} (ID: {subscriber_id})")
            return subscriber_id
            
        except sqlite3.IntegrityError:
            conn.close()
            logger.warning(f"Email already subscribed: {email}")
            return -1
    
    @staticmethod
    def get_all_active() -> List[Dict]:
        """Get all active subscribers"""
        conn = sqlite3.connect(db_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM newsletter_subscribers 
            WHERE active = 1 
            ORDER BY subscribed_at DESC
        """)
        
        subscribers = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return subscribers

class AdminUser:
    """Admin user model"""
    
    @staticmethod
    def create(username: str, password_hash: str, email: str = "") -> int:
        """Create admin user"""
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO admin_users (username, password_hash, email)
            VALUES (?, ?, ?)
        """, (username, password_hash, email))
        
        admin_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Created admin user: {username}")
        return admin_id
    
    @staticmethod
    def verify(username: str, password_hash: str) -> Optional[Dict]:
        """Verify admin credentials"""
        conn = sqlite3.connect(db_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM admin_users WHERE username = ? AND password_hash = ?
        """, (username, password_hash))
        
        row = cursor.fetchone()
        
        if row:
            # Update last login
            cursor.execute("""
                UPDATE admin_users SET last_login = CURRENT_TIMESTAMP WHERE id = ?
            """, (row['id'],))
            conn.commit()
        
        conn.close()
        return dict(row) if row else None