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
                         f"📅 Plan valid until: {subscription.end_date.strftime('%Y-%m-%d')}\n\n"
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
            logger.error(f"Invalid callback data format: {query.data}")
            await query.answer("Invalid selection format. Please try again.")
            return
            
        plan_id = query.data[len("subscribe_"):]  # Remove "subscribe_" prefix
        logger.info(f"Extracted plan_id: {plan_id}")
        
        # Validate plan_id against SUBSCRIPTION_PLANS
        if plan_id not in SUBSCRIPTION_PLANS:
            logger.error(f"Invalid plan_id: {plan_id}")
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
        
        # Proceed with payment creation
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
                if not payment:
                    logger.error(f"Payment not found for order_id: {order_id}")
                    await query.message.reply_text("Error: Payment details not found.")
                    return

                user = User.query.get(payment.user_id)
                if not user:
                    logger.error(f"User not found for payment: {payment.id}")
                    await query.message.reply_text("Error: User details not found.")
                    return

                # Find plan from payment amount
                matching_plan = None
                for plan_id, plan in SUBSCRIPTION_PLANS.items():
                    if plan['price'] == payment.amount:
                        matching_plan = plan
                        break

                if matching_plan:
                    # Get channels list properly
                    channels = []
                    if 'channels' in matching_plan:
                        channels = matching_plan['channels']
                    elif 'channel_id' in matching_plan:
                        channels = [matching_plan['channel_id']]
                    else:
                        logger.error(f"No channel information found in plan: {matching_plan}")
                        await query.message.reply_text("Error: Invalid plan configuration.")
                        return

                    # Validate channels list
                    if not channels:
                        logger.error("Empty channels list")
                        await query.message.reply_text("Error: No channels configured for this plan.")
                        return

                    # Track successful and failed invites
                    success_count = 0
                    failed_channels = []

                    # Generate invite for each channel
                    for channel in channels:
                        logger.info(f"Attempting to generate invite for channel: {channel}")
                        try:
                            invite_result = await generate_channel_invite(channel, user.telegram_id, order_id)
                            if invite_result:
                                success_count += 1
                                logger.info(f"Successfully generated invite for channel {channel}")
                            else:
                                failed_channels.append(channel)
                                logger.error(f"Failed to generate invite for channel {channel}")
                        except Exception as e:
                            failed_channels.append(channel)
                            logger.error(f"Exception while generating invite for channel {channel}: {str(e)}")

                    # Prepare status message
                    status_message = (
                        f"✅ Payment Successful!\n\n"
                        f"🔖 Order ID: {order_id}\n"
                        f"💰 Amount: ₹{status['result']['amount']}\n"
                        f"📅 Transaction Date: {status['result']['date']}\n\n"
                        f"🎉 Your subscription has been activated!\n"
                    )

                    if success_count > 0:
                        status_message += f"✅ Successfully generated {success_count} channel invite{'s' if success_count > 1 else ''}.\n"
                    
                    if failed_channels:
                        status_message += (
                            f"⚠️ Failed to generate invites for {len(failed_channels)} channel{'s' if len(failed_channels) > 1 else ''}.\n"
                            f"Please contact @happy69now for assistance."
                        )
                        logger.error(f"Failed to generate invites for channels: {failed_channels}")

                    status_message += (
                        f"\n❓ Need help? Contact @happy69now\n"
                        f"❗ Note: Save this message for future reference."
                    )

                    await query.message.reply_text(status_message)
                else:
                    logger.error(f"No matching plan found for amount: {payment.amount}")
                    await query.message.reply_text("Error: Could not find matching subscription plan.")
            else:
                await query.message.reply_text(
                    "⏳ Payment Pending\n"
                    "Please complete the payment to activate your subscription."
                )
            
            logger.info(f"Payment status check completed for order {order_id}: {status.get('status')}")
        
    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}", exc_info=True)
        await query.answer("An error occurred while checking payment status.")

# Admin commands are updated to use /stats, /list_users, /revoke_sub, /grant_sub, /make_admin, and /remove_admin
def setup_bot():
    """Initialize and configure the bot with handlers"""
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
    
    # Callback queries
    application.add_handler(CallbackQueryHandler(show_plans, pattern="^show_plans$"))
    application.add_handler(CallbackQueryHandler(handle_subscription, pattern="^subscribe_"))
    application.add_handler(CallbackQueryHandler(check_payment_status, pattern="^check_status_"))

    return application