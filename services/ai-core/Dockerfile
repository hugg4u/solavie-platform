FROM python:3.12-slim

WORKDIR /app

# Install system dependencies if any needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy protobuf and all app code
COPY . .

# Compile Protobuf definitions
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. proto/ai_core.proto

# Expose ports: 8000 for FastAPI, 50051 for gRPC
EXPOSE 8000
EXPOSE 50051

# Run FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
