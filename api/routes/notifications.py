from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user, login_required
from extensions import db
from models.models import PushSubscription
from pywebpush import webpush, WebPushException
import json

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api')

@notifications_bp.route('/vapid_public_key')
def get_vapid_public_key():
    return jsonify({'publicKey': current_app.config['VAPID_PUBLIC_KEY']})

@notifications_bp.route('/subscribe', methods=['POST'])
def subscribe():
    data = request.json
    subscription_info = data.get('subscription_info')
    
    if not subscription_info:
        return jsonify({'error': 'No subscription info provided'}), 400
        
    endpoint = subscription_info.get('endpoint')
    keys = subscription_info.get('keys', {})
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')
    
    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Invalid subscription info'}), 400
        
    # Check if exists
    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        # Update if user changed (e.g. login)
        if current_user.is_authenticated:
            existing.user_id = current_user.id
            db.session.commit()
        return jsonify({'status': 'exists', 'message': 'Already subscribed.'})
    
    new_sub = PushSubscription(
        user_id=current_user.id if current_user.is_authenticated else None,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth
    )
    db.session.add(new_sub)
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Subscribed successfully.'}), 201

def send_web_push(message_body):
    """
    Helper to send push notification to all subscribers (or filtered ones).
    For MVP, sending to ALL subscriptions.
    """
    subscriptions = PushSubscription.query.all()
    
    current_app.logger.info(f"Sending push to {len(subscriptions)} subscribers: {message_body}")
    
    if not subscriptions:
        current_app.logger.warning("No push subscriptions found in database!")
        return
    
    vapid_private = current_app.config.get('VAPID_PRIVATE_KEY')
    vapid_public = current_app.config.get('VAPID_PUBLIC_KEY')
    vapid_email = current_app.config.get('VAPID_CLAIM_EMAIL', 'mailto:admin@example.com')
    
    if not vapid_private or not vapid_public:
        current_app.logger.error("VAPID keys not configured! Set VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY")
        return
    
    vapid_claims = {"sub": vapid_email}
    
    success_count = 0
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub.to_dict(),
                data=json.dumps(message_body),
                vapid_private_key=vapid_private,
                vapid_claims=vapid_claims
            )
            success_count += 1
            current_app.logger.info(f"Push sent to subscription ID {sub.id}")
        except WebPushException as ex:
            if ex.response and ex.response.status_code == 410:
                # Expired subscription
                current_app.logger.info(f"Removing expired subscription ID {sub.id}")
                db.session.delete(sub)
                db.session.commit()
            else:
                current_app.logger.error(f"WebPush Error for sub {sub.id}: {ex}")
        except Exception as e:
            current_app.logger.error(f"Push Error for sub {sub.id}: {e}")
    
    current_app.logger.info(f"Push complete: {success_count}/{len(subscriptions)} sent successfully")
