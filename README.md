# 🧩 ValidadorFacturas

> Este proyecto contiene todo el código y partes del validador masivo y la API de validación de facturas con el SAT.

[![Windows](https://img.shields.io/badge/Platform-Windows-blue.svg)](https://www.microsoft.com/windows)
[![Linux](https://img.shields.io/badge/Platform-Linux-yellow.svg)]()
[![Release](https://img.shields.io/badge/Release-v1.0-orange.svg)]()

---

## 🎯 Descripción

Este proyecto tiene dos partes principales una que es la API Principal que se estara consumiendo, 
donde se le manda informacion de una factura y se enviara al sat por validacion, 
Y una seccion especifica para generar un trabajo que revise de manera masiva los datos de la base,
todos los dias de los ultimos 3 meses. 


---

## ✨ Características API

- ✅ Valida el Estatus de una Factura.
- ✅ Valida direcciones de correo electrónico.
- ✅ Parsea archivos XML CFDI.
- ✅ Envía archivos (XML y PDF) por correo electrónico.

## ✨ Características Validador

- ✅ Buscar Información del mes dado 
- ✅ Validar Estatus 
- ✅ Actulizar estatus en la Base  
- 🚀 Próximamente:
- Generar un wrap del vallidador para automatizar

---

## 🛠 Instalación

> Requisitos previos: `requirements.txt`

### Opción 1 – Desde fuente
```bash
git clone http://200.1.1.247:3002/senjuana/ValidadorFacturas.git

cd ValidadorFacturas

```

### 2. Ejecución

1. Por definir

## 📧 Endpoint de Envío de Archivos por Correo

El endpoint `/enviar_archivos_por_correo/` permite enviar archivos XML y PDF a un correo electrónico.

### Configuración

Antes de usar el endpoint, crea un archivo `.env` en la carpeta `api/` con las siguientes variables:

```env
SMTP_HOST=tu-smtp-server.com
SMTP_PORT=587
SMTP_USER=usuario@tu-dominio.com
SMTP_PASSWORD=tu_contraseña
SMTP_USE_TLS=true
SMTP_FROM=noreply@dominio.com
```

### Uso del Endpoint

**URL**: `POST /enviar_archivos_por_correo/`

**Parámetros (multipart/form-data)**:
- `xml`: Archivo XML a adjuntar
- `pdf`: Archivo PDF a adjuntar
- `email_destino`: Correo electrónico destinatario
- `asunto`: Asunto del correo
- `mensaje_cuerpo`: Cuerpo del mensaje (opcional, por defecto "Archivos adjuntos")

### Ejemplo de Request (cURL)

```bash
curl -X POST "http://localhost:8000/enviar_archivos_por_correo/" \
  -F "xml=@factura.xml" \
  -F "pdf=@factura.pdf" \
  -F "email_destino=cliente@ejemplo.com" \
  -F "asunto=Factura adjunta" \
  -F "mensaje_cuerpo=Adjunto encontrará la factura en formato XML y PDF"
```

### Respuesta

```json
{
  "exito": true,
  "mensaje": "Correo enviado exitosamente a cliente@ejemplo.com",
  "error": null,
  "id_operacion": "123e4567-e89b-12d3-a456-426614174000"
}
```


