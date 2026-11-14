-- Education Service MySQL 8 integration schema for a fresh local test database.
-- Structure only. No account records, credentials, business rows, or trigger definers.
SET NAMES utf8mb4;
SET @previous_foreign_key_checks = @@FOREIGN_KEY_CHECKS;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE `academic_deadline` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `student_id` bigint unsigned DEFAULT NULL COMMENT '学生ID（NULL=通用DDL）',
  `deadline_type` enum('paper','exam','application','visa','other') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'DDL类型',
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '节点名称',
  `description` text COLLATE utf8mb4_unicode_ci COMMENT '描述',
  `deadline` datetime NOT NULL COMMENT '截止时间',
  `reminder_enabled` tinyint NOT NULL DEFAULT '1' COMMENT '是否开启提醒',
  `reminder_days` json DEFAULT NULL COMMENT '提前提醒天数配置 [7,3,1]',
  `status` enum('pending','reminded','done','missed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT '状态',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_student_id` (`student_id`),
  KEY `idx_deadline` (`deadline`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学业关键节点/DDL表';

CREATE TABLE `application_progress` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `student_id` bigint unsigned NOT NULL COMMENT '学生ID',
  `target_school` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '目标院校',
  `target_major` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '目标专业',
  `stage` enum('document_prep','submitted','under_review','offer_received','visa_processing','enrolled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'document_prep' COMMENT '申请阶段',
  `progress_detail` text COLLATE utf8mb4_unicode_ci COMMENT '进度详情描述',
  `deadline` date DEFAULT NULL COMMENT '关键截止日期',
  `next_action` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '下一步操作',
  `handler_id` bigint unsigned DEFAULT NULL COMMENT '负责顾问ID',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_student_id` (`student_id`),
  KEY `idx_stage` (`stage`),
  KEY `idx_deadline` (`deadline`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='留学申请进度追踪表';

CREATE TABLE `auth_refresh_token` (
  `token_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `family_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` bigint unsigned NOT NULL,
  `expires_at` datetime NOT NULL,
  `used_at` datetime DEFAULT NULL,
  `revoked_at` datetime DEFAULT NULL,
  `replaced_by` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`token_hash`),
  KEY `idx_refresh_family` (`family_id`),
  KEY `idx_refresh_session` (`session_id`),
  KEY `idx_refresh_user` (`user_id`),
  CONSTRAINT `fk_refresh_session` FOREIGN KEY (`session_id`) REFERENCES `ent_auth_session` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `auth_service_client` (
  `client_id` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `display_name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('active','disabled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `secret_hash` binary(32) NOT NULL,
  `previous_secret_hash` binary(32) DEFAULT NULL,
  `previous_secret_expires_at` datetime(6) DEFAULT NULL,
  `create_time` datetime(6) NOT NULL,
  `update_time` datetime(6) NOT NULL,
  PRIMARY KEY (`client_id`),
  CONSTRAINT `chk_service_client_id` CHECK (regexp_like(`client_id`,_latin1'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')),
  CONSTRAINT `chk_service_previous_secret` CHECK ((((`previous_secret_hash` is null) and (`previous_secret_expires_at` is null)) or ((`previous_secret_hash` is not null) and (`previous_secret_expires_at` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `auth_service_client_audience` (
  `client_id` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `audience` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  PRIMARY KEY (`client_id`,`audience`),
  CONSTRAINT `fk_service_audience_client` FOREIGN KEY (`client_id`) REFERENCES `auth_service_client` (`client_id`),
  CONSTRAINT `chk_service_audience` CHECK ((`audience` in (_latin1'edu-api:ent',_latin1'edu-api:pf',_latin1'edu-api:cs',_latin1'edu-api:stu',_latin1'edu-api:rpt')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `auth_service_session` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_id` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `revoked_at` datetime(6) DEFAULT NULL,
  `create_time` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_service_session_client` (`client_id`),
  CONSTRAINT `fk_service_session_client` FOREIGN KEY (`client_id`) REFERENCES `auth_service_client` (`client_id`),
  CONSTRAINT `chk_service_session_ttl` CHECK (((`expires_at` > `create_time`) and (`expires_at` <= (`create_time` + interval 60 minute))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `auth_service_session_kid` (
  `session_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `kid` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `first_issued_at` datetime(6) NOT NULL,
  PRIMARY KEY (`session_id`,`kid`),
  KEY `idx_kid` (`kid`),
  CONSTRAINT `fk_service_session_kid` FOREIGN KEY (`session_id`) REFERENCES `auth_service_session` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `auth_user_session_kid` (
  `session_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `kid` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `first_issued_at` datetime NOT NULL,
  PRIMARY KEY (`session_id`,`kid`),
  KEY `idx_kid` (`kid`),
  CONSTRAINT `fk_user_session_kid` FOREIGN KEY (`session_id`) REFERENCES `ent_auth_session` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `chat_message` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '关联会话ID',
  `role` enum('user','assistant','system') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '消息角色',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '消息内容',
  `intent` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'AI识别的意图（业务查询/政策咨询/闲聊等）',
  `tokens_used` int DEFAULT NULL COMMENT '本次消耗Token数',
  `response_time_ms` int DEFAULT NULL COMMENT '响应耗时（毫秒）',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_session_id` (`session_id`),
  KEY `idx_intent` (`intent`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客服消息记录表';

CREATE TABLE `chat_session` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '会话唯一标识',
  `user_id` bigint unsigned DEFAULT NULL COMMENT '关联用户ID（已注册用户）',
  `visitor_name` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '访客昵称',
  `visitor_contact` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '访客联系方式（用于线索收集）',
  `status` enum('active','closed','timeout') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active' COMMENT '会话状态',
  `last_message_time` datetime DEFAULT NULL COMMENT '最后一条消息时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `close_time` datetime DEFAULT NULL COMMENT '会话关闭时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_id` (`session_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_status` (`status`),
  KEY `idx_last_message` (`last_message_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客服会话表';

CREATE TABLE `course_project` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `project_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '项目/课程名称',
  `category` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '类别（语言培训/背景提升/硕博连读等）',
  `description` text COLLATE utf8mb4_unicode_ci COMMENT '项目详情介绍',
  `target_audience` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '适合人群/学历要求',
  `price` decimal(10,2) DEFAULT NULL COMMENT '价格',
  `duration` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '课程周期',
  `tags` json DEFAULT NULL COMMENT '标签（用于匹配推荐）',
  `status` tinyint NOT NULL DEFAULT '1' COMMENT '状态 1=上架 0=下架',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_category` (`category`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='课程与项目表';

CREATE TABLE `crm_follow_up` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `lead_id` bigint unsigned NOT NULL COMMENT '关联意向客户ID',
  `employee_id` bigint unsigned NOT NULL COMMENT '跟进人ID',
  `follow_type` enum('phone','wechat','meeting','email','other') COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '跟进方式',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '跟进记录内容',
  `next_plan` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '下次跟进计划',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_lead_id` (`lead_id`),
  KEY `idx_employee_id` (`employee_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户跟进记录表';

CREATE TABLE `crm_lead` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `customer_name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '客户姓名',
  `contact_info` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '联系方式（手机/邮箱）',
  `gender` enum('M','F','U') COLLATE utf8mb4_unicode_ci DEFAULT 'U' COMMENT '性别',
  `age` int DEFAULT NULL COMMENT '年龄',
  `education_level` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '学历层次',
  `intended_country` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '意向国家（多值逗号分隔）',
  `intended_major` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '意向专业',
  `background_info` text COLLATE utf8mb4_unicode_ci COMMENT '客户背景与档案',
  `customer_profile_id` bigint unsigned DEFAULT NULL COMMENT '关联客户画像ID',
  `source_channel` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '来源渠道（线上/线下/转介绍等）',
  `status` enum('new','contacting','qualified','signed','lost') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'new' COMMENT '流转状态',
  `owner_employee_id` bigint unsigned NOT NULL COMMENT '负责员工ID',
  `last_contact_time` datetime DEFAULT NULL COMMENT '最后联系时间',
  `lost_reason` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '流失原因',
  `remark` text COLLATE utf8mb4_unicode_ci COMMENT '备注',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_status` (`status`),
  KEY `idx_owner` (`owner_employee_id`),
  KEY `idx_customer_profile` (`customer_profile_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='意向客户表';

CREATE TABLE `customer_profile` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `customer_name` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '客户姓名',
  `contact_info` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '联系方式',
  `source_id` bigint unsigned DEFAULT NULL COMMENT '关联客户信息来源ID',
  `background_info` json DEFAULT NULL COMMENT '客户背景信息结构化数据（学历/年龄/意向国家等）',
  `match_result` enum('matched','partial','not_matched') COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '匹配结果',
  `matched_product` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '匹配的产品线',
  `match_score` decimal(5,2) DEFAULT NULL COMMENT '匹配度评分（0-100）',
  `match_reason` text COLLATE utf8mb4_unicode_ci COMMENT 'AI研判原因说明',
  `recommended_programs` json DEFAULT NULL COMMENT '推荐的专业/项目列表',
  `evaluator_id` bigint unsigned DEFAULT NULL COMMENT '研判人/操作人ID',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_source_id` (`source_id`),
  KEY `idx_match_result` (`match_result`),
  KEY `idx_matched_product` (`matched_product`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户画像研判结果表';

CREATE TABLE `customer_source` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `source_type` enum('text','pdf_resume','excel','import','manual') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '信息来源类型',
  `raw_content` text COLLATE utf8mb4_unicode_ci COMMENT '原始文本内容',
  `file_url` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '上传文件URL（PDF/Excel）',
  `file_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '原始文件名',
  `parse_status` enum('pending','success','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT '解析状态',
  `parse_result` json DEFAULT NULL COMMENT 'AI解析后的结构化结果',
  `parse_error` text COLLATE utf8mb4_unicode_ci COMMENT '解析失败原因',
  `operator_id` bigint unsigned DEFAULT NULL COMMENT '操作人ID',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_source_type` (`source_type`),
  KEY `idx_parse_status` (`parse_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户信息来源记录表';

CREATE TABLE `employee_daily_report` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `employee_id` bigint unsigned NOT NULL COMMENT '员工ID',
  `report_date` date NOT NULL COMMENT '日报所属日期',
  `raw_content` text COLLATE utf8mb4_unicode_ci COMMENT '原始口述/输入内容',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'AI结构化后的日报文本',
  `key_progress` json DEFAULT NULL COMMENT 'AI提取的核心进展',
  `risks` json DEFAULT NULL COMMENT 'AI识别的潜在风险',
  `next_plan` text COLLATE utf8mb4_unicode_ci COMMENT '明日计划',
  `status` enum('draft','submitted') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft' COMMENT '状态',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_employee_date` (`employee_id`,`report_date`),
  KEY `idx_report_date` (`report_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='员工日报表';

CREATE TABLE `ent_ai_conversation` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `employee_id` bigint NOT NULL,
  `title` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `pending` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `version` int NOT NULL,
  `busy_token` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `busy_until` datetime DEFAULT NULL,
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_ent_ai_conversation_employee_id` (`employee_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `ent_ai_message` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `conversation_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `metadata_json` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `create_time` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_ent_ai_message_conversation_id` (`conversation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `ent_auth_audit` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `actor_id` bigint DEFAULT NULL,
  `action` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `details` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `create_time` datetime NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `ent_auth_login_attempt` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `attempt_key` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `create_time` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_ent_auth_login_attempt_attempt_key` (`attempt_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `ent_auth_role_permission` (
  `role_id` bigint NOT NULL,
  `permission` varchar(96) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`role_id`,`permission`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `ent_auth_session` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` bigint NOT NULL,
  `expires_at` datetime NOT NULL,
  `revoked_at` datetime DEFAULT NULL,
  `create_time` datetime NOT NULL,
  `last_used_at` datetime DEFAULT NULL,
  `parent_session_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_ent_auth_session_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `ent_auth_student_scope` (
  `user_id` bigint NOT NULL,
  `student_id` bigint NOT NULL,
  PRIMARY KEY (`user_id`,`student_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `event_lecture` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `event_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '活动/讲座名称',
  `event_type` enum('online','offline','hybrid') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '类型',
  `description` text COLLATE utf8mb4_unicode_ci COMMENT '活动详情',
  `start_time` datetime NOT NULL COMMENT '开始时间',
  `end_time` datetime DEFAULT NULL COMMENT '结束时间',
  `location` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '地点或线上链接',
  `max_participants` int DEFAULT NULL COMMENT '最大报名人数',
  `current_participants` int NOT NULL DEFAULT '0' COMMENT '当前报名人数',
  `organizer_id` bigint unsigned DEFAULT NULL COMMENT '组织者ID',
  `status` enum('upcoming','ongoing','ended','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'upcoming' COMMENT '活动状态',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_event_type` (`event_type`),
  KEY `idx_status` (`status`),
  KEY `idx_start_time` (`start_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='活动与讲座表';

CREATE TABLE `event_registration` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `event_id` bigint unsigned NOT NULL COMMENT '关联活动ID',
  `user_id` bigint unsigned DEFAULT NULL COMMENT '报名用户ID（注册用户）',
  `customer_name` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '报名客户姓名（未注册用户）',
  `contact_info` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '联系方式',
  `status` enum('registered','attended','cancelled','no_show') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'registered' COMMENT '报名状态',
  `remark` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '备注',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `customer_id` bigint DEFAULT NULL,
  `cancelled_at` datetime DEFAULT NULL,
  `attended_at` datetime DEFAULT NULL,
  `checked_in_by` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_event_user` (`event_id`,`user_id`),
  UNIQUE KEY `uq_event_customer` (`event_id`,`customer_id`),
  KEY `idx_event_id` (`event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='活动报名表';

CREATE TABLE `intent_config` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `intent_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '意图编码',
  `intent_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '意图名称',
  `scene` enum('customer_service','enterprise','student') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '适用场景',
  `system_prompt` text COLLATE utf8mb4_unicode_ci COMMENT '该意图对应的系统提示词',
  `routing_rule` json DEFAULT NULL COMMENT '路由规则配置',
  `status` tinyint NOT NULL DEFAULT '1' COMMENT '状态 1=启用 0=禁用',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_intent_scene` (`intent_code`,`scene`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI意图识别配置表';

CREATE TABLE `knowledge_base` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `category` enum('company_info','business','policy','faq','overseas_life') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '知识分类',
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '文档标题',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '文档内容',
  `source_file` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '来源文件路径/URL',
  `chunk_index` int NOT NULL DEFAULT '0' COMMENT '切片序号',
  `embedding_vector` blob COMMENT '向量化存储（用于RAG检索）',
  `status` tinyint NOT NULL DEFAULT '1' COMMENT '状态 1=启用 0=禁用',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_category` (`category`),
  FULLTEXT KEY `ft_content` (`title`,`content`) /*!50100 WITH PARSER `ngram` */
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库文档表';

CREATE TABLE `notification_log` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id` bigint unsigned NOT NULL COMMENT '接收人ID',
  `notification_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '通知类型',
  `related_type` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '关联业务类型',
  `related_id` bigint unsigned DEFAULT NULL COMMENT '关联业务ID',
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '通知标题',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '通知内容',
  `channel` enum('system','email','sms','wechat') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'system' COMMENT '通知渠道',
  `status` enum('pending','sent','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT '发送状态',
  `error_message` text COLLATE utf8mb4_unicode_ci COMMENT '失败原因',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `dedup_key` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_notification_dedup` (`dedup_key`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_status` (`status`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='提醒通知记录表';

CREATE TABLE `onboarding_guide` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '指引标题',
  `category` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '分类（入职指南/规章制度/业务流程等）',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '指引内容',
  `embedding_vector` blob COMMENT '向量化存储（用于RAG检索）',
  `sort_order` int NOT NULL DEFAULT '0' COMMENT '排序权重',
  `status` tinyint NOT NULL DEFAULT '1' COMMENT '状态 1=启用 0=禁用',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='新人入职指引知识库';

CREATE TABLE `overseas_life_knowledge` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `country` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家',
  `category` enum('medical','transport','emergency','daily_life','other') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '分类',
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '知识标题',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '知识内容',
  `embedding_vector` blob COMMENT '向量化存储',
  `status` tinyint NOT NULL DEFAULT '1' COMMENT '状态 1=启用 0=禁用',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_country` (`country`),
  KEY `idx_category` (`category`),
  FULLTEXT KEY `ft_knowledge` (`title`,`content`) /*!50100 WITH PARSER `ngram` */
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='海外生活知识库';

CREATE TABLE `profile_rule` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `product_line` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '产品线（如：留学申请/背景提升/硕博连读）',
  `rule_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '规则名称',
  `rule_content` json NOT NULL COMMENT '研判规则配置（JSON格式，含学历/语言/年龄等条件）',
  `match_prompt` text COLLATE utf8mb4_unicode_ci COMMENT 'AI研判使用的系统提示词',
  `priority` tinyint NOT NULL DEFAULT '0' COMMENT '优先级 数值越大越优先',
  `status` tinyint NOT NULL DEFAULT '1' COMMENT '状态 1=启用 0=禁用',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_product_line` (`product_line`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户画像研判规则表';

CREATE TABLE `report_generation` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `report_type` enum('customer_ops','daily_summary','weekly_summary','psych_weekly','complaint_weekly') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '报告类型',
  `report_title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '报告标题',
  `report_content` json DEFAULT NULL COMMENT '报告内容（结构化数据）',
  `report_html` mediumtext COLLATE utf8mb4_unicode_ci COMMENT '报告HTML渲染内容',
  `period_start` date DEFAULT NULL COMMENT '统计周期起始',
  `period_end` date DEFAULT NULL COMMENT '统计周期结束',
  `generated_by` bigint unsigned DEFAULT NULL COMMENT '生成人ID',
  `status` enum('generating','completed','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'generating' COMMENT '生成状态',
  `error_message` text COLLATE utf8mb4_unicode_ci COMMENT '失败原因',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_report_type` (`report_type`),
  KEY `idx_period` (`period_start`,`period_end`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报告生成记录表';

CREATE TABLE `report_schedule` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `report_type` enum('customer_ops','daily_summary','weekly_summary','psych_weekly','complaint_weekly') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '报告类型',
  `schedule_cron` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Cron表达式',
  `recipients` json NOT NULL COMMENT '接收人列表（用户ID数组）',
  `enabled` tinyint NOT NULL DEFAULT '1' COMMENT '是否启用 1=启用 0=禁用',
  `last_run_time` datetime DEFAULT NULL COMMENT '上次执行时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_report_type` (`report_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报告定时任务配置表';

CREATE TABLE `student_admin_service` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `student_id` bigint unsigned NOT NULL COMMENT '学生ID',
  `service_type` enum('leave','exam_query','other') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '服务类型',
  `leave_type` enum('sick','personal','emergency') COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '请假类型（仅请假时有效）',
  `start_time` datetime DEFAULT NULL COMMENT '开始时间',
  `end_time` datetime DEFAULT NULL COMMENT '结束时间',
  `reason` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '申请事由',
  `attachment_url` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '附件URL（如病假证明）',
  `status` enum('pending','approved','rejected','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT '审批状态',
  `approver_id` bigint unsigned DEFAULT NULL COMMENT '审批人/班主任ID',
  `approval_comment` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '审批意见',
  `approval_time` datetime DEFAULT NULL COMMENT '审批时间',
  `related_academic_id` bigint unsigned DEFAULT NULL COMMENT '关联教务数据ID',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_student_id` (`student_id`),
  KEY `idx_status` (`status`),
  KEY `idx_service_type` (`service_type`),
  KEY `idx_approver` (`approver_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生行政服务表（请假/考务等申请）';

CREATE TABLE `student_feedback_ticket` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `student_id` bigint unsigned NOT NULL COMMENT '学生ID',
  `ticket_type` enum('complaint','suggestion','consult') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'complaint' COMMENT '工单类型',
  `category` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '投诉分类（签证办理/院校申请/生活服务/其他）',
  `title` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '工单标题',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '投诉/反馈内容摘要',
  `detail` text COLLATE utf8mb4_unicode_ci COMMENT '详细反馈内容',
  `status` enum('pending','processing','resolved','closed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT '处理进度',
  `priority` enum('low','medium','high','urgent') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'medium' COMMENT '优先级',
  `assignee_id` bigint unsigned DEFAULT NULL COMMENT '指派处理人ID',
  `solution` text COLLATE utf8mb4_unicode_ci COMMENT '最终解决方案',
  `satisfaction` tinyint DEFAULT NULL COMMENT '满意度评分（1-5星）',
  `is_notified` tinyint NOT NULL DEFAULT '0' COMMENT '是否已通知学生（0否 1是）',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_student_id` (`student_id`),
  KEY `idx_status` (`status`),
  KEY `idx_category` (`category`),
  KEY `idx_assignee` (`assignee_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='售后反馈工单表';

CREATE TABLE `student_info` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id` bigint unsigned NOT NULL COMMENT '关联用户ID',
  `student_no` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '学号',
  `school` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '所在院校',
  `major` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '专业',
  `grade` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '年级',
  `abroad_country` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '留学国家',
  `class_teacher_id` bigint unsigned DEFAULT NULL COMMENT '班主任ID',
  `enroll_date` date DEFAULT NULL COMMENT '入学日期',
  `status` enum('active','graduated','suspended','withdrawn') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active' COMMENT '学生状态',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_id` (`user_id`),
  KEY `idx_class_teacher` (`class_teacher_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生信息扩展表';

CREATE TABLE `student_psych_alert` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `student_id` bigint unsigned NOT NULL COMMENT '学生ID',
  `trigger_reason` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '触发原因（AI提取的关键词或原句）',
  `risk_level` enum('low','medium','high') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '风险等级',
  `status` enum('pending','following','resolved','dismissed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT '处理状态',
  `teacher_id` bigint unsigned DEFAULT NULL COMMENT '负责跟进的老师ID',
  `follow_record` text COLLATE utf8mb4_unicode_ci COMMENT '跟进记录',
  `resolved_time` datetime DEFAULT NULL COMMENT '解除时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_student_id` (`student_id`),
  KEY `idx_risk_level` (`risk_level`),
  KEY `idx_status` (`status`),
  KEY `idx_teacher_id` (`teacher_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='心理预警表';

CREATE TABLE `student_psych_profile` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `student_id` bigint unsigned NOT NULL COMMENT '学生ID',
  `latest_emotion_tag` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '最新情绪标签（焦虑/平稳/低落等）',
  `emotion_score` int DEFAULT NULL COMMENT '情绪分值（0-100，分值越高越积极）',
  `last_interaction_time` datetime DEFAULT NULL COMMENT '最近一次交互时间',
  `risk_level` enum('low','medium','high') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'low' COMMENT '风险等级',
  `weekly_summary` json DEFAULT NULL COMMENT '本周心理状态摘要',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_student_id` (`student_id`),
  KEY `idx_risk_level` (`risk_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='心理健康画像表';

CREATE TABLE `student_psych_record` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `student_id` bigint unsigned NOT NULL COMMENT '学生ID',
  `emotion_tag` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '情绪标签',
  `emotion_score` int DEFAULT NULL COMMENT '情绪分值（0-100）',
  `interaction_content` text COLLATE utf8mb4_unicode_ci COMMENT '交互内容摘要',
  `trigger_keywords` json DEFAULT NULL COMMENT 'AI提取的触发关键词',
  `record_date` date NOT NULL COMMENT '记录日期',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_student_date` (`student_id`,`record_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='心理健康记录表';

CREATE TABLE `student_score` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `student_id` bigint unsigned NOT NULL COMMENT '学生ID（关联sys_user）',
  `course_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '课程名称',
  `score` decimal(5,2) NOT NULL COMMENT '成绩',
  `semester` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '学期（如 2025-2026-1）',
  `credit` decimal(3,1) DEFAULT NULL COMMENT '学分',
  `recorded_by` bigint unsigned DEFAULT NULL COMMENT '录入人ID',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `exam_key` varchar(96) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `submission_key` varchar(96) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `submission_hash` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `version` int NOT NULL DEFAULT '1',
  `update_time` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_score_exam` (`student_id`,`exam_key`),
  UNIQUE KEY `uk_score_submission` (`student_id`,`submission_key`),
  KEY `idx_student_id` (`student_id`),
  KEY `idx_semester` (`semester`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生成绩表';

CREATE TABLE `student_score_history` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `score_id` bigint unsigned NOT NULL,
  `version` int NOT NULL,
  `operation` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_by` bigint unsigned DEFAULT NULL,
  `change_reason` text COLLATE utf8mb4_unicode_ci,
  `before_data` json DEFAULT NULL,
  `after_data` json NOT NULL,
  `create_time` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_score_history_version` (`score_id`,`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `sys_org_member` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `org_id` bigint unsigned NOT NULL,
  `effective_from` datetime NOT NULL,
  `effective_to` datetime DEFAULT NULL,
  `status` enum('active','inactive') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_member_id_user` (`id`,`user_id`),
  UNIQUE KEY `uk_user_org` (`user_id`,`org_id`),
  KEY `fk_member_org` (`org_id`),
  CONSTRAINT `fk_member_org` FOREIGN KEY (`org_id`) REFERENCES `sys_organization` (`id`),
  CONSTRAINT `fk_member_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `chk_member_window` CHECK (((`effective_to` is null) or (`effective_to` > `effective_from`)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `sys_org_member_history` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `member_id` bigint unsigned NOT NULL,
  `user_id` bigint unsigned NOT NULL,
  `org_id` bigint unsigned NOT NULL,
  `change_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `status_before` enum('active','inactive') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status_after` enum('active','inactive') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `effective_from_before` datetime DEFAULT NULL,
  `effective_to_before` datetime DEFAULT NULL,
  `effective_from_after` datetime NOT NULL,
  `effective_to_after` datetime DEFAULT NULL,
  `primary_pointer_cleared` tinyint(1) NOT NULL DEFAULT '0',
  `actor_type` enum('user','system') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_user_id` bigint unsigned DEFAULT NULL,
  `changed_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_org_hist_user` (`user_id`,`changed_at`),
  KEY `idx_org_hist_org` (`org_id`,`changed_at`),
  KEY `idx_org_hist_member` (`member_id`,`changed_at`),
  KEY `fk_org_hist_actor` (`actor_user_id`),
  CONSTRAINT `fk_org_hist_actor` FOREIGN KEY (`actor_user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `fk_org_hist_org` FOREIGN KEY (`org_id`) REFERENCES `sys_organization` (`id`),
  CONSTRAINT `fk_org_hist_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `chk_org_hist_actor` CHECK ((((`actor_type` = _latin1'system') and (`actor_user_id` is null)) or ((`actor_type` = _latin1'user') and (`actor_user_id` is not null)))),
  CONSTRAINT `chk_org_hist_created` CHECK ((((`change_type` = _latin1'member_created') and (`status_before` is null) and (`effective_from_before` is null) and (`effective_to_before` is null)) or ((`change_type` <> _latin1'member_created') and (`status_before` is not null) and (`effective_from_before` is not null)))),
  CONSTRAINT `chk_org_hist_type` CHECK ((`change_type` in (_latin1'member_created',_latin1'member_updated',_latin1'user_type_left',_latin1'account_disabled',_latin1'pointer_cleared')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `sys_organization` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `org_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '组织/部门名称',
  `parent_id` bigint unsigned DEFAULT NULL COMMENT '上级组织ID',
  `org_level` tinyint NOT NULL DEFAULT '1' COMMENT '层级 1=公司 2=部门 3=小组',
  `manager_id` bigint unsigned DEFAULT NULL COMMENT '负责人ID',
  `sort_order` int NOT NULL DEFAULT '0' COMMENT '排序权重',
  `status` tinyint NOT NULL DEFAULT '1' COMMENT '状态 1=启用 0=停用',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_parent_id` (`parent_id`),
  KEY `idx_manager_id` (`manager_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='组织架构表';

CREATE TABLE `sys_role` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `role_code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '角色编码（如 ADMIN/EMPLOYEE/STUDENT）',
  `role_name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '角色名称',
  `description` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '角色描述',
  `status` tinyint NOT NULL DEFAULT '1' COMMENT '状态 1=启用 0=禁用',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_role_code` (`role_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统角色字典表';

CREATE TABLE `sys_user` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `username` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '登录账号',
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '密码哈希',
  `real_name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '真实姓名',
  `user_type` enum('student','employee','admin') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户类型',
  `role_id` bigint unsigned DEFAULT NULL COMMENT '关联角色ID',
  `department` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '所属部门/院系',
  `contact_info` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '联系方式（手机号/邮箱）',
  `avatar_url` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '头像URL',
  `status` enum('normal','disabled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'normal' COMMENT '账号状态',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`),
  KEY `idx_user_type` (`user_type`),
  KEY `idx_role_id` (`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='统一用户表（学生/员工/管理员）';

CREATE TABLE `sys_user_primary_org` (
  `user_id` bigint unsigned NOT NULL,
  `member_id` bigint unsigned NOT NULL,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `uk_primary_member` (`member_id`),
  KEY `fk_primary_member` (`member_id`,`user_id`),
  CONSTRAINT `fk_primary_member` FOREIGN KEY (`member_id`, `user_id`) REFERENCES `sys_org_member` (`id`, `user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `todo_item` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `assignee_id` bigint unsigned NOT NULL COMMENT '指派人ID',
  `todo_type` enum('leave_approval','complaint_follow','report_remind','custom') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '待办类型',
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '待办标题',
  `description` text COLLATE utf8mb4_unicode_ci COMMENT '待办描述',
  `related_type` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '关联业务类型',
  `related_id` bigint unsigned DEFAULT NULL COMMENT '关联业务ID',
  `priority` enum('low','medium','high','urgent') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'medium' COMMENT '优先级',
  `status` enum('pending','in_progress','done','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending' COMMENT '状态',
  `due_time` datetime DEFAULT NULL COMMENT '截止时间',
  `completed_time` datetime DEFAULT NULL COMMENT '完成时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `assignment_version` int NOT NULL DEFAULT '1',
  `source_status` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_todo_source` (`related_type`,`related_id`),
  KEY `idx_assignee` (`assignee_id`),
  KEY `idx_status` (`status`),
  KEY `idx_todo_type` (`todo_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='待办事项表';

CREATE TABLE `visitor_account` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(64) NOT NULL,
  `name` varchar(64) NOT NULL,
  `contact` varchar(128) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `visitor_call` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `visitor_id` bigint NOT NULL,
  `advisor_id` bigint NOT NULL,
  `request_id` varchar(36) NOT NULL,
  `notes` text NOT NULL,
  `recorded_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_visitor_call_request` (`visitor_id`,`request_id`),
  CONSTRAINT `visitor_call_ibfk_1` FOREIGN KEY (`visitor_id`) REFERENCES `visitor_intake` (`visitor_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `visitor_intake` (
  `visitor_id` bigint NOT NULL,
  `advisor_id` bigint NOT NULL,
  `claimed_at` datetime NOT NULL,
  `last_contact_at` datetime DEFAULT NULL,
  `manual_source_id` bigint unsigned DEFAULT NULL,
  `crm_lead_id` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`visitor_id`),
  UNIQUE KEY `manual_source_id` (`manual_source_id`),
  UNIQUE KEY `uq_visitor_intake_crm` (`crm_lead_id`),
  KEY `ix_visitor_intake_advisor_id` (`advisor_id`),
  CONSTRAINT `fk_visitor_intake_crm` FOREIGN KEY (`crm_lead_id`) REFERENCES `crm_lead` (`id`),
  CONSTRAINT `visitor_intake_ibfk_1` FOREIGN KEY (`visitor_id`) REFERENCES `visitor_account` (`id`),
  CONSTRAINT `visitor_intake_ibfk_2` FOREIGN KEY (`manual_source_id`) REFERENCES `customer_source` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `visitor_material` (
  `source_id` bigint unsigned NOT NULL,
  `visitor_id` bigint NOT NULL,
  `file_content` mediumblob,
  PRIMARY KEY (`source_id`),
  KEY `ix_visitor_material_visitor_id` (`visitor_id`),
  CONSTRAINT `visitor_material_ibfk_1` FOREIGN KEY (`source_id`) REFERENCES `customer_source` (`id`),
  CONSTRAINT `visitor_material_ibfk_2` FOREIGN KEY (`visitor_id`) REFERENCES `visitor_account` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `visitor_session` (
  `digest` varchar(64) NOT NULL,
  `visitor_id` bigint NOT NULL,
  `expires_at` datetime NOT NULL,
  PRIMARY KEY (`digest`),
  KEY `ix_visitor_session_expires_at` (`expires_at`),
  KEY `ix_visitor_session_visitor_id` (`visitor_id`),
  CONSTRAINT `visitor_session_ibfk_1` FOREIGN KEY (`visitor_id`) REFERENCES `visitor_account` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `website_student_access` (
  `visitor_id` bigint NOT NULL,
  `student_id` bigint unsigned NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  PRIMARY KEY (`visitor_id`),
  UNIQUE KEY `uq_website_student_access` (`student_id`),
  CONSTRAINT `website_student_access_ibfk_1` FOREIGN KEY (`visitor_id`) REFERENCES `visitor_account` (`id`),
  CONSTRAINT `website_student_access_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

SET FOREIGN_KEY_CHECKS = @previous_foreign_key_checks;

DELIMITER $$
CREATE TRIGGER `trg_member_after_insert` AFTER INSERT ON `sys_org_member` FOR EACH ROW
BEGIN
  IF @base_org_actor_user_id IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'member actor missing';
  END IF;
  INSERT INTO sys_org_member_history (
    member_id, user_id, org_id, change_type,
    status_before, status_after,
    effective_from_before, effective_to_before,
    effective_from_after, effective_to_after,
    primary_pointer_cleared, actor_type, actor_user_id, changed_at)
  VALUES (
    NEW.id, NEW.user_id, NEW.org_id, 'member_created',
    NULL, NEW.status, NULL, NULL,
    NEW.effective_from, NEW.effective_to,
    0, 'user', @base_org_actor_user_id, UTC_TIMESTAMP(6));
END$$

CREATE TRIGGER `trg_member_before_insert` BEFORE INSERT ON `sys_org_member` FOR EACH ROW
BEGIN
  DECLARE ut VARCHAR(32);
  DECLARE st VARCHAR(32);
  SELECT user_type, status INTO ut, st FROM sys_user WHERE id = NEW.user_id FOR SHARE;
  IF ut IS NULL OR ut NOT IN ('employee','admin') OR st <> 'normal' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'member insert denied';
  END IF;
END$$

CREATE TRIGGER `trg_member_before_update` BEFORE UPDATE ON `sys_org_member` FOR EACH ROW
BEGIN
  DECLARE ut VARCHAR(32);
  DECLARE st VARCHAR(32);
  DECLARE cleared TINYINT DEFAULT 0;
  DECLARE reason VARCHAR(32);
  DECLARE changed TINYINT DEFAULT 0;
  DECLARE system_stop TINYINT DEFAULT 0;
  SELECT user_type, status INTO ut, st FROM sys_user WHERE id = OLD.user_id FOR SHARE;
  IF NEW.user_id <> OLD.user_id OR NEW.org_id <> OLD.org_id THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'member identity is immutable';
  END IF;
  IF ut IS NULL OR ut NOT IN ('employee','admin') OR st <> 'normal' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'member update denied';
  END IF;
  IF NOT (OLD.status <=> NEW.status)
     OR NOT (OLD.effective_from <=> NEW.effective_from)
     OR NOT (OLD.effective_to <=> NEW.effective_to) THEN
    SET changed = 1;
  END IF;
  IF changed = 0 THEN
    SET @base_org_reason = NULL;
  ELSE
    SET system_stop = (
      OLD.status = 'active' AND NEW.status = 'inactive'
      AND OLD.effective_from <=> NEW.effective_from
      AND OLD.effective_to <=> NEW.effective_to
      AND @base_org_reason IN ('user_type_left','account_disabled'));
    IF system_stop = 1 THEN
      SET reason = @base_org_reason;
    ELSE
      SET reason = 'member_updated';
      IF @base_org_actor_user_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'member actor missing';
      END IF;
    END IF;
    IF NEW.status <> 'active'
       OR NEW.effective_from > UTC_TIMESTAMP()
       OR (NEW.effective_to IS NOT NULL AND NEW.effective_to <= UTC_TIMESTAMP()) THEN
      DELETE FROM sys_user_primary_org
        WHERE user_id = OLD.user_id AND member_id = OLD.id;
      IF ROW_COUNT() > 0 THEN
        SET cleared = 1;
      END IF;
    END IF;
    INSERT INTO sys_org_member_history (
      member_id, user_id, org_id, change_type,
      status_before, status_after,
      effective_from_before, effective_to_before,
      effective_from_after, effective_to_after,
      primary_pointer_cleared, actor_type, actor_user_id, changed_at)
    VALUES (
      OLD.id, OLD.user_id, OLD.org_id, reason,
      OLD.status, NEW.status,
      OLD.effective_from, OLD.effective_to,
      NEW.effective_from, NEW.effective_to,
      cleared,
      IF(system_stop = 1, 'system', 'user'),
      IF(system_stop = 1, NULL, @base_org_actor_user_id),
      UTC_TIMESTAMP(6));
  END IF;
END$$

CREATE TRIGGER `trg_user_before_update` BEFORE UPDATE ON `sys_user` FOR EACH ROW
BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    SET @base_org_reason = NULL;
    RESIGNAL;
  END;
  IF (OLD.user_type IN ('employee','admin') AND NEW.user_type NOT IN ('employee','admin'))
     OR (OLD.status = 'normal' AND NEW.status <> 'normal') THEN
    IF OLD.user_type IN ('employee','admin') AND NEW.user_type NOT IN ('employee','admin') THEN
      SET @base_org_reason = 'user_type_left';
    ELSE
      SET @base_org_reason = 'account_disabled';
    END IF;
    UPDATE sys_org_member
      SET status = 'inactive'
      WHERE user_id = OLD.id AND status = 'active'
      ORDER BY id;
  END IF;
  SET @base_org_reason = NULL;
END$$

DELIMITER ;
