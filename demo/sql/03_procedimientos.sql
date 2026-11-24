/*
================================================================================================
 DEMO · 03 · RESTABLECIMIENTO DIARIO
================================================================================================
 La demo es pública y sus cuentas son compartidas: cualquiera puede mover pedidos. Una vez al
 día la base vuelve a su estado inicial. La web llama a Demo_Reiniciar_Si_Toca en cada login
 (sdbr_web/datos/demo.py), que solo actúa la primera vez de cada día. No hay tarea programada:
 en Azure SQL con la oferta gratuita, despertar la base cada noche gastaría la cuota del mes.

 El "día" es el de Colombia (SA Pacific Standard Time), el mismo que usa la vista.
================================================================================================
*/

DROP PROCEDURE IF EXISTS dbo.Demo_Reiniciar_Si_Toca;
DROP PROCEDURE IF EXISTS dbo.Demo_Reiniciar;
GO

-- Vuelve al estado recién generado: estados de las líneas, historial (con las fechas desplazadas
-- igual que la vista), auditoría de los visitantes y bloqueos de las cuentas demo.
CREATE PROCEDURE dbo.Demo_Reiniciar
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @hoy DATE = CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'SA Pacific Standard Time' AS DATE);
    DECLARE @desfase INT = (SELECT DATEDIFF(DAY, Fecha_Generacion, @hoy) FROM dbo.Demo_Control);

    BEGIN TRANSACTION;

    DELETE FROM dbo.SDBR_MOV;
    INSERT INTO dbo.SDBR_MOV (pedconsecutivo, producto, Estado_SDBR, Estado_Final)
    SELECT pedconsecutivo, producto, Estado_SDBR, Estado_Final
    FROM dbo.Demo_Estado_Inicial;

    DELETE FROM dbo.Mov_Tiempo_Real3;
    INSERT INTO dbo.Mov_Tiempo_Real3 (Fecha_Mov, Pedido, Producto, Sale_De, Entra_A, Fecha_PSL,
                                      Tiempo_Pedido, On_time, Buffer_Zona, Retroceso, Calificacion)
    SELECT DATEADD(DAY, @desfase, Fecha_Mov), Pedido, Producto, Sale_De, Entra_A,
           DATEADD(DAY, @desfase, Fecha_PSL), Tiempo_Pedido, On_time, Buffer_Zona, Retroceso,
           Calificacion
    FROM dbo.Demo_Historial_Inicial;

    DELETE FROM dbo.SDBR_Auditoria WHERE Accion <> 'crear_usuario';

    UPDATE dbo.SDBR_Usuarios
    SET Intentos_Fallidos = 0, Bloqueado_Hasta = NULL
    WHERE Usuario LIKE 'demo.%';

    UPDATE dbo.Demo_Control SET Ultimo_Reinicio = @hoy;

    COMMIT TRANSACTION;
END;
GO

-- Restablece solo si hoy aún no se hizo. Devuelve una fila: Reiniciada = 1 si restableció.
-- UPDLOCK + HOLDLOCK sobre Demo_Control: dos logins simultáneos no restablecen dos veces.
CREATE PROCEDURE dbo.Demo_Reiniciar_Si_Toca
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @hoy DATE = CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'SA Pacific Standard Time' AS DATE);
    DECLARE @reiniciada BIT = 0;

    BEGIN TRANSACTION;

    IF NOT EXISTS (
        SELECT 1 FROM dbo.Demo_Control WITH (UPDLOCK, HOLDLOCK)
        WHERE Ultimo_Reinicio >= @hoy
    )
    BEGIN
        EXEC dbo.Demo_Reiniciar;
        SET @reiniciada = 1;
    END;

    COMMIT TRANSACTION;

    SELECT @reiniciada AS Reiniciada;
END;
GO
