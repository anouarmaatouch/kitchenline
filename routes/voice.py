import json
import os
import collections
import base64
import asyncio
import threading
import audioop
from flask import Blueprint, request, jsonify, current_app
from extensions import sock, db
from models import User, Order
from routes.orders import add_event

voice_bp = Blueprint('voice', __name__)

# Gemini model for voice
GEMINI_MODEL = "gemini-live-2.5-flash-native-audio"
# GEMINI_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

@voice_bp.route('/webhooks/event', methods=['POST'])
def event():
    data = request.get_json() or {}
    current_app.logger.info(f"Vonage event: {data}")
    return jsonify({'status': 'ok'})

@voice_bp.route('/webhooks/answer', methods=['POST', 'GET'])
def answer_call():
    data = request.get_json() or {}
    to_number = data.get('to') or request.args.get('to')
    from_number = data.get('from') or request.args.get('from')
    
    host = current_app.config.get('PUBLIC_URL')
    if not host:
        host = request.host
        
    scheme = "wss" if request.is_secure or request.scheme == 'https' else "ws"
    if 'fly.dev' in host:
        scheme = 'wss'

    ws_uri = f"{scheme}://{host}/voice/stream?to_number={to_number}&caller_number={from_number}"
    
    current_app.logger.info(f"NCCO WebSocket URI: {ws_uri}")
    
    return jsonify([
        {
            "action": "connect",
            "from": to_number,
            "endpoint": [{
                "type": "websocket",
                "uri": ws_uri,
                "content-type": "audio/l16;rate=16000",
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
    Handle incoming voice stream from Vonage using Gemini Live API.
    Uses threading to bridge sync Flask-Sock with async Gemini SDK.
    """
    to_number = request.args.get('to_number') or request.headers.get('to-number')
    caller_number = request.args.get('caller_number') or request.headers.get('caller-number')
    
    current_app.logger.info(f"📞 Incoming call to: {to_number} from: {caller_number}")
    
    # Fetch user context
    user = User.query.filter_by(phone_number=to_number).first()
    if not user and to_number:
        if to_number.startswith('+'):
            user = User.query.filter_by(phone_number=to_number[1:]).first()
        else:
            user = User.query.filter_by(phone_number=f"+{to_number}").first()
    
    if user and not user.agent_on:
        current_app.logger.info(f"Agent OFF for {to_number}")
        ws.close()
        return
    
    # Build system instruction
    # Build system instruction (Moroccan Darija default)
    # Build system instruction (Moroccan Darija default)
    # Build system instruction (Moroccan Darija default)
    system_instruction = "You are a friendly AI restaurant assistant. You MUST speak in strictly Moroccan Darija (Arabic dialect). (تكلم بالدارجة المغربية فقط). Do not speak French or standard Arabic unless requested. Be polite and helpful."
    voice_name = "Puck"
    
    if user:
        if user.voice:
            voice_name = user.voice
        if user.system_prompt:
            system_instruction = user.system_prompt
        
        # Enforce Darija
        system_instruction += "\n\nIMPORTANT: Speak in Moroccan Darija (Arabic dialect) at all times."
        if user.menu:
            system_instruction += f"\n\nHere is the Menu:\n{user.menu}"
    
    system_instruction += "\n\nWhen the order is confirmed, use the 'create_order' function to submit it. Always ask for the customer's name."
    
    app = current_app._get_current_object()
    app = current_app._get_current_object()
    
    # Vertex AI Credentials
    creds_path = os.path.abspath("vertex-json.json")
    if os.path.exists(creds_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
    else:
        current_app.logger.error(f"Vertex message: Creds not found at {creds_path}")
    
    current_app.logger.info("🔗 Starting Gemini Live session...")
    
    # Shared state between threads
    stop_event = threading.Event()
    audio_queue = collections.deque()
    audio_lock = threading.Lock()
    
    def gemini_thread():
        """Run Gemini in a separate thread with its own event loop"""
        
        async def run_gemini():
            from google import genai
            from google.genai import types
            
            try:
                # Initialize Vertex AI Client
                client = genai.Client(
                    vertexai=True,
                    project="polar-equinox-472800-j2",
                    location="us-central1"
                )
                
                # Define order creation tool
                create_order_tool = types.FunctionDeclaration(
                    name="create_order",
                    description="Submit a completed restaurant order after the customer confirms.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "order_details": types.Schema(
                                type=types.Type.STRING,
                                description="Full list of ordered items"
                            ),
                            "customer_name": types.Schema(
                                type=types.Type.STRING,
                                description="Customer's full name"
                            ),
                            "address": types.Schema(
                                type=types.Type.STRING,
                                description="Delivery address if provided, otherwise leave empty or 'Non defini'"
                            ),
                        },
                        required=["order_details", "customer_name"]
                    )
                )
                
                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                        )
                    ),
                    system_instruction=types.Content(
                        parts=[types.Part(text=system_instruction)]
                    ),
                    tools=[types.Tool(function_declarations=[create_order_tool])]
                )
                
                async with client.aio.live.connect(
                    model=GEMINI_MODEL,
                    config=config
                ) as session:
                    with app.app_context():
                        current_app.logger.info("✅ Connected to Gemini Live!")
                        
                        # Trigger Greeting
                        await session.send(input="The customer is online. Say 'Salam' and ask for their order in Moroccan Darija.", end_of_turn=True)
                    
                    # Task to send audio to Gemini
                    async def send_audio():
                        while not stop_event.is_set():
                            audio_data = None
                            with audio_lock:
                                if audio_queue:
                                    audio_data = audio_queue.popleft()
                            
                            if audio_data:
                                try:
                                    await session.send(
                                        input=types.LiveClientRealtimeInput(
                                            media_chunks=[types.Blob(
                                                mime_type="audio/pcm",
                                                data=audio_data
                                            )]
                                        )
                                    )
                                except Exception as e:
                                    with app.app_context():
                                        current_app.logger.error(f"Send to Gemini error: {e}")
                                    break
                            else:
                                await asyncio.sleep(0.005)
                    
                    # Resampling state (24k -> 16k)
                    resample_state = None

                    # Task to receive from Gemini
                    async def receive_audio():
                        nonlocal resample_state
                        try:
                            while not stop_event.is_set():
                                try:
                                    async for response in session.receive():
                                        if stop_event.is_set():
                                            break
                                        
                                        # Handle audio response
                                        if response.server_content and response.server_content.model_turn:
                                            for part in response.server_content.model_turn.parts:
                                                if part.inline_data and part.inline_data.data:
                                                    try:
                                                        # Resample 24kHz (Gemini) -> 16kHz (Vonage)
                                                        # audioop.ratecv(fragment, width, nchannels, inrate, outrate, state)
                                                        fragment = part.inline_data.data
                                                        new_fragment, resample_state = audioop.ratecv(
                                                            fragment, 2, 1, 24000, 16000, resample_state
                                                        )
                                                        ws.send(new_fragment)
                                                    except Exception as e:
                                                        with app.app_context():
                                                            current_app.logger.info(f"Vonage closed or send error: {e}")
                                                        stop_event.set()
                                                        return
                                        
                                        # Handle function calls
                                        if response.tool_call:
                                            for fc in response.tool_call.function_calls:
                                                if fc.name == "create_order":
                                                    with app.app_context():
                                                        args = dict(fc.args)
                                                        current_app.logger.info(f"📦 Creating order: {args}")
                                                        
                                                        try:
                                                            new_order = Order(
                                                                status='recu',
                                                                order_detail=args.get('order_details'),
                                                                customer_name=args.get('customer_name', 'Unknown'),
                                                                customer_phone=caller_number or 'Unknown',
                                                                company_phone=to_number,
                                                                address=args.get('address', 'Non defini')
                                                            )
                                                            db.session.add(new_order)
                                                            db.session.commit()
                                                            order_id = new_order.id
                                                            
                                                            add_event('new_order', {'message': 'Ordre reçu'})
                                                            
                                                            try:
                                                                from routes.notifications import send_web_push
                                                                send_web_push({
                                                                    "title": "Ordre reçus",
                                                                    "message": f"{args.get('customer_name', 'Client')}: {args.get('order_details', '')}"
                                                                })
                                                            except:
                                                                pass
                                                            
                                                            await session.send(
                                                                input=types.LiveClientToolResponse(
                                                                    function_responses=[types.FunctionResponse(
                                                                        name="create_order",
                                                                        id=fc.id,
                                                                        response={"status": "success", "order_id": order_id}
                                                                    )]
                                                                )
                                                            )
                                                        except Exception as db_e:
                                                            current_app.logger.error(f"DB Error: {db_e}")
                                        
                                        # Handle interruption
                                        if response.server_content and response.server_content.interrupted:
                                            with app.app_context():
                                                current_app.logger.info("🛑 User interrupted")
                                                                
                                except Exception as e:
                                    with app.app_context():
                                        current_app.logger.error(f"Receive loop error: {e}")
                                    # If critical error (not just empty turn), allow break?
                                    # But usually we want to keep trying for next turn unless connection died
                                    if "1000" in str(e) or "1001" in str(e): # WebSocket closed
                                         break
                                    # Slight delay before retry to prevent spin loop on error
                                    await asyncio.sleep(0.1)
                                        
                        except Exception as e:
                            with app.app_context():
                                current_app.logger.error(f"Receive wrapper error: {e}")
                        finally:
                            stop_event.set()
                    
                    # Run both tasks
                    await asyncio.gather(
                        send_audio(),
                        receive_audio(),
                        return_exceptions=True
                    )
                    
            except Exception as e:
                with app.app_context():
                    current_app.logger.error(f"Gemini session error: {e}")
            finally:
                stop_event.set()
                with app.app_context():
                    current_app.logger.info("Gemini session ended")
        
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_gemini())
        finally:
            loop.close()
    
    # Start Gemini thread
    gemini_t = threading.Thread(target=gemini_thread, daemon=True)
    gemini_t.start()
    
    # Main thread: Read from Vonage WebSocket
    try:
        while not stop_event.is_set():
            try:
                data = ws.receive(timeout=1.0)
                if not data:
                    current_app.logger.info("Vonage WebSocket closed")
                    break
                if isinstance(data, bytes):
                    with audio_lock:
                        audio_queue.append(data)
            except Exception as e:
                if "timed out" in str(e).lower():
                    continue
                if "1000" in str(e) or "1001" in str(e):
                    current_app.logger.info("Call ended normally")
                else:
                    current_app.logger.error(f"Vonage receive error: {e}")
                break
    finally:
        stop_event.set()
        current_app.logger.info("Voice stream ended")
