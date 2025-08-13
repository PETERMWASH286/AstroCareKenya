# celery_worker.py
from app import create_app
from app.extensions import celery

app = create_app()

# Initialize Celery
celery.conf.update(app.config)
celery.conf.broker_url = app.config['CELERY_BROKER_URL']
celery.conf.result_backend = app.config['CELERY_RESULT_BACKEND']
celery.conf.timezone = 'UTC'
celery.conf.enable_utc = True
# Context task
class ContextTask(celery.Task):
    def __call__(self, *args, **kwargs):
        with app.app_context():
            return self.run(*args, **kwargs)

celery.Task = ContextTask