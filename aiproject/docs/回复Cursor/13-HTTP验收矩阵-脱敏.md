# HTTP 验收矩阵（脱敏）

- 标记：`E2E_HTTP_20261111_172938`
- Python：3.10.4
- 退出判定：matrix_pass_excluding_known_defect=True
- **已知缺陷**：服务 token 可伪造员工头（见 spoof_defect 用例）

```json
{
  "marker": "E2E_HTTP_20261111_172938",
  "lead_id": 4,
  "python": "3.10.4",
  "timezone": "Asia/Shanghai",
  "started_at": "2026-11-11T17:29:43.827342+08:00",
  "script": "scripts/run_customer_http_matrix.py",
  "port": 8766,
  "matrix_results": [
    {
      "case": "happy_create",
      "expect": 200,
      "passed": true,
      "note": ""
    },
    {
      "case": "unauth_no_bearer",
      "expect": [
        401,
        503
      ],
      "passed": true,
      "note": ""
    },
    {
      "case": "unauth_wrong_bearer",
      "expect": 401,
      "passed": true,
      "note": ""
    },
    {
      "case": "missing_employee_header",
      "expect": 401,
      "passed": true,
      "note": ""
    },
    {
      "case": "forbidden_owner_body_mismatch",
      "expect": 403,
      "passed": true,
      "note": ""
    },
    {
      "case": "forbidden_emp2_detail",
      "expect": 403,
      "passed": true,
      "note": ""
    },
    {
      "case": "forbidden_emp2_status",
      "expect": 403,
      "passed": true,
      "note": ""
    },
    {
      "case": "forbidden_emp2_follow",
      "expect": 403,
      "passed": true,
      "note": ""
    },
    {
      "case": "spoof_defect_holder_can_act_as_emp1",
      "expect": "DEFECT",
      "passed": false,
      "note": "持有服务token即可伪造X-Employee-Id=1；非身份验收通过项"
    },
    {
      "case": "not_found_lead",
      "expect": 404,
      "passed": true,
      "note": ""
    },
    {
      "case": "invalid_status_enum",
      "expect": [
        400,
        422
      ],
      "passed": true,
      "note": ""
    },
    {
      "case": "illegal_transition",
      "expect": 409,
      "passed": true,
      "note": ""
    },
    {
      "case": "happy_follow_up",
      "expect": 200,
      "passed": true,
      "note": "crm_follow_up count=1"
    },
    {
      "case": "db_consistency",
      "expect": "SELECT",
      "passed": true,
      "note": "[{'id': 4, 'status': 'qualified', 'owner_employee_id': 1, 'remark': 'E2E_HTTP_20261111_172938'}]"
    },
    {
      "case": "no_token_config_503",
      "expect": 503,
      "passed": true,
      "note": "独立启动实例未配置 AUTH_BEARER_TOKEN"
    }
  ],
  "identity_defect_recorded": true,
  "matrix_pass_excluding_known_defect": true,
  "http_steps": [
    {
      "case": "happy_create",
      "status": 200,
      "body": {
        "code": 0,
        "message": "录入成功",
        "data": {
          "id": 4,
          "customer_name": "HTTP矩阵E2E_HTTP_20261111_172938",
          "contact_info": "139****9999",
          "gender": "U",
          "age": null,
          "education_level": null,
          "intended_country": "德国",
          "intended_major": null,
          "background_info": null,
          "source_channel": null,
          "status": "new",
          "owner_employee_id": 1,
          "last_contact_time": null,
          "lost_reason": null,
          "remark": "E2E_HTTP_20261111_172938",
          "create_time": "2026-11-11T17:29:40",
          "update_time": "2026-11-11T17:29:40"
        }
      }
    },
    {
      "case": "happy_list",
      "status": 200,
      "body": {
        "code": 0,
        "message": "ok",
        "data": {
          "total": 1,
          "page": 1,
          "page_size": 20,
          "items": [
            {
              "id": 4,
              "customer_name": "HTTP矩阵E2E_HTTP_20261111_172938",
              "contact_info": "139****9999",
              "gender": "U",
              "age": null,
              "education_level": null,
              "intended_country": "德国",
              "intended_major": null,
              "background_info": null,
              "source_channel": null,
              "status": "new",
              "owner_employee_id": 1,
              "last_contact_time": null,
              "lost_reason": null,
              "remark": "E2E_HTTP_20261111_172938",
              "create_time": "2026-11-11T17:29:40",
              "update_time": "2026-11-11T17:29:40"
            }
          ]
        }
      }
    },
    {
      "case": "happy_detail",
      "status": 200,
      "body": {
        "code": 0,
        "message": "ok",
        "data": {
          "lead": {
            "id": 4,
            "customer_name": "HTTP矩阵E2E_HTTP_20261111_172938",
            "contact_info": "139****9999",
            "gender": "U",
            "age": null,
            "education_level": null,
            "intended_country": "德国",
            "intended_major": null,
            "background_info": null,
            "source_channel": null,
            "status": "new",
            "owner_employee_id": 1,
            "last_contact_time": null,
            "lost_reason": null,
            "remark": "E2E_HTTP_20261111_172938",
            "create_time": "2026-11-11T17:29:40",
            "update_time": "2026-11-11T17:29:40"
          },
          "follow_ups": []
        }
      }
    },
    {
      "case": "happy_status",
      "status": 200,
      "body": {
        "code": 0,
        "message": "状态已更新",
        "data": {
          "id": 4,
          "customer_name": "HTTP矩阵E2E_HTTP_20261111_172938",
          "contact_info": "139****9999",
          "gender": "U",
          "age": null,
          "education_level": null,
          "intended_country": "德国",
          "intended_major": null,
          "background_info": null,
          "source_channel": null,
          "status": "contacting",
          "owner_employee_id": 1,
          "last_contact_time": null,
          "lost_reason": null,
          "remark": "E2E_HTTP_20261111_172938",
          "create_time": "2026-11-11T17:29:40",
          "update_time": "2026-11-11T17:29:40"
        }
      }
    },
    {
      "case": "happy_detail_after",
      "status": 200,
      "body": {
        "code": 0,
        "message": "ok",
        "data": {
          "lead": {
            "id": 4,
            "customer_name": "HTTP矩阵E2E_HTTP_20261111_172938",
            "contact_info": "139****9999",
            "gender": "U",
            "age": null,
            "education_level": null,
            "intended_country": "德国",
            "intended_major": null,
            "background_info": null,
            "source_channel": null,
            "status": "contacting",
            "owner_employee_id": 1,
            "last_contact_time": null,
            "lost_reason": null,
            "remark": "E2E_HTTP_20261111_172938",
            "create_time": "2026-11-11T17:29:40",
            "update_time": "2026-11-11T17:29:40"
          },
          "follow_ups": []
        }
      }
    },
    {
      "case": "happy_follow_up",
      "status": 200,
      "body": {
        "code": 0,
        "message": "跟进已保存",
        "data": {
          "id": 2,
          "lead_id": 4,
          "employee_id": 1,
          "follow_type": "phone",
          "content": "跟进-E2E_HTTP_20261111_172938",
          "next_plan": "回访",
          "create_time": "2026-11-11T17:29:40"
        }
      }
    },
    {
      "case": "unauth_no_bearer",
      "status": 401,
      "body": {
        "detail": "未认证"
      }
    },
    {
      "case": "unauth_wrong_bearer",
      "status": 401,
      "body": {
        "detail": "凭据无效"
      }
    },
    {
      "case": "missing_employee_header",
      "status": 401,
      "body": {
        "detail": "缺少可信员工身份（X-Employee-Id）"
      }
    },
    {
      "case": "forbidden_owner_body_mismatch",
      "status": 403,
      "body": {
        "detail": "仅可为本人名下录入客户"
      }
    },
    {
      "case": "forbidden_emp2_detail",
      "status": 403,
      "body": {
        "detail": "无权查看该客户"
      }
    },
    {
      "case": "forbidden_emp2_status",
      "status": 403,
      "body": {
        "detail": "仅负责顾问可更新该客户状态"
      }
    },
    {
      "case": "forbidden_emp2_follow",
      "status": 403,
      "body": {
        "detail": "无权跟进该客户"
      }
    },
    {
      "case": "spoof_defect_holder_can_act_as_emp1",
      "status": 200,
      "body": {
        "code": 0,
        "message": "状态已更新",
        "data": {
          "id": 4,
          "customer_name": "HTTP矩阵E2E_HTTP_20261111_172938",
          "contact_info": "139****9999",
          "gender": "U",
          "age": null,
          "education_level": null,
          "intended_country": "德国",
          "intended_major": null,
          "background_info": null,
          "source_channel": null,
          "status": "qualified",
          "owner_employee_id": 1,
          "last_contact_time": "2026-11-11T17:29:40",
          "lost_reason": null,
          "remark": "E2E_HTTP_20261111_172938",
          "create_time": "2026-11-11T17:29:40",
          "update_time": "2026-11-11T17:29:41"
        }
      }
    },
    {
      "case": "not_found_lead",
      "status": 404,
      "body": {
        "detail": "客户不存在"
      }
    },
    {
      "case": "invalid_status_enum",
      "status": 422,
      "body": {
        "detail": [
          {
            "type": "literal_error",
            "loc": [
              "body",
              "status"
            ],
            "msg": "Input should be 'new', 'contacting', 'qualified', 'signed' or 'lost'",
            "input": "not_a_valid_status",
            "ctx": {
              "expected": "'new', 'contacting', 'qualified', 'signed' or 'lost'"
            }
          }
        ]
      }
    },
    {
      "case": "illegal_transition_back_to_new",
      "status": 409,
      "body": {
        "detail": "不允许从 qualified 变更为 new"
      }
    },
    {
      "case": "no_token_config_503",
      "status": 503,
      "body": {
        "detail": "认证服务未配置（AUTH_BEARER_TOKEN 未设置），业务接口暂不可用"
      }
    }
  ],
  "db_leads": [
    {
      "id": 4,
      "status": "qualified",
      "owner_employee_id": 1,
      "remark": "E2E_HTTP_20261111_172938"
    }
  ]
}
```
