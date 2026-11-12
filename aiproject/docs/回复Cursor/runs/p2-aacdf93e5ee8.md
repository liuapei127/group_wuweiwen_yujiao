# P2 HTTP（repro app）

run_id=`aacdf93e5ee8`

```json
{
  "run_id": "aacdf93e5ee8",
  "suite": "p2_repro_app_auth_logic",
  "layer": "application_auth_under_repro_not_trusted_identity",
  "marker": "P2_HTTP_20261111_181354",
  "git": {
    "git_sha": "177df8fa856d537c38e84a7bc77a378eb263d328",
    "git_status_short": "M ../README.md\n?? ../.gitignore\n?? ../.uvicorn_test_pid.txt\n?? ./\n?? ../backend/\n?? ../鏁欒偛鏈嶅姟_0914/",
    "git_diff_stat": "README.md | 12 +++++++++++-\n 1 file changed, 11 insertions(+), 1 deletion(-)"
  },
  "python": "3.10.4",
  "started_at": "2026-11-11T18:13:54.791332+08:00",
  "finished_at": "2026-11-11T18:13:57.672541+08:00",
  "security_acceptance": "FAIL",
  "p2_isolation_http_auth_layer": "PASS",
  "results": [
    {
      "case": "seed_leads",
      "outcome": "PASS",
      "leads_a": [
        10,
        11
      ],
      "leads_b": [
        12,
        13,
        14
      ]
    },
    {
      "case": "list_common_keyword_emp_a",
      "outcome": "PASS",
      "total": 2,
      "expected_total": 2,
      "ids": [
        10,
        11
      ]
    },
    {
      "case": "list_common_keyword_emp_b",
      "outcome": "PASS",
      "ids": [
        12,
        13,
        14
      ]
    },
    {
      "case": "list_pagination_page_size_1",
      "outcome": "PASS",
      "pages": [
        11,
        10
      ]
    },
    {
      "case": "list_opponent_exclusive_keyword_empty",
      "outcome": "PASS",
      "total": 0
    },
    {
      "case": "list_default_owner_scope_marked_subset",
      "outcome": "PASS",
      "n": 2
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
        "id": 10,
        "contact_info": "13811112222",
        "intended_country": "英国",
        "owner_employee_id": 1,
        "remark": "P2_HTTP_20261111_181354_A1"
      },
      "after": {
        "id": 10,
        "contact_info": "13811112222",
        "intended_country": "英国",
        "owner_employee_id": 1,
        "remark": "P2_HTTP_20261111_181354_A1"
      }
    },
    {
      "case": "follow_up_same_id_field_match",
      "outcome": "PASS",
      "follow_id": 4,
      "db_row": {
        "id": 4,
        "lead_id": 10,
        "employee_id": 1,
        "follow_type": "phone",
        "content": "跟进精确P2_HTTP_20261111_181354",
        "next_plan": "回访"
      },
      "detail_row": {
        "id": 4,
        "lead_id": 10,
        "employee_id": 1,
        "follow_type": "phone",
        "content": "跟进精确P2_HTTP_20261111_181354",
        "next_plan": "回访",
        "create_time": "2026-11-11T18:13:57"
      }
    },
    {
      "case": "follow_body_employee_conflict",
      "outcome": "PASS",
      "ids_before": [
        4
      ],
      "ids_after": [
        4
      ]
    }
  ],
  "process_exit_code": 0
}
```
