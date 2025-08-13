# Use a lightweight Python image as the base
FROM python:3.10-slim-buster

# Set environment variables
ENV PYTHONUNBUFFERED 1
ENV FLASK_CONFIG production
ENV CELERY_BROKER_URL redis://redis:6379/0 # Use the service name from docker-compose
ENV CELERY_RESULT_BACKEND redis://redis:6379/0
# Database URL should ideally come from Docker Secrets or environment variables in docker-compose
# ENV DATABASE_URL postgresql://user:password@db:5432/mydb # Example for PostgreSQL

# Set the working directory in the container
WORKDIR /app

# Copy the dependency files and install dependencies
COPY requirements.txt dev-requirements.txt /app/
# Install production dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . /app/

# Expose the port the Flask app will run on
EXPOSE 5000

# Command to run the application using a WSGI server (Gunicorn example)
# Assumes Gunicorn is in requirements.txt
# Use the wsgi.py entry point
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "wsgi:app"]

# To run the Celery worker in a separate container based on this image,
# the command in docker-compose.yml would override this CMD.
# Example worker command: celery -A celery_worker.celery_app worker -l info