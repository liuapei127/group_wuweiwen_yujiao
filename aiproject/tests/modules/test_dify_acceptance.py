from scripts.run_ent_dify_acceptance import evaluate_report


def test_acceptance_rejects_business_failure_even_if_commands_exit_zero():
    report={"pytest":{"exit_code":0},"api_from_dify_container":{"exit_code":0,"stdout":'{"status":"ok"}'},"api_host":{"health_status":200,"health":{"status":"ok"},"consultant_post_status":503}}
    assert all(evaluate_report(report).values())
    report["api_host"]["consultant_post_status"]=500
    assert not all(evaluate_report(report).values())
    report["api_host"]["consultant_post_status"]=503
    report["api_from_dify_container"]["stdout"]='<html>error</html>'
    assert not all(evaluate_report(report).values())
