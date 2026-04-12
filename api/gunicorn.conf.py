# gunicorn.conf.py
bind = "0.0.0.0:5000"
workers = 33  # Consider adjusting this number
worker_class = "uvicorn.workers.UvicornWorker"
chdir = "/home/sistemas/ValidadorFacturas/api"  # This solves your path issue
