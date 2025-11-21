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
from attachments import fetch_messages_with_attachments
import time

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

        installedappflow.from_client_secrets_file(
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







class LabelSort(BaseModel):
    label: Literal["invoice", "none"]




class InvoiceLinePayload(BaseModel):
    item: str
    rate: float
    quantity: float = 1.0
    description: Optional[str] = None


class InvoicePayload(BaseModel):
    vendor_display_name: str
    memo: Optional[str] = None
    items: List[InvoiceLinePayload]
    total_amount: Optional[float] = None

def ai_invoice(message_text: str, attachments: list = None, client: Optional[OpenAI] = None):
     if client is None:
         client = OpenAI()

     context= message_text

     if attachments:
         context +="\n\nAttachments found:\n"
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


     return response.output_parsed.label



def build_invoice_draft(message_text: str, client: Optional[OpenAI] = None, attachments:list=None) -> Optional[InvoiceDraft]:
    if client is None:
        client = OpenAI()

    context= message_text
    if attachments:
        context +="\n\nAttachments found:\n"
        for filename, data in attachments:
            context += f"-{filename}\n"

    response = client.responses.parse(
        model="gpt-4o-2024-08-06",
        input=[
            {
                "role": "system",
                "content": (
                    "Extract structured invoice data from the email. "
                    "Always respond with JSON matching the schema. "
                    "If you do not find invoice information, return an empty items list."
                    "Our company name is Cape Property Pros, and we are always the reciever of the invoice"
                ),
            },
            {"role": "user", "content": context},
        ],
        text_format=InvoicePayload,
    )
    payload = response.output_parsed
    print(f"Payload: {payload}")
    if payload:
        print(f"Items: {payload.items}")
        print(f"Vendor: {payload.vendor_display_name}")


    if not payload or not payload.items:
        return None

    line_items = [
        InvoiceLine(
            item=item.item,
            rate=item.rate,
            quantity=item.quantity,
            description=item.description,
        )
        for item in payload.items
        if item.item and item.rate is not None
    ]
    if not line_items or not payload.vendor_display_name:
        return None

    return InvoiceDraft(
        customer_display_name=payload.vendor_display_name,
        customer_company_name=None,
        memo=payload.memo,
        line_items=line_items,
        total_amount=payload.total_amount,
    )


def main():
    get_or_create_label(service,"ai_checked")
    download_dir = Path("attachments")
    download_dir.mkdir(exist_ok=True)
    qb_service = QuickBooksInvoiceService()
    openai_client = OpenAI()
    messages = list(fetch_messages_with_attachments(max_results=10))

    # Process messages
    for idx, (message_id, subject, message_text, attachments) in enumerate(messages, start=1):
        label = ai_invoice(message_text, attachments, client=openai_client)
        print(f"[{idx}/{len(messages)}] {message_id}: subject -> {subject} label -> {label}")

        if label == "invoice":
            print("hello")
            # Try to build draft from message text first

            # If we have PDF attachments, try to extract invoice from them
            for filename, data in attachments:
                print(f"Attachment: {filename}, Type: {type(data).__name__}, IsString: {isinstance(data, str)}")
                if isinstance(data, str):  # PDF text already extracted
                    print(f"[{idx}/{len(messages)}] {message_id}: processing PDF {filename}")
                    pdf_draft = build_invoice_draft(message_text=data, client=openai_client)
                    if pdf_draft and pdf_draft.line_items:
                        draft = pdf_draft
                        break
                else:  # Binary attachment (non-PDF)
                    target = download_dir / filename
                    target.write_bytes(data)
                    print(f"[{idx}/{len(messages)}] {message_id}: saved attachment {filename}")

            # If we have a valid draft, push to QuickBooks
            if draft and draft.line_items:
                print(f"[{idx}/{len(messages)}] {message_id}: line items:")
                for line in draft.line_items:
                    print("   ", line.model_dump())

                # Calculate and verify total
                calculated_total = sum(line.amount for line in draft.line_items)
                if draft.total_amount is not None:
                    if abs(draft.total_amount - calculated_total) > 0.01:
                        print(f"[{idx}/{len(messages)}] {message_id}: total mismatch (draft={draft.total_amount}, calculated={calculated_total})")
                else:
                    draft.total_amount = calculated_total
                    print(draft.total_amount)
                # Push to QuickBooks
                invoice = qb_service.push_invoice(draft)
                invoice_id = getattr(invoice, "Id", None)
                if invoice_id:
                    print(f"[{idx}/{len(messages)}] {message_id}: QuickBooks invoice created (Id={invoice_id})")
                else:
                    print(f"[{idx}/{len(messages)}] {message_id}: QuickBooks invoice created")
            else:
                print(f"[{idx}/{len(messages)}] {message_id}: no valid invoice data found")


if __name__ == "__main__":
    main()



