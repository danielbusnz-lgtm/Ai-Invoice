from typing import Optional, Sequence
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


DEFAULT_LABEL_NAME="Invoice"


def _build_service():
    """Create a Gmail API service using stored credentials."""
    apply_label_to_message    # Local import avoids a circular dependency when quickstart imports this module.
    from quickstart import load_creds

    creds = load_creds()
    if creds is None:
        raise RuntimeError("Gmail credentials are unavailable. Run the OAuth flow first.")
    return build("gmail", "v1", credentials=creds)





def _find_label_id(service) -> Optional[str]:
    """Return the Gmail label id that matches label_name, if it exists."""
    results = service.users().labels().list(userId="me").execute()
    labels = results.get("labels", [])

    for label in labels:
        #print(f"name: {label['name']} | ID: {label['id']}")
        label_name= label['name']
        print(label_name)
        return label_name



def apply_label_to_message(
    message_id: str,
    label_id: str,
    remove_label_ids: Optional[Sequence[str]] = None,
    service=None,
) -> None:
    """Apply the existing label to a Gmail message."""
    if not message_id:
        raise ValueError("message_id is required.")
    if not label_id:
        raise ValueError("label_id is required.")

    service = service or _build_service()
    try:
        body = {
            "addLabelIds": [label_id],
            "removeLabelIds": list(remove_label_ids) if remove_label_ids else [],
        }
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body=body,
            name=DEFAULT_LABEL_NAME
        ).execute()
    except HttpError as exc:
        raise RuntimeError(f"Failed to label message {message_id}: {exc}") from exc



def main():
    service=_build_service()
    labels=_find_label_id(service)
    print(labels)
if __name__ == "__main__":
         main()
