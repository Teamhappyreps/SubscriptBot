import requests

class KhilaadiXProSDK:
    def __init__(self):
        self.base_url = "https://liveipl.live/api/"
    
    def create_order(self, telegram_id, user_token, amount, order_id, redirect_url, remark1, remark2):
        endpoint = self.base_url + "create-order"
        payload = {
            "customer_id": str(telegram_id),  # Using telegram_id as customer identifier
            "user_token": user_token,
            "amount": amount,
            "order_id": order_id,
            "redirect_url": redirect_url,
            "remark1": remark1,
            "remark2": remark2
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        try:
            response = requests.post(endpoint, data=payload, headers=headers)
            if response.status_code == 200:
                return response.json()
            else:
                return {"status": False, "message": "Error in API call"}
        except requests.exceptions.RequestException as e:
            return {"status": False, "message": str(e)}
