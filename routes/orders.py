import json
import time
from flask import Blueprint, render_template, request, jsonify, Response, stream_with_context, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from datetime import datetime
from models import Order

orders_bp = Blueprint('orders', __name__)

# Simple event queue for SSE
# In production with multiple workers, use Redis/RabbitMQ. 
# For this single worker setup, a global list or queue works.
event_queue = []

def add_event(event_type, data):
    event_queue.append({
        'type': event_type,
        'data': data,
        'timestamp': time.time()
    })

@orders_bp.route('/')
@login_required
def dashboard():
    # Fetch orders by status
    orders_recu = Order.query.filter_by(status='recu').order_by(Order.created_at.desc()).all()
    orders_en_cours = Order.query.filter_by(status='en_cours').order_by(Order.created_at.desc()).all()
    orders_termine = Order.query.filter_by(status='termine').order_by(Order.created_at.desc()).all()
    
    return render_template('dashboard.html', 
                         orders_recu=orders_recu, 
                         orders_en_cours=orders_en_cours, 
                         orders_termine=orders_termine)

@orders_bp.route('/api/orders/<int:order_id>/status', methods=['POST'])
@login_required
def update_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.json.get('status')
    
    if new_status in ['recu', 'en_cours', 'termine']:
        order.status = new_status
        db.session.commit()
        return jsonify({'success': True, 'status': new_status})
        
    return jsonify({'error': 'Invalid status'}), 400

@orders_bp.route('/api/orders/<int:order_id>', methods=['DELETE'])
@login_required
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    db.session.delete(order)
    db.session.commit()
    return jsonify({'success': True})

@orders_bp.route('/api/orders/<int:order_id>', methods=['PUT'])
@login_required
def edit_order(order_id):
    order = Order.query.get_or_404(order_id)
    data = request.json
    
    if 'order_detail' in data:
        order.order_detail = data['order_detail']
    if 'customer_name' in data:
        order.customer_name = data['customer_name']
    if 'customer_phone' in data:
        order.customer_phone = data['customer_phone']
    if 'address' in data:
        order.address = data['address']
        
    db.session.commit()
    return jsonify({'success': True})

@orders_bp.route('/toggle_agent', methods=['POST'])
@login_required
def toggle_agent():
    current_user.agent_on = not current_user.agent_on
    db.session.commit()
    # status = "ON" if current_user.agent_on else "OFF"
    # flash(f"Agent turned {status}") 
    return redirect(url_for('orders.dashboard'))

@orders_bp.route('/events')
@login_required
def events():
    @stream_with_context
    def generate():
        last_check = time.time()
        while True:
            # Check for new events since last check
            # This is a very basic polling implementation for SSE within the generator
            # Ideally use a queue or threading event
            
            # Filter events that happened after last_check
            current_events = [e for e in event_queue if e['timestamp'] > last_check]
            
            for event in current_events:
                yield f"data: {json.dumps(event)}\n\n"
            
            if current_events:
                last_check = current_events[-1]['timestamp']
            
            time.sleep(1) # Heartbeat / Poll interval
            
    return Response(generate(), mimetype='text/event-stream')

# Public endpoint to create orders (simulating external system or manual entry for testing)
# This will be called by the Voice Agent logic too
@orders_bp.route('/api/orders', methods=['POST'])
def create_order():
    data = request.json
    order = Order(
        order_detail=data.get('order_detail'),
        customer_name=data.get('customer_name'),
        customer_phone=data.get('customer_phone'),
        address=data.get('address'),
        status='recu'
    )
    db.session.add(order)
    db.session.commit()
    
    # Trigger Web Push
    try:
        from routes.notifications import send_web_push
        send_web_push({
            "title": "Ordre reçus",
            "message": f"{data.get('customer_name')} : {data.get('order_detail')}"
        })
    except Exception as e:
        current_app.logger.error(f"Push Error: {e}")

    # Trigger SSE
    add_event('new_order', {'message': 'Ordre reçu'})
    
    return jsonify(order.to_dict()), 201
