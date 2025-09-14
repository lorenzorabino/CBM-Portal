import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app


def main():
    app = create_app()
    with app.test_client() as client:
        resp = client.get("/planner_entries")
        print("STATUS:", resp.status_code)
        html = resp.data.decode("utf-8", errors="ignore")
        print("BYTES:", len(resp.data))
        # Quick heuristic: count table rows for planner entries
        rows = html.count("<tr>")
        print("<tr> tags:", rows)
        print(html[:500])


if __name__ == "__main__":
    main()
