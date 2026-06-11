# ==========================================
# Stage 1: Build Stage (Builder)
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Cài đặt công cụ build cần thiết để compile C extensions nếu cần
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Khởi tạo môi trường ảo (virtualenv) để cô lập dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Sao chép requirements và cài đặt thư viện
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --upgrade pip \
    && pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# Sao chép và biên dịch file Protobuf (Tách riêng layer để tận dụng Docker Cache)
COPY proto/ ./proto/
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. proto/ai_core.proto

# Gỡ bỏ thư viện grpcio-tools sau khi build xong để tiết kiệm ~120MB dung lượng
RUN pip uninstall -y grpcio-tools

# ==========================================
# Stage 2: Runtime Stage (Runner)
# ==========================================
FROM python:3.12-slim AS runner

WORKDIR /app

# Copy môi trường ảo chứa toàn bộ dependencies đã được cài đặt và thu gọn
COPY --from=builder /opt/venv /opt/venv

# Copy mã nguồn ứng dụng (Bỏ qua .env và file rác nhờ .dockerignore)
COPY . .

# Sao chép lại file protobuf đã được compile từ stage builder
COPY --from=builder /app/proto/ /app/proto/

# Cấu hình môi trường sử dụng venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose ports: 8000 cho FastAPI, 50051 cho gRPC
EXPOSE 8000
EXPOSE 50051

# Chạy ứng dụng FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
