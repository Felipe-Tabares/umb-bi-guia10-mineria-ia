// Segmentador de Clientes: algoritmo para agregar un cliente con validacion.
// Es la misma secuencia de reglas de validacion.py y de Almacen.agregar en datos.py.
// Abrir en PSeInt y usar "Dibujar diagrama de flujo" para ver el diagrama.
Algoritmo AgregarCliente
	Definir codigo, pais, estado, mercado, mensaje Como Caracter
	Definir codigos Como Caracter
	Definir recencia, frecuencia, valor, unidades, productos Como Real
	Definir ticket, distancia, mejor, zr, zf, zm Como Real
	Definir media, escala, centroide Como Real
	Definir k, i, j, n, grupo Como Entero
	Definir valido, repetido Como Logico
	Dimension codigos[5000]
	Dimension media[3], escala[3]
	Dimension centroide[8,3]

	// Modelo K-means vigente. En el programa sale de la base de datos;
	// aqui se digita para poder seguir el algoritmo a mano.
	Escribir "Numero de grupos del modelo vigente (k):"
	Leer k
	Para i <- 1 Hasta 3 Hacer
		Escribir "Media y desviacion de la variable ", i, " (1 recencia, 2 frecuencia, 3 valor, en logaritmo):"
		Leer media[i], escala[i]
	FinPara
	Para j <- 1 Hasta k Hacer
		Para i <- 1 Hasta 3 Hacer
			Escribir "Centroide del grupo ", j, ", coordenada ", i, ":"
			Leer centroide[j,i]
		FinPara
	FinPara
	n <- 0

	Repetir
		Escribir "Codigo del cliente (FIN para terminar):"
		Leer codigo
		Si codigo <> "FIN" Entonces
			Escribir "Pais:"
			Leer pais
			Escribir "Recencia (dias desde la ultima compra):"
			Leer recencia
			Escribir "Frecuencia (compras distintas):"
			Leer frecuencia
			Escribir "Valor total en libras:"
			Leer valor
			Escribir "Unidades compradas (0 si no se conocen):"
			Leer unidades
			Escribir "Productos distintos (0 si no se conocen):"
			Leer productos

			valido <- Verdadero
			mensaje <- ""

			// 1. Codigo obligatorio, maximo 20 caracteres y sin repetir
			Si Longitud(codigo) = 0 O Longitud(codigo) > 20 Entonces
				valido <- Falso
				mensaje <- "Escriba el codigo del cliente (maximo 20 caracteres)."
			FinSi
			Si valido Entonces
				repetido <- Falso
				Para i <- 1 Hasta n Hacer
					Si codigos[i] = codigo Entonces
						repetido <- Verdadero
					FinSi
				FinPara
				Si repetido Entonces
					valido <- Falso
					mensaje <- Concatenar("Ya existe el cliente ", codigo)
				FinSi
			FinSi

			// 2. Pais obligatorio
			Si valido Y Longitud(pais) = 0 Entonces
				valido <- Falso
				mensaje <- "Escriba el pais del cliente."
			FinSi

			// 3. Recencia entera entre 0 y 3650 dias
			Si valido Y (recencia < 0 O recencia > 3650 O recencia <> trunc(recencia)) Entonces
				valido <- Falso
				mensaje <- "La recencia debe ser un numero entero entre 0 y 3650."
			FinSi

			// 4. Frecuencia entera desde 1
			Si valido Y (frecuencia < 1 O frecuencia <> trunc(frecuencia)) Entonces
				valido <- Falso
				mensaje <- "La frecuencia debe ser un numero entero mayor o igual a 1."
			FinSi

			// 5. Valor total mayor que cero
			Si valido Y valor <= 0 Entonces
				valido <- Falso
				mensaje <- "El valor total debe ser mayor que 0."
			FinSi

			// 6. Unidades y productos enteros desde 0, y no mas productos que unidades
			Si valido Y (unidades < 0 O productos < 0 O unidades <> trunc(unidades) O productos <> trunc(productos)) Entonces
				valido <- Falso
				mensaje <- "Unidades y productos deben ser enteros mayores o iguales a 0."
			FinSi
			Si valido Y unidades > 0 Y productos > unidades Entonces
				valido <- Falso
				mensaje <- "Los productos distintos no pueden ser mas que las unidades compradas."
			FinSi

			Si NO valido Entonces
				Escribir "Rechazado: ", mensaje
				Escribir "No se guardo nada."
			SiNo
				// 7. Campos que el programa calcula solo
				Si recencia <= 90 Entonces
					estado <- "Activo"
				SiNo
					estado <- "Inactivo"
				FinSi
				Si Minusculas(pais) = "united kingdom" O Minusculas(pais) = "reino unido" Entonces
					mercado <- "Reino Unido"
				SiNo
					mercado <- "Internacional"
				FinSi
				ticket <- valor / frecuencia

				// 8. Grupo: centroide mas cercano con las variables estandarizadas
				zr <- (ln(1 + recencia) - media[1]) / escala[1]
				zf <- (ln(1 + frecuencia) - media[2]) / escala[2]
				zm <- (ln(1 + valor) - media[3]) / escala[3]
				grupo <- 1
				mejor <- -1
				Para j <- 1 Hasta k Hacer
					distancia <- (zr - centroide[j,1])^2 + (zf - centroide[j,2])^2 + (zm - centroide[j,3])^2
					Si mejor < 0 O distancia < mejor Entonces
						mejor <- distancia
						grupo <- j
					FinSi
				FinPara

				// 9. Guardar y dejar constancia
				n <- n + 1
				codigos[n] <- codigo
				Escribir "Guardado el cliente ", codigo, " (", pais, ", ", mercado, ")."
				Escribir "Estado: ", estado, ". Ticket promedio: ", ticket, " libras. Grupo asignado: ", grupo
				Escribir "Se registra en la bitacora y se redibujan la tabla y la grafica."
			FinSi
		FinSi
	Hasta Que codigo = "FIN"
FinAlgoritmo
