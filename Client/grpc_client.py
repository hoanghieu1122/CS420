from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, TypeVar

import grpc

import student_pb2
import student_pb2_grpc


SERVER_ADDRESS = "192.168.1.217:50051"
RPC_TIMEOUT_SECONDS = 8
STREAM_TIMEOUT_SECONDS = 15
CONNECTION_TIMEOUT_SECONDS = 3
MAX_RPC_HISTORY = 200

T = TypeVar("T")


@dataclass(frozen=True)
class RpcRecord:
    timestamp: datetime
    method: str
    success: bool
    status: str
    latency_ms: float


@dataclass(frozen=True)
class ConnectionSnapshot:
    address: str
    connected: bool
    total_requests: int
    last_latency_ms: float | None
    history: tuple[RpcRecord, ...]


class StudentGrpcClient:
    """Thread-safe gRPC gateway with per-session request telemetry."""

    def __init__(self, address: str = SERVER_ADDRESS) -> None:
        self.address = address
        self._lock = threading.RLock()
        self._history: deque[RpcRecord] = deque(maxlen=MAX_RPC_HISTORY)
        self._total_requests = 0
        self._last_latency_ms: float | None = None
        self._connected = False
        self._channel: grpc.Channel
        self._stub: student_pb2_grpc.StudentServiceStub
        self._create_channel()

    def _create_channel(self) -> None:
        self._channel = grpc.insecure_channel(self.address)
        self._stub = student_pb2_grpc.StudentServiceStub(self._channel)

    @staticmethod
    def _connection_failed(code: grpc.StatusCode) -> bool:
        return code in {
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            grpc.StatusCode.CANCELLED,
        }

    def _record(
        self, method: str, success: bool, status: str, latency_ms: float
    ) -> None:
        with self._lock:
            self._total_requests += 1
            self._last_latency_ms = latency_ms
            self._history.appendleft(
                RpcRecord(
                    timestamp=datetime.now(),
                    method=method,
                    success=success,
                    status=status,
                    latency_ms=latency_ms,
                )
            )

    def _execute(self, method: str, operation: Callable[[], T]) -> T:
        started = time.perf_counter()
        try:
            result = operation()
        except grpc.RpcError as error:
            latency_ms = (time.perf_counter() - started) * 1000
            code = error.code()
            with self._lock:
                if self._connection_failed(code):
                    self._connected = False
                else:
                    self._connected = True
            self._record(method, False, code.name, latency_ms)
            raise
        except BaseException:
            latency_ms = (time.perf_counter() - started) * 1000
            self._record(method, False, "CLIENT_ERROR", latency_ms)
            raise

        latency_ms = (time.perf_counter() - started) * 1000
        with self._lock:
            self._connected = True
        self._record(method, True, "OK", latency_ms)
        return result

    def create_student(self, student: student_pb2.Student) -> student_pb2.Student:
        return self._execute(
            "CreateStudent",
            lambda: self._stub.CreateStudent(student, timeout=RPC_TIMEOUT_SECONDS),
        )

    def get_student(self, student_id: str) -> student_pb2.Student:
        return self._execute(
            "GetStudent",
            lambda: self._stub.GetStudent(
                student_pb2.StudentIdRequest(id=student_id),
                timeout=RPC_TIMEOUT_SECONDS,
            ),
        )

    def update_student(self, student: student_pb2.Student) -> student_pb2.Student:
        return self._execute(
            "UpdateStudent",
            lambda: self._stub.UpdateStudent(student, timeout=RPC_TIMEOUT_SECONDS),
        )

    def delete_student(self, student_id: str) -> student_pb2.DeleteStudentResponse:
        return self._execute(
            "DeleteStudent",
            lambda: self._stub.DeleteStudent(
                student_pb2.StudentIdRequest(id=student_id),
                timeout=RPC_TIMEOUT_SECONDS,
            ),
        )

    def list_students(self) -> list[student_pb2.Student]:
        return self._execute(
            "ListStudents",
            lambda: list(
                self._stub.ListStudents(
                    student_pb2.Empty(), timeout=STREAM_TIMEOUT_SECONDS
                )
            ),
        )

    def check_connection(self) -> bool:
        """Wait for the real channel to become ready without inventing an RPC."""

        started = time.perf_counter()
        try:
            grpc.channel_ready_future(self._channel).result(
                timeout=CONNECTION_TIMEOUT_SECONDS
            )
        except (grpc.FutureTimeoutError, grpc.RpcError):
            latency_ms = (time.perf_counter() - started) * 1000
            with self._lock:
                self._connected = False
            self._record("ChannelReady", False, "UNAVAILABLE", latency_ms)
            return False

        latency_ms = (time.perf_counter() - started) * 1000
        with self._lock:
            self._connected = True
        self._record("ChannelReady", True, "READY", latency_ms)
        return True

    def reconnect(self) -> bool:
        with self._lock:
            old_channel = self._channel
            self._create_channel()
        old_channel.close()
        return self.check_connection()

    def snapshot(self) -> ConnectionSnapshot:
        with self._lock:
            return ConnectionSnapshot(
                address=self.address,
                connected=self._connected,
                total_requests=self._total_requests,
                last_latency_ms=self._last_latency_ms,
                history=tuple(self._history),
            )

    def close(self) -> None:
        with self._lock:
            self._connected = False
            self._channel.close()
