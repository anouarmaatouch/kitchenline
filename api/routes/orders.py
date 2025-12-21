from flask import Blueprint, request, jsonify, Response, stream_with_context
from flask_login import login_required, current_user
from extensions import db
from models.models import Order, Demand
from utils.phone import normalize_phone
import json
import time

orders_bp = Blueprint('orders', __name__, url_prefix='/api')

event_queue = []

def add_event(event_type, data):
    event_queue.append({
        'type': event_type,
        'data': data,
        'timestamp': time.time()
    })

@orders_bp.route('/dashboard')
@login_required
def dashboard():
    # Get phone from company, not user
    user_phone = None
    if current_user.company_ref and current_user.company_ref.phone_number:
        user_phone = normalize_phone(current_user.company_ref.phone_number)
    
    # Filter by company_id instead of company_phone
    if current_user.company_ref:
        company_id = current_user.company_ref.id
        orders_recu = Order.query.filter_by(status='recu', company_id=company_id).order_by(Order.created_at.desc()).all()
        orders_en_cours = Order.query.filter_by(status='en_cours', company_id=company_id).order_by(Order.created_at.desc()).all()
        orders_termine = Order.query.filter_by(status='termine', company_id=company_id).order_by(Order.created_at.desc()).all()
    else:
        # Fallback: if no company, return empty or all orders (for superadmin)
        orders_recu = Order.query.filter_by(status='recu').order_by(Order.created_at.desc()).all() if current_user.is_superadmin else []
        orders_en_cours = Order.query.filter_by(status='en_cours').order_by(Order.created_at.desc()).all() if current_user.is_superadmin else []
        orders_termine = Order.query.filter_by(status='termine').order_by(Order.created_at.desc()).all() if current_user.is_superadmin else []
    
    return jsonify({
        'orders_recu': [o.to_dict() for o in orders_recu],
        'orders_en_cours': [o.to_dict() for o in orders_en_cours],
        'orders_termine': [o.to_dict() for o in orders_termine]
    })

@orders_bp.route('/demands')
@login_required
def demands_dashboard():
    # Filter by company_id instead of user_id
    if current_user.is_superadmin:
        demands = Demand.query.order_by(Demand.created_at.desc()).all()
    elif current_user.company_ref:
        company_id = current_user.company_ref.id
        demands = Demand.query.filter_by(company_id=company_id).order_by(Demand.created_at.desc()).all()
    else:
        demands = []
    
    demand_list = []
    for demand in demands:
        d_dict = demand.to_dict()
        if demand.customer_phone:
            active_orders_count = Order.query.filter(
                Order.customer_phone == demand.customer_phone,
                Order.status.in_(['recu', 'en_cours'])
            ).count()
            d_dict['active_orders_count'] = active_orders_count
        else:
            d_dict['active_orders_count'] = 0
        demand_list.append(d_dict)
            
    return jsonify({
        'demands_new': [d for d in demand_list if d['status'] == 'new'],
        'demands_processed': [d for d in demand_list if d['status'] == 'processed']
    })

@orders_bp.route('/demands/<int:demand_id>/status', methods=['POST'])
@login_required
def update_demand_status(demand_id):
    demand = Demand.query.get_or_404(demand_id)
    new_status = request.json.get('status')
    if new_status in ['new', 'processed']:
        demand.status = new_status
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'Invalid status'}), 400

@orders_bp.route('/demands/<int:demand_id>', methods=['DELETE'])
@login_required
def delete_demand(demand_id):
    demand = Demand.query.get_or_404(demand_id)
    db.session.delete(demand)
    db.session.commit()
    return jsonify({'success': True})

@orders_bp.route('/orders/<int:order_id>/status', methods=['POST'])
@login_required
def update_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.json.get('status')
    
    if new_status in ['recu', 'en_cours', 'termine']:
        order.status = new_status
        db.session.commit()
        return jsonify({'success': True, 'status': new_status})
        
    return jsonify({'error': 'Invalid status'}), 400

@orders_bp.route('/orders/<int:order_id>', methods=['DELETE'])
@login_required
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    db.session.delete(order)
    db.session.commit()
    return jsonify({'success': True})

@orders_bp.route('/orders/<int:order_id>', methods=['PUT'])
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
    if not current_user.company_ref:
        return jsonify({'error': 'No company associated'}), 400
    current_user.company_ref.agent_on = not current_user.company_ref.agent_on
    db.session.commit()
    return jsonify({'success': True, 'agent_on': current_user.company_ref.agent_on})

@orders_bp.route('/events')
def events():
    @stream_with_context
    def generate():
        last_check = time.time()
        while True:
            current_events = [e for e in event_queue if e['timestamp'] > last_check]
            for event in current_events:
                yield f"data: {json.dumps(event)}\n\n"
            if current_events:
                last_check = current_events[-1]['timestamp']
            time.sleep(1)
            
    return Response(generate(), mimetype='text/event-stream')

@orders_bp.route('/orders', methods=['POST'])
def create_order():
    data = request.json
    order = Order(
        order_detail=data.get('order_detail'),
        customer_name=data.get('customer_name'),
        customer_phone=normalize_phone(data.get('customer_phone')),
        address=data.get('address'),
        status='recu',
        company_phone=normalize_phone(data.get('company_phone'))
    )
    db.session.add(order)
    db.session.commit()
    
    try:
        from routes.notifications import send_web_push
        send_web_push({
            "title": "Ordre reçus",
            "message": f"{data.get('customer_name')} : {data.get('order_detail')}"
        })
    except:
        pass

    add_event('new_order', {'message': 'Ordre reçu'})
    return jsonify({'success': True, 'order_id': order.id}), 201

@orders_bp.route('/customer/history/<phone>')
@login_required
def get_customer_history(phone):
    orders = Order.query.filter_by(customer_phone=phone).order_by(Order.created_at.desc()).limit(20).all()
    return jsonify([o.to_dict() for o in orders])
