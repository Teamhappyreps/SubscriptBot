from create_order import KhilaadiXProSDK
from order_status_sdk import OrderStatusSDK
import uuid
from models import Payment, db
from config import PAYMENT_BASE_URL, WEBHOOK_BASE_URL

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
            customer_mobile=telegram_id,  # Updated parameter name
            user_token="05851bd38cb8872279f355c404a8863f",  # Updated user token
            amount=str(amount),
            order_id=order_id,
            redirect_url=redirect_url,
            remark1=f"Subscription for user {user_id}",
            remark2="Telegram Channel Subscription"
        )
        
        return result, payment

    def check_payment_status(self, order_id):
        result = self.status_sdk.check_order_status(
            user_token="05851bd38cb8872279f355c404a8863f",  # Updated user token
            order_id=order_id
        )
        
        payment = Payment.query.filter_by(order_id=order_id).first()
        if payment and result.get('status') == 'SUCCESS':
            payment.status = 'SUCCESS'
            db.session.commit()
            
        return result
