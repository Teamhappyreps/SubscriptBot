import requests
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class KhilaadiXProSDK:
    def __init__(self):
        self.base_url = "https://liveipl.live"
    
    def create_order(self, customer_mobile, user_token, amount, order_id, redirect_url, remark1, remark2):
        endpoint = f"{self.base_url}/api/create-order"
        payload = {
            "customer_mobile": str(customer_mobile),
            "user_token": str(user_token),
            "amount": str(amount),
            "order_id": str(order_id),
            "redirect_url": str(redirect_url),
            "remark1": str(remark1),
            "remark2": str(remark2)
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        logger.info(f"Creating order with payload: {payload}")
        
        try:
            response = requests.post(endpoint, data=payload, headers=headers)
            response.encoding = 'utf-8'  # Set encoding explicitly
            logger.info(f"API Response Status: {response.status_code}")
            logger.info(f"API Response Content: {response.text}")  # Log raw response
            
            try:
                response_data = response.json()
                logger.info(f"API Response Data: {response_data}")
                
                if response_data.get('status') and response_data.get('result'):
                    return {
                        'status': True,
                        'message': response_data.get('message', 'Order Created Successfully'),
                        'payment_url': response_data['result']['payment_url'],
                        'order_id': response_data['result']['orderId']
                    }
                else:
                    error_message = response_data.get('message', 'Unknown error')
                    logger.error(f"API Error: {error_message}")
                    return {"status": False, "message": error_message}
                    
            except ValueError as e:
                logger.error(f"Error parsing JSON response: {str(e)}")
                logger.error(f"Raw response content: {response.text}")
                return {"status": False, "message": "Invalid JSON response from API"}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request Exception: {str(e)}")
            return {"status": False, "message": f"Request failed: {str(e)}"}
