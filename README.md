# Hệ thống quản lý sinh viên phân tán sử dụng gRPC bằng Python

Đồ án minh họa mô hình **Client–Server phân tán**. Nhiều Client có thể kết nối đồng thời đến một gRPC Server để thêm, tìm kiếm, cập nhật, xóa và xem danh sách sinh viên được lưu trong SQLite.

## 1. Công nghệ sử dụng

- Python 3.10 trở lên
- gRPC và Protocol Buffers
- SQLite
- `ThreadPoolExecutor` để Server xử lý đồng thời nhiều request
- `threading.Lock` để bảo vệ kết nối cơ sở dữ liệu

## 2. Chức năng

1. Thêm sinh viên (`CreateStudent`)
2. Tìm sinh viên theo mã (`GetStudent`)
3. Cập nhật sinh viên (`UpdateStudent`)
4. Xóa sinh viên (`DeleteStudent`)
5. Xem danh sách sinh viên bằng **Server Streaming** (`ListStudents`)

Server kiểm tra GPA trong khoảng `0.0` đến `4.0` và trả các gRPC status code phù hợp:

- `INVALID_ARGUMENT`: dữ liệu đầu vào không hợp lệ hoặc GPA ngoài khoảng cho phép.
- `ALREADY_EXISTS`: mã sinh viên đã tồn tại.
- `NOT_FOUND`: không tìm thấy mã sinh viên cần tìm, cập nhật hoặc xóa.
- `UNAVAILABLE`: Client không kết nối được đến Server.

## 3. Cấu trúc thư mục

```text
DoAn_CS420/
├── README.md
├── requirements.txt
├── student.proto
├── database.py
├── server.py
├── client.py
├── student_pb2.py          # Sinh tự động từ student.proto
├── student_pb2_grpc.py     # Sinh tự động từ student.proto
└── students.db             # Tự tạo khi Server chạy lần đầu
```

> Không chỉnh sửa thủ công `student_pb2.py` và `student_pb2_grpc.py`. Khi thay đổi `student.proto`, hãy chạy lại lệnh biên dịch Protocol Buffers.

## 4. Yêu cầu môi trường

Cài đặt:

- Python 3.10 hoặc mới hơn: <https://www.python.org/downloads/>
- Visual Studio Code: <https://code.visualstudio.com/>
- Extension **Python** của Microsoft trong VS Code

Kiểm tra Python trong Terminal:

```powershell
python --version
```

Nếu lệnh `python` không hoạt động nhưng Python Launcher đã được cài đặt, có thể thay `python` bằng `py` trong các lệnh bên dưới.

## 5. Tạo và kích hoạt môi trường ảo

Mở thư mục `E:\DoAn_CS420` bằng VS Code, sau đó mở **Terminal → New Terminal**.

### PowerShell

```powershell
cd E:\DoAn_CS420
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn script kích hoạt, chạy lệnh sau một lần trong Terminal hiện tại rồi kích hoạt lại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Command Prompt (CMD)

```bat
cd /d E:\DoAn_CS420
python -m venv .venv
.venv\Scripts\activate.bat
```

Khi môi trường được kích hoạt thành công, đầu dòng lệnh sẽ xuất hiện `(.venv)`.

## 6. Cài đặt thư viện

Sau khi kích hoạt môi trường ảo:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Các phiên bản thư viện được ghim trong `requirements.txt` để các máy sử dụng cùng môi trường:

```text
grpcio==1.76.0
grpcio-tools==1.76.0
protobuf==6.33.0
```

## 7. Biên dịch file Protocol Buffers

Tại thư mục gốc của dự án, chạy:

```powershell
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. student.proto
```

Lệnh trên tạo hai file:

- `student_pb2.py`: chứa các lớp message Protobuf.
- `student_pb2_grpc.py`: chứa Stub phía Client và Servicer phía Server.

Do hai file được sinh ngay tại thư mục gốc, các lệnh import sau trong `server.py` và `client.py` hoạt động trực tiếp:

```python
import student_pb2
import student_pb2_grpc
```

Kiểm tra nhanh hai file đã được tạo:

```powershell
Get-ChildItem student_pb2*.py
```

Trong CMD có thể dùng:

```bat
dir student_pb2*.py
```

## 8. Chạy hệ thống

Cần mở **ba Terminal riêng biệt**: một Terminal chạy Server và hai Terminal chạy hai Client.

### Terminal 1 – Chạy Server

```powershell
cd E:\DoAn_CS420
.\.venv\Scripts\Activate.ps1
python server.py
```

Kết quả mong đợi:

```text
2026-... | INFO | gRPC Server đang chạy tại cổng 50051
```

Server lắng nghe tại cổng `50051`. File `students.db` được tạo tự động trong thư mục dự án khi Server chạy lần đầu.

Giữ Terminal này hoạt động trong suốt quá trình sử dụng. Nhấn `Ctrl+C` khi muốn dừng Server.

### Terminal 2 – Chạy Client thứ nhất

```powershell
cd E:\DoAn_CS420
.\.venv\Scripts\Activate.ps1
python client.py
```

### Terminal 3 – Chạy Client thứ hai

```powershell
cd E:\DoAn_CS420
.\.venv\Scripts\Activate.ps1
python client.py
```

Hai Client kết nối độc lập tới cùng Server và cùng thao tác trên cơ sở dữ liệu `students.db`. Đây là cách minh họa nhiều tiến trình Client gửi request đồng thời trong mô hình phân tán.

## 9. Sử dụng menu Client

Client hiển thị menu:

```text
========== QUẢN LÝ SINH VIÊN QUA gRPC ==========
1. Thêm sinh viên
2. Tìm sinh viên theo mã
3. Cập nhật sinh viên
4. Xóa sinh viên
5. Xem danh sách sinh viên (Server Streaming)
0. Thoát
```

### Ví dụ thêm sinh viên

Chọn `1`, sau đó nhập:

```text
Mã sinh viên: SV001
Họ tên: Nguyễn Văn An
Email: an@example.com
Chuyên ngành: Công nghệ thông tin
GPA (0.0 - 4.0): 3.5
```

### Ví dụ tìm sinh viên

Chọn `2` và nhập `SV001`.

### Ví dụ cập nhật sinh viên

Chọn `3`, nhập lại mã sinh viên hiện có và toàn bộ thông tin mới. Server thay thế các trường `name`, `email`, `major` và `gpa` của sinh viên đó.

### Ví dụ xóa sinh viên

Chọn `4` và nhập mã cần xóa.

### Xem danh sách bằng Server Streaming

Chọn `5`. Server gửi từng message `Student` trong stream; Client nhận các message và hiển thị dưới dạng bảng.

### Thoát Client

Chọn `0`. Việc thoát một Client không làm dừng Server hoặc các Client khác.

## 10. Kịch bản demo đa Client

1. Chạy Server ở Terminal 1.
2. Chạy Client 1 ở Terminal 2.
3. Chạy Client 2 ở Terminal 3.
4. Tại Client 1, thêm sinh viên `SV001`.
5. Tại Client 2, chọn chức năng xem danh sách và kiểm tra `SV001` xuất hiện.
6. Tại Client 2, cập nhật GPA của `SV001`.
7. Tại Client 1, tìm lại `SV001` và kiểm tra dữ liệu mới.
8. Thử thêm lại `SV001` để quan sát lỗi `ALREADY_EXISTS`.
9. Thử tìm một mã không tồn tại để quan sát lỗi `NOT_FOUND`.
10. Nhập GPA ngoài khoảng `0.0`–`4.0` để quan sát việc kiểm tra dữ liệu.

Kịch bản này minh họa hai Client độc lập cùng truy cập một dịch vụ gRPC và nhìn thấy dữ liệu nhất quán được quản lý tập trung tại Server.

## 11. Khế ước gRPC

`student.proto` định nghĩa message `Student`:

```protobuf
message Student {
  string id = 1;
  string name = 2;
  string email = 3;
  string major = 4;
  float gpa = 5;
}
```

Service gồm năm RPC:

```protobuf
service StudentService {
  rpc CreateStudent(Student) returns (Student);
  rpc GetStudent(StudentIdRequest) returns (Student);
  rpc UpdateStudent(Student) returns (Student);
  rpc DeleteStudent(StudentIdRequest) returns (DeleteStudentResponse);
  rpc ListStudents(Empty) returns (stream Student);
}
```

Từ khóa `stream` trong kiểu trả về của `ListStudents` xác định đây là **Server Streaming RPC**.

## 12. Cơ chế xử lý đồng thời

- gRPC Server dùng `ThreadPoolExecutor(max_workers=10)` để xử lý nhiều request đồng thời.
- SQLite được mở với `check_same_thread=False` để kết nối có thể được sử dụng bởi các worker thread.
- `database.py` dùng một `threading.Lock` chung quanh mọi truy vấn và thao tác `commit`.
- Cách triển khai này ngăn nhiều thread sử dụng cùng kết nối SQLite tại cùng một thời điểm.

## 13. Khắc phục lỗi thường gặp

### `ModuleNotFoundError: No module named 'grpc'`

Môi trường ảo chưa được kích hoạt hoặc chưa cài thư viện:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### `ModuleNotFoundError: No module named 'student_pb2'`

Chưa biên dịch file `.proto`, hoặc đang chạy lệnh ngoài thư mục dự án:

```powershell
cd E:\DoAn_CS420
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. student.proto
```

### Client báo không thể kết nối đến Server

Kiểm tra:

1. Terminal Server còn đang chạy hay không.
2. Server có hiển thị thông báo chạy tại cổng `50051` hay không.
3. `client.py` đang dùng địa chỉ `localhost:50051`.
4. Tường lửa hoặc chương trình khác có chiếm cổng `50051` hay không.

Có thể kiểm tra cổng trên Windows bằng:

```powershell
Get-NetTCPConnection -LocalPort 50051
```

### Lỗi không kích hoạt được `.venv` trong PowerShell

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Thiết lập này chỉ áp dụng cho phiên PowerShell hiện tại.

### Thay đổi `student.proto` nhưng chương trình vẫn dùng cấu trúc cũ

Biên dịch lại file `.proto` rồi khởi động lại Server và Client:

```powershell
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. student.proto
```

## 14. Dữ liệu và chạy lại từ đầu

Dữ liệu được lưu trong `students.db`. Muốn làm sạch dữ liệu để demo lại từ đầu:

1. Dừng Server bằng `Ctrl+C`.
2. Sao lưu `students.db` nếu cần giữ dữ liệu.
3. Xóa `students.db`.
4. Chạy lại `python server.py`; Server sẽ tự tạo cơ sở dữ liệu và bảng `students` mới.

Không xóa file cơ sở dữ liệu trong lúc Server đang chạy.

## 15. Lưu ý bảo mật và phạm vi đồ án

Dự án dùng `grpc.insecure_channel` và Server không cấu hình TLS để phù hợp với môi trường học tập, chạy cục bộ và demo trên một máy. Trong hệ thống thực tế cần bổ sung TLS, xác thực, phân quyền, validation email nâng cao và chiến lược quản lý kết nối cơ sở dữ liệu phù hợp với tải lớn.
