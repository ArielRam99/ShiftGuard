import math
from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_predict


SUPPORTED_MODELS = (
    "random_forest",
    "gradient_boosting",
    "linear_regression",
)


@dataclass(frozen=True)
class StaffingPrediction:
    required_staff: int
    range_min: int
    range_max: int
    confidence_level: float
    source: str
    training_records: int
    metrics: dict | None = None


class StaffingPredictor:
    """Compare and run advisory staffing-demand models.

    Metrics use reproducible shuffled K-fold out-of-fold predictions. Confidence
    ranges use the 95th percentile of absolute out-of-fold errors and are an
    operational uncertainty estimate, not a statistical guarantee.
    """

    minimum_training_records = 5
    confidence_level = 0.95

    @staticmethod
    def _model(strategy):
        if strategy == "random_forest":
            return RandomForestRegressor(
                n_estimators=80,
                random_state=42,
                min_samples_leaf=1,
            )
        if strategy == "gradient_boosting":
            return GradientBoostingRegressor(random_state=42)
        if strategy == "linear_regression":
            return LinearRegression()
        raise ValueError(f"Unsupported model strategy: {strategy}")

    @staticmethod
    def _dataset(history):
        records = list(history)
        features = np.asarray(
            [
                [
                    int(row["day_of_week"]),
                    float(row["workload_score"]),
                    float(row["shift_length_hours"]),
                ]
                for row in records
            ],
            dtype=float,
        )
        targets = np.asarray(
            [int(row["required_staff"]) for row in records], dtype=float
        )
        return records, features, targets

    @staticmethod
    def _folds(record_count):
        return KFold(
            n_splits=min(5, record_count),
            shuffle=True,
            random_state=42,
        )

    def _evaluate(self, strategy, features, targets):
        predictions = cross_val_predict(
            self._model(strategy),
            features,
            targets,
            cv=self._folds(len(targets)),
        )
        errors = np.abs(targets - predictions)
        metrics = {
            "mae": round(float(mean_absolute_error(targets, predictions)), 4),
            "rmse": round(
                float(math.sqrt(mean_squared_error(targets, predictions))), 4
            ),
            "r2": round(float(r2_score(targets, predictions)), 4),
        }
        error_margin = max(1, int(math.ceil(np.quantile(errors, 0.95))))
        return metrics, error_margin

    def compare(self, history):
        records, features, targets = self._dataset(history)
        if len(records) < self.minimum_training_records:
            return {
                "training_records": len(records),
                "minimum_training_records": self.minimum_training_records,
                "best_model": "rules_fallback",
                "models": [],
            }

        results = []
        for strategy in SUPPORTED_MODELS:
            metrics, error_margin = self._evaluate(strategy, features, targets)
            results.append(
                {
                    "strategy": strategy,
                    **metrics,
                    "confidence_error_margin": error_margin,
                }
            )
        results.sort(
            key=lambda result: (
                result["mae"],
                result["rmse"],
                result["strategy"],
            )
        )
        return {
            "training_records": len(records),
            "minimum_training_records": self.minimum_training_records,
            "best_model": results[0]["strategy"],
            "models": results,
        }

    def predict(
        self,
        history,
        day_of_week,
        workload_score,
        shift_length_hours,
        strategy="random_forest",
    ):
        records, features, targets = self._dataset(history)
        if len(records) < self.minimum_training_records:
            workload_units = max(1, math.ceil(float(workload_score) / 25))
            length_factor = max(0.75, float(shift_length_hours) / 8)
            predicted = min(50, max(1, math.ceil(workload_units * length_factor)))
            return StaffingPrediction(
                predicted,
                max(1, predicted - 1),
                min(50, predicted + 1),
                self.confidence_level,
                "rules_fallback",
                len(records),
            )

        if strategy == "auto":
            comparison = self.compare(records)
            selected_strategy = comparison["best_model"]
            selected = next(
                result
                for result in comparison["models"]
                if result["strategy"] == selected_strategy
            )
        else:
            selected_strategy = strategy
            metrics, error_margin = self._evaluate(
                selected_strategy, features, targets
            )
            selected = {
                "strategy": selected_strategy,
                **metrics,
                "confidence_error_margin": error_margin,
            }
        if selected_strategy not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported model strategy: {selected_strategy}")
        model = self._model(selected_strategy)
        model.fit(features, targets)
        raw_prediction = model.predict(
            np.asarray(
                [[day_of_week, workload_score, shift_length_hours]], dtype=float
            )
        )[0]
        predicted = min(50, max(1, int(round(raw_prediction))))
        error_margin = selected["confidence_error_margin"]
        metrics = {key: selected[key] for key in ("mae", "rmse", "r2")}
        return StaffingPrediction(
            predicted,
            max(1, predicted - error_margin),
            min(50, predicted + error_margin),
            self.confidence_level,
            selected_strategy,
            len(records),
            metrics,
        )
