# 客户管理 HTTP E2E

时间：2026-11-11T17:18:18.000462

```json
{
  "marker": "E2E_HTTP_20261111_171814",
  "lead_id": 1,
  "http_steps": [
    {
      "step": "create",
      "status": 200,
      "body": {
        "code": 0,
        "message": "录入成功",
        "data": {
          "id": 1,
          "customer_name": "HTTP测评E2E_HTTP_20261111_171814",
          "contact_info": "13900009999",
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
          "remark": "E2E_HTTP_20261111_171814",
          "create_time": "2026-11-11T17:18:17",
          "update_time": "2026-11-11T17:18:17"
        }
      }
    },
    {
      "step": "list",
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
              "id": 1,
              "customer_name": "HTTP测评E2E_HTTP_20261111_171814",
              "contact_info": "13900009999",
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
              "remark": "E2E_HTTP_20261111_171814",
              "create_time": "2026-11-11T17:18:17",
              "update_time": "2026-11-11T17:18:17"
            }
          ]
        }
      }
    },
    {
      "step": "detail",
      "status": 200,
      "body": {
        "code": 0,
        "message": "ok",
        "data": {
          "lead": {
            "id": 1,
            "customer_name": "HTTP测评E2E_HTTP_20261111_171814",
            "contact_info": "13900009999",
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
            "remark": "E2E_HTTP_20261111_171814",
            "create_time": "2026-11-11T17:18:17",
            "update_time": "2026-11-11T17:18:17"
          },
          "follow_ups": []
        }
      }
    },
    {
      "step": "status",
      "status": 200,
      "body": {
        "code": 0,
        "message": "状态已更新",
        "data": {
          "id": 1,
          "customer_name": "HTTP测评E2E_HTTP_20261111_171814",
          "contact_info": "13900009999",
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
          "remark": "E2E_HTTP_20261111_171814",
          "create_time": "2026-11-11T17:18:17",
          "update_time": "2026-11-11T17:18:17"
        }
      }
    },
    {
      "step": "detail_after",
      "status": 200,
      "body": {
        "code": 0,
        "message": "ok",
        "data": {
          "lead": {
            "id": 1,
            "customer_name": "HTTP测评E2E_HTTP_20261111_171814",
            "contact_info": "13900009999",
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
            "remark": "E2E_HTTP_20261111_171814",
            "create_time": "2026-11-11T17:18:17",
            "update_time": "2026-11-11T17:18:17"
          },
          "follow_ups": []
        }
      }
    },
    {
      "step": "unauth_create",
      "status": 401,
      "body": "{\"detail\":\"未认证\"}"
    }
  ],
  "db_rows": [
    {
      "id": 1,
      "status": "contacting",
      "owner_employee_id": 1,
      "remark": "E2E_HTTP_20261111_171814"
    }
  ]
}
```
