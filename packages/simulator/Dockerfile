# Paper-trading simulator only. No exchange credentials, no real orders.
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY packages ./packages
COPY docs ./docs
RUN pip install --no-cache-dir -e ".[dev,ui]"
EXPOSE 8502
# One-command demo: run a seeded synthetic scenario, then serve the dashboard.
CMD gridpilot-sim run --scenario normal --speed 0 --seed 0 --out /app/packages/simulator/results \
 && streamlit run packages/simulator/src/gridpilot_simulator/dashboard.py --server.port=8502 --server.address=0.0.0.0
