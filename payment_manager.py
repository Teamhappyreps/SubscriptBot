from create_order import KhilaadiXProSDK
from order_status_sdk import OrderStatusSDK
import uuid
from models import Payment, User, db
from config import PAYMENT_BASE_URL, WEBHOOK_BASE_URL, SUBSCRIPTION_PLANS
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
            user_token="05851bd38cb8872279f355c404a8863f",
            amount=str(amount),
            order_id=order_id,
            redirect_url=redirect_url,
            remark1=f"Subscription for user {user_id}",
            remark2="Telegram Channel Subscription"
        )
        
        return result, payment

    def check_payment_status(self, order_id):
        result = self.status_sdk.check_order_status(
            user_token="05851bd38cb8872279f355c404a8863f",
            order_id=order_id
        )
        
        # Update payment status in database
        payment = Payment.query.filter_by(order_id=order_id).first()
        if payment:
            if result.get('status') == 'SUCCESS':
                payment.status = 'SUCCESS'
                db.session.commit()
                
                # Create subscription if payment successful
                try:
                    user = User.query.get(payment.user_id)
                    if user:
                        # Find the plan based on payment amount
                        for plan_id, plan in SUBSCRIPTION_PLANS.items():
                            if plan['price'] == payment.amount:
                                SubscriptionManager.create_subscription(user.id, plan_id)
                                break
                except Exception as e:
                    logger.error(f"Error creating subscription after payment: {e}")
                    
        return result
