from typing import List
from fastapi import WebSocket
from opentelemetry import trace

# No es necesario hacer cambios aquí si se usa la instrumentación automática,
# pero se podría hacer instrumentación manual si fuera necesario.
# tracer = trace.get_tracer("events")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

