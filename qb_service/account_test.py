from quickbooks.exceptions import QuickbooksException
from quickbooks.objects.customer import Customer

from quickstart import QuickBooksInvoiceService





from quickstart import QuickBooksInvoiceService
from quickbooks.objects.account import Account

svc = QuickBooksInvoiceService()

accounts = Account.filter(AccountType="Income", qb=svc.qb)
for acct in accounts:
    print(acct.Id, acct.Name)

def main() -> None:
    svc = QuickBooksInvoiceService()

    try:
        customers = Customer.all(qb=svc.qb)
    except QuickbooksException as exc:
        raise RuntimeError(f"Failed to fetch customers: {exc}") from exc

    for customer in customers:
        display_name = getattr(customer, "DisplayName", None) or "<unnamed>"
        print(f"{customer.Id}: {display_name}")



if __name__ == "__main__":
    main()
