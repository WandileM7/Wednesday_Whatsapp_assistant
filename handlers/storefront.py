"""
Customer storefront interface
"""
from flask import Blueprint, render_template_string, request, jsonify
from models import Product, Review
import logging

logger = logging.getLogger(__name__)

# Create blueprint for storefront
store_bp = Blueprint('store', __name__, url_prefix='/store')

@store_bp.route('/')
def storefront():
    """Main storefront page"""
    products = Product.get_all()
    return render_template_string(STOREFRONT_TEMPLATE, products=products)

@store_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    """Product detail page with reviews"""
    product = Product.get_by_id(product_id)
    if not product:
        return "Product not found", 404
    
    reviews = Review.get_by_product(product_id)
    avg_rating = sum(r['rating'] for r in reviews) / len(reviews) if reviews else 0
    
    return render_template_string(PRODUCT_DETAIL_TEMPLATE, 
                                product=product, 
                                reviews=reviews, 
                                avg_rating=avg_rating)

@store_bp.route('/checkout')
def checkout():
    """Checkout page"""
    return render_template_string(CHECKOUT_TEMPLATE)

@store_bp.route('/newsletter-signup')
def newsletter_signup():
    """Newsletter signup page"""
    return render_template_string(NEWSLETTER_SIGNUP_TEMPLATE)

# HTML Templates
STOREFRONT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Wednesday Assistant Store</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f8f9fa; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px 0; text-align: center; }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { font-size: 1.2em; opacity: 0.9; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .products-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 30px; }
        .product-card { background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: transform 0.3s; overflow: hidden; }
        .product-card:hover { transform: translateY(-5px); box-shadow: 0 8px 15px rgba(0,0,0,0.2); }
        .product-image { width: 100%; height: 200px; background: #eee; display: flex; align-items: center; justify-content: center; font-size: 3em; color: #ccc; }
        .product-info { padding: 20px; }
        .product-name { font-size: 1.3em; font-weight: bold; margin-bottom: 10px; color: #333; }
        .product-description { color: #666; margin-bottom: 15px; line-height: 1.4; }
        .product-price { font-size: 1.5em; font-weight: bold; color: #28a745; margin-bottom: 15px; }
        .product-category { background: #007bff; color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.8em; display: inline-block; margin-bottom: 10px; }
        .btn { background: #28a745; color: white; padding: 12px 20px; border: none; border-radius: 6px; cursor: pointer; font-size: 1em; transition: background 0.3s; text-decoration: none; display: inline-block; text-align: center; }
        .btn:hover { background: #218838; }
        .btn-secondary { background: #6c757d; }
        .btn-secondary:hover { background: #545b62; }
        .navbar { background: white; padding: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .nav-container { max-width: 1200px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; padding: 0 20px; }
        .nav-links a { text-decoration: none; color: #333; margin: 0 15px; font-weight: 500; }
        .nav-links a:hover { color: #007bff; }
        .footer { background: #343a40; color: white; text-align: center; padding: 30px 0; margin-top: 50px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🛍️ Wednesday Assistant Store</h1>
        <p>Your AI-powered shopping experience</p>
    </div>
    
    <nav class="navbar">
        <div class="nav-container">
            <div class="nav-links">
                <a href="/store">Home</a>
                <a href="/store/checkout">Checkout</a>
                <a href="/store/newsletter-signup">Newsletter</a>
                <a href="/admin/login">Admin</a>
            </div>
            <div>
                <span id="cart-count">0 items in cart</span>
            </div>
        </div>
    </nav>
    
    <div class="container">
        {% if products %}
            <div class="products-grid">
                {% for product in products %}
                <div class="product-card">
                    <div class="product-image">
                        {% if product.image_url %}
                            <img src="{{ product.image_url }}" alt="{{ product.name }}" style="width: 100%; height: 100%; object-fit: cover;">
                        {% else %}
                            📦
                        {% endif %}
                    </div>
                    <div class="product-info">
                        {% if product.category %}
                            <span class="product-category">{{ product.category }}</span>
                        {% endif %}
                        <div class="product-name">{{ product.name }}</div>
                        <div class="product-description">{{ product.description or 'No description available.' }}</div>
                        <div class="product-price">R{{ "%.2f"|format(product.price) }}</div>
                        <div style="display: flex; gap: 10px;">
                            <a href="/store/product/{{ product.id }}" class="btn btn-secondary">View Details</a>
                            <button class="btn" onclick="addToCart({{ product.id }}, '{{ product.name }}', {{ product.price }})">Add to Cart</button>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        {% else %}
            <div style="text-align: center; padding: 50px; background: white; border-radius: 10px;">
                <h2>No products available</h2>
                <p>Please check back later or contact the store admin.</p>
            </div>
        {% endif %}
    </div>
    
    <div class="footer">
        <p>&copy; 2024 Wednesday Assistant Store. Powered by AI technology.</p>
    </div>
    
    <script>
        let cart = JSON.parse(localStorage.getItem('cart') || '[]');
        updateCartCount();
        
        function addToCart(productId, name, price) {
            const existingItem = cart.find(item => item.id === productId);
            if (existingItem) {
                existingItem.quantity += 1;
            } else {
                cart.push({ id: productId, name: name, price: price, quantity: 1 });
            }
            
            localStorage.setItem('cart', JSON.stringify(cart));
            updateCartCount();
            alert(`${name} added to cart!`);
        }
        
        function updateCartCount() {
            const count = cart.reduce((total, item) => total + item.quantity, 0);
            document.getElementById('cart-count').textContent = `${count} items in cart`;
        }
    </script>
</body>
</html>
"""

PRODUCT_DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ product.name }} - Wednesday Assistant Store</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f8f9fa; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px 0; text-align: center; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .product-detail { background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); padding: 30px; margin-top: 20px; }
        .product-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; margin-bottom: 40px; }
        .product-image { background: #eee; height: 400px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 4em; color: #ccc; }
        .product-info h1 { font-size: 2.5em; margin-bottom: 15px; }
        .product-price { font-size: 2em; color: #28a745; font-weight: bold; margin: 20px 0; }
        .product-description { font-size: 1.1em; line-height: 1.6; color: #555; margin-bottom: 20px; }
        .btn { background: #28a745; color: white; padding: 15px 30px; border: none; border-radius: 6px; font-size: 1.1em; cursor: pointer; }
        .btn:hover { background: #218838; }
        .reviews-section { margin-top: 40px; }
        .review-card { background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 15px; }
        .review-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .rating { color: #ffc107; }
        .review-form { background: #e9ecef; padding: 20px; border-radius: 8px; margin-top: 20px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input, .form-group textarea, .form-group select { width: 100%; padding: 10px; border: 1px solid #ced4da; border-radius: 4px; }
        .back-link { color: #007bff; text-decoration: none; margin-bottom: 20px; display: inline-block; }
        .back-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ product.name }}</h1>
    </div>
    
    <div class="container">
        <a href="/store" class="back-link">← Back to Store</a>
        
        <div class="product-detail">
            <div class="product-grid">
                <div class="product-image">
                    {% if product.image_url %}
                        <img src="{{ product.image_url }}" alt="{{ product.name }}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 8px;">
                    {% else %}
                        📦
                    {% endif %}
                </div>
                
                <div class="product-info">
                    <h1>{{ product.name }}</h1>
                    {% if product.category %}
                        <span style="background: #007bff; color: white; padding: 6px 12px; border-radius: 4px; font-size: 0.9em;">{{ product.category }}</span>
                    {% endif %}
                    
                    <div class="product-price">R{{ "%.2f"|format(product.price) }}</div>
                    
                    <div class="product-description">
                        {{ product.description or 'No description available.' }}
                    </div>
                    
                    <div style="margin-bottom: 20px;">
                        <strong>Stock:</strong> {{ product.stock_quantity }} available
                    </div>
                    
                    {% if reviews %}
                        <div style="margin-bottom: 20px;">
                            <strong>Rating:</strong> 
                            <span class="rating">
                                {% for i in range(1, 6) %}
                                    {% if i <= avg_rating %}⭐{% else %}☆{% endif %}
                                {% endfor %}
                            </span>
                            ({{ avg_rating|round(1) }}/5 from {{ reviews|length }} reviews)
                        </div>
                    {% endif %}
                    
                    <button class="btn" onclick="addToCart({{ product.id }}, '{{ product.name }}', {{ product.price }})">
                        Add to Cart
                    </button>
                </div>
            </div>
            
            <div class="reviews-section">
                <h3>Customer Reviews</h3>
                
                {% if reviews %}
                    {% for review in reviews %}
                    <div class="review-card">
                        <div class="review-header">
                            <strong>{{ review.customer_name or 'Anonymous' }}</strong>
                            <span class="rating">
                                {% for i in range(1, 6) %}
                                    {% if i <= review.rating %}⭐{% else %}☆{% endif %}
                                {% endfor %}
                            </span>
                        </div>
                        <p>{{ review.comment or 'No comment provided.' }}</p>
                        <small style="color: #666;">{{ review.created_at[:10] }}</small>
                    </div>
                    {% endfor %}
                {% else %}
                    <p>No reviews yet. Be the first to review this product!</p>
                {% endif %}
                
                <div class="review-form">
                    <h4>Write a Review</h4>
                    <form id="reviewForm">
                        <div class="form-group">
                            <label>Your Phone Number:</label>
                            <input type="tel" name="customer_phone" required placeholder="Your phone number">
                        </div>
                        <div class="form-group">
                            <label>Rating:</label>
                            <select name="rating" required>
                                <option value="">Select rating</option>
                                <option value="5">⭐⭐⭐⭐⭐ Excellent</option>
                                <option value="4">⭐⭐⭐⭐☆ Good</option>
                                <option value="3">⭐⭐⭐☆☆ Average</option>
                                <option value="2">⭐⭐☆☆☆ Poor</option>
                                <option value="1">⭐☆☆☆☆ Terrible</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Your Review:</label>
                            <textarea name="comment" rows="4" placeholder="Share your experience with this product..."></textarea>
                        </div>
                        <button type="submit" class="btn">Submit Review</button>
                    </form>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let cart = JSON.parse(localStorage.getItem('cart') || '[]');
        
        function addToCart(productId, name, price) {
            const existingItem = cart.find(item => item.id === productId);
            if (existingItem) {
                existingItem.quantity += 1;
            } else {
                cart.push({ id: productId, name: name, price: price, quantity: 1 });
            }
            
            localStorage.setItem('cart', JSON.stringify(cart));
            alert(`${name} added to cart!`);
        }
        
        document.getElementById('reviewForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const reviewData = {
                product_id: {{ product.id }},
                customer_phone: formData.get('customer_phone'),
                rating: parseInt(formData.get('rating')),
                comment: formData.get('comment')
            };
            
            fetch('/api/orders/reviews/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(reviewData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Review submitted successfully!');
                    location.reload();
                } else {
                    alert('Error: ' + data.error);
                }
            })
            .catch(error => {
                alert('Error submitting review: ' + error);
            });
        });
    </script>
</body>
</html>
"""

CHECKOUT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Checkout - Wednesday Assistant Store</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f8f9fa; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px 0; text-align: center; }
        .container { max-width: 800px; margin: 0 auto; padding: 20px; }
        .checkout-form { background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); padding: 30px; margin-top: 20px; }
        .form-section { margin-bottom: 30px; }
        .form-section h3 { margin-bottom: 15px; color: #333; border-bottom: 2px solid #007bff; padding-bottom: 5px; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 12px; border: 1px solid #ced4da; border-radius: 6px; font-size: 1em; }
        .cart-items { background: #f8f9fa; padding: 20px; border-radius: 6px; margin-bottom: 20px; }
        .cart-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #dee2e6; }
        .cart-item:last-child { border-bottom: none; }
        .btn { background: #28a745; color: white; padding: 15px 30px; border: none; border-radius: 6px; font-size: 1.1em; cursor: pointer; width: 100%; }
        .btn:hover { background: #218838; }
        .btn:disabled { background: #6c757d; cursor: not-allowed; }
        .pickup-point { border: 1px solid #dee2e6; padding: 15px; border-radius: 6px; margin-bottom: 10px; cursor: pointer; }
        .pickup-point.selected { border-color: #007bff; background: #e7f3ff; }
        .pickup-point h4 { margin-bottom: 5px; }
        .total-section { background: #e9ecef; padding: 20px; border-radius: 6px; margin-top: 20px; }
        .back-link { color: #007bff; text-decoration: none; margin-bottom: 20px; display: inline-block; }
        .back-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🛒 Checkout</h1>
    </div>
    
    <div class="container">
        <a href="/store" class="back-link">← Continue Shopping</a>
        
        <div class="checkout-form">
            <div id="cart-summary" class="cart-items">
                <h3>Your Order</h3>
                <div id="cart-items-list"></div>
            </div>
            
            <form id="checkoutForm">
                <div class="form-section">
                    <h3>Customer Information</h3>
                    <div class="form-row">
                        <div class="form-group">
                            <label>Full Name *</label>
                            <input type="text" name="customer_name" required>
                        </div>
                        <div class="form-group">
                            <label>Phone Number *</label>
                            <input type="tel" name="customer_phone" required>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>Email</label>
                            <input type="email" name="customer_email">
                        </div>
                        <div class="form-group">
                            <label>WhatsApp Number</label>
                            <input type="tel" name="customer_whatsapp">
                        </div>
                    </div>
                </div>
                
                <div class="form-section">
                    <h3>Delivery Information</h3>
                    <div class="form-group">
                        <label>City *</label>
                        <input type="text" name="delivery_city" required onchange="loadPickupPoints()">
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>Address</label>
                            <input type="text" name="delivery_address">
                        </div>
                        <div class="form-group">
                            <label>Postal Code</label>
                            <input type="text" name="delivery_postal_code">
                        </div>
                    </div>
                </div>
                
                <div class="form-section">
                    <h3>PAXI Pickup Point *</h3>
                    <div id="pickup-points-list">
                        <p>Enter your city above to see available pickup points.</p>
                    </div>
                    <input type="hidden" name="pickup_point_id" id="selected_pickup_point">
                </div>
                
                <div class="form-section">
                    <h3>Additional Notes</h3>
                    <div class="form-group">
                        <textarea name="notes" rows="3" placeholder="Any special instructions..."></textarea>
                    </div>
                </div>
                
                <div class="total-section">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                        <span>Subtotal:</span>
                        <span id="subtotal">R0.00</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                        <span>Delivery:</span>
                        <span id="delivery-cost">R0.00</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 1.2em; font-weight: bold; border-top: 1px solid #ccc; padding-top: 10px;">
                        <span>Total:</span>
                        <span id="total">R0.00</span>
                    </div>
                </div>
                
                <button type="submit" class="btn" id="place-order-btn" disabled>
                    Place Order
                </button>
            </form>
            
            <div style="margin-top: 20px; text-align: center;">
                <a href="/store/newsletter-signup" style="color: #007bff;">📧 Subscribe to our newsletter for updates</a>
            </div>
        </div>
    </div>
    
    <script>
        let cart = JSON.parse(localStorage.getItem('cart') || '[]');
        let pickupPoints = [];
        let selectedPickupPoint = null;
        
        // Load cart items
        function loadCart() {
            const cartList = document.getElementById('cart-items-list');
            if (cart.length === 0) {
                cartList.innerHTML = '<p>Your cart is empty. <a href="/store">Continue shopping</a></p>';
                return;
            }
            
            let html = '';
            let subtotal = 0;
            
            cart.forEach(item => {
                const itemTotal = item.price * item.quantity;
                subtotal += itemTotal;
                
                html += `
                    <div class="cart-item">
                        <div>
                            <strong>${item.name}</strong><br>
                            <small>Qty: ${item.quantity} × R${item.price.toFixed(2)}</small>
                        </div>
                        <div>R${itemTotal.toFixed(2)}</div>
                    </div>
                `;
            });
            
            cartList.innerHTML = html;
            document.getElementById('subtotal').textContent = `R${subtotal.toFixed(2)}`;
            updateTotal();
        }
        
        // Load pickup points
        function loadPickupPoints() {
            const city = document.querySelector('input[name="delivery_city"]').value;
            if (!city) return;
            
            fetch(`/api/orders/delivery-options?city=${encodeURIComponent(city)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        pickupPoints = data.pickup_points;
                        displayPickupPoints();
                    }
                })
                .catch(error => console.error('Error loading pickup points:', error));
        }
        
        // Display pickup points
        function displayPickupPoints() {
            const container = document.getElementById('pickup-points-list');
            
            if (pickupPoints.length === 0) {
                container.innerHTML = '<p>No pickup points available for this city.</p>';
                return;
            }
            
            let html = '';
            pickupPoints.forEach(point => {
                html += `
                    <div class="pickup-point" onclick="selectPickupPoint('${point.id}', this)">
                        <h4>${point.name}</h4>
                        <p>${point.address}</p>
                        <small>${point.operating_hours}</small>
                    </div>
                `;
            });
            
            container.innerHTML = html;
        }
        
        // Select pickup point
        function selectPickupPoint(pointId, element) {
            // Remove previous selection
            document.querySelectorAll('.pickup-point').forEach(el => el.classList.remove('selected'));
            
            // Select new point
            element.classList.add('selected');
            document.getElementById('selected_pickup_point').value = pointId;
            selectedPickupPoint = pointId;
            
            // Calculate delivery cost
            calculateDelivery();
            
            // Enable order button
            document.getElementById('place-order-btn').disabled = false;
        }
        
        // Calculate delivery cost
        function calculateDelivery() {
            if (!selectedPickupPoint) return;
            
            const totalWeight = cart.reduce((total, item) => total + (item.quantity * 1.0), 0); // Assume 1kg per item
            
            fetch(`/api/orders/calculate-shipping?pickup_point_id=${selectedPickupPoint}&weight=${totalWeight}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('delivery-cost').textContent = `R${data.cost.toFixed(2)}`;
                        updateTotal();
                    }
                })
                .catch(error => console.error('Error calculating delivery:', error));
        }
        
        // Update total
        function updateTotal() {
            const subtotal = parseFloat(document.getElementById('subtotal').textContent.replace('R', ''));
            const delivery = parseFloat(document.getElementById('delivery-cost').textContent.replace('R', '') || '0');
            const total = subtotal + delivery;
            document.getElementById('total').textContent = `R${total.toFixed(2)}`;
        }
        
        // Submit order
        document.getElementById('checkoutForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            if (!selectedPickupPoint) {
                alert('Please select a pickup point');
                return;
            }
            
            const formData = new FormData(this);
            const orderData = {
                customer_name: formData.get('customer_name'),
                customer_phone: formData.get('customer_phone'),
                customer_email: formData.get('customer_email'),
                customer_whatsapp: formData.get('customer_whatsapp'),
                delivery_address: formData.get('delivery_address'),
                delivery_city: formData.get('delivery_city'),
                delivery_postal_code: formData.get('delivery_postal_code'),
                pickup_point_id: selectedPickupPoint,
                notes: formData.get('notes'),
                items: cart
            };
            
            document.getElementById('place-order-btn').disabled = true;
            document.getElementById('place-order-btn').textContent = 'Processing...';
            
            fetch('/api/orders/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(orderData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Clear cart
                    localStorage.removeItem('cart');
                    
                    alert(`Order placed successfully!\\n\\nOrder Number: ${data.order_number}\\nTotal: R${data.total_amount.toFixed(2)}\\n\\nYou will receive notifications about your order.`);
                    
                    // Redirect to store
                    window.location.href = '/store';
                } else {
                    alert('Error placing order: ' + data.error);
                    document.getElementById('place-order-btn').disabled = false;
                    document.getElementById('place-order-btn').textContent = 'Place Order';
                }
            })
            .catch(error => {
                alert('Error placing order: ' + error);
                document.getElementById('place-order-btn').disabled = false;
                document.getElementById('place-order-btn').textContent = 'Place Order';
            });
        });
        
        // Initialize
        loadCart();
    </script>
</body>
</html>
"""

NEWSLETTER_SIGNUP_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Newsletter Signup - Wednesday Assistant Store</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f8f9fa; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 0; text-align: center; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .signup-form { background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); padding: 40px; margin-top: 20px; text-align: center; }
        .form-group { margin-bottom: 20px; text-align: left; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: bold; }
        .form-group input { width: 100%; padding: 12px; border: 1px solid #ced4da; border-radius: 6px; font-size: 1em; }
        .btn { background: #28a745; color: white; padding: 15px 30px; border: none; border-radius: 6px; font-size: 1.1em; cursor: pointer; width: 100%; }
        .btn:hover { background: #218838; }
        .back-link { color: #007bff; text-decoration: none; margin-bottom: 20px; display: inline-block; }
        .back-link:hover { text-decoration: underline; }
        .benefits { text-align: left; margin: 20px 0; }
        .benefits ul { padding-left: 20px; }
        .benefits li { margin-bottom: 8px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📧 Newsletter Signup</h1>
        <p>Stay updated with our latest products and offers</p>
    </div>
    
    <div class="container">
        <a href="/store" class="back-link">← Back to Store</a>
        
        <div class="signup-form">
            <h2>Join Our Newsletter</h2>
            
            <div class="benefits">
                <h3>What you'll get:</h3>
                <ul>
                    <li>✨ Exclusive product launches</li>
                    <li>🎯 Special offers and discounts</li>
                    <li>📦 Order updates and tracking</li>
                    <li>💡 Product recommendations</li>
                    <li>🎉 Seasonal promotions</li>
                </ul>
            </div>
            
            <form id="newsletterForm">
                <div class="form-group">
                    <label>Email Address *</label>
                    <input type="email" name="email" required placeholder="your@email.com">
                </div>
                <div class="form-group">
                    <label>Full Name</label>
                    <input type="text" name="name" placeholder="Your full name">
                </div>
                <div class="form-group">
                    <label>Phone Number</label>
                    <input type="tel" name="phone" placeholder="Your phone number">
                </div>
                <div class="form-group">
                    <label>WhatsApp Number</label>
                    <input type="tel" name="whatsapp_number" placeholder="Your WhatsApp number">
                </div>
                
                <button type="submit" class="btn">Subscribe to Newsletter</button>
            </form>
            
            <p style="margin-top: 20px; font-size: 0.9em; color: #666;">
                We respect your privacy. You can unsubscribe at any time.
            </p>
        </div>
    </div>
    
    <script>
        document.getElementById('newsletterForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const subscriptionData = {
                email: formData.get('email'),
                name: formData.get('name'),
                phone: formData.get('phone'),
                whatsapp_number: formData.get('whatsapp_number')
            };
            
            fetch('/api/orders/newsletter/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(subscriptionData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Successfully subscribed to newsletter! Thank you for joining us.');
                    this.reset();
                } else {
                    alert('Error: ' + data.error);
                }
            })
            .catch(error => {
                alert('Error subscribing: ' + error);
            });
        });
    </script>
</body>
</html>
"""