-- Reverses new service identity storage. Back up any enrolled clients before use.
DROP TABLE auth_service_session_kid;
DROP TABLE auth_service_session;
DROP TABLE auth_service_client_audience;
DROP TABLE auth_service_client;
