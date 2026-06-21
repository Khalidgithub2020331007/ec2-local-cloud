import os
from flask import Flask, render_template
from app.database import init_db
from app.auth.routes import auth_bp
from app.compute.routes import compute_bp
from app.images.routes import images_bp
from app.network.routes import network_bp


def create_app():
    # template_folder এবং static_folder root থেকে relative path দিতে হয়
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'static'),
    )

    # App start হওয়ার সাথে সাথে DB tables তৈরি হয়ে যাবে (না থাকলে)
    init_db()

    # Auth blueprint register — সব /api/v1/auth/* routes এখানে থাকবে
    app.register_blueprint(auth_bp)
    app.register_blueprint(compute_bp)
    app.register_blueprint(images_bp)
    app.register_blueprint(network_bp)

    # Dashboard page routes
    @app.route('/')
    def login_page():
        return render_template('login.html')

    @app.route('/register')
    def register_page():
        return render_template('register.html')

    @app.route('/dashboard')
    def dashboard_page():
        return render_template('dashboard.html')

    return app
