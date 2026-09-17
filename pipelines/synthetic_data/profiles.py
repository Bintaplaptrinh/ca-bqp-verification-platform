SURNAMES = ["Nguyễn","Trần","Lê","Phạm","Hoàng","Huỳnh","Phan","Vũ","Võ","Đặng","Bùi","Đỗ","Hồ","Ngô","Dương"]
MIDDLES = ["Văn","Thị","Minh","Quốc","Thanh","Đức","Gia","Anh","Ngọc","Hữu","Xuân","Tuấn","Khánh","Bảo"]
GIVEN = ["An","Bình","Cường","Dũng","Hà","Hải","Hạnh","Hiếu","Hùng","Khang","Lan","Linh","Long","Mai","Nam","Nga","Phúc","Quân","Sơn","Thảo","Trang","Trung","Tú","Vy"]

POSITIONS = {
    "BCA": ["Cán bộ","Chuyên viên","Đội trưởng","Phó Đội trưởng","Trưởng phòng","Kỹ thuật viên","Giảng viên"],
    "BQP": ["Sĩ quan","Quân nhân chuyên nghiệp","Cán bộ","Kỹ sư","Giảng viên","Trợ lý"],
    "OTHER": ["Nhân viên","Chuyên viên","Kỹ sư","Quản lý","Giảng viên"],
}

SUBJECT_GROUPS = {
    "BCA": ["CAND_OFFICER","CAND_NCO","PUBLIC_SECURITY_WORKER","CONTRACT_WORKER"],
    "BQP": ["MILITARY_OFFICER","PROFESSIONAL_MILITARY","DEFENCE_WORKER","CONTRACT_WORKER"],
    "OTHER": ["CIVILIAN_EMPLOYEE","PUBLIC_EMPLOYEE","CONTRACT_WORKER"],
}

EMPLOYMENT = ["ACTIVE","ACTIVE","ACTIVE","CONTRACT","TEMPORARY"]

TEMPLATES = [
    ("T01", "{name}, mã {code}, hiện công tác tại {unit}, chức vụ {position}."),
    ("T02", "Họ tên: {name}. Mã: {code}. Đơn vị công tác hiện tại: {unit}. Chức vụ: {position}."),
    ("T03", "{name} hiện đang làm việc tại {unit} với chức vụ {position}."),
]

HISTORY_TEMPLATES = [
    ("T04", "{name} trước đây công tác tại {former}, hiện công tác tại {unit}; chức vụ {position}."),
    ("T05", "Quá trình công tác: {name} từng thuộc {former}. Hiện nay công tác tại {unit}, vị trí {position}."),
]
