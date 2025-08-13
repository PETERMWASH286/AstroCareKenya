import os
from celery import Celery
from app import create_app

# For Windows compatibility
if os.name == 'nt':
    os.environ.setdefault('FORKED_BY_MULTIPROCESSING', '1')

# Create Flask app
app = create_app(os.environ.get('FLASK_CONFIG', 'production'))

# Create Celery app
celery = Celery(__name__)
celery.conf.update(
    broker_url=app.config['CELERY_BROKER_URL'],
    result_backend=app.config['CELERY_RESULT_BACKEND'],
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True
)

# Set up task using app context
class ContextTask(celery.Task):
    def __call__(self, *args, **kwargs):
        with app.app_context():
            return self.run(*args, **kwargs)

celery.Task = ContextTask

# Import tasks AFTER setting up Celery
from app.notifications import tasks

if __name__ == '__main__':
    celery.start()