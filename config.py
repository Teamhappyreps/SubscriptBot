import os

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Database Configuration
POSTGRES_URI = os.environ.get('DATABASE_URL')

# Subscription Plans
SUBSCRIPTION_PLANS = {
    'daily_desi_monthly': {
        'name': 'Daily Desi Monthly',
        'price': 299,
        'duration_days': 30,
        'channel_id': '@daily_desi'  # Replace with actual channel ID
    },
    'daily_desi_yearly': {
        'name': 'Daily Desi Yearly',
        'price': 999,
        'duration_days': 365,
        'channel_id': '@daily_desi'
    },
    'tamil_tango_monthly': {
        'name': 'Tamil Tango Monthly',
        'price': 299,
        'duration_days': 30,
        'channel_id': '@tamil_tango'
    },
    'all_access_yearly': {
        'name': 'All Access Bundle Yearly',
        'price': 1499,
        'duration_days': 365,
        'channels': ['@daily_desi', '@tamil_tango']
    }
}

# Payment Gateway Configuration
PAYMENT_BASE_URL = "https://liveipl.live"
WEBHOOK_BASE_URL = "https://your-domain.com"  # Replace with actual domain
USER_TOKEN = "05851bd38cb8872279f355c404a8863f"
