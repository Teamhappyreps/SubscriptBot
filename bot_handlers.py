import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from config import TELEGRAM_BOT_TOKEN, SUBSCRIPTION_PLANS
from models import User, Payment, InviteLink, db
from payment_manager import PaymentManager
from subscription_manager import SubscriptionManager
from app import app
from datetime import datetime, timedelta
import re
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def generate_channel_invite(channel_id, user_telegram_id, order_id):
    try:
        with app.app_context():
            user = User.query.filter_by(telegram_id=user_telegram_id).first()
            if not user:
                logger.error(f"User not found for telegram_id: {user_telegram_id}")
                return None

            # Create invite link with expiry
            bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
            invite = await bot.create_chat_invite_link(
                chat_id=channel_id,
                member_limit=1,
                expire_date=datetime.utcnow() + timedelta(days=1)  # 24-hour validity
            )

            # Store invite link in database
            if invite:
                invite_link = InviteLink(
                    user_id=user.id,
                    channel_id=channel_id,
                    order_id=order_id,
                    invite_link=invite.invite_link,
                    expires_at=datetime.utcnow() + timedelta(days=1)
                )
                db.session.add(invite_link)
                db.session.commit()

                # Send invite link to user with updated message
                await bot.send_message(
                    chat_id=user_telegram_id,
                    text=f"🎉 Channel Access Granted!\n\n"
                         f"🔗 Join Channel: {invite.invite_link}\n\n"
                         f"⚠️ This invite link expires in 24 hours\n\n"
                         f"❓ Need help? Contact @happy69now"
                )
            else:
                logger.error("Failed to create invite link")
                return None
            
            return invite_link

    except telegram.error.TelegramError as e:
        logger.error(f"Telegram API error while generating invite for channel {channel_id}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error generating invite for channel {channel_id}: {str(e)}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with app.app_context():
        db_user = User.query.filter_by(telegram_id=user.id).first()
        if not db_user:
            db_user = User(telegram_id=user.id, username=user.username)
            db.session.add(db_user)
            db.session.commit()
            logger.info(f"New user registered: {user.id}")

    keyboard = [
        [InlineKeyboardButton("View Subscription Plans", callback_data="show_plans")],
        [InlineKeyboardButton("My Subscriptions", callback_data="my_subs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎉 Welcome to Premium Services!\n\n"
        "Choose an option below to get started:\n"
        "• View our subscription plans\n"
        "• Check your active subscriptions\n\n"
        "❓ Need help? Contact @happy69now",
        reply_markup=reply_markup
    )

async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        keyboard = []
        plans_message = "Available Subscription Plans:\n\n"
        
        logger.info("Starting to generate subscription plan buttons")
        for plan_id, plan in SUBSCRIPTION_PLANS.items():
            # Validate plan data
            if not all(key in plan for key in ['name', 'price', 'duration_days']):
                logger.error(f"Invalid plan data for {plan_id}: missing required fields")
                continue
                
            # Calculate number of channels
            num_channels = len(plan.get('channels', [plan.get('channel_id', 'Unknown')]))
            
            plan_info = (
                f"📦 {plan['name']}\n"
                f"💰 Price: ₹{plan['price']}\n"
                f"⏳ Duration: {plan['duration_days']} days\n"
                f"📺 Channels: {num_channels} Premium Channel{'s' if num_channels > 1 else ''}\n\n"
            )
            plans_message += plan_info
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{plan['name']} - ₹{plan['price']} ({plan['duration_days']} days)",
                    callback_data=f"subscribe_{plan_id}"
                )
            ])
            
        keyboard.append([InlineKeyboardButton("Back", callback_data="start")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            plans_message + "\nChoose a plan to subscribe:",
            reply_markup=reply_markup
        )
        logger.info("Successfully displayed all subscription plans")
        
    except Exception as e:
        logger.error(f"Error in show_plans: {str(e)}", exc_info=True)
        await update.callback_query.answer("Error displaying plans. Please try again.")

async def handle_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        
        # Validate callback data format
        if not query.data:
            logger.error("Callback data is missing")
            await query.answer("Invalid selection. Please try again.")
            return
            
        logger.info(f"Received callback data: {query.data}")
        
        # Validate callback data format and extract plan_id
        if not query.data.startswith("subscribe_"):
            logger.error(f"Invalid callback data format: {query.data}. Expected format: subscribe_<plan_id>")
            await query.answer("Invalid selection format. Please try again.")
            return
            
        plan_id = query.data[len("subscribe_"):]  # Remove "subscribe_" prefix
        logger.info(f"Extracted plan_id: {plan_id}")
        
        # Validate plan_id against SUBSCRIPTION_PLANS
        if plan_id not in SUBSCRIPTION_PLANS:
            logger.error(f"Invalid plan_id: {plan_id}. Available plans: {list(SUBSCRIPTION_PLANS.keys())}")
            await query.answer("Invalid plan selected. Please choose a valid plan.")
            return
            
        plan = SUBSCRIPTION_PLANS[plan_id]
        logger.info(f"Found valid plan: {plan['name']} (ID: {plan_id})")

        # Store plan details in context
        context.user_data['pending_plan'] = {
            'id': plan_id,
            'name': plan['name'],
            'price': plan['price'],
            'duration': plan['duration_days']
        }
        
        # Proceed directly with payment creation
        with app.app_context():
            user = User.query.filter_by(telegram_id=update.effective_user.id).first()
            if not user:
                logger.error(f"User not found in database: {update.effective_user.id}")
                await query.answer("Error: User not found. Please start over with /start")
                return

            payment_manager = PaymentManager()
            result, payment = payment_manager.create_payment(
                user.id,
                plan['price'],
                update.effective_user.id
            )

            if result.get('status'):
                # Create keyboard with payment URL and status check button
                keyboard = [
                    [InlineKeyboardButton("Pay Now", url=result['payment_url'])],
                    [InlineKeyboardButton("Check Payment Status", callback_data=f"check_status_{payment.order_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.message.reply_text(
                    f"✅ Payment link created!\n\n"
                    f"Plan: {plan['name']}\n"
                    f"Amount: ₹{plan['price']}\n"
                    f"Duration: {plan['duration_days']} days\n\n"
                    f"Please click the Pay Now button below to complete your payment.",
                    reply_markup=reply_markup
                )
                logger.info(f"Payment link created for user {user.id}, plan {plan_id}")
            else:
                error_msg = result.get('message', 'Unknown error')
                logger.error(f"Payment creation failed: {error_msg}")
                await query.message.reply_text(
                    "❌ Sorry, there was an error creating the payment.\n"
                    f"Error: {error_msg}\n"
                    "Please try again or contact support."
                )
        
        # Clear the pending plan data
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error in handle_subscription: {str(e)}", exc_info=True)
        await query.answer("An error occurred. Please try again.")

async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        order_id = query.data.replace("check_status_", "")
        logger.info(f"Checking payment status for order: {order_id}")
        
        with app.app_context():
            payment_manager = PaymentManager()
            status = payment_manager.check_payment_status(order_id)
            
            if status.get('status') == 'SUCCESS':
                # Get subscription plan details
                payment = Payment.query.filter_by(order_id=order_id).first()
                user = User.query.get(payment.user_id)
                
                # Find plan from payment amount
                for plan_id, plan in SUBSCRIPTION_PLANS.items():
                    if plan['price'] == payment.amount:
                        channels = plan.get('channels', [plan['channel_id']])
                        # Generate invite for each channel
                        for channel in channels:
                            await generate_channel_invite(channel, user.telegram_id, order_id)
                        break

                await query.message.reply_text(
                    f"✅ Payment Successful!\n\n"
                    f"🔖 Order ID: {order_id}\n"
                    f"💰 Amount: ₹{status['result']['amount']}\n"
                    f"📅 Transaction Date: {status['result']['date']}\n\n"
                    f"🎉 Your subscription has been activated!\n"
                    f"📱 Channel invite links will be sent shortly.\n\n"
                    f"❓ Need help? Contact @happy69now\n"
                    f"❗ Note: Save this message for future reference."
                )
            else:
                await query.message.reply_text(
                    "⏳ Payment Pending\n"
                    "Please complete the payment to activate your subscription."
                )
            
        logger.info(f"Payment status for order {order_id}: {status.get('status')}")
        
    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}", exc_info=True)
        await query.message.reply_text("Error checking payment status. Please try again.")

def setup_bot():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(show_plans, pattern="^show_plans$"))
    application.add_handler(CallbackQueryHandler(handle_subscription, pattern="^subscribe_"))
    application.add_handler(CallbackQueryHandler(check_payment_status, pattern="^check_status_"))
    
    return application
