
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ConnectionManager import ConnectionManager
from MathProcessor import MathProcessor
from CognitiveEngine import CognitiveEngine

app = FastAPI()
manager = ConnectionManager()

@app.get("/")
def read_root():
    return {"status": "ITIM Backend Running"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "stroke":
                print(f"Stroke received: {len(message['points'])} points")
                await manager.broadcast(data)

            elif message.get("type") == "user_message":
                user_text = message.get("text")
                print(f"Chat: {user_text}")
                
                response = {
                    "type": "tutor_message",
                    "text": f"J'ai bien reçu ton message : '{user_text}'. J'analyse tes calculs...",
                    "role": "assistant"
                }
                await websocket.send_json(response)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("Client disconnected")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7000)