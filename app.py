import os
import sqlite3
import pandas as pd
from flask import Flask, jsonify, render_template_string, request
from sklearn.linear_model import LinearRegression

app = Flask(__name__)
DB_FILE = "shiftguard.db"


def init_db():
  """Initialize a simple SQLite database for shifts and predictions."""
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS historical_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_of_week INTEGER,
            workload_hours REAL,
            actual_headcount INTEGER
        )
    """)
  # Insert dummy data if table is empty
  cursor.execute("SELECT COUNT(*) FROM historical_shifts")
  if cursor.fetchone()[0] == 0:
    sample_data = [
        (0, 35.0, 5),
        (1, 42.5, 6),
        (2, 38.0, 5),
        (3, 50.0, 7),
        (4, 55.0, 8),
        (5, 20.0, 3),
        (6, 15.0, 2),
    ]
    cursor.executemany(
        """
            INSERT INTO historical_shifts (day_of_week, workload_hours, actual_headcount)
            VALUES (?, ?, ?)
        """,
        sample_data,
    )
    conn.commit()
  conn.close()


# HTML Template embedded for instant MVP rendering
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ShiftGuard AI - MVP Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 font-sans p-6">
    <div class="max-w-4xl mx-auto bg-white p-6 rounded-lg shadow-md">
        <h1 class="text-2xl font-bold text-gray-800 mb-2">ShiftGuard AI Dashboard</h1>
        <p class="text-gray-600 mb-6">AI-powered workforce scheduling MVP using Flask & Scikit-learn.</p>
        
        <div class="bg-blue-50 border-l-4 border-blue-500 p-4 mb-6">
            <h2 class="font-semibold text-blue-800">Run AI Staffing Prediction</h2>
            <form action="/predict" method="POST" class="mt-2 flex gap-4">
                <input type="number" name="workload" placeholder="Expected Workload Hours (e.g. 45)" required 
                       class="border border-gray-300 rounded px-3 py-2 w-1/2">
                <select name="day" class="border border-gray-300 rounded px-3 py-2">
                    <option value="0">Monday</option>
                    <option value="1">Tuesday</option>
                    <option value="2">Wednesday</option>
                    <option value="3">Thursday</option>
                    <option value="4">Friday</option>
                    <option value="5">Saturday</option>
                    <option value="6">Sunday</option>
                </select>
                <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Predict Headcount</button>
            </form>
        </div>

        {% if prediction is defined %}
        <div class="bg-green-50 border border-green-200 p-4 rounded">
            <h3 class="font-bold text-green-800">Recommendation Result:</h3>
            <p class="text-green-700">Recommended Staffing Headcount: <strong>{{ prediction }} employees</strong></p>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""


@app.route("/")
def index():
  return render_template_string(HTML_TEMPLATE)


@app.route("/predict", methods=["POST"])
def predict():
  workload = float(request.form["workload"])
  day = int(request.form["day"])

  # Fetch historical data from SQLite to train model on the fly
  conn = sqlite3.connect(DB_FILE)
  df = pd.read_sql_query(
      "SELECT day_of_week, workload_hours, actual_headcount FROM"
      " historical_shifts",
      conn,
  )
  conn.close()

  # Train a simple Scikit-learn OLS Linear Regression model
  X = df[["day_of_week", "workload_hours"]]
  y = df["actual_headcount"]

  model = LinearRegression()
  model.fit(X, y)

  # Predict for requested input
  input_df = pd.DataFrame(
      {"day_of_week": [day], "workload_hours": [workload]}
  )
  predicted_headcount = round(model.predict(input_df)[0])
  predicted_headcount = max(
      1, predicted_headcount
  )  # Ensure at least 1 staff member

  return render_template_string(
      HTML_TEMPLATE, prediction=predicted_headcount
  )


if __name__ == "__main__":
  init_db()
  app.run(debug=True, port=5000)