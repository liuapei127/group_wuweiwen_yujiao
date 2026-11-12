# 09 · Cursor 第五轮修复任务（依据 08 号）

1. **生产隔离**：`app.main` 移除 `insecure_header_repro` 运行时逻辑；复现仅 `tests.repro.asgi_app`。  
2. **main 反向验证**：设置 insecure 模式启动应失败（secure 矩阵 `main_rejects_insecure_mode`）。  
3. **repro 脚本**：必跑集、精确 KNOWN_DEFECT（200+状态写入）、`security_acceptance=FAIL`。  
4. **secure 扩展**：consultant 多路由 503 + 动态端口 + 进程存活检查。  
5. **CRM**：`19-CRM逐维差异表.md`；收窄 18 号结论表述。  
6. **04**：区分默认 blocked 与测试复现入口。  
7. **汇总**：`10-Cursor第五轮执行结果.md`。  
8. **P2 / 3.11 / 云**：继续标未执行。
