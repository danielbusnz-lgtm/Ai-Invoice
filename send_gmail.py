from quickstart import load_creds
from googleapiclient.discovery import build
from email.message import EmailMessage
import base64
from google.auth.transport.requests import Request

creds= load_creds()

service = build("gmail", "v1", credentials=load_creds())


def test_invoice():
    msg = EmailMessage()
    msg["Subject"] = "invoice"
    msg["From"] = "danielbusnz@gmail.com"
    msg["To"] = "danielbusnz@gmail.com"
    msg.set_content("Please see the attachment.")
    print("enter attachment filename")
    attachments=input()
    if attachments:
            print(attachments)
            with open(attachments, 'rb') as content_file:
                content = content_file.read()
                msg.add_attachment(content, maintype='application', subtype= (attachments.split('.')[1]), filename=attachments)

    encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent= service.users().messages().send(
        userId="me",
        body={"raw":encoded},
    ).execute()
    print(sent)





def main():
    test_invoice()
main()
