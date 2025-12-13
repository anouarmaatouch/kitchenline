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
        
        # Notify clients about status change (optional, or just refresh)
        # For now, UI might just reload or move DOM element.
        return jsonify({'success': True, 'status': new_status})
        
    return jsonify({'error': 'Invalid status'}), 400

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
    
    # Trigger SSE
    add_event('new_order', {'message': 'Ordre reçu'})
    
    return jsonify(order.to_dict()), 201
