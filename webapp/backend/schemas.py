"""Pydantic response models for the FastAPI backend.

Stable API contract — every endpoint returns one of these models.
This makes the OpenAPI schema self-documenting and prevents accidental
exposure of internal object attributes.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str


class KPIValue(BaseModel):
    value: float
    unit: str
    change: float
    label: str


class TrainingStatusFlags(BaseModel):
    nsga2_complete: bool
    lstm_complete: bool
    ppo_complete: bool
    des_complete: bool


class NetworkInfo(BaseModel):
    warehouses: int
    customers: int
    routes_active: int
    vehicles: Dict[str, int]


class DashboardSummaryResponse(BaseModel):
    training_status: Optional[TrainingStatusFlags] = None
    kpis: Optional[Dict[str, KPIValue]] = None
    network: Optional[NetworkInfo] = None
    training_details: Optional[Dict[str, Dict[str, Any]]] = None
    is_mock_data: bool = False
    is_mock: Optional[bool] = None
    status: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Any] = None
    data_sources: Optional[Dict[str, str]] = None


class WarehouseNode(BaseModel):
    id: str
    name: str
    lat: float
    lng: float
    capacity: float


class CustomerNode(BaseModel):
    id: str
    lat: float
    lng: float
    demand: float


class NetworkNodesResponse(BaseModel):
    warehouses: List[WarehouseNode]
    customers: List[CustomerNode]


class ParetoPoint(BaseModel):
    id: int
    cost: float
    carbon: float
    service_level: Optional[float] = None
    ev_fraction: Optional[float] = None


class ParetoFrontResponse(BaseModel):
    points: Optional[List[ParetoPoint]] = None
    is_mock: bool = False
    status: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Any] = None
    params_used: Optional[Dict[str, Any]] = None
    note: Optional[str] = None


class HypervolumeHistory(BaseModel):
    generation: Optional[int] = None
    seed: Optional[int] = None
    hypervolume: float
    std: Optional[float] = None


class HypervolumeResponse(BaseModel):
    history: Optional[List[HypervolumeHistory]] = None
    n_seeds: Optional[int] = None
    is_mock: bool = False
    status: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Any] = None


class ServiceLevelDataPoint(BaseModel):
    day: int
    service_level: float


class MCSample(BaseModel):
    run: int
    service_level: float


class ServiceLevelStatistics(BaseModel):
    mean: float
    std: float
    min: float
    max: float
    n_simulations: int


class ServiceLevelResponse(BaseModel):
    data: Optional[List[ServiceLevelDataPoint]] = None
    mc_samples: Optional[List[MCSample]] = None
    statistics: Optional[ServiceLevelStatistics] = None
    is_mock: bool = False
    status: Optional[str] = None
    error: Optional[str] = None
    data_sources: Optional[Dict[str, str]] = None


class ResilienceMetric(BaseModel):
    value: float
    unit: str
    description: str


class ResilienceMetricsResponse(BaseModel):
    metrics: Optional[Dict[str, ResilienceMetric]] = None
    is_mock: bool = False
    status: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Any] = None


class ForecastDataPoint(BaseModel):
    day: int
    demand: float
    type: str


class ForecastMetrics(BaseModel):
    mape: float
    rmse: float
    mae: float


class ForecastDataInfo(BaseModel):
    total_predictions_shape: List[int]
    total_actuals_shape: List[int]
    displayed_days: int
    customer_index: int


class ForecastResponse(BaseModel):
    historical: Optional[List[ForecastDataPoint]] = None
    forecast: Optional[List[ForecastDataPoint]] = None
    metrics: Optional[ForecastMetrics] = None
    data_info: Optional[ForecastDataInfo] = None
    is_mock: bool = False
    status: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Any] = None


class ShockEvent(BaseModel):
    day: int
    type: str
    label: str


class ShockResponse(BaseModel):
    service_level: Optional[List[ServiceLevelDataPoint]] = None
    baseline: Optional[float] = None
    shock_events: Optional[List[ShockEvent]] = None
    params_used: Dict[str, Any]
    is_mock: bool = True
    note: Optional[str] = None


class AttentionWeightPoint(BaseModel):
    forecast_step: str
    feature: str
    weight: float


class AttentionWeightsResponse(BaseModel):
    features: Optional[List[str]] = None
    forecast_steps: Optional[List[str]] = None
    heatmap: Optional[List[AttentionWeightPoint]] = None
    is_mock: bool = True
    status: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Any] = None
    note: Optional[str] = None
