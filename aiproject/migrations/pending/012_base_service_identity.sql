CREATE TABLE `auth_service_client` (
  `client_id` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `display_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('active','disabled') COLLATE utf8mb4_unicode_ci NOT NULL,
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
  `kid` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `first_issued_at` datetime(6) NOT NULL,
  PRIMARY KEY (`session_id`,`kid`),
  KEY `idx_kid` (`kid`),
  CONSTRAINT `fk_service_session_kid` FOREIGN KEY (`session_id`) REFERENCES `auth_service_session` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
