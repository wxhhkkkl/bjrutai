-- Immutable empty legacy-023 test schema, generated from the pre-mall ORM metadata.
-- No data, credentials or production schema dump. Only used inside runner-owned MySQL.
CREATE TABLE _deprecated_hierarchy_nodes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	parent_id INTEGER, 
	level INTEGER NOT NULL, 
	node_type ENUM('HEADQUARTERS','REGION','BRANCH','PROMOTER','TERMINAL') NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix__deprecated_hierarchy_nodes_parent_id ON _deprecated_hierarchy_nodes (parent_id);
CREATE TABLE admin_accounts (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	username VARCHAR(100) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	status ENUM('ACTIVE','DISABLED','LOCKED') NOT NULL, 
	locked_until DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (username)
);
CREATE TABLE agreements (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	type ENUM('PRIVACY_POLICY','TERMS_OF_SERVICE','DATA_AUTHORIZATION','MARKETING_CONSENT') NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	version VARCHAR(20) NOT NULL, 
	summary TEXT, 
	content_url VARCHAR(500), 
	effective_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE api_call_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	interface_name VARCHAR(200) NOT NULL, 
	request_params JSON, 
	response_status INTEGER NOT NULL, 
	duration_ms INTEGER NOT NULL, 
	error_message TEXT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_api_call_logs_created_at ON api_call_logs (created_at);
CREATE INDEX ix_api_call_logs_interface_name ON api_call_logs (interface_name);
CREATE TABLE article_categories (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(50) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE TABLE banners (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	title VARCHAR(100), 
	image_url VARCHAR(2048) NOT NULL, 
	action_type ENUM('NONE','ARTICLE') NOT NULL, 
	article_id INTEGER, 
	sort_order INTEGER NOT NULL, 
	status ENUM('ENABLED','DISABLED') NOT NULL, 
	version INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE idempotency_keys (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	`key` VARCHAR(255) NOT NULL, 
	status_code INTEGER NOT NULL, 
	response_body TEXT NOT NULL, 
	response_headers TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_idempotency_keys_created_at ON idempotency_keys (created_at);
CREATE UNIQUE INDEX ix_idempotency_keys_key ON idempotency_keys (`key`);
CREATE TABLE organizations (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	parent_id INTEGER, 
	name VARCHAR(128) NOT NULL, 
	org_type VARCHAR(50), 
	level INTEGER NOT NULL, 
	sort_order INTEGER NOT NULL, 
	status ENUM('active','disabled') NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_organizations_parent_id ON organizations (parent_id);
CREATE TABLE performance_settlements (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	period VARCHAR(7) NOT NULL, 
	status ENUM('pending','reviewed','rejected') NOT NULL, 
	reviewed_by INTEGER, 
	reviewed_at DATETIME, 
	reject_reason VARCHAR(500), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_performance_settlements_period ON performance_settlements (period);
CREATE TABLE reports (
	id VARCHAR(36) NOT NULL, 
	start_date VARCHAR(10) NOT NULL, 
	end_date VARCHAR(10) NOT NULL, 
	dimensions JSON NOT NULL, 
	sections JSON NOT NULL, 
	generated_by VARCHAR(100), 
	source VARCHAR(32) NOT NULL DEFAULT 'reconciliation', 
	period VARCHAR(7), 
	status VARCHAR(16), 
	generated_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_reports_period ON reports (period);
CREATE TABLE roles (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(100) NOT NULL, 
	permissions JSON NOT NULL, 
	is_system BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE TABLE user_tokens (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	token_type ENUM('ACCESS','REFRESH') NOT NULL, 
	token_hash VARCHAR(255) NOT NULL, 
	family VARCHAR(255), 
	expires_at DATETIME NOT NULL, 
	is_revoked BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_user_tokens_family ON user_tokens (family);
CREATE UNIQUE INDEX ix_user_tokens_token_hash ON user_tokens (token_hash);
CREATE INDEX ix_user_tokens_user_id ON user_tokens (user_id);
CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	openid VARCHAR(128), 
	user_type ENUM('PERSONAL','PROMOTER','DOCTOR','ADMIN','FINANCE','OPS','DISTRIBUTOR') NOT NULL, 
	name VARCHAR(100), 
	phone VARCHAR(20), 
	phone_masked VARCHAR(20), 
	password_hash VARCHAR(255), 
	id_card_encrypted TEXT, 
	organization VARCHAR(200), 
	avatar_url VARCHAR(500), 
	activation_status ENUM('ACTIVE','INACTIVE','DISABLED') NOT NULL, 
	qualification_status ENUM('DRAFT','REVIEWING','APPROVED','REJECTED','EXPIRING','EXPIRED') NOT NULL, 
	profile_completed BOOL NOT NULL, 
	wechat_bound BOOL NOT NULL, 
	phone_authorized BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_users_openid ON users (openid);
CREATE TABLE _deprecated_promoters (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	qualification_status VARCHAR(50), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	UNIQUE (node_id)
);
CREATE TABLE admin_account_roles (
	admin_account_id INTEGER NOT NULL, 
	role_id INTEGER NOT NULL, 
	PRIMARY KEY (admin_account_id, role_id)
);
CREATE TABLE article_videos (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	upload_session_id VARCHAR(36) NOT NULL, 
	uploaded_by_admin_id INTEGER NOT NULL, 
	file_name VARCHAR(255) NOT NULL, 
	content_type VARCHAR(50) NOT NULL, 
	declared_size_bytes BIGINT NOT NULL, 
	actual_size_bytes BIGINT, 
	vod_sub_app_id BIGINT NOT NULL, 
	file_id VARCHAR(100), 
	procedure_task_id VARCHAR(255), 
	status ENUM('authorized','processing','ready','failed','deleting','deleted') NOT NULL, 
	ownership_verified BOOL NOT NULL, 
	upload_confirmed_at DATETIME, 
	processing_confirmed_at DATETIME, 
	playback_url VARCHAR(2048), 
	poster_url VARCHAR(2048), 
	duration_seconds FLOAT, 
	failure_message VARCHAR(255), 
	unbound_at DATETIME, 
	cloud_deleted_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (upload_session_id), 
	UNIQUE (file_id)
);
CREATE INDEX ix_article_videos_cleanup ON article_videos (status, unbound_at);
CREATE TABLE audit_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER, 
	action VARCHAR(100) NOT NULL, 
	entity_type VARCHAR(100) NOT NULL, 
	entity_id VARCHAR(100), 
	detail JSON, 
	ip_address VARCHAR(45), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_audit_logs_action ON audit_logs (action);
CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);
CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id);
CREATE TABLE distributors (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	org_id INTEGER NOT NULL, 
	org_role ENUM('member','admin') NOT NULL, 
	status ENUM('active','disabled') NOT NULL, 
	source_channel VARCHAR(32) NOT NULL COMMENT '人员来源渠道: admin_create / staff_invite / migrated' DEFAULT 'admin_create', 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id)
);
CREATE INDEX ix_distributors_org_id ON distributors (org_id);
CREATE TABLE hierarchy_snapshots (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	node_id INTEGER NOT NULL, 
	snapshot_data JSON, 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE org_history (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	org_id INTEGER NOT NULL, 
	action ENUM('created','updated','moved','deleted') NOT NULL, 
	operator_id INTEGER, 
	detail JSON, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_org_history_org_id ON org_history (org_id);
CREATE TABLE org_qualifications (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	org_id INTEGER NOT NULL, 
	legal_entity_name VARCHAR(256) NOT NULL, 
	qualification_types JSON NOT NULL, 
	credit_code VARCHAR(64) NOT NULL, 
	file_urls JSON NOT NULL, 
	valid_from DATETIME, 
	valid_until DATETIME NOT NULL, 
	status ENUM('reviewing','approved','rejected') NOT NULL, 
	review_comment TEXT, 
	reviewed_by INTEGER, 
	reviewed_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_org_qualifications_org_id ON org_qualifications (org_id);
CREATE TABLE performance_rules (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	org_id INTEGER NOT NULL, 
	rule_type ENUM('intra_org','org_management') NOT NULL, 
	tiers JSON NOT NULL, 
	status ENUM('active','inactive') NOT NULL, 
	version INTEGER NOT NULL, 
	created_by INTEGER, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uk_rule_org_type UNIQUE (org_id, rule_type)
);
CREATE TABLE sharing_rules (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	level INTEGER NOT NULL, 
	rule_type ENUM('FIXED_RATIO','FIXED_AMOUNT','TIERED') NOT NULL, 
	base ENUM('PAID_AMOUNT','TOTAL_AMOUNT') NOT NULL, 
	value TEXT NOT NULL, 
	effective_at DATETIME NOT NULL, 
	expires_at DATETIME, 
	status ENUM('ACTIVE','INACTIVE','EXPIRED') NOT NULL, 
	version INTEGER NOT NULL, 
	created_by INTEGER, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE _deprecated_qualifications (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	promoter_id INTEGER NOT NULL, 
	legal_entity VARCHAR(200), 
	qualification_type ENUM('INDIVIDUAL','ENTERPRISE') NOT NULL, 
	credit_code_encrypted VARCHAR(500), 
	credit_code_masked VARCHAR(100), 
	expires_at DATETIME, 
	status ENUM('DRAFT','REVIEWING','APPROVED','REJECTED','EXPIRING','EXPIRED') NOT NULL, 
	file_id VARCHAR(255), 
	file_name VARCHAR(255), 
	file_type VARCHAR(50), 
	file_size INTEGER, 
	submitted_at DATETIME, 
	approved_at DATETIME, 
	rejected_reason VARCHAR(500), 
	version INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix__deprecated_qualifications_promoter_id ON _deprecated_qualifications (promoter_id);
CREATE TABLE articles (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	title VARCHAR(200) NOT NULL, 
	summary VARCHAR(500), 
	content TEXT NOT NULL, 
	cover_url VARCHAR(2048), 
	category VARCHAR(50), 
	category_label VARCHAR(100), 
	category_id INTEGER, 
	video_id INTEGER, 
	tags JSON, 
	status ENUM('DRAFT','PUBLISHED','UNPUBLISHED') NOT NULL, 
	author_name VARCHAR(100), 
	view_count INTEGER NOT NULL, 
	published_at DATETIME, 
	version INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (video_id)
);
CREATE TABLE commission_results (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	period VARCHAR(7) NOT NULL, 
	distributor_id INTEGER NOT NULL, 
	org_id INTEGER NOT NULL, 
	rule_type ENUM('intra_org','org_management') NOT NULL, 
	base_cent INTEGER NOT NULL, 
	ratio VARCHAR(20) NOT NULL, 
	commission_cent INTEGER NOT NULL, 
	rule_snapshot JSON, 
	computed_at DATETIME NOT NULL, 
	redeemed_points_x100 INTEGER, 
	points_redeemed_by INTEGER, 
	points_redeemed_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uk_comm_period_dist_type UNIQUE (period, distributor_id, rule_type)
);
CREATE INDEX ix_commission_results_period ON commission_results (period);
CREATE TABLE customers (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER, 
	distributor_id INTEGER, 
	name VARCHAR(100), 
	phone VARCHAR(20), 
	phone_normalized VARCHAR(20), 
	phone_masked VARCHAR(20), 
	id_card_encrypted TEXT, 
	id_card_masked VARCHAR(50), 
	medical_account_encrypted TEXT, 
	family_phone VARCHAR(20), 
	rutai_user_id VARCHAR(100), 
	note TEXT, 
	binding_status ENUM('PENDING','BOUND','UNBOUND') NOT NULL, 
	bound_at DATETIME, 
	version INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_customers_distributor_id ON customers (distributor_id);
CREATE INDEX ix_customers_phone_normalized ON customers (phone_normalized);
CREATE INDEX ix_customers_rutai_user_id ON customers (rutai_user_id);
CREATE UNIQUE INDEX ix_customers_user_id ON customers (user_id);
CREATE TABLE feedbacks (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	feedback_no VARCHAR(40) NOT NULL, 
	user_id INTEGER, 
	submitter_name_snapshot VARCHAR(100), 
	submitter_phone_masked_snapshot VARCHAR(20), 
	type VARCHAR(20) NOT NULL, 
	content TEXT NOT NULL, 
	image_files JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	first_handler_id INTEGER, 
	first_handled_at DATETIME, 
	resolved_by_id INTEGER, 
	resolved_at DATETIME, 
	resolution TEXT, 
	version INTEGER NOT NULL, 
	idempotency_key VARCHAR(128), 
	submission_fingerprint VARCHAR(64), 
	source_audit_log_id INTEGER, 
	notification_status VARCHAR(20) NOT NULL, 
	notification_attempts INTEGER NOT NULL, 
	notification_next_retry_at DATETIME, 
	notification_last_error VARCHAR(500), 
	notification_sent_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_feedbacks_user_idempotency UNIQUE (user_id, idempotency_key), 
	CONSTRAINT uq_feedbacks_source_audit_log UNIQUE (source_audit_log_id)
);
CREATE UNIQUE INDEX ix_feedbacks_feedback_no ON feedbacks (feedback_no);
CREATE INDEX ix_feedbacks_status_created ON feedbacks (status, created_at, id);
CREATE INDEX ix_feedbacks_type_created ON feedbacks (type, created_at, id);
CREATE INDEX ix_feedbacks_user_created ON feedbacks (user_id, created_at, id);
CREATE INDEX ix_feedbacks_user_id ON feedbacks (user_id);
CREATE TABLE performance_rule_change_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	rule_id INTEGER NOT NULL, 
	operation_type ENUM('create','update','apply') NOT NULL, 
	changed_by INTEGER NOT NULL, 
	old_value JSON, 
	new_value JSON, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_performance_rule_change_logs_rule_id ON performance_rule_change_logs (rule_id);
CREATE TABLE personal_performance_rules (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	distributor_id INTEGER NOT NULL, 
	tiers JSON NOT NULL, 
	version INTEGER NOT NULL, 
	created_by INTEGER, 
	updated_by INTEGER, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_personal_perf_distributor UNIQUE (distributor_id)
);
CREATE TABLE promotion_codes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	distributor_id INTEGER NOT NULL, 
	ref_token VARCHAR(255) NOT NULL, 
	source_code VARCHAR(10) NOT NULL, 
	qr_image_url VARCHAR(500), 
	share_title VARCHAR(200), 
	share_path VARCHAR(500), 
	status ENUM('AVAILABLE','DISABLED','EXPIRED') NOT NULL, 
	expires_at DATETIME, 
	disabled_reason TEXT, 
	scan_count INTEGER NOT NULL, 
	lead_count INTEGER NOT NULL, 
	bind_count INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (distributor_id)
);
CREATE UNIQUE INDEX ix_promotion_codes_ref_token ON promotion_codes (ref_token);
CREATE TABLE sharing_rule_change_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	rule_id INTEGER NOT NULL, 
	changed_by INTEGER NOT NULL, 
	old_value JSON, 
	new_value JSON, 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE staff_invite_codes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	org_id INTEGER NOT NULL, 
	inviter_distributor_id INTEGER NOT NULL, 
	ref_token VARCHAR(255) NOT NULL, 
	status ENUM('available','disabled','expired') NOT NULL, 
	expires_at DATETIME NOT NULL, 
	joined_count INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_staff_invite_codes_inviter_distributor_id ON staff_invite_codes (inviter_distributor_id);
CREATE INDEX ix_staff_invite_codes_org_id ON staff_invite_codes (org_id);
CREATE UNIQUE INDEX ix_staff_invite_codes_ref_token ON staff_invite_codes (ref_token);
CREATE TABLE article_comments (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	article_id INTEGER NOT NULL, 
	user_id INTEGER, 
	display_name_snapshot VARCHAR(100) NOT NULL, 
	avatar_url_snapshot VARCHAR(500), 
	content TEXT, 
	status VARCHAR(20) NOT NULL, 
	moderation_status VARCHAR(20) NOT NULL, 
	moderation_category VARCHAR(32), 
	moderation_rule_version VARCHAR(32), 
	moderation_checked_at DATETIME, 
	moderation_reason VARCHAR(255), 
	is_pinned BOOL NOT NULL, 
	like_count INTEGER NOT NULL, 
	version INTEGER NOT NULL, 
	hidden_at DATETIME, 
	deleted_at DATETIME, 
	idempotency_key VARCHAR(128), 
	submission_fingerprint VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_article_comments_user_idempotency UNIQUE (user_id, idempotency_key)
);
CREATE INDEX ix_article_comments_article_id ON article_comments (article_id);
CREATE INDEX ix_article_comments_deleted_at ON article_comments (status, deleted_at);
CREATE INDEX ix_article_comments_public_order ON article_comments (article_id, status, is_pinned, created_at, id);
CREATE INDEX ix_article_comments_status_created ON article_comments (status, created_at, id);
CREATE INDEX ix_article_comments_user_id ON article_comments (user_id);
CREATE TABLE bills (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	customer_id INTEGER NOT NULL, 
	rutai_user_id VARCHAR(100), 
	transaction_id VARCHAR(100) NOT NULL, 
	transaction_time DATETIME NOT NULL, 
	consultation_fee_cent INTEGER NOT NULL, 
	medicine_fee_cent INTEGER NOT NULL, 
	total_amount_cent INTEGER NOT NULL, 
	discount_amount_cent INTEGER NOT NULL, 
	paid_amount_cent INTEGER NOT NULL, 
	refund_amount_cent INTEGER NOT NULL, 
	transaction_status ENUM('PAID','PARTIALLY_REFUNDED','REFUNDED','CANCELLED') NOT NULL, 
	source VARCHAR(20) NOT NULL DEFAULT 'rutai_sync', 
	attributed_distributor_id INTEGER, 
	attributed_person_name VARCHAR(100), 
	attributed_org_id INTEGER, 
	attributed_org_name VARCHAR(128), 
	entry_note TEXT, 
	created_by_admin_id INTEGER, 
	idempotency_key VARCHAR(128), 
	submission_fingerprint VARCHAR(64), 
	updated_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_bills_admin_idempotency UNIQUE (created_by_admin_id, idempotency_key)
);
CREATE INDEX ix_bills_customer_id ON bills (customer_id);
CREATE INDEX ix_bills_source_created ON bills (source, created_at, id);
CREATE UNIQUE INDEX ix_bills_transaction_id ON bills (transaction_id);
CREATE TABLE consent_records (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER, 
	customer_id INTEGER, 
	subject_type ENUM('USER','CUSTOMER') NOT NULL, 
	scene ENUM('REGISTRATION','BINDING','PROMOTION','FOLLOWUP') NOT NULL, 
	agreement_versions JSON NOT NULL, 
	scopes JSON NOT NULL, 
	confirmed BOOL NOT NULL, 
	evidence_type ENUM('CLICK','SIGNATURE','SMS','FACIAL'), 
	status VARCHAR(50) NOT NULL, 
	consented_at DATETIME NOT NULL, 
	expires_at DATETIME, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_consent_records_customer_id ON consent_records (customer_id);
CREATE TABLE customer_change_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	customer_id INTEGER NOT NULL, 
	operation_type ENUM('created','transfer') NOT NULL, 
	previous_distributor_id INTEGER, 
	new_distributor_id INTEGER, 
	operator_id INTEGER NOT NULL, 
	reason VARCHAR(500), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_customer_change_logs_customer_id ON customer_change_logs (customer_id);
CREATE TABLE feedback_actions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	feedback_id INTEGER NOT NULL, 
	operator_id INTEGER, 
	operator_name_snapshot VARCHAR(100) NOT NULL, 
	action_type VARCHAR(20) NOT NULL, 
	from_status VARCHAR(20) NOT NULL, 
	to_status VARCHAR(20) NOT NULL, 
	internal_note TEXT, 
	user_resolution TEXT, 
	version_before INTEGER NOT NULL, 
	version_after INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_feedback_actions_feedback_created ON feedback_actions (feedback_id, created_at, id);
CREATE TABLE followup_records (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	customer_id INTEGER NOT NULL, 
	doctor_id INTEGER NOT NULL, 
	method ENUM('PHONE','WECHAT','VISIT','OTHER') NOT NULL, 
	result ENUM('SUCCESSFUL','FAILED','PENDING','NO_ANSWER') NOT NULL, 
	content TEXT, 
	reminder_enabled BOOL NOT NULL, 
	reminder_at DATETIME, 
	reminder_status ENUM('PENDING','SENT','CANCELLED') NOT NULL, 
	version INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_followup_records_customer_id ON followup_records (customer_id);
CREATE TABLE notifications (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	category ENUM('SYSTEM','BINDING','PROMOTION','BILL','FOLLOWUP','QUALIFICATION') NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	summary TEXT, 
	target VARCHAR(500), 
	feedback_id INTEGER, 
	is_read BOOL NOT NULL, 
	read_at DATETIME, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_notifications_feedback_id ON notifications (feedback_id);
CREATE INDEX ix_notifications_user_id ON notifications (user_id);
CREATE TABLE binding_requests (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	customer_id INTEGER, 
	distributor_id INTEGER NOT NULL, 
	submitted_by INTEGER NOT NULL, 
	rutai_user_id_masked VARCHAR(100), 
	customer_name VARCHAR(100), 
	phone_masked VARCHAR(20), 
	id_card_masked VARCHAR(50), 
	source_type ENUM('SCAN','MANUAL','SHARE','IMPORT') NOT NULL, 
	source_lead_id VARCHAR(100), 
	ref_token VARCHAR(255), 
	consent_record_id INTEGER, 
	status ENUM('PENDING_MATCH','MATCHING','BOUND','NO_CONSUME','RETRYING','MANUAL_REVIEW','ABNORMAL','UNBOUND','TRANSFERRED') NOT NULL, 
	match_level ENUM('EXACT','FUZZY','NONE'), 
	retry_count INTEGER NOT NULL, 
	next_retry_at DATETIME, 
	failure_reason TEXT, 
	bound_at DATETIME, 
	version INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_binding_requests_customer_id ON binding_requests (customer_id);
CREATE INDEX ix_binding_requests_distributor_id ON binding_requests (distributor_id);
CREATE INDEX ix_binding_requests_ref_token ON binding_requests (ref_token);
CREATE TABLE comment_actions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	comment_id INTEGER NOT NULL, 
	operator_admin_id INTEGER, 
	operator_name_snapshot VARCHAR(100) NOT NULL, 
	action_type VARCHAR(24) NOT NULL, 
	from_status VARCHAR(20) NOT NULL, 
	to_status VARCHAR(20) NOT NULL, 
	reason TEXT, 
	moderation_rule_version VARCHAR(32), 
	version_before INTEGER NOT NULL, 
	version_after INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_comment_actions_comment_created ON comment_actions (comment_id, created_at, id);
CREATE INDEX ix_comment_actions_type_created ON comment_actions (action_type, created_at);
CREATE TABLE comment_likes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	comment_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_comment_likes_comment_user UNIQUE (comment_id, user_id)
);
CREATE INDEX ix_comment_likes_user_comment ON comment_likes (user_id, comment_id);
CREATE TABLE binding_change_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	binding_request_id INTEGER NOT NULL, 
	operation_type ENUM('BIND','UNBIND','TRANSFER') NOT NULL, 
	previous_promoter_id INTEGER, 
	new_promoter_id INTEGER, 
	operator_id INTEGER NOT NULL, 
	reason TEXT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_binding_change_logs_binding_request_id ON binding_change_logs (binding_request_id);
ALTER TABLE _deprecated_hierarchy_nodes ADD FOREIGN KEY(parent_id) REFERENCES _deprecated_hierarchy_nodes (id);
ALTER TABLE organizations ADD FOREIGN KEY(parent_id) REFERENCES organizations (id);
ALTER TABLE _deprecated_promoters ADD FOREIGN KEY(node_id) REFERENCES _deprecated_hierarchy_nodes (id);
ALTER TABLE _deprecated_promoters ADD FOREIGN KEY(user_id) REFERENCES users (id);
ALTER TABLE admin_account_roles ADD FOREIGN KEY(admin_account_id) REFERENCES admin_accounts (id) ON DELETE CASCADE;
ALTER TABLE admin_account_roles ADD FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE;
ALTER TABLE article_videos ADD FOREIGN KEY(uploaded_by_admin_id) REFERENCES admin_accounts (id);
ALTER TABLE audit_logs ADD FOREIGN KEY(user_id) REFERENCES users (id);
ALTER TABLE distributors ADD FOREIGN KEY(org_id) REFERENCES organizations (id);
ALTER TABLE distributors ADD FOREIGN KEY(user_id) REFERENCES users (id);
ALTER TABLE hierarchy_snapshots ADD FOREIGN KEY(node_id) REFERENCES _deprecated_hierarchy_nodes (id);
ALTER TABLE org_history ADD FOREIGN KEY(operator_id) REFERENCES admin_accounts (id);
ALTER TABLE org_history ADD FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE;
ALTER TABLE org_qualifications ADD FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE;
ALTER TABLE org_qualifications ADD FOREIGN KEY(reviewed_by) REFERENCES admin_accounts (id);
ALTER TABLE performance_rules ADD FOREIGN KEY(created_by) REFERENCES users (id);
ALTER TABLE performance_rules ADD FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE;
ALTER TABLE sharing_rules ADD FOREIGN KEY(created_by) REFERENCES users (id);
ALTER TABLE _deprecated_qualifications ADD FOREIGN KEY(promoter_id) REFERENCES _deprecated_promoters (id);
ALTER TABLE articles ADD FOREIGN KEY(category_id) REFERENCES article_categories (id) ON DELETE SET NULL;
ALTER TABLE articles ADD FOREIGN KEY(video_id) REFERENCES article_videos (id) ON DELETE RESTRICT;
ALTER TABLE commission_results ADD FOREIGN KEY(distributor_id) REFERENCES distributors (id) ON DELETE CASCADE;
ALTER TABLE customers ADD FOREIGN KEY(distributor_id) REFERENCES distributors (id);
ALTER TABLE customers ADD FOREIGN KEY(user_id) REFERENCES users (id);
ALTER TABLE feedbacks ADD FOREIGN KEY(first_handler_id) REFERENCES admin_accounts (id) ON DELETE SET NULL;
ALTER TABLE feedbacks ADD FOREIGN KEY(resolved_by_id) REFERENCES admin_accounts (id) ON DELETE SET NULL;
ALTER TABLE feedbacks ADD FOREIGN KEY(source_audit_log_id) REFERENCES audit_logs (id) ON DELETE SET NULL;
ALTER TABLE feedbacks ADD FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL;
ALTER TABLE performance_rule_change_logs ADD FOREIGN KEY(rule_id) REFERENCES performance_rules (id) ON DELETE CASCADE;
ALTER TABLE personal_performance_rules ADD FOREIGN KEY(distributor_id) REFERENCES distributors (id) ON DELETE CASCADE;
ALTER TABLE promotion_codes ADD FOREIGN KEY(distributor_id) REFERENCES distributors (id);
ALTER TABLE sharing_rule_change_logs ADD FOREIGN KEY(changed_by) REFERENCES users (id);
ALTER TABLE sharing_rule_change_logs ADD FOREIGN KEY(rule_id) REFERENCES sharing_rules (id);
ALTER TABLE staff_invite_codes ADD FOREIGN KEY(inviter_distributor_id) REFERENCES distributors (id);
ALTER TABLE staff_invite_codes ADD FOREIGN KEY(org_id) REFERENCES organizations (id);
ALTER TABLE article_comments ADD FOREIGN KEY(article_id) REFERENCES articles (id) ON DELETE CASCADE;
ALTER TABLE article_comments ADD FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL;
ALTER TABLE bills ADD FOREIGN KEY(created_by_admin_id) REFERENCES admin_accounts (id) ON DELETE SET NULL;
ALTER TABLE bills ADD FOREIGN KEY(customer_id) REFERENCES customers (id);
ALTER TABLE consent_records ADD FOREIGN KEY(customer_id) REFERENCES customers (id);
ALTER TABLE consent_records ADD FOREIGN KEY(user_id) REFERENCES users (id);
ALTER TABLE customer_change_logs ADD FOREIGN KEY(customer_id) REFERENCES customers (id) ON DELETE CASCADE;
ALTER TABLE customer_change_logs ADD FOREIGN KEY(operator_id) REFERENCES users (id);
ALTER TABLE feedback_actions ADD FOREIGN KEY(feedback_id) REFERENCES feedbacks (id) ON DELETE CASCADE;
ALTER TABLE feedback_actions ADD FOREIGN KEY(operator_id) REFERENCES admin_accounts (id) ON DELETE SET NULL;
ALTER TABLE followup_records ADD FOREIGN KEY(customer_id) REFERENCES customers (id);
ALTER TABLE followup_records ADD FOREIGN KEY(doctor_id) REFERENCES users (id);
ALTER TABLE notifications ADD FOREIGN KEY(feedback_id) REFERENCES feedbacks (id) ON DELETE SET NULL;
ALTER TABLE notifications ADD FOREIGN KEY(user_id) REFERENCES users (id);
ALTER TABLE binding_requests ADD FOREIGN KEY(consent_record_id) REFERENCES consent_records (id);
ALTER TABLE binding_requests ADD FOREIGN KEY(customer_id) REFERENCES customers (id);
ALTER TABLE binding_requests ADD FOREIGN KEY(distributor_id) REFERENCES distributors (id);
ALTER TABLE binding_requests ADD FOREIGN KEY(submitted_by) REFERENCES users (id);
ALTER TABLE comment_actions ADD FOREIGN KEY(comment_id) REFERENCES article_comments (id) ON DELETE CASCADE;
ALTER TABLE comment_actions ADD FOREIGN KEY(operator_admin_id) REFERENCES admin_accounts (id) ON DELETE SET NULL;
ALTER TABLE comment_likes ADD FOREIGN KEY(comment_id) REFERENCES article_comments (id) ON DELETE CASCADE;
ALTER TABLE comment_likes ADD FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE;
ALTER TABLE binding_change_logs ADD FOREIGN KEY(binding_request_id) REFERENCES binding_requests (id);
ALTER TABLE binding_change_logs ADD FOREIGN KEY(operator_id) REFERENCES users (id);
