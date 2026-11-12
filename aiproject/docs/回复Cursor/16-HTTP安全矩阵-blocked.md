# HTTP 安全矩阵（blocked）

run_id=`967a14227fa7`

```json
{
  "run_id": "967a14227fa7",
  "suite": "secure_blocked_identity",
  "app": "app.main:app",
  "python": "3.10.4",
  "started_at": "2026-11-11T17:59:59.008554+08:00",
  "finished_at": "2026-11-11T18:00:06.568358+08:00",
  "expected_case_set": [
    "health_db",
    "main_rejects_insecure_mode",
    "consultant_create_503",
    "consultant_list_503",
    "consultant_detail_503",
    "consultant_patch_lead_503",
    "consultant_status_503",
    "consultant_follow_503",
    "consultant_no_bearer_503",
    "empty_token_still_503"
  ],
  "results": {
    "health_db": {
      "expected": 200,
      "actual": 200,
      "outcome": "PASS"
    },
    "consultant_create_503": {
      "expected": 503,
      "actual": 503,
      "outcome": "PASS"
    },
    "consultant_list_503": {
      "expected": 503,
      "actual": 503,
      "outcome": "PASS"
    },
    "consultant_detail_503": {
      "expected": 503,
      "actual": 503,
      "outcome": "PASS"
    },
    "consultant_patch_lead_503": {
      "expected": 503,
      "actual": 503,
      "outcome": "PASS"
    },
    "consultant_status_503": {
      "expected": 503,
      "actual": 503,
      "outcome": "PASS"
    },
    "consultant_follow_503": {
      "expected": 503,
      "actual": 503,
      "outcome": "PASS"
    },
    "consultant_no_bearer_503": {
      "expected": 503,
      "actual": 503,
      "outcome": "PASS"
    },
    "main_rejects_insecure_mode": {
      "outcome": "PASS",
      "exit_code": 1,
      "stderr_tail_redacted": " 688, in _load_unlocked\r\n  File \"<frozen importlib._bootstrap_external>\", line 883, in exec_module\r\n  File \"<frozen importlib._bootstrap>\", line 241, in _call_with_frames_removed\r\n  File \"D:\\Project course\\group_wuweiwen_yujiao\\aiproject\\app\\main.py\", line 8, in <module>\r\n    raise RuntimeError(\r\nRuntimeError: app.main 不允许 EMPLOYEE_IDENTITY_MODE=insecure_header_repro；漏洞复现请使用 tests.repro.asgi_app\r\n"
    },
    "empty_token_still_503": {
      "expected": 503,
      "actual": 503,
      "outcome": "PASS",
      "note": "blocked 下非 token 专属分支"
    }
  },
  "process_exit_code": 0
}
```
