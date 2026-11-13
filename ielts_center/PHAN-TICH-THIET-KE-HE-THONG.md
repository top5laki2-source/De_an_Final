# Phân tích và thiết kế hệ thống quản lý trung tâm IELTS

## 1. Phạm vi và tác nhân

Các sơ đồ phản ánh chức năng hiện có trong ứng dụng Flask, các blueprint và README:

- **Học viên (Student):** xem khóa học đang mở, lớp đã ghi danh, điểm danh, bài tập, kết quả đã công bố; nộp bài và tải bảng điểm CSV.
- **Giáo viên (Teacher):** xem lớp được phân công và lịch dạy; điểm danh; giao/quản lý bài tập; nhập, chốt và xuất điểm.
- **Quản trị viên (Admin):** quản lý khóa học, lớp, lịch, hồ sơ học viên/giáo viên, ghi danh, tài khoản; xem báo cáo điểm danh/kết quả và mở khóa điểm.
- **Hệ thống:** xác thực và phân quyền, kiểm tra ràng buộc nghiệp vụ, tính Overall, lưu dữ liệu và nhật ký điểm.

Không mô hình hóa thanh toán, điểm danh tự động, email đặt lại mật khẩu, nhắn tin hay lớp học trực tuyến vì đây không phải chức năng hiện có.

## 2. USE CASE tổng quát

```mermaid
flowchart LR
    Student["Học viên"]
    Teacher["Giáo viên"]
    Admin["Quản trị viên"]

    subgraph System["Hệ thống quản lý trung tâm IELTS"]
        UC_Login(["Đăng nhập"])
        UC_Logout(["Đăng xuất"])
        UC_ChangePassword(["Đổi mật khẩu"])
        UC_ForgotPassword(["Gửi yêu cầu quên mật khẩu"])
        UC_Profile(["Tra cứu dữ liệu theo vai trò"])
        UC_Training(["Quản lý khóa học, lớp và lịch"])
        UC_Enrollment(["Quản lý hồ sơ và ghi danh"])
        UC_Attendance(["Điểm danh và tra cứu điểm danh"])
        UC_Homework(["Quản lý, nộp và theo dõi bài tập"])
        UC_Scores(["Nhập, chốt và xem kết quả"])
        UC_Account(["Quản lý tài khoản"])
        UC_Reports(["Xem báo cáo, xuất CSV"])
        UC_Unlock(["Mở khóa điểm đã chốt"])
        UC_Lock(["Khóa tài khoản sau nhiều lần đăng nhập sai"])
    end

    Student --- UC_Login
    Teacher --- UC_Login
    Admin --- UC_Login
    Student --- UC_Logout
    Teacher --- UC_Logout
    Admin --- UC_Logout
    Student --- UC_ChangePassword
    Teacher --- UC_ChangePassword
    Admin --- UC_ChangePassword
    Student --- UC_ForgotPassword
    Teacher --- UC_ForgotPassword
    Admin --- UC_ForgotPassword

    Student --- UC_Profile
    Student --- UC_Attendance
    Student --- UC_Homework
    Student --- UC_Scores
    Student --- UC_Reports

    Teacher --- UC_Profile
    Teacher --- UC_Attendance
    Teacher --- UC_Homework
    Teacher --- UC_Scores
    Teacher --- UC_Reports

    Admin --- UC_Training
    Admin --- UC_Enrollment
    Admin --- UC_Account
    Admin --- UC_Attendance
    Admin --- UC_Scores
    Admin --- UC_Reports
    Admin --- UC_Unlock

    UC_Login -. "mở rộng khi sai đủ số lần" .-> UC_Lock
```

## 3. USE CASE phân rã theo vai trò

### 3.1. Học viên (Students)

```mermaid
flowchart LR
    Student["Học viên"]
    subgraph StudentSystem["Phân hệ học viên"]
        S_Dashboard(["Xem trang cá nhân"])
        S_Courses(["Xem khóa học đang mở"])
        S_Class(["Xem thông tin lớp đã ghi danh"])
        S_Attendance(["Xem lịch sử và thống kê điểm danh"])
        S_Homework(["Xem bài tập và tài liệu"])
        S_Submit(["Nộp bài tập bằng tệp"])
        S_Submission(["Xem trạng thái bài nộp"])
        S_Results(["Xem điểm đã công bố và nhận xét"])
        S_Progress(["Xem biểu đồ tiến bộ"])
        S_CSV(["Tải bảng điểm cá nhân CSV"])
    end
    Student --- S_Dashboard
    Student --- S_Courses
    Student --- S_Class
    Student --- S_Attendance
    Student --- S_Homework
    Student --- S_Submit
    Student --- S_Submission
    Student --- S_Results
    Student --- S_Progress
    Student --- S_CSV
    S_Submit -. "bao gồm" .-> S_Submission
    S_Progress -. "chỉ dùng kết quả đã công bố" .-> S_Results
    S_CSV -. "chỉ xuất kết quả đã công bố" .-> S_Results
```

### 3.2. Giáo viên (Teachers)

```mermaid
flowchart LR
    Teacher["Giáo viên"]
    subgraph TeacherSystem["Phân hệ giáo viên"]
        T_Dashboard(["Xem lớp được phân công"])
        T_Schedule(["Xem lịch dạy"])
        T_Class(["Xem danh sách và tiến độ lớp"])
        T_StudentScore(["Xem điểm đã công bố của học viên"])
        T_Attendance(["Ghi nhận và xem điểm danh"])
        T_Homework(["Tạo, sửa bài tập và tài liệu"])
        T_Submissions(["Xem bài nộp và tải tệp"])
        T_EnterScore(["Nhập hoặc sửa điểm 4 kỹ năng"])
        T_Overall(["Tính band Overall"])
        T_Publish(["Chốt và công bố điểm"])
        T_Export(["Xuất bảng điểm lớp CSV"])
    end
    Teacher --- T_Dashboard
    Teacher --- T_Schedule
    Teacher --- T_Class
    Teacher --- T_StudentScore
    Teacher --- T_Attendance
    Teacher --- T_Homework
    Teacher --- T_Submissions
    Teacher --- T_EnterScore
    Teacher --- T_Publish
    Teacher --- T_Export
    T_EnterScore -. "bao gồm" .-> T_Overall
    T_Publish -. "bao gồm kiểm tra đủ điểm và lưu nhật ký" .-> T_EnterScore
    T_Submissions -. "chỉ trong lớp được phân công" .-> T_Homework
```

### 3.3. Quản trị viên (Admin)

```mermaid
flowchart LR
    Admin["Quản trị viên"]
    subgraph AdminSystem["Phân hệ quản trị"]
        A_Dashboard(["Xem tổng quan"])
        A_Course(["Tạo, sửa và mở/ngừng tuyển sinh khóa học"])
        A_Class(["Tạo, sửa, đóng/hủy lớp"])
        A_Assign(["Phân công giáo viên và phòng học"])
        A_Schedule(["Tạo, sửa, xóa thời khóa biểu"])
        A_Conflict(["Kiểm tra xung đột lịch"])
        A_Teacher(["Quản lý hồ sơ giáo viên"])
        A_Student(["Quản lý hồ sơ học viên"])
        A_Enroll(["Ghi danh, bảo lưu, hoàn thành hoặc cho nghỉ"])
        A_Admission(["Kiểm tra band đầu vào, trạng thái lớp và sĩ số"])
        A_Account(["Tạo và quản lý tài khoản, vai trò"])
        A_Reset(["Khóa/mở tài khoản, đặt lại mật khẩu"])
        A_ResetRequest(["Xử lý yêu cầu quên mật khẩu"])
        A_Attendance(["Xem báo cáo điểm danh"])
        A_Score(["Xem kết quả và nhật ký điểm"])
        A_Unlock(["Mở khóa điểm đã chốt"])
    end
    Admin --- A_Dashboard
    Admin --- A_Course
    Admin --- A_Class
    Admin --- A_Assign
    Admin --- A_Schedule
    Admin --- A_Teacher
    Admin --- A_Student
    Admin --- A_Enroll
    Admin --- A_Account
    Admin --- A_Reset
    Admin --- A_ResetRequest
    Admin --- A_Attendance
    Admin --- A_Score
    Admin --- A_Unlock
    A_Schedule -. "bao gồm" .-> A_Conflict
    A_Enroll -. "bao gồm" .-> A_Admission
    A_Unlock -. "cho phép giáo viên sửa lại" .-> A_Score
```

## 4. Biểu đồ lớp phân tích (mô hình miền)

Biểu đồ tập trung vào các thực thể dữ liệu và quan hệ chính đang được ánh xạ bằng SQLAlchemy.

```mermaid
classDiagram
    class User {
        +int id
        +string username
        +string role
        +string full_name
        +bool is_locked
    }
    class StudentProfile {
        +int id
        +string code
        +float entry_band
        +bool is_active
    }
    class TeacherProfile {
        +int id
        +float ielts_band
        +string skills
        +bool is_active
    }
    class Course {
        +int id
        +string code
        +float entry_band
        +float target_band
        +int sessions
        +int tuition
        +bool is_open
    }
    class ClassRoom {
        +int id
        +string code
        +string room
        +int max_size
        +string status
    }
    class Schedule {
        +int id
        +int weekday
        +string start_time
        +string end_time
    }
    class Enrollment {
        +int id
        +datetime enrolled_at
        +string status
    }
    class AttendanceRecord {
        +int id
        +date attendance_date
        +string status
    }
    class Homework {
        +int id
        +string title
        +datetime deadline
    }
    class HomeworkMaterial {
        +int id
        +string original_filename
        +string stored_filename
    }
    class HomeworkSubmission {
        +int id
        +datetime submitted_at
        +bool is_late
    }
    class HomeworkSubmissionFile {
        +int id
        +string original_filename
        +string stored_filename
    }
    class ScoreRecord {
        +int id
        +string term
        +float listening
        +float reading
        +float writing
        +float speaking
        +float overall
        +bool is_published
    }
    class ScoreLog {
        +int id
        +datetime changed_at
        +string action
        +string old_value
        +string new_value
    }
    class PasswordResetRequest {
        +int id
        +datetime created_at
        +bool handled
    }

    User "1" -- "0..1" StudentProfile : hồ sơ học viên
    User "1" -- "0..1" TeacherProfile : hồ sơ giáo viên
    User "1" -- "0..*" PasswordResetRequest : gửi yêu cầu
    User "1" -- "0..*" Homework : tạo bài tập
    User "1" -- "0..*" AttendanceRecord : ghi nhận
    User "0..1" -- "0..*" ScoreLog : thay đổi điểm
    Course "1" -- "0..*" ClassRoom : mở thành
    TeacherProfile "0..1" -- "0..*" ClassRoom : phụ trách
    ClassRoom "1" *-- "0..*" Schedule : có lịch
    StudentProfile "1" -- "0..*" Enrollment : ghi danh
    ClassRoom "1" -- "0..*" Enrollment : nhận học viên
    Enrollment "1" *-- "0..*" AttendanceRecord : điểm danh
    ClassRoom "1" -- "0..*" Homework : giao bài
    Homework "1" *-- "0..*" HomeworkMaterial : tài liệu
    Enrollment "1" -- "0..*" HomeworkSubmission : nộp bài
    Homework "1" -- "0..*" HomeworkSubmission : bài được giao
    HomeworkSubmission "1" *-- "0..*" HomeworkSubmissionFile : tệp nộp
    Enrollment "1" *-- "0..*" ScoreRecord : kết quả theo kỳ
    ScoreRecord "1" *-- "0..*" ScoreLog : lịch sử thay đổi
```

## 5. Biểu đồ hoạt động: ghi danh học viên vào lớp

```mermaid
flowchart TD
    Start([Bắt đầu]) --> Select[Quản trị viên chọn học viên và lớp]
    Select --> CheckStudent{Học viên và lớp có tồn tại hợp lệ?}
    CheckStudent -- Không --> RejectStudent[Thông báo lỗi, không ghi danh]
    CheckStudent -- Có --> CheckClass{Lớp còn nhận học viên?}
    CheckClass -- "Không: lớp đóng/hủy hoặc hết chỗ" --> RejectClass[Thông báo lỗi, không ghi danh]
    CheckClass -- Có --> CheckBand{Band đầu vào đạt yêu cầu khóa học?}
    CheckBand -- Không --> RejectBand[Thông báo band không đạt]
    CheckBand -- Có --> CheckDuplicate{Đã có ghi danh vào lớp này?}
    CheckDuplicate -- Có --> RejectDuplicate[Không tạo ghi danh trùng]
    CheckDuplicate -- Không --> Create[Khởi tạo ghi danh trạng thái đang học]
    Create --> Save[(Lưu Enrollment)]
    Save --> Success[Thông báo ghi danh thành công]
    RejectStudent --> End([Kết thúc])
    RejectClass --> End
    RejectBand --> End
    RejectDuplicate --> End
    Success --> End
```

## 6. Biểu đồ tuần tự: nhập và công bố điểm

```mermaid
sequenceDiagram
    actor GV as Giáo viên
    participant UI as Giao diện web
    participant App as Flask / Teacher blueprint
    participant DB as SQLite
    actor HV as Học viên
    participant StudentApp as Flask / Student blueprint

    GV->>UI: Nhập điểm 4 kỹ năng và nhận xét
    UI->>App: Gửi dữ liệu điểm
    App->>App: Kiểm tra quyền phụ trách lớp và giá trị điểm
    App->>App: Tính Overall theo quy tắc IELTS
    App->>DB: Lưu ScoreRecord và ScoreLog
    DB-->>App: Xác nhận lưu
    App-->>UI: Hiển thị kết quả đã lưu
    GV->>UI: Chốt và công bố điểm
    UI->>App: Yêu cầu công bố
    App->>App: Kiểm tra đủ điểm và quyền lớp
    App->>DB: Đánh dấu đã công bố, ghi nhật ký
    DB-->>App: Xác nhận
    App-->>UI: Thông báo chốt điểm
    HV->>StudentApp: Mở trang kết quả
    StudentApp->>DB: Đọc kết quả thuộc học viên
    DB-->>StudentApp: Các ScoreRecord
    StudentApp->>StudentApp: Lọc chỉ các kết quả đã công bố
    StudentApp-->>HV: Hiển thị điểm, nhận xét và biểu đồ
    UI-->>GV: Điểm đã chốt, Admin cần mở khóa nếu muốn sửa lại
```

## 7. Biểu đồ tuần tự: học viên nộp bài tập

```mermaid
sequenceDiagram
    actor HV as Học viên
    participant UI as Giao diện web
    participant App as Flask / Student blueprint
    participant FS as Thư mục lưu tệp riêng tư
    participant DB as SQLite

    HV->>UI: Chọn bài tập và tệp cần nộp
    UI->>App: Gửi yêu cầu nộp bài
    App->>DB: Kiểm tra bài tập và ghi danh của học viên
    DB-->>App: Bài tập và Enrollment
    App->>App: Kiểm tra trạng thái đang học và định dạng/kích thước tệp
    alt Dữ liệu không hợp lệ
        App-->>UI: Trả thông báo lỗi, yêu cầu gửi lại
    else Hợp lệ
        App->>FS: Lưu tệp tải lên
        FS-->>App: Tên tệp lưu trữ
        App->>App: So sánh thời điểm nộp với hạn bài tập
        App->>DB: Lưu HomeworkSubmission và HomeworkSubmissionFile
        DB-->>App: Xác nhận lưu
        App-->>UI: Hiển thị nộp thành công hoặc nộp muộn
    end
```

## 8. Biểu đồ thành phần và triển khai

```mermaid
flowchart TB
    Browser["Trình duyệt người dùng<br/>HTML / CSS / Bootstrap / JavaScript"]
    subgraph FlaskApp["Ứng dụng web Flask"]
        AppFactory["app.py<br/>Khởi tạo ứng dụng"]
        Auth["Blueprint xác thực"]
        Admin["Blueprint quản trị"]
        Teacher["Blueprint giáo viên"]
        Student["Blueprint học viên"]
        Domain["models.py<br/>SQLAlchemy và quy tắc miền"]
        Helpers["utils.py / homework_files.py<br/>Phân quyền, kiểm tra nghiệp vụ, xử lý tệp"]
        Templates["Jinja2 templates"]
    end
    Database[("SQLite<br/>instance/ielts_center.db")]
    Uploads[("Hệ thống tệp riêng tư<br/>instance/homework_uploads")]

    Browser <-->|HTTP request / response| AppFactory
    AppFactory --> Auth
    AppFactory --> Admin
    AppFactory --> Teacher
    AppFactory --> Student
    Auth --> Domain
    Admin --> Domain
    Teacher --> Domain
    Student --> Domain
    Auth --> Helpers
    Admin --> Helpers
    Teacher --> Helpers
    Student --> Helpers
    Auth --> Templates
    Admin --> Templates
    Teacher --> Templates
    Student --> Templates
    Domain <--> Database
    Helpers <--> Uploads
```

## 9. Quy tắc và giới hạn nghiệp vụ thể hiện trong thiết kế

- Giáo viên chỉ thao tác với lớp được phân công; học viên chỉ truy cập dữ liệu ghi danh của chính mình.
- Điểm kỹ năng nằm trong khoảng 0.0–9.0 theo bước 0.5; Overall là trung bình bốn kỹ năng và được làm tròn theo quy tắc band IELTS.
- Học viên chỉ xem được điểm đã công bố. Giáo viên không sửa được điểm đã chốt cho đến khi quản trị viên mở khóa.
- Ghi danh kiểm tra band đầu vào, trạng thái lớp, sĩ số; lịch học được kiểm tra xung đột giờ, giáo viên và phòng.
- Bài nộp được gắn cờ nộp muộn nếu thời điểm nộp vượt hạn. Điểm danh và tệp bài tập được giới hạn theo quyền/lớp tương ứng.
- Yêu cầu quên mật khẩu được lưu để quản trị viên xử lý thủ công; hệ thống không gửi email đặt lại tự động.
