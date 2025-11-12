from  gmail_labels import apply_label_to_message
from gmail_labels import  _build_service
from gmail_labels import _find_label_id
from quickstart import get_messages
from gmail_labels import apply_label_to_message
from quickstart import get_message_id
from quickstart import ai_invoice
from pydantic import BaseModel
from openai import OpenAI


def main():
    client = OpenAI()
    service=_build_service()
    messages=get_messages()
    for message in messages:
        print(ai_invoice(message, client))
    #print(get_message_id())
    #find_label=_find_label_id(service)
   # print(message_id)
if __name__ == "__main__":
         main()
