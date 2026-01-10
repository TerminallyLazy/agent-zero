import imaplib
import email
from email.header import decode_header
import json
import socket

def fetch_emails():
    user = ""
    password = ""
    
    try:
        socket.setdefaulttimeout(10)
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.select("inbox")
        
        status, messages = mail.search(None, 'ALL')
        if status != 'OK':
            return {"success": False, "error": "Could not search inbox"}

        ids = messages[0].split()[-5:][::-1]
        inbox = []
        
        for e_id in ids:
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes): subject = subject.decode(encoding or "utf-8")
                    
                    from_, encoding = decode_header(msg.get("From"))[0]
                    if isinstance(from_, bytes): from_ = from_.decode(encoding or "utf-8")
                    
                    inbox.append({
                        "id": e_id.decode(),
                        "from": from_,
                        "subject": subject,
                        "date": msg.get("Date")
                    })
        
        mail.logout()
        return {"success": True, "emails": inbox}

    except imaplib.IMAP4.error as e:
        err_str = str(e)
        if "Application-specific password required" in err_str:
            return {"success": False, "error": "APP_PASSWORD_REQUIRED"}
        return {"success": False, "error": err_str}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    print(json.dumps(fetch_emails()))
