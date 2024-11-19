import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from config import TELEGRAM_BOT_TOKEN, SUBSCRIPTION_PLANS
from models import User, Payment, InviteLink, db, Subscription
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

# Admin command handlers
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin statistics about users and subscriptions"""
    with app.app_context():
        user = User.query.filter_by(telegram_id=update.effective_user.id).first()
        if not user or not (user.is_admin or user.is_super_admin):
            await update.message.reply_text("⚠️ You don't have permission to use this command.")
            return

        total_users = User.query.count()
        active_subs = Subscription.query.filter_by(active=True).count()
        total_payments = Payment.query.filter_by(status='SUCCESS').count()
        
        stats_message = (
            "📊 System Statistics\n\n"
            f"👥 Total Users: {total_users}\n"
            f"✅ Active Subscriptions: {active_subs}\n"
            f"💰 Successful Payments: {total_payments}\n"
        )
        await update.message.reply_text(stats_message)

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all users with their subscription status"""
    with app.app_context():
        user = User.query.filter_by(telegram_id=update.effective_user.id).first()
        if not user or not (user.is_admin or user.is_super_admin):
            await update.message.reply_text("⚠️ You don't have permission to use this command.")
            return

        users = User.query.all()
        user_list = "👥 User List:\n\n"
        
        for u in users:
            active_sub = Subscription.query.filter_by(user_id=u.id, active=True).first()
            status = "✅ Active" if active_sub else "❌ No active subscription"
            user_list += f"ID: {u.telegram_id}\nUsername: @{u.username}\nStatus: {status}\n\n"

        # Split message if too long
        if len(user_list) > 4096:
            chunks = [user_list[i:i+4096] for i in range(0, len(user_list), 4096)]
            for chunk in chunks:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(user_list)

async def admin_revoke_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Revoke a user's subscription"""
    with app.app_context():
        admin = User.query.filter_by(telegram_id=update.effective_user.id).first()
        if not admin or not (admin.is_admin or admin.is_super_admin):
            await update.message.reply_text("⚠️ You don't have permission to use this command.")
            return

        try:
            # Command format: /revoke_sub user_telegram_id
            if len(context.args) < 1:
                await update.message.reply_text("Usage: /revoke_sub <user_telegram_id>")
                return

            target_telegram_id = int(context.args[0])
            target_user = User.query.filter_by(telegram_id=target_telegram_id).first()
            
            if not target_user:
                await update.message.reply_text("❌ User not found.")
                return

            active_sub = Subscription.query.filter_by(user_id=target_user.id, active=True).first()
            if not active_sub:
                await update.message.reply_text("❌ User has no active subscription.")
                return

            # Only super admin can revoke other admin's subscriptions
            if target_user.is_admin and not admin.is_super_admin:
                await update.message.reply_text("⚠️ Only super admin can revoke admin subscriptions.")
                return

            active_sub.active = False
            db.session.commit()

            # Remove from channels
            plan = SUBSCRIPTION_PLANS.get(active_sub.plan_id)
            if plan:
                channels = plan.get('channels', [plan.get('channel_id')])
                for channel in channels:
                    await SubscriptionManager.remove_from_channel(target_telegram_id, channel)

            await update.message.reply_text(f"✅ Successfully revoked subscription for user {target_telegram_id}")

        except ValueError:
            await update.message.reply_text("❌ Invalid user ID format.")
        except Exception as e:
            logger.error(f"Error in admin_revoke_sub: {str(e)}")
            await update.message.reply_text("❌ An error occurred while revoking the subscription.")

async def admin_grant_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grant a subscription to a user"""
    with app.app_context():
        admin = User.query.filter_by(telegram_id=update.effective_user.id).first()
        if not admin or not (admin.is_admin or admin.is_super_admin):
            await update.message.reply_text("⚠️ You don't have permission to use this command.")
            return

        try:
            # Command format: /grant_sub user_telegram_id plan_id duration_days
            if len(context.args) < 3:
                await update.message.reply_text("Usage: /grant_sub <user_telegram_id> <plan_id> <duration_days>")
                return

            target_telegram_id = int(context.args[0])
            plan_id = context.args[1]
            duration_days = int(context.args[2])

            if plan_id not in SUBSCRIPTION_PLANS:
                await update.message.reply_text("❌ Invalid plan ID.")
                return

            target_user = User.query.filter_by(telegram_id=target_telegram_id).first()
            if not target_user:
                await update.message.reply_text("❌ User not found.")
                return

            # Create new subscription
            end_date = datetime.utcnow() + timedelta(days=duration_days)
            subscription = Subscription(
                user_id=target_user.id,
                plan_id=plan_id,
                end_date=end_date,
                active=True
            )
            db.session.add(subscription)
            db.session.commit()

            # Generate invite links
            plan = SUBSCRIPTION_PLANS[plan_id]
            channels = plan.get('channels', [plan.get('channel_id')])
            for channel in channels:
                await generate_channel_invite(channel, target_telegram_id, f"admin_grant_{subscription.id}")

            await update.message.reply_text(
                f"✅ Successfully granted {plan['name']} subscription to user {target_telegram_id}\n"
                f"Duration: {duration_days} days"
            )

        except ValueError:
            await update.message.reply_text("❌ Invalid number format.")
        except Exception as e:
            logger.error(f"Error in admin_grant_sub: {str(e)}")
            await update.message.reply_text("❌ An error occurred while granting the subscription.")

async def admin_make_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Make a user an admin (super admin only)"""
    with app.app_context():
        admin = User.query.filter_by(telegram_id=update.effective_user.id).first()
        if not admin or not admin.is_super_admin:
            await update.message.reply_text("⚠️ This command is only available to super admin.")
            return

        try:
            if len(context.args) < 1:
                await update.message.reply_text("Usage: /make_admin <user_telegram_id>")
                return

            target_telegram_id = int(context.args[0])
            target_user = User.query.filter_by(telegram_id=target_telegram_id).first()
            
            if not target_user:
                await update.message.reply_text("❌ User not found.")
                return

            if target_user.is_admin:
                await update.message.reply_text("⚠️ User is already an admin.")
                return

            target_user.is_admin = True
            db.session.commit()

            await update.message.reply_text(f"✅ Successfully made user {target_telegram_id} an admin.")

        except ValueError:
            await update.message.reply_text("❌ Invalid user ID format.")
        except Exception as e:
            logger.error(f"Error in admin_make_admin: {str(e)}")
            await update.message.reply_text("❌ An error occurred while granting admin privileges.")

async def admin_remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove admin status from a user (super admin only)"""
    with app.app_context():
        admin = User.query.filter_by(telegram_id=update.effective_user.id).first()
        if not admin or not admin.is_super_admin:
            await update.message.reply_text("⚠️ This command is only available to super admin.")
            return

        try:
            if len(context.args) < 1:
                await update.message.reply_text("Usage: /remove_admin <user_telegram_id>")
                return

            target_telegram_id = int(context.args[0])
            target_user = User.query.filter_by(telegram_id=target_telegram_id).first()
            
            if not target_user:
                await update.message.reply_text("❌ User not found.")
                return

            if not target_user.is_admin:
                await update.message.reply_text("⚠️ User is not an admin.")
                return

            if target_user.is_super_admin:
                await update.message.reply_text("⚠️ Cannot remove super admin status.")
                return

            target_user.is_admin = False
            db.session.commit()

            await update.message.reply_text(f"✅ Successfully removed admin status from user {target_telegram_id}.")

        except ValueError:
            await update.message.reply_text("❌ Invalid user ID format.")
        except Exception as e:
            logger.error(f"Error in admin_remove_admin: {str(e)}")
            await update.message.reply_text("❌ An error occurred while removing admin privileges.")

async def validate_channel_id(bot: telegram.Bot, channel_id: str) -> bool:
    try:
        await bot.get_chat(channel_id)
        return True
    except telegram.error.TelegramError as e:
        logger.error(f"Error validating channel {channel_id}: {str(e)}")
        return False

async def generate_channel_invite(channel_id, user_telegram_id, order_id):
    try:
        with app.app_context():
            user = User.query.filter_by(telegram_id=user_telegram_id).first()
            if not user:
                logger.error(f"User not found for telegram_id: {user_telegram_id}")
                return None

            # Get active subscription
            subscription = Subscription.query.filter_by(
                user_id=user.id,
                active=True
            ).order_by(Subscription.end_date.desc()).first()

            if not subscription:
                logger.error(f"No active subscription found for user {user.id}")
                return None

            bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
            
            # Validate channel ID before proceeding
            if not await validate_channel_id(bot, channel_id):
                logger.error(f"Invalid channel ID or bot not admin: {channel_id}")
                return None

            # Get plan details from channel_id
            plan_name = None
            for plan_id, plan in SUBSCRIPTION_PLANS.items():
                if channel_id in plan.get('channels', [plan.get('channel_id')]):
                    plan_name = plan['name']
                    break

            # Get channel name
            try:
                chat = await bot.get_chat(channel_id)
                channel_name = chat.title
            except telegram.error.TelegramError as e:
                logger.error(f"Error getting channel name for {channel_id}: {str(e)}")
                channel_name = "Premium Channel"

            # Create invite link with expiry
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
                logger.info(f"Created invite link for channel {channel_id} for user {user_telegram_id}")

                # Send invite link to user with updated message
                await bot.send_message(
                    chat_id=user_telegram_id,
                    text=f"🎉 Channel Access Granted!\n\n"
                         f"📺 Channel: {channel_name}\n"
                         f"📦 Plan: {plan_name}\n"
                         f"🔗 Join Channel: {invite.invite_link}\n"
                         f"⏳ Link expires in 24 hours\n"
                         f"📅 Plan valid until: {subscription.end_date.strftime('%Y-%m-%d')}\n"
                         f"🔢 Order ID: {order_id}\n\n"
                         f"❓ Need help? Contact @happy69now"
                )
            else:
                logger.error(f"Failed to create invite link for channel {channel_id}")
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
            channels = plan.get('channels', [plan.get('channel_id')])
            num_channels = len(channels) if isinstance(channels, list) else 1
            
            plan_info = (
                f"📦 {plan['name']}\n"
                f"💰 Price: ₹{plan['price']}\n"
                f"⏳ Duration: {plan['duration_days']} days\n"
                f"📺 Channels: {num_channels}\n\n"
            )
            plans_message += plan_info
            keyboard.append([InlineKeyboardButton(f"Subscribe to {plan['name']}", callback_data=f"subscribe_{plan_id}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.message.reply_text(plans_message, reply_markup=reply_markup)
        await update.callback_query.answer()

    except Exception as e:
        logger.error(f"Error in show_plans: {str(e)}")
        await update.callback_query.message.reply_text("❌ Error displaying plans. Please try again later.")
        await update.callback_query.answer()

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast a message to users (admin only)"""
    with app.app_context():
        user = User.query.filter_by(telegram_id=update.effective_user.id).first()
        if not user or not (user.is_admin or user.is_super_admin):
            await update.message.reply_text("⚠️ You don't have permission to use this command.")
            return

        # Check if message and target are provided
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage:\n"
                "/broadcast <target> <message>\n\n"
                "Targets:\n"
                "- all: Send to all users\n"
                "- active: Send only to users with active subscriptions"
            )
            return

        target = context.args[0].lower()
        message = ' '.join(context.args[1:])

        if target not in ['all', 'active']:
            await update.message.reply_text("❌ Invalid target. Use 'all' or 'active'.")
            return

        try:
            if target == 'all':
                users = User.query.all()
            else:  # active subscribers
                users = User.query.join(Subscription).filter(
                    Subscription.active == True,
                    Subscription.end_date > datetime.utcnow()
                ).distinct().all()

            success_count = 0
            fail_count = 0

            for target_user in users:
                try:
                    await context.bot.send_message(
                        chat_id=target_user.telegram_id,
                        text=f"📢 Broadcast Message:\n\n{message}"
                    )
                    success_count += 1
                except telegram.error.TelegramError as e:
                    logger.error(f"Failed to send broadcast to {target_user.telegram_id}: {str(e)}")
                    fail_count += 1

            status_message = (
                f"📊 Broadcast Summary\n\n"
                f"✅ Successfully sent: {success_count}\n"
                f"❌ Failed: {fail_count}\n"
                f"📝 Message: {message}"
            )
            await update.message.reply_text(status_message)

        except Exception as e:
            logger.error(f"Error in broadcast_message: {str(e)}")
            await update.message.reply_text("❌ An error occurred while broadcasting the message.")

def setup_bot():
    """Initialize and configure the bot with all handlers"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Basic commands
    application.add_handler(CommandHandler("start", start))
    
    # Admin commands
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("list_users", admin_list_users))
    application.add_handler(CommandHandler("revoke_sub", admin_revoke_sub))
    application.add_handler(CommandHandler("grant_sub", admin_grant_sub))
    application.add_handler(CommandHandler("make_admin", admin_make_admin))
    application.add_handler(CommandHandler("remove_admin", admin_remove_admin))
    application.add_handler(CommandHandler("broadcast", broadcast_message))

    # Callback queries
    application.add_handler(CallbackQueryHandler(show_plans, pattern="^show_plans$"))

    return application