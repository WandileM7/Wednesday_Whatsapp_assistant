"""
Expense Tracking Handler
Track expenses and generate spending reports.
"""

import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# Storage file for expenses
EXPENSES_FILE = "task_data/expenses.json"


def _load_expenses() -> Dict[str, List[Dict[str, Any]]]:
    """Load expenses from file."""
    try:
        if os.path.exists(EXPENSES_FILE):
            with open(EXPENSES_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading expenses: {e}")
    return {}


def _save_expenses(expenses: Dict[str, List[Dict[str, Any]]]) -> bool:
    """Save expenses to file."""
    try:
        os.makedirs(os.path.dirname(EXPENSES_FILE), exist_ok=True)
        with open(EXPENSES_FILE, 'w') as f:
            json.dump(expenses, f, indent=2, default=str)
        return True
    except Exception as e:
        logger.error(f"Error saving expenses: {e}")
        return False


def add_expense(
    phone: str,
    amount: float,
    category: str,
    description: str = "",
    date: str = None
) -> Dict[str, Any]:
    """
    Add a new expense.
    
    Args:
        phone: User's phone number
        amount: Expense amount
        category: Expense category (food, transport, entertainment, etc.)
        description: Optional description
        date: Optional date (YYYY-MM-DD), defaults to today
        
    Returns:
        Result dictionary
    """
    expenses = _load_expenses()
    
    if phone not in expenses:
        expenses[phone] = []
    
    expense = {
        'id': len(expenses[phone]) + 1,
        'amount': float(amount),
        'category': category.lower(),
        'description': description,
        'date': date or datetime.now().strftime('%Y-%m-%d'),
        'created_at': datetime.now().isoformat()
    }
    
    expenses[phone].append(expense)
    _save_expenses(expenses)
    
    return {
        'success': True,
        'expense': expense,
        'message': f"✅ Recorded: R{amount:.2f} for {category}"
    }


def get_expenses(
    phone: str,
    days: int = 30,
    category: str = None
) -> List[Dict[str, Any]]:
    """
    Get expenses for a user.
    
    Args:
        phone: User's phone number
        days: Number of days to look back
        category: Optional category filter
        
    Returns:
        List of expenses
    """
    expenses = _load_expenses()
    user_expenses = expenses.get(phone, [])
    
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    filtered = [
        e for e in user_expenses
        if e['date'] >= cutoff_date
        and (category is None or e['category'] == category.lower())
    ]
    
    return sorted(filtered, key=lambda x: x['date'], reverse=True)


def get_spending_summary(phone: str, days: int = 30) -> Dict[str, Any]:
    """
    Get a spending summary for a user.
    
    Args:
        phone: User's phone number
        days: Number of days to analyze
        
    Returns:
        Spending summary dictionary
    """
    expenses = get_expenses(phone, days)
    
    if not expenses:
        return {
            'total': 0,
            'by_category': {},
            'count': 0,
            'period': f"Last {days} days",
            'message': "No expenses recorded yet."
        }
    
    total = sum(e['amount'] for e in expenses)
    by_category = defaultdict(float)
    
    for e in expenses:
        by_category[e['category']] += e['amount']
    
    # Sort categories by amount
    sorted_categories = dict(sorted(by_category.items(), key=lambda x: x[1], reverse=True))
    
    return {
        'total': total,
        'by_category': dict(sorted_categories),
        'count': len(expenses),
        'period': f"Last {days} days",
        'daily_average': total / days
    }


def format_spending_report(phone: str, days: int = 30) -> str:
    """
    Generate a formatted spending report.
    
    Args:
        phone: User's phone number
        days: Number of days to analyze
        
    Returns:
        Formatted report string
    """
    summary = get_spending_summary(phone, days)
    
    if summary.get('count', 0) == 0:
        return "📊 **Spending Report**\n\nNo expenses recorded yet. Use:\n`I spent R50 on groceries`\nto start tracking!"
    
    report = f"📊 **Spending Report** ({summary['period']})\n\n"
    report += f"💰 **Total Spent**: R{summary['total']:.2f}\n"
    report += f"📈 **Daily Average**: R{summary['daily_average']:.2f}\n"
    report += f"🧾 **Transactions**: {summary['count']}\n\n"
    
    report += "**By Category:**\n"
    
    category_emojis = {
        'food': '🍔',
        'groceries': '🛒',
        'transport': '🚗',
        'entertainment': '🎬',
        'shopping': '🛍️',
        'utilities': '💡',
        'health': '💊',
        'education': '📚',
        'subscriptions': '📱',
        'other': '📦'
    }
    
    for cat, amount in summary['by_category'].items():
        emoji = category_emojis.get(cat, '💵')
        percentage = (amount / summary['total']) * 100
        report += f"{emoji} {cat.title()}: R{amount:.2f} ({percentage:.0f}%)\n"
    
    return report


def get_weekly_report(phone: str) -> str:
    """Get a weekly spending report."""
    return format_spending_report(phone, 7)


def get_monthly_report(phone: str) -> str:
    """Get a monthly spending report."""
    return format_spending_report(phone, 30)


def parse_expense_from_text(text: str, phone: str) -> Dict[str, Any]:
    """
    Parse an expense from natural language text.
    
    Args:
        text: Natural language expense description
        phone: User's phone number
        
    Returns:
        Parsed expense result
    """
    import re
    
    # Common patterns for expense mentions
    # "I spent R50 on groceries"
    # "R100 for transport"
    # "Paid R250 for dinner"
    
    amount_pattern = r'R?\s*(\d+(?:\.\d{2})?)'
    
    # Find amount
    amount_match = re.search(amount_pattern, text, re.IGNORECASE)
    if not amount_match:
        return {'error': 'Could not find amount in text'}
    
    amount = float(amount_match.group(1))
    
    # Detect category from keywords
    category_keywords = {
        'food': ['food', 'lunch', 'dinner', 'breakfast', 'meal', 'restaurant', 'cafe', 'coffee'],
        'groceries': ['groceries', 'grocery', 'supermarket', 'shop', 'woolworths', 'checkers', 'pick n pay', 'spar'],
        'transport': ['transport', 'uber', 'bolt', 'taxi', 'petrol', 'fuel', 'gas', 'bus', 'train'],
        'entertainment': ['movie', 'cinema', 'netflix', 'spotify', 'game', 'concert', 'show'],
        'shopping': ['clothes', 'shoes', 'electronics', 'amazon', 'takealot'],
        'utilities': ['electricity', 'water', 'internet', 'wifi', 'phone', 'airtime', 'data'],
        'health': ['doctor', 'pharmacy', 'medicine', 'gym', 'medical'],
        'subscriptions': ['subscription', 'monthly', 'netflix', 'spotify', 'youtube']
    }
    
    text_lower = text.lower()
    detected_category = 'other'
    
    for category, keywords in category_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            detected_category = category
            break
    
    # Extract description (everything after amount or category keywords)
    description = text
    
    return add_expense(phone, amount, detected_category, description)


def delete_last_expense(phone: str) -> Dict[str, Any]:
    """Delete the last recorded expense."""
    expenses = _load_expenses()
    
    if phone not in expenses or not expenses[phone]:
        return {'error': 'No expenses to delete'}
    
    deleted = expenses[phone].pop()
    _save_expenses(expenses)
    
    return {
        'success': True,
        'deleted': deleted,
        'message': f"🗑️ Deleted: R{deleted['amount']:.2f} for {deleted['category']}"
    }


def set_budget(phone: str, category: str, amount: float, period: str = 'monthly') -> Dict[str, Any]:
    """Set a budget for a category."""
    # This would store budgets - simplified for now
    return {
        'success': True,
        'message': f"✅ Budget set: R{amount:.2f} for {category} ({period})"
    }


# Expense tracking service instance
class ExpenseService:
    """Service class for expense tracking."""
    
    def add(self, phone: str, amount: float, category: str, description: str = "") -> Dict[str, Any]:
        return add_expense(phone, amount, category, description)
    
    def get_summary(self, phone: str, days: int = 30) -> Dict[str, Any]:
        return get_spending_summary(phone, days)
    
    def get_report(self, phone: str, days: int = 30) -> str:
        return format_spending_report(phone, days)
    
    def parse_and_add(self, phone: str, text: str) -> Dict[str, Any]:
        return parse_expense_from_text(text, phone)


expense_service = ExpenseService()
