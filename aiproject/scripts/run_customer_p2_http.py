"""P2 三组（repro app）：列表/分页/total、PATCH 双字段、跟进同 ID 三方一致。"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pymysql

ROOT = Path(__file__).resolve().parents[1]
MARKER = f"P2_HTTP_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
RUN_ID = uuid.uuid4().hex[:12]
SUITE = "p2_repro_app_auth_logic"

SOURCE_FINGERPRINT_PATHS = (
    "scripts/run_customer_p2_http.py",
    "tests/repro/asgi_app.py",
    "tests/repro/factory.py",
    "tests/repro/insecure_auth.py",
    "app/modules/consultant/repository.py",
    "app/modules/consultant/service.py",
    "app/modules/consultant/router.py",
)


def load_env_file() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def git_meta() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for key, cmd in (
            ("git_sha", ["git", "rev-parse", "HEAD"]),
            ("git_status_short", ["git", "status", "--short"]),
            ("git_diff_stat", ["git", "diff", "--stat"]),
        ):
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=10)
            out[key] = (r.stdout or "").strip() or (r.stderr or "").strip()
    except Exception as e:
        out["git_error"] = str(e)
    return out


def source_fingerprint() -> dict[str, Any]:
    h = hashlib.sha256()
    parts: list[str] = []
    missing: list[str] = []
    for rel in SOURCE_FINGERPRINT_PATHS:
        p = ROOT / rel
        if not p.is_file():
            missing.append(rel)
            continue
        raw = p.read_bytes()
        h.update(rel.encode())
        h.update(raw)
        parts.append(rel)
    return {
        "sha256": h.hexdigest() if parts else "",
        "files": parts,
        "missing": missing,
    }


def db_conn():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "education_service"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def db_lead(lead_id: int) -> dict | None:
    with db_conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT id, contact_info, intended_country, owner_employee_id, remark FROM crm_lead WHERE id=%s",
                (lead_id,),
            )
            return cur.fetchone()


def db_lead_count_owner_marker(owner: int, marker: str) -> int:
    with db_conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS c FROM crm_lead WHERE owner_employee_id=%s AND remark LIKE %s",
                (owner, f"%{marker}%"),
            )
            return int(cur.fetchone()["c"])


def db_follow_by_id(follow_id: int) -> dict | None:
    with db_conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT id, lead_id, employee_id, follow_type, content, next_plan FROM crm_follow_up WHERE id=%s",
                (follow_id,),
            )
            return cur.fetchone()


def db_follow_ids_for_lead_marker(lead_id: int, marker: str) -> list[int]:
    with db_conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT id FROM crm_follow_up WHERE lead_id=%s AND content LIKE %s ORDER BY id",
                (lead_id, f"%{marker}%"),
            )
            return [int(r["id"]) for r in cur.fetchall()]


def hdr(emp: int, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Employee-Id": str(emp),
        "Content-Type": "application/json",
    }


def add(results: list, case: str, outcome: str, **kw: Any) -> None:
    results.append({"case": case, "outcome": outcome, **kw})


def parse_envelope(resp: httpx.Response) -> tuple[bool, dict, dict]:
    """HTTP 200 + business code 0 + data object（可为空 dict，但必须是 dict）。"""
    if resp.status_code != 200:
        return False, {}, {}
    try:
        body = resp.json()
    except Exception:
        return False, {}, {}
    if not isinstance(body, dict) or body.get("code") != 0:
        return False, body if isinstance(body, dict) else {}, {}
    data = body.get("data")
    if not isinstance(data, dict):
        return False, body, {}
    return True, body, data


def api_data(resp: httpx.Response) -> dict:
    ok, _, data = parse_envelope(resp)
    return data if ok else {}


def paginate_all(
    base: str,
    emp: int,
    token: str,
    *,
    keyword: str | None,
    page_size: int,
    max_pages: int = 20,
) -> tuple[bool, list[dict], int | None, list[str]]:
    """逐页拉取；每页断言 items 长度 ≤ page_size，末页可更短。"""
    all_items: list[dict] = []
    total: int | None = None
    errors: list[str] = []
    for page in range(1, max_pages + 1):
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if keyword is not None:
            params["keyword"] = keyword
        rp = httpx.get(
            f"{base}/api/v1/consultant/leads",
            headers=hdr(emp, token),
            params=params,
            timeout=15,
        )
        ok, body, data = parse_envelope(rp)
        if not ok:
            errors.append(f"page={page} http={rp.status_code} body={body}")
            return False, all_items, total, errors
        items = data.get("items")
        if not isinstance(items, list):
            errors.append(f"page={page} missing items list")
            return False, all_items, total, errors
        if total is None:
            t = data.get("total")
            if not isinstance(t, int):
                errors.append(f"page={page} total not int")
                return False, all_items, total, errors
            total = t
        elif data.get("total") != total:
            errors.append(f"page={page} total drift")
            return False, all_items, total, errors
        if len(items) > page_size:
            errors.append(f"page={page} len(items)={len(items)} > page_size")
            return False, all_items, total, errors
        all_items.extend(items)
        if not items or len(all_items) >= (total or 0):
            break
    return True, all_items, total, errors


def follow_fields_equal(resp_row: dict, detail_row: dict, db_row: dict, expected: dict) -> bool:
    keys = ("id", "lead_id", "employee_id", "content", "follow_type", "next_plan")
    for k in keys:
        ev = expected.get(k)
        if resp_row.get(k) != ev or detail_row.get(k) != ev or db_row.get(k) != ev:
            return False
    return True


def main() -> int:
    started_at = datetime.now(timezone.utc).astimezone().isoformat()
    load_env_file()
    token = os.environ.get("AUTH_BEARER_TOKEN", "")
    if not token:
        print("BLOCKER: AUTH_BEARER_TOKEN")
        return 2

    port = pick_port()
    env = os.environ.copy()
    env.pop("EMPLOYEE_IDENTITY_MODE", None)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.repro.asgi_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    results: list[dict] = []
    leads_a: list[int] = []
    leads_b: list[int] = []
    patch_target: int | None = None

    try:
        ready = False
        for _ in range(40):
            if proc.poll() is not None:
                break
            try:
                if httpx.get(f"{base}/health/db", timeout=2).status_code == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.25)
        if not ready:
            add(results, "server_ready", "BLOCKED")
        else:
            kw_common = MARKER
            only_b = f"{MARKER}_ONLY_B"

            def create(emp: int, name: str, remark: str) -> int | None:
                r = httpx.post(
                    f"{base}/api/v1/consultant/leads",
                    headers=hdr(emp, token),
                    json={
                        "customer_name": name,
                        "owner_employee_id": emp,
                        "remark": remark,
                        "contact_info": f"1388{emp:02d}{len(remark) % 10000:04d}",
                    },
                    timeout=15,
                )
                d = api_data(r)
                return d.get("id") if r.status_code == 200 else None

            for suffix in ("1", "2"):
                lid = create(1, f"公共{kw_common}员工A{suffix}", f"{MARKER}_A{suffix}")
                if lid:
                    leads_a.append(lid)
            for suffix in ("1", "2"):
                lid = create(2, f"公共{kw_common}员工B{suffix}", f"{MARKER}_B{suffix}")
                if lid:
                    leads_b.append(lid)
            lid_ob = create(2, f"专属{only_b}", f"{MARKER}_Bonly")
            if lid_ob:
                leads_b.append(lid_ob)

            patch_target = leads_a[0] if leads_a else None
            add(
                results,
                "seed_leads",
                "PASS" if len(leads_a) >= 2 and len(leads_b) >= 2 else "FAIL",
                leads_a=leads_a,
                leads_b=leads_b,
            )

            expected_a = db_lead_count_owner_marker(1, MARKER)
            expected_b = db_lead_count_owner_marker(2, MARKER)

            ok_a, items_a, total_a, err_a = paginate_all(
                base, 1, token, keyword=kw_common, page_size=10
            )
            ids_a = {x["id"] for x in items_a}
            common_ok = (
                ok_a
                and ids_a == set(leads_a)
                and not ids_a.intersection(leads_b)
                and all(x.get("owner_employee_id") == 1 for x in items_a)
                and total_a == expected_a
                and total_a == len(leads_a)
            )
            add(
                results,
                "list_common_keyword_emp_a",
                "PASS" if common_ok else "FAIL",
                total=total_a,
                expected_total=expected_a,
                ids=sorted(ids_a),
                errors=err_a,
            )

            ok_b, items_b, total_b, err_b = paginate_all(
                base, 2, token, keyword=kw_common, page_size=10
            )
            ids_b = {x["id"] for x in items_b}
            common_b_ok = (
                ok_b
                and ids_b == set(leads_b)
                and not ids_b.intersection(leads_a)
                and all(x.get("owner_employee_id") == 2 for x in items_b)
                and total_b == expected_b
                and total_b == len(leads_b)
            )
            add(
                results,
                "list_common_keyword_emp_b",
                "PASS" if common_b_ok else "FAIL",
                total=total_b,
                expected_total=expected_b,
                ids=sorted(ids_b),
                errors=err_b,
            )

            def assert_paged_exact(
                emp: int, expected_ids: set[int], owner: int
            ) -> tuple[bool, list[int], list[str]]:
                page_size = 1
                n = len(expected_ids)
                got: list[int] = []
                errs: list[str] = []
                for page in range(1, n + 1):
                    params = {"keyword": kw_common, "page": page, "page_size": page_size}
                    rp = httpx.get(
                        f"{base}/api/v1/consultant/leads",
                        headers=hdr(emp, token),
                        params=params,
                        timeout=15,
                    )
                    ok, _, data = parse_envelope(rp)
                    if not ok:
                        errs.append(f"p{page}: envelope fail http={rp.status_code}")
                        continue
                    items = data.get("items") or []
                    expect_len = page_size if page < n else 1
                    if len(items) != expect_len:
                        errs.append(f"p{page}: len={len(items)} expected {expect_len}")
                    if data.get("total") != n:
                        errs.append(f"p{page}: total mismatch")
                    for it in items:
                        if it.get("owner_employee_id") != owner:
                            errs.append(f"p{page}: wrong owner")
                        got.append(it["id"])
                return not errs and set(got) == expected_ids, got, errs

            pag_a_ok, pages_a, pag_a_err = assert_paged_exact(1, set(leads_a), 1)
            add(
                results,
                "list_pagination_page_size_1_emp_a",
                "PASS" if pag_a_ok else "FAIL",
                pages=pages_a,
                errors=pag_a_err,
            )
            pag_b_ok, pages_b, pag_b_err = assert_paged_exact(2, set(leads_b), 2)
            add(
                results,
                "list_pagination_page_size_1_emp_b",
                "PASS" if pag_b_ok else "FAIL",
                pages=pages_b,
                errors=pag_b_err,
            )

            rz = httpx.get(
                f"{base}/api/v1/consultant/leads",
                headers=hdr(1, token),
                params={"keyword": only_b, "page": 1, "page_size": 20},
                timeout=15,
            )
            z_ok, _, zd = parse_envelope(rz)
            z_items = zd.get("items") if isinstance(zd.get("items"), list) else None
            z_total = zd.get("total")
            zero_ok = (
                z_ok
                and z_total == 0
                and z_items is not None
                and len(z_items) == 0
            )
            add(
                results,
                "list_opponent_exclusive_keyword_empty",
                "PASS" if zero_ok else "FAIL",
                http=rz.status_code,
                total=z_total,
            )

            ok_d, items_d, total_d, err_d = paginate_all(base, 1, token, keyword=None, page_size=50)
            marked = [x for x in items_d if MARKER in (x.get("remark") or "")]
            marked_ids = {x["id"] for x in marked}
            db_marked_count = expected_a
            default_ok = (
                ok_d
                and marked
                and marked_ids == set(leads_a)
                and all(x.get("owner_employee_id") == 1 for x in marked)
                and len(marked) == db_marked_count
            )
            add(
                results,
                "list_default_owner_scope_marked_subset",
                "PASS" if default_ok else "FAIL",
                n=len(marked),
                db_count=db_marked_count,
                errors=err_d,
            )

            r_forbid = httpx.get(
                f"{base}/api/v1/consultant/leads",
                headers=hdr(2, token),
                params={"owner_employee_id": 1},
                timeout=15,
            )
            add(results, "list_forbid_other_owner_filter", "PASS" if r_forbid.status_code == 403 else "FAIL")

            # PATCH 双字段
            if patch_target:
                new_contact = "13811112222"
                new_country = "英国"
                snap_before = db_lead(patch_target)
                rp = httpx.patch(
                    f"{base}/api/v1/consultant/leads/{patch_target}",
                    headers=hdr(1, token),
                    json={"contact_info": new_contact, "intended_country": new_country},
                    timeout=15,
                )
                p_ok, body, data = parse_envelope(rp)
                snap_db = db_lead(patch_target)
                det = httpx.get(f"{base}/api/v1/consultant/leads/{patch_target}", headers=hdr(1, token), timeout=15)
                d_ok, _, det_data = parse_envelope(det)
                lead_det = det_data.get("lead") or {} if d_ok else {}
                patch_ok = (
                    p_ok
                    and data.get("id") == patch_target
                    and data.get("contact_info") == new_contact
                    and data.get("intended_country") == new_country
                    and snap_db
                    and snap_db.get("contact_info") == new_contact
                    and snap_db.get("intended_country") == new_country
                    and lead_det.get("contact_info") == new_contact
                    and lead_det.get("intended_country") == new_country
                )
                add(
                    results,
                    "patch_own_two_fields_triple_match",
                    "PASS" if patch_ok else "FAIL",
                    response_fields={"contact_info": data.get("contact_info"), "intended_country": data.get("intended_country")},
                )

                snap_mid = db_lead(patch_target)
                rd = httpx.patch(
                    f"{base}/api/v1/consultant/leads/{patch_target}",
                    headers=hdr(2, token),
                    json={"contact_info": "13899999999"},
                    timeout=15,
                )
                snap_after = db_lead(patch_target)
                no_side = rd.status_code == 403 and snap_mid == snap_after
                add(
                    results,
                    "patch_other_forbidden_no_side_effect",
                    "PASS" if no_side else "FAIL",
                    before=snap_mid,
                    after=snap_after,
                )

            # 跟进同 ID
            if patch_target:
                content = f"跟进精确{MARKER}"
                next_plan = "回访"
                rf = httpx.post(
                    f"{base}/api/v1/consultant/leads/{patch_target}/follow-ups",
                    headers=hdr(1, token),
                    json={
                        "employee_id": 1,
                        "follow_type": "phone",
                        "content": content,
                        "next_plan": next_plan,
                    },
                    timeout=15,
                )
                f_ok, _, fdata = parse_envelope(rf)
                follow_id = fdata.get("id")
                row = db_follow_by_id(follow_id) if follow_id else None
                det = httpx.get(f"{base}/api/v1/consultant/leads/{patch_target}", headers=hdr(1, token), timeout=15)
                det_ok, _, det_data = parse_envelope(det)
                fus = det_data.get("follow_ups") or [] if det_ok else []
                fu = next((x for x in fus if x.get("id") == follow_id), None)
                expected_fu = {
                    "id": follow_id,
                    "lead_id": patch_target,
                    "employee_id": 1,
                    "content": content,
                    "follow_type": "phone",
                    "next_plan": next_plan,
                }
                triple_ok = (
                    f_ok
                    and follow_id
                    and row
                    and fu
                    and follow_fields_equal(fdata, fu, row, expected_fu)
                )
                add(
                    results,
                    "follow_up_same_id_field_match",
                    "PASS" if triple_ok else "FAIL",
                    follow_id=follow_id,
                    db_row=row,
                    detail_row=fu,
                )

                ids_before = db_follow_ids_for_lead_marker(patch_target, MARKER)
                rb = httpx.post(
                    f"{base}/api/v1/consultant/leads/{patch_target}/follow-ups",
                    headers=hdr(1, token),
                    json={"employee_id": 2, "content": f"冲突{MARKER}"},
                    timeout=15,
                )
                ids_after = db_follow_ids_for_lead_marker(patch_target, MARKER)
                add(
                    results,
                    "follow_body_employee_conflict",
                    "PASS" if rb.status_code == 403 and ids_before == ids_after else "FAIL",
                    ids_before=ids_before,
                    ids_after=ids_after,
                )

    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=15)

    finished_at = datetime.now(timezone.utc).astimezone().isoformat()
    required = [
        "list_common_keyword_emp_a",
        "list_common_keyword_emp_b",
        "list_pagination_page_size_1_emp_a",
        "list_pagination_page_size_1_emp_b",
        "list_opponent_exclusive_keyword_empty",
        "list_default_owner_scope_marked_subset",
        "list_forbid_other_owner_filter",
        "patch_own_two_fields_triple_match",
        "patch_other_forbidden_no_side_effect",
        "follow_up_same_id_field_match",
        "follow_body_employee_conflict",
    ]
    for c in required:
        if c not in {r["case"] for r in results}:
            add(results, c, "BLOCKED", reason="not run")
    fails = [r for r in results if r["outcome"] != "PASS"]
    exit_code = 0 if not fails else 1

    out = {
        "run_id": RUN_ID,
        "suite": SUITE,
        "layer": "application_auth_under_repro_not_trusted_identity",
        "marker": MARKER,
        "git": git_meta(),
        "source_fingerprint": source_fingerprint(),
        "python": sys.version.split()[0],
        "started_at": started_at,
        "finished_at": finished_at,
        "security_acceptance": "FAIL",
        "p2_isolation_http_auth_layer": "PASS" if exit_code == 0 else "FAIL",
        "results": results,
        "process_exit_code": exit_code,
    }
    body = f"# P2 HTTP（repro app）\n\nrun_id=`{RUN_ID}`\n\n```json\n{json.dumps(out, ensure_ascii=False, indent=2)}\n```\n"
    runs = ROOT / "docs" / "回复Cursor" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"p2-{RUN_ID}.md").write_text(body, encoding="utf-8")
    (ROOT / "docs" / "回复Cursor" / "25-P2-HTTP验收记录.md").write_text(body, encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
