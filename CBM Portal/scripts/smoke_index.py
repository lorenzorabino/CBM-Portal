import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app


def main():
    app = create_app()
    with app.test_client() as client:
        resp = client.get("/")
        print("STATUS:", resp.status_code)
        print("BYTES:", len(resp.data))
        # Print a short preview of the HTML to confirm render
        try:
            print((resp.data[:200]).decode("utf-8", errors="ignore"))
        except Exception:
            pass


if __name__ == "__main__":
    main()
