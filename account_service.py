from quickbooks.objects.account import Account
from qb_service.quickstart import QuickBooksInvoiceService

svc = QuickBooksInvoiceService()   # grabs AuthClient/QuickBooks with your env vars

account = Account()

print(svc)
