from collections.abc import Iterable

import grpc

import student_pb2
import student_pb2_grpc


SERVER_ADDRESS = "localhost:50051"


def input_required(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Dữ liệu không được để trống. Vui lòng nhập lại.")


def input_gpa(prompt: str = "GPA (0.0 - 4.0): ") -> float:
    while True:
        raw_value = input(prompt).strip()
        try:
            gpa = float(raw_value)
        except ValueError:
            print("GPA phải là một số. Vui lòng nhập lại.")
            continue

        if 0.0 <= gpa <= 4.0:
            return gpa
        print("GPA phải nằm trong khoảng từ 0.0 đến 4.0.")


def input_student() -> student_pb2.Student:
    return student_pb2.Student(
        id=input_required("Mã sinh viên: "),
        name=input_required("Họ tên: "),
        email=input_required("Email: "),
        major=input_required("Chuyên ngành: "),
        gpa=input_gpa(),
    )


def print_student(student: student_pb2.Student) -> None:
    print(f"Mã sinh viên : {student.id}")
    print(f"Họ tên       : {student.name}")
    print(f"Email        : {student.email}")
    print(f"Chuyên ngành : {student.major}")
    print(f"GPA          : {student.gpa:.2f}")


def print_student_table(students: Iterable[student_pb2.Student]) -> None:
    rows = [
        [student.id, student.name, student.email, student.major, f"{student.gpa:.2f}"]
        for student in students
    ]
    if not rows:
        print("Danh sách sinh viên đang trống.")
        return

    headers = ["Mã SV", "Họ tên", "Email", "Chuyên ngành", "GPA"]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"

    def format_row(row: list[str]) -> str:
        return "| " + " | ".join(
            value.ljust(widths[index]) for index, value in enumerate(row)
        ) + " |"

    print(separator)
    print(format_row(headers))
    print(separator)
    for row in rows:
        print(format_row(row))
    print(separator)


def show_rpc_error(error: grpc.RpcError) -> None:
    code = error.code()
    details = error.details() or "Không có thông tin chi tiết."
    if code == grpc.StatusCode.UNAVAILABLE:
        print("Không thể kết nối đến Server. Hãy kiểm tra Server đang chạy tại cổng 50051.")
    else:
        print(f"Lỗi gRPC [{code.name}]: {details}")


def create_student(stub: student_pb2_grpc.StudentServiceStub) -> None:
    print("\n--- THÊM SINH VIÊN ---")
    student = stub.CreateStudent(input_student())
    print("Thêm sinh viên thành công:")
    print_student(student)


def get_student(stub: student_pb2_grpc.StudentServiceStub) -> None:
    print("\n--- TÌM SINH VIÊN ---")
    student_id = input_required("Nhập mã sinh viên cần tìm: ")
    student = stub.GetStudent(student_pb2.StudentIdRequest(id=student_id))
    print("Thông tin sinh viên:")
    print_student(student)


def update_student(stub: student_pb2_grpc.StudentServiceStub) -> None:
    print("\n--- CẬP NHẬT SINH VIÊN ---")
    print("Nhập đầy đủ thông tin mới của sinh viên.")
    student = stub.UpdateStudent(input_student())
    print("Cập nhật sinh viên thành công:")
    print_student(student)


def delete_student(stub: student_pb2_grpc.StudentServiceStub) -> None:
    print("\n--- XÓA SINH VIÊN ---")
    student_id = input_required("Nhập mã sinh viên cần xóa: ")
    response = stub.DeleteStudent(student_pb2.StudentIdRequest(id=student_id))
    print(response.message)


def list_students(stub: student_pb2_grpc.StudentServiceStub) -> None:
    print("\n--- DANH SÁCH SINH VIÊN (SERVER STREAMING) ---")
    # Lặp trực tiếp trên iterator để nhận từng message từ Server.
    students = list(stub.ListStudents(student_pb2.Empty()))
    print_student_table(students)


def print_menu() -> None:
    print("\n========== QUẢN LÝ SINH VIÊN QUA gRPC ==========")
    print("1. Thêm sinh viên")
    print("2. Tìm sinh viên theo mã")
    print("3. Cập nhật sinh viên")
    print("4. Xóa sinh viên")
    print("5. Xem danh sách sinh viên (Server Streaming)")
    print("0. Thoát")


def run() -> None:
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = student_pb2_grpc.StudentServiceStub(channel)
        actions = {
            "1": create_student,
            "2": get_student,
            "3": update_student,
            "4": delete_student,
            "5": list_students,
        }

        while True:
            print_menu()
            choice = input("Chọn chức năng: ").strip()
            if choice == "0":
                print("Đã thoát chương trình Client.")
                break

            action = actions.get(choice)
            if action is None:
                print("Lựa chọn không hợp lệ. Vui lòng chọn từ 0 đến 5.")
                continue

            try:
                action(stub)
            except grpc.RpcError as error:
                show_rpc_error(error)
            except (EOFError, KeyboardInterrupt):
                print("\nThao tác nhập liệu đã bị hủy.")


if __name__ == "__main__":
    try:
        run()
    except (EOFError, KeyboardInterrupt):
        print("\nĐã thoát chương trình Client.")
