import requests
from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.print_style import PrintStyle


class DrchronoTest(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        access_token = input.get('access_token', '')
        base_url = input.get('base_url', 'https://drchrono.com/api')
        
        if not access_token:
            return {
                "success": False, 
                "message": "Access token is required"
            }
        
        try:
            # Test DrChrono API connection
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            # Try to get current user info
            response = requests.get(f"{base_url}/users/current", headers=headers, timeout=10)
            
            if response.status_code == 200:
                user_data = response.json()
                username = user_data.get('username', 'Unknown')
                
                PrintStyle(font_color="green").print(f"DrChrono API test successful for user: {username}")
                
                return {
                    "success": True,
                    "message": f"Successfully connected to DrChrono as {username}",
                    "user_data": user_data
                }
            elif response.status_code == 401:
                return {
                    "success": False,
                    "message": "Authentication failed. Access token may be expired or invalid."
                }
            elif response.status_code == 403:
                return {
                    "success": False,
                    "message": "Access forbidden. Check your DrChrono permissions and scopes."
                }
            else:
                return {
                    "success": False,
                    "message": f"DrChrono API returned {response.status_code}: {response.text}"
                }
                
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Connection timed out. DrChrono API may be unreachable."
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Failed to connect to DrChrono API. Check your internet connection."
            }
        except Exception as e:
            error_msg = f"DrChrono API test failed: {str(e)}"
            PrintStyle(font_color="red").print(error_msg)
            return {
                "success": False,
                "message": error_msg
            }