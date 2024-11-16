import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from config import TELEGRAM_BOT_TOKEN, SUBSCRIPTION_PLANS
from models import User, db
from payment_manager import PaymentManager
from subscription_manager import SubscriptionManager

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = User.query.filter_by(telegram_id=user.id).first()
    if not db_user:
        db_user = User(telegram_id=user.id, username=user.username)
        db.session.add(db_user)
        db.session.commit()

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
    keyboard = []
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        keyboard.append([
            InlineKeyboardButton(
                f"{plan['name']} - ₹{plan['price']}",
                callback_data=f"subscribe_{plan_id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("Back", callback_data="start")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "Available Subscription Plans:\n\n"
        "Choose a plan to subscribe:",
        reply_markup=reply_markup
    )

async def handle_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    plan_id = query.data.split('_')[1]
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    
    if not plan:
        await query.answer("Invalid plan selected!")
        return

    await query.message.reply_text(
        f"Please send your mobile number to proceed with payment of ₹{plan['price']} "
        f"for {plan['name']}"
    )
    context.user_data['pending_plan'] = plan_id

async def process_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mobile_number = update.message.text
    plan_id = context.user_data.get('pending_plan')
    
    if not plan_id:
        await update.message.reply_text("Please select a plan first!")
        return

    plan = SUBSCRIPTION_PLANS[plan_id]
    user = User.query.filter_by(telegram_id=update.effective_user.id).first()
    
    payment_manager = PaymentManager()
    result, payment = payment_manager.create_payment(
        user.id,
        plan['price'],
        mobile_number
    )

    if result.get('status'):
        await update.message.reply_text(
            f"Payment link created! Please complete the payment:\n"
            f"{result['payment_url']}"
        )
    else:
        await update.message.reply_text(
            "Sorry, there was an error creating the payment. Please try again."
        )

def setup_bot():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(show_plans, pattern="^show_plans$"))
    application.add_handler(CallbackQueryHandler(handle_subscription, pattern="^subscribe_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_payment))
    
    return application
