import time
from quickstart import main


if __name__ == "__main__":
    while True:
        try :
            main()
        except exception as exc:
            print(f"failed run: {exc}")
        time.sleep(300)
