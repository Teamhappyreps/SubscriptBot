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
        'channel_id': '-1002280414979'  # Replace with actual channel ID
    },
    'daily_desi_yearly': {
        'name': 'Daily Desi Yearly',
        'price': 999,
        'duration_days': 365,
        'channel_id': '-1002280414979'
    },
    'tamil_tango_monthly': {
        'name': 'Tamil Tango Monthly',
        'price': 299,
        'duration_days': 30,
        'channel_id': '-1002294971726'
    },
    'tamil_tango_yearly': {
        'name': 'Tamil Tango Yearly',
        'price': 699,
        'duration_days': 365,
        'channel_id': '-1002294971726'
    },
    'models_monthly': {
        'name': 'Model collection Monthly',
        'price': 299,
        'duration_days': 30,
        'channel_id': '-1002444202487'
    },
    'models_yearly': {
        'name': 'Model collection Yearly',
        'price': 699,
        'duration_days': 365,
        'channel_id': '-1002444202487'
    },
    'all_access_yearly': {
        'name': 'All Access Bundle Yearly',
        'price': 1499,
        'duration_days': 365,
        'channels': ['-1002280414979', '-1002294971726', '-1002444202487']
    }
}

# Payment Gateway Configuration
PAYMENT_BASE_URL = "https://liveipl.live"
WEBHOOK_BASE_URL = "https://happy99now.replit.app"  # Replace with actual domain
USER_TOKEN = "05851bd38cb8872279f355c404a8863f"
