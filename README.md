# ValidadorFacturas

API REST para validación y cancelación de facturas CFDI con el SAT.

---

## Descripcion

Este proyecto contiene una API para validar y cancelar facturas CFDI con el SAT, 
integrada con el servicio de MySuite para la cancelación de comprobantes fiscales.

---

## Caracteristicas API

- Valida el estatus de una factura CFDI ante el SAT
- Valida direcciones de correo electronico
- Parsea archivos XML CFDI (versiones 3.2, 3.3 y 4.0)
- Envia archivos (XML y PDF) por correo electronico
- Cancela facturas CFDI 4.0 via MySuite
- Llena formularios PDF para tramites vehiculares

---

## Requisitos

- Python 3.8+
- FastAPI
- Uvicorn

### Dependencias

```
fastapi
uvicorn[standard]
pydantic
python-dotenv
pycfdi-transform
pdfrw
requests
dns.resolver
aiosmtplib
email
tenacity
```

---

## Instalacion

```bash
git clone https://github.com/sucksens/ValidadoresFacturas.git

cd ValidadoresFacturas/api

cp .env.example .env
```

### Configuracion del archivo .env

```env
# Servidor SMTP para envio de correos
SMTP_HOST=tu-smtp-server.com
SMTP_PORT=587
SMTP_USER=usuario@tu-dominio.com
SMTP_PASSWORD=tu_password
SMTP_USE_TLS=true
SMTP_FROM=noreply@tu-dominio.com

# MySuite para cancelacion de facturas
MYSUITE_URL=https://api.mysuite.com
MYSUITE_TOKEN=tu_token_aqui
```

### Ejecucion

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

La API estara disponible en: http://localhost:8000

Documentacion Swagger: http://localhost:8000/docs

---

## Endpoints

### Validar Factura

Valida el estatus de una factura CFDI ante el SAT.

**URL**: `POST /validar_factura/`

```json
{
  "rfc_emisor": "XAXX010101000",
  "rfc_receptor": "XEXX010101000",
  "total": 1000.00,
  "uuid": "uuid-guia-123"
}
```

---

### Validar Email

Valida si un correo electronico existe mediante verificacion MX y SMTP.

**URL**: `POST /validar_email/`

```json
{
  "email": "correo@ejemplo.com",
  "tipo": false
}
```

---

### Parsear XML

Parsea archivos XML CFDI y extrae los datos.

**URL**: `POST /parsear_xml/`

Parametros: Archivo XML (multipart/form-data)

---

### Enviar Archivos por Correo

Envia archivos XML y PDF por correo electronico.

**URL**: `POST /enviar_archivos_por_correo/`

Parametros (multipart/form-data):
- `xml`: Archivo XML
- `pdf`: Archivo PDF
- `email_destino`: Correo destinatario
- `asunto`: Asunto del correo
- `mensaje_cuerpo`: Cuerpo del mensaje

---

### Cancelar Factura (CFDI 4.0)

Cancela facturas CFDI version 4.0 usando el servicio de MySuite.

**URL**: `POST /cancelar_factura/`

```json
{
  "rfc": "XAXX010101000",
  "tipo": "emitidos",
  "uuids": ["uuid-a-cancelar"],
  "foliosSustitucion": ["uuid-sustituto"],
  "motivo": "01"
}
```

**Codigos de motivo de cancelacion:**
- `01`: Comprobante emitido con errores con relacion (requiere foliosSustitucion)
- `02`: Comprobante emitido con errores sin relacion
- `03`: No se llevo a cabo la operacion
- `04`: Operacion nominativa relacionada en la factura

---

### Llenar Padron

Llena el formulario PDF V1J AUTO con los datos proporcionados.

**URL**: `POST /llenar_padron/`

Parametros: Objeto JSON con los campos del formulario (todos opcionales)

---

## Documentacion

Una vez ejecutando la aplicacion, accede a:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc