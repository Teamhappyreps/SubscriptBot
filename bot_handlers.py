import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from config import TELEGRAM_BOT_TOKEN, SUBSCRIPTION_PLANS
from models import User, db
from payment_manager import PaymentManager
from subscription_manager import SubscriptionManager
from app import app
import re
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
        "Welcome to the Channel Subscription Bot!\n"
        "Choose an option below:",
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
                
            plan_info = (
                f"📦 {plan['name']}\n"
                f"💰 Price: ₹{plan['price']}\n"
                f"⏳ Duration: {plan['duration_days']} days\n"
                f"📺 Channels: {', '.join(plan.get('channels', [plan.get('channel_id', 'Unknown')]))}\n\n"
            )
            plans_message += plan_info
            
            callback_data = f"subscribe_{plan_id}"
            logger.info(f"Generating callback data - Plan ID: {plan_id}, Full callback data: {callback_data}")
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{plan['name']} - ₹{plan['price']} ({plan['duration_days']} days)",
                    callback_data=callback_data
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
            
            status_message = "Payment Successful! ✅" if status.get('status') == 'SUCCESS' else "Payment Pending ⏳"
            
        await query.message.reply_text(status_message)
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
