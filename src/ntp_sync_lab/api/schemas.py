"""HTTP-only models. Exact timestamps/offsets remain decimal strings in OpenAPI."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

DecimalMs = Annotated[str, Field(strict=True, max_length=128, pattern=r'^-?[0-9]+(?:\.[0-9]{1,6})?$')]
IntegerNs = Annotated[str, Field(strict=True, max_length=128, pattern=r'^-?(?:0|[1-9][0-9]*)$')]
ExactNs = Annotated[str, Field(strict=True, pattern=r'^-?[0-9]+(?:\.[0-9]+)?$')]

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')

class MeasurementInput(Input):
    server_id: str = Field(default='pool', min_length=1, max_length=64)
    timeout_seconds: float = Field(default=3, ge=0.1, le=10, allow_inf_nan=False)

    @model_validator(mode='before')
    @classmethod
    def numeric_timeout(cls, value):
        if isinstance(value, dict) and 'timeout_seconds' in value and type(value['timeout_seconds']) not in (int, float):
            raise ValueError('timeout_seconds must be a JSON number')
        return value

class DelayInput(Input):
    preset: str | None = Field(default=None, max_length=64)
    true_offset_ms: DecimalMs | None = None
    forward_ms: DecimalMs | None = None
    reverse_ms: DecimalMs | None = None
    processing_ms: DecimalMs | None = None
    reference_unix_ns: IntegerNs | None = None
    round_trip_ms: DecimalMs | None = None
    sweep_points: int | None = Field(default=None, strict=True, ge=2, le=200)
    increments_ms: list[DecimalMs] | None = Field(default=None, min_length=2, max_length=200)

class SyncInput(Input):
    client_offset_ms: DecimalMs = '120'
    forward_ms: DecimalMs = '20'
    reverse_ms: DecimalMs = '20'
    processing_ms: DecimalMs = '5'
    reference_unix_ns: IntegerNs | None = None
    mode: Literal['step'] = 'step'

class ReplayInput(Input):
    recording_id: str | None = Field(default=None, min_length=1, max_length=64)
    scenario_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode='after')
    def one_selection(self):
        if (self.recording_id is None) == (self.scenario_id is None):
            raise ValueError('provide exactly one recording_id or scenario_id')
        return self

class Timestamps(BaseModel):
    t1_unix_ns: IntegerNs
    t2_unix_ns: IntegerNs
    t3_unix_ns: IntegerNs
    t4_unix_ns: IntegerNs

class ExchangeData(BaseModel):
    model_config = ConfigDict(extra='allow')
    __pydantic_extra__: dict[str, JsonValue]
    timestamps: Timestamps
    estimated_offset_ns: ExactNs
    round_trip_delay_ns: IntegerNs
    client_elapsed_ns: IntegerNs
    server_processing_ns: IntegerNs
    true_offset_ns: ExactNs | None
    estimation_error_ns: ExactNs | None

class Result(BaseModel):
    schema_version: Literal['1']
    experiment: Literal['real_exchange', 'network_delay', 'clock_sync']
    source: Literal['live', 'simulation']
    result_id: str
    created_at_utc: str
    provenance: dict[str, JsonValue]
    parameters: dict[str, JsonValue]
    data: ExchangeData
    warnings: list[str]
    assumptions: list[str]

class Snapshot(BaseModel):
    reference_unix_ns: IntegerNs
    virtual_client_unix_ns: ExactNs
    client_error_ns: ExactNs

class TimelinePoint(Snapshot):
    sequence: int
    stage: str
    applied_correction_ns: ExactNs

class SyncData(ExchangeData):
    initial_client_error_ns: IntegerNs
    applied_correction_ns: ExactNs
    final_client_error_ns: ExactNs
    measurement: Result
    before: Snapshot
    after: Snapshot
    correction_event: dict[str, JsonValue]
    timeline: list[TimelinePoint]
    explanation: list[str]
    conclusion: str

class SyncResult(Result):
    data: SyncData

class SeriesData(BaseModel):
    points: list[Result]

class SeriesResult(Result):
    data: SeriesData

class ReplayResult(BaseModel):
    schema_version: Literal['1']
    experiment: str
    source: Literal['replay']
    provenance: dict[str, JsonValue]
    # Preserved legacy batch or result; never coerced/re-serialized as a new capture.
    recording: dict[str, JsonValue]

class ErrorInfo(BaseModel):
    code: str
    message: str
    details: dict[str, JsonValue]

class ErrorResult(BaseModel):
    schema_version: Literal['1'] = '1'
    error: ErrorInfo
