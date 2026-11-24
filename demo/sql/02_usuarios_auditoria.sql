/*
================================================================================================
 DEMO · 02 · USUARIOS PROPIOS DE SDBR WEB Y AUDITORÍA
================================================================================================
 Las mismas tablas que crea en producción sql/06_usuarios_auditoria.sql (que no se publica),
 sin sus GRANT: los permisos del usuario de la aplicación los da demo/instalar.py. Si cambia una
 columna allí, hay que cambiarla aquí; tests/test_demo_datos.py compara las dos definiciones.
================================================================================================
*/

DROP TABLE IF EXISTS dbo.SDBR_Usuarios_Areas;
DROP TABLE IF EXISTS dbo.SDBR_Usuarios;
DROP TABLE IF EXISTS dbo.SDBR_Auditoria;
GO

-- Usuarios de la aplicación web. La contraseña se guarda con hash (scrypt, werkzeug.security).
CREATE TABLE dbo.SDBR_Usuarios (
    Id                     INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_SDBR_Usuarios PRIMARY KEY,
    Usuario                NVARCHAR(50)  NOT NULL CONSTRAINT UQ_SDBR_Usuarios_Usuario UNIQUE,
    Nombre                 NVARCHAR(100) NOT NULL,
    Hash_Password          NVARCHAR(255) NOT NULL,
    Rol                    VARCHAR(20)   NOT NULL
        CONSTRAINT CK_SDBR_Usuarios_Rol CHECK (Rol IN ('consulta', 'operador', 'supervisor', 'admin')),
    Activo                 BIT           NOT NULL CONSTRAINT DF_SDBR_Usuarios_Activo DEFAULT (1),
    Debe_Cambiar_Password  BIT           NOT NULL CONSTRAINT DF_SDBR_Usuarios_Cambiar DEFAULT (1),
    Intentos_Fallidos      INT           NOT NULL CONSTRAINT DF_SDBR_Usuarios_Intentos DEFAULT (0),
    Bloqueado_Hasta        DATETIME2(0)  NULL,
    Creado                 DATETIME2(0)  NOT NULL CONSTRAINT DF_SDBR_Usuarios_Creado DEFAULT (SYSDATETIME()),
    Ultimo_Acceso          DATETIME2(0)  NULL
);

-- Áreas en las que un operador puede mover pedidos, con el nombre de la base
-- ('Planeacion', no 'Ops').
CREATE TABLE dbo.SDBR_Usuarios_Areas (
    Usuario_Id  INT          NOT NULL
        CONSTRAINT FK_SDBR_Usuarios_Areas_Usuario REFERENCES dbo.SDBR_Usuarios (Id) ON DELETE CASCADE,
    Area        VARCHAR(30)  NOT NULL,
    CONSTRAINT PK_SDBR_Usuarios_Areas PRIMARY KEY (Usuario_Id, Area)
);

-- Una fila por cada escritura hecha desde la web: quién, cuándo, qué y sobre qué.
CREATE TABLE dbo.SDBR_Auditoria (
    Id        BIGINT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_SDBR_Auditoria PRIMARY KEY,
    Fecha     DATETIME2(0)  NOT NULL CONSTRAINT DF_SDBR_Auditoria_Fecha DEFAULT (SYSDATETIME()),
    Usuario   NVARCHAR(50)  NOT NULL,
    Accion    VARCHAR(40)   NOT NULL,
    Pedido    NVARCHAR(30)  NULL,
    Producto  NVARCHAR(100) NULL,
    Origen    VARCHAR(30)   NULL,
    Destino   VARCHAR(30)   NULL,
    Detalle   NVARCHAR(MAX) NULL
);
CREATE INDEX IX_SDBR_Auditoria_Fecha ON dbo.SDBR_Auditoria (Fecha);
CREATE INDEX IX_SDBR_Auditoria_Pedido ON dbo.SDBR_Auditoria (Pedido);
GO
