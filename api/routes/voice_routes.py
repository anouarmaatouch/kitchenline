import asyncio
import base64
import json
import os
import audioop
import time
from typing import Optional
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
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

@router.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    await websocket.accept()
    
    # Extract params from headers or query
    # Vonage sends headers in the initial handshake
    # FastAPI WebSocket.headers is a dict-like object
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

    # 2. Build System Instruction
    system_instruction = "You are a friendly AI restaurant assistant. You MUST speak in strictly Moroccan Darija (Arabic dialect). (تكلم بالدارجة المغربية فقط). Do not speak French or standard Arabic unless requested. Be polite and helpful."
    voice_name = "Puck"
    
    if company:
        if company.voice:
            voice_name = company.voice
        if company.system_prompt:
            system_instruction = company.system_prompt
        
        system_instruction += "\n\nIMPORTANT: Speak in Moroccan Darija (Arabic dialect) at all times."
        if company.menu:
            system_instruction += f"\n\nHere is the Menu:\n{company.menu}"
            
    system_instruction += "\n\nWhen the order is confirmed, use the 'create_order' function to submit it. If the customer has a special request, demand, or modification that is NOT a direct food order, use 'submit_demand'. Always ask for the customer's name."

    # 3. Setup Gemini Client
    creds_path = os.path.abspath("vertex-json.json")
    if os.path.exists(creds_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        
    client = genai.Client(
        vertexai=True,
        project="polar-equinox-472800-j2",
        location="us-central1"
    )
    
    # Define Tools
    create_order_tool = types.FunctionDeclaration(
        name="create_order",
        description="Submit a completed restaurant order after the customer confirms.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "order_details": types.Schema(type=types.Type.STRING, description="Full list of ordered items"),
                "customer_name": types.Schema(type=types.Type.STRING, description="Customer's full name"),
                "address": types.Schema(type=types.Type.STRING, description="Delivery address if provided, otherwise 'Non defini'"),
            },
            required=["order_details", "customer_name"]
        )
    )
    
    submit_demand_tool = types.FunctionDeclaration(
        name="submit_demand",
        description="Submit a special request or modification that is NOT a direct food order.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "content": types.Schema(type=types.Type.STRING, description="Details of the request in the agent's language"),
                "customer_name": types.Schema(type=types.Type.STRING, description="Customer's full name"),
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
            print("✅ Connected to Gemini Live!")
            
            # Send initial greeting
            await session.send(
                input="The customer is online. Say 'Salam' and ask for their order in Moroccan Darija.", 
                end_of_turn=True
            )
            
            # 5. Concurrent Tasks (no threads!)
            async def receive_from_vonage():
                """Read audio from WebSocket -> Send to Gemini"""
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        if not data:
                            break
                        
                        await session.send(input=types.LiveClientRealtimeInput(
                            media_chunks=[types.Blob(mime_type="audio/pcm", data=data)]
                        ))
                except WebSocketDisconnect:
                    print("Vonage Client disconnected")
                except Exception as e:
                    print(f"Error receiving from Vonage: {e}")

            async def receive_from_gemini():
                """Read audio/tools from Gemini -> Send to WebSocket"""
                resample_state = None
                try:
                    async for response in session.receive():
                        # Audio
                        if response.server_content and response.server_content.model_turn:
                            for part in response.server_content.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    fragment = part.inline_data.data
                                    # Resample 24k -> 16k
                                    new_fragment, resample_state = audioop.ratecv(
                                        fragment, 2, 1, 24000, 16000, resample_state
                                    )
                                    await websocket.send_bytes(new_fragment)
                        
                        # Tools
                        if response.tool_call:
                            for fc in response.tool_call.function_calls:
                                if fc.name == "create_order":
                                    args = dict(fc.args)
                                    print(f"📦 Creating order: {args}")
                                    
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
                                    await db.refresh(new_order)
                                    
                                    # Send Push Notification
                                    try:
                                        from services.notification_service import send_web_push_async
                                        await send_web_push_async({
                                            "title": "Ordre reçus",
                                            "message": f"{args.get('customer_name', 'Client')}: {args.get('order_details', '')}"
                                        })
                                    except Exception as e:
                                        print(f"Push error: {e}")
                                    
                                    await session.send(input=types.LiveClientToolResponse(
                                        function_responses=[types.FunctionResponse(
                                            name="create_order",
                                            id=fc.id,
                                            response={"status": "success", "order_id": new_order.id}
                                        )]
                                    ))
                                    
                                elif fc.name == "submit_demand":
                                    args = dict(fc.args)
                                    print(f"💡 Submitting demand: {args}")
                                    
                                    # Find recent order
                                    stmt = select(Order).filter(
                                        Order.company_phone == to_number,
                                        Order.customer_phone == (caller_number or 'Unknown'),
                                        Order.status.in_(['recu', 'en_cours'])
                                    ).order_by(desc(Order.created_at))
                                    res = await db.execute(stmt)
                                    recent_order = res.scalars().first()
                                    
                                    new_demand = Demand(
                                        company_id=company.id if company else None,
                                        order_id=recent_order.id if recent_order else None,
                                        customer_name=args.get('customer_name') or (recent_order.customer_name if recent_order else 'Unknown'),
                                        customer_phone=normalize_phone(caller_number) or 'Unknown',
                                        content=args.get('content'),
                                        status='new'
                                    )
                                    db.add(new_demand)
                                    await db.commit()
                                    
                                    # Send Push Notification
                                    try:
                                        from services.notification_service import send_web_push_async
                                        await send_web_push_async({
                                            "title": "Nouvelle Demande",
                                            "message": f"{args.get('content', '')[:50]}..."
                                        })
                                    except Exception as e:
                                        print(f"Push error: {e}")
                                    
                                    await session.send(input=types.LiveClientToolResponse(
                                        function_responses=[types.FunctionResponse(
                                            name="submit_demand",
                                            id=fc.id,
                                            response={"status": "success", "message": "Ok"}
                                        )]
                                    ))

                        if response.server_content and response.server_content.interrupted:
                             print("🛑 Interrupted")
                             
                except Exception as e:
                    print(f"Error receiving from Gemini: {e}")

            # Run both
            await asyncio.gather(receive_from_vonage(), receive_from_gemini())

    except Exception as e:
        print(f"Gemini connection error: {e}")
        await websocket.close()
