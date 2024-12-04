from create_order import KhilaadiXProSDK
from order_status_sdk import OrderStatusSDK
import uuid
from models import Payment, User, db
from config import PAYMENT_BASE_URL, WEBHOOK_BASE_URL, SUBSCRIPTION_PLANS, USER_TOKEN
from subscription_manager import SubscriptionManager
import logging

logger = logging.getLogger(__name__)

class PaymentManager:
    def __init__(self):
        self.sdk = KhilaadiXProSDK()
        self.status_sdk = OrderStatusSDK(PAYMENT_BASE_URL)

    def create_payment(self, user_id, amount, telegram_id):
        order_id = str(uuid.uuid4().int)[:10]
        redirect_url = f"{WEBHOOK_BASE_URL}/payment/callback"
        
        payment = Payment(
            user_id=user_id,
            order_id=order_id,
            amount=amount,
            status='PENDING'
        )
        db.session.add(payment)
        db.session.commit()

        result = self.sdk.create_order(
            customer_mobile=telegram_id,
            user_token=USER_TOKEN,
            amount=str(amount),
            order_id=order_id,
            redirect_url=redirect_url,
            remark1=f"Subscription for user {user_id}",
            remark2="Telegram Channel Subscription"
        )
        
        return result, payment

    def check_payment_status(self, order_id):
        result = self.status_sdk.check_order_status(
            user_token=USER_TOKEN,
            order_id=order_id
        )
        
        # Update payment status in database
        payment = Payment.query.filter_by(order_id=order_id).first()
        if payment and result.get('status') == 'SUCCESS':
            try:
                payment.status = 'SUCCESS'
                
                # Process creator revenue share
                user = User.query.get(payment.user_id)
                if user:
                    # Find the plan based on payment amount
                    for plan_id, plan in SUBSCRIPTION_PLANS.items():
                        if plan['price'] == payment.amount:
                            # Check if channel has a creator
                            channels = plan.get('channels', [plan.get('channel_id')])
                            
                            # Find creators for the channels
                            creators = User.query.filter(
                                User.is_creator == True,
                                User.creator_channels.contains(channels)
                            ).all()
                            
                            if creators:
                                # Split revenue among creators
                                creator_count = len(creators)
                                for creator in creators:
                                    creator_share = (payment.amount * (creator.revenue_share / 100)) / creator_count
                                    payment.creator_share = creator_share
                            
                            SubscriptionManager.create_subscription(user.id, plan_id)
                            break
                
                db.session.commit()
            except Exception as e:
                logger.error(f"Error processing payment and subscription: {e}")
                db.session.rollback()
                
        return result