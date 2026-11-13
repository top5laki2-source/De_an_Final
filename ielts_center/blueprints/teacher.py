"""Cac use case cua Giao vien: xem lop giang day va quan ly ket qua hoc tap."""
import csv
import io
import os
from calendar import monthrange
from datetime import date, datetime

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user

from extensions import db
from homework_files import MAX_FILES_PER_UPLOAD, save_upload, validate_uploads
from models import (
    ATTENDANCE_STATUSES,
    Homework,
    HomeworkMaterial,
    HomeworkSubmission,
    HomeworkSubmissionFile,
    SKILLS,
    WEEKDAYS,
    AttendanceRecord,
    ClassRoom,
    Enrollment,
    ScoreLog,
    ScoreRecord,
)
from utils import band_valid, parse_float, teacher_required

teacher_bp = Blueprint("teacher", __name__, url_prefix="/giao-vien")

TERMS = ["Đầu vào", "Giữa khóa", "Cuối khóa"]


@teacher_bp.before_request
@teacher_required
def _guard():
    return None


def my_classes():
    """Chi lay cac lop ma giao vien dang dang nhap duoc phan cong."""
    profile = current_user.teacher
    if profile is None:
        return []
    return (
        ClassRoom.query.filter_by(teacher_id=profile.id).order_by(ClassRoom.code).all()
    )


def owns_class(classroom):
    profile = current_user.teacher
    return profile is not None and classroom is not None and classroom.teacher_id == profile.id


def owns_homework(homework):
    return homework is not None and owns_class(homework.classroom)


# ============================================================ TRANG CHU


@teacher_bp.route("/")
def dashboard():
    """UC Xem danh sach lop duoc phan cong."""
    classes = my_classes()
    total_students = sum(c.current_size for c in classes)
    pending = 0
    for c in classes:
        for e in c.enrollments:
            if e.status != "stopped" and not any(s.is_published for s in e.scores):
                pending += 1
    return render_template(
        "teacher/dashboard.html",
        classes=classes,
        total_students=total_students,
        pending=pending,
    )


@teacher_bp.route("/lich-day")
def schedule():
    """UC Xem lich day ca nhan."""
    classes = my_classes()
    table = {i: [] for i in range(7)}
    for c in classes:
        if c.status in ("cancelled", "finished"):
            continue
        for s in c.schedules:
            table[s.weekday].append((s, c))
    for day in table:
        table[day].sort(key=lambda item: item[0].start_time)
    return render_template("teacher/schedule.html", table=table, weekdays=WEEKDAYS)


# ============================================================ BAI TAP VE NHA


@teacher_bp.route("/bai-tap")
def homework_list():
    classes = my_classes()
    class_ids = [classroom.id for classroom in classes]
    assignments = (
        Homework.query.filter(Homework.class_id.in_(class_ids))
        .order_by(Homework.deadline.desc(), Homework.id.desc())
        .all()
        if class_ids else []
    )
    return render_template(
        "teacher/homework.html",
        classes=classes,
        assignments=assignments,
        now=datetime.now(),
    )


@teacher_bp.route("/bai-tap/tao", methods=["POST"])
def create_homework():
    classes = my_classes()
    try:
        class_id = int(request.form.get("class_id", ""))
    except ValueError:
        flash("Vui lòng chọn lớp hợp lệ.", "danger")
        return redirect(url_for("teacher.homework_list"))

    classroom = next((item for item in classes if item.id == class_id), None)
    if classroom is None:
        flash("Bạn không được phân công phụ trách lớp này.", "danger")
        return redirect(url_for("teacher.homework_list"))

    title = request.form.get("title", "").strip()
    instructions = request.form.get("instructions", "").strip()
    raw_deadline = request.form.get("deadline", "").strip()
    try:
        deadline = datetime.strptime(raw_deadline, "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("Vui lòng nhập hạn nộp hợp lệ.", "danger")
        return redirect(url_for("teacher.homework_list"))
    if not title or len(title) > 150 or not instructions:
        flash("Vui lòng nhập tiêu đề (tối đa 150 ký tự) và yêu cầu bài tập.", "danger")
        return redirect(url_for("teacher.homework_list"))

    uploads, error = validate_uploads(request.files.getlist("materials"))
    if error:
        flash(error, "danger")
        return redirect(url_for("teacher.homework_list"))

    homework = Homework(
        classroom=classroom,
        teacher=current_user,
        title=title,
        instructions=instructions,
        deadline=deadline,
    )
    for file, filename in uploads:
        homework.materials.append(
            HomeworkMaterial(
                original_filename=filename,
                stored_filename=save_upload(file),
            )
        )
    db.session.add(homework)
    db.session.commit()
    flash("Đã giao bài tập về nhà.", "success")
    return redirect(url_for("teacher.homework_detail", homework_id=homework.id))


@teacher_bp.route("/bai-tap/<int:homework_id>/sua", methods=["GET", "POST"])
def edit_homework(homework_id):
    homework = db.session.get(Homework, homework_id)
    if not owns_homework(homework):
        abort(404)

    def render_edit_form():
        return render_template(
            "teacher/homework_edit.html",
            homework=homework,
            title=request.form.get("title", homework.title),
            instructions=request.form.get("instructions", homework.instructions),
            deadline=request.form.get(
                "deadline", homework.deadline.strftime("%Y-%m-%dT%H:%M")
            ),
        )

    if request.method == "GET":
        return render_edit_form()

    title = request.form.get("title", "").strip()
    instructions = request.form.get("instructions", "").strip()
    raw_deadline = request.form.get("deadline", "").strip()
    try:
        deadline = datetime.strptime(raw_deadline, "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("Vui lòng nhập hạn nộp hợp lệ.", "danger")
        return render_edit_form()
    if not title or len(title) > 150 or not instructions:
        flash("Vui lòng nhập tiêu đề (tối đa 150 ký tự) và yêu cầu bài tập.", "danger")
        return render_edit_form()

    try:
        remove_material_ids = {
            int(material_id)
            for material_id in request.form.getlist("remove_materials")
        }
    except ValueError:
        flash("Danh sách tài liệu cần gỡ không hợp lệ.", "danger")
        return render_edit_form()

    materials_by_id = {material.id: material for material in homework.materials}
    if not remove_material_ids.issubset(materials_by_id):
        abort(404)

    uploads, error = validate_uploads(request.files.getlist("materials"))
    if error:
        flash(error, "danger")
        return render_edit_form()

    remaining_count = len(homework.materials) - len(remove_material_ids)
    if remaining_count + len(uploads) > MAX_FILES_PER_UPLOAD:
        flash(
            f"Mỗi bài tập chỉ được có tối đa {MAX_FILES_PER_UPLOAD} tài liệu.",
            "danger",
        )
        return render_edit_form()

    removed_paths = [
        os.path.join(
            current_app.config["HOMEWORK_UPLOAD_DIR"],
            materials_by_id[material_id].stored_filename,
        )
        for material_id in remove_material_ids
    ]
    for material_id in remove_material_ids:
        homework.materials.remove(materials_by_id[material_id])

    homework.title = title
    homework.instructions = instructions
    homework.deadline = deadline
    for file, filename in uploads:
        homework.materials.append(
            HomeworkMaterial(
                original_filename=filename,
                stored_filename=save_upload(file),
            )
        )
    db.session.commit()

    cleanup_failed = False
    for path in removed_paths:
        try:
            os.remove(path)
        except OSError:
            current_app.logger.exception("Could not remove homework material file: %s", path)
            cleanup_failed = True

    flash("Đã cập nhật bài tập.", "success")
    if cleanup_failed:
        flash("Một số tệp đã gỡ khỏi bài tập nhưng chưa xóa được khỏi máy chủ.", "warning")
    return redirect(url_for("teacher.homework_detail", homework_id=homework.id))


@teacher_bp.route("/bai-tap/<int:homework_id>")
def homework_detail(homework_id):
    homework = db.session.get(Homework, homework_id)
    if not owns_homework(homework):
        abort(404)
    enrollments = [
        enrollment for enrollment in homework.classroom.enrollments
        if enrollment.status != "stopped"
        or any(
            submission.enrollment_id == enrollment.id
            for submission in homework.submissions
        )
    ]
    submissions_by_enrollment = {
        enrollment.id: [
            submission for submission in homework.submissions
            if submission.enrollment_id == enrollment.id
        ]
        for enrollment in enrollments
    }
    return render_template(
        "teacher/homework_detail.html",
        homework=homework,
        enrollments=enrollments,
        submissions_by_enrollment=submissions_by_enrollment,
        now=datetime.now(),
    )


@teacher_bp.route("/bai-tap/<int:homework_id>/tai-tai-lieu/<int:material_id>")
def download_homework_material(homework_id, material_id):
    homework = db.session.get(Homework, homework_id)
    if not owns_homework(homework):
        abort(404)
    material = HomeworkMaterial.query.filter_by(
        id=material_id, homework_id=homework.id
    ).first_or_404()
    path = os.path.join(
        current_app.config["HOMEWORK_UPLOAD_DIR"], material.stored_filename
    )
    return send_file(path, as_attachment=True, download_name=material.original_filename)


@teacher_bp.route("/bai-tap/<int:homework_id>/tai-bai-nop/<int:file_id>")
def download_homework_submission(homework_id, file_id):
    homework = db.session.get(Homework, homework_id)
    if not owns_homework(homework):
        abort(404)
    submission_file = (
        HomeworkSubmissionFile.query.join(HomeworkSubmission)
        .filter(
            HomeworkSubmissionFile.id == file_id,
            HomeworkSubmission.homework_id == homework.id,
        )
        .first_or_404()
    )
    path = os.path.join(
        current_app.config["HOMEWORK_UPLOAD_DIR"], submission_file.stored_filename
    )
    return send_file(
        path, as_attachment=True, download_name=submission_file.original_filename
    )


# ============================================================ LOP HOC


@teacher_bp.route("/lop/<int:class_id>")
def class_detail(class_id):
    """UC Xem danh sach hoc vien trong lop + Xem tien do ca lop."""
    classroom = db.session.get(ClassRoom, class_id)
    if not owns_class(classroom):
        flash("Bạn không được phân công phụ trách lớp này.", "danger")
        return redirect(url_for("teacher.dashboard"))

    # Tien do ca lop: band trung binh theo tung ky nang (chi tinh diem da chot)
    totals = {key: [] for key, _ in SKILLS}
    overalls = []
    active_enrollments = [
        enrollment for enrollment in classroom.enrollments
        if enrollment.status != "stopped"
    ]
    for enrollment in active_enrollments:
        latest = enrollment.latest_score
        if latest is None:
            continue
        for key, _ in SKILLS:
            value = getattr(latest, key)
            if value is not None:
                totals[key].append(value)
        if latest.overall is not None:
            overalls.append(latest.overall)

    averages = {
        key: (round(sum(values) / len(values), 2) if values else None)
        for key, values in totals.items()
    }
    class_average = round(sum(overalls) / len(overalls), 2) if overalls else None

    return render_template(
        "teacher/class_detail.html",
        classroom=classroom,
        active_enrollments=active_enrollments,
        skills=SKILLS,
        averages=averages,
        class_average=class_average,
        scores_by_term={
            enrollment.id: {
                term: next(
                    (
                        score for score in enrollment.scores
                        if score.term == term and score.is_published
                    ),
                    None,
                )
                for term in TERMS[1:]
            }
            for enrollment in active_enrollments
        },
    )


@teacher_bp.route("/lop/<int:class_id>/hoc-vien/<int:enrollment_id>")
def student_scores(class_id, enrollment_id):
    """Xem chi tiet diem da cong bo cua hoc vien trong lop giao vien phu trach."""
    classroom = db.session.get(ClassRoom, class_id)
    if not owns_class(classroom):
        flash("Bạn không được phân công phụ trách lớp này.", "danger")
        return redirect(url_for("teacher.dashboard"))

    enrollment = Enrollment.query.filter_by(
        id=enrollment_id, class_id=class_id
    ).first()
    if enrollment is None:
        abort(404)

    term_order = {term: index for index, term in enumerate(TERMS)}
    published_scores = sorted(
        (score for score in enrollment.scores if score.is_published),
        key=lambda score: (
            term_order.get(score.term, len(TERMS)),
            score.id,
        ),
    )
    return render_template(
        "teacher/student_scores.html",
        classroom=classroom,
        enrollment=enrollment,
        published_scores=published_scores,
        skills=SKILLS,
    )


# ============================================================ DIEM DANH


@teacher_bp.route("/diem-danh", methods=["GET", "POST"])
@teacher_bp.route(
    "/lop/<int:class_id>/diem-danh", methods=["GET", "POST"], endpoint="take_attendance"
)
def attendance(class_id=None):
    """Xem lich su theo thang va ghi nhan diem danh cho lop duoc phan cong."""
    classes = my_classes()
    raw_class_id = class_id or request.values.get("class_id")
    try:
        selected_class_id = int(raw_class_id) if raw_class_id else (
            classes[0].id if classes else None
        )
    except ValueError:
        flash("Lớp học không hợp lệ.", "danger")
        return redirect(url_for("teacher.dashboard"))

    classroom = db.session.get(ClassRoom, selected_class_id) if selected_class_id else None
    if selected_class_id and classroom is None:
        abort(404)
    if classroom is not None and not owns_class(classroom):
        flash("Bạn không được phân công phụ trách lớp này.", "danger")
        return redirect(url_for("teacher.dashboard"))

    raw_date = request.values.get("date")
    try:
        attendance_date = (
            datetime.strptime(raw_date, "%Y-%m-%d").date() if raw_date else date.today()
        )
    except ValueError:
        flash("Ngày điểm danh không hợp lệ.", "danger")
        return redirect(url_for("teacher.attendance", class_id=selected_class_id))

    current_month = date.today().strftime("%Y-%m")
    month_value = request.values.get("month", current_month)
    try:
        month_start = datetime.strptime(month_value, "%Y-%m").date().replace(day=1)
    except ValueError:
        flash("Tháng điểm danh không hợp lệ.", "danger")
        month_start = date.today().replace(day=1)
        month_value = current_month
    month_end = (
        month_start.replace(year=month_start.year + 1, month=1)
        if month_start.month == 12
        else month_start.replace(month=month_start.month + 1)
    )

    active_enrollments = (
        [
            enrollment for enrollment in classroom.enrollments
            if enrollment.status == "studying"
        ]
        if classroom else []
    )

    if request.method == "POST":
        if classroom is None:
            flash("Bạn chưa được phân công lớp để điểm danh.", "danger")
            return redirect(url_for("teacher.attendance"))
        submitted_statuses = {
            enrollment.id: request.form.get(f"status_{enrollment.id}", "")
            for enrollment in active_enrollments
        }
        if any(status not in ATTENDANCE_STATUSES for status in submitted_statuses.values()):
            flash("Vui lòng chọn trạng thái điểm danh hợp lệ cho từng học viên.", "danger")
            return redirect(
                url_for(
                    "teacher.attendance",
                    class_id=classroom.id,
                    date=attendance_date.isoformat(),
                    month=month_value,
                )
            )

        for enrollment in active_enrollments:
            record = AttendanceRecord.query.filter_by(
                enrollment_id=enrollment.id, attendance_date=attendance_date
            ).first()
            if record is None:
                record = AttendanceRecord(
                    enrollment_id=enrollment.id,
                    attendance_date=attendance_date,
                    marked_by=current_user.id,
                )
                db.session.add(record)
            record.status = submitted_statuses[enrollment.id]
            record.marked_by = current_user.id
            record.marked_at = datetime.now()

        db.session.commit()
        flash(f"Đã lưu điểm danh ngày {attendance_date.strftime('%d/%m/%Y')}.", "success")
        return redirect(
            url_for(
                "teacher.attendance",
                class_id=classroom.id,
                date=attendance_date.isoformat(),
                month=month_value,
            )
        )

    records = {
        record.enrollment_id: record
        for record in AttendanceRecord.query.filter(
            AttendanceRecord.enrollment_id.in_(
                [enrollment.id for enrollment in active_enrollments]
            ),
            AttendanceRecord.attendance_date == attendance_date,
        ).all()
    } if active_enrollments else {}
    monthly_records = (
        AttendanceRecord.query.join(Enrollment)
        .filter(
            Enrollment.class_id == classroom.id,
            AttendanceRecord.attendance_date >= month_start,
            AttendanceRecord.attendance_date < month_end,
        )
        .order_by(
            AttendanceRecord.attendance_date.desc(),
            AttendanceRecord.marked_at.desc(),
        )
        .all()
        if classroom else []
    )
    monthly_summary = {
        status: sum(record.status == status for record in monthly_records)
        for status in ATTENDANCE_STATUSES
    }
    attendance_matrix = {}
    for record in monthly_records:
        attendance_matrix.setdefault(record.enrollment_id, {})[
            record.attendance_date.day
        ] = record
    attendance_rows = (
        [
            enrollment for enrollment in classroom.enrollments
            if enrollment.status != "stopped" or enrollment.id in attendance_matrix
        ]
        if classroom else []
    )
    return render_template(
        "teacher/attendance.html",
        classes=classes,
        classroom=classroom,
        active_enrollments=active_enrollments,
        attendance_date=attendance_date,
        month_value=month_value,
        attendance_statuses=ATTENDANCE_STATUSES,
        records=records,
        monthly_records=monthly_records,
        monthly_summary=monthly_summary,
        attendance_matrix=attendance_matrix,
        attendance_rows=attendance_rows,
        month_days=range(1, monthrange(month_start.year, month_start.month)[1] + 1),
    )


# ============================================================ NHAP DIEM


@teacher_bp.route("/lop/<int:class_id>/nhap-diem", methods=["GET", "POST"])
def enter_scores(class_id):
    """UC Nhap diem 4 ky nang - include Tinh band Overall (lam tron 0.5)."""
    classroom = db.session.get(ClassRoom, class_id)
    if not owns_class(classroom):
        flash("Bạn không được phân công phụ trách lớp này.", "danger")
        return redirect(url_for("teacher.dashboard"))

    term = request.args.get("term") or request.form.get("term") or TERMS[1]

    if request.method == "POST":
        saved, blocked, invalid = 0, 0, 0
        for enrollment in classroom.enrollments:
            if enrollment.status not in ("studying", "finished"):
                continue
            prefix = f"e{enrollment.id}_"
            values = {key: parse_float(request.form.get(prefix + key)) for key, _ in SKILLS}

            if all(v is None for v in values.values()) and not request.form.get(
                prefix + "comment"
            ):
                continue
            if any(not band_valid(v) for v in values.values()):
                invalid += 1
                continue

            record = ScoreRecord.query.filter_by(
                enrollment_id=enrollment.id, term=term
            ).first()
            if record and record.is_published:
                blocked += 1
                continue

            old_summary = record.summary if record else "(chưa có)"
            if record is None:
                record = ScoreRecord(enrollment_id=enrollment.id, term=term)
                db.session.add(record)

            for key, _ in SKILLS:
                setattr(record, key, values[key])
            record.comment = request.form.get(prefix + "comment", "").strip()
            record.compute_overall()
            db.session.flush()

            db.session.add(
                ScoreLog(
                    score_id=record.id,
                    changed_by=current_user.id,
                    old_value=old_summary,
                    new_value=record.summary,
                    action="Nhập/sửa điểm",
                )
            )
            saved += 1

        db.session.commit()
        if saved:
            flash(f"Đã lưu điểm cho {saved} học viên (kỳ {term}).", "success")
        if blocked:
            flash(
                f"{blocked} học viên đã chốt điểm nên không sửa được. "
                "Cần quản trị viên mở khóa.",
                "warning",
            )
        if invalid:
            flash(f"{invalid} học viên có điểm không hợp lệ (0.0 - 9.0, bước 0.5).", "danger")
        return redirect(url_for("teacher.enter_scores", class_id=class_id, term=term))

    active_enrollments = [
        enrollment for enrollment in classroom.enrollments
        if enrollment.status != "stopped"
    ]
    records = {}
    for enrollment in active_enrollments:
        records[enrollment.id] = ScoreRecord.query.filter_by(
            enrollment_id=enrollment.id, term=term
        ).first()

    return render_template(
        "teacher/enter_scores.html",
        classroom=classroom,
        active_enrollments=active_enrollments,
        skills=SKILLS,
        terms=TERMS,
        term=term,
        records=records,
    )


@teacher_bp.route("/lop/<int:class_id>/chot-diem", methods=["POST"])
def publish_scores(class_id):
    """UC Chot va cong bo ket qua - include Gui thong bao ket qua cho hoc vien."""
    classroom = db.session.get(ClassRoom, class_id)
    if not owns_class(classroom):
        flash("Bạn không được phân công phụ trách lớp này.", "danger")
        return redirect(url_for("teacher.dashboard"))

    term = request.form.get("term", TERMS[1])
    published, missing = 0, 0
    for enrollment in classroom.enrollments:
        if enrollment.status == "stopped":
            continue
        record = ScoreRecord.query.filter_by(enrollment_id=enrollment.id, term=term).first()
        if record is None or record.overall is None:
            missing += 1
            continue
        if record.is_published:
            continue
        record.is_published = True
        db.session.add(
            ScoreLog(
                score_id=record.id,
                changed_by=current_user.id,
                old_value="Chưa công bố",
                new_value=f"Đã công bố - Overall {record.overall}",
                action="Chốt và công bố kết quả",
            )
        )
        published += 1

    db.session.commit()
    if published:
        flash(
            f"Đã chốt và công bố kết quả kỳ {term} cho {published} học viên. "
            "Học viên đã có thể xem điểm.",
            "success",
        )
    if missing:
        flash(f"{missing} học viên chưa đủ điểm 4 kỹ năng nên chưa chốt được.", "warning")
    return redirect(url_for("teacher.enter_scores", class_id=class_id, term=term))


@teacher_bp.route("/lop/<int:class_id>/xuat-bang-diem")
def export_scores(class_id):
    """UC Xuat bang diem lop (CSV mo duoc bang Excel)."""
    classroom = db.session.get(ClassRoom, class_id)
    if not owns_class(classroom):
        flash("Bạn không được phân công phụ trách lớp này.", "danger")
        return redirect(url_for("teacher.dashboard"))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Lớp", classroom.code, "Khóa học", classroom.course.name])
    writer.writerow([])
    writer.writerow(
        ["Mã HV", "Họ tên", "Kỳ", "Listening", "Reading", "Writing", "Speaking",
         "Overall", "Nhận xét", "Trạng thái"]
    )
    for enrollment in classroom.enrollments:
        for record in sorted(enrollment.scores, key=lambda r: r.term):
            writer.writerow(
                [
                    enrollment.student.code or "",
                    enrollment.student.full_name,
                    record.term,
                    record.listening, record.reading, record.writing, record.speaking,
                    record.overall,
                    (record.comment or "").replace("\n", " "),
                    "Đã công bố" if record.is_published else "Chưa công bố",
                ]
            )

    output = "﻿" + buffer.getvalue()  # BOM de Excel doc dung tieng Viet
    return Response(
        output,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=bang-diem-{classroom.code}.csv"
        },
    )
