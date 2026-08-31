import math
from dataclasses import dataclass

from sklearn.ensemble import RandomForestRegressor


@dataclass(frozen=True)
class StaffingPrediction:
    required_staff: int
    source: str
    training_records: int


class StaffingPredictor:
    """Predict staffing demand from historical workload observations.

    The model advises the scheduler only. A manager must approve every schedule.
    """

    minimum_training_records = 5

    def predict(self, history, day_of_week, workload_score, shift_length_hours):
        records = list(history)
        if len(records) < self.minimum_training_records:
            # A documented fallback keeps a new installation usable before it
            # accumulates enough history to train a model.
            workload_units = max(1, math.ceil(float(workload_score) / 25))
            length_factor = max(0.75, float(shift_length_hours) / 8)
            predicted = max(1, math.ceil(workload_units * length_factor))
            return StaffingPrediction(predicted, "rules_fallback", len(records))

        features = [
            [
                int(row["day_of_week"]),
                float(row["workload_score"]),
                float(row["shift_length_hours"]),
            ]
            for row in records
        ]
        targets = [int(row["required_staff"]) for row in records]
        model = RandomForestRegressor(
            n_estimators=80,
            random_state=42,
            min_samples_leaf=1,
        )
        model.fit(features, targets)
        raw_prediction = model.predict(
            [[int(day_of_week), float(workload_score), float(shift_length_hours)]]
        )[0]
        predicted = min(50, max(1, int(round(raw_prediction))))
        return StaffingPrediction(predicted, "random_forest", len(records))

