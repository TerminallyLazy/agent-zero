import imaplib
import email
from email.header import decode_header
import json
import socket

def fetch_emails():
    user = ""
    password = ""
    
    try:
        # Set a strict timeout for the connection
        socket.setdefaulttimeout(15)
        
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.select("inbox")
        
        status, messages = mail.search(None, 'ALL')
        if status != 'OK':
            return {"success": False, "error": "Could not search inbox"}

        # Get latest 5 emails
        ids = messages[0].split()[-5:][::-1]
        inbox = []
        
        for e_id in ids:
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Decode Subject
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes): subject = subject.decode(encoding or "utf-8")
                    
                    # Decode From
                    from_, encoding = decode_header(msg.get("From"))[0]
                    if isinstance(from_, bytes): from_ = from_.decode(encoding or "utf-8")
                    
                    inbox.append({
                        "id": e_id.decode(),
                        "from": from_,
                        "subject": subject,
                        "date": msg.get("Date")
                    })
        return {"success": True, "emails": inbox}

    except imaplib.IMAP4.error as e:
        err_msg = str(e)
        if "Application-specific password required" in err_msg:
            return {"success": False, "error": "APP_PASSWORD_REQUIRED"}
        return {"success": False, "error": f"Authentication failed: {err_msg}"}
    except socket.timeout:
        return {"success": False, "error": "Connection timed out. Please check your network or try again."}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    print(json.dumps(fetch_emails()))
