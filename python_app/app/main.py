import os
import uuid
import logging
import atexit
from fastapi import FastAPI, WebSocket, Request, Response, WebSocketDisconnect
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

# --- Logging estructurado ---
LoggingInstrumentor().instrument()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# --- Recursos ---
resource = Resource(attributes={SERVICE_NAME: "fastapi-server"})

# --- Tracer ---
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(span_exporter))

# --- Métricas: intervalo configurable ---
default_interval_ms = 30000  # 30 segundos (producción)
export_interval_ms = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", default_interval_ms))

metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=endpoint, insecure=True),
    export_interval_millis=export_interval_ms
)

meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
metrics.set_meter_provider(meter_provider)

# Métricas de WebSocket
meter = metrics.get_meter("fastapi-websocket")
active_connections = meter.create_up_down_counter(
    "websocket.active_connections",
    description="Number of active WebSocket connections"
)
broadcast_counter = meter.create_counter(
    "websocket.broadcast.total",
    description="Total messages broadcasted"
)

# Métricas del sistema
SystemMetricsInstrumentor().instrument()

# --- App ---
app = FastAPI(
    title="Servidor Python con FastAPI y WebSockets",
    description="API de ejemplo con OpenTelemetry y WebSockets.",
    version="1.0.0",
)

# Instrumentación completa (traces + métricas HTTP)
FastAPIInstrumentor.instrument_app(app)

# --- Models & Events ---
from app.models import Message, Event
from app.events import manager

@app.post("/notify", tags=["Notificaciones"])
async def send_notification(message: Message, request: Request, response: Response):
    with tracer.start_as_current_span("send_notification_event") as span:
        event_id = str(uuid.uuid4())
        span.set_attribute("event.id", event_id)
        span.set_attribute("event.message", message.message)

        event = Event(event_id=event_id, message=message.message)
        await manager.broadcast(event.model_dump_json())
        broadcast_counter.add(1)
        return {"status": "success", "event_id": event_id}

@app.websocket("/ws/events/")
async def websocket_endpoint(websocket: WebSocket):
    with tracer.start_as_current_span("websocket_connection") as span:
        await manager.connect(websocket)
        active_connections.add(1)
        span.add_event("connection_accepted")
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            span.add_event("client_disconnected")
            log.info("Client disconnected normally")
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            log.exception("WebSocket error")
        finally:
            manager.disconnect(websocket)
            active_connections.add(-1)

# --- Shutdown ---
def _shutdown_otel():
    try:
        metrics.get_meter_provider().shutdown()
        trace.get_tracer_provider().shutdown()
        log.info("OpenTelemetry providers shutdown")
    except Exception as e:
        log.warning(f"Error shutting down OTel: {e}")

atexit.register(_shutdown_otel)

# --- Log de intervalo ---
log.info(f"Métricas se exportan cada {export_interval_ms/1000:.1f} segundos")