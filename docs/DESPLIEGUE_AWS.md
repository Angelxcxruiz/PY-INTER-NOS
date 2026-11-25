# Despliegue AWS

## Base de datos

Crear Amazon RDS for MySQL 8 en subred privada, copias de seguridad automáticas,
Multi-AZ opcional y Security Group que permita tráfico solo desde EC2/ECS.
La aplicación usa `DATABASE_URL` con el usuario y secreto administrado por AWS.

La migración `0012_triggers_vistas` crea triggers y un procedimiento. En RDS, que mantiene el
registro binario activo, hay que poner `log_bin_trust_function_creators = 1` en el *parameter
group* de la instancia (no hace falta reiniciar); de lo contrario la migración falla con el error
1419 porque el usuario de la aplicación no tiene `SUPER`.

## Imagen

Construir la imagen Docker y subirla a Amazon ECR. Cada despliegue usa una etiqueta
inmutable o el hash del commit.

## Ejecución

### EC2 con Docker Compose

Es la opción recomendada para el proyecto académico por su bajo costo:

- EC2 en subred privada o pública según HTTPS.
- Docker Compose ejecuta `api` y `worker`.
- Nginx con Let's Encrypt o Application Load Balancer con ACM proporciona HTTPS.
- El arranque de API espera RDS y ejecuta Alembic.

### ECS Fargate

Alternativa sin administración de servidores:

- Servicios separados para API y worker.
- Tareas con imágenes de ECR.
- RDS accesible desde los Security Groups de las tareas.

## Correo

Amazon SES requiere dominio o remitente verificado y `EMAIL_BACKEND=smtp`.
Configurar credenciales SMTP mediante Secrets Manager o SSM Parameter Store.

## Secretos

Usar AWS Secrets Manager o SSM Parameter Store para `JWT_SECRET`, `FERNET_KEY`,
contraseñas de base de datos y SMTP. No copiar secretos en la imagen ni en
variables públicas de GitHub Actions.

## Seguridad de red

- RDS no expuesto a Internet.
- Security Group de RDS: solo puerto 3306 desde API/worker.
- ALB: solo puertos 80 y 443.
- EC2: SSH limitado a una IP administradora.
- HTTPS obligatorio.

## Observabilidad

Enviar stdout/stderr a Amazon CloudWatch Logs. Crear alarmas para API, worker,
fallos de base de datos y fallos SMTP.

## GitHub Actions

- En cada pull request: lint, formato, migraciones y pruebas.
- En merge a `main`: build, push a ECR y despliegue manual o automatizado.
