from quickstart import load_creds
from googleapiclient.discovery import build
from email.message import EmailMessage
import base64
from google.auth.transport.requests import Request
import mimetypes

service = build("gmail", "v1", credentials=load_creds())

def send_attachment():
    msg = EmailMessage()
    print("enter subject")
    subject=input()
    msg['Subject'] = subject
    msg['From'] = "danielbusnz@gmail.com"
    msg['To'] = "danielbusnz@gmail.com"
    print("input content")
    content=input()
    msg.set_content(content)
    print("insert the file path")
    attachment_path = input().strip('"')


    mime_type, _ =mimetypes.guess_type(attachment_path)
    if mime_type:
        maintype, subtype= mime_type.split('/',1)
    else:
        maintype, subtype= 'application', 'octet-stream'

    with open(attachment_path, 'rb') as f:
        file_data = f.read()
        msg.add_attachment(file_data, maintype=maintype, subtype=subtype,filename=attachment_path)
    encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent= service.users().messages().send(
        userId="me",
        body={"raw":encoded},
    ).execute()
    print(sent)
def main():
    send_attachment()
main()
