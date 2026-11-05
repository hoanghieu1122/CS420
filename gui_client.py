import math
import queue
import threading
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import Any, Optional

import customtkinter as ctk
import grpc

import student_pb2
import student_pb2_grpc


SERVER_ADDRESS = "localhost:50051"
RPC_TIMEOUT_SECONDS = 8
STREAM_TIMEOUT_SECONDS = 15

COLORS = {
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "sidebar": "#0F3D77",
    "sidebar_hover": "#164E92",
    "background": "#F1F5F9",
    "surface": "#FFFFFF",
    "surface_muted": "#E2E8F0",
    "text": "#0F172A",
    "text_muted": "#64748B",
    "success": "#16A34A",
    "danger": "#DC2626",
    "danger_hover": "#B91C1C",
}


class StudentDialog(ctk.CTkToplevel):
    """Hộp thoại dùng chung cho thao tác thêm và cập nhật sinh viên."""

    def __init__(
        self,
        parent: "StudentManagementApp",
        title: str,
        on_submit: Callable[[student_pb2.Student, "StudentDialog"], None],
        student: Optional[student_pb2.Student] = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._editing = student is not None
        self._busy = False

        self.title(title)
        self.geometry("520x590")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["background"])
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, padx=32, pady=(28, 6), sticky="w")

        subtitle = (
            "Chỉnh sửa thông tin và nhấn Lưu thay đổi."
            if self._editing
            else "Nhập đầy đủ thông tin sinh viên mới."
        )
        ctk.CTkLabel(
            self,
            text=subtitle,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_muted"],
        ).grid(row=1, column=0, padx=32, pady=(0, 20), sticky="w")

        form = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=14)
        form.grid(row=2, column=0, padx=32, sticky="nsew")
        form.grid_columnconfigure(0, weight=1)

        self.id_entry = self._create_field(form, 0, "Mã sinh viên", "Ví dụ: SV001")
        self.name_entry = self._create_field(form, 2, "Họ và tên", "Nguyễn Văn An")
        self.email_entry = self._create_field(form, 4, "Email", "sinhvien@example.com")
        self.major_entry = self._create_field(
            form, 6, "Chuyên ngành", "Công nghệ thông tin"
        )
        self.gpa_entry = self._create_field(form, 8, "GPA", "Từ 0.0 đến 4.0")

        if student is not None:
            self.id_entry.insert(0, student.id)
            self.name_entry.insert(0, student.name)
            self.email_entry.insert(0, student.email)
            self.major_entry.insert(0, student.major)
            self.gpa_entry.insert(0, f"{student.gpa:.2f}")
            self.id_entry.configure(state="disabled")

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=3, column=0, padx=32, pady=24, sticky="ew")
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.cancel_button = ctk.CTkButton(
            button_frame,
            text="Hủy",
            height=42,
            corner_radius=9,
            fg_color=COLORS["surface_muted"],
            hover_color="#CBD5E1",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=self._close,
        )
        self.cancel_button.grid(row=0, column=0, padx=(0, 7), sticky="ew")

        self.save_button = ctk.CTkButton(
            button_frame,
            text="Lưu thay đổi" if self._editing else "Thêm sinh viên",
            height=42,
            corner_radius=9,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=self._submit,
        )
        self.save_button.grid(row=0, column=1, padx=(7, 0), sticky="ew")

        self.bind("<Return>", lambda _event: self._submit())
        self.after(20, self._center_on_parent)
        if not self._editing:
            self.id_entry.focus_set()
        else:
            self.name_entry.focus_set()

    @staticmethod
    def _create_field(
        parent: ctk.CTkFrame, row: int, label: str, placeholder: str
    ) -> ctk.CTkEntry:
        ctk.CTkLabel(
            parent,
            text=label,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=row, column=0, padx=22, pady=(14 if row == 0 else 8, 5), sticky="w")

        entry = ctk.CTkEntry(
            parent,
            height=40,
            corner_radius=8,
            border_color="#CBD5E1",
            fg_color="#F8FAFC",
            text_color=COLORS["text"],
            placeholder_text=placeholder,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        entry.grid(row=row + 1, column=0, padx=22, pady=(0, 5), sticky="ew")
        return entry

    def _center_on_parent(self) -> None:
        if not self.winfo_exists():
            return
        self.update_idletasks()
        parent = self.master
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _submit(self) -> None:
        if self._busy:
            return

        student_id = self.id_entry.get().strip()
        name = self.name_entry.get().strip()
        email = self.email_entry.get().strip()
        major = self.major_entry.get().strip()
        gpa_text = self.gpa_entry.get().strip()

        if not all((student_id, name, email, major, gpa_text)):
            messagebox.showwarning(
                "Thiếu thông tin",
                "Vui lòng nhập đầy đủ tất cả các trường.",
                parent=self,
            )
            return

        try:
            gpa = float(gpa_text)
        except ValueError:
            messagebox.showwarning(
                "GPA không hợp lệ", "GPA phải là một số.", parent=self
            )
            self.gpa_entry.focus_set()
            return

        if not math.isfinite(gpa) or not 0.0 <= gpa <= 4.0:
            messagebox.showwarning(
                "GPA không hợp lệ",
                "GPA phải nằm trong khoảng từ 0.0 đến 4.0.",
                parent=self,
            )
            self.gpa_entry.focus_set()
            return

        student = student_pb2.Student(
            id=student_id,
            name=name,
            email=email,
            major=major,
            gpa=gpa,
        )
        self.set_busy(True)
        self._on_submit(student, self)

    def set_busy(self, busy: bool) -> None:
        if not self.winfo_exists():
            return
        self._busy = busy
        self.save_button.configure(
            state="disabled" if busy else "normal",
            text="Đang xử lý..."
            if busy
            else ("Lưu thay đổi" if self._editing else "Thêm sinh viên"),
        )
        self.cancel_button.configure(state="disabled" if busy else "normal")

    def _close(self) -> None:
        if not self._busy and self.winfo_exists():
            self.grab_release()
            self.destroy()


class StudentManagementApp(ctk.CTk):
    """Ứng dụng quản lý sinh viên kết nối đến gRPC Server."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Hệ thống quản lý sinh viên phân tán")
        self.geometry("1220x760")
        self.minsize(1040, 680)
        self.configure(fg_color=COLORS["background"])

        self._closing = False
        self._students: dict[str, student_pb2.Student] = {}
        self._ui_queue: queue.Queue[
            tuple[Callable[..., None], tuple[Any, ...]]
        ] = queue.Queue()
        self._view_generation = 0

        self._channel = grpc.insecure_channel(SERVER_ADDRESS)
        self._stub = student_pb2_grpc.StudentServiceStub(self._channel)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._build_sidebar()
        self._build_main_content()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Queue được đọc trên Tk thread; worker không truy cập widget trực tiếp.
        self.after(50, self._drain_ui_queue)
        self.after(150, self.refresh_students)

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(
            self, width=255, corner_radius=0, fg_color=COLORS["sidebar"]
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(7, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            sidebar,
            text="STUDENT\nMANAGER",
            justify="left",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color="#FFFFFF",
        ).grid(row=0, column=0, padx=26, pady=(36, 8), sticky="ew")

        ctk.CTkLabel(
            sidebar,
            text="Hệ thống quản lý phân tán",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#BFDBFE",
        ).grid(row=1, column=0, padx=26, pady=(0, 30), sticky="ew")

        ctk.CTkLabel(
            sidebar,
            text="TRẠNG THÁI gRPC",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#93C5FD",
        ).grid(row=2, column=0, padx=26, pady=(0, 8), sticky="ew")

        self.status_label = ctk.CTkLabel(
            sidebar,
            text="●  Disconnected",
            height=38,
            corner_radius=8,
            fg_color="#153B6D",
            text_color="#FCA5A5",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        )
        self.status_label.grid(row=3, column=0, padx=20, pady=(0, 30), sticky="ew")

        self.refresh_button = ctk.CTkButton(
            sidebar,
            text="↻  Làm mới danh sách",
            height=44,
            corner_radius=9,
            anchor="w",
            fg_color=COLORS["sidebar_hover"],
            hover_color="#1E5FA9",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=self.refresh_students,
        )
        self.refresh_button.grid(row=4, column=0, padx=20, pady=(0, 12), sticky="ew")

        ctk.CTkButton(
            sidebar,
            text="＋  Thêm sinh viên",
            height=44,
            corner_radius=9,
            anchor="w",
            fg_color="#FFFFFF",
            hover_color="#DBEAFE",
            text_color=COLORS["sidebar"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=self.open_add_dialog,
        ).grid(row=5, column=0, padx=20, sticky="ew")

        ctk.CTkLabel(
            sidebar,
            text=f"Server: {SERVER_ADDRESS}",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#93C5FD",
        ).grid(row=8, column=0, padx=26, pady=24, sticky="sew")

    def _build_main_content(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, padx=30, pady=26, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            main,
            text="Quản lý sinh viên",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(
            main,
            text="Theo dõi và quản lý dữ liệu sinh viên qua gRPC.",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).grid(row=1, column=0, pady=(2, 18), sticky="ew")

        top_area = ctk.CTkFrame(main, fg_color="transparent")
        top_area.grid(row=2, column=0, pady=(0, 18), sticky="ew")
        top_area.grid_columnconfigure(1, weight=1)

        total_card = ctk.CTkFrame(
            top_area,
            width=230,
            height=104,
            fg_color=COLORS["surface"],
            corner_radius=14,
            border_width=1,
            border_color="#E2E8F0",
        )
        total_card.grid(row=0, column=0, padx=(0, 18), sticky="nsw")
        total_card.grid_propagate(False)

        ctk.CTkLabel(
            total_card,
            text="TỔNG SỐ SINH VIÊN",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(fill="x", padx=20, pady=(17, 2))

        self.total_label = ctk.CTkLabel(
            total_card,
            text="0",
            font=ctk.CTkFont(family="Segoe UI", size=34, weight="bold"),
            text_color=COLORS["primary"],
            anchor="w",
        )
        self.total_label.pack(fill="x", padx=20)

        search_card = ctk.CTkFrame(
            top_area,
            height=104,
            fg_color=COLORS["surface"],
            corner_radius=14,
            border_width=1,
            border_color="#E2E8F0",
        )
        search_card.grid(row=0, column=1, sticky="nsew")
        search_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            search_card,
            text="TÌM KIẾM THEO MÃ SINH VIÊN",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, padx=20, pady=(14, 7), sticky="ew")

        self.search_entry = ctk.CTkEntry(
            search_card,
            height=38,
            placeholder_text="Nhập mã sinh viên...",
            border_color="#CBD5E1",
            fg_color="#F8FAFC",
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.search_entry.grid(row=1, column=0, padx=(20, 8), pady=(0, 14), sticky="ew")
        self.search_entry.bind("<Return>", lambda _event: self.search_student())

        self.search_button = ctk.CTkButton(
            search_card,
            text="Tìm kiếm",
            width=100,
            height=38,
            corner_radius=8,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            command=self.search_student,
        )
        self.search_button.grid(row=1, column=1, padx=0, pady=(0, 14))

        ctk.CTkButton(
            search_card,
            text="Hiện tất cả",
            width=100,
            height=38,
            corner_radius=8,
            fg_color=COLORS["surface_muted"],
            hover_color="#CBD5E1",
            text_color=COLORS["text"],
            command=self.show_all_students,
        ).grid(row=1, column=2, padx=(8, 20), pady=(0, 14))

        table_card = ctk.CTkFrame(
            main,
            fg_color=COLORS["surface"],
            corner_radius=14,
            border_width=1,
            border_color="#E2E8F0",
        )
        table_card.grid(row=3, column=0, sticky="nsew")
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(1, weight=1)

        table_header = ctk.CTkFrame(table_card, fg_color="transparent")
        table_header.grid(row=0, column=0, padx=20, pady=(16, 12), sticky="ew")
        table_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            table_header,
            text="Danh sách sinh viên",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        self.edit_button = ctk.CTkButton(
            table_header,
            text="Sửa",
            width=78,
            height=34,
            corner_radius=8,
            state="disabled",
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            command=self.open_edit_dialog,
        )
        self.edit_button.grid(row=0, column=1, padx=(8, 0))

        self.delete_button = ctk.CTkButton(
            table_header,
            text="Xóa",
            width=78,
            height=34,
            corner_radius=8,
            state="disabled",
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self.delete_selected_student,
        )
        self.delete_button.grid(row=0, column=2, padx=(8, 0))

        tree_frame = ctk.CTkFrame(table_card, fg_color="transparent")
        tree_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self._configure_treeview_style()
        columns = ("id", "name", "email", "major", "gpa")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            style="Students.Treeview",
            selectmode="browse",
        )
        headings = {
            "id": "Mã SV",
            "name": "Họ tên",
            "email": "Email",
            "major": "Chuyên ngành",
            "gpa": "GPA",
        }
        widths = {"id": 105, "name": 190, "email": 220, "major": 180, "gpa": 70}
        for column in columns:
            self.tree.heading(column, text=headings[column], anchor="w")
            self.tree.column(
                column,
                width=widths[column],
                minwidth=60,
                stretch=column not in ("id", "gpa"),
                anchor="w" if column != "gpa" else "center",
            )

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_selection)
        self.tree.bind("<Double-1>", lambda _event: self.open_edit_dialog())

    @staticmethod
    def _configure_treeview_style() -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Students.Treeview",
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground=COLORS["text"],
            rowheight=38,
            borderwidth=0,
            relief="flat",
            font=("Segoe UI", 11),
        )
        style.configure(
            "Students.Treeview.Heading",
            background="#EAF2FF",
            foreground="#1E3A5F",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 11, "bold"),
            padding=(8, 10),
        )
        style.map(
            "Students.Treeview",
            background=[("selected", COLORS["primary"])],
            foreground=[("selected", "#FFFFFF")],
        )
        style.map(
            "Students.Treeview.Heading",
            background=[("active", "#DBEAFE")],
        )

    def _run_rpc(
        self,
        worker: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Optional[Callable[[BaseException], None]] = None,
    ) -> None:
        """Chạy RPC trên worker thread và chuyển kết quả về Tk event loop."""

        def task() -> None:
            try:
                result = worker()
            except BaseException as error:
                callback = on_error or self._handle_rpc_error
                self._ui_queue.put((callback, (error,)))
            else:
                self._ui_queue.put((on_success, (result,)))

        threading.Thread(target=task, daemon=True).start()

    def _drain_ui_queue(self) -> None:
        if self._closing:
            return

        while True:
            try:
                callback, arguments = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*arguments)
            except Exception as error:
                messagebox.showerror(
                    "Lỗi giao diện",
                    f"Không thể cập nhật giao diện: {error}",
                    parent=self,
                )

        self.after(50, self._drain_ui_queue)

    def _next_view_generation(self) -> int:
        self._view_generation += 1
        return self._view_generation

    def _set_connection_status(self, connected: bool) -> None:
        if connected:
            self.status_label.configure(
                text="●  Connected", text_color="#86EFAC", fg_color="#14532D"
            )
        else:
            self.status_label.configure(
                text="●  Disconnected", text_color="#FCA5A5", fg_color="#153B6D"
            )

    def refresh_students(self) -> None:
        generation = self._next_view_generation()
        self.refresh_button.configure(state="disabled", text="↻  Đang tải...")

        def worker() -> list[student_pb2.Student]:
            # ListStudents là Server Streaming; mỗi message được nhận trên worker thread.
            stream = self._stub.ListStudents(
                student_pb2.Empty(), timeout=STREAM_TIMEOUT_SECONDS
            )
            return list(stream)

        def success(students: list[student_pb2.Student]) -> None:
            self.refresh_button.configure(state="normal", text="↻  Làm mới danh sách")
            if generation != self._view_generation:
                return
            self._students = {student.id: student for student in students}
            self._render_students(students)
            self.total_label.configure(text=str(len(students)))
            self._set_connection_status(True)

        def failure(error: BaseException) -> None:
            self.refresh_button.configure(state="normal", text="↻  Làm mới danh sách")
            if generation == self._view_generation:
                self._handle_rpc_error(error)

        self._run_rpc(worker, success, failure)

    def search_student(self) -> None:
        student_id = self.search_entry.get().strip()
        if not student_id:
            self.refresh_students()
            return

        generation = self._next_view_generation()
        self.search_button.configure(state="disabled", text="Đang tìm...")

        def worker() -> student_pb2.Student:
            return self._stub.GetStudent(
                student_pb2.StudentIdRequest(id=student_id),
                timeout=RPC_TIMEOUT_SECONDS,
            )

        def success(student: student_pb2.Student) -> None:
            self.search_button.configure(state="normal", text="Tìm kiếm")
            if generation != self._view_generation:
                return
            self._students[student.id] = student
            self._render_students([student])
            self._set_connection_status(True)

        def failure(error: BaseException) -> None:
            self.search_button.configure(state="normal", text="Tìm kiếm")
            if generation == self._view_generation:
                self._handle_rpc_error(error)

        self._run_rpc(worker, success, failure)

    def show_all_students(self) -> None:
        self.search_entry.delete(0, "end")
        self.refresh_students()

    def _render_students(self, students: list[student_pb2.Student]) -> None:
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

        for student in students:
            self.tree.insert(
                "",
                "end",
                iid=student.id,
                values=(
                    student.id,
                    student.name,
                    student.email,
                    student.major,
                    f"{student.gpa:.2f}",
                ),
            )
        self._on_tree_selection()

    def _selected_student(self) -> Optional[student_pb2.Student]:
        selected = self.tree.selection()
        if len(selected) != 1:
            return None
        return self._students.get(selected[0])

    def _on_tree_selection(self, _event: Any = None) -> None:
        state = "normal" if self._selected_student() is not None else "disabled"
        self.edit_button.configure(state=state)
        self.delete_button.configure(state=state)

    def open_add_dialog(self) -> None:
        StudentDialog(
            self,
            title="Thêm sinh viên",
            on_submit=self.create_student,
        )

    def open_edit_dialog(self) -> None:
        student = self._selected_student()
        if student is None:
            messagebox.showinfo(
                "Chưa chọn sinh viên",
                "Vui lòng chọn một sinh viên trong bảng để cập nhật.",
                parent=self,
            )
            return
        StudentDialog(
            self,
            title="Cập nhật sinh viên",
            student=student,
            on_submit=self.update_student,
        )

    def create_student(
        self, student: student_pb2.Student, dialog: StudentDialog
    ) -> None:
        def worker() -> student_pb2.Student:
            return self._stub.CreateStudent(student, timeout=RPC_TIMEOUT_SECONDS)

        def success(created: student_pb2.Student) -> None:
            self._set_connection_status(True)
            if dialog.winfo_exists():
                dialog.set_busy(False)
                dialog.destroy()
            messagebox.showinfo(
                "Thành công",
                f"Đã thêm sinh viên '{created.id}'.",
                parent=self,
            )
            self.refresh_students()

        def failure(error: BaseException) -> None:
            if dialog.winfo_exists():
                dialog.set_busy(False)
            self._handle_rpc_error(error, parent=dialog if dialog.winfo_exists() else self)

        self._run_rpc(worker, success, failure)

    def update_student(
        self, student: student_pb2.Student, dialog: StudentDialog
    ) -> None:
        def worker() -> student_pb2.Student:
            return self._stub.UpdateStudent(student, timeout=RPC_TIMEOUT_SECONDS)

        def success(updated: student_pb2.Student) -> None:
            self._set_connection_status(True)
            if dialog.winfo_exists():
                dialog.set_busy(False)
                dialog.destroy()
            messagebox.showinfo(
                "Thành công",
                f"Đã cập nhật sinh viên '{updated.id}'.",
                parent=self,
            )
            self.refresh_students()

        def failure(error: BaseException) -> None:
            if dialog.winfo_exists():
                dialog.set_busy(False)
            self._handle_rpc_error(error, parent=dialog if dialog.winfo_exists() else self)

        self._run_rpc(worker, success, failure)

    def delete_selected_student(self) -> None:
        student = self._selected_student()
        if student is None:
            messagebox.showinfo(
                "Chưa chọn sinh viên",
                "Vui lòng chọn một sinh viên trong bảng để xóa.",
                parent=self,
            )
            return

        confirmed = messagebox.askyesno(
            "Xác nhận xóa",
            f"Bạn có chắc muốn xóa sinh viên '{student.id} - {student.name}' không?",
            icon="warning",
            parent=self,
        )
        if not confirmed:
            return

        self.delete_button.configure(state="disabled", text="Đang xóa...")

        def worker() -> student_pb2.DeleteStudentResponse:
            return self._stub.DeleteStudent(
                student_pb2.StudentIdRequest(id=student.id),
                timeout=RPC_TIMEOUT_SECONDS,
            )

        def success(response: student_pb2.DeleteStudentResponse) -> None:
            self._set_connection_status(True)
            self.delete_button.configure(state="disabled", text="Xóa")
            messagebox.showinfo("Thành công", response.message, parent=self)
            self.refresh_students()

        def failure(error: BaseException) -> None:
            self.delete_button.configure(state="normal", text="Xóa")
            self._handle_rpc_error(error)

        self._run_rpc(worker, success, failure)

    def _handle_rpc_error(
        self, error: BaseException, parent: Optional[Any] = None
    ) -> None:
        parent = parent or self
        if not isinstance(error, grpc.RpcError):
            messagebox.showerror(
                "Lỗi không xác định",
                f"Đã xảy ra lỗi: {error}",
                parent=parent,
            )
            return

        code = error.code()
        details = error.details() or "Server không cung cấp thông tin chi tiết."

        if code == grpc.StatusCode.UNAVAILABLE:
            self._set_connection_status(False)
            message = (
                "Không thể kết nối đến gRPC Server tại cổng 50051. "
                "Vui lòng kiểm tra Server đang chạy."
            )
        elif code == grpc.StatusCode.NOT_FOUND:
            self._set_connection_status(True)
            message = f"Không tìm thấy dữ liệu.\n\n{details}"
        elif code == grpc.StatusCode.ALREADY_EXISTS:
            self._set_connection_status(True)
            message = f"Mã sinh viên đã tồn tại.\n\n{details}"
        elif code == grpc.StatusCode.INVALID_ARGUMENT:
            self._set_connection_status(True)
            message = f"Dữ liệu không hợp lệ.\n\n{details}"
        elif code == grpc.StatusCode.DEADLINE_EXCEEDED:
            message = "Yêu cầu đã quá thời gian chờ. Vui lòng thử lại."
        else:
            message = f"Lỗi gRPC [{code.name}]: {details}"

        messagebox.showerror("Lỗi gRPC", message, parent=parent)

    def _on_close(self) -> None:
        self._closing = True
        self._channel.close()
        self.destroy()


def main() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = StudentManagementApp()
    app.mainloop()


if __name__ == "__main__":
    main()
