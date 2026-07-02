# आय·AI Airflow image: official Airflow + the aayai pipeline dependencies,
# baked in once at build time (no per-boot pip installs).
FROM apache/airflow:2.10.5-python3.12
COPY requirements.txt /tmp/aayai-requirements.txt
RUN pip install --no-cache-dir -r /tmp/aayai-requirements.txt
