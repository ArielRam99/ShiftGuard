# ShiftGuard AI - Wiki Guide

## Overview of Functionality

### 1. Database Management & Initialization (`init_db`)
* **SQLite Setup:** Automatically checks for or creates a local database file (`shiftguard.db`) in your project folder.
* **Table Schema:** Establishes a structured table called `historical_shifts` containing columns for `day_of_week` (0–6), `workload_hours` (expected volume of work), and `actual_headcount` (staff needed).

### 2. User Interface & Dashboard (`index`)
* **Tailwind CSS Styling:** Renders a clean, modern web interface using lightweight utility classes for layout, input boxes, headers, and cards.
* **Dual-Card Layout:** Separates functionality into two distinct operational blocks: **CSV Data Upload** and **AI Headcount Prediction**.

### 3. Historical CSV Data Ingestion (`upload_csv`)
* **File Upload Route (`/upload-csv`):** Accepts multi-part file uploads specifically targeted at `.csv` formats.
* **Pandas Processing:** Reads the uploaded file into a Pandas DataFrame.
* **Column Validation & Filtering:** Inspects incoming columns to ensure the necessary schema (`day_of_week`, `workload_hours`, `actual_headcount`) is present, dropping or ignoring auxiliary data.
* **Database Persistence:** Bulk-appends the parsed rows straight into the SQLite database using `to_sql()`.

### 4. Machine Learning Staffing Prediction (`predict`)
* **Dynamic Training (`LinearRegression`):** Whenever a prediction is requested, the app queries the SQLite database, loads the historical dataset, and instantly trains a fresh Ordinary Least Squares (OLS) Linear Regression model using Scikit-learn.
* **Feature Inputs:** Takes user-defined parameters—specifically expected **workload hours** and the selected **day of the week** (0–6)—via a POST request form.
* **Prediction Logic:** Runs the input features through the trained model to calculate a projected staffing requirement.
* **Safety Bounds:** Rounds the decimal prediction to the nearest integer, guarantees a minimum staffing floor of at least 1 employee, and renders the recommendation back onto the dashboard UI.

### 5. Application Server Lifecycle (`__main__`)
* **Flask Development Server:** Automatically runs `init_db()` to guarantee the database is ready upon startup, then launches the Flask app in debug mode on port `5000`.

---

## How to Run Locally

Follow these step-by-step instructions to set up and run the application on your local machine:

### Step 1: Clone the Repository Locally
Clone the project repository to your local machine using Git:
```bash
git clone https://github.com/ArielRam99/ShiftGuard.git C:\repos\ShiftGuard
```

### Step 2: Open Your Project Folder
Navigate to your local project directory: 
C:\repos\ShiftGuard

### Step 3: Install Requirements for ShiftGuard

```bash
python -m pip install pandas
python -m pip install numpy
python -m pip install scikit-learn
python -m pip install Flask
```

### Step 4: Start the application locally
Navigate to your local project directory: C:\repos\ShiftGuard\
```bash
python app.py
```

### Step 5: Open the dashboard
Open your web browser, and go to the following address to use the dashboard:
```bash
http://127.0.0.1:5000
```

---

## How to Run Unit Tests Locally

Follow these steps to run the test suite (`tests.py`) on your local machine:

### Step 1: Install Requirements
Make sure the application dependencies from the [How to Run Locally](#step-3-install-requirements-for-shiftguard) section are installed:
```bash
python -m pip install pandas
python -m pip install numpy
python -m pip install scikit-learn
python -m pip install Flask
```

### Step 2: Navigate to the Project Directory
Navigate to your local project directory, where `tests.py` is located.

### Step 3: Run the Test Suite
Run the tests using Python's built-in `unittest` module:
```bash
python -m unittest -v tests.py
```
The `-v` flag runs the tests in verbose mode, printing the name and result of each test case.

### Step 4: Review the Results
A successful run will show `OK` at the end of the output, confirming that the database initialization, dashboard route, and prediction endpoint are all working as expected.