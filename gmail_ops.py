import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import sys
import time

def log(msg):
    print(f"[LOG] {msg}", file=sys.stderr)

def login_gmail(username, password):
    try:
        log(f"Connecting to imap.gmail.com...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        log(f"Logging in as {username}...")
        mail.login(username, password)
        log("Login successful.")
        mail.logout()
        return True, "Login successful"
    except Exception as e:
        log(f"Login failed: {str(e)}")
        return False, str(e)

def fetch_inbox(username, password, limit=10):
    try:
        log(f"Connecting to imap.gmail.com...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        log(f"Logging in as {username}...")
        mail.login(username, password)
        log("Selecting inbox...")
        mail.select("inbox")
        
        log("Searching for messages...")
        status, messages = mail.search(None, "ALL")
        email_ids = messages[0].split()[-limit:][::-1]
        log(f"Found {len(email_ids)} messages.")
        
        inbox_data = []
        for e_id in email_ids:
            log(f"Fetching message {e_id.decode()}...")
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes): subject = subject.decode(encoding or "utf-8")
                    
                    from_, encoding = decode_header(msg.get("From"))[0]
                    if isinstance(from_, bytes): from_ = from_.decode(encoding or "utf-8")
                    
                    snippet = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                payload = part.get_payload(decode=True)
                                if payload: snippet = payload.decode(errors='ignore')[:100] + "..."
                                break
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload: snippet = payload.decode(errors='ignore')[:100] + "..."

                    inbox_data.append({
                        "from": from_,
                        "subject": subject,
                        "snippet": snippet,
                        "date": msg.get("Date")
                    })
        log("Logging out...")
        mail.logout()
        return True, inbox_data
    except Exception as e:
        log(f"Fetch failed: {str(e)}")
        return False, str(e)

def send_email(username, password, to, subject, body):
    try:
        log(f"Preparing email to {to}...")
        msg = MIMEMultipart()
        msg['From'] = username
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        log("Connecting to smtp.gmail.com...")
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        log(f"Logging in as {username}...")
        server.login(username, password)
        log("Sending message...")
        server.send_message(msg)
        server.quit()
        log("Email sent successfully.")
        return True, "Email sent successfully"
    except Exception as e:
        log(f"Send failed: {str(e)}")
        return False, str(e)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(json.dumps({"success": False, "message": "Missing arguments"}))
        sys.exit(1)
        
    action = sys.argv[1]
    user = sys.argv[2]
    pw = sys.argv[3]
    
    if action == "login":
        success, msg = login_gmail(user, pw)
        print(json.dumps({"success": success, "message": msg}))
    elif action == "fetch":
        success, data = fetch_inbox(user, pw)
        print(json.dumps({"success": success, "data": data}))
    elif action == "send":
        if len(sys.argv) < 7:
            print(json.dumps({"success": False, "message": "Missing send arguments"}))
            sys.exit(1)
        to = sys.argv[4]
        subject = sys.argv[5]
        body = sys.argv[6]
        success, msg = send_email(user, pw, to, subject, body)
        print(json.dumps({"success": success, "message": msg}))
