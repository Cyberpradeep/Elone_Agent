import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from shared.providers.base import BaseProvider

class SystemOpsProvider(BaseProvider):
    
    @property
    def provider_name(self) -> str:
        return "system"

    def send_email(self, inputs: dict) -> dict:
        to_email = inputs.get("to_email")
        subject = inputs.get("subject")
        body = inputs.get("body")
        
        smtp_server = os.environ.get("SMTP_SERVER", "sandbox.smtp.mailtrap.io")
        try:
            smtp_port = int(os.environ.get("SMTP_PORT", 2525))
        except ValueError:
            smtp_port = 2525
        username = os.environ.get("SMTP_USERNAME")
        password = os.environ.get("SMTP_PASSWORD")
        
        try:
            msg = MIMEMultipart()
            msg['From'] = username or "support@company.com"
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            if username and password:
                server.login(username, password)
            server.sendmail(msg['From'], to_email, msg.as_string())
            server.quit()
            return {"status": "ok", "message": f"Email sent successfully to {to_email}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to send email: {str(e)}"}
