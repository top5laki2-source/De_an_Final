"""Kiem tra nhanh toan bo luong cua he thong (chay: python tests_smoke.py).

Script nay dung test client cua Flask nen khong can khoi dong server.
"""
import os
import shutil
import sys
import tempfile
from datetime import date, datetime
from io import BytesIO
from uuid import uuid4

from app import create_app
from extensions import db
from models import (
    AttendanceRecord,
    ClassRoom,
    Enrollment,
    Homework,
    HomeworkSubmission,
    ScoreRecord,
    StudentProfile,
    User,
    ielts_round,
)

app = create_app()
FAILED = []


def check(label, condition, detail=""):
    status = "OK  " if condition else "LỖI "
    print(f"[{status}] {label}{(' — ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILED.append(label)


def login(client, username, password="123456"):
    return client.post(
        "/dang-nhap", data={"username": username, "password": password}, follow_redirects=True
    )


def get(client, url, expect=200):
    response = client.get(url)
    check(f"GET {url} -> {response.status_code}", response.status_code == expect,
          f"mong đợi {expect}")
    return response


def test_homework_workflow(class_id, another_class_id):
    original_upload_dir = app.config["HOMEWORK_UPLOAD_DIR"]
    upload_dir = tempfile.mkdtemp(prefix="homework-smoke-")
    app.config["HOMEWORK_UPLOAD_DIR"] = upload_dir
    homework_id = None
    try:
        with app.app_context():
            student = StudentProfile.query.join(User).filter(User.username == "hv.an").first()
            enrollment = Enrollment.query.filter_by(
                student_id=student.id, class_id=class_id
            ).first()
            check("Tài khoản kiểm thử có ghi danh lớp giao bài", enrollment is not None)
            enrollment_id = enrollment.id
            other_enrollment = Enrollment.query.filter_by(
                class_id=another_class_id, status="studying"
            ).first()
            other_student_username = other_enrollment.student.user.username

        with app.test_client() as teacher_client:
            login(teacher_client, "gv.mai")
            response = teacher_client.get("/giao-vien/bai-tap")
            check("Giáo viên mở trang bài tập về nhà",
                  response.status_code == 200 and "Giao bài tập mới" in response.get_data(as_text=True))
            response = teacher_client.post(
                "/giao-vien/bai-tap/tao",
                data={
                    "class_id": str(class_id),
                    "title": "Bài tập smoke test",
                    "instructions": "Hoàn thành bài tập và tải tệp lên.",
                    "deadline": "2000-01-01T10:00",
                    "materials": (BytesIO(b"homework brief"), "de-bai.pdf"),
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            check("Giáo viên giao bài kèm tài liệu",
                  "Bài tập smoke test" in response.get_data(as_text=True))
            with app.app_context():
                homework = Homework.query.filter_by(title="Bài tập smoke test").first()
                homework_id = homework.id
                material_id = homework.materials[0].id
                original_stored_filename = homework.materials[0].stored_filename
            get(teacher_client, f"/giao-vien/bai-tap/{homework_id}")
            response = teacher_client.get(
                f"/giao-vien/bai-tap/{homework_id}/tai-tai-lieu/{material_id}"
            )
            check("Giáo viên tải được tài liệu đã giao",
                  response.status_code == 200 and response.data == b"homework brief")
            get(teacher_client, f"/giao-vien/bai-tap/{homework_id}/tai-bai-nop/999999",
                expect=404)

        with app.test_client() as student_client:
            login(student_client, "hv.an")
            response = get(student_client, "/hoc-vien/bai-tap")
            check("Học viên nhìn thấy bài được giao",
                  "Bài tập smoke test" in response.get_data(as_text=True))
            get(student_client, f"/hoc-vien/bai-tap/{homework_id}")
            response = student_client.get(
                f"/hoc-vien/bai-tap/{homework_id}/tai-tai-lieu/{material_id}"
            )
            check("Học viên tải được tài liệu bài tập",
                  response.status_code == 200 and response.data == b"homework brief")
            response = student_client.post(
                f"/hoc-vien/bai-tap/{homework_id}/nop",
                data={"files": (BytesIO(b"late homework"), "bai-lam.docx")},
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            check("Học viên được nộp bài quá hạn và được báo nộp muộn",
                  "nộp muộn" in response.get_data(as_text=True).lower())
            with app.app_context():
                submission = HomeworkSubmission.query.filter_by(
                    homework_id=homework_id, enrollment_id=enrollment_id
                ).first()
                check("Lưu trạng thái nộp muộn vào dữ liệu",
                      submission is not None and submission.is_late)
                submitted_file_id = submission.files[0].id
                homework = db.session.get(Homework, homework_id)
                homework.deadline = datetime(2099, 12, 31, 23, 59)
                db.session.commit()
            response = student_client.post(
                f"/hoc-vien/bai-tap/{homework_id}/nop",
                data={"files": (BytesIO(b"on-time homework"), "bai-lam-dung-han.docx")},
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            check("Học viên nộp trước hạn được ghi nhận đúng hạn",
                  "Đã nộp bài tập thành công" in response.get_data(as_text=True))
            with app.app_context():
                submissions = HomeworkSubmission.query.filter_by(
                    homework_id=homework_id, enrollment_id=enrollment_id
                ).all()
                check("Lưu riêng trạng thái đúng hạn và nộp muộn",
                      len(submissions) == 2
                      and {submission.is_late for submission in submissions} == {True, False})

        with app.test_client() as other_teacher_client:
            login(other_teacher_client, "gv.lan")
            get(other_teacher_client, f"/giao-vien/bai-tap/{homework_id}/sua", expect=404)

        with app.test_client() as teacher_client:
            login(teacher_client, "gv.mai")
            response = get(teacher_client, f"/giao-vien/bai-tap/{homework_id}/sua")
            check("Trang sửa hiển thị thông tin và tài liệu hiện tại",
                  "Hoàn thành bài tập và tải tệp lên." in response.get_data(as_text=True)
                  and "de-bai.pdf" in response.get_data(as_text=True))
            response = teacher_client.post(
                f"/giao-vien/bai-tap/{homework_id}/sua",
                data={
                    "title": "Bài tập smoke test đã sửa",
                    "instructions": "Yêu cầu đã bổ sung.\nHoàn thành và tải tệp lên.",
                    "deadline": "2099-12-31T23:59",
                    "remove_materials": str(material_id),
                    "materials": (BytesIO(b"additional reference"), "tai-lieu-bo-sung.pdf"),
                },
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            check("Giáo viên cập nhật đề và thay tài liệu đã giao",
                  "Đã cập nhật bài tập." in response.get_data(as_text=True)
                  and "Bài tập smoke test đã sửa" in response.get_data(as_text=True))
            with app.app_context():
                homework = db.session.get(Homework, homework_id)
                updated_materials = list(homework.materials)
                check("Lưu yêu cầu mới và chỉ giữ tài liệu mới",
                      homework.instructions == "Yêu cầu đã bổ sung.\nHoàn thành và tải tệp lên."
                      and len(updated_materials) == 1
                      and updated_materials[0].original_filename == "tai-lieu-bo-sung.pdf")
                updated_material_id = updated_materials[0].id
            check("Tệp tài liệu đã gỡ được xóa khỏi kho lưu trữ",
                  not os.path.exists(os.path.join(upload_dir, original_stored_filename)))
            response = teacher_client.get(
                f"/giao-vien/bai-tap/{homework_id}/tai-tai-lieu/{updated_material_id}"
            )
            check("Giáo viên tải được tài liệu vừa thêm",
                  response.status_code == 200 and response.data == b"additional reference")
            get(teacher_client,
                f"/giao-vien/bai-tap/{homework_id}/tai-tai-lieu/{material_id}",
                expect=404)
            response = get(teacher_client, f"/giao-vien/bai-tap/{homework_id}")
            teacher_html = response.get_data(as_text=True)
            check("Giáo viên theo dõi bài nộp muộn",
                  "Nộp muộn" in teacher_html and "Đúng hạn" in teacher_html
                  and "bai-lam.docx" in teacher_html
                  and "bai-lam-dung-han.docx" in teacher_html)
            response = teacher_client.get(
                f"/giao-vien/bai-tap/{homework_id}/tai-bai-nop/{submitted_file_id}"
            )
            check("Giáo viên tải được bài học viên đã nộp",
                  response.status_code == 200 and response.data == b"late homework")
            get(teacher_client, f"/giao-vien/bai-tap/{homework_id}/tai-tai-lieu/999999",
                expect=404)

        with app.test_client() as updated_student_client:
            login(updated_student_client, "hv.an")
            response = get(updated_student_client, f"/hoc-vien/bai-tap/{homework_id}")
            student_html = response.get_data(as_text=True)
            check("Học viên nhìn thấy đề và tài liệu đã cập nhật",
                  "Yêu cầu đã bổ sung." in student_html
                  and "tai-lieu-bo-sung.pdf" in student_html)
            response = updated_student_client.get(
                f"/hoc-vien/bai-tap/{homework_id}/tai-tai-lieu/{updated_material_id}"
            )
            check("Học viên tải được tài liệu vừa bổ sung",
                  response.status_code == 200 and response.data == b"additional reference")
            get(updated_student_client,
                f"/hoc-vien/bai-tap/{homework_id}/tai-tai-lieu/{material_id}",
                expect=404)

        with app.test_client() as student_client:
            login(student_client, "hv.an")
            response = student_client.get(
                f"/hoc-vien/bai-tap/{homework_id}/tai-bai-nop/{submitted_file_id}"
            )
            check("Học viên tải lại được bài đã nộp",
                  response.status_code == 200 and response.data == b"late homework")
            response = student_client.post(
                f"/hoc-vien/bai-tap/{homework_id}/nop",
                data={"files": (BytesIO(b"bad type"), "payload.exe")},
                content_type="multipart/form-data",
                follow_redirects=True,
            )
            check("Từ chối định dạng tệp không được hỗ trợ",
                  "chưa được hỗ trợ" in response.get_data(as_text=True))
            original_max_content_length = app.config["MAX_CONTENT_LENGTH"]
            app.config["MAX_CONTENT_LENGTH"] = 128
            response = student_client.post(
                f"/hoc-vien/bai-tap/{homework_id}/nop",
                data={"files": (BytesIO(b"x" * 512), "too-large.pdf")},
                content_type="multipart/form-data",
            )
            check("Tệp vượt giới hạn được báo lỗi 413 rõ ràng",
                  response.status_code == 413
                  and "Tệp tải lên quá lớn" in response.get_data(as_text=True))
            app.config["MAX_CONTENT_LENGTH"] = original_max_content_length

        with app.test_client() as other_student_client:
            login(other_student_client, other_student_username)
            get(other_student_client, f"/hoc-vien/bai-tap/{homework_id}", expect=404)
    finally:
        if homework_id is not None:
            with app.app_context():
                homework = db.session.get(Homework, homework_id)
                if homework is not None:
                    db.session.delete(homework)
                    db.session.commit()
        app.config["HOMEWORK_UPLOAD_DIR"] = original_upload_dir
        shutil.rmtree(upload_dir)


def main():
    print("\n=== 1. Quy tac lam tron band IELTS ===")
    cases = [(6.0, 6.0), (6.125, 6.0), (6.25, 6.5), (6.5, 6.5), (6.625, 6.5), (6.75, 7.0), (5.875, 6.0)]
    for raw, expected in cases:
        check(f"ielts_round({raw}) = {expected}", ielts_round(raw) == expected,
              f"nhận {ielts_round(raw)}")

    with app.app_context():
        admin_class = ClassRoom.query.filter_by(code="IELTS-A1").first()
        a2_class = ClassRoom.query.filter_by(code="IELTS-A2").first()
        student = StudentProfile.query.join(User).filter(User.username == "hv.an").first()
        class_a1_id, class_a2_id, student_id = admin_class.id, a2_class.id, student.id
        seeded_classes = ClassRoom.query.order_by(ClassRoom.code).all()
        roster_sizes = [classroom.current_size for classroom in seeded_classes]
        start_dates = [classroom.start_date for classroom in seeded_classes]
        attendance_by_class = {
            classroom.id: AttendanceRecord.query.join(Enrollment)
            .filter(
                Enrollment.class_id == classroom.id,
                AttendanceRecord.attendance_date >= date(2026, 6, 1),
                AttendanceRecord.attendance_date <= date(2026, 11, 10),
            )
            .count()
            for classroom in seeded_classes
        }

    check("Dữ liệu mẫu có 7-9 học viên trong mỗi lớp",
          len(roster_sizes) == 4 and all(7 <= size <= 9 for size in roster_sizes))
    check("Ngày khai giảng rải trong các tháng giữa năm 2026",
          all(start_date and start_date.year == 2026 for start_date in start_dates)
          and all(6 <= start_date.month <= 10 for start_date in start_dates)
          and len({start_date.month for start_date in start_dates}) >= 4)
    check("Mỗi lớp có lịch sử điểm danh đến tháng 11/2026",
          bool(attendance_by_class)
          and all(record_count > 0 for record_count in attendance_by_class.values()))

    print("\n=== 2. Bao ve route khi chua dang nhap ===")
    with app.test_client() as client:
        for url in ["/quan-tri/", "/giao-vien/", "/hoc-vien/"]:
            response = client.get(url)
            check(f"Chưa đăng nhập, {url} bị chuyển hướng", response.status_code == 302)

    print("\n=== 3. Vai tro Quan tri vien ===")
    with app.test_client() as client:
        response = login(client, "admin")
        check("Đăng nhập admin", "Tổng quan hệ thống" in response.get_data(as_text=True))
        for url in [
            "/quan-tri/", "/quan-tri/khoa-hoc", "/quan-tri/khoa-hoc/them",
            "/quan-tri/lop-hoc", "/quan-tri/lop-hoc/them", f"/quan-tri/lop-hoc/{class_a1_id}",
            "/quan-tri/giao-vien", "/quan-tri/giao-vien/them",
            "/quan-tri/hoc-vien", "/quan-tri/hoc-vien/them", f"/quan-tri/hoc-vien/{student_id}",
            "/quan-tri/diem-danh", "/quan-tri/tai-khoan", "/quan-tri/tai-khoan/them",
            "/quan-tri/ket-qua",
            "/doi-mat-khau",
        ]:
            get(client, url)

        with app.app_context():
            test_user = User(
                username=f"smoke-{uuid4().hex}",
                full_name="Smoke Password Reset",
                role="student",
            )
            test_user.set_password("original-password")
            db.session.add(test_user)
            db.session.commit()
            test_user_id = test_user.id
            test_username = test_user.username
        try:
            response = client.post(
                f"/quan-tri/tai-khoan/{test_user_id}/dat-lai-mat-khau",
                data={"new_password": "1234567"},
                follow_redirects=True,
            )
            response_text = response.get_data(as_text=True)
            with app.app_context():
                test_user = db.session.get(User, test_user_id)
                check("Đặt lại mật khẩu lưu giá trị mới",
                      test_user.check_password("1234567"))
            check("Thông báo đặt lại không làm lộ mật khẩu",
                  f"Đã đặt lại mật khẩu cho {test_username}." in response_text
                  and "1234567" not in response_text)
            check("Trang tài khoản không nhầm placeholder với mật khẩu hiện tại",
                  "Mật khẩu hiện tại không được hiển thị" in response_text
                  and 'placeholder="Mật khẩu mới"' in response_text
                  and 'placeholder="123456"' not in response_text)
        finally:
            with app.app_context():
                test_user = db.session.get(User, test_user_id)
                db.session.delete(test_user)
                db.session.commit()

        with app.app_context():
            enrollment_to_remove = (
                Enrollment.query.filter_by(class_id=class_a1_id, status="studying").first()
            )
            removed_enrollment_id = enrollment_to_remove.id
            removed_student_name = enrollment_to_remove.student.full_name
            original_enrollment_status = enrollment_to_remove.status
            original_score_count = len(enrollment_to_remove.scores)
        response = client.post(
            f"/quan-tri/lop-hoc/{class_a1_id}/hoc-vien/{removed_enrollment_id}/xoa",
            follow_redirects=True,
        )
        with app.app_context():
            removed_enrollment = db.session.get(Enrollment, removed_enrollment_id)
            check("Xóa học viên khỏi lớp nhưng giữ lịch sử điểm",
                  removed_enrollment.status == "stopped"
                  and len(removed_enrollment.scores) == original_score_count)
            check("Học viên đã xóa không còn trong danh sách lớp",
                  f"/hoc-vien/{removed_enrollment_id}/xoa"
                  not in response.get_data(as_text=True))

        with app.test_client() as teacher_client:
            login(teacher_client, "gv.mai")
            teacher_response = teacher_client.get(f"/giao-vien/lop/{class_a1_id}")
            check("Học viên đã xóa không còn trong danh sách giáo viên",
                  removed_student_name not in teacher_response.get_data(as_text=True))

        with app.app_context():
            removed_enrollment = db.session.get(Enrollment, removed_enrollment_id)
            removed_enrollment.status = original_enrollment_status
            db.session.commit()

        # Tao khoa hoc moi
        response = client.post(
            "/quan-tri/khoa-hoc/them",
            data={"code": "TEST01", "name": "Khóa kiểm thử", "entry_band": "4.0",
                  "target_band": "5.5", "sessions": "20", "tuition": "3000000", "is_open": "on"},
            follow_redirects=True,
        )
        check("Tạo khóa học mới", "TEST01" in response.get_data(as_text=True))

        # Rang buoc: band muc tieu phai cao hon band dau vao
        response = client.post(
            "/quan-tri/khoa-hoc/them",
            data={"code": "TEST02", "name": "Khóa sai", "entry_band": "6.0",
                  "target_band": "5.0", "sessions": "20", "tuition": "0"},
            follow_redirects=True,
        )
        check("Chặn band mục tiêu <= band đầu vào",
              "phải cao hơn" in response.get_data(as_text=True))

        # Rang buoc: trung gio voi chinh buoi hoc khac cua lop
        response = client.post(
            f"/quan-tri/lop-hoc/{class_a1_id}/lich/them",
            data={"weekday": "0", "start_time": "18:30", "end_time": "20:30"},
            follow_redirects=True,
        )
        check("Chặn xếp lịch trùng giờ trong cùng lớp",
              "trùng giờ" in response.get_data(as_text=True))

        # Rang buoc: gio ket thuc phai sau gio bat dau
        response = client.post(
            f"/quan-tri/lop-hoc/{class_a1_id}/lich/them",
            data={"weekday": "3", "start_time": "20:00", "end_time": "18:00"},
            follow_redirects=True,
        )
        check("Chặn giờ kết thúc trước giờ bắt đầu",
              "phải sau giờ bắt đầu" in response.get_data(as_text=True))

        # Rang buoc: trung lich giao vien giua hai lop khac nhau
        with app.app_context():
            b1 = ClassRoom.query.filter_by(code="IELTS-B1").first()
            a2 = ClassRoom.query.filter_by(code="IELTS-A2").first()
            b1_id, a2_teacher_id, b1_course_id = b1.id, a2.teacher_id, b1.course_id
        client.post(
            f"/quan-tri/lop-hoc/{b1_id}/sua",
            data={"code": "IELTS-B1", "course_id": str(b1_course_id),
                  "teacher_id": str(a2_teacher_id), "room": "P.301",
                  "max_size": "12", "status": "open"},
            follow_redirects=True,
        )
        response = client.post(
            f"/quan-tri/lop-hoc/{b1_id}/lich/them",
            data={"weekday": "1", "start_time": "18:00", "end_time": "19:30"},
            follow_redirects=True,
        )
        check("Chặn xếp lịch trùng giáo viên giữa hai lớp",
              "đã có lịch dạy lớp" in response.get_data(as_text=True))

        # Rang buoc: trung phong hoc giua hai lop khac nhau
        client.post(
            f"/quan-tri/lop-hoc/{b1_id}/sua",
            data={"code": "IELTS-B1", "course_id": str(b1_course_id),
                  "teacher_id": "", "room": "P.202",
                  "max_size": "12", "status": "open"},
            follow_redirects=True,
        )
        response = client.post(
            f"/quan-tri/lop-hoc/{b1_id}/lich/them",
            data={"weekday": "3", "start_time": "19:00", "end_time": "21:00"},
            follow_redirects=True,
        )
        check("Chặn xếp lịch trùng phòng học giữa hai lớp",
              "đã được lớp" in response.get_data(as_text=True))

        # Rang buoc: hoc vien chua du band dau vao thi khong xep duoc lop nang cao
        with app.app_context():
            adv_class = ClassRoom.query.filter_by(code="IELTS-B1").first()
            adv_id = adv_class.id
        response = client.post(
            f"/quan-tri/hoc-vien/{student_id}/ghi-danh",
            data={"class_id": str(adv_id)}, follow_redirects=True,
        )
        check("Chặn xếp lớp khi band đầu vào chưa đạt",
              "thấp hơn yêu cầu" in response.get_data(as_text=True))

    print("\n=== 4. Vai tro Giao vien ===")
    with app.test_client() as client:
        response = login(client, "gv.mai")
        check("Đăng nhập giáo viên", "Lớp được phân công" in response.get_data(as_text=True))
        get(client, "/giao-vien/")
        get(client, "/giao-vien/lich-day")
        teacher_attendance = get(client, "/giao-vien/diem-danh?month=2099-12")
        teacher_attendance_html = teacher_attendance.get_data(as_text=True)
        check("Lịch sử giáo viên là bảng theo ngày trong tháng",
              "attendance-matrix" in teacher_attendance_html
              and ">31</th>" in teacher_attendance_html)
        class_response = get(client, f"/giao-vien/lop/{class_a1_id}")
        class_html = class_response.get_data(as_text=True)
        check("Trang lớp không còn nút điểm danh",
              f'href="/giao-vien/lop/{class_a1_id}/diem-danh"' not in class_html)
        check("Bảng tiến độ có Overall giữa khóa và cuối khóa",
              "Overall giữa khóa" in class_html and "Overall cuối khóa" in class_html)
        with app.app_context():
            detail_enrollment = Enrollment.query.filter_by(
                class_id=class_a1_id, status="studying"
            ).first()
            other_class_enrollment = Enrollment.query.filter_by(
                class_id=class_a2_id, status="studying"
            ).first()
            detail_enrollment_id = detail_enrollment.id
            other_class_enrollment_id = other_class_enrollment.id
            detail_student_name = detail_enrollment.student.full_name
        detail_response = get(
            client,
            f"/giao-vien/lop/{class_a1_id}/hoc-vien/{detail_enrollment_id}",
        )
        detail_html = detail_response.get_data(as_text=True)
        check("Tên học viên mở trang điểm chi tiết",
              detail_student_name in detail_html
              and "Chi tiết điểm theo giai đoạn" in detail_html)
        check("Trang chi tiết có điểm theo giai đoạn và kỹ năng",
              all(term in detail_html for term in ("Giữa khóa", "Cuối khóa", "Listening")))
        get(client, f"/giao-vien/lop/{class_a1_id}/hoc-vien/{other_class_enrollment_id}",
            expect=404)
        get(client, f"/giao-vien/lop/{class_a1_id}/nhap-diem")
        response = get(client, f"/giao-vien/lop/{class_a1_id}/xuat-bang-diem")
        check("Xuất bảng điểm trả về CSV", "text/csv" in response.headers.get("Content-Type", ""))

        attendance_date = date(2099, 12, 31)
        with app.app_context():
            attendance_enrollments = Enrollment.query.filter_by(
                class_id=class_a1_id, status="studying"
            ).all()
            attendance_enrollment_ids = [
                enrollment.id for enrollment in attendance_enrollments
            ]
            attendance_student_id = attendance_enrollments[0].student_id
            AttendanceRecord.query.filter(
                AttendanceRecord.enrollment_id.in_(attendance_enrollment_ids),
                AttendanceRecord.attendance_date == attendance_date,
            ).delete(synchronize_session=False)
            db.session.commit()
        attendance_statuses = ["present", "absent", "late"]
        attendance_data = {"date": attendance_date.isoformat()}
        for index, enrollment_id in enumerate(attendance_enrollment_ids):
            attendance_data[f"status_{enrollment_id}"] = attendance_statuses[
                index % len(attendance_statuses)
            ]
        attendance_response = client.post(
            f"/giao-vien/lop/{class_a1_id}/diem-danh",
            data=attendance_data,
            follow_redirects=True,
        )
        check("Giáo viên ghi nhận điểm danh theo ngày",
              "Đã lưu điểm danh" in attendance_response.get_data(as_text=True))
        with app.app_context():
            saved_attendance = AttendanceRecord.query.filter(
                AttendanceRecord.enrollment_id.in_(attendance_enrollment_ids),
                AttendanceRecord.attendance_date == attendance_date,
            ).all()
            check("Lưu trạng thái có mặt, vắng và đến muộn",
                  len(saved_attendance) == len(attendance_enrollment_ids)
                  and {record.status for record in saved_attendance}
                  == set(attendance_statuses))
        matrix_response = client.get(
            f"/giao-vien/diem-danh?class_id={class_a1_id}&month=2099-12"
        )
        matrix_html = matrix_response.get_data(as_text=True)
        check("Bảng giáo viên tô màu ô có mặt và vắng",
              matrix_response.status_code == 200
              and "attendance-present" in matrix_html
              and "attendance-absent" in matrix_html)
        # Khong duoc mo lop cua giao vien khac
        response = client.get(f"/giao-vien/lop/{class_a2_id}", follow_redirects=True)
        check("Chặn giáo viên mở lớp không phụ trách",
              "không được phân công" in response.get_data(as_text=True))

        # Khong duoc vao khu vuc quan tri
        response = client.get("/quan-tri/")
        check("Giáo viên bị chặn khỏi khu vực quản trị (403)", response.status_code == 403)

        # Nhap diem cho mot hoc vien roi chot
        with app.app_context():
            enrollment = (
                Enrollment.query.filter_by(class_id=class_a1_id)
                .join(StudentProfile).join(User)
                .filter(User.username == "hv.cuong").first()
            )
            enrollment_id = enrollment.id
        response = client.post(
            f"/giao-vien/lop/{class_a1_id}/nhap-diem",
            data={
                "term": "Đầu vào",
                f"e{enrollment_id}_listening": "6.0",
                f"e{enrollment_id}_reading": "6.5",
                f"e{enrollment_id}_writing": "5.5",
                f"e{enrollment_id}_speaking": "6.0",
                f"e{enrollment_id}_comment": "Tiến bộ rõ ở Reading.",
            },
            follow_redirects=True,
        )
        check("Lưu điểm kỳ Đầu vào", "Đã lưu điểm" in response.get_data(as_text=True))

        with app.app_context():
            record = ScoreRecord.query.filter_by(
                enrollment_id=enrollment_id, term="Đầu vào"
            ).first()
            check("Overall tính đúng (6.0+6.5+5.5+6.0)/4 = 6.0", record.overall == 6.0,
                  f"nhận {record.overall}")
            check("Có ghi nhật ký thay đổi điểm", len(record.logs) >= 1)

        # Diem sai quy cach bi tu choi
        response = client.post(
            f"/giao-vien/lop/{class_a1_id}/nhap-diem",
            data={"term": "Đầu vào", f"e{enrollment_id}_listening": "6.3",
                  f"e{enrollment_id}_reading": "6.5", f"e{enrollment_id}_writing": "5.5",
                  f"e{enrollment_id}_speaking": "6.0"},
            follow_redirects=True,
        )
        check("Chặn điểm không đúng bước 0.5", "không hợp lệ" in response.get_data(as_text=True))

        # Chot va cong bo
        response = client.post(
            f"/giao-vien/lop/{class_a1_id}/chot-diem",
            data={"term": "Đầu vào"}, follow_redirects=True,
        )
        check("Chốt và công bố kết quả", "Đã chốt và công bố" in response.get_data(as_text=True))

        # Sau khi chot thi khong sua duoc nua
        response = client.post(
            f"/giao-vien/lop/{class_a1_id}/nhap-diem",
            data={"term": "Đầu vào", f"e{enrollment_id}_listening": "7.0",
                  f"e{enrollment_id}_reading": "7.0", f"e{enrollment_id}_writing": "7.0",
                  f"e{enrollment_id}_speaking": "7.0"},
            follow_redirects=True,
        )
        check("Khóa sửa điểm sau khi chốt", "đã chốt điểm nên không sửa được"
              in response.get_data(as_text=True))

    with app.test_client() as client:
        login(client, "admin")
        report_response = get(client, "/quan-tri/diem-danh")
        check("Admin xem được báo cáo điểm danh",
              "Tình hình điểm danh" in report_response.get_data(as_text=True))
        student_response = get(
            client, f"/quan-tri/hoc-vien/{attendance_student_id}"
        )
        student_html = student_response.get_data(as_text=True)
        check("Admin xem được lịch sử trên hồ sơ học viên",
              "Tình hình điểm danh" in student_html
              and "31/12/2099" in student_html)
    with app.app_context():
        AttendanceRecord.query.filter(
            AttendanceRecord.enrollment_id.in_(attendance_enrollment_ids),
            AttendanceRecord.attendance_date == attendance_date,
        ).delete(synchronize_session=False)
        student_user = User.query.filter_by(username="hv.an").first()
        matrix_enrollment = Enrollment.query.filter_by(
            student_id=student_user.student.id, class_id=class_a1_id
        ).first()
        attendance_teacher = User.query.filter_by(username="gv.mai").first()
        matrix_enrollment_id = matrix_enrollment.id
        db.session.add(
            AttendanceRecord(
                enrollment_id=matrix_enrollment_id,
                attendance_date=attendance_date,
                status="present",
                marked_by=attendance_teacher.id,
            )
        )
        db.session.commit()

    print("\n=== 5. Quan tri vien mo khoa sua diem (<<extend>>) ===")
    with app.app_context():
        score = ScoreRecord.query.filter_by(enrollment_id=enrollment_id, term="Đầu vào").first()
        score_id = score.id
    with app.test_client() as client:
        login(client, "admin")
        response = client.post(f"/quan-tri/ket-qua/{score_id}/mo-khoa", follow_redirects=True)
        check("Mở khóa điểm đã chốt", "Đã mở khóa" in response.get_data(as_text=True))
    with app.app_context():
        score = db.session.get(ScoreRecord, score_id)
        check("Điểm chuyển về trạng thái chưa công bố", score.is_published is False)

    print("\n=== 6. Vai tro Hoc vien ===")
    with app.test_client() as client:
        response = login(client, "hv.an")
        check("Đăng nhập học viên", "Xin chào" in response.get_data(as_text=True))
        get(client, "/hoc-vien/")
        get(client, "/hoc-vien/khoa-hoc")
        get(client, f"/hoc-vien/lop/{class_a1_id}")
        attendance_response = get(client, "/hoc-vien/diem-danh")
        attendance_html = attendance_response.get_data(as_text=True)
        check("Trang điểm danh học viên có thống kê tháng và lịch sử",
              "Tổng buổi trong tháng" in attendance_html
              and "attendance-matrix" in attendance_html
              and "Lớp học" in attendance_html)
        student_matrix = client.get("/hoc-vien/diem-danh?month=2099-12")
        check("Bảng học viên tô màu ô điểm danh theo ngày",
              "attendance-present" in student_matrix.get_data(as_text=True))
        response = get(client, "/hoc-vien/ket-qua")
        check("Học viên thấy điểm đã công bố", "Giữa khóa" in response.get_data(as_text=True))
        response = get(client, "/hoc-vien/bang-diem.csv")
        check("Tải bảng điểm cá nhân", "text/csv" in response.headers.get("Content-Type", ""))

        # Khong xem duoc lop minh khong hoc
        response = client.get(f"/hoc-vien/lop/{class_a2_id}", follow_redirects=True)
        check("Chặn học viên xem lớp không thuộc về mình",
              "không thuộc lớp học này" in response.get_data(as_text=True))
        response = client.get("/quan-tri/")
        check("Học viên bị chặn khỏi khu vực quản trị (403)", response.status_code == 403)
    with app.app_context():
        AttendanceRecord.query.filter_by(
            enrollment_id=matrix_enrollment_id, attendance_date=attendance_date
        ).delete()
        db.session.commit()

    test_homework_workflow(class_a1_id, class_a2_id)

    print("\n=== 7. Khoa tai khoan sau 5 lan dang nhap sai ===")
    with app.test_client() as client:
        for _ in range(5):
            client.post("/dang-nhap", data={"username": "hv.hoa", "password": "sai-mat-khau"})
        response = client.post(
            "/dang-nhap", data={"username": "hv.hoa", "password": "123456"}, follow_redirects=True
        )
        check("Tài khoản bị khóa sau 5 lần sai", "đang bị khóa" in response.get_data(as_text=True))

    with app.test_client() as client:
        login(client, "admin")
        with app.app_context():
            locked = User.query.filter_by(username="hv.hoa").first()
            locked_id = locked.id
        client.post(f"/quan-tri/tai-khoan/{locked_id}/khoa", follow_redirects=True)
    with app.test_client() as client:
        response = login(client, "hv.hoa")
        check("Mở khóa xong đăng nhập lại được", "Xin chào" in response.get_data(as_text=True))

    print("\n=== 8. Trang loi ===")
    with app.test_client() as client:
        response = client.get("/duong-dan-khong-ton-tai")
        check("Trang 404 hoạt động", response.status_code == 404)

    print("\n" + "=" * 50)
    if FAILED:
        print(f"CÓ {len(FAILED)} KIỂM TRA THẤT BẠI:")
        for item in FAILED:
            print("  -", item)
        sys.exit(1)
    print("TẤT CẢ KIỂM TRA ĐỀU ĐẠT.")


if __name__ == "__main__":
    main()
