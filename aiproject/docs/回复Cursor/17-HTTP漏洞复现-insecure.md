# 漏洞复现（tests.repro.asgi_app）

run_id=`15d43aa9c180` · security_acceptance=**FAIL**

```json
{
  "run_id": "15d43aa9c180",
  "suite": "tests.repro.asgi_app",
  "security_acceptance": "FAIL",
  "marker": "E2E_REPRO_20261111_175259",
  "lead_id": 7,
  "port": 63747,
  "python": "3.10.4",
  "started_at": "2026-11-11T17:52:59.370438+08:00",
  "finished_at": "2026-11-11T17:53:02.165008+08:00",
  "required_cases": [
    "create_has_id",
    "create_owner_and_status",
    "emp2_status_403",
    "emp2_no_side_effect",
    "spoof_repro"
  ],
  "results": [
    {
      "case": "create_has_id",
      "outcome": "PASS",
      "http_status": 200,
      "lead_id": 7
    },
    {
      "case": "create_owner_and_status",
      "outcome": "PASS",
      "snapshot": {
        "id": 7,
        "status": "new",
        "owner_employee_id": 1,
        "remark": "E2E_REPRO_20261111_175259"
      }
    },
    {
      "case": "emp2_status_403",
      "outcome": "PASS",
      "actual": 403
    },
    {
      "case": "emp2_no_side_effect",
      "outcome": "PASS"
    },
    {
      "case": "spoof_repro",
      "outcome": "KNOWN_DEFECT",
      "security_expected": "reject",
      "repro_http": 200,
      "before": {
        "id": 7,
        "status": "new",
        "owner_employee_id": 1,
        "remark": "E2E_REPRO_20261111_175259"
      },
      "after": {
        "id": 7,
        "status": "contacting",
        "owner_employee_id": 1,
        "remark": "E2E_REPRO_20261111_175259"
      }
    }
  ],
  "known_defects": 1,
  "exit_code": 0
}
```
