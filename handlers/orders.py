"""
Order processing API with email and WhatsApp notifications
"""
import os
import json
import smtplib
import requests
from datetime import datetime
from typing import Dict
try:
    from email.mime.text import MimeText
    from email.mime.multipart import MimeMultipart
except ImportError:
    # Fallback for systems where email.mime might not be fully available
    MimeText = None
    MimeMultipart = None
from flask import Blueprint, request, jsonify
from models import Order, Customer, Product, Review, NewsletterSubscriber
from handlers.paxi import create_order_delivery, get_delivery_options, calculate_shipping_cost
import logging

logger = logging.getLogger(__name__)

# Create blueprint for order API
order_bp = Blueprint('orders', __name__, url_prefix='/api/orders')

class NotificationService:
    """Service for sending email and WhatsApp notifications"""
    
    def __init__(self):
        # Email configuration
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.email_user = os.getenv('EMAIL_USER', '')
        self.email_password = os.getenv('EMAIL_PASSWORD', '')
        self.from_email = os.getenv('FROM_EMAIL', self.email_user)
        
        # WhatsApp configuration (using existing WAHA setup)
        self.waha_url = os.getenv('WAHA_URL', 'http://localhost:3000/api/sendText')
        
    def send_email(self, to_email: str, subject: str, body: str, html_body: str = "") -> bool:
        """Send email notification"""
        try:
            if not self.email_user or not self.email_password:
                logger.warning("Email not configured, skipping email notification")
                return False
            
            if MimeText is None or MimeMultipart is None:
                logger.warning("Email MIME modules not available, skipping email notification")
                return False
            
            msg = MimeMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # Add text part
            text_part = MimeText(body, 'plain')
            msg.attach(text_part)
            
            # Add HTML part if provided
            if html_body:
                html_part = MimeText(html_body, 'html')
                msg.attach(html_part)
            
            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.email_user, self.email_password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def send_whatsapp(self, phone_number: str, message: str) -> bool:
        """Send WhatsApp notification"""
        try:
            # Format phone number (ensure it starts with country code)
            if not phone_number.startswith('+'):
                phone_number = '+27' + phone_number.lstrip('0')
            
            # Format for WhatsApp API (remove + and add @c.us)
            whatsapp_id = phone_number.replace('+', '') + '@c.us'
            
            payload = {
                'chatId': whatsapp_id,
                'text': message
            }
            
            response = requests.post(
                self.waha_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"WhatsApp message sent successfully to {phone_number}")
                return True
            else:
                logger.warning(f"WhatsApp API returned status {response.status_code} for {phone_number}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message to {phone_number}: {e}")
            return False

# Global notification service
notification_service = NotificationService()

@order_bp.route('/create', methods=['POST'])
def create_order():
    """Create a new order"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['customer_name', 'customer_phone', 'items', 'pickup_point_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        # Get or create customer
        customer = Customer.get_by_phone(data['customer_phone'])
        if not customer:
            customer_id = Customer.create(
                name=data['customer_name'],
                phone=data['customer_phone'],
                email=data.get('customer_email', ''),
                whatsapp_number=data.get('customer_whatsapp', data['customer_phone']),
                address=data.get('delivery_address', ''),
                city=data.get('delivery_city', ''),
                postal_code=data.get('delivery_postal_code', '')
            )
        else:
            customer_id = customer['id']
        
        # Calculate total amount
        total_amount = 0
        for item in data['items']:
            product = Product.get_by_id(item['product_id'])
            if not product:
                return jsonify({'success': False, 'error': f'Product {item["product_id"]} not found'}), 404
            
            total_amount += product['price'] * item['quantity']
        
        # Calculate delivery cost
        total_weight = sum(item.get('weight', 1.0) * item['quantity'] for item in data['items'])
        delivery_cost = calculate_shipping_cost(data['pickup_point_id'], total_weight)
        
        if delivery_cost.get('success'):
            total_amount += delivery_cost.get('cost', 0)
        
        # Create order
        order_number = Order.create(
            customer_id=customer_id,
            total_amount=total_amount,
            delivery_address=data.get('delivery_address', ''),
            delivery_city=data.get('delivery_city', ''),
            delivery_postal_code=data.get('delivery_postal_code', ''),
            notes=data.get('notes', '')
        )
        
        # Add order items
        for item in data['items']:
            product = Product.get_by_id(item['product_id'])
            Order.add_item(
                order_number=order_number,
                product_id=item['product_id'],
                quantity=item['quantity'],
                unit_price=product['price']
            )
            
            # Update product stock
            new_stock = max(0, product['stock_quantity'] - item['quantity'])
            Product.update_stock(item['product_id'], new_stock)
        
        # Create PAXI delivery
        customer_data = Customer.get_by_phone(data['customer_phone']) or {}
        customer_data['total_amount'] = total_amount
        customer_data['weight'] = total_weight
        
        delivery_result = create_order_delivery(order_number, customer_data, data['pickup_point_id'])
        
        # Update order with PAXI tracking if successful
        if delivery_result.get('success'):
            Order.update_status(order_number, 'processing', delivery_result.get('tracking_number', ''))
        
        # Send notifications
        send_order_notifications(order_number, customer_data, data.get('pickup_point_id'))
        
        return jsonify({
            'success': True,
            'order_number': order_number,
            'total_amount': total_amount,
            'delivery_cost': delivery_cost.get('cost', 0),
            'tracking_number': delivery_result.get('tracking_number'),
            'estimated_delivery': delivery_result.get('estimated_delivery')
        })
        
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@order_bp.route('/track/<order_number>')
def track_order(order_number):
    """Track an order"""
    try:
        # Get order from database
        orders = Order.get_all()
        order = next((o for o in orders if o['order_number'] == order_number), None)
        
        if not order:
            return jsonify({'success': False, 'error': 'Order not found'}), 404
        
        # Get PAXI tracking if available
        paxi_tracking = None
        if order.get('paxi_tracking_number'):
            from handlers.paxi import track_order_delivery
            paxi_tracking = track_order_delivery(order['paxi_tracking_number'])
        
        return jsonify({
            'success': True,
            'order': {
                'order_number': order['order_number'],
                'status': order['status'],
                'total_amount': order['total_amount'],
                'created_at': order['created_at'],
                'customer_name': order['customer_name'],
                'paxi_tracking': order.get('paxi_tracking_number'),
                'delivery_status': paxi_tracking
            }
        })
        
    except Exception as e:
        logger.error(f"Error tracking order {order_number}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@order_bp.route('/delivery-options')
def get_order_delivery_options():
    """Get delivery options for checkout"""
    try:
        city = request.args.get('city', '')
        postal_code = request.args.get('postal_code', '')
        
        options = get_delivery_options(city, postal_code)
        
        return jsonify(options)
        
    except Exception as e:
        logger.error(f"Error getting delivery options: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@order_bp.route('/calculate-shipping')
def calculate_order_shipping():
    """Calculate shipping cost for checkout"""
    try:
        pickup_point_id = request.args.get('pickup_point_id')
        weight = float(request.args.get('weight', 1.0))
        
        if not pickup_point_id:
            return jsonify({'success': False, 'error': 'pickup_point_id required'}), 400
        
        cost = calculate_shipping_cost(pickup_point_id, weight)
        
        return jsonify(cost)
        
    except Exception as e:
        logger.error(f"Error calculating shipping: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@order_bp.route('/accept/<order_number>', methods=['POST'])
def accept_order(order_number):
    """Accept an order and send notifications (for admin use)"""
    try:
        # Get order details
        orders = Order.get_all()
        order = next((o for o in orders if o['order_number'] == order_number), None)
        
        if not order:
            return jsonify({'success': False, 'error': 'Order not found'}), 404
        
        # Update order status
        Order.update_status(order_number, 'accepted')
        
        # Get customer details
        customer = Customer.get_by_phone(order['customer_phone'])
        
        # Send acceptance notifications
        send_order_acceptance_notifications(order, customer)
        
        return jsonify({
            'success': True,
            'message': 'Order accepted and notifications sent'
        })
        
    except Exception as e:
        logger.error(f"Error accepting order {order_number}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@order_bp.route('/newsletter/subscribe', methods=['POST'])
def subscribe_newsletter():
    """Subscribe to newsletter"""
    try:
        data = request.get_json()
        
        email = data.get('email')
        if not email:
            return jsonify({'success': False, 'error': 'Email required'}), 400
        
        subscriber_id = NewsletterSubscriber.subscribe(
            email=email,
            name=data.get('name', ''),
            phone=data.get('phone', ''),
            whatsapp_number=data.get('whatsapp_number', '')
        )
        
        if subscriber_id == -1:
            return jsonify({'success': False, 'error': 'Email already subscribed'}), 409
        
        return jsonify({
            'success': True,
            'message': 'Successfully subscribed to newsletter',
            'subscriber_id': subscriber_id
        })
        
    except Exception as e:
        logger.error(f"Error subscribing to newsletter: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@order_bp.route('/reviews/add', methods=['POST'])
def add_review():
    """Add a product review"""
    try:
        data = request.get_json()
        
        required_fields = ['product_id', 'customer_phone', 'rating']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        # Get customer
        customer = Customer.get_by_phone(data['customer_phone'])
        if not customer:
            return jsonify({'success': False, 'error': 'Customer not found'}), 404
        
        # Validate rating
        rating = int(data['rating'])
        if rating < 1 or rating > 5:
            return jsonify({'success': False, 'error': 'Rating must be between 1 and 5'}), 400
        
        # Create review
        review_id = Review.create(
            product_id=data['product_id'],
            customer_id=customer['id'],
            rating=rating,
            comment=data.get('comment', '')
        )
        
        return jsonify({
            'success': True,
            'review_id': review_id,
            'message': 'Review added successfully'
        })
        
    except Exception as e:
        logger.error(f"Error adding review: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@order_bp.route('/reviews/<int:product_id>')
def get_product_reviews(product_id):
    """Get reviews for a product"""
    try:
        reviews = Review.get_by_product(product_id)
        
        return jsonify({
            'success': True,
            'reviews': reviews,
            'count': len(reviews)
        })
        
    except Exception as e:
        logger.error(f"Error getting reviews for product {product_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def send_order_notifications(order_number: str, customer_data: Dict, pickup_point_id: str):
    """Send order confirmation notifications"""
    try:
        # Email notification
        if customer_data.get('email'):
            subject = f"Order Confirmation - {order_number}"
            body = f"""
Thank you for your order!

Order Number: {order_number}
Total Amount: R{customer_data.get('total_amount', 0):.2f}

Your order has been received and is being processed.
You will receive tracking information once your order is shipped.

Thank you for shopping with us!

Best regards,
Wednesday Assistant Store
            """
            
            html_body = f"""
<html>
<body>
    <h2>Order Confirmation</h2>
    <p>Thank you for your order!</p>
    
    <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
        <strong>Order Number:</strong> {order_number}<br>
        <strong>Total Amount:</strong> R{customer_data.get('total_amount', 0):.2f}
    </div>
    
    <p>Your order has been received and is being processed.</p>
    <p>You will receive tracking information once your order is shipped.</p>
    
    <p>Thank you for shopping with us!</p>
    
    <p>Best regards,<br>Wednesday Assistant Store</p>
</body>
</html>
            """
            
            notification_service.send_email(customer_data['email'], subject, body, html_body)
        
        # WhatsApp notification
        phone = customer_data.get('whatsapp_number') or customer_data.get('phone')
        if phone:
            whatsapp_message = f"""
🛍️ *Order Confirmation*

Thank you for your order!

📋 Order Number: *{order_number}*
💰 Total Amount: *R{customer_data.get('total_amount', 0):.2f}*

✅ Your order has been received and is being processed.
📦 You will receive tracking information once your order is shipped.

Thank you for shopping with us! 🙏

_Wednesday Assistant Store_
            """
            
            notification_service.send_whatsapp(phone, whatsapp_message)
        
        logger.info(f"Order notifications sent for {order_number}")
        
    except Exception as e:
        logger.error(f"Error sending order notifications: {e}")

def send_order_acceptance_notifications(order: Dict, customer: Dict):
    """Send order acceptance notifications"""
    try:
        order_number = order['order_number']
        
        # Email notification
        if customer.get('email'):
            subject = f"Order Accepted - {order_number}"
            body = f"""
Great news! Your order has been accepted.

Order Number: {order_number}
Status: Accepted
Total Amount: R{order.get('total_amount', 0):.2f}

Your order is now being prepared for shipment.
You will receive tracking information shortly.

Best regards,
Wednesday Assistant Store
            """
            
            notification_service.send_email(customer['email'], subject, body)
        
        # WhatsApp notification
        phone = customer.get('whatsapp_number') or customer.get('phone')
        if phone:
            whatsapp_message = f"""
🎉 *Order Accepted!*

Great news! Your order has been accepted.

📋 Order Number: *{order_number}*
✅ Status: *Accepted*
💰 Total Amount: *R{order.get('total_amount', 0):.2f}*

📦 Your order is now being prepared for shipment.
🚚 You will receive tracking information shortly.

Thank you for your patience! 🙏

_Wednesday Assistant Store_
            """
            
            notification_service.send_whatsapp(phone, whatsapp_message)
        
        logger.info(f"Order acceptance notifications sent for {order_number}")
        
    except Exception as e:
        logger.error(f"Error sending order acceptance notifications: {e}")

def get_notification_service_status() -> Dict:
    """Get notification service status for admin dashboard"""
    return {
        'email_configured': bool(notification_service.email_user and notification_service.email_password),
        'whatsapp_configured': bool(notification_service.waha_url),
        'smtp_server': notification_service.smtp_server,
        'from_email': notification_service.from_email
    }