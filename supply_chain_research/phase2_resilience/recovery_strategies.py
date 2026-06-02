"""Recovery strategies for mitigating disruption impacts in the DES environment."""

class RecoveryStrategy:
    """Base class for recovery strategies.
    Parameters
    ----------
    """
    def apply(self, des_env):
        """
        Parameters
        ----------
        """
        raise NotImplementedError("Subclasses must implement apply()")

    def get_demand_multiplier(self, customer_id, current_day):
        """
        Parameters
        ----------
        """
        return 1.0

    @property
    def shock_start(self):
        """
        Parameters
        ----------
        """
        return None

    @property
    def shock_end(self):
        """
        Parameters
        ----------
        """
        return None

    @property
    def duration(self):
        """
        Parameters
        ----------
        """
        return 0


class CapacitySharing(RecoveryStrategy):
    """Capacity sharing: healthy warehouses daily share inventory with shocked warehouses.

    Attributes:
        transfer_threshold_pct: Target inventory level fraction under which a warehouse requests sharing.
        transfer_amount: Daily maximum quantity in kg transferred per shocked warehouse.
    
    Parameters
    ----------
    """

    def __init__(self, transfer_threshold_pct=0.2, transfer_amount=2000.0):
        """
        Parameters
        ----------
        """
        self.transfer_threshold_pct = transfer_threshold_pct
        self.transfer_amount = transfer_amount

    def apply(self, des_env):
        """
        Parameters
        ----------
        """
        while True:
            yield des_env.env.timeout(1)  # Check daily
            
            # Find shocked and healthy warehouses
            shocked_whs = [wh for wh in des_env.warehouses if wh.shock_factor < 0.9]
            healthy_whs = [wh for wh in des_env.warehouses if wh.shock_factor >= 0.9]
            
            if shocked_whs and healthy_whs:
                for target_wh in shocked_whs:
                    if target_wh.level < target_wh.capacity * self.transfer_threshold_pct:
                        # Find the healthy warehouse with the highest inventory level
                        source_wh = max(healthy_whs, key=lambda w: w.level)
                        if source_wh.level > source_wh.capacity * 0.4:
                            qty = min(self.transfer_amount, source_wh.level - source_wh.capacity * 0.3)
                            if qty > 0:
                                yield source_wh.container.get(qty)
                                yield target_wh.container.put(qty)
                                
                                # Add cost penalty for inter-facility shipping
                                current_idx = int(des_env.env.now) - des_env.warmup_days - 1
                                if 0 <= current_idx < len(des_env.daily_costs):
                                    # Charge standard rate per km for distance between them (approximate distance)
                                    inter_distance = 100.0  # standard inter-warehouse transfer distance in km
                                    des_env.daily_costs[current_idx] += float(inter_distance * des_env.config.vehicle.hcv_cost_per_km)


class BackupSupplier(RecoveryStrategy):
    """Backup supplier activation: boost replenishment rate under critical inventory levels.

    Attributes:
        trigger_level_pct: Warehouse inventory fraction below which backup is triggered.
        backup_boost_factor: Multiplier to replenishment rate (e.g. 1.5x replenishment).
        premium_order_cost: Fixed premium cost (INR) charged per day backup is active.
    
    Parameters
    ----------
    """

    def __init__(self, trigger_level_pct=0.15, backup_boost_factor=1.5, premium_order_cost=5000.0):
        """
        Parameters
        ----------
        """
        self.trigger_level_pct = trigger_level_pct
        self.backup_boost_factor = backup_boost_factor
        self.premium_order_cost = premium_order_cost

    def apply(self, des_env):
        """
        Parameters
        ----------
        """
        orig_rates = [wh.replenishment_rate for wh in des_env.warehouses]
        while True:
            yield des_env.env.timeout(1)
            for i, wh in enumerate(des_env.warehouses):
                if wh.shock_factor < 0.9:
                    if wh.level < wh.capacity * self.trigger_level_pct:
                        # Activate backup supplier
                        wh.replenishment_rate = orig_rates[i] * self.backup_boost_factor
                        current_idx = int(des_env.env.now) - des_env.warmup_days - 1
                        if 0 <= current_idx < len(des_env.daily_costs):
                            des_env.daily_costs[current_idx] += self.premium_order_cost
                    else:
                        wh.replenishment_rate = orig_rates[i]
                else:
                    wh.replenishment_rate = orig_rates[i]
        orig_rates = [wh.replenishment_rate for wh in des_env.warehouses]
        while True:
            yield des_env.env.timeout(1)
            for i, wh in enumerate(des_env.warehouses):
                if wh.shock_factor < 0.9:
                    if wh.level < wh.capacity * self.trigger_level_pct:
                        # Activate backup supplier
                        wh.replenishment_rate = orig_rates[i] * self.backup_boost_factor
                        current_idx = int(des_env.env.now) - des_env.warmup_days - 1
                        if 0 <= current_idx < len(des_env.daily_costs):
                            des_env.daily_costs[current_idx] += self.premium_order_cost
                    else:
                        wh.replenishment_rate = orig_rates[i]
                else:
                    wh.replenishment_rate = orig_rates[i]
