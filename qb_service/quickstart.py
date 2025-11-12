import os
from typing import List, Optional

from intuitlib.client import AuthClient
from pydantic import BaseModel, Field
from quickbooks import QuickBooks
from quickbooks.exceptions import QuickbooksException
from quickbooks.objects.account import Account
from quickbooks.objects.customer import Customer
from quickbooks.objects.detailline import SalesItemLine, SalesItemLineDetail
from quickbooks.objects.invoice import Invoice
from quickbooks.objects.item import Item

class InvoiceLine(BaseModel):
    item_name: str
    rate: float
    quantity: float = Field(default=1.0, gt=0)
    description: Optional[str] = None

    @property
    def amount(self) -> float:
        """Total dollar amount for this line item."""
        return self.rate * self.quantity


class InvoiceDraft(BaseModel):
    customer_display_name: str
    customer_company_name: Optional[str] = None
    line_items: List[InvoiceLine]
    memo: Optional[str] = None
    total_amount: Optional[float] = None


class QuickBooksInvoiceService:
    """High-level helper for creating invoices via the QuickBooks SDK."""

    def __init__(self) -> None:
        self.auth_client = AuthClient(
            client_id=self._require_env("CLIENT_ID"),
            client_secret=self._require_env("CLIENT_SECRET"),
            environment=os.getenv("QB_ENVIRONMENT", "sandbox"),
            redirect_uri=os.getenv("QB_REDIRECT_URI", "http://localhost:8000/callback"),
        )
        self.qb = QuickBooks(
            auth_client=self.auth_client,
            refresh_token=self._require_env("QB_REFRESH_TOKEN"),
            company_id=self._require_env("QB_REALM_ID"),
        )
        self.qb.session.headers.update({"Accept-Encoding": "identity"})
        try:
            self.income_account_ref = self._load_account_ref(
                value_key="QB_INCOME_ACCOUNT_ID",
                name_key="QB_INCOME_ACCOUNT_NAME",
                description="item income account",
                required=True,
                default_name="Inventory",
            )
        except RuntimeError as exc:
            account_name = os.getenv("QB_INCOME_ACCOUNT_NAME")
            if account_name and "No QuickBooks account named" in str(exc):
                account = self.ensure_account(
                    name=account_name,
                    account_type=os.getenv("QB_INCOME_ACCOUNT_TYPE", "Income"),
                    account_sub_type=os.getenv("QB_INCOME_ACCOUNT_SUBTYPE"),
                    description=os.getenv("QB_INCOME_ACCOUNT_DESCRIPTION"),
                    acct_num=os.getenv("QB_INCOME_ACCOUNT_ACCTNUM"),
                    tax_code_id=os.getenv("QB_INCOME_ACCOUNT_TAXCODE_ID"),
                )
                self.income_account_ref = account.to_ref()
            else:
                raise
        self.expense_account_ref = self._load_account_ref(
            value_key="QB_EXPENSE_ACCOUNT_ID",
            name_key="QB_EXPENSE_ACCOUNT_NAME",
            description="item expense account",
            required=False,
        )

    def ensure_customer(self, display_name: str, company_name: Optional[str]) -> Customer:
        existing = Customer.filter(DisplayName=display_name, qb=self.qb)
        if existing:
            return existing[0]

        customer = Customer()
        customer.DisplayName = display_name
        if company_name:
            customer.CompanyName = company_name
        customer.save(qb=self.qb)
        return customer

    def ensure_item(self, item_name: str, rate: float) -> Item:
        existing = Item.filter(Name=item_name, qb=self.qb)
        if existing:
            return existing[0]

        item = Item()
        item.Name = item_name
        item.UnitPrice = rate
        item.Type = "Service"  # adjust if you need other item types
        item.IncomeAccountRef = self.income_account_ref
        if self.expense_account_ref:
            item.ExpenseAccountRef = self.expense_account_ref
        item.save(qb=self.qb)
        return item

    def push_invoice(self, draft: InvoiceDraft) -> Invoice:
        customer = self.ensure_customer(
            draft.customer_display_name,
            draft.customer_company_name,
        )

        invoice = Invoice()
        invoice.CustomerRef = customer.to_ref()
        if draft.memo:
            invoice.PrivateNote = draft.memo
        if draft.total_amount is not None:
            try:
                invoice.TotalAmt = float(draft.total_amount)
            except (TypeError, ValueError):
                pass

        lines: List[SalesItemLine] = []
        for line in draft.line_items:
            item = self.ensure_item(line.item_name, line.rate)

            qb_line = SalesItemLine()
            qb_line.Amount = line.amount
            qb_line.DetailType = "SalesItemLineDetail"
            if line.description:
                qb_line.Description = line.description

            detail = SalesItemLineDetail()
            detail.ItemRef = item.to_ref()
            detail.UnitPrice = line.rate
            detail.Qty = line.quantity
            qb_line.SalesItemLineDetail = detail

            lines.append(qb_line)

        invoice.Line = lines
        try:
            invoice.save(qb=self.qb)
        except QuickbooksException as exc:
            raise RuntimeError(f"Failed to create invoice in QuickBooks: {exc}") from exc
        return invoice

    def ensure_account(
        self,
        *,
        name: str,
        account_type: Optional[str] = None,
        account_sub_type: Optional[str] = None,
        description: Optional[str] = None,
        acct_num: Optional[str] = None,
        tax_code_id: Optional[str] = None,
        active: bool = True,
    ) -> Account:
        """Return an account matching ``name``; create it if it does not exist."""
        if '"' in name or ":" in name:
            raise ValueError('Account names cannot contain double quotes (") or colon (:).')

        try:
            matches = Account.filter(Name=name, qb=self.qb)
        except QuickbooksException as exc:
            raise RuntimeError(f"Failed to lookup account '{name}' in QuickBooks: {exc}") from exc
        if matches:
            return matches[0]

        if not account_type and not account_sub_type:
            raise ValueError("Provide account_type or account_sub_type to create a new account.")

        account = Account()
        account.Name = name
        if account_type:
            account.AccountType = account_type
        if account_sub_type:
            account.AccountSubType = account_sub_type
        if acct_num:
            if ":" in acct_num:
                raise ValueError("Account numbers cannot contain colon (:).")
            account.AcctNum = acct_num
        if description:
            account.Description = description
        if tax_code_id:
            account.TaxCodeRef = {"value": tax_code_id}
        account.Active = active

        try:
            account.save(qb=self.qb)
        except QuickbooksException as exc:
            raise RuntimeError(f"Failed to create QuickBooks account '{name}': {exc}") from exc
        return account

    @staticmethod
    def _require_env(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise RuntimeError(f"Environment variable {key} is required for QuickBooks access")
        return value

    def _load_account_ref(
        self,
        *,
        value_key: str,
        name_key: str,
        description: str,
        required: bool,
        default_name: Optional[str] = None,
    ) -> Optional[dict]:
        account_id = os.getenv(value_key)
        if account_id:
            try:
                account = Account.get(account_id, qb=self.qb)
            except QuickbooksException as exc:
                raise RuntimeError(
                    f"Failed to load {description} using {value_key}={account_id}: {exc}"
                ) from exc
            return account.to_ref()

        account_name = os.getenv(name_key)
        if account_name:
            try:
                matches = Account.filter(Name=account_name, qb=self.qb)
            except QuickbooksException as exc:
                raise RuntimeError(
                    f"Failed to look up {description} named '{account_name}': {exc}"
                ) from exc
            if not matches:
                raise RuntimeError(
                    f"No QuickBooks account named '{account_name}' found for {description}."
                )
            return matches[0].to_ref()

        if default_name:
            try:
                matches = Account.filter(Name=default_name, qb=self.qb)
            except QuickbooksException as exc:
                raise RuntimeError(
                    f"Failed to look up default {description} named '{default_name}': {exc}"
                ) from exc
            if matches:
                return matches[0].to_ref()
            if required:
                raise RuntimeError(
                    f"Default {description} '{default_name}' not found in QuickBooks."
                )

        if required:
            raise RuntimeError(
                f"Set {value_key} or {name_key} to identify the {description}."
            )
        return None
def main():
    QuickBooksInvoiceService()
if __name__ == "__main__":
    main()
