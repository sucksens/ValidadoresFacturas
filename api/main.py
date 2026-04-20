# IMPORTS
# Imports de construccion de la API
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, EmailStr
from typing import Annotated, Optional
import uuid as uuid_lib

# Imports de reintentos y manejo multihilo para no lockear las llamadas
import asyncio
import traceback
from tenacity import retry, stop_after_attempt, wait_fixed

# Import de la clase local de validacion
from ValidacionClass import Validacion

# import del endpoint de email
import dns.resolver
import aiosmtplib

# Import de pycfdi-transform para parsear XML
from pycfdi_transform import CFDI32SAXHandler, CFDI33SAXHandler, CFDI40SAXHandler
from fastapi import File, UploadFile, Form

# Import para envio de email
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from dotenv import load_dotenv

# Import para manipular PDFs
import PyPDF2
import pdfrw

# Import para cancelar facturas via MySuite
import requests

# Cargar variables de entorno
load_dotenv()


# --- Inicialización de la Aplicación FastAPI ---
app = FastAPI(
    title="API de Validaciónes Interna",
    description="Una API RESTful para hacer diferentes validaciones, desde cfdis hasta validaciones de correo. ",
    version="1.0.1",
)


"""
    -----------------------------------------------------------------------------------------------------
    Modelos de Solicitud: 
    -----------------------------------------------------------------------------------------------------
"""


class DocumentRequest(BaseModel):
    """
    Define la estructura de datos para la solicitud POST al endpoint de validación.
    Utiliza Pydantic para la validación automática de los campos.
    """

    rfc_emisor: Annotated[str, Field(min_length=12, max_length=13)]
    rfc_receptor: Annotated[str, Field(min_length=12, max_length=13)]
    total: Annotated[float, Field(gt=-1)]
    uuid: Annotated[uuid_lib.UUID, Field()]


class EmailRequest(BaseModel):
    """
    Modelos del Request del endpoint de validacion de correo
    """

    email: Annotated[EmailStr, Field(min_length=5)]
    tipo: bool


class PdfFormRequest(BaseModel):
    """
    Modelo de solicitud para llenar el formulario PDF V1J AUTO.
    Todos los campos son opcionales para permitir llenar solo algunos campos.
    """

    # Campos de texto
    entidad: Optional[str] = None
    ext: Optional[str] = None
    int_: Optional[str] = Field(default=None, alias="int")
    col: Optional[str] = None
    postal: Optional[str] = None
    correo_1: Optional[str] = Field(default=None, alias="correo_1")
    denominacion_razon_social_1: Optional[str] = Field(
        default=None, alias="denominacion_razon_social_1"
    )
    denominacion_razon_social_2: Optional[str] = Field(
        default=None, alias="denominacion_razon_social_2"
    )
    regimen_sociedad: Optional[str] = Field(default=None, alias="regimen_sociedad")
    entre: Optional[str] = None
    y_de: Optional[str] = Field(default=None, alias="y_de")
    calle: Optional[str] = None
    tipo_vialidad: Optional[str] = Field(default=None, alias="tipo_vialidad")
    mpo: Optional[str] = None
    marca: Optional[str] = None
    tipo: Optional[str] = None
    rfc: Optional[str] = Field(default=None, alias="rfc")
    curp: Optional[str] = None
    apellido_paterno: Optional[str] = Field(default=None, alias="apellido_paterno")
    apellido_materno: Optional[str] = Field(default=None, alias="apellido_materno")
    nombre: Optional[str] = None
    num_escritura: Optional[str] = Field(default=None, alias="num_escritura")
    foja: Optional[str] = None
    modelo: Optional[str] = None
    no_motor: Optional[str] = Field(default=None, alias="no_motor")
    serie: Optional[str] = None
    color: Optional[str] = None
    folio_fiscal: Optional[str] = Field(default=None, alias="folio_fiscal")
    telefono: Optional[str] = None
    mes_2: Optional[str] = Field(default=None, alias="mes_2")
    anio: Optional[str] = Field(default=None, alias="anio")
    ndp: Optional[str] = None
    registro_estatal: Optional[str] = Field(default=None, alias="registro_estatal")
    mes_final: Optional[str] = Field(default=None, alias="mes_final")
    fecha_final: Optional[str] = Field(default=None, alias="fecha_final")
    anio_2: Optional[str] = Field(default=None, alias="anio_2")
    libro: Optional[str] = None
    localidad: Optional[str] = None
    dia_2: Optional[str] = Field(default=None, alias="dia_2")
    anio_3: Optional[str] = Field(default=None, alias="anio_3")
    dia: Optional[str] = None
    tipo_sol: Optional[str] = Field(default=None, alias="tipo_sol")
    mes: Optional[str] = None
    lugar_fecha: Optional[str] = Field(default=None, alias="lugar_fecha")
    placa_ant: Optional[str] = Field(default=None, alias="placa_ant")
    calle_posterior: Optional[str] = Field(default=None, alias="calle_posterior")
    no_placa: Optional[str] = Field(default=None, alias="no_placa")
    entidad_federativa: Optional[str] = Field(default=None, alias="entidad_federativa")
    no: Optional[str] = None
    n_orf: Optional[str] = Field(default=None, alias="n_orf")
    facturacion: Optional[str] = None
    pedimento: Optional[str] = None

    # Campos de checkbox (boolean)
    trasera: Optional[bool] = None
    cp: Optional[bool] = Field(default=None, alias="cp")
    pn: Optional[bool] = Field(default=None, alias="pn")
    delamtera: Optional[bool] = None
    ninguna: Optional[bool] = None
    unica_motocicleta: Optional[bool] = Field(default=None, alias="unica_motocicleta")
    servicios_pub: Optional[bool] = Field(default=None, alias="servicios_pub")
    servicios_pri: Optional[bool] = Field(default=None, alias="servicios_pri")
    camioneta: Optional[bool] = None
    camion: Optional[bool] = None
    minibus: Optional[bool] = None
    remolque: Optional[bool] = None
    motocicleta: Optional[bool] = None
    cuatrimoto: Optional[bool] = None
    taxi: Optional[bool] = None
    gasolina: Optional[bool] = None
    electrico_hibrido: Optional[bool] = Field(default=None, alias="electrico_hibrido")
    hibrido: Optional[bool] = None
    diesel: Optional[bool] = None
    gas: Optional[bool] = None
    gas_lp: Optional[bool] = Field(default=None, alias="gas_lp")
    no_usa: Optional[bool] = Field(default=None, alias="no_usa")
    otros: Optional[bool] = None
    dictamen: Optional[bool] = None
    ambas: Optional[bool] = None
    concesion: Optional[bool] = None
    denuncia: Optional[bool] = None


class XmlResponse(BaseModel):
    """
    Modelo de respuesta para el endpoint de parseo XML
    """

    exito: bool = Field(description="Indica si el XML fue parseado exitosamente")
    version: Optional[str] = Field(
        description="Versión del CFDI detectada", default=None
    )
    datos: Optional[dict] = Field(
        description="Estructura de datos del XML parseado", default=None
    )
    error: Optional[str] = Field(
        description="Mensaje de error si el XML no pudo ser parseado", default=None
    )


class CancelacionRequest(BaseModel):
    """
    Modelo de solicitud para cancelar facturas CFDI 4.0 via MySuite
    """

    rfc: Annotated[
        str, Field(min_length=12, max_length=13, description="RFC del emisor")
    ]
    tipo: Annotated[str, Field(description="Tipo de CFDI: 'emitidos' o 'recibidos'")]
    uuids: Annotated[
        list[str], Field(min_length=1, description="Lista de UUIDs a cancelar")
    ]
    foliosSustitucion: Optional[list[str]] = Field(
        default=None, description="UUIDs de los CFDI que sustituyen al cancelado"
    )
    motivo: Annotated[
        str, Field(description="Código de motivo de cancelación (01, 02, 03, 04)")
    ]


class CancelacionResponse(BaseModel):
    """
    Modelo de respuesta para el endpoint de cancelación de facturas
    """

    exito: bool = Field(
        description="Indica si la cancelación fue procesada exitosamente"
    )
    mensaje: str = Field(description="Mensaje descriptivo del resultado")
    resultado: Optional[dict] = Field(
        default=None,
        description="Respuesta de MySuite con el detalle de la cancelación",
    )
    id_operacion: uuid_lib.UUID = Field(
        description="ID único generado para esta operación"
    )
    error: Optional[str] = Field(
        default=None, description="Mensaje de error sifalló la cancelación"
    )


# Configuración de seguridad para parseo XML
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_MIME_TYPES = ["text/xml", "application/xml"]

# Configuración segura del parser XML (protección XXE)
import lxml.etree as etree

XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    huge_tree=False,
)


"""
    -----------------------------------------------------------------------------------------------------
    Modelos de Respuesta: 
    -----------------------------------------------------------------------------------------------------
"""


class DocumentResponse(BaseModel):
    """
    Define la estructura de datos para la respuesta del endpoint de validación.
    Proporciona información clara sobre el resultado de la operación.
    """

    mensaje: str = Field(
        description="Un mensaje descriptivo sobre el resultado de la operación."
    )
    datos_recibidos: dict = Field(
        description="Los datos exactos que fueron recibidos en la solicitud para su validación."
    )
    estado_validacion: str = Field(
        description="El estado de validación del documento CFDI. "
        "Valores posibles pueden incluir 'VIGENTE', 'CANCELADO', 'ERROR', etc., "
        "dependiendo de la respuesta del servicio de validación."
    )
    codigo_estatus: str = Field(
        description="El código de estatus de la respuesta del SAT."
    )
    es_cancelable: str = Field(description="Indica si el comprobante es cancelable.")
    estatus_cancelacion: Optional[str] = Field(
        default=None, description="El estatus de cancelación del comprobante."
    )
    validacion_efos: Optional[str] = Field(
        default=None, description="El resultado de la validación EFOS."
    )
    id_operacion: uuid_lib.UUID = Field(
        description="Un ID único generado para esta operación de validación específica, "
        "útil para el seguimiento de solicitudes."
    )
    procesamiento_exitoso: bool = Field(
        description="Indica si la operación de procesamiento y validación se completó sin errores."
    )


class EmailValidationResponse(BaseModel):
    """
    Define la estructura de datos de la respues del endpoint de validacion del correo.
    Proporciona informacion clara sobre los resultados de la operacion.
    """

    email: str = Field(description="El correo que se envio a validar")
    domain_has_mx: bool = Field(
        description="Un booleano que te dice si el dominio existe y si tiene correo"
    )
    domain_mx_records: Optional[list[str]] = None
    smtp_check_possible: bool = False
    smtp_check_result: Optional[str] = (
        None  # "accepted", "rejected", "timeout", "error"
    )
    exists: Optional[bool] = None  # Solo si el smtp check es positivo
    error: Optional[str] = None


class EmailSendResponse(BaseModel):
    """
    Define la estructura de datos para la respuesta del endpoint de envio de archivos por correo.
    """

    exito: bool = Field(description="Indica si el correo fue enviado exitosamente")
    mensaje: str = Field(
        description="Mensaje descriptivo sobre el resultado de la operacion"
    )
    error: Optional[str] = Field(
        default=None, description="Mensaje de error si el correo no pudo ser enviado"
    )
    id_operacion: uuid_lib.UUID = Field(
        description="Un ID unico generado para esta operacion de envio"
    )


# Reintento automático: hasta 3 intentos con 2 segundos entre cada uno
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def obtener_estado_con_reintento(validacion, documento):
    """
    Funcion de validacion con reintento, recibe el aobjeto de Validacion, y documento de request ya validado con el DocumentRequest
    """
    return validacion.obtener_estado(
        rfc_emisor=documento.rfc_emisor,
        rfc_receptor=documento.rfc_receptor,
        total=str(documento.total),
        uuid=str(documento.uuid),
    )


def llenar_formulario_pdf(pdf_template_path: str, datos_formulario: dict) -> bytes:
    """
    Llena los campos de un formulario PDF con los datos proporcionados.

    Args:
        pdf_template_path: Ruta al PDF template
        datos_formulario: Diccionario con los datos del formulario

    Returns:
        bytes: Contenido del PDF generado con los campos llenos
    """
    try:
        # Leer el PDF template usando pdfrw
        template_pdf = pdfrw.PdfReader(pdf_template_path)

        # Crear un diccionario de mapeo entre campos del request y campos del PDF
        mapeo_campos = {
            "entidad": "ENTIDAD",
            "ext": "EXT",
            "int_": "INT",
            "col": "COL",
            "postal": "POSTAL",
            "correo_1": "CORREO 1",
            "denominacion_razon_social_1": "DENOMINACIÓN O RAZON SOCIAL_1",
            "denominacion_razon_social_2": "DENOMINACIÓN O RAZON SOCIAL_2",
            "regimen_sociedad": "RÉGIMEN DE SOCIEDAD",
            "entre": "ENTRE",
            "y_de": "Y DE",
            "calle": "CALLE",
            "tipo_vialidad": "TIPO DE VIALIDAD",
            "mpo": "MPO",
            "marca": "MARCA",
            "tipo": "TIPO",
            "rfc": "Registro Federal Contribuyente",
            "curp": "CURP",
            "apellido_paterno": "APELLIDO PATERNO",
            "apellido_materno": "APELLIDO MATERNO",
            "nombre": "NOMBRE",
            "num_escritura": "Núm Escritura",
            "foja": "FOJA",
            "modelo": "MODELO",
            "no_motor": "NO MOTOR",
            "serie": "SERIE",
            "color": "COLOR",
            "folio_fiscal": "FOLIO FISCAL",
            "telefono": "TELEFONO",
            "mes_2": "Mes_2",
            "anio": "Año",
            "ndp": "NDP",
            "registro_estatal": "Registro Estatal",
            "mes_final": "MES FINAL",
            "fecha_final": "FECHA FINAL",
            "anio_2": "AÑO",
            "libro": "LIBRO",
            "localidad": "LOCALIDAD",
            "dia_2": "Día_2",
            "anio_3": "Año_2",
            "dia": "Día",
            "tipo_sol": "TipoSol",
            "mes": "Mes",
            "lugar_fecha": "Lugar y fecha",
            "placa_ant": "PLACA ANT",
            "calle_posterior": "CALLER POSTERIOR",
            "no_placa": "No Placa",
            "entidad_federativa": "ENTIDAD FEDERATIVA",
            "no": "NO",
            "n_orf": "N ORF",
            "facturacion": "FACTURACIÓN",
            "trasera": "TRASERA",
            "cp": "CP",
            "pn": "PN",
            "delamtera": "DELAMTERA",
            "ninguna": "NINGUNA",
            "unica_motocicleta": "UNICA PARA MOTOCICLETA",
            "servicios_pub": "SERVICIOS PUB",
            "servicios_pri": "SERVICIOS PRI",
            "camioneta": "CAMIONETA",
            "camion": "CAMIÓN",
            "minibus": "MINIBÚS",
            "remolque": "REMOLQUE",
            "motocicleta": "MOTOCICLETA",
            "cuatrimoto": "CUATROMOTO",
            "taxi": "TAXI",
            "gasolina": "GASOLINA",
            "electrico_hibrido": "ELÉCTRICO O HIBRIDO",
            "hibrido": "HIBRIDO",
            "diesel": "DIÉSEL",
            "gas": "GAS",
            "gas_lp": "GAS LP",
            "no_usa": "NO USA",
            "otros": "OTROS",
            "dictamen": "DICTAMNE",
            "ambas": "AMBAS",
            "concesion": "CONCESIÓN",
            "denuncia": "DENUNCIA",
            "pedimento": "PEDIMENTO",
        }

        # Llenar los campos del formulario
        if "/AcroForm" in template_pdf.Root:
            acroform = template_pdf.Root["/AcroForm"]

            # Forzar al visor de PDF a regenerar las apariencias visuales
            # de los campos del formulario (sin esto, se muestran los datos viejos)
            acroform.update(pdfrw.PdfDict(NeedAppearances=pdfrw.PdfObject("true")))

            if "/Fields" in acroform:
                fields = acroform["/Fields"]

                # Crear un mapeo inverso: nombre_campo_pdf -> valor
                mapeo_inverso = {}
                for campo_request, valor in datos_formulario.items():
                    campo_pdf = mapeo_campos.get(campo_request)
                    if campo_pdf:
                        mapeo_inverso[campo_pdf] = valor

                def procesar_campo(field):
                    """Procesa un campo del PDF: lo llena o lo limpia.
                    Si tiene campos hijos (Kids), los procesa recursivamente."""
                    field_name = field.T
                    if isinstance(field_name, bytes):
                        field_name = field_name.decode("utf-8", errors="ignore")

                    # Limpiar el nombre del campo: quitar paréntesis y espacios
                    field_name_clean = (
                        field_name.strip("() ").strip() if field_name else None
                    )

                    field_type = field.FT

                    # Eliminar la apariencia visual cacheada
                    if "/AP" in field:
                        del field["/AP"]

                    # Procesar este campo si tiene tipo definido
                    if field_type and field_name_clean:
                        if field_name_clean in mapeo_inverso:
                            valor = mapeo_inverso[field_name_clean]
                            if field_type == "/Tx":
                                if valor is not None:
                                    field.V = pdfrw.objects.pdfstring.PdfString.encode(
                                        str(valor)
                                    )
                                else:
                                    field.V = pdfrw.objects.pdfstring.PdfString.encode(
                                        ""
                                    )
                            elif field_type == "/Btn":
                                if valor:
                                    field.V = pdfrw.PdfName("Yes")
                                    field.AS = pdfrw.PdfName("Yes")
                                else:
                                    field.V = pdfrw.PdfName("Off")
                                    field.AS = pdfrw.PdfName("Off")
                        else:
                            # Campo no mapeado: limpiar
                            if field_type == "/Tx":
                                field.V = pdfrw.objects.pdfstring.PdfString.encode("")
                            elif field_type == "/Btn":
                                field.V = pdfrw.PdfName("Off")
                                field.AS = pdfrw.PdfName("Off")

                    # Procesar campos hijos recursivamente
                    if field.Kids:
                        for kid in field.Kids:
                            procesar_campo(kid)

                # Recorrer TODOS los campos del PDF recursivamente
                for field in fields:
                    procesar_campo(field)

        # Generar el PDF en memoria
        from io import BytesIO

        output_stream = BytesIO()
        pdfrw.PdfWriter().write(output_stream, template_pdf)
        output_stream.seek(0)

        return output_stream.read()

    except Exception as e:
        import traceback

        traceback_str = "".join(traceback.format_exception(None, e, e.__traceback__))
        print(f"Error al llenar formulario PDF: {traceback_str}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al generar el PDF: {str(e)}",
        )


"""
    -----------------------------------------------------------------------------------------------------
    Endpoints: 
    -----------------------------------------------------------------------------------------------------
"""


@app.post("/validar_factura/", response_model=DocumentResponse)
async def validar_factura(documento: DocumentRequest):
    """
    Endpoint POST que recibe los datos de un documento CFDI para su validación.
    Utiliza la clase local Validacion para obtener el estado del documento y
    devuelve una respuesta estructurada con la información de la validación.

    **Parámetros de la Solicitud (en el cuerpo JSON):**
    - `rfc_emisor`: RFC del emisor (string, 12 o 13 caracteres)
    - `rfc_receptor`: RFC del receptor (string, 12 o 13 caracteres)
    - `total`: Monto total del documento (número flotante, mayor que 0)
    - `uuid`: UUID del documento (string en formato UUID)

    **Respuestas HTTP:**
    - `200 OK`: Retorna un `DocumentResponse` si la validación se procesa correctamente.
    - `422 Unprocessable Entity`: Si los datos de entrada no cumplen con las validaciones de Pydantic (ej. formato de RFC, tipo de total, formato de UUID).
    - `500 Internal Server Error`: Si ocurre un error inesperado durante la ejecución de la lógica de validación.
    """
    try:
        # Instancia la clase de validación local.
        # Esta instancia es la que interactúa con el servicio de validación real.
        validacion = Validacion(timeout=40)
        # Llama al método 'obtener_estado_con_reintento' con el objeto de validacion  en un su propio hilo para que no se bloqueé
        estado_resultado = await asyncio.to_thread(
            obtener_estado_con_reintento, validacion, documento
        )

        # Extrae el estado de validación del diccionario de respuesta.
        # Si 'estado' no está presente, se asigna 'DESCONOCIDO' como valor por defecto.
        estado_cfdi = estado_resultado.get("estado", "DESCONOCIDO")
        codigo_estatus = estado_resultado.get("codigo_estatus", "DESCONOCIDO")
        es_cancelable = estado_resultado.get("es_cancelable", "DESCONOCIDO")
        estatus_cancelacion = estado_resultado.get("estatus_cancelacion")
        validacion_efos = estado_resultado.get("validacion_efos")

        # Convierte el objeto de solicitud Pydantic a un diccionario para incluirlo en la respuesta.
        datos_recibidos_dict = documento.model_dump()

        # Genera un nuevo UUID para esta operación de API, útil para rastrear cada solicitud.
        id_operacion = uuid_lib.uuid4()

        # Retorna la respuesta exitosa con los datos de validación.
        return DocumentResponse(
            mensaje="Factura procesada y validada exitosamente.",
            datos_recibidos=datos_recibidos_dict,
            estado_validacion=estado_cfdi,
            codigo_estatus=codigo_estatus,
            es_cancelable=es_cancelable,
            estatus_cancelacion=estatus_cancelacion,
            validacion_efos=validacion_efos,
            procesamiento_exitoso=True,
            id_operacion=id_operacion,
        )
    except Exception as e:
        # Manejo de excepciones: Si ocurre cualquier error inesperado durante el proceso
        # de validación, se captura y se retorna un error 500 al cliente.
        # El detalle incluye el mensaje de la excepción para facilitar la depuración.
        traceback_str = "".join(traceback.format_exception(None, e, e.__traceback__))
        print(f"ERROR durante validación: {traceback_str}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor al validar la factura: {str(e)}",
        )


@app.post("/validar_email/", response_model=EmailValidationResponse)
async def validar_email(request: EmailRequest):
    email = request.email
    tipo = request.tipo
    domain = email.split("@")[1]

    response = EmailValidationResponse(
        email=email,
        domain_has_mx=False,
        domain_mx_records=[],
        smtp_check_possible=False,
        smtp_check_result=None,
        exists=None,
        error=None,
    )

    # 1. Verificar registros MX del dominio
    try:
        mx_records = dns.resolver.resolve(domain, "MX")
        mx_list = [str(mx.exchange).rstrip(".") for mx in mx_records]
        response.domain_has_mx = True
        response.domain_mx_records = mx_list
    except Exception as e:
        response.error = f"Error resolving MX records: {str(e)}"
        return response

    if tipo:
        return response
    # 2. Opcional: Intentar verificar existencia real del correo vía SMTP (con advertencias)
    # ⚠️ Esto NO es 100% confiable. Muchos servidores rechazan o ignoran estos checks por anti-spam.
    try:
        # Tomar el primer servidor MX
        mx_host = response.domain_mx_records[0]
        # Conectar al servidor SMTP del dominio
        server = aiosmtplib.SMTP(timeout=10)
        await server.connect(hostname=mx_host, port=25)  # Puerto 25 estándar para SMTP

        # Enviar comandos SMTP básicos
        await server.helo()  # o ehlo
        await server.mail("validator@motormexa.mx")  # Remitente ficticio
        code, message = await server.rcpt(email)  # Intentar destinatario

        await server.quit()

        # Interpretar respuesta
        if code == 250:
            response.smtp_check_possible = True
            response.smtp_check_result = "accepted"
            response.exists = True
        elif code in (550, 553):
            response.smtp_check_possible = True
            response.smtp_check_result = "rejected"
            response.exists = False
        else:
            response.smtp_check_possible = True
            response.smtp_check_result = f"unknown_code_{code}"
            response.exists = None  # Incierto

    except asyncio.TimeoutError:
        response.smtp_check_result = "timeout"
    except Exception as smtp_error:
        response.smtp_check_result = "error"
        response.error = f"SMTP check failed: {str(smtp_error)}"

    return response


def validar_xml_seguro(xml_content: bytes) -> bool:
    """
    Valida que el contenido sea XML válido y no contenga estructuras maliciosas.
    Retorna True si es válido, False si hay problemas.
    """
    try:
        root = etree.fromstring(xml_content, parser=XML_PARSER)
        return True
    except etree.XMLSyntaxError:
        return False
    except etree.XMLParserError:
        return False
    except Exception:
        return False


def detectar_version_cfdi(xml_content: str) -> Optional[str]:
    """
    Detecta la versión del CFDI desde el contenido XML
    """
    import re

    # Buscar versión en el atributo Version del nodo principal
    version_match = re.search(r'version="([3-4]\.[0-9])"', xml_content.lower())
    if version_match:
        return version_match.group(1)

    # Buscar versión en el atributo Version del nodo Comprobante
    comprobante_match = re.search(
        r'cfdi:comprobante[^>]*version="([3-4]\.[0-9])"', xml_content.lower()
    )
    if comprobante_match:
        return comprobante_match.group(1)

    # Buscar versión en el namespace
    namespace_match = re.search(
        r"http://www\.sat\.gob\.mx/cfd/([3-4])", xml_content.lower()
    )
    if namespace_match:
        return (
            f"{namespace_match.group(1)}.0"
            if namespace_match.group(1) == "3"
            else "4.0"
        )

    return None


async def enviar_email_con_adjuntos(
    email_destino: str,
    asunto: str,
    mensaje_cuerpo: str,
    xml_bytes: bytes,
    xml_filename: str,
    pdf_bytes: bytes,
    pdf_filename: str,
):
    """
    Envía un correo electrónico con archivos adjuntos usando SMTP configurado.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = 587
    smtp_port_env = os.getenv("SMTP_PORT")
    if smtp_port_env:
        smtp_port = int(smtp_port_env)
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    smtp_from_env = os.getenv("SMTP_FROM")
    smtp_from = smtp_from_env if smtp_from_env else smtp_user

    if not smtp_host or not smtp_user or not smtp_password or not smtp_from:
        raise ValueError(
            "Faltan configuraciones SMTP. Verifica las variables de entorno."
        )

    # Crear el mensaje
    msg = MIMEMultipart()
    msg["From"] = smtp_from
    msg["To"] = email_destino
    msg["Subject"] = asunto

    # Agregar cuerpo del mensaje
    msg.attach(MIMEText(mensaje_cuerpo, "plain"))

    # Adjuntar XML
    xml_attachment = MIMEApplication(xml_bytes, Name=xml_filename)
    xml_attachment["Content-Disposition"] = f'attachment; filename="{xml_filename}"'
    msg.attach(xml_attachment)

    # Adjuntar PDF
    pdf_attachment = MIMEApplication(pdf_bytes, Name=pdf_filename)
    pdf_attachment["Content-Disposition"] = f'attachment; filename="{pdf_filename}"'
    msg.attach(pdf_attachment)

    # Enviar usando aiosmtplib
    await aiosmtplib.send(
        msg,
        hostname=smtp_host,
        port=smtp_port,
        username=smtp_user,
        password=smtp_password,
        use_tls=smtp_use_tls,
        timeout=30,
    )


@app.post("/parsear_xml/", response_model=XmlResponse)
async def parsear_xml(file: UploadFile = File(...)):
    """
    Endpoint que recibe un archivo XML CFDI y lo parsea usando pycfdi-transform.
    Soporta versiones 3.2, 3.3 y 4.0 del CFDI.

    **Parámetros de la Solicitud (multipart/form-data):**
    - `file`: Archivo XML a parsear

    **Respuestas HTTP:**
    - `200 OK`: Retorna un `XmlResponse` con los datos parseados o error
    - `400 Bad Request`: Si el archivo no es válido
    - `413 Payload Too Large`: Si el archivo excede el tamaño máximo
    - `422 Unprocessable Entity`: Si los datos de entrada no cumplen con las validaciones
    - `500 Internal Server Error`: Si ocurre un error inesperado durante el procesamiento
    """
    detected_version = None

    try:
        # Validación 1: Verificar extensión del archivo
        if not file.filename or not file.filename.lower().endswith(".xml"):
            raise HTTPException(
                status_code=400,
                detail="El archivo debe tener extensión .xml",
            )

        # Validación 2: Verificar tamaño del archivo
        if file.size and file.size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo excede el tamaño máximo de {MAX_FILE_SIZE // (1024 * 1024)}MB",
            )

        # Leer contenido del archivo
        content = await file.read()

        # Validación 3: Verificar que no esté vacío
        if not content or len(content) == 0:
            raise HTTPException(
                status_code=400,
                detail="El archivo está vacío",
            )

        # Validación 4: Verificar tamaño real después de leer
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo excede el tamaño máximo de {MAX_FILE_SIZE // (1024 * 1024)}MB",
            )

        # Convertir a string para detección de versión
        xml_content = content.decode("utf-8")

        # Validar que el XML es seguro y está bien formado
        if not validar_xml_seguro(content):
            return XmlResponse(
                exito=False,
                version=None,
                datos=None,
                error="XML malformado o estructura inválida",
            )

        # Detectar la versión del CFDI
        detected_version = detectar_version_cfdi(xml_content)

        if not detected_version:
            return XmlResponse(
                exito=False,
                version=None,
                datos=None,
                error="No se pudo detectar la versión del CFDI",
            )

        # Seleccionar el handler apropiado según la versión
        if detected_version == "3.2":
            transformer = (
                CFDI32SAXHandler().use_concepts_cfdi32().use_ventavehiculos11()
            )
        elif detected_version == "3.3":
            transformer = (
                CFDI33SAXHandler()
                .use_concepts_cfdi33()
                .use_pagos10()
                .use_related_cfdis()
                .use_ventavehiculos11()
            )
        elif detected_version == "4.0":
            transformer = (
                CFDI40SAXHandler()
                .use_concepts_cfdi40()
                .use_pagos20()
                .use_related_cfdis()
                .use_ventavehiculos11()
            )
        else:
            return XmlResponse(
                exito=False,
                version=detected_version,
                datos=None,
                error=f"Versión de CFDI {detected_version} no soportada",
            )

        # Parsear el XML desde el string
        cfdi_data = transformer.transform_from_string(xml_content)

        return XmlResponse(
            exito=True,
            version=detected_version,
            datos=cfdi_data,
            error=None,
        )

    except HTTPException:
        raise

    except Exception as e:
        # Manejar errores de XML malformado o que no es CFDI
        error_msg = str(e)

        # Determinar si es un error de XML malformado
        if "XML" in error_msg.upper() or "PARS" in error_msg.upper():
            error_msg = "XML malformado o no es un CFDI válido"

        return XmlResponse(
            exito=False,
            version=detected_version,
            datos=None,
            error=error_msg,
        )


@app.post("/enviar_archivos_por_correo/", response_model=EmailSendResponse)
async def enviar_archivos_por_correo(
    xml: UploadFile = File(..., description="Archivo XML a adjuntar"),
    pdf: UploadFile = File(..., description="Archivo PDF a adjuntar"),
    email_destino: Annotated[
        EmailStr, Field(description="Correo electrónico destinatario")
    ] = Form(...),
    asunto: Annotated[str, Field(min_length=1, description="Asunto del correo")] = Form(
        ...
    ),
    mensaje_cuerpo: Annotated[
        str,
        Field(default="Archivos adjuntos", description="Cuerpo del mensaje del correo"),
    ] = Form(...),
):
    """
    Endpoint que recibe un archivo XML, un PDF, un correo destino, un asunto y opcionalmente un mensaje cuerpo,
    y envia estos archivos al correo proporcionado.

    **Parámetros de la Solicitud (multipart/form-data):**
    - `xml`: Archivo XML a adjuntar
    - `pdf`: Archivo PDF a adjuntar
    - `email_destino`: Correo electrónico destinatario
    - `asunto`: Asunto del correo
    - `mensaje_cuerpo`: Cuerpo del mensaje (opcional, por defecto "Archivos adjuntos")

    **Respuestas HTTP:**
    - `200 OK`: Retorna un `EmailSendResponse` si el correo fue enviado exitosamente
    - `400 Bad Request`: Si los archivos no son válidos o faltan
    - `413 Payload Too Large`: Si algún archivo excede el tamaño máximo
    - `422 Unprocessable Entity`: Si los datos de entrada no cumplen con las validaciones
    - `500 Internal Server Error`: Si ocurre un error durante el envío del correo
    """
    id_operacion = uuid_lib.uuid4()

    try:
        # Validación 1: Verificar extensión de archivos
        if not xml.filename or not xml.filename.lower().endswith(".xml"):
            raise HTTPException(
                status_code=400,
                detail="El archivo XML debe tener extensión .xml",
            )

        if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="El archivo PDF debe tener extensión .pdf",
            )

        # Validación 2: Verificar tamaño de archivos
        for archivo, nombre in [(xml, "XML"), (pdf, "PDF")]:
            if archivo.size and archivo.size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"El archivo {nombre} excede el tamaño máximo de {MAX_FILE_SIZE // (1024 * 1024)}MB",
                )

        # Leer contenido de archivos
        xml_content = await xml.read()
        pdf_content = await pdf.read()

        # Validación 3: Verificar que no estén vacíos
        if not xml_content or len(xml_content) == 0:
            raise HTTPException(
                status_code=400,
                detail="El archivo XML está vacío",
            )

        if not pdf_content or len(pdf_content) == 0:
            raise HTTPException(
                status_code=400,
                detail="El archivo PDF está vacío",
            )

        # Validación 4: Verificar tamaño real después de leer
        if len(xml_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo XML excede el tamaño máximo de {MAX_FILE_SIZE // (1024 * 1024)}MB",
            )

        if len(pdf_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo PDF excede el tamaño máximo de {MAX_FILE_SIZE // (1024 * 1024)}MB",
            )

        # Validar que el XML es seguro y está bien formado
        if not validar_xml_seguro(xml_content):
            return EmailSendResponse(
                exito=False,
                mensaje="El archivo XML no es válido",
                error="XML malformado o estructura inválida",
                id_operacion=id_operacion,
            )

        # Enviar email con los archivos adjuntos
        await enviar_email_con_adjuntos(
            email_destino=email_destino,
            asunto=asunto,
            mensaje_cuerpo=mensaje_cuerpo,
            xml_bytes=xml_content,
            xml_filename=xml.filename,
            pdf_bytes=pdf_content,
            pdf_filename=pdf.filename,
        )

        return EmailSendResponse(
            exito=True,
            mensaje=f"Correo enviado exitosamente a {email_destino}",
            error=None,
            id_operacion=id_operacion,
        )

    except HTTPException:
        raise

    except ValueError as ve:
        return EmailSendResponse(
            exito=False,
            mensaje="Error de configuración SMTP",
            error=str(ve),
            id_operacion=id_operacion,
        )

    except Exception as e:
        traceback_str = "".join(traceback.format_exception(None, e, e.__traceback__))
        print(f"ERROR durante envío de correo: {traceback_str}")
        return EmailSendResponse(
            exito=False,
            mensaje="Error al enviar el correo",
            error=str(e),
            id_operacion=id_operacion,
        )


@app.post("/llenar_padron/")
async def llenar_padron(request: PdfFormRequest):
    """
    Endpoint que recibe datos para llenar el formulario PDF V1J AUTO
    y retorna el PDF generado con los campos llenos.

    **Parámetros de la Solicitud (JSON):**
    - Todos los campos del formulario son opcionales
    - Campos de texto: valores string
    - Campos de checkbox: valores boolean

    **Respuestas HTTP:**
    - `200 OK`: Retorna el PDF generado con Content-Type: application/pdf
    - `422 Unprocessable Entity`: Si los datos de entrada no cumplen con las validaciones
    - `500 Internal Server Error`: Si ocurre un error durante la generación del PDF
    """
    try:
        # Ruta al PDF template
        pdf_template_path = os.path.join(
            os.path.dirname(__file__), "..", "FORMATO V1J AUTO.pdf"
        )

        # Verificar que el PDF template existe
        if not os.path.exists(pdf_template_path):
            raise HTTPException(
                status_code=404,
                detail="No se encontró el archivo PDF template",
            )

        # Convertir el modelo Pydantic a diccionario
        datos_formulario = request.model_dump()

        # Llenar el formulario PDF
        pdf_content = llenar_formulario_pdf(pdf_template_path, datos_formulario)

        # Retornar el PDF generado
        from fastapi.responses import Response

        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=FORMATO_V1J_AUTO_LLENO.pdf"
            },
        )

    except HTTPException:
        raise

    except Exception as e:
        traceback_str = "".join(traceback.format_exception(None, e, e.__traceback__))
        print(f"ERROR durante generación de PDF: {traceback_str}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor al generar el PDF: {str(e)}",
        )


MOTIVOS_CANCELACION = {
    "01": "Comprobante emitido con errores con relación",
    "02": "Comprobante emitido con errores sin relación",
    "03": "No se llevó a cabo la operación",
    "04": "Operación nominativa relacionada en la factura",
}

MOTIVOS_REQUIERE_SUSTITUCION = ["01"]


@app.post("/cancelar_factura/", response_model=CancelacionResponse)
async def cancelar_factura(request: CancelacionRequest):
    """
    Endpoint que cancela facturas CFDI 4.0 usando el servicio de MySuite.

    **Parámetros de la Solicitud (JSON):**
    - `rfc`: RFC del emisor (12 o 13 caracteres)
    - `tipo`: Tipo de CFDI ("emitidos" o "recibidos")
    - `uuids`: Lista de UUIDs de los comprobantes a cancelar
    - `foliosSustitucion`: UUIDs de los CFDI que sustituyen al cancelado (opcional, requerido si motivo es "01")
    - `motivo`: Código de motivo de cancelación (01, 02, 03, 04)

    **Códigos de motivo:**
    - "01": Comprobante emitido con errores con relación (requiere foliosSustitucion)
    - "02": Comprobante emitido con errores sin relación
    - "03": No se llevó a cabo la operación
    - "04": Operación nominativa relacionada en la factura

    **Respuestas HTTP:**
    - `200 OK`: Retorna un `CancelacionResponse` con el resultado de la cancelación
    - `400 Bad Request`: Si los parámetros son inválidos
    - `422 Unprocessable Entity`: Si los datos de entrada no cumplen con las validaciones
    - `500 Internal Server Error`: Si ocurre un error durante el proceso
    """
    id_operacion = uuid_lib.uuid4()

    try:
        motivo = request.motivo
        if motivo not in MOTIVOS_CANCELACION:
            return CancelacionResponse(
                exito=False,
                mensaje=f"Motivo de cancelación inválido: {motivo}",
                resultado=None,
                id_operacion=id_operacion,
                error=f"Motivos válidos: {', '.join(MOTIVOS_CANCELACION.keys())}",
            )

        if motivo in MOTIVOS_REQUIERE_SUSTITUCION and not request.foliosSustitucion:
            return CancelacionResponse(
                exito=False,
                mensaje="El motivo de cancelación requiere folios de sustitución",
                resultado=None,
                id_operacion=id_operacion,
                error=f"El motivo '{motivo}' ({MOTIVOS_CANCELACION[motivo]}) requiere especificar foliosSustitucion",
            )

        mysuite_url = os.getenv("MYSUITE_URL")
        mysuite_token = os.getenv("MYSUITE_TOKEN")

        if not mysuite_url or not mysuite_token:
            return CancelacionResponse(
                exito=False,
                mensaje="Configuración incompleta de MySuite",
                resultado=None,
                id_operacion=id_operacion,
                error="Faltan las variables de entorno MYSUITE_URL o MYSUITE_TOKEN",
            )

        tipo = request.tipo.lower()
        if tipo not in ["emitidos", "recibidos"]:
            return CancelacionResponse(
                exito=False,
                mensaje="Tipo de CFDI inválido",
                resultado=None,
                id_operacion=id_operacion,
                error="El tipo debe ser 'emitidos' o 'recibidos'",
            )

        url = f"{mysuite_url}/cfdi40/{request.rfc}/{tipo}/cancelar"

        payload = {
            "uuids": request.uuids,
            "foliosSustitucion": request.foliosSustitucion,
            "motivo": request.motivo,
        }

        headers = {
            "Authorization": f"Bearer {mysuite_token}",
            "Content-Type": "application/json",
        }

        response = requests.post(url, json=payload, headers=headers, timeout=60)

        if response.status_code == 200:
            try:
                resultado = response.json()
                return CancelacionResponse(
                    exito=True,
                    mensaje="Factura(s) cancelada(s) exitosamente",
                    resultado=resultado,
                    id_operacion=id_operacion,
                    error=None,
                )
            except Exception:
                return CancelacionResponse(
                    exito=True,
                    mensaje="Factura(s) cancelada(s) exitosamente",
                    resultado={"raw_response": response.text},
                    id_operacion=id_operacion,
                    error=None,
                )
        elif response.status_code == 400:
            return CancelacionResponse(
                exito=False,
                mensaje="Error en la solicitud de cancelación",
                resultado=None,
                id_operacion=id_operacion,
                error=f"Error 400: {response.text}",
            )
        elif response.status_code == 401:
            return CancelacionResponse(
                exito=False,
                mensaje="Error de autenticación con MySuite",
                resultado=None,
                id_operacion=id_operacion,
                error="Token de MySuite inválido o expirado",
            )
        elif response.status_code == 403:
            return CancelacionResponse(
                exito=False,
                mensaje="Permisos insuficientes",
                resultado=None,
                id_operacion=id_operacion,
                error="No tienes permisos para cancelar facturas en MySuite",
            )
        else:
            return CancelacionResponse(
                exito=False,
                mensaje="Error al cancelar la factura",
                resultado=None,
                id_operacion=id_operacion,
                error=f"Error {response.status_code}: {response.text}",
            )

    except requests.exceptions.Timeout:
        return CancelacionResponse(
            exito=False,
            mensaje="Tiempo de espera agotado al conectar con MySuite",
            resultado=None,
            id_operacion=id_operacion,
            error="La solicitud tardó más de 60 segundos",
        )
    except requests.exceptions.ConnectionError:
        return CancelacionResponse(
            exito=False,
            mensaje="Error de conexión con MySuite",
            resultado=None,
            id_operacion=id_operacion,
            error="No se pudo conectar al servidor de MySuite",
        )
    except Exception as e:
        traceback_str = "".join(traceback.format_exception(None, e, e.__traceback__))
        print(f"ERROR durante cancelación: {traceback_str}")
        return CancelacionResponse(
            exito=False,
            mensaje="Error interno del servidor",
            resultado=None,
            id_operacion=id_operacion,
            error=str(e),
        )


# --- Instrucciones para Ejecutar la Aplicación ---
# Para ejecutar esta aplicación:
# 1. Guarda el código en un archivo Python (ej. main.py).
# 2. Asegúrate de tener FastAPI y Uvicorn instalados:
#    pip install fastapi "uvicorn[standard]"
# 3. Ejecuta la aplicación desde tu terminal en el mismo directorio:
#    uvicorn main:app --reload

# Una vez en ejecución, puedes acceder a:
# - La documentación interactiva de la API (Swagger UI): http://127.0.0.1:8000/docs
# - El endpoint para enviar solicitudes POST: http://127.0.0.1:8000/validar_factura/
