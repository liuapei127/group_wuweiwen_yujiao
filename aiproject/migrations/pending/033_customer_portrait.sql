-- 客户画像保存《用户画像研判规则》中的属性。年龄和学历仍用原字段。
ALTER TABLE crm_lead
    ADD COLUMN portrait JSON NULL COMMENT '用户画像研判属性';
