from flask import Blueprint

# To:
store_web_bp = Blueprint('store_web_bp', __name__,
                        template_folder='templates',
                        static_folder='static')

from . import routes #, models, schemas, services
