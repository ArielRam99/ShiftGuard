import os
import sqlite3
import pandas as pd
from flask import Flask, redirect, render_template_string, request, url_for
from sklearn.linear_model import LinearRegression

app = Flask(__name__)
DB_FILE = "shiftguard.db"


def init_db():
  """Initialize the SQLite database for shifts."""
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
  conn.commit()
  conn.close()


# Updated HTML Template with a CSV Upload Section
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ShiftGuard AI - MVP Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 font-sans p-6">
    <div class="max-w-4xl mx-auto space-y-6">
        
        <!-- Header -->
        <div class="bg-white p-6 rounded-lg shadow-md">
            <h1 class="text-2xl font-bold text-gray-800 mb-2">ShiftGuard AI Dashboard</h1>
            <p class="text-gray-600">AI-powered workforce scheduling MVP using Flask, SQLite, & Scikit-learn.</p>
        </div>

        <!-- CSV Upload Card -->
        <div class="bg-white p-6 rounded-lg shadow-md border-t-4 border-indigo-500">
            <h2 class="font-semibold text-indigo-900 text-lg mb-2">1. Upload Historical Timesheet CSV</h2>
            <p class="text-sm text-gray-500 mb-4">CSV must contain columns: <code class="bg-gray-100 px-1 py-0.5 rounded">day_of_week</code> (0-6), <code class="bg-gray-100 px-1 py-0.5 rounded">workload_hours</code>, and <code class="bg-gray-100 px-1 py-0.5 rounded">actual_headcount</code>.</p>
            
            <form action="/upload-csv" method="POST" enctype="multipart/form-data" class="flex gap-4 items-center">
                <input type="file" name="file" accept=".csv" required 
                       class="border border-gray-300 rounded px-3 py-2 text-sm w-full bg-gray-50">
                <button type="submit" class="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 text-sm whitespace-nowrap">Upload CSV</button>
            </form>
            {% if message %}
            <p class="mt-3 text-sm font-medium text-green-600">{{ message }}</p>
            {% endif %}
        </div>

        <!-- AI Prediction Card -->
        <div class="bg-white p-6 rounded-lg shadow-md border-t-4 border-blue-500">
            <h2 class="font-semibold text-blue-900 text-lg mb-2">2. Run AI Staffing Prediction</h2>
            <form action="/predict" method="POST" class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-3">
                <input type="number" step="any" name="workload" placeholder="Expected Workload Hours (e.g. 45)" required 
                       class="border border-gray-300 rounded px-3 py-2">
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

            {% if prediction is defined %}
            <div class="mt-4 bg-green-50 border border-green-200 p-4 rounded">
                <h3 class="font-bold text-green-800">Recommendation Result:</h3>
                <p class="text-green-700">Recommended Staffing Headcount: <strong>{{ prediction }} employees</strong></p>
            </div>
            {% endif %}
        </div>

    </div>
</body>
</html>
"""


@app.route("/")
def index():
  return render_template_string(HTML_TEMPLATE)

@app.route('/upload-csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('index'))
        
    if file and file.filename.endswith('.csv'):
        df = pd.read_csv(file)
        expected_cols = ['day_of_week', 'workload_hours', 'actual_headcount']
        df = df[[col for col in expected_cols if col in df.columns]]
        
        if not all(col in df.columns for col in expected_cols):
            return render_template_string(HTML_TEMPLATE, message="Error: CSV is missing required columns.")
            
        conn = sqlite3.connect(DB_FILE)
        df.to_sql('historical_shifts', conn, if_exists='append', index=False)
        conn.close()
        
        return render_template_string(HTML_TEMPLATE, message=f"Successfully imported {len(df)} records from {file.filename}!")
        
    return render_template_string(HTML_TEMPLATE, message="Please upload a valid .csv file.")


@app.route("/predict", methods=["POST"])
def predict():
  workload = float(request.form["workload"])
  day = int(request.form["day"])

  conn = sqlite3.connect(DB_FILE)
  df = pd.read_sql_query(
      "SELECT day_of_week, workload_hours, actual_headcount FROM"
      " historical_shifts",
      conn,
  )
  conn.close()

  # Check if we have data to train on
  if df.empty:
    return render_template_string(
        HTML_TEMPLATE,
        prediction=(
            "Error: Database is empty! Please upload a historical CSV dataset"
            " first."
        ),
    )

  # Train Scikit-learn OLS Linear Regression model on uploaded data
  X = df[["day_of_week", "workload_hours"]]
  y = df["actual_headcount"]

  model = LinearRegression()
  model.fit(X, y)

  input_df = pd.DataFrame(
      {"day_of_week": [day], "workload_hours": [workload]}
  )
  predicted_headcount = round(model.predict(input_df)[0])
  predicted_headcount = max(1, predicted_headcount)

  return render_template_string(
      HTML_TEMPLATE, prediction=predicted_headcount
  )


if __name__ == "__main__":
  init_db()
  app.run(debug=True, port=5000)