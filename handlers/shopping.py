"""
Shopping Cart and Order Management for WhatsApp Assistant

Provides shopping cart functionality with Paxi delivery integration.
Manages orders from creation through checkout to WhatsApp notifications.
"""

import os
import json
import logging
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from handlers.paxi import paxi_service

logger = logging.getLogger(__name__)

class ShoppingCart:
    """Individual shopping cart for a user session"""
    
    def __init__(self, user_id: str = None):
        self.user_id = user_id or str(uuid.uuid4())
        self.items = []
        self.created_at = datetime.now()
        self.delivery_info = {}
        self.total_amount = 0.0
    
    def add_item(self, item: Dict) -> str:
        """Add an item to the cart"""
        try:
            required_fields = ["name", "price"]
            for field in required_fields:
                if field not in item:
                    return f"❌ Missing required field: {field}"
            
            # Generate item ID if not provided
            if "id" not in item:
                item["id"] = str(uuid.uuid4())[:8]
            
            # Set default quantity
            if "quantity" not in item:
                item["quantity"] = 1
            
            # Add timestamp
            item["added_at"] = datetime.now().isoformat()
            
            self.items.append(item)
            self._update_total()
            
            return f"✅ Added {item['name']} to cart (R{item['price']:.2f})"
            
        except Exception as e:
            logger.error(f"Error adding item to cart: {e}")
            return f"❌ Error adding item: {str(e)}"
    
    def remove_item(self, item_id: str) -> str:
        """Remove an item from the cart"""
        try:
            for i, item in enumerate(self.items):
                if item.get("id") == item_id:
                    removed_item = self.items.pop(i)
                    self._update_total()
                    return f"✅ Removed {removed_item['name']} from cart"
            
            return f"❌ Item with ID {item_id} not found in cart"
            
        except Exception as e:
            logger.error(f"Error removing item from cart: {e}")
            return f"❌ Error removing item: {str(e)}"
    
    def update_quantity(self, item_id: str, quantity: int) -> str:
        """Update the quantity of an item in the cart"""
        try:
            if quantity <= 0:
                return self.remove_item(item_id)
            
            for item in self.items:
                if item.get("id") == item_id:
                    old_qty = item["quantity"]
                    item["quantity"] = quantity
                    self._update_total()
                    return f"✅ Updated {item['name']} quantity from {old_qty} to {quantity}"
            
            return f"❌ Item with ID {item_id} not found in cart"
            
        except Exception as e:
            logger.error(f"Error updating item quantity: {e}")
            return f"❌ Error updating quantity: {str(e)}"
    
    def clear_cart(self) -> str:
        """Clear all items from the cart"""
        item_count = len(self.items)
        self.items = []
        self.total_amount = 0.0
        return f"🗑️ Cleared {item_count} items from cart"
    
    def _update_total(self):
        """Recalculate cart total"""
        self.total_amount = sum(item["price"] * item["quantity"] for item in self.items)
    
    def get_summary(self) -> str:
        """Get cart summary"""
        if not self.items:
            return "🛒 Your cart is empty"
        
        response = f"🛒 Shopping Cart ({len(self.items)} items):\n"
        response += "=" * 30 + "\n\n"
        
        for item in self.items:
            response += f"📦 {item['name']}\n"
            response += f"   💰 R{item['price']:.2f} x {item['quantity']} = R{item['price'] * item['quantity']:.2f}\n"
            if item.get("description"):
                response += f"   📝 {item['description']}\n"
            response += "\n"
        
        response += f"💳 **Total: R{self.total_amount:.2f}**\n"
        
        return response.strip()
    
    def set_delivery_info(self, delivery_type: str, delivery_details: Dict) -> str:
        """Set delivery information for the cart"""
        self.delivery_info = {
            "type": delivery_type,
            "details": delivery_details,
            "updated_at": datetime.now().isoformat()
        }
        return f"✅ Delivery set to: {delivery_type}"


class OrderManager:
    """Manages orders and shopping carts"""
    
    def __init__(self):
        self.carts = {}  # user_id -> ShoppingCart
        self.orders = {}  # order_id -> Order
        self.order_file = "orders.json"
        self._load_orders()
    
    def _load_orders(self):
        """Load orders from file"""
        try:
            if os.path.exists(self.order_file):
                with open(self.order_file, 'r') as f:
                    self.orders = json.load(f)
        except Exception as e:
            logger.error(f"Error loading orders: {e}")
            self.orders = {}
    
    def _save_orders(self):
        """Save orders to file"""
        try:
            with open(self.order_file, 'w') as f:
                json.dump(self.orders, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving orders: {e}")
    
    def get_or_create_cart(self, user_id: str) -> ShoppingCart:
        """Get existing cart or create new one for user"""
        if user_id not in self.carts:
            self.carts[user_id] = ShoppingCart(user_id)
        return self.carts[user_id]
    
    def add_to_cart(self, user_id: str, item: Dict) -> str:
        """Add item to user's cart"""
        cart = self.get_or_create_cart(user_id)
        return cart.add_item(item)
    
    def view_cart(self, user_id: str) -> str:
        """View user's cart"""
        cart = self.get_or_create_cart(user_id)
        return cart.get_summary()
    
    def clear_cart(self, user_id: str) -> str:
        """Clear user's cart"""
        cart = self.get_or_create_cart(user_id)
        return cart.clear_cart()
    
    def checkout_with_paxi(self, user_id: str, pickup_point_id: str, customer_details: Dict) -> Dict:
        """Checkout cart with Paxi delivery"""
        try:
            cart = self.get_or_create_cart(user_id)
            
            if not cart.items:
                return {"error": "Cart is empty"}
            
            # Get pickup point details
            pickup_point = paxi_service.get_pickup_point_details(pickup_point_id)
            if "error" in pickup_point:
                return {"error": f"Invalid pickup point: {pickup_point['error']}"}
            
            # Calculate delivery cost
            delivery_cost = paxi_service.calculate_delivery_cost(pickup_point_id, "medium")
            
            # Create order
            order_id = f"WA{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            order_data = {
                "order_id": order_id,
                "user_id": user_id,
                "items": cart.items,
                "subtotal": cart.total_amount,
                "delivery_cost": delivery_cost.get("cost", 25.00),
                "total": cart.total_amount + delivery_cost.get("cost", 25.00),
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "delivery": {
                    "type": "paxi_pickup",
                    "pickup_point": pickup_point,
                    "customer": customer_details
                }
            }
            
            # Create Paxi delivery order
            paxi_order_details = {
                "pickup_point_id": pickup_point_id,
                "recipient_name": customer_details.get("name", ""),
                "recipient_phone": customer_details.get("phone", ""),
                "recipient_email": customer_details.get("email", ""),
                "package_size": "medium",
                "package_description": f"Order {order_id} - {len(cart.items)} items",
                "package_value": cart.total_amount,
                "order_reference": order_id
            }
            
            paxi_response = paxi_service.create_delivery_order(paxi_order_details)
            
            if "error" in paxi_response:
                return {"error": f"Paxi order failed: {paxi_response['error']}"}
            
            # Add Paxi tracking info to order
            order_data["paxi"] = {
                "tracking_number": paxi_response.get("tracking_number"),
                "status": paxi_response.get("status"),
                "estimated_delivery": paxi_response.get("estimated_delivery")
            }
            
            # Save order
            self.orders[order_id] = order_data
            self._save_orders()
            
            # Clear cart
            cart.clear_cart()
            
            return {
                "success": True,
                "order": order_data,
                "paxi_tracking": paxi_response.get("tracking_number"),
                "pickup_point": pickup_point
            }
            
        except Exception as e:
            logger.error(f"Error during checkout: {e}")
            return {"error": f"Checkout failed: {str(e)}"}
    
    def get_order(self, order_id: str) -> Dict:
        """Get order details"""
        return self.orders.get(order_id, {"error": "Order not found"})
    
    def list_user_orders(self, user_id: str) -> List[Dict]:
        """List all orders for a user"""
        user_orders = []
        for order in self.orders.values():
            if order.get("user_id") == user_id:
                user_orders.append(order)
        return sorted(user_orders, key=lambda x: x.get("created_at", ""), reverse=True)
    
    def format_order_for_whatsapp(self, order_data: Dict) -> str:
        """Format order details for WhatsApp message"""
        try:
            order_id = order_data["order_id"]
            items = order_data["items"]
            total = order_data["total"]
            delivery = order_data["delivery"]
            paxi = order_data.get("paxi", {})
            
            message = f"🛍️ **ORDER CONFIRMATION**\n"
            message += f"📋 Order #: {order_id}\n"
            message += f"📅 Date: {datetime.fromisoformat(order_data['created_at']).strftime('%d %b %Y %H:%M')}\n\n"
            
            message += "📦 **ITEMS ORDERED:**\n"
            for item in items:
                message += f"• {item['name']} x{item['quantity']} - R{item['price'] * item['quantity']:.2f}\n"
            
            message += f"\n💰 Subtotal: R{order_data['subtotal']:.2f}\n"
            message += f"🚚 Delivery: R{order_data['delivery_cost']:.2f}\n"
            message += f"💳 **TOTAL: R{total:.2f}**\n\n"
            
            # Paxi delivery details
            message += "🚚 **DELIVERY DETAILS:**\n"
            message += f"📦 Type: Paxi Pickup Point\n"
            
            if paxi.get("tracking_number"):
                message += f"📋 Paxi Number: {paxi['tracking_number']}\n"
            
            pickup_point = delivery.get("pickup_point", {})
            
            # Handle case where pickup_point might contain a 'pickup_points' list
            if "pickup_points" in pickup_point:
                # Extract the first pickup point from the list
                pickup_points_list = pickup_point["pickup_points"]
                if pickup_points_list:
                    pickup_point = pickup_points_list[0]  # Use the first one
                else:
                    pickup_point = {}
            
            if pickup_point and pickup_point.get("name"):
                message += f"📍 Pickup Location: {pickup_point['name']}\n"
                message += f"📍 Address: {pickup_point['address']}\n"
                message += f"📞 Phone: {pickup_point.get('phone', 'N/A')}\n"
                message += f"🕒 Hours: {pickup_point.get('hours', 'Contact store')}\n"
            
            if paxi.get("estimated_delivery"):
                message += f"📅 Est. Ready for Collection: {paxi['estimated_delivery']}\n"
            
            message += "\n📱 You'll receive an SMS when your order is ready for collection.\n"
            message += "🆔 Please bring ID and this message when collecting.\n\n"
            message += "Thank you for your order! 🙏"
            
            return message
            
        except Exception as e:
            logger.error(f"Error formatting order for WhatsApp: {e}")
            return f"✅ Order {order_data.get('order_id', 'unknown')} confirmed!\n\n📋 Paxi Number: {order_data.get('paxi', {}).get('tracking_number', 'N/A')}\n📍 Pickup Point: {order_data.get('delivery', {}).get('pickup_point', {}).get('name', 'See order details')}\n💳 Total: R{order_data.get('total', 0):.2f}\n\nCheck your order confirmation for full details."


# Global order manager instance
order_manager = OrderManager()