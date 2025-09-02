"""
Admin dashboard for e-commerce management
"""
import os
import hashlib
import json
import csv
import io
from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template_string, request, jsonify, session, redirect, url_for, make_response
from models import Product, Customer, Order, Review, NewsletterSubscriber, AdminUser, db_manager
import logging

logger = logging.getLogger(__name__)

# Create blueprint for admin routes
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def hash_password(password: str) -> str:
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    """Decorator to require admin login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_user' not in session:
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username and password:
            password_hash = hash_password(password)
            admin = AdminUser.verify(username, password_hash)
            
            if admin:
                session['admin_user'] = {
                    'id': admin['id'],
                    'username': admin['username'],
                    'email': admin['email']
                }
                return redirect(url_for('admin.dashboard'))
            else:
                return render_template_string(LOGIN_TEMPLATE, error="Invalid credentials")
    
    return render_template_string(LOGIN_TEMPLATE)

@admin_bp.route('/logout')
def logout():
    """Admin logout"""
    session.pop('admin_user', None)
    return redirect(url_for('admin.login'))

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    """Main admin dashboard"""
    # Get dashboard statistics
    orders = Order.get_all()
    products = Product.get_all()
    customers = Customer.get_all()
    subscribers = NewsletterSubscriber.get_all_active()
    
    stats = {
        'total_orders': len(orders),
        'pending_orders': len([o for o in orders if o['status'] == 'pending']),
        'total_products': len(products),
        'total_customers': len(customers),
        'newsletter_subscribers': len(subscribers),
        'recent_orders': orders[:5]  # Last 5 orders
    }
    
    return render_template_string(DASHBOARD_TEMPLATE, stats=stats, user=session['admin_user'])

@admin_bp.route('/orders')
@login_required
def orders():
    """Orders management page"""
    orders = Order.get_all()
    return render_template_string(ORDERS_TEMPLATE, orders=orders)

@admin_bp.route('/orders/<order_number>/update', methods=['POST'])
@login_required
def update_order(order_number):
    """Update order status"""
    status = request.form.get('status')
    paxi_tracking = request.form.get('paxi_tracking', '')
    
    Order.update_status(order_number, status, paxi_tracking)
    
    return jsonify({'success': True, 'message': 'Order updated successfully'})

@admin_bp.route('/products')
@login_required
def products():
    """Products management page"""
    products = Product.get_all()
    return render_template_string(PRODUCTS_TEMPLATE, products=products)

@admin_bp.route('/products/create', methods=['POST'])
@login_required
def create_product():
    """Create new product"""
    name = request.form.get('name')
    price = float(request.form.get('price', 0))
    description = request.form.get('description', '')
    category = request.form.get('category', '')
    stock = int(request.form.get('stock', 0))
    image_url = request.form.get('image_url', '')
    
    product_id = Product.create(name, price, description, category, stock, image_url)
    
    return jsonify({'success': True, 'product_id': product_id})

@admin_bp.route('/customers')
@login_required
def customers():
    """Customers management page"""
    customers = Customer.get_all()
    return render_template_string(CUSTOMERS_TEMPLATE, customers=customers)

@admin_bp.route('/newsletter')
@login_required
def newsletter():
    """Newsletter management page"""
    subscribers = NewsletterSubscriber.get_all_active()
    return render_template_string(NEWSLETTER_TEMPLATE, subscribers=subscribers)

@admin_bp.route('/newsletter/send', methods=['POST'])
@login_required
def send_newsletter():
    """Send newsletter to all subscribers"""
    title = request.form.get('title')
    content = request.form.get('content')
    
    subscribers = NewsletterSubscriber.get_all_active()
    
    # TODO: Implement actual email sending
    # For now, just log the action
    logger.info(f"Newsletter '{title}' would be sent to {len(subscribers)} subscribers")
    
    return jsonify({
        'success': True, 
        'message': f'Newsletter sent to {len(subscribers)} subscribers',
        'recipients': len(subscribers)
    })

@admin_bp.route('/export/orders')
@login_required
def export_orders():
    """Export orders to CSV for financial tracking"""
    orders = Order.get_all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Order Number', 'Customer Name', 'Customer Email', 'Customer Phone',
        'Status', 'Total Amount', 'Delivery Address', 'Delivery City',
        'PAXI Tracking', 'Order Date', 'Notes'
    ])
    
    # Write order data
    for order in orders:
        writer.writerow([
            order['order_number'],
            order['customer_name'],
            order['customer_email'],
            order['customer_phone'],
            order['status'],
            order['total_amount'],
            order['delivery_address'],
            order['delivery_city'],
            order['paxi_tracking_number'] or '',
            order['created_at'],
            order['notes'] or ''
        ])
    
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=orders_{datetime.now().strftime("%Y%m%d")}.csv'
    
    return response

@admin_bp.route('/export/customers')
@login_required
def export_customers():
    """Export customers to CSV"""
    customers = Customer.get_all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'ID', 'Name', 'Email', 'Phone', 'WhatsApp', 'Address', 'City', 'Postal Code', 'Joined Date'
    ])
    
    # Write customer data
    for customer in customers:
        writer.writerow([
            customer['id'],
            customer['name'],
            customer['email'],
            customer['phone'],
            customer['whatsapp_number'],
            customer['address'],
            customer['city'],
            customer['postal_code'],
            customer['created_at']
        ])
    
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=customers_{datetime.now().strftime("%Y%m%d")}.csv'
    
    return response

@admin_bp.route('/setup')
def setup():
    """Initial admin setup"""
    # Check if admin already exists
    import sqlite3
    conn = sqlite3.connect(db_manager.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM admin_users")
    admin_count = cursor.fetchone()[0]
    conn.close()
    
    if admin_count > 0:
        return redirect(url_for('admin.login'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email', '')
        
        if username and password:
            password_hash = hash_password(password)
            AdminUser.create(username, password_hash, email)
            return redirect(url_for('admin.login'))
    
    return render_template_string(SETUP_TEMPLATE)

# HTML Templates
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Login - Wednesday Assistant</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 50px; }
        .login-container { max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="text"], input[type="password"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }
        .btn { background: #007bff; color: white; padding: 12px 20px; border: none; border-radius: 5px; cursor: pointer; width: 100%; }
        .btn:hover { background: #0056b3; }
        .error { color: red; margin-bottom: 15px; }
        h2 { text-align: center; color: #333; }
    </style>
</head>
<body>
    <div class="login-container">
        <h2>Admin Login</h2>
        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label for="username">Username:</label>
                <input type="text" id="username" name="username" required>
            </div>
            <div class="form-group">
                <label for="password">Password:</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn">Login</button>
        </form>
    </div>
</body>
</html>
"""

SETUP_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Setup - Wednesday Assistant</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 50px; }
        .setup-container { max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="text"], input[type="password"], input[type="email"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }
        .btn { background: #28a745; color: white; padding: 12px 20px; border: none; border-radius: 5px; cursor: pointer; width: 100%; }
        .btn:hover { background: #218838; }
        h2 { text-align: center; color: #333; }
        .info { background: #e9ecef; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="setup-container">
        <h2>Create Admin Account</h2>
        <div class="info">
            <strong>First Time Setup:</strong> Create your admin account to access the dashboard.
        </div>
        <form method="POST">
            <div class="form-group">
                <label for="username">Username:</label>
                <input type="text" id="username" name="username" required>
            </div>
            <div class="form-group">
                <label for="password">Password:</label>
                <input type="password" id="password" name="password" required>
            </div>
            <div class="form-group">
                <label for="email">Email (optional):</label>
                <input type="email" id="email" name="email">
            </div>
            <button type="submit" class="btn">Create Admin Account</button>
        </form>
    </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Dashboard - Wednesday Assistant</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f8f9fa; }
        .header { background: #343a40; color: white; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; }
        .nav { background: #495057; padding: 10px 20px; }
        .nav a { color: white; text-decoration: none; margin-right: 20px; padding: 8px 15px; border-radius: 4px; }
        .nav a:hover { background: #6c757d; }
        .container { padding: 20px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }
        .stat-number { font-size: 2em; font-weight: bold; color: #007bff; }
        .stat-label { color: #6c757d; margin-top: 5px; }
        .section { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }
        .table th { background: #f8f9fa; font-weight: bold; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.875em; }
        .badge-pending { background: #fff3cd; color: #856404; }
        .badge-completed { background: #d4edda; color: #155724; }
        .badge-processing { background: #cce7ff; color: #004085; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Wednesday Assistant - Admin Dashboard</h1>
        <div>
            Welcome, {{ user.username }} | <a href="{{ url_for('admin.logout') }}" style="color: #ffc107;">Logout</a>
        </div>
    </div>
    
    <div class="nav">
        <a href="{{ url_for('admin.dashboard') }}">Dashboard</a>
        <a href="{{ url_for('admin.orders') }}">Orders</a>
        <a href="{{ url_for('admin.products') }}">Products</a>
        <a href="{{ url_for('admin.customers') }}">Customers</a>
        <a href="{{ url_for('admin.newsletter') }}">Newsletter</a>
        <a href="{{ url_for('admin.export_orders') }}">Export Orders</a>
    </div>
    
    <div class="container">
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{{ stats.total_orders }}</div>
                <div class="stat-label">Total Orders</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ stats.pending_orders }}</div>
                <div class="stat-label">Pending Orders</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ stats.total_products }}</div>
                <div class="stat-label">Products</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ stats.total_customers }}</div>
                <div class="stat-label">Customers</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ stats.newsletter_subscribers }}</div>
                <div class="stat-label">Newsletter Subscribers</div>
            </div>
        </div>
        
        <div class="section">
            <h3>Recent Orders</h3>
            <table class="table">
                <thead>
                    <tr>
                        <th>Order #</th>
                        <th>Customer</th>
                        <th>Amount</th>
                        <th>Status</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody>
                    {% for order in stats.recent_orders %}
                    <tr>
                        <td>{{ order.order_number }}</td>
                        <td>{{ order.customer_name }}</td>
                        <td>R{{ "%.2f"|format(order.total_amount) }}</td>
                        <td>
                            <span class="badge badge-{{ order.status }}">{{ order.status|title }}</span>
                        </td>
                        <td>{{ order.created_at[:10] }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

ORDERS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Orders Management - Wednesday Assistant</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f8f9fa; }
        .header { background: #343a40; color: white; padding: 15px 20px; }
        .nav { background: #495057; padding: 10px 20px; }
        .nav a { color: white; text-decoration: none; margin-right: 20px; padding: 8px 15px; border-radius: 4px; }
        .nav a:hover { background: #6c757d; }
        .container { padding: 20px; }
        .section { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }
        .table th { background: #f8f9fa; font-weight: bold; }
        .btn { padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.875em; }
        .btn-primary { background: #007bff; color: white; }
        .btn-success { background: #28a745; color: white; }
        select { padding: 4px 8px; border: 1px solid #ced4da; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Orders Management</h1>
    </div>
    
    <div class="nav">
        <a href="{{ url_for('admin.dashboard') }}">Dashboard</a>
        <a href="{{ url_for('admin.orders') }}">Orders</a>
        <a href="{{ url_for('admin.products') }}">Products</a>
        <a href="{{ url_for('admin.customers') }}">Customers</a>
        <a href="{{ url_for('admin.newsletter') }}">Newsletter</a>
    </div>
    
    <div class="container">
        <div class="section">
            <h3>All Orders</h3>
            <table class="table">
                <thead>
                    <tr>
                        <th>Order #</th>
                        <th>Customer</th>
                        <th>Email</th>
                        <th>Phone</th>
                        <th>Amount</th>
                        <th>Status</th>
                        <th>PAXI Tracking</th>
                        <th>Date</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for order in orders %}
                    <tr>
                        <td>{{ order.order_number }}</td>
                        <td>{{ order.customer_name }}</td>
                        <td>{{ order.customer_email or '-' }}</td>
                        <td>{{ order.customer_phone or '-' }}</td>
                        <td>R{{ "%.2f"|format(order.total_amount) }}</td>
                        <td>
                            <select onchange="updateOrderStatus('{{ order.order_number }}', this.value)">
                                <option value="pending" {{ 'selected' if order.status == 'pending' }}>Pending</option>
                                <option value="processing" {{ 'selected' if order.status == 'processing' }}>Processing</option>
                                <option value="shipped" {{ 'selected' if order.status == 'shipped' }}>Shipped</option>
                                <option value="delivered" {{ 'selected' if order.status == 'delivered' }}>Delivered</option>
                                <option value="cancelled" {{ 'selected' if order.status == 'cancelled' }}>Cancelled</option>
                            </select>
                        </td>
                        <td>
                            <input type="text" value="{{ order.paxi_tracking_number or '' }}" 
                                   onchange="updatePaxiTracking('{{ order.order_number }}', this.value)"
                                   placeholder="Enter tracking #">
                        </td>
                        <td>{{ order.created_at[:10] }}</td>
                        <td>
                            <button class="btn btn-primary" onclick="viewOrder('{{ order.order_number }}')">View</button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        function updateOrderStatus(orderNumber, status) {
            fetch(`/admin/orders/${orderNumber}/update`, {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: `status=${status}`
            }).then(response => response.json())
              .then(data => {
                  if (data.success) {
                      alert('Order status updated successfully');
                  }
              });
        }
        
        function updatePaxiTracking(orderNumber, tracking) {
            if (tracking.trim() === '') return;
            
            fetch(`/admin/orders/${orderNumber}/update`, {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: `paxi_tracking=${tracking}`
            }).then(response => response.json())
              .then(data => {
                  if (data.success) {
                      alert('PAXI tracking updated successfully');
                  }
              });
        }
    </script>
</body>
</html>
"""

PRODUCTS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Products Management - Wednesday Assistant</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f8f9fa; }
        .header { background: #343a40; color: white; padding: 15px 20px; }
        .nav { background: #495057; padding: 10px 20px; }
        .nav a { color: white; text-decoration: none; margin-right: 20px; padding: 8px 15px; border-radius: 4px; }
        .nav a:hover { background: #6c757d; }
        .container { padding: 20px; }
        .section { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }
        .table th { background: #f8f9fa; font-weight: bold; }
        .form-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 15px; }
        input[type="text"], input[type="number"], textarea, select { width: 100%; padding: 8px; border: 1px solid #ced4da; border-radius: 4px; }
        .btn { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
        .btn-success { background: #28a745; color: white; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Products Management</h1>
    </div>
    
    <div class="nav">
        <a href="{{ url_for('admin.dashboard') }}">Dashboard</a>
        <a href="{{ url_for('admin.orders') }}">Orders</a>
        <a href="{{ url_for('admin.products') }}">Products</a>
        <a href="{{ url_for('admin.customers') }}">Customers</a>
        <a href="{{ url_for('admin.newsletter') }}">Newsletter</a>
    </div>
    
    <div class="container">
        <div class="section">
            <h3>Add New Product</h3>
            <form id="productForm">
                <div class="form-row">
                    <input type="text" name="name" placeholder="Product Name" required>
                    <input type="number" name="price" placeholder="Price" step="0.01" required>
                    <input type="text" name="category" placeholder="Category">
                </div>
                <div class="form-row">
                    <input type="number" name="stock" placeholder="Stock Quantity" value="0">
                    <input type="text" name="image_url" placeholder="Image URL">
                </div>
                <div class="form-row">
                    <textarea name="description" placeholder="Product Description" rows="3"></textarea>
                </div>
                <button type="submit" class="btn btn-success">Add Product</button>
            </form>
        </div>
        
        <div class="section">
            <h3>All Products</h3>
            <table class="table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Category</th>
                        <th>Price</th>
                        <th>Stock</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody>
                    {% for product in products %}
                    <tr>
                        <td>{{ product.id }}</td>
                        <td>{{ product.name }}</td>
                        <td>{{ product.category or '-' }}</td>
                        <td>R{{ "%.2f"|format(product.price) }}</td>
                        <td>{{ product.stock_quantity }}</td>
                        <td>{{ product.created_at[:10] }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        document.getElementById('productForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            
            fetch('/admin/products/create', {
                method: 'POST',
                body: formData
            }).then(response => response.json())
              .then(data => {
                  if (data.success) {
                      alert('Product created successfully');
                      location.reload();
                  }
              });
        });
    </script>
</body>
</html>
"""

CUSTOMERS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Customers Management - Wednesday Assistant</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f8f9fa; }
        .header { background: #343a40; color: white; padding: 15px 20px; }
        .nav { background: #495057; padding: 10px 20px; }
        .nav a { color: white; text-decoration: none; margin-right: 20px; padding: 8px 15px; border-radius: 4px; }
        .nav a:hover { background: #6c757d; }
        .container { padding: 20px; }
        .section { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }
        .table th { background: #f8f9fa; font-weight: bold; }
        .btn { padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.875em; }
        .btn-primary { background: #007bff; color: white; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Customers Management</h1>
    </div>
    
    <div class="nav">
        <a href="{{ url_for('admin.dashboard') }}">Dashboard</a>
        <a href="{{ url_for('admin.orders') }}">Orders</a>
        <a href="{{ url_for('admin.products') }}">Products</a>
        <a href="{{ url_for('admin.customers') }}">Customers</a>
        <a href="{{ url_for('admin.newsletter') }}">Newsletter</a>
    </div>
    
    <div class="container">
        <div class="section">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h3>All Customers</h3>
                <a href="{{ url_for('admin.export_customers') }}" class="btn btn-primary">Export to CSV</a>
            </div>
            <table class="table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Phone</th>
                        <th>WhatsApp</th>
                        <th>City</th>
                        <th>Joined</th>
                    </tr>
                </thead>
                <tbody>
                    {% for customer in customers %}
                    <tr>
                        <td>{{ customer.id }}</td>
                        <td>{{ customer.name }}</td>
                        <td>{{ customer.email or '-' }}</td>
                        <td>{{ customer.phone or '-' }}</td>
                        <td>{{ customer.whatsapp_number or '-' }}</td>
                        <td>{{ customer.city or '-' }}</td>
                        <td>{{ customer.created_at[:10] }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

NEWSLETTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Newsletter Management - Wednesday Assistant</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f8f9fa; }
        .header { background: #343a40; color: white; padding: 15px 20px; }
        .nav { background: #495057; padding: 10px 20px; }
        .nav a { color: white; text-decoration: none; margin-right: 20px; padding: 8px 15px; border-radius: 4px; }
        .nav a:hover { background: #6c757d; }
        .container { padding: 20px; }
        .section { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }
        .table th { background: #f8f9fa; font-weight: bold; }
        .form-group { margin-bottom: 15px; }
        input[type="text"], textarea { width: 100%; padding: 10px; border: 1px solid #ced4da; border-radius: 4px; }
        .btn { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
        .btn-success { background: #28a745; color: white; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Newsletter Management</h1>
    </div>
    
    <div class="nav">
        <a href="{{ url_for('admin.dashboard') }}">Dashboard</a>
        <a href="{{ url_for('admin.orders') }}">Orders</a>
        <a href="{{ url_for('admin.products') }}">Products</a>
        <a href="{{ url_for('admin.customers') }}">Customers</a>
        <a href="{{ url_for('admin.newsletter') }}">Newsletter</a>
    </div>
    
    <div class="container">
        <div class="section">
            <h3>Send Newsletter</h3>
            <form id="newsletterForm">
                <div class="form-group">
                    <input type="text" name="title" placeholder="Newsletter Title" required>
                </div>
                <div class="form-group">
                    <textarea name="content" placeholder="Newsletter Content" rows="8" required></textarea>
                </div>
                <button type="submit" class="btn btn-success">Send to All Subscribers ({{ subscribers|length }})</button>
            </form>
        </div>
        
        <div class="section">
            <h3>Newsletter Subscribers ({{ subscribers|length }})</h3>
            <table class="table">
                <thead>
                    <tr>
                        <th>Email</th>
                        <th>Name</th>
                        <th>Phone</th>
                        <th>WhatsApp</th>
                        <th>Subscribed</th>
                    </tr>
                </thead>
                <tbody>
                    {% for subscriber in subscribers %}
                    <tr>
                        <td>{{ subscriber.email }}</td>
                        <td>{{ subscriber.name or '-' }}</td>
                        <td>{{ subscriber.phone or '-' }}</td>
                        <td>{{ subscriber.whatsapp_number or '-' }}</td>
                        <td>{{ subscriber.subscribed_at[:10] }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        document.getElementById('newsletterForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            
            fetch('/admin/newsletter/send', {
                method: 'POST',
                body: formData
            }).then(response => response.json())
              .then(data => {
                  if (data.success) {
                      alert(data.message);
                      this.reset();
                  }
              });
        });
    </script>
</body>
</html>
"""