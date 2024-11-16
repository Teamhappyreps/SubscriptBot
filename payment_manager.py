from create_order import KhilaadiXProSDK
from order_status_sdk import OrderStatusSDK
import uuid
from models import Payment, db
from config import PAYMENT_BASE_URL, WEBHOOK_BASE_URL

class PaymentManager:
    def __init__(self):
        self.sdk = KhilaadiXProSDK()
        self.status_sdk = OrderStatusSDK(PAYMENT_BASE_URL)

    def create_payment(self, user_id, amount, mobile_number):
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
            customer_mobile=mobile_number,
            user_token="e8d2a2f1ac98d41d3b7422fd11ab98fa",  # Use environment variable in production
            amount=str(amount),
            order_id=order_id,
            redirect_url=redirect_url,
            remark1=f"Subscription for user {user_id}",
            remark2="Telegram Channel Subscription"
        )
        
        return result, payment

    def check_payment_status(self, order_id):
        result = self.status_sdk.check_order_status(
            user_token="2048f66bef68633fa3262d7a398ab577",  # Use environment variable in production
            order_id=order_id
        )
        
        payment = Payment.query.filter_by(order_id=order_id).first()
        if payment and result.get('status') == 'SUCCESS':
            payment.status = 'SUCCESS'
            db.session.commit()
            
        return result
