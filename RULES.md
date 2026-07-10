# RULES.md — Reglas universales de biblio_skills (referencia numerada)

> Autogenerado por `install.ps1 -Project <ruta>`. No editar a mano.
> Regenerar cuando las reglas de biblio_skills cambien: `pwsh -File ../biblio_skills/install.ps1 -Project .`
> Las reglas se aplican automáticamente vía el CLAUDE.md global. Este fichero es solo referencia.

---

# Secretos y seguridad fail-closed

- Ningún valor sensible (API keys, passwords, tokens, URLs privadas) aparece nunca
  en el código. Van en `.env` (nunca en git) con un `.env.example` sin valores reales.
- Si detectas un hardcode en código existente, lo señalas y propones la corrección;
  no lo dejas pasar. Si el usuario pide una credencial en texto plano, la rechazas.
- Para generar tokens usa `secrets`/`cryptography`, nunca `random`.
- Nunca ejecutes shell con input sin sanitizar.

**Fail-closed en config que controla comportamiento crítico** (kill switch, feature
flag, modo paper/live, permisos): cualquier error al leer el fichero (permisos,
corrupción, ausencia) DEBE asumir el estado **más restrictivo**, no pasar en silencio.

- Correcto: `try: read → if error: assume BLOCKED/ACTIVE`.
- Incorrecto: `if file.exists(): read` — la ausencia del fichero desactiva la protección.

Razón: el fallo silencioso en un gate de seguridad es justo lo que el gate debe
prevenir. Fail-open convierte un error de infraestructura en un bypass.

[CI] La detección de secretos comiteados se enforca con `detect-secrets` en
pre-commit (ver `ci-templates/`).

---

# Tests

- Los tests se escriben en la **misma entrega** que la funcionalidad, no en un paso
  posterior. Cubrir mínimo: happy path + 2-3 casos adversos (input inválido, estado
  límite, fallo esperado).
- Marca correctamente los tests que requieren red o servicios externos
  (ej. `@pytest.mark.integration`).
- Antes de declarar una tarea completada, la suite pasa al 100%. Un test en rojo
  **bloquea** el cierre. Si un fallo es deuda preexistente ajena al cambio, se
  documenta explícitamente — nunca se silencia.
- **Política de Mocks:** Mockea solo las fronteras puras (APIs externas/Red/BBDD productivas/Tiempo). Todo el código interno propio debe probarse de forma real y conectada. El "sobre-mockeo" de funciones y clases internas está prohibido porque genera tests que pasan siempre pero no verifican nada.

Razón: el test escrito junto al código es el que de verdad refleja la intención;
añadido después tiende a ratificar lo que hay en vez de comprobarlo.

[CI] "Suite verde antes de cerrar" se enforca como gate de CI sobre el PR
(ver `ci-templates/github-actions-ci.yml`). La regla aquí es el estándar; el gate
es el que bloquea.

---

# Seguridad del cambio

**Antes de editar una función/clase/módulo existente:**

1. Lee la firma original (nombre, parámetros, tipos de retorno).
2. Identifica todos los callers (`grep` o equivalente).
3. Verifica compatibilidad con cada caller — no asumas que "se ve obvio".
4. Cualquier cambio de firma es un cambio de contrato: documéntalo y verifica todos
   los callers antes de proceder.

El cambio debe ser **quirúrgico** (mínima superficie). No refactorices módulos
completos sin requerimiento explícito.

**Al introducir o renombrar un concepto, ruta o convención**, busca en el repo las
referencias al anterior (`grep`) y actualízalas en la **misma pasada**. Incluye la
documentación normativa (README, reglas, AGENTS.md): una convención nueva que convive con la
vieja en otro fichero es una contradicción, no una mejora. Termina con un `grep` del término
viejo para confirmar que no quedan referencias sueltas.

**Diagnostica antes de parchear.** Si se reporta un error, no apliques un fix rápido:
analiza la causa raíz. Un parche que oculta el problema es peor que no hacer nada.

**Código sobre documentación.** Antes de actuar sobre cualquier afirmación documental
(README, docstring, whitepaper, AGENTS.md) que describa un comportamiento concreto,
lee el código y verifica que es correcta. La documentación es una hipótesis hasta
que se verifica; el hallazgo real es el código. Al detectar divergencia, corrige el
documento o el código según cuál sea incorrecto — ignorar la discrepancia no es opción.

**Excepción: documentos normativos.** Si el documento es *normativo* (un contrato, una
especificación, una política o una constitución que dicta lo que el código DEBE hacer), la
divergencia es una presunción de que el **código** está mal, no el documento. No "ajustes"
el contrato para que cuadre con el código sin autorización explícita: verifica cuál refleja
la intención y corrige el código si es él quien se desvía.

---

# Dependencias

Convención canónica del proyecto (por repo): **`requirements.in` + `requirements.lock`**, no
un `requirements.txt` mantenido a mano.

- *`requirements.in`* — dependencias **directas**, con el rango/versión mínima que necesites y
  un comentario de propósito. Si una dep es de infra/desarrollo (no de negocio), va en sección
  separada.
- *`requirements.lock`* — árbol completo clavado: `uv pip compile requirements.in -o requirements.lock`.
  Es lo reproducible y **va en git**. Se restaura con `uv pip sync requirements.lock`.
- No inventes dependencias: antes de un `import`, verifica que la librería existe y está
  declarada en `requirements.in`. Nunca asumas que está disponible sin comprobarlo.
- Objetivo: que `uv pip sync requirements.lock` reconstruya el entorno exacto, sin dependencias
  fantasma ni drift de versiones.

**Toolchain global (por máquina, NO por proyecto):** Git/GitHub CLI, Node.js/npm,
versión de Python, CLIs de calidad (pre-commit, ruff, detect-secrets), CLIs LLM
auxiliares (codex, claude, gemini), herramientas de sistema (poppler) y conexión
de `biblio_skills` con Antigravity. Se instala una vez con
`setup/bootstrap-machine.ps1` en Windows o `setup/bootstrap-machine.sh` en
Unix/WSL. Un `requirements.lock` global es un anti-patrón: rompe el aislamiento
y provoca conflictos de versión entre proyectos. Los instalables no-pip se
declaran en la sección "Comandos" del `AGENTS.md` del repo.

[CI] La coherencia "lo importado está declarado / lo declarado está instalado" es
comprobable y se enforca con checks de `ci-templates/`.

[CI] Todo entorno automatizado debe instalar desde `requirements.lock` con
`uv pip sync requirements.lock`. No uses `pip install -r requirements.txt` en CI, hooks ni
documentación nueva. Si un proyecto legado trae `requirements.txt`, migra a
`requirements.in` + `requirements.lock` antes de aplicar estas plantillas.

---

# Git y cierre de sesión

**Al cerrar cualquier sesión con cambios en disco** (código, tests, config, docs):

1. `git status` — identifica qué cambió.
2. **Commits atómicos secuenciales** — NUNCA agrupes cambios de naturaleza distinta (ej: refactor de código y actualización de README) en un solo "commit Frankenstein". Haz los `git add` y `git commit` por separado de forma automática y secuencial, **sin pedir intervención al usuario**.
3. `git push` para sincronizar con el remote.

Si el proyecto no tiene remote, avísalo: los cambios locales no tienen backup.
La automatización de este cierre vive en el workflow `/cierre`.

**Plan de trabajo por unidad lógica.** Cuando se acumulan varias mejoras o fixes,
agrúpalos por **unidad lógica** (un cambio coherente, verificable y revertible): un bloque
= una unidad + un test run + un commit. Los archivos tocados son indicador secundario, no
el criterio. Una sola pasada de tests por bloque. Las acciones que modifican estado externo
irreversible van en su propio bloque, aisladas del código. El orden entre bloques lo rigen
las dependencias técnicas, salvo que una corrección bloqueante para una fase prevalezca.

**Protocolo de pausa larga** (semanas/meses): suite limpia, limpieza de artefactos
huérfanos en directorios críticos, verificación de integridad de ficheros de
producción si hay checksums, y un briefing de reanudación (estado actual · qué hacer
primero · qué monitorizar · comandos de diagnóstico).

**Memoria del proyecto — dos capas, sin duplicar:**

1. *Automática y local (Antigravity):* los **Knowledge Items** son el mecanismo nativo.
   Un subagente de conocimiento extrae al cerrar cada conversación los hechos clave y los
   carga al inicio de la siguiente. No requiere mantenimiento manual. Limitación: son
   locales a la máquina y a Antigravity, no van en git, y NO los lee Claude Code.
2. *Portable y auditable (git):* memoria versionada que cualquier harness lee vía `@import`
   y que sobrevive a un cambio de PC. La estructura canónica la define la skill
   **`memory-keeper`** (`docs/memory/`: un índice `MEMORY.md` autogenerado + ficheros
   tipados). El estado de proyecto vive ahí como `docs/memory/project-state.md`, que es lo
   que `/cierre` actualiza. No crees ficheros de memoria ad-hoc fuera de ese sistema
   (saturación); usa memory-keeper, que es la fuente única de la capa portable.

---

# Disciplina de razonamiento

**Exploración vs. confirmación.** La exploración inicial no requiere hipótesis binaria:
sirve para entender un sistema desconocido y formular hipótesis. Antes de un experimento
*confirmatorio*, en cambio, define: (1) pregunta binaria, (2) criterio de éxito, (3) criterio
de falsificación. Si no hay falsificación posible, no lo llames experimento.

**Hechos vs. hipótesis.** Cuando una decisión dependa de información incompleta, separa
hechos observados, inferencias e hipótesis. No construyas sobre hipótesis tratadas como
hechos. Si una hipótesis condiciona el diseño, decláralo.

**Síntoma vs. causa estructural.** Dos disparadores distintos para la misma acción: *parar
y reexaminar*. (1) *Fallo repetido*: el sistema se rompe una y otra vez pese a correcciones
sucesivas → la causa probablemente es estructural, no el último bug. (2) *Deriva de
objetivo*: nada falla, pero la solución solo crece desarrollando la dirección ya iniciada en
lugar de resolver el problema correcto. Señales: las correcciones están al límite del
sistema; un cambio externo *podría explicar* el inicio del fallo (la coincidencia temporal
sugiere, no prueba — investígala); la premisa básica ya no se cumple. Acción en ambos casos:
reexamina las asunciones, reformula el objetivo y compáralo con una alternativa más simple,
en vez de añadir más ajustes.

**Cierre razonado.** Cuando descartes una dirección, feature o rama, documenta por qué se
abandona y qué tendría que cambiar para reconsiderarla. La evidencia negativa evita repetir
callejones sin salida.

> El alcance y la complejidad del diseño (empezar por lo mínimo, build-vs-buy, riesgos
> explícitos) están en la regla 08.

---

# Descubrimiento de skills (consultar antes de improvisar)

Al inicio de cualquier tarea **sustantiva** (más de un paso, o especializada), si ninguna
skill de dominio se ha activado obviamente, **consulta el catálogo de la biblioteca** antes
de improvisar una solución: usa la skill `skill-finder` (o lee `biblio_skills/INDEX.json`).

- Si existe una skill relevante y está instalada → úsala.
- Si existe pero no está instalada → léela desde `biblio_skills/skills/<x>/SKILL.md` para esta
  tarea y ofrece instalarla (junction) para el futuro.
- Si no existe y la tarea es recurrente/reutilizable → ofrece crearla vía
  `skill-development-framework`.

Razón: la biblioteca puede tener más skills de las que el usuario recuerda. Recordar qué
existe y proponerlo es trabajo del agente, no del usuario. No satures: propón, no instales sin
confirmación.

---

# Diseño mínimo y build-vs-buy

Aplica a capacidades **no triviales**: las que vas a mantener, las que tienen una alternativa
madura conocida, o las que cuestan un esfuerzo material. Por debajo de ese umbral (una función
corta, un script de un solo uso) construye y sigue — exigir este gate a lo trivial es la misma
burocracia anticipada que esta regla evita.

**Empieza por lo mínimo.** Propón la solución más pequeña que satisface el objetivo declarado.
Añade complejidad solo por un requisito concreto o un riesgo conocido, específico y plausible
—ponderado por su impacto: baja probabilidad con impacto grave (pérdida de datos, secreto
expuesto, acción irreversible) cuenta—. No uses riesgos genéricos para justificar frameworks,
abstracciones o automatización anticipada.

**"No hacer nada" es una opción.** Cuando evalúes crear, ampliar o extraer una capacidad,
comprueba primero si el repo ya cubre el caso con una regla, skill, workflow, plantilla CI o
memoria. Si está cubierto y no hay hueco real, responde "no" y referencia la fuente existente. Sé adversativo con tus propuestas. Ser adversativo no significa buscar una razón para no hacer nada: significa exigir que
cada cambio tenga un beneficio concreto.

**Quitar es mejor que añadir (Borrado Positivo).** Ejerce explícitamente la libertad de proponer la eliminación de código muerto, código comentado (zombie), features obsoletas o abstracciones sin uso demostrable. A menudo, la mejor manera de refactorizar o estabilizar un código problemático heredado no es rodearlo de más lógica protectora, sino proponer su eliminación directa.

**Reutilizar antes de construir.** Antes de implementar una capacidad propia —métrica, harness,
pipeline, evaluador, parser, orquestador, extractor, integración— revisa si existe una
herramienta, librería, estándar o patrón maduro que ya resuelva la parte genérica.

**Entregable previo (antes de construir a medida).** Declara, una línea cada uno:
1. la solución existente conocida, o "ninguna conocida";
2. por qué no basta;
3. qué parte es específica del dominio;
4. qué coste de mantenimiento introduces.
Si no has investigado prior art real, dilo.

**Construye solo lo diferencial.** No repliques infraestructura resuelta. Construye solo la capa
específica: reglas de negocio, adaptación al dominio, integración local, formato de salida o
restricciones propias.

**Sospecha de lo inventado — pero cierra el bucle.** Si propones un enfoque que no ves usado en
producción, asume primero que PUEDE haber una razón (coste, fragilidad, mantenimiento, seguridad,
escala, bugs ya resueltos) e investígala. Si tras investigarla no aparece, adoptarlo es legítimo:
documenta por qué. La novedad no es un defecto; la novedad **no investigada** sí.

**Riesgos y decisión explícitos.** Antes de recomendar un diseño relevante, declara los riesgos
principales (diseño, ejecución, operación, reversibilidad) — identificarlos no obliga a
mitigarlos, solo a no ocultarlos. Si construyes a medida pese a existir alternativa madura,
documenta la alternativa descartada, el trade-off aceptado y qué haría reconsiderar la decisión.

**Prioriza la comprensión humana sobre la elegancia o la generalidad:** ante dos soluciones, gana la más fácil de entender y mantener, aunque sea menos elegante o algo menos general.

---

# Resiliencia y Estabilidad

Prácticas para evitar que la automatización genere deuda técnica, corrumpa datos o entierre errores silenciosamente. Estas previenen los clásicos vicios de programación generativa.

## 1. Falla Rápido y Ruidoso (No Silent Swallows)

Queda **estrictamente prohibido ahogar errores técnicos**. Existe una tendencia patológica en la generación de código a envolver bloques que fallan con `try... except Exception: pass` o `catch (e) {}` genéricos para forzar que el programa no se detenga.

- Si el código entra en un estado inválido, falta un import, o una dependencia falla, el programa debe **explotar inmediatamente y con ruido** mostrando una traza (stacktrace) clara.
- Una excepción debe propagarse salvo que tengas una estrategia transaccional concreta para mitigarla (ej: reintentos de red).
- Un programa que choca ruidosamente es salvable; un programa que captura sus propios fallos sin registrarlos, genera silenciosamente datos corruptos en la base de datos.

## 2. Idempotencia Rigurosa (En Scripts y Manejo de Datos)

Todo script, tarea de automatización (especialmente en `backend-automation`), pipeline o notebook debe ser **estrictamente idempotente**. Esto significa que ejecutar tu script 1 vez debe generar exactamente el mismo resultado final en el sistema que ejecutarlo 100 veces seguidas.

- Evita usar el modo `append` ciego al generar archivos de salida; reescribe el estado consolidado o averigua qué IDs ya se escribieron para no duplicarlos (esto evita que el usuario tenga un archivo de Excel quintuplicado solo porque testeaste el código cinco veces).
- En bases de datos, utiliza cláusulas preventivas como `UPSERT`, `MERGE` o `ON CONFLICT` en lugar de `INSERT` a ciegas.
- Si envías correos masivos o haces llamadas destructivas a APIs, mantén un registro de "ya procesado" antes del envío real.
- Debes codificar asumiendo que el script fallará en el registro 50 de 100 por un problema de red, y el usuario lo re-ejecutará desde el principio esperando que tu script sepa qué omitir.
