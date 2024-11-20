from flask import Flask, request, jsonify
from app import app, db
from bot_handlers import setup_bot
from models import Payment, User, Subscription
from subscription_manager import SubscriptionManager
from payment_manager import PaymentManager
from telegram.ext import ExtBot
from telegram.error import TelegramError
from config import TELEGRAM_BOT_TOKEN, SUBSCRIPTION_PLANS
from datetime import datetime
import asyncio
import threading
from sqlalchemy import exc

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
bot = ExtBot(token=TELEGRAM_BOT_TOKEN)
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
                            
                            async def send_confirmation():
                                try:
                                    message = (
                                        f"🎉 Payment Successful!\n\n"
                                        f"Order ID: {order_id}\n"
                                        f"Amount: ₹{payment.amount}\n"
                                        f"Subscription: {plan['name']}\n"
                                        f"Valid until: {subscription.end_date.strftime('%Y-%m-%d')}"
                                    )
                                    await bot.send_message(chat_id=user.telegram_id, text=message)
                                    
                                    # Add user to channel(s)
                                    channels = plan.get('channels', [plan['channel_id']])
                                    
                                    for channel in channels:
                                        try:
                                            invite_link = await bot.create_chat_invite_link(
                                                chat_id=channel,
                                                member_limit=1,
                                                expire_date=subscription.end_date
                                            )
                                            await bot.send_message(
                                                chat_id=user.telegram_id,
                                                text=f"Join your channel here: {invite_link.invite_link}"
                                            )
                                        except Exception as e:
                                            print(f"Error creating invite link for channel {channel}: {e}")
                                            continue
                                            
                                except Exception as e:
                                    print(f"Error sending confirmation: {e}")
                                    
                            # Run async operations
                            loop.run_until_complete(send_confirmation())
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
    try:
        bot_app = setup_bot()
        bot_app.run_polling(drop_pending_updates=True, allowed_updates=['message', 'callback_query'])
    except Exception as e:
        logger.error(f"Error in bot polling: {e}")
        raise

if __name__ == '__main__':
    try:
        # Start Flask in a separate thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # Run the bot in the main thread
        run_bot()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        raise
