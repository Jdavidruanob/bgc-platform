# 12 — Entornos: producción y pruebas

Cómo saber, en cualquier momento y desde cualquiera de las tres piezas del
sistema, si se está trabajando contra la base **real** o contra la de
**pruebas** — y qué hay que configurar para que ese aviso funcione.

---

## 1. El problema que resuelve

Hasta ahora existía una sola base de datos: la de producción, en Railway. Toda
prueba de la app o del bot se hacía sobre datos reales — saldos de socios,
cuotas de créditos, saldo en caja.

Ahora hay dos bases, **idénticas en estructura y datos**, que se distinguen
solo por el puerto:

| Entorno | Host | Puerto |
|---|---|---|
| Producción | `sakura.proxy.rlwy.net` | **42792** |
| Pruebas | `sakura.proxy.rlwy.net` | **54722** |

Que se distingan solo por el puerto es justamente el peligro: las dos URLs se
ven casi iguales, y equivocarse no da ningún error — simplemente se escribe en
la base que no era. Por eso el entorno se declara de forma explícita y se
muestra en pantalla de forma permanente.

**La regla:** el error caro es creer que se está en pruebas cuando en realidad
se está moviendo plata real. Por eso, ante la duda, **todo el sistema asume
producción**. Un aviso de pruebas que no aparece cuando debería es un
inconveniente; un aviso de pruebas que aparece cuando en realidad es producción
es un desastre.

---

## 2. `APP_ENV`: la variable

Una sola variable gobierna las tres piezas:

```
APP_ENV=produccion     # base real
APP_ENV=pruebas        # base de copia
```

Se aceptan sinónimos, sin distinguir mayúsculas ni tildes: `prod`,
`production`, `live`, `real` para producción; `dev`, `desarrollo`, `test`,
`testing`, `staging`, `local` para pruebas.

### Cómo se decide el entorno

En orden. El primero que responda, manda:

1. **`APP_ENV`**, si está definida. Es la fuente de verdad.
2. **El puerto de `DATABASE_URL`**, comparado contra la tabla de arriba.
   Solo aplica a la app y a la API — el bot no tiene `DATABASE_URL`.
3. **Producción**, si no se reconoció nada.

El paso 2 existe como red de seguridad, no como método principal: funciona hoy
porque los puertos son los que son, pero si Railway reasigna un puerto o se
crea una tercera base, deja de funcionar sin avisar. **Definir `APP_ENV`
siempre.**

---

## 3. Qué hace cada pieza

### 3.1 App de escritorio (repo `BGC-software`)

Lee `APP_ENV` del archivo `.env` que está junto al ejecutable.

En **producción** la app se ve exactamente como siempre. En **pruebas**:

- Aparece una **franja ámbar permanente** bajo la barra superior:
  `🧪 MODO PRUEBAS — los cambios NO afectan la base real · host:puerto/base`.
  No tiene botón de cerrar, a propósito.
- El **título de la ventana** pasa a `bgc software vX.Y.Z — 🧪 PRUEBAS`, para
  poder distinguirlas en la barra de tareas si se abren las dos a la vez.
- Al arrancar, la consola imprime `🌐 Entorno: PRUEBAS · host:puerto/base`.

Cambiar de entorno es editar dos líneas del `.env`:

```ini
APP_ENV=pruebas
# DATABASE_URL=postgresql://postgres:<pass>@sakura.proxy.rlwy.net:42792/railway   <- producción
DATABASE_URL=postgresql://postgres:<pass>@sakura.proxy.rlwy.net:54722/railway     <- pruebas
```

> **Importante:** hay que cambiar **las dos**. Si `APP_ENV=pruebas` pero la
> `DATABASE_URL` sigue apuntando a producción, la app mostrará la franja de
> pruebas mientras escribe en la base real. `APP_ENV` manda sobre la detección
> por puerto justamente para permitir casos raros, y esa flexibilidad es
> también la forma de pegarse un tiro en el pie.

Módulo: `entorno.py` en la raíz del repo. No importa Qt, así que también sirve
para scripts de mantenimiento.

### 3.2 API (repo `bgc-platform`, `packages/api`)

Es la pieza que realmente escribe en la base, así que aquí el entorno es lo más
importante de todo.

- Expone el entorno en `GET /health`:
  ```json
  { "status": "ok", "version": "0.1.0", "entorno": "produccion" }
  ```
  Sirve para confirmar desde fuera contra qué base está escribiendo una
  instancia **antes** de operar con ella.
- Al arrancar escribe en el log, con nivel `WARNING` para que no se pierda:
  ```
  coop-api arrancando · entorno=produccion · base=sakura.proxy.rlwy.net:42792/railway
  ```

El campo `entorno` de `/health` tiene valor por defecto `produccion`, así que
un cliente viejo que no lo conozca sigue funcionando igual.

Módulo: `packages/api/src/coop_api/entorno.py`.

**La contraseña nunca aparece.** Ni en `/health`, ni en los logs: solo se
publica `host:puerto/base`.

### 3.3 Bot (repo `bgc-platform`, `packages/bot`)

**El bot no habla con la base de datos.** Habla con la API por HTTP, y es la
API la que decide dónde escribe. Por eso, para el bot, "entorno" significa
*contra qué API estoy hablando*.

Esto tiene una consecuencia práctica importante: **el bot no tiene
`DATABASE_URL`**, así que el paso 2 de la detección no aplica. Sin `APP_ENV`,
el bot siempre se creerá en producción.

En pruebas, el bot antepone a **cada** respuesta:

```
🧪 MODO PRUEBAS — esto no afecta la base real

<el mensaje de siempre>
```

Está puesto en `enviar_texto` y en el `caption` de `enviar_pdf`, que son el
único embudo por donde salen los mensajes del bot. Ningún mensaje puede
escaparse sin el aviso.

Al arrancar registra `Entorno: PRODUCCIÓN · API: https://...`.

Módulo: `packages/bot/src/coop_bot/entorno.py`.

---

## 4. Lo que falta configurar — y por qué importa

Este es el aviso concreto. **La app ya está lista**, porque su `.env` es un
archivo local que ya quedó escrito. Pero la API y el bot **no corren en el
computador de nadie**: corren en Railway y en Fly.io, donde no existe ningún
`.env`. Allá las variables se definen en el panel del servicio, y **`APP_ENV`
todavía no está definida en ninguno de los dos.**

Estado actual, sin haber tocado nada en los paneles:

| Pieza | Dónde corre | ¿Detecta bien el entorno hoy? |
|---|---|---|
| App de escritorio | Computador del operador | ✅ Sí, por `APP_ENV` del `.env` |
| API | Railway | ⚠️ Sí, pero **por el puerto**, no porque se lo hayan dicho |
| Bot | Fly.io | ❌ No. Siempre dirá producción |

Nada está roto hoy. Pero:

- **La API acierta por casualidad.** Funciona porque su `DATABASE_URL` apunta
  al puerto 42792, que está en la tabla de bases conocidas. Es el mecanismo de
  respaldo haciendo el trabajo del principal. El día que se levante una segunda
  instancia de la API contra la base de pruebas, seguirá acertando *solo* si esa
  instancia usa el puerto 54722 exacto.
- **El bot no tiene forma de saberlo.** Este es el hueco real. Si mañana se
  levanta un bot de pruebas apuntando a una API de pruebas, ese bot
  **respondería sin la franja `🧪 MODO PRUEBAS`**, indistinguible del bot real.
  Es exactamente el escenario que todo este trabajo pretende evitar.

En otras palabras: la protección del bot está escrita pero **inactiva** hasta
que se defina la variable.

### 4.1 Qué hay que hacer

**API en Railway** — en el servicio de la API, pestaña *Variables*:

```
APP_ENV=produccion
```

**Bot en Fly.io** — desde la carpeta del repo:

```bash
fly secrets set APP_ENV=produccion --app coop-bot
```

O, como no es un dato sensible, se puede dejar versionado en `fly.toml`:

```toml
[env]
  PORT = "8080"
  APP_ENV = "produccion"
```

> `fly.toml` en la raíz corresponde a `coop-api-staging`. Si ese despliegue
> apunta a la base de pruebas, su `APP_ENV` debería ser `pruebas`, no
> `produccion`.

**Al crear un despliegue de pruebas**, la variable va en `pruebas` *y* la
`DATABASE_URL` de la API va al puerto 54722. Las dos cosas, siempre.

### 4.2 Cómo comprobar que quedó bien

```bash
curl https://<url-de-la-api>/health
```

Debe responder con el campo `entorno` correcto:

```json
{ "status": "ok", "version": "0.1.0", "entorno": "produccion" }
```

Para el bot, basta escribirle por Telegram: si es de pruebas, toda respuesta
debe empezar con `🧪 MODO PRUEBAS`. Si no aparece, la variable no quedó.

---

## 5. Resumen operativo

| Quiero… | Hago… |
|---|---|
| Probar en la app sin tocar datos reales | `APP_ENV=pruebas` + `DATABASE_URL` al 54722 en el `.env` |
| Volver la app a producción | `APP_ENV=produccion` + `DATABASE_URL` al 42792 |
| Saber contra qué base está una API | `GET /health` → campo `entorno` |
| Saber si un bot es de pruebas | Escribirle: debe anteponer `🧪 MODO PRUEBAS` |
| Levantar un entorno de pruebas completo | `APP_ENV=pruebas` en API **y** bot, y la `DATABASE_URL` de la API al 54722 |

**Nunca** dejar `APP_ENV` sin definir en un despliegue de pruebas: se
presentaría como producción.
