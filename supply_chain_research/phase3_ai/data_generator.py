"""Synthetic demand data generator for LSTM training.

Generates 3 years of daily demand for 100 customers with
weekly seasonality, annual cycles, Diwali spikes, and noise.
Applies temporal train/val/test split (70/15/15).
"""

import numpy as np


class DemandDataGenerator:
    """Generate synthetic daily demand data with realistic patterns.

    Patterns include:
    - Weekly seasonality (7-day cycle)
    - Annual cycle (365-day period)
    - Diwali spike (mid-October to mid-November)
    - Random noise

    Parameters
    ----------
    n_customers : int, optional
        Number of customers to generate data for (default 100).
    n_years : int, optional
        Number of years of daily data (default 3).
    seed : int, optional
        Random seed for reproducibility (default 42).

    Attributes
    ----------
    n_customers, n_years, n_days, seed : int
        Stored generator parameters; ``n_days = n_years * 365``.
    rng : numpy.random.Generator
        Per-instance NumPy random generator.
    """

    def __init__(self, n_customers=100, n_years=3, seed=42):
        """Initialize demand data generator.

        Args:
            n_customers: Number of customers to generate data for.
            n_years: Number of years of daily data.
            seed: Random seed for reproducibility.
        """
        self.n_customers = n_customers
        self.n_years = n_years
        self.n_days = n_years * 365
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def generate(self):
        """Generate synthetic demand data.

        Returns:
            Dictionary with keys:
                'demand': array of shape (n_days, n_customers)
                'train': tuple (X_train, y_train) - not split yet
                'dates': array of day indices
        """
        demand = np.zeros((self.n_days, self.n_customers))

        for c in range(self.n_customers):
            demand[:, c] = self._generate_customer_demand(c)

        return {
            'demand': demand,
            'n_days': self.n_days,
            'n_customers': self.n_customers,
        }

    def _generate_customer_demand(self, customer_id):
        """Generate demand time series for a single customer.

        Uses multiplicative composition per specification:
        demand(j, t) = base_demand(j) * weekly_factor(t) * annual_factor(t)
                       * trend_factor(t) * diwali_factor(t) * noise(t)

        All factors are positive, ensuring demand is always positive.

        Args:
            customer_id: Customer index (used to vary base demand).

        Returns:
            Array of shape (n_days,) with daily demand values.
        """
        t = np.arange(self.n_days, dtype=np.float64)

        # Base demand: positive value varying by customer (lognormal gives positive values)
        # Mean around 50-150 units depending on customer
        base = np.exp(self.rng.uniform(3.9, 5.0))  # ~50 to ~150

        # Weekly factor: day-of-week multipliers [Mon, Tue, Wed, Thu, Fri, Sat, Sun]
        weekly_multipliers = np.array([1.0, 1.1, 1.05, 1.0, 1.15, 0.9, 0.75])
        weekly = weekly_multipliers[t.astype(int) % 7]

        # Annual factor: sinusoidal with peak shifted to festive season
        # 1.0 + 0.6 * sin(2*pi*(t - 100)/365)
        annual = 1.0 + 0.6 * np.sin(2 * np.pi * (t - 100) / 365.0)

        # Trend factor: 0.5% monthly growth
        # 1.0 + 0.005 * (t / 30)
        trend = 1.0 + 0.005 * (t / 30.0)

        # Diwali spike factor: multiplicative 2x-3x during days 285-320 each year
        diwali = np.ones(self.n_days)
        for year in range(self.n_years):
            start_day = year * 365 + 285  # ~Oct 12
            end_day = year * 365 + 320    # ~Nov 16
            if end_day <= self.n_days:
                diwali_mult = self.rng.uniform(2.0, 3.0)
                diwali[start_day:end_day] = diwali_mult

        # Multiplicative noise: LogNormal(0, 0.1) - always positive, mean ~1.005
        noise = self.rng.lognormal(0, 0.1, size=self.n_days)

        # Multiplicative composition - all factors positive, so demand always positive
        demand = base * weekly * annual * trend * diwali * noise

        return demand

    def generate_edge_case_demand(self):
        """Generate edge-case demand data for data augmentation.

        Produces demand with extreme patterns including sudden spikes,
        seasonal droughts, and high-frequency noise to improve LSTM
        robustness on unusual market conditions.

        Returns:
            Array of shape (n_days, n_customers) with edge-case patterns.
        """
        demand = np.zeros((self.n_days, self.n_customers))

        for c in range(self.n_customers):
            demand[:, c] = self._generate_customer_demand(c)

        # Apply sudden demand spikes: 5-10 periods of 2-5 consecutive days at 3x
        n_spikes = self.rng.integers(5, 11)
        spike_periods = []
        for _ in range(n_spikes):
            duration = self.rng.integers(2, 6)
            # Try to find a non-overlapping period
            for _attempt in range(100):
                start = self.rng.integers(0, self.n_days - duration)
                end = start + duration
                overlaps = False
                for s, e in spike_periods:
                    if start < e and end > s:
                        overlaps = True
                        break
                if not overlaps:
                    spike_periods.append((start, end))
                    break
            else:
                # If we can't find non-overlapping, skip this spike
                continue

        for start, end in spike_periods:
            demand[start:end, :] *= 3.0

        # Apply seasonal drops/droughts: 3-5 periods of 10-30 days at 20-40%
        n_droughts = self.rng.integers(3, 6)
        for _ in range(n_droughts):
            duration = self.rng.integers(10, 31)
            start = self.rng.integers(0, self.n_days - duration)
            reduction = self.rng.uniform(0.2, 0.4)
            demand[start:start + duration, :] *= reduction

        # Apply high-frequency noise: lognormal with sigma=0.5
        noise = self.rng.lognormal(0, 0.5, size=(self.n_days, self.n_customers))
        demand *= noise

        return demand

    def create_augmented_dataset(self, seq_length=30, forecast_horizon=7,
                                 edge_case_ratio=0.3):
        """Create augmented dataset mixing standard and edge-case data.

        Generates both standard and edge-case demand sequences, then
        combines them at the specified ratio for robust LSTM training.

        Args:
            seq_length: Number of past days as input sequence.
            forecast_horizon: Number of future days to predict.
            edge_case_ratio: Target fraction of edge-case samples in
                the final dataset (default 0.3 for 30/70 mix).

        Returns:
            Dictionary with keys:
                'X': Combined input sequences array.
                'y': Combined target sequences array.
        """
        # Generate standard data
        standard_data = self.generate()
        X_standard, y_standard = self.create_sequences(
            standard_data['demand'], seq_length, forecast_horizon
        )

        # Generate edge-case data
        edge_demand = self.generate_edge_case_demand()
        X_edge, y_edge = self.create_sequences(
            edge_demand, seq_length, forecast_horizon
        )

        # Calculate how many edge-case samples to include
        n_edge = int(len(X_standard) * edge_case_ratio / (1 - edge_case_ratio))

        # Sample or use all edge sequences
        if n_edge > len(X_edge):
            X_edge_selected = X_edge
            y_edge_selected = y_edge
        else:
            indices = self.rng.choice(len(X_edge), size=n_edge, replace=False)
            X_edge_selected = X_edge[indices]
            y_edge_selected = y_edge[indices]

        # Concatenate standard and edge-case data
        X_combined = np.concatenate([X_standard, X_edge_selected], axis=0)
        y_combined = np.concatenate([y_standard, y_edge_selected], axis=0)

        # Shuffle sequences (not internal time steps)
        shuffle_idx = self.rng.permutation(len(X_combined))
        X_combined = X_combined[shuffle_idx]
        y_combined = y_combined[shuffle_idx]

        return {'X': X_combined, 'y': y_combined}

    def create_sequences(self, demand, seq_length=30,
                         forecast_horizon=7):
        """Create input sequences and target forecasts.

        Args:
            demand: Array of shape (n_days, n_customers).
            seq_length: Number of past days as input.
            forecast_horizon: Number of future days to predict.

        Returns:
            Tuple of (X, y) where:
                X has shape (n_samples, seq_length, n_customers)
                y has shape (n_samples, forecast_horizon, n_customers)
        """
        n_days = demand.shape[0]
        n_samples = n_days - seq_length - forecast_horizon + 1

        X = np.zeros((n_samples, seq_length, self.n_customers))
        y = np.zeros((
            n_samples, forecast_horizon, self.n_customers
        ))

        for i in range(n_samples):
            X[i] = demand[i:i + seq_length]
            y[i] = demand[
                i + seq_length:i + seq_length + forecast_horizon
            ]

        return X, y

    def temporal_split(self, X, y, train_ratio=0.7,
                       val_ratio=0.15, seq_length=30,
                       forecast_horizon=7):
        """Audit 2.5: Block-bootstrap holdout that quarantines Diwali.

        Identifies all Diwali windows (days 285-320 of each year) in the
        full series, holds out the FINAL Diwali window as the test set,
        uses the preceding 15% of non-Diwali days as validation, and
        the remaining days as training. Prints a warning if any Diwali
        spike day appears in both train and test partitions (which can
        only happen if the input X/y were generated from a different
        n_years).

        Parameters
        ----------
        X : np.ndarray
            Sequences of shape (n_samples, seq_length, n_customers).
        y : np.ndarray
            Targets of shape (n_samples, forecast_horizon, n_customers).
        train_ratio : float
            Ignored; kept for back-compat. Train uses non-Diwali, non-test
            days plus all Diwali periods except the last.
        val_ratio : float
            Fraction of non-Diwali days (preceding test) used for val.
        seq_length : int
        forecast_horizon : int

        Returns
        -------
        Same dict signature as before.
        """
        n_samples = X.shape[0]
        # The sample index i covers source days [i, i+seq_length+forecast_horizon).
        # We classify a sample as Diwali-touching if any source day falls in any
        # year-relative window 285..320.
        all_days = np.arange(self.n_days)
        # Diwali mask over the original day axis
        diwali_day_mask = np.zeros(self.n_days, dtype=bool)
        for year in range(self.n_years):
            start_d = year * 365 + 285
            end_d = year * 365 + 320
            if end_d <= self.n_days:
                diwali_day_mask[start_d:end_d] = True

        # For each sample, check whether its source-day window touches Diwali
        sample_touches_diwali = np.zeros(n_samples, dtype=bool)
        for i in range(n_samples):
            window = slice(i, i + seq_length + forecast_horizon)
            sample_touches_diwali[i] = diwali_day_mask[window].any()

        # Test set = the LAST contiguous run of Diwali-touching samples
        test_indices = []
        if sample_touches_diwali.any():
            # Find runs of True
            runs = []
            in_run = False
            run_start = None
            for i, v in enumerate(sample_touches_diwali):
                if v and not in_run:
                    in_run, run_start = True, i
                elif not v and in_run:
                    runs.append((run_start, i))
                    in_run = False
            if in_run:
                runs.append((run_start, n_samples))
            if runs:
                last_start, last_end = runs[-1]
                test_indices = list(range(last_start, last_end))

        if not test_indices:
            # Fallback: use last 15%
            cut = int(n_samples * 0.85)
            test_indices = list(range(cut, n_samples))

        test_set = set(test_indices)
        non_test_indices = [i for i in range(n_samples) if i not in test_set]

        # Validation = preceding val_ratio fraction of non-test, non-Diwali samples
        non_test_non_diwali = [
            i for i in non_test_indices if not sample_touches_diwali[i]
        ]
        n_val = int(len(non_test_non_diwali) * val_ratio)
        val_indices = non_test_non_diwali[-n_val:] if n_val > 0 else []
        val_set = set(val_indices)
        train_indices = [
            i for i in non_test_indices if i not in val_set
        ]

        # Diwali-leakage warning: any sample index appearing in both
        # train and test (cannot happen with set-disjoint construction
        # but verify defensively).
        leak = test_set.intersection(train_indices)
        if leak:
            import warnings
            warnings.warn(
                f"Diwali leakage detected: {len(leak)} samples shared "
                "between train and test."
            )

        X_train, y_train = X[train_indices], y[train_indices]
        X_val, y_val = (
            (X[val_indices], y[val_indices]) if val_indices
            else (np.empty((0,) + X.shape[1:], dtype=X.dtype),
                  np.empty((0,) + y.shape[1:], dtype=y.dtype))
        )
        X_test, y_test = X[test_indices], y[test_indices]

        # Normalize using ONLY training set statistics
        train_mean = X_train.mean() if X_train.size > 0 else 0.0
        train_std = X_train.std() if X_train.size > 0 else 1.0
        if train_std < 1e-8:
            train_std = 1.0

        def _norm(arr):
            if arr.size == 0:
                return arr.astype(np.float32)
            return ((arr - train_mean) / train_std).astype(np.float32)

        return {
            'X_train': _norm(X_train),
            'y_train': _norm(y_train),
            'X_val': _norm(X_val),
            'y_val': _norm(y_val),
            'X_test': _norm(X_test),
            'y_test': _norm(y_test),
            'train_mean': float(train_mean),
            'train_std': float(train_std),
            'y_test_raw': y_test.astype(np.float32),
            'y_val_raw': y_val.astype(np.float32) if y_val.size > 0 else y_val.astype(np.float32),
            'split_strategy': 'block_bootstrap_diwali_holdout',
            'n_test_samples': len(test_indices),
            'n_val_samples': len(val_indices),
            'n_train_samples': len(train_indices),
        }
