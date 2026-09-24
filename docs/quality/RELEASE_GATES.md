# Release Gates

Release bị chặn nếu một trong các điều kiện sau fail:

- 8 Golden Suites critical fail.
- Policy regression fail.
- Audit/evidence contract regression.
- Registry snapshot validation fail.
- False positive/conflict/unknown behavior regression.
- Migration upgrade/downgrade drill fail.
- Backup/restore drill chưa có biên bản gần release.
- Critical security finding chưa được xử lý/chấp nhận chính thức.
- Container/dependency scan fail theo CI policy.
- Readiness dependency fail ở staging.

Quality target là **precision + abstention đúng**, không tối ưu accuracy tổng bằng cách ép nhãn.
