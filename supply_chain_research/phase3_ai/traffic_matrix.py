"""Traffic Matrix for Dynamic Spatio-Temporal Routing (Phase 13).

Provides time-of-day specific traffic penalties for route evaluation,
calibrated using the Delhi Travel Time dataset.
"""

from pathlib import Path

import pandas as pd
from loguru import logger


class TrafficMatrix:
    """Provides dynamic traffic penalties based on time of day."""

    def __init__(self, data_path=None):
        """
        Loads the traffic dataset and computes average speed multipliers per time window.
        """
        self.time_multipliers = {}
        
        # Default fallback penalties if data loading fails
        self._default_multipliers = {
            "Night": 1.0,           # 22:00 - 06:00
            "Morning Peak": 2.5,    # 08:00 - 11:30
            "Evening Peak": 3.0,    # 17:00 - 20:30
            "Off-Peak": 1.5         # Other times
        }

        if data_path and Path(data_path).exists():
            self._calibrate_from_data(data_path)
        else:
            logger.warning(f"Traffic dataset not found at {data_path}. Using default penalties.")
            self.time_multipliers = self._default_multipliers.copy()

    def _calibrate_from_data(self, data_path):
        """Calculates actual multipliers from the dataset speeds."""
        logger.info(f"Calibrating TrafficMatrix from {data_path}...")
        df = pd.read_csv(data_path)
        
        # Calculate mean speed for each time_of_day category
        speed_by_time = df.groupby('time_of_day')['average_speed_kmph'].mean().to_dict()
        
        if "Night" not in speed_by_time:
            speed_by_time["Night"] = df['average_speed_kmph'].max() # Assume max speed is baseline
            
        baseline_speed = speed_by_time["Night"]
        
        for tod, speed in speed_by_time.items():
            # Penalty multiplier is (Baseline Speed / Actual Speed)
            # Cap at 5.0 to prevent absurd routing loops
            self.time_multipliers[tod] = min(5.0, baseline_speed / max(speed, 1.0))
            
        logger.info(f"Calibrated Multipliers: {self.time_multipliers}")

    def get_time_category(self, hour: float) -> str:
        """Maps continuous 24-hour time to a categorical time-of-day."""
        h = hour % 24
        if h < 6 or h >= 22:
            return "Night"
        elif 8 <= h < 11.5:
            return "Morning Peak"
        elif 17 <= h < 20.5:
            return "Evening Peak"
        else:
            return "Off-Peak"

    def get_penalty(self, current_time_hours: float) -> float:
        """
        Returns the distance/cost inflation multiplier for a given time.
        
        Parameters
        ----------
        current_time_hours : float
            The cumulative time since the truck departed, in hours (e.g., 8.5 = 08:30 AM).
            
        Returns
        -------
        float
            The multiplier to apply to the edge cost.
        """
        category = self.get_time_category(current_time_hours)
        return self.time_multipliers.get(category, 1.0)

if __name__ == "__main__":
    base_dir = Path(__file__).parent.parent.parent
    data_path = base_dir / "data" / "external" / "traffic_data" / "delhi_travel_time" / "delhi_traffic_features.csv"
    tm = TrafficMatrix(data_path=str(data_path))
    
    print(f"Morning Peak Penalty: {tm.get_penalty(9.0)}")
    print(f"Night Penalty: {tm.get_penalty(3.0)}")
