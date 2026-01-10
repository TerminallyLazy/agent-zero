import imaplib
import socket
import json

def diag():
    user = ""
    password = ""
    results = []
    
    try:
        socket.setdefaulttimeout(10)
        results.append("Connecting to imap.gmail.com...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        results.append("Connected.")
        
        results.append(f"Attempting login for {user}...")
        mail.login(user, password)
        results.append("Login successful!")
        
        mail.logout()
        return {"success": True, "log": results}
    except imaplib.IMAP4.error as e:
        return {"success": False, "error": f"Auth Error: {str(e)}", "log": results}
    except socket.timeout:
        return {"success": False, "error": "Connection timed out.", "log": results}
    except Exception as e:
        return {"success": False, "error": str(e), "log": results}

if __name__ == "__main__":
    print(json.dumps(diag()))
