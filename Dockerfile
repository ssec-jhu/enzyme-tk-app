FROM python:3.12-slim

WORKDIR /app

COPY requirements/prd.txt requirements.txt

RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8050

CMD ["gunicorn", "enzyme_tk_app.app.app:server", "--bind", "0.0.0.0:8050", "--workers", "2", "--threads", "4"]
