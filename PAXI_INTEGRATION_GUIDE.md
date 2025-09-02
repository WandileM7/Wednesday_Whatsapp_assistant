# Paxi Integration for WhatsApp Orders - Testing Guide

## Overview
The WhatsApp assistant now includes Paxi integration for South African delivery services. Users can add items to a shopping cart, select Paxi pickup points, and checkout with automatic WhatsApp order confirmations that include Paxi tracking details.

## New Features Added

### 1. Shopping Cart Management
- Add items to cart with AI conversation or API
- View cart contents
- Clear cart

### 2. Paxi Pickup Point Services
- Find pickup points by location
- Get pickup point details (address, hours, phone)
- Calculate delivery costs

### 3. Checkout with Paxi Integration
- Complete checkout flow with Paxi delivery
- Generate Paxi tracking numbers
- Send formatted WhatsApp order confirmations

### 4. Delivery Options
- Paxi pickup points (R25-R50, 1-3 days)
- Home delivery (R50-R100, 1-2 days) 
- Office delivery (R45-R80, 1-2 days)

## API Endpoints

### Shopping Cart
- `GET /shopping/cart?user_id=<id>` - View cart
- `POST /shopping/cart/add` - Add item to cart
- `POST /shopping/cart/clear` - Clear cart

### Paxi Services
- `GET /paxi/pickup-points?location=<location>&city=<city>` - Find pickup points
- `GET /paxi/delivery-options` - Get delivery options
- `GET /paxi/track?tracking_number=<number>` - Track delivery
- `POST /checkout/paxi` - Checkout with Paxi

### Testing
- `GET /test-paxi-integration` - Test all Paxi functionality

## Conversational AI Integration

Users can now interact via WhatsApp messages like:
- "Add Samsung Galaxy Watch to my cart for R2500"
- "Show me my shopping cart"
- "Find Paxi pickup points near me in Cape Town"
- "Checkout my cart using Paxi pickup point CPT001, my name is John Doe and phone is 27812345678"

## WhatsApp Order Format

When an order is placed, the system sends a formatted WhatsApp message including:

```
🛍️ **ORDER CONFIRMATION**
📋 Order #: WA20250902120541
📅 Date: 02 Sep 2025 12:05

📦 **ITEMS ORDERED:**
• Samsung Galaxy Earbuds x1 - R1299.00

💰 Subtotal: R1299.00
🚚 Delivery: R25.00
💳 **TOTAL: R1324.00**

🚚 **DELIVERY DETAILS:**
📦 Type: Paxi Pickup Point
📋 Paxi Number: PX202509020126
📍 Pickup Location: Pick n Pay - Claremont
📍 Address: Cavendish Square, Claremont, Cape Town
📞 Phone: +27 21 674 4000
🕒 Hours: Mon-Fri: 8:00-20:00, Sat: 8:00-18:00, Sun: 9:00-17:00
📅 Est. Ready for Collection: 2025-09-04

📱 You'll receive an SMS when your order is ready for collection.
🆔 Please bring ID and this message when collecting.

Thank you for your order! 🙏
```

## Configuration

Add to `.env` file:
```
PAXI_API_KEY=your_paxi_api_key
PAXI_BASE_URL=https://api.paxi.com/v1
PAXI_PARTNER_ID=your_partner_id
```

## Mock Data
When PAXI_API_KEY is not set or set to "test_paxi_key", the system uses mock data for testing:
- 3 sample pickup points (Cape Town, Johannesburg)
- Mock tracking numbers
- Test delivery costs and times

## Files Created/Modified

### New Files:
- `handlers/paxi.py` - Paxi API integration service
- `handlers/shopping.py` - Shopping cart and order management
- `PAXI_INTEGRATION_GUIDE.md` - This guide

### Modified Files:
- `handlers/gemini.py` - Added shopping/Paxi AI functions
- `config.py` - Added Paxi configuration variables
- `main.py` - Added shopping and Paxi API endpoints
- `.env` - Added Paxi configuration

## Testing Examples

### 1. Test Paxi Integration
```bash
curl http://localhost:5000/test-paxi-integration
```

### 2. Add Item to Cart
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"name": "Samsung Galaxy Earbuds", "price": 1299.00, "quantity": 1}' \
  http://localhost:5000/shopping/cart/add
```

### 3. View Cart
```bash
curl http://localhost:5000/shopping/cart
```

### 4. Find Pickup Points
```bash
curl "http://localhost:5000/paxi/pickup-points?city=Cape Town"
```

### 5. Complete Checkout
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"pickup_point_id": "CPT001", "customer_name": "John Doe", "customer_phone": "27812345678"}' \
  http://localhost:5000/checkout/paxi
```

### 6. AI Conversation
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"payload": {"chatId": "27812345678@c.us", "body": "Add iPhone 15 to cart for R15000", "fromMe": false, "type": "text"}}' \
  http://localhost:5000/webhook
```

## Production Deployment

1. Sign up for Paxi developer account
2. Obtain API credentials
3. Set real PAXI_API_KEY in environment
4. Configure PAXI_PARTNER_ID if applicable
5. Test with real pickup points and orders

The system gracefully falls back to mock data when API credentials are not available, making it safe for development and testing.