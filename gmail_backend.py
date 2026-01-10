import imaplib, smtplib, email, json, socket, sys
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

socket.setdefaulttimeout(30)

def get_val(header):
    if not header: return "(No Subject)"
    decoded = decode_header(header)
    parts = []
    for val, encoding in decoded:
        if isinstance(val, bytes):
            parts.append(val.decode(encoding or "utf-8", errors="replace"))
        else: parts.append(str(val))
    return "".join(parts)

def fetch_inbox(user, password, limit=15):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.select("INBOX")
        _, msgs = mail.search(None, "ALL")
        ids = msgs[0].split()[-limit:][::-1]
        inbox = []
        for i in ids:
            _, data = mail.fetch(i, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload: body = payload.decode(errors="replace")
                        break
            else:
                payload = msg.get_payload(decode=True)
                if payload: body = payload.decode(errors="replace")
            inbox.append({
                "id": i.decode(),
                "from": get_val(msg["From"]),
                "subject": get_val(msg["Subject"]),
                "date": msg["Date"],
                "body": body
            })
        with open("inbox.json", "w") as f: json.dump(inbox, f)
        print(f"SUCCESS: Fetched {len(inbox)} messages")
    except Exception as e:
        print(f"ERROR: {str(e)}")

def send_email(user, password, to, subject, body):
    try:
        msg = MIMEMultipart()
        msg["From"] = user
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(user, password)
        server.send_message(msg)
        server.quit()
        print(f"SUCCESS: Email sent to {to}")
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python gmail_backend.py <action> <user> <password> [args...]")
        sys.exit(1)
    action = sys.argv[1]
    user = sys.argv[2]
    password = sys.argv[3]
    if action == "fetch":
        fetch_inbox(user, password)
    elif action == "send":
        send_email(user, password, sys.argv[4], sys.argv[5], sys.argv[6])
    else:
        print("Invalid action")
        sys.exit(1)
    print("Invalid action")
    sys.exit(1)
