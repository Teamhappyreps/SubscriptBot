import requests

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
            response = requests.post(url, data=payload, headers=headers)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('status') == 'COMPLETED':
                    return {
                        'status': 'SUCCESS',
                        'message': response_data.get('message'),
                        'result': response_data.get('result', {})
                    }
                return response_data
            else:
                return {"status": "ERROR", "message": "API request failed"}
                
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

if __name__ == "__main__":
    base_url = "https://khilaadixpro.shop"
    sdk = OrderStatusSDK(base_url)
    user_token = "05851bd38cb8872279f355c404a8863f"  # Updated token
    order_id = "8052313697"

    result = sdk.check_order_status(user_token, order_id)
    print(result)
