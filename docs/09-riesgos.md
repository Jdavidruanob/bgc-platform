# 09 — Registro de riesgos

> Escala: Probabilidad (A=Alta, M=Media, B=Baja) × Impacto (A=Alto, M=Medio, B=Bajo)

---

## Riesgos que pueden mover dinero incorrectamente

> Para estos, la mitigación es un mecanismo técnico, no "tener cuidado".

---

### R-01 — Transcripción errónea de montos
**Probabilidad:** M | **Impacto:** A

Whisper puede transcribir "ciento veinte" como "120.000" o "20.000" dependiendo del contexto. Un monto equivocado en el registro es un error financiero real.

**Mitigación técnica:**
1. El resumen de confirmación formatea el monto con separadores de miles en estilo colombiano (`$120.000`) para que el operador lo vea antes de confirmar. El operador es la validación final.
2. Los schemas de intención tienen `gt=0` en montos; un monto de `0` o negativo es rechazado en la capa NLU antes de llegar a la API.
3. Para montos que parezcan inusualmente grandes (heurística: > $5.000.000 en un aporte individual), el bot añade un aviso: ⚠️ "Este monto parece inusual. ¿Es correcto?"

---

### R-02 — Resolución errónea de entidades (socio equivocado)
**Probabilidad:** M | **Impacto:** A

El bot puede identificar "Pedro" como Pedro A cuando el operador quería decir Pedro B. Si la operación se confirma, el movimiento queda registrado en el socio incorrecto.

**Mitigación técnica:**
1. El resumen de confirmación siempre muestra el **nombre completo** tal como está en la DB (no el nombre como fue dicho). Si el operador dijo "Pedro" pero el resumen dice "Pedro Luis García Suárez", puede notar la diferencia.
2. Si hay más de un candidato con score ≥ 0.70, el bot **siempre** presenta la lista, incluso si el primer candidato tiene score 1.0.
3. El umbral de resolución automática es 0.85 para match único, no 0.70. Por debajo de 0.85 siempre se pide confirmación.
4. Después de la desambiguación, el resumen dice explícitamente "¿Confirmas que [nombre completo] es la persona correcta?" antes de ejecutar.

---

### R-03 — Operación duplicada (doble envío)
**Probabilidad:** B | **Impacto:** A

El operador envía el mismo mensaje dos veces (ej: doble tap accidental en Telegram), o la red reenvía el webhook de Telegram.

**Mitigación técnica:**
1. La API implementa **idempotencia obligatoria**: cada request de escritura lleva un `Idempotency-Key` único generado por el bot. El segundo request con la misma key retorna el resultado original sin re-ejecutar la operación.
2. La key se genera por el bot al inicio del flujo de confirmación (no al recibir el mensaje), lo que garantiza que la key cubre exactamente la operación confirmada.
3. Las keys se almacenan 24 horas. Cualquier reintento dentro de esa ventana es idempotente.

---

### R-04 — Alucinación del LLM (intención incorrecta)
**Probabilidad:** B | **Impacto:** A

El LLM produce un JSON sintácticamente válido pero semánticamente incorrecto: socio diferente, monto inventado, intención equivocada.

**Mitigación técnica:**
1. El LLM no puede inventar IDs de socios ni montos calculados; esos campos no existen en el schema de intención del LLM.
2. Los schemas Pydantic de `coop-contracts` validan el JSON antes de usarlo. Un JSON inválido produce `incompleta` o `desconocida`, no una operación silenciosa.
3. El resumen de confirmación muestra **datos resueltos** (nombres reales de la DB, no lo que dijo el LLM) antes de ejecutar. El operador puede detectar la alucinación en ese momento.
4. El prompt del sistema instruye explícitamente al LLM que produzca `incompleta` cuando le falten datos, no que invente valores.

---

### R-05 — Aporte aplicado a socio incorrecto por homónimos en la DB
**Probabilidad:** B | **Impacto:** A

Si la DB tiene dos socios con nombre idéntico (ej: dos "Carlos Ruiz"), cualquier resolución automática puede afectar al equivocado.

**Mitigación técnica:**
1. La regla de resolución automática requiere **exactamente un candidato** con score ≥ 0.85. Con dos homónimos, el score máximo puede ser 1.0 para ambos, pero como hay múltiples candidatos, siempre se presenta la lista de desambiguación.
2. Los datos del mock server deben incluir al menos un par de homónimos para testear esta ruta.

---

## Riesgos de infraestructura y datos

---

### R-06 — Migración SQLite → Postgres introduce inconsistencias
**Probabilidad:** M | **Impacto:** A

El script de migración puede importar mal los datos históricos: saldos incorrectos, cuotas marcadas como pagadas cuando no lo estaban, etc.

**Mitigación:**
1. El script de migración tiene tests de aserción post-migración: suma de saldos de socios == saldo_en_caja, número de cuotas pendientes == expected, etc.
2. La migración se corre primero en un entorno de staging con una copia de la DB real.
3. El punto de no retorno de la migración está claramente marcado en `docs/10-plan-fases.md`. Antes de ese punto, la DB de Postgres es solo staging y la SQLite sigue siendo la fuente de verdad.
4. Se mantiene un backup de la SQLite original antes de la migración.

---

### R-07 — Pérdida de datos (falla del proveedor de Postgres)
**Probabilidad:** B | **Impacto:** A

**Mitigación:**
1. Usar un proveedor con backups diarios automáticos y retención de al menos 7 días (Neon, Fly Postgres).
2. Complementar con un pg_dump semanal manual guardado localmente.
3. El snapshot SQLite local del escritorio (refreshed cada 30 min) sirve como respaldo parcial de solo lectura.

---

### R-08 — Acceso no autorizado al bot
**Probabilidad:** M | **Impacto:** M

Alguien que conozca el handle del bot de Telegram puede intentar enviarle mensajes.

**Mitigación técnica:**
1. El bot verifica `chat_id` en una lista blanca configurada en variable de entorno. Cualquier mensaje de un `chat_id` no autorizado es descartado silenciosamente (no se responde para no confirmar la existencia del bot).
2. El token del bot de Telegram se configura como variable de entorno en el servidor, nunca en el código.
3. Los endpoints de escritura de la API requieren `Authorization: Bearer <token>`. El token del bot no es accesible desde fuera del servidor del bot.

---

### R-09 — Dependencia de servicios externos (Whisper, OpenAI)
**Probabilidad:** M | **Impacto:** M

OpenAI puede estar caído, tener latencia alta o cambiar su API.

**Mitigación:**
1. El bot implementa timeout de 30 segundos en todas las llamadas externas. Si Whisper o OpenAI no responden, el bot responde "El servicio de transcripción no está disponible ahora. Intenta de nuevo en unos minutos."
2. El flujo de texto (sin audio) no depende de Whisper. El operador puede tipear si el audio falla.
3. El modelo de LLM se configura por variable de entorno (`OPENAI_MODEL=gpt-4o-mini`). Si hay un cambio de nombre de modelo, se actualiza en un minuto sin redesploy.
4. Versión del contrato de OpenAI pinned en `pyproject.toml` (`openai>=1.30,<2.0`).

---

### R-10 — Transcripción incorrecta de nombres propios
**Probabilidad:** A | **Impacto:** B

Whisper puede transcribir "Carmenza" como "Carmensa" o "Hernando" como "Fernando". El fuzzy match en la resolución de entidades mitiga esto, pero no siempre.

**Mitigación:**
1. El umbral de fuzzy match está calibrado para tolerar diferencias de 1-2 caracteres.
2. El bot muestra el nombre completo tal como está en la DB en el resumen de confirmación. El operador detecta la discrepancia visualmente.
3. Si el fuzzy match no encuentra nada con score ≥ 0.70, el bot lo reporta y el operador puede reformular.
4. Riesgo residual bajo: el impacto de identificar al socio incorrecto se mitiga por R-02.

---

### R-11 — El tesorero acepta un resumen sin leerlo
**Probabilidad:** M | **Impacto:** M

El operador puede desarrollar el hábito de responder "sí" sin verificar el resumen (fatiga de confirmación).

**Mitigación:**
1. El resumen está formateado para ser escaneado rápidamente (nombres en negrita, montos con símbolo $).
2. Para montos inusualmente grandes (heurística: > $5.000.000), el bot añade un emoji de advertencia ⚠️.
3. La verificación final es responsabilidad del operador; el sistema no puede sustituirla. Este riesgo residual es aceptado.

---

### R-12 — Meta restringe o bloquea la cuenta de WhatsApp sin verificar
**Probabilidad:** M | **Impacto:** M

Meta puede restringir una cuenta de WhatsApp Business sin verificar en cualquier momento, sin previo aviso, cortando el canal de notificación a socios.

**Mitigación técnica:**
1. Las notificaciones WhatsApp **nunca son bloqueantes**: la operación financiera ya fue persistida antes de intentar el envío. Un bloqueo de Meta no afecta la integridad de los datos.
2. **Fallback `WaMeLinkNotificador`**: si Cloud API falla, el bot envía al operador (Telegram) un enlace `wa.me` con el texto pre-redactado. El operador lo abre y envía manualmente. Funciona sin cuenta de Meta.
3. La interfaz `Notificador` hace que cambiar de implementación (CloudAPI → WaMe → Manual) sea un cambio de configuración, no de código.
4. Riesgo residual aceptado: el fallback manual requiere acción del operador. Esto es conocido y aceptado.

---

## Matriz de resumen

| ID | Riesgo | P | I | Mecanismo técnico principal |
|----|--------|---|---|---------------------------|
| R-01 | Monto transcrito incorrectamente | M | A | Confirmación con formato visual + heurística de monto inusual |
| R-02 | Socio equivocado | M | A | Desambiguación obligatoria + nombre completo en confirmación |
| R-03 | Operación duplicada | B | A | Idempotencia obligatoria en todos los POST |
| R-04 | Alucinación del LLM | B | A | Schemas estrictos + confirmación con datos resueltos |
| R-05 | Homónimos en DB | B | A | Múltiples candidatos → siempre desambiguación |
| R-06 | Migración con inconsistencias | M | A | Tests de aserción post-migración en staging |
| R-07 | Pérdida de datos | B | A | Backups automáticos del proveedor + pg_dump semanal |
| R-08 | Acceso no autorizado | M | M | Whitelist de chat_id + token de bot en vars de entorno |
| R-09 | Caída de OpenAI/Whisper | M | M | Timeout + fallback a texto manual |
| R-10 | Nombre mal transcrito | A | B | Fuzzy match calibrado + nombre real en confirmación |
| R-11 | Confirmación sin leer | M | M | Formato visual + advertencia en montos grandes |
| R-12 | Meta restringe cuenta WhatsApp | M | M | Notificaciones no bloqueantes + fallback wa.me |
