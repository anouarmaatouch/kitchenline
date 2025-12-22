import asyncio
import base64
import json
import os
import audioop
import time
from typing import Optional
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

try:
    from google import genai
    from google.genai import types
except ImportError:
    pass

from config.config import Config
from database import get_db
from models_new import Company, Order, Demand
from utils.phone import normalize_phone

# Router
router = APIRouter(tags=["Voice"])

# Constants
GEMINI_MODEL = "gemini-live-2.5-flash-native-audio"

@router.post("/webhooks/event")
async def event_webhook(request: Request):
    try:
        data = await request.json()
    except:
        data = {}
    print(f"🔔 Vonage Event: {data}")
    return {"status": "ok"}

@router.api_route("/webhooks/answer", methods=["GET", "POST"])
async def answer_call(request: Request):
    # Handle data from POST body or GET query
    data = {}
    if request.method == "POST":
        try:
            data = await request.json()
        except:
            pass
    
    # Merge query params (GET params override JSON if present, or fallback)
    query_params = dict(request.query_params)
    
    to_number = data.get('to') or query_params.get('to')
    from_number = data.get('from') or query_params.get('from')
    
    host = request.headers.get("host")
    # Use PUBLIC_URL if set, otherwise fallback to request host
    # In Fly.io, we might want to ensure https/wss
    
    scheme = "wss" # Default to secure
    # If strictly local, might be ws, but let's assume wss for deployment
    # Check X-Forwarded-Proto?
    proto = request.headers.get("x-forwarded-proto")
    if proto == "http" and "localhost" in host:
        scheme = "ws"
        
    ws_uri = f"{scheme}://{host}/voice/stream?to_number={to_number}&caller_number={from_number}"
    
    print(f"📞 NCCO WebSocket URI: {ws_uri}")
    
    return [
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
    ]

@router.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    await websocket.accept()
    
    # Extract params
    to_number = websocket.headers.get("to-number") or websocket.query_params.get("to_number")
    caller_number = websocket.headers.get("caller-number") or websocket.query_params.get("caller_number")
    
    print(f"📞 Incoming call to: {to_number} from: {caller_number}")
    
    # 1. Fetch Company
    norm_to = normalize_phone(to_number)
    
    # Async DB query
    result = await db.execute(select(Company).where(Company.phone_number == norm_to))
    company = result.scalars().first()
    
    if company and not company.agent_on:
        print(f"Agent OFF for {to_number}")
        await websocket.close()
        return

    # 2. Build System Instruction (RELAXED)
    system_instruction = "You are a friendly AI restaurant assistant. Speak in Moroccan Darija (Arabic dialect). You can also understand French and English. (تكلم بالدارجة المغربية). Be polite and helpful."
    voice_name = "Puck"
    
    if company:
        if company.voice: voice_name = company.voice
        if company.system_prompt: system_instruction = company.system_prompt
        system_instruction += "\n\nIMPORTANT: Speak in Moroccan Darija (Arabic dialect) at all times."
        if company.menu: system_instruction += f"\n\nMenu:\n{company.menu}"
            
    system_instruction += "\n\nWhen the order is confirmed, use 'create_order'. If it's a special request, use 'submit_demand'. Always ask for the customer's name."

    # 3. Setup Gemini Client
    creds_path = os.path.abspath("vertex-json.json")
    if os.path.exists(creds_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        
    client = genai.Client(vertexai=True, project="polar-equinox-472800-j2", location="us-central1")
    
    # Define Tools
    create_order_tool = types.FunctionDeclaration(
        name="create_order",
        description="Submit a completed restaurant order.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "order_details": types.Schema(type=types.Type.STRING),
                "customer_name": types.Schema(type=types.Type.STRING),
                "address": types.Schema(type=types.Type.STRING),
            },
            required=["order_details", "customer_name"]
        )
    )
    submit_demand_tool = types.FunctionDeclaration(
        name="submit_demand",
        description="Submit a special request.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "content": types.Schema(type=types.Type.STRING),
                "customer_name": types.Schema(type=types.Type.STRING),
            },
            required=["content"]
        )
    )
    
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
        system_instruction=types.Content(parts=[types.Part(text=system_instruction)]),
        tools=[types.Tool(function_declarations=[create_order_tool, submit_demand_tool])]
    )

    # 4. Connect to Gemini Live
    try:
        async with client.aio.live.connect(model=GEMINI_MODEL, config=config) as session:
            print(f"✅ Connected to Gemini Live ({GEMINI_MODEL})!")
            
            # Initial greeting
            await session.send(
                 input="The customer is online. Say 'Salam' and ask for their order in Moroccan Darija.", 
                 end_of_turn=True
            )
            
            # 5. Pipeline Logic
            resample_state_out = None
            chunk_count = 0
            buffer_in = bytearray()
            # 2 chunks of 20ms = 40ms (1280 bytes)
            BUFFER_THRESHOLD = 1280

            async def send_to_gemini():
                """Read from Vonage -> Process -> Send to Gemini"""
                nonlocal chunk_count, buffer_in
                try:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect": break
                        if "bytes" in message:
                            raw = message["bytes"]
                            if raw:
                                buffer_in.extend(raw)
                                if len(buffer_in) >= BUFFER_THRESHOLD:
                                    chunk_count += 1
                                    data_raw = bytes(buffer_in)
                                    buffer_in.clear()

                                    # 1. Byteswap (Big -> Little) - MANDATORY
                                    data = audioop.byteswap(data_raw, 2)
                                    
                                    # 2. DC Offset Removal (Subtract Mean)
                                    # This centers your voice at 0.
                                    avg = audioop.avg(data, 2)
                                    data = audioop.bias(data, 2, -avg)

                                    # 3. No Boost (Clean Signal)
                                    # Previous RMS 21k was loud, let's try raw.
                                    
                                    # 4. No Resampling (Send 16k Raw)

                                    # Monitoring
                                    if chunk_count % 50 == 0:
                                        rms = audioop.rms(data, 2)
                                        print(f"🎤 [Stream] 40ms Block {chunk_count} | RMS: {rms} | DC Avg: {avg}")

                                    # Send Direct (Explicitly declare 16k)
                                    await session.send(input=types.LiveClientRealtimeInput(
                                        media_chunks=[types.Blob(mime_type="audio/l16;rate=16000", data=data)]
                                    ))
                except Exception as e:
                    print(f"Stream Send Error: {e}")

            async def receive_from_gemini():
                """Read from Gemini -> Process -> Send to Vonage"""
                nonlocal resample_state_out
                try:
                    async for response in session.receive():
                        # LOG EVERYTHING for diagnostics
                        if not (response.server_content and response.server_content.model_turn):
                             msg = []
                             if response.voice_activity_detection_signal:
                                 msg.append(f"👂 VAD: {response.voice_activity_detection_signal.type}")
                             if response.server_content and response.server_content.interrupted:
                                 msg.append("🛑 Interrupted")
                             if response.server_content and response.server_content.turn_complete:
                                 msg.append("🏁 Turn Complete")
                             if response.usage_metadata:
                                 msg.append(f"📊 Usage: T={response.usage_metadata.total_token_count}")
                             
                             if msg:
                                 print(f"🚀 Gemini: {' | '.join(msg)}")
                             elif not response.setup_complete:
                                 # Fallback for unexpected events
                                 print(f"🚀 Gemini Event: {response}")

                        # 1. Handle Audio
                        if response.server_content and response.server_content.model_turn:
                            for part in response.server_content.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    # Resample 24k -> 16k (Output is always 24k)
                                    new_fragment, resample_state_out = audioop.ratecv(
                                        part.inline_data.data, 2, 1, 24000, 16000, resample_state_out
                                    )
                                    await websocket.send_bytes(new_fragment)
                        
                        # 2. Handle Tools
                        if response.tool_call:
                            for fc in response.tool_call.function_calls:
                                if fc.name == "create_order":
                                    args = dict(fc.args)
                                    print(f"📦 Order: {args}")
                                    new_order = Order(
                                        status='recu',
                                        order_detail=args.get('order_details'),
                                        customer_name=args.get('customer_name', 'Unknown'),
                                        customer_phone=normalize_phone(caller_number) or 'Unknown',
                                        company_id=company.id if company else None,
                                        company_phone=normalize_phone(to_number),
                                        address=args.get('address', 'Non defini')
                                    )
                                    db.add(new_order)
                                    await db.commit()
                                    await session.send(input=types.LiveClientToolResponse(
                                        function_responses=[types.FunctionResponse(
                                            name="create_order", id=fc.id, response={"status": "success"}
                                        )]
                                    ))
                                elif fc.name == "submit_demand":
                                    args = dict(fc.args)
                                    print(f"💡 Demand: {args}")
                                    new_demand = Demand(
                                        company_id=company.id if company else None,
                                        customer_name=args.get('customer_name') or 'Unknown',
                                        customer_phone=normalize_phone(caller_number) or 'Unknown',
                                        content=args.get('content'),
                                        status='new'
                                    )
                                    db.add(new_demand)
                                    await db.commit()
                                    await session.send(input=types.LiveClientToolResponse(
                                        function_responses=[types.FunctionResponse(
                                            name="submit_demand", id=fc.id, response={"status": "success"}
                                        )]
                                    ))
                except Exception as e:
                    print(f"Stream Receive Error: {e}")

            # Execute
            await asyncio.gather(send_to_gemini(), receive_from_gemini())

    except Exception as e:
        print(f"Final Error: {e}")
        await websocket.close()
