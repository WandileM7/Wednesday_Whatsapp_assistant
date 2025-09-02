# E-commerce Platform Features

This document describes the comprehensive e-commerce functionality added to the Wednesday WhatsApp Assistant.

## 🛍️ Features Overview

### ✅ Implemented Features

1. **Admin Dashboard with Login System**
   - Secure admin authentication
   - Order tracking and management
   - Product management
   - Customer management
   - Newsletter management
   - Export functionality for financial tracking

2. **PAXI API Integration**
   - Real PAXI delivery API integration
   - Pickup point selection
   - Shipping cost calculation
   - Delivery tracking
   - Mock mode for testing without API keys

3. **Order Management API**
   - Complete order processing
   - Email notifications to customers
   - WhatsApp notifications via existing WAHA system
   - Order status tracking
   - Order acceptance workflow

4. **Customer Review System**
   - Product reviews with ratings (1-5 stars)
   - Comment system
   - Reviews display on product pages
   - Persistent storage through deployments

5. **Newsletter System**
   - Easy subscriber management
   - Admin newsletter sending
   - Customer signup from storefront
   - Contact information collection

6. **Customer Storefront**
   - Product catalog with search/filtering
   - Shopping cart functionality
   - Checkout with PAXI integration
   - Newsletter signup
   - Product reviews

## 🚀 Quick Start

### 1. Initial Setup
```bash
# Run the setup script
python3 setup_ecommerce.py

# Follow prompts to create admin user and sample products
```

### 2. Start the Application
```bash
python3 main.py
```

### 3. Access Points
- **Storefront**: http://localhost:5000/store
- **Admin Dashboard**: http://localhost:5000/admin/login
- **API Documentation**: See API Endpoints section below

## 🔧 Configuration

### Environment Variables

Copy and update the `.env` file with your production settings:

```bash
# PAXI API Configuration
PAXI_API_KEY=your_paxi_api_key_here
PAXI_MERCHANT_ID=your_paxi_merchant_id_here
PAXI_BASE_URL=https://api.paxi.co.za/v1

# Email Configuration
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password_here
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
FROM_EMAIL=noreply@your-domain.com
```

### PAXI API Setup
1. Register at [PAXI Developer Portal](https://developer.paxi.co.za)
2. Obtain API key and merchant ID
3. Update environment variables
4. Test with small orders first

### Email Setup (Gmail)
1. Enable 2-factor authentication on Gmail
2. Generate an app password: Google Account → Security → App passwords
3. Use your Gmail address as `EMAIL_USER`
4. Use the app password as `EMAIL_PASSWORD`

## 📱 API Endpoints

### Store/Products API
- `GET /api/products` - Get all products
- `GET /api/store/status` - Get store status

### Orders API
- `POST /api/orders/create` - Create new order
- `GET /api/orders/track/<order_number>` - Track order
- `POST /api/orders/accept/<order_number>` - Accept order (admin)
- `GET /api/orders/delivery-options` - Get PAXI pickup points
- `GET /api/orders/calculate-shipping` - Calculate shipping cost

### Reviews API
- `POST /api/orders/reviews/add` - Add product review
- `GET /api/orders/reviews/<product_id>` - Get product reviews

### Newsletter API
- `POST /api/orders/newsletter/subscribe` - Subscribe to newsletter

### Admin Routes
- `/admin/login` - Admin login
- `/admin/dashboard` - Main dashboard
- `/admin/orders` - Order management
- `/admin/products` - Product management
- `/admin/customers` - Customer management
- `/admin/newsletter` - Newsletter management
- `/admin/export/orders` - Export orders to CSV

### Storefront Routes
- `/store` - Main storefront
- `/store/product/<id>` - Product detail page
- `/store/checkout` - Checkout page
- `/store/newsletter-signup` - Newsletter signup

## 📊 Database Schema

The e-commerce platform uses SQLite with the following tables:

- **products** - Product catalog
- **customers** - Customer information
- **orders** - Order records
- **order_items** - Order line items
- **reviews** - Product reviews
- **newsletter_subscribers** - Newsletter subscribers
- **newsletter_campaigns** - Campaign history
- **admin_users** - Admin authentication

## 🔄 Order Workflow

1. **Customer Places Order** (`/store/checkout`)
   - Selects products and quantities
   - Chooses PAXI pickup point
   - Provides contact details
   - Submits order

2. **Order Processing** (`/api/orders/create`)
   - Creates customer record (if new)
   - Calculates total with delivery costs
   - Creates PAXI delivery
   - Sends confirmation notifications

3. **Admin Management** (`/admin/orders`)
   - Views all orders
   - Updates order status
   - Manages PAXI tracking
   - Accepts/rejects orders

4. **Customer Notifications**
   - Email confirmations (if configured)
   - WhatsApp notifications
   - Order acceptance notifications
   - Delivery updates

## 📧 Notification System

### Email Notifications
- Order confirmations
- Order acceptance notifications  
- Newsletter campaigns
- Requires Gmail/SMTP configuration

### WhatsApp Notifications
- Uses existing WAHA system
- Order confirmations
- Status updates
- Works with current WhatsApp integration

## 💰 Financial Tracking

### Export Features
- CSV export of all orders
- Customer export for analysis
- Includes all order details, amounts, dates
- Accessible from admin dashboard

### Order Data Includes
- Order numbers and dates
- Customer contact information
- Product details and quantities
- Payment amounts
- Delivery information
- PAXI tracking numbers

## 🛡️ Security Features

- Admin authentication with hashed passwords
- Session management
- Input validation on all forms
- SQL injection protection
- CSRF protection through Flask

## 🧪 Testing

### Manual Testing
The platform includes extensive manual testing capabilities:

```bash
# Test store status
curl http://localhost:5000/api/store/status

# Test PAXI integration
curl "http://localhost:5000/api/orders/delivery-options?city=Johannesburg"

# Test shipping calculation
curl "http://localhost:5000/api/orders/calculate-shipping?pickup_point_id=JHB001&weight=2.0"
```

### Mock Data
- PAXI API returns mock data when not configured
- Sample products included in setup
- Fallback modes for all external services

## 🚀 Production Deployment

### Render Deployment
The application is ready for Render deployment with existing `render.yaml`:

1. Configure environment variables in Render dashboard
2. Set up PAXI API credentials
3. Configure email settings
4. Deploy and test

### Database Persistence
- SQLite database file (`ecommerce.db`) persists data
- Automatic initialization on startup
- Backup/restore via file copy

## 📈 Features Not Included (Future Enhancements)

- Payment gateway integration
- Advanced inventory management
- Multi-vendor support
- Advanced analytics dashboard
- Mobile app
- Real-time order tracking
- Automated marketing campaigns

## 🆘 Troubleshooting

### Common Issues

1. **Email not sending**
   - Check EMAIL_USER and EMAIL_PASSWORD
   - Verify Gmail app password setup
   - Check SMTP settings

2. **PAXI API errors**
   - Verify API key and merchant ID
   - Check rate limits
   - Test with mock mode first

3. **WhatsApp notifications not working**
   - Ensure WAHA service is running
   - Check WAHA_URL configuration
   - Verify phone number format

4. **Database errors**
   - Check file permissions
   - Verify SQLite installation
   - Check disk space

### Debug Mode
Enable debug logging by setting `FLASK_DEBUG=true` in .env file.

## 📝 License

This e-commerce platform extension maintains the same license as the base Wednesday Assistant project.

## 👥 Support

For issues and questions:
1. Check this documentation first
2. Review error logs
3. Test with mock/sample data
4. Create GitHub issue with details

---

**Built with ❤️ for the Wednesday Assistant ecosystem**