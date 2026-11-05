import logging
from concurrent import futures
from typing import Any

import grpc

import student_pb2
import student_pb2_grpc
from database import StudentDatabase


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger(__name__)


def record_to_student(record: dict[str, Any]) -> student_pb2.Student:
    """Chuyển bản ghi SQLite thành message Protobuf."""
    return student_pb2.Student(
        id=record["id"],
        name=record["name"],
        email=record["email"],
        major=record["major"],
        gpa=record["gpa"],
    )


class StudentService(student_pb2_grpc.StudentServiceServicer):
    def __init__(self, database: StudentDatabase) -> None:
        self._database = database

    @staticmethod
    def _validate_id(student_id: str, context: grpc.ServicerContext) -> str:
        normalized_id = student_id.strip()
        if not normalized_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Mã sinh viên không được để trống.")
        return normalized_id

    @classmethod
    def _validate_student(
        cls, request: student_pb2.Student, context: grpc.ServicerContext
    ) -> student_pb2.Student:
        # Chuẩn hóa và kiểm tra dữ liệu ngay tại tầng server.
        student = student_pb2.Student(
            id=cls._validate_id(request.id, context),
            name=request.name.strip(),
            email=request.email.strip(),
            major=request.major.strip(),
            gpa=request.gpa,
        )

        if not student.name:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Họ tên không được để trống.")
        if not student.email:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Email không được để trống.")
        if not student.major:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Chuyên ngành không được để trống.")
        if not 0.0 <= student.gpa <= 4.0:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "GPA phải nằm trong khoảng từ 0.0 đến 4.0.",
            )
        return student

    def CreateStudent(
        self, request: student_pb2.Student, context: grpc.ServicerContext
    ) -> student_pb2.Student:
        student = self._validate_student(request, context)
        created = self._database.create_student(
            student.id, student.name, student.email, student.major, student.gpa
        )
        if not created:
            LOGGER.warning("Thêm thất bại do trùng mã sinh viên: %s", student.id)
            context.abort(
                grpc.StatusCode.ALREADY_EXISTS,
                f"Sinh viên có mã '{student.id}' đã tồn tại.",
            )

        LOGGER.info("Đã thêm sinh viên: %s", student.id)
        return student

    def GetStudent(
        self, request: student_pb2.StudentIdRequest, context: grpc.ServicerContext
    ) -> student_pb2.Student:
        student_id = self._validate_id(request.id, context)
        record = self._database.get_student(student_id)
        if record is None:
            LOGGER.warning("Không tìm thấy sinh viên: %s", student_id)
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Không tìm thấy sinh viên có mã '{student_id}'.",
            )

        LOGGER.info("Đã tìm sinh viên: %s", student_id)
        return record_to_student(record)

    def UpdateStudent(
        self, request: student_pb2.Student, context: grpc.ServicerContext
    ) -> student_pb2.Student:
        student = self._validate_student(request, context)
        updated = self._database.update_student(
            student.id, student.name, student.email, student.major, student.gpa
        )
        if not updated:
            LOGGER.warning("Không thể cập nhật sinh viên không tồn tại: %s", student.id)
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Không tìm thấy sinh viên có mã '{student.id}'.",
            )

        LOGGER.info("Đã cập nhật sinh viên: %s", student.id)
        return student

    def DeleteStudent(
        self, request: student_pb2.StudentIdRequest, context: grpc.ServicerContext
    ) -> student_pb2.DeleteStudentResponse:
        student_id = self._validate_id(request.id, context)
        deleted = self._database.delete_student(student_id)
        if not deleted:
            LOGGER.warning("Không thể xóa sinh viên không tồn tại: %s", student_id)
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Không tìm thấy sinh viên có mã '{student_id}'.",
            )

        LOGGER.info("Đã xóa sinh viên: %s", student_id)
        return student_pb2.DeleteStudentResponse(
            message=f"Đã xóa sinh viên có mã '{student_id}'."
        )

    def ListStudents(
        self, request: student_pb2.Empty, context: grpc.ServicerContext
    ):
        # Mỗi phần tử được yield riêng để tạo server stream.
        records = self._database.list_students()
        LOGGER.info("Bắt đầu stream danh sách %d sinh viên", len(records))
        for record in records:
            yield record_to_student(record)


def serve() -> None:
    database = StudentDatabase()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    student_pb2_grpc.add_StudentServiceServicer_to_server(
        StudentService(database), server
    )
    server.add_insecure_port("[::]:50051")
    server.start()
    LOGGER.info("gRPC Server đang chạy tại cổng 50051")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        LOGGER.info("Đang dừng gRPC Server...")
        server.stop(grace=5).wait()
    finally:
        database.close()
        LOGGER.info("Đã đóng kết nối cơ sở dữ liệu")


if __name__ == "__main__":
    serve()
