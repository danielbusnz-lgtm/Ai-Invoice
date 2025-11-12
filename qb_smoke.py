from openai import OpenAI
from qb_service.quickstart import QuickBooksInvoiceService
from quickstart import build_invoice_draft

FAKE_EMAIL = """
Subject: Invoice 12345

Hi Daniel,

Thank you for your business. Invoice 12345
Customer: Acme Corp
Line 1: Consulting Services - $150/hour x 10 hours
Memo: July engagement

Regards,
Vendor Co
  """
client = OpenAI()  # make sure your OpenAI key is set
draft = build_invoice_draft(FAKE_EMAIL, client=client)
print("Draft:", draft)


