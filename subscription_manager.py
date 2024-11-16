from datetime import datetime, timedelta
from models import Subscription, User, db
from config import SUBSCRIPTION_PLANS
import telegram
from config import TELEGRAM_BOT_TOKEN

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

class SubscriptionManager:
    @staticmethod
    def create_subscription(user_id, plan_id):
        plan = SUBSCRIPTION_PLANS.get(plan_id)
        if not plan:
            return False

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

    @staticmethod
    def check_expired_subscriptions():
        expired_subs = Subscription.query.filter(
            Subscription.end_date <= datetime.utcnow(),
            Subscription.active == True
        ).all()

        for sub in expired_subs:
            sub.active = False
            user = User.query.get(sub.user_id)
            plan = SUBSCRIPTION_PLANS.get(sub.plan_id)
            
            if plan:
                if 'channels' in plan:
                    channels = plan['channels']
                else:
                    channels = [plan['channel_id']]
                
                for channel in channels:
                    try:
                        bot.ban_chat_member(
                            chat_id=channel,
                            user_id=user.telegram_id,
                            until_date=datetime.utcnow()
                        )
                    except Exception as e:
                        print(f"Error removing user from channel: {e}")

        db.session.commit()

def setup_subscription_checks(scheduler):
    scheduler.add_job(
        SubscriptionManager.check_expired_subscriptions,
        'interval',
        hours=1
    )
