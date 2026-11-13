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


SERVER_ADDRESS = "127.0.0.1:50051"
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
        self._channel_generation = 0
        self._channel, self._stub = self._create_channel(self.address)

    @staticmethod
    def _create_channel(
        address: str,
    ) -> tuple[grpc.Channel, student_pb2_grpc.StudentServiceStub]:
        channel = grpc.insecure_channel(address)
        return channel, student_pb2_grpc.StudentServiceStub(channel)

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

    def _execute(
        self, method: str, operation: Callable[[], T], generation: int
    ) -> T:
        started = time.perf_counter()
        try:
            result = operation()
        except grpc.RpcError as error:
            latency_ms = (time.perf_counter() - started) * 1000
            code = error.code()
            with self._lock:
                if generation == self._channel_generation:
                    self._connected = not self._connection_failed(code)
            self._record(method, False, code.name, latency_ms)
            raise
        except BaseException:
            latency_ms = (time.perf_counter() - started) * 1000
            self._record(method, False, "CLIENT_ERROR", latency_ms)
            raise

        latency_ms = (time.perf_counter() - started) * 1000
        with self._lock:
            if generation == self._channel_generation:
                self._connected = True
        self._record(method, True, "OK", latency_ms)
        return result

    def _active_stub(
        self,
    ) -> tuple[student_pb2_grpc.StudentServiceStub, int]:
        with self._lock:
            return self._stub, self._channel_generation

    def create_student(self, student: student_pb2.Student) -> student_pb2.Student:
        stub, generation = self._active_stub()
        return self._execute(
            "CreateStudent",
            lambda: stub.CreateStudent(student, timeout=RPC_TIMEOUT_SECONDS),
            generation,
        )

    def get_student(self, student_id: str) -> student_pb2.Student:
        stub, generation = self._active_stub()
        return self._execute(
            "GetStudent",
            lambda: stub.GetStudent(
                student_pb2.StudentIdRequest(id=student_id),
                timeout=RPC_TIMEOUT_SECONDS,
            ),
            generation,
        )

    def update_student(self, student: student_pb2.Student) -> student_pb2.Student:
        stub, generation = self._active_stub()
        return self._execute(
            "UpdateStudent",
            lambda: stub.UpdateStudent(student, timeout=RPC_TIMEOUT_SECONDS),
            generation,
        )

    def delete_student(self, student_id: str) -> student_pb2.DeleteStudentResponse:
        stub, generation = self._active_stub()
        return self._execute(
            "DeleteStudent",
            lambda: stub.DeleteStudent(
                student_pb2.StudentIdRequest(id=student_id),
                timeout=RPC_TIMEOUT_SECONDS,
            ),
            generation,
        )

    def list_students(self) -> list[student_pb2.Student]:
        stub, generation = self._active_stub()
        return self._execute(
            "ListStudents",
            lambda: list(
                stub.ListStudents(
                    student_pb2.Empty(), timeout=STREAM_TIMEOUT_SECONDS
                )
            ),
            generation,
        )

    def _check_channel(self, channel: grpc.Channel, generation: int) -> bool:
        started = time.perf_counter()
        connected = True
        status = "READY"
        try:
            grpc.channel_ready_future(channel).result(
                timeout=CONNECTION_TIMEOUT_SECONDS
            )
        except (grpc.FutureTimeoutError, grpc.RpcError):
            connected = False
            status = "UNAVAILABLE"

        latency_ms = (time.perf_counter() - started) * 1000
        with self._lock:
            is_current = (
                generation == self._channel_generation and channel is self._channel
            )
            if is_current:
                self._connected = connected
        if is_current:
            self._record("ChannelReady", connected, status, latency_ms)
        return connected and is_current

    def check_connection(self) -> bool:
        """Wait for the active channel to become ready without inventing an RPC."""

        with self._lock:
            channel = self._channel
            generation = self._channel_generation
        return self._check_channel(channel, generation)

    def connect(self, address: str) -> bool:
        normalized_address = address.strip()
        if not normalized_address:
            raise ValueError("Địa chỉ gRPC không được để trống.")

        new_channel, new_stub = self._create_channel(normalized_address)
        with self._lock:
            old_channel = self._channel
            self.address = normalized_address
            self._channel = new_channel
            self._stub = new_stub
            self._connected = False
            self._channel_generation += 1
            generation = self._channel_generation
        old_channel.close()
        return self._check_channel(new_channel, generation)

    def reconnect(self) -> bool:
        with self._lock:
            address = self.address
        return self.connect(address)

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
            self._channel_generation += 1
            channel = self._channel
        channel.close()
