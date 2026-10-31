// Segmentador de Clientes: algoritmo para recalcular los grupos con K-means.
// Sigue la receta de modelo.py (entrenar): logaritmo, estandarizacion, K-means con
// 20 inicios distintos y renumeracion de los grupos por valor medio.
// La silueta y el indice de Davies-Bouldin los calcula el programa con scikit-learn.
// Abrir en PSeInt y usar "Dibujar diagrama de flujo" para ver el diagrama.
Algoritmo RecalcularGruposKMeans
	Definir n, k, i, j, d, a, b, g, intento, iteracion, cambios, grupo Como Entero
	Definir r, f, m, suma, distancia, mejorDistancia, inercia, mejorInercia Como Real
	Definir x, media, escala, centro, valorTotal, valorMedio Como Real
	Definir asignado, mejorAsignado, cuantos, orden, nuevoNumero Como Entero
	Dimension x[5000,3], valorTotal[5000], asignado[5000], mejorAsignado[5000]
	Dimension media[3], escala[3]
	Dimension centro[8,3], cuantos[8], valorMedio[8], orden[8], nuevoNumero[8]

	Escribir "Cuantos clientes hay (minimo 2)?"
	Leer n
	Repetir
		Escribir "Numero de grupos k (2 a 8):"
		Leer k
		Si k < 2 O k > 8 O k > n Entonces
			Escribir "Rechazado: k debe estar entre 2 y 8 y no puede pasar del numero de clientes."
		FinSi
	Hasta Que k >= 2 Y k <= 8 Y k <= n

	// 1. Variables: logaritmo de (1 + recencia), (1 + frecuencia) y (1 + valor total)
	Para i <- 1 Hasta n Hacer
		Escribir "Cliente ", i, ": recencia, frecuencia y valor total"
		Leer r, f, m
		valorTotal[i] <- m
		x[i,1] <- ln(1 + r)
		x[i,2] <- ln(1 + f)
		x[i,3] <- ln(1 + m)
	FinPara

	// 2. Estandarizar cada variable: media 0 y desviacion 1
	Para d <- 1 Hasta 3 Hacer
		suma <- 0
		Para i <- 1 Hasta n Hacer
			suma <- suma + x[i,d]
		FinPara
		media[d] <- suma / n
		suma <- 0
		Para i <- 1 Hasta n Hacer
			suma <- suma + (x[i,d] - media[d])^2
		FinPara
		escala[d] <- rc(suma / n)
		Si escala[d] = 0 Entonces
			escala[d] <- 1
		FinSi
		Para i <- 1 Hasta n Hacer
			x[i,d] <- (x[i,d] - media[d]) / escala[d]
		FinPara
	FinPara

	// 3. K-means con 20 inicios distintos; se queda el de menor inercia
	mejorInercia <- -1
	Para intento <- 1 Hasta 20 Hacer
		// Centros iniciales: k clientes escogidos al azar
		Para j <- 1 Hasta k Hacer
			a <- azar(n) + 1
			Para d <- 1 Hasta 3 Hacer
				centro[j,d] <- x[a,d]
			FinPara
		FinPara
		Para i <- 1 Hasta n Hacer
			asignado[i] <- 0
		FinPara
		iteracion <- 0
		Repetir
			// 3a. Asignar cada cliente al centro mas cercano
			cambios <- 0
			Para i <- 1 Hasta n Hacer
				grupo <- 1
				mejorDistancia <- -1
				Para j <- 1 Hasta k Hacer
					distancia <- 0
					Para d <- 1 Hasta 3 Hacer
						distancia <- distancia + (x[i,d] - centro[j,d])^2
					FinPara
					Si mejorDistancia < 0 O distancia < mejorDistancia Entonces
						mejorDistancia <- distancia
						grupo <- j
					FinSi
				FinPara
				Si asignado[i] <> grupo Entonces
					asignado[i] <- grupo
					cambios <- cambios + 1
				FinSi
			FinPara
			// 3b. Mover cada centro al promedio de sus clientes
			Para j <- 1 Hasta k Hacer
				cuantos[j] <- 0
				Para d <- 1 Hasta 3 Hacer
					centro[j,d] <- 0
				FinPara
			FinPara
			Para i <- 1 Hasta n Hacer
				g <- asignado[i]
				cuantos[g] <- cuantos[g] + 1
				Para d <- 1 Hasta 3 Hacer
					centro[g,d] <- centro[g,d] + x[i,d]
				FinPara
			FinPara
			Para j <- 1 Hasta k Hacer
				Si cuantos[j] > 0 Entonces
					Para d <- 1 Hasta 3 Hacer
						centro[j,d] <- centro[j,d] / cuantos[j]
					FinPara
				FinSi
			FinPara
			iteracion <- iteracion + 1
		Hasta Que cambios = 0 O iteracion = 300

		// 3c. Inercia: suma de distancias al cuadrado de cada cliente a su centro
		inercia <- 0
		Para i <- 1 Hasta n Hacer
			Para d <- 1 Hasta 3 Hacer
				inercia <- inercia + (x[i,d] - centro[asignado[i],d])^2
			FinPara
		FinPara
		Si mejorInercia < 0 O inercia < mejorInercia Entonces
			mejorInercia <- inercia
			Para i <- 1 Hasta n Hacer
				mejorAsignado[i] <- asignado[i]
			FinPara
		FinSi
	FinPara

	// 4. Renumerar: el grupo 1 es el de mayor valor total medio
	Para j <- 1 Hasta k Hacer
		valorMedio[j] <- 0
		cuantos[j] <- 0
		orden[j] <- j
	FinPara
	Para i <- 1 Hasta n Hacer
		g <- mejorAsignado[i]
		valorMedio[g] <- valorMedio[g] + valorTotal[i]
		cuantos[g] <- cuantos[g] + 1
	FinPara
	Para j <- 1 Hasta k Hacer
		Si cuantos[j] > 0 Entonces
			valorMedio[j] <- valorMedio[j] / cuantos[j]
		FinSi
	FinPara
	// Ordenamiento burbuja de mayor a menor valor medio
	Para a <- 1 Hasta k - 1 Hacer
		Para b <- 1 Hasta k - a Hacer
			Si valorMedio[orden[b]] < valorMedio[orden[b + 1]] Entonces
				g <- orden[b]
				orden[b] <- orden[b + 1]
				orden[b + 1] <- g
			FinSi
		FinPara
	FinPara
	Para a <- 1 Hasta k Hacer
		nuevoNumero[orden[a]] <- a
	FinPara

	// 5. Resultado
	Escribir "Inercia del mejor intento: ", mejorInercia
	Para a <- 1 Hasta k Hacer
		Escribir "Grupo ", a, ": ", cuantos[orden[a]], " clientes, valor medio ", valorMedio[orden[a]], " libras"
	FinPara
	Para i <- 1 Hasta n Hacer
		Escribir "Cliente ", i, " queda en el grupo ", nuevoNumero[mejorAsignado[i]]
	FinPara
FinAlgoritmo
