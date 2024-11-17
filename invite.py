import asyncio
from telegram import Bot
from datetime import datetime, timedelta
from config import TELEGRAM_BOT_TOKEN, SUBSCRIPTION_PLANS
from models import Payment, InviteLink, User, db
import logging

logger = logging.getLogger(__name__)

async def generate_invite_for_order_8967775955(bot: Bot):
    """
    Generate invite link specifically for order ID 8967775955
    """
    ORDER_ID = "8967775955"
    
    try:
        with app.app_context():
            # 1. Fetch payment record
            payment = Payment.query.filter_by(order_id=ORDER_ID).first()
            if not payment:
                logger.error(f"Payment not found for order ID: {ORDER_ID}")
                return {
                    'status': False,
                    'message': 'Payment record not found'
                }

            # 2. Get user details
            user = User.query.get(payment.user_id)
            if not user:
                logger.error(f"User not found for payment: {payment.id}")
                return {
                    'status': False,
                    'message': 'User not found'
                }

            # 3. Determine channel ID based on payment amount
            channel_id = None
            for plan_id, plan in SUBSCRIPTION_PLANS.items():
                if plan['price'] == payment.amount:
                    if 'channels' in plan:
                        # For all access bundle
                        channel_ids = plan['channels']
                    else:
                        # For single channel plans
                        channel_ids = [plan['channel_id']]
                    break

            if not channel_ids:
                logger.error(f"No matching plan found for amount: {payment.amount}")
                return {
                    'status': False,
                    'message': 'No matching subscription plan found'
                }

            results = []
            # 4. Generate invite links for each channel
            for channel_id in channel_ids:
                try:
                    # Create invite link with 24-hour validity
                    invite = await bot.create_chat_invite_link(
                        chat_id=channel_id,
                        member_limit=1,
                        expire_date=datetime.utcnow() + timedelta(days=1)
                    )

                    # Store in database
                    new_invite = InviteLink(
                        user_id=user.id,
                        channel_id=channel_id,
                        order_id=ORDER_ID,
                        invite_link=invite.invite_link,
                        expires_at=datetime.utcnow() + timedelta(days=1)
                    )
                    db.session.add(new_invite)
                    
                    results.append({
                        'channel_id': channel_id,
                        'invite_link': invite.invite_link,
                        'expires_at': new_invite.expires_at
                    })

                except Exception as e:
                    logger.error(f"Error generating invite for channel {channel_id}: {str(e)}")
                    results.append({
                        'channel_id': channel_id,
                        'error': str(e)
                    })

            db.session.commit()

            # 5. Send invite links to user
            if results:
                message_text = "🎉 Here are your channel invite links:\n\n"
                for result in results:
                    if 'invite_link' in result:
                        message_text += f"Channel {result['channel_id']}:\n{result['invite_link']}\n\n"
                
                message_text += "⚠️ These links will expire in 24 hours. Please join soon!"
                
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=message_text
                )

            return {
                'status': True,
                'message': 'Invite links generated successfully',
                'results': results,
                'user_telegram_id': user.telegram_id
            }

    except Exception as e:
        logger.error(f"Error in invite generation: {str(e)}", exc_info=True)
        return {
            'status': False,
            'message': f'Error: {str(e)}'
        }

# Execute the function
if __name__ == "__main__":
    async def main():
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        print("Generating invite link for order 8967775955...")
        result = await generate_invite_for_order_8967775955(bot)
        print(f"Result: {result}")
        if result['status']:
            print("✅ Invite links generated and sent successfully!")
        else:
            print(f"❌ Error: {result['message']}")

    asyncio.run(main())