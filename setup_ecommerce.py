#!/usr/bin/env python3
"""
Setup script for Wednesday Assistant E-commerce Platform
"""
import hashlib
from models import AdminUser, Product, db_manager

def hash_password(password: str) -> str:
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def setup_admin_user():
    """Create initial admin user"""
    print("🔐 Setting up admin user...")
    
    username = input("Enter admin username (default: admin): ").strip() or "admin"
    password = input("Enter admin password (default: admin123): ").strip() or "admin123"
    email = input("Enter admin email (optional): ").strip()
    
    password_hash = hash_password(password)
    
    try:
        admin_id = AdminUser.create(username, password_hash, email)
        print(f"✅ Admin user created successfully (ID: {admin_id})")
        print(f"   Username: {username}")
        print(f"   Password: {password}")
        print(f"   Login URL: http://localhost:5000/admin/login")
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")

def setup_sample_products():
    """Create sample products for testing"""
    print("\n📦 Setting up sample products...")
    
    sample_products = [
        {
            "name": "AI-Powered Smart Watch",
            "description": "A cutting-edge smartwatch with AI features, health monitoring, and WhatsApp notifications.",
            "price": 2999.99,
            "category": "Electronics",
            "stock_quantity": 50,
            "image_url": ""
        },
        {
            "name": "Wireless Earbuds Pro",
            "description": "Premium wireless earbuds with noise cancellation and long battery life.",
            "price": 899.99,
            "category": "Electronics", 
            "stock_quantity": 75,
            "image_url": ""
        },
        {
            "name": "Smart Home Assistant",
            "description": "Voice-controlled home assistant that integrates with your WhatsApp and other smart devices.",
            "price": 1499.99,
            "category": "Smart Home",
            "stock_quantity": 30,
            "image_url": ""
        },
        {
            "name": "Fitness Tracker Band",
            "description": "Track your fitness goals with this comfortable and feature-rich fitness band.",
            "price": 599.99,
            "category": "Health & Fitness",
            "stock_quantity": 100,
            "image_url": ""
        },
        {
            "name": "Bluetooth Speaker",
            "description": "Portable Bluetooth speaker with excellent sound quality and water resistance.",
            "price": 399.99,
            "category": "Electronics",
            "stock_quantity": 60,
            "image_url": ""
        }
    ]
    
    try:
        for product_data in sample_products:
            product_id = Product.create(
                name=product_data["name"],
                price=product_data["price"],
                description=product_data["description"],
                category=product_data["category"],
                stock_quantity=product_data["stock_quantity"],
                image_url=product_data["image_url"]
            )
            print(f"   ✅ Created: {product_data['name']} (ID: {product_id})")
        
        print(f"✅ {len(sample_products)} sample products created successfully")
        
    except Exception as e:
        print(f"❌ Error creating sample products: {e}")

def main():
    """Main setup function"""
    print("🚀 Wednesday Assistant E-commerce Setup")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    try:
        db_manager.init_database()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return
    
    # Setup admin user
    setup_admin_user()
    
    # Setup sample products
    create_products = input("\nWould you like to create sample products? (y/N): ").strip().lower()
    if create_products in ['y', 'yes']:
        setup_sample_products()
    
    print("\n🎉 Setup complete!")
    print("\nNext steps:")
    print("1. Start the application: python3 main.py")
    print("2. Visit the storefront: http://localhost:5000/store")
    print("3. Access admin dashboard: http://localhost:5000/admin/login")
    print("4. Configure PAXI API and email settings in .env file")
    print("\nEnvironment variables to configure:")
    print("   PAXI_API_KEY=your_paxi_api_key")
    print("   PAXI_MERCHANT_ID=your_merchant_id")
    print("   EMAIL_USER=your_email@gmail.com")
    print("   EMAIL_PASSWORD=your_app_password")
    print("   SMTP_SERVER=smtp.gmail.com")

if __name__ == "__main__":
    main()