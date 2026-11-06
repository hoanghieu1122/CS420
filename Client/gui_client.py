from __future__ import annotations

import math
import queue
import re
import threading
from collections import Counter
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import Any, Optional

import customtkinter as ctk
import grpc
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import student_pb2
from grpc_client import ConnectionSnapshot, StudentGrpcClient


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
    "warning": "#D97706",
    "border": "#E2E8F0",
}

FONT_FAMILY = "Segoe UI"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class StudentDialog(ctk.CTkToplevel):
    """Hộp thoại thêm/cập nhật với form cuộn và footer luôn hiển thị."""

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
        self._error_labels: dict[str, ctk.CTkLabel] = {}
        self._entries: dict[str, ctk.CTkEntry] = {}

        self.title(title)
        self.configure(fg_color=COLORS["background"])
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grab_set()

        available_height = max(520, self.winfo_screenheight() - 120)
        self.minsize(480, min(520, available_height))
        self.maxsize(620, available_height)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header(title)
        self._build_form(student)
        self._build_footer()

        self.bind("<Return>", lambda _event: self._submit())
        self.bind("<Escape>", lambda _event: self._close())
        self.after(20, self._fit_and_center)
        (self.name_entry if self._editing else self.id_entry).focus_set()

    def _build_header(self, title: str) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=28, pady=(22, 12), sticky="ew")

        ctk.CTkLabel(
            header,
            text=title,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=23, weight="bold"),
            text_color=COLORS["text"],
        ).pack(fill="x")
        subtitle = (
            "Chỉnh sửa thông tin và lưu thay đổi."
            if self._editing
            else "Nhập đầy đủ thông tin sinh viên mới."
        )
        ctk.CTkLabel(
            header,
            text=subtitle,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color=COLORS["text_muted"],
        ).pack(fill="x", pady=(3, 0))

    def _build_form(self, student: Optional[student_pb2.Student]) -> None:
        self.form = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=14,
            border_width=1,
            border_color=COLORS["border"],
            scrollbar_button_color="#CBD5E1",
            scrollbar_button_hover_color="#94A3B8",
        )
        self.form.grid(row=1, column=0, padx=28, sticky="nsew")
        self.form.grid_columnconfigure(0, weight=1)

        self.id_entry = self._create_field("id", "Mã sinh viên", "Ví dụ: SV001")
        self.name_entry = self._create_field("name", "Họ và tên", "Nguyễn Văn An")
        self.email_entry = self._create_field(
            "email", "Email", "sinhvien@example.com"
        )
        self.major_entry = self._create_field(
            "major", "Chuyên ngành", "Công nghệ thông tin"
        )
        self.gpa_entry = self._create_field("gpa", "GPA", "Từ 0.0 đến 4.0")

        if student is not None:
            values = {
                "id": student.id,
                "name": student.name,
                "email": student.email,
                "major": student.major,
                "gpa": f"{student.gpa:.2f}",
            }
            for field, value in values.items():
                self._entries[field].insert(0, value)
            self.id_entry.configure(state="disabled")

    def _create_field(self, field: str, label: str, placeholder: str) -> ctk.CTkEntry:
        row = len(self._entries) * 3
        ctk.CTkLabel(
            self.form,
            text=label,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=row, column=0, padx=18, pady=(14 if row == 0 else 8, 5), sticky="ew")

        entry = ctk.CTkEntry(
            self.form,
            height=40,
            corner_radius=8,
            border_color="#CBD5E1",
            fg_color="#F8FAFC",
            text_color=COLORS["text"],
            placeholder_text=placeholder,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
        )
        entry.grid(row=row + 1, column=0, padx=18, sticky="ew")
        entry.bind("<KeyRelease>", lambda _event, name=field: self._clear_error(name))

        error_label = ctk.CTkLabel(
            self.form,
            text="",
            height=17,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLORS["danger"],
        )
        error_label.grid(row=row + 2, column=0, padx=18, pady=(2, 0), sticky="ew")
        self._entries[field] = entry
        self._error_labels[field] = error_label
        return entry

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=COLORS["background"])
        footer.grid(row=2, column=0, padx=28, pady=(14, 20), sticky="ew")
        footer.grid_columnconfigure((0, 1), weight=1)

        self.cancel_button = ctk.CTkButton(
            footer,
            text="Hủy",
            height=42,
            corner_radius=9,
            fg_color=COLORS["surface_muted"],
            hover_color="#CBD5E1",
            text_color=COLORS["text"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            command=self._close,
        )
        self.cancel_button.grid(row=0, column=0, padx=(0, 7), sticky="ew")

        self.save_button = ctk.CTkButton(
            footer,
            text=self._save_text,
            height=42,
            corner_radius=9,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            command=self._submit,
        )
        self.save_button.grid(row=0, column=1, padx=(7, 0), sticky="ew")

    @property
    def _save_text(self) -> str:
        return "Lưu thay đổi" if self._editing else "Lưu sinh viên"

    def _fit_and_center(self) -> None:
        if not self.winfo_exists():
            return
        self.update_idletasks()
        max_height = max(520, self.winfo_screenheight() - 120)
        target_height = min(max(self.winfo_reqheight(), 560), max_height)
        target_width = min(max(self.winfo_reqwidth(), 520), 620)
        parent = self.master
        x = parent.winfo_rootx() + (parent.winfo_width() - target_width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - target_height) // 2
        y = min(max(y, 10), max(10, self.winfo_screenheight() - target_height - 80))
        self.geometry(f"{target_width}x{target_height}+{max(x, 0)}+{y}")

    def _clear_error(self, field: str) -> None:
        self._error_labels[field].configure(text="")
        self._entries[field].configure(border_color="#CBD5E1")

    def _set_error(self, field: str, message: str) -> None:
        self._error_labels[field].configure(text=message)
        self._entries[field].configure(border_color=COLORS["danger"])

    def _validate_form(self) -> tuple[dict[str, str], float] | None:
        for field in self._entries:
            self._clear_error(field)

        values = {field: entry.get().strip() for field, entry in self._entries.items()}
        labels = {
            "id": "Mã sinh viên",
            "name": "Họ và tên",
            "email": "Email",
            "major": "Chuyên ngành",
            "gpa": "GPA",
        }
        errors: dict[str, str] = {}
        for field, value in values.items():
            if not value:
                errors[field] = f"{labels[field]} không được để trống."

        if values["email"] and not EMAIL_PATTERN.fullmatch(values["email"]):
            errors["email"] = "Email không đúng định dạng."

        gpa = 0.0
        if values["gpa"]:
            try:
                gpa = float(values["gpa"])
            except ValueError:
                errors["gpa"] = "GPA phải là một số."
            else:
                if not math.isfinite(gpa) or not 0.0 <= gpa <= 4.0:
                    errors["gpa"] = "GPA phải nằm trong khoảng 0.0 đến 4.0."

        for field, message in errors.items():
            self._set_error(field, message)
        if errors:
            first_field = next(field for field in self._entries if field in errors)
            first_entry = self._entries[first_field]
            first_entry.focus_set()
            self.update_idletasks()
            content_height = max(self.form.winfo_reqheight(), 1)
            self.form._parent_canvas.yview_moveto(  # type: ignore[attr-defined]
                max(0.0, first_entry.winfo_y() / content_height - 0.05)
            )
            return None
        return values, gpa

    def _submit(self) -> None:
        if self._busy:
            return
        validated = self._validate_form()
        if validated is None:
            return
        values, gpa = validated
        student = student_pb2.Student(
            id=values["id"],
            name=values["name"],
            email=values["email"],
            major=values["major"],
            gpa=gpa,
        )
        self.set_busy(True)
        self._on_submit(student, self)

    def set_busy(self, busy: bool) -> None:
        if not self.winfo_exists():
            return
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.save_button.configure(state=state, text="Đang xử lý..." if busy else self._save_text)
        self.cancel_button.configure(state=state)

    def _close(self) -> None:
        if not self._busy and self.winfo_exists():
            self.grab_release()
            self.destroy()


class StudentManagementApp(ctk.CTk):
    """Dashboard bốn trang kết nối Student Service qua gateway thread-safe."""

    PAGE_TITLES = {
        "dashboard": ("Tổng quan", "Tổng hợp dữ liệu và hoạt động gần đây của hệ thống."),
        "students": ("Quản lý sinh viên", "Tìm kiếm và quản lý dữ liệu sinh viên qua gRPC."),
        "statistics": ("Thống kê & Báo cáo", "Phân tích chuyên ngành và kết quả học tập."),
        "monitor": ("Giám sát gRPC", "Theo dõi kết nối, độ trễ và lịch sử RPC theo thời gian thực."),
    }

    def __init__(self) -> None:
        super().__init__()
        self.title("Hệ thống quản lý sinh viên phân tán")
        self.geometry("1280x720")
        self.minsize(1080, 680)
        self.configure(fg_color=COLORS["background"])

        self._closing = False
        self._students: dict[str, student_pb2.Student] = {}
        self._displayed_students: dict[str, student_pb2.Student] = {}
        self._ui_queue: queue.Queue[tuple[Callable[..., None], tuple[Any, ...]]] = queue.Queue()
        self._view_generation = 0
        self._current_page = "dashboard"
        self._refresh_in_progress = False
        self._search_in_progress = False
        self._queue_after_id: Optional[str] = None
        self._telemetry_after_id: Optional[str] = None
        self.grpc_client = StudentGrpcClient()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self._configure_treeview_styles()
        self._build_sidebar()
        self._build_content_shell()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._show_page("dashboard")
        self._queue_after_id = self.after(50, self._drain_ui_queue)
        self._telemetry_after_id = self.after(250, self._telemetry_tick)
        self.after(150, self.refresh_students)

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=COLORS["sidebar"])
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(
            sidebar,
            text="STUDENT\nMANAGER",
            justify="left",
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=24, weight="bold"),
            text_color="#FFFFFF",
        ).grid(row=0, column=0, padx=22, pady=(28, 4), sticky="ew")
        ctk.CTkLabel(
            sidebar,
            text="Hệ thống quản lý phân tán",
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color="#BFDBFE",
        ).grid(row=1, column=0, padx=22, pady=(0, 24), sticky="ew")

        nav_items = [
            ("dashboard", "▦  Tổng quan"),
            ("students", "♟  Quản lý SV"),
            ("statistics", "▥  Thống kê"),
            ("monitor", "⌁  Giám sát gRPC"),
        ]
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for row, (page, text) in enumerate(nav_items, start=2):
            button = ctk.CTkButton(
                sidebar,
                text=text,
                height=42,
                corner_radius=8,
                anchor="w",
                fg_color="transparent",
                hover_color=COLORS["sidebar_hover"],
                font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
                command=lambda name=page: self._show_page(name),
            )
            button.grid(row=row, column=0, padx=14, pady=3, sticky="ew")
            self.nav_buttons[page] = button

        footer = ctk.CTkFrame(sidebar, fg_color="#0B315F", corner_radius=12)
        footer.grid(row=7, column=0, padx=14, pady=16, sticky="sew")
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            footer,
            text="TRẠNG THÁI SERVER",
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color="#93C5FD",
        ).grid(row=0, column=0, padx=14, pady=(12, 3), sticky="ew")
        self.status_label = ctk.CTkLabel(
            footer,
            text="●  Disconnected",
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color="#FCA5A5",
        )
        self.status_label.grid(row=1, column=0, padx=14, sticky="ew")
        ctk.CTkLabel(
            footer,
            text=self.grpc_client.address,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color="#BFDBFE",
        ).grid(row=2, column=0, padx=14, pady=(1, 9), sticky="ew")
        self.reconnect_button = ctk.CTkButton(
            footer,
            text="↻  Reconnect",
            height=34,
            corner_radius=7,
            fg_color=COLORS["sidebar_hover"],
            hover_color="#1E5FA9",
            command=self.reconnect,
        )
        self.reconnect_button.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")

    def _build_content_shell(self) -> None:
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, padx=24, pady=20, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.pages: dict[str, ctk.CTkFrame] = {}
        self.pages["dashboard"] = self._build_dashboard_page()
        self.pages["students"] = self._build_students_page()
        self.pages["statistics"] = self._build_statistics_page()
        self.pages["monitor"] = self._build_monitor_page()
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _page_frame(self, name: str) -> tuple[ctk.CTkFrame, ctk.CTkFrame]:
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        title, subtitle = self.PAGE_TITLES[name]
        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, pady=(0, 15), sticky="ew")
        ctk.CTkLabel(
            header,
            text=title,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=27, weight="bold"),
            text_color=COLORS["text"],
        ).pack(fill="x")
        ctk.CTkLabel(
            header,
            text=subtitle,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color=COLORS["text_muted"],
        ).pack(fill="x", pady=(1, 0))
        body = ctk.CTkFrame(page, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        return page, body

    def _build_dashboard_page(self) -> ctk.CTkFrame:
        page, body = self._page_frame("dashboard")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        stats = ctk.CTkFrame(body, fg_color="transparent")
        stats.grid(row=0, column=0, pady=(0, 15), sticky="ew")
        stats.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="dashboard_cards")
        self.dashboard_values: dict[str, ctk.CTkLabel] = {}
        cards = [
            ("total", "TỔNG SINH VIÊN", "0", COLORS["primary"]),
            ("average", "GPA TRUNG BÌNH", "—", "#7C3AED"),
            ("majors", "CHUYÊN NGÀNH", "0", COLORS["warning"]),
            ("connection", "TRẠNG THÁI gRPC", "Offline", COLORS["danger"]),
        ]
        for column, (key, label, value, color) in enumerate(cards):
            card = self._stat_card(stats, label, value, color)
            card.grid(row=0, column=column, padx=(0 if column == 0 else 6, 0 if column == 3 else 6), sticky="nsew")
            self.dashboard_values[key] = card.value_label  # type: ignore[attr-defined]

        activity = self._surface_card(body)
        activity.grid(row=1, column=0, sticky="nsew")
        activity.grid_columnconfigure(0, weight=1)
        activity.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            activity,
            text="Hoạt động gần đây",
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=17, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, padx=18, pady=(15, 10), sticky="ew")
        self.recent_tree = self._create_history_tree(activity, "Recent.Treeview")
        self.recent_tree.grid(row=1, column=0, padx=18, pady=(0, 16), sticky="nsew")
        self.recent_empty = ctk.CTkLabel(
            activity,
            text="Chưa có hoạt động RPC.\nDữ liệu sẽ xuất hiện sau khi kết nối server.",
            justify="center",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14),
            text_color=COLORS["text_muted"],
        )
        return page

    def _build_students_page(self) -> ctk.CTkFrame:
        page, body = self._page_frame("students")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        toolbar = self._surface_card(body)
        toolbar.grid(row=0, column=0, pady=(0, 12), sticky="ew")
        toolbar.grid_columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(
            toolbar,
            height=38,
            placeholder_text="Tìm theo mã sinh viên...",
            border_color="#CBD5E1",
            fg_color="#F8FAFC",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
        )
        self.search_entry.grid(row=0, column=0, padx=(14, 7), pady=13, sticky="ew")
        self.search_entry.bind("<Return>", lambda _event: self.search_student())
        self.search_button = self._toolbar_button(toolbar, "Tìm", self.search_student, 80)
        self.search_button.grid(row=0, column=1, padx=4)
        self.refresh_button = self._toolbar_button(toolbar, "↻ Refresh", self.show_all_students, 92, muted=True)
        self.refresh_button.grid(row=0, column=2, padx=4)
        self.add_button = self._toolbar_button(toolbar, "+ Add", self.open_add_dialog, 78)
        self.add_button.grid(row=0, column=3, padx=4)
        self.edit_button = self._toolbar_button(toolbar, "Edit", self.open_edit_dialog, 72, muted=True)
        self.edit_button.configure(state="disabled")
        self.edit_button.grid(row=0, column=4, padx=4)
        self.delete_button = self._toolbar_button(toolbar, "Delete", self.delete_selected_student, 78, danger=True)
        self.delete_button.configure(state="disabled")
        self.delete_button.grid(row=0, column=5, padx=(4, 14))

        table_card = self._surface_card(body)
        table_card.grid(row=1, column=0, sticky="nsew")
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(1, weight=1)
        self.student_count_label = ctk.CTkLabel(
            table_card,
            text="Danh sách sinh viên · 0 bản ghi",
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            text_color=COLORS["text"],
        )
        self.student_count_label.grid(row=0, column=0, padx=18, pady=(14, 10), sticky="ew")

        tree_frame = ctk.CTkFrame(table_card, fg_color="transparent")
        tree_frame.grid(row=1, column=0, padx=18, pady=(0, 16), sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        columns = ("id", "name", "email", "major", "gpa")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            style="Students.Treeview",
            selectmode="browse",
        )
        headings = {"id": "Mã SV", "name": "Họ tên", "email": "Email", "major": "Chuyên ngành", "gpa": "GPA"}
        widths = {"id": 100, "name": 175, "email": 210, "major": 170, "gpa": 65}
        for column in columns:
            self.tree.heading(column, text=headings[column], anchor="w")
            self.tree.column(
                column,
                width=widths[column],
                minwidth=55,
                stretch=column not in ("id", "gpa"),
                anchor="center" if column == "gpa" else "w",
            )
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_selection)
        self.tree.bind("<Double-1>", lambda _event: self.open_edit_dialog())
        return page

    def _build_statistics_page(self) -> ctk.CTkFrame:
        page, body = self._page_frame("statistics")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        chart_card = self._surface_card(body)
        chart_card.grid(row=0, column=0, sticky="nsew")
        chart_card.grid_rowconfigure(0, weight=1)
        chart_card.grid_columnconfigure(0, weight=1)

        self.figure = Figure(figsize=(9, 5), dpi=100, facecolor=COLORS["surface"])
        self.major_axis = self.figure.add_subplot(121)
        self.gpa_axis = self.figure.add_subplot(122)
        self.chart_canvas = FigureCanvasTkAgg(self.figure, master=chart_card)
        chart_widget = self.chart_canvas.get_tk_widget()
        chart_widget.configure(background=COLORS["surface"], highlightthickness=0)
        chart_widget.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")
        self._update_statistics()
        return page

    def _build_monitor_page(self) -> ctk.CTkFrame:
        page, body = self._page_frame("monitor")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        stats = ctk.CTkFrame(body, fg_color="transparent")
        stats.grid(row=0, column=0, pady=(0, 12), sticky="ew")
        stats.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="monitor_cards")
        self.monitor_values: dict[str, ctk.CTkLabel] = {}
        cards = [
            ("requests", "TỔNG REQUEST", "0", COLORS["primary"]),
            ("latency", "LATENCY GẦN NHẤT", "— ms", "#7C3AED"),
            ("success", "THÀNH CÔNG", "0", COLORS["success"]),
            ("failed", "THẤT BẠI", "0", COLORS["danger"]),
        ]
        for column, (key, label, value, color) in enumerate(cards):
            card = self._stat_card(stats, label, value, color, compact=True)
            card.grid(row=0, column=column, padx=(0 if column == 0 else 5, 0 if column == 3 else 5), sticky="nsew")
            self.monitor_values[key] = card.value_label  # type: ignore[attr-defined]

        history_card = self._surface_card(body)
        history_card.grid(row=1, column=0, pady=(0, 12), sticky="nsew")
        history_card.grid_columnconfigure(0, weight=1)
        history_card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            history_card,
            text="Lịch sử RPC",
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, padx=16, pady=(12, 7), sticky="ew")
        self.monitor_tree = self._create_history_tree(history_card, "Monitor.Treeview")
        self.monitor_tree.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")
        self.monitor_empty = ctk.CTkLabel(
            history_card,
            text="Chưa có RPC nào trong phiên làm việc này.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color=COLORS["text_muted"],
        )

        flow_card = self._surface_card(body)
        flow_card.grid(row=2, column=0, sticky="ew")
        flow_card.grid_columnconfigure((0, 2, 4, 6), weight=1, uniform="flow_nodes")
        nodes = [
            ("GUI Client", "CustomTkinter"),
            ("Worker + Queue", "Thread-safe UI"),
            ("gRPC Channel", self.grpc_client.address),
            ("Server + SQLite", "StudentService"),
        ]
        for index, (title, subtitle) in enumerate(nodes):
            column = index * 2
            node = ctk.CTkFrame(flow_card, fg_color="#EFF6FF", corner_radius=9, border_width=1, border_color="#BFDBFE")
            node.grid(row=0, column=column, padx=(12 if index == 0 else 4, 12 if index == 3 else 4), pady=10, sticky="ew")
            ctk.CTkLabel(node, text=title, font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"), text_color="#1E3A8A").pack(padx=8, pady=(7, 0))
            ctk.CTkLabel(node, text=subtitle, font=ctk.CTkFont(family=FONT_FAMILY, size=9), text_color=COLORS["text_muted"]).pack(padx=8, pady=(0, 7))
            if index < len(nodes) - 1:
                ctk.CTkLabel(flow_card, text="→", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLORS["primary"]).grid(row=0, column=column + 1)
        return page

    @staticmethod
    def _surface_card(parent: Any) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            fg_color=COLORS["surface"],
            corner_radius=13,
            border_width=1,
            border_color=COLORS["border"],
        )

    def _stat_card(
        self,
        parent: Any,
        label: str,
        value: str,
        color: str,
        compact: bool = False,
    ) -> ctk.CTkFrame:
        card = self._surface_card(parent)
        ctk.CTkLabel(
            card,
            text=label,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=COLORS["text_muted"],
        ).pack(fill="x", padx=15, pady=(12 if compact else 15, 1))
        value_label = ctk.CTkLabel(
            card,
            text=value,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=22 if compact else 27, weight="bold"),
            text_color=color,
        )
        value_label.pack(fill="x", padx=15, pady=(0, 11 if compact else 14))
        card.value_label = value_label  # type: ignore[attr-defined]
        return card

    @staticmethod
    def _toolbar_button(
        parent: Any,
        text: str,
        command: Callable[[], None],
        width: int,
        muted: bool = False,
        danger: bool = False,
    ) -> ctk.CTkButton:
        if danger:
            fg_color, hover_color, text_color = COLORS["danger"], COLORS["danger_hover"], "#FFFFFF"
        elif muted:
            fg_color, hover_color, text_color = COLORS["surface_muted"], "#CBD5E1", COLORS["text"]
        else:
            fg_color, hover_color, text_color = COLORS["primary"], COLORS["primary_hover"], "#FFFFFF"
        return ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=36,
            corner_radius=8,
            fg_color=fg_color,
            hover_color=hover_color,
            text_color=text_color,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            command=command,
        )

    @staticmethod
    def _create_history_tree(parent: Any, style: str) -> ttk.Treeview:
        tree = ttk.Treeview(
            parent,
            columns=("time", "method", "result", "status", "latency"),
            show="headings",
            style=style,
            selectmode="none",
            height=6,
        )
        config = [
            ("time", "Thời gian", 120, False),
            ("method", "RPC", 165, True),
            ("result", "Kết quả", 85, False),
            ("status", "Status", 120, True),
            ("latency", "Latency", 90, False),
        ]
        for column, heading, width, stretch in config:
            tree.heading(column, text=heading, anchor="w")
            tree.column(column, width=width, minwidth=60, stretch=stretch, anchor="w")
        return tree

    @staticmethod
    def _configure_treeview_styles() -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        for name, rowheight in (("Students.Treeview", 36), ("Recent.Treeview", 34), ("Monitor.Treeview", 32)):
            style.configure(
                name,
                background="#FFFFFF",
                fieldbackground="#FFFFFF",
                foreground=COLORS["text"],
                rowheight=rowheight,
                borderwidth=0,
                relief="flat",
                font=(FONT_FAMILY, 10),
            )
            style.configure(
                f"{name}.Heading",
                background="#EAF2FF",
                foreground="#1E3A5F",
                relief="flat",
                borderwidth=0,
                font=(FONT_FAMILY, 10, "bold"),
                padding=(7, 8),
            )
            style.map(name, background=[("selected", COLORS["primary"])], foreground=[("selected", "#FFFFFF")])
            style.map(f"{name}.Heading", background=[("active", "#DBEAFE")])

    def _show_page(self, page_name: str) -> None:
        if page_name not in self.pages:
            return
        self._current_page = page_name
        self.pages[page_name].tkraise()
        for name, button in self.nav_buttons.items():
            button.configure(fg_color=COLORS["sidebar_hover"] if name == page_name else "transparent")
        if page_name == "statistics":
            self._update_statistics()
        self._refresh_telemetry_views()

    def _run_rpc(
        self,
        worker: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Optional[Callable[[BaseException], None]] = None,
    ) -> None:
        """Chạy RPC ngoài Tk thread và chuyển callback về hàng đợi giao diện."""

        def task() -> None:
            try:
                result = worker()
            except BaseException as error:
                if not self._closing:
                    self._ui_queue.put((on_error or self._handle_rpc_error, (error,)))
            else:
                if not self._closing:
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
                if not self._closing:
                    messagebox.showerror("Lỗi giao diện", f"Không thể cập nhật giao diện: {error}", parent=self)
        self._queue_after_id = self.after(50, self._drain_ui_queue)

    def _telemetry_tick(self) -> None:
        if self._closing:
            return
        self._refresh_telemetry_views()
        self._telemetry_after_id = self.after(750, self._telemetry_tick)

    def _next_view_generation(self) -> int:
        self._view_generation += 1
        return self._view_generation

    def refresh_students(self) -> None:
        if self._refresh_in_progress:
            return
        self._refresh_in_progress = True
        generation = self._next_view_generation()
        self.refresh_button.configure(state="disabled", text="Đang tải...")

        def success(students: list[student_pb2.Student]) -> None:
            self._refresh_in_progress = False
            self.refresh_button.configure(state="normal", text="↻ Refresh")
            if generation != self._view_generation:
                return
            self._students = {student.id: student for student in students}
            self._render_students(students)
            self._sync_data_views()

        def failure(error: BaseException) -> None:
            self._refresh_in_progress = False
            self.refresh_button.configure(state="normal", text="↻ Refresh")
            if generation == self._view_generation:
                self._handle_rpc_error(error)

        self._run_rpc(self.grpc_client.list_students, success, failure)

    def search_student(self) -> None:
        if self._search_in_progress:
            return
        student_id = self.search_entry.get().strip()
        if not student_id:
            self.refresh_students()
            return
        self._search_in_progress = True
        generation = self._next_view_generation()
        self.search_button.configure(state="disabled", text="Đang tìm...")

        def success(student: student_pb2.Student) -> None:
            self._search_in_progress = False
            self.search_button.configure(state="normal", text="Tìm")
            if generation != self._view_generation:
                return
            self._render_students([student])
            self._refresh_telemetry_views()

        def failure(error: BaseException) -> None:
            self._search_in_progress = False
            self.search_button.configure(state="normal", text="Tìm")
            if generation == self._view_generation:
                self._handle_rpc_error(error)

        self._run_rpc(lambda: self.grpc_client.get_student(student_id), success, failure)

    def show_all_students(self) -> None:
        self.search_entry.delete(0, "end")
        self.refresh_students()

    def _render_students(self, students: list[student_pb2.Student]) -> None:
        self._displayed_students = {student.id: student for student in students}
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)
        for student in students:
            self.tree.insert(
                "",
                "end",
                iid=student.id,
                values=(student.id, student.name, student.email, student.major, f"{student.gpa:.2f}"),
            )
        self.student_count_label.configure(text=f"Danh sách sinh viên · {len(students)} bản ghi")
        self._on_tree_selection()

    def _selected_student(self) -> Optional[student_pb2.Student]:
        selected = self.tree.selection()
        if len(selected) != 1:
            return None
        return self._displayed_students.get(selected[0])

    def _on_tree_selection(self, _event: Any = None) -> None:
        state = "normal" if self._selected_student() is not None else "disabled"
        self.edit_button.configure(state=state)
        self.delete_button.configure(state=state)

    def open_add_dialog(self) -> None:
        StudentDialog(self, title="Thêm sinh viên", on_submit=self.create_student)

    def open_edit_dialog(self) -> None:
        student = self._selected_student()
        if student is None:
            messagebox.showinfo("Chưa chọn sinh viên", "Vui lòng chọn một sinh viên trong bảng để cập nhật.", parent=self)
            return
        StudentDialog(self, title="Cập nhật sinh viên", student=student, on_submit=self.update_student)

    def create_student(self, student: student_pb2.Student, dialog: StudentDialog) -> None:
        def success(created: student_pb2.Student) -> None:
            if dialog.winfo_exists():
                dialog.set_busy(False)
                dialog.destroy()
            messagebox.showinfo("Thành công", f"Đã thêm sinh viên '{created.id}'.", parent=self)
            self.refresh_students()

        def failure(error: BaseException) -> None:
            if dialog.winfo_exists():
                dialog.set_busy(False)
            self._handle_rpc_error(error, parent=dialog if dialog.winfo_exists() else self)

        self._run_rpc(lambda: self.grpc_client.create_student(student), success, failure)

    def update_student(self, student: student_pb2.Student, dialog: StudentDialog) -> None:
        def success(updated: student_pb2.Student) -> None:
            if dialog.winfo_exists():
                dialog.set_busy(False)
                dialog.destroy()
            messagebox.showinfo("Thành công", f"Đã cập nhật sinh viên '{updated.id}'.", parent=self)
            self.refresh_students()

        def failure(error: BaseException) -> None:
            if dialog.winfo_exists():
                dialog.set_busy(False)
            self._handle_rpc_error(error, parent=dialog if dialog.winfo_exists() else self)

        self._run_rpc(lambda: self.grpc_client.update_student(student), success, failure)

    def delete_selected_student(self) -> None:
        student = self._selected_student()
        if student is None:
            messagebox.showinfo("Chưa chọn sinh viên", "Vui lòng chọn một sinh viên trong bảng để xóa.", parent=self)
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

        def success(response: student_pb2.DeleteStudentResponse) -> None:
            self.delete_button.configure(state="disabled", text="Delete")
            messagebox.showinfo("Thành công", response.message, parent=self)
            self.refresh_students()

        def failure(error: BaseException) -> None:
            self.delete_button.configure(state="normal", text="Delete")
            self._handle_rpc_error(error)

        self._run_rpc(lambda: self.grpc_client.delete_student(student.id), success, failure)

    def reconnect(self) -> None:
        self.reconnect_button.configure(state="disabled", text="Đang kết nối...")

        def success(connected: bool) -> None:
            self.reconnect_button.configure(state="normal", text="↻  Reconnect")
            self._refresh_telemetry_views()
            if connected:
                self.refresh_students()
            else:
                messagebox.showerror(
                    "Không thể kết nối",
                    f"Không thể kết nối đến gRPC Server tại {self.grpc_client.address}.",
                    parent=self,
                )

        def failure(error: BaseException) -> None:
            self.reconnect_button.configure(state="normal", text="↻  Reconnect")
            self._handle_rpc_error(error)

        self._run_rpc(self.grpc_client.reconnect, success, failure)

    def _sync_data_views(self) -> None:
        students = list(self._students.values())
        average = sum(student.gpa for student in students) / len(students) if students else None
        majors = len({student.major.strip().casefold() for student in students if student.major.strip()})
        self.dashboard_values["total"].configure(text=str(len(students)))
        self.dashboard_values["average"].configure(text=f"{average:.2f}" if average is not None else "—")
        self.dashboard_values["majors"].configure(text=str(majors))
        self._update_statistics()
        self._refresh_telemetry_views()

    def _update_statistics(self) -> None:
        if not hasattr(self, "major_axis"):
            return
        students = list(self._students.values())
        self.major_axis.clear()
        self.gpa_axis.clear()
        self.major_axis.set_axis_on()
        self.gpa_axis.set_axis_on()
        if not students:
            for axis, title in ((self.major_axis, "Sinh viên theo chuyên ngành"), (self.gpa_axis, "Phân bố GPA")):
                axis.set_axis_off()
                axis.set_title(title, fontsize=12, fontweight="bold", color=COLORS["text"], pad=14)
                axis.text(0.5, 0.5, "Chưa có dữ liệu", ha="center", va="center", color=COLORS["text_muted"], fontsize=12, transform=axis.transAxes)
        else:
            majors = Counter(student.major.strip() or "Khác" for student in students)
            names = list(majors.keys())
            counts = list(majors.values())
            bars = self.major_axis.bar(names, counts, color="#3B82F6", width=0.65)
            self.major_axis.set_title("Sinh viên theo chuyên ngành", fontsize=12, fontweight="bold", color=COLORS["text"], pad=14)
            self.major_axis.set_ylabel("Số sinh viên", color=COLORS["text_muted"])
            self.major_axis.tick_params(axis="x", rotation=25, labelsize=8)
            self.major_axis.tick_params(axis="y", labelsize=8)
            self.major_axis.grid(axis="y", alpha=0.18)
            self.major_axis.spines[["top", "right"]].set_visible(False)
            self.major_axis.bar_label(bars, padding=2, fontsize=8)

            distribution = [0, 0, 0, 0]
            for student in students:
                distribution[min(max(int(student.gpa), 0), 3)] += 1
            labels = ["0–<1", "1–<2", "2–<3", "3–4"]
            colors = ["#F87171", "#FBBF24", "#60A5FA", "#34D399"]
            bars = self.gpa_axis.bar(labels, distribution, color=colors, width=0.65)
            self.gpa_axis.set_title("Phân bố GPA", fontsize=12, fontweight="bold", color=COLORS["text"], pad=14)
            self.gpa_axis.set_ylabel("Số sinh viên", color=COLORS["text_muted"])
            self.gpa_axis.tick_params(labelsize=8)
            self.gpa_axis.grid(axis="y", alpha=0.18)
            self.gpa_axis.spines[["top", "right"]].set_visible(False)
            self.gpa_axis.bar_label(bars, padding=2, fontsize=8)
        self.figure.tight_layout(pad=2.2)
        self.chart_canvas.draw_idle()

    def _refresh_telemetry_views(self) -> None:
        if self._closing:
            return
        snapshot = self.grpc_client.snapshot()
        self._set_connection_status(snapshot.connected)
        successes = sum(record.success for record in snapshot.history)
        failures = len(snapshot.history) - successes
        self.monitor_values["requests"].configure(text=str(snapshot.total_requests))
        self.monitor_values["latency"].configure(
            text=f"{snapshot.last_latency_ms:.1f} ms" if snapshot.last_latency_ms is not None else "— ms"
        )
        self.monitor_values["success"].configure(text=str(successes))
        self.monitor_values["failed"].configure(text=str(failures))
        self._render_history(self.monitor_tree, self.monitor_empty, snapshot, limit=100)
        self._render_history(self.recent_tree, self.recent_empty, snapshot, limit=8)

    def _set_connection_status(self, connected: bool) -> None:
        if connected:
            self.status_label.configure(text="●  Connected", text_color="#86EFAC")
            self.dashboard_values["connection"].configure(text="Online", text_color=COLORS["success"])
        else:
            self.status_label.configure(text="●  Disconnected", text_color="#FCA5A5")
            self.dashboard_values["connection"].configure(text="Offline", text_color=COLORS["danger"])

    @staticmethod
    def _render_history(
        tree: ttk.Treeview,
        empty_label: ctk.CTkLabel,
        snapshot: ConnectionSnapshot,
        limit: int,
    ) -> None:
        for item in tree.get_children():
            tree.delete(item)
        records = snapshot.history[:limit]
        if not records:
            tree.grid_remove()
            empty_label.grid(row=1, column=0, padx=18, pady=(12, 25), sticky="nsew")
            return
        empty_label.grid_remove()
        tree.grid()
        for index, record in enumerate(records):
            tree.insert(
                "",
                "end",
                iid=f"{record.timestamp.timestamp()}-{index}-{record.method}",
                values=(
                    record.timestamp.strftime("%H:%M:%S"),
                    record.method,
                    "Thành công" if record.success else "Thất bại",
                    record.status,
                    f"{record.latency_ms:.1f} ms",
                ),
            )

    def _handle_rpc_error(self, error: BaseException, parent: Optional[Any] = None) -> None:
        self._refresh_telemetry_views()
        parent = parent or self
        if not isinstance(error, grpc.RpcError):
            messagebox.showerror("Lỗi không xác định", f"Đã xảy ra lỗi: {error}", parent=parent)
            return
        code = error.code()
        details = error.details() or "Server không cung cấp thông tin chi tiết."
        if code == grpc.StatusCode.UNAVAILABLE:
            message = f"Không thể kết nối đến gRPC Server tại {self.grpc_client.address}. Vui lòng kiểm tra Server đang chạy."
        elif code == grpc.StatusCode.NOT_FOUND:
            message = f"Không tìm thấy dữ liệu.\n\n{details}"
        elif code == grpc.StatusCode.ALREADY_EXISTS:
            message = f"Mã sinh viên đã tồn tại.\n\n{details}"
        elif code == grpc.StatusCode.INVALID_ARGUMENT:
            message = f"Dữ liệu không hợp lệ.\n\n{details}"
        elif code == grpc.StatusCode.DEADLINE_EXCEEDED:
            message = "Yêu cầu đã quá thời gian chờ. Vui lòng thử lại."
        else:
            message = f"Lỗi gRPC [{code.name}]: {details}"
        messagebox.showerror("Lỗi gRPC", message, parent=parent)

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        for after_id in (self._queue_after_id, self._telemetry_after_id):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
        self.grpc_client.close()
        self.destroy()


def main() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = StudentManagementApp()
    app.mainloop()


if __name__ == "__main__":
    main()
