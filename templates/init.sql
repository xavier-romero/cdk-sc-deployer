CREATE USER bridge_user with password 'bridge_password';
CREATE DATABASE bridge_db OWNER bridge_user;
grant all privileges on database bridge_db to bridge_user;

CREATE USER aggregator_user with password 'aggregator_password';
CREATE DATABASE aggregator_db OWNER aggregator_user;
grant all privileges on database aggregator_db to aggregator_user;

CREATE USER sync_user with password 'sync_password';
CREATE DATABASE sync_db OWNER sync_user;
grant all privileges on database sync_db to sync_user;

CREATE USER pm_user with password 'pm_password';
CREATE DATABASE pm_db OWNER pm_user;
grant all privileges on database pm_db to pm_user;

CREATE USER dac_user with password 'dac_password';
CREATE DATABASE dac_db OWNER dac_user;
grant all privileges on database dac_db to dac_user;
