# Sistema POS & Scoring Crediticio Heurístico para Micronegocios Minoristas

**Proyecto de Grado:** Desarrollo de un sistema de información con motor analítico de scoring crediticio para la gestión operativa y financiera de micronegocios minoristas de Barranquilla.  
**Autores:** Altime Andrés Heredia Jaimes, Andrés Felipe Segura Angulo  
**Repositorio Oficial:** [`alti0921/mi_proyecto_tienda`](https://github.com/alti0921/mi_proyecto_tienda)  
**Versión de Python:** 3.12+  
**Tecnología UI:** Python Standard Library (`tkinter` / `ttk`) — Sin dependencias gráficas externas pesadas.

---

## 1. Descripción y Arquitectura

El sistema integra un Punto de Venta (POS), control de inventario con redondeo direccional conservador (RS-05), libro contable inmutable para Cuentas por Cobrar (CxC append-only), gestión de usuarios y roles con control de acceso reactivo (RBAC) y un **motor de decisión de scoring crediticio basado en reglas heurísticas transparentes** (Matriz de Scoring v2.0, sin machine learning de caja negra). 

El diseño se estructura bajo una **Arquitectura en 4 Capas**:
1. **Presentación (`/ui`):** Interfaz gráfica de escritorio en Tkinter con navegación multi-frame persistente, ciclo de vida de permisos reactivo en caliente (`al_mostrar()`), diálogo común de alta de clientes y captura de validaciones de negocio.
2. **Lógica de Negocio (`/services`):** Orquestador transaccional del POS (`pos_service`), motor de scoring y sugerencias de cupo (`scoring_service`), ledger contable (`cxc_service`), gestión de stock (`inventario_service`), autenticación y usuarios (`auth_service`), utilidades de fecha y zona horaria (`fechas.py`) y consolidados de arqueo/cartera (`reportes_service`).
3. **Dominio (`/models`):** Dataclasses puras de Python desacopladas del motor de persistencia (`Cliente`, `Producto`, `Venta`, `VentaDetalle`, `CuentaPorCobrar`, `Usuario`, `ScoringHistorial`).
4. **Persistencia (`/db`):** SQLite relacional con llaves foráneas (`PRAGMA foreign_keys = ON`), checks de integridad, triggers de inmutabilidad append-only y módulo de migraciones automáticas no destructivas (`migraciones.py`).

---

## 2. Requisitos Previos

- **Python 3.12 o superior** instalado en el sistema.
- Soporte de **Tkinter** habilitado (incluido por defecto en las distribuciones estándar de Python para Windows y macOS; en distribuciones Linux basadas en Debian/Ubuntu instalar con `sudo apt-get install python3-tk`).
- Git (opcional, para clonar y control de versiones).

---

## 3. Instalación y Configuración del Entorno

### Paso 1: Clonar o descargar el repositorio
```bash
git clone https://github.com/alti0921/mi_proyecto_tienda.git
cd mi_proyecto_tienda
```

### Paso 2: Crear el entorno virtual (`venv`)
En la raíz del proyecto:
```bash
python -m venv venv
```

### Paso 3: Activar el entorno virtual
- **Windows (PowerShell):**
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- **Windows (Símbolo del sistema / CMD):**
  ```cmd
  venv\Scripts\activate.bat
  ```
- **Linux / macOS (Bash / Zsh):**
  ```bash
  source venv/bin/activate
  ```

### Paso 4: Instalar dependencias
La aplicación utiliza la biblioteca estándar de Python (`sqlite3`, `tkinter`, `dataclasses`, `hashlib`, `hmac`). Se requiere `reportlab` para la generación de comprobantes en PDF de formato térmico 80mm (RF-CXC-04) y `pytest` para la ejecución de pruebas:
```bash
pip install pytest reportlab
```

---

## 4. Inicialización y Sembrado de la Base de Datos

El sistema almacena sus datos en `db/tienda.db`. Para inicializar de forma segura la base de datos sin riesgo de sobreescribir datos existentes, ejecuta el siguiente comando:

```bash
python -c "import os, sqlite3; p='db/tienda.db'; print('La base ya existe; no se reinicializa. Las migraciones se aplican solas al abrir la aplicación.') if os.path.exists(p) else (lambda c: [c.executescript(open('db/schema.sql', encoding='utf-8').read()), c.executescript(open('db/seeds_test.sql', encoding='utf-8').read()), c.close(), print('Base de datos inicializada y sembrada con éxito.')])(sqlite3.connect(p))"
```

> [!WARNING] Advertencia crítica sobre la base de datos:
> NUNCA ejecutes `db/schema.sql` directamente sobre una base de datos con datos reales (`db/tienda.db`), ya que comienza con instrucciones `DROP TABLE` y borraría irreversiblemente toda la información. Las modificaciones y adiciones de esquema en bases existentes se aplican automáticamente y de forma segura a través de `db/migraciones.py`, el cual genera primero un respaldo con timestamp (`db/*.bak-*`) antes de realizar cualquier cambio estructural.

---

## 5. Credenciales de Acceso para Pruebas

Los datos semilla configuran dos cuentas predefinidas con contraseñas hasheadas en SHA-256 con salt criptográfico individual. **Estas credenciales son exclusivas para pruebas y desarrollo local; deben cambiarse obligatoriamente desde la pantalla "Usuarios" antes de poner el sistema en producción en una tienda real (longitud mínima de 6 caracteres):**

| Rol | Usuario | Contraseña | Capacidades y Restricciones |
|---|---|---|---|
| **Administrador** | `admin` | `admin123` | **Acceso total:** Ventas POS, asignación y ajuste de cupos y plazos pactados (8/15 días), confirmación de sugerencias de cupo (+20%), creación/edición de productos en catálogo, desactivación lógica, ajustes manuales de stock, consulta de Arqueo Diario, acceso exclusivo al Consolidado Global de Cartera/CxC y gestión de usuarios (crear usuarios con rol, desactivar/reactivar y restablecer contraseñas). |
| **Vendedor / Cajero** | `vendedor` | `vend123` | **Acceso operativo:** Ventas POS, alta rápida de clientes con datos demográficos básicos, registro de abonos en efectivo, emisión de comprobantes PDF, ajustes de stock y consulta del Arqueo Diario del día completo. **Restricciones:** No puede asignar o modificar cupos/plazos a clientes, no puede crear/editar/desactivar productos del catálogo, no puede acceder a la pestaña de Cartera/CxC y en la pantalla de Usuarios únicamente puede cambiar su propia contraseña. |

---

## 6. Ejecución de la Aplicación de Escritorio

Con el entorno virtual activo y la base de datos inicializada, lanza la interfaz gráfica ejecutando el módulo principal de la UI:

```bash
python -m ui.app
```

### Recorrido por las 6 Pantallas del Sistema:
1. **Pantalla 1 — Login (`login.py`):** Autenticación de credenciales, alternador de visibilidad de contraseña y manejo genérico de errores (previene enumeración de usuarios).
2. **Pantalla 2 — Punto de Venta / POS (`pos.py`):** Catálogo de productos, buscador predictivo por nombre o código de barras, **adición directa de producto al carrito mediante tecla Enter en máximo 2 interacciones (RF-POS-01)**, **botón de alta rápida de nuevos clientes mediante diálogo común (`DialogoNuevoCliente`, RF-CXC-01)**, venta rápida por monto global (RF-POS-02), carrito en memoria, cobro en efectivo/Nequi/crédito con cálculo de cambio, registro de anticipos en ventas a crédito (RF-POS-04) y visualización del badge de riesgo y reglas de veto R1/R2 del cliente.
3. **Pantalla 3 — Perfil de Cliente & CxC (`perfil_cliente.py`):** Ficha demográfica editable, alta mediante diálogo modal común, configuración de cupo y **plazo pactado por cliente (8 días semanal / 15 días quincenal, RF-CXC-07)**, motor de scoring en vivo (SW1/SW2/SW3), **sugerencia de incremento de cupo (+20%) para clientes Clase A aplicable exclusivamente bajo confirmación explícita del administrador (RF-SCR-05)**, sugerencia de cupo semilla para clientes en Cold-Start, registro de abonos sobre historial inmutable con fechas en hora local, **columna auditable de cajero/usuario responsable** y **emisión de comprobantes digitales en PDF térmico 80mm del movimiento seleccionado en la tabla (RF-CXC-04)**.
4. **Pantalla 4 — Gestión de Inventario (`inventario.py`):** Catálogo maestro-detalle, resaltado en ámbar de productos bajo el umbral mínimo (RF-INV-03), badge global de alertas, formularios de creación/edición/baja lógica (solo admin) y stepper de ajuste de stock en unidades enteras (RS-05).
5. **Pantalla 5 — Reportes Operativos (`reportes.py`):** Contenedor con pestañas:
   - *Arqueo Diario:* Consulta por fecha agrupada en hora local (`strftime(..., 'localtime')`), 5 tarjetas KPI con cálculo certificado de caja física (`ventas_efectivo + anticipos_credito + abonos_cxc`) y tabla cronológica de transacciones en hora local.
   - *Cartera / CxC (Solo Admin):* Bloqueo reactivo por rol, tarjetas resumen por banda de riesgo según mora efectiva FIFO (Vigente, Preventiva, Congelada Clase C por veto R1, Crítica Clase D por veto R2) y filtros en memoria por clase y mora.
6. **Pantalla 6 — Gestión de Usuarios (`usuarios.py`):** Panel administrativo para la creación de cuentas de usuario, asignación de roles (admin/vendedor), activación/desactivación de usuarios con **protección que impide desactivar al último administrador activo**, restablecimiento de contraseñas de otros usuarios por el administrador y formulario de cambio seguro de contraseña para el usuario actualmente autenticado (RF-AUT-02, RF-AUT-03).

---

## 7. Ejecución de la Suite de Pruebas Automatizadas

El proyecto cuenta con una cobertura integral de **162 pruebas automatizadas** que validan la capa de seguridad, integridad contable, motor analítico heurístico, reglas de veto, persistencia en UTC con presentación en hora local, scripts de rendimiento y reactividad de la interfaz gráfica.

Para correr toda la suite con detalle de ejecución:

```bash
pytest -v
```

### Distribución de la Suite (162 Tests):
- `tests/test_auth.py` (15 tests): Hashing seguro SHA-256 + salt, verificación resistente a timing attacks (`hmac.compare_digest`), autenticación case-insensitive (`COLLATE NOCASE`), cambio de contraseña con validación de contraseña actual y longitud mínima (6 caracteres), protección contra desactivación del último administrador activo (RF-AUT-03).
- `tests/test_cxc.py` (15 tests): Inmutabilidad append-only contra triggers SQL, control de límites de cupo (RF-CXC-06), prevención de saldos negativos, actualización de vínculo, persistencia auditable de `usuario_id` y `cajero_nombre` en cargos y abonos, soporte de plazo pactado (8/15 días) (RF-CXC-07).
- `tests/test_fechas.py` (2 tests): Conversión de marcas de tiempo UTC almacenadas por SQLite a la zona horaria local del sistema (`a_hora_local`), manejo de valores nulos, cadenas vacías y entradas inválidas.
- `tests/test_inventario.py` (13 tests): Unicidad de códigos de barra, redondeo direccional conservador (`math.floor` en salidas / `math.ceil` en entradas), baja lógica con `ValueError`, alertas de stock mínimo.
- `tests/test_migraciones.py` (3 tests): Verificación de claves foráneas activas, migración segura de bases de datos legadas con respaldo automático previo (`.bak`) e idempotencia ante bases sin inicializar.
- `tests/test_pos.py` (15 tests): Orquestador atómico, bloqueo de ventas a crédito en Clase D (RF-SCR-03), regla de desbloqueo Clase C mediante abono $\ge 50\%$ (RF-SCR-04), transaccionalidad compuesta `auto_commit=False`, propagación de `usuario_id` al ledger, asignación de cupo con plazo pactado y reglas de veto R1/R2.
- `tests/test_rendimiento_script.py` (2 tests): Ejecución del script de medición de rendimiento bajo base de datos temporal con volúmenes reducidos (verificación de 5 operaciones, consistencia de `COUNT(*)`) y rechazo estricto contra la base de producción `db/tienda.db`.
- `tests/test_reportes.py` (10 tests): Consolidación de arqueo de caja física agrupado por día en hora local (`strftime(..., 'localtime')`), clasificación de bandas de mora según Matriz de Scoring v2.0, emisión de comprobantes en PDF térmico 80mm del movimiento seleccionado con cajero registrado y hora local.
- `tests/test_scoring.py` (39 tests): Motor analítico heurístico completo (Matriz v2.0), mora efectiva con referencia FIFO (ignora cargos saldados), reglas de veto R1 (mora efectiva de 7 a 10 días $\rightarrow$ como máximo Clase C) y R2 (mora > 10 días $\rightarrow$ Clase D), predominancia de categorías por valor comprado (V2.2), protocolo Cold-Start con plazo pactado (8/15 días) y graduación por 3 ciclos de pago oportunos, y sugerencia de aumento de cupo (+20%) para clientes Clase A (RF-SCR-05).
- `tests/test_ui.py` (48 tests): Ciclo de vida de sesión, componentes visuales reactivos (`AreaError`, `BotonRestringidoPorRol`), alta de clientes desde POS con diálogo común (`DialogoNuevoCliente`), adición de producto al carrito con tecla Enter en $\le 2$ interacciones (RF-POS-01), sugerencia de +20% aplicable solo tras confirmación explícita, visualización de reglas de veto en POS y perfil, panel de gestión de usuarios (Pantalla 6), cambio de contraseña y comprobantes PDF del movimiento seleccionado.

---

## 8. Medición de Rendimiento (RNF-03)

El sistema incluye una herramienta automatizada de evaluación de desempeño contra los umbrales de tiempo de respuesta exigidos en el requisito no funcional **RNF-03** ($\le 500$ milisegundos para operaciones transaccionales clave). El umbral de 500 ms aplica a las operaciones individuales (inventario, saldo y scoring de un cliente); el consolidado de cartera se mide solo como referencia analítica e informativa.

Para ejecutar la prueba de rendimiento:

```bash
python -m scripts.medir_rendimiento
```

> [!NOTE] Base de datos temporal:
> Este script genera una base de datos SQLite completamente aislada en un directorio temporal (`tempfile.TemporaryDirectory`) poblada con 500 productos, 200 clientes, 5.000 movimientos en cuentas por cobrar y 2.000 ventas. Al finalizar las mediciones, exporta los resultados a `scripts/resultados_rendimiento.csv` y destruye la base temporal sin alterar bajo ninguna circunstancia la base de producción `db/tienda.db`.

---

## 9. Estructura del Repositorio

```text
mi_proyecto_tienda/
├── db/
│   ├── connection.py            # Conexión SQLite con PRAGMA foreign_keys = ON y migraciones
│   ├── migraciones.py           # Migraciones seguras no destructivas con respaldo automático (.bak)
│   ├── schema.sql               # DDL con 7 tablas, checks, triggers append-only e índices
│   └── seeds_test.sql           # Datos semilla para pruebas y desarrollo
├── models/                      # Dataclasses puras de dominio
│   ├── cliente.py
│   ├── cuenta_por_cobrar.py
│   ├── producto.py
│   ├── scoring.py
│   ├── usuario.py
│   ├── venta.py
│   └── venta_detalle.py
├── services/                    # Capa de lógica de negocio y transaccionalidad
│   ├── auth_service.py          # Autenticación, hash SHA-256 con sal, RBAC y gestión de usuarios
│   ├── cxc_service.py           # Libro contable append-only, auditoría de cajero y límites
│   ├── fechas.py                # Conversión de marcas de tiempo UTC a hora local del SO
│   ├── inventario_service.py    # Catálogo, redondeo conservador y alertas de stock
│   ├── pos_service.py           # Orquestador atómico del POS, validaciones y anticipos
│   ├── reportes_service.py      # Arqueo de caja física, cartera y comprobantes PDF 80mm
│   └── scoring_service.py       # Motor analítico heurístico, veto R1/R2, FIFO y sugerencia +20%
├── ui/                          # Interfaz gráfica de usuario en Tkinter
│   ├── app.py                   # Ventana principal, enrutador y navegación reactiva
│   ├── estilos.py               # Paleta de colores, semáforo de scoring y estilos ttk
│   ├── sesion.py                # Estado de sesión activa y verificación de roles
│   ├── widgets_comunes.py       # Área de error, botones restringidos, barra superior y modales
│   └── pantallas/               # Vistas especializadas
│       ├── inventario.py        # Pantalla 4: Catálogo y ajuste de stock
│       ├── login.py             # Pantalla 1: Inicio de sesión
│       ├── perfil_cliente.py    # Pantalla 3: Perfil demográfico, cupo, scoring y CxC
│       ├── pos.py               # Pantalla 2: Punto de venta con alta rápida y búsqueda Enter
│       ├── reportes.py          # Pantalla 5: Arqueo diario y cartera global
│       └── usuarios.py          # Pantalla 6: Gestión de usuarios y cambio de contraseñas
├── scripts/                     # Scripts de diagnóstico y medición
│   ├── __init__.py
│   └── medir_rendimiento.py     # Medición automatizada RNF-03 bajo base temporal
├── tests/                       # Suite completa de pruebas automatizadas (162 tests)
│   ├── conftest.py              # Fixtures compartidas y semillas en memoria
│   ├── test_auth.py
│   ├── test_cxc.py
│   ├── test_fechas.py
│   ├── test_inventario.py
│   ├── test_migraciones.py
│   ├── test_pos.py
│   ├── test_rendimiento_script.py
│   ├── test_reportes.py
│   ├── test_scoring.py
│   └── test_ui.py
├── docs/                        # Documentación técnica
│   └── historico_v1/            # Registro histórico de especificaciones de la versión 1.0
│       ├── ERS.md
│       ├── contexto_tecnico.md
│       ├── matriz_scoring.md
│       ├── paso1_modelo_bd.md
│       └── LEEME.md
├── .gitignore                   # Exclusiones de Git (bases .db, respaldos .bak, reportes temporales)
└── README.md                    # Guía general de instalación, uso y arquitectura
```

---

## 10. Documentación Técnica de Referencia

La documentación oficial y actualizada del sistema corresponde a la suite de documentos **Versión 2.0** en formato `.docx` entregada como parte del proyecto de grado (no incluida en este repositorio):
- **ERS v2.0 (Especificación de Requisitos del Sistema, IEEE-830)**
- **Matriz de Variables y Ponderaciones Calibrada v2.0**
- **Modelo Entidad-Relación v2.0**
- **Blueprint de Arquitectura del Sistema v2.0**
- **Wireframes de Interfaz v2.0**
- **Contexto Técnico del Proyecto**

Los documentos Markdown preliminares de la fase inicial (anteriores al 8 de octubre de 2026) han sido archivados como referencia histórica en [`docs/historico_v1/`](docs/historico_v1/LEEME.md).
