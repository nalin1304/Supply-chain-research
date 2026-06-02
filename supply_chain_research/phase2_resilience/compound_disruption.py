"""Compound disruption modeling for sequential cascades and simultaneous events."""

import numpy as np


class CompoundDisruption:
    """Compound disruption modeling sequential cascades or simultaneous overlapping events.

    Attributes:
        shocks: List of individual shock objects (e.g. SupplyShock, DemandShock, Cyberattack).
        cascade_prob_matrix: Dict mapping tuple (primary_class_name, secondary_class_name) to cascading probability.
        simultaneous: If True, all shocks start at the same start_day. Otherwise, they are cascaded.
    
    Parameters
    ----------
    """

    def __init__(self, shocks, cascade_prob_matrix=None, simultaneous=False, seed=42):
        """
        Parameters
        ----------
        """
        self.shocks = shocks
        self.cascade_prob_matrix = cascade_prob_matrix or {}
        self.simultaneous = simultaneous
        self.rng = np.random.default_rng(seed)
        self._actual_start = None
        self._actual_end = None
        self._duration = 0

    def apply(self, des_env):
        """
        Parameters
        ----------
        """
        warmup = des_env.warmup_days

        if self.simultaneous:
            # All shocks start at the same day
            start_day = des_env.sim_days // 4  # e.g., 25% of sim
            for s in self.shocks:
                s.start_day = start_day
            self._actual_start = start_day
            
            # Start all shocks
            for s in self.shocks:
                des_env.env.process(s.apply(des_env))

            # Wait to gather timing after they initialize
            yield des_env.env.timeout(1)
            starts = [s.shock_start for s in self.shocks if s.shock_start is not None]
            ends = [s.shock_end for s in self.shocks if s.shock_end is not None]
            if starts and ends:
                self._actual_start = min(starts)
                self._actual_end = max(ends)
                self._duration = self._actual_end - self._actual_start
        else:
            # Sequential cascade: primary shock triggers secondary shocks
            primary = self.shocks[0]
            if primary.start_day is None:
                primary.start_day = des_env.sim_days // 5
            
            self._actual_start = primary.start_day
            des_env.env.process(primary.apply(des_env))
            
            # Wait for primary to start so its actual properties are set
            yield des_env.env.timeout(1)

            # Cascaded trigger check for downstream shocks
            for s in self.shocks[1:]:
                primary_name = primary.__class__.__name__
                sec_name = s.__class__.__name__
                p_trigger = self.cascade_prob_matrix.get((primary_name, sec_name), 0.5)
                
                if self.rng.random() < p_trigger:
                    # Start cascade with a small delay
                    trigger_delay = int(self.rng.integers(1, max(2, (primary.duration or 14) // 2)))
                    s.start_day = primary.start_day + trigger_delay
                    des_env.env.process(s.apply(des_env))
            
            # Wait again for all shocks to spin up
            yield des_env.env.timeout(1)
            starts = [s.shock_start for s in self.shocks if s.shock_start is not None]
            ends = [s.shock_end for s in self.shocks if s.shock_end is not None]
            if starts and ends:
                self._actual_start = min(starts)
                self._actual_end = max(ends)
                self._duration = self._actual_end - self._actual_start

    def get_demand_multiplier(self, customer_id, current_day):
        """
        Parameters
        ----------
        """
        multiplier = 1.0
        for s in self.shocks:
            multiplier *= s.get_demand_multiplier(customer_id, current_day)
        return multiplier

    @property
    def shock_start(self):
        """
        Parameters
        ----------
        """
        return self._actual_start

    @property
    def shock_end(self):
        """
        Parameters
        ----------
        """
        return self._actual_end

    @property
    def duration(self):
        """
        Parameters
        ----------
        """
        return self._duration
