import os
from app import create_app # Import the app factory
from redis import Redis
from rq import Worker, Queue, Connection

# Determine config name, suitable for background worker
config_name = os.environ.get('FLASK_CONFIG', 'production')

# Create the Flask application instance (minimal app context for RQ)
app = create_app(config_name)

# Establish Redis connection (using config from app)
# Assuming Redis URL is in app.config['REDIS_URL'] or similar
redis_conn = Redis.from_url(app.config.get('REDIS_URL', 'redis://localhost:6379/0'))

# Define the queues you want the worker to listen to
listen = ['high', 'default', 'low'] # Example queues

# This file is the entry point for running an RQ worker.
# Example command: python worker.py
if __name__ == '__main__':
    with Connection(redis_conn):
        # Create workers for the specified queues
        worker = Worker(list(map(Queue, listen)))
        # Start the worker
        worker.work()