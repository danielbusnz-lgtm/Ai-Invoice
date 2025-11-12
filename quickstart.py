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
from qb_service.quickstart import InvoiceDraft, InvoiceLine, QuickBooksInvoiceService



# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.modify"
]





def load_creds():
  """Shows basic usage of the Gmail API.
  Lists the user's Gmail labels.
  """
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






def get_message_id(max_results: int = 10):
    service = build("gmail", "v1", credentials=load_creds())
    message_ids = []
    results = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        q="is:unread"
    ).execute()
    message_refs = results.get("messages", [])
    print(f"Received {len(message_refs)} message reference(s).")
    for ref in message_refs:
        message_ids.append(ref["id"])
    return message_ids



#grab all the emails and run them through the decorder
def get_messages(max_results: int = 10):
    service = build("gmail", "v1", credentials=load_creds())
    message_text = []
    results = service.users().messages().list(
        userId="me",
        maxResults=max_results,
    ).execute()
    message_refs = results.get("messages", [])
    for idx, ref in enumerate(message_refs, start=1):
        msg = service.users().messages().get(
            userId="me",
            id=ref["id"],
            format="full",
        ).execute()
        payload = msg.get("payload", {})
        body = payload.get("body", {})
        raw_data = body.get("data", "")

        if not raw_data:
            for parts in payload.get("parts", []):
                raw_data = parts.get("body", {}).get("data", "")
                if raw_data:
                    break

        decoded = decode_data(raw_data)
        if not decoded:
            print(f"[{idx}/{len(message_refs)}] {ref['id']}: no decodable body, skipping.")
            continue

        soup = BeautifulSoup(decoded, "html.parser")
        message_text.append((ref["id"], soup.get_text(separator="", strip=True)))
        print(f"[{idx}/{len(message_refs)}] {ref['id']}: message decoded.")
    return message_text



#Get the email attachment
def get_attachment(max_results: int = 10):
    service = build("gmail", "v1", credentials=load_creds())

    results = service.users().messages().list(userId="me", maxResults=max_results,).execute()

    for ref in results.get("messages",[]):
        msg = service.users().messages().get(
            userId="me",
            id=ref["id"],
            format="full",
        ).execute()
        payload = msg.get("payload", {})
        parts_to_inspect = [payload]

        while parts_to_inspect:
            part = parts_to_inspect.pop()
            filename = part.get("filename")
            body = part.get("body", {})

            inline_data = body.get("data")
            if filename and inline_data:
                yield filename, decode_bytes(inline_data)
                continue

            attachment_id = body.get("attachmentId")
            if filename and attachment_id:
                attachment = service.users().messages().attachments().get(
                    userId="me",
                    messageId=ref["id"],
                    id=attachment_id,
                ).execute()
                yield filename, decode_bytes(attachment.get("data", ""))

            parts_to_inspect.extend(part.get("parts", []))


def fetch_messages_with_attachments(max_results: int = 10, query: Optional[str] = None):
    service = build("gmail", "v1", credentials=load_creds())

    list_params = {
        "userId": "me",
        "maxResults": max_results,
        "q":"is:unread",
    }
    if query:
        list_params["q"] = query

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
                attachments.append((filename, decode_bytes(inline_data)))
                continue

            attachment_id = part_body.get("attachmentId")
            if filename and attachment_id:
                attachment = service.users().messages().attachments().get(
                    userId="me",
                    messageId=ref["id"],
                    id=attachment_id,
                ).execute()
                attachments.append((filename, decode_bytes(attachment.get("data", ""))))

            parts_to_inspect.extend(part.get("parts", []))

        yield ref["id"], subject, message_text, attachments

class LabelSort(BaseModel):
    label: Literal["invoice", "none"]

label_lookup = {
    "invoice": "Invoice",
    "none": "",
}


class InvoiceLinePayload(BaseModel):
    item_name: str
    rate: float
    quantity: float = 1.0
    description: Optional[str] = None


class InvoicePayload(BaseModel):
    customer_display_name: str
    customer_company_name: Optional[str] = None
    memo: Optional[str] = None
    items: List[InvoiceLinePayload]
    total_amount: Optional[float] = None

def ai_invoice(message_text: str, client: Optional[OpenAI] = None):
    if client is None:
        client = OpenAI()

    response = client.responses.parse(
        model="gpt-4o-2024-08-06",
         input=[
        {"role": "system", "content": "Extract wheter or not the following email is an invoice or not. If it is an email return: Invoice and if not return: none. Those with attachments should be labeled as invoices"},
        {
            "role": "user",
            "content": "{message_text}",
        },
    ],
        text_format=LabelSort,  # your structured output class
    )


    chosen_label = response.output_parsed.label.strip().lower()
    return chosen_label




def build_invoice_draft(message_text: str, client: OpenAI) -> Optional[InvoiceDraft]:
    response = client.responses.parse(
        model="gpt-4o-2024-08-06",
        input=[
            {
                "role": "system",
                "content": (
                    "Extract structured invoice data from the email. "
                    "Always respond with JSON matching the schema. "
                    "If you do not find invoice information, return an empty items list."
                ),
            },
            {"role": "user", "content": message_text},
        ],
        text_format=InvoicePayload,
    )
    payload = response.output_parsed
    if not payload or not payload.items:
        return None

    line_items = [
        InvoiceLine(
            item_name=item.item_name,
            rate=item.rate,
            quantity=item.quantity,
            description=item.description,
        )
        for item in payload.items
        if item.item_name and item.rate is not None
    ]
    if not line_items or not payload.customer_display_name:
        return None
    return InvoiceDraft(
        customer_display_name=payload.customer_display_name,
        customer_company_name=payload.customer_company_name,
        memo=payload.memo,
        line_items=line_items,
        total_amount=payload.total_amount,
    )


def main():
    download_dir = Path("attachments")
    download_dir.mkdir(exist_ok=True)
    qb_service = QuickBooksInvoiceService()
    openai_client = OpenAI()
    messages = list(
            fetch_messages_with_attachments(max_results=10, query="in:inbox -label:Read")
        )
    label_service = None

    invoice_label_id: Optional[str] = None

    label_service = build("gmail", "v1", credentials=load_creds())


    for idx, (message_id, subject, message_text, attachments) in enumerate(messages, start=1):
        label = ai_invoice(message_text, client=openai_client)
        print(f"[{idx}/{len(messages)}] {message_id}: subject -> {subject} label -> {label}")

        if label == "Invoice":
            for filename, data in attachments:
                target = download_dir / filename
                target.write_bytes(data)
                print(f"[{idx}/{len(messages)}] {message_id}: saved attachment {filename} to {target}")

                if target.suffix.lower() != ".pdf":
                    pdf_text = extract_text_from_pdf(target)
                    draft = build_invoice_draft(pdf_text, client=openai_client)
                    calculated_total = sum(line.amount for line in draft.line_items)

                    if draft.total_amount is not None:
                        if abs(draft.total_amount - calculated_total) > 0.01:
                            print(f"[{idx}/{len(messages)}] {message_id}: "f"total mismatch (draft={draft.total_amount}, calculated={calculated_total})")
                    else:
                        draft.total_amount = calculated_total

                        print(f"[{idx}/{len(messages)}] {message_id}: line items parsed from {filename}:")
                else:
                    print("no invoice")
                for line in draft.line_items:
                    print("   ", line.model_dump())

                    invoice = qb_service.push_invoice(draft)


                    invoice_id = getattr(invoice, "Id", None)

                    draft = build_invoice_draft(message_text, client=openai_client)
                    calculated_total = sum(line.amount for line in draft.line_items)
                    if draft.total_amount is not None:
                        if abs(draft.total_amount - calculated_total) > 0.01:
                            print(
                                f"[{idx}/{len(messages)}] {message_id}: "
                                f"total mismatch (draft={draft.total_amount}, calculated={calculated_total})"
                             )
                    else:
                        draft.total_amount = calculated_total

                    print(f"[{idx}/{len(messages)}] {message_id}: line items parsed from message body:")
                    for line in draft.line_items:
                        print("   ", line.model_dump())

                        invoice = qb_service.push_invoice(draft)
                        invoice_id = getattr(invoice, "Id", None)
                    if invoice_id:
                        print(f"[{idx}/{len(messages)}] {message_id}: QuickBooks invoice created (Id={invoice_id}).")
                    else:
                        print(f"[{idx}/{len(messages)}] {message_id}: QuickBooks invoice created.")


if __name__ == "__main__":
    main()



