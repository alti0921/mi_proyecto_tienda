# Sistema POS & Scoring Crediticio Heurístico para Micronegocios Minoristas

**Proyecto de Grado:** Desarrollo de un sistema de información con motor analítico de scoring crediticio para la gestión operativa y financiera de micronegocios minoristas de Barranquilla.  
**Autores:** Altime Andrés Heredia Jaimes, Andrés Felipe Segura Angulo  
**Repositorio Oficial:** [`alti0921/mi_proyecto_tienda`](https://github.com/alti0921/mi_proyecto_tienda)  
**Versión de Python:** 3.12+  
**Tecnología UI:** Python Standard Library (`tkinter` / `ttk`) — Sin dependencias gráficas externas pesadas.

---

## 1. Descripción y Arquitectura

El sistema integra un Punto de Venta (POS), control de inventario con redondeo direccional conservador (RS-05), libro contable inmutable para Cuentas por Cobrar (CxC append-only) y un **motor de decisión de scoring crediticio basado en reglas heurísticas** (sin machine learning de caja negra). 

El diseño se estructura bajo una **Arquitectura en 4 Capas**:
1. **Presentación (`/ui`):** Interfaz gráfica de escritorio en Tkinter con navegación multi-frame persistente, ciclo de vida de permisos reactivo en caliente (`al_mostrar()`) y captura de validaciones de negocio.
2. **Lógica de Negocio (`/services`):** Orquestador transaccional del POS (`pos_service`), motor de scoring (`scoring_service`), ledger contable (`cxc_service`), gestión de stock (`inventario_service`), autenticación (`auth_service`) y consolidados de arqueo/cartera (`reportes_service`).
3. **Dominio (`/models`):** Dataclasses puras de Python desacopladas del motor de persistencia (`Cliente`, `Producto`, `Venta`, `CuentaPorCobrar`, `Usuario`, etc.).
4. **Persistencia (`/db`):** SQLite relacional con llaves foráneas (`PRAGMA foreign_keys = ON`), checks de integridad y triggers de inmutabilidad append-only.

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

El sistema almacena sus datos en `db/tienda.db`. Para crear las tablas con sus triggers de inmutabilidad (`db/schema.sql`) y sembrar los datos de prueba (`db/seeds_test.sql`), ejecuta el siguiente comando multiplataforma en tu terminal:

### Opción A: Inicialización con comando Python (Recomendada)
```bash
python -c "import sqlite3; conn = sqlite3.connect('db/tienda.db'); conn.executescript(open('db/schema.sql', encoding='utf-8').read()); conn.executescript(open('db/seeds_test.sql', encoding='utf-8').read()); conn.close(); print('Base de datos inicializada y sembrada con exito.')"
```

### Opción B: Inicialización con CLI de SQLite3 (Alternativa)
Si dispones de la herramienta de línea de comandos `sqlite3`:
```bash
sqlite3 db/tienda.db < db/schema.sql
sqlite3 db/tienda.db < db/seeds_test.sql
```

---

## 5. Credenciales de Acceso para Pruebas

Los datos semilla configuran dos cuentas predefinidas con contraseñas hasheadas en SHA-256 con salt criptográfico:

| Rol | Usuario | Contraseña | Capacidades y Restricciones |
|---|---|---|---|
| **Administrador** | `admin` | `admin123` | **Acceso total:** Ventas POS, asignación y ajuste de cupos de crédito, creación/edición de productos en catálogo, desactivación lógica, ajustes manuales de stock, consulta de Arqueo Diario y acceso exclusivo al Consolidado Global de Cartera/CxC. |
| **Vendedor / Cajero** | `vendedor` | `vend123` | **Acceso operativo:** Ventas POS, registro de abonos en efectivo, ajustes manuales de stock (entradas y salidas) y consulta de Arqueo Diario de su turno. **Restricciones:** No puede asignar cupos a clientes, no puede crear/editar/desactivar productos del catálogo, y la pestaña de Cartera/CxC permanece bloqueada/deshabilitada reactivamente. |

---

## 6. Ejecución de la Aplicación de Escritorio

Con el entorno virtual activo y la base de datos inicializada, lanza la interfaz gráfica ejecutando el módulo principal de la UI:

```bash
python -m ui.app
```

### Recorrido por las 5 Pantallas del Sistema:
1. **Pantalla 1 — Login (`login.py`):** Autenticación de credenciales, alternador de visibilidad de contraseña y manejo genérico de errores (previene enumeración de usuarios).
2. **Pantalla 2 — Punto de Venta / POS (`pos.py`):** Catálogo de productos, buscador predictivo, venta rápida por monto global (RF-POS-02), carrito en memoria, cobro en efectivo/Nequi/crédito con cálculo de cambio, registro de anticipos en ventas a crédito (RF-POS-04) y visualización del badge de riesgo del cliente.
3. **Pantalla 3 — Perfil de Cliente & CxC (`perfil_cliente.py`):** Ficha demográfica editable, motor de scoring en vivo con recálculo dinámico en caliente ante cambios de vínculo social (SW3), sugerencia de cupo semilla para clientes nuevos (Cold-Start), asignación auditable de cupos (solo admin), registro de abonos sobre historial inmutable y **emisión de comprobantes digitales en PDF térmico 80mm con visor del sistema (RF-CXC-04)**.
4. **Pantalla 4 — Gestión de Inventario (`inventario.py`):** Catálogo maestro-detalle, resaltado en ámbar de productos bajo el umbral mínimo (RF-INV-03), badge global de alertas, formularios de creación/edición/baja lógica (solo admin) y stepper de ajuste de stock en unidades enteras (RS-05).
5. **Pantalla 5 — Reportes Operativos (`reportes.py`):** Contenedor con pestañas:
   - *Arqueo Diario:* Consulta por fecha, 5 tarjetas KPI con cálculo certificado de caja física (`ventas_efectivo + anticipos_credito + abonos_cxc`) y tabla cronológica de transacciones.
   - *Cartera / CxC (Solo Admin):* Bloqueo reactivo por rol, tarjetas resumen por banda de riesgo (Vigente, Preventiva, Congelada, Crítica) y filtros en memoria por clase y mora.

---

## 7. Ejecución de la Suite de Pruebas Automatizadas

El proyecto cuenta con una cobertura integral de **84 pruebas automatizadas** que validan la capa de seguridad, integridad contable, motor analítico, generación de comprobantes y reactividad de la interfaz gráfica.

Para correr toda la suite con detalle de ejecución:

```bash
pytest -v
```

### Distribución de la Suite (84 Tests):
- `tests/test_auth.py` (8 tests): Hashing seguro SHA-256 + salt, verificación resistente a timing attacks (`hmac.compare_digest`), autenticación case-insensitive (`COLLATE NOCASE`).
- `tests/test_cxc.py` (13 tests): Inmutabilidad append-only contra triggers SQL, control de límites de cupo (RF-CXC-06), prevención de saldos negativos, actualización de vínculo, persistencia auditable de `usuario_id` en cargos y abonos.
- `tests/test_inventario.py` (13 tests): Unicidad de códigos de barra, redondeo direccional conservador (`math.floor` en salidas / `math.ceil` en entradas), baja lógica con `ValueError`.
- `tests/test_pos.py` (12 tests): Orquestador atómico, bloqueo de ventas a crédito en Clase D (RF-SCR-03), regla de desbloqueo Clase C mediante abono $\ge 50\%$ (RF-SCR-04), transaccionalidad compuesta `auto_commit=False`, propagación de `usuario_id` al ledger.
- `tests/test_reportes.py` (8 tests): Consolidación de arqueo de caja física, integración estricta de bandas de mora (`PLAZO_ESTANDAR_DIAS = 8`) con `scoring_service`, **generación de comprobantes térmicos en PDF 80mm (`generar_comprobante_pdf`), validación de cajero histórico y caso legado**.
- `tests/test_scoring.py` (8 tests): Fórmulas de scoring ponderado ($S = 0.40 \cdot SW1 + 0.35 \cdot SW2 + 0.25 \cdot SW3$), rangos empíricos P-Q9 en mora efectiva, protocolo Cold-Start con desactivación por mora.
- `tests/test_ui.py` (22 tests): Ciclo de vida de sesión, componentes visuales, conmutación reactiva de permisos entre roles en caliente (Parche #19), flujo completo del POS, historial append-only, emisión de PDF desde perfil de cliente, ajuste con signo en inventario y bloqueo de pestañas en reportes.

---

## 8. Estructura del Repositorio

```text
mi_proyecto_tienda/
├── db/
│   ├── connection.py        # Conexión SQLite con PRAGMA foreign_keys = ON
│   ├── schema.sql           # DDL con 7 tablas, checks, triggers append-only e índices
│   └── seeds_test.sql       # Datos semilla para pruebas y desarrollo
├── models/                  # Dataclasses puras de dominio
│   ├── cliente.py
│   ├── cuenta_por_cobrar.py
│   ├── producto.py
│   ├── scoring_historial.py
│   ├── usuario.py
│   └── venta.py
├── services/                # Capa de lógica de negocio y transaccionalidad
│   ├── auth_service.py
│   ├── cxc_service.py
│   ├── inventario_service.py
│   ├── pos_service.py
│   ├── reportes_service.py
│   └── scoring_service.py
├── ui/                      # Interfaz gráfica de usuario en Tkinter
│   ├── app.py               # Ventana principal, navegación y gestión de sesión
│   ├── estilos.py           # Paleta de colores, semáforo de scoring y estilos ttk
│   ├── sesion.py            # Estado de sesión activa y verificación de roles
│   ├── widgets_comunes.py   # Área de error, botones restringidos, barra superior
│   └── pantallas/           # Vistas especializadas
│       ├── login.py
│       ├── pos.py
│       ├── perfil_cliente.py
│       ├── inventario.py
│       └── reportes.py
├── tests/                   # Suite de pruebas automatizadas (84 tests)
│   ├── test_auth.py
│   ├── test_cxc.py
│   ├── test_inventario.py
│   ├── test_pos.py
│   ├── test_reportes.py
│   ├── test_scoring.py
│   └── test_ui.py
├── docs/
│   ├── contexto_tecnico.md  # Bitácora técnica exhaustiva, parches y auditorías
│   ├── ERS.md               # Especificación de Requisitos de Software (IEEE-830)
│   ├── matriz_scoring.md    # Calibración empírica de variables de scoring
│   └── paso1_modelo_bd.md   # Justificación del modelo relacional
└── README.md                # Guía de instalación, ejecución y pruebas
```

---

## 9. Documentación Técnica de Referencia

Para detalles profundos sobre las decisiones de diseño, la matriz de trazabilidad entre requisitos funcionales (RF) y código, y el historial de los 20 parches técnicos certificados, consultar [`docs/contexto_tecnico.md`](docs/contexto_tecnico.md).
