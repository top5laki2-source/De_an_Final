"""Cac use case cua Hoc vien: xem thong tin khoa hoc va ket qua - tien do hoc tap."""
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
from homework_files import save_upload, validate_uploads
from models import (
    ATTENDANCE_STATUSES,
    SKILLS,
    WEEKDAYS,
    AttendanceRecord,
    ClassRoom,
    Course,
    Enrollment,
    Homework,
    HomeworkMaterial,
    HomeworkSubmission,
    HomeworkSubmissionFile,
    ScoreRecord,
)
from utils import student_required

student_bp = Blueprint("student", __name__, url_prefix="/hoc-vien")


@student_bp.before_request
@student_required
def _guard():
    return None


def my_enrollments():
    """Hoc vien chi xem duoc du lieu cua chinh minh."""
    profile = current_user.student
    if profile is None:
        return []
    return (
        Enrollment.query.filter_by(student_id=profile.id)
        .order_by(Enrollment.enrolled_at.desc())
        .all()
    )


@student_bp.route("/")
def dashboard():
    enrollments = my_enrollments()
    studying = [e for e in enrollments if e.status == "studying"]
    latest = None
    for enrollment in enrollments:
        score = enrollment.latest_score
        if score and (latest is None or (score.overall or 0) > (latest.overall or 0)):
            latest = score
    return render_template(
        "student/dashboard.html",
        enrollments=enrollments,
        studying=studying,
        latest=latest,
        profile=current_user.student,
    )


@student_bp.route("/khoa-hoc")
def courses():
    """UC Xem danh sach khoa hoc dang mo."""
    open_courses = Course.query.filter_by(is_open=True).order_by(Course.entry_band).all()
    return render_template("student/courses.html", courses=open_courses)


@student_bp.route("/lop/<int:class_id>")
def class_detail(class_id):
    """UC Xem chi tiet lop dang hoc: giao vien, phong, thoi khoa bieu."""
    profile = current_user.student
    enrollment = Enrollment.query.filter_by(
        student_id=profile.id if profile else 0, class_id=class_id
    ).first()
    if enrollment is None or enrollment.status == "stopped":
        flash("Bạn không thuộc lớp học này.", "danger")
        return redirect(url_for("student.dashboard"))

    classroom = db.session.get(ClassRoom, class_id)
    return render_template(
        "student/class_detail.html",
        classroom=classroom,
        enrollment=enrollment,
        weekdays=WEEKDAYS,
    )


@student_bp.route("/ket-qua")
def results():
    """UC Xem diem tung ky nang + Xem bieu do tien bo + Xem nhan xet cua giao vien."""
    enrollments = my_enrollments()
    published = []
    for enrollment in enrollments:
        for record in enrollment.scores:
            if record.is_published:
                published.append((enrollment, record))
    published.sort(key=lambda item: (item[1].updated_at or item[1].id))

    entry_band = current_user.student.entry_band if current_user.student else None

    # Diem dau vao duoc dua vao bieu do lam moc so sanh ban dau
    chart_labels = ["Đầu vào"] + [f"{e.classroom.code} - {r.term}" for e, r in published]
    chart_data = {
        key: [None] + [getattr(r, key) for _, r in published] for key, _ in SKILLS
    }
    chart_data["overall"] = [entry_band] + [r.overall for _, r in published]

    improvement = None
    if entry_band is not None and published:
        last_overall = published[-1][1].overall
        if last_overall is not None:
            improvement = round(last_overall - entry_band, 1)

    return render_template(
        "student/results.html",
        published=published,
        skills=SKILLS,
        chart_labels=chart_labels,
        chart_data=chart_data,
        entry_band=entry_band,
        improvement=improvement,
    )


@student_bp.route("/bai-tap")
def homework_list():
    enrollments = my_enrollments()
    class_ids = [enrollment.class_id for enrollment in enrollments]
    assignments = (
        Homework.query.filter(Homework.class_id.in_(class_ids))
        .order_by(Homework.deadline.asc(), Homework.id.desc())
        .all()
        if class_ids else []
    )
    enrollment_by_class = {
        enrollment.class_id: enrollment for enrollment in enrollments
    }
    latest_submissions = {
        homework.id: next(
            (
                submission for submission in homework.submissions
                if submission.enrollment_id
                == enrollment_by_class[homework.class_id].id
            ),
            None,
        )
        for homework in assignments
    }
    return render_template(
        "student/homework.html",
        assignments=assignments,
        latest_submissions=latest_submissions,
        now=datetime.now(),
    )


@student_bp.route("/bai-tap/<int:homework_id>", methods=["GET"])
def homework_detail(homework_id):
    homework = db.session.get(Homework, homework_id)
    if homework is None or current_user.student is None:
        abort(404)
    enrollment = Enrollment.query.filter_by(
        student_id=current_user.student.id, class_id=homework.class_id
    ).first_or_404()
    return render_template(
        "student/homework_detail.html",
        homework=homework,
        enrollment=enrollment,
        now=datetime.now(),
    )


@student_bp.route("/bai-tap/<int:homework_id>/nop", methods=["POST"])
def submit_homework(homework_id):
    homework = db.session.get(Homework, homework_id)
    if homework is None or current_user.student is None:
        abort(404)
    enrollment = Enrollment.query.filter_by(
        student_id=current_user.student.id, class_id=homework.class_id
    ).first_or_404()
    if enrollment.status != "studying":
        flash("Chỉ học viên đang học mới có thể nộp bài.", "danger")
        return redirect(url_for("student.homework_detail", homework_id=homework.id))

    uploads, error = validate_uploads(request.files.getlist("files"), required=True)
    if error:
        flash(error, "danger")
        return redirect(url_for("student.homework_detail", homework_id=homework.id))

    submitted_at = datetime.now()
    submission = HomeworkSubmission(
        homework=homework,
        enrollment=enrollment,
        submitted_at=submitted_at,
        is_late=submitted_at > homework.deadline,
    )
    for file, filename in uploads:
        submission.files.append(
            HomeworkSubmissionFile(
                original_filename=filename,
                stored_filename=save_upload(file),
            )
        )
    db.session.add(submission)
    db.session.commit()
    if submission.is_late:
        flash("Đã nộp bài. Bài được ghi nhận là nộp muộn.", "warning")
    else:
        flash("Đã nộp bài tập thành công.", "success")
    return redirect(url_for("student.homework_detail", homework_id=homework.id))


@student_bp.route("/bai-tap/<int:homework_id>/tai-tai-lieu/<int:material_id>")
def download_homework_material(homework_id, material_id):
    homework = db.session.get(Homework, homework_id)
    if homework is None or current_user.student is None:
        abort(404)
    enrollment = Enrollment.query.filter_by(
        student_id=current_user.student.id, class_id=homework.class_id
    ).first_or_404()
    material = HomeworkMaterial.query.filter_by(
        id=material_id, homework_id=homework.id
    ).first_or_404()
    path = os.path.join(
        current_app.config["HOMEWORK_UPLOAD_DIR"], material.stored_filename
    )
    return send_file(path, as_attachment=True, download_name=material.original_filename)


@student_bp.route("/bai-tap/<int:homework_id>/tai-bai-nop/<int:file_id>")
def download_own_homework_submission(homework_id, file_id):
    if current_user.student is None:
        abort(404)
    submission_file = (
        HomeworkSubmissionFile.query.join(HomeworkSubmission)
        .join(Enrollment)
        .filter(
            HomeworkSubmissionFile.id == file_id,
            HomeworkSubmission.homework_id == homework_id,
            Enrollment.student_id == current_user.student.id,
        )
        .first_or_404()
    )
    path = os.path.join(
        current_app.config["HOMEWORK_UPLOAD_DIR"], submission_file.stored_filename
    )
    return send_file(
        path, as_attachment=True, download_name=submission_file.original_filename
    )


@student_bp.route("/diem-danh")
def attendance():
    """Xem lich su diem danh va thong ke theo thang cua hoc vien."""
    month_value = request.args.get("month", date.today().strftime("%Y-%m"))
    try:
        month_start = datetime.strptime(month_value, "%Y-%m").date().replace(day=1)
    except ValueError:
        flash("Tháng điểm danh không hợp lệ.", "danger")
        month_start = date.today().replace(day=1)
        month_value = date.today().strftime("%Y-%m")
    month_end = (
        month_start.replace(year=month_start.year + 1, month=1)
        if month_start.month == 12
        else month_start.replace(month=month_start.month + 1)
    )

    enrollments = my_enrollments()
    enrollment_ids = [enrollment.id for enrollment in enrollments]
    records = (
        AttendanceRecord.query.filter(
            AttendanceRecord.enrollment_id.in_(enrollment_ids),
            AttendanceRecord.attendance_date >= month_start,
            AttendanceRecord.attendance_date < month_end,
        )
        .order_by(
            AttendanceRecord.attendance_date.desc(),
            AttendanceRecord.marked_at.desc(),
        )
        .all()
        if enrollment_ids else []
    )
    attendance_matrix = {}
    for record in records:
        attendance_matrix.setdefault(record.enrollment_id, {})[
            record.attendance_date.day
        ] = record
    monthly_summary = {
        status: sum(record.status == status for record in records)
        for status in ATTENDANCE_STATUSES
    }
    return render_template(
        "student/attendance.html",
        records=records,
        attendance_matrix=attendance_matrix,
        attendance_rows=enrollments,
        month_days=range(1, monthrange(month_start.year, month_start.month)[1] + 1),
        month_value=month_value,
        monthly_summary=monthly_summary,
        attendance_statuses=ATTENDANCE_STATUSES,
        total_sessions=len(records),
    )


@student_bp.route("/bang-diem.csv")
def export_transcript():
    """UC Tai bang diem ca nhan."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Học viên", current_user.full_name])
    writer.writerow([])
    writer.writerow(
        ["Lớp", "Khóa học", "Kỳ", "Listening", "Reading", "Writing", "Speaking",
         "Overall", "Nhận xét"]
    )
    for enrollment in my_enrollments():
        for record in enrollment.scores:
            if not record.is_published:
                continue
            writer.writerow(
                [
                    enrollment.classroom.code,
                    enrollment.classroom.course.name,
                    record.term,
                    record.listening, record.reading, record.writing, record.speaking,
                    record.overall,
                    (record.comment or "").replace("\n", " "),
                ]
            )

    output = "﻿" + buffer.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=bang-diem-ca-nhan.csv"},
    )
