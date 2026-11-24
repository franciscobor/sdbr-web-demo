/*
================================================================================================
 DEMO · 01 · ESQUEMA DEL FLUJO S-DBR
================================================================================================
 Base de demostración con datos ficticios. La ejecuta demo/instalar.py, que antes comprueba que
 la base es de demo (vacía o solo con objetos de la demo). Borra y vuelve a crear todo.

 Reproduce, con los mismos nombres y columnas, los objetos que SDBR Web lee y escribe (su
 "contrato" con la base de producción). Así el código de la web es el mismo en los dos sitios:
   - Pedidos_Fechas_Fin2_V3  vista de pedidos en planta con sus fechas y lead times por área
   - SDBR_MOV                estado actual de cada línea (la web hace UPDATE de Estado_SDBR)
   - Mov_Tiempo_Real3        historial de movimientos (la web hace INSERT y reclasifica)
   - vendedores_pedidos      vendedor de cada pedido (pantalla de Derogaciones)
 En producción la vista sale del ERP; aquí sale de Demo_Lineas, que llena generar_datos.py.

 Fechas vivas: los datos se generan una vez, pero la vista desplaza todas las fechas tantos días
 como hayan pasado desde la generación. Así el reparto de zonas de color no envejece y la demo se
 ve igual cualquier día. Demo_Reiniciar (03_procedimientos.sql) aplica el mismo desplazamiento
 al historial.

 Regla: cada pantalla nueva de la web que lea un objeto que aquí no está añade su réplica.
================================================================================================
*/

DROP VIEW IF EXISTS dbo.Pedidos_Fechas_Fin2_V3;
DROP TABLE IF EXISTS dbo.SDBR_MOV;
DROP TABLE IF EXISTS dbo.Mov_Tiempo_Real3;
DROP TABLE IF EXISTS dbo.vendedores_pedidos;
DROP TABLE IF EXISTS dbo.Demo_Estado_Inicial;
DROP TABLE IF EXISTS dbo.Demo_Historial_Inicial;
DROP TABLE IF EXISTS dbo.Demo_Lineas;
DROP TABLE IF EXISTS dbo.Demo_Control;
GO

-- Una sola fila: cuándo se generaron los datos y cuándo se restableció la demo por última vez.
CREATE TABLE dbo.Demo_Control (
    Id                TINYINT  NOT NULL CONSTRAINT PK_Demo_Control PRIMARY KEY
                               CONSTRAINT CK_Demo_Control_Una_Fila CHECK (Id = 1),
    Fecha_Generacion  DATE     NOT NULL,
    Ultimo_Reinicio   DATE     NULL,
    Semilla           INT      NOT NULL
);

-- Datos de cada línea de pedido tal como los daría el ERP, con las fechas del día de generación.
-- Lead times (Buffer_*) en días; Final_* es la fecha en que el área debe terminar.
CREATE TABLE dbo.Demo_Lineas (
    Id                  INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_Demo_Lineas PRIMARY KEY,
    pedconsecutivo      NVARCHAR(20)  NOT NULL,
    Producto            NVARCHAR(40)  NOT NULL,
    Descripcion         NVARCHAR(120) NOT NULL,
    NombCliente         NVARCHAR(120) NOT NULL,
    NombreFamilia       NVARCHAR(60)  NULL,
    Cantidad            INT           NOT NULL,
    FechaDocumen        DATETIME      NOT NULL,
    Final_Inge          DATETIME      NULL,
    Final_Plane         DATETIME      NULL,
    Final_Compras       DATETIME      NULL,
    Fecha_Venci_Espejo  DATETIME      NOT NULL,
    Buffer_Ing          INT           NULL,
    Buffer_Plane        INT           NULL,
    Buffer_Compras      INT           NULL,
    Buffer_Manuf        INT           NULL,
    CONSTRAINT UQ_Demo_Lineas UNIQUE (pedconsecutivo, Producto)
);

-- Estado actual de cada línea: lo único que mueve la web.
CREATE TABLE dbo.SDBR_MOV (
    Id              INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_SDBR_MOV PRIMARY KEY,
    pedconsecutivo  NVARCHAR(20) NOT NULL,
    producto        NVARCHAR(40) NOT NULL,
    Estado_SDBR     VARCHAR(30)  NOT NULL,
    Estado_Final    VARCHAR(20)  NOT NULL CONSTRAINT DF_SDBR_MOV_Final DEFAULT ('En_planta')
);
CREATE INDEX IX_SDBR_MOV_Pedido ON dbo.SDBR_MOV (pedconsecutivo, producto);

-- Copia del estado de SDBR_MOV recién generado: Demo_Reiniciar vuelve a él cada día.
CREATE TABLE dbo.Demo_Estado_Inicial (
    pedconsecutivo  NVARCHAR(20) NOT NULL,
    producto        NVARCHAR(40) NOT NULL,
    Estado_SDBR     VARCHAR(30)  NOT NULL,
    Estado_Final    VARCHAR(20)  NOT NULL,
    CONSTRAINT PK_Demo_Estado_Inicial PRIMARY KEY (pedconsecutivo, producto)
);

-- Historial de movimientos, con las columnas que escribe la web (dominio/movimientos.py).
CREATE TABLE dbo.Mov_Tiempo_Real3 (
    Id             INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_Mov_Tiempo_Real3 PRIMARY KEY,
    Fecha_Mov      DATETIME      NOT NULL,
    Pedido         NVARCHAR(20)  NOT NULL,
    Producto       NVARCHAR(40)  NOT NULL,
    Sale_De        VARCHAR(30)   NOT NULL,
    Entra_A        VARCHAR(30)   NOT NULL,
    Fecha_PSL      DATETIME      NULL,
    Tiempo_Pedido  FLOAT         NULL,   -- buffer global del pedido al moverse
    On_time        INT           NULL,   -- 1 si el buffer del área era <= 100
    Buffer_Zona    INT           NULL,   -- buffer del área al moverse
    Retroceso      VARCHAR(2)    NOT NULL,
    Calificacion   VARCHAR(10)   NOT NULL
);
CREATE INDEX IX_Mov_Tiempo_Real3_Pedido ON dbo.Mov_Tiempo_Real3 (Pedido, Sale_De, Calificacion);

-- Historial de la semilla, con las fechas del día de generación.
CREATE TABLE dbo.Demo_Historial_Inicial (
    Fecha_Mov      DATETIME      NOT NULL,
    Pedido         NVARCHAR(20)  NOT NULL,
    Producto       NVARCHAR(40)  NOT NULL,
    Sale_De        VARCHAR(30)   NOT NULL,
    Entra_A        VARCHAR(30)   NOT NULL,
    Fecha_PSL      DATETIME      NULL,
    Tiempo_Pedido  FLOAT         NULL,
    On_time        INT           NULL,
    Buffer_Zona    INT           NULL,
    Retroceso      VARCHAR(2)    NOT NULL,
    Calificacion   VARCHAR(10)   NOT NULL
);

CREATE TABLE dbo.vendedores_pedidos (
    peeconsecutivo  NVARCHAR(20)  NOT NULL CONSTRAINT PK_vendedores_pedidos PRIMARY KEY,
    tgenombre       NVARCHAR(80)  NOT NULL
);
GO

-- La vista que leen todas las pantallas del flujo. Buffer es el buffer global del pedido:
-- el porcentaje consumido del tiempo total entre la fecha del pedido y la fecha comprometida.
CREATE VIEW dbo.Pedidos_Fechas_Fin2_V3
AS
WITH Desfase AS (
    SELECT DATEDIFF(
               DAY,
               Fecha_Generacion,
               CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'SA Pacific Standard Time' AS DATE)
           ) AS Dias
    FROM dbo.Demo_Control
),
Lineas AS (
    SELECT
        l.pedconsecutivo,
        l.Producto,
        l.Descripcion,
        l.NombCliente,
        l.NombreFamilia,
        l.Cantidad,
        DATEADD(DAY, d.Dias, l.FechaDocumen)       AS FechaDocumen,
        DATEADD(DAY, d.Dias, l.Final_Inge)         AS Final_Inge,
        DATEADD(DAY, d.Dias, l.Final_Plane)        AS Final_Plane,
        DATEADD(DAY, d.Dias, l.Final_Compras)      AS Final_Compras,
        DATEADD(DAY, d.Dias, l.Fecha_Venci_Espejo) AS Fecha_Venci_Espejo,
        l.Buffer_Ing,
        l.Buffer_Plane,
        l.Buffer_Compras,
        l.Buffer_Manuf,
        m.Estado_SDBR,
        m.Estado_Final
    FROM dbo.Demo_Lineas AS l
    INNER JOIN dbo.SDBR_MOV AS m
        ON m.pedconsecutivo = l.pedconsecutivo AND m.producto = l.Producto
    CROSS JOIN Desfase AS d
)
SELECT
    pedconsecutivo,
    NombCliente,
    Producto,
    Descripcion,
    Cantidad,
    NombreFamilia,
    FechaDocumen,
    Final_Inge,
    Final_Plane,
    Final_Compras,
    Fecha_Venci_Espejo,
    Buffer_Ing,
    Buffer_Plane,
    Buffer_Compras,
    Buffer_Manuf,
    CAST(ROUND(
        (1.0 - DATEDIFF(
                   DAY,
                   CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'SA Pacific Standard Time' AS DATE),
                   Fecha_Venci_Espejo
               ) * 1.0 / NULLIF(DATEDIFF(DAY, FechaDocumen, Fecha_Venci_Espejo), 0)
        ) * 100, 0) AS INT) AS Buffer,
    Estado_SDBR,
    Estado_Final
FROM Lineas;
GO
