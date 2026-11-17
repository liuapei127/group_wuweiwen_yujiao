-- Apply once after 027. Existing conversations and life content are retained.
ALTER TABLE overseas_life_knowledge ADD COLUMN details JSON NULL;
ALTER TABLE stu_assistant_message ADD COLUMN presentation_json JSON NULL;
