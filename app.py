from gevent import monkey
monkey.patch_all()

from flask import Flask
from config import Config
from extensions import db, sock
from flask_login import LoginManager
from models import User

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Required for Fly.io / Heroku (Handles HTTPS headers from Load Balancer)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Configure Logging
    import logging
    import sys
    
    if not app.debug and not app.testing:
        # Production logging
        pass

    # Ensure logs go to stdout for Docker
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    
    # Also configure root logger for other modules (like voice.py if using print/logging)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    # Initialize extensions
    db.init_app(app)
    sock.init_app(app)
    
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.orders import orders_bp
    from routes.voice import voice_bp
    from routes.admin import admin_bp
    from routes.notifications import notifications_bp
    from routes.test_routes import test_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(test_bp)
    
    with app.app_context():
        db.create_all()
        
    @app.route('/sw.js')
    def sw():
        from flask import send_from_directory
        return send_from_directory('static', 'sw.js', mimetype='application/javascript')

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
