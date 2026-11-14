CREATE TABLE `sys_org_member` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `org_id` bigint unsigned NOT NULL,
  `effective_from` datetime NOT NULL,
  `effective_to` datetime DEFAULT NULL,
  `status` enum('active','inactive') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
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

CREATE TABLE `sys_user_primary_org` (
  `user_id` bigint unsigned NOT NULL,
  `member_id` bigint unsigned NOT NULL,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `uk_primary_member` (`member_id`),
  KEY `fk_primary_member` (`member_id`,`user_id`),
  CONSTRAINT `fk_primary_member` FOREIGN KEY (`member_id`, `user_id`) REFERENCES `sys_org_member` (`id`, `user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `sys_org_member_history` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `member_id` bigint unsigned NOT NULL,
  `user_id` bigint unsigned NOT NULL,
  `org_id` bigint unsigned NOT NULL,
  `change_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status_before` enum('active','inactive') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status_after` enum('active','inactive') COLLATE utf8mb4_unicode_ci NOT NULL,
  `effective_from_before` datetime DEFAULT NULL,
  `effective_to_before` datetime DEFAULT NULL,
  `effective_from_after` datetime NOT NULL,
  `effective_to_after` datetime DEFAULT NULL,
  `primary_pointer_cleared` tinyint(1) NOT NULL DEFAULT '0',
  `actor_type` enum('user','system') COLLATE utf8mb4_unicode_ci NOT NULL,
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

DELIMITER $$
CREATE TRIGGER `trg_user_before_update` BEFORE UPDATE ON `sys_user` FOR EACH ROW BEGIN
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

CREATE TRIGGER `trg_member_before_insert` BEFORE INSERT ON `sys_org_member` FOR EACH ROW BEGIN
  DECLARE ut VARCHAR(32);
  DECLARE st VARCHAR(32);
  SELECT user_type, status INTO ut, st FROM sys_user WHERE id = NEW.user_id FOR SHARE;
  IF ut IS NULL OR ut NOT IN ('employee','admin') OR st <> 'normal' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'member insert denied';
  END IF;
END$$

CREATE TRIGGER `trg_member_before_update` BEFORE UPDATE ON `sys_org_member` FOR EACH ROW BEGIN
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

CREATE TRIGGER `trg_member_after_insert` AFTER INSERT ON `sys_org_member` FOR EACH ROW BEGIN
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
DELIMITER ;
