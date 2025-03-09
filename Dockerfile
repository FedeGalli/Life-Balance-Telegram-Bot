FROM python:alpine3.9
WORKDIR .
COPY . .
RUN pip install -r requirements.txt
ENTRYPOINT ["python", "main.py"]
