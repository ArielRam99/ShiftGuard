import random
import pandas as pd

random.seed(42)
date_range = pd.date_range(start="2025-09-01", end="2026-08-31", freq="D")

data = []
for date in date_range:
  day_of_week = date.dayofweek  # 0 = Monday, 6 = Sunday

  # Simulate workload hours based on the day of the week
  # Weekdays (0-4) are busier; Weekends (5-6) are slower
  if day_of_week < 5:
    workload_hours = round(random.uniform(35.0, 65.0), 1)
    # Headcount correlates roughly with workload, plus a little random variance
    actual_headcount = max(
        3, int(workload_hours / 7.5 + random.uniform(-1, 1))
    )
  else:
    workload_hours = round(random.uniform(15.0, 30.0), 1)
    actual_headcount = max(
        2, int(workload_hours / 7.0 + random.uniform(-1, 1))
    )

  data.append({
      "date": date.strftime("%Y-%m-%d"),
      "day_of_week": day_of_week,
      "workload_hours": workload_hours,
      "actual_headcount": actual_headcount,
  })

# Convert to DataFrame and save to CSV
df = pd.DataFrame(data)
df.to_csv("sample_shifts_year.csv", index=False)

print(
    "Successfully generated 'sample_shifts_year.csv' with"
    f" {len(df)} records!"
)