"""
gRPC Server bootstrapper for AI-CORE Service.

Starts an async gRPC server on port 50052, registering the AICoreServicer.
Runs as a background coroutine alongside the FastAPI app.
"""

import logging
import grpc
from grpc_server.servicer import AICoreServicer

logger = logging.getLogger("solavie.ai_core.grpc.server")


async def serve_grpc() -> None:
    """Launch the async gRPC server on port 50052."""
    try:
        from proto import ai_core_pb2_grpc
    except ImportError:
        logger.warning(
            "gRPC server not started: protobuf modules (ai_core_pb2_grpc) not found. "
            "Run `python -m grpc_tools.protoc` to compile .proto files first."
        )
        return

    server = grpc.aio.server()
    servicer = AICoreServicer()
    ai_core_pb2_grpc.add_AICoreServicer_to_server(servicer, server)

    listen_addr = "[::]:50052"
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await server.start()
    await server.wait_for_termination()
