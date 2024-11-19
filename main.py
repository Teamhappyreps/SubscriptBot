from flask import Flask, request, jsonify
from app import app, db
from bot_handlers import setup_bot, generate_channel_invite
from models import Payment, User, Subscription
from subscription_manager import SubscriptionManager
from payment_manager import PaymentManager
import telegram
from config import TELEGRAM_BOT_TOKEN, SUBSCRIPTION_PLANS
from datetime import datetime
import asyncio
import threading
from sqlalchemy import exc

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
payment_manager = PaymentManager()

@app.route('/')
def index():
    return "Telegram Subscription Bot Server is running!"

@app.route('/payment/callback', methods=['POST'])
def payment_callback():
    try:
        order_id = request.form.get('order_id')
        status = request.form.get('status')
        
        if not order_id:
            return jsonify({'status': 'error', 'message': 'Missing order_id'}), 400

        # Start database transaction
        db.session.begin_nested()
        
        payment = Payment.query.filter_by(order_id=order_id).first()
        if not payment:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': 'Invalid order_id'}), 404

        # Verify payment status
        payment_status = payment_manager.check_payment_status(order_id)
        
        if payment_status.get('status') == 'SUCCESS':
            payment.status = 'SUCCESS'
            db.session.commit()

            # Create subscription for user
            user = User.query.get(payment.user_id)
            if user:
                try:
                    # Find subscription details from payment amount
                    for plan_id, plan in SUBSCRIPTION_PLANS.items():
                        if plan['price'] == payment.amount:
                            subscription = SubscriptionManager.create_subscription(user.id, plan_id)
                            
                            # Create event loop for async operations
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            
                            async def process_channels():
                                try:
                                    channels = plan.get('channels', [plan['channel_id']])
                                    for channel in channels:
                                        await generate_channel_invite(channel, user.telegram_id, order_id)
                                except telegram.error.TelegramError as e:
                                    print(f"Error processing channels: {e}")
                            
                            # Run async operations
                            loop.run_until_complete(process_channels())
                            loop.close()
                            break
                            
                except Exception as e:
                    db.session.rollback()
                    print(f"Error processing subscription: {e}")
                    return jsonify({'status': 'error', 'message': 'Error processing subscription'}), 500

            return jsonify({'status': 'success'})
        
        return jsonify({'status': 'pending'})
        
    except exc.SQLAlchemyError as e:
        db.session.rollback()
        print(f"Database error: {e}")
        return jsonify({'status': 'error', 'message': 'Database error'}), 500
    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def run_bot():
    bot_app = setup_bot()
    bot_app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run the bot in the main thread
    run_bot()
