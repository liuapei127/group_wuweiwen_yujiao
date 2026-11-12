# P2 HTTP（repro app）

run_id=`6f81d1535b0e`

```json
{
  "run_id": "6f81d1535b0e",
  "suite": "p2_repro_app_auth_logic",
  "layer": "application_auth_under_repro_not_trusted_identity",
  "marker": "P2_HTTP_20261111_181743",
  "git": {
    "git_sha": "177df8fa856d537c38e84a7bc77a378eb263d328",
    "git_status_short": "M ../README.md\n?? ../.gitignore\n?? ../.uvicorn_test_pid.txt\n?? ./\n?? ../backend/\n?? ../鏁欒偛鏈嶅姟_0914/",
    "git_diff_stat": "README.md | 12 +++++++++++-\n 1 file changed, 11 insertions(+), 1 deletion(-)"
  },
  "source_fingerprint": {
    "sha256": "6129cda118d48ffc5e3bee5044cae33419c45677d6910b469034bd32e97b624f",
    "files": [
      "scripts/run_customer_p2_http.py",
      "tests/repro/asgi_app.py",
      "tests/repro/factory.py",
      "tests/repro/insecure_auth.py",
      "app/modules/consultant/repository.py",
      "app/modules/consultant/service.py",
      "app/modules/consultant/router.py"
    ],
    "missing": []
  },
  "python": "3.10.4",
  "started_at": "2026-11-11T18:17:43.801845+08:00",
  "finished_at": "2026-11-11T18:17:47.352827+08:00",
  "security_acceptance": "FAIL",
  "p2_isolation_http_auth_layer": "PASS",
  "results": [
    {
      "case": "seed_leads",
      "outcome": "PASS",
      "leads_a": [
        15,
        16
      ],
      "leads_b": [
        17,
        18,
        19
      ]
    },
    {
      "case": "list_common_keyword_emp_a",
      "outcome": "PASS",
      "total": 2,
      "expected_total": 2,
      "ids": [
        15,
        16
      ],
      "errors": []
    },
    {
      "case": "list_common_keyword_emp_b",
      "outcome": "PASS",
      "total": 3,
      "expected_total": 3,
      "ids": [
        17,
        18,
        19
      ],
      "errors": []
    },
    {
      "case": "list_pagination_page_size_1_emp_a",
      "outcome": "PASS",
      "pages": [
        16,
        15
      ],
      "errors": []
    },
    {
      "case": "list_pagination_page_size_1_emp_b",
      "outcome": "PASS",
      "pages": [
        19,
        18,
        17
      ],
      "errors": []
    },
    {
      "case": "list_opponent_exclusive_keyword_empty",
      "outcome": "PASS",
      "http": 200,
      "total": 0
    },
    {
      "case": "list_default_owner_scope_marked_subset",
      "outcome": "PASS",
      "n": 2,
      "db_count": 2,
      "errors": []
    },
    {
      "case": "list_forbid_other_owner_filter",
      "outcome": "PASS"
    },
    {
      "case": "patch_own_two_fields_triple_match",
      "outcome": "PASS",
      "response_fields": {
        "contact_info": "13811112222",
        "intended_country": "英国"
      }
    },
    {
      "case": "patch_other_forbidden_no_side_effect",
      "outcome": "PASS",
      "before": {
        "id": 15,
        "contact_info": "13811112222",
        "intended_country": "英国",
        "owner_employee_id": 1,
        "remark": "P2_HTTP_20261111_181743_A1"
      },
      "after": {
        "id": 15,
        "contact_info": "13811112222",
        "intended_country": "英国",
        "owner_employee_id": 1,
        "remark": "P2_HTTP_20261111_181743_A1"
      }
    },
    {
      "case": "follow_up_same_id_field_match",
      "outcome": "PASS",
      "follow_id": 5,
      "db_row": {
        "id": 5,
        "lead_id": 15,
        "employee_id": 1,
        "follow_type": "phone",
        "content": "跟进精确P2_HTTP_20261111_181743",
        "next_plan": "回访"
      },
      "detail_row": {
        "id": 5,
        "lead_id": 15,
        "employee_id": 1,
        "follow_type": "phone",
        "content": "跟进精确P2_HTTP_20261111_181743",
        "next_plan": "回访",
        "create_time": "2026-11-11T18:17:47"
      }
    },
    {
      "case": "follow_body_employee_conflict",
      "outcome": "PASS",
      "ids_before": [
        5
      ],
      "ids_after": [
        5
      ]
    }
  ],
  "process_exit_code": 0
}
```
