# CUL — Corporación Universitaria Latinoamericana
**Facultad de Ingeniería**  
**Programa de Ingeniería de Sistemas y Computación**  

## Documento de Especificación de Requerimientos del Sistema (ERS)
**Estándar IEEE-830**

**Título del Proyecto:** Desarrollo de un sistema de información con motor analítico de scoring crediticio para la gestión operativa y financiera de micronegocios minoristas de Barranquilla  
**Presentado por:** Altime Andrés Heredia Jaimes y Andrés Felipe Segura Angulo  
**Docente:** Luis Cardozo  
**Barranquilla, Colombia — 2026**

---

## 1. Introducción

### 1.1 Propósito
El presente documento define las especificaciones funcionales y no funcionales bajo el estándar IEEE-830 para el desarrollo del sistema de información de escritorio con motor analítico de scoring crediticio. Su objetivo es servir de referencia técnica para el modelado de arquitectura (Fase 2) y la codificación modular en Python y SQLite (Fase 3).

### 1.2 Alcance del Sistema
El sistema es una solución monolítica de escritorio desarrollada en Python (Tkinter) con almacenamiento relacional local en SQLite. La aplicación automatiza el control de existencias, el registro transaccional en punto de venta (POS), la administración inmutable de cuentas por cobrar (Append-Only), la ejecución del motor experto de scoring crediticio y la generación de reportes para el cuadre diario de caja en micronegocios minoristas de Barranquilla.

### 1.3 Definiciones y Acrónimos
* **ERS:** Especificación de Requisitos del Sistema (IEEE-830).
* **POS:** Point of Sale (Punto de Venta).
* **CRM:** Customer Relationship Management (Gestión de Cuentas por Cobrar / Fiados).
* **Append-Only:** Modelo de persistencia inmutable en SQLite donde solo se permiten inserciones secuenciales, prohibiendo la eliminación o modificación de saldos pasados.
* **Cold-Start:** Mecanismo de evaluación inicial de cupo semilla para clientes sin historial registrado en el software.

---

## 2. Descripción General

### 2.1 Perspectiva del Producto
El software es un sistema independiente de arquitectura local (100% Offline) diseñado para ejecutarse sobre sistema operativo Windows (10/11) en equipos con recursos de hardware básicos. No requiere conectividad a internet, servidores remotos, facturación electrónica DIAN ni impresoras térmicas de tiquetes.

### 2.2 Funciones Principales
1. **Módulo de Autenticación y Seguridad:** Control de acceso mediante roles de usuario.
2. **Módulo de Gestión de Inventarios (CRUD):** Registro de catálogo, precios y alertas de stock bajo.
3. **Módulo Punto de Venta (POS):** Venta rápida por carrito o por monto global.
4. **Módulo de Cuentas por Cobrar (CRM / Fiados):** Expediente del cliente y registro inmutable de abonos (Append-Only).
5. **Motor Analítico de Scoring Crediticio:** Evaluación lineal ponderada de riesgo crediticio y protocolo Cold-Start.
6. **Módulo de Reportes Operativos:** Consolidación de cartera y cuadre diario de caja.

---

## 3. Requisitos Específicos

### 3.1 Requisitos Funcionales (RF)

| Código | Módulo | Nombre del Requisito | Descripción Operativa | Trazabilidad de Campo (Fase 1) | Prioridad |
|---|---|---|---|---|---|
| **RF-AUT-01** | Autenticación | Control de Acceso | El sistema debe permitir el inicio de sesión mediante credenciales (usuario y contraseña) encriptadas localmente. | Requisito de seguridad operativa | Alta |
| **RF-INV-01** | Inventarios | Registro de Productos | El sistema debe permitir la creación, edición, consulta y eliminación (CRUD) de productos con código de barras (código interno), nombre, costo, precio de venta y stock mínimo. | Chequeo #1 y #2 (Falta de control de existencias) | Alta |
| **RF-INV-02** | Inventarios | Categorización por Canasta | El sistema debe clasificar los productos en: Canasta Básica, Cesta Mixta y Consumo Suntuario para la evaluación del scoring. | Entrevista P-Q10 (Preferencia de fiado en primera necesidad) | Alta |
| **RF-INV-03** | Inventarios | Alertas de Stock Bajo | El sistema debe resaltar en la interfaz gráfica los productos cuya existencia sea menor o igual al límite mínimo definido. | Alcance de diseño de UI | Media |
| **RF-POS-01** | POS | Búsqueda y Carrito Rápido | El sistema debe permitir la selección de productos y armado de carrito en máximo 3 interacciones (clics/entradas). | Requisito de baja carga cognitiva en horas pico | Alta |
| **RF-POS-02** | POS | Venta por Monto Global | El sistema debe permitir registrar una venta rápida ingresando directamente un valor monetario global cuando el producto no esté catalogado. | Alcance Módulo POS | Media |
| **RF-POS-03** | POS | Tipo de Pago | El sistema debe permitir liquidar la transacción seleccionando la modalidad: Efectivo, Nequi/Transferencia o Crédito (Fiado). | Alcance Módulo POS y Delimitaciones | Alta |
| **RF-POS-04** | POS | Anticipo en Venta a Crédito (Abono Inicial) | El sistema debe permitir que, al registrar una venta con tipo de pago Crédito (Fiado), el cliente entregue un anticipo en efectivo al momento de la transacción. El sistema debe registrar en la cabecera de la venta tanto el total de la venta como el anticipo recibido, y debe generar el cargo en la cuenta por cobrar del cliente únicamente por el saldo neto financiado ($\text{Total de la Venta} - \text{Anticipo Recibido}$). Si el anticipo entregado es mayor o igual al total de la venta, el sistema debe rechazar la operación y exigir que se registre como una venta de contado (Efectivo o Nequi). | Vinculado a RF-POS-03 (Tipo de Pago) y RF-CXC-03 (Registro de Abonos) | Media |
| **RF-CXC-01** | CRM / Fiados | Registro de Clientes | El sistema debe permitir crear perfiles de clientes con ID único, nombre o apodo, y campos opcionales de teléfono y dirección. | Chequeo #5 y P-Q11 (53.3% usa solo apodo) | Alta |
| **RF-CXC-02** | CRM / Fiados | Historial Append-Only | El sistema no debe permitir la modificación ni eliminación de transacciones o abonos pasados. Todo evento se registrará de forma secuencial. | Chequeo #6 (66.7% borra o tacha registros en papel) | Alta |
| **RF-CXC-03** | CRM / Fiados | Registro de Abonos | El sistema debe procesar abonos parciales o totales actualizando automáticamente el saldo deudor de la cartera del cliente. | Alcance Módulo CRM | Alta |
| **RF-CXC-04** | CRM / Fiados | Comprobante Digital (PDF) | El sistema debe generar un comprobante digital en formato PDF por cada operación de fiado o abono, consultable y exportable. | Chequeo #8 (60% no entrega comprobante físico) | Alta |
| **RF-CXC-05** | CRM / Fiados | Visualización de Cupo | El sistema debe mostrar de forma visible en el perfil del cliente el cupo total asignado, el monto usado y el monto disponible. | Chequeo #11 (86.7% sin cupo anotado visiblemente) | Media |
| **RF-CXC-06** | CRM / Fiados | Bloqueo por Cupo Excedido | El sistema debe rechazar el registro de cualquier cargo a crédito cuyo saldo resultante supere el límite de crédito (cupo) asignado al cliente. Un cliente sin cupo asignado explícitamente (límite de crédito en $0) no debe poder recibir ningún cargo fiado, sin excepción. | Vinculado a RF-CXC-05 (Visualización de Cupo) y Chequeo #11 (86.7% de tenderos sin cupo anotado visiblemente) | Alta |
| **RF-SCR-01** | Scoring | Cálculo Dinámico de Score | El sistema debe calcular el puntaje S de 0 a 100 puntos evaluando las funciones de subvariables internalizadas sobre mora efectiva tras el plazo pactado de 8 días: $\text{Días de Mora Efectiva} = \max(0, \text{Días Transcurridos} - 8)$, aplicando los umbrales directos de calibración empírica en V1.1 (0 a 3 días = 100 pts; 4 a 6 días = 70 pts; 7 a 10 días = 30 pts; más de 10 días = 0 pts). | Matriz de Variables y Ponderaciones Calibrada (Fase 1) | Alta |
| **RF-SCR-02** | Scoring | Protocolo Cold-Start | Para clientes sin historial, el sistema evaluará únicamente V3.1 y sugerirá al tendero un cupo semilla entre $30.000 y $50.000 COP, según el nivel de vínculo del cliente, válido para los primeros 3 ciclos de pago oportunos. La asignación efectiva del cupo al perfil del cliente requiere confirmación operativa del tendero; el sistema no debe persistir el cupo de forma automática sin esa confirmación. | Entrevista P-Q6 y Alcance del Proyecto | Alta |
| **RF-SCR-03** | Scoring | Alerta y Bloqueo (Clase D) | Si el puntaje S es menor a 40 puntos (0-39 pts), el sistema debe bloquear automáticamente el otorgamiento de crédito y resaltar al cliente en color rojo. | Entrevista P-Q14 y Matriz de Decisión | Alta |
| **RF-SCR-04** | Scoring | Congelamiento por Riesgo (Clase C) | Si el puntaje S está entre 40 y 59 puntos, el sistema debe congelar el cupo y exigir un abono previo del 50% del saldo antes de despachar un nuevo fiado. | Matriz de Decisión (Fase 1) | Alta |
| **RF-SCR-05** | Scoring | Sugerencia de Incremento (Clase A) | Si el puntaje S está entre 80 y 100 puntos, el sistema debe sugerir al tendero la posibilidad de incrementar el cupo hasta en un 20%. | Matriz de Decisión (Fase 1) | Media |
| **RF-SCR-06** | Scoring | Aprobación Estándar (Clase B) | Si el puntaje S se ubica entre 60 y 79 puntos (Riesgo Medio / Clase B), el sistema debe autorizar la transacción manteniendo el cupo asignado y los plazos de cobro habituales sin aplicar restricciones o incrementos. | Matriz de Decisión y Alcance del Scoring | Alta |
| **RF-REP-01** | Reportes | Arqueo Diario de Caja | El sistema debe consolidar al final de la jornada el total ingresado por efectivo, transferencias y el volumen otorgado en fiado. | Alcance Módulo de Reportes | Alta |
| **RF-REP-02** | Reportes | Consolidado de Cartera | El sistema debe presentar el monto total de cartera activa y el consolidado clasificado por niveles de riesgo según V1.1: Cartera Vigente (0 a 3 días de mora efectiva), Alerta Preventiva (4 a 6 días), Cartera Congelada (7 a 10 días, según umbral P-Q9) y Cartera Crítica/Bloqueada (más de 10 días de mora efectiva). | Entrevista P-Q9 y Alcance Módulo Reportes | Media |

---

### 3.2 Requisitos No Funcionales (RNF)
* **RNF-01 (Operatividad Offline / Disponibilidad):** El sistema debe funcionar al 100% de manera local sin dependencia de acceso a internet ni conexión a servidores web.
* **RNF-02 (Usabilidad y Baja Carga Cognitiva):** La interfaz gráfica realizada en Tkinter debe utilizar botones de gran tamaño, fuentes de alto contraste y un diseño simplificado para adaptarse a comerciantes con diversa alfabetización digital.
* **RNF-03 (Rendimiento y Tiempo de Respuesta):** Las consultas de inventario, actualización de saldos y la ejecución del motor de scoring en SQLite no deben superar un tiempo de respuesta de 500 milisegundos.
* **RNF-04 (Portabilidad y Requisitos de Hardware):** La aplicación debe ejecutarse sobre el sistema operativo Windows (10/11) en computadores de escritorio o portátiles con especificaciones básicas (mínimo 2 GB de RAM y procesador Intel Celeron o equivalente).
* **RNF-05 (Integridad y Consistencia de Datos):** La base de datos SQLite debe estructurarse mediante restricciones de clave foránea (Foreign Keys) para evitar registros huérfanos de ventas o abonos.

---

### 3.3 Restricciones del Sistema (RS)

| Código | Restricción de Diseño y Dominio | Sustentación y Delimitación |
|---|---|---|
| **RS-01** | Exclusión de Facturación Electrónica DIAN | El software se concibe estrictamente como una herramienta de control administrativo interno para el tendero, prescindiendo de integración fiscal. |
| **RS-02** | Exclusión de Impresión Térmica de Tiquetes | El sistema no requiere hardware de impresión física; la emisión y consulta de comprobantes se gestionará exclusivamente en pantalla o formato digital PDF. |
| **RS-03** | Exclusión de Despliegue en la Nube y Móvil | La aplicación operará de forma monolítica 100% local en entorno Windows 10/11, sin sincronización distribuida ni soporte para dispositivos móviles. |
| **RS-04** | Exclusión de Centrales de Riesgo Bancario | El motor de scoring evaluará el riesgo mediante indicadores locales del comercio informal, sin conexión ni reportes a Datacrédito o TransUnion. |
| **RS-05** | Aprovisionamiento de Inventario en Unidades Enteras | El módulo de inventario gestiona las existencias en cantidades enteras (INTEGER). La recepción y abastecimiento de mercancía desde proveedores se asume operativamente en empaques o unidades enteras. El manejo de cantidades fraccionarias se restringe al despacho a granel en el Punto de Venta bajo una política de redondeo conservador hacia el piso (math.floor), constituyendo el ingreso fraccionario de mercancía una limitación conocida no soportada en el flujo regular. |
