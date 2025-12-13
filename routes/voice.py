import json
import base64
import threading
import websocket
import os
from flask import Blueprint, request, jsonify, current_app
from extensions import sock, db
from models import User, Order
from routes.orders import add_event

voice_bp = Blueprint('voice', __name__)

OPENAI_WS_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"

@voice_bp.route('/webhooks/event', methods=['POST'])
def event():
    # Log events from Vonage
    data = request.get_json() or {}
    current_app.logger.error(f"event data: {data}")
    return jsonify({'status': 'ok'})

@voice_bp.route('/webhooks/answer', methods=['POST', 'GET'])
def answer_call():
    return jsonify([{"action": "talk", "text": "Hello, your call is connected."}])

    # "to" is the Vonage number being called
    data = request.get_json() or {}
    to_number = data.get('to') or request.args.get('to')
    from_number = data.get('from') or request.args.get('from')
    host = current_app.config['PUBLIC_URL']
    
    return jsonify([
        {
            "action": "connect",
            "from": to_number,
            "endpoint": [{
                "type": "websocket",
                "uri": f"wss://{host}/voice/stream",
                "content-type": "audio/l16;rate=16000",
                "headers": {
                    "to_number": to_number,
                    "caller_number": from_number
                }
            }]
        }
    ])

@sock.route('/voice/stream')
def voice_stream(ws):
    """
    Sync implementation using threads/gevent and websocket-client.
    """
    to_number = request.headers.get('to_number') or request.args.get('to_number')
    caller_number = request.headers.get('caller_number') or request.args.get('caller_number')
    
    # 1. Fetch Context
    user = User.query.filter_by(phone_number=to_number).first()
    
    if user and not user.agent_on:
        # Agent is OFF
        # We can play a message or just close
        # Ideally we should assume the webhook 'answer' handles this, but here we can just close with a text to speech?
        # OpenAI Realtime doesn't support "just say one thing and leave" easily without connection.
        # But we can just return early or not connect. 
        # But vonage is already connected to this websocket.
        # We'll just close for now or let it be silent.
        # Better: Connect to OpenAI just to say "We are closed" (expensive?) or just close socket.
        current_app.logger.info(f"Call rejected: Agent Off for {to_number}")
        ws.close()
        return

    system_instruction = "You are a helpful AI assistant taking food orders."
    voice_api = 'sage' # Default
    
    if user:
        if user.system_prompt:
             system_instruction = user.system_prompt
        if user.menu:
             system_instruction += f"\n\nHere is the Menu:\n{user.menu}"
        if user.voice:
             voice_api = user.voice
    
    system_instruction += "\n\nWhen the order is confirmed, you MUST use the 'create_order_tool' to submit it. Ask for name and address if missing."

    # 2. Connect to OpenAI
    api_key = current_app.config['OPENAI_API_KEY']
    # websocket-client accepts list of strings for headers
    headers = [
        f"Authorization: Bearer {api_key}",
        "OpenAI-Beta: realtime=v1"
    ]
    
    try:
        openai_ws = websocket.create_connection(OPENAI_WS_URL, header=headers)
    except Exception as e:
        current_app.logger.error(f"Failed to connect to OpenAI: {e}")
        return

    try:
        # Initialize Session
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": system_instruction,
                "voice": voice_api,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500
                },
                "tools": [{
                    "type": "function",
                    "name": "create_order_tool",
                    "description": "Submit a completed order to the restaurant system.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_details": {"type": "string", "description": "The full details of the items ordered"},
                            "customer_name": {"type": "string", "description": "Name of the customer"},
                            "customer_address": {"type": "string", "description": "Delivery address"},
                        },
                        "required": ["order_details"]
                    }
                }]
            }
        }
        openai_ws.send(json.dumps(session_update))

        # Thread 1: Vonage -> OpenAI
        def vonage_to_openai():
            try:
                while True:
                    # Blocking read from Vonage (Flask-Sock)
                    data = ws.receive()
                    if not data:
                        break
                    
                    if isinstance(data, bytes):
                        # Audio
                        audio_b64 = base64.b64encode(data).decode('utf-8')
                        event = {
                            "type": "input_audio_buffer.append",
                            "audio": audio_b64
                        }
                        openai_ws.send(json.dumps(event))
                    else:
                        # Control message or text?
                        pass
            except Exception as e:
                current_app.logger.error(f"Vonage -> OpenAI Error: {e}")
            finally:
                try:
                    openai_ws.close()
                except:
                    pass

        # Thread 2: OpenAI -> Vonage
        def openai_to_vonage():
            # We need to preserve app context if we access DB
            # But the thread target doesn't inherit it automatically unless we pass it 
            # or rely on current_app being proxied correctly in gevent if not detached.
            # Safest is to use app.app_context()
            
            # However, since we define this function inside the request scope, 
            # 'current_app' is captured from closure? 
            # current_app is a proxy. It should work if the request context is alive.
            # But request context corresponds to the main thread handling the request.
            # If that thread is blocked on 't1.join()', context is alive.
            # Yes, we will join threads at end of request handler.
            
            try:
                while True:
                    # Blocking read from OpenAI
                    try:
                        msg = openai_ws.recv()
                    except websocket.WebSocketConnectionClosedException:
                        break
                        
                    if not msg:
                        break
                    
                    event = json.loads(msg)
                    event_type = event.get('type')
                    
                    if event_type == 'response.audio.delta':
                        audio_b64 = event.get('delta')
                        if audio_b64:
                            audio_bytes = base64.b64decode(audio_b64)
                            ws.send(audio_bytes)
                    
                    elif event_type == 'response.function_call_arguments.done':
                        call_id = event.get('call_id')
                        args_str = event.get('arguments')
                        name = event.get('name')
                        
                        if name == 'create_order_tool':
                            args = json.loads(args_str)
                            current_app.logger.info(f"Creating Order: {args}")
                            
                            try:
                                # We need a new session or properly scoped one
                                # db.session is scoped.
                                with current_app.app_context():
                                    new_order = Order(
                                        status='recu',
                                        order_detail=args.get('order_details'),
                                        customer_name=args.get('customer_name', 'Unknown'),
                                        customer_phone=caller_number or 'Unknown',
                                        address=args.get('customer_address', 'Pickup')
                                    )
                                    db.session.add(new_order)
                                    db.session.commit()
                                    
                                    # Output
                                    order_id = new_order.id
                                    add_event('new_order', {'message': 'Ordre reçu'})

                                # Send Output
                                output_event = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps({"status": "success", "order_id": order_id})
                                    }
                                }
                                openai_ws.send(json.dumps(output_event))
                                openai_ws.send(json.dumps({"type": "response.create"}))
                                
                            except Exception as db_e:
                                current_app.logger.error(f"DB Error: {db_e}")

            except Exception as e:
                current_app.logger.error(f"OpenAI -> Vonage Error: {e}")
            finally:
                try:
                    # Closing downstream
                    ws.close()
                except:
                    pass

        t1 = threading.Thread(target=vonage_to_openai)
        t2 = threading.Thread(target=openai_to_vonage)
        
        t1.start()
        t2.start()
        
        # Keep the main handler alive until threads finish
        t1.join()
        t2.join()

    except Exception as e:
        current_app.logger.error(f"Voice Stream Error: {e}")
    finally:
        try:
            openai_ws.close()
        except:
            pass
