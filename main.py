import os
from typing import List, Optional
from difflib import SequenceMatcher
from intuitlib.client import AuthClient
from pydantic import BaseModel, Field
from quickbooks import QuickBooks
from quickbooks.exceptions import QuickbooksException
from quickbooks.objects.account import Account
from quickbooks.objects.vendor import Vendor
from quickbooks.objects.detailline import AccountBasedExpenseLine, AccountBasedExpenseLineDetail
from quickbooks.objects.bill import Bill
from quickbooks.objects.customer import Customer
from quickbooks.objects.customer import Customer


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
            environment=os.getenv("QB_ENVIRONMENT", "production"),
            redirect_uri=os.getenv("QB_REDIRECT_URI", " https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"),
        )
        self.qb = QuickBooks(
            auth_client=self.auth_client,
            refresh_token=self._require_env("QB_REFRESH_TOKEN"),
            company_id=self._require_env("QB_REALM_ID"),
        )
        self.qb.session.headers.update({"Accept-Encoding": "identity"})
        # For bills, we need an expense account
        self.expense_account_ref = self._load_account_ref(
            value_key="QB_EXPENSE_ACCOUNT_ID",
            name_key="QB_EXPENSE_ACCOUNT_NAME",
            description="expense account",
            required=True,
            default_name="Job Expenses",
        )

    def ensure_vendor(self, display_name: str, company_name: Optional[str]) -> Vendor:
        # Get all vendors for matching
        all_vendors = Vendor.all(qb=self.qb)
        print(display_name)

        # Try exact match first
        for vendor in all_vendors:
            if vendor.DisplayName and vendor.DisplayName.lower().strip() == display_name.lower().strip():
                print(f"DEBUG: Found exact match: '{vendor.DisplayName}'")
                return vendor

        # Try fuzzy match (80% similarity threshold)
        best_match = None
        best_ratio = 0.8  # Minimum 80% similarity

        for vendor in all_vendors:
            if vendor.DisplayName:
                ratio = SequenceMatcher(None, vendor.DisplayName.lower(), display_name.lower()).ratio()
                print(f"DEBUG: Comparing '{display_name}' to '{vendor.DisplayName}': {ratio:.2%}")
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = vendor

        if best_match:
            print(f"Found similar vendor: '{best_match.DisplayName}' (similarity: {best_ratio:.2%})")
            return best_match

        # No match found, try to create new vendor
        print(f"DEBUG: No match found, attempting to create new vendor '{display_name}'")
        try:
            vendor = Vendor()
            vendor.DisplayName = display_name
            if company_name:
                vendor.CompanyName = company_name
            vendor.save(qb=self.qb)
            print(f"DEBUG: Successfully created new vendor '{display_name}'")
            return vendor
        except QuickbooksException as exc:
            # If duplicate error, try to get the vendor by ID or query directly
            if "6240" in str(exc) or "Duplicate" in str(exc):
                print(f"Vendor '{display_name}' already exists (error caught)")

                # Extract vendor ID from error message if present
                import re
                match = re.search(r'Id=(\d+)', str(exc))
                if match:
                    vendor_id = match.group(1)
                    print(f"DEBUG: Attempting to fetch vendor by ID={vendor_id}")
                    try:
                        vendor = Vendor.get(vendor_id, qb=self.qb)
                        print(f"DEBUG: Successfully fetched vendor by ID: '{vendor.DisplayName}'")
                        return vendor
                    except Exception as e:
                        print(f"DEBUG: Failed to fetch by ID: {e}")

                # Try querying by name using the filter method
                print(f"DEBUG: Attempting to query vendor by name='{display_name}'")
                try:
                    matches = Vendor.filter(DisplayName=display_name, qb=self.qb)
                    if matches:
                        print(f"DEBUG: Found vendor by filter query: '{matches[0].DisplayName}'")
                        return matches[0]
                except Exception as e:
                    print(f"DEBUG: Filter query failed: {e}")

                # Last resort: fetch all vendors again with lower threshold
                print(f"DEBUG: Fetching all vendors again with 50% threshold...")
                all_vendors = Vendor.all(qb=self.qb)
                print(f"DEBUG: Re-searching among {len(all_vendors)} vendors")
                for vendor in all_vendors:
                    if vendor.DisplayName:
                        ratio = SequenceMatcher(None, vendor.DisplayName.lower(), display_name.lower()).ratio()
                        if ratio >= 0.5:  # Very low threshold for error case
                            print(f"DEBUG: Potential match: '{vendor.DisplayName}' (similarity: {ratio:.2%})")
                        if ratio >= 0.75:
                            print(f"Found match: '{vendor.DisplayName}' (similarity: {ratio:.2%})")
                            return vendor
            raise

    def push_invoice(self, draft: InvoiceDraft) -> Bill:
        vendor = self.ensure_vendor(
            draft.customer_display_name,
            draft.customer_company_name,
        )

        bill = Bill()
        bill.VendorRef = vendor.to_ref()
        if draft.memo:
            bill.PrivateNote = draft.memo

        lines: List[AccountBasedExpenseLine] = []
        for line in draft.line_items:
            qb_line = AccountBasedExpenseLine()
            qb_line.Amount = line.amount
            qb_line.DetailType = "AccountBasedExpenseLineDetail"
            if line.description:
                qb_line.Description = line.description

            detail = AccountBasedExpenseLineDetail()
            detail.AccountRef = self.expense_account_ref
            qb_line.AccountBasedExpenseLineDetail = detail

            lines.append(qb_line)

        bill.Line = lines
        try:
            bill.save(qb=self.qb)
        except QuickbooksException as exc:
            raise RuntimeError(f"Failed to create bill in QuickBooks: {exc}") from exc
        return bill

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
                account = Account.get(account_id, qb=selhttps://github.com/troolee/quickbooks-python/blob/master/README.mdf.qb)
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
