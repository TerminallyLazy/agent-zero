from python.helpers import runtime, crypto, dotenv

async def get_root_password():
    if runtime.is_dockerized():
        pswd = _get_root_password()
    else:
        # Try to get root password directly from environment first
        pswd = _get_root_password()
        if pswd:
            return pswd

        # If no direct password, try RFC call (requires Docker instance)
        try:
            priv = crypto._generate_private_key()
            pub = crypto._generate_public_key(priv)
            enc = await runtime.call_development_function(_provide_root_password, pub)
            pswd = crypto.decrypt_data(enc, priv)
        except Exception as e:
            # If RFC fails, return empty password (will disable code execution)
            print(f"Warning: Could not get root password via RFC: {e}")
            print("Code execution will be disabled. Set ROOT_PASSWORD in .env to enable it.")
            pswd = ""
    return pswd
    
def _provide_root_password(public_key_pem: str):
    pswd = _get_root_password()
    enc = crypto.encrypt_data(pswd, public_key_pem)
    return enc

def _get_root_password():
    return dotenv.get_dotenv_value(dotenv.KEY_ROOT_PASSWORD) or ""