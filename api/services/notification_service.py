import json
import asyncio
from sqlalchemy.future import select
from pywebpush import webpush, WebPushException
from config.config import Config
from models_new import PushSubscription
from database import async_session

async def send_web_push_async(message_body: dict):
    """
    Send web push notifications to all subscribers asynchronously.
    """
    async with async_session() as db:
        result = await db.execute(select(PushSubscription))
        subscriptions = result.scalars().all()
        
        if not subscriptions:
            return

        vapid_private = Config.VAPID_PRIVATE_KEY
        vapid_public = Config.VAPID_PUBLIC_KEY
        vapid_email = Config.VAPID_CLAIM_EMAIL
        
        if not vapid_private:
            print("VAPID keys missing")
            return
            
        vapid_claims = {"sub": vapid_email}
        
        # Blocking function to run in executor
        def _send_push(sub_info, data_str):
            try:
                webpush(
                    subscription_info=sub_info,
                    data=data_str,
                    vapid_private_key=vapid_private,
                    vapid_claims=vapid_claims
                )
                return True
            except WebPushException as ex:
                if ex.response and ex.response.status_code == 410:
                    return "expired"
                return False
            except Exception as e:
                print(f"Push error: {e}")
                return False

        loop = asyncio.get_running_loop()
        data_str = json.dumps(message_body)
        tasks = []
        
        for sub in subscriptions:
            sub_info = {
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth}
            }
            # Offload blocking IO to thread pool
            tasks.append(loop.run_in_executor(None, _send_push, sub_info, data_str))
            
        results = await asyncio.gather(*tasks)
        
        # Cleanup expired (Best effort)
        # In a real app, we'd collect IDs of expired subs and delete them
        # But for now we just log
        success = results.count(True)
        print(f"Push notification sent to {success}/{len(subscriptions)} devices")
