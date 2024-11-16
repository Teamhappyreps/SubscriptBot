import requests
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class OrderStatusSDK:
    def __init__(self, base_url):
        self.base_url = base_url

    def check_order_status(self, user_token, order_id):
        url = f"{self.base_url}/api/check-order-status"
        payload = {
            "user_token": str(user_token),
            "order_id": str(order_id)
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        try:
            logger.info(f"Request URL: {url}")
            logger.info(f"Request payload: {payload}")
            
            response = requests.post(url, data=payload, headers=headers)
            response.encoding = 'utf-8'
            
            logger.info(f"Response status code: {response.status_code}")
            logger.info(f"Response content: {response.text}")
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('status') is True:  # API returns boolean true
                    result_data = response_data.get('result', {})
                    return {
                        'status': 'SUCCESS' if result_data.get('txnStatus') == 'SUCCESS' else 'PENDING',
                        'message': response_data.get('message', ''),
                        'result': {
                            'txnStatus': result_data.get('txnStatus'),
                            'orderId': result_data.get('orderId'),
                            'amount': result_data.get('amount'),
                            'date': result_data.get('date'),
                            'utr': result_data.get('utr')
                        }
                    }
                return response_data
            else:
                return {"status": "ERROR", "message": f"API request failed with status code: {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            return {"status": "ERROR", "message": f"Request failed: {str(e)}"}

if __name__ == "__main__":
    base_url = "https://liveipl.live"
    sdk = OrderStatusSDK(base_url)
    user_token = "05851bd38cb8872279f355c404a8863f"
    order_id = "8967775955"

    result = sdk.check_order_status(user_token, order_id)
    logger.info(f"Status Check Result: {result}")
