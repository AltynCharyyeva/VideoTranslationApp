from celery import Celery
import os
from worker.ai_models import load_ai_models
from celery.signals import worker_process_init


celery_app = Celery(
    'tasks', 
    broker=os.getenv("CELERY_BROKER_URL"),
    include=['worker.tasks']
)

@worker_process_init.connect
def on_worker_start(**kwargs):
    load_ai_models()