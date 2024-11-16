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
        self.base_url = "https://liveipl.live"  # Removed /api/ as it's included in endpoint
    
    def create_order(self, telegram_id, user_token, amount, order_id, redirect_url, remark1, remark2):
        endpoint = f"{self.base_url}/api/create-order"  # Added /api/ to endpoint
        payload = {
            "customer_id": str(telegram_id),  # Ensure telegram_id is string
            "user_token": str(user_token),
            "amount": str(amount),
            "order_id": str(order_id),
            "redirect_url": str(redirect_url),
            "remark1": str(remark1),
            "remark2": str(remark2)
        }
        
        headers = {
            'Content-Type': 'application/json',  # Changed to JSON content type
            'Accept': 'application/json'
        }
        
        logger.info(f"Creating order with payload: {payload}")
        
        try:
            response = requests.post(endpoint, json=payload, headers=headers)  # Using json parameter for JSON payload
            logger.info(f"API Response Status: {response.status_code}")
            
            try:
                response_data = response.json()
                logger.info(f"API Response Data: {response_data}")
                
                if response.status_code == 200:
                    return response_data
                else:
                    error_message = response_data.get('message', 'Unknown error')
                    logger.error(f"API Error: {error_message}")
                    return {"status": False, "message": f"API Error: {error_message}"}
                    
            except ValueError as e:
                logger.error(f"Error parsing JSON response: {str(e)}")
                return {"status": False, "message": "Invalid JSON response from API"}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request Exception: {str(e)}")
            return {"status": False, "message": f"Request failed: {str(e)}"}
