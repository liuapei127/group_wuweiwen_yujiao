"""生成 XMind 可打开的 .xmind（ZIP：content + metadata + manifest）。"""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "企业智能助手-组会讲解.xmind"


def nid() -> str:
    return uuid.uuid4().hex[:24]


def leaf(title: str) -> dict:
    return {"id": nid(), "class": "topic", "title": title}


def branch(title: str, kids: list) -> dict:
    return {
        "id": nid(),
        "class": "topic",
        "title": title,
        "children": {"attached": kids},
    }


def build_tree() -> dict:
    return branch(
        "ENT 企业智能助手",
        [
            branch(
                "一分钟是啥",
                [
                    leaf("顾问用 Dify 对话"),
                    leaf("FastAPI 读写 MySQL"),
                    leaf("31 表 education_service"),
                    leaf("刘培阳: 接口+安全+文档"),
                ],
            ),
            branch(
                "业务需求",
                [
                    branch("ENT-01 录入客户", [leaf("POST /consultant/leads"), leaf("Dify 抽字段")]),
                    branch("ENT-02 档案跟进", [leaf("列表/详情/跟进"), leaf("P2 repro 已测签收")]),
                    branch("ENT-03 状态流转", [leaf("PATCH /status")]),
                    branch("ENT-04/05 日报", [leaf("Dify 语音→JSON"), leaf("API 只入库")]),
                    branch("ENT-09 请假审批", [leaf("需 STU 先提交"), leaf("pending/approve")]),
                    branch("ENT-11 NL2SQL", [leaf("白名单 intent"), leaf("禁止 raw SQL")]),
                    branch("ENT-12 指令", [leaf("/enterprise/commands"), leaf("action 尚不全")]),
                    branch("后期", [leaf("组织/新人/成绩"), leaf("投诉/主动待办")]),
                ],
            ),
            branch(
                "两条门（别搞混）",
                [
                    branch("app.main 正式入口", [
                        leaf("员工业务全 503"),
                        leaf("等可信 JWT"),
                        leaf("/health 200 探活"),
                    ]),
                    branch("tests.repro 演习场", [
                        leaf("测权限隔离"),
                        leaf("P2 限定签收"),
                        leaf("≠ 生产身份验收"),
                    ]),
                ],
            ),
            branch(
                "2026-11-11 进展",
                [
                    branch("Python 3.13", [leaf(".venv313"), leaf("Docker build 有证据")]),
                    branch("鉴权收口", [
                        leaf("日报/请假/指令/NL2SQL"),
                        leaf("与 consultant 同 503"),
                    ]),
                ],
            ),
            branch(
                "进度四态",
                [
                    leaf("已实现=有代码"),
                    leaf("已测试=有证据"),
                    leaf("已部署=云上可调"),
                    leaf("已验收=能对外说 OK"),
                ],
            ),
            branch(
                "跨模块要什么",
                [
                    branch("公共 auth", [leaf("JWT 契约"), leaf("填 04 三栏表")]),
                    branch("Dify", [leaf("企业 Chatflow"), leaf("education-api:8000")]),
                    leaf("STU 请假联调"),
                    leaf("RPT 日报字段对齐"),
                    leaf("运维 3.13 rebuild 上云"),
                ],
            ),
            branch(
                "当前阻塞",
                [
                    leaf("可信身份未落地"),
                    leaf("云业务 API 未上"),
                    leaf("Dify 未端到端"),
                    leaf("STU 全链路未联调"),
                ],
            ),
            branch(
                "下一步",
                [
                    leaf("1 指定 auth 负责人"),
                    leaf("2 云 rebuild API"),
                    leaf("3 JWT 后 app.main 回归"),
                    leaf("4 Dify+STU 联调"),
                ],
            ),
        ],
    )


def main() -> None:
    sheet_id = nid()
    root = build_tree()
    root["structureClass"] = "org.xmind.ui.map.clockwise"

    content = [
        {
            "id": sheet_id,
            "class": "sheet",
            "title": "ENT 组会讲解",
            "rootTopic": root,
        }
    ]

    manifest = {"file-entries": {"content.json": {}, "metadata.json": {}}}
    metadata = {
        "creator": {"name": "XMind", "version": "24.04.10311"},
        "activeSheetId": sheet_id,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False))
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False))

    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
