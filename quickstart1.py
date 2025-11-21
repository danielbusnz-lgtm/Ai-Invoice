from quickbooks.objects.customer import Customer
from quickbooks import *
from quickbooks.objects.vendor import Vendor
from quickbooks.objects.bill import Bill
from quickbooks.objects.account import Account
from quickbooks.objects.item import Item
from quickbooks.objects.payment import Payment
from pydantic import BaseModel, Field
from typing import List, Optional
import os
from difflib import SequenceMatcher
from quickbooks.objects.detailline import AccountBasedExpenseLine, AccountBasedExpenseLineDetail
from quickbooks.objects.base import Ref
from intuitlib.client import AuthClient
from dotenv import load_dotenv
load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
ENVIRONMENT = os.getenv("INTUIT_ENVIRONMENT"," production")

class InvoiceLine(BaseModel):
    item: str
    rate: float
    quantity: float = Field(default=1.0, gt=0)
    description: Optional[str] = None

    @property
    def amount(self) -> float:
        return self.rate * self.quantity
class InvoiceDraft(BaseModel):
    customer_display_name: str
    customer_company_name: Optional[str] = None
    line_items: List[InvoiceLine]
    memo: Optional[str] = None
    total_amount: Optional[float] = None



class QuickbooksInvoiceService:
    def __init__(self) -> None:
        self.auth_client = AuthClient(
            client_id=os.getenv('CLIENT_ID'),
            client_secret=os.getenv('CLIENT_SECRET'),
            environment='production',
            redirect_uri='https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl',
        )

        self.qb_client = QuickBooks(
            auth_client=self.auth_client,
            refresh_token=os.getenv('QB_REFRESH_TOKEN'),
            company_id=os.getenv('QB_REALM_ID'),
	    )


    def ensure_vendors(display_name: str, company_name: Optional[str]=None) -> Vendor:
        all_vendors=Vendor.all(qb =self.qb_client)
       
        for vendor in all_vendors:
            if vendor.DisplayName and vendor.DisplayName.lower().strip() == display_name.lower().strip():
                print(f"found a match'{vendor.DisplayName}'")
                return vendor    
        best_match= None
        best_ratio= 0.8
        for vendor in all_vendors:
            if vendor.DisplayName:
                ratio= SequenceMatcher(None, vendor.DisplayName.lower(),display_name.lower()).ratio()
                if ratio> best_ratio:
                    best_ratio= ratio
                    best_match=vendor
        if best_match:
            print(f"found the best match'{best_match}'")
            return best_match
       
        else:
            vendor = Vendor()
            vendor.DisplayName= display_name
            if company_name:
                vendor.CompanyName =company_name
            vendor.save(qb=self.qb_client)
            print("made new vendor")
            print(f"'{vendor.DisplayName}'")
            return vendor

    def push_invoice(self,customer_display_name,customer_company_name, memo, line_items,total_amount) -> Bill:
        bill = Bill()
        line = AccountBasedExpenseLine()
       # for line in line_items:
            #line.name=item_name
           # item.rate=rate
          #  item.quantity=
        line.Amount = 200
        line.DetailType = "AccountBasedExpenseLineDetail"
        account_ref = Ref()
        account_ref.type = "Account"
        account_ref.value = 1
        line.AccountBasedExpenseLineDetail = AccountBasedExpenseLineDetail()
        line.AccountBasedExpenseLineDetail.AccountRef = account_ref
        bill.Line.append(line)
        vendor = Vendor.all(max_results=1, qb=self.qb_client)[0]
        bill.VendorRef = vendor.to_ref()
        bill.save(qb=self.qb_client)
        query_bill = Bill.get(bill.Id, qb=self.qb_client)
        print(bill.save(qb=self.qb_client))
        print(query_bill)
        print(line.Amount)
        print(line.DetailType)
        
        print(account_ref.type)
        print(vendor) 

def main():
    sample_message = """
    Invoice from ABC Supply Company

    Please process payment for the following items:

    Item 1: Office Supplies - Box of pens (10 boxes) @ $15.00 each = $150.00
    Item 2: Printer Paper (5 reams) @ $8.50 each = $42.50
    Item 3: Desk organizers (3 units) @ $22.00 each = $66.00

    Subtotal: $258.50

    Notes: Delivery scheduled for next Tuesday. Please reference PO#12345

    Vendor: ABC Supply Company
    Contact: John Smith
    Email: john@abcsupply.com
    """

    from quickstart  import build_invoice_draft
    build_invoice_draft(sample_message)
if __name__=="__main__":
    main()
    # service = QuickbooksInvoiceService()
    # service.push_invoice()
