import os.path
from enum import Enum
from pydantic import BaseModel
import base64
from bs4 import BeautifulSoup
from pydantic import BaseModel
from openai import OpenAI
import os
from typing import List, Literal, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pathlib import Path
from pdf_parser import extract_text_from_pdf
from quickstart1 import InvoiceDraft, InvoiceLine, QuickbooksInvoiceService
import pdfplumber


# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.modify"
]


def load_creds():
  creds = None
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
  # If there are no (valid) credentials available, let the user log in.
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:

        flow = InstalledAppFlow.from_client_secrets_file(
          "credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open("token.json", "w") as token:
      token.write(creds.to_json())
  return creds
service = build("gmail", "v1", credentials=load_creds())


#decode the emails using utf-8
def decode_data(encoded):
      if not encoded:
          return None
      padded = encoded + "=" * (-len(encoded) % 4)
      return base64.urlsafe_b64decode(padded).decode("utf-8")


def decode_bytes(encoded: str) -> bytes:
      if not encoded:
          return b""
      padded = encoded + "=" * (-len(encoded) % 4)
      return base64.urlsafe_b64decode(padded)




#make sure there is a proper label
def get_or_create_label(service, label_name):
      """Get label ID by name, or create if it doesn't exist"""
      # List all labels
      results = service.users().labels().list(userId='me').execute()
      labels = results.get('labels', [])

      # Check if label exists
      for label in labels:
          if label['name'].lower() == label_name.lower():
              return label['id']

      # Create label if it doesn't exist
      label_object = {
          'name': label_name,
          'labelListVisibility': 'labelShow',
          'messageListVisibility': 'show'
      }
      created_label = service.users().labels().create(
          userId='me',
          body=label_object
      ).execute()

      return created_label['id']




#get the message and its attachment if provided
def fetch_messages_with_attachments(max_results: int = 10, query: Optional[str] = None):
    list_params = {
        "userId": "me",
        "maxResults": max_results,
        "q":" -label:ai_checked"
    }
    results = service.users().messages().list(**list_params).execute()
    for ref in results.get("messages", []):
        msg = service.users().messages().get(
            userId="me",
            id=ref["id"],
            format="full",
        ).execute()
        payload = msg.get("payload", {})
        headers = {
            h.get("name", "").lower(): h.get("value", "")
            for h in payload.get("headers", [])
        }
        subject = headers.get("subject", "")
        body = payload.get("body", {})
        raw_data = body.get("data", "")
        label_id = get_or_create_label(service, "ai_checked")
        service.users().messages().modify(
        userId='me',
        id=ref["id"],
        body={'addLabelIds': [label_id]}
        ).execute()

        if not raw_data:
            for part in payload.get("parts", []):
                raw_data = part.get("body", {}).get("data", "")
                if raw_data:
                    break

        message_text = ""
        if raw_data:
            decoded = decode_data(raw_data)
            if decoded:
                soup = BeautifulSoup(decoded, "html.parser")
                message_text = soup.get_text(separator="", strip=True)




        attachments = []
        parts_to_inspect = [payload]
        while parts_to_inspect:
            part = parts_to_inspect.pop()
            filename = part.get("filename")
            part_body = part.get("body", {})
            inline_data = part_body.get("data")
            if filename and inline_data:
                binary_data = decode_bytes(inline_data)
                if filename.lower().endswith('.pdf'):
                    temp_path = Path("attachments")/filename
                    temp_path.parent.mkdir(exist_ok=True)
                    temp_path.write_bytes(binary_data)
                    pdf_text = extract_text_from_pdf(temp_path)
                    attachments.append((filename, pdf_text))
                else:
                    attachments.append((filename, binary_data))
                continue    
                

            attachment_id = part_body.get("attachmentId")
            if filename and attachment_id:
                attachment = service.users().messages().attachments().get(
                    userId="me",
                    messageId=ref["id"],
                    id=attachment_id,
                ).execute()
                binary_data = decode_bytes(attachment.get("data", ""))
                if filename.lower().endswith('.pdf'):
                    temp_path = Path("attachments")/filename
                    temp_path.parent.mkdir(exist_ok=True)
                    temp_path.write_bytes(binary_data)
                    pdf_text = extract_text_from_pdf(temp_path)
                    attachments.append((filename, pdf_text))
                else:
                    attachments.append((filename, binary_data))
               

            parts_to_inspect.extend(part.get("parts", []))

        yield ref["id"], subject, message_text, attachments



class LabelSort(BaseModel):
    label: Literal["invoice", "none"]
   



def ai_invoice(message_text: str,attachments:list = None, client: Optional[OpenAI] = None):
     context= message_text
     print(attachments)
     if attachments:
         context +="\n\nAttachments found:\n"
         print(context)
         for filename, data in attachments:
             context += f"- {filename}\n"
     response = client.responses.parse(
        model="gpt-4o-2024-08-06",
         input=[
        {"role": "system", "content": "Extract wheter or not the following email is an invoice or not. If it is an email return: invoice and if not return: none."},
        {
            "role": "user",
            "content": context,
        },
    ],
        text_format=LabelSort,  # your structured output class
    )


     return response.output_parsed



def main():
    get_or_create_label(service,"ai_checked")
    download_dir = Path("attachments")
    download_dir.mkdir(exist_ok=True)
    openai_client = OpenAI()

    # Iterate through the generator
    for message_id, subject, message_text, attachments in fetch_messages_with_attachments(max_results=10):
        print(f"\n--- Message ID: {message_id} ---")
        print(f"Subject: {subject}")
        print(f"Message Text: {message_text[:100]}...")  # First 100 chars

        # Check attachments
        if attachments:
            print(f"Found {len(attachments)} attachment(s)")
            for filename, data in attachments:
                print(f"  - {filename}")
                if isinstance(data, str):  # PDF text
                    print(f"    Text preview: {data[:100]}...")
                else:  # Binary data
                    print(f"    Binary data: {len(data)} bytes")



        # Optional: Call AI to classify
        label = ai_invoice(message_text, attachments, client=openai_client)
        print(f"AI Label: {label}")

















if __name__ == "__main__":
    main()



