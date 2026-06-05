CREATE DATABASE IF NOT EXISTS minerguard CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE minerguard;

CREATE TABLE IF NOT EXISTS trabajador (
    id_dispositivo INT NOT NULL,
    nombres VARCHAR(120) NULL,
    apellidos VARCHAR(120) NULL,
    empresa VARCHAR(120) NULL,
    proyecto VARCHAR(120) NULL,
    fecha_ingreso DATE NULL,
    fecha_nacimiento DATE NULL,
    fotografia LONGBLOB NULL,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id_dispositivo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
