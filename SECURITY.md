# Política de seguridad

## Versiones con soporte

| Versión | Soporte |
|---|---|
| 1.x | Sí |

## Cómo comunicar una vulnerabilidad

No abras una incidencia pública. Usa la opción **Report a vulnerability** de la
pestaña *Security* de este repositorio (informe privado de GitHub). Recibirás
respuesta en un plazo razonable y se coordinará contigo la publicación del
arreglo.

## Alcance

Este recolector accede únicamente a información publicada abiertamente por el
Portal de Subastas del BOE. Los datos sensibles que maneja son los del usuario
que lo ejecuta: las credenciales del portal (variables de entorno) y el
fichero de sesión (`session.json`, creado con permisos restrictivos). Cualquier
comportamiento que exponga esos datos —en la salida, en los registros o en
ficheros— se considera una vulnerabilidad.
