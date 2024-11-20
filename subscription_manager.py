from datetime import datetime, timedelta
from models import Subscription, User, db
from config import SUBSCRIPTION_PLANS
from telegram.ext import ExtBot
from telegram.error import TelegramError
from config import TELEGRAM_BOT_TOKEN
import asyncio
from sqlalchemy import exc
from app import app

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
bot = ExtBot(token=TELEGRAM_BOT_TOKEN)

class SubscriptionManager:
    @staticmethod
    def create_subscription(user_id, plan_id):
        try:
            plan = SUBSCRIPTION_PLANS.get(plan_id)
            if not plan:
                return False

            with app.app_context():
                db.session.begin_nested()
                
                end_date = datetime.utcnow() + timedelta(days=plan['duration_days'])
                subscription = Subscription(
                    user_id=user_id,
                    plan_id=plan_id,
                    end_date=end_date,
                    active=True
                )
                db.session.add(subscription)
                db.session.commit()
                
                return subscription
                
        except exc.SQLAlchemyError as e:
            with app.app_context():
                db.session.rollback()
            print(f"Database error in create_subscription: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error in create_subscription: {e}")
            return False

    @staticmethod
    async def remove_from_channel(user_telegram_id, channel):
        try:
            await bot.ban_chat_member(
                chat_id=channel,
                user_id=user_telegram_id,
                until_date=datetime.utcnow()
            )
            # Immediately unban to allow future subscriptions
            await bot.unban_chat_member(
                chat_id=channel,
                user_id=user_telegram_id
            )
            return True
        except Exception as e:
            print(f"Error removing user from channel {channel}: {e}")
            return False

    @staticmethod
    def check_expired_subscriptions():
        try:
            with app.app_context():
                expired_subs = Subscription.query.filter(
                    Subscription.end_date <= datetime.utcnow(),
                    Subscription.active == True
                ).all()

                for sub in expired_subs:
                    try:
                        db.session.begin_nested()
                        
                        sub.active = False
                        user = User.query.get(sub.user_id)
                        plan = SUBSCRIPTION_PLANS.get(sub.plan_id)
                        
                        if plan and user:
                            channels = plan.get('channels', [plan['channel_id']])
                            
                            # Create event loop for async operations
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            
                            async def remove_from_channels():
                                for channel in channels:
                                    await SubscriptionManager.remove_from_channel(user.telegram_id, channel)
                                    
                                try:
                                    await bot.send_message(
                                        chat_id=user.telegram_id,
                                        text=f"Your subscription to {plan['name']} has expired. "
                                             f"Please renew to continue accessing the content."
                                    )
                                except Exception as e:
                                    print(f"Error sending expiration notice: {e}")
                            
                            # Run async operations
                            loop.run_until_complete(remove_from_channels())
                            loop.close()
                        
                        db.session.commit()
                        
                    except exc.SQLAlchemyError as e:
                        db.session.rollback()
                        print(f"Database error processing expired subscription {sub.id}: {e}")
                    except Exception as e:
                        print(f"Error processing expired subscription {sub.id}: {e}")

        except exc.SQLAlchemyError as e:
            print(f"Database error in check_expired_subscriptions: {e}")
        except Exception as e:
            print(f"Unexpected error in check_expired_subscriptions: {e}")

    @staticmethod
    def send_renewal_reminders():
        try:
            with app.app_context():
                # Get subscriptions expiring in the next 7 days
                reminder_date = datetime.utcnow() + timedelta(days=7)
                expiring_soon = Subscription.query.filter(
                    Subscription.end_date <= reminder_date,
                    Subscription.end_date > datetime.utcnow(),
                    Subscription.active == True
                ).all()

                for sub in expiring_soon:
                    try:
                        user = User.query.get(sub.user_id)
                        plan = SUBSCRIPTION_PLANS.get(sub.plan_id)
                        
                        if plan and user:
                            days_left = (sub.end_date - datetime.utcnow()).days
                            
                            # Create event loop for async operations
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            
                            async def send_reminder():
                                try:
                                    message = (
                                        f"⚠️ Subscription Renewal Reminder ⚠️\n\n"
                                        f"Your subscription to {plan['name']} will expire in {days_left} days.\n"
                                        f"Subscription end date: {sub.end_date.strftime('%Y-%m-%d')}\n\n"
                                        f"To continue enjoying our content, please renew your subscription.\n"
                                        f"Use /start command to view available plans."
                                    )
                                    await bot.send_message(
                                        chat_id=user.telegram_id,
                                        text=message
                                    )
                                except Exception as e:
                                    print(f"Error sending renewal reminder: {e}")
                            
                            # Run async operations
                            loop.run_until_complete(send_reminder())
                            loop.close()
                            
                    except Exception as e:
                        print(f"Error processing renewal reminder for subscription {sub.id}: {e}")

        except exc.SQLAlchemyError as e:
            print(f"Database error in send_renewal_reminders: {e}")
        except Exception as e:
            print(f"Unexpected error in send_renewal_reminders: {e}")

def setup_subscription_checks(scheduler):
    # Check for expired subscriptions every hour
    scheduler.add_job(
        SubscriptionManager.check_expired_subscriptions,
        'interval',
        hours=1,
        next_run_time=datetime.utcnow()  # Run immediately on startup
    )
    
    # Send renewal reminders daily at 10:00 AM
    scheduler.add_job(
        SubscriptionManager.send_renewal_reminders,
        'cron',
        hour=10,
        minute=0,
        next_run_time=datetime.utcnow()  # Also run immediately on startup
    )
