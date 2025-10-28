# import os
# import uuid
# from fastapi import FastAPI, WebSocket, Request, Response
# from app.models import Message, Event
# from app.events import manager
# from opentelemetry import trace, context
# from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
# from opentelemetry.sdk.trace import TracerProvider
# from opentelemetry.sdk.trace.export import BatchSpanProcessor
# from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
# from opentelemetry.sdk.resources import Resource, SERVICE_NAME

# # Configuración de OpenTelemetry
# resource = Resource(attributes={
#     SERVICE_NAME: "fastapi-server",
# })
# provider = TracerProvider(resource=resource)

# # Leer el endpoint del colector de la variable de entorno
# # Si no se define, se usará el valor por defecto 'otel-collector:4317'
# otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector:4317")
# otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)
# provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

# trace.set_tracer_provider(provider)
# tracer = trace.get_tracer(__name__)

# # Instanciamos la aplicación de FastAPI
# app = FastAPI(
#     title="Servidor Python con FastAPI y WebSockets",
#     description="API de ejemplo con OpenTelemetry y WebSockets.",
#     version="1.0.0",
# )

# FastAPIInstrumentor.instrument_app(app)

# @app.post("/notify", tags=["Notificaciones"])
# async def send_notification(message: Message, request: Request, response: Response):
#     """
#     Envía una notificación de evento a todos los clientes conectados.
#     """
#     with tracer.start_as_current_span("send_notification_event") as span:
#         event_id = str(uuid.uuid4())
#         span.set_attribute("event.id", event_id)
#         span.set_attribute("event.message", message.message)
#         event = Event(event_id=event_id, message=message.message)
#         await manager.broadcast(event.model_dump_json())
#         return {"status": "success", "event_id": event_id}

# @app.websocket("/ws/events/")
# async def websocket_endpoint(websocket: WebSocket):
#     """
#     Endpoint de WebSocket para que los clientes reciban notificaciones en tiempo real.
#     """
#     with tracer.start_as_current_span("websocket_connection") as span:
#         await manager.connect(websocket)
#         span.add_event("websocket connection accepted")
#         ctx = context.get_current()
#         try:
#             while True:
#                 await websocket.receive_text()
#         except Exception as e:
#             span.add_event("websocket disconnect", attributes={"error": str(e)})
#             manager.disconnect(websocket)
#             span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
#         finally:
#             span.end()
import os
import uuid
from fastapi import FastAPI, WebSocket, Request, Response
from app.models import Message, Event
from app.events import manager
from opentelemetry import trace, context
from opentelemetry.metrics import set_meter_provider, get_meter_provider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor # <--- Importar

# Configuración de OpenTelemetry para trazas
resource = Resource(attributes={
    SERVICE_NAME: "fastapi-server",
})
provider = TracerProvider(resource=resource)
otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector:4317")
otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

# Configuración de OpenTelemetry para métricas
metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=otel_endpoint, insecure=True)
)
meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
set_meter_provider(meter_provider)

meter = get_meter_provider().get_meter("fastapi-server-metrics")
requests_counter = meter.create_counter(
    "api.requests.total",
    description="Number of total requests to the API",
)

# Iniciar el instrumentador de métricas del sistema <--- Añadir esto
SystemMetricsInstrumentor().instrument()

# Instanciamos la aplicación de FastAPI
app = FastAPI(
    title="Servidor Python con FastAPI y WebSockets",
    description="API de ejemplo con OpenTelemetry y WebSockets.",
    version="1.0.0",
)

# Instrumentamos FastAPI automáticamente para los endpoints HTTP
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)

@app.post("/notify", tags=["Notificaciones"])
async def send_notification(message: Message, request: Request, response: Response):
    """
    Envía una notificación de evento a todos los clientes conectados.
    """
    requests_counter.add(1, {"endpoint": "/notify"})

    with tracer.start_as_current_span("send_notification_event") as span:
        event_id = str(uuid.uuid4())
        span.set_attribute("event.id", event_id)
        span.set_attribute("event.message", message.message)
        event = Event(event_id=event_id, message=message.message)
        await manager.broadcast(event.model_dump_json())
        return {"status": "success", "event_id": event_id}

@app.websocket("/ws/events/")
async def websocket_endpoint(websocket: WebSocket):
    """
    Endpoint de WebSocket para que los clientes reciban notificaciones en tiempo real.
    """
    with tracer.start_as_current_span("websocket_connection") as span:
        await manager.connect(websocket)
        span.add_event("websocket connection accepted")
        ctx = context.get_current()
        try:
            while True:
                await websocket.receive_text()
        except Exception as e:
            span.add_event("websocket disconnect", attributes={"error": str(e)})
            manager.disconnect(websocket)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
        finally:
            span.end()
