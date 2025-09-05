# Simple Web Portal

This is a simple web portal project built using Python and Flask. It serves as a basic task management tool, similar to Monday.com but simplified for beginners.

## Project Structure

```
simple-web-portal
├── app
│   ├── __init__.py
│   ├── routes.py
│   ├── models.py
│   └── templates
│       └── index.html
├── static
│   └── style.css
├── database
│   └── portal.db
├── requirements.txt
├── README.md
└── run.py
```

## Setup Instructions

1. **Clone the repository**:
   ```
   git clone <repository-url>
   cd simple-web-portal
   ```

2. **Create a virtual environment** (optional but recommended):
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install the required packages**:
   ```
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```
   python run.py
   ```

5. **Access the web portal**:
   Open your web browser and go to `http://127.0.0.1:5000`.

## Usage

- The home page displays a simple interface for managing tasks.
- You can add, view, and delete tasks using the provided functionalities.

## License

This project is open-source and available under the MIT License.


# 1) Create and activate a local venv for this machine
python.exe -m pip install -r requirements.txt