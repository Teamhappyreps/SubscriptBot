from datetime import datetime, timedelta
from models import Subscription, User, db
from config import SUBSCRIPTION_PLANS
import telegram
from config import TELEGRAM_BOT_TOKEN
import asyncio
from sqlalchemy import exc

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

class SubscriptionManager:
    @staticmethod
    def create_subscription(user_id, plan_id):
        try:
            plan = SUBSCRIPTION_PLANS.get(plan_id)
            if not plan:
                return False

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
        except telegram.error.TelegramError as e:
            print(f"Error removing user from channel {channel}: {e}")
            return False

    @staticmethod
    def check_expired_subscriptions():
        try:
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
                            except telegram.error.TelegramError as e:
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

def setup_subscription_checks(scheduler):
    scheduler.add_job(
        SubscriptionManager.check_expired_subscriptions,
        'interval',
        hours=1,
        next_run_time=datetime.utcnow()  # Run immediately on startup
    )
