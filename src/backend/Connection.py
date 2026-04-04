from fastapi import FastAPI, WebSocket
import json

app = FastAPI()

@websocket_route("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connecté !")
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Si on reçoit un trait (stroke)
            if message.get("type") == "stroke":
                print(f"Trait reçu : {len(message['points'])} points")
                # Ici on appellera ton moteur ACT-R
                await websocket.send_text(json.dumps({
                    "type": "tutor_response",
                    "text": "Bien reçu ! J'analyse ton calcul..."
                }))
    except Exception as e:
        print(f"Déconnexion : {e}")