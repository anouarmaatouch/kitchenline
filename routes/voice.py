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

OPENAI_WS_URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime"

@voice_bp.route('/webhooks/event', methods=['POST'])
def event():
    # Log events from Vonage
    data = request.get_json() or {}
    current_app.logger.error(f"event data: {data}")
    return jsonify({'status': 'ok'})

@voice_bp.route('/webhooks/answer', methods=['POST', 'GET'])
def answer_call():
    #return jsonify([{"action": "talk", "text": "Hello, your call is connected."}])

    # "to" is the Vonage number being called
    data = request.get_json() or {}
    to_number = data.get('to') or request.args.get('to')
    from_number = data.get('from') or request.args.get('from')
    
    # Robust Host Resolution
    host = current_app.config.get('PUBLIC_URL')
    if not host:
        host = request.host # e.g. restau.fly.dev
        
    scheme = "wss" if request.is_secure or request.scheme == 'https' else "ws"
    # Force wss on Fly (headers might be stripped locally but usually x-forwarded-proto handles it)
    if 'fly.dev' in host:
        scheme = 'wss'

    ws_uri = f"{scheme}://{host}/voice/stream?to_number={to_number}&caller_number={from_number}"
    
    current_app.logger.info(f"Generating NCCO with WebSocket URI: {ws_uri}")
    
    return jsonify([
        {
            "action": "connect",
            "from": to_number,
            "endpoint": [{
                "type": "websocket",
                "uri": ws_uri,
                "content-type": "audio/l16;rate=24000",
                "headers": {
                    "to-number": to_number,
                    "caller-number": from_number
                }
            }]
        }
    ])

@sock.route('/voice/stream')
def voice_stream(ws):
    """
    Sync implementation using threads/gevent and websocket-client.
    """
    # Accept header with hyphens or underscores, or query param
    to_number = request.args.get('to_number') or request.headers.get('to-number') or request.headers.get('to_number')
    caller_number = request.args.get('caller_number') or request.headers.get('caller-number') or request.headers.get('caller_number')
    
    # Urgent Log
    print(f"DEBUG PRINT: Incoming call to {to_number} from {caller_number}", flush=True)
    current_app.logger.info(f"Incoming call to: {to_number} (Caller: {caller_number})")
    # 1. Fetch Context
    # Normalize query: Try exact match first, then with '+' if missing, or without '+' if present
    user = User.query.filter_by(phone_number=to_number).first()
    if not user and to_number:
        # Try alternatives
        if to_number.startswith('+'):
            user = User.query.filter_by(phone_number=to_number[1:]).first()
        else:
            user = User.query.filter_by(phone_number=f"+{to_number}").first()
    
    current_app.logger.info(f"Incoming call to: {to_number} (Matched User: {user.username if user else 'None'})")
    
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
        # CRITICAL: Use g711_ulaw for telephony (Vonage) - it handles sample rate conversion automatically
        # Alternative: Keep pcm16 but Vonage must be configured for 24kHz (not standard)
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": system_instruction,
                "voice": voice_api,
                "input_audio_format": "pcm16",      # 24kHz raw audio
                "output_audio_format": "pcm16",     # 24kHz raw audio
                "input_audio_transcription": {       # Enable for better speech recognition
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.3,               # Very sensitive - detects speech quickly
                    "prefix_padding_ms": 50,        # Minimal context
                    "silence_duration_ms": 100      # Absolute minimum - responds ASAP after silence
                },
                "tools": [
                {
                    "type": "function",
                    "name": "create_order_tool",
                    "description": "Submit a completed restaurant order after the customer confirms all details.",
                    "parameters": {
                    "type": "object",
                    "properties": {
                        "order_details": {
                        "type": "string",
                        "description": "Full list of ordered items with quantities and options (size, sauce, drink, extras)."
                        },
                        "customer_name": {
                        "type": "string",
                        "description": "Customer's full name as spoken by the caller. Ask to repeat or spell if unclear."
                        }
                    },
                        "required": ["order_details", "customer_name"]
                    }
                }]
            }
        }
        current_app.logger.info(f"OpenAI Session Update: Voice={voice_api}, Instructions_Len={len(system_instruction)}")
        openai_ws.send(json.dumps(session_update))

        # Capture app object for thread context
        app = current_app._get_current_object()

        # Thread 1: Vonage -> OpenAI
        def vonage_to_openai():
            with app.app_context():
                try:
                    while True:
                        data = ws.receive()
                        if not data:
                            current_app.logger.info("Vonage WebSocket closed (empty data)")
                            break
                        
                        if isinstance(data, bytes):
                            audio_b64 = base64.b64encode(data).decode('utf-8')
                            event = {
                                "type": "input_audio_buffer.append",
                                "audio": audio_b64
                            }
                            openai_ws.send(json.dumps(event))
                        else:
                            current_app.logger.debug(f"Received non-byte data from Vonage: {data}")
                except Exception as e:
                    # Check for normal closure code 1000 or 1001 inside string representation if exception class unavailable
                    if "1000" in str(e) or "1001" in str(e):
                         current_app.logger.info("Vonage Call Ended (Normal Closure)")
                    else:
                        current_app.logger.error(f"Vonage -> OpenAI Error: {e}")
                finally:
                    try:
                        openai_ws.close()
                    except:
                        pass

        # Thread 2: OpenAI -> Vonage
        def openai_to_vonage():
            with app.app_context():
                try:
                    while True:
                        try:
                            msg = openai_ws.recv()
                        except websocket.WebSocketConnectionClosedException:
                            current_app.logger.info("OpenAI WebSocket closed")
                            break
                            
                        if not msg:
                            break
                        
                        event = json.loads(msg)
                        event_type = event.get('type')
                        
                        # Handle Interruption: Cancel OpenAI's current response immediately
                        if event_type == 'input_audio_buffer.speech_started':
                             current_app.logger.info("User interruption detected - Cancelling OpenAI response")
                             # Tell OpenAI to stop generating the current response
                             try:
                                 # Cancel the current response
                                 openai_ws.send(json.dumps({"type": "response.cancel"}))
                                 # Clear input audio buffer to start fresh
                                 openai_ws.send(json.dumps({"type": "input_audio_buffer.clear"}))
                             except Exception as cancel_e:
                                 current_app.logger.warning(f"Failed to send cancel: {cancel_e}")
                        
                        # Also handle when user speech ends (to ensure clean state)
                        if event_type == 'input_audio_buffer.speech_stopped':
                             current_app.logger.debug("User stopped speaking")
                        
                        # Log meaningful events (ignore frequent audio deltas to reduce noise)
                        # if event_type not in ['response.audio.delta', 'response.audio_transcript.delta']:
                        #    current_app.logger.info(f"OpenAI Event: {event_type}")

                        if event_type == 'response.audio.delta':
                            audio_b64 = event.get('delta')
                            if audio_b64:
                                audio_bytes = base64.b64decode(audio_b64)
                                try:
                                    ws.send(audio_bytes)
                                except Exception as send_e:
                                    # If Vonage closed, we might fail to send
                                    if "1000" in str(send_e) or "1001" in str(send_e):
                                        break
                                    raise send_e
                        
                        elif event_type == 'response.function_call_arguments.done':
                            call_id = event.get('call_id')
                            args_str = event.get('arguments')
                            name = event.get('name')
                            
                            if name == 'create_order_tool':
                                args = json.loads(args_str)
                                current_app.logger.info(f"Creating Order: {args}")
                                
                                try:
                                    # Create Order
                                    with current_app.app_context():
                                        new_order = Order(
                                            status='recu',
                                            order_detail=args.get('order_details'),
                                            customer_name=args.get('customer_name', 'Unknown'),
                                            customer_phone=caller_number or 'Unknown',
                                            company_phone=to_number,
                                            address='Non defini'
                                        )
                                        db.session.add(new_order)
                                        db.session.commit()
                                        
                                        # Output
                                        order_id = new_order.id
                                        add_event('new_order', {'message': 'Ordre reçu'})
                                        
                                        # Send Push Notification
                                        try:
                                            from routes.notifications import send_web_push
                                            send_web_push({
                                                "title": "Ordre reçus",
                                                "message": f"{args.get('customer_name', 'Client')} : {args.get('order_details', 'Nouvelle commande')}"
                                            })
                                        except Exception as push_e:
                                            current_app.logger.error(f"Push notification error: {push_e}")

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
                    if "1000" in str(e) or "1001" in str(e):
                        current_app.logger.info("OpenAI -> Vonage loop ended (Client disconnected)")
                    else:
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
