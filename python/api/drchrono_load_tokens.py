import json
import os
from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.files import get_abs_path
from python.helpers.print_style import PrintStyle


class DrchronoLoadTokens(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        try:
            tokens_file = get_abs_path("drchrono_tokens.json")
            
            if not os.path.exists(tokens_file):
                return {
                    "success": False,
                    "message": "drchrono_tokens.json file not found. Please create it with your DrChrono tokens."
                }
            
            with open(tokens_file, 'r') as f:
                tokens = json.load(f)
            
            access_token = tokens.get('access_token', '')
            refresh_token = tokens.get('refresh_token', '')
            
            if not access_token:
                return {
                    "success": False,
                    "message": "No access_token found in drchrono_tokens.json. Please add your DrChrono access token."
                }
            
            PrintStyle(font_color="green").print(f"Loaded DrChrono tokens from file")
            
            return {
                "success": True,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": tokens.get('expires_in', 36000),
                "token_type": tokens.get('token_type', 'Bearer'),
                "message": "Tokens loaded successfully from drchrono_tokens.json"
            }
            
        except json.JSONDecodeError:
            return {
                "success": False,
                "message": "Invalid JSON in drchrono_tokens.json file"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error loading tokens: {str(e)}"
            }