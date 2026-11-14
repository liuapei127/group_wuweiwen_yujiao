-- 014 学生助手：会话、短期消息、本地长期记忆
--
-- 幂等脚本。旧版本由 app.modules.student.assistant_store 在运行期自动建表，
-- 本迁移接管这三张表；已存在的库重复执行为空操作，不修改既有数据。
--
-- 执行：mysql --default-character-set=utf8mb4 -u <user> -p <db> < 014_student_assistant.sql
-- 回退会删除会话与记忆数据，未提供回退脚本；需要时先导出这三张表再手动 DROP。

CREATE TABLE IF NOT EXISTS `stu_assistant_conversation` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '会话ID（token_hex 16 字节）',
  `student_id` bigint unsigned NOT NULL COMMENT '学生ID',
  `title` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '新对话' COMMENT '会话标题',
  `create_time` datetime NOT NULL COMMENT '创建时间',
  `update_time` datetime NOT NULL COMMENT '最后消息时间',
  PRIMARY KEY (`id`),
  KEY `ix_stu_assistant_conversation_student_id` (`student_id`),
  KEY `ix_stu_assistant_conversation_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生助手会话';

CREATE TABLE IF NOT EXISTS `stu_assistant_message` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `conversation_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '所属会话',
  `role` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'user / assistant',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '消息正文',
  `create_time` datetime NOT NULL COMMENT '写入时间',
  PRIMARY KEY (`id`),
  KEY `ix_stu_assistant_message_conversation_id` (`conversation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生助手短期消息';

CREATE TABLE IF NOT EXISTS `stu_mem0_memory` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'stu_<student_id>',
  `memory` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '压缩后的长期记忆事实',
  `metadata_json` text COLLATE utf8mb4_unicode_ci COMMENT '来源元数据',
  `create_time` datetime NOT NULL COMMENT '创建时间',
  `update_time` datetime NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `ix_stu_mem0_memory_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生助手本地长期记忆';
