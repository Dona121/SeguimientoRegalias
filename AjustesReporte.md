En este archivo se encuentra el registro de cambios que debes realizar. Cuando realices un cambio agrega al inicio el texto: REALIZADO.

REALIZADO 0. Agregué una nueva versión del excel donde podrás encontrar la columna del punto 3. Esta nueva versión ahora incluye los siguientes ajustes:
    - Se realizó el siguiente cambio en el nombre de la columna: FECHA DE SUSCRIPCION -> FECHA DE SUSCRIPCIÓN DEL CONTRATO PRINCIPAL
    - Se agregó la columna: FECHA DE SUSCRIPCIÓN DEL PRIMER CONTRATO
REALIZADO 1. En hito 5 (H5) - En ejecución rezagado quita la condición CPI = 0 y SPI = 0. El resto de condiciones en este hito se mantienen iguales.
REALIZADO 2. Debajo de la descripción del hito cero (H0) en la vista guia de hitos agrega la imagen EficienciaContratacion.png que se encuentra en la carpeta static. Asegurate que tanto la imagen como la descripción queden en un solo recuadro.
REALIZADO 3. Agrega un nuevo hito: H7 - Proyectos suspendidos. Con las siguientes condiciones:
    c1 - Estado del proyecto = CONTRATADO EN EJECUCIÓN
    c2 - Al menos un contrato del proyecto se encuentra suspendido: Te puedes apoyar con el archivo de CG-cttos. Tienes que revisar si al menos uno de los contratos del proyecto se encuentra en estado suspendido. La estrategia que vayas a usar me la compartes. A mi se me ocurre agregar una columna condicionada al estado del contrato (si estado == suspendido entonces 1, luego te apoyas con una función de venta usando sum() y si la suma da mas de 1 entonces el proyecto aplica. Sin mebargo, si encuentras una forma mas eficiente de hacerlo me la compartes). Este hito por lo pronto agregalo solo en MatrizSeguimientoEvaluacion, ya que aun no contamos con archivo de contratos para descentralizadas.
    c3 - Este hito se mide como número de proyectos y no tiene asociado semaforos.
REALIZADO 4. Agrega un nuevo hito: H8 - Proyecto para cierre. Con las siguientes condiciones:
    c1 - Estado del proyecto = PARA CIERRE
    c2-  Deben existir los siguientes datos para que se realice el calculo: FECHA EN LA QUE PASO A ESTADO PARA CIERRE, FECHA DE CORTE GESPROY Y FECHA ACTUAL (esa la generas de forma automatica). Para cada proyecto realizas la siguiente operacion FECHA DE CORTE GESPROY/FECHA ACTUAL - FECHA EN LA QUE PASO A ESTADO PARA CIERRE en dias totales y luego promedias los días por dependencia.
    c3 - Este hito se mide como promedio de días de los proyectos que se calculen la c2 y no tiene asociado semaforos.
REALIZADO 5. Quita del panel izquierdo las opciones de cargar el excel de seguimiento y el archivo de contratos. Estos archivos se van a tomar de ahora en adelante del repositorio en el cual se está haciendo cargue. Solo deja los botones de recargar datos del repositorio y de exportar
REALIZADO 6. Agrega un boton adicional debajo de exportar que lleve al siguiente enlace: https://consolidacionregalias.streamlit.app/
REALIZADO 7. Revisa la carpeta capturas_pantalla, ahí cargué una imagen de como se ven los hitos H1 al H8 en la vista guia de hitos. El contenedor está bien organizado, sin embargo, debajo del nombre del hito muestra una etiqueta div y el color de la tarjeta quedó complemente en azul, afectando el contraste con el texto.
REALIZADO 8. Revisa la carpeta capturas_pantalla la imagen BotonConsolidacion.png. Debes ajustar el color y letra del boton
REALIZADO 9. Asegurate de que los nuevos hitos agregados aparezcan en la sección DETALLE POR HITO
REALIZADO 10. Revisa el datelle del hito 7. En Días (pasar el cursor) aparecen elementos HTML
REALIZADO 11. Las ultimas dos columnas: Suspendidos, Para cierre los cuales solo estan contando los proyectos en ese estado, dejalos ocultos. Comenta el codigo correspondiente a estas ultimas dos columnas.


Notas: 
    - El archivo de CG-cttos se debe subir si o si siempre. Así que en caso de que no se suba. Generado un mensaje al entrar en la pagina solictando al usuario el cargue del archivo. Respecto al hito 5 y 7 
    - Si se quita CPI/SPI, un proyecto en ejecución con horizonte vencido y con contrato suspendido podría estar en H5 y H7 a la vez. En ese caso excluye los suspendidos del hito 5