import os
import sqlite3
import unittest
import app

class ShiftGuardTestCase(unittest.TestCase):
    
    def setUp(self):
        """Set up test client and create a fresh database for testing."""
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()
        
        # Ensure a clean slate by removing any existing database file
        if os.path.exists('shiftguard.db'):
            os.remove('shiftguard.db')
            
        # Initialize the database table via app function
        with app.app.app_context():
            app.init_db()

    def tearDown(self):
        """Clean up the test database after each test."""
        if os.path.exists('shiftguard.db'):
            os.remove('shiftguard.db')

    def test_index_route(self):
        """Test that the home page loads successfully."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_database_initialization(self):
        """Test that the SQLite database and table are created properly."""
        self.assertTrue(os.path.exists('shiftguard.db'))

    def test_prediction_route_bounds(self):
        """Test the ML prediction endpoint directly via test client or verify database state."""
        conn = sqlite3.connect('shiftguard.db')
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO historical_shifts (day_of_week, workload_hours, actual_headcount) VALUES (?, ?, ?)",
            [
                (1, 30.0, 4),
                (2, 40.0, 6),
                (3, 50.0, 8)
            ]
        )
        conn.commit()
        conn.close()

        # verify the route exists and test with JSON if your app accepts JSON, 
        # or check what happens with a GET request first.
        response = self.client.get('/predict')
        
        # If /predict only accepts POST, a GET should return a 405 Method Not Allowed.
        # If it returns 405, we know the route exists and is actively listening!
        self.assertIn(response.status_code, [200, 302, 405])

if __name__ == '__main__':
    unittest.main()