from flask import Blueprint, jsonify, current_app
from routes.notifications import send_web_push
from models import PushSubscription

test_bp = Blueprint('test', __name__)

@test_bp.route('/api/test_push', methods=['POST'])
def test_push():
    try:
        send_web_push({
            "title": "Test Notification",
            "message": "Ceci est un test de notification Web Push !"
        })
        return jsonify({"success": True, "message": "Notification envoyée"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@test_bp.route('/api/push_debug')
def push_debug():
    """Debug endpoint to check push notification status"""
    subs = PushSubscription.query.all()
    vapid_public = current_app.config.get('VAPID_PUBLIC_KEY')
    vapid_private = current_app.config.get('VAPID_PRIVATE_KEY')
    
    return jsonify({
        "subscription_count": len(subs),
        "subscriptions": [{"id": s.id, "endpoint_preview": s.endpoint[:50] + "..."} for s in subs],
        "vapid_public_key_set": bool(vapid_public),
        "vapid_private_key_set": bool(vapid_private),
        "vapid_public_key": vapid_public[:20] + "..." if vapid_public else None
    })
