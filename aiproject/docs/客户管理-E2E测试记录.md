# 客户管理 E2E 测试记录

执行时间：2026-11-11T16:42:44

```json
{
  "entrypoint": "uvicorn app.main:app",
  "db_env_vars": [
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD"
  ],
  "test_customer_marker": "[E2E_TEST_20260311]",
  "auth_blocker": "无 modules/auth；测试未使用 X-Employee-Id 完成状态更新（避免伪造身份验收）",
  "db_verification": [
    {
      "id": 1,
      "customer_name": "测评客户[E2E_TEST_20260311]",
      "status": "contacting",
      "owner_employee_id": 1,
      "remark": "[E2E_TEST_20260311]"
    }
  ],
  "steps": [
    {
      "step": "0_health_db",
      "method": "GET",
      "path": "/health/db",
      "http_status": 200,
      "response_code": null,
      "response_message": null,
      "response_data": null
    },
    {
      "step": "1_create_lead",
      "method": "POST",
      "path": "/api/v1/consultant/leads",
      "http_status": 200,
      "response_code": 0,
      "response_message": "录入成功",
      "response_data": {
        "id": 1,
        "customer_name": "测评客户[E2E_TEST_20260311]",
        "contact_info": "139****1234",
        "gender": "U",
        "age": null,
        "education_level": null,
        "intended_country": "德国",
        "intended_major": "机械工程",
        "background_info": null,
        "source_channel": "E2E测试",
        "status": "new",
        "owner_employee_id": 1,
        "last_contact_time": null,
        "lost_reason": null,
        "remark": "[E2E_TEST_20260311]",
        "create_time": "2026-11-11T16:42:43",
        "update_time": "2026-11-11T16:42:43"
      }
    },
    {
      "step": "2_list_keyword",
      "method": "GET",
      "path": "/api/v1/consultant/leads?keyword=[E2E_TEST_20260311]&page_size=5",
      "http_status": 200,
      "response_code": 0,
      "response_message": "ok",
      "response_data": {
        "total": 1,
        "page": 1,
        "page_size": 5,
        "items": [
          {
            "id": 1,
            "customer_name": "测评客户[E2E_TEST_20260311]",
            "contact_info": "13900001234",
            "gender": "U",
            "age": null,
            "education_level": null,
            "intended_country": "德国",
            "intended_major": "机械工程",
            "background_info": null,
            "source_channel": "E2E测试",
            "status": "new",
            "owner_employee_id": 1,
            "last_contact_time": null,
            "lost_reason": null,
            "remark": "[E2E_TEST_20260311]",
            "create_time": "2026-11-11T16:42:43",
            "update_time": "2026-11-11T16:42:43"
          }
        ]
      }
    },
    {
      "step": "3_get_detail",
      "method": "GET",
      "path": "/api/v1/consultant/leads/1",
      "http_status": 200,
      "response_code": 0,
      "response_message": "ok",
      "response_data": {
        "lead": {
          "id": 1,
          "customer_name": "测评客户[E2E_TEST_20260311]",
          "contact_info": "139****1234",
          "gender": "U",
          "age": null,
          "education_level": null,
          "intended_country": "德国",
          "intended_major": "机械工程",
          "background_info": null,
          "source_channel": "E2E测试",
          "status": "new",
          "owner_employee_id": 1,
          "last_contact_time": null,
          "lost_reason": null,
          "remark": "[E2E_TEST_20260311]",
          "create_time": "2026-11-11T16:42:43",
          "update_time": "2026-11-11T16:42:43"
        },
        "follow_ups": []
      }
    },
    {
      "step": "4_status_contacting",
      "method": "PATCH",
      "path": "/api/v1/consultant/leads/1/status",
      "http_status": 200,
      "response_code": 0,
      "response_message": "状态已更新",
      "response_data": {
        "id": 1,
        "customer_name": "测评客户[E2E_TEST_20260311]",
        "contact_info": "139****1234",
        "gender": "U",
        "age": null,
        "education_level": null,
        "intended_country": "德国",
        "intended_major": "机械工程",
        "background_info": null,
        "source_channel": "E2E测试",
        "status": "contacting",
        "owner_employee_id": 1,
        "last_contact_time": null,
        "lost_reason": null,
        "remark": "[E2E_TEST_20260311]",
        "create_time": "2026-11-11T16:42:43",
        "update_time": "2026-11-11T16:42:44"
      }
    },
    {
      "step": "5_get_detail_after_status",
      "method": "GET",
      "path": "/api/v1/consultant/leads/1",
      "http_status": 200,
      "response_code": 0,
      "response_message": "ok",
      "response_data": {
        "lead": {
          "id": 1,
          "customer_name": "测评客户[E2E_TEST_20260311]",
          "contact_info": "139****1234",
          "gender": "U",
          "age": null,
          "education_level": null,
          "intended_country": "德国",
          "intended_major": "机械工程",
          "background_info": null,
          "source_channel": "E2E测试",
          "status": "contacting",
          "owner_employee_id": 1,
          "last_contact_time": null,
          "lost_reason": null,
          "remark": "[E2E_TEST_20260311]",
          "create_time": "2026-11-11T16:42:43",
          "update_time": "2026-11-11T16:42:44"
        },
        "follow_ups": []
      }
    },
    {
      "step": "4b_status_forbidden_demo",
      "method": "PATCH",
      "path": "/api/v1/consultant/leads/1/status",
      "http_status": 200,
      "response_code": 403,
      "response_message": "仅负责顾问可更新该客户状态",
      "response_data": null
    }
  ]
}
```
