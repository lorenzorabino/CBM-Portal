from flask import Flask, jsonify
import sqlite3

app = Flask(__name__)

@app.route('/get-data')
def get_data():
    conn = sqlite3.connect('portal_demo3.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

if __name__ == '__main__':
    app.run(debug=True)
